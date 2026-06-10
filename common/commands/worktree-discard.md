---
description: Discard a session worktree that was a dead end — remove the worktree and delete its branch, after showing you exactly what work would be lost. The "throw it away" half of the lifecycle, opposite /common:worktree-merge.
argument-hint: <name>   (the session slice name, e.g. billing-api — with or without the session/ prefix)
---

# /common:worktree-discard

## Purpose

Not every slice is worth landing. When a session worktree was a dead end,
this removes it cleanly — worktree directory plus branch — so it stops showing
up in the unmerged reminder. It completes the lifecycle: a worktree ends in
either `/common:worktree-merge` (keep) or `/common:worktree-discard` (drop).

This deletes work. It refuses to do so silently — it shows you what's there
and requires confirmation first.

## Variables

- `$ARGUMENTS` — `<name>`: the slice name (`billing-api` or `session/billing-api`).

## Steps

1. **Resolve.** Normalize `<name>` to branch `session/<name>` and find its
   worktree via `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session-worktrees.py"`
   (or `git worktree list`). If it doesn't exist, stop and list what does.

2. **Show what would be lost — then confirm.** Report the branch's unmerged
   commits (`git log --oneline <base>..session/<name>`) and any uncommitted
   changes (`git -C <worktree> status --porcelain`). Call out **untracked files
   explicitly** (the `??` lines) — these live nowhere else and are gone for good.
   Seeded files (`.env` and the like, copied from the main tree at creation) are
   expected and safe to lose; genuinely new untracked work is not — flag it.
   Tell the user plainly: *"This will permanently delete N commits and these
   untracked files: … in `session/<name>`. Confirm?"* **Wait for explicit
   confirmation.** Do not proceed on anything short of a clear yes.

3. **Refuse if a live session is using it.** If the worktree has a live session
   (per the registry), stop — tell the user to close that window first.

4. **Discard.** On confirmation:
   - `git worktree remove --force <worktree-path>`
   - `git branch -D session/<name>`
   - Report what was removed.

## Notes

- For a worktree with valuable work, use `/common:worktree-merge` instead — this
  command is specifically for throwing work away.
- If you only want to remove a *finished* worktree (already merged, clean),
  you don't need this — those are auto-removed on the next session start.
