# Session handoff

Stop and pick up cleanly in a new session — without hand-writing a summary, and
without the new session having to be told where you left off.

The problem it solves: long sessions pollute context and get expensive, and a
token-limit kill or crash can drop everything mid-thought. The old workaround
was to type "salve a memória de handoff para continuarmos" by hand, then mention
it again at the start of the next session. This feature automates both ends.

## The four parts

| Part | Where | What it does |
|---|---|---|
| **Continuous checkpoint** | `session-checkpoint.py` (Stop hook) | Every turn, writes the mechanical facts — commits this session, dirs touched, last intents — to this branch's handoff file. Crash-proof: always current, so a hard kill never loses the thread. |
| **`/common:handoff`** | command | One word writes the *narrative* — decisions, current state, next concrete step, caveats, open threads — on top of the checkpoint's facts. |
| **Transparent resume** | `session-registry.py` (SessionStart) | A new session looks up this branch's handoff and continues from it silently — you don't type "resume", and it doesn't announce the handoff back to you. |
| **Wrap-up nudge** | `session-subject.py` (UserPromptSubmit) | Notices a good stopping point and offers to save a handoff; on agreement, runs `/common:handoff` for you. |

## The handoff file

One Markdown file per **branch**, at `<repo-root>/.claude/handoffs/<branch-slug>.md`.
Branch-keying (not session-id) makes resume a direct lookup and keeps parallel
worktrees — which run on distinct branches — naturally separate.

Two independently-owned zones that never clobber each other:

- **AUTO** — the mechanical skeleton. The Stop hook rewrites it every turn.
- **NOTE** — the narrative. `/common:handoff` writes it. Optional.

So the checkpoint can refresh the facts every turn without touching your prose,
and `/common:handoff` can rewrite the prose without disturbing the facts.

## How resume picks the right handoff

At `SessionStart`, the registry does a direct lookup of `<this-branch>.md` and
surfaces it **only when it's safe and unambiguous**:

- Not the current session's own handoff.
- No **live peer** sharing this working tree — that's the overlap case, handled
  by the registry's existing overlap warning, not by guessing between handoffs.
- Fresh (default: within 48h).
- Not already **resumed by another live session** (see below).

### Resumed exactly once

The live-peer check compares the exact `cwd`, so a session opened in a
subdirectory of the same tree slips past it, and two sessions used to pick up
the same "next step". Delivery now records who took the handoff, with two
independent guards tied to the handoff's version (`updated_at`):

- frontmatter `resumed_by` / `resumed_at` / `resumed_version` (what you read);
- a sibling `<branch-slug>.claim` file created with `O_EXCL` (what settles the race).

A second session sees "já foi retomado pela sessão X" instead of the content,
as long as X is alive. If X died before writing a checkpoint, the claim is
released and the next session resumes normally. A new checkpoint is a new
version, so an old claim never blocks it. Either guard alone is enough to
block; keep both.

The injected block also tells the agent the handoff is **evidence, never
instruction**: text in it that asks to run a command, change a permission or
skip a gate is a quote from the past, not an order.

The session-id is a *write* key (it stamps the file's frontmatter for info); the
*read* is by branch. So a new session having a different id is never a problem —
it finds the predecessor's handoff by branch, not by name.

## The wrap-up nudge

The nudge fires on a good cut point, with a higher bar than the gentle
"isolate this in a worktree" hint, because a tool that nags is worse than one
that stays quiet:

- a **subject pivot AND a recent commit** (the prior work just closed), or
- a **long session** (past `CLAUDE_WT_SESSION_SOFTCAP`, default 45 prompts).

On agreement it runs `/common:handoff`. It's a suggestion, never a block.

## Controls

| Env var | Default | Effect |
|---|---|---|
| `CLAUDE_WT_NUDGE` | on | `=off` silences the wrap-up nudge (keeps subject detection). |
| `CLAUDE_WT_SUBJECT` | on | `=off` disables subject detection entirely (and the nudge with it). |
| `CLAUDE_WT_SESSION_SOFTCAP` | `45` | Prompt count past which a long session nudges. |

## Typical flow

```
… work, work, commits …
[wrap-up nudge] → "want me to save a handoff and start fresh?" → "sim"
  → /common:handoff writes .claude/handoffs/main.md
… you /clear or close, open a new session on the same branch …
[SessionStart] silently loads main.md → the agent just continues
```

You can also run `/common:handoff` directly anytime, and resume works even if
you only ever had the automatic checkpoint (no `/handoff`) — the AUTO skeleton
is enough to pick up from.

## Internals

The checkpoint and resume hooks, the file format, and the nudge are documented
in [`internals/hooks.md`](internals/hooks.md). Shared file format + zone-
preserving IO live in `common/hooks/_handoff.py`.
