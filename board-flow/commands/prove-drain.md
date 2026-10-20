---
description: Bulk-prove the Review column. Iterates cards in `defaults.status_map.in_review` (priority order) and runs the equivalent of /board-flow:prove on each — change-driven proof, then routes the verdict. Unlike /board-flow:drain, it does NOT stop on a failed card: UNPROVEN bounces back and the drain continues, because clearing the queue is the whole point. PROVEN auto-advances (if a done status is configured), NEEDS-HUMAN stays for you. Use to triage a backlogged Review column.
argument-hint: [--max N] [--scope "<jql>"] [--no-scope]
interaction: routine
---

# /board-flow:prove-drain

## Purpose

Drain the *Review* column through the change-driven proof gate. The Review pile
grows because manual review is the bottleneck; this iterates the column and lets
`proof-reviewer`'s evidence triage it — PROVEN out, UNPROVEN back, NEEDS-HUMAN
held for the human. What's left in Review afterward is precisely the set that
actually needs a person.

**Heavy operation:** each card runs a full proof (integration build + JaCoCo +
PIT, in a throwaway worktree). Use `--max` to cap per run. Default `--max 5`.

## Variables

- `$ARGUMENTS` — optionally `--max N`. Default max = 5.
- `--scope "<jql>"` — a raw JQL fragment that narrows the drain to a slice of the Review column for this run only, overriding any configured scope.
- `--no-scope` — ignore configured scope entirely; sweep the whole Review column.

**Scope** lets you triage a slice of Review (e.g. one team's cards, or `labels = needs-review`) instead of the entire column. By default the drain applies the effective scope resolved from `board-flow.yaml` (`defaults.scope` / `scope_overrides.prove_drain` / the active topology's `scope`); the two flags above override that for one run. You don't resolve the precedence yourself — pass the command name and any flag to `atlassian-expert`, which resolves and reports the effective fragment.

## Instructions

