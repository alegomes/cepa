---
description: Bulk-prove the Review column. Iterates cards in `defaults.status_map.in_review` (priority order) and runs the equivalent of /board-flow:prove on each — change-driven proof, then routes the verdict. Unlike /board-flow:drain, it does NOT stop on a failed card: UNPROVEN bounces back and the drain continues, because clearing the queue is the whole point. PROVEN auto-advances (if a done status is configured), NEEDS-HUMAN stays for you. Use to triage a backlogged Review column.
argument-hint: [--max N] [--scope "<jql>"] [--no-scope]
---

# /board-flow:prove-drain

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
- `--scope "<jql>"` — a raw JQL fragment that narrows the drain to a slice of the Review column for this run only, overriding any configured scope.
- `--no-scope` — ignore configured scope entirely; sweep the whole Review column.

**Scope** lets you triage a slice of Review (e.g. one team's cards, or `labels = needs-review`) instead of the entire column. By default the drain applies the effective scope resolved from `board-flow.yaml` (`defaults.scope` / `scope_overrides.prove_drain` / the active topology's `scope`); the two flags above override that for one run. You don't resolve the precedence yourself — pass the command name and any flag to `atlassian-expert`, which resolves and reports the effective fragment.

## Instructions

You are the orchestrator. Iterate the Review column, prove each card, route each
verdict. Apply `scope-discipline` (don't exceed `--max`). **Do not stop on
UNPROVEN** — sending a card back is forward progress, not a blocker (this is the
deliberate difference from `/board-flow:drain`).

## Workflow

### 1. Parse arguments & resolve config

- Max cards: parse `--max N`. Default 5.
- Scope flags: detect `--no-scope` and `--scope "<jql>"` (mutually exclusive; if both appear, abort with "pass either --scope or --no-scope, not both"). Build the **scope directive**: `--no-scope` → `Scope: none`; `--scope "<jql>"` → `Scope: <jql>`; neither → omit the line (atlassian-expert resolves the effective scope from config).
- Read `default_topology` and `defaults.status_map.in_review` from
  `board-flow.yaml`. Confirm the topology ships `proof-reviewer` (else abort as in
  `/board-flow:prove`).

### 2. List cards in Review

Delegate to `atlassian-expert` (the `Command:` line tells it to resolve scope for `prove_drain`; include the scope directive only if a flag was passed):

> Command: prove_drain
> <Scope: ... — only if a flag was passed>
>
> List Jira issues where `status = "<in_review>"` in the project, applying the
> effective prove_drain scope, ordered by priority and rank. Limit to <max>.
> Return key + summary + issue type + priority, plus the effective scope you used.

If 0 cards → "Nothing in Review (scope: <effective scope, or 'none'>)." — call out
the scope so an over-narrow filter isn't mistaken for an empty queue. Stop.

### 3. Confirm with user

```
Found N cards in Review (column "<in_review>", scope: <effective scope, or "none — whole column">):
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

  a. Run the equivalent of `/board-flow:prove <card-key>` (proof + verdict-driven
     transition).
  b. Capture the verdict and the action taken.
  c. **Continue regardless of verdict** — UNPROVEN does not stop the drain.
  d. If `proof-reviewer` returns a hard environmental failure for a card (can't
     create a worktree, build infra down), record it as `ERROR` for that card
     and continue to the next — one broken card shouldn't sink the batch.

### 5. Final report

```
Proved from Review (max <N>, scope: <effective scope, or "none">):
  PROVEN → advanced:    <count>   (keys)
  UNPROVEN → returned:  <count>   (keys + one-line gap each)
  NEEDS-HUMAN → held:   <count>   (keys + what to look at)
  ERROR:                <count>   (keys + reason)

Remaining in Review (not attempted this run): <count>
```

The table above is the at-a-glance count. For each card in the NEEDS-HUMAN set —
the only one that costs the user attention — expand it in plain language (apply
`conversational-response`'s "translate jargon at the human boundary"): the one
decision you need and why, not a wall of `assumed`/`L2`/`altitude` the user has
to decode. If you put any held card's decision to the user interactively (an
`AskUserQuestion`), the same rule covers the question, every option label, and
every option description — never a bare `L4` / `waiver` / `altitude` in a label.
Suggest re-running for the next batch if cards remain, and point the user at the
NEEDS-HUMAN set as their actual review queue.

## Constraints

- Default `--max 5`. Each card is an expensive proof; raise deliberately.
- **No stop-on-failure.** UNPROVEN and NEEDS-HUMAN are normal outcomes; the drain
  processes the whole confirmed batch. (Contrast `/board-flow:drain`, which stops
  on BLOCKED.)
- Always confirm before starting. Don't prove N cards without buy-in.
- Per-card proof is FULL — don't shortcut to save time across cards.
- **Scope narrows, never widens.** It only subtracts cards from Review; `--no-scope` returns the full sweep. Show the effective scope on the confirmation screen, and surface a rejected scope JQL fragment as a config/flag error — not an empty Review queue.
- `atlassian-expert` is the only Jira write path.
