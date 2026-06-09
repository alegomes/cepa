#!/usr/bin/env python3
"""PreToolUse hook (common) — the enforcement surface is off-limits to subagents.

WHY THIS EXISTS
---------------
The per-topology path-locks protect IN-PROJECT paths. They cannot protect the
files that DEFINE the rules, because those live outside any project root:
the installed plugin code under `~/.claude/plugins/`, the user's global
`~/.claude/settings.json` (which declares the hooks), and a project's own
`.claude/hooks/` + `.claude/settings*.json`.

A proof-reviewer agent, blocked from writing its output, edited
`~/.claude/plugins/cache/.../hooks/path-lock.py` via Bash to add itself to the
allowlist — a silent privilege escalation. Both the Write path-lock and the
Bash path-lock allowed it, because the target is out of project root and they
deliberately treat out-of-root as "not our business" (to avoid false positives
on /tmp, $HOME, build caches). The lock cannot defend itself with an
in-project allowlist.

This guard is the missing invariant: **no plugin subagent writes to the
enforcement / installed-plugin surface, anywhere on disk** — via Bash OR
Edit/Write/MultiEdit. The main session and built-in (non-prefixed) agents are
NOT gated, so you can still reinstall, edit settings, and manage plugins.

PROTECTED SURFACES (any `.claude` segment in the resolved path):
  - `<...>/.claude/plugins/**`            — installed plugin code (the incident)
  - `<...>/.claude/hooks/**`              — hook scripts (home or project)
  - `<...>/.claude/settings.json`,
    `<...>/.claude/settings.local.json`,
    `<...>/.claude/keybindings.json`      — hook/keybinding definitions

CARVE-OUT: an agent's OWN expertise file (`<agent>-mental-model.yaml` in an
`expertise/` dir) stays writable even under `~/.claude/plugins/.../expertise/`,
because that is its legitimate mental-model home. Filename is keyed to the
agent's own name, so it can only ever write its own.

Exit codes:
  0 — allowed (not a protected target, out of scope, or own expertise file)
  2 — blocked: a write to the enforcement surface
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

_REDIR_RE = re.compile(r"""(?<![0-9&])>>?\s*(?!&)("[^"]+"|'[^']+'|[^\s;&|<>()]+)""")
_PSEUDO = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")
_SEP_RE = re.compile(r"(?:\|\||&&|[;|&\n])")
_SETTINGS_FILES = {"settings.json", "settings.local.json", "keybindings.json"}
_GATED_FILE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def _unquote(tok: str) -> str:
    if len(tok) >= 2 and tok[0] in "\"'" and tok[-1] == tok[0]:
        return tok[1:-1]
    return tok


def _is_flag(tok: str) -> bool:
    return tok.startswith("-") and tok != "-"


def _segment_targets(segment: str) -> list:
    targets = [_unquote(m.group(1)) for m in _REDIR_RE.finditer(segment)]
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
        if any(t.startswith("-i") or t.startswith("--in-place") for t in rest):
            targets.extend(nonflags[1:] if len(nonflags) >= 2 else nonflags)
    elif cmd in ("cp", "mv", "install"):
        if len(nonflags) >= 2:
            targets.append(nonflags[-1])
    elif cmd == "dd":
        targets.extend(t[3:] for t in rest if t.startswith("of="))
    elif cmd == "truncate":
        targets.extend(nonflags[1:] if nonflags else [])
    return targets


def extract_bash_targets(command: str) -> list:
    out, seen = [], set()
    for seg in _SEP_RE.split(command):
        seg = seg.strip()
        if not seg:
            continue
        for t in _segment_targets(seg):
            t = _unquote(t).strip()
            if not t or t in _PSEUDO or t.startswith("&") or t in seen:
                continue
            seen.add(t)
            out.append(t)
    return out


def resolve_target(t: str, project_root: Path) -> Path:
    """Expand ~ and $HOME, then resolve (relative paths against project root)."""
    t = os.path.expandvars(os.path.expanduser(t))
    p = Path(t)
    if not p.is_absolute():
        p = project_root / p
    try:
        return p.resolve()
    except (OSError, RuntimeError):
        return p


def is_own_expertise_file(cand: Path, agent: str) -> bool:
    return cand.name == f"{agent}-mental-model.yaml" and cand.parent.name == "expertise"


def protected_reason(cand: Path) -> str:
    """Return a human reason if `cand` is on the enforcement surface, else ''."""
    parts = cand.parts
    for i, part in enumerate(parts):
        if part != ".claude":
            continue
        child = parts[i + 1] if i + 1 < len(parts) else ""
        if child == "plugins":
            return "installed plugin code under .claude/plugins/"
        if child == "hooks":
            return "hook scripts under .claude/hooks/"
        if child in _SETTINGS_FILES:
            return f"hook/keybinding definitions ({child})"
    return ""


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[enforcement-guard] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    # Only gate plugin SUBAGENTS. No prefix → main session or a built-in agent
    # → not gated, so the human can reinstall / edit settings / manage plugins.
    raw_agent_type = payload.get("agent_type", "") or ""
    if ":" not in raw_agent_type:
        sys.exit(0)
    agent = raw_agent_type.split(":", 1)[1]

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()

    if tool_name in _GATED_FILE_TOOLS:
        fp = tool_input.get("file_path", "")
        targets = [fp] if fp else []
    elif tool_name == "Bash":
        targets = extract_bash_targets(tool_input.get("command", ""))
    else:
        sys.exit(0)

    for t in targets:
        cand = resolve_target(t, project_root)
        if is_own_expertise_file(cand, agent):
            continue
        reason = protected_reason(cand)
        if reason:
            print(
                f"[enforcement-guard] BLOCKED: agent {agent!r} attempted to write the "
                f"enforcement surface — {reason}.\n"
                f"  Target: {t}\n"
                f"  Editing the code/config that DEFINES the rules to grant yourself "
                f"permission is a silent privilege escalation, even if the change looks "
                f"correct. The enforcement surface is never an agent's to edit.\n"
                f"  STOP and report the block (agent, target, and what you needed) so a "
                f"human fixes the policy in the SOURCE repo — not the installed cache, "
                f"which a reinstall overwrites.",
                file=sys.stderr,
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
