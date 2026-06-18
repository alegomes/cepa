#!/usr/bin/env python3
"""PreToolUse hook for the docs topology.

Enforces per-agent write boundaries across docs/ (the produced Diátaxis tree),
docs/_survey/ (the survey scratch), and the structural-move targets. Each worker
owns specific paths; the lead owns only the gap-report + status; the orchestrator
writes nothing.

Exit codes:
  0 — allowed
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

PLUGIN_NAME = "docs"

ALLOWED_WRITES = {
    # Orchestrator — main session, delegates only.
    "orchestrator":            [],

    # Lead — synthesizes the survey into the gap-report; tracks phase status.
    "docs-lead":               ["docs/_survey/gap-report.md", "docs/_survey/STATUS.md"],

    # Survey workers (fase 1, read-only on the codebase, one ledger each).
    "diataxis-inventory":      ["docs/_survey/inventory.md"],
    "how-extractor":           ["docs/_survey/how-ledger.md"],
    "flow-tracer":             ["docs/_survey/flows.md"],
    "rationale-archaeologist": ["docs/_survey/why-ledger.md", "docs/_survey/open-questions.md"],

    # Structural surgeon (fase 2) — archives exhaust, demotes rival front-doors.
    # Deliberately broad: this phase moves files across the doc tree and out to
    # archive/. Owner-gated by the /docs:declutter command, not by this glob.
    "structure-surgeon":       ["docs/**", "archive/**", ".process/**", "README.md", "AGENTS.md"],

    # Authoring workers (fase 4).
    "doc-author":              ["docs/how-to/**", "docs/reference/**", "docs/explanation/**", "docs/README.md"],
    "tutorial-author":         ["docs/tutorial/**"],

    # Finalization.
    "consistency-reviewer":    ["docs/_survey/consistency-review.md"],
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


def debug_log(payload: dict, resolved_agent: str) -> None:
    if os.environ.get("DOCS_PATHLOCK_DEBUG") != "1":
        return
    log_path = os.environ.get("DOCS_PATHLOCK_DEBUG_LOG", "/tmp/docs-pathlock-debug.log")
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
        print("[docs path-lock] could not parse hook payload; allowing", file=sys.stderr)
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
        # No prefix at all — either main session (empty agent_type) or a built-in
        # CC agent (statusline-setup, Explore, Plan, general-purpose, etc.).
        # Neither is from our plugin; not our concern. Fail-open.
        sys.exit(0)

    # Out-of-root writes are not this lock's jurisdiction. It enforces
    # boundaries WITHIN the project tree; a write to /tmp, $HOME, or a sibling
    # tree is none of our business. (Without this carve-out, relative_to() raises
    # ValueError and the write is falsely BLOCKED.)
    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()
    try:
        Path(file_path).resolve().relative_to(project_root)
    except ValueError:
        sys.exit(0)

    agent = detect_agent(payload)
    debug_log(payload, agent)

    if is_own_expertise_file(file_path, agent):
        sys.exit(0)

    allowed = ALLOWED_WRITES.get(agent)

    if allowed is None:
        print(
            f"[docs path-lock] BLOCKED: unknown agent {agent!r} attempted "
            f"{tool_name} on {file_path}. Add {agent!r} to "
            f"docs-topology/hooks/path-lock.py if this is intentional.",
            file=sys.stderr,
        )
        sys.exit(2)

    if path_matches(file_path, allowed, project_root):
        sys.exit(0)

    print(
        f"[docs path-lock] BLOCKED: agent {agent!r} cannot {tool_name} {file_path}.\n"
        f"  Allowed write globs for {agent!r}:\n  - "
        + "\n  - ".join(allowed or ["(none — only own expertise file)"])
        + f"\n  Plus its own expertise file: .claude/expertise/{agent}-mental-model.yaml\n"
        f"  Delegate to the appropriate worker instead.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
