#!/usr/bin/env python3
"""PreToolUse hook: enforce per-agent path-write locks for the git-history plugin.

Same contract as the other topology plugins' path-lock: read the JSON payload,
identify the calling agent, allow its own expertise file anywhere, otherwise
match the target against the agent's allowed write-globs (project-root-relative).

Note: this gates Edit/Write/MultiEdit only. The collector/renderer scripts write
datapack.json and PNGs via Bash, which is not gated here — that's intentional;
those are deterministic, idempotent artifacts under git-history-report/.

Exit codes:
  0 — allowed
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

PLUGIN_NAME = "git-history"

# Keep these globs identical to the "Writes" row in each agent's .md file so
# the prompt and the physical lock never drift apart.
ALLOWED_WRITES = {
    "orchestrator":       [],
    "git-historian":      [],                      # lead — synthesizes, writes nothing
    "history-collector":  ["git-history-report/**"],
    "history-narrator":   ["git-history-report/**"],
}

GATED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def detect_agent(payload: dict) -> str:
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
    return p.name == f"{agent}-mental-model.yaml" and p.parent.name == "expertise"


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
        print("[path-lock] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if tool_name not in GATED_TOOLS:
        sys.exit(0)

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    raw_agent_type = payload.get("agent_type", "") or ""
    if ":" in raw_agent_type:
        if raw_agent_type.split(":", 1)[0] != PLUGIN_NAME:
            sys.exit(0)  # not our plugin's agent
    else:
        sys.exit(0)  # main session or built-in agent — not our concern

    agent = detect_agent(payload)

    if is_own_expertise_file(file_path, agent):
        sys.exit(0)

    allowed = ALLOWED_WRITES.get(agent)
    if allowed is None:
        print(
            f"[path-lock] BLOCKED: unknown agent {agent!r} attempted "
            f"{tool_name} on {file_path}. Add {agent!r} to "
            f"git-history/hooks/path-lock.py if this is intentional.",
            file=sys.stderr,
        )
        sys.exit(2)

    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()
    if path_matches(file_path, allowed, project_root):
        sys.exit(0)

    print(
        f"[path-lock] BLOCKED: agent {agent!r} cannot {tool_name} {file_path}.\n"
        f"  Allowed write globs for {agent!r}:\n  - "
        + "\n  - ".join(allowed or ["(none — only own expertise file)"])
        + f"\n  Plus its own expertise file: .claude/expertise/{agent}-mental-model.yaml",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
