#!/usr/bin/env python3
"""PreToolUse hook for the docs topology — the BASH half of the path-lock.

WHY THIS EXISTS
---------------
`path-lock.py` gates Edit / Write / MultiEdit / NotebookEdit. It does NOT see
Bash. An agent whose Write is blocked can reach for the shell — `sed -i`,
`cat > file`, `tee`, a heredoc — and land the exact write the path-lock was
meant to stop. That is not a hypothetical: a lead once edited source via Bash
because Write was locked and Bash wasn't. The artifact happened to be correct,
so nothing in the pipeline flagged it. A control enforced on one tool but not
its equivalent is not a control.

This hook is the SECOND lock. It reuses path-lock.py's per-agent allowlist
(single source of truth — never re-declare globs here) and applies it to
shell-level writes.

FOUR BUCKETS — deny-by-default (Layer 1, since 2026-09-25)
----------------------------------------------------------
Until then the hook asked "does this command look like a known write?" and
let the rest through. The rest included `python3 -c "open('src/main/...','w')"`:
exactly what a qa-engineer used in WEGO-1936 after having its `cp` blocked.
Now the question is "is this command provably harmless?". Every command
segment of a locked agent falls into exactly one bucket:

1. ANALYZABLE WRITER — the target is on the line (redirect, tee, cp, mv, sed -i,
   mkdir, rm, ln, sort -o, git mv/checkout --/restore...). Target inside the
   root and outside the agent's globs → DENY.
2. HARMLESS VERB — audited list (_SIMPLE, _HANDLERS), each verb with the flags
   that make it a writer/executor denied (sed -i/w/e, find -exec/-delete,
   git reset --hard/stash/apply, npm exec, npx -c, mvn exec:...).
3. OUTSIDE THE JURISDICTION — the segment runs in a directory outside the root
   (the disposable perturbation worktree: `cd "$D/red" && ...`,
   `git -C /tmp/x ...`) and nothing on the line cites the root → everything
   allowed. It is the same out-of-root carve-out as path-lock.py, which the
   proof-reviewer's perturbation needs.
4. EVERYTHING ELSE → DENY. Inline interpreter, nested shell, heredoc/pipe to an
   interpreter, script outside the project or inside the agent's own lane —
   except inside a worktree of this repo (the disposable perturbation copy),
   which is bucket 3 jurisdiction —, xargs with a writer, a verb nobody
   listed. A new vector falls here by construction.

Command substitution (`$(...)`, backtick, `<(...)`) is another command and is
classified with the same rules before the segment that contains it. A `cd`
only takes out of the root the segments linked to it by `&&` (with `;` or `||`
the cd may have failed; in `|` and subshell it does not hold outside).

Main session / built-in agents (no plugin-prefixed agent_type) are NOT gated —
same fail-open contract as path-lock.py.

Shadow mode: CEPA_BASHLOCK_ENFORCE=0 lets bucket 4 through and records
`bash_pathlock_would_deny` in the telemetry ledger (bucket 1 is never
loosened). Every denial records `bash_pathlock_deny`; `git worktree add`
outside the root records `perturb_worktree_created`. The orphan log in /tmp
that nobody read is dead.

HONEST LIMITS (guardrail, not sandbox)
--------------------------------------
- PREVENTS: a shell write with a visible target outside the lane, and execution
  of unsanctioned code at the moment of the Bash call (the vector does not even
  run).
- DOES NOT SEE: what a harmless verb writes through a SUBPROCESS (`./mvnw test`
  running a test that writes to src/main; `npm test` running a package.json
  script; the lead's `git merge`). That is Layer 2 work (diff-based
  write-fence), not built yet.
- DOES NOT SEE: a root path assembled at runtime from a directory outside it
  (bucket 3 is a string check). Obfuscating after a deny is willful.
- A project script the agent CANNOT write (outside its lane) is treated like
  `npm test`: harmless. A script in /tmp or in its own lane is not.

Exit codes:
  0 — allowed (or out of scope)
  2 — denied: bucket 1 (write outside the lane) or bucket 4 (outside the list)
"""

import importlib.util
import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path

PLUGIN_NAME = "docs"

# ─── reuse path-lock.py as the single source of truth for allowlists ──────────

def _load_pathlock_module():
    """Import the sibling path-lock.py (hyphen in the filename → importlib)."""
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "docs_path_lock", str(here / "path-lock.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Redirection: `>` or `>>`, NOT preceded by a digit or `&` (excludes `2>`,
# `&>`, `1>&2`), and the target must not start with `&` (excludes `>&1`) or `=`
# (excludes the `>=` comparison operator — `>` immediately followed by `=` is
# never a redirect; without this, `sed -i 's/>=/>/'`, `grep '>='`, and
# `[[ $a >= $b ]]` capture junk targets and get falsely blocked).
_REDIR_RE = re.compile(r"""(?<![0-9&])>>?\s*(?![&=])("[^"]+"|'[^']+'|[^\s;&|<>()]+)""")

# Constructs we cannot statically analyze — fail open but log.
_UNCOVERED_RE = re.compile(
    r"""(?:
        \bpython3?\s+-c\b | \bperl\s+-[eE]\b | \bruby\s+-e\b | \bnode\s+-e\b |
        \bawk\b[^|;&]*\b-i\b | \b-i\s+inplace\b | \bgawk\b[^|;&]*\binplace\b |
        \bed\b | \bpatch\b | <<-?\s*['"]?\w+   # heredoc
    )""",
    re.VERBOSE,
)

# Targets that are never real files.
_PSEUDO = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")

# Command separators, applied only OUTSIDE quotes (see _quoted_mask).
_SEP_PAIRS = ("||", "&&")
_SEP_CHARS = ";|&\n"


def _quoted_mask(s: str) -> list:
    """One boolean per character: True where it is inside quotes or escaped.

    It exists because the hook used to read quoted text as if it were shell. The
    real case (22/08/2026, WEGO-2087): `git commit -m "title\n\nbody with A -> B"`.
    The body's `\n` was treated as a command separator, each line of the message
    became a "segment", and the `->` of a sentence matched _REDIR_RE: the hook
    reported a phantom write to `B` and blocked the commit. The dev could only
    commit after shortening the message to one line.

    Unclosed quotes mask the rest of the string: it is fail-open, consistent
    with the hook's contract, and a command with unclosed quotes does not run in
    the shell.

    The body of a heredoc (`<<EOF`, `<<-EOF`, `<<'EOF'`) is also data, not
    shell, and is masked too. Same defect as the quotes, one step further and
    measured on 04/09/2026: a commit message passed via
    `git commit -F - <<'MSG'` that QUOTED `while true` made `no-busy-wait`
    block the commit as if it were a busy wait. The quote was inside the body,
    not on a command line. A here-string (`<<<`) does not open a body and is
    left out.
    """
    mask = [False] * len(s)
    quote = None
    pending_heredocs = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if quote is None:
            # The body of a heredoc announced on this line starts after the
            # line break and runs to the delimiter line. None of it is
            # shell, it is data.
            if c == "\n" and pending_heredocs:
                j = i + 1
                for delim, strip_tabs in pending_heredocs:
                    while j < n:
                        line_end = s.find("\n", j)
                        if line_end == -1:
                            line_end = n
                        line = s[j:line_end]
                        j = line_end + 1 if line_end < n else n
                        if (line.lstrip("\t") if strip_tabs else line).strip() == delim:
                            break
                # The line break that OPENS the body goes into the mask too:
                # it is still a command separator for `_split_segments`, and
                # without it the whole body became a "second command", which
                # is exactly how the body's prose came to be read as shell again.
                for p in range(i, min(j, n)):
                    mask[p] = True
                pending_heredocs = []
                i = min(j, n)
                continue
            if s[i:i + 2] == "<<" and s[i:i + 3] != "<<<":
                k = i + 2
                strip_tabs = k < n and s[k] == "-"
                if strip_tabs:
                    k += 1
                while k < n and s[k] in " \t":
                    k += 1
                quoted = s[k] if k < n and s[k] in "\"'" else None
                if quoted:
                    k += 1
                delim_start = k
                while k < n and (s[k].isalnum() or s[k] in "_-."):
                    k += 1
                delim = s[delim_start:k]
                if quoted and k < n and s[k] == quoted:
                    k += 1
                if delim:
                    # The operator and the delimiter stay VISIBLE on purpose:
                    # `cat <<EOF > out.txt` writes, and it is the `<<` in the
                    # unquoted view that sustains the "cannot analyze this"
                    # signal (_UNCOVERED_RE). Only the BODY is data. Masking
                    # the operator too would erase the signal and the heredoc
                    # would start writing silently.
                    pending_heredocs.append((delim, strip_tabs))
                    i = k
                    continue
            if c == "\\":
                mask[i] = True
                if i + 1 < n:
                    mask[i + 1] = True
                i += 2
                continue
            if c in "\"'":
                quote = c
                mask[i] = True
            i += 1
            continue
        mask[i] = True
        if quote == '"' and c == "\\":
            if i + 1 < n:
                mask[i + 1] = True
            i += 2
            continue
        if c == quote:
            quote = None
        i += 1
    return mask


def _split_segments(command: str) -> list:
    """Splits into command segments, ignoring separators inside quotes."""
    mask = _quoted_mask(command)
    segments = []
    start = i = 0
    n = len(command)
    while i < n:
        if mask[i]:
            i += 1
            continue
        if command[i:i + 2] in _SEP_PAIRS:
            segments.append(command[start:i])
            i += 2
            start = i
            continue
        if command[i] in _SEP_CHARS:
            segments.append(command[start:i])
            i += 1
            start = i
            continue
        i += 1
    segments.append(command[start:])
    return segments


# A whole redirection: optional descriptor (`2>`), operator, optional `&`
# (`>&2`) and the operand. It serves only to ERASE the redirection before
# tokenizing the command: `tee out.txt < in.txt` used to tokenize as
# `["tee", "out.txt", "<", "in.txt"]`, and the `tee` rule (every argument that
# is not a flag is written) recorded `<` and `in.txt` as write targets.
# `in.txt` is being READ. Same family as the multi-line commit false
# positive: a piece of the line read as what it is not.
_REDIR_STRIP_RE = re.compile(
    r"""[0-9]?(?:>>?|<<?)&?\s*(?:"[^"]*"|'[^']*'|[^\s;&|<>()]+)?"""
)


def _strip_redirections(segment: str, mask: list) -> str:
    """Removes the redirections OUTSIDE quotes, leaving the rest intact."""
    cuts = [
        (m.start(), m.end())
        for m in _REDIR_STRIP_RE.finditer(segment)
        if m.group() and not mask[m.start()]
    ]
    if not cuts:
        return segment
    out, pos = [], 0
    for span_start, span_end in cuts:
        out.append(segment[pos:span_start])
        pos = span_end
    out.append(segment[pos:])
    return " ".join(p for p in out if p)


def _unquoted_view(command: str) -> str:
    """The command line with the quoted content replaced by spaces.

    The undecidable-construct detector (_UNCOVERED_RE) used to scan the whole
    line, quotes included: a commit message with the word `ed`, or with a `<<`
    in the middle of the prose, generated a false entry in the coverage log.
    The log exists only to say what the hook could NOT analyze, and filling it
    with prose teaches people to ignore it.
    """
    mask = _quoted_mask(command)
    return "".join(" " if m else c for c, m in zip(command, mask))


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] in "\"'" and tok[-1] == tok[0]:
        return tok[1:-1]
    return tok


def _is_flag(tok: str) -> bool:
    return tok.startswith("-") and tok != "-"


