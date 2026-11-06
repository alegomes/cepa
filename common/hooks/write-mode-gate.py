#!/usr/bin/env python3
"""Write gate by mode: each mode only writes what it PRODUCES.

## The hole this hook closes

A session's mode used to be prose. `session-mode.py` injects every turn:

    an action outside this mode does NOT become a question and does NOT become
    work now; record it through `off-mode-capture` and carry on.

Nothing blocked it. In session `session/drain-plan-speed` (2026-08-26) the agent
did the opposite of both halves seven times in a row: it turned every deviation
into a closed question with "Recomendo sim", collected the yes, and built. The
exit condition of exploration — a strategy document with 2+ paths, run through
the advisors panel — was met in the FIRST of the seven commits; the next four
were construction. No deviation capture was recorded; `off-mode-capture` was
not invoked even once.

Two skills applied and were never confronted: `default-yes` says to decide
alone on a reversible action, and the mode says not to work outside it.
`default-yes` won every time, and the agent never named the conflict to the
owner.

It is the pattern this repo has already catalogued three times (memory
`gate-por-nome-de-ferramenta-falha-aberto`): **a control that depends on the
agent behaving is not a control.** Here the workaround had the owner's approval
at every step, which makes it harder to see, not less real.

## How it works

Sibling of `refactor-gate.py`, which is already a write gate scoped by mode. The
rule is an allow-list of DESTINATIONS per mode — what that mode produces — and
it lives in `_modes.py`, together with the rest of the table, and not here: a
second table of modes is the disease that file treats.

`construction` and `refactor` declare `"tudo"` ("everything"). That is not an
absence of enforcement: in construction the completion-auditor and the
proof-reviewer enforce, and in refactor the `refactor-gate.py` does.

Six decisions that came from damage already paid for in this repo:

1. **Bash too.** Blocking only `Write`/`Edit` lets `sed -i`, `cat >`, `tee` and
   `git mv` through — memory `bash-pathlock-bypass`, which cost a fix across 5
   topologies. The command-line reading is that of `_shellscan.py`, the shared
   source, and not a new copy.
2. **A write outside the session root passes.** The perturbation worktree in
   `/tmp` and the scratchpad belong to no mode; narrowing the gate to outside
   the root is what stalled the proof-reviewer on 2026-06-18 and left 5 cards
   stuck in NEEDS-HUMAN (memory `path-lock-out-of-root`).
3. **An undecidable construct becomes a WARNING, not a block.** `python3 -c`,
   `patch`, `ed` and heredoc write without the destination being statically
   readable — `_shellscan` already flagged this and nobody consumed the
   signal, so those lines slipped through the gate silently (proof-reviewer
   finding, 2026-08-26). Blocking would be consistent with the repo doctrine
   ("effect that cannot be audited -> block"), and it is the decision that was
   NOT taken: the list includes heredoc, which is how this repo runs scripts,
   and a mode that blocks every `python3 - <<PY` is a mode nobody uses. The
   warning makes the hole visible and emits `modo_escrita_indecidivel` in the
   telemetry; the real block is left for its own card, with the list of
   constructs reviewed one by one. A warning is a weaker control than a block,
   and this is recorded as such.
4. **The escape is not cheap and is not advertised.** A `# modo-ok` in the
   command would be the same escape again — the agent types it and moves on.
   The honest escape is to end the mode and open the mode of the work you want
   to do, which is a new session, and that is the right cost: switching
   activity SHOULD cost something. `CEPA_MODO=off` turns the whole mechanism
   off and is visible, but the block message does not offer it — the next
   failure mode, if it is offered, is the agent starting to ask to turn the
   gate off, and then the hole has only moved.

5. **A target the gate cannot resolve is not a verdict on the mode.** On
   2026-09-02, three blocks in an `exploration` session blamed the mode for a
   reading error: a variable assigned in the command itself (`D=...; cat >
   "$D/x"`) reached the gate as the literal `$D/x`, which matches no list. The
   message told the user to end the mode, and whoever reads it believes it. Now
   the simple assignment in the line itself is expanded before matching (nothing
   is executed), and what remains unresolved — a variable the line does not
   assign, `$(...)`, `${D:-x}` — blocks saying "could not resolve the target",
   never "you are outside the mode". The other two episodes (backtick and `>`
   quoted in the heredoc BODY) had already died in `_shellscan`, which masks the
   body since 2026-09-04.

6. **The checkout's `.git/info/` passes in every mode.** Episode fb-20261105-1
   (2026-11-05): in a `discovery` session the gate blocked `echo
   '.playwright-mcp/' >> .git/info/exclude`, preparing the checkout so Playwright
   logs stay out of git, and the owner was left with a command to run by hand.
   The per-mode lists say what a mode PRODUCES; `.git/info/` (exclude,
   attributes, sparse-checkout) is produced by no mode and has no execution path,
   so `_modes.ALWAYS_WRITABLE` is consulted before the mode's list. The boundary:
   `.git/hooks/*` and `.git/config` stay blocked (git runs code from them on the
   next command, an indirect bypass of this gate), and `.gitignore` is versioned.

What this gate does NOT reach is the "does not become a question" half: that is
the agent's text, not a tool call, and no hook reads the wording of a reply. But
the write lock makes the question useless — there is nothing to offer when the
next step is blocked.
"""

