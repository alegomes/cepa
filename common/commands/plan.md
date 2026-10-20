---
description: The single writer of the repo's `single-track` queue, `.claude/programs/<name>/plan.yaml`: the document that keeps the ORDER of the items and the WHY of each position, which is what a tracker loses. Four sources: `--from-spec` turns each success criterion of a /common:spec specification into an item, inheriting the order of the text (and saying so); `--from-epic` with `--ciclo N` turns each sentence of a cycle's "O que atravessa" in a /common:epic Epic into an item and the cycle's demonstration script into the queue's `demonstra:`; `--from-jira` takes the classification of /board-flow:triage (which reads the cards and hunts evidence in the code) and records the order it proposed; or a queue dictated by hand, for a repo with no tracker and no spec. Needs no Jira. Refuses to overwrite a `parallel-waves` file of /maestro:program-plan. /common:next reads the queue afterwards.
argument-hint: <name> [--from-spec docs/spec/<slug>.md | --from-epic docs/epics/<name>.md --ciclo N | --from-jira [column|handoff.json]] [--dry-run] [--on-missing refuse|keep|drop]
interaction: conversational
---

# /common:plan

## Purpose

Give the `single-track` queue an author in a repo that has no tracker.

The document has existed since 2026-07-28 and solves a real pain: Jira keeps
the QUEUE (the To Do column) and keeps neither its ORDER nor its WHY, so the
prioritization decided in a session became prose in the handoff and
evaporated. But the only command able to write that file was
`/board-flow:triage`, which requires Jira. The result is the hole this command
closes:

- **a repo without a tracker had no queue** — and without a queue
  `/common:next` has nothing to read, so the question "and now, what do I do?"
  is once again answered nowhere in writing;
- **`/common:spec` had no way out** — it was built on purpose not to require a
  configured board, and still what it produces (a closed specification, with
  success criteria already measured) only kept moving with one.

