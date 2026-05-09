#!/usr/bin/env python3
"""PreToolUse hook for the book topology.

Enforces per-agent write boundaries across manuscript/ and code/.
Each worker owns specific file names within the chapter directories;
leads own only top-level manuscript files.

Exit codes:
  0 — allowed
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

PLUGIN_NAME = "book"

ALLOWED_WRITES = {
    # Leads — orchestrate, don't write chapter content.
    "orchestrator":       [],
    "book-architect":     ["manuscript/BOOK.md", "manuscript/audience.md"],
    "writing-lead":       [],

    # Inception worker.
    "audience-profiler":  ["manuscript/audience.md"],

    # Per-chapter workers — each owns one file type within any chapter dir.
    "chapter-outliner":   ["manuscript/*/outline.md"],
    "researcher":         ["manuscript/*/research.md", "manuscript/*/references.md"],
    "technical-writer":   ["manuscript/*/draft.md"],
    "code-author":        ["code/**"],
    "exercise-designer":  ["manuscript/*/exercises.md"],
    "technical-reviewer":   ["manuscript/*/review-technical.md"],
    "copy-editor":          ["manuscript/*/review-copy.md"],

    # Finalization workers.
    "continuity-reviewer":  ["manuscript/continuity-review.md"],
    "manuscript-compiler":  ["manuscript/compiled/**"],
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
    if os.environ.get("BOOK_PATHLOCK_DEBUG") != "1":
        return
    log_path = os.environ.get("BOOK_PATHLOCK_DEBUG_LOG", "/tmp/book-pathlock-debug.log")
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
        print("[book path-lock] could not parse hook payload; allowing", file=sys.stderr)
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
    elif not raw_agent_type:
        sys.exit(0)

    agent = detect_agent(payload)
    debug_log(payload, agent)

    if is_own_expertise_file(file_path, agent):
        sys.exit(0)

    allowed = ALLOWED_WRITES.get(agent)

    if allowed is None:
        print(
            f"[book path-lock] BLOCKED: unknown agent {agent!r} attempted "
            f"{tool_name} on {file_path}. Add {agent!r} to "
            f"book/hooks/path-lock.py if this is intentional.",
            file=sys.stderr,
        )
        sys.exit(2)

    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()

    if path_matches(file_path, allowed, project_root):
        sys.exit(0)

    print(
        f"[book path-lock] BLOCKED: agent {agent!r} cannot {tool_name} {file_path}.\n"
        f"  Allowed write globs for {agent!r}:\n  - "
        + "\n  - ".join(allowed or ["(none — only own expertise file)"])
        + f"\n  Plus its own expertise file: .claude/expertise/{agent}-mental-model.yaml\n"
        f"  Delegate to the appropriate worker instead.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
