---
description: Execute one existing Jira card. Reviews the card detail; if insufficient, runs a planning enrichment pass to update the card description before proceeding to build + validate. Use /jira-flow:plan-track-build-validate for abstract input that needs decomposition.
argument-hint: <jira-key>
---

# /jira-flow:execute

## Purpose

Execute a single, already-tracked Jira card. Reviews the card detail before execution — if the card is one-line or under-specified, runs a planning enrichment pass to update the card description first; otherwise proceeds straight to build + validate.

**Requires** a topology with `planning-lead`, `engineering-lead`, `validation-lead` subagents installed alongside jira-flow.

## Variables

- `$ARGUMENTS` — the Jira issue key (e.g., `WEGO-1234`).

## Instructions

You are the orchestrator. Drive a focused build → validate flow on one Jira card. Apply `till-done`, `scope-discipline`. The detail audit ALWAYS runs — even if the card looks fine at first glance.

## Workflow

### 0. Resolve topology prefix

Read the project Jira config: `jira-flow.yaml` at project root if present, otherwise legacy `.claude/jira-flow.lifecycle.yaml`. Extract the top-level `default_topology` value (e.g., `hex-backend`, `multi-team`, `discovery`).

- If found, prefix every topology-agent delegation in this workflow with it: `<default_topology>:planning-lead`, `<default_topology>:engineering-lead`, `<default_topology>:validation-lead`.
- If the file is absent or `default_topology` is not set, use bare names — backward compatible, but may misroute when multiple topologies are installed.

`atlassian-expert` is always bare (it belongs to jira-flow, not a topology).

### 1. Fetch card details

Delegate to `atlassian-expert`:

> Fetch Jira issue $ARGUMENTS — full details (summary, description, acceptance criteria, status, last 3 comments). Reply with the verbatim content.

If the card doesn't exist or you don't have access → abort with a clear error.

### 2. Detail audit (planning-lead)

Delegate to `planning-lead`:

> The Jira card $ARGUMENTS contains: <paste the card content from atlassian-expert>.
>
> Audit it:
> - Outcome / acceptance criteria present?
> - NFRs (security, observability, resilience) called out where relevant?
> - External contracts referenced if integration-touching?
>
> If sufficient detail → reply with `SUFFICIENT, proceed to build` and a one-line summary of what the card asks for.
> If insufficient → enrich (delegate to epic-author / product-manager / integration-analyst as needed). Reply with the enriched description ready to update the card.

### 3. (Conditional) Update card with enrichments

If planning-lead enriched the card, delegate to `atlassian-expert`:

> Update Jira issue $ARGUMENTS: replace description with <enriched description from planning-lead>. Add a comment: "[automated] Description enriched by jira-flow's detail audit."

If planning-lead said SUFFICIENT, skip this step.

### 4. Move card to "in progress"

Read `defaults.status_map.in_progress` from `jira-flow.yaml` (default `"In Progress"`). Delegate to `atlassian-expert`:

> Transition $ARGUMENTS to status `<defaults.status_map.in_progress>`.

### 5. Build (per-Task quality loop)

Delegate to `engineering-lead`:

> Implement the Story described in Jira card $ARGUMENTS. Card content: <verbatim card description, post-enrichment>.
> Decompose into atomic Tasks (TASK.md per Task). Run the per-Task quality loop: dev worker → qa-engineer → refactor-advisor → code-reviewer. Iterate until each Task is APPROVED. Reply with paths built, refactor-advisor findings, risks for cross-cutting validation.

### 6. Validate

Delegate to `validation-lead`:

> Cross-cutting validation for $ARGUMENTS. Security review + full build verify + verdict.

### 7. Transition based on verdict

If READY-TO-SHIP or READY-WITH-CAVEATS, build the Implementation Summary from engineering-lead's report (paths built, tests added) and qa-engineer's BUILD SUCCESS evidence (commit SHA). Format using the canonical template (see atlassian-expert's "Transition to Review with Implementation Summary"). Read `defaults.status_map.in_review` from `jira-flow.yaml` (default `"In Review"`). Then delegate to `atlassian-expert`:

> Transition $ARGUMENTS to status `<defaults.status_map.in_review>` with the Implementation Summary below. Post the summary as a comment first, then run the transition.
>
> ```markdown
> ## Implementation summary
>
> **Files touched:**
> - <list from engineering-lead>
>
> **Tests added/updated:**
> - <list from engineering-lead / qa-engineer>
>
> **Build verification:** `./mvnw <scope> verify` → BUILD SUCCESS (commit `<SHA from qa-engineer>`)
>
> **Caveats / follow-ups:**
> - <none, or caveats from validation-lead's READY-WITH-CAVEATS verdict>
> ```

If BLOCKED: leave the card where it is (in `<defaults.status_map.in_progress>`). If `defaults.status_map.blocked` is set (non-null), optionally also transition into the blocked column — ask the user once at session start which they prefer; default to leaving in `in_progress` with a comment. Delegate to `atlassian-expert`:

> Add a comment to $ARGUMENTS with the specific block reason from validation-lead and any failing-test paths. Do NOT transition.

## Report

A single concise message back to the user:

- **Card:** $ARGUMENTS Jira link + title.
- **Card status before:** (e.g., "To Do," "Backlog").
- **Enrichment:** "yes — description updated" + one-line summary, or "no — sufficient as-is."
- **Built:** files touched.
- **Refactor advisory:** one-line summary.
- **Verdict:** validation-lead's verdict.
- **New card status:** In Review / still In Progress (BLOCKED).
- **Notes:** caveats or follow-ups.

## Constraints

- The card MUST exist before invoking — atlassian-expert returns an error otherwise; abort gracefully.
- The detail audit ALWAYS runs. Don't skip — even if the card looks fine.
- Don't auto-transition past In Review unless explicitly asked.
- atlassian-expert is the only Jira write path.
