---
description: Run the canonical marketing flow on a content request — distill the brief (audience, offer, canonical numbers, brand rules), write every piece in parallel, and run brand-style and factual review in parallel until both PASS (max 2 revise rounds, then BLOCKED with the disagreement named). For single-step / board-driven work, delegate to content-lead directly or use /board-flow:advance.
argument-hint: <content request or docs/marketing/<slug>/ path>
interaction: routine
---

# /marketing:brief-write-review

## Purpose

Run the full content-production loop on a request that needs all of it: a
shared, sourced brief; every piece written from it in parallel; an
adversarial brand/style review and an adversarial factual review; and a
revise loop bounded to 2 rounds before it stops and names the disagreement.
For a single already-briefed piece, delegate to `content-lead` directly
instead of running this command.

## Variables

- `$ARGUMENTS` — the content request (or a path to an existing
  `docs/marketing/<slug>/` folder), passed verbatim into the content-lead
  delegation.

## Instructions

You are the orchestrator. Do not produce content artifacts yourself. Drive
the loop through `content-lead`, synthesize, and report back to the user
with the verdict and artifact paths.

Apply `till-done` at every step: a REVISE from either gate routes back to
the owning worker — don't wrap with caveats and call it done. Apply
`name-the-disagreement` when `brand-style-critic` and `fact-checker` pull
against each other, or when the loop hits 2 REVISE rounds without a PASS.

## Workflow

Drive `content-lead` through the phases. The lead delegates to its workers;
you do not address the workers directly.

### 1. Brief

Delegate to `content-lead`:

> Produce content for the following request: **$ARGUMENTS**
>
> Run the Strategize phase: have `content-strategist` distill the request
> into `docs/marketing/<slug>/BRIEF.md` — audience, offer, the
> canonical-numbers table (every figure sourced), brand/style rules (folding
> in `docs/marketing/brand-rules.yaml` if it exists and saying so if it
> doesn't), and the piece list. Report the slug, the brief path, and any
> open question that blocks writing.

### 2. Write

Delegate to `content-lead`:

> Run the Write phase: have `copywriter` write every piece in the brief's
> piece list, one invocation per piece, in parallel, each write-locked to
> its own file under `docs/marketing/<slug>/pecas/`. No copywriter invents a
> number outside `BRIEF.md`'s canonical-numbers table — a gap routes back to
> `content-strategist`, not a guess. Report the piece paths.

### 3. Review

Delegate to `content-lead`:

> Run the Review phase: have `brand-style-critic` and `fact-checker` review
> every piece in parallel and each return PASS / REVISE with located
> findings in `docs/marketing/reviews/<slug>-brand.md` and
> `docs/marketing/reviews/<slug>-facts.md`.
>
> If either gate returns REVISE, route the findings back to the owning
> worker (`copywriter` for a wrong number or a style fix; `content-strategist`
> for a genuinely missing brief row) and re-review. This is round N of at
> most 2. If round 2 still doesn't reach PASS on both gates for every piece,
> stop and report BLOCKED with the specific unresolved finding and which
> gate raised it — don't run a third round silently.

### 4. Delivered

Once both gates PASS every piece, delegate to `content-lead`:

> Assemble the delivery report: list every piece under
> `docs/marketing/<slug>/pecas/` with its brand-style and fact-check
> verdicts. This is what a reviewer or the requester reads to confirm the
> set is ready.

## Report

A single concise message back to the user:

- **Content:** `<slug>`
- **Artifacts:** `docs/marketing/<slug>/` (`BRIEF.md`, `pecas/*.md`, reviews)
- **Verdicts:** brand-style-critic and fact-checker, per piece
- **Delivery:** "pieces are ready" — or the specific unresolved finding and
  which gate raised it, if the loop hit BLOCKED

If the loop never reached PASS on both gates, surface that as the
headline — it's the most important signal. Name the unresolved finding and
the next step (usually: a human call on the disagreement).

## Constraints

- Don't produce content artifacts yourself. The orchestrator delegates only.
- If `content-lead` returns asking for clarification, answer from the
  conversation context — bounce back to the user only when the ambiguity is
  genuinely unresolvable from what they said.
- Keep the user-facing report short. The workers' detailed artifacts stay on
  disk; the user gets the synthesis and the links.
