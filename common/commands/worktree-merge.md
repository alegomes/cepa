---
description: Fold a session worktree's branch back into your integration branch and prune the worktree. /common:worktree-merge <slice> verifies the branch is green, merges session/<slice> into the branch you're on, surfaces any conflict as a normal git conflict to resolve, optionally names the merge, and on success removes the worktree and deletes the branch. The landing half of the worktree lifecycle.
argument-hint: <slice>   (the slice name, e.g. billing-api or session/billing-api; omit to infer from the current branch)
---

# /common:worktree-merge

## Purpose

The landing step of the worktree lifecycle: take the work done in a session
worktree (branch `session/<slice>`) and merge it back into your integration
branch, then clean up the worktree and branch.

This is where the "occasional conflict" between parallel slices gets resolved —
**deliberately, by git**, instead of one window having silently overwritten the
other. If the slices stayed independent, the merge is clean; if they touched the
same lines, git stops and shows you the conflict to resolve by hand.

## Variables

- `$ARGUMENTS` — `<slice>` (optional): the slice name. If omitted and the
  current branch is itself `session/<slice>`, infer the slice from it and tell
  the user they must run the merge from the **integration** branch, not from
  inside the session worktree (you can't merge a branch into itself).

## Where to run this

Run it from your **integration branch** (e.g. `main`, or whatever you forked
from) in the **base** worktree — not from inside the session worktree. Git can
only merge a branch into the branch currently checked out in the current
worktree, so the current branch *is* the merge target. If the user is inside the
session worktree, tell them to switch to the integration session/worktree first.

## Steps

1. **Locate.** Run `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session-worktrees.py"`
   (or `git worktree list`). Resolve `<slice>` → branch `session/<slice>` and
   its worktree path. If the branch doesn't exist, stop and report what session
   branches *do* exist. Note the dashboard's conflict prediction for this
   branch — if it says "will CONFLICT," warn the user up front so the merge step
   is no surprise. Also note whether the dashboard marks it `LIVE` — step 3 will
   guard on that.

2. **Confirm a safe target.** Determine the current branch
   (`git rev-parse --abbrev-ref HEAD`). If it equals `session/<slice>`, stop:
   the user is on the source branch — instruct them to check out the integration
   branch (in the base worktree) and re-run. The current branch is the merge
   **destination**; name it back to the user so there's no ambiguity about where
   the work is landing.

3. **Guard against live owners (single-owner branch rule).** Run
   `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/worktree-guard.py" session/<slice>`
   from the integration worktree. If its first line is `BLOCK:`, **stop** and
   relay the detail: either the source branch is held by a live session (its
   history may be getting rewritten under you — a fixed merge goes stale the next
   minute) or the destination branch is, in which case landing would move the
   ground under that session. Tell the user to land or close that window first.
   Only proceed if the user explicitly overrides after seeing who's live. If the
   first line is `OK`, continue.

4. **Confirm both sides are committed.** The session worktree's work must be
   committed on `session/<slice>`. If `git -C "<worktree-path>" status
   --porcelain` shows uncommitted changes, stop and tell the user to commit (or
   discard) them in the session window first — a worktree merge only carries
   committed history. (If the session window already closed, the SessionEnd hook
   will have WIP-autosaved them onto the branch — check `git log`.)

5. **Green-gate the source.** Read `<worktree-path>/.claude/last-build.json`.
   Unless `<worktree-path>/.claude/no-build` exists, refuse to merge when the
   session branch's last build status is `STALE` or `FAILURE` — landing a broken
   branch onto your integration branch is exactly what green-or-revert exists to
   prevent. Tell the user to get the branch green in its own window first, then
   re-run. (If `last-build.json` is absent and there's no `no-build` marker, say
   so and ask the user to confirm they've verified the branch before proceeding.)

6. **Merge.** `git merge --no-ff session/<slice>` into the current branch.
   - **Clean merge** → optionally offer to name it: this is the honest moment to
     label the work, since you can now see everything it contains. If the branch
     has a neutral auto-name (`session/0611-1430`) or spans multiple areas, ask
     "name this merge for the history?" and use their answer as the merge commit
     subject (amend the merge commit message). Then proceed to step 7.
   - **Conflict** → STOP. Do not auto-resolve. Report the conflicted files
     (`git diff --name-only --diff-filter=U`) and tell the user to resolve them,
     `git add`, and `git commit` to complete the merge — then re-run
     `/common:worktree-merge <slice>` to do the cleanup (step 7). This is the
     expected, healthy outcome when two slices touched the same code.

7. **Prune.** Once the merge is committed:
   - `git worktree remove "<worktree-path>"` (use `--force` only if the user
     confirms there's nothing unsaved there).
   - `git branch -d session/<slice>` (use `-D` only with explicit user
     confirmation if git refuses because of unmerged commits — that refusal
     usually means something didn't actually land).
   - Report: branch merged into `<integration-branch>`, worktree removed, branch
     deleted. The slice is fully folded back in.

## Notes

- A clean merge here is the proof the slices were genuinely independent. A
  conflict is not a failure of the worktree approach — it's the approach working:
  the collision surfaced as something you resolve, not something you discover
  later as corrupted output.
- This command only writes via git; it never edits source files to resolve a
  conflict. Resolution is the user's call.
