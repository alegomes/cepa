---
description: Execute a Bug-type Jira card via the topology's reproduce-fix-verify flow (failing test first, fix, verify). Wraps the bug flow with Jira lifecycle — transitions through To Do → In Progress → In Review with Implementation Summary. Use directly for bugs, or rely on /jira-flow:execute's auto-detect to route here when the card's issue type is Bug.
argument-hint: <jira-key>
---

# /jira-flow:fix

## Purpose

Bug-flow wrapper around the topology's `reproduce-fix-verify` command. Mirror of `/jira-flow:execute` but routes the bug-shaped work: confirm reproducer → write failing regression test → fix → verify with green build → APPROVE. Transitions the Jira card through the canonical lifecycle (In Progress → In Review with Implementation Summary).

**Requires** a topology with a `reproduce-fix-verify` command (currently `hex-backend` ships it; `multi-team` and `solo-pair` do not). If your topology doesn't have it, this command aborts with a clear error suggesting `/jira-flow:execute --force-feature-flow` as the fallback.

For a non-existent card (greenfield bug discovery) use `/jira-flow:capture Bug: <description>` first, then `/jira-flow:fix <KEY>`.

## Variables

- `$ARGUMENTS` — the Jira issue key (e.g., `WEGO-1234`).

## Instructions

You are the orchestrator. Drive a focused reproduce → fix → verify flow on one Jira card. Apply `till-done`, `scope-discipline`. Apply the green-build-evidence rule — `PASS` requires literal BUILD SUCCESS in the worker's reply.

## Workflow

### 0. Resolve topology prefix

Read the project Jira config: `jira-flow.yaml` at project root if present, otherwise legacy `.claude/jira-flow.lifecycle.yaml`. Extract the top-level `default_topology` value.

- Prefix every topology-agent delegation with it: `<default_topology>:engineering-lead`, `<default_topology>:qa-engineer`, etc.
- Check that `/<default_topology>:reproduce-fix-verify` exists. If the topology doesn't ship that command (multi-team and solo-pair don't), abort with: "Topology `<default_topology>` doesn't ship `reproduce-fix-verify`. Either switch topologies, or use `/jira-flow:execute <jira-key> --force-feature-flow` to run the plan-build-validate flow on this bug instead (heavier, but works)."

`atlassian-expert` is always bare. Write delegations include `Topology: <default_topology>` as the first line of the prompt so per-topology overrides apply (e.g., the right Team field per topology).

### 1. Fetch card details

Delegate to `atlassian-expert`:

> Fetch Jira issue $ARGUMENTS — full details (summary, description, acceptance criteria, issue type, status, last 3 comments). Reply with the verbatim content.

If the card doesn't exist → abort with a clear error.

### 2. Reproducer audit (lightweight)

For bugs, the "detail audit" shape is different from features. Bugs need a clear REPRODUCER, not a planning enrichment pass.

Inspect the card content yourself (don't delegate to planning-lead — it's overkill for a bug). Check:

- Does the description name an observed behavior (what happens)?
- Does it name the expected behavior (what should happen)?
- Are there repro steps, or a payload/input that triggers the bug?

If all three are present → proceed.

If any are missing AND the card description is too vague to attempt reproduction → delegate to `atlassian-expert`:

> Add a comment to $ARGUMENTS: "[automated] /jira-flow:fix paused — the description lacks reproduction details. Need: observed behavior, expected behavior, steps to reproduce or input that triggers. Please update the card and re-run." Do NOT transition.

Report to the user that the card needs more detail. Stop.

### 3. Move card to "in progress"

Read `defaults.status_map.in_progress` from `jira-flow.yaml`. Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Transition $ARGUMENTS to status `<defaults.status_map.in_progress>`.

### 4. Run reproduce-fix-verify

Delegate to `<default_topology>:engineering-lead` (or invoke the command directly — depending on topology design, the lead drives reproduce-fix-verify internally):

