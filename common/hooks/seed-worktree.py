#!/usr/bin/env python3
"""Seed a freshly created session worktree with gitignored essentials.

A fresh worktree carries only tracked content, so gitignored files the main
tree relies on (.env and friends) are missing — you'd recreate them by hand and
lose them again on discard. This copies them in. Which files: $CEPA_SEED, else a
`.claude/worktree-seed` file, else the built-in default (.env, .env.local) —
plus, always, the `seed:` list of `.claude/env.yaml` when the project has an
environment manifest (docs/env-manifest.md).

Usage:  seed-worktree.py <worktree-path> [<main-root>]
Prints one "seeded <relpath>" line per file copied. Never fails the caller.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wtlib as L  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: seed-worktree.py <worktree-path> [<main-root>]", file=sys.stderr)
        return 0
    wt = os.path.abspath(sys.argv[1])
    main_root = sys.argv[2] if len(sys.argv) > 2 else (L.main_root(wt) or L.repo_root(wt))
    if not main_root or L.same_path(main_root, wt):
        return 0  # nothing to seed from, or pointed at the main tree itself
    for rel in L.seed_worktree(main_root, wt):
        print(f"seeded {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
