#!/usr/bin/env python3
"""CLI behind /common:worktree-list — a dashboard of session worktrees.

Reports, per `session/*` worktree: branch, base, commits ahead, dirty/clean,
live/idle, age, areas touched (multi-area flag), conflict prediction against
its base (via `git merge-tree`, no working-tree change), and last build status.

Usage: python3 session-worktrees.py [--cwd <dir>]
Reads the registry from the main worktree; safe to run from anywhere in the repo.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402


def build_status(wt_path: str) -> str:
    f = os.path.join(wt_path, ".claude", "last-build.json")
    try:
        return json.loads(open(f, encoding="utf-8").read()).get("status", "?")
    except (OSError, json.JSONDecodeError):
        return "—"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", default=os.getcwd())
    args = ap.parse_args()

    root = L.main_root(os.path.abspath(args.cwd))
    if not root:
        print("Not inside a git repository.")
        return 0

    rows = L.classify(root, predict=True)
    if not rows:
        print("No session worktrees. (You're working solo in the main tree — "
              "nothing to isolate or merge.)")
        return 0

    print(f"Session worktrees for {root}:\n")
    for c in rows:
        conflict = c.get("conflict")
        conflict_s = ("⚠ will CONFLICT" if conflict is True
                      else "clean merge" if conflict is False else "merge: ?")
        flags = []
        if c["alive"]:
            flags.append("LIVE")
        if c["dirty"]:
            flags.append("dirty")
        if c["merged"]:
            flags.append("merged/empty")
        areas = f" · areas: {', '.join(c['areas'][:5])}" if c["areas"] else ""
        multi = " (multi-area!)" if c["multi_area"] else ""
        print(f"• {c['branch']}  →  base {c['base']}")
        print(f"    {c['ahead'] if c['ahead'] >= 0 else '?'} commits ahead · "
              f"{conflict_s} · build {build_status(c['path'])} · "
              f"{c['age']} old{(' · ' + ', '.join(flags)) if flags else ''}")
        if areas:
            print(f"   {areas}{multi}")
        print(f"    {c['path']}")
        print()

    print("Land: /common:worktree-merge <name> · "
          "Drop: /common:worktree-discard <name> · "
          "(finished+clean worktrees are auto-removed on next session start)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
