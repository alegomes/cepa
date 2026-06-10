---
description: Spin up an isolated git worktree so a parallel `claude` window works on its own slice of the repo without colliding with other windows. /common:worktree-start <slice> creates ~/ccw-worktrees/<repo>-<slice> (outside the repo, to dodge cloud-sync races) on branch session/<slice> and tells you where to open the new session. Merge it back with /common:worktree-merge.
argument-hint: <slice>   (a short kebab-case name for the slice of work, e.g. billing-api)
---

# /common:worktree-start

## Purpose

> **Most of the time you don't need this command.** Launch with `ccw` instead of
> `claude` and isolation is automatic — `ccw` starts a normal session in the
> current directory and only spins up a worktree when another live session is
> already here. `ccw -s <slice>` forces a named worktree in one step (create +
> launch). Reach for `/common:worktree-start` when you want to *prepare* a
> worktree from inside an existing session without launching into it yet.

Two `claude` windows open in the **same checked-out directory** share one copy
of the source and one `.claude/` state directory. They race: on the
green-or-revert gate (`.claude/last-build.json`), on the recap log, and — when
their edits touch the same files — on the source itself, silently
last-write-wins. The `session-registry` hook warns you when this happens, but
the actual fix is to stop sharing the working tree.

This command gives each parallel session its **own git worktree**: a second
checked-out directory, on its own branch, backed by the same `.git`. Sessions
working on different slices then physically cannot collide — separate files,
separate `.claude/` state, separate builds. And the *occasional* real overlap
(both slices touch one file) stops being a silent clobber and becomes a normal
git **merge conflict** at merge-back time — visible and resolvable.

`/common:worktree-merge` owns the other half of the loop: folding the slice's
branch back into your integration branch and pruning the worktree.

## Variables

- `$ARGUMENTS` — `<slice>`: a short kebab-case name for this slice of work
  (e.g. `billing-api`, `tenant-cache`). Used for both the branch name
  (`session/<slice>`) and the worktree directory (`<repo>-<slice>`).
- `CCW_WORKTREE_HOME` (env, optional) — parent directory for session worktrees.
  Defaults to `~/ccw-worktrees`. Set it to relocate where worktrees are created.
- `CCW_SEED` (env, optional) — space/colon-separated globs of gitignored files
  to copy into a fresh worktree. Overrides `.claude/worktree-seed`; both fall
  back to `.env`, `.env.local`.

## Steps

1. **Validate.** Confirm we're inside a git repository:
   `git rev-parse --show-toplevel`. If not, stop and tell the user this command
   only works inside a git repo. Capture the repo root and its directory name
   (`<repo>`). Require a non-empty `<slice>` argument; if missing, ask for one.
   Normalize `<slice>` to kebab-case.

2. **Derive names.**
   - Branch: `session/<slice>`.
   - Worktree home: `$CCW_WORKTREE_HOME` if set, else `~/ccw-worktrees`. Worktrees
     live **outside the repo tree on purpose** — a repo under a cloud-sync folder
     (Insync/Dropbox/iCloud) would otherwise have its sibling worktrees synced
     too, and the sync daemon's own move/replace/conflict-copy races delete live
     worktrees mid-step. Create the home dir if missing (`mkdir -p`).
   - Worktree path: `<worktree-home>/<repo>-<slice>`.
   - The fork point is **the current HEAD** (whatever branch/commit this session
     is on). Note it so the user knows what they're branching from; mention it.

3. **Guard against collisions.**
   - If branch `session/<slice>` already exists (`git rev-parse --verify
     --quiet refs/heads/session/<slice>`), stop and report it — the user either
     wants a different slice name or wants to resume the existing worktree (point
     them at `git worktree list`).
   - If the target directory already exists, stop and report it; don't overwrite.

4. **Create the worktree.**
   `git worktree add "<worktree-home>/<repo>-<slice>" -b session/<slice>`
   (A dirty working tree in *this* session is fine — `git worktree add` only
   carries committed history, so uncommitted changes here stay here.)
   If the command fails, surface stderr verbatim and stop.

5. **Seed gitignored essentials.** A fresh worktree carries only tracked
   content, so files like `.env` are missing. Copy them in:
   `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/seed-worktree.py" "<worktree-home>/<repo>-<slice>"`
   (Configurable via `$CCW_SEED` or a `.claude/worktree-seed` file; defaults to
   `.env`, `.env.local`. Best-effort — never blocks worktree creation.) Mention
   any files it seeded.

6. **Hand off.** Report success and tell the user exactly how to start the
   parallel session — this command does **not** move the current session into
   the worktree:

   > Worktree ready: `<absolute path>` on branch `session/<slice>` (forked from
   > `<fork-point>`). Open a new terminal and run:
   >
   > ```
   > cd "<absolute path>" && claude
   > ```
   >
   > Work the `<slice>` slice there. When it's done, from your integration
   > branch run `/common:worktree-merge <slice>` to fold it back and prune the
   > worktree.

## Notes

- This is the architectural complement to the `session-registry` warning: the
  hook tells you *that* you're overlapping; this command is *how* you stop.
- Keep slices genuinely independent. The whole benefit is that different slices
  don't touch the same files — when they do, you'll resolve it as a merge
  conflict at `/common:worktree-merge`, which is the safe outcome but still
  costs you a resolution.
- Leads must never run worktree-*isolated* via the Task tool (the
  `lead-no-worktree` hook enforces that) — this command is about a separate
  top-level `claude` session in a separate directory, which is unrelated and
  fine.
