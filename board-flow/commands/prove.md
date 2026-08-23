---
description: Prove one Jira card that is already in Review. Delegates to the topology's proof-reviewer, which interrogates the card's diff (base_commit..HEAD) and proves every changed line of behavior is load-bearing at the external surface — external coverage of the diff, diff-scoped mutation against the integration tests, adversarial input against the touched endpoints, and (for bugs) regression-red-at-base. Then applies the verdict to the card: PROVEN advances, UNPROVEN sends back, NEEDS-HUMAN stays for you. Use to clear the Review column without losing rigor.
argument-hint: <jira-key> [--no-scope]
interaction: routine
---

# /board-flow:prove

## Purpose

Automate the *Review* gate without lowering the bar. A card reached Review
having passed build + security + the `completion-auditor` (criterion-driven).
This command runs the **change-driven** proof: `proof-reviewer` interrogates the
whole diff and proves each changed line is observable at the external surface.
The verdict drives the Jira transition — so PROVEN cards leave your queue
automatically and UNPROVEN cards bounce back with the evidence, leaving only
genuinely ambiguous cards (NEEDS-HUMAN) for you.

This is the **outbound** counterpart to the `completion-auditor`'s inbound gate.
Different lens (change-driven, not criterion-driven), different position (out of
Review, not into it). They compose; they do not overlap.

**Requires** a topology that ships a `proof-reviewer` subagent (currently
`build-hex`). If the active topology has none, this command aborts with a
clear error.

## Variables

- `$ARGUMENTS` — the Jira issue key (e.g., `WEGO-1234`).
- `--no-scope` — suppress the out-of-scope warning (step 1). The named card is proved regardless; this just silences the heads-up.

## Instructions

You are the orchestrator. Drive a single card through the proof gate and apply
the verdict. Apply `defense-in-depth`, `evidence-over-assumption`,
`scope-discipline`. You do NOT decide the verdict — `proof-reviewer` does, from
evidence. You only route the Jira transition off its verdict.

Apply `default-yes`: este comando roda quase sempre DENTRO de um run maior
(`/board-flow:drain`, `/board-flow:prove-drain`, `/common:session`), e uma
pergunta feita aqui chega ao usuário no meio da fila — o ponto mais caro para
interromper, porque responder exige recarregar o contexto inteiro da lista.
Achado reversível, ou que só registra algo, com recomendação clara: execute e
registre para o relatório de quem te chamou. Pergunta só para o irreversível, e
ela sobe para o relatório final do run, nunca para o meio dele.

## Workflow

### 0. Resolve topology prefix

Read `board-flow.yaml` at project root (else legacy `.claude/board-flow.lifecycle.yaml`).
Extract `default_topology`. Prefix the proof delegation: `<default_topology>:proof-reviewer`.

Check the topology ships `proof-reviewer`. If not, abort: "Topology
`<default_topology>` doesn't ship `proof-reviewer`. The change-driven proof gate
is currently implemented for `build-hex` (Maven/JaCoCo/PIT). Switch topologies
or build a `proof-reviewer` for `<default_topology>` (JS would use Stryker for
the mutation level)."

`atlassian-expert` is always bare; write delegations include `Topology:
<default_topology>` as the first line.

### 1. Fetch card details

Detect a `--no-scope` flag in `$ARGUMENTS`; the remaining token is the key. Delegate to `atlassian-expert` (the `Command:` line asks it to also report scope membership — a guard, not a filter; add `Scope: none` only if `--no-scope` was passed):

> Command: prove
> <Scope: none — only if --no-scope was passed>
>
> Fetch Jira issue $ARGUMENTS — summary, description, acceptance criteria,
> **issue type**, status, and the **full text of the most recent Implementation
> Summary comment** (it carries the head commit SHA and the touched-files list).
> Reply verbatim, and include the one-line scope verdict (`scope: in` / `scope: OUT (...)` / `scope: n/a`).

If the card doesn't exist / no access → abort with a clear error.