def _segment_targets(segment: str) -> list:
    """Best-effort extraction of shell-write targets from one command segment."""
    targets = []

    # 1. Redirections (covers `cat > f`, `echo .. >> f`, `cmd > f`, heredoc-to-file).
    #    The `>` must be outside quotes: a `->` in the middle of a commit
    #    message is prose, not a redirection.
    redir_mask = _quoted_mask(segment)
    for m in _REDIR_RE.finditer(segment):
        if not redir_mask[m.start()]:
            targets.append(_unquote(m.group(1)))

    # 2. argv-shaped writers — tokenize; fall back silently if shlex chokes.
    #    Without the redirections: they already became targets in step 1, and
    #    leaving them here makes `tee` count the input operand as a write.
    no_redir = _strip_redirections(segment, redir_mask)
    try:
        argv = shlex.split(no_redir, posix=True)
    except ValueError:
        argv = no_redir.split()
    if not argv:
        return targets

    cmd = os.path.basename(argv[0])
    rest = argv[1:]
    nonflags = [t for t in rest if t and not _is_flag(t)]

    if cmd == "tee":
        # every non-flag arg is written (flags: -a/--append/-i…)
        targets.extend(nonflags)
    elif cmd == "sed":
        if any(t == "-i" or t.startswith("-i") or t == "--in-place"
               or t.startswith("--in-place") for t in rest):
            # in-place edits its file operands — everything after the script.
            # Heuristic: all non-flag args except the first (the sed program).
            if len(nonflags) >= 2:
                targets.extend(nonflags[1:])
            elif nonflags:
                targets.extend(nonflags)  # `sed -i'' file` form with no separate prog
    elif cmd in ("cp", "mv", "install"):
        if len(nonflags) >= 2:
            targets.append(nonflags[-1])  # destination is the last operand
            if cmd == "mv":
                # `mv` DELETES its source(s) — that is a write on the origin
                # path too, not just the destination (P4, CS-5: renaming
                # counts as a write on both paths). `cp`/`install` only READ
                # their source, so they stay destination-only.
                targets.extend(nonflags[:-1])
    elif cmd == "dd":
        for t in rest:
            if t.startswith("of="):
                targets.append(t[3:])
    elif cmd == "git":
        # `git mv <src> <dst>` is a real file move, which the path-lock must
        # govern like any other write. It was only in the docs copy
        # (structure-surgeon uses git mv to preserve history); the other
        # four let it through. Found by the divergence detector.
        #
        # Source AND destination count as a write (P4, CS-5): `git mv` deletes
        # the source path as much as it creates the destination one. A slice
        # locked to write in domain/** that renames infrastructure/Foo.java to
        # domain/Foo.java "wrote" outside its own lane (it removed a file from
        # infrastructure/), even though the destination is allowed. Checking
        # only the destination, as before, let this direction slip by.
        if len(nonflags) >= 3 and nonflags[0] == "mv":
            targets.extend(nonflags[1:])
        elif nonflags and nonflags[0] in ("checkout", "restore"):
            # `git checkout <ref> -- file` and `git restore file`
            # OVERWRITE the file on disk with the version from elsewhere,
            # the same effect as the `git mv` above, in the same tool already
            # watched, and it was the easiest way to silently revert a file
            # outside the lane (proof-reviewer finding, 26/08/2026).
            #
            # Without `--`, `checkout` is a branch switch: it writes a lot,
            # but it is not a write aimed at a path, and treating it as a
            # target would turn every `git checkout main` into a block.
            if "--" in rest:
                targets.extend(t for t in rest[rest.index("--") + 1:]
                               if not _is_flag(t))
            elif nonflags[0] == "restore":
                targets.extend(nonflags[1:])
    elif cmd == "truncate":
        targets.extend(nonflags[1:] if nonflags else [])
    elif cmd in ("curl", "wget"):
        # Downloading to a file is writing to it. Proof-reviewer finding on
        # 26/08/2026: `curl -o` and `wget -O` are statically decidable (the
        # destination is explicit in argv) and yet they went through silent,
        # neither blocked nor logged. The form without an explicit destination
        # (`curl -O`, `wget <url>`, which save under the remote name in the
        # current directory) stays out: there the name is not on the command line.
        dest = ("-o", "--output") if cmd == "curl" else ("-O", "--output-document")
        prefixes = tuple(f"{d}=" for d in dest if d.startswith("--"))
        for i, t in enumerate(rest):
            if t in dest and i + 1 < len(rest):
                targets.append(rest[i + 1])
            elif t.startswith(prefixes):
                targets.append(t.split("=", 1)[1])
    elif cmd == "touch":
        # Creates the file if it does not exist: it is a write, even with empty content.
        targets.extend(nonflags)
    elif cmd == "rsync":
        # Like `cp`: reads the source, writes to the last operand.
        if len(nonflags) >= 2:
            targets.append(nonflags[-1])

    return targets


def extract_write_targets(command: str) -> tuple:
    """Return (targets, has_uncovered_construct)."""
    targets = []
    for seg in _split_segments(command):
        seg = seg.strip()
        if seg:
            targets.extend(_segment_targets(seg))
    # de-dup, drop pseudo-devices and fd dups
    clean = []
    seen = set()
    for t in targets:
        t = _unquote(t).strip()
        if not t or t in _PSEUDO or t.startswith("&") or t in seen:
            continue
        seen.add(t)
        clean.append(t)
    return clean, bool(_UNCOVERED_RE.search(_unquoted_view(command)))


# ─────────────────────────────────────────────────────────────────────────────
# LAYER 1 — deny-by-default in four buckets
#
# Design: docs/internals/gauntlet-pilot-bash-path-lock.md ("Layer 1"),
# approved on 2026-08-15. Reason: WEGO-1936 — a qa-engineer blocked on `cp`
# rewrote `src/main` with `python3 -c "open(...,'w')"`, and the old hook let
# inline interpreters through ("I can't analyze it → allow + log in /tmp").
# Nobody read the log.
#
# The hook's question was inverted. Before: "does this look like a known
# write?" — every new vector was an invisible false negative. Now: "is this
# provably harmless?". Every command segment of a locked agent falls into
# exactly one bucket:
#
#   1. ANALYZABLE WRITER — the target is on the command line (redirect, tee,
#      cp, sed -i, mkdir, rm...). Target inside the root and outside the
#      lane → deny.
#   2. HARMLESS VERB — audited list below (_SIMPLE and _HANDLERS), each verb
#      with the flags that turn it into a writer/executor denied.
#   3. OUTSIDE THE JURISDICTION — every directory the segment may run in is
#      outside the root, and nothing on the line cites the root: it is the
#      disposable perturbation worktree. Everything allowed.
#   4. EVERYTHING ELSE → DENIED. Inline interpreter, nested shell, a script
#      the agent itself could have written — except inside a worktree of this
#      repo (the disposable perturbation copy), which is bucket 3
#      jurisdiction —, a verb nobody listed. A new vector falls here BY
#      CONSTRUCTION: it does not need to be on any list, it only needs not to
#      be on the harmless one.
#
# Maintenance becomes adding a harmless verb (false positive: noisy, visible,
# cheap) instead of hunting bypasses (false negative: invisible).
# ─────────────────────────────────────────────────────────────────────────────

# Shadow mode (rollout): CEPA_BASHLOCK_ENFORCE=0 lets bucket 4 through and
# records `bash_pathlock_would_deny` in the ledger. Bucket 1 (write outside the
# lane) is never loosened — it already blocked before this layer existed.
_ENFORCE_ENV = "CEPA_BASHLOCK_ENFORCE"

_MAX_DEPTH = 6

# Marks that the line reading inserts in place of what is not argv.
_SUB_MARK = "__CEPASUB{}__"
_SUB_MARK_RE = re.compile(r"__CEPASUB(\d+)__")
_HEREDOC_MARK = "<__CEPAHEREDOC__"
_UNKNOWN = "\x00"

_VAR_RE = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*)|(\{[^}]*\}|[0-9@*#?$!-]))"
)
_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\+?=)(.*)$", re.S)

# Stdout redirections that the shared _REDIR_RE does not see because they
# start with a digit or `&`: `1> f`, `&> f`, `>| f`, `3> f`. `2>` (stderr)
# stays out of scope, as it always was (`./mvnw test 2> err.log`).
_EXTRA_REDIR_RE = re.compile(
    r"""(?<![0-9&>])(?:[013-9]>>?|&>>?|>>?\|)\s*(?!&)("[^"]+"|'[^']+'|[^\s;&|<>()]+)"""
)

_SYSTEM_BIN_DIRS = {"/bin", "/usr/bin", "/usr/local/bin", "/opt/homebrew/bin",
                    "/usr/sbin", "/sbin"}

