---
description: Run a read-only analysis flow on a hex-backend codebase — examine the code/contracts, write a markdown findings report, conclude with a recommended next step (no-issue / bug / feature-or-refactor / design-decision-needed). Use when you're unsure whether something is wrong, duplicated, or missing.
argument-hint: <question or hypothesis to investigate, e.g., "endpoints X and Y look duplicated, confirm or refute">
---

# /hex-backend:investigate

## Purpose

You're not sure whether something is broken, duplicated, missing, or fine. This
command runs a focused, read-only analysis: lead reads code, optionally
delegates to a specialist (e.g., `integration-analyst` for API/contract
questions), writes a findings report, and concludes with one of:

- **NOT-AN-ISSUE** — the concern is unfounded; here's why.
- **BUG** — confirmed broken; recommend `/hex-backend:reproduce-fix-verify`.
- **FEATURE-OR-REFACTOR** — real work, not a bug; recommend
  `/hex-backend:plan-build-validate`.
- **DESIGN-DECISION-NEEDED** — multiple viable options; here are N choices and
  the trade-offs.

No code changes. No tests. No commits. Output is a markdown report at
`docs/investigations/<slug>.md` plus a one-line conclusion to the user.

For a confirmed bug, skip this and run `/hex-backend:reproduce-fix-verify`.
For known feature work, skip this and run `/hex-backend:plan-build-validate`.

## Variables

- `$ARGUMENTS` — the question or hypothesis. Free-form text. Examples:
  - "endpoints `POST /assinaturas` and `POST /v2/assinaturas` look duplicated"
  - "the retry logic in `PlugSignAdapter` may double-charge"
  - "is the cancellation flow consistent across `domain` and `api-rest`?"

## Instructions

You are the orchestrator. Drive a single read-only investigation. Apply
`scope-discipline` (don't expand into a full audit — answer the specific
question), apply `evidence-over-assumption` (every claim in the report cites
file:line).

## Worktree policy

Same constraint as the other hex-backend commands: leads run in main session,
never with `isolation: "worktree"`. Workers in this command are read-only and
don't need worktree.

## Workflow

### 1. Scope and route

Delegate to `engineering-lead`:

> Investigate: **$ARGUMENTS**
>
> Phase 1: SCOPE. Decide which specialist should examine this:
> - API/contract/endpoint questions → `integration-analyst`.
> - Domain logic / use-case / port questions → you read directly (no
>   sub-delegation; the read is yours).
> - Adapter/infrastructure questions → you read directly.
>
> If multiple specialists are needed (e.g., a question that crosses domain ↔
> api-rest), pick the one whose layer is the *primary* concern and read the
> other yourself.
>
> Reply with: chosen route + a one-line scope statement ("I will examine X
> to determine Y").

### 2. Read and write findings

If route is `integration-analyst`, delegate to it:

> Investigation: **$ARGUMENTS**
>
> Read the relevant code/contracts. Produce a findings report at
> `docs/investigations/<slug>.md` (slug = short-kebab-case of the question)
> covering:
> - **Question** — verbatim.
> - **What I read** — file paths examined.
> - **Findings** — bullet points; each cites file:line.
> - **Conclusion** — one of: NOT-AN-ISSUE / BUG / FEATURE-OR-REFACTOR /
>   DESIGN-DECISION-NEEDED. One paragraph of justification.
> - **Recommended next step** — concrete: which command to run, or "close
>   the question, no further action."
>
> Read-only. Do NOT modify any source file. Reply with the doc path + the
> one-line conclusion.

If route is engineering-lead-direct, the lead does the same work itself
(reads + writes the same report shape to the same path). The lead has read
access everywhere; for write access to `docs/investigations/**`, see the
path-lock note below.

### 3. Surface to user

Read the findings report. Reply to the user with:

- **Question:** verbatim restatement.
- **Conclusion:** one-line verdict + the report path.
- **Recommended next step:** the specific follow-up command (or "no further
  action").

## Report

The findings report itself is the deliverable. The user-facing reply is short:
2-3 lines pointing to the report and the recommendation. Don't paraphrase the
report's findings — the report is the source of truth.

## Constraints

- **Read-only.** No `Edit`/`Write`/`MultiEdit` against source files. The only
  write is the findings report at `docs/investigations/<slug>.md`.
- **No tests, no fixes, no commits.** If the investigation reveals work to do,
  the recommendation is a *next command*, not silent execution.
- **scope-discipline.** Answer the specific question; don't expand into "while
  I was looking, I noticed N other things." Flag related concerns at the end
  of the report under "Adjacent observations (not investigated)" so they're
  recorded but not silently scoped in.
- **evidence-over-assumption.** Every finding cites `file:line`. "I think X"
  without a citation is not a finding.
- **One investigation per invocation.** If the user's question contains
  multiple distinct hypotheses, ask which to investigate first; don't batch.
