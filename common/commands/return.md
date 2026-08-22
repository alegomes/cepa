---
description: Close a fork opened by /common:branch. In the side session it captures the conclusion of the side discussion into a resolution; back in the origin session it ingests only that resolution and pops the fork off the LIFO stack — so the origin thread comes back with the answer, not the whole detour. No-arg form operates on the top of the stack; pass a fork-id to target a specific frame.
argument-hint: [<fork-id>]   (no id = top of the stack; mode is inferred from whether THIS session resumed the fork)
interaction: routine
---

# /common:return

## Purpose

The other half of `/common:branch`. A fork has two closing moves and this
command owns both, choosing between them by reading the room:

- **save** — run in the **side** session once the topic is settled:
  distill the side discussion into `resolution.md` and mark the frame
  `resolved`.
- **ingest** — run in the **origin** session: read that resolution, fold a
  concise summary into the main thread, and pop the frame off the stack so
  you're back exactly where you forked — carrying the conclusion, not the
  transcript.

## Variables

- `$ARGUMENTS` — optional `<fork-id>`. Default: the **top of the stack** =
  the top-most frame in `.claude/forks/stack.yaml` whose status is not
  `closed`. Closed frames stay in the file as an audit record but are
  skipped when resolving "the top".

## Mode selection (do this first, no fragile heuristics)

You decide save-vs-ingest by reading your own conversation, not by guessing
from global state:

1. **Did THIS session resume the fork?** I.e. earlier in *this* conversation
   did you run `/common:branch resume` (or otherwise load
   `.claude/forks/<id>/context.md`) and hold the side discussion?
   → **save mode.**
2. Otherwise — this is the origin session that created the fork, you did not
   hold the side discussion here, and the frame's status is `resolved`
   (its `resolution.md` exists). → **ingest mode.**
3. **Ambiguous / conflicting signals** (e.g. status is `resolved` but you
   also discussed it here, or status is `active` but you're clearly in
   origin): do not act on a guess. State what you see and ask the user which
   mode they want. This is the one place a wrong call corrupts the loop.

## Instructions

You are the orchestrator. Apply `active-listener` before either mode.

### save mode  (side session — finalize the fork)

1. Resolve the target frame (arg id, else top of stack). Confirm its status
   is `active`; if not, surface the mismatch before proceeding.
2. Synthesize the side discussion into `.claude/forks/<id>/resolution.md`.
   This is the *only* thing that flows back to the origin — make it carry
   the discussion, not reproduce it:
   - **Answer** — the conclusion to the fork's question, stated plainly up
     front.
   - **Why** — the reasoning that settled it, in a few bullets. Name any
     disagreement that was resolved (apply `name-the-disagreement`).
   - **Changes made** — any files touched / commits / artifacts produced in
     the side session, as file:line or paths. Be honest about what was only
     proposed vs. actually done (apply `evidence-over-assumption`).
   - **Carry-back** — what the origin thread should now do differently, tied
     to that fork's `RESUME POINT` from context.md.
   - **Loose ends** — anything deferred, so it doesn't silently vanish.
3. Set the frame's status to `resolved` in `stack.yaml`.
4. Tell the user (apply `conversational-response`): the fork is resolved;
   return to the **origin** session and run `/common:return` there to pull
   the conclusion in.

### ingest mode  (origin session — come back to the fork point)

1. Resolve the target frame (arg id, else top of stack). Require its status
   to be `resolved`; if it's still `open`/`active`, the side session hasn't
   finished — tell the user to run `/common:return` there first, and stop.
2. Read `.claude/forks/<id>/resolution.md`.
3. Fold it back into the main thread as a **concise** briefing — the Answer
   and the Carry-back are what matter; do not paste the whole resolution.
   Re-anchor on the fork's `RESUME POINT` so the thread continues from where
   it forked, now informed by the conclusion.
4. Set the frame's status to `closed` **in place** — keep its entry in
   `stack:` (and its `<fork-id>/` directory on disk) as an audit record.
   Do **not** delete the row: a persisted `closed` status is what makes
   re-ingest idempotent and keeps the lifecycle (`open → active → resolved
   → closed`) honest. Because "the top of the stack" is defined as the
   top-most non-`closed` frame, marking this one `closed` automatically
   makes the previous frame the new top — that's how the LIFO pops.
5. Continue the origin work from the resume point. If nested frames remain
   open, note that they're still pending.

## Notes

- **LIFO.** No-arg `/common:return` always targets the top of the stack
  (top-most non-`closed` frame), so nested forks unwind innermost-first.
  Pass an explicit `<fork-id>` only to close one out of order.
- **Idempotence.** If the target frame is already `closed`, no-op with a
  note — do not double-inject. (This is why ingest marks `closed` in place
  instead of deleting the row: the status is the idempotence guard.)
- **Nothing is destroyed.** Closed frames keep their `stack:` entry (status
  `closed`) plus their `context.md` / `resolution.md` under
  `.claude/forks/<id>/` as an audit trail. Prune entries/directories
  manually if the file gets noisy.
- If `resolution.md` is missing but status says `resolved`, treat it as a
  corrupted frame: report it, don't fabricate a conclusion.
