---
description: Bulk-execute Jira cards from a column (default = `defaults.status_map.to_do` from `board-flow.yaml`, fallback "To Do"). Iterates through up to N cards in the order the single-track queue (`<programs>/<project_key>/plan.yaml`) puts them, when one exists — cards outside the queue follow, in Jira priority/rank order; with no queue, falls back to Jira priority/rank order as before. Stops on first BLOCKED to avoid wasting budget on a stuck card. Heavy operation — each card runs the full execution flow. The split between Backlog (unrefined) and `to_do` (ready for dev) is intentional: drain only pulls from `to_do`, so unrefined Backlog items stay safe.
argument-hint: [column] [--max N] [--scope "<jql>"] [--no-scope]
interaction: routine
---

# /board-flow:drain

## Purpose

Bulk-execute pending Jira cards. Iterates through cards in a column (default = `defaults.status_map.to_do` from `board-flow.yaml`, fallback `"To Do"`), running the equivalent of `/board-flow:execute` on each. Stops on first BLOCKED card.

Why `to_do` and not Backlog: the project convention encoded in `status_map` is that Backlog holds unrefined / unprioritized items, and `to_do` holds items refined and ready for development. Drain pulls only from `to_do` so the team's grooming process stays meaningful.

**Heavy operation:** each card runs the full plan-track-build-validate flow. Use `--max` to cap the number of cards processed in a single drain. Default `--max 5`.

## Variables

- `$ARGUMENTS` — typically the column name followed optionally by `--max N`. If empty, defaults: column = `defaults.status_map.to_do` from `board-flow.yaml` (fallback `"To Do"` if no config), max = 5.
- `--scope "<jql>"` — a raw JQL fragment that narrows the drain to a slice of the column for this run only, overriding any configured scope.
- `--no-scope` — ignore configured scope entirely; sweep the whole column.

**Scope** lets you drain a slice of the column (a sprint, a team, a label) instead of all of it. By default the drain applies the effective scope resolved from `board-flow.yaml` (`defaults.scope` / `scope_overrides.drain` / the active topology's `scope`); the two flags above override that for one run. You don't resolve the precedence yourself — pass the command name and any flag to `atlassian-expert`, which resolves and reports the effective fragment.

## Instructions

You are the orchestrator. Iterate through pending cards. Stop on first BLOCKED. Apply `till-done` within each card's execution loop, `scope-discipline` across the drain (don't process more than `--max`).

## Workflow

### 1. Parse arguments

- Column name: `$ARGUMENTS` minus any flag (`--max N`, `--scope "..."`, `--no-scope`). If empty, read `defaults.status_map.to_do` from `board-flow.yaml`; if config missing entirely, fallback to literal `"To Do"`.
- Max cards: parse `--max N` from `$ARGUMENTS`. Default: 5.
- **The run's claim id**: generate one, now, as described in **Card reservation**. It identifies THIS run on every card it touches.
- Scope flags: detect `--no-scope` and `--scope "<jql>"`. They are mutually exclusive; if both appear, abort with "pass either --scope or --no-scope, not both." Build the **scope directive** to hand to `atlassian-expert`: `--no-scope` → `Scope: none`; `--scope "<jql>"` → `Scope: <jql>`; neither → omit the line (atlassian-expert resolves the effective scope from config).

### 2. List pending cards

Resolve the single-track queue first, because it changes how many cards to ask
for: `<programs>/<project_key>/plan.yaml` (`<programs>` = `<main-root>/.claude/programs`,
`<main-root>` = the main clone, never the current worktree's own `.claude/`;
`<project_key>` from `board-flow.yaml`). Check whether that file exists before
delegating.

Delegate to `atlassian-expert` (the `Command:` line tells it to resolve scope for `drain`; include the scope directive only if a flag was passed):

> Command: drain
> <Scope: ... — only if a flag was passed>
>
> List Jira issues where `status = "<column>"` in the project, applying the effective drain scope, ordered by priority and rank. Limit to <the whole column, no limit, if the single-track queue exists — otherwise <max>> cards. Return key + summary + priority for each, plus the effective scope you used.

**Why the whole column when a queue exists:** `--max` caps how many cards this
run *executes*, not how many exist. Asking Jira for only the first `<max>` in
its own priority/rank order, then reordering by the queue, could cut off the
queue's actual first items if Jira's rank disagrees — the cap has to apply
*after* reordering (step 2b), never before.

If 0 cards → report "Nothing in column <column>" (note the effective scope, so an empty result from an over-narrow filter is obvious, not mistaken for an empty board) and stop.

### 2b. Reorder by the queue, if one exists

