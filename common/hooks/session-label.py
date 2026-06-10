#!/usr/bin/env python3
"""CLI behind /common:worktree-label — get/set/clear a session worktree's
free-text label (its purpose).

The label is stored as the branch's git description
(`branch.<name>.description`), so it is durable: it survives session end and git
removes it when the branch is deleted by merge/discard. The branch *name* is
never touched — this is a note, not a rename.

Usage:
  session-label.py [--cwd DIR] [--branch NAME] [--clear] [TEXT ...]

  no TEXT, no --clear  → print the target's label (or a dim subject guess)
  TEXT ...             → set the label to the joined text
  --clear              → remove the label

Target = --branch if given, else the session/* worktree at --cwd (default cwd).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402


def entry_for_branch(root: str, branch: str) -> dict:
    for _, e in L.read_entries(root):
        if e.get("branch") == branch:
            return e
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--branch", default="")
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("text", nargs="*")
    args = ap.parse_args()

    cwd = os.path.abspath(args.cwd)
    root = L.main_root(cwd)
    if not root:
        print("Not inside a git repository.")
        return 1

    branch = args.branch or L.current_branch(cwd)
    if not branch.startswith("session/"):
        print(
            f"`{branch or '(detached)'}` is not a session worktree. Labels apply "
            "to `session/*` branches. Pass --branch session/<name>, or run this "
            "from inside the worktree you mean."
        )
        return 1

    text = " ".join(args.text).strip()

    # ── set / clear ──
    if args.clear or text:
        if not L.set_branch_description(root, branch, "" if args.clear else text):
            print(f"Failed to update the label on {branch}.")
            return 1
        if args.clear:
            print(f"Cleared the label on {branch}.")
        else:
            print(f"{branch} is now “{text}”.")
        return 0

    # ── get ──
    label = L.branch_description(root, branch)
    if label:
        print(f"{branch} — “{label}”")
        return 0
    hint = L.subject_hint(entry_for_branch(root, branch))
    if hint:
        print(f"{branch} — no label yet (assunto≈ {hint}). "
              f"Set one: /common:worktree-label <purpose>")
    else:
        print(f"{branch} — no label yet. Set one: /common:worktree-label <purpose>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