**Out-of-scope warning (warn, don't block).** If `atlassian-expert` reports `scope: OUT` and `--no-scope` was not passed, print a heads-up — "⚠ `$ARGUMENTS` is outside the configured scope (`<effective fragment>`); proving it anyway because you named it. Pass `--no-scope` to silence." — then continue. Never abort on scope for an explicitly-named card.

### 2. Precondition: card must be in Review

Read `defaults.status_map.in_review` from `board-flow.yaml` (this MUST match the
board's literal status name — e.g. `"Review"` or `"In Review"`).

If the card's status is NOT `in_review`, do not proceed. Report:
"$ARGUMENTS is in `<status>`, not `<in_review>`. /board-flow:prove only runs on
cards in Review — it proves work that's already been built and is awaiting
review." Stop.

### 3. Run the proof gate

Delegate to `<default_topology>:proof-reviewer`:

> Prove Jira card $ARGUMENTS, which is in Review.
>
> - Issue type: `<type>`.
> - Acceptance criteria: `<verbatim>`.
> - Implementation Summary (head commit + touched files): `<verbatim comment>`.
> - Baseline: read `.claude/cards/$ARGUMENTS.yaml` for `base_commit`.
>
> Reconstruct the diff (`base_commit..HEAD` ∩ touched files), run L2 (external
> coverage of the diff), L3 (diff-scoped mutation against the IT suite), L4
> (adversarial input on the touched endpoints), and — if this is a Bug — the
> regression-red-at-base check. Operate ONLY in a throwaway git worktree; never
> touch the primary working tree or edit any code. Write
> `docs/proof/$ARGUMENTS.yaml` (versionado; `.claude/` é gitignored e some
> com a worktree) and return your verdict with evidence.

Wait for the verdict. Then read `docs/proof/$ARGUMENTS.yaml` yourself and
**cross-check it — do not trust the `verdict` field blindly.** Re-derive the
verdict from the levels: if any level is `assumed`/`skipped`/`gap`/`survived`/
`green-at-base`, the only valid verdicts are UNPROVEN or NEEDS-HUMAN — never
PROVEN. If the artifact says `verdict: proven` but a level contradicts it (a
self-granted waiver the agent must never write), treat the card as
**NEEDS-HUMAN**, act on that, and flag the inconsistency in your report. The
verdict field is not authoritative when it disagrees with its own levels — the
levels are.

### 3b. UI gate — when the diff touches a declared UI surface

If the repo has `docs/ui-proof.yaml` (or, in a repo that hasn't moved it yet,
`.claude/ui-proof.yaml`) AND the card's diff (touched files
from the Implementation Summary) matches the `covers:` globs of at least one
flow in it, the backend verdict alone is not enough — also delegate to
`common:ui-proof-reviewer` (same diff context, slug = the card key; it writes
`docs/proof/ui-<KEY>.yaml`, alongside the backend verdict). Combine mechanically: **PROVEN requires BOTH
verdicts PROVEN**; any UNPROVEN → UNPROVEN; otherwise any NEEDS-HUMAN →
NEEDS-HUMAN. Name which gate produced each part of the combined verdict in
your report and in the Jira comment. If the manifest exists but no flow
covers the diff, skip this step and say so in one line (no UI surface
declared for these files — a manifest gap to flag, not a block).

### 4. Apply the verdict

#### PROVEN

Read `defaults.status_map.done` from `board-flow.yaml` (optional).

- **If `done` is set:** build a Proof Summary and delegate to `atlassian-expert`:

  > Topology: `<default_topology>`.
  >
  > Transition $ARGUMENTS to status `<defaults.status_map.done>` with the Proof
  > Summary below. Post the summary as a comment first, then transition.
  >
  > ```markdown
  > ## Proof summary — change-driven gate PROVEN
  >
  > **Diff proven:** `<base_commit>..<head>` (changed classes: <list>)
  >
  > - **L2 external coverage:** every changed line exercised by an integration test. `<run line>`
  > - **L3 diff mutation:** 0 surviving mutants on changed lines under the IT suite. `<run line>`
  > - **L4 adversarial input:** no unasserted external behavior. `<run line>`
  > <- for Bug: **Regression:** red at base_commit, green at HEAD. `<run line>`>
  >
  > Artifact: `docs/proof/<KEY>.yaml`. Auto-advanced — change is load-bearing at the external surface.
  > ```

- **If `done` is NOT set:** do not transition. Post the Proof Summary as a
  comment with a ✅ and leave the card in Review (triage-only mode — the human
  makes the final move, but now with the proof attached).

#### UNPROVEN

The change is provably not load-bearing somewhere. Send it back. Read
`defaults.status_map.in_progress`. Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Transition $ARGUMENTS back to `<defaults.status_map.in_progress>` with the
> comment below. Post the comment first, then transition.
>
> ```markdown
> ## Proof gate — UNPROVEN, returning for rework
>
> The change is not demonstrably reflected at the external surface:
>
> - <for each failure: `file:line` — which level caught it — the external test that must exist to close it>
>
> **Reason:** <the single concrete gap, in one sentence — `file:line` plus the external test that would close it>
>
> Artifact: `docs/proof/<KEY>.yaml`. This is the recurring last-mile gap: the behavior exists in the code but no test proves it from outside.
> ```

The `Reason:` field is not decoration: `bounce-reason-gate` blocks the comment
without it. A card that comes back carrying only "not proven" forces the next
session to re-derive the WHY from the diff — the reason costs one sentence to
write and an archaeology to reconstruct.

**And name the real condition.** "Attention" is not a state. When a card stops
for something other than rework, say which: **Blocked** (waiting on X),
**Deferred** (until Y), **Dropped** (because Z) — each with its reason. A status
that only signals "someone look at this" hides the one fact the next person
needs.

#### NEEDS-HUMAN

Deterministic levels passed, but L4 surfaced something or a level couldn't run.
Leave the card in Review — this is exactly the card that needs your judgment.

If you put the decision to the user interactively (an `AskUserQuestion` rather
than just the Jira comment), the question, the option labels, and the option
descriptions are last-hop user-facing text — apply `conversational-response`'s
"translate jargon at the human boundary" to all of them (plain headline,
protocol code in parens; never a bare `L4` / `waiver` / `altitude` in a label).

Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Add a comment to $ARGUMENTS (do NOT transition):
>
> ```markdown
> ## Proof gate — NEEDS-HUMAN
>
> Deterministic levels (coverage + mutation) passed. Escalating for human review because:
>
> - <L4 findings: input + observed response, each unasserted>
> - <and/or: level(s) that couldn't run and why — e.g. "PIT not configured → mutation assumed">
>
> Artifact: `docs/proof/<KEY>.yaml`. Left in Review for you to adjudicate.
> ```

## Report

Write for a human, not for the protocol — apply `conversational-response`'s
"translate jargon at the human boundary." Lead with the plain-language outcome
and what you need from them; keep the protocol codes as parenthetical anchors,
never as the headline.

- **What happened, in one plain line** — e.g. "Proved the fix is load-bearing
  except for one thing I can't measure" — then the card link, type, and where it
  ended up (advanced / returned / left in Review).
- **The evidence as the questions a human actually asks** — one line per level,
  phrased *question → plain answer (code in parens)*:
  - "Do the tests catch a broken fix? **Yes** — every changed line, broken,
    turned a test red *(L3 mutation: 0 survived)*."
  - "Does the coverage reach the endpoint? **Can't measure** — no coverage tool
    in the project, not a fault of this card *(L2: assumed)*."
- **If UNPROVEN:** in plain words, what isn't proven and the one test that would
  close it.
- **If NEEDS-HUMAN:** state the single decision you need, plainly (e.g. "is the
  contract test good enough as the external proof, or should we add the missing
  coverage tool first?"), plus anything you're obligated to flag (e.g. an
  artifact whose `verdict` disagreed with its levels).
- Close with the concrete options and one "how do you want to proceed?"

Then, **only when the card advanced (PROVEN)**, add **"And now?"** — proving a
card is exactly the moment the user is left holding "so is it done, or do I
still have to touch it?". On UNPROVEN or NEEDS-HUMAN the next step is the card
itself, and this section would compete with it; skip it there.

- **Left for you:** the card's **Human validation route** verbatim, from the
  Implementation Summary. A proof gate closes *load-bearing at the surface it
  claims* — it does not close *a human looked at it*, and the two get conflated
  precisely here. If the route is the explicit null ("not applicable — internal
  substrate"), say so: "nothing to check by hand" is the answer, not silence.
- **Next in the plan:** read `<programs>/<project_key>/plan.yaml` (schema
  `common/plan-schema.yaml`, `mode: single-track`) and name the next `pending`
  item not `blocked_by` an unfinished one — key, title, and its `why`. Mark the
  proven card `done` there, carrying its Human validation route into
  `human_pending`. No plan file? Say so and offer `/board-flow:triage`.

  `<programs>` = `<main-root>/.claude/programs`, where `<main-root>` is the
  parent of `git rev-parse --git-common-dir` with the trailing `/.git` removed
  — the MAIN clone when you are in a linked worktree. Resolving the plan
  against the current tree instead loses it (`docs/execution-plan.md`,
  "Where the file lives").

## Constraints

- **Runs only on cards in Review.** It proves built work; it does not build.
- **`proof-reviewer` never edits code and never touches the primary working
  tree** — it works in a throwaway worktree. Verify the verdict against the
  written artifact before transitioning.
- **You do not override the verdict.** No "looks fine, advance anyway." The
  whole point is that the transition is evidence-driven.
- `atlassian-expert` is the only Jira write path.
- Don't auto-advance PROVEN unless `defaults.status_map.done` is set — absent it,
  triage-only (comment + leave in Review).