- No `plan.yaml` for `<project_key>` → keep Jira's priority/rank order exactly
  as listed in step 2 (today's behavior). Skip to step 3.
- `plan.yaml` exists → run:

  ```
  python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-plan" ordena <project_key> --keys <K1,K2,...> --json
  ```

  (`common/bin/cepa-plan` is a relative path that only exists inside the
  `cepa` repo — this shim finds the real `cepa-plan` from `common`, in the
  repo or the plugin cache, so it also works in host projects like WEGO.)

  passing every key step 2 returned, in the order Jira gave them. The command
  returns the queue's order for keys that are items of it, then the rest —
  `fora_do_plano` — in the Jira order they came in. Use that combined order for
  steps 3 onward. Exit 2 (no queue after all — e.g. it was removed between the
  two calls) falls back to Jira order, same as "no `plan.yaml`" above.
- Cards in `fora_do_plano` are **named** in the step-3 confirmation screen and
  the final report, with the hint that `/common:plan <project_key> --from-jira`
  or `python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-plan" add <project_key> <key> --title "..."` is
  what puts a card into the queue.
- Apply `--max` to the reordered list now, not to the raw Jira listing from
  step 2.

### 3. Confirm with user

Show the user (order = the queue's, when step 2b found one; Jira's otherwise):

```
Found N cards in <column> (scope: <effective scope, or "none — whole column">)<, queue: <project_key> — if a plan.yaml drove the order>:
  WEGO-1234 (P1) — <summary>
  WEGO-1235 (P2) — <summary>  (out of the queue — only enters it with /common:plan <project_key> --from-jira or cepa-plan add)
  ...

Drain these? Each card runs the full execute flow (planning audit + build + validate + Jira transitions).

And if a card gets stuck (BLOCKED — a condition outside the card that only you can clear):
  (a) I stop the run there and call you                ← default
  (b) I skip the card, record the reason and go on with the rest

Reply yes / no / first-N (e.g., "first-2") to drain only a subset, and (a) or (b)
for the stuck card. A bare "yes" counts as yes + (a).
```

Render this screen to the owner in Brazilian Portuguese (pt-BR); a bare "sim"
is the "yes" above.

Wait for user confirmation before proceeding. **This is the only planned stop
of the run** — apply `default-yes`.

**The (a)/(b) alternative has to be WRITTEN on the screen above, not implied.**
A "can I go?" that only shows the card count collects no answer at all about
the stuck card: at card 3 of 5 the run stops to ask, and by then the user has
already lost the context of the list — which is exactly the cost the single stop
exists to avoid. Asking at the start costs two lines of screen.

If the run came from `/common:session`, these answers were already collected —
go on without asking.

### 4. Iterate

For each card the user confirmed:

  a. **Reserve the card first** — re-read status + comments and publish the claim, per **Card reservation** below. If the card was skipped (it left the column or is reserved by another session), record `SKIPPED` and go to the next card WITHOUT running anything.
  b. Run the equivalent of `/board-flow:execute <card-key>` (full detail audit + build + validate + transitions).
  c. Capture the verdict.
  d. **If verdict is BLOCKED:** follow the policy chosen in the step 3
     confirmation — stop (default) or skip the card and continue. In both cases:
     - If the card stopped without getting a verdict comment, publish the claim release (`🔓`) before moving on.
     - Record the card and the reason for the final report; **ask nothing
       now** — the user already answered that question at the start.
     - Stopping: go to step 5 (final report). Skipping: next card.
  e. **If READY-TO-SHIP or READY-WITH-CAVEATS:**
     - Continue to the next card.
  f. Record that card's **outcome terminal** before moving on (see below). A card
     you touched and cannot name an outcome for is an unfinished card, not a
     quiet success.

### 4b. Outcome terminal — no card leaves the drain unnamed

The drain does not finish while any attempted card lacks a named terminal
outcome. Every card you touched ends in exactly one of:

| Outcome | Means |
|---|---|
| `SHIPPED` | moved to In Review / done, verdict recorded |
| `BLOCKED` | stopped on a condition outside the card — name the condition and who clears it |
| `DEFERRED` | deliberately postponed — name what must be true to pick it up |
| `DROPPED` | will not be done — name why |
| `ERROR` | the run itself failed (infra, permissions) — name the failure |
| `SKIPPED` | another session already had the card (active reservation) or it left the column — name which of the two |

"In progress", "partially done", "needs attention" and silence are **not**
outcomes. They are the absence of a decision wearing a status label, and they are
how a card returns to the board next week with nobody knowing what happened to
it. If you cannot name the outcome, the honest terminal is `BLOCKED` with the
reason "outcome undetermined: <what you don't know>".

This mirrors the same rule the maestro applies per wave (a wave doesn't land with
a non-terminal slice) — one discipline, two surfaces.

### 5. Final report

A single summary message:

- **Drained from column:** <column> (scope: <effective scope, or "none">)
- **Order:** queue `<project_key>` (`<programs>/<project_key>/plan.yaml`), or "Jira priority/rank (no queue for `<project_key>`)"
- **Out of the queue (drained in Jira order, after the queued ones):** keys, or "none" — only when a queue drove the order; name them and repeat the hint (`/common:plan <project_key> --from-jira` or `cepa-plan add`)
- **Cards attempted:** N — each with its outcome terminal (`SHIPPED` / `BLOCKED` / `DEFERRED` / `DROPPED` / `ERROR`). The count of attempted cards MUST equal the count of named outcomes; if it doesn't, the drain is not finished.
- **Moved to In Review:** M (list keys + verdicts)
- **Blocked:** 0 or 1 (key + reason)
- **Skipped:** count (keys + which session's reservation, or which status the card had already moved to)
- **Remaining in column (not attempted this run):** count
- **Approximate cost:** sum of per-card durations (informational)
- **Next step suggestion:** if any blocked, surface the block; if all drained, suggest re-running for the next batch if more remain.

## Card reservation — the queue is the contested resource

The list built in step 2 is a **snapshot**, not a reservation. Between the
listing and the moment this run reaches card N, another session (another
worktree, another machine, the same user in two windows) may have taken the same
card — and the cost isn't a file conflict, it's the whole job redone. The shared
resource is the board column, so the reservation is made on the board.

**Claim id.** Generate ONE per run, in step 1, and use the same one for every card:

```bash
echo "$(basename "$PWD")-$(python3 -c 'import uuid;print(uuid.uuid4().hex[:8])')"
```

**Before touching each card** (it's the first step of 4, before any build,
worktree or delegation), delegate to `atlassian-expert`:

> Read card `<KEY>`: current status, assignee, and the comments from the last
> 90 minutes. Return it without changing anything.

And decide, mechanically:

- **Status ≠ `<the run's column>`** → the card left the queue since the listing.
  **Skip** it, record `SKIPPED (left the column: now in <status>)` and move on to
  the next.
- **There is a claim comment from ANOTHER claim id, less than 90 minutes old and
  without the `🔓` release** → another session is on it right now. **Skip** it,
  record `SKIPPED (reserved by <claim-id> at <hh:mm>)` and move on.
- **Otherwise** → reserve it, publishing the comment via `atlassian-expert`. The
  comment body is posted verbatim, in pt-BR (`atlassian-expert` looks for the
  `🔒 claim:` / `🔓 claim` prefixes):

  > `🔒 claim: <claim-id> — <nome do comando> em andamento desde <timestamp>.`
  > `Outra sessão deve pular este card. A reserva expira em 90 minutos.`

  ("claim: <claim-id> — <command name> in progress since <timestamp>. Another
  session must skip this card. The reservation expires in 90 minutes.")

  Only after that comment exists may the card be worked.

**Release.** The card's verdict ends the reservation — the result comment
(implementation summary, bounce with `**Reason:**`) is already the signal that
the reservation is over. When the card ends WITHOUT a verdict (`ERROR`, `BLOCKED`
without a comment, run interruption), publish the explicit release (verbatim,
pt-BR), otherwise the card stays untouchable for 90 minutes:

> `🔓 claim <claim-id> liberado — <motivo>.`

("claim <claim-id> released — <reason>.")

**Why 90 minutes and not a permanent lock:** a session that dies midway must not
freeze the queue. The window is longer than one card's time and shorter than a
work shift, so an orphaned reservation resolves itself without anyone having to
unlock anything by hand.

**Skipped cards don't consume `--max`** — no work ran on them. They show up in
the final report with the reason, because "vanished from the list without
explanation" is exactly the hole this mechanism exists to close. A `SKIPPED` also
does **not** stop the drain: only `BLOCKED` stops it.

## Constraints

- Default `--max 5`. Higher values risk runaway cost; set explicitly to override.
- Stop-on-first-BLOCKED is intentional. We don't keep pushing through stuck work.
- Each card's per-Task loop is FULL — don't shortcut to "save time" across cards. The whole point of the topology is per-Task quality.
- If `atlassian-expert` can't list cards (permissions issue, malformed column name, or a rejected scope JQL fragment), abort with a clear error — surface a rejected scope fragment as a config/flag problem, not an empty column.
- **Scope narrows, never widens.** The effective scope only ever subtracts cards from the column; `--no-scope` is the way back to the full sweep. Always show the effective scope on the confirmation screen so the user sees what's being excluded.
- **Reserve before executing, card by card.** The listing is a snapshot; the reservation on the board is what keeps two sessions from building the same card. Without the claim published, the card is not worked.
- Always confirm with the user before starting the drain. Don't auto-execute on N cards without buy-in.
