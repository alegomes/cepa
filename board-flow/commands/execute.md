---
description: Execute one existing Jira card. Auto-detects the issue type — Bug cards dispatch to /board-flow:fix (reproduce-fix-verify flow); Story/Task/Epic cards proceed with the canonical plan-build-validate flow (detail audit + build + validate). Override auto-dispatch with --force-feature-flow. Use /board-flow:plan-track-build-validate for abstract input that needs decomposition.
argument-hint: <jira-key> [--force-feature-flow] [--no-scope]
---

# /board-flow:execute

## Purpose

Execute a single, already-tracked Jira card. Reviews the card detail before execution — if the card is one-line or under-specified, runs a planning enrichment pass to update the card description first; otherwise proceeds straight to build + validate.

**Requires** a topology with `planning-lead`, `engineering-lead`, `validation-lead` subagents installed alongside board-flow.

## Variables

- `$ARGUMENTS` — the Jira issue key (e.g., `WEGO-1234`).
- `--no-scope` — suppress the out-of-scope warning (see step 1). You named the card by key, so it runs regardless; this just silences the heads-up.

## Instructions

You are the orchestrator. Drive a focused build → validate flow on one Jira card. Apply `till-done`, `scope-discipline`, `acceptance-completeness`. The detail audit ALWAYS runs — even if the card looks fine at first glance. A second, independent bar gates In Review: the card does not advance until `validation-lead`'s `completion-auditor` returns COMPLETE — a green build proves the parts, not each acceptance criterion at its user-facing surface.

## Workflow

### 0. Resolve topology prefix

Read the project Jira config: `board-flow.yaml` at project root if present, otherwise legacy `.claude/board-flow.lifecycle.yaml`. Extract the top-level `default_topology` value (e.g., `build-hex`, `build-team`, `discovery`).

- If found, prefix every topology-agent delegation in this workflow with it: `<default_topology>:planning-lead`, `<default_topology>:engineering-lead`, `<default_topology>:validation-lead`.
- If the file is absent or `default_topology` is not set, use bare names — backward compatible, but may misroute when multiple topologies are installed.

`atlassian-expert` is always bare (it belongs to board-flow, not a topology). However, every delegation to `atlassian-expert` for **write operations** (createIssue, transition, addComment, edit) below MUST include `Topology: <default_topology>` as the first line of the delegation prompt — atlassian-expert uses this to apply per-topology overrides from `topologies.<X>` in `board-flow.yaml` (e.g., the right Team field value for Engineering vs. Product). Read-only delegations don't need the hint.

### 1. Fetch card details

Parse `$ARGUMENTS`: the first token is the Jira key. Detect `--force-feature-flow` and `--no-scope` flags (anywhere in the args). The key without the flags is the issue identifier.

