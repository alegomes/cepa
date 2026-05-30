---
description: Fork the current discussion into its own isolated context to handle a side topic, then return cleanly to where you forked. /branch <assunto> snapshots the main thread into a checkpoint and opens a fork frame; /branch resume <id> picks that fork up in a fresh session so the side discussion never bloats the origin thread. Pairs with /common:return. Supports nested forks via a LIFO stack.
argument-hint: <assunto>  |  resume [<fork-id>]   (no id on resume = top-most not-yet-resolved frame on the stack)
---

# /common:branch

## Purpose

There are recurring moments in a development flow where you want to peel
off into a focused side discussion — chase a tangent, settle one design
question, debug one thing — without that detour polluting the context of
the thread you were in. And when the tangent is settled, you want to come
back to exactly where you forked, with only the *conclusion* brought back,
not the whole side transcript.

A single Claude Code session is one linear, ever-growing context window —
there is no native "push a frame, work in it, pop back." So `/branch`
implements the fork the only way that actually keeps the origin thread
lean: the side discussion happens in a **separate session**, and a distilled
resolution is what flows back. This command owns the two write-points of
that loop:

- `/branch <assunto>` — in the **origin** session: snapshot where you are
  and open a fork frame.
- `/branch resume [<id>]` — in a **fresh** session: load that snapshot so
  the side discussion starts with the context it needs.

`/common:return` owns the two read/finalize points (capture the resolution
in the side session; ingest it back in the origin). See that command for
the other half.

## Variables

- `$ARGUMENTS` — one of:
  - `<assunto>` — free-text topic for the fork (e.g. `branch should we cache the tenant lookup`). Anything that is not the literal word `resume` is treated as the topic → **create** mode.
  - `resume [<fork-id>]` — pick up an existing fork in this session → **resume** mode. With no id, resumes the **top of the stack** = the top-most frame whose status is `open` or `active` (i.e. not yet `resolved`/`closed`). Including `active` means a side session abandoned mid-discussion can still be picked back up without remembering its id.

## State layout

All fork state lives under `.claude/forks/` in the current project (the
same transient-state home as `.claude/session-log.md` and
`.claude/last-build.json` — never committed, never in `docs/`):

```
.claude/forks/
  stack.yaml                 # LIFO list of fork frames + their status
  <fork-id>/
    context.md               # written by create mode — origin-thread snapshot + the question
    resolution.md            # written by /common:return in the side session
```

`fork-id` format: `YYYY-MM-DD-HHMM-<slug>` where `<slug>` is the topic
kebab-cased and truncated to ~6 words. Get the timestamp from
`date +%Y-%m-%d-%H%M` via Bash — do not guess it.

`stack.yaml` schema:

```yaml
schema_version: 1
stack:                        # ordered, last = top
  - id: 2026-05-29-1430-cache-tenant-lookup
    topic: should we cache the tenant lookup
    status: open              # open -> active -> resolved -> closed
    created_at: 2026-05-29T14:30:11-03:00
```

Status meanings: `open` = created in origin, side session not started yet;
`active` = resumed in a side session, discussion in progress; `resolved` =
side session wrote a resolution (set by `/common:return`); `closed` =
resolution ingested back into origin (set by `/common:return`).

**Stack semantics.** Frames are never deleted — `/common:return` advances a
frame to `closed` *in place* and leaves the row as an audit record. So "the
top of the stack" is not literally the last row; it's the **top-most frame
that is not `closed`**. Create mode pushes a new row (the new top); return
ingest marks the current top `closed` (the previous frame becomes the new
top). That single rule drives the whole LIFO unwind.

## Instructions

You are the orchestrator. Read the room first (apply `active-listener`):
the snapshot you write is only as good as your grasp of what the origin
thread was actually doing.

### Mode = create  (`/branch <assunto>`, run in the ORIGIN session)

1. Generate `fork-id` from the timestamp + topic slug.
2. Write `.claude/forks/<fork-id>/context.md` — a tight, self-sufficient
   snapshot a fresh session can boot from with zero access to this
   conversation. Include:
   - **Topic** — the `<assunto>`, verbatim, as the question to resolve.
   - **Why this fork** — the trigger: what in the origin thread raised it.
   - **Origin state** — what the main thread was doing, in 2-4 bullets.
   - **Relevant anchors** — file:line refs, function/symbol names, command
     outputs, decisions already made that the side topic depends on.
   - **Constraints** — anything the side discussion must respect (don't
     touch X, must stay compatible with Y).
   - **RESUME POINT** — one sentence: what the origin thread was about to
     do next, so `/common:return` can stitch back cleanly.
   - **Done-when** — what a good resolution looks like (the bar to clear
     before running `/common:return` in the side session).
3. Append the frame to `.claude/forks/stack.yaml` with `status: open`
   (create the file with the schema above if absent).
4. Report back to the user (apply `conversational-response`):
   - Confirm the fork id.
   - Give the exact next step: *open a new session and run*
     `/common:branch resume <fork-id>`.
   - Remind them: when the side topic is settled, run `/common:return` in
     that session to capture the conclusion, then come back here and run
     `/common:return` to pull it in.
   - **Do not start discussing the side topic here.** The whole point is
     to keep this thread untouched. Stop after the snapshot.

### Mode = resume  (`/branch resume [<id>]`, run in a FRESH session)

1. Resolve the target fork: explicit `<id>`, else the top-of-stack frame
   (top-most with status `open` or `active`). If the stack is empty or every
   frame is `resolved`/`closed`, say so and stop (don't invent one).
2. Read `.claude/forks/<id>/context.md` in full. Brief yourself out loud
   in 2-3 lines: the topic, the constraints, the bar to clear.
3. Set that frame's status to `active` in `stack.yaml`.
4. Begin the side discussion *interactively* with the user, grounded in the
   snapshot. This session is yours to spend freely — it will not touch the
   origin thread. When the topic is settled, the user runs `/common:return`
   here to write the resolution.

## Notes

- **Nesting works.** Running `/branch <assunto>` inside a side session just
  pushes another frame. `/common:return` always pops the top, so forks
  unwind in LIFO order — innermost first.
- **This command never deletes state.** `/common:return` is what advances
  status and (optionally) prunes closed frames.
- If the user runs create mode but clearly *wants* the tangent handled
  inline right now (small, no isolation needed), say so and suggest just
  answering it directly or delegating to a subagent — don't force the
  two-session ceremony on a 30-second question.