import fnmatch
import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _modes  # noqa: E402
import _shellscan as S  # noqa: E402
import _telemetry as T  # noqa: E402
import _wtlib  # noqa: E402

_FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def active_mode(root):
    """The declared mode of this session, or None."""
    try:
        # `mode:` (or the old `modo:`), already with the new mode name
        return (_modes.read_session_mode(root) or {}).get("mode")
    except Exception:  # noqa: BLE001
        return None


def targets(tool, inp):
    """(paths this call writes, is the line undecidable?)

    The second value is what `_shellscan` already knew and nobody used: there
    are constructs whose destination cannot be read statically — `python3 -c`,
    `patch`, `ed`, heredoc. `bash-path-lock` records them in a coverage log;
    here they become a WARNING, for the reason in the header.
    """
    if tool in _FILE_TOOLS:
        t = inp.get("file_path") or inp.get("notebook_path")
        return ([t] if t else []), False
    if tool == "Bash":
        command = inp.get("command") or ""
        return bash_targets(command), S.extract_write_targets(command)[1]
    return [], False


_VAR_RE = re.compile(r"\$\{([A-Za-z_]\w*)\}|\$([A-Za-z_]\w*)")
_ASSIGN_RE = re.compile(r"^([A-Za-z_]\w*)=(.*)$", re.S)


def _expand(text, known):
    """Replace `$X`/`${X}` with the value the line itself assigned to X.

    Only the simple form. `${X:-y}`, `${#X}` and `$(...)` stay as they are, and
    the `$` left over is what `unresolved` sees: in those cases the gate prefers
    to say it does not know rather than guess.
    """
    def swap(m):
        name = m.group(1) or m.group(2)
        return known.get(name, m.group(0))
    return _VAR_RE.sub(swap, text)


def _assignments(segment):
    """The NAME=value pairs of a segment that ONLY assigns, or None.

    `D=x cmd` does not count: in the shell a prefix assignment does not apply to
    the command's own expansions. `export`/`readonly`/`local` count.
    """
    try:
        argv = shlex.split(segment, posix=True)
    except ValueError:
        return None
    if argv and argv[0] in ("export", "readonly", "local"):
        argv = [a for a in argv[1:] if not a.startswith("-")]
    if not argv:
        return None
    pairs = [_ASSIGN_RE.match(a) for a in argv]
    if not all(pairs):
        return None
    return [(m.group(1), m.group(2)) for m in pairs]


def bash_targets(command):
    """The write targets of the line, with its variables already expanded.

    Walks the segments in order: an assignment only counts for what comes after
    it, and an assignment the gate cannot read (value with `$(...)` or with an
    unknown variable) ERASES the previous value — otherwise `D=docs;
    D=$(pwd); echo > $D/x` would match the old `docs`.
    """
    known = {}
    out = []
    for seg in S._split_segments(command):
        seg = seg.strip()
        if not seg:
            continue
        pairs = _assignments(seg)
        if pairs is not None:
            for name, value in pairs:
                value = _expand(value, known)
                if "$" in value or "`" in value:
                    known.pop(name, None)
                else:
                    known[name] = value
            continue
        for t in S._segment_targets(seg):
            t = S._unquote(t).strip()
            if not t or t in S._PSEUDO or t.startswith("&"):
                continue
            t = _expand(t, known)
            if t not in out:
                out.append(t)
        # `unset D`, `read D`, `let D=1`, `((D++))`: the command touches the
        # variable without being a simple assignment, and the value the gate
        # kept stopped being valid. Naming the variable without `$` is enough
        # to forget it: forgetting needlessly only leads to "unresolved", which
        # blocks; remembering needlessly would release a target the shell will
        # not use (pair-reviewer finding).
        for name in [n for n in known
                     if re.search(r"(?<![$\w{])" + n + r"\b", seg)]:
            del known[name]
    return out


def unresolved(target):
    """Does the target still have shell expansion after the line's variables and the environment's?"""
    path = os.path.expandvars(os.path.expanduser(target))
    return "$" in path or "`" in path


