---
description: Register a raw product signal as an Opportunity card on the discovery board. Lightweight — no framing, no research, just tracking. Lands in Inbox. Use /jira-flow:advance once you're ready to start work on it.
argument-hint: <one-line description of the signal>
---

# /discovery:capture

## Purpose

Drop a raw product signal — a user complaint, a sales-team note, an idea from a stakeholder, a support-ticket pattern — into the discovery board's Inbox column as an Opportunity card. No framing, no research, no decomposition. Just get it tracked so it doesn't get lost.

The card stays in Inbox until you (or your team) decide to start work on it via `/jira-flow:advance <KEY>`, which routes through `discovery-lead` and the right phase agent.

**Requires** `jira-flow@alegomes` installed (for `atlassian-expert`). Without it, abort with a clear error.

## Variables

- `$ARGUMENTS` — the signal description. Free-form. The first 80 chars become the card summary; the full text becomes the description seed.

## Instructions

You are the orchestrator. Don't frame, don't research, don't run discovery-lead. Just create the card.

`atlassian-expert` is the only Jira write path.

## Workflow

### 1. Resolve discovery board project + issue type

Read the project Jira config: `jira-flow.yaml` at project root if present, otherwise legacy `.claude/jira-flow.lifecycle.yaml`. Find the `discovery` lifecycle entry. Read its `project_key` (or, if the new-schema `defaults.project_key` is set and matches, use that). That's the target project.

For issue type:
- If the lifecycle file declares an `issue_type` key on the discovery lifecycle, use it.
- Otherwise, default to `Story` and ask the user once: "Captured as Story. Your discovery board may use a different type (Idea, Opportunity, Discovery). Add `issue_type: <Type>` to the discovery lifecycle in `jira-flow.yaml` to set a default."

If `jira-flow.yaml` has no `discovery` lifecycle entry → abort with: "No discovery lifecycle declared. Run `/discovery:capture` after writing `jira-flow.yaml` (see discovery-topology.md)."

### 2. Create the card

Delegate to `atlassian-expert`:

> Create a new Jira issue in project `<key>`: `issueType=<type>`, summary `<first 80 chars of $ARGUMENTS>`, description:
>
> ```
> <full $ARGUMENTS>
>
> ---
> Captured via /discovery:capture on <today's date>. Lands in Inbox.
> Lifecycle: discovery. Next: /jira-flow:advance <KEY> when ready to frame.
> ```
>
> Return: issue key + URL.

The card lands in the project's default initial status (typically "To Do"), which discovery's lifecycle maps to the Inbox column.

### 3. (Optional) Bootstrap the artifact folder

If the user has indicated they want the artifact folder created up front, run `mkdir -p docs/discovery/<KEY>/evidence/` and create a placeholder README at `docs/discovery/<KEY>/README.md`:

```markdown
# Discovery: <summary>

**Card:** <KEY>
**Captured:** <date>

Artifacts will be authored by discovery agents as the card advances:
- `framing.md` — opportunity-framer (Framing column)
- `research.md` — user-researcher (Researching column)
- `assumptions.md` — assumption-tester (Researching → Validating)
- `audit.md` — evidence-auditor (Validating → Validated)
- `handoff.md` — epic-briefer (Validated → Handed off)

Drop raw evidence (transcripts, CSVs, screenshots) into `evidence/`.
```

Default: ask the user once whether to bootstrap. Don't auto-create the folder on every capture — empty folders are noise.

### 4. Report

A single line to the user:

```
Captured: <KEY> — <summary>  (<URL>)
Column: Inbox.
Next: /jira-flow:advance <KEY> when you're ready to frame the opportunity.
```

## Constraints

- **No planning, no framing.** This is intentionally minimal. The opportunity-framer runs only when the user explicitly advances the card.
- **No transitions.** The card lands in Inbox. Don't move it.
- **No follow-up workflow.** Don't chain into `/jira-flow:advance` unless the user asks.
- **One card per invocation.** If the signal contains multiple distinct opportunities, ask whether to capture them as separate cards.
- **`atlassian-expert` is the only Jira write path.** Don't call MCP tools directly.
