# context-forking

Fork a discussion into its own isolated context to handle a side topic,
then return to exactly where you forked — carrying back only the
conclusion, not the whole detour. Implemented by two `common` commands,
`/branch` and `/return`, plus a small state file under `.claude/forks/`.

## Why this exists

There are recurring moments in a development flow where you want to peel
off into a focused side discussion — chase a tangent, settle one design
question, debug one thing — without that detour polluting the thread you
were in. And when it's settled, you want to come back to where you
forked, with only the *conclusion* brought back.

The obstacle is structural: a single Claude Code session is **one linear,
ever-growing context window**. There is no native "push a frame, work in
it, pop back to where I was." Once the side-topic tokens enter the
window, they stay until compaction — so a fork done *inline* doesn't
actually keep the origin thread lean; it just buries it under the
tangent.

The only mechanism that genuinely isolates the side discussion is to run
it in a **separate session** and bring back a distilled resolution. That
is exactly what these two commands orchestrate.

## The shape of a fork

```
ORIGIN session                         SIDE session (fresh)
──────────────                         ────────────────────
/branch <assunto>
  └─ snapshot origin → context.md
     push frame (status: open)
                          ────────►   /branch resume [<id>]
                                        └─ read context.md
                                           (status: active)
                                           …interactive discussion…
                                        /return
                                          └─ distill → resolution.md
                                             (status: resolved)
/return            ◄────────────────
  └─ read resolution.md (only this
     flows back), fold concise
     briefing into origin thread
     (status: closed — frame stays
      as audit record)
```

The origin thread grows only by the final resolution, never by the side
transcript. That is the whole point.

## The state file: `.claude/forks/`

Fork state lives under `.claude/forks/` in the current project — the same
transient-state home as `.claude/session-log.md` and
`.claude/last-build.json`. It is **not** written to `docs/` (which is real
documentation), and it follows the same fate as the other `.claude/`
scratch: untracked, not part of the plugin.

```
.claude/forks/
  stack.yaml                 # LIFO list of fork frames + their status
  <fork-id>/
    context.md               # origin-thread snapshot + the question (written by /branch)
    resolution.md            # the distilled conclusion (written by /return in the side session)
```

`fork-id` format: `YYYY-MM-DD-HHMM-<slug>` (timestamp from
`date +%Y-%m-%d-%H%M`, never guessed; slug = topic kebab-cased).

`stack.yaml` frame:

```yaml
schema_version: 1
stack:                        # ordered, last pushed = newest
  - id: 2026-05-30-1539-cache-tenant-lookup
    topic: should we cache the tenant lookup
    status: open              # open -> active -> resolved -> closed
    created_at: 2026-05-30T15:39:00-03:00
```

## The state machine

| status | meaning | set by |
|---|---|---|
| `open` | created in origin, side session not started yet | `/branch <assunto>` |
| `active` | resumed in a side session, discussion in progress | `/branch resume` |
| `resolved` | side session wrote `resolution.md` | `/return` (side session) |
| `closed` | resolution ingested back into origin | `/return` (origin) |

**The one invariant that drives everything:** *the "top of the stack" is
the top-most frame whose status is not `closed`.*

- `/branch` pushes a new frame → it becomes the new top.
- `/return` ingest marks the current top `closed` **in place** (the row is
  never deleted) → the previous frame automatically becomes the new top.

That single rule gives you both the **LIFO unwind** (nested forks close
innermost-first) and **idempotence** (re-ingesting an already-`closed`
frame is a no-op, because its status is the guard). Closed frames stay in
`stack.yaml` plus their `<fork-id>/` directory as an audit trail.

## Nested forks

Running `/branch` *inside* a side session just pushes another frame. The
LIFO rule means `/return` always closes the innermost open fork first, so
forks unwind in the order you'd expect:

```
push A (open)          top = A
push B (open)          top = B      ← B nested inside A's side session
B resolved → ingest    top = A      ← B closed in place, A re-surfaces
A resolved → ingest    top = (none) ← stack drained
```

## How `/return` picks save-vs-ingest

`/return` has two jobs — write the resolution (in the side session) or
ingest it (back in origin) — and it chooses by **reading its own
conversation**, not by a fragile global flag:

- **Did *this* session resume the fork** (run `/branch resume` / load its
  `context.md`)? → **save** mode: distill the discussion into
  `resolution.md`, mark `resolved`.
- **Otherwise** — this is the origin session, the frame is already
  `resolved` — → **ingest** mode: read the resolution, fold it in, mark
  `closed`.
- **Ambiguous** (conflicting signals)? `/return` stops and asks. A wrong
  call here is the one thing that corrupts the loop, so it never guesses.

This is why the nested case works: the session that *created* fork B did
not *resume* it, so from that session `/return` correctly resolves to
ingest, not save.

## When to use this — and when not to

Use `/branch` + `/return` when the side topic:

- needs **interactive** back-and-forth (a human in the loop), and
- is big enough that letting it run inline would bury the origin thread.

Do **not** reach for it when:

- The tangent is a 30-second question — just answer it inline.
- The side work is a self-contained, delegatable unit with **no** human
  back-and-forth — spawn a **subagent** (Task) instead. A subagent already
  gives you "fork into an isolated window → return only a summary"; it's
  the non-interactive sibling of this loop. The two-session ceremony only
  earns its keep when you need to *steer* the side discussion yourself.

## Commands

See [`commands.md`](commands.md#common) for the argument reference.

| Command | Role |
|---|---|
| `/common:branch <assunto>` | Origin session: snapshot the thread, push an `open` frame. Does **not** discuss the topic — it stops after the snapshot. |
| `/common:branch resume [<id>]` | Fresh session: load the snapshot, mark `active`, start the interactive side discussion. No id = top-most `open`/`active` frame (so an abandoned side session is still reachable). |
| `/common:return` (side session) | Distill the discussion into `resolution.md`, mark `resolved`. |
| `/common:return [<id>]` (origin) | Ingest the resolution into the main thread, mark the frame `closed` (LIFO pop). No id = top of stack. |

## Caveats

- **Two sessions, by design.** The isolation only holds because the side
  discussion runs elsewhere. If you run `/branch` and then keep talking in
  the *same* session, you get the snapshot but not the lean return.
- **Nothing is destroyed.** `/return` advances status; it never deletes a
  frame or its files. Prune `.claude/forks/<id>/` manually if it gets
  noisy.
- **Plugin cache.** New commands only appear after the `common` plugin is
  reloaded (cache is stale on same-version). See
  [`troubleshooting.md`](troubleshooting.md).