def relative_to(target, root):
    """The target relative to the session root, or None if it is outside it.

    Outside the root the gate gives no opinion: see decision 2 in the header.
    """
    path = os.path.expandvars(os.path.expanduser(target))
    if not os.path.isabs(path):
        path = os.path.join(root, path)
    path = os.path.normpath(path)
    base = os.path.normpath(root)
    if path == base:
        return None
    if not path.startswith(base + os.sep):
        return None
    return os.path.relpath(path, base).replace(os.sep, "/")


def allowed(rel, patterns):
    """`docs/**` is a directory prefix; the rest is fnmatch over the path.

    `fnmatch` alone does not serve the distinction the table makes: its `*`
    crosses `/`, so `docs/design/*` would match `docs/design/a/b/c` — which is
    even desired — but `docs/*` would also match `docs/design/x`, and then the
    discovery list (`docs/discovery/**`, `docs/spec/**`) would stop meaning what
    it says.
    """
    for pat in patterns:
        if pat.endswith("/**"):
            prefix = pat[:-2]  # keeps the trailing slash
            if rel.startswith(prefix):
                return True
        elif fnmatch.fnmatch(rel, pat):
            return True
    return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_MODO", "on") == "off":
            sys.exit(0)

        cwd = payload.get("cwd") or os.getcwd()
        root = _wtlib.session_root(cwd)
        mode = active_mode(root)
        if not mode:
            sys.exit(0)

        patterns = (_modes.MODES.get(mode) or {}).get("write")
        # Unknown mode (or one without a table entry) blocks nothing: the gate
        # CONCEDES the block, and when in doubt it does not concede.
        if not patterns or patterns == "tudo":
            sys.exit(0)

        found, undecidable = targets(payload.get("tool_name", ""),
                                     payload.get("tool_input", {}) or {})
        for target in found:
            if unresolved(target):
                # Blocks, because the destination could be anywhere — but
                # without the "outside the mode" message: see decision 5.
                T.emit("modo_escrita_nao_resolvido", cwd=cwd, modo=mode)
                print(
                    f"[write-mode-gate] BLOCKED: I could not resolve the "
                    f"target of this write, so I do not know whether it is "
                    f"inside mode {mode}.\n"
                    f"  Target as the gate read it: {target}\n"
                    f"  This is a limit of the gate's reading, not a verdict "
                    f"on the mode: a variable the line does not assign, "
                    f"$(...) and ${{X:-y}} are not expanded.\n"
                    f"  What to do: write the path in full (or assign the "
                    f"variable with a literal value in the same line) and run "
                    f"again. Allowed destinations: {', '.join(patterns)}",
                    file=sys.stderr,
                )
                sys.exit(2)
            rel = relative_to(target, root)
            if (rel is None or allowed(rel, _modes.ALWAYS_WRITABLE)
                    or allowed(rel, patterns)):
                continue
            produces = (_modes.MODES.get(mode) or {}).get("produces", "")
            print(
                f"[write-mode-gate] BLOCKED: this session operates in mode "
                f"{mode} and you were about to write outside what that mode "
                f"produces.\n"
                f"  Target: {target}\n"
                f"  Mode {mode} produces: {produces}\n"
                f"  Allowed destinations: {', '.join(patterns)}\n"
                f"  What to do: record this deviation through the "
                f"off-mode-capture skill and carry on with the mode's work. If "
                f"the deviation really has to happen NOW, end this mode and "
                f"open a session in the mode it belongs to — switching activity "
                f"has a cost, and that cost is what the mode exists to charge.",
                file=sys.stderr,
            )
            sys.exit(2)

        # No READABLE target outside the list — but the line may have written
        # where the gate cannot see. Warning instead of blocking is a choice
        # with a declared cost (see the header): blocking would hit the intent
        # and take every heredoc with it, which is how this repo runs scripts.
        if undecidable:
            T.emit("modo_escrita_indecidivel", cwd=cwd, modo=mode)
            print(
                f"[write-mode-gate] WARNING: this session operates in mode "
                f"{mode}, and this command uses a construct whose write "
                f"destination cannot be read (python -c, perl -e, ed, patch or "
                f"heredoc).\n"
                f"  The gate did NOT block, and did not check either: if the "
                f"command writes outside {', '.join(patterns)}, it just "
                f"punched through the mode with nothing recording the "
                f"deviation.\n"
                f"  If that is the case, record it through the off-mode-capture "
                f"skill.",
                file=sys.stderr,
            )
    except Exception as e:  # noqa: BLE001
        print(f"[write-mode-gate] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
