---
description: Run plan → build → validate against any topology that ships planning-lead/engineering-lead/validation-lead, AND keep the Jira lifecycle in sync (Epic + Stories registered, Story transitions through To Do → In Progress → In Review). For abstract input that needs decomposition. Use /jira-flow:execute for an existing card.
argument-hint: <abstract task description>
---

# /jira-flow:plan-track-build-validate

## Purpose

Same plan → build → validate flow as `/hex-backend:plan-build-validate` (or `/multi-team:plan-build-validate`), wrapped with Jira lifecycle: register Epic + Stories before execution; transition the executing Story through To Do → In Progress → In Review.

For an existing Jira card (no decomposition needed), use `/jira-flow:execute` instead.

**Requires** a topology plugin that ships `planning-lead`, `engineering-lead`, and `validation-lead` subagents (e.g., `hex-backend@alegomes` or `multi-team@alegomes`). Won't work with `solo-pair` alone (no leads).

## Variables

- `$ARGUMENTS` — the abstract task description.

## Instructions

You are the orchestrator. Drive the planning, building, validation phases AND keep the Jira issue lifecycle in sync. Apply `till-done`, `scope-discipline`, `name-the-disagreement` throughout.

`atlassian-expert` is the ONLY agent allowed to modify Jira state. Don't try to call Atlassian MCP tools directly. If `atlassian-expert` is missing (jira-flow not installed properly), abort with a clear error.

## Workflow

### 0. Resolve topology prefix

Read `.claude/jira-flow.lifecycle.yaml` if it exists. Extract the top-level `default_topology` value (e.g., `hex-backend`, `multi-team`, `discovery`).

- If found, prefix every topology-agent delegation in this workflow with it: `<default_topology>:planning-lead`, `<default_topology>:engineering-lead`, `<default_topology>:validation-lead`.
- If the file is absent or `default_topology` is not set, use bare names — backward compatible, but may misroute when multiple topologies are installed.

`atlassian-expert` is always bare (it belongs to jira-flow, not a topology).

### 1. Register skeleton Epic in To Do

Delegate to `atlassian-expert`:

> Create a new Jira issue: `issueType=Epic`, status implicitly To Do, summary `[Auto-Pending] $ARGUMENTS`, description "Pending planning — spec will be attached when ready." Return the Epic key + URL.

### 2. Plan

Delegate to `planning-lead`:

> Produce a one-page spec for: **$ARGUMENTS**. Decompose into Epic + 1-3 candidate Stories with acceptance criteria. Run epic-author + product-manager + integration-analyst (or your topology's equivalents) in parallel; synthesize to `spec/<short-slug>.md`.

Wait for the spec path + Epic title + Stories list.

### 3. Update Epic and create Stories in Jira

Delegate to `atlassian-expert`:

> Update Epic <key from step 1>: replace summary with the proper Epic title from the spec; replace description with the spec's Epic description (link to `spec/<slug>.md`).
> Create child Story issues for each Story in the spec — `issueType=Story`, parent=<Epic key>, summary=Story title, description=Story description + acceptance criteria.
> Return all keys.

### 4. Pick a Story to execute

If only one Story → use it.
If multiple → ask the user: "Stories proposed: [list]. Which should I execute now?"

### 5. Move Story to In Progress

Delegate to `atlassian-expert`:

> Transition Story <key> to "In Progress."

### 6. Build (per-Story, with per-Task quality loop)

Delegate to `engineering-lead`:

> Implement the Story <key>: <Story title>. Spec is at `spec/<slug>.md`.
> Decompose into atomic Tasks (write `TASK.md` per Task). Run the per-Task quality loop: dev worker → qa-engineer → refactor-advisor → code-reviewer. Iterate until each Task is APPROVED. Move to next Task. Reply with paths built, paths punted, refactor-advisor findings, integration risks.

Wait for the implementation summary.

### 7. Validate

Delegate to `validation-lead`:

> Cross-cutting validation for Story <key>'s implementation. Delegate to security-reviewer, run the project's full build verify, produce verdict (READY-TO-SHIP / READY-WITH-CAVEATS / BLOCKED).

Wait for the verdict.

### 8. Move Story based on verdict

Delegate to `atlassian-expert`:

- If READY-TO-SHIP or READY-WITH-CAVEATS: Transition Story <key> to "In Review." If READY-WITH-CAVEATS, also `addCommentToJiraIssue` with the caveats.
- If BLOCKED: Leave In Progress. `addCommentToJiraIssue` with the block reason and the path to the failing test or finding.

## Report

A single concise message back to the user:

- **Epic:** Jira link + title.
- **Story executed:** key + title.
- **Spec:** `spec/<slug>.md`.
- **Built:** files touched (from engineering-lead's report).
- **Refactor advisory:** one-line summary (refactor-advisor's findings).
- **Verdict:** validation-lead's verdict.
- **Story status:** In Review / still In Progress (BLOCKED).
- **Notes:** caveats or follow-up actions. If other Stories from the Epic are still To Do, list them so the user knows what's pending.

## Constraints

- Don't edit code yourself; you're the orchestrator.
- Don't auto-transition past In Review unless explicitly asked. The user owns Done/Closed.
- The per-Task quality loop is mandatory inside engineering-lead's phase. Don't skip qa, refactor-advisor, or code-reviewer.
- If `atlassian-expert` is unavailable (jira-flow not installed), abort with: "jira-flow's atlassian-expert is required for this command; install jira-flow@alegomes or use /hex-backend:plan-build-validate (no Jira tracking)."