It is stage 1 of the "one writer, three sources" design (`BACKLOG.md`, "Cinco
portas de planejamento", approved by the owner on 2026-08-24): one queue, one
author, several sources. The other stages consume the file this command now
writes.

Stage 2 closed the other side: `/board-flow:triage` **stopped writing**
`plan.yaml` and started handing its classification over to this command. Since
then "one writer" is literal — the queue has a single author, and the Jira
source is one of the three instead of the prerequisite.

**This does not plan waves.** `mode: parallel-waves` is another document, with
another author (`/maestro:program-plan`) and another executor (`/maestro:run`):
it has a disjoint surface, a fork point and an executable acceptance per slice.
Both live in the same directory and are told apart by an internal field, so
this command **refuses** to write to a name that is already a wave plan,
instead of erasing it.

## Variables

- `<name>` — the program name, which becomes
  `<main-root>/.claude/programs/<name>/plan.yaml`. In a repo with a
  tracker, the custom is to use the project key (`WEGO`); without a tracker,
  the repo name or the name of the batch of work.
- `--from-spec docs/spec/<slug>.md` — each success criterion of the
  specification becomes an item of the queue.
- `--from-epic docs/epics/<name>.md` — the queue comes from ONE cycle of the
  value ladder of a `/common:epic` Epic: each sentence of the "O que atravessa"
  column becomes an item, and the cycle's demonstration script becomes the
  header's `demonstra:`. Always with `--ciclo`.
- `--ciclo N` — which cycle of the ladder becomes a queue (the number in the
  "Ciclo" column). An Epic has several cycles and a queue belongs to only one;
  the custom is for the queue name to end in `-c<N>`.
- `--from-jira [column|handoff.json]` — the queue comes from the
  classification of a triage. With a file, it records a handoff a triage has
  already produced; with a column name (or nothing, which is `Backlog`), it
  runs `/board-flow:triage` first and records its handoff.
- `--source "text"` — where the demands came from, for traceability. Without
  the flag, the command fills it in from the source it used.
- `--dry-run` — shows the file that would be written and does not write it.
- `--on-missing refuse|keep|drop` — what to do with an item that is already in
  the queue on disk and that the new list does not mention. Default `refuse`:
  making it vanish silently erases a position and a `why` someone decided. With
  `--from-jira`, `keep` is the **partial triage**: the queue on disk stays in
  its own order and the new cards come after it, in the triage's order — the
  triage read a piece of the column, and its order does not stand against
  pending items the owner already prioritized. Without `--on-missing`,
  `--from-jira` does not refuse: `done`/`dropped` items the triage does not
  mention are preserved as a block at the start of the queue, the triage's
  items come in the approved order, and the open ones it did not cite come
  after, in the old order (the command warns which). With `drop`, only those
  open ones become `dropped`; `done` items are never touched.

**`--from-jira` does not query Jira on its own.** The order of a queue that
comes from a board comes from the CLASSIFICATION, never from the column: the one
who reads the cards, hunts for evidence in the code and routes the four buckets
is `/board-flow:triage`. This command records what it classified. Building the
queue here from a raw Jira query would give back the board's rank order — which
is exactly the order this document exists to replace.

## Instructions

**The order and the `why` belong to the owner, never to you.** This command
writes the document that records a prioritization decision — inventing a
plausible `why` is worse than having none, because the invented text reads,
months later, as a criterion someone chose. Where the `why` is already written
(in a spec, a card, `BACKLOG.md`), inherit it and say where it came from. Where
it is not, ask.

That is why this command is `conversational`: the `default-yes` policy is not
injected here, and the `guided-interrogation` skill applies while the queue is
being dictated by hand. Asking for the order is the job, not the last resort.

**Does not execute anything.** The command writes a file. The
one who names the next step is `/common:next`; the one who executes in batch is
`/common:drain-plan` (stage 3, built on 2026-08-25), in the order this queue
keeps.

**The write is mechanical.** The one who validates, merges and writes is
`common/bin/cepa-plan` — do not write the YAML by hand with `Write`. The script
refuses an empty `why`, a repeated `id`, a `blocked_by` pointing to a
nonexistent item, a blocking cycle and a `human_pending` without the key; if you
write the file from outside, none of those refusals happens.

## Workflow

### 1. Resolve the root and check the name

The queue lives in the **main clone**: `<main-root>/.claude/programs/<name>/`,
where `<main-root>` is the parent of
`git rev-parse --git-common-dir` without the trailing `/.git` — inside a linked
worktree that is the MAIN clone, not this tree. Writing against the current
directory is the loss of 2026-08-18: in a repo whose `.gitignore` covers
`.claude/`, the queue is invisible to git and dies with the worktree, without a
word (`docs/execution-plan.md`, "Where the file lives").

You do not need to resolve this by hand — `cepa-plan` resolves it by the same
rule — but you need to know it, because it is the path that goes in the report.

```
python3 common/bin/cepa-plan check-name <name> --repo .
```

Exit 3 is a **collision with a wave plan**: stop and say the name of the
program that is there. Do not suggest `--force`, it does not exist: erasing the
waves means losing the surface and the acceptance of each slice. Ask for
another name.

Exit 0 with the note "nome ocupado por uma fila" (name taken by a queue) is a
rewrite, the normal reprioritization flow — go on, knowing the queue there will
be merged in step 4.

### 2. Gather the items

#### With `--from-spec`

**Reading the spec is mechanical**, not yours:

```
python3 common/bin/cepa-plan from-spec docs/spec/<slug>.md
```

It returns the list of items as JSON — **one item per success criterion**
(`### CS-N`), in the order they appear in the text — and warns on stderr when
the spec is still a draft, when a `- [ ]` question is left over or when some
criterion does not declare **Teste vermelho:** (red test). It is not decoration
that this is code: the sentence that records the inherited order must appear in
the written file, and a prose instruction only proves the command PROMISES to
write it.

What comes out of there is a draft for you to review with the owner, not the
final result:

- `id` — `CS-1`, `CS-2`… or the criterion's slug; what matters is that it is
  stable, since `blocked_by` points by it.
- `title` — the criterion in observable terms, the line of the `### CS-N`
  itself.
- `why` — the script builds it from what the specification already wrote: the
  **Superfície** (surface) where the criterion is observable, the declared
  **Teste vermelho**, and the sentence that records the inheritance —
  **"herdado da ordem do texto da especificação; ninguém priorizou os critérios
  entre si"** (inherited from the order of the specification's text; nobody
  prioritized the criteria among themselves). Where the Problema/Escopo section
  says why that criterion comes before the others, replace the inheritance
  sentence with that reason, which is better. The report says out loud what was
  inherited.
