---
description: Advance a Jira card to the next column in its topology's lifecycle. Reads `board-flow.yaml` to know what "next" means and which agent (if any) runs on entry. Generic across topologies — used by discovery, build-hex with custom flows, etc. For the default To Do → In Progress → In Review flow, use /board-flow:execute instead.
argument-hint: <jira-key> [--no-scope]
interaction: routine
---

# /board-flow:advance

## Purpose

Move one Jira card forward in its topology's defined lifecycle. The lifecycle file declares the column flow, the agent that runs on entry to each column (if any), and the gate that must be satisfied before entering (if any).

Generic by design — the same command works for discovery's 7-column flow, build-hex's delivery flow, or any custom lifecycle a topology wants to declare. The lifecycle file at `board-flow.yaml` is the source of truth.

For the standard To Do → In Progress → In Review flow with planning + build + validate, use `/board-flow:execute` — it remains the right tool when no custom lifecycle is needed.

## Variables

- `$ARGUMENTS` — the Jira issue key (e.g., `WEGO-1234`).
- `--no-scope` — suppress the out-of-scope warning (step 2). The named card advances regardless; this just silences the heads-up.

## Lifecycle file format

`board-flow.yaml` (host project, copied or hand-authored from a topology's template):

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

If `board-flow.yaml` is missing → abort with: "No lifecycle file found. Create `board-flow.yaml` or use `/board-flow:execute` for the default flow."

## Instructions

You are the orchestrator. Don't implement anything yourself; delegate to `atlassian-expert` for Jira reads/writes and to whichever `on_enter` agent the lifecycle names.

Apply `default-yes`: este comando roda quase sempre DENTRO de um run maior
(`/board-flow:drain`, `/board-flow:prove-drain`, `/common:session`), e uma
pergunta feita aqui chega ao usuário no meio da fila — o ponto mais caro para
interromper, porque responder exige recarregar o contexto inteiro da lista.
Achado reversível, ou que só registra algo, com recomendação clara: execute e
registre para o relatório de quem te chamou. Pergunta só para o irreversível, e
ela sobe para o relatório final do run, nunca para o meio dele.

`atlassian-expert` is the only Jira write path. If it isn't installed, abort.

## Workflow

The active topology for write delegations is the matched lifecycle entry's `topology` field (set in step 3). Every delegation to `atlassian-expert` for write operations (createIssue, transition, addComment, edit) below MUST include `Topology: <matched-lifecycle-topology>` as the first line of the delegation prompt — atlassian-expert uses this to apply per-topology overrides from `topologies.<X>` in `board-flow.yaml`.

### 1. Load project config

Read the project Jira config: `board-flow.yaml` at project root first, falling back to legacy `.claude/board-flow.lifecycle.yaml` if the new location isn't present (with a one-time deprecation note in your reply: "Note: reading legacy `.claude/board-flow.lifecycle.yaml` — move to `board-flow.yaml` at project root."). If neither exists → abort with the message above.

Parse the `lifecycles` list. Hold all of them in mind — the matching one will be picked in step 3.

### 2. Fetch current card state

Detect a `--no-scope` flag in `$ARGUMENTS`; the remaining token is the key. Delegate to `atlassian-expert` (the `Command:` line asks it to also report scope membership — a guard, not a filter; add `Scope: none` only if `--no-scope` was passed):

> Command: advance
> <Scope: none — only if --no-scope was passed>
>
> Fetch Jira issue $ARGUMENTS — return summary, current status, project key, last 3 comments, and the one-line scope verdict (`scope: in` / `scope: OUT (...)` / `scope: n/a`).

If the card doesn't exist → abort with a clear error.

**Out-of-scope warning (warn, don't block).** If `atlassian-expert` reports `scope: OUT` and `--no-scope` was not passed, print a heads-up — "⚠ `$ARGUMENTS` is outside the configured scope (`<effective fragment>`); advancing it anyway because you named it. Pass `--no-scope` to silence." — then continue. Never abort on scope for an explicitly-named card.

### 3. Match card to a lifecycle

Find the lifecycle in the file where:
- `project_key` matches the card's project, AND
- one of its `columns` has `status` matching the card's current status.

If no match → abort: "Card $ARGUMENTS is in status `<X>` which is not declared in any lifecycle in `board-flow.yaml`. Update the file or transition the card manually."

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
- If `no` → abort: "Gate not satisfied. Resolve the gate condition before re-running `/board-flow:advance $ARGUMENTS`."
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
  Next: /board-flow:advance $ARGUMENTS to move forward, or work the column manually.
```

## Constraints

- **One column at a time.** Don't auto-advance through multiple columns in one invocation. Each column is a deliberate step.
- **Gates are non-negotiable.** If the next column has an `enter_gate`, it must be confirmed before transitioning. Don't skip the prompt.
- **No parallel cards.** This command operates on one card. For batch movement across cards, invoke /advance once per card.
- **`atlassian-expert` is the only Jira write path.** Don't call MCP tools directly.
- **Lifecycle file is the source of truth.** Don't try to infer column flow from Jira board configuration — that's brittle across projects.
- **If the on_enter agent isn't installed** (e.g., `epic-briefer` from discovery is referenced but discovery plugin isn't installed), abort with: "Lifecycle references agent `<name>` which isn't installed. Install the topology that ships it, or update the lifecycle file."