> Run the reproduce-fix-verify flow for the bug described in Jira card $ARGUMENTS. Card content (verbatim): <paste content from step 1>.
>
> Apply the canonical reproduce → fix → verify shape: qa-engineer writes the failing regression test first; the right dev-worker (domain-dev / api-dev / adapter-dev based on the affected layer) makes minimum change to pass; qa-engineer re-runs `./mvnw verify` with green-build evidence; code-reviewer approves. NOT-A-BUG is a valid outcome if reproduction reveals the code already handles the case.
>
> Reply with: reproducer test path, fix commit SHA, paths touched, verdict (READY-TO-SHIP / READY-WITH-CAVEATS / BLOCKED / NOT-A-BUG).

Equivalently, if the topology surface includes a slash command form: invoke `/<default_topology>:reproduce-fix-verify <card description verbatim>` and wait for the report.

Wait for the verdict.

### 5. Transition based on verdict

#### READY-TO-SHIP or READY-WITH-CAVEATS

Build the Implementation Summary from the reproduce-fix-verify report (reproducer test path, fix commit SHA, paths touched, qa-engineer's BUILD SUCCESS evidence). Read `defaults.status_map.in_review` from `jira-flow.yaml`.

Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Transition $ARGUMENTS to status `<defaults.status_map.in_review>` with the Implementation Summary below. Post the summary as a comment first, then run the transition.
>
> ```markdown
> ## Implementation summary (bug fix)
>
> **Reproducer:** <failing test path that now passes>
>
> **Fix:** <paths touched, one line per>
>
> **Build verification:** `./mvnw <scope> verify` → BUILD SUCCESS (commit `<SHA>`)
>
> **Caveats / follow-ups:**
> - <none, or caveats from READY-WITH-CAVEATS verdict>
> ```

#### NOT-A-BUG

The reproduction failed because the code already handles the case. This is a valid outcome — confirming a non-bug is not a wasted run.

Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Add a comment to $ARGUMENTS:
>
> "[automated] /jira-flow:fix concluded NOT-A-BUG. Reason: <one-line evidence from reproducer attempt>. The reported behavior could not be reproduced; the code at `<file:line>` already handles the case. Suggest closing as 'Cannot Reproduce' or 'Not a Bug' — leaving status decision to the reporter."
>
> Do NOT transition. Leave status decision to the human.

#### BLOCKED

Leave the card in `defaults.status_map.in_progress`. Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Add a comment to $ARGUMENTS with the blocker reason and any failing-test paths. Do NOT transition.

## Report

A single concise message back to the user:

- **Card:** $ARGUMENTS Jira link + title.
- **Card status before:** (e.g., "To Do," "Backlog").
- **Issue type:** Bug.
- **Reproducer:** test path that captures the bug (or `NOT-A-BUG` with evidence).
- **Fix:** commit SHA + paths touched (or "n/a — NOT-A-BUG").
- **Verdict:** READY-TO-SHIP / READY-WITH-CAVEATS / NOT-A-BUG / BLOCKED.
- **New card status:** In Review / still In Progress (BLOCKED) / unchanged (NOT-A-BUG).
- **Notes:** caveats, follow-ups, or "the reported behavior wasn't reproducible — close as not-a-bug?"

## Constraints

- **The card MUST exist** — atlassian-expert returns an error otherwise; abort gracefully.
- **No planning enrichment phase.** The failing test is the spec for bugs; we don't run `planning-lead` decomposition here. If the card lacks repro details, comment-back-and-pause is the right behavior — let the human fix the card.
- **No worktree at any layer** by default (per the underlying `reproduce-fix-verify` flow). Single fix, one worker, no parallelism.
- **NOT-A-BUG is a valid outcome** — confirming a non-bug is honest. Don't fabricate a fix just because the flow expects one. Surface clearly to the user and to the Jira card.
- **scope-discipline is mandatory.** The dev worker does NOT do unrelated cleanup, even if they spot it. Flag for follow-up; don't silently include.
- `atlassian-expert` is the only Jira write path.
