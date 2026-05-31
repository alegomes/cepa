---
description: Bulk-prove the Review column. Iterates cards in `defaults.status_map.in_review` (priority order) and runs the equivalent of /jira-flow:prove on each — change-driven proof, then routes the verdict. Unlike /jira-flow:drain, it does NOT stop on a failed card: UNPROVEN bounces back and the drain continues, because clearing the queue is the whole point. PROVEN auto-advances (if a done status is configured), NEEDS-HUMAN stays for you. Use to triage a backlogged Review column.
argument-hint: [--max N]
---

# /jira-flow:prove-drain

## Purpose

Drain the *Review* column through the change-driven proof gate. The Review pile
grows because manual review is the bottleneck; this iterates the column and lets
`proof-reviewer`'s evidence triage it — PROVEN out, UNPROVEN back, NEEDS-HUMAN
held for the human. What's left in Review afterward is precisely the set that
actually needs a person.

**Heavy operation:** each card runs a full proof (integration build + JaCoCo +
PIT, in a throwaway worktree). Use `--max` to cap per run. Default `--max 5`.

## Variables

- `$ARGUMENTS` — optionally `--max N`. Default max = 5.

## Instructions

You are the orchestrator. Iterate the Review column, prove each card, route each
verdict. Apply `scope-discipline` (don't exceed `--max`). **Do not stop on
UNPROVEN** — sending a card back is forward progress, not a blocker (this is the
deliberate difference from `/jira-flow:drain`).

## Workflow

### 1. Parse arguments & resolve config

- Max cards: parse `--max N`. Default 5.
- Read `default_topology` and `defaults.status_map.in_review` from
  `jira-flow.yaml`. Confirm the topology ships `proof-reviewer` (else abort as in
  `/jira-flow:prove`).

### 2. List cards in Review

Delegate to `atlassian-expert`:

> List Jira issues where `status = "<in_review>"` in the project, ordered by
> priority and rank. Limit to <max>. Return key + summary + issue type + priority.

If 0 cards → "Nothing in Review." Stop.

### 3. Confirm with user

```
Found N cards in Review (column "<in_review>"):
  WEGO-1234 (Bug, P1) — <summary>
  WEGO-1235 (Story, P2) — <summary>
  ...

Prove these? Each runs the change-driven proof gate (integration coverage +
diff-scoped mutation + adversarial input, in a throwaway worktree).
  · PROVEN     → auto-advances (if a done status is configured)
  · UNPROVEN   → returned to In Progress with the gap (drain CONTINUES)
  · NEEDS-HUMAN→ stays in Review for you

Reply yes / no / first-N to prove a subset.
```

Wait for confirmation.

### 4. Iterate

For each confirmed card, in priority order:

  a. Run the equivalent of `/jira-flow:prove <card-key>` (proof + verdict-driven
     transition).
  b. Capture the verdict and the action taken.
  c. **Continue regardless of verdict** — UNPROVEN does not stop the drain.
  d. If `proof-reviewer` returns a hard environmental failure for a card (can't
     create a worktree, build infra down), record it as `ERROR` for that card
     and continue to the next — one broken card shouldn't sink the batch.

### 5. Final report

```
Proved from Review (max <N>):
  PROVEN → advanced:    <count>   (keys)
  UNPROVEN → returned:  <count>   (keys + one-line gap each)
  NEEDS-HUMAN → held:   <count>   (keys + what to look at)
  ERROR:                <count>   (keys + reason)

Remaining in Review (not attempted this run): <count>
```

Suggest re-running for the next batch if cards remain, and point the user at the
NEEDS-HUMAN set as their actual review queue.

## Constraints

- Default `--max 5`. Each card is an expensive proof; raise deliberately.
- **No stop-on-failure.** UNPROVEN and NEEDS-HUMAN are normal outcomes; the drain
  processes the whole confirmed batch. (Contrast `/jira-flow:drain`, which stops
  on BLOCKED.)
- Always confirm before starting. Don't prove N cards without buy-in.
- Per-card proof is FULL — don't shortcut to save time across cards.
- `atlassian-expert` is the only Jira write path.
