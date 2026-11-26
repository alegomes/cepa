---
description: Give the current (or a named) session worktree a meaningful name. Auto-isolated sessions get neutral names like session/0611-1430; rename one to session/<something-readable> once you know what it's about. Optional — naming is never required.
argument-hint: <new-slice>  [<old-slice>]   (omit old-slice to rename the worktree you're currently in)
interaction: routine
---

# /common:worktree-rename

## Purpose

Auto-isolated sessions are named neutrally (`session/0611-1430`) on purpose — a
name guessed at minute one lies the moment a session covers more than one thing.
But once *you* know what a session is about, you can label it. This renames a
session branch to something readable, so the reminder and merge read like intent.

Naming is always optional. The dashboard already shows commit count, areas
touched, and age — the facts that don't go stale — so an unnamed worktree is
never a problem, just less pretty.

## Variables

- `$ARGUMENTS` — `<new-slice>` and optionally `<old-slice>`:
  - one arg → rename the session worktree you're currently in to
    `session/<new-slice>`.
  - two args → rename `session/<old-slice>` to `session/<new-slice>`.

## Steps

1. **Resolve the target.** With one arg, confirm the current branch is a
   `session/*` branch (`git rev-parse --abbrev-ref HEAD`); if not, ask which
   worktree to rename. With two args, locate `session/<old-slice>`.

2. **Guard.** Refuse if `session/<new-slice>` already exists. Normalize
   `<new-slice>` to kebab-case.

3. **Rename the branch.** `git branch -m session/<old> session/<new>`
   (or `git branch -m session/<new>` when renaming the current branch).

4. **Keep the registry in sync.** Update the matching entry in
   `<main-root>/.claude/sessions/*.json`: set its `branch` to `session/<new>`.
   (Find the entry whose `worktree_path` matches this worktree.) The worktree
   *directory* name can stay as-is — git doesn't require dir and branch to
   match, and the dashboard shows both.

5. **Report.** Confirm the new name and remind that merge/discard now use it:
   `/common:worktree-merge <new-slice>`.

## Notes

- This only relabels; it moves no commits and changes no files.
- If you'd rather name at the moment of landing, skip this — `/common:worktree-merge`
  offers to name the merge commit then, which is the other natural moment.
