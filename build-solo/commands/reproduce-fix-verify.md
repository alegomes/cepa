---
description: Run the build-solo bug-fix flow — pair-dev writes a failing regression test first, then the fix, pair-reviewer reviews, the orchestrator runs the full test suite and commits. The flow /common:autonomous-start and /common:drain-plan dispatch defects to when .claude/topology says build-solo.
argument-hint: <bug description, error message, or failing test>
interaction: routine
---

# /build-solo:reproduce-fix-verify

## Purpose

Confirmed bug → red regression test → fix → green suite → review, at pair
size. `/common:autonomous-start` and `/common:drain-plan` send defects to
`/<topology>:reproduce-fix-verify`; without this command a `build-solo` repo
aborts on the first bug in its queue.

## Variables

- `$ARGUMENTS` — the bug: free text, an error message, or the failing test.

## Instructions

You are the orchestrator. Do not edit source yourself — route through
`pair-dev`. Apply `till-done` (the fix reaches a green suite) and
`scope-discipline` (the fix matches the failing test, no drive-by changes).

## Workflow

### 1. Reproduce

Delegate to `pair-dev`:

> Reproduce this bug with a test that fails for the reported reason, before
> changing any source: **$ARGUMENTS**
>
> If a test already fails for it, use that one. Report the test and its red
> output. If you cannot reproduce it, say so and stop — do not fix a bug you
> could not see.

Can't reproduce → `BLOCKED` with what was tried.

### 2. Fix

Delegate to `pair-dev`: make that test pass with the smallest change that
addresses the cause. Report paths touched and the green output.

### 3. Review

Delegate to `pair-reviewer`, passing both reports. Same loop as
`/build-solo:plan-build-validate`: one round back on `NEEDS-FIX`, then
`BLOCKED`.

### 4. Verify

Run the project's full test suite yourself, in the foreground, and read the
result in this same turn (the command the repo names; otherwise the first of
`tests/run-all.sh`, `make test`, `npm test`, `pytest` that exists).

### 5. Commit

Commit the regression test and the fix on the current branch. No push, no
merge.

## Report

- **Regression test:** path, red before, green after
- **Fix:** paths touched and the commit SHA
- **Review:** `pair-reviewer`'s verdict
- **Tests:** the suite command and its result
- **Verdict:** `FIXED` or `BLOCKED` (with the specific reason)
