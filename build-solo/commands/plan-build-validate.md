---
description: Run the build-solo workflow on one well-scoped task — pair-dev implements, pair-reviewer reviews, the orchestrator runs the project's full test suite and commits. The flow /common:autonomous-start and /common:drain-plan dispatch to when .claude/topology says build-solo.
argument-hint: <task description>
interaction: routine
---

# /build-solo:plan-build-validate

## Purpose

The three verbs of the other topologies, at pair size: the task description
is the plan, `pair-dev` builds, `pair-reviewer` plus the full test suite
validate. There is no planning-lead and no spec file — if the task needs one,
it is the wrong topology (see rule 4 of `build-solo-topology.md`).

This command exists so a repo wired to `build-solo` can run an unattended
queue: `/common:autonomous-start` and `/common:drain-plan` dispatch to
`/<topology>:plan-build-validate`, and without it they abort.

## Variables

- `$ARGUMENTS` — the task description, passed verbatim to `pair-dev`.

## Instructions

You are the orchestrator. Do not edit source yourself — route through
`pair-dev`. Apply `till-done` and `scope-discipline`: the task is what
`$ARGUMENTS` says, not what is nearby.

## Workflow

### 1. Build

Delegate to `pair-dev`:

> Implement: **$ARGUMENTS**
>
> Read 2-3 sibling files first and match their conventions. If the change
> alters behavior, add or update the test that shows it. Report: paths
> touched, the test that covers the change, non-obvious decisions, and what
> the reviewer should look at extra-carefully. If this is bigger than one
> pass, say so and stop.

### 2. Review

Delegate to `pair-reviewer`, passing `pair-dev`'s report. `NEEDS-FIX` goes
back to `pair-dev` once; a second `NEEDS-FIX` is `BLOCKED` with the
disagreement named. `OK-WITH-NOTES` whose notes are fixes goes back too.

### 3. Validate

Run the project's full test suite yourself, in the foreground, and read the
result in this same turn. The command is the one the repo names (`CLAUDE.md`,
`README.md`); otherwise the first of `tests/run-all.sh`, `make test`,
`npm test`, `pytest` that exists. A red test that was already red before the
change is named as such, with the evidence (the same test red at the base
commit), never silently accepted.

### 4. Commit

Commit the change on the current branch with a message that says what and
why. No push, no merge — landing is the caller's job.

## Report

- **Built:** paths touched and the commit SHA
- **Review:** `pair-reviewer`'s verdict
- **Tests:** the suite command and its result
- **Verdict:** `READY` or `BLOCKED` (with the specific reason)

## Constraints

- Don't edit source in the orchestrator — delegate to `pair-dev`.
- Don't skip the reviewer or the suite to save time.
- A build left running in the background is not a result: wait for it.
