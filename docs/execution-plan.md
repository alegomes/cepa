# The execution plan

*What do I do next?* — the question a long session dissolves, and what the
harness does to keep it answerable.

## The problem

At the end of a working session on one card, after hours of detours, the owner
wrote:

> Depois de tantas idas e vindas, a minha memória se perde e eu não sei o que
> fazer na sequência. Sim, o harness me sugeriu fazer um handoff agora mas, e
> depois? [...] Tenho que testá-lo manualmente? Ou tenho que executar um próximo
> card? [...] O card nasceu em uma sessão anterior na qual ele foi priorizado
> junto a vários outros. Quais são mesmo esses outros? Qual era mesmo a ordem?

That is one feeling and **three distinct losses**:

1. **The execution order doesn't survive the session that produced it.** A
   planning moment prioritised several items together. That priority became
   prose in a handoff and a line in a card description — but the list and its
   order never existed as a consultable artifact. A tracker stores the *queue*
   (the To Do column); it stores neither the *order* nor the *why*.
2. **The end of a card points nowhere.** A card closes with a summary, a verdict
   and a status. Nothing answers "and now?", so the two plausible answers —
   *validate it by hand* and *pull the next one* — compete in silence.
3. **A long session dissolves the thread.** Three rounds of proof gate, four
   cards opened, two scope decisions, and the original objective is buried under
   the trail of how you got here.

**Why the existing pieces don't cover it:** `/common:handoff` and the wrap-up
nudge save context and look *backwards* — great for resuming *this* line of
work, mute about the queue that preceded it. `/common:recap` is explicitly
retrospective (you asked / I delivered). `/board-flow:drain` runs a whole column
in priority order, but it's all-or-nothing with no human stop. `/maestro:run` is
the closest relative and solves the other half — but it was built for *parallel
execution in worktrees*, which is far too much machinery for "I have six items
and I'll work them one at a time, across different sessions."

## The artifact

One file: `<main-root>/.claude/programs/<nome>/plan.yaml`, `mode: single-track`,
schema annotated in [`common/plan-schema.yaml`](../common/plan-schema.yaml). The
`<main-root>` prefix is not decoration — see "Where the file lives" below.

```yaml
schema_version: 2
mode: single-track
program: ACME
source: "Jira ACME · To Do, triaged 2026-07-28"
items:
  - id: ACME-1235                 # card key OR an anchor in the source ("P9 do BACKLOG")
    title: "Block a bounce comment with no reason"
    why: "first — unblocks 1237 and 1240, which touch the same hook"
    status: pending               # pending | in_progress | done | blocked | dropped
    blocked_by: []
    human_pending: null
```

The order of `items` **is** the data. Three fields carry the three losses:

| Field | The question it answers |
|---|---|
| the order of `items` | "which one was first, again?" |
| `why` | "does this order still make sense?" — without it you re-prioritise from scratch |
| `human_pending` | "do I still have to validate this by hand?" |

`human_pending` is fed from the **Human validation route** of the Implementation
Summary — a field that is already mandatory (the `summary-nulls-gate` hook
blocks the comment without it) and was simply never aggregated anywhere.

**A tracker is optional.** An item's `id` is a card key *or* an anchor in
whatever source the work comes from. A repo whose demands live in `BACKLOG.md` —
the `cepa` repo itself, which keeps its own plan at
`.claude/programs/cepa/plan.yaml` — gets the order, the `why` and the human debt
all the same. What it doesn't get is reconciliation, and the tooling says so
rather than implying a verification that never happened.

### Where the file lives

`<programs>` = `<main-root>/.claude/programs`, where `<main-root>` is the parent
of `git rev-parse --git-common-dir` with the trailing `/.git` removed. Inside a
linked worktree that resolves to the MAIN clone, not to the current tree;
anywhere else it is the same thing as `git rev-parse --show-toplevel`. Every
command that touches a plan resolves the path this way — on read and on write
alike.

The plan is repo state, not session state, and the two obvious shortcuts each
lose it:

- **Writing it under the current worktree** hides the plan from every other
  session and destroys it when the worktree goes. Where `.gitignore` covers
  `.claude/` wholesale the file is invisible to git, so no guard on the removal
  path even sees it — that is what the rescue net in `_wtlib.py` exists to catch
  (BACKLOG, "camada 1"), and a net is worse than not needing one.
- **Copying a plan per worktree** (adding it to the seeding list of
  `seed_worktree`) trades a loud failure for a silent one: N copies, each
  written by its own session, none of them wrong-looking. On 2026-08-18 two
  copies of the same WEGO plan read 14 items and 47 items and both looked
  authoritative.

Anchoring at the main root is "camada 0" of the BACKLOG item on worktree
artifact loss: the layer that prevents the loss instead of recovering from it.

## The three moments

The plan answers the question only if something asks it. Three moments do:

