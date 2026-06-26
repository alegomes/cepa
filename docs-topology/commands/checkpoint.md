---
description: Phase 3 — the owner checkpoint. Walks the owner through the gap-report's WHY-gaps, "expected-or-deviation?" questions, and drifts. Their answers become SOURCED:owner rationale in the gap-report. Where an answer reveals a real defect or security gap, open a tracker card (pairs with board-flow). This is the make-or-break grounding step — no authoring until it's done.
argument-hint: "(none — walks the gap-report's open questions)"
---

# /docs:checkpoint

## Purpose

Ground the WHY. The survey deliberately did not invent rationale — it parked every
un-sourced decision as a question. Here you (orchestrator) walk the owner through
those questions and record the answers, which become the only legitimate source for
rationale that isn't in code/ADR/commit/Jira. **This is why the topology isn't
autonomous.**

## Workflow

### 1. Load the open questions

Read `docs/_survey/gap-report.md` §3 (WHY-gaps), §4 ("expected or deviation?"), and
§5 (drift), plus `docs/_survey/open-questions.md`. If missing, run `/docs:survey`.

### 2. Walk the owner through them — prioritized

Ask the owner, in this order:
1. **Security / correctness gaps first.** Any WHY-gap that hides a risk (an
   unauthenticated endpoint, a tenant bypass, a dead guard) — these may need a card
   before docs even ship.
2. **Drift decisions (§5).** For each: which side is the truth — the code or the
   doc? The losing side gets corrected.
3. **WHY-gaps (§3) and "expected-or-deviation?" (§4).** For each: the rationale, or
   "it's an accident — file it." Capture the owner's actual words; don't smooth a
   non-answer into a rationale.

Ask in small batches; this is a conversation, not a form dump.

### 3. Record answers as SOURCED:owner

Delegate to docs-lead:

> Run the **checkpoint** phase. Append the owner's answers to
> `docs/_survey/gap-report.md` as a "Checkpoint — owner answers" section, each
> tagged `SOURCED: owner`, with its follow-up (becomes doc content / becomes a
> card). Anything the owner did not answer stays an open question — do not
> paraphrase it into a rationale.

### 4. Open cards for the defects (optional — board-flow)

For each answer that revealed a real defect/security/correctness issue, open a
tracker card. If `board-flow` is installed and `board-flow.yaml` exists, use
`/board-flow:capture` (or delegate to `atlassian-expert`) to register each one and
note the key in the gap-report. (The pilot opened 5 cards this way.)

### 5. Report next step

- **Grounded:** <N WHY-gaps now SOURCED:owner>
- **Cards opened:** <keys, if any>
- **Still open:** <gaps the owner deferred>
- **Next:** `/docs:author` — now that the WHYs are grounded.

## Constraints

- **Never invent rationale.** A deferred or unanswered question stays open. Better a
  documented gap than a fabricated reason.
- **Capture the owner's words.** `SOURCED: owner` must reflect what they actually
  said, not your interpretation.
- **Defects become cards, not doc prose.** Documenting a security hole as
  "intended" because it exists is exactly the failure to avoid — if it's a defect,
  card it.
