---
description: End-of-session one-shot — chain the whole shutdown ritual behind a single confirmation. /common:wrap-up commits the session worktree, writes the handoff, then lands the branch (merge into its integration branch + push + prune) — or, with --discard, throws a dead-end worktree away. Replaces typing "commit it / merge it / push / handoff" by hand. Reuses worktree-merge's guards (green-gate, single-owner, conflict-stop) so nothing unsafe slips through.
argument-hint: [--discard] [commit message]   (no args = land the current session worktree)
interaction: routine
---

# /common:wrap-up

## Purpose

The shutdown ritual in one word. A session in a `cepa` worktree normally ends
with the same five steps typed by hand — *commit it, merge it, push, handoff,
exit*. This chains them behind a **single confirmation**, reusing the existing
commands' logic so every safety check still fires:

- **green-gate** — won't land a `STALE`/`FAILURE`/`EMPTY` branch (unless `.claude/no-build`).
- **single-owner guard** — won't merge a branch a *live* session is sitting on.
- **conflict-stop** — a merge conflict halts the chain for you to resolve by hand.

It does **not** silently barrel through danger. The single confirmation is an
*approval* of the plan; the guards are *safety stops* that can still halt mid-chain.

Two terminal paths, auto-detected:

- **Land** (default) — commit → handoff → merge into integration → push integration → prune.
- **Discard** (`--discard`, or when there's nothing to land) — commit-or-skip →
  optional handoff → drop the worktree + branch, after showing what's lost.

## Variables

- `$ARGUMENTS`:
  - `--discard` (optional first token) — force the discard path instead of land.
  - the remainder (optional) — a commit message. If omitted, generate one from
    the diff (a tight, conventional subject line).

## The cross-worktree fact that shapes every step

`wrap-up` runs from **inside** the session worktree (`session/<slice>`). Two
git constraints follow, and the whole command is built around them:

1. **You can't merge a branch into itself.** The merge must run in the worktree
   that has the *integration* branch checked out — reached with `git -C <base-worktree>`.
2. **You must NOT remove the worktree you're standing in.** `git worktree remove`
   would delete the directory this very session is running in. The session still
   has one more turn left (this command's final report), and when that turn ends
   its **Stop hook fires from the now-deleted cwd** — Claude Code can't even
   `posix_spawn '/bin/sh'` to launch the hook, so you get a
   `Stop hook error: … ENOENT … /bin/sh`. So the prune is **deferred**: wrap-up
   drops a marker and the `session-registry` SessionEnd hook reaps the worktree
   *after* your last turn (see L7). No live cwd is ever deleted.

## Steps

### 0. Read the situation (no writes yet)

- `root` = main worktree root: parent of `git rev-parse --git-common-dir` with
  trailing `/.git` removed (in a linked worktree). This is where the registry
  and handoff files live.
- Current branch: `git rev-parse --abbrev-ref HEAD`.
- **If the current branch is not `session/*`** → there's no worktree lifecycle to
  run. Degrade gracefully: this becomes a plain *commit + handoff (+ push if a
  remote exists)*. Skip the merge/prune steps, tell the user that's what you're
  doing, and otherwise follow the same confirm-once shape.
- Find this worktree's registry entry and its **integration branch**: read
  `<root>/.claude/sessions/*.json` for the entry whose `cwd`/`worktree_path`
  matches the current worktree, and take `base_branch` (+ `base_commit`). If no
  entry records it, fall back to `default_base` (origin/HEAD → main → master) and
  **say so** — don't silently assume `main`. **Note that entry's filename stem —
  it is this session's `<session_id>`, needed for the deferred-prune marker (L7
  / discard step 3).**
- Compute: dirty? (`git status --porcelain`), commits ahead of base
  (`git rev-list --count <base>..HEAD`), and the session slice
  (`session/<slice>` → `<slice>`).
- From `git status --porcelain`, split the working-tree changes into **what
  you'll commit** (tracked changes + genuine new work) versus **runtime noise to
  leave alone** (untracked `.claude/` session state, build output, caches). You
  show the first list in the plan and stage exactly it in L2 — see L2 for the
  rule. If anything is ambiguous, mark it for the user to decide at confirmation.
- **Decide the path.** Default **land**. Switch to **discard** if `--discard`
  was passed, OR if there are 0 commits ahead of base AND nothing worth
  committing (an empty branch — landing it would be a no-op merge). If you flip
  to discard on your own, say why.

### 1. Show the plan — then confirm ONCE

Print a compact, scannable plan of exactly what will run, so one "yes" covers
the whole chain. Land example:

```
wrap-up plan — landing session/<slice> → <base>
  1. commit <N> file(s)           <path-a>, <path-b>, …   msg: "<subject>"
                                  (skipping runtime noise: .claude/sessions/, …)
  2. handoff                      → .claude/handoffs/<slug>.md
  3. merge --no-ff into <base>    (in base worktree <path>)   [green: OK | no-build]
  4. push <base>                  → origin   (or: local-only, skip)
  5. prune                        remove worktree + delete session/<slice>
Proceed? (this merges, pushes, and deletes the branch)
```

Discard example:

```
wrap-up plan — DISCARDING session/<slice>
  will permanently delete: <N> unmerged commit(s) + these untracked files: …
  (handoff: <write / skip>)
Proceed? This throws the work away.
```

**Wait for an explicit yes.** Anything short of a clear yes → stop, change
nothing. If the user wants a different message or path, take the correction and
re-show the plan.

---

## Land path (on confirmation)

### L2. Commit

- **Stage deliberately — never blind `git add -A`.** A blanket add sweeps in
  session/runtime state that lives nowhere in git on purpose: `.claude/session-log.md`,
  `.claude/sessions/`, `.claude/handoffs/`, `.claude/last-build.json`, and the
  like. In a repo that gitignores `.claude/` this is moot; in one that doesn't
  (the plugin repo itself, for instance) `-A` would commit that noise onto the
  branch you're about to land.
- Do it in two moves, in the session worktree:
  1. `git add -u` — stages modifications/deletions to **already-tracked** files
     only. This can never pull in untracked runtime state.
  2. For untracked files (the `??` lines of `git status --porcelain`), add only
     **genuine new work** explicitly by path (a new source file, a new doc).
     **Skip** generated/runtime files — anything under `.claude/` that isn't a
     deliberately-tracked marker (e.g. `.claude/no-build`), build output, caches.
     If an untracked file's nature is ambiguous (work vs noise), **surface it and
     ask** rather than guess — don't silently commit OR silently drop it.
- The plan (step 1) already listed the exact paths to be committed, so the single
  confirmation covers this staging — what gets committed should match that list.
- If the tree was already clean (nothing to commit), say so and continue — the
  branch may already carry committed work to land.

### L3. Handoff

- Run the `/common:handoff` workflow: write only the `HANDOFF:NOTE` zone of
  `<root>/.claude/handoffs/<branch-slug>.md`, preserving the `HANDOFF:AUTO` zone
  byte-for-byte. On a landed branch this is archival (the branch is about to be
  deleted, so it won't auto-resume) — write it anyway for the record; keep it
  tight. Don't block landing on it.

### L4. Locate the base worktree + run the guards

- Find the worktree that currently has `<base>` checked out
  (`git worktree list --porcelain`). Call it `<base-worktree>`.
  - If `<base>` is checked out **nowhere** → it's not landable without a
    checkout. Stop and tell the user to open/`git checkout <base>` in the base
    window, then re-run. Don't force a checkout under a window you can't see.
  - If `<base-worktree>` is dirty, check **whether the dirt intersects the
    merge.** Compute the merge's changed-file set
    (`git -C <base-worktree> diff --name-only <base>...session/<slice>`) and the
    base worktree's dirty paths (`git -C <base-worktree> status --porcelain`).
    Only **stop** if the two sets intersect (the merge would touch a file with
    uncommitted edits — a real clobber risk) or if an untracked file in the base
    collides with one the merge adds. Don't block on unrelated dirt: a base
    worktree on `main` is almost always "dirty" with hook-written runtime state
    (`.claude/sessions/`, `expertise/*.yaml`, `session-log.md`) that no merge
    touches — blocking on that makes auto-merge impossible. When you proceed past
    non-intersecting dirt, say so in one line.
- **single-owner guard:**
  `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/worktree-guard.py" session/<slice> --cwd <base-worktree> --exclude-cwd <session-worktree>`
  — `--cwd` MUST be the base worktree (or `dest` resolves to the session branch
  itself), and `--exclude-cwd` MUST be the session worktree you're calling from
  (or the guard counts THIS session as a live owner of the source branch and
  self-blocks every time). First line `BLOCK:` → stop, relay the detail (some
  *other* live session holds the source or destination); proceed only on an
  explicit override.
- **green-gate:** read `<session-worktree>/.claude/last-build.json`. Unless
  `<session-worktree>/.claude/no-build` exists, refuse on anything other than
  `SUCCESS` (`STALE`/`FAILURE`/`EMPTY` — EMPTY is a filtered run that executed zero tests) —
  same rule as `/common:worktree-merge`. (Absent + no marker → ask the user to
  confirm they verified the branch.)

### L5. Merge

- `git -C <base-worktree> merge --no-ff session/<slice>`.
- **Conflict** → STOP the chain. Report the conflicted files
  (`git -C <base-worktree> diff --name-only --diff-filter=U`) and tell the user
  to resolve + `git add` + `git commit` in the base window, then finish with
  `/common:worktree-merge <slice>` for the prune. Do **not** auto-resolve, and do
  **not** prune. (Handoff already written, so nothing is lost.)
- Clean merge → continue.

### L6. Push the integration branch (only if it has a remote)

- If `<base>` has an upstream / origin exists
  (`git -C <base-worktree> rev-parse --abbrev-ref --symbolic-full-name @{u}`
  succeeds, or `git -C <base-worktree> remote` is non-empty): `git -C <base-worktree> push`.
- Otherwise (local-only repo) skip silently and note "local-only, not pushed".
- **Surface the push size BEFORE the confirmation, not after.** Count
  `git -C <base-worktree> rev-list --count @{u}..<base>` and show it in the plan
  (step 1). If the branch is ahead of its upstream by **substantially more than
  this session's own commits** (other accumulated local work that would ride
  along), call that out explicitly — "push will publish N commits, M of them
  from earlier work" — so the user isn't surprised to publish history they
  forgot was unpushed. A plain `git push` can't push only this merge.
- Push the **integration branch only** — never the session branch; it's about to
  be deleted.

### L7. Defer the prune to SessionEnd (do NOT remove your own cwd)

Removing the current session worktree from here would delete the directory this
session is running in, and the next Stop hook would fail to launch (see "The
cross-worktree fact" above). So **don't** run `worktree remove` now. Instead drop
a one-shot marker the SessionEnd hook consumes after your final turn:

- Write `<root>/.claude/sessions/<session_id>.prune-on-exit` (the `<session_id>`
  noted in step 0), containing:
  ```json
  {
    "base_worktree": "<base-worktree-path>",
    "base_branch": "<base>",
    "branch": "session/<slice>",
    "session_worktree": "<this-worktree-path>",
    "discard": false
  }
  ```
  (`<this-worktree-path>` = `git rev-parse --show-toplevel`.)
- On `exit`, `session-registry`'s SessionEnd handler verifies the branch is
  merged into `<base>`, then runs `git -C <base-worktree> worktree remove` +
  `git branch -d session/<slice>` — after your last turn, so no hook fires from a
  dead cwd. (Backstop: if the session crashes before SessionEnd, `auto_clean` on
  the next session start reaps the now-merged, clean, not-alive worktree anyway.)

### L8. Report

One block: landed `session/<slice>` → `<base>`; pushed (or local-only); handoff
at `<path>`; **the worktree + branch will be removed automatically when you
`exit`** (or run `/common:worktree-discard <slice>` from the base window to drop
it now). Close with: **"Safe to `exit`."** (A slash command can't close the
session for you — that last keystroke is yours, but everything is already landed,
so it's a no-op safety-wise.)

---

## Discard path (on confirmation)

Mirror `/common:worktree-discard`:

1. Show what would be lost — unmerged commits (`git log --oneline <base>..HEAD`)
   and uncommitted changes, calling out genuinely-new untracked files (`??`)
   explicitly (seeded `.env`-style files copied at creation are safe to lose).
   This was already in the plan; the confirmation covers it.
2. Optional handoff (default skip for a dead end; write it if the user asked or
   if there's a lesson worth keeping). 
3. **Defer the removal the same way the land path does** — never delete your own
   cwd (see "The cross-worktree fact"). Write
   `<root>/.claude/sessions/<session_id>.prune-on-exit` with `"discard": true`:
   ```json
   {
     "base_worktree": "<base-worktree-path>",
     "branch": "session/<slice>",
     "session_worktree": "<this-worktree-path>",
     "discard": true
   }
   ```
   On `exit`, the SessionEnd hook force-removes the worktree and `-D`s the branch
   (no merge check — the user chose to throw it away). Locating `<base-worktree>`
   needs the same `git worktree list` lookup the land path uses in L4.
4. Report what *will* be removed on `exit`. Close with **"Safe to `exit`."**

## Constraints

- **One approval, real stops.** Confirm the plan once; then the only things that
  halt the chain are the safety guards (green/owner/conflict) — surface them, never
  paper over them.
- **Never auto-resolve a merge conflict.** Resolution is the user's call.
- **Push the integration branch only**, and only when a remote exists.
- This command writes via git + the handoff file. It never edits source to make a
  merge land.

## See also

- `/common:worktree-merge` — the land half on its own (run from the base window).
- `/common:worktree-discard` — the drop half on its own.
- `/common:handoff` — the narrative-only handoff.