# Variables that make a harmless verb run code chosen by whoever defines them
# (pager, editor, external diff, library preload, PATH).
_DANGEROUS_ENV = {
    "PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT", "BASH_ENV", "ENV",
    "PROMPT_COMMAND", "PYTHONSTARTUP", "PERL5OPT", "RUBYOPT", "NODE_OPTIONS",
    "GIT_EXTERNAL_DIFF", "GIT_PAGER", "PAGER", "GIT_EDITOR", "EDITOR", "VISUAL",
    "GIT_SEQUENCE_EDITOR", "GIT_SSH", "GIT_SSH_COMMAND", "GIT_ASKPASS",
    "SSH_ASKPASS", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT", "GIT_CONFIG",
    "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_DIR", "GIT_WORK_TREE",
    "GIT_EXEC_PATH", "GIT_TEMPLATE_DIR", "MANPAGER", "LESSOPEN", "BROWSER",
}
_DANGEROUS_ENV_PREFIX = ("DYLD_", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
_JVM_OPTS_ENV = {"JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS",
                 "MAVEN_OPTS", "GRADLE_OPTS", "JAVA_OPTS"}

# ─── bucket 2: the audited list of harmless verbs ───────────────────────────
#
# Verbs that neither write files nor run code brought in by the command line.
# Their arguments do not matter; a write, if any, only through redirection —
# and redirection is bucket 1. Whoever has a dangerous flag does NOT go here:
# it goes to _HANDLERS, with the flag denied.
_SIMPLE = frozenset("""
    ls cat head tail wc grep egrep fgrep zgrep ag diff diff3 cmp comm stat file
    du df pwd echo printf true false : test [ [[ ]] which whereis type basename
    dirname realpath readlink date whoami id hostname uname printenv cut tr nl
    paste column rev fold expand unexpand fmt tac seq sleep wait read exit return
    shift set unset shopt umask ulimit tput clear ps pgrep lsof uptime md5 md5sum
    shasum sha1sum sha256sum sha512sum cksum od hexdump strings jq zcat bzcat
    xzcat let getopts arch sw_vers nproc locale tty groups logname users who
    netstat cal look jobs fi done esac } for select
""".split())

# Control words that open a command: the word goes, the command stays.
_LEADING_KEYWORDS = {"if", "then", "do", "else", "elif", "while", "until", "!", "{"}

# Verbs whose writes are all on the command line (bucket 1).
_WRITERS = frozenset("""
    cp mv install tee dd truncate touch rsync mkdir rmdir rm unlink ln chmod
    chown chgrp
""".split())


class _Denied(Exception):
    def __init__(self, bucket, verb, reason, segment="", targets=None):
        super().__init__(reason)
        self.bucket = bucket
        self.verb = verb
        self.reason = reason
        self.segment = segment
        self.targets = targets or []


class _Arg:
    """A token of the argv with the known variables expanded.

    `value` replaces what cannot be known with _UNKNOWN. `lead_unknown` says
    whether the token STARTS with something unknown — only that one can hide a
    flag (`sed $X file` with X=-i), so only it weighs in the decision.
    """
    __slots__ = ("raw", "value", "known", "lead_unknown")

    def __init__(self, raw, value):
        self.raw = raw
        self.value = value
        self.known = _UNKNOWN not in value
        self.lead_unknown = value.startswith(_UNKNOWN)


class _Ctx:
    def __init__(self, root, agent, allowed, pl, shadow):
        self.root = root
        self.agent = agent
        self.allowed = allowed
        self.pl = pl
        self.shadow = shadow
        self.vars = {}
        self.sub_values = {}
        self.would = []     # bucket 4 denials in shadow mode
        self.events = []    # (event, fields) for the ledger
        self.sub_base = 0   # global numbering of the substitutions
        # directories (`cd $X`, `git -C $X`) whose value this call does not know.
        # They deny nothing on their own; they go into the message of a denial
        # that comes later, because they are almost always its cause.
        self.unknown_dirs = []
        # argv + redirections of the current segment, so _script_rule can
        # reuse _refs_root without recomputing them.
        self.seg_args = []
        # lazy cache of this repo's registered worktrees (see _worktrees).
        self._worktrees = None


# ─── line reading: substitutions and heredocs ──────────────────────────────

def _heredoc_at(s, i):
    """If there is a heredoc operator at s[i:], returns (end, delim, strip_tabs, quoted)."""
    n = len(s)
    if s[i:i + 2] != "<<" or s[i:i + 3] == "<<<":
        return None
    k = i + 2
    strip_tabs = k < n and s[k] == "-"
    if strip_tabs:
        k += 1
    while k < n and s[k] in " \t":
        k += 1
    quoted = False
    q = None
    if k < n and s[k] in "\"'":
        q = s[k]
        quoted = True
        k += 1
    elif k < n and s[k] == "\\":
        quoted = True
        k += 1
    span_start = k
    while k < n and (s[k].isalnum() or s[k] in "_-."):
        k += 1
    delim = s[span_start:k]
    if q and k < n and s[k] == q:
        k += 1
    if not delim:
        return None
    return k, delim, strip_tabs, quoted


def _skip_heredoc_body(s, j, delim, strip_tabs):
    """From the start of the body (j), returns the index right after the delimiter line."""
    n = len(s)
    while j < n:
        span_end = s.find("\n", j)
        if span_end == -1:
            span_end = n
        line = s[j:span_end]
        j = span_end + 1 if span_end < n else n
        if (line.lstrip("\t") if strip_tabs else line).strip() == delim:
            break
    return j


def _match_close(s, i, closer):
    """Index of the close of a substitution opened right before s[i].

    Respects quotes, escapes, nested substitutions and heredoc bodies (the
    commit message in the `"$(cat <<'EOF' ... EOF)"` pattern has apostrophes
    and parentheses in the prose). Returns -1 if it does not close.
    """
    n = len(s)
    depth = 1
    quote = None
    pend = []
    while i < n:
        c = s[i]
        if quote == "'":
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\":
            i += 2
            continue
        if quote == '"':
            if c == '"':
                quote = None
            elif s.startswith("$(", i):
                j = _match_close(s, i + 2, ")")
                if j < 0:
                    return -1
                i = j + 1
                continue
            elif c == "`":
                j = _match_close(s, i + 1, "`")
                if j < 0:
                    return -1
                i = j + 1
                continue
            i += 1
            continue
        if closer == "`" and c == "`":
            return i
        if c == "\n" and pend:
            j = i + 1
            for delim, strip_tabs in pend:
                j = _skip_heredoc_body(s, j, delim, strip_tabs)
            pend = []
            i = j
            continue
        if s.startswith("<<<", i):
            i += 3
            continue
        h = _heredoc_at(s, i)
        if h:
            pend.append((h[1], h[2]))
            i = h[0]
            continue
        if c in "\"'":
            quote = c
        elif closer == ")" and c == "(":
            depth += 1
        elif closer == ")" and c == ")":
            depth -= 1
            if depth == 0:
                return i
        elif closer == ")" and c == "`":
            j = _match_close(s, i + 1, "`")
            if j < 0:
                return -1
            i = j
        i += 1
    return -1


def _flatten(command):
    """Replaces each `$(...)`, backtick, `<(...)` and `>(...)` with a mark and
    strips the heredoc bodies.

    Returns (flat_line, substitutions, orphans). A substitution is another
    command, which runs BEFORE the segment that contains it — so it is
    classified as a command, with the same rules. That is the design's gap:
    `echo $(python3 -c ...)` had a harmless verb in front and arbitrary code
    inside. `orphans` are the substitutions in the body of a heredoc whose
    delimiter is unquoted (the shell expands them).
    """
    s = command
    n = len(s)
    out = []
    subs = []
    orphans = []
    quote = None
    pend = []
    i = 0

    def add_sub(inner):
        subs.append(inner)
        return _SUB_MARK.format(len(subs) - 1)

    while i < n:
        c = s[i]
        if quote == "'":
            out.append(c)
            if c == "'":
                quote = None
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(s[i:i + 2])
            i += 2
            continue
        is_sub = s.startswith("$(", i) and not s.startswith("$((", i)
        is_proc = quote is None and (s.startswith("<(", i) or s.startswith(">(", i))
        if is_sub or is_proc:
            j = _match_close(s, i + 2, ")")
            inner = s[i + 2:j] if j >= 0 else s[i + 2:]
            out.append(add_sub(inner))
            i = j + 1 if j >= 0 else n
            continue
        if s.startswith("$((", i):
            # Arithmetic is not a command — but it may hide `$(...)` inside.
            j = _match_close(s, i + 3, ")")
            inner = s[i + 3:j] if j >= 0 else s[i + 3:]
            f_inner, f_subs, _ = _flatten(inner)
            base = len(subs)
            subs.extend(f_subs)
            f_inner = _SUB_MARK_RE.sub(
                lambda m: _SUB_MARK.format(base + int(m.group(1))), f_inner)
            out.append("__CEPAARITH__")
            orphans.extend(range(base, len(subs)))
            del f_inner
            i = (j + 2) if j >= 0 else n
            continue
        if c == "`":
            j = _match_close(s, i + 1, "`")
            inner = s[i + 1:j] if j >= 0 else s[i + 1:]
            out.append(add_sub(inner))
            i = j + 1 if j >= 0 else n
            continue
        if quote == '"':
            out.append(c)
            if c == '"':
                quote = None
            i += 1
            continue
        # outside quotes
        if c in "\"'":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "\n" and pend:
            out.append("\n")
            j = i + 1
            for delim, strip_tabs, quoted in pend:
                span_end = _skip_heredoc_body(s, j, delim, strip_tabs)
                body = s[j:span_end]
                if not quoted:
                    # body with an unquoted delimiter: `$(...)` there EXECUTES
                    _, c_subs, c_orf = _flatten('"' + body.replace('"', " ") + '"')
                    base = len(subs)
                    subs.extend(c_subs)
                    orphans.extend(range(base, len(subs)))
                j = span_end
            pend = []
            i = j
            continue
        if s.startswith("<<<", i):
            out.append("<<<")  # here-string: does not open a body
            i += 3
            continue
        h = _heredoc_at(s, i)
        if h:
            pend.append((h[1], h[2], h[3]))
            out.append(" " + _HEREDOC_MARK + " ")
            i = h[0]
            continue
        out.append(c)
        i += 1
    return "".join(out), subs, orphans


def _split_with_seps(command):
    """Segments with the separator that PRECEDES them: '', '&&', '||', ';', '|', '&', '\\n'.

    Differs from the shared _split_segments at two points that decide the
    bucket: it keeps the separator (a `cd` only holds for the next segment if
    `&&` came) and it does not cut at the `&` of `2>&1` / `&>` — cutting there
    turned the `1` of `./mvnw test 2>&1 | tail` into an unknown "command".
    """
    mask = _quoted_mask(command)
    out = []
    start = i = 0
    sep = ""
    n = len(command)
    while i < n:
        if mask[i]:
            i += 1
            continue
        two = command[i:i + 2]
        if two in ("&&", "||"):
            out.append((sep, command[start:i]))
            sep = two
            i += 2
            start = i
            continue
        c = command[i]
        if c == "&" and ((i > 0 and command[i - 1] in "<>") or command[i + 1:i + 2] == ">"):
            i += 1
            continue
        if c == "|" and i > 0 and command[i - 1] == ">":
            i += 1  # `>|` is a redirection, not a pipe
            continue
        if c in ";|&\n":
            out.append((sep, command[start:i]))
            sep = c
            i += 1
            start = i
            continue
        i += 1
    out.append((sep, command[start:]))
    return out


# ─── expansion and resolution ───────────────────────────────────────────────

def _expand(ctx, raw, cwds):
    def var(m):
        name = m.group(1) or m.group(2)
        if not name:
            return _UNKNOWN
        if name in ctx.vars:
            v = ctx.vars[name]
            return _UNKNOWN if v is None else v
        if name == "PWD" and len(cwds) == 1:
            return str(next(iter(cwds)))
        v = os.environ.get(name)
        return _UNKNOWN if v is None else v

    def sub(m):
        v = ctx.sub_values.get(int(m.group(1)))
        return _UNKNOWN if v is None else v

    val = _SUB_MARK_RE.sub(sub, raw)
    val = val.replace("__CEPAARITH__", "0")
    val = _VAR_RE.sub(var, val)
    return _Arg(raw, val)


def _resolve_all(val, cwds):
    v = os.path.expanduser(val)
    if os.path.isabs(v):
        return [Path(v).resolve()]
    return [(Path(c) / v).resolve() for c in cwds]


def _inside(p, root):
    try:
        Path(p).relative_to(root)
        return True
    except ValueError:
        return False


def _worktrees(ctx):
    """Registered worktrees of this repo (git worktree list), except the root.

    Cache in ctx: only called when a script OUTSIDE the root is actually
    executed, so it costs nothing on the common path. Fail-silent: an error or
    timeout returns an empty list — the worst case is the script falling into
    the old denial, never being allowed by mistake.
    """
    if ctx._worktrees is not None:
        return ctx._worktrees
    result = []
    try:
        import subprocess
        out = subprocess.run(
            ["git", "-C", str(ctx.root), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=5)
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                if line.startswith("worktree "):
                    p = Path(line[len("worktree "):]).resolve()
                    if p != ctx.root:
                        result.append(p)
    except Exception:
        result = []
    ctx._worktrees = result
    return result


def _refs_root(ctx, text, args, cwds):
    """Does the line cite the root? (condition for bucket 3 NOT to hold)

    A string check, declared as such: a path assembled at runtime
    (`$(echo L3Jvb3Q= | base64 -d)`) escapes. The design accepts that
    residue — obfuscating after a deny is willful, not discovery.
    """
    root_s = str(ctx.root)
    if root_s in text:
        return True
    for a in args:
        if not a.known:
            return True
        v = a.value
        if root_s in v:
            return True
        if v.startswith("~") or ".." in v or os.path.isabs(v):
            for p in _resolve_all(v.split("=", 1)[-1] if v.startswith("-") else v, cwds):
                if _inside(p, ctx.root):
                    return True
    return False


def _deny(bucket, verb, reason, seg):
    raise _Denied(bucket, verb, reason, seg)


def _check_targets(ctx, targets, cwds, verb, seg):
    """Bucket 1: every target inside the root must be in the agent's lane."""
    outside = []
    for t in targets:
        val = t.value if isinstance(t, _Arg) else t
        raw = t.raw if isinstance(t, _Arg) else t
        val = _unquote(val).strip()
        if _UNKNOWN in val:
            raise _Denied(1, verb, f"alvo de escrita que não sei resolver: {raw}",
                          seg, [raw])
        if not val or val in _PSEUDO or val.startswith("&") or val == "-":
            continue
        for p in _resolve_all(val, cwds):
            if not _inside(p, ctx.root):
                continue
            ps = str(p)
            if ctx.pl.is_own_expertise_file(ps, ctx.agent):
                continue
            if ctx.allowed and ctx.pl.path_matches(ps, ctx.allowed, ctx.root):
                continue
            outside.append(raw)
            break
    if outside:
        raise _Denied(1, verb, "escrita fora da sua pista", seg, outside)


def _no_hidden_flags(args, verb, seg, value_flags=()):
    """A token that STARTS with an unknown value may be a disguised flag."""
    prev = None
    for a in args:
        if a.lead_unknown and prev not in value_flags:
            _deny(4, verb, f"argumento que não sei avaliar ({a.raw}) pode esconder "
                            f"uma flag que torna `{verb}` escritor ou executor", seg)
        prev = a.value if a.known else None


def _script_rule(ctx, arg, cwds, verb, seg):
    """Running a file is harmless only if the agent CANNOT have written it.

    A project script outside the lane (`./mvnw`, `bash scripts/build.sh`,
    `source .venv/bin/activate`): written by someone else — it is the
    equivalent of an `npm test`. A script outside the root (/tmp) or inside
    the agent's own lane: the agent may have just written it, so running it is
    writing arbitrarily.

    Exception: a script inside a registered worktree of this repo (the
    disposable perturbation copy created with `git worktree add`) is the same
    jurisdiction as bucket 3 — running the script from inside the copy opens
    nothing that `cd <copy> && <the same script>` (bucket 3, already allowed)
    would not open, as long as the line does not cite the root. Found in run
    2026-09-28-0558: the proof-reviewer created the copy in /tmp and was
    blocked when running the test from inside it.
    """
    if not arg.known:
        _deny(4, verb, f"o arquivo executado vem de valor que não sei avaliar ({arg.raw})", seg)
    for p in _resolve_all(arg.value, cwds):
        if not _inside(p, ctx.root):
            if any(_inside(p, wt) for wt in _worktrees(ctx)) and not _refs_root(
                    ctx, seg, ctx.seg_args, cwds):
                continue
            _deny(4, verb, f"executar arquivo fora do projeto ({arg.value}) — "
                            f"você pode tê-lo escrito, e aí ele escreve o que quiser. "
                            f"Cópia descartável criada com `git worktree add` é a "
                            f"exceção: script de dentro dela passa", seg)
        ps = str(p)
        if ctx.pl.is_own_expertise_file(ps, ctx.agent) or (
                ctx.allowed and ctx.pl.path_matches(ps, ctx.allowed, ctx.root)):
            _deny(4, verb, f"executar arquivo da sua própria pista ({arg.value}) — "
                            f"é código que você mesmo pode ter escrito", seg)


# ─── per-verb handlers (bucket 2 with a denied flag, or bucket 1) ──────────

def _vals(args):
    return [a.value for a in args]


def _nonflags(args, value_flags=()):
    out = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a.known and a.value in value_flags:
            skip = True
            continue
        if a.known and _is_flag(a.value):
            continue
        out.append(a)
    return out


def _generic_targets(verb, args):
    """Targets from the shared extractor (_segment_targets) + the ones missing there."""
    vals = [verb] + _vals(args)
    line = " ".join(shlex.quote(v) for v in vals)
    targets = list(_segment_targets(line))
    rest = vals[1:]
    nf = [v for v in rest if v and not _is_flag(v)]
    if verb in ("cp", "mv", "install", "ln"):
        for k, v in enumerate(rest):
            if v in ("-t", "--target-directory") and k + 1 < len(rest):
                targets.append(rest[k + 1])
            elif v.startswith("--target-directory="):
                targets.append(v.split("=", 1)[1])
    if verb == "ln":
        if len(nf) >= 2:
            targets.append(nf[-1])
        elif nf:
            targets.append(os.path.basename(nf[0].rstrip("/")))
    elif verb in ("mkdir", "rmdir", "rm", "unlink"):
        targets.extend(nf)
    elif verb in ("chmod", "chown", "chgrp"):
        targets.extend(nf[1:])
    return targets


def _h_writer(ctx, verb, args, cwds, seg):
    if verb == "rsync" and any(a.value in ("-e", "--rsh", "--rsync-path") or
                               a.value.startswith(("--rsh=", "--rsync-path="))
                               for a in args):
        _deny(4, verb, "rsync -e/--rsh executa um comando", seg)
    _check_targets(ctx, _generic_targets(verb, args), cwds, verb, seg)


def _h_sed(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    if any(v in ("-f", "--file") or v.startswith("--file=") for v in vals):
        _deny(4, verb, "sed -f lê o programa de um arquivo — não sei o que ele faz", seg)
    _no_hidden_flags(args, verb, seg, ("-e", "--expression"))
    scripts = []
    for k, v in enumerate(vals):
        if v in ("-e", "--expression") and k + 1 < len(vals):
            scripts.append(vals[k + 1])
        elif v.startswith("--expression="):
            scripts.append(v.split("=", 1)[1])
    if not scripts:
        nf = [a.value for a in _nonflags(args, ("-e", "--expression", "-l"))]
        nf = [v for v in nf if v]  # `sed -i ''` (BSD): the empty suffix is not a script
        if nf:
            scripts.append(nf[0])
    for sc in scripts:
        if _sed_executes_or_writes(sc):
            _deny(4, verb, "o programa do sed escreve arquivo (w/W) ou executa (e)", seg)
    if any(v == "-i" or v.startswith("-i") or v.startswith("--in-place") for v in vals):
        _check_targets(ctx, _generic_targets("sed", args), cwds, verb, seg)


# The sed script is read command by command, the way sed itself reads it. The
# previous version scanned the text character by character looking for an `s`:
# on a word like "stays" inside an `/.../` address or inside the text of an
# `a`/`i`/`c`, it read `s` + delimiter `t` and found an `e` in the "flags" —
# denying a legitimate `sed -i` (deviations.md, 2026-09-27). Reading by command
# is what separates text from command; what this reader does not recognize is
# denied, never allowed.
_SED_SIMPLE = set("=dDgGhHlnNpPxzFqQLv")


def _sed_delimited(script, i, d):
    """Advances from `i` to just after the next unescaped `d`; -1 if it does not close."""
    n = len(script)
    while i < n:
        c = script[i]
        if c == "\\":
            i += 2
            continue
        if c == d:
            return i + 1
        if c == "\n" and d != "\n":
            return -1
        i += 1
    return -1


def _sed_address(script, i):
    """Consumes an address (number, $, /re/, \\cREc, first~step); -1 if malformed."""
    n = len(script)
    if i < n and script[i].isdigit():
        while i < n and script[i].isdigit():
            i += 1
        if i < n and script[i] == "~":
            i += 1
            while i < n and script[i].isdigit():
                i += 1
        return i
    if i < n and script[i] == "$":
        return i + 1
    if i < n and script[i] in "/\\":
        if script[i] == "\\":
            if i + 1 >= n or script[i + 1] in "\n\\":
                return -1
            d, i = script[i + 1], i + 2
        else:
            d, i = "/", i + 1
        i = _sed_delimited(script, i, d)
        if i < 0:
            return -1
        while i < n and script[i] in "IM":
            i += 1
        return i
    return i


def _sed_line_end(script, i, continues=False):
    """Advances to the end of the line. Only the text of a/i/c continues onto the
    next line with a trailing backslash; a comment and a file name end at the break."""
    n = len(script)
    while i < n:
        if continues and script[i] == "\\":
            i += 2
            continue
        if script[i] == "\n":
            return i
        i += 1
    return n


def _sed_executes_or_writes(script):
    """True if the script writes a file (w/W, the s flag w) or executes (e,
    the s flag e) — or if it cannot be read. Fails closed: the caller denies."""
    i, n = 0, len(script)
    while i < n:
        while i < n and script[i] in " \t\n;":
            i += 1
        if i >= n:
            break
        c = script[i]
        if c == "#":
            i = _sed_line_end(script, i)
            continue
        if c == "}":
            i += 1
            continue
        i = _sed_address(script, i)
        if i < 0:
            return True
        if i < n and script[i] == ",":
            i += 1
            while i < n and script[i] in " \t":
                i += 1
            if i < n and script[i] in "+~":
                i += 1
                while i < n and script[i].isdigit():
                    i += 1
            else:
                j = _sed_address(script, i)
                if j < 0 or j == i:
                    return True
                i = j
        while i < n and script[i] in " \t!":
            i += 1
        if i >= n:
            return True  # address without a command: sed refuses, I do not guess
        c = script[i]
        i += 1
        if c in "eWw":
            return True
        if c == "{":
            continue
        if c in "aic":
            i = _sed_line_end(script, i, continues=True)  # text, never a command
            continue
        if c in "rR#":
            i = _sed_line_end(script, i)  # name of a file to read, or a comment
            continue
        if c in ":btT":  # a label ends at `;` or at a space, as in GNU sed
            while i < n and script[i] in " \t":
                i += 1
            while i < n and script[i] not in " \t;\n}":
                i += 1
            continue
        if c in "sy":
            if i >= n or script[i] in "\n\\":
                return True
            d = script[i]
            i = _sed_delimited(script, i + 1, d)
            if i >= 0:
                i = _sed_delimited(script, i, d)
            if i < 0:
                return True
            if c == "s":
                k = i
                while k < n and script[k] not in " \t\n;}":
                    k += 1
                flags = script[i:k]
                if "e" in flags or "w" in flags or "W" in flags:
                    return True
                if flags.strip("gpiImM0123456789"):
                    return True  # flag desconhecida
                i = k
            continue
        if c in _SED_SIMPLE:
            while i < n and script[i] not in ";\n}#":
                i += 1
            continue
        return True  # a command sed does not have, or that this reader does not know
    return False


def _h_awk(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    for v in vals:
        if v in ("-f", "--file", "-i", "--include", "-l", "--load", "-E", "--exec") \
                or v.startswith(("--file=", "--include=", "--load=", "--exec=")):
            _deny(4, verb, f"awk {v} carrega programa de fora da linha", seg)
    nf = _nonflags(args, ("-F", "-v", "--field-separator", "--assign"))
    if not nf:
        return
    prog = nf[0].raw
    # `>` and `|` only write/execute in the context of print/printf; outside it
    # they are comparison (`NR>1`) and regex alternation (`/a|b/`), pure reads.
    if re.search(r"\bsystem\s*\(|\bgetline\b|@(?:include|load|namespace)\b", prog) or \
            re.search(r"\bprintf?\b[^;{}]*[>|]", prog):
        _deny(4, verb, "o programa awk escreve (print > arquivo), abre pipe ou "
                        "executa (system/getline)", seg)


def _h_find(ctx, verb, args, cwds, seg):
    _no_hidden_flags(args, verb, seg)
    bad_flags = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0",
             "-fprintf", "-fls"}
    for a in args:
        if a.value in bad_flags:
            _deny(4, verb, f"find {a.value} executa comando ou apaga/escreve arquivo", seg)


def _h_flagdeny(bad, prefixes=()):
    def h(ctx, verb, args, cwds, seg):
        _no_hidden_flags(args, verb, seg)
        for a in args:
            if a.value in bad or (prefixes and a.value.startswith(prefixes)):
                _deny(4, verb, f"{verb} {a.value} escreve arquivo ou executa comando", seg)
    return h


def _h_output_flag(flags):
    """Harmless verb whose output flag becomes a write target (sort -o, tree -o)."""
    def h(ctx, verb, args, cwds, seg):
        _no_hidden_flags(args, verb, seg, flags)
        vals = _vals(args)
        targets = []
        for k, v in enumerate(vals):
            if v in flags and k + 1 < len(vals):
                targets.append(args[k + 1])
            for f in flags:
                if f.startswith("--") and v.startswith(f + "="):
                    targets.append(v.split("=", 1)[1])
                elif not f.startswith("--") and v.startswith(f) and len(v) > len(f):
                    targets.append(v[len(f):])
        _check_targets(ctx, targets, cwds, verb, seg)
    return h


def _h_second_operand(ctx, verb, args, cwds, seg):
    """`uniq input output`, `xxd input output`: the 2nd operand is written."""
    _no_hidden_flags(args, verb, seg)
    nf = _nonflags(args, ("-s", "-f", "-c", "-l", "-g", "-o", "-n", "-w"))
    if len(nf) >= 2:
        _check_targets(ctx, [nf[1]], cwds, verb, seg)


def _h_mktemp(ctx, verb, args, cwds, seg):
    _no_hidden_flags(args, verb, seg, ("-p", "--tmpdir", "-t", "--suffix"))
    targets = []
    vals = _vals(args)
    for k, v in enumerate(vals):
        if v in ("-p", "--tmpdir") and k + 1 < len(vals):
            targets.append(os.path.join(vals[k + 1], "x"))
        elif v.startswith("--tmpdir="):
            targets.append(os.path.join(v.split("=", 1)[1], "x"))
    nf = _nonflags(args, ("-p", "--tmpdir", "-t", "--suffix"))
    if nf and not targets:
        targets.append(nf[0])
    _check_targets(ctx, targets, cwds, verb, seg)


def _h_curl(ctx, verb, args, cwds, seg):
    _no_hidden_flags(args, verb, seg, ("-o", "--output", "-d", "--data", "-H",
                                        "--header", "-u", "--user", "-X", "-F"))
    vals = _vals(args)
    targets = []
    for k, v in enumerate(vals):
        if v in ("-O", "--remote-name", "--remote-name-all", "-J",
                 "--remote-header-name", "--output-dir", "-K", "--config") \
                or v.startswith(("--output-dir=", "--config=")):
            _deny(4, verb, f"curl {v} grava com nome que a linha não diz", seg)
        if v in ("-o", "--output") and k + 1 < len(vals):
            targets.append(args[k + 1])
        elif v.startswith("--output="):
            targets.append(v.split("=", 1)[1])
        elif re.match(r"^-[a-zA-Z]+$", v) and not v.startswith("--"):
            letters = v[1:]
            if "O" in letters or "K" in letters or "J" in letters:
                _deny(4, verb, f"curl {v} grava com nome que a linha não diz", seg)
            if "o" in letters:
                remainder = letters[letters.index("o") + 1:]
                if remainder:
                    targets.append(remainder)
                elif k + 1 < len(vals):
                    targets.append(args[k + 1])
    _check_targets(ctx, targets, cwds, verb, seg)


def _h_wget(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    targets = []
    for k, v in enumerate(vals):
        if v in ("-O", "--output-document") and k + 1 < len(vals):
            targets.append(args[k + 1])
        elif v.startswith("--output-document="):
            targets.append(v.split("=", 1)[1])
        elif re.match(r"^-[a-zA-Z]*O", v):
            remainder = v[v.index("O") + 1:]
            targets.append(remainder if remainder else (vals[k + 1] if k + 1 < len(vals) else "?"))
    if not targets and "--spider" not in vals:
        _deny(4, verb, "wget sem -O grava com o nome remoto no diretório corrente", seg)
    _check_targets(ctx, targets, cwds, verb, seg)


def _h_archive_readonly(modes_ok):
    def h(ctx, verb, args, cwds, seg):
        vals = _vals(args)
        if verb == "tar":
            letters = ""
            for k, v in enumerate(vals):
                if v.startswith("--"):
                    letters += {"--list": "t", "--extract": "x", "--get": "x",
                               "--create": "c", "--append": "r",
                               "--update": "u"}.get(v, "")
                elif v.startswith("-") or k == 0:
                    letters += v.lstrip("-")
            if "t" in letters and not any(m in letters for m in "xcruA"):
                return
            _deny(4, verb, "tar só é inocente listando (-t); extrair/criar escreve "
                            "onde a linha não diz", seg)
        if not any(v in modes_ok for v in vals):
            _deny(4, verb, f"{verb} só é inocente em modo de leitura "
                            f"({', '.join(sorted(modes_ok))})", seg)
    return h


def _wrapper_inner(verb, args):
    """Strips the options of a finite wrapper and returns the wrapped command."""
    vals = _vals(args)
    i = 0
    if verb == "time":
        while i < len(vals) and vals[i] in ("-p", "-l"):
            i += 1
    elif verb == "nohup":
        pass
    elif verb == "nice":
        while i < len(vals) and _is_flag(vals[i]):
            i += 2 if vals[i] in ("-n", "--adjustment") else 1
    elif verb == "timeout":
        while i < len(vals) and _is_flag(vals[i]):
            i += 2 if vals[i] in ("-s", "--signal", "-k", "--kill-after") else 1
        i += 1  # the duration
    elif verb == "stdbuf":
        while i < len(vals) and _is_flag(vals[i]):
            i += 2 if vals[i] in ("-i", "-o", "-e") else 1
    elif verb == "command":
        while i < len(vals) and vals[i] == "-p":
            i += 1
    return args[i:]


def _h_wrapper(ctx, verb, args, cwds, seg):
    if verb == "command" and any(a.value in ("-v", "-V") for a in args):
        return
    for a in args:
        if a.lead_unknown:
            _deny(4, verb, f"{verb} com argumento que não sei avaliar ({a.raw})", seg)
    inner = _wrapper_inner(verb, args)
    if inner:
        _dispatch(ctx, inner, cwds, seg)


def _h_env(ctx, verb, args, cwds, seg):
    i = 0
    vals = _vals(args)
    while i < len(vals):
        v = vals[i]
        if v in ("-S", "--split-string", "-C", "--chdir") or v.startswith(
                ("--split-string=", "--chdir=")) or (re.match(r"^-[a-zA-Z]+$", v)
                                                     and ("S" in v or "C" in v)):
            _deny(4, verb, "env -S/-C monta ou muda o comando por fora da linha", seg)
        if v in ("-u", "--unset"):
            i += 2
            continue
        if _is_flag(v) and not _ASSIGN_RE.match(v):
            i += 1
            continue
        break
    inner = args[i:]
    if inner:
        _dispatch(ctx, inner, cwds, seg)


_XARGS_VALUE_FLAGS = {"-I", "-L", "-l", "-n", "-P", "-s", "-d", "-E", "-e", "-a",
                      "--max-args", "--max-procs", "--delimiter", "--arg-file",
                      "--replace", "--max-lines", "--eof", "--max-chars"}


def _h_xargs(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    i = 0
    while i < len(vals) and _is_flag(vals[i]):
        i += 2 if vals[i] in _XARGS_VALUE_FLAGS else 1
    inner = args[i:]
    if not inner:
        return  # xargs without a command = echo
    iv = inner[0].value if inner[0].known else ""
    if iv not in _SIMPLE and iv not in ("sed", "awk", "find", "rg", "fd", "jq"):
        _deny(4, verb, f"xargs executa `{inner[0].raw}` com argumentos vindos da "
                        f"entrada — só verbos de leitura passam por xargs", seg)
    _dispatch(ctx, inner, cwds, seg)


_PY_MODULES_OK = {"pytest", "unittest", "json.tool", "py_compile", "compileall",
                  "mypy", "flake8", "pylint", "pyflakes", "pycodestyle", "platform",
                  "sysconfig", "site", "tabnanny"}


def _h_pylike_tool(ctx, tool, args, cwds, seg):
    """Python tools that can be called standalone or via `-m`."""
    vals = _vals(args)
    nf = [a.value for a in _nonflags(args)]
    if tool == "pip" or tool == "pip3":
        if nf and nf[0] in ("list", "show", "freeze", "check", "debug") or \
                any(v in ("--version", "-V") for v in vals):
            return
        _deny(4, tool, "pip só é inocente consultando (list/show/freeze/check)", seg)
    if tool == "ruff":
        if "--fix" in vals or (nf and nf[0] == "format" and not
                               any(v in ("--check", "--diff") for v in vals)):
            _deny(4, tool, "ruff --fix/format reescreve arquivos", seg)
        return
    if tool == "black" or tool == "isort":
        if not any(v in ("--check", "--diff", "--check-only", "-c") for v in vals):
            _deny(4, tool, f"{tool} sem --check/--diff reescreve arquivos", seg)
        return
    if tool == "coverage":
        if nf and nf[0] == "run":
            rest = args[[a.value for a in args].index("run") + 1:]
            rv = _vals(rest)
            if "-m" in rv:
                k = rv.index("-m")
                if k + 1 >= len(rv) or rv[k + 1] not in _PY_MODULES_OK:
                    _deny(4, tool, "coverage run -m com módulo fora da lista", seg)
                return
            rest_nonflags = _nonflags(rest, ("--rcfile", "--source", "--omit", "--include",
                                   "--data-file", "--context"))
            if rest_nonflags:
                _script_rule(ctx, rest_nonflags[0], cwds, tool, seg)
        return
    # mypy, flake8, pylint...: they only read
    return


def _h_python(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    i = 0
    while i < len(vals):
        a = args[i]
        v = vals[i]
        if a.lead_unknown:
            _deny(4, verb, f"argumento que não sei avaliar ({a.raw})", seg)
        if v in ("-V", "--version", "-h", "--help", "-VV"):
            return
        if v == "--":
            i += 1
            break
        if v in ("-W", "-X"):
            i += 2
            continue
        if v.startswith(("-W", "-X")):
            i += 1
            continue
        if v == "-m" or (re.match(r"^-[a-zA-Z]+$", v) and "m" in v and "c" not in v):
            if v == "-m":
                mod = vals[i + 1] if i + 1 < len(vals) else ""
                rest = args[i + 2:]
            else:
                remainder = v[v.index("m") + 1:]
                mod = remainder or (vals[i + 1] if i + 1 < len(vals) else "")
                rest = args[i + 1:] if remainder else args[i + 2:]
            if mod in _PY_MODULES_OK:
                return
            if mod in ("pip", "ruff", "black", "isort", "coverage"):
                _h_pylike_tool(ctx, mod, rest, cwds, seg)
                return
            _deny(4, verb, f"`{verb} -m {mod}` — módulo fora da lista de inocentes", seg)
        if v.startswith("--"):
            i += 1
            continue
        if v.startswith("-") and v != "-":
            letters = v[1:]
            if "c" in letters:
                _deny(4, verb, f"`{verb} -c` roda código inline — código arbitrário "
                                f"é escrita arbitrária", seg)
            if "i" in letters:
                _deny(4, verb, f"`{verb} -i` é interpretador interativo", seg)
            i += 1
            continue
        break
    if i >= len(vals) or vals[i] == "-":
        _deny(4, verb, f"`{verb}` lendo o programa da entrada (heredoc/pipe) — "
                        f"código arbitrário é escrita arbitrária", seg)
    _script_rule(ctx, args[i], cwds, verb, seg)


def _h_node(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    bad_flags = ("-e", "--eval", "-p", "--print", "-r", "--require", "--import",
             "--loader", "--experimental-loader", "-i", "--interactive", "-pe")
    for a in args:
        if a.lead_unknown:
            _deny(4, verb, f"argumento que não sei avaliar ({a.raw})", seg)
        v = a.value
        if v in bad_flags or v.startswith(tuple(r + "=" for r in bad_flags if r.startswith("--"))):
            _deny(4, verb, f"`node {v}` roda código inline — código arbitrário é "
                            f"escrita arbitrária", seg)
    if any(v in ("-v", "--version", "-h", "--help") for v in vals) or "--test" in vals:
        return
    nf = _nonflags(args)
    if not nf or nf[0].value == "-":
        _deny(4, verb, "`node` lendo o programa da entrada", seg)
    _script_rule(ctx, nf[0], cwds, verb, seg)


def _h_shell(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    i = 0
    while i < len(vals):
        v = vals[i]
        if args[i].lead_unknown:
            _deny(4, verb, f"argumento que não sei avaliar ({args[i].raw})", seg)
        if v == "--":
            i += 1
            break
        if v in ("-o", "+o"):
            i += 2
            continue
        if re.match(r"^[-+][a-zA-Z]+$", v):
            if any(x in v[1:] for x in "csi"):
                _deny(4, verb, f"`{verb} {v}` roda comando de uma string ou da "
                                f"entrada — shell aninhado não é analisável", seg)
            i += 1
            continue
        if v.startswith("--"):
            i += 1
            continue
        break
    if i >= len(vals):
        _deny(4, verb, f"`{verb}` lendo comandos da entrada (heredoc/pipe)", seg)
    _script_rule(ctx, args[i], cwds, verb, seg)


def _h_source(ctx, verb, args, cwds, seg):
    nf = _nonflags(args)
    if not nf:
        _deny(4, verb, "source sem arquivo", seg)
    _script_rule(ctx, nf[0], cwds, verb, seg)


def _mvn_args(ctx, verb, args, seg):
    for a in args:
        if a.lead_unknown:
            _deny(4, verb, f"argumento que não sei avaliar ({a.raw}) pode esconder "
                            f"um goal que executa comando", seg)
        v = a.value
        if v.startswith(("exec:", "antrun:")) or any(
                p in v for p in ("exec-maven-plugin", "maven-antrun-plugin",
                                 "gmavenplus", "groovy-maven-plugin")):
            _deny(4, verb, f"goal `{v}` executa comando arbitrário", seg)


def _h_mvn(ctx, verb, args, cwds, seg):
    _mvn_args(ctx, verb, args, seg)


def _h_gradle(ctx, verb, args, cwds, seg):
    _no_hidden_flags(args, verb, seg)


def _h_make(ctx, verb, args, cwds, seg):
    _no_hidden_flags(args, verb, seg, ("-C", "-j"))
    for v in _vals(args):
        if v in ("-f", "--file", "--makefile", "--eval", "-E") or v.startswith(
                ("--file=", "--makefile=", "--eval=")):
            _deny(4, verb, f"make {v} lê receita de fora do projeto", seg)


_NPM_VALUE_FLAGS = {"--prefix", "-C", "--dir", "-w", "--workspace", "--filter",
                    "--cwd", "-F"}
_NPM_OK = {"test", "t", "tst", "run", "run-script", "rum", "urn", "start", "stop",
           "restart", "ci", "install", "i", "in", "ins", "inst", "insta", "instal",
           "isnt", "isnta", "isntal", "ls", "list", "ll", "la", "view", "v", "info",
           "show", "outdated", "audit", "explain", "why", "config", "c", "prefix",
           "root", "bin", "help", "doctor", "whoami", "ping", "search", "fund",
           "version", "build", "lint", "typecheck"}
_PM_DENY = {"exec", "x", "dlx", "node", "add", "remove", "rm", "uninstall", "un",
            "unlink", "link", "ln", "up", "upgrade", "update", "patch",
            "patch-commit", "set", "plugin", "create", "init", "import", "publish",
            "pack", "rebuild", "dedupe", "prune", "pkg", "set-script", "edit"}


def _h_pm(ctx, verb, args, cwds, seg):
    """npm / pnpm / yarn."""
    _no_hidden_flags(args, verb, seg, tuple(_NPM_VALUE_FLAGS))
    vals = _vals(args)
    if any(v in ("--fix", "--write") for v in vals):
        _deny(4, verb, f"{verb} ... --fix/--write reescreve arquivos de outras pistas", seg)
    nf = _nonflags(args, _NPM_VALUE_FLAGS)
    if not nf:
        return  # `npm --version`, `yarn` (= install)
    sub = nf[0].value
    if sub in _PM_DENY:
        _deny(4, verb, f"`{verb} {sub}` instala/executa/reescreve fora da lista", seg)
    if sub in ("install", "i", "in", "ins", "inst", "insta", "instal", "isnt",
               "isnta", "isntal") and len(nf) > 1:
        _deny(4, verb, f"`{verb} {sub} <pacote>` muda o package.json", seg)
    if sub == "audit" and len(nf) > 1 and nf[1].value == "fix":
        _deny(4, verb, "`audit fix` reescreve package.json/lockfile", seg)
    if sub in ("config", "c") and len(nf) > 1 and nf[1].value not in ("get", "list", "ls"):
        _deny(4, verb, "config que grava", seg)
    if sub == "version" and len(nf) > 1:
        _deny(4, verb, "`version <x>` reescreve o package.json", seg)
    if verb == "npm" and sub not in _NPM_OK:
        _deny(4, verb, f"`npm {sub}` fora da lista de inocentes", seg)


_NPX_DENY_PKGS = {"node", "ts-node", "tsx", "bun", "deno", "zx", "sh", "bash",
                  "python", "python3", "perl", "ruby", "rimraf", "shx", "cross-env",
                  "del-cli", "trash-cli", "cpy-cli", "cpx", "ncp", "copyfiles", "mv",
                  "rm", "npm", "pnpm", "yarn"}


def _h_npx(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    _no_hidden_flags(args, verb, seg, ("-p", "--package"))
    for v in vals:
        if v in ("-c", "--call") or v.startswith("--call="):
            _deny(4, verb, "`npx -c` roda uma string de shell", seg)
        if v in ("--fix", "--write"):
            _deny(4, verb, f"npx ... {v} reescreve arquivos de outras pistas", seg)
    nf = _nonflags(args, ("-p", "--package"))
    if not nf:
        _deny(4, verb, "npx sem pacote", seg)
    pkg = nf[0].value
    base = pkg.rsplit("@", 1)[0] if pkg.count("@") and not pkg.startswith("@") else pkg
    if base.split("/")[-1] in _NPX_DENY_PKGS or base in _NPX_DENY_PKGS:
        _deny(4, verb, f"`npx {pkg}` executa código arbitrário ou apaga/copia arquivo", seg)
    if base.endswith("prettier") and "-w" in vals:
        _deny(4, verb, "prettier -w reescreve arquivos", seg)


def _h_js_tool(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    _no_hidden_flags(args, verb, seg)
    if verb == "eslint" and "--fix" in vals:
        _deny(4, verb, "eslint --fix reescreve arquivos", seg)
    if verb == "prettier" and any(v in ("--write", "-w") for v in vals):
        _deny(4, verb, "prettier --write reescreve arquivos", seg)


def _h_sub_allow(allowed_subs, deny_flags=()):
    def h(ctx, verb, args, cwds, seg):
        _no_hidden_flags(args, verb, seg)
        vals = _vals(args)
        if any(v in ("--version", "-V", "version", "--help", "-h") for v in vals[:1]):
            return
        for f in deny_flags:
            if f in vals:
                _deny(4, verb, f"{verb} {f} reescreve arquivos", seg)
        nf = _nonflags(args)
        if not nf or nf[0].value not in allowed_subs:
            sub = nf[0].value if nf else "(nada)"
            _deny(4, verb, f"`{verb} {sub}` fora da lista de inocentes "
                            f"({', '.join(sorted(allowed_subs))})", seg)
    return h


def _h_java(ctx, verb, args, cwds, seg):
    if all(a.value in ("-version", "--version", "-showversion") for a in args) and args:
        return
    _deny(4, verb, "java roda bytecode/fonte arbitrário — use o build (./mvnw)", seg)


_DOCKER_OK = {"ps", "images", "image", "logs", "inspect", "version", "info", "stats",
              "top", "port", "pull", "build", "stop", "start", "restart", "rm", "rmi",
              "kill", "exec", "network", "volume", "container", "system", "context",
              "events", "wait", "compose", "run", "cp", "create", "pause", "unpause",
              "ls", "config", "down", "up", "buildx"}
_DOCKER_VALUE_FLAGS = ("-H", "--host", "--context", "-c", "-f", "--file", "-p",
                       "--project-name", "--project-directory", "--profile",
                       "--env-file", "--log-level")


def _h_docker(ctx, verb, args, cwds, seg):
    _no_hidden_flags(args, verb, seg, _DOCKER_VALUE_FLAGS)
    nf = _nonflags(args, _DOCKER_VALUE_FLAGS)
    if not nf:
        return
    k = 0
    if nf[0].value == "compose":
        k = 1
    if len(nf) <= k:
        return
    sub = nf[k].value
    if sub not in _DOCKER_OK:
        _deny(4, verb, f"`{verb} {sub}` fora da lista de inocentes", seg)
    vals = _vals(args)
    if sub == "build" and any(v in ("-o", "--output") or v.startswith("--output=")
                              for v in vals):
        _deny(4, verb, "docker build --output grava no disco local", seg)
    if sub in ("run", "create"):
        for i, v in enumerate(vals):
            src = None
            if v in ("-v", "--volume", "--mount") and i + 1 < len(args):
                src = args[i + 1]
            elif v.startswith(("--volume=", "--mount=")):
                src = _Arg(v, v.split("=", 1)[1])
            if src is None:
                continue
            source = src.value.split(":", 1)[0]
            if src.value.startswith("type="):
                m = re.search(r"(?:source|src)=([^,]+)", src.value)
                source = m.group(1) if m else ""
            if not src.known or not os.path.isabs(os.path.expanduser(source)) or any(
                    _inside(p, ctx.root) for p in _resolve_all(source, cwds)):
                _deny(4, verb, "docker run montando pasta do projeto: o container "
                                "escreve nela sem passar pelo cadeado", seg)
    if sub == "cp" and len(nf) >= k + 3:
        dest = nf[-1]
        if ":" not in dest.value.split("/")[0]:
            _check_targets(ctx, [dest], cwds, verb, seg)


def _h_gh(ctx, verb, args, cwds, seg):
    _no_hidden_flags(args, verb, seg, ("-R", "--repo", "-b", "--body", "-t",
                                        "--title", "-F", "--body-file", "-q", "--jq"))
    nf = [a.value for a in _nonflags(args, ("-R", "--repo", "-b", "--body", "-t",
                                           "--title", "-F", "--body-file", "-q",
                                           "--jq"))]
    pair = tuple(nf[:2])
    if pair in {("repo", "clone"), ("run", "download"), ("release", "download"),
               ("pr", "checkout"), ("gist", "clone")} or (nf and nf[0] in
                                                          ("alias", "extension", "ext")):
        _deny(4, verb, f"`gh {' '.join(pair)}` grava arquivos ou executa extensão", seg)


# git ─────────────────────────────────────────────────────────────────────────

_GIT_READONLY = {
    "status", "log", "diff", "show", "blame", "annotate", "rev-parse", "rev-list",
    "ls-files", "ls-tree", "ls-remote", "cat-file", "describe", "shortlog",
    "merge-base", "name-rev", "for-each-ref", "show-ref", "show-branch",
    "whatchanged", "count-objects", "version", "help", "check-ignore", "check-attr",
    "check-ref-format", "var", "diff-tree", "diff-files", "diff-index",
    "range-diff", "cherry", "fetch", "add", "commit", "branch", "tag", "push",
    "switch", "fsck", "verify-commit", "verify-tag", "symbolic-ref", "merge",
    "grep",
}
# `git -c key=value`: only keys that execute nothing.
_GIT_C_OK = ("color.", "core.quotepath", "user.", "log.", "advice.",
             "init.defaultbranch", "commit.gpgsign", "gc.auto", "diff.renames",
             "diff.noprefix", "merge.conflictstyle", "pull.rebase", "push.default",
             "safe.directory", "core.autocrlf", "core.filemode", "column.")
_GIT_VALUE_FLAGS_COMMIT = ("-m", "--message", "-F", "--file", "--author", "--date",
                           "-C", "-c", "--reuse-message", "--reedit-message",
                           "--fixup", "--squash", "-t", "--template")


def _looks_like_path(v, cwds):
    if any(p.exists() for p in _resolve_all(v, cwds)):
        return True
    return "/" in v and bool(re.search(r"\.[A-Za-z][A-Za-z0-9]{0,5}$", v))


def _h_git(ctx, verb, args, cwds, seg):
    vals = _vals(args)
    i = 0
    git_cwds = cwds
    while i < len(vals):
        v = vals[i]
        a = args[i]
        if a.lead_unknown:
            _deny(4, verb, f"argumento que não sei avaliar ({a.raw})", seg)
        if v == "-C" and i + 1 < len(args):
            target = args[i + 1]
            if not target.known:
                ctx.unknown_dirs.append(target.raw)
                _deny(4, verb, f"git -C com caminho que não sei avaliar ({target.raw})", seg)
            git_cwds = {p for p in _resolve_all(target.value, git_cwds)}
            i += 2
            continue
        if v == "-c" and i + 1 < len(args):
            key = vals[i + 1].split("=", 1)[0].lower()
            if not key.startswith(_GIT_C_OK):
                _deny(4, verb, f"git -c {key}=... pode fazer o git executar um "
                                f"comando (pager, editor, alias, hook)", seg)
            i += 2
            continue
        if v in ("--git-dir", "--work-tree") or v.startswith(("--git-dir=", "--work-tree=")):
            _deny(4, verb, f"git {v} aponta o git para outra árvore — use git -C", seg)
        if v.startswith("-"):
            i += 1
            continue
        break
    # git -C <outside the root> without citing the root: it is the disposable worktree (bucket 3)
    rest_args = args[i:]
    if git_cwds is not cwds and all(not _inside(c, ctx.root) for c in git_cwds) and \
            not _refs_root(ctx, seg, rest_args, git_cwds):
        return
    if i >= len(vals):
        return  # `git --version`, `git -C x`
    sub = vals[i]
    rest = args[i + 1:]
    rv = _vals(rest)
    cw = git_cwds

    def writer(targets):
        _check_targets(ctx, targets, cw, "git", seg)

    if sub in ("diff", "show", "log", "format-patch"):
        if sub == "format-patch":
            _deny(4, verb, "git format-patch grava arquivos", seg)
        for k, x in enumerate(rv):
            if x == "--output" and k + 1 < len(rest):
                writer([rest[k + 1]])
            elif x.startswith("--output="):
                writer([x.split("=", 1)[1]])
        return
    if sub == "grep":
        if any(x in ("-O", "--open-files-in-pager") or x.startswith(
                ("-O", "--open-files-in-pager=")) for x in rv):
            _deny(4, verb, "git grep -O abre um pager/editor", seg)
        return
    if sub == "commit":
        return
    if sub in _GIT_READONLY:
        return
    if sub == "mv":
        writer([t for t in _segment_targets(
            " ".join(shlex.quote(x) for x in ["git", "mv"] + rv))])
        return
    if sub == "rm":
        writer([a for a in _nonflags(rest)])
        return
    if sub == "restore":
        writer(_nonflags(rest, ("-s", "--source")))
        return
    if sub == "checkout":
        if "--" in rv:
            writer(rest[rv.index("--") + 1:])
            return
        nf = _nonflags(rest, ("-b", "-B", "--orphan", "--conflict"))
        if any(x in ("-b", "-B", "--orphan") for x in rv):
            if len(nf) >= 2:
                writer(nf[1:])
            return
        if any(not a.known for a in nf):
            _deny(4, verb, "git checkout com argumento que não sei avaliar pode "
                            "sobrescrever arquivo", seg)
        if len(nf) >= 2:
            writer(nf[1:])  # `git checkout <ref> <path>` without `--`
        elif len(nf) == 1 and nf[0].known and _looks_like_path(nf[0].value, cw):
            writer(nf)      # `git checkout <file>`: overwrites the file
        return
    if sub == "reset":
        if any(x in ("--hard", "--merge", "--keep") for x in rv):
            _deny(4, verb, "git reset --hard/--merge/--keep reescreve arquivos da árvore", seg)
        return
    if sub == "stash":
        if rv and rv[0] in ("list", "show"):
            return
        _deny(4, verb, "git stash (push/pop/apply) reescreve arquivos da árvore", seg)
    if sub == "config":
        read_only_flags = ("--get", "--get-all", "--get-regexp", "--list", "-l",
                   "--get-urlmatch", "--show-origin", "--show-scope", "--name-only")
        nf = _nonflags(rest, ("--file", "-f", "--blob", "--type"))
        if any(x in read_only_flags for x in rv) or len(nf) <= 1:
            return
        _deny(4, verb, "git config que grava (core.hooksPath, alias, pager executam "
                        "comandos)", seg)
    if sub == "remote":
        nf = _nonflags(rest)
        if not nf or nf[0].value in ("show", "get-url"):
            return
        _deny(4, verb, "git remote que grava", seg)
    if sub == "reflog":
        if not rv or rv[0] in ("show",) or _is_flag(rv[0]):
            return
        _deny(4, verb, "git reflog expire/delete", seg)
    if sub == "submodule":
        if rv and rv[0] in ("status", "summary"):
            return
        _deny(4, verb, "git submodule que grava ou executa (foreach)", seg)
    if sub == "worktree":
        action = rv[0] if rv else ""
        if action in ("list", "prune", "lock", "unlock", "repair", "remove"):
            return
        if action == "add":
            nf = _nonflags(rest[1:], ("-b", "-B", "--reason"))
            if not nf:
                _deny(4, verb, "git worktree add sem caminho", seg)
            dest = nf[0]
            if not dest.known:
                _deny(4, verb, f"git worktree add num caminho que não sei avaliar "
                                f"({dest.raw})", seg)
            if any(_inside(p, ctx.root) for p in _resolve_all(dest.value, cw)):
                # fb-20261013-3: the disposable-worktree recipe belongs only to the proof-reviewer.
                if (ctx.agent or "").rsplit(":", 1)[-1] == "proof-reviewer":
                    _deny(4, verb, "git worktree add DENTRO da raiz duplica o código na "
                                    "árvore — crie fora: D=$(mktemp -d) && git worktree "
                                    "add --detach \"$D/red\" HEAD", seg)
                _deny(4, verb, "git worktree add DENTRO da raiz duplica o código na "
                                "árvore, e worktree descartável não é sua: a prova por "
                                "perturbação é do proof-reviewer; teste de regressão fica "
                                "vermelho pela ORDEM (escrito antes do fix)", seg)
            ctx.events.append(("perturb_worktree_created", {}))
            return
        _deny(4, verb, f"git worktree {action}", seg)
    _deny(4, verb, f"`git {sub}` reescreve arquivos da árvore ou não está na lista "
                    f"de subcomandos inocentes", seg)


def _h_decl(ctx, verb, args, cwds, seg):
    """export / declare / local / typeset / readonly: assignments that persist."""
    for a in args:
        m = _ASSIGN_RE.match(a.raw)
        if not m:
            continue
        _check_env_assign(m.group(1), a, seg)
        ctx.vars[m.group(1)] = _expand(ctx, m.group(3), cwds).value if \
            _expand(ctx, m.group(3), cwds).known else None


def _check_env_assign(name, arg, seg):
    if name in _DANGEROUS_ENV or name.startswith(_DANGEROUS_ENV_PREFIX):
        _deny(4, name, f"`{name}=` faz um verbo inocente executar outro programa "
                       f"(pager, editor, diff externo, PATH, pré-carga)", seg)
    if name in _JVM_OPTS_ENV and (not arg.known or any(
            x in arg.value for x in ("-javaagent", "-agentpath", "-agentlib"))):
        _deny(4, name, f"`{name}` com agente JVM executa código arbitrário", seg)


_HANDLERS = {
    "sed": _h_sed, "gsed": _h_sed,
    "awk": _h_awk, "gawk": _h_awk, "nawk": _h_awk, "mawk": _h_awk,
    "find": _h_find,
    "rg": _h_flagdeny({"--pre"}, ("--pre=",)),
    "fd": _h_flagdeny({"-x", "--exec", "-X", "--exec-batch"}),
    "yq": _h_flagdeny({"-i", "--inplace"}),
    "sort": _h_output_flag(("-o", "--output")),
    "tree": _h_output_flag(("-o",)),
    "base64": _h_output_flag(("-o", "--output")),
    "uniq": _h_second_operand, "xxd": _h_second_operand,
    "mktemp": _h_mktemp,
    "curl": _h_curl, "wget": _h_wget,
    "tar": _h_archive_readonly(set()),
    "unzip": _h_archive_readonly({"-l", "-Z", "-t", "-v"}),
    "gzip": _h_archive_readonly({"-c", "-l", "-t", "--stdout", "--list", "--test"}),
    "gunzip": _h_archive_readonly({"-c", "-l", "-t", "--stdout", "--list", "--test"}),
    "bzip2": _h_archive_readonly({"-c", "-t", "--stdout", "--test"}),
    "xz": _h_archive_readonly({"-c", "-l", "-t", "--stdout", "--list", "--test"}),
    "time": _h_wrapper, "nohup": _h_wrapper, "nice": _h_wrapper,
    "timeout": _h_wrapper, "gtimeout": _h_wrapper, "stdbuf": _h_wrapper,
    "command": _h_wrapper,
    "env": _h_env, "xargs": _h_xargs,
    "python": _h_python, "python3": _h_python,
    "node": _h_node,
    "bash": _h_shell, "sh": _h_shell, "zsh": _h_shell, "dash": _h_shell, "ksh": _h_shell,
    "source": _h_source, ".": _h_source,
    "mvn": _h_mvn, "gradle": _h_gradle, "make": _h_make, "gmake": _h_make,
    "npm": _h_pm, "pnpm": _h_pm, "yarn": _h_pm,
    "npx": _h_npx,
    "jest": _h_js_tool, "vitest": _h_js_tool, "mocha": _h_js_tool, "tsc": _h_js_tool,
    "eslint": _h_js_tool, "prettier": _h_js_tool, "playwright": _h_js_tool,
    "pytest": _h_gradle, "py.test": _h_gradle,
    "pip": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "pip3": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "ruff": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "black": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "isort": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "coverage": lambda c, v, a, w, s: _h_pylike_tool(c, v, a, w, s),
    "mypy": _h_gradle, "flake8": _h_gradle, "pylint": _h_gradle,
    "go": _h_sub_allow({"test", "vet", "list", "version", "env", "build", "doc", "help"}),
    "cargo": _h_sub_allow({"test", "build", "check", "clippy", "doc", "tree",
                           "metadata", "bench"}, ("--fix",)),
    "dotnet": _h_sub_allow({"test", "build", "restore", "--info", "--list-sdks",
                            "--list-runtimes"}),
    "java": _h_java,
    "docker": _h_docker, "docker-compose": _h_docker, "podman": _h_docker,
    "gh": _h_gh,
    "git": _h_git,
    "export": _h_decl, "declare": _h_decl, "local": _h_decl, "typeset": _h_decl,
    "readonly": _h_decl,
}
for _w in _WRITERS:
    _HANDLERS[_w] = _h_writer


def _dispatch(ctx, args, cwds, seg):
    """Classifies an already-expanded argv: bucket 1, 2 or 4."""
    assigns = []
    while args and args[0].raw in _LEADING_KEYWORDS:
        args = args[1:]
    while args:
        m = _ASSIGN_RE.match(args[0].raw)
        if not m:
            break
        _check_env_assign(m.group(1), _expand(ctx, m.group(3), cwds), seg)
        assigns.append((m.group(1), m.group(3)))
        args = args[1:]
    if not args:
        # pure assignment: persists for the next segments
        for name, raw_value in assigns:
            e = _expand(ctx, raw_value, cwds)
            ctx.vars[name] = e.value if e.known else None
        return
    va = args[0]
    rest = args[1:]
    if not va.known:
        _deny(4, va.raw, f"o verbo vem de variável ou substituição que não sei "
                         f"avaliar ({va.raw})", seg)
    v = va.value
    if "/" in v:
        d, b = os.path.split(v)
        if d in _SYSTEM_BIN_DIRS:
            v = b
        else:
            _script_rule(ctx, va, cwds, b, seg)
            if b == "mvnw":
                _mvn_args(ctx, b, rest, seg)
            elif b == "gradlew":
                _no_hidden_flags(rest, b, seg)
            return
    if re.match(r"^python[0-9.]*$", v):
        v = "python3"
    if v in _SIMPLE:
        return
    h = _HANDLERS.get(v)
    if h:
        h(ctx, v, rest, cwds, seg)
        return
    _deny(4, v, f"`{v}` não está na lista de verbos inocentes", seg)


def _sub_value(ctx, inner, cwds):
    """The value of a substitution, when it can be known without running it."""
    try:
        argv = shlex.split(inner.strip(), posix=True)
    except ValueError:
        return None
    if not argv:
        return None
    v = argv[0]
    if v == "mktemp":
        nf = [x for x in argv[1:] if not _is_flag(x)]
        for k, x in enumerate(argv):
            if x in ("-p", "--tmpdir") and k + 1 < len(argv):
                return os.path.join(argv[k + 1], "cepa-mktemp")
        if nf:
            return str(_resolve_all(nf[0], cwds)[0])
        return os.path.join(tempfile.gettempdir(), "cepa-mktemp")
    if v == "pwd" and len(cwds) == 1:
        return str(next(iter(cwds)))
    if v == "git" and "--show-toplevel" in argv and len(cwds) == 1:
        c = next(iter(cwds))
        return str(ctx.root) if _inside(c, ctx.root) else None
    # `$(echo word)`: only a single literal, that does not start with `-` and
    # does not split into words. Without this, `sed $(printf -- -i) ...` hid the `-i`.
    if v in ("echo", "printf") and len(argv) == 2 and not argv[1].startswith("-") \
            and not re.search(r"[\s*?\[\\%$`]", argv[1]):
        return argv[1]
    return None


def _classify(ctx, command, cwds, depth=0):
    """Classifies the whole line; raises _Denied at the first problem."""
    if depth > _MAX_DEPTH:
        _deny(4, "", "substituições aninhadas demais para analisar", command[:120])
    flat, subs, orphans = _flatten(command)
    base = ctx.sub_base
    ctx.sub_base += len(subs) + 1
    # the marks are local to this call: renumber so they do not collide with the outer one's
    flat = _SUB_MARK_RE.sub(lambda m: _SUB_MARK.format(base + int(m.group(1))), flat)
    done = set()

    def run_sub(idx, where):
        if idx in done:
            return
        done.add(idx)
        saved = dict(ctx.vars)
        try:
            _guard(ctx, lambda: _classify(ctx, subs[idx], where, depth + 1))
        finally:
            ctx.vars = saved
        ctx.sub_values[base + idx] = _sub_value(ctx, subs[idx], where)

    state_in = frozenset(cwds)
    history = set(state_in)
    prev = None
    stack = []
    for sep, seg in _split_with_seps(flat):
        if prev is not None:
            p_in, p_ok, p_fail = prev
            if sep == "&&":
                state_in = p_ok
            elif sep in ("|", "&"):
                state_in = p_in
            else:
                state_in = frozenset(history | p_ok | p_fail)
        text = seg.strip()
        if not text:
            prev = (state_in, state_in, state_in)
            continue
        while text.startswith("(") and not text.startswith("(("):
            stack.append(state_in)
            text = text[1:].lstrip()
        m = _quoted_mask(text)
        opens = sum(1 for c, q in zip(text, m) if c == "(" and not q)
        closes = sum(1 for c, q in zip(text, m) if c == ")" and not q)
        pops = max(0, closes - opens)
        for _ in range(pops):
            text = text.rstrip()
            if text.endswith(")"):
                text = text[:-1]
        for sm in _SUB_MARK_RE.finditer(text):
            run_sub(int(sm.group(1)) - base, state_in)
        ok = fail = state_in
        if text.strip() and not text.startswith("(("):
            res = _guard(ctx, lambda: _classify_segment(ctx, text.strip(), state_in))
            if res is not None:
                ok, fail = res
        for _ in range(pops):
            ok = fail = stack.pop() if stack else frozenset(cwds)
        history |= ok | fail | state_in
        prev = (state_in, ok, fail)
    for idx in orphans:
        run_sub(idx, frozenset(cwds))
    for idx in range(len(subs)):
        run_sub(idx, frozenset(cwds))


def _guard(ctx, fn):
    """In shadow mode, bucket 4 records instead of denying — and the analysis goes on."""
    try:
        return fn()
    except _Denied as n:
        if ctx.shadow and n.bucket == 4:
            ctx.would.append(n)
            return None
        raise


def _classify_segment(ctx, text, cwds):
    """One segment. Returns (cwds if it succeeded, cwds if it failed)."""
    mask = _quoted_mask(text)
    redirs = []
    for rx in (_REDIR_RE, _EXTRA_REDIR_RE):
        for m in rx.finditer(text):
            if not mask[m.start()]:
                redirs.append(_expand(ctx, _unquote(m.group(1)), cwds))
    no_redir = _strip_redirections(text, mask)
    try:
        argv = shlex.split(no_redir, posix=True)
    except ValueError:
        _deny(4, "", "não consegui ler a linha (aspas desbalanceadas?)", text)
    args = [_expand(ctx, t, cwds) for t in argv]
    while args and args[0].raw in _LEADING_KEYWORDS:
        args = args[1:]

    # cd / pushd / popd change where the NEXT segments run
    if args and args[0].raw in ("cd", "pushd", "popd"):
        verb = args[0].raw
        _check_targets(ctx, redirs, cwds, verb, text)
        if verb == "popd":
            return frozenset(set(cwds) | {ctx.root}), frozenset(cwds)
        nf = _nonflags(args[1:])
        if not nf:
            dest = {Path.home().resolve()}
        elif not nf[0].known or nf[0].value == "-":
            dest = {ctx.root}   # I do not know where it went: treat it as the root
            if not nf[0].known:
                ctx.unknown_dirs.append(nf[0].raw)
        else:
            dest = set(_resolve_all(nf[0].value, cwds))
        return frozenset(dest), frozenset(cwds)

    # bucket 3 — everything outside the root, and the line does not cite the root
    if all(not _inside(c, ctx.root) for c in cwds) and not _refs_root(
            ctx, text, args + redirs, cwds):
        if args and _ASSIGN_RE.match(args[0].raw) and all(
                _ASSIGN_RE.match(a.raw) for a in args):
            for a in args:
                mm = _ASSIGN_RE.match(a.raw)
                e = _expand(ctx, mm.group(3), cwds)
                ctx.vars[mm.group(1)] = e.value if e.known else None
        return cwds, cwds

    # make argv + redirs of this segment available to _script_rule, which
    # needs _refs_root outside of here (bucket 4, script inside a worktree).
    ctx.seg_args = args + redirs

    # bucket 1 — redirections
    verb = args[0].value if args and args[0].known else "?"
    _check_targets(ctx, redirs, cwds, verb, text)
    if args:
        _dispatch(ctx, args, cwds, text)
    return cwds, cwds


# ─── telemetry (minimal mirror of common/hooks/_telemetry.py) ─────────────

def _t_emit(event: str, cwd: str = None, **fields) -> None:
    """Minimal mirror of common/hooks/_telemetry.py (a cross-plugin import is
    fragile across versioned cache directories). Strictly fail-silent."""
    try:
        import subprocess
        from datetime import datetime, timezone
        repo = ""
        try:
            out = subprocess.run(
                ["git", "-C", cwd or os.getcwd(), "rev-parse",
                 "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, timeout=5)
            if out.returncode == 0:
                common = out.stdout.strip()
                repo = Path(common).parent.name if common.endswith("/.git") else Path(common).name
            else:
                repo = Path(cwd or os.getcwd()).name
        except Exception:
            pass
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "event": event, "repo": repo, "topology": PLUGIN_NAME}
        for k, v in fields.items():
            entry[k] = v[:200] if isinstance(v, str) else v
        tdir = Path(os.environ.get("CEPA_TELEMETRY_DIR") or
                    (Path.home() / ".claude" / "cepa-telemetry"))
        tdir.mkdir(parents=True, exist_ok=True)
        with open(tdir / f"events-{entry['ts'][:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _cmd_hash(command: str) -> str:
    import hashlib
    return hashlib.blake2b(command.encode("utf-8", "replace"), digest_size=6).hexdigest()


_BUCKET_NAME = {
    1: "balde 1 — escrita fora da sua pista",
    4: "balde 4 — fora da lista de comandos inocentes",
}


def _unknown_dir_hint(raws):
    """The denial came from a directory this call does not know how to resolve.

    Case measured on 2026-09-26: the proof-reviewer created the disposable
    worktree in one call (`WT=$(mktemp -d)/red && git worktree add ...`) and
    used `cd "$WT" && git checkout ...` in the next one. The lock reads each
    call on its own, so `$WT` has no value, the `cd` counts as "stays in the
    root" and the revert becomes a write outside the lane. The old message said
    only "write outside your lane" and suggested the same recipe with
    `"$D/red"`; the agents worked around it with `python3 -c`, the WEGO-1936
    vector.
    """
    names = ", ".join(dict.fromkeys(raws))
    return [
        "",
        f"  Por que caiu aqui: {names} não tem valor que eu conheça nesta chamada.",
        "  Cada chamada do Bash é lida sozinha: variável definida numa chamada",
        "  anterior (WT=..., D=$(mktemp -d)) não existe nesta. Sem saber o destino,",
        "  o `cd` conta como se você continuasse na raiz do projeto.",
        "  Repita o caminho LITERAL que a chamada anterior imprimiu:",
        "    cd /tmp/tmp.AbC123/red && <comando>",
        "    git -C /tmp/tmp.AbC123/red <subcomando>",
        "  Trocar por python3 -c não resolve: é o balde 4, e contornar é violação.",
    ]


def _build_message(n, agent, command, allowed, unknown_dirs=()):
    globs = "\n      - ".join(allowed or ["(nenhum — só o seu arquivo de expertise)"])
    lines = [
        f"[docs bash-path-lock] NEGADO ({_BUCKET_NAME.get(n.bucket, n.bucket)}): "
        f"agente {agent!r}.",
        f"  Motivo: {n.reason}",
    ]
    if n.targets:
        lines.append(f"  Alvo(s) fora da pista: {', '.join(n.targets)}")
    if n.segment and n.segment.strip() != command.strip():
        lines.append(f"  Trecho: {n.segment.strip()[:200]}")
    lines += [
        f"  Comando: {command[:300]}",
    ]
    if unknown_dirs:
        lines += _unknown_dir_hint(unknown_dirs)
    lines += [
        "",
        "  Este cadeado só deixa passar o que é comprovadamente inofensivo: escrita",
        "  com alvo visível dentro da sua pista, verbo da lista de inocentes, ou",
        "  comando rodando FORA da raiz do projeto. Código inline (python3 -c,",
        "  node -e, bash -c, heredoc para interpretador) é escrita arbitrária.",
        "  Escrever artefatos por Bash para contornar o path-lock é bypass de delegação.",
        "",
        "  O que fazer em vez disso:",
        f"    - escrever nos SEUS caminhos: use Write/Edit (o path-lock governa). Globs:",
        f"      - {globs}",
        "    - escrever fora da sua pista: delegue ao worker dono do caminho;",
    ]
    # fb-20261013-3: the disposable-worktree recipe belongs to the proof-reviewer
    # (perturbation gate). Shown to every denied agent, it sent the qa-engineer
    # off to open a worktree in the middle of the night. The others get the
    # pointer to the order/proof-reviewer.
    if agent.rsplit(":", 1)[-1] == "proof-reviewer":
        lines += [
            "    - provar RED revertendo código: worktree descartável FORA da raiz",
            "      (lá o cadeado não tem jurisdição, e a reversão nunca vaza para o diff):",
            "        D=$(mktemp -d) && git worktree add --detach \"$D/red\" HEAD && "
            "cd \"$D/red\" && <reverta e rode o teste>",
            "      Nas chamadas SEGUINTES, $D não existe mais: use o caminho literal",
            "      (cd /tmp/tmp.AbC123/red && ..., ou git -C /tmp/tmp.AbC123/red ...):",
            "        git worktree remove --force /tmp/tmp.AbC123/red",
        ]
    else:
        lines += [
            "    - provar RED revertendo código não é seu: a prova por perturbação (verde→vermelho)",
            "      é do proof-reviewer, na worktree descartável DELE. Teste de regressão fica",
            "      vermelho pela ORDEM (escrito antes do fix). Não abra worktree nem cópia do repo.",
        ]
    lines += [
        "    - verbo legítimo que faltou na lista: diga no seu relatório — quem",
        "      decide incluir é o humano, nunca o agente bloqueado.",
        "",
        "  A negação foi registrada no ledger de telemetria. Contornar depois de",
        "  negado não é esperteza: é violação auditada.",
    ]
    text = "\n".join(lines)
    # the internal marks of the line reading go back to the form the agent wrote
    text = _SUB_MARK_RE.sub("$(…)", text).replace(_HEREDOC_MARK, "<<…")
    return text.replace("__CEPAARITH__", "$((…))")


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[docs bash-path-lock] could not parse hook payload; allowing",
              file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name", "") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command.strip():
        sys.exit(0)

    # Only act on THIS plugin's subagents. No prefix → main session or a
    # built-in agent → not ours. Same fail-open contract as path-lock.py.
    raw_agent_type = payload.get("agent_type", "") or ""
    if ":" not in raw_agent_type or raw_agent_type.split(":", 1)[0] != PLUGIN_NAME:
        sys.exit(0)

    pl = _load_pathlock_module()
    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()
    agent = pl.detect_agent(payload)
    allowed = pl.ALLOWED_WRITES.get(agent)

    shadow = os.environ.get(_ENFORCE_ENV, "1").strip() == "0"
    ctx = _Ctx(project_root, agent, allowed, pl, shadow)
    cwd_s = str(project_root)
    try:
        try:
            _classify(ctx, command, [project_root])
        except _Denied:
            raise
        except Exception as e:  # noqa: BLE001
            # A defect in the classifier itself. Allowing silently would be the
            # silent failure this layer exists to kill; denying is loud and
            # shows up in the ledger. In shadow mode, it only records.
            if shadow:
                _t_emit("bash_pathlock_would_deny", cwd=cwd_s, agent=agent, bucket=0,
                        verb="?", cmd_hash=_cmd_hash(command), erro=type(e).__name__)
                sys.exit(0)
            raise _Denied(4, "?", f"erro interno do classificador ({type(e).__name__}: "
                                  f"{e}) — relate este comando no seu relatório", command)
    except _Denied as n:
        _t_emit("bash_pathlock_deny", cwd=cwd_s, agent=agent, bucket=n.bucket,
                verb=n.verb, cmd_hash=_cmd_hash(command),
                card=os.environ.get("CLAUDE_AUTONOMOUS_RUN_ID", ""))
        print(_build_message(n, agent, command, allowed, ctx.unknown_dirs),
              file=sys.stderr)
        sys.exit(2)

    for n in ctx.would:
        _t_emit("bash_pathlock_would_deny", cwd=cwd_s, agent=agent, bucket=n.bucket,
                verb=n.verb, cmd_hash=_cmd_hash(command))
    for ev, fields in ctx.events:
        _t_emit(ev, cwd=cwd_s, agent=agent, **fields)
    sys.exit(0)


if __name__ == "__main__":
    main()