Delegate to `atlassian-expert` (the `Command:` line asks it to also report this card's scope membership — a guard, not a filter; add `Scope: none` only if `--no-scope` was passed):

> Command: execute
> <Scope: none — only if --no-scope was passed>
>
> Fetch Jira issue `<jira-key>` — full details (summary, description, acceptance criteria, **issue type**, status, last 3 comments). Reply with the verbatim content. Include the issue type name (e.g., `Bug`, `Story`, `Task`, `Epic`), and the one-line scope verdict (`scope: in` / `scope: OUT (...)` / `scope: n/a`).

If the card doesn't exist or you don't have access → abort with a clear error.

**Out-of-scope warning (warn, don't block).** If `atlassian-expert` reports `scope: OUT` and `--no-scope` was not passed, print a heads-up before continuing — e.g. "⚠ `<jira-key>` is outside the configured scope (`<effective fragment>`). Running it anyway because you named it explicitly; pass `--no-scope` to silence this." Then proceed normally. Never abort on scope for a single, explicitly-named card.

### 1a. Auto-dispatch on Bug type

Read the card's issue type. Read `defaults.issue_types.bug` from `board-flow.yaml` (default `"Bug"`).

If `--force-feature-flow` was NOT passed AND the card's issue type matches `defaults.issue_types.bug` (case-insensitive):

> The card `<jira-key>` is a Bug. Dispatching to `/board-flow:fix <jira-key>` — that command uses the topology's reproduce-fix-verify flow (failing test first, fix, verify) which is the right shape for bugs. The plan-build-validate ceremony in this command is overhead for a confirmed bug.
>
> If you actually want the heavier feature-flow on this Bug (e.g., the card represents systemic-bug-as-feature scope work), re-run as `/board-flow:execute <jira-key> --force-feature-flow`.

Then invoke `/board-flow:fix <jira-key>` and STOP this command. Don't continue to step 2. If `--no-scope` was passed, forward it (`/board-flow:fix <jira-key> --no-scope`) so the scope warning isn't repeated — `fix` re-fetches the card and would otherwise re-emit the out-of-scope heads-up you already saw in step 1.

If the issue type is `Story`, `Task`, `Epic`, or any non-bug type, OR `--force-feature-flow` was passed → continue with step 2 (the canonical feature flow below).

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

> Update Jira issue $ARGUMENTS: replace description with <enriched description from planning-lead>. Add a comment: "[automated] Description enriched by board-flow's detail audit."

If planning-lead said SUFFICIENT, skip this step.

### 4. Move card to "in progress"

Clear any stale acceptance artifact from a prior run so it can't block a fresh start (mirrors `/board-flow:fix`): if `.claude/acceptance/<jira-key>.yaml` exists, delete it — `validation-lead`'s `completion-auditor` will rewrite it at the end of this run.

**Capture the change baseline** for the later change-scoped proof (`/board-flow:prove`). Before any code is written, record the current commit as this card's baseline: run `git rev-parse HEAD` and write `.claude/cards/<jira-key>.yaml`:

```yaml
card: <jira-key>
base_commit: <SHA from git rev-parse HEAD>
```

Create `.claude/cards/` if absent. This baseline is what lets `proof-reviewer` reconstruct the card's diff (`base_commit..HEAD`, intersected with the Implementation Summary's touched-files list) without relying on a branch-per-card convention. If this is not a git repo or `git` is unavailable, skip silently — proof falls back to the touched-files list alone.

Read `defaults.status_map.in_progress` from `board-flow.yaml` (default `"In Progress"`). Delegate to `atlassian-expert`:

> Transition $ARGUMENTS to status `<defaults.status_map.in_progress>`.

### 5. Build (per-Task quality loop)

Delegate to `engineering-lead`:

> Implement the Story described in Jira card $ARGUMENTS. Card content: <verbatim card description, post-enrichment>.
> Decompose into atomic Tasks (TASK.md per Task). Run the per-Task quality loop: dev worker → qa-engineer → refactor-advisor → code-reviewer. Iterate until each Task is APPROVED. Reply with paths built, refactor-advisor findings, risks for cross-cutting validation.

### 6. Validate

Delegate to `validation-lead`:

> Cross-cutting validation for $ARGUMENTS. Security review + full build verify + verdict.

### 7. Transition based on verdict

**Acceptance precondition.** validation-lead's verdict must carry a `completion-auditor` COMPLETE and the `.claude/acceptance/<jira-key>.yaml` path. If the audit is INCOMPLETE (or absent), do NOT transition — report the open gap and stop; the card stays in `in_progress` until the missing user-facing-surface test lands. (Even if you tried to transition anyway, the `acceptance-gate` hook in `common` reads the artifact and blocks the `transitionJiraIssue` call while `status != complete` — this precondition just fails earlier and more clearly.)

If READY-TO-SHIP or READY-WITH-CAVEATS, build the Implementation Summary from engineering-lead's report (paths built, tests added) and qa-engineer's BUILD SUCCESS evidence (commit SHA). Format using the canonical template (see atlassian-expert's "Transition to Review with Implementation Summary"). Read `defaults.status_map.in_review` from `board-flow.yaml` (default `"In Review"`). Then delegate to `atlassian-expert`:

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
> **Acceptance:** completion-auditor COMPLETE — each criterion demonstrated at its altitude (the user-facing surface it names). Artifact: `.claude/acceptance/<jira-key>.yaml`.
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
