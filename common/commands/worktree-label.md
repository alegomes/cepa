---
description: Get or set a session worktree's free-text label — a short note of what it's *for*, so a timestamp branch like session/0609-2030 stops being a mystery. Set it once you know the purpose; read it any time. Stored as the branch's git description (durable, survives the session, never renames the branch).
argument-hint: [<purpose…>]   (no args = show the current worktree's label; --clear to remove)
interaction: routine
---

# /common:worktree-label

## Purpose

Auto-isolated sessions get neutral timestamp names (`session/0609-2030`) — stable
for git, useless for memory. This attaches a free-text **note of purpose** to a
session worktree, surfaced in the SessionStart reminder and `/common:worktree-list`
so you always know what each parallel window is *for*.

Unlike `/common:worktree-name`, this does **not** rename the branch — the note is
a full phrase, lives in the branch's git description, survives session end, and is
removed automatically when the branch is merged or discarded. Read it any time;
set it whenever you know the purpose (the wrap-up nudge will also offer).

## Variables

- `$ARGUMENTS`:
  - **empty** → print the current worktree's label (or a dim subject guess if
    none yet).
  - **text** → set the label of the current worktree to that text.
  - **`--clear`** → remove the label.
  - To target another worktree instead of the current one, the helper takes
    `--branch session/<name>`.

## Steps

1. Run the helper, passing `$ARGUMENTS` through, and show its output verbatim:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session-label.py" $ARGUMENTS
   ```

   - With no arguments it reads; with text it sets; with `--clear` it removes.
   - If you're not inside a `session/*` worktree and no `--branch` was given, the
     helper says so — pass `--branch session/<name>` to target a specific one.

2. On a set, confirm the new label and remind that it now shows in
   `/common:worktree-list` and the next SessionStart reminder.

## Notes

- The label is a note, not a rename — `git branch` and the shell prompt still show
  the timestamp branch. Consult the label via this command (no args) or
  `/common:worktree-list`. That's the trade-off you chose for a free-text phrase
  over a kebab branch rename.
- A `“quoted”` caption in the dashboard is a label you set; `(assunto≈ …)` is a
  weak auto-guess from the session's vocabulary, shown only until you label it.
