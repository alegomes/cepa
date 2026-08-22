---
description: Show all session worktrees and their state — commits ahead, clean/dirty, live/idle, age, areas touched, conflict prediction against base, and build status. Read-only dashboard so you never lose track of parallel work or a pending merge.
argument-hint: (no arguments)
interaction: routine
---

# /common:worktree-list

## Purpose

A read-only dashboard of every `session/*` worktree in this repo, so unmerged
work can never be silently forgotten. For each one it shows commits ahead of
base, dirty/clean, live/idle, age, the dirs it touched (with a multi-area
flag), whether it will merge cleanly or **conflict** (predicted via
`git merge-tree`, without touching your tree), and its last build status.

## Steps

1. Run the dashboard helper and show its output verbatim:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session-worktrees.py"
   ```

2. If the user asks about a specific worktree, read its details from the same
   output; don't re-derive by hand.

3. Close with the relevant next step: `/common:worktree-merge <name>` to land
   one, `/common:worktree-discard <name>` to drop a dead end. Note that
   finished+clean worktrees are auto-removed on the next session start, so the
   list only ever shows things that still need a decision.

## Notes

- Purely informational — it changes nothing.
- "will CONFLICT" is a prediction, not a failure: it means that worktree
  touched the same lines as its base, so its merge will need hand-resolution.
  Better to know before you start than to discover it mid-merge.
