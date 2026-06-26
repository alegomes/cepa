#!/usr/bin/env python3
"""PreToolUse hook for the discovery topology.

Same structure as build-team and build-hex path-locks, but keyed to the
discovery topology's artifact area: docs/discovery/<card-key>/**.

Discovery agents don't write source code. They write framings, research
notes, assumption maps, test plans, evidence summaries, and handoff briefs
under docs/discovery/. The path-lock enforces that.

Exit codes:
  0 — allowed
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

PLUGIN_NAME = "discovery"

ALLOWED_WRITES = {
    # Lead — orchestrates only, writes nothing except own expertise file.
    "discovery-lead":      [],

    # Workers — all write under docs/discovery/<card-key>/**.
    "opportunity-framer":  ["docs/discovery/**"],
    "user-researcher":     ["docs/discovery/**"],
    "assumption-tester":   ["docs/discovery/**"],
    "evidence-auditor":    ["docs/discovery/**"],
    "epic-briefer":        ["docs/discovery/**"],
}

GATED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def detect_agent(payload: dict) -> str:
    """Figure out which agent triggered this tool call."""
    agent_type = payload.get("agent_type", "")
    if agent_type:
        return agent_type.split(":", 1)[1] if ":" in agent_type else agent_type
    for key in ("agent_name", "subagent_name", "agent", "subagent_type"):
        if key in payload and payload[key]:
            return payload[key]
    for env_key in ("CLAUDE_AGENT_NAME", "CLAUDE_SUBAGENT_NAME"):
        v = os.environ.get(env_key)
        if v:
            return v
    return "orchestrator"


def is_own_expertise_file(file_path: str, agent: str) -> bool:
    p = Path(file_path)
    return (
        p.name == f"{agent}-mental-model.yaml"
        and p.parent.name == "expertise"
    )


def path_matches(file_path: str, globs: list, project_root: Path) -> bool:
    try:
        rel = str(Path(file_path).resolve().relative_to(project_root))
    except ValueError:
        return False
    rel_posix = rel.replace(os.sep, "/")
    for g in globs:
        if fnmatch.fnmatchcase(rel_posix, g):
            return True
        if g.endswith("/**") and (rel_posix == g[:-3] or rel_posix.startswith(g[:-2])):
            return True
    return False


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[discovery path-lock] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if tool_name not in GATED_TOOLS:
        sys.exit(0)

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    raw_agent_type = payload.get("agent_type", "") or ""
    if ":" in raw_agent_type:
        prefix = raw_agent_type.split(":", 1)[0]
        if prefix != PLUGIN_NAME:
            sys.exit(0)
    else:
        # No prefix at all — either main session (empty agent_type) or a
        # built-in CC agent (statusline-setup, Explore, Plan, general-purpose,
        # etc.). Neither is from our plugin; not our concern. Fail-open.
        sys.exit(0)

    # Out-of-root writes are not this lock's jurisdiction. It enforces
    # architectural boundaries WITHIN the project tree; a write to /tmp, $HOME,
    # or a sibling tree is none of our business. (Same carve-out bash-path-lock.py
    # already applies; without it, relative_to() raises ValueError and the write
    # is falsely BLOCKED.) The enforcement-guard hook still blocks subagent writes
    # to plugins/hooks/settings regardless of location.
    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()
    try:
        Path(file_path).resolve().relative_to(project_root)
    except ValueError:
        sys.exit(0)

    agent = detect_agent(payload)

    if is_own_expertise_file(file_path, agent):
        sys.exit(0)

    allowed = ALLOWED_WRITES.get(agent)

    if allowed is None:
        print(
            f"[discovery path-lock] BLOCKED: unknown agent {agent!r} attempted "
            f"{tool_name} on {file_path}. Add {agent!r} to "
            f"discovery/hooks/path-lock.py if this is intentional.",
            file=sys.stderr,
        )
        sys.exit(2)

    if path_matches(file_path, allowed, project_root):
        sys.exit(0)

    print(
        f"[discovery path-lock] BLOCKED: agent {agent!r} cannot {tool_name} {file_path}.\n"
        f"  Allowed write globs for {agent!r}:\n  - "
        + "\n  - ".join(allowed or ["(none — only own expertise file)"])
        + f"\n  Plus its own expertise file: .claude/expertise/{agent}-mental-model.yaml\n"
        f"  Delegate to the appropriate worker instead.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
