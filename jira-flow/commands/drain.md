---
description: Bulk-execute Jira cards from a column (default = `defaults.status_map.to_do` from `jira-flow.yaml`, fallback "To Do"). Iterates through up to N cards in priority order. Stops on first BLOCKED to avoid wasting budget on a stuck card. Heavy operation — each card runs the full execution flow. The split between Backlog (unrefined) and `to_do` (ready for dev) is intentional: drain only pulls from `to_do`, so unrefined Backlog items stay safe.
argument-hint: [column] [--max N] [--scope "<jql>"] [--no-scope]
---

# /jira-flow:drain

## Purpose

Bulk-execute pending Jira cards. Iterates through cards in a column (default = `defaults.status_map.to_do` from `jira-flow.yaml`, fallback `"To Do"`), running the equivalent of `/jira-flow:execute` on each. Stops on first BLOCKED card.

Why `to_do` and not Backlog: the project convention encoded in `status_map` is that Backlog holds unrefined / unprioritized items, and `to_do` holds items refined and ready for development. Drain pulls only from `to_do` so the team's grooming process stays meaningful.

**Heavy operation:** each card runs the full plan-track-build-validate flow. Use `--max` to cap the number of cards processed in a single drain. Default `--max 5`.

## Variables

- `$ARGUMENTS` — typically the column name followed optionally by `--max N`. If empty, defaults: column = `defaults.status_map.to_do` from `jira-flow.yaml` (fallback `"To Do"` if no config), max = 5.
- `--scope "<jql>"` — a raw JQL fragment that narrows the drain to a slice of the column for this run only, overriding any configured scope.
- `--no-scope` — ignore configured scope entirely; sweep the whole column.

**Scope** lets you drain a slice of the column (a sprint, a team, a label) instead of all of it. By default the drain applies the effective scope resolved from `jira-flow.yaml` (`defaults.scope` / `scope_overrides.drain` / the active topology's `scope`); the two flags above override that for one run. You don't resolve the precedence yourself — pass the command name and any flag to `atlassian-expert`, which resolves and reports the effective fragment.

## Instructions

You are the orchestrator. Iterate through pending cards. Stop on first BLOCKED. Apply `till-done` within each card's execution loop, `scope-discipline` across the drain (don't process more than `--max`).

## Workflow

### 1. Parse arguments

- Column name: `$ARGUMENTS` minus any flag (`--max N`, `--scope "..."`, `--no-scope`). If empty, read `defaults.status_map.to_do` from `jira-flow.yaml`; if config missing entirely, fallback to literal `"To Do"`.
- Max cards: parse `--max N` from `$ARGUMENTS`. Default: 5.
- Scope flags: detect `--no-scope` and `--scope "<jql>"`. They are mutually exclusive; if both appear, abort with "pass either --scope or --no-scope, not both." Build the **scope directive** to hand to `atlassian-expert`: `--no-scope` → `Scope: none`; `--scope "<jql>"` → `Scope: <jql>`; neither → omit the line (atlassian-expert resolves the effective scope from config).

### 2. List pending cards

Delegate to `atlassian-expert` (the `Command:` line tells it to resolve scope for `drain`; include the scope directive only if a flag was passed):

> Command: drain
> <Scope: ... — only if a flag was passed>
>
> List Jira issues where `status = "<column>"` in the project, applying the effective drain scope, ordered by priority and rank. Limit to <max> cards. Return key + summary + priority for each, plus the effective scope you used.

If 0 cards → report "Nothing in column <column>" (note the effective scope, so an empty result from an over-narrow filter is obvious, not mistaken for an empty board) and stop.

### 3. Confirm with user

Show the user:

```
Found N cards in <column> (scope: <effective scope, or "none — whole column">):
  WEGO-1234 (P1) — <summary>
  WEGO-1235 (P2) — <summary>
  ...

Drain these? Each card runs the full execute flow (planning audit + build + validate + Jira transitions). BLOCKED on any card stops the drain.

Reply yes / no / first-N (e.g., "first-2") to drain only a subset.
```

Wait for user confirmation before proceeding.

### 4. Iterate

For each card the user confirmed:

  a. Run the equivalent of `/jira-flow:execute <card-key>` (full detail audit + build + validate + transitions).
  b. Capture the verdict.
  c. **If verdict is BLOCKED:**
     - Stop the drain. Don't process remaining cards.
     - Surface the blocked card + reason to the user.
     - Move to step 5 (final report).
  d. **If READY-TO-SHIP or READY-WITH-CAVEATS:**
     - Continue to the next card.

### 5. Final report

A single summary message:

- **Drained from column:** <column> (scope: <effective scope, or "none">)
- **Cards attempted:** N
- **Moved to In Review:** M (list keys + verdicts)
- **Blocked:** 0 or 1 (key + reason)
- **Remaining in column (not attempted this run):** count
- **Approximate cost:** sum of per-card durations (informational)
- **Next step suggestion:** if any blocked, surface the block; if all drained, suggest re-running for the next batch if more remain.

## Constraints

- Default `--max 5`. Higher values risk runaway cost; set explicitly to override.
- Stop-on-first-BLOCKED is intentional. We don't keep pushing through stuck work.
- Each card's per-Task loop is FULL — don't shortcut to "save time" across cards. The whole point of the topology is per-Task quality.
- If `atlassian-expert` can't list cards (permissions issue, malformed column name, or a rejected scope JQL fragment), abort with a clear error — surface a rejected scope fragment as a config/flag problem, not an empty column.
- **Scope narrows, never widens.** The effective scope only ever subtracts cards from the column; `--no-scope` is the way back to the full sweep. Always show the effective scope on the confirmation screen so the user sees what's being excluded.
- Always confirm with the user before starting the drain. Don't auto-execute on N cards without buy-in.
