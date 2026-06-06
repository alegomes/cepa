#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write|MultiEdit): record which top-level dirs a
session touches, into its registry entry.

Feeds two things: the "multi-area" flag in the unmerged-worktree reminder /
`/common:worktree-list` (so you can see a worktree is heterogeneous before you
merge it), and a cheap structural signal of what the session is actually
working on. Pure bookkeeping — never blocks, exit 0 always.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402


def top_dir(file_path: str, cwd: str) -> str:
    try:
        rel = os.path.relpath(os.path.abspath(file_path), cwd)
    except ValueError:
        return ""
    if rel.startswith(".."):
        return ""  # outside the tree
    parts = rel.split(os.sep)
    return parts[0] if len(parts) > 1 else "(root)"


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    if payload.get("tool_name") not in {"Edit", "Write", "MultiEdit"}:
        sys.exit(0)
    session_id = payload.get("session_id") or ""
    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not session_id or not file_path:
        sys.exit(0)
    cwd = os.path.abspath(payload.get("cwd") or os.getcwd())

    try:
        root = L.main_root(cwd)
        entry = L.find_entry(root, session_id)
        if not entry:
            sys.exit(0)  # session not registered (e.g. started before install)
        d = top_dir(file_path, cwd)
        if d and not d.startswith(".claude"):
            touched = entry.setdefault("touched_dirs", {})
            touched[d] = touched.get(d, 0) + 1
            entry["last_seen"] = L.now_iso()
            L.write_entry(root, session_id, entry)
    except Exception as e:  # noqa: BLE001
        print(f"[session-activity] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
