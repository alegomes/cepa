---
description: Run the canonical hex-backend workflow — plan with planning-lead, decompose+build with engineering-lead (per-Task quality loop), validate with validation-lead.
argument-hint: <task description>
---

# /hex-backend:plan-build-validate

## Purpose

Run the full plan → build → validate flow for one Story-sized task on a
hexagonal-architecture backend. For tasks that only need one or two
phases, delegate to those leads directly instead of running this command.

For Jira-tracked work, prefer `/jira-flow:plan-track-build-validate` —
this command does NOT touch Jira.

## Variables

- `$ARGUMENTS` — the task description, passed verbatim into the
  planning-lead delegation.

## Instructions

You are the orchestrator. Do not write files yourself. Drive the three
phases (with the per-Task quality loop inside the build phase),
synthesize their outputs, and report back to the user with the final
verdict and links to artifacts.

Apply the `till-done` skill at every step: don't accept a partial return
when a worker should have pushed through. Route back rather than wrap
with caveats. Apply `scope-discipline`: don't expand the task beyond
what was asked. Apply `name-the-disagreement` when synthesizing
conflicting reports.

## Workflow

### 1. Plan

Delegate to `planning-lead`:

> Produce a one-page spec for: **$ARGUMENTS**
>
> Decompose into Epic + 1-3 candidate Stories. Run product-manager,
> epic-author, and integration-analyst in parallel; synthesize. Write
> the spec to `spec/<short-slug>.md` (or `specs/<slug>.md` if that's
> the convention in this repo). Cover: Goal, Approach, Trade-offs, Open
> questions, Assumptions, Biggest risk, proposed Stories with
> acceptance criteria.

Wait for `planning-lead` to return with the spec path and 3-bullet summary.

### 2. Build (per-Story, with per-Task quality loop)

Pick one Story from the spec (the user can specify; otherwise the first / smallest viable one). Delegate to `engineering-lead`:

> Implement the Story described in `spec/<slug>.md` (Story: ...).
>
> 1. Decompose into atomic Tasks. Write a `TASK.md` per Task under
>    `docs/tasks/<story-slug>/`. Identify integration seams up front.
> 2. For each Task, run the per-Task loop:
>    - Delegate to the right dev worker (domain-dev / api-dev /
>      adapter-dev). Failing test first; minimum implementation; produce
>      `RESULT.md` summary.
>    - Delegate to qa-engineer for coverage gap scan. If CRITICAL/HIGH
>      gaps remain, route back to the dev worker; iterate.
>    - Delegate to refactor-advisor for a housekeeping pass (advisory
>      only — never blocks).
>    - Delegate to code-reviewer for APPROVE/REJECT. If REJECT, route
>      back to the dev worker with feedback; iterate.
>    - Move to next Task only after APPROVE.
> 3. Reply with: paths built, paths NOT built and why, integration
>    risks for validation, refactor-advisor's findings (verbatim,
>    advisory).

Wait for `engineering-lead` to return the implementation summary.

### 3. Validate (cross-cutting)

Delegate to `validation-lead`:

> Cross-cutting validation for the Story implemented above.
>
> 1. Delegate to security-reviewer for auth, OWASP, dependency-risk scan.
> 2. Run the project's full build verification (e.g., `./mvnw verify`
>    if it's a Quarkus/Maven project; the equivalent for other stacks).
>    The build must pass clean before declaring done.
> 3. Synthesize: `READY-TO-SHIP`, `READY-WITH-CAVEATS` (with caveats),
>    or `BLOCKED` (with the specific reason).

Wait for the verdict.

## Report

A single concise message back to the user:

- **Spec:** `spec/<slug>.md`
- **Story:** which Story was executed (one-line description)
- **Tasks:** count + paths to RESULT.md files
- **Built:** files touched (from engineering-lead's report)
- **Refactor advisory:** refactor-advisor's findings (one-line summary)
- **Verdict:** the validation-lead's verdict
- **Notes:** caveats or follow-up actions

If the verdict is `BLOCKED`, do NOT hide that. Surface the specific reason
and propose the next step.

## Constraints

- Don't edit code yourself.
- If a lead returns asking for clarification on the user's request, answer
  it from the conversation context — don't bounce back to the user unless
  the ambiguity is genuinely unresolvable.
- Keep the user-facing report short. Detailed reports stay internal.
- The per-Task loop is mandatory. Don't skip qa, refactor-advisor, or
  code-reviewer to "save time."
