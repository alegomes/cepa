---
description: Runs the repo's `single-track` queue, `.claude/queues/<name>/queue.yaml`, in batch and IN THE ORDER IT KEEPS. Stage 3 of the "one writer, three sources" design, closing the loop without a tracker: `/common:queue` writes the queue, `/common:next` names ONE step, this command runs several. Needs no Jira and never takes the ORDER from one: the only batch that existed before, `/board-flow:drain`, takes its order from the board rank, exactly the order the queue exists to replace. Keeps what drain got right: stop at the first stuck item and the `--max` ceiling. A route only a human closes DEFERS the item and the batch goes on, listing every route at the end. Reserves each item before touching it, with a recorded owner (to tell a live session from a dead run), and records the outcome of all of them. In a repo with Jira it reconciles against the board before building the batch and always moves the card of every item that is a card: In Progress on reserve, In Review on finish, a comment with the reason on block.
argument-hint: <name> [--max N] [--dry-run] [--offline] [--na-branch <branch>]
interaction: routine
---

# /common:drain-plan

## Purpose

Run the queue in its own order.

The `mode: single-track` of `queue.yaml` exists to keep the two things the
tracker loses: the execution **order** and the **`why`** of each item sitting
in that position. Until now no command ran that queue in batch:

- `/common:next` reads the queue and names ONE item, and is read-only by contract;
- `/board-flow:drain` runs in batch, but its source is the Jira column,
  sorted by the board's `priority and rank` — the order the queue exists to
  replace. It never opens `queue.yaml`;
