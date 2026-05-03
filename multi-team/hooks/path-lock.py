#!/usr/bin/env python3
"""PreToolUse hook: enforce per-agent path-write locks.

Claude Code invokes this before every Edit / Write / MultiEdit call. We:
  1. Read the JSON payload from stdin.
  2. Identify which agent is calling (subagent name, or "orchestrator" if
     the call comes from the main session).
  3. Allow if the target is the agent's own expertise file (anywhere on disk
     — see `is_own_expertise_file`).
  4. Otherwise look up the allowed write-glob list for that agent.
  5. Match the target file_path. If outside, exit 2 (CC blocks the call).

Exit codes:
  0 — allowed
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

# Per-agent in-project write allowlist. Keep these globs identical to the
# prose in each subagent's .md file's "Writes" row so the prompt and the
# physical lock can never drift apart.
#
# The agent's *expertise* file (`common/expertise/<agent>-mental-model.yaml`)
# is NOT listed here — it's allowed via the structural `is_own_expertise_file`
# check below, which works regardless of where the plugin lives on disk.
ALLOWED_WRITES = {
    # leads — no code edits
    "orchestrator":      [],
    "planning-lead":     ["specs/**"],
    "engineering-lead":  [],
    "validation-lead":   [],

    # workers — domain-locked
    "product-manager":   ["specs/**"],
    "ux-researcher":     ["specs/**"],
    "frontend-dev":      ["apps/*/web/**", "apps/*/frontend/**"],
    "backend-dev":       ["apps/*/api/**", "apps/*/backend/**", "apps/*/migrations/**",
                          "apps/classifier/**"],
    "qa-engineer":       ["tests/**", "apps/*/tests/**", "apps/*/__tests__/**"],
    "security-reviewer": ["specs/security-reviews/**"],
}

# Tools we gate. Other tools pass through.
GATED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def detect_agent(payload: dict) -> str:
    """Figure out which agent triggered this tool call.

    CC 2.1.x sends `agent_type` in PreToolUse payloads when a subagent is the
    caller. The value is plugin-namespaced (e.g. "multi-team:backend-dev"); we
    strip the prefix to match the bare names used in ALLOWED_WRITES.

    When the call comes from the main session (no subagent), `agent_type` is
    absent and we fall back to "orchestrator".
    """
    agent_type = payload.get("agent_type", "")
    if agent_type:
        return agent_type.split(":", 1)[1] if ":" in agent_type else agent_type
    # Legacy / alternate keys (kept defensively for older CC versions).
    for key in ("agent_name", "subagent_name", "agent", "subagent_type"):
        if key in payload and payload[key]:
            return payload[key]
    for env_key in ("CLAUDE_AGENT_NAME", "CLAUDE_SUBAGENT_NAME"):
        v = os.environ.get(env_key)
        if v:
            return v
    return "orchestrator"


def is_own_expertise_file(file_path: str, agent: str) -> bool:
    """An agent's expertise file is allowed regardless of disk location.

    Centralized expertise lives in the plugin (`common/expertise/<agent>-mental-model.yaml`)
    rather than in the host project, but the on-disk path varies by install method
    (local-marketplace path, plugin cache, etc.). We identify expertise files by
    structure, not absolute path: filename matches `<agent>-mental-model.yaml` AND
    the parent directory is named `expertise`.
    """
    p = Path(file_path)
    return (
        p.name == f"{agent}-mental-model.yaml"
        and p.parent.name == "expertise"
    )


def path_matches(file_path: str, globs: list[str], project_root: Path) -> bool:
    """Match against globs interpreted relative to project root."""
    try:
        rel = str(Path(file_path).resolve().relative_to(project_root))
    except ValueError:
        # Outside the project — never allowed via in-project globs.
        return False
    rel_posix = rel.replace(os.sep, "/")
    for g in globs:
        if fnmatch.fnmatchcase(rel_posix, g):
            return True
        # fnmatch doesn't treat ** specially; expand "a/**" → match anything
        # under "a/" by also matching the literal prefix.
        if g.endswith("/**") and (rel_posix == g[:-3] or rel_posix.startswith(g[:-2])):
            return True
    return False


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        # Malformed payload — fail open so we don't break the session.
        # Log to stderr so it surfaces in `claude --debug`.
        print(f"[path-lock] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if tool_name not in GATED_TOOLS:
        sys.exit(0)

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    agent = detect_agent(payload)

    # Always allow the agent to write its own expertise file, regardless of
    # whether the plugin lives in a marketplace cache, a local clone, or anywhere
    # else on disk. Each agent can only write its own file (filename keyed by name).
    if is_own_expertise_file(file_path, agent):
        sys.exit(0)

    allowed = ALLOWED_WRITES.get(agent)

    # Unknown agent — fail closed. Add it to ALLOWED_WRITES if it's legit.
    if allowed is None:
        print(
            f"[path-lock] BLOCKED: unknown agent {agent!r} attempted "
            f"{tool_name} on {file_path}. Add {agent!r} to "
            f".claude/hooks/path-lock.py if this is intentional.",
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
        + f"\n  Plus its own expertise file: .claude/expertise/{agent}-mental-model.yaml\n"
        f"  Delegate to the appropriate worker instead.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
