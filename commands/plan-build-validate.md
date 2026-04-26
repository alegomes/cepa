---
description: Run the canonical multi-team workflow — plan with planning-lead, build with engineering-lead, validate with validation-lead. Each step delegates further to its own workers.
argument-hint: <task description>
---

# /plan-build-validate

Run the full plan → build → validate flow for the task: **$ARGUMENTS**

You are the orchestrator. Do not write files yourself. Drive the three leads
in sequence, synthesize their outputs, and report back to the user with
the final verdict and links to the artifacts.

## The flow

### 1. Plan
Delegate to `planning-lead`:
> Produce a one-page spec for the following task: **$ARGUMENTS**
>
> The spec must cover: Goal, Approach, Trade-offs, Open questions,
> Assumptions, Biggest risk. Write it to `specs/<short-slug>.md`.

Wait for the planning-lead to return with the spec path and a short summary.

### 2. Build
Delegate to `engineering-lead`:
> Implement the change described in `specs/<spec-from-step-1>.md`. Name
> integration seams up front and delegate to your team in parallel where
> possible. Report what was built (paths), what was *not* built and why,
> and any risks the validation team should specifically look at.

Wait for the engineering-lead to return with paths + risks.

### 3. Validate
Delegate to `validation-lead`, passing the engineering-lead's report:
> Validate the changes from the previous step. Run QA in parallel with a
> security review. Produce a verdict: READY-TO-SHIP, READY-WITH-CAVEATS
> (with the caveats), or BLOCKED (with the specific reason).

Wait for the validation-lead to return with the verdict.

## Final report to the user

Single, concise message:

- **Spec:** `specs/<slug>.md`
- **Built:** files touched (from engineering-lead's report)
- **Verdict:** the validation-lead's verdict (one of the three)
- **Notes:** any caveats or follow-up actions

If the verdict is `BLOCKED`, do **not** hide that — it's the most
important signal. Surface the specific reason and propose the next step
(usually a follow-up `engineering-lead` delegation to address the block).

## Constraints

- Do not edit code yourself. The orchestrator delegates only.
- If at any step a lead returns asking for clarification on the user's
  request, answer it from the conversation context — do not bounce
  back to the user unless the ambiguity is genuinely unresolvable from
  what they said.
- Keep the user-facing report short. The leads' detailed reports stay
  internal; the user gets the synthesis.
