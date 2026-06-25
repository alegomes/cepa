---
description: Run plan → build → validate against any topology that ships planning-lead/engineering-lead/validation-lead, AND keep the Jira lifecycle in sync (Epic + Stories registered, Story transitions through To Do → In Progress → In Review). For abstract input that needs decomposition. Use /jira-flow:execute for an existing card.
argument-hint: <abstract task description>
---

# /jira-flow:plan-track-build-validate

## Purpose

Same plan → build → validate flow as `/hex-backend:plan-build-validate` (or `/multi-team:plan-build-validate`), wrapped with Jira lifecycle: register Epic + Stories before execution; transition the executing Story through To Do → In Progress → In Review.

For an existing Jira card (no decomposition needed), use `/jira-flow:execute` instead.

**Requires** a topology plugin that ships `planning-lead`, `engineering-lead`, and `validation-lead` subagents (e.g., `hex-backend@alegomes` or `multi-team@alegomes`). Won't work with `build-solo` alone (no leads).

## Variables

- `$ARGUMENTS` — the abstract task description.

## Instructions

You are the orchestrator. Drive the planning, building, validation phases AND keep the Jira issue lifecycle in sync. Apply `till-done`, `scope-discipline`, `name-the-disagreement`, `acceptance-completeness` throughout. The Story does not reach In Review until `validation-lead`'s `completion-auditor` returns COMPLETE — a green build proves the parts, not each acceptance criterion at its user-facing surface; the `acceptance-gate` hook enforces this structurally at the transition.

`atlassian-expert` is the ONLY agent allowed to modify Jira state. Don't try to call Atlassian MCP tools directly. If `atlassian-expert` is missing (jira-flow not installed properly), abort with a clear error.

## Workflow

### 0. Resolve topology prefix

Read the project Jira config: `jira-flow.yaml` at project root if present, otherwise legacy `.claude/jira-flow.lifecycle.yaml`. Extract the top-level `default_topology` value (e.g., `hex-backend`, `multi-team`, `discovery`).

- If found, prefix every topology-agent delegation in this workflow with it: `<default_topology>:planning-lead`, `<default_topology>:engineering-lead`, `<default_topology>:validation-lead`.
- If the file is absent or `default_topology` is not set, use bare names — backward compatible, but may misroute when multiple topologies are installed.

`atlassian-expert` is always bare (it belongs to jira-flow, not a topology). However, every delegation to `atlassian-expert` for **write operations** (createIssue, transition, addComment, edit) below MUST include `Topology: <default_topology>` as the first line of the delegation prompt — atlassian-expert uses this to apply per-topology overrides from `topologies.<X>` in `jira-flow.yaml`. Read-only delegations don't need the hint.

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

Clear any stale acceptance artifact from a prior run so it can't block a fresh start (mirrors `/jira-flow:fix`): if `.claude/acceptance/<key>.yaml` exists, delete it — `validation-lead`'s `completion-auditor` will rewrite it at the end of this run.

Delegate to `atlassian-expert`:

> Transition Story <key> to "In Progress."

### 6. Build (per-Story, with per-Task quality loop)

Delegate to `engineering-lead`:

> Implement the Story <key>: <Story title>. Spec is at `spec/<slug>.md`.
> Decompose into atomic Tasks (write `TASK.md` per Task). Run the per-Task quality loop: dev worker → qa-engineer → refactor-advisor → code-reviewer. Iterate until each Task is APPROVED. Move to next Task. Reply with paths built, paths punted, refactor-advisor findings, integration risks.

Wait for the implementation summary.

### 7. Validate

Delegate to `validation-lead`:

> Cross-cutting validation for Story <key>'s implementation. Delegate to security-reviewer, run the project's full build verify, and run the independent acceptance audit (`completion-auditor`) confirming each acceptance criterion is demonstrated at its user-facing altitude. Produce verdict (READY-TO-SHIP / READY-WITH-CAVEATS / BLOCKED) — INCOMPLETE acceptance blocks READY-TO-SHIP. Report the `.claude/acceptance/<key>.yaml` path.

Wait for the verdict.

### 8. Move Story based on verdict

**Acceptance precondition.** validation-lead's verdict must carry a `completion-auditor` COMPLETE and the `.claude/acceptance/<key>.yaml` path. If the audit is INCOMPLETE (or absent), do NOT transition — report the open gap and stop; the Story stays In Progress until the missing user-facing-surface test lands. (Even if you tried to transition anyway, the `acceptance-gate` hook in `common` reads the artifact and blocks the `transitionJiraIssue` call while `status != complete`.)

If READY-TO-SHIP or READY-WITH-CAVEATS, build the Implementation Summary from engineering-lead's report (paths built, tests added) and qa-engineer's BUILD SUCCESS evidence (commit SHA). Format using the canonical template (see atlassian-expert's "Transition to Review with Implementation Summary"). Read `defaults.status_map.in_review` from `jira-flow.yaml` (default `"In Review"`). Then delegate to `atlassian-expert`:

> Transition Story <key> to status `<defaults.status_map.in_review>` with the Implementation Summary below. Post the summary as a comment first, then run the transition.
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
> **Build verification:** `./mvnw <scope> verify` → BUILD SUCCESS (commit `<SHA>`)
>
> **Acceptance:** completion-auditor COMPLETE — each criterion demonstrated at its altitude (the user-facing surface it names). Artifact: `.claude/acceptance/<key>.yaml`.
>
> **Caveats / follow-ups:**
> - <none, or caveats from READY-WITH-CAVEATS verdict>
> ```

If BLOCKED: Leave In Progress. Delegate to `atlassian-expert`:

> Add a comment to Story <key> with the block reason and the path to the failing test or finding. Do NOT transition.

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
