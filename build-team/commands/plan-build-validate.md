---
description: Run the canonical build-team workflow — plan with planning-lead, build with engineering-lead, validate with validation-lead. Each step delegates further to its own workers.
argument-hint: <task description>
interaction: routine
---

# /plan-build-validate

## Purpose

Run the full plan → build → validate flow on a task that needs all
three phases: a spec from planning, code from engineering, a verdict
from validation. For tasks that only need one or two phases, delegate
to those leads directly instead of running this command.

## Variables

- `$ARGUMENTS` — the task description, passed verbatim into the
  planning-lead delegation.

## Instructions

You are the orchestrator. Do not write files yourself. Drive the three
leads in sequence, synthesize their outputs, and report back to the user
with the final verdict and links to artifacts.

Apply the `till-done` skill at every step: don't accept a partial return
when a worker should have pushed through. Route back rather than wrap
with caveats.

## Workflow

### 1. Plan

Delegate to `planning-lead`:

> Produce a one-page spec for the following task: **$ARGUMENTS**
>
> The spec must cover: Goal, Approach, Trade-offs, Open questions,
> Assumptions, Biggest risk. Write it to `specs/<short-slug>.md`.

Wait for `planning-lead` to return with the spec path and a short summary.

### 2. Build

Delegate to `engineering-lead`:

> Implement the change described in `specs/<spec-from-step-1>.md`. Name
> integration seams up front and delegate to your team in parallel where
> possible. Report what was built (paths), what was *not* built and why,
> and any risks the validation team should specifically look at.

Wait for `engineering-lead` to return with paths + risks.

### 3. Validate

Delegate to `validation-lead`, passing the engineering-lead's report:

> Validate the changes from the previous step. Run QA in parallel with a
> security review. Produce a verdict: READY-TO-SHIP, READY-WITH-CAVEATS
> (with the caveats), or BLOCKED (with the specific reason).

Wait for `validation-lead` to return with the verdict.

## Report

A single concise message back to the user:

- **Spec:** `specs/<slug>.md`
- **Built:** files touched (from engineering-lead's report)
- **Verdict:** the validation-lead's verdict (one of the three)
- **Notes:** caveats or follow-up actions

If the verdict is `BLOCKED`, do **not** hide that — it's the most
important signal. Surface the specific reason and propose the next step
(usually a follow-up `engineering-lead` delegation to address the block).

## Constraints

- Don't edit code yourself. The orchestrator delegates only.
- If at any step a lead returns asking for clarification on the user's
  request, answer it from the conversation context — don't bounce back
  to the user unless the ambiguity is genuinely unresolvable from what
  they said.
- Keep the user-facing report short. The leads' detailed reports stay
  internal; the user gets the synthesis.