- `blocked_by` — the script fills it with what the spec itself declares in
  prose ("Depois do CS-1", "após o CS-2 e CS-3"). Until 2026-09-24 it always
  returned empty and the rule was for you to add it by hand; in WEGO nobody
  did. Do not deduce dependency beyond that, such as two criteria touching the
  same file.
- `human_pending` — `null`. At planning time there is no route to collect on
  yet; the field is filled in later, when the item closes and the
  Implementation Summary says what the human validation route is.

**Order inherited, and said so.** The criteria of a spec do not come
prioritized among themselves. The preference recorded in the design is to
inherit the order of the text and **say that it inherited it** — not to ask item by item, which hands the owner a job they already did
once. Offer to reorder in ONE closed question at the end, with the whole queue
in view.

**Spec still a draft.** If `**Status:**` is not `pronta-para-construir`, say
how many `- [ ]` questions are still open and ask ONE closed question: close
the specification first (`/common:spec --fechar <slug>`) or write the queue
anyway. Recommend closing first — a criterion without an observable surface
becomes a queue item nobody knows when finished.

#### With `--from-epic` and `--ciclo`

The source here is a cycle of the value ladder of an Epic
(`docs/epics/<name>.md`, written by `/common:epic`). **The reading is
mechanical**, not yours:

```
python3 common/bin/cepa-plan from-epic docs/epics/<name>.md --ciclo N
```

It returns a JSON with the cycle's `demonstra` and `items`, and applies the
rules that previously had no owner:

- **the queue's `demonstra:` is the cycle's script**, verbatim. It is what the
  Epic declares as acceptance, and it is what `cepa-plan show` prints later;
- **one item per sentence of "O que atravessa"**, in the order of the text,
  with id `C<N>-<k>`. A sentence is the stretch ending in `.` or `;` outside
  backticks: `/common:epic` writes one sentence per piece, and an Epic written
  by hand before it separates the pieces with `;`. An abbreviation with a
  period ("etc.", "p. ex.") also splits the sentence: in the Epic, it goes
  inside backticks;
