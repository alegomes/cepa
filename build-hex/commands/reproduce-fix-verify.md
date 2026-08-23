---
description: Run a focused bug-fix flow on a build-hex codebase — reproduce the bug with a failing regression test, route the fix to the right dev worker, verify with green build evidence and code review. Use this for confirmed bugs, not for "I'm not sure if X is wrong" (use /build-hex:investigate for that).
argument-hint: <bug description, error message, or steps to reproduce>
interaction: routine
---

# /build-hex:reproduce-fix-verify

## Purpose

Confirmed bug → regression test → fix → green build → APPROVE. The shape mirrors
`plan-build-validate`'s three-verb pattern but the work is different: there's no
planning phase (the spec is the failing test), no parallel fan-out (one bug,
one worker), and no validation-lead by default (bug fixes are narrow; the user
can run validation explicitly if the bug is security-relevant).

For a bug whose existence is uncertain, run `/build-hex:investigate` first.
For a feature, run `/build-hex:plan-build-validate`.

## Variables

- `$ARGUMENTS` — the bug description: free-form text, an error message, steps
  to reproduce, or a Jira description pasted verbatim.

## Instructions

You are the orchestrator. Drive reproduce → fix → verify. Apply `till-done`
(don't accept a partial return — the fix must reach green build), apply
`scope-discipline` (no drive-by refactors; the fix should match the failing test),
and apply `acceptance-completeness` (the regression test must demonstrate the
card's acceptance criterion **at the altitude it was written at** — if the
criterion names an HTTP surface, "the failing test" is an HTTP test, not a
mocked use-case test).

Apply `default-yes`: este comando roda quase sempre DENTRO de um run maior
(`/board-flow:drain`, `/board-flow:prove-drain`, `/common:session`), e uma
pergunta feita aqui chega ao usuário no meio da fila — o ponto mais caro para
interromper, porque responder exige recarregar o contexto inteiro da lista.
Achado reversível, ou que só registra algo, com recomendação clara: execute e
registre para o relatório de quem te chamou. Pergunta só para o irreversível, e
ela sobe para o relatório final do run, nunca para o meio dele.

## Worktree policy

Same constraint as `/build-hex:plan-build-validate`: leads run in main session.
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
>    reason (i.e., the bug's symptom, not a typo or import error). **Place it at
>    the altitude of the card's acceptance criterion** (`acceptance-completeness`):
>    if the criterion names an HTTP endpoint ('POST /x returns 422'), write an
>    integration/E2E test that issues the request and asserts the status/body —
>    not a mocked use-case test. If an `specs/e2e-assertions.md` section exists
>    for the endpoint, it is the source of truth. Run it; paste the literal
>    failure output. Reply with the test file path + the failure tail."
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
>    with the same rules as `/build-hex:plan-build-validate` (branch name,
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

### 4. Acceptance audit (independent last-mile gate)

Green build + code review prove the change is correct and minimal. They do
**not** prove the card's acceptance criterion is demonstrated at the surface it
was written at — that's the recurring last-mile gap (`acceptance-completeness`).

**You (the orchestrator) invoke `completion-auditor` directly** — not through
`engineering-lead`. Independence is the point: the chain that built the fix does
not get to certify its own completeness.

> Delegate to `completion-auditor`:
>
> > Audit acceptance completeness for this bug fix.
> > Card content (verbatim, includes acceptance criteria): <paste $ARGUMENTS>.
> > Changed files / commit: <paths + SHA from phase 2>.
> > Reproducer test: <path from phase 1>.
> > Pin each acceptance criterion to its altitude, find and RUN the test that
> > demonstrates it at that surface, write `.claude/acceptance/<KEY>.yaml`
> > (use the Jira key if the card content has one, else a slug), and return
> > COMPLETE or INCOMPLETE with the precise gap per criterion.

- If **INCOMPLETE** → route the named gap back to the right dev/qa worker (write
  the missing altitude test), re-run Verify, re-audit. Do **not** declare
  READY-TO-SHIP with an open gap. `till-done` applies — the last mile is part
  of the job, not a follow-up.
- If **COMPLETE** → proceed. The verdict is now anchored to demonstrated
  acceptance, not just a green build.

## Report

A single concise message back to the user:

- **Bug:** one-line restatement.
- **Reproducer:** failing test path.
- **Fix:** paths touched + commit SHA.
- **Verdict:** qa + code-reviewer outcome + `completion-auditor` COMPLETE/INCOMPLETE.
- **Acceptance:** the `.claude/acceptance/<KEY>.yaml` path + per-criterion
  altitude/test (or the open gap if INCOMPLETE).
- **Notes:** anything the user should know — e.g., "the fix exposes a related
  edge case worth a follow-up Story" (don't expand scope; flag for later).

If `NOT-A-BUG`, report that with the evidence and stop. Don't apologize for
"wasting the run" — confirming a non-bug is a valid outcome.

## Constraints

- **No planning phase.** The failing test is the spec. Don't decompose into
  Tasks; this is a single-Task flow. **But "the failing test is the spec" only
  holds if the test sits at the acceptance criterion's altitude** — a mocked
  use-case test is not the spec for an HTTP-surface criterion. That is what the
  acceptance audit (step 4) enforces.
- **The acceptance audit is not optional.** A READY-TO-SHIP verdict requires a
  `completion-auditor` COMPLETE. When run via `/board-flow:fix`, the
  `acceptance-gate` hook independently blocks the In-Review transition while the
  audit is INCOMPLETE — so skipping it doesn't get the card moved anyway.
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
