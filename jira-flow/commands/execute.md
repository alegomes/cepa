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

### 4. Move card to In Progress

Delegate to `atlassian-expert`:

> Transition $ARGUMENTS to "In Progress."

### 5. Build (per-Task quality loop)

Delegate to `engineering-lead`:

> Implement the Story described in Jira card $ARGUMENTS. Card content: <verbatim card description, post-enrichment>.
> Decompose into atomic Tasks (TASK.md per Task). Run the per-Task quality loop: dev worker → qa-engineer → refactor-advisor → code-reviewer. Iterate until each Task is APPROVED. Reply with paths built, refactor-advisor findings, risks for cross-cutting validation.

### 6. Validate

Delegate to `validation-lead`:

> Cross-cutting validation for $ARGUMENTS. Security review + full build verify + verdict.

### 7. Transition based on verdict

Delegate to `atlassian-expert`:

- If READY-TO-SHIP or READY-WITH-CAVEATS: Transition $ARGUMENTS to "In Review." Add caveats as a comment if any.
- If BLOCKED: Leave In Progress. Add a comment with the specific block reason and any failing-test paths.

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
