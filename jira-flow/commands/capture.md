---
description: Register a freeform user request as a Jira card without executing it. Use when the user describes new work and there's no card yet — keeps Jira as the source of truth without forcing the full plan-track-build-validate flow.
argument-hint: <one-line description, optionally prefixed with "Epic:" / "Bug:" / "Task:" to override the default Story type>
---

# /jira-flow:capture

## Purpose

Lightweight capture: take a freeform user request and register it as a single Jira issue. No planning, no decomposition, no execution — just get it tracked so it doesn't get lost. The card can be picked up later by `/jira-flow:execute <KEY>` (single card) or `/jira-flow:plan-track-build-validate` (if it grows into an Epic).

Default issue type is **Story**. Override by prefixing `$ARGUMENTS` with `Epic:`, `Bug:`, or `Task:`.

## Variables

- `$ARGUMENTS` — the freeform description, optionally typed-prefixed.

## Instructions

You are the orchestrator. Do **not** plan, decompose, or execute. Just capture.

`atlassian-expert` is the only Jira write path. If it isn't installed, abort with a clear error.

## Workflow

### 1. Parse type and description

- If `$ARGUMENTS` starts with `Epic:`, `Bug:`, or `Task:` (case-insensitive), strip the prefix and use that as the issue type.
- Otherwise use `Story`.
- Trim whitespace. The remaining text is the summary + description seed.

### 2. Resolve project key

- If the user has previously named a project key in this session (e.g., `WEGO-1559`), reuse the same project prefix.
- If not, ask the user: "Which Jira project key (e.g., WEGO)?"
- Don't guess.

### 3. Create the issue

Resolve the active topology for this capture: prefer the orchestrator's current context if known (e.g., called from inside an autonomous run with a `--topology` flag); else read `.claude/topology`; else fall back to `defaults.default_topology` in `jira-flow.yaml`. Pass it to atlassian-expert so the right `topologies.<active>.required_fields` apply (e.g., Team = Engineering for hex-backend, Team = Product for discovery).

Delegate to `atlassian-expert`:

> Topology: `<resolved-topology>`.
>
> Create a new Jira issue in project `<key>`: `issueType=<type>`, summary `<first 80 chars of the description>`, description:
>
> ```
> <full description>
>
> ---
> Captured via /jira-flow:capture on <today's date>. Not yet planned or scheduled.
> ```
>
> Return: issue key + URL.
>
> Apply your read-back verification rule — confirm the card actually exists before reporting success. If `getJiraIssue` doesn't find the key, return BLOCKED.

If `atlassian-expert` returns BLOCKED, do NOT report success to the user. Surface the BLOCKED verdict + the original error verbatim, and stop. The user will fix the underlying cause (auth, required-field, permissions) and re-run.

### 4. Verify before reporting

Even though `atlassian-expert` does its own read-back, run a redundant check at the orchestrator level — capture is the command users are most likely to "fire and forget", so a false positive here means the request is silently lost. Delegate to `atlassian-expert`:

> Confirm Jira issue `<KEY>` exists. Return: status, summary, URL.

If this second `getJiraIssue` doesn't find the key (or returns inconsistent data), reply to the user:

```
BLOCKED: Capture reported card <KEY> created, but it does not exist on Jira.
Likely cause: <atlassian-expert's BLOCKED reason, or "MCP response was lying">.
The card was NOT created. Re-run /jira-flow:capture after fixing the underlying issue.
```

### 5. Report back

A single line to the user (only if both create AND verification PASS):

```
Captured: <KEY> — <summary>  (<URL>)
Verified: card exists in Jira at status <status>.
Next: /jira-flow:execute <KEY> to work on it, or leave it in the backlog.
```

## Constraints

- **No planning enrichment.** Don't run planning-lead. Capture is intentionally minimal — the card may be one-line and that's fine.
- **No transitions.** New cards land in the project's default "To Do" / "Backlog" status. Don't move them.
- **No follow-up workflow.** Do not chain into `/jira-flow:execute` or `plan-track-build-validate` unless the user asks.
- **One card per invocation.** If the user's description clearly contains multiple distinct work items, ask whether to capture them as separate cards or as a single Epic — don't decide silently.
