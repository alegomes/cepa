#!/usr/bin/env python3
"""_shellscan — the shared command-line reading engine of common.

## Why it exists

Two `common` hooks analyze a Bash command to decide whether to block it:
`enforcement-guard.py` (no subagent writes to `plugins/`, `hooks/` or
`settings.json`) and `maven-reactor-guard.py` (no partial-reactor build
without `-am`). Both had a manual copy of the same parsing engine, copied from
`bash-path-lock.py`, and that silent duplication has already cost dearly:

- the `>=` false positive (the `>` of the comparison operator read as a
  redirection) was fixed in the 5 copies of `bash-path-lock` on 11/06/2026 and
  **survived 2 months** in `enforcement-guard`, because the divergence detector
  between copies (`tests/test_lock_copies_drift.py`) and the generator
  (`bin/gen-locks.py`) only knew those 5;
- the same happened with the multi-line commit (22/08/2026, WEGO-2087): the
  hole was in 7 hooks and the radar covered 5.

Here the two guards import instead of copying. The 5 copies of
`bash-path-lock.py` are still generated from the template, since they live in
other plugins and cannot import from `common`. That leaves **two** sources of
the engine instead of seven, and `tests/test_lock_copies_drift.py` compares the
two by syntax tree.

Usage, following the pattern of the other private helpers in this folder:

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _shellscan as S
"""

import os
import re
import shlex

# Redirection: `>` or `>>`, NOT preceded by a digit or `&` (excludes `2>`,
# `&>`, `1>&2`), and the target must not start with `&` (excludes `>&1`) or `=`
# (excludes the `>=` comparison operator — `>` immediately followed by `=` is
# never a redirect; without this, `sed -i 's/>=/>/'`, `grep '>='`, and
# `[[ $a >= $b ]]` capture junk targets and get falsely blocked).
_REDIR_RE = re.compile(r"""(?<![0-9&])>>?\s*(?![&=])("[^"]+"|'[^']+'|[^\s;&|<>()]+)""")

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


# ─────────────────────────────────────────────────────────────────────────────
# Extraction of WRITE TARGETS: the step above parsing.
#
# Ported verbatim from build-hex's `bash-path-lock.py` on 26/08/2026, when
# `write-mode-gate` needed the same question the locks already answered:
# "which files does this command line WRITE?". The copy that existed in
# `enforcement-guard.py` had already diverged silently: it does not know
# `git mv` nor count the SOURCE of an `mv` as a write, so an agent moves a
# file out of its lane and the guard sees only the destination. Copying a
# third time would repeat the disease this module treats;
# `tests/test_lock_copies_drift.py` compares these two functions between the
# two sources of the engine.
# ─────────────────────────────────────────────────────────────────────────────

# Constructs we cannot statically analyze — fail open but log.
_UNCOVERED_RE = re.compile(
    r"""(?:
        \bpython3?\s+-c\b | \bperl\s+-[eE]\b | \bruby\s+-e\b | \bnode\s+-e\b |
        \bawk\b[^|;&]*\b-i\b | \b-i\s+inplace\b | \bgawk\b[^|;&]*\binplace\b |
        \bed\b | \bpatch\b | <<-?\s*['"]?\w+   # heredoc
    )""",
    re.VERBOSE,
)


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
# "Which files did this tool call write?" The same question for Edit/Write
# and for Bash.
#
# The PostToolUse hooks that react to writes (`mark-build-stale`,
# `session-activity`) were only registered on `Edit|Write|MultiEdit`. Auto
# mode prefers `sed`, heredoc and a short script over `Edit`/`Write`, and then
# the code changed with the build baseline still marked fresh: `gate-advance`
# let through a green that described code that no longer existed
# (BACKLOG, "Auto mode edits via `sed`...", 2026-08-25). Instead of each hook
# getting its own shell reading, all of them ask here.
# ─────────────────────────────────────────────────────────────────────────────

WRITE_TOOLS = ("Edit", "Write", "MultiEdit")


def _cd_target(segment: str):
    """The directory of a `cd X` segment, or None if the segment is not a cd."""
    try:
        argv = shlex.split(segment, posix=True)
    except ValueError:
        return None
    if len(argv) == 2 and argv[0] == "cd":
        return os.path.expanduser(argv[1])
    return None


def _git_dash_c(segment: str):
    """The `-C` arguments of a `git [-C X]... subcommand` segment, in order.

    Empty list if the segment is not git or has no `-C`. `-c key=value` is
    skipped (it does not change directory).
    """
    try:
        argv = shlex.split(segment, posix=True)
    except ValueError:
        return []
    if not argv or os.path.basename(argv[0]) != "git":
        return []
    out, i = [], 1
    while i < len(argv) and argv[i].startswith("-"):
        if argv[i] == "-C" and i + 1 < len(argv):
            out.append(os.path.expanduser(argv[i + 1]))
            i += 2
        elif argv[i].startswith("-C") and len(argv[i]) > 2:
            out.append(os.path.expanduser(argv[i][2:]))
            i += 1
        elif argv[i] == "-c":
            i += 2
        else:
            i += 1
    return out


def segment_dirs(command: str, cwd: str) -> list:
    """`[(segment, directory, explicit)]` for each segment that is NOT a `cd`.

    The directory is where the segment runs: that of the last `cd` before it on
    the line (relative to `cwd`; `~` expanded) and, in a `git -C X ...`, the `X`
    resolved from there. `explicit` is False when neither `cd` nor `-C` moved
    the directory (the segment runs in the payload's `cwd`). It is the same
    resolution as `edited_paths`, exposed for whoever needs to know WHERE a
    command acts (e.g. `gate-advance`, which judges the repo that receives the commit).
    """
    base = os.path.abspath(cwd)
    explicit = False
    out = []
    for seg in _split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        cd_dir = _cd_target(seg)
        if cd_dir is not None:
            base = os.path.normpath(os.path.join(base, cd_dir))
            explicit = True
            continue
        d, exp = base, explicit
        for c in _git_dash_c(seg):
            d = os.path.normpath(os.path.join(d, c))
            exp = True
        out.append((seg, d, exp))
    return out


def edited_paths(payload: dict) -> list:
    """Absolute paths that this tool call wrote.

    Edit/Write/MultiEdit: the `file_path`. Bash: the write targets that
    `extract_write_targets` knows how to read (redirection, heredoc to file,
    `sed -i`, `tee`, `cp`, `mv`...). A relative target is resolved against the
    directory of the last `cd` before it on the line, and with no `cd` against
    the payload's `cwd`: `cd /tmp/wt && sed -i ... X.java` wrote in /tmp/wt, not
    in the session tree. What the engine cannot analyze (`python -c`, `perl -e`,
    `awk -i inplace`, `ed`, `patch`) does not show up here: the limits are its own.
    """
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    base = os.path.abspath(payload.get("cwd") or os.getcwd())
    if tool in WRITE_TOOLS:
        fp = tool_input.get("file_path") or ""
        return [os.path.normpath(os.path.join(base, fp))] if fp else []
    if tool != "Bash":
        return []
    command = tool_input.get("command") or ""
    out = []
    for seg in _split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        cd_dir = _cd_target(seg)
        if cd_dir is not None:
            base = os.path.normpath(os.path.join(base, cd_dir))
            continue
        for t in _segment_targets(seg):
            t = _unquote(t).strip()
            if not t or t in _PSEUDO or t.startswith("&"):
                continue
            p = os.path.normpath(os.path.join(base, os.path.expanduser(t)))
            if p not in out:
                out.append(p)
    return out
