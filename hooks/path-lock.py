#!/usr/bin/env python3
"""PreToolUse hook: enforce per-agent path-write locks.

Claude Code invokes this before every Edit / Write / MultiEdit call. We:
  1. Read the JSON payload from stdin.
  2. Identify which agent is calling (subagent name, or "orchestrator" if
     the call comes from the main session).
  3. Look up the allowed write-glob list for that agent.
  4. Match the target file_path. If outside, exit 2 (CC blocks the call).

Exit codes:
  0 — allowed
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

# Per-agent write allowlist. Keep these globs identical to the prose in
# each subagent's .md file's "Domain" section so the prompt and the
# physical lock can never drift apart.
ALLOWED_WRITES = {
    # leads — no code edits, only their own expertise (and specs for planning)
    "orchestrator":      [".claude/expertise/orchestrator-mental-model.yaml"],
    "planning-lead":     ["specs/**", ".claude/expertise/planning-lead-mental-model.yaml"],
    "engineering-lead":  [".claude/expertise/engineering-lead-mental-model.yaml"],
    "validation-lead":   [".claude/expertise/validation-lead-mental-model.yaml"],

    # workers — domain-locked
    "product-manager":   ["specs/**", ".claude/expertise/product-manager-mental-model.yaml"],
    "ux-researcher":     ["specs/**", ".claude/expertise/ux-researcher-mental-model.yaml"],
    "frontend-dev":      ["apps/*/web/**", "apps/*/frontend/**",
                          ".claude/expertise/frontend-dev-mental-model.yaml"],
    "backend-dev":       ["apps/*/api/**", "apps/*/backend/**", "apps/*/migrations/**",
                          "apps/classifier/**",
                          ".claude/expertise/backend-dev-mental-model.yaml"],
    "qa-engineer":       ["tests/**", "apps/*/tests/**", "apps/*/__tests__/**",
                          ".claude/expertise/qa-engineer-mental-model.yaml"],
    "security-reviewer": ["specs/security-reviews/**",
                          ".claude/expertise/security-reviewer-mental-model.yaml"],
}

# Tools we gate. Other tools pass through.
GATED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def detect_agent(payload: dict) -> str:
    """Best-effort: figure out which agent triggered this tool call."""
    # 1. Hook payload may carry it directly (varies by CC version).
    for key in ("agent_name", "subagent_name", "agent", "subagent_type"):
        if key in payload and payload[key]:
            return payload[key]
    # 2. Some CC versions expose via env.
    for env_key in ("CLAUDE_AGENT_NAME", "CLAUDE_SUBAGENT_NAME"):
        v = os.environ.get(env_key)
        if v:
            return v
    # 3. Fall back: the main session is the orchestrator.
    return "orchestrator"


def path_matches(file_path: str, globs: list[str], project_root: Path) -> bool:
    """Match against globs interpreted relative to project root."""
    try:
        rel = str(Path(file_path).resolve().relative_to(project_root))
    except ValueError:
        # Outside the project — never allowed.
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
        + "\n  - ".join(allowed)
        + "\n  Delegate to the appropriate worker instead.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
