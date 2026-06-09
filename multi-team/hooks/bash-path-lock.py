#!/usr/bin/env python3
"""PreToolUse hook for the multi-team topology — the BASH half of the path-lock.

WHY THIS EXISTS
---------------
`path-lock.py` gates Edit / Write / MultiEdit / NotebookEdit. It does NOT see
Bash. An agent whose Write is blocked can reach for the shell — `sed -i`,
`cat > file`, `tee`, a heredoc — and land the exact write the path-lock was
meant to stop. A control enforced on one tool but not its equivalent is not a
control. This hook is the SECOND lock.

It reuses path-lock.py's ALLOWED_WRITES (single source of truth — never
re-declare globs here) and applies it to shell-level writes.

DESIGN — deliberately narrow, to keep false positives near zero
---------------------------------------------------------------
- We only fire on writes the SHELL performs explicitly: redirections
  (`>`, `>>`), `tee`, `sed -i`, `cp`, `mv`, `install`, `dd of=`, `truncate`.
- We do NOT inspect what a subprocess writes internally (a test runner, git,
  a bundler) — those are invisible here, which is correct.
- We only flag a target that resolves INSIDE the project tree. Writes to
  /tmp, /dev/null, caches, $HOME — out of scope, always allowed.
- Main session / built-in agents (no plugin-prefixed agent_type) are NOT
  gated — same fail-open contract as path-lock.py.

HONEST LIMITS (guardrail, not a sandbox)
----------------------------------------
We cannot see writes done by `python -c`, `perl -e`, `ruby -e`, `node -e`,
`awk -i inplace`, `ed`, `patch`, or a heredoc body fed to an interpreter.
When detected we fail open but log to BASH_PATHLOCK_COVERAGE_LOG (default
/tmp/multiteam-bash-pathlock-uncovered.log) so the gap is visible, never
silent. The agent's own discipline (prompt + expertise) is the primary
control; this is defense-in-depth under it.

Exit codes:
  0 — allowed (or out of scope, or could not analyze → fail-open + logged)
  2 — blocked: a shell write to an in-project path outside the agent's allowlist
"""

import importlib.util
import json
import os
import re
import shlex
import sys
from pathlib import Path

PLUGIN_NAME = "multi-team"


def _load_pathlock_module():
    """Import the sibling path-lock.py (hyphen in the filename → importlib)."""
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(
        "multiteam_path_lock", str(here / "path-lock.py")
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

_UNCOVERED_RE = re.compile(
    r"""(?:
        \bpython3?\s+-c\b | \bperl\s+-[eE]\b | \bruby\s+-e\b | \bnode\s+-e\b |
        \bawk\b[^|;&]*\b-i\b | \b-i\s+inplace\b | \bgawk\b[^|;&]*\binplace\b |
        \bed\b | \bpatch\b | <<-?\s*['"]?\w+   # heredoc
    )""",
    re.VERBOSE,
)

_PSEUDO = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")
_SEP_RE = re.compile(r"(?:\|\||&&|[;|&\n])")


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] in "\"'" and tok[-1] == tok[0]:
        return tok[1:-1]
    return tok


def _is_flag(tok: str) -> bool:
    return tok.startswith("-") and tok != "-"


def _segment_targets(segment: str) -> list:
    targets = []
    for m in _REDIR_RE.finditer(segment):
        targets.append(_unquote(m.group(1)))

    try:
        argv = shlex.split(segment, posix=True)
    except ValueError:
        argv = segment.split()
    if not argv:
        return targets

    cmd = os.path.basename(argv[0])
    rest = argv[1:]
    nonflags = [t for t in rest if not _is_flag(t)]

    if cmd == "tee":
        targets.extend(nonflags)
    elif cmd == "sed":
        if any(t == "-i" or t.startswith("-i") or t == "--in-place"
               or t.startswith("--in-place") for t in rest):
            if len(nonflags) >= 2:
                targets.extend(nonflags[1:])
            elif nonflags:
                targets.extend(nonflags)
    elif cmd in ("cp", "mv", "install"):
        if len(nonflags) >= 2:
            targets.append(nonflags[-1])
    elif cmd == "dd":
        for t in rest:
            if t.startswith("of="):
                targets.append(t[3:])
    elif cmd == "truncate":
        targets.extend(nonflags[1:] if nonflags else [])

    return targets


def extract_write_targets(command: str) -> tuple:
    targets = []
    for seg in _SEP_RE.split(command):
        seg = seg.strip()
        if seg:
            targets.extend(_segment_targets(seg))
    clean = []
    seen = set()
    for t in targets:
        t = _unquote(t).strip()
        if not t or t in _PSEUDO or t.startswith("&") or t in seen:
            continue
        seen.add(t)
        clean.append(t)
    return clean, bool(_UNCOVERED_RE.search(command))


def log_uncovered(command: str, agent: str) -> None:
    log_path = os.environ.get(
        "BASH_PATHLOCK_COVERAGE_LOG", "/tmp/multiteam-bash-pathlock-uncovered.log"
    )
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps({"agent": agent, "command": command[:500]}) + "\n")
    except OSError:
        pass


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[multi-team bash-path-lock] could not parse hook payload; allowing",
              file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name", "") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "")
    if not command.strip():
        sys.exit(0)

    raw_agent_type = payload.get("agent_type", "") or ""
    if ":" not in raw_agent_type or raw_agent_type.split(":", 1)[0] != PLUGIN_NAME:
        sys.exit(0)

    pl = _load_pathlock_module()
    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()
    agent = pl.detect_agent(payload)
    allowed = pl.ALLOWED_WRITES.get(agent)

    targets, has_uncovered = extract_write_targets(command)
    if has_uncovered:
        log_uncovered(command, agent)

    if not targets:
        sys.exit(0)

    violations = []
    for t in targets:
        cand = (project_root / t).resolve() if not os.path.isabs(t) else Path(t).resolve()
        try:
            cand.relative_to(project_root)
        except ValueError:
            continue
        cand_str = str(cand)
        if pl.is_own_expertise_file(cand_str, agent):
            continue
        if allowed and pl.path_matches(cand_str, allowed, project_root):
            continue
        violations.append(t)

    if not violations:
        sys.exit(0)

    allowed_disp = "\n  - ".join(allowed or ["(none — only own expertise file)"])
    print(
        f"[multi-team bash-path-lock] BLOCKED: agent {agent!r} attempted a "
        f"shell-level write to a path outside its allowlist via Bash.\n"
        f"  Offending target(s): {', '.join(violations)}\n"
        f"  Command: {command[:300]}\n"
        f"  Allowed write globs for {agent!r}:\n  - {allowed_disp}\n"
        f"  Writing source via Bash (sed -i / cat > / tee / heredoc) bypasses "
        f"the path-lock — that is a delegation bypass, not a workaround.\n"
        f"  Use the Write tool (which the path-lock governs) for paths you own, "
        f"or delegate to the worker that owns this path.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
