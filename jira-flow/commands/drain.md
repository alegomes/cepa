---
description: Bulk-execute Jira cards from a column (default "To Do"). Iterates through up to N cards in priority order. Stops on first BLOCKED to avoid wasting budget on a stuck card. Heavy operation — each card runs the full execution flow.
argument-hint: [column] [--max N]
---

# /jira-flow:drain

## Purpose

Bulk-execute pending Jira cards. Iterates through cards in a column (default `To Do`), running the equivalent of `/jira-flow:execute` on each. Stops on first BLOCKED card.

**Heavy operation:** each card runs the full plan-track-build-validate flow. Use `--max` to cap the number of cards processed in a single drain. Default `--max 5`.

## Variables

- `$ARGUMENTS` — typically the column name followed optionally by `--max N`. If empty, defaults: column = "To Do", max = 5.

## Instructions

You are the orchestrator. Iterate through pending cards. Stop on first BLOCKED. Apply `till-done` within each card's execution loop, `scope-discipline` across the drain (don't process more than `--max`).

## Workflow

### 1. Parse arguments

- Column name: `$ARGUMENTS` minus any `--max N` flag. Default: `To Do`.
- Max cards: parse `--max N` from `$ARGUMENTS`. Default: 5.

### 2. List pending cards

Delegate to `atlassian-expert`:

> List Jira issues where `status = "<column>"` in the project, ordered by priority and rank. Limit to <max> cards. Return key + summary + priority for each.

If 0 cards → report "Nothing in column <column>" and stop.

### 3. Confirm with user

Show the user:

```
Found N cards in <column>:
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

- **Drained from column:** <column>
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
- If `atlassian-expert` can't list cards (permissions issue, malformed column name), abort with a clear error.
- Always confirm with the user before starting the drain. Don't auto-execute on N cards without buy-in.