- in a repo with no tracker (this repo's `cepa` queue, whose ids are not cards)
  there wasn't even that way out: all that was left was chaining
  `/common:next` + execution by hand, one item at a time.

In other words: the owner wrote the order into the queue, and the only way to
run it in batch was one that ignored that order. This command closes the loop —
write (`/common:queue`) → point (`/common:next`) → run (here) — with no tracker
at all in the path.

**This does not run waves.** `mode: parallel-waves` is another document, with
another author (`/maestro:program-plan`) and another runner (`/maestro:run`),
which forks worktrees in parallel. This command **refuses** a waves plan instead
of trying to linearize it.

## Variables

- `<nome>` — the program whose queue will be run, that is
  `<raiz-principal>/.claude/queues/<nome>/queue.yaml`. Without the argument,
  resolution is the same as `/common:next`: `board-flow.yaml` → `project_key`, or
  the only `single-track` queue that exists; if there is more than one, the
  command lists them and asks instead of choosing for you.
- `--max N` — ceiling of items in this batch. Default **3**. It is lower than
  `/board-flow:drain`'s (5) because a queue item tends to be bigger than a card:
  each one runs the topology's whole flow plus the two gates (acceptance and proof).
- `--dry-run` — shows the batch that would run, with the stop and the why of
  each item, and neither runs nor marks anything.
- `--offline` — does not read the board in step 0 and does not transition any
  card. Use it when Jira is down or you want to run without network; the report
  says the queue's status is self-reported.
- `--na-branch <branch>` — passed by `cepa-until`. It says the directory you
  woke up in is already the worktree of the overnight branch, and it changes
  three things (see "On the overnight branch", in step 3).

## Instructions

**The order is the data.** Do not pick items, do not skip a stuck item to reach
the one below, do not reorder because "this one is faster". Skipping is
reordering the queue in silence — and a queue reordered in silence is the same
as having no queue, which is the state this document exists to get rid of.

**The batch is built by `cepa-plan`, not by your eye.** While the rules for
"what can run now" lived in a command's prose, the only possible test was to
grep the prose — which proves the command PROMISES to respect the order, never
that a run did. Run `cepa-plan queue` and execute what it returned.

**Never edit `queue.yaml` by hand** — not with `Write`, not with `sed`. Marking
goes through `cepa-plan start` / `cepa-plan finish`, which refuse an outcome
without evidence, refuse a double reservation and refuse to close a human route.
Written from outside, none of those refusals happen.

**The queue rules the ORDER; the board, when there is one, is mirrored.** This
command never takes the order from Jira — that is exactly what
`/board-flow:drain` does and what the queue exists to replace. But it no longer
ignores the board (the two directions keep their pt-BR labels, which the owner
reads: "Trazer status do Jira (grava no plano)" = pull status from Jira, writes
to the queue; "Atualizar o Jira (grava no quadro)" = update Jira, writes to the
board):

- **before** building the batch, **Trazer status do Jira (grava no plano)** (step 0): reads Jira and writes to the
  queue — without it the batch runs an item someone already closed elsewhere;
- **during** the batch, every item whose `id` is a card key goes through
  **Atualizar o Jira (grava no quadro)**, and that is **mandatory**, not optional: on reserve
  (step 3.a) the card goes to `defaults.status_map.in_progress`; on closing
  `done` (step 3.e) it goes to `defaults.status_map.in_review` with the
  Implementation Summary; on getting stuck or going back to `pending` (step 3.f)
  it gets a comment with the reason, and goes to `defaults.status_map.blocked`
  when the board declares that column. It is the same cycle as
  `/board-flow:execute`. Without it, every drained batch PRODUCES the divergence
  the next reconciliation would have to fix, and the owner sees on the board a
  card in To Do that already has finished code on a branch (WEGO-2349, run
  2026-10-02-0838).

Jira is always spoken to by `atlassian-expert` — this command does not call any
Atlassian tool directly, and the queue × board comparison belongs to
`cepa-plan reconcile`, not your eye. Repo without `board-flow.yaml`: none of this
happens, and the queue is the only truth.

## Workflow

### 0. Trazer status do Jira (grava no plano) — only when there is a board

The name says the direction: this step READS Jira and WRITES to `queue.yaml`. It
does not touch the board. (The opposite, writing to the board, is the
"Atualizar o Jira (grava no quadro)" of step 3.e.) "Reconciliar" (reconcile) and
"sync" were the old names and did not say which of the two sides changed; the
owner had to ask (desvios.md, 2026-08-29).

Skip this whole step if there is no `board-flow.yaml` (nor
`.claude/board-flow.lifecycle.yaml`), or with `--offline`. Without a board there
is nothing to reconcile: the queue is the only truth and the report says so.

With a board, delegate the reading to `atlassian-expert` — the only one who
speaks to Jira — asking for the current status of **each queue `id` that is a
card key**, and which of those keys Jira says do not exist:

> Read the current status of these Jira issues: `<queue ids>`. Return JSON:
> `{"cards": [{"key": ..., "status": "<the literal Jira status name>"}],
> "missing": ["<keys Jira reports as nonexistent>"]}`. Do not transition
> anything.

The "Do not transition anything" applies only to THIS request, which is a read.
It is not the batch's policy toward the board: the transitions of step 3 are
mandatory.

Save the response and hand it to the comparer:

```
python3 common/bin/cepa-plan reconcile <nome> --board <arquivo.json> --apply --repo .
```

The comparison is its job, not yours: it reads the `defaults.status_map` from
`board-flow.yaml` (status names vary by team — "Doing", "Code Review") and
returns the divergences already classified. What it does **not** do, and neither
do you: close a `human_pending` (only the human closes it) and append to the
queue a card the board has and the queue does not — a position without a `why`
is precisely the decision the queue keeps. Cards in that situation come out in
`missing_from_plan`: **name them in the report** and say that the one who puts
them in is `/common:queue <nome> --from-jira`.

A status the `status_map` does not describe is not reconciled, and comes back as
a warning. Pass the warning on instead of guessing its role.

### 1. Resolve the queue and build the batch

The queue lives in the **main clone**: `<raiz-principal>/.claude/queues/<nome>/`,
where `<raiz-principal>` is the parent of `git rev-parse --git-common-dir` without
the trailing `/.git` — inside a linked worktree that is the MAIN clone, not this
tree. You don't resolve this by hand (`cepa-plan` resolves it by the same rule),
but you need to know, because it is the path that goes in the report.

```
python3 common/bin/cepa-plan queue <nome> --max N --repo . --json
```

What comes back: `batch` (the items runnable now, in queue order, each with the
`why` that put it in that position), `stop` (why the batch ends where it ends),
`warnings` and `totals`.

Exit 3 is a **waves plan**: stop and say that the runner for that document is
`/maestro:run`. Exit 2 with no queue: say there is no queue and that the writer
is `/common:queue <nome>` — do not invent an order, and do not fall back to
`/board-flow:drain` as a substitute, because it would run the board's order.

The stop reasons, and what each one wants from you:

| `stop.reason` | what happened |
|---|---|
| `teto` | `--max` filled up; the named item would be the next. Run again later. |
| `fim-da-fila` | no pending item left. Offer `/common:queue` for the next round. |
| `bloqueado` | the item depends on something that is neither done nor in this batch. |

And `queue` also returns `deferred` — the **deferred** items, which don't run
now and **don't stop the batch**. Deferring is an execution decision: the item
leaves this batch and comes back in the next `queue`, and the order recorded in
`queue.yaml` does not change. The four reasons:

| deferral reason | what happened |
|---|---|
| `human_pending` | the item has a route that **only you** close. Owner decision (2026-08-28, revisiting the one of 08-25): the route no longer blocks the flow — locking the queue until the human came back turned a batch of 3 into a batch of 1. The debt does not vanish: it is collected in the final report. |
| `reservado` | another **live** session is on the item right now — the deferral says which session, in which tree, since when. |
| `depende-de-adiado` | the item depends (`blocked_by`) on one that was left out. The cascade is what makes deferral work: without it, deferring B would make C stop the batch. |
| `bloqueado-antes` | the item came out `blocked` from a previous run and the outside condition did not change. It is not re-run — it would be the same block — but since 2026-08-30 it also does not block the ones after it. Owner decision, revisiting what was inherited from `/board-flow:drain`: in an unattended window (`cepa-until`), an item stuck at the head of the queue cost the whole night. |

A fourth situation is neither deferral nor stop: an `in_progress` whose owning
session **no longer exists** (dead pid on the same host, or a reservation from
another machine older than 24h) is an **orphan reservation** — `queue` returns it
as runnable, with a warning, and `start` claims it. The alternative was the queue
locking forever because of a run that ended. An `in_progress` **with no recorded
owner** (queue marked before this field existed), on the other hand, is deferred
saying there is no way to know: returning it to `pending` is your decision.

### 2. Confirm, only once

Show the batch and ask **once**, at the start — including the question that would
only come up in the middle of the run. The screen shown to the owner is rendered
in Brazilian Portuguese (pt-BR); the two board labels stay verbatim:

```
Queue <nome> — <path>
Batch of N item(s), in queue order:
  1. <id> — <title>
     because: <why>
  2. ...

Deferred (don't run now, don't block the batch):
  <id> — <reason>: <detail>          ← or "none"

After them the batch stops: <stop.reason> — <stop.detail>
<warnings, if any>

Board (only when there is one; with no board: "no board, queue status self-reported"):
  Trazer status do Jira (grava no plano): <what step 0 changed in the queue, or "nothing changed">
  Atualizar o Jira (grava no quadro): each item that is a card goes to <in_progress> when
    reserved, to <in_review> on finish, and gets the reason when it gets stuck

Shall I run it? Each item runs the topology's whole flow + the acceptance and proof gates.

And if an item gets stuck (BLOCKED — an outside condition only you can resolve):
  (a) I stop the batch there and call you                ← default
  (b) I record the reason on the item and go on with the rest

Answer yes / no / "only the first N", and (a) or (b).
```

This is the run's **only planned stop** — apply `default-yes`. The (a)/(b)
alternative has to be written there, not implied: asking at item 3 of 5 arrives
when the user has already lost the context of the list, and that cost is what
the single stop exists to avoid. If the run came from `/common:session`, these
answers were already collected — go on without asking.

With `--dry-run`, print that screen and stop.

### 3. Run, item by item

For each item of the batch, in order:

  a. **Reserve first**, before any build, worktree or delegation:

     ```
     python3 common/bin/cepa-plan start <nome> <id> --repo .
     ```

     Exit 5 means the item stopped being reservable since the batch was built
     (a live session reserved it, or a human route appeared). The refusal
     **names the session** — pass that name on, don't summarize it as "it is
     reserved". Record `SKIPPED` with the reason the command returned and go to
     the next one **without running anything** — a skipped item does not consume
     `--max`, because no work ran on it.

     The reservation is signed: `start` records `claimed_by` (session, pid, host,
     tree, time), which is what answers, in the next `queue`, whether it is a live
     session or a dead run. If the output says it recovered an **orphan
     reservation** (it prints "reserva órfã recuperada"), say so in the report —
     it means a previous run died in the middle of that item, and what it left
     half-done is yours to check.

     If the output carries **`evidence anterior`** (previous evidence), the item
     has already been through here and came back with a message (`cepa-until`
     returns to `pending` an item whose build went red, saying which build
     failed, the reason and the side branch with the commits). Carry the whole
     message into the flow of step b as part of the request: it is what says
     whether to reuse the side branch (`git cherry-pick` or `merge` inside this
     attempt) or redo it. Disabling or deleting the test that went red does not
     count as a fix.

     **Atualizar o Jira (grava no quadro), on reserve.** If the `id` is a card
     key and the repo has a board (and `--offline` was not passed), transition
     the card to `defaults.status_map.in_progress` right after `start` and before
     any work, delegating to `atlassian-expert`, like step 4 of
     `/board-flow:execute`. A card already in `in_progress` needs no transition.
     A failed transition does not undo the reservation nor stop the item: record
     the card as pending transition in the report.

     The reservation is the tracker-less equivalent of the claim
     `/board-flow:drain` publishes on the card: the list of step 1 is a snapshot,
     and between the snapshot and the moment you reach item N another window may
     have taken the same item. The cost of not reserving is not a file conflict,
     it is the whole work redone.

  b. **Run the item** through the repo's topology flow (`.claude/topology`),
     the way `/common:autonomous-start` dispatches: a defect item goes to
     `reproduce-fix-verify`, the rest to `plan-build-validate`. The item's
     `title` and `why` are the description; the `why` is priority context, not
     scope — do not widen the item to "make the most of being here"
     (`scope-discipline`).

  **On the overnight branch (`--na-branch <branch>`).**
  First check that `git rev-parse --abbrev-ref HEAD` returns exactly `<branch>`;
  if it does not, `finish --status blocked` with the divergence and stop. Then:

  - **work here.** Do not create a worktree or branch for the item (`git worktree
    add -b`, `git checkout -b`, `/common:worktree-start`), and do not start from
    `origin/main`. The overnight branch ALREADY has the night's earlier cards,
    and that is why it exists: in the run of 2026-09-23 each item opened its own
    worktree from `origin/main`, nothing merged, and 20 of 25 rounds got stuck
    because the previous card only existed on a loose branch. A throwaway
    worktree for proof perturbation (`git worktree add --detach /tmp/...`)
    remains allowed ONLY for `proof-reviewer`; `qa-engineer` and any other agent
    prove RED by ordering (test written before the fix) or leave the proof to
    `proof-reviewer`, and the `cepa-until` summary lists every worktree opened
    by another agent;
  - **commit directly on this branch**, with a clean tree before `finish`. The
    supervisor stashes whatever is left uncommitted, and the next card does not
    see it;
  - **no merge, no push, no Done.** The supervisor runs the full build after your
    `finish --status done`; if red, it removes your commits from the branch and
    marks the item `blocked`. The card goes to Review as always, and the
    evidence does not say "merge is left to the owner": it says the code is on
    the overnight branch;
  - **do not run the full build, and tell whoever you delegate to.** It belongs
    to the supervisor, which runs it right after your `finish`. Here run only the
    tests the item touched and their neighbors (`-Dtest=...` with `-am`, `-k`,
    the test file), in a command that fits in 10 minutes, the ceiling of each of
    the agent's commands: past that, Bash itself sends the command to the
    background and step d below becomes a broken rule without anyone having
    asked for it. Pass this rule in writing in the request of every agent that
    runs tests (`qa-engineer`, `validation-lead`, `proof-reviewer`). In the run
    of 2026-09-26 the `qa-engineer` of WEGO-2320 ran the `bootstrap` suite,
    which takes 15 minutes, it went to the background, and the round ended in
    "Continuo aguardando" ("Still waiting") after 85 minutes and US$ 14.15, with
    the item `in_progress`.

  - **whoever delegates waits for the worker in the same turn, and tell every
    lead.** Here each round is a `claude -p` and the lead is your subagent: if it
    ends its turn "waiting for the notification", what comes back to you is the
    item half-done, with the worker still running, and you spend a turn
    resending the result. Write in the request of every lead (`engineering-lead`,
    `validation-lead`, `planning-lead`) that it delegates with
    `run_in_background: false` and only returns with the worker's result in hand.
    In the run of 2026-10-15-1946 of wego-digitacao-backend there were 10 manual
    resumes in 5 of the 7 rounds, and S3-fio-openai cost US$ 22.54, 41.8% of the
    run.

  An item that depends on another of the same queue that is already `done` on the
  overnight branch is **not** stuck on "the predecessor is not on main": its code
  is here.

  c. **Go through both gates** before calling the item closed — they are the
     same as for any build in this harness, and the batch does not skip them for
     being a batch: `completion-auditor` (COMPLETE) and, when the item changed
     behavior, `proof-reviewer` (PROVEN). Any other verdict is not `done`; it is
     `blocked` or back to `pending`, with the reason.

     **Topology with `validation-lead` (build-hex, build-team): it is also a
     gate.** Its flow ends in it, and it is the one that calls
     `security-reviewer`. Delegate to `validation-lead` with the item's `id` as
     key; it writes `docs/validation/<id>.yaml`, and only `READY-TO-SHIP` or
     `READY-WITH-CAVEATS` closes `done`. `cepa-plan finish --status done` refuses
     without that file, so skipping the gate does not go unnoticed: in the run of
     2026-09-23 none of the 5 WEGO cards went through `validation-lead`, and
     WEGO-2318, which logs into the portal with the carrier's credential, closed
     without a security review. On the overnight branch, say in the request that
     the full build belongs to the supervisor: it records `build:
     delegated-to-supervisor` instead of running `./mvnw verify`.

  d. **Do not end the turn with your own work running in the background.** A
     build you started (`./mvnw verify`, `npm test`, the proof gate) has to be
     AWAITED and collected in the same turn it was started. Phrases like "I'm
     waiting for the build notification", "when it goes green I'll push" and "it's
     compiling in the background" describe a future that does not exist: when
     this command runs inside `cepa-until`, the process is a `claude -p` and
     **there is no next turn** — the process dies at the end of this one, the
     build becomes an orphan and the item stays `in_progress` with no outcome.

     It was the measured cause of the only two non-trivial failures of the run of
     2026-08-30: 34 of the window's 49 minutes, two items stopped exactly like
     that, exit 0 and nothing recorded.

     If the build does not fit in the turn, the outcome is not silence: it is
     `finish --status blocked --evidence "build disparado e não colhido: <o
     comando, e onde está o log>"` (build started and not collected: the command,
     and where the log is), or `--status pending` with the same evidence. An item
     with a named outcome comes back in the next window knowing where it stopped;
     an item with no outcome comes back as an orphan reservation and starts over
     from scratch.

  e. **Record the outcome**, always:

     ```
     python3 common/bin/cepa-plan finish <nome> <id> --status done \
         --evidence "commits, verdicts, what was left out" --repo .
     ```

     `--evidence` is mandatory: `done` is a word, and what makes it auditable
     months later is what happened. If the run produced a route only the human
     closes (validate in the UI, approve a PR, rotate a secret), open it with
     `--human-pending "<the route, verbatim>"` — that is how it survives the
     session. **Never close a route**: only whoever ran it knows whether it
     passed, and the command refuses.

     **A waiver produced in the item is a proposal, not a waiver.** If a waiver
     came out during the item (`waivers.gravar` in an autonomous run records
     `status: proposta`, with `fila=`/`item=`), open it as `--human-pending
     "Aceitar ou recusar a dispensa de <escopo> (<motivo>)"` with `--pergunta
     "Aceito a dispensa de <escopo> por <razão>? Recomendo <sim/não>: <porquê>"`
     (both owner-facing, in pt-BR: "Accept or refuse the waiver of <scope>
     (<reason>)" / "Do I accept the waiver of <scope> for <reason>? I recommend
     <yes/no>: <why>"). The owner's `cepa-plan responde ... "sim: ..."` turns
     the proposal into a waiver (fb-20261014-3); the agent never records a waiver
     on the owner's behalf.

     **Atualizar o Jira (grava no quadro).** If the `id` is a card key and the repo has a board (and
     `--offline` was not passed), transition the card right after, delegating to
     `atlassian-expert` — the only one who speaks to Jira — to
     `defaults.status_map.in_review` with the Implementation Summary, exactly as
     `/board-flow:execute` does. Without it the batch closes the item in the
     queue and leaves the card behind, and the divergence the next reconciliation
     finds was produced by this command. A failed transition does **not** undo
     the `finish`: the work happened. Record the card as pending transition in
     the report.

  f. **Stuck item:** follow the policy chosen in step 2 — stop (default) or go
     on. In both cases, `finish --status blocked --evidence "<the outside
     condition and who resolves it>"` before going on, otherwise the item stays
     `in_progress` forever and blocks the next batch. Don't ask anything now:
     the user already answered that at the start.

     **Atualizar o Jira (grava no quadro), on block.** An item that is a card and
     closed `blocked`, or went back to `pending`, with a board and without
     `--offline`: delegate to `atlassian-expert` a comment on the card with the
     reason from the evidence, the gate verdicts and the branch where the commits
     stayed. If `defaults.status_map.blocked` is declared, move the card to it;
     without that column, the card stays in `defaults.status_map.in_progress`,
     where the reservation put it. Never leave it in `to_do`: the board would say
     no one touched a card that has finished code.

     Along with it, record `--pergunta "<the closed question that unblocks the
     item, with your recommendation>"`, and do the same when opening a
     `--human-pending`. The question is shown to the owner, so write it in pt-BR.
     E.g.: `--pergunta "Fecho o card como 'medir depois do go-live' ou movo a
     medição para o checklist do primeiro deploy? Recomendo o checklist: a
     pergunta sobrevive sem travar a fila"` (Do I close the card as "measure
     after go-live" or move the measurement to the first-deploy checklist? I
     recommend the checklist: the question survives without blocking the queue).
     It is what `cepa-until decidir` shows the owner at the end of the night, in
     a fixed menu where **yes = the item goes back to the queue with this
     answer** and **no = it stays as it is**: write the question so that "yes"
     means that. Up to 25 words, without a branch name, test class name or file
     name (that stays in the evidence, which the owner opens with `[e]`). Without
     a question, the terminal asks the default one ("destravo o item e devolvo
     para a fila?" — do I unblock the item and return it to the queue?) and the
     owner decides without the context only you have. Their answer comes back
     through the item's evidence (`cepa-plan responde`), and the next run reads
     it there.

### 4. Terminal outcome — no item leaves the batch without a name

The batch does not end while a touched item has no named outcome. Every item you
touched ends in exactly one of these:

| Outcome | Means |
|---|---|
| `DONE` | closed, with both gates (plus `validation-lead`, in the topology that has it) and the evidence recorded |
| `BLOCKED` | stuck on an outside condition — name the condition and who resolves it |
| `DEFERRED` | deferred on purpose — name what needs to be true to resume |
| `DROPPED` | will not be done — name why |
| `ERROR` | the run itself failed (infra, permission) — name the failure |
| `SKIPPED` | the item stopped being reservable since the batch was built — say which of the cases |

"In progress", "almost there", "waiting for the build" and silence are **not**
outcomes. They are the absence of
a decision dressed up as status, and that is how an item comes back the next
week without anyone knowing what happened to it. If you can't name it, the
honest outcome is `BLOCKED` with the reason "outcome undetermined: <what you
don't know>".

### 5. Report

A single report, in the `plain-report` format, written in Brazilian Portuguese
(pt-BR). Its contents:

- **Queue drained:** `<nome>` — `<path>`
- **Items attempted:** N, each with its terminal outcome. The count of items
  attempted HAS to match the count of named outcomes; if it doesn't, the batch
  has not ended.
- **Closed:** list with the gate verdict of each one.
- **Stuck / skipped:** with the reason.
- **Deferred:** every item that left the batch without running, with the reason
  (open human route, live session on it, cascade). None? Say "nenhum adiado"
  (none deferred). This block is what keeps deferral from turning into
  forgetting — the item did not stop the queue, so the report is the only place
  where it shows up.
- **Pendente com você** (pending with you): every open `human_pending` route this
  run found or opened, verbatim — including those of the items deferred because
  of them. None? Say "nada a validar à mão" (nothing to validate by hand) —
  silence here is the ambiguity the field exists to kill.
- **Board:** in two lines, one per direction. **Trazer status do Jira (grava no plano)**: what
  step 0 changed in the queue, and the board's cards with no position in it. **Atualizar o Jira (grava no quadro)**:
  the cards transitioned by this run (In Progress, In Review and stuck ones
  commented), and the ones left pending transition. Without a board, one line saying the queue status is
  self-reported.
- **Where the batch stopped and what is left:** the `stop` of the next `queue` and
  how many pending items remain.
- **What now:** `/common:next` for the next step, or this command again if the
  stop was `teto`.

## Constraints

- **Default `--max 3`.** Each item is the whole flow plus two gates; high values
  risk an expensive run nobody follows.
- **Only one thing still stops the batch: an unmet dependency** (`bloqueado`)
  — you don't push work that depends on what has not closed.
- **An open `human_pending` DEFERS the item; it does not stop the batch.** Owner
  decision on 2026-08-28, revisiting the one of 08-25. Whatever depends on the
  deferred item is deferred along with it, in cascade, and every open route is
  collected in the final report.
- **`blocked` from a previous run DEFERS the item; it does not stop the batch.**
  Owner decision on 2026-08-30, by the same reasoning one step further: the
  stuck item is not re-run (it would be the same block), but locking the queue
  behind it in an unattended window costs the whole window. Inheritance from
  `/board-flow:drain` deliberately revisited — there the order comes from the
  board, here it comes from the queue.
- **Deferring never rewrites the order of `queue.yaml`.** Deferring is execution;
  reordering belongs to `/common:queue`. A runner that touches the order is what
  the queue exists to prevent.
- **An orphan reservation is recovered, a live reservation is respected.**
  Liveness is the one from `_wtlib` (live pid on the same host, 24h horizon), the
  same as the worktree system's — two copies of the rule drift apart.
- **Reserve before running, item by item.** Without `start`, the item is not
  worked on.
- **A turn that ends with a build in the background is an item with no outcome.**
  Inside `cepa-until` each item is a `claude -p` that dies at the end of the turn:
  there is no "when it goes green I'll come back". Await and collect in the same
  turn, or name the outcome before stopping.
- **Marking is mechanical** (`cepa-plan start` / `finish`). Editing the YAML by
  hand bypasses all the refusals.
- **The order never comes from the board.** Reconciling is reading each item's
  STATE; the position remains the one `/common:queue` recorded. Taking the order
  from the board rank is `/board-flow:drain`, and it is what this command exists
  to replace.
- **Refuses a `parallel-waves` plan** — waves are run by `/maestro:run`.
- **Does not write the queue.** An item missing from the queue belongs to
  `/common:queue`; inventing a position and a `why` here would forge exactly the
  decision the document keeps.
- **Needs no tracker.** Without `board-flow.yaml`, the queue is the only truth.
  With a board, moving the card of every item that is a card is mandatory
  (steps 3.a, 3.e and 3.f), always through `atlassian-expert`.