You are the orchestrator. Iterate the Review column, prove each card, route each
verdict. Apply `scope-discipline` (don't exceed `--max`). **Do not stop on
UNPROVEN** — sending a card back is forward progress, not a blocker (this is the
deliberate difference from `/board-flow:drain`).

## Workflow

### 1. Parse arguments & resolve config

- Max cards: parse `--max N`. Default 5.
- Scope flags: detect `--no-scope` and `--scope "<jql>"` (mutually exclusive; if both appear, abort with "pass either --scope or --no-scope, not both"). Build the **scope directive**: `--no-scope` → `Scope: none`; `--scope "<jql>"` → `Scope: <jql>`; neither → omit the line (atlassian-expert resolves the effective scope from config).
- **The run's claim id**: generate one, now, as described in
  **Card reservation**. It identifies THIS run on every card
  it touches.
- Read `default_topology` and `defaults.status_map.in_review` from
  `board-flow.yaml`. Confirm the topology ships `proof-reviewer` (else abort as in
  `/board-flow:prove`).

### 2. List cards in Review

Delegate to `atlassian-expert` (the `Command:` line tells it to resolve scope for `prove_drain`; include the scope directive only if a flag was passed):

> Command: prove_drain
> <Scope: ... — only if a flag was passed>
>
> List Jira issues where `status = "<in_review>"` in the project, applying the
> effective prove_drain scope, ordered by priority and rank. Limit to <max>.
> Return key + summary + issue type + priority, plus the effective scope you used.

If 0 cards → "Nothing in Review (scope: <effective scope, or 'none'>)." — call out
the scope so an over-narrow filter isn't mistaken for an empty queue. Stop.

### 3. Confirm with user

```
Found N cards in Review (column "<in_review>", scope: <effective scope, or "none — whole column">):
  WEGO-1234 (Bug, P1) — <summary>
  WEGO-1235 (Story, P2) — <summary>
  ...

Prove these? Each runs the change-driven proof gate (integration coverage +
diff-scoped mutation + adversarial input, in a throwaway worktree).
  · PROVEN     → auto-advances (if a done status is configured)
  · UNPROVEN   → returned to In Progress with the gap (drain CONTINUES)
  · NEEDS-HUMAN→ stays in Review for you

And, at the end, the ones that stop at NEEDS-HUMAN (neither proven nor
returned — the ones that depend on a decision of yours):
  (a) I apply each reason's recommendation and just tell you what I did   ← default
  (b) I hold them all and ask you one by one in the report

Reply yes / no / first-N to prove a subset, and (a) or (b) for the NEEDS-HUMAN.
A bare "yes" counts as yes + (a).
```

Render this screen to the owner in Brazilian Portuguese (pt-BR); a bare "sim"
is the "yes" above.

Wait for confirmation. **This is the ONLY stop of the run** — apply `default-yes`:
fold into this confirmation everything you would ask later. A question in the
middle of the drain costs the user reloading the whole context to answer it.

**The (a)/(b) alternative has to be WRITTEN on the screen above, not implied.**
Step 6 only skips the second round of questions "if the user already answered
that policy in the step 3 confirmation" — and a screen that shows the card count
and asks "can I go?" collects no answer at all about NEEDS-HUMAN. A "yes" to it
doesn't close that conditional, step 6 asks everything again at the end, and the
run that announced itself as the ONLY stop charges two. That's how it was until
22/08/2026. A dry "yes" still counts: it's (a), the default.

If the run came from `/common:session`, these answers were already collected at
the start — don't ask again.

### 4. Iterate

For each confirmed card, in priority order:

  a. **Reserve the card first** — re-read status +
     comments and publish the claim, per **Card reservation** below. If the card
     was skipped (it left the column or is reserved by another session), record
     `SKIPPED` and go to the next card WITHOUT running any proof.
  b. Run the equivalent of `/board-flow:prove <card-key>` (proof + verdict-driven
     transition), reusing the card content from the claim read in (a) — skip
     prove's step 1 fetch.
  c. Capture the verdict and the action taken.
  d. **Continue regardless of verdict** — UNPROVEN does not stop the drain.
     Every card returned on UNPROVEN carries its own `**Reason:**` — the
     concrete gap for THAT card, not the batch's. `bounce-reason-gate` blocks
     the comment without it, and a shared reason pasted across N cards is the
     failure it exists to prevent: it reads as answered while telling the next
     session nothing about any individual card. Where a card stops for
     something other than rework, name the real condition — **Blocked**
     (waiting on X) / **Deferred** (until Y) / **Dropped** (because Z).
     "Attention" is not a state.
  e. If `proof-reviewer` returns a hard environmental failure for a card (can't
     create a worktree, build infra down), record it as `ERROR` for that card
     and continue to the next — one broken card shouldn't sink the batch. A
     card that ends in `ERROR` got no verdict, so **publish the claim
     release** (`🔓`) before moving on.
  f. Before recording any card's outcome, apply **Coupled closure** below. The
     batch is a scheduling convenience; it is never the unit of evidence.

### 5. Final report

```
Proved from Review (max <N>, scope: <effective scope, or "none">):
  PROVEN → advanced:    <count>   (keys)
  UNPROVEN → returned:  <count>   (keys + one-line gap each)
  NEEDS-HUMAN → held:   <count>   (keys + what to look at)
  ERROR:                <count>   (keys + reason)
  SKIPPED (reserved/moved): <count>   (keys + which session or which status)

Remaining in Review (not attempted this run): <count>
```

The table above is the at-a-glance count. For each card in the NEEDS-HUMAN set —
the only one that costs the user attention — expand it in plain language (apply
`conversational-response`'s "translate jargon at the human boundary"): the one
decision you need and why, not a wall of `assumed`/`L2`/`altitude` the user has
to decode. If you put any held card's decision to the user interactively (an
`AskUserQuestion`), the same rule covers the question, every option label, and
every option description — never a bare `L4` / `waiver` / `altitude` in a label.
Suggest re-running for the next batch if cards remain, and point the user at the
NEEDS-HUMAN set as their actual review queue.

**When the NEEDS-HUMAN count is 1 or more, do NOT send the user to run another
command — do the grouping here, in the same report.** Apply the logic of
`/board-flow:decide` to the set THIS run just produced: classify each card into
the seven reasons of `docs/needs-human-motivos.md`, take off the plate what is
nobody's decision (Docker down, missing tool — resolve or record it, don't ask),
group the rest by reason and ask **one closed question per group, with a
recommendation**, accepting a batch answer ("1 yes, 2 no"; in pt-BR, "1 sim,
2 não").

**If the user answered (a) in step 3 — or answered just "yes", which is (a) —
don't ask anything here.** Apply each reason's recommendation and report what
was done, card by card, with the reason alongside. The closed per-group
questions above are path (b), and only that.

Why here and not in another command: the run that produced the cards is the run
that knows which they are and why. Ending with "now run `/board-flow:decide`"
hands the user a second cycle of reading and deciding over the same material
— the cost `decide` existed to remove, reintroduced at the point of delivery.
`/board-flow:decide` still exists for when the Review column piled up outside a
drain (cards from other sessions, from another day).

## Card reservation — the queue is the contested resource

The list built in step 2 is a **snapshot**, not a reservation. Between the
listing and the moment this run reaches card N, another session (another
worktree, another machine, the same user in two windows) may have taken the same
card — and the cost isn't a file conflict, it's the whole job redone. The shared
resource is the board column, so the reservation is made on the board.

**Claim id.** Generate ONE per run, in step 1, and use the same one for every card:

```bash
echo "$(basename "$PWD")-$(python3 -c 'import uuid;print(uuid.uuid4().hex[:8])')"
```

**Before touching each card** (it's the first step of 4, before any build,
worktree or delegation), delegate to `atlassian-expert`:

> Read card `<KEY>`: current status, assignee, the comments from the last
> 90 minutes, and also summary, description, acceptance criteria, **issue type**
> and the **full text of the latest Implementation Summary**. Return it without changing anything.

That read already brings everything step 1 of `/board-flow:prove` would ask for.
In 4b, hand that content to the proof instead of fetching the card again:
measured on 13/09/2026, re-reading a card the session had just read was the
source of part of the 277 avoidable re-reads.

And decide, mechanically:

- **Status ≠ `<the run's column>`** → the card left the queue since the listing.
  **Skip** it, record `SKIPPED (left the column: now in <status>)` and move on to
  the next.
- **There is a claim comment from ANOTHER claim id, less than 90 minutes old and
  without the `🔓` release** → another session is on it right now. **Skip** it,
  record `SKIPPED (reserved by <claim-id> at <hh:mm>)` and move on.
- **Otherwise** → reserve it, publishing the comment via `atlassian-expert`. The
  comment body is posted verbatim, in pt-BR (`atlassian-expert` looks for the
  `🔒 claim:` / `🔓 claim` prefixes):

  > `🔒 claim: <claim-id> — <nome do comando> em andamento desde <timestamp>.`
  > `Outra sessão deve pular este card. A reserva expira em 90 minutos.`

  ("claim: <claim-id> — <command name> in progress since <timestamp>. Another
  session must skip this card. The reservation expires in 90 minutes.")

  Only after that comment exists may the card be worked.

**Release.** The card's verdict ends the reservation — the result comment
(proof, bounce with `**Reason:**`, implementation summary) is already the signal
that the reservation is over. When the card ends WITHOUT a verdict (`ERROR`,
interruption, run abort), publish the explicit release (verbatim, pt-BR),
otherwise the card stays untouchable for 90 min:

> `🔓 claim <claim-id> liberado — <motivo>.`

("claim <claim-id> released — <reason>.")

**Why 90 minutes and not a permanent lock:** a session that dies midway must not
freeze the queue. The window is longer than one card's time (the proof takes
9 to 12 minutes) and shorter than a work shift, so an orphaned reservation
resolves itself without anyone having to unlock anything by hand.

**Skipped cards don't consume `--max`** — no work ran on them. They show up in
the final report with the reason, because "vanished from the list without
explanation" is exactly the hole this mechanism exists to close.

## Coupled closure — the batch is not the unit of evidence

Draining N cards in one run creates a standing temptation: prove once, close
many. The saving is real and the reasoning is almost never valid. Two cards that
merely rode the same commit are not the same change.

**Closing cards together is allowed only when both hold:**

1. **Causally coupled** — they are one change split across cards (the same hunk
   satisfies them; fixing one necessarily fixes the other), not merely adjacent,
   same-file, same-sprint, or same-author.
2. **Shared validation boundary** — a single external surface exercises all of
   them, so one perturbation going RED demonstrably covers every card in the set.

**Forbidden outright — no matter how coupled they look:** cards carrying
independent risk, or independent debt. A shared proof cannot speak for a risk
only one of them introduces.

**Even when both conditions hold, every card gets its own line:**

- its **evidence** — the specific run line / perturbation that covers THAT card;
- its **reason** — the `**Reason:**` required by `bounce-reason-gate`, written
  for that card, never pasted across the set;
- its **debt impact** — the `New debt introduced` value for that card, and (per
  `summary-nulls-gate`) the `Revisit trigger` when that value isn't none/unknown.

A batch-level "all proven, same fix" is not evidence — it is the absence of
evidence formatted to look like a conclusion. When you cannot write the per-card
line, the card is not closed: route it individually.

**Telemetry, not enforcement (this wave).** No hook checks this yet. If a batch
without per-card evidence appears in practice, record it as a counted occurrence
so the next wave knows whether prose was enough. Discipline first; a gate only
once the failure is observed.

## Constraints

- Default `--max 5`. Each card is an expensive proof; raise deliberately.
- **Coupled closure or individual closure — never batch-by-convenience.** See the
  section above; per-card evidence, reason, and debt impact are required even for
  a legitimately coupled set.
- **No stop-on-failure.** UNPROVEN and NEEDS-HUMAN are normal outcomes; the drain
  processes the whole confirmed batch. (Contrast `/board-flow:drain`, which stops
  on BLOCKED.)
- **Reserve before proving, card by card.** The listing is a snapshot; the
  reservation on the board is what keeps two sessions from proving the same card.
  Without the claim published, the card is not worked.
- Always confirm before starting. Don't prove N cards without buy-in. But
  confirm **only once**: the step 3 confirmation also carries the policy for
  whatever stops at NEEDS-HUMAN (`default-yes`).
- Per-card proof is FULL — don't shortcut to save time across cards.
- **Scope narrows, never widens.** It only subtracts cards from Review; `--no-scope` returns the full sweep. Show the effective scope on the confirmation screen, and surface a rejected scope JQL fragment as a config/flag error — not an empty Review queue.
- `atlassian-expert` is the only Jira write path.
