---
description: Run the canonical design flow on a feature — explore (flows ∥ visual), systematize against the design system, prototype via Gamma/Canva, critique, and assemble a build-ready design spec. Each step delegates to the design team's workers. For single-step / board-driven work, delegate to design-lead directly or use /board-flow:advance.
argument-hint: <feature description or docs/design/<slug>/ path>
---

# /design:explore-critique-spec

## Purpose

Run the full design loop on a feature that needs all of it: interaction
flows, a visual direction, design-system reconciliation, a shareable
prototype, an adversarial critique, and a build-ready spec engineering can
implement against. For a feature that only needs one phase (just flows, or
just a critique of an existing design), delegate to `design-lead` directly
instead of running this command.

## Variables

- `$ARGUMENTS` — the feature description (or a path to an existing
  `docs/design/<slug>/` folder), passed verbatim into the design-lead
  delegation.

## Instructions

You are the orchestrator. Do not produce design artifacts yourself. Drive
the design loop through `design-lead`, synthesize, and report back to the
user with the verdict and artifact paths.

Apply `till-done` at every step: a REVISE/BLOCK critique routes back to the
owning worker — don't wrap with caveats and call it done. Apply
`name-the-disagreement` when the visual direction and the design system
pull against each other.

## Workflow

Drive `design-lead` through the phases. The lead delegates to its workers;
you do not address the workers directly.

### 1. Explore

Delegate to `design-lead`:

> Design the following feature: **$ARGUMENTS**
>
> Start the Explore phase: run `ux-architect` and `visual-designer` in
> parallel to draft the flows (with full state sets) and the visual
> direction under `docs/design/<slug>/`. Report the slug, the two artifact
> paths, and any open question that blocks systematizing.

### 2. Systematize

Delegate to `design-lead`:

> Run the Systematize phase on `docs/design/<slug>/`: have
> `design-system-keeper` reconcile the visual spec against the existing
> design system — every choice REUSE / ADD (justified) / REJECT. Report
> `system.md` plus any new tokens that need to be admitted.

### 3. Prototype

Delegate to `design-lead`:

> Run the Prototype phase: have `prototyper` generate a shareable Gamma/Canva
> prototype from the specs and record it in `docs/design/<slug>/prototype.md`.
> If Gamma/Canva is unavailable, accept the written walkthrough fallback —
> don't block the flow.

### 4. Critique

Delegate to `design-lead`:

> Run the Critique phase: have `design-critic` adversarially review the
> design (heuristics, flow completeness, system consistency, accessibility,
> brief fit) and return SHIP / REVISE / BLOCK with located findings in
> `docs/design/reviews/<slug>.md`.
>
> If the verdict is REVISE or BLOCK, route the findings back to the owning
> worker and re-critique. Loop until SHIP — do not proceed on an unresolved
> BLOCKER.

### 5. Spec

Once the critique is SHIP, delegate to `design-lead`:

> Assemble the build-ready spec at `docs/design/<slug>/design-spec.md`: a
> single entry point that references flows, visual, system (with the token
> list), the prototype link, and the passing critique. This is the artifact
> engineering builds from.

## Report

A single concise message back to the user:

- **Feature:** `<slug>`
- **Artifacts:** `docs/design/<slug>/` (flows, visual, system, prototype, design-spec)
- **Prototype:** the Gamma/Canva link (or "written walkthrough — tool unavailable")
- **Verdict:** the design-critic's final verdict
- **Handoff:** "`design-spec.md` is ready for engineering" — or the specific blocker if it never reached SHIP

If the loop never reached SHIP, surface that as the headline — it's the
most important signal. Name the unresolved BLOCKER and the next step.

## Constraints

- Don't produce design artifacts yourself. The orchestrator delegates only.
- If `design-lead` returns asking for clarification, answer from the
  conversation context — bounce back to the user only when the ambiguity is
  genuinely unresolvable from what they said.
- Keep the user-facing report short. The workers' detailed artifacts stay on
  disk; the user gets the synthesis and the links.
