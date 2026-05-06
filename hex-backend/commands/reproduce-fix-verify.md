---
description: Run a focused bug-fix flow on a hex-backend codebase — reproduce the bug with a failing regression test, route the fix to the right dev worker, verify with green build evidence and code review. Use this for confirmed bugs, not for "I'm not sure if X is wrong" (use /hex-backend:investigate for that).
argument-hint: <bug description, error message, or steps to reproduce>
---

# /hex-backend:reproduce-fix-verify

## Purpose

Confirmed bug → regression test → fix → green build → APPROVE. The shape mirrors
`plan-build-validate`'s three-verb pattern but the work is different: there's no
planning phase (the spec is the failing test), no parallel fan-out (one bug,
one worker), and no validation-lead by default (bug fixes are narrow; the user
can run validation explicitly if the bug is security-relevant).

For a bug whose existence is uncertain, run `/hex-backend:investigate` first.
For a feature, run `/hex-backend:plan-build-validate`.

## Variables

- `$ARGUMENTS` — the bug description: free-form text, an error message, steps
  to reproduce, or a Jira description pasted verbatim.

## Instructions

You are the orchestrator. Drive reproduce → fix → verify. Apply `till-done`
(don't accept a partial return — the fix must reach green build), apply
`scope-discipline` (no drive-by refactors; the fix should match the failing test).

## Worktree policy

Same constraint as `/hex-backend:plan-build-validate`: leads run in main session.
For this command, the dev worker also runs in main session by default — there's
no parallelism benefit for a single fix and worktree adds merge ceremony for no
gain. If the user wants the fix isolated on its own branch, they should create
the branch *before* invoking this command; the worker will then commit there.

Never invoke `engineering-lead` with `isolation: "worktree"` (CC 2.1.x strips
the `Task` tool from worktreed leads — see `cc_plugin_quirks.md`).

## Workflow

### 1. Reproduce

Delegate to `engineering-lead`:

> A bug has been reported: **$ARGUMENTS**
>
> Phase 1: REPRODUCE.
>
> 1. Read the relevant code to locate the suspected failure surface.
> 2. Delegate to `qa-engineer` with: "Write a failing regression test that
>    captures this bug. The test must fail on the current code for the right
>    reason (i.e., the bug's symptom, not a typo or import error). Place it in
>    the appropriate test module. Run it; paste the literal failure output.
>    Reply with the test file path + the failure tail."
> 3. If qa-engineer cannot reproduce the bug:
>    - If the bug description is too vague to reproduce → reply `BLOCKED:
>      cannot reproduce` with what you tried and what you'd need from the user.
>    - If the bug isn't reproducible because the code already handles it →
>      reply `NOT-A-BUG: <evidence>`. Stop the flow.
> 4. Otherwise reply with: failing test path + failure-output tail + your
>    diagnosis of the responsible layer (domain / application / api-rest /
>    infrastructure / bootstrap).

Wait for engineering-lead's reply.

If `BLOCKED` or `NOT-A-BUG`, surface to the user and stop.

### 2. Fix

Delegate to `engineering-lead`:

> Phase 2: FIX. Failing test is at `<path from phase 1>`. Responsible layer is
> `<layer>`.
>
> 1. Delegate to the right dev worker (`domain-dev`, `api-dev`, or `adapter-dev`)
>    based on the responsible layer. Tell them: "The failing test at `<path>`
>    captures bug **$ARGUMENTS**. Make it pass with the minimum change. No
>    drive-by refactors — `scope-discipline` applies. Commit before returning
>    with the same rules as `/hex-backend:plan-build-validate` (branch name,
>    commit SHA, RESULT.md path)."
> 2. Wait for the worker's RESULT.md + commit SHA.
> 3. Reply with: paths touched, commit SHA, RESULT.md path.

### 3. Verify

Delegate to `engineering-lead`:

> Phase 3: VERIFY (in main session, NOT in worktree).
>
> 1. Delegate to `qa-engineer`: "Run `./mvnw <appropriate-scope> verify`. The
>    failing test from phase 1 must now pass; no other tests may regress. Reply
>    with the literal command run and BUILD SUCCESS tail (the green-build-evidence
>    rule applies — no green build, no PASS)."
> 2. If qa returns BLOCKED or FAIL → route back to the dev worker with the
>    specific failure → iterate.
> 3. Delegate to `code-reviewer`: "APPROVE/REJECT this fix. Confirm the change
>    is minimal (the failing test is the entire spec; nothing extra). Confirm
>    green-build evidence is attached." If REJECT → back to dev worker → iterate.
> 4. Reply with: qa verdict, code-reviewer verdict, final commit SHA.

## Report

A single concise message back to the user:

- **Bug:** one-line restatement.
- **Reproducer:** failing test path.
- **Fix:** paths touched + commit SHA.
- **Verdict:** qa + code-reviewer outcome.
- **Notes:** anything the user should know — e.g., "the fix exposes a related
  edge case worth a follow-up Story" (don't expand scope; flag for later).

If `NOT-A-BUG`, report that with the evidence and stop. Don't apologize for
"wasting the run" — confirming a non-bug is a valid outcome.

## Constraints

- **No planning phase.** The failing test is the spec. Don't decompose into
  Tasks; this is a single-Task flow.
- **No worktree at any layer** by default — single fix, one worker, no
  parallelism. User can branch manually if they want isolation.
- **No validation-lead** unless the user explicitly asks (e.g., for a
  security-relevant fix). Validation-lead is for cross-cutting checks; bug
  fixes are typically narrow.
- **scope-discipline is mandatory.** The dev worker may NOT do unrelated
  cleanup, even if they spot it. Flag it for a follow-up; don't silently
  include it in the bug-fix commit.
- **NOT-A-BUG is a valid outcome.** If reproducing reveals the code already
  handles the case, surface that; don't fabricate a fix.