| When | What answers | What it does |
|---|---|---|
| The order is being decided | [`/common:plan`](commands.md) | The single writer of the queue. From a spec, from a board (`--from-jira`, where [`/board-flow:triage`](commands.md) grooms the column by code evidence and hands back the order), or dictated by hand |
| A card closes | `/board-flow:execute` · `/fix` · `/prove` | Close with **"And now?"** — the human route verbatim + the next unblocked item |
| Mid-session, thread lost | [`/common:next`](commands.md) | Reconciles against the tracker (if any) and names **one** next step |
| Several items are ready to run | [`/common:drain-plan`](commands.md) | Executes the queue **in its own order**, stopping at the first item it cannot resolve on its own |

### Writing it: `/common:plan`

One document, one writer, three sources. Triage already read every card,
gathered evidence, and routed the queue — it was simply emitting an *unordered*
list and letting the ordering rationale die in the chat. It now proposes the To
Do list **in execution order**, each item carrying the reason it sits where it
sits, and — since stage 2 — hands that classification to `/common:plan` instead
of writing the file itself.

An order you merely approved still beats one that was never written down.

Re-running the writer **merges** rather than overwrites: `done` items keep their
`human_pending`, cancelled cards become `dropped` (kept, so the plan still
explains why they left). Under `--max`, the queue holds only the cards actually
classified, and the `source` line carries a `PARCIAL` note saying so — a
truncated plan must never read as the whole board.

Why the writer moved out of the tracker plugin: while `/board-flow:triage` was
the only command able to write the file, a repo with no Jira had no queue at
all, and the rules for turning a classified card into an item lived in that
command's prose — where they erode without a single test going red. They are
now in `cepa-plan from-triage`, which refuses a READY card with no `why`, an
OBSOLETE card with no reason, and a card still sitting in `needs-decision` (a
grill that never finished, buried inside a queue that reads as decided).

### Reading it: `/common:next`

It lives in `common`, not `board-flow`, because a plan doesn't require a tracker.

It ends with **one** recommendation and its `why` — never a menu, since a list of
equally-weighted options is precisely the state you're stuck in when you run it.
Before answering it reconciles the plan against the tracker, because **the plan
is a hypothesis, not a contract**: it records what was true when it was written.

Every divergence is *named*, never absorbed — each one means something happened
outside the plan, and a plan that silently absorbs reality is a plan that lies:

| Plan says | Tracker says | Reading |
|---|---|---|
| `pending` | done | finished elsewhere → ask what its human validation route was, or that debt is lost |
| `pending` | in progress | a live session may be on it → warn before starting it too |
| `done` | in progress / to do | it bounced back → `pending` again, and probably the real next step |
| item present | card gone / Won't Do | → `dropped`, with the reason |
| — | in To Do, absent from plan | the plan is stale or truncated → **name these**; never fold them in as if prioritised |

Cards on the board but absent from the plan are never appended: they were given
no position and no rationale, and inventing one would forge exactly the decision
this mechanism exists to preserve.

With no tracker wired, the command skips reconciliation and says the statuses are
self-reported. It does **not** substitute a guess: git proves a commit exists,
never that an item is *done*, and inferring `done` from a commit message is the
false confidence the done-confidence ladder exists to prevent.

### Closing human debt

A `human_pending` clears by becoming `null`, and **only the user clears it** —
they alone know whether they actually ran the route. Never a green test, never a
card status, never elapsed time. A list that closes itself is decoration, and the
debt goes back to being invisible.

## Relationship to the maestro

Both read the same schema; neither plugin depends on the other.

| | `single-track` | `parallel-waves` |
|---|---|---|
| Owner | board-flow / common | maestro |
| Unit | one item at a time, across sessions | waves of slices forked into worktrees |
| Extra fields | — | `surface`, `fork_after`, `acceptance_cmd`, `timeout_min`, … |
| Floor | none | ≥4 demands (D7) |
| Reader | `/common:next` | `/maestro:run` |

Point a single-track plan at `/maestro:run` or `cepa-dor` and it refuses by
**naming the right command**, instead of failing downstream with "no pending
wave" — an error that says what went wrong but not what to do.

Promoting single-track → a wave is deliberately manual: it requires declaring a
disjoint surface and an executable acceptance per item, which is real work worth
doing only against a real demand.

### Schema versions

**v2** made `mode` explicit and required. **v1** (waves only, no `mode`) is still
read by every consumer, so plans already on disk need no migration; `mode:
single-track` in a v1 plan is refused with an instruction to raise the version.

The version exists because `mode` changes what the document *means*: a
single-track plan has no `waves`. Without the number, a wave-only consumer can't
say "I don't know how to read this" — it reads a missing `waves` as an empty plan
and carries on.

## Status

The three pieces are built and guarded by `tests/test_fio_condutor.py`
(prompt-contract assertions with perturbation proofs). The two halves are at
different stages, and saying "none of it ran" hid that:

- **`/board-flow:triage` has run against live cards** — twice on the WEGO board
  (2026-08-16 over the whole 55-card queue, 2026-08-18 over 15 of them), and the
  merged result is on disk at `.claude/programs/WEGO/plan.yaml`: 77 ordered
  items, each with its `why`. Checked 2026-08-24.
