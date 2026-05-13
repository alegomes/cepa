#!/usr/bin/env python3
"""PreToolUse hook for the hex-backend topology.

Same structure and detection logic as multi-team's path-lock.py, but the
ALLOWED_WRITES table is keyed to a hexagonal-architecture Maven layout:
  domain/        application/        api-rest/        infrastructure/        bootstrap/

Each module has src/main and src/test. Workers are domain/api/adapter-aware.

Exit codes:
  0 — allowed
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

PLUGIN_NAME = "hex-backend"

ALLOWED_WRITES = {
    # Orchestrator + leads — no source writes; only own expertise file.
    "orchestrator":      [],
    "planning-lead":     ["spec/**", "specs/**", "docs/**"],
    "engineering-lead":  ["docs/tasks/**", "docs/investigations/**", "pom.xml", "**/pom.xml"],
    "validation-lead":   [],

    # Planning workers — write specs and decomposition artifacts.
    "epic-author":       ["spec/**", "specs/**", "docs/**"],
    "product-manager":   ["spec/**", "specs/**", "docs/**"],
    "integration-analyst": ["spec/**", "specs/**", "docs/**"],

    # Engineering workers — domain-aware writes per hex layer.
    "domain-dev":        ["domain/src/main/**",
                          "application/src/main/**"],
    "api-dev":           ["api-rest/src/main/**"],
    "adapter-dev":       ["infrastructure/src/main/**",
                          "bootstrap/src/main/**"],

    # Validation workers.
    "qa-engineer":       ["domain/src/test/**",
                          "application/src/test/**",
                          "api-rest/src/test/**",
                          "infrastructure/src/test/**",
                          "bootstrap/src/test/**"],
    "refactor-advisor":  ["docs/housekeeping/**"],
    "security-reviewer": ["docs/security-reviews/**"],
    "code-reviewer":     [],   # advisory only, no writes
}

GATED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def detect_agent(payload: dict) -> str:
    """Figure out which agent triggered this tool call.

    CC sends `agent_type` in PreToolUse payloads when a subagent is the caller.
    Plugin-namespaced as `<plugin>:<agent>`; we strip the prefix.
    """
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


def debug_log(payload: dict, resolved_agent: str) -> None:
    """When HEX_PATHLOCK_DEBUG=1, append a JSON line to the debug log so we can
    see what CC actually sends in the PreToolUse payload. Default log path is
    /tmp/hex-pathlock-debug.log; override with HEX_PATHLOCK_DEBUG_LOG."""
    if os.environ.get("HEX_PATHLOCK_DEBUG") != "1":
        return
    log_path = os.environ.get("HEX_PATHLOCK_DEBUG_LOG", "/tmp/hex-pathlock-debug.log")
    identity_keys = ("agent_type", "agent_name", "subagent_name", "agent", "subagent_type")
    snapshot = {
        "top_level_keys": sorted(payload.keys()),
        "identity_fields": {k: payload.get(k) for k in identity_keys},
        "env_agent_vars": {
            k: os.environ.get(k)
            for k in ("CLAUDE_AGENT_NAME", "CLAUDE_SUBAGENT_NAME")
            if os.environ.get(k)
        },
        "resolved_agent": resolved_agent,
        "tool_name": payload.get("tool_name"),
        "file_path": (payload.get("tool_input") or {}).get("file_path"),
    }
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(snapshot) + "\n")
    except OSError:
        pass


def is_own_expertise_file(file_path: str, agent: str) -> bool:
    """Each agent can write its own `<agent>-mental-model.yaml` regardless of
    where it lives on disk (host symlink to plugin source, or plugin cache)."""
    p = Path(file_path)
    return (
        p.name == f"{agent}-mental-model.yaml"
        and p.parent.name == "expertise"
    )


def path_matches(file_path: str, globs: list[str], project_root: Path) -> bool:
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
        print(f"[hex-backend path-lock] could not parse hook payload; allowing", file=sys.stderr)
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

    agent = detect_agent(payload)
    debug_log(payload, agent)

    if is_own_expertise_file(file_path, agent):
        sys.exit(0)

    allowed = ALLOWED_WRITES.get(agent)

    if allowed is None:
        print(
            f"[hex-backend path-lock] BLOCKED: unknown agent {agent!r} attempted "
            f"{tool_name} on {file_path}. Add {agent!r} to "
            f"hex-backend/hooks/path-lock.py if this is intentional.",
            file=sys.stderr,
        )
        sys.exit(2)

    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()

    if path_matches(file_path, allowed, project_root):
        sys.exit(0)

    print(
        f"[hex-backend path-lock] BLOCKED: agent {agent!r} cannot {tool_name} {file_path}.\n"
        f"  Allowed write globs for {agent!r}:\n  - "
        + "\n  - ".join(allowed or ["(none — only own expertise file)"])
        + f"\n  Plus its own expertise file: .claude/expertise/{agent}-mental-model.yaml\n"
        f"  Delegate to the appropriate worker instead.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
