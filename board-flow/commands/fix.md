---
description: Execute a Bug-type Jira card via the topology's reproduce-fix-verify flow (failing test first, fix, verify). Wraps the bug flow with Jira lifecycle — transitions through To Do → In Progress → In Review with Implementation Summary. Use directly for bugs, or rely on /board-flow:execute's auto-detect to route here when the card's issue type is Bug.
argument-hint: <jira-key> [--no-scope]
interaction: routine
---

# /board-flow:fix

## Purpose

Bug-flow wrapper around the topology's `reproduce-fix-verify` command. Mirror of `/board-flow:execute` but routes the bug-shaped work: confirm reproducer → write failing regression test → fix → verify with green build → APPROVE. Transitions the Jira card through the canonical lifecycle (In Progress → In Review with Implementation Summary).

**Requires** a topology with a `reproduce-fix-verify` command (currently `build-hex` ships it; `build-team` and `build-solo` do not). If your topology doesn't have it, this command aborts with a clear error suggesting `/board-flow:execute --force-feature-flow` as the fallback.

For a non-existent card (greenfield bug discovery) use `/board-flow:capture Bug: <description>` first, then `/board-flow:fix <KEY>`.

## Variables

- `$ARGUMENTS` — the Jira issue key (e.g., `WEGO-1234`).
- `--no-scope` — suppress the out-of-scope warning (step 1). The named bug is fixed regardless; this just silences the heads-up.

## Instructions

You are the orchestrator. Drive a focused reproduce → fix → verify flow on one Jira card. Apply `till-done`, `scope-discipline`, `acceptance-completeness`. Apply the green-build-evidence rule — `PASS` requires literal BUILD SUCCESS in the worker's reply. And a second, independent bar: the card does not reach In Review until `completion-auditor` returns COMPLETE — a green build proves the parts, not the acceptance criterion at its stated surface.

## Workflow

### 0. Resolve topology prefix

Read the project Jira config: `board-flow.yaml` at project root if present, otherwise legacy `.claude/board-flow.lifecycle.yaml`. Extract the top-level `default_topology` value.

- Prefix every topology-agent delegation with it: `<default_topology>:engineering-lead`, `<default_topology>:qa-engineer`, etc.
- Check that `/<default_topology>:reproduce-fix-verify` exists. If the topology doesn't ship that command (build-team and build-solo don't), abort with: "Topology `<default_topology>` doesn't ship `reproduce-fix-verify`. Either switch topologies, or use `/board-flow:execute <jira-key> --force-feature-flow` to run the plan-build-validate flow on this bug instead (heavier, but works)."

`atlassian-expert` is always bare. Write delegations include `Topology: <default_topology>` as the first line of the prompt so per-topology overrides apply (e.g., the right Team field per topology).

### 1. Fetch card details

**Already have the card?** When `/board-flow:execute` dispatched here after its own step 1, it already fetched the same fields (summary, description, acceptance criteria, issue type, status, last 3 comments) and showed the scope verdict. Reuse that content and skip this delegation.

Detect a `--no-scope` flag in `$ARGUMENTS`; the remaining token is the key. Delegate to `atlassian-expert` (the `Command:` line asks it to also report scope membership — a guard, not a filter; add `Scope: none` only if `--no-scope` was passed):

> Command: fix
> <Scope: none — only if --no-scope was passed>
>
> Fetch Jira issue $ARGUMENTS — full details (summary, description, acceptance criteria, issue type, status, last 3 comments). Reply with the verbatim content, and include the one-line scope verdict (`scope: in` / `scope: OUT (...)` / `scope: n/a`).

If the card doesn't exist → abort with a clear error.