- **`/common:next` has never reconciled against a live tracker.** That same file
  says so in its own header ("rode `/common:next --sync` para reconciliar contra
  o board antes de confiar"), and 76 of its 77 items still read `status:
  pending` — the statuses are what triage declared, not what the board says.

So the tests lock the contract, and one of the two consumers has now met a real
board. `--sync` against a live tracker remains unexercised.

One question is still deliberately open, to be decided with use rather than
guessed: whether the plan should surface at `SessionStart` alongside the handoff.

The other one — **who writes the plan in a repo with no tracker** — was answered
on 2026-08-24: a new `/common:plan <name>`, the single writer of the
`single-track` file, fed by `--from-spec`, by `--from-jira` (where
`/board-flow:triage` classifies and hands back the order instead of writing the
file itself), or dictated by hand. The card in `BACKLOG.md` ("Cinco portas de
planejamento") holds the full shape and what it costs.

**Stage 1 is built** (2026-08-24): `/common:plan` with `--from-spec` and the
hand-dictated queue, plus `common/bin/cepa-plan` — the mechanical writer, so the
refusals are code rather than prose. Reading the specification is mechanical too
(`cepa-plan from-spec`, one item per `### CS-N`, in the order of the text): while
it was only a paragraph of instruction, the only possible test was a grep over
that paragraph, which proves the command *promises* to inherit the order and
never that a run produces the queue it promised.

**Stage 2 is built** (2026-08-25): `--from-jira`, and `/board-flow:triage` no
longer writes `plan.yaml`. It writes a **handoff** —
`<programs>/<project_key>/triagem-<YYYY-MM-DD>.json`, the four buckets in the
execution order confirmed at its step 7 — and `cepa-plan from-triage` turns that
into items. The same lesson as stage 1 decided the shape: the rules that say
which bucket becomes a `pending` item (only `ready`; `implemented` belongs to
the proof queue, `needs-refinement` stays in the backlog, `obsolete` is kept as
`dropped` with its reason) were prose in `triage.md`, provable only by grepping
the prose. **Stage 3 is built** (2026-08-25): `/common:drain-plan <name>` executes the
queue in the order the queue keeps. Until then the only bulk executor was
`/board-flow:drain`, whose source is the board column ordered by `priority and
rank` — precisely the order this document exists to replace — so the owner wrote
an order down and the only way to run it in bulk was one that ignored it. Which
items are runnable *right now* is mechanical too (`cepa-plan queue`), for the
same reason as stages 1 and 2: as prose, "respect the order" is provable only by
grepping the prose. The batch walks the list from the top and **stops** at the
first thing it cannot resolve alone — an open `human_pending` (the owner's call,
2026-08-25: the next item usually builds on what that route validates), an item
blocked by something outside the batch, one already `blocked` by an earlier run,
one reserved by another session, or the `--max` ceiling. It never skips a stuck
item to reach the one below, because that is reordering the queue in silence.
Each item is reserved before it is touched (`cepa-plan start` — the trackerless
equivalent of the claim `/board-flow:drain` posts on a card) and gets a named
terminal outcome with evidence (`cepa-plan finish`). Stage 4 (`--from-plan` on
`/maestro:program-plan`) is not built.

### Who may write the queue, and what the writer refuses

`cepa-plan` exists because the losses this document is about are all silent
ones, and a `.md` telling the model to check the `why` before writing is exactly
the kind of instruction that erodes without anyone noticing. It refuses an empty
`why` (the queue would keep the order and lose its criterion — the one thing a
tracker already failed to keep), a duplicate `id`, a `blocked_by` pointing at an
item that isn't in the queue *and was never classified* (a dependency on a card
the triage routed elsewhere is dropped from the field and named out loud
instead, since `/common:next` can only wait on items of its own queue), and a
blocking cycle, which is the nastiest of the
four: with two items blocking each other nothing is ever a candidate, so
`/common:next` reports the queue as finished rather than as stuck.

It is also the mirror of `maestro-programs --check-name`. Both planners write
into the same directory and the program name is the caller's free choice, so
each side refuses to overwrite the other's document: waves never overwrite a
queue, and a queue never overwrites waves.

On a rewrite — repriorising is normal — the new list rules the order, the
`title` and the `why`, which are planning decisions; the file on disk rules
`status` and any OPEN `human_pending`, which came from execution. That second
one matters more than it looks: only the human closes a `human_pending`, and a
freshly planned list carries `null` in every item, so taking it literally would
erase the debt at the exact moment someone is re-reading the queue.

## See also

- [`common/plan-schema.yaml`](../common/plan-schema.yaml) — the annotated schema, both modes
- [commands.md](commands.md) — `/common:plan` (the writer), `/common:next`, `/board-flow:triage`
- [board-flow.md](board-flow.md) — the tracker half: config, Implementation Summary contract
- [maestro.md](maestro.md) — the `parallel-waves` sibling
- [handoff.md](handoff.md) — resuming *this* line of work (the plan handles the queue *around* it)
