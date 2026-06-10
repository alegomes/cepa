#!/usr/bin/env python3
"""Merge-safety guard for /common:worktree-merge — single-owner branch rule.

Given a source branch to merge into the branch currently checked out at --cwd,
report whether EITHER side is held by another LIVE session:

  - source held live  → its history is unstable; the session may be rewriting it
    (rebase/amend) out from under you. A merge fixes a snapshot that goes stale
    the next minute.
  - destination held live → another session sits on the branch you'd be moving;
    merging into it shifts the ground under them mid-work.

Both are exactly the cross-session clobbers that motivated the worktree model.

Usage: worktree-guard.py <source-branch> [--cwd <dir>]
Prints a first line "BLOCK: <n>" or "OK", then human detail. Exit 0 always —
this is advisory; the command enforces the refusal so a human can override.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402


def describe(e: dict) -> str:
    host = e.get("hostname", "?")
    cwd = e.get("cwd", "?")
    age = L.age_str(e.get("last_seen") or e.get("started_at", ""))
    return f"{host}:{cwd} (active {age} ago)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--cwd", default=os.getcwd())
    args = ap.parse_args()

    cwd = os.path.abspath(args.cwd)
    root = L.main_root(cwd)
    if not root:
        print("OK")
        print("(not inside a git repository — nothing to guard)")
        return 0

    source = args.source.replace("refs/heads/", "")
    if not source.startswith("session/"):
        source = f"session/{source}"
    dest = L.current_branch(cwd)

    src_owners = L.branch_owners(root, source, exclude_cwd=cwd)
    dest_owners = L.branch_owners(root, dest, exclude_cwd=cwd) if dest else []

    blockers = len(src_owners) + len(dest_owners)
    if blockers == 0:
        print("OK")
        print(f"No other live session is on `{source}` or on `{dest}` — safe to merge.")
        return 0

    print(f"BLOCK: {blockers}")
    for e in src_owners:
        print(f"  source `{source}` is held by a LIVE session — {describe(e)}")
        print("    its history may be rewritten under you; ask it to land or close first.")
    for e in dest_owners:
        print(f"  destination `{dest}` is held by a LIVE session — {describe(e)}")
        print("    merging into it would move the ground under that session.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