**Out-of-scope warning (warn, don't block).** If `atlassian-expert` reports `scope: OUT` and `--no-scope` was not passed, print a heads-up — "⚠ `$ARGUMENTS` is outside the configured scope (`<effective fragment>`); fixing it anyway because you named it. Pass `--no-scope` to silence." — then continue. Never abort on scope for an explicitly-named card.

### 2. Reproducer audit (lightweight)

For bugs, the "detail audit" shape is different from features. Bugs need a clear REPRODUCER, not a planning enrichment pass.

Inspect the card content yourself (don't delegate to planning-lead — it's overkill for a bug). Check:

- Does the description name an observed behavior (what happens)?
- Does it name the expected behavior (what should happen)?
- Are there repro steps, or a payload/input that triggers the bug?

If all three are present → proceed.

If any are missing AND the card description is too vague to attempt reproduction → delegate to `atlassian-expert`:

> Add a comment to $ARGUMENTS: "[automated] /board-flow:fix paused — the description lacks reproduction details. Need: observed behavior, expected behavior, steps to reproduce or input that triggers. Please update the card and re-run." Do NOT transition.

Report to the user that the card needs more detail. Stop.

### 3. Move card to "in progress"

Clear any stale acceptance artifact from a prior run so it can't block a fresh
start: if `.claude/acceptance/$ARGUMENTS.yaml` exists, delete it (the
`completion-auditor` will rewrite it at the end of this run).

**Capture the change baseline** for the later change-scoped proof
(`/board-flow:prove`). Before any code is written, record the current commit as
this card's baseline: run `git rev-parse HEAD` and write
`.claude/cards/$ARGUMENTS.yaml`:

```yaml
card: <jira-key>
base_commit: <SHA from git rev-parse HEAD>
```

Create `.claude/cards/` if absent. For a bug fix this baseline is doubly
important: `proof-reviewer` uses it to confirm the regression test goes **red at
`base_commit`** (test present, fix reverted) — the proof that the test actually
captures the bug. If this is not a git repo or `git` is unavailable, skip
silently and note it.

Read `defaults.status_map.in_progress` from `board-flow.yaml`. Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Transition $ARGUMENTS to status `<defaults.status_map.in_progress>`.

### 4. Run reproduce-fix-verify

**Invoke the command, don't hand the whole flow to a lead.** Run
`/<default_topology>:reproduce-fix-verify` with the card description verbatim:

> /`<default_topology>`:reproduce-fix-verify The bug described in Jira card $ARGUMENTS. Card content (verbatim): <paste content from step 1>.

That command is the orchestrator of the reproduce → fix → verify phases: it
drives `engineering-lead` one phase at a time (qa-engineer writes the failing
regression test first; the right dev-worker — domain-dev / api-dev / adapter-dev
based on the affected layer — makes the minimum change to pass; qa-engineer
re-runs `./mvnw verify` with green-build evidence; code-reviewer approves).
NOT-A-BUG is a valid outcome if reproduction reveals the code already handles
the case.

Do NOT collapse this into a single `Task` that tells `engineering-lead` to "run
the whole flow," and **never** invoke any lead with `isolation: "worktree"`. A
worktreed lead loses the `Task` tool in CC 2.1.x (the `lead-no-worktree` hook in
`common` blocks it), and a one-shot "do everything" delegation turns the lead
into a solo do-it-all agent that can't reach its workers — see the "Worktree
policy" section in `reproduce-fix-verify.md` and `cc_plugin_quirks.md`.

The command reports back: reproducer test path, fix commit SHA, paths touched,
verdict (READY-TO-SHIP / READY-WITH-CAVEATS / BLOCKED / NOT-A-BUG). Wait for it.

### 5. Transition based on verdict

#### READY-TO-SHIP or READY-WITH-CAVEATS

**Acceptance precondition.** The reproduce-fix-verify report must include a
`completion-auditor` verdict of COMPLETE and the `.claude/acceptance/$ARGUMENTS.yaml`
path. If the audit is INCOMPLETE (or absent), do NOT transition — report the open
gap and stop; the card stays in `in_progress` until the missing altitude test
lands. (Even if you tried to transition anyway, the `acceptance-gate` hook in
`common` reads the artifact and blocks the `transitionJiraIssue` call while
status != complete — this precondition just fails earlier and more clearly.)

Build the Implementation Summary from the reproduce-fix-verify report (reproducer test path, fix commit SHA, paths touched, qa-engineer's BUILD SUCCESS evidence, and the acceptance artifact path). Read `defaults.status_map.in_review` from `board-flow.yaml`.

Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Transition $ARGUMENTS to status `<defaults.status_map.in_review>` with the Implementation Summary below. Post the summary as a comment first, then run the transition.
>
> ```markdown
> ## Implementation summary (bug fix)
>
> **Reproducer:** <failing test path that now passes>
>
> **Fix:** <paths touched, one line per>
>
> **Build verification:** `./mvnw <scope> verify` → BUILD SUCCESS (commit `<SHA>`)
>
> **Acceptance:** completion-auditor COMPLETE — each criterion demonstrated at its altitude (e.g. `POST /api/v1/x → 422` via `<endpoint test>`). Artifact: `.claude/acceptance/<KEY>.yaml`.
>
> **New debt introduced:** <none, or list, each with a revisit trigger>
>
> **Revisit trigger:** <required when debt is anything other than none/unknown — the condition that brings it back into view; `Closure condition:` optional>
>
> **Scope captured outside the card:** <none, or findings captured as follow-ups — never silently absorbed into the fix>
>
> **Release needed:** <no, or yes: what and why>
>
> **Human validation route:** <if the bug was user-visible: command/URL + expected observation + fail condition to confirm the symptom is gone; if internal: "not applicable (internal substrate — regression test above suffices)">
>
> **Caveats / follow-ups:**
> - <none, or caveats from READY-WITH-CAVEATS verdict>
> ```

The four explicit-null fields are mandatory even when negative — the summary-nulls-gate hook blocks the comment without them. For a user-visible bug, the route is the human replaying the original symptom; green regression tests support the fix but do not replace that check.

#### NOT-A-BUG

The reproduction failed because the code already handles the case. This is a valid outcome — confirming a non-bug is not a wasted run.

Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Add a comment to $ARGUMENTS:
>
> "[automated] /board-flow:fix concluded NOT-A-BUG. Reason: <one-line evidence from reproducer attempt>. The reported behavior could not be reproduced; the code at `<file:line>` already handles the case. Suggest closing as 'Cannot Reproduce' or 'Not a Bug' — leaving status decision to the reporter."
>
> Do NOT transition. Leave status decision to the human.

#### BLOCKED

Leave the card in `defaults.status_map.in_progress`. Delegate to `atlassian-expert`:

> Topology: `<default_topology>`.
>
> Add a comment to $ARGUMENTS with the blocker reason and any failing-test paths. Do NOT transition.

## Report

A single concise message back to the user:

- **Card:** $ARGUMENTS Jira link + title.
- **Card status before:** (e.g., "To Do," "Backlog").
- **Issue type:** Bug.
- **Reproducer:** test path that captures the bug (or `NOT-A-BUG` with evidence).
- **Fix:** commit SHA + paths touched (or "n/a — NOT-A-BUG").
- **Verdict:** READY-TO-SHIP / READY-WITH-CAVEATS / NOT-A-BUG / BLOCKED.
- **New card status:** In Review / still In Progress (BLOCKED) / unchanged (NOT-A-BUG).
- **Notes:** caveats, follow-ups, or "the reported behavior wasn't reproducible — close as not-a-bug?"

Then close with **"And now?"** — the report says what *was done*; this says what
*is left*. Without it the two plausible answers ("validate it by hand" and "pull
the next card") compete in silence. Two lines, always both:

- **Left for you:** the card's **Human validation route** verbatim, when it is a
  real route. On a bug this is rarely null — a user-visible symptom is exactly
  what a green regression test cannot close alone. If it *is* the explicit null,
  say so plainly rather than staying quiet. Add any other human-only leftover.
- **Next in the plan:** read `<programs>/<project_key>/plan.yaml` (schema
  `common/plan-schema.yaml`, `mode: single-track`) and name the next `pending`
  item not `blocked_by` an unfinished one — key, title, and its `why`. Mark the
  card just fixed as `done` there, carrying its Human validation route into
  `human_pending`. No plan file? Say so and offer `/board-flow:triage`; do not
  invent an order from the board's default sort.

  `<programs>` = `<main-root>/.claude/programs`, where `<main-root>` is the
  parent of `git rev-parse --git-common-dir` with the trailing `/.git` removed
  — the MAIN clone when you are in a linked worktree. Resolving the plan
  against the current tree instead loses it (`docs/execution-plan.md`,
  "Where the file lives").

## Constraints

- **The card MUST exist** — atlassian-expert returns an error otherwise; abort gracefully.
- **No planning enrichment phase.** The failing test is the spec for bugs; we don't run `planning-lead` decomposition here. If the card lacks repro details, comment-back-and-pause is the right behavior — let the human fix the card.
- **No worktree at any layer** by default (per the underlying `reproduce-fix-verify` flow). Single fix, one worker, no parallelism.
- **NOT-A-BUG is a valid outcome** — confirming a non-bug is honest. Don't fabricate a fix just because the flow expects one. Surface clearly to the user and to the Jira card.
- **scope-discipline is mandatory.** The dev worker does NOT do unrelated cleanup, even if they spot it. Flag for follow-up; don't silently include.
- `atlassian-expert` is the only Jira write path.
