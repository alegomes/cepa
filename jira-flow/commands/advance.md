---
description: Advance a Jira card to the next column in its topology's lifecycle. Reads `.claude/jira-flow.lifecycle.yaml` to know what "next" means and which agent (if any) runs on entry. Generic across topologies — used by discovery, hex-backend with custom flows, etc. For the default To Do → In Progress → In Review flow, use /jira-flow:execute instead.
argument-hint: <jira-key>
---

# /jira-flow:advance

## Purpose

Move one Jira card forward in its topology's defined lifecycle. The lifecycle file declares the column flow, the agent that runs on entry to each column (if any), and the gate that must be satisfied before entering (if any).

Generic by design — the same command works for discovery's 7-column flow, hex-backend's delivery flow, or any custom lifecycle a topology wants to declare. The lifecycle file at `.claude/jira-flow.lifecycle.yaml` is the source of truth.

For the standard To Do → In Progress → In Review flow with planning + build + validate, use `/jira-flow:execute` — it remains the right tool when no custom lifecycle is needed.

## Variables

- `$ARGUMENTS` — the Jira issue key (e.g., `WEGO-1234`).

## Lifecycle file format

`.claude/jira-flow.lifecycle.yaml` (host project, copied or hand-authored from a topology's template):

```yaml
schema_version: 1
lifecycles:
  - topology: discovery
    project_key: WEGO
    columns:
      - name: Inbox
        status: "To Do"
      - name: Framing
        status: "Framing"
        on_enter: opportunity-framer
      - name: Researching
        status: "Researching"
        on_enter: user-researcher
      - name: Validating
        status: "Validating"
        enter_gate: "card has assumption-tester test plan in description or comments"
      - name: Validated
        status: "Validated"
        enter_gate: "evidence-auditor verdict = Confirmed"
      - name: Handed off
        status: "Done"
        on_enter: epic-briefer
      - name: Discarded
        status: "Won't Do"
```

Schema rules:
- `lifecycles` is a list — supports multiple topologies in one host project.
- Each lifecycle's `columns` are ordered; "next" means the column immediately after the card's current one.
- `on_enter` (optional) names a subagent to run when the card enters the column.
- `enter_gate` (optional) is a human-readable precondition. The orchestrator confirms it with the user before transitioning.
- `requires_summary` (optional, boolean, default `false`) — if `true`, transitioning into this column requires an Implementation Summary, which is posted as a comment before the transition. Auto-true for any column whose `status` name contains `review` or `qa` (case-insensitive), even if the field is omitted.
- `status` is the literal Jira status name in the project (case-sensitive).

If `.claude/jira-flow.lifecycle.yaml` is missing → abort with: "No lifecycle file found. Create `.claude/jira-flow.lifecycle.yaml` or use `/jira-flow:execute` for the default flow."

## Instructions

You are the orchestrator. Don't implement anything yourself; delegate to `atlassian-expert` for Jira reads/writes and to whichever `on_enter` agent the lifecycle names.

`atlassian-expert` is the only Jira write path. If it isn't installed, abort.

## Workflow

### 1. Load lifecycle file

Read `.claude/jira-flow.lifecycle.yaml`. If missing → abort with the message above.

Parse the `lifecycles` list. Hold all of them in mind — the matching one will be picked in step 3.

### 2. Fetch current card state

Delegate to `atlassian-expert`:

> Fetch Jira issue $ARGUMENTS — return summary, current status, project key, and last 3 comments.

If the card doesn't exist → abort with a clear error.

### 3. Match card to a lifecycle

Find the lifecycle in the file where:
- `project_key` matches the card's project, AND
- one of its `columns` has `status` matching the card's current status.

If no match → abort: "Card $ARGUMENTS is in status `<X>` which is not declared in any lifecycle in `.claude/jira-flow.lifecycle.yaml`. Update the file or transition the card manually."

If multiple lifecycles match (same project + same status) → ask the user which lifecycle to use. Don't guess.

### 4. Identify next column

Find the matched column's index in the lifecycle's `columns` list. The "next" column is at index+1.

If the card is already in the last column → report "Card $ARGUMENTS is in the terminal column `<name>`. Nothing to advance." and stop.

### 5. Check enter_gate (if defined on next column)

If the next column has an `enter_gate`:

Show the gate description to the user and ask:

> Gate for entering `<next column name>`: <gate description>
>
> Has this been satisfied? (yes / no / show me the card so I can decide)

- If `yes` → proceed.
- If `no` → abort: "Gate not satisfied. Resolve the gate condition before re-running `/jira-flow:advance $ARGUMENTS`."
- If `show me the card` → display the card content and re-ask.

### 6. (Conditional) Collect Implementation Summary

If the next column requires a summary (its `requires_summary` is `true`, OR its status name contains `review`/`qa` case-insensitively):

- If you have artifacts in context from a preceding flow (engineering-lead's report, qa-engineer's BUILD SUCCESS evidence) → assemble the summary using the canonical template (see atlassian-expert's "Transition to Review with Implementation Summary").
- If you don't (this command was invoked standalone, no preceding flow) → ask the user:

> Transitioning $ARGUMENTS into `<next column>` requires an Implementation Summary. Paste it now (free-form text — I'll fit it into the canonical template), or reply `skip` to abort the transition.

If the user replies `skip` → abort. Don't transition without the summary.

### 7. Transition the card

If a summary is required:

Delegate to `atlassian-expert`:

> Transition Jira issue $ARGUMENTS to status `<next column's status>` with the Implementation Summary below. Post the summary as a comment first, then run the transition.
>
> ```markdown
> ## Implementation summary
> <assembled summary, in the canonical template>
> ```

If no summary is required:

Delegate to `atlassian-expert`:

> Transition Jira issue $ARGUMENTS to status `<next column's status>`.

### 8. Run on_enter agent (if defined on next column)

If the next column has an `on_enter` agent:

Delegate to that agent:

> The card $ARGUMENTS has just entered the `<next column>` column of the `<topology>` lifecycle. Card content: <full description from atlassian-expert>.
>
> Do your job for this column. Output an artifact (or comment) the next agent in the flow can read.

After the agent reports back, decide whether to:
- Update the card description (delegate to atlassian-expert) with the artifact summary, OR
- Add a comment to the card with the artifact path.

The agent's prompt should make clear what artifact it produces.

### 9. Report

A single concise message to the user:

```
Advanced: $ARGUMENTS
  From: <prior column> (<prior status>)
  To:   <next column> (<next status>)
  Topology: <topology name>
  on_enter: <agent name, or "none">
  Artifact: <path or "none — see card comment">
  Next: /jira-flow:advance $ARGUMENTS to move forward, or work the column manually.
```

## Constraints

- **One column at a time.** Don't auto-advance through multiple columns in one invocation. Each column is a deliberate step.
- **Gates are non-negotiable.** If the next column has an `enter_gate`, it must be confirmed before transitioning. Don't skip the prompt.
- **No parallel cards.** This command operates on one card. For batch movement across cards, invoke /advance once per card.
- **`atlassian-expert` is the only Jira write path.** Don't call MCP tools directly.
- **Lifecycle file is the source of truth.** Don't try to infer column flow from Jira board configuration — that's brittle across projects.
- **If the on_enter agent isn't installed** (e.g., `epic-briefer` from discovery is referenced but discovery plugin isn't installed), abort with: "Lifecycle references agent `<name>` which isn't installed. Install the topology that ships it, or update the lifecycle file."