- **the `why` of each item says** which cycle and which Epic the piece came
  from, that the order was inherited from the text (nobody prioritized the
  pieces among themselves), the **acceptance criterion** (the cycle's script)
  and the **surface where it is observed** (the "Efeito em tela" and "Efeito em
  backend" columns). No piece gets an invented criterion of its own: the Epic
  did not write one;
- **an Epic without the effect columns is not refused**, and that is said:
  each item is born with the surface "não declarada" (not declared) and a
  warning. Recommend that the owner fill in the cycle through `/common:epic`
  before draining the queue;
- **an Epic in `rascunho` (draft), or with a `- [ ]` question, is a warning**,
  as with the spec. Ask the same closed question: close the Epic first or
  write the queue anyway. Recommend closing first;
- **a cycle that does not exist, has no script or has an empty "O que
  atravessa" is a refusal**, with exit 2 and the reason. Do not fill the gap on
  your own.

When nothing changed in what `from-epic` returned, write directly with
`--from-epic <file> --ciclo N` in place of `--items`: it is the only path
that brings `demonstra:` into the header, because the item list does not carry
it.

#### With `--from-jira`

The source here is the **classification** of a triage, not the board column.

**If a file came** (`--from-jira <handoff.json>`), a triage has already run and
its handoff is on disk — usually at
`<main-root>/.claude/programs/<name>/triagem-<YYYY-MM-DD>.json`, where
`/board-flow:triage` leaves it. Skip to step 3.

**If a column name came** (or nothing, which is `Backlog`), the triage has not
run yet. Require the two things it depends on, and stop naming whichever is
missing:

- the `board-flow` plugin installed — without it there is no one to talk to
  Jira (`atlassian-expert` is the harness's only write path);
- a `board-flow.yaml` at the project root (or the legacy
  `.claude/board-flow.lifecycle.yaml`), where `defaults.project_key` and the
  `status_map` come from.

If either is missing, **do not improvise a Jira query**: say that a queue from a board needs the triage, and offer
the two ways out that exist without it — `--from-spec`, if there is a closed
specification, or the queue dictated by hand.

With both present, run `/board-flow:triage <column>` and follow its workflow up
to step 9, which is where it records the handoff. What comes back is the
classification in the four buckets with the execution order **that the owner
confirmed in step 7** — the order is theirs and the evidence the triage
gathered, not yours.

**Reading the handoff is mechanical**, not yours:

```
python3 common/bin/cepa-plan from-triage <handoff.json>
```

For the same reason as `from-spec`: the rules below lived in the prose of
`triage.md`, and command prose erodes without any test going red. The script
applies them, and refuses when it cannot:

- **only a `ready` card becomes a `pending` item.** An `implemented` card went
  to In Review and belongs to the PROOF queue (`/board-flow:prove-drain`); a
  `needs-refinement` card stays in the backlog. Both leave the queue and the
  script SAYS which, with the count — repeat that in the report.
- **an `obsolete` card comes in as `dropped`, with the reason.** The card
  leaves the queue and the document keeps explaining why; deleting it makes the
  next sweep propose the same demand again.
- **a READY card without a `why` is a refusal**, not an item with an invented
  `why`. The `why` of each position was already said in step 7 of the triage —
  if it got lost on the way, ask, do not fill it in.
- **a card still in `needs-decision` is a refusal.** The grilling of step 6 is
  not finished, and writing like that would hide an open question inside a
  queue that reads as decided.
- **a dependency pointing outside the queue leaves `blocked_by`, and that is
  said.** A READY card that depended on a card that went to In Review loses its
  `blocked_by` (`/common:next` only knows how to wait for an item of its own
  queue) and the warning names both — from then on the dependency is the
  owner's to watch.
- **`--max` is never silent.** The handoff's `remaining_in_column` becomes a
  `PARCIAL` note on the plan's `source` line, and that is what keeps a queue of
  15 cards out of 27 from being read, months later, as the whole board.

When nothing changed in what `from-triage` returned, `--from-triage <file>`
does the reading and the writing at once, in place of `--items`. The `source`
line comes from the handoff itself (project, column, scope, date, and the
partiality note).

#### No flag — the queue dictated by hand

The case of the repo with no tracker and no spec (this repo is one). Before
asking anything, **read the source of demands the repo already has**:
`BACKLOG.md`, the documents in `docs/`, the handoffs in
`<main-root>/.claude/handoffs/`. A question whose answer was in the repo
burns the owner's patience.

Then, in rounds of at most four questions:

1. **which demands come in** — propose the list you read, with each one's
   anchor in the source (`"P9 do BACKLOG"`, an ADR, an issue number), and let
   the owner cut;
2. **in what order** — propose one, with the reason for each position, and let
   the owner correct it. A proposal with a reason is much cheaper to answer
   than an open question;
3. **the `why` of each position** — whatever you could not get from the
   source, ask. An item without a `why` cannot be written, and `cepa-plan`
   refuses the whole queue because of it.

### 3. Show the queue before writing

Always. Run with `--dry-run` and show the queue in three columns — position,
item, `why` on one line — plus what the queue on disk already had, if it is a
rewrite. **One closed question** ("write it like this?"), not an item-by-item
review. Ask it in Brazilian Portuguese (pt-BR).

### 4. Write

```
python3 common/bin/cepa-plan write <name> \
  --items <file.json> --source "<where it came from>" --quando <YYYY-MM-DD> --repo .
```

When nothing changed in what `from-spec` (or `from-triage`, or `from-epic`)
returned, `--from-spec <file>` / `--from-triage <file>` /
`--from-epic <file> --ciclo N` does both things at once, in place of
`--items`.

Write the items into a temporary JSON file (or send them via stdin with `-`).
The script:

- validates everything and **writes nothing** if any item has a gap — the
  queue is one document, half a queue written is worse than none;
- merges with what is already on disk: the new list rules the order, the
  `title` and the `why`, which are planning decisions; the disk rules the
  `status` and the `human_pending`, which came from execution. **This is not a
  detail**: only the human closes a `human_pending`, so a rewrite that zeroed
  them would erase debt nobody paid;
- copies the previous file to `plan.yaml.bak` before overwriting, because
  comments written by hand (the evidence of each `done`, for example) do not
  survive the rewrite.

Exit 4 is an item on disk that the new list does not mention (`--from-jira`
no longer refuses: `done`/`dropped` are preserved and the absent open ones go
after, with a warning): **do not pass
`--on-missing drop` on your own** — show the ids and ask.

### 5. Report and point forward

Say where it was written, how many items, from what source, and what was
**not** decided here. End by naming who reads the file now: `/common:next`.

## Report

The report is written in Brazilian Portuguese (pt-BR); the template below is
its English rendering:

```
Queue written: <main-root>/.claude/programs/cepa/plan.yaml
  7 items · source: docs/spec/planejador-de-lotes.md (7 success criteria)

Order inherited from the specification's text. Nobody prioritized the criteria
among themselves — if the order matters, now is the time to say so.

  1. CS-1 — planner accepts a source that is not the BACKLOG
     because: it is the only criterion the other six presuppose
  2. CS-2 — ...

Nothing pending with you: no item was born with a human validation route; that
field gets filled in when the item closes.

Next step: /common:next (names ONE item and the why of it).
```

## Constraints

- **Never invents order or `why`.** It inherits
  from a written source and says where from, or asks. A plausible `why` written
  by you reads later as a criterion someone chose, and that is exactly the lie
  the queue exists not to tell.
- **Never writes over a wave plan.** A collision is a named refusal, with no escape.
- **Never queries Jira directly.** With
  `--from-jira`, the one who reads the cards and classifies is
  `/board-flow:triage`; this command records what it classified. A queue built
  from a raw query to the column inherits the board's rank order, which is the
  order this document exists to replace.
- **Never writes the YAML by hand.** The write
  goes through `common/bin/cepa-plan`, which is where the refusals live.
- **Never closes anyone's `human_pending`.**
  An item that comes from disk with an open pending action keeps it. The one
  who closes it is the owner, in `/common:next --sync`.
- **Does not execute and does not touch the tracker.** The only file this command writes is the queue (plus the `.bak`
  of the previous version).
- **One queue per name.** On finding an existing one, merge; do not create
  `<name>-2`.

## See also

- [`docs/execution-plan.md`](../../docs/execution-plan.md) — the whole mechanism and why the file lives in the main clone
- [`common/plan-schema.yaml`](../plan-schema.yaml) — the annotated schema, the two modes
- `/common:next` — the queue's consumer
- `/common:spec` — the source `--from-spec` reads
- `/board-flow:triage` — the source `--from-jira` reads: it classifies the cards and hands over the order; since stage 2 it no longer writes `plan.yaml`
