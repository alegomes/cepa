---
description: Run the canonical build-hex workflow — plan with planning-lead, decompose+build with engineering-lead (per-Task quality loop), validate with validation-lead.
argument-hint: <task description>
interaction: routine
---

# /build-hex:plan-build-validate

## Purpose

Run the full plan → build → validate flow for one Story-sized task on a
hexagonal-architecture backend. For tasks that only need one or two
phases, delegate to those leads directly instead of running this command.

For Jira-tracked work, prefer `/board-flow:plan-track-build-validate` —
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

Apply `default-yes`: este comando roda quase sempre DENTRO de um run maior
(`/board-flow:drain`, `/board-flow:prove-drain`, `/common:session`), e uma
pergunta feita aqui chega ao usuário no meio da fila — o ponto mais caro para
interromper, porque responder exige recarregar o contexto inteiro da lista.
Achado reversível, ou que só registra algo, com recomendação clara: execute e
registre para o relatório de quem te chamou. Pergunta só para o irreversível, e
ela sobe para o relatório final do run, nunca para o meio dele.

## Worktree policy

**Leads run in the main session. Workers may fan out to worktrees.**

When invoking subagents via the `Agent` tool:

- `planning-lead`, `engineering-lead`, `validation-lead` — **never** with
  `isolation: "worktree"`. Leads delegate to other subagents; CC strips
  the `Task` tool from worktree-isolated subagents in 2.1.x, so a
  worktreed lead cannot delegate. Empirically observed; see
  `cc_plugin_quirks.md`.
- `domain-dev`, `api-dev`, `adapter-dev` — **may** be invoked with
  `isolation: "worktree"` for parallel Tasks within one Story. They are
  leaves and don't need `Task`.
- `qa-engineer` — **never** in worktree. It runs `./mvnw verify`
  against the merged integration branch, not against a single Task's
  isolated state.
- `refactor-advisor`, `code-reviewer`, `security-reviewer` — leaves;
  worktree allowed but pointless (read-only / advisory).

For parallel **Stories** (not Tasks within one Story), run multiple
`/build-hex:plan-build-validate` invocations rather than worktreeing
the leads.

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
>    For each Task, predict the file paths it will touch (the
>    "Affected files" field) — that prediction drives the parallelism
>    decision in step 2.
> 2. Group Tasks by independence. Tasks whose predicted paths don't
>    overlap can run in parallel; Tasks that share paths must run
>    sequentially. For each independent group, fan out dev workers in
>    parallel using `isolation: "worktree"` (one worktree per Task).
>    For each dev worker invocation:
>    - Failing test first; minimum implementation; commit before
>      returning (the worker's spec requires this).
>    - Worker returns: `RESULT.md` path, worktree branch name, last
>      commit SHA.
> 3. Merge worker branches into a per-Story integration branch — see
>    "Merge strategy" below.
> 4. Run the quality loop on the integration branch (in main session,
>    NOT in worktree):
>    - qa-engineer: coverage scan + `./mvnw <scope> verify` with green
>      build evidence in the reply. If CRITICAL/HIGH gaps or build
>      failure, route back to the responsible dev worker; iterate.
>    - refactor-advisor: housekeeping pass (advisory only).
>    - code-reviewer: APPROVE/REJECT for the whole integration. If
>      REJECT, route back per the reviewer's feedback.
> 5. On APPROVE: merge integration branch to base; clean up worker
>    worktrees and the integration branch.
> 6. Reply with: paths built, paths NOT built and why, integration
>    risks for validation, refactor-advisor's findings (verbatim,
>    advisory), the base-branch commit SHA after integration merge.

## Merge strategy

When dev workers fan out into parallel worktrees, the `engineering-lead`
owns the merge. Sequence:

1. Create per-Story integration branch off the current base:
   `git checkout -b <story-slug>-integration`.
2. For each worker branch, in deterministic order (Task number ascending),
   merge with `--no-ff` to preserve per-Task commits and traceability.
3. On conflict, classify and route:
   - **Decomposition error** — conflict in a file BOTH TASK.mds predicted
     touching → the original decomposition was wrong. Re-scope the Tasks
     (rewrite TASK.md), re-delegate from scratch.
   - **Scope creep** — conflict in a file NEITHER TASK.md predicted →
     one worker overreached. Treat as REJECT for that worker; ask them
     to redo without the drive-by edit.
   - **True semantic** — both legitimately needed the same file (e.g.,
     shared port + adapter signature). Lead resolves manually, writes
     `docs/tasks/<story-slug>/MERGE.md` documenting the choice. Should
     be rare if integration seams were named in TASK.md upfront.
4. After all merges land, qa-engineer runs against the integration
   branch in main session.
5. After APPROVE: merge integration → base with `--no-ff`, then
   `git worktree remove` each worker worktree and `git branch -d` the
   integration branch (it's redundant once base has the merge commit).
6. **Empty branches** — if a worker returned `BLOCKED`, skip its merge.
   Report the unfinished Task separately to the orchestrator. qa runs
   on the partial integration anyway; other Tasks may still ship.
7. **History style** — default is `--no-ff` (preserves Task-level
   history). Override with `--squash` only if explicitly requested.

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
- **Never invoke a lead with `isolation: "worktree"`.** Leads delegate;
  worktree-isolated subagents lose the `Task` tool in CC 2.1.x.
  Worktree only at the dev-worker layer.
