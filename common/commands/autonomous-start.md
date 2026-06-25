---
description: Start an autonomous (unattended) run on whichever topology this project is wired to. Reads .claude/topology to dispatch into the right plan-build-validate / reproduce-fix-verify / investigate flow. If a Jira key (e.g. WEGO-1234) appears in the description and jira-flow.yaml exists, also wraps the run with Jira lifecycle: transitions to In Progress before work, and to In Review with an Implementation Summary comment after. Generates a run-id, writes state, activates autonomous-mode, and dispatches.
argument-hint: [--topology=NAME] [--flow=plan-build-validate|reproduce-fix-verify|investigate] [--no-jira] <task description, may include a Jira key like WEGO-1234>
---

# /common:autonomous-start

## Purpose

Kick off an unattended run. The team works without asking you questions, decides ambiguities itself (logging rationale), and survives token-limit hits via a state file that `/common:autonomous-resume` can read back.

## Variables

- `$ARGUMENTS` — the task description. May be prefixed with `--topology=NAME` and/or `--flow=NAME` flags. The description after the flags is what you'd normally pass to `plan-build-validate` / `reproduce-fix-verify` / `investigate`.

## Instructions

You are the orchestrator. Apply `till-done` and `scope-discipline` per usual. Activate the `autonomous-mode` skill for the rest of the session — it overrides the default ask-the-user-when-uncertain behavior.

## Workflow

### 1. Resolve topology

Parse `--topology=NAME` from `$ARGUMENTS` if present. Otherwise read `.claude/topology` (a one-line text file with the topology name).

If neither flag nor file exists:

> Reply with: "No topology configured. Run `bin/install.sh --topology=NAME` from the plugin repo (NAME = `hex-backend` | `multi-team` | `discovery` | `build-solo`), or pass `--topology=NAME` to this command. Aborting." Stop.

If the topology name doesn't match any installed plugin, surface that and abort. Don't guess.

### 2. Resolve flow

Parse `--flow=NAME` from `$ARGUMENTS` if present. Otherwise infer from the description:

- Mentions of "bug", "broken", "fails", "error", "regression" → `reproduce-fix-verify`.
- Mentions of "investigate", "look into", "not sure", "might be", "is X duplicated", "why does Y" → `investigate`.
- Anything else → `plan-build-validate` (default).

If the chosen flow doesn't exist for the chosen topology (e.g., `discovery` doesn't have `reproduce-fix-verify`), surface and abort with a one-line explanation.

### 3. Resolve Jira tracking

Detect a Jira key in `$ARGUMENTS` using regex `[A-Z]{2,}-\d+`. If multiple match, take the first.

If a key is found AND `--no-jira` is not set AND `jira-flow.yaml` exists at project root (or legacy `.claude/jira-flow.lifecycle.yaml`):

- Set `jira_key = <found-key>`. The run will be Jira-tracked: this command will transition the card to **In Progress** before dispatching the flow, and to **In Review** with an Implementation Summary comment after the flow returns.
- If `jira-flow@alegomes` plugin is NOT installed (no `atlassian-expert` agent available), surface that as a soft warning ("Jira key detected but jira-flow not installed; running without lifecycle wrapping") and proceed without Jira tracking.

If no key found OR `--no-jira` is set OR `jira-flow.yaml` is missing: `jira_key = null`. The run is not Jira-tracked. (Note this in the final report.)

### 4. Generate run-id

Format: `<YYYY-MM-DD>-<short-slug>` where short-slug is a 3-5 word kebab-case summary of the description. Example: `2026-05-06-overlapping-endpoints`. If a Jira key is set, prefer `<YYYY-MM-DD>-<jira-key-lowercase>` (e.g., `2026-05-09-wego-1567`). If a state file with that id already exists, append `-2`, `-3`, etc.

### 5. Write initial state file

Write `docs/autonomous/<run-id>/state.yaml`:

```yaml
schema_version: 1
run_id: <run-id>
topology: <topology>
flow: <flow>
jira_key: <key or null>
started_at: <ISO 8601 timestamp>
description: |
  <verbatim task description, with flags stripped>
status: in-progress
blockers: []
log: []
```

Create the directory if it doesn't exist.

### 6. Export run-id

Run a Bash command to write the run-id to a session-local marker file at `docs/autonomous/<run-id>/.run-id` AND set `CLAUDE_AUTONOMOUS_RUN_ID=<run-id>` for the rest of this session via `export`. The hook reads the env var; the marker file is a fallback for resume.

### 7. (Conditional) Transition Jira card to "in progress"

If `jira_key` is set, read `defaults.status_map.in_progress` from `jira-flow.yaml` (default `"In Progress"`). Delegate to `atlassian-expert`:

> Transition Jira issue `<jira_key>` to status `<defaults.status_map.in_progress>`. (Use `getTransitionsForJiraIssue` to find the actual transition ID — names vary across projects.)
>
> Add a comment: "[automated] Autonomous run `<run-id>` started — `<topology>:<flow>` flow. Description: `<one-line description, ~80 chars>`. State file: `docs/autonomous/<run-id>/state.yaml`."

If `atlassian-expert` returns BLOCKED (e.g., card already past `in_progress`, transition not available, MCP auth dropout), record the blocker in state.yaml's `blockers` and continue with the flow anyway. The work is more valuable than the lifecycle ceremony — but the user sees the issue in the final report.

### 8. Dispatch

Hand off to the chosen flow's slash command, prefixing the description as if the user had run it directly. Examples:

- topology=hex-backend, flow=plan-build-validate → invoke `/hex-backend:plan-build-validate <description>`
- topology=hex-backend, flow=reproduce-fix-verify → invoke `/hex-backend:reproduce-fix-verify <description>`
- topology=hex-backend, flow=investigate → invoke `/hex-backend:investigate <description>`
- topology=multi-team, flow=plan-build-validate → invoke `/multi-team:plan-build-validate <description>`
- topology=discovery, flow=investigate → invoke `/discovery:investigate <description>` (when/if it exists)

The autonomous-mode skill is now in effect; the called command's orchestrator inherits the no-questions discipline. The checkpoint hook captures every subagent call.

### 9. (Conditional) Transition Jira card to "in review" with Implementation Summary

If `jira_key` is set AND the flow returned successfully (not blocked at the topology level):

Read `defaults.status_map.in_review` from `jira-flow.yaml` (default `"In Review"`). Assemble the Implementation Summary using the canonical template (from `atlassian-expert`'s "Transition to Review with Implementation Summary" common operation):

```markdown
## Implementation summary

**Files touched:**
- <list from the topology flow's report — paths actually committed>

**Tests added/updated:**
- <list from qa-engineer's output, or N/A for investigate flow>

**Build verification:** `<mvnw command run>` → BUILD SUCCESS (commit `<SHA>`)
  (For investigate flow: "Read-only investigation — no build run. See findings: docs/investigations/<slug>.md")
  (For reproduce-fix-verify: failing test path that now passes + commit SHA)

**Caveats / follow-ups:**
- <validation-lead's caveats, refactor-advisor findings, or "none">

**Autonomous run:** `<run-id>` — see `docs/autonomous/<run-id>/state.yaml` for the full log and `/common:debrief <run-id>` to review decisions.
```

Then delegate to `atlassian-expert`:

> Transition Jira issue `<jira_key>` to status `<defaults.status_map.in_review>` with the Implementation Summary above. Post the summary as a comment first, then run the transition. (atlassian-expert enforces this ordering — comment first, transition second.)

If the flow ended BLOCKED instead, leave the card where it is (in `<defaults.status_map.in_progress>`; if `defaults.status_map.blocked` is set non-null and your project convention is to move blocked cards to it, transition there) and delegate to `atlassian-expert`:

> Add a comment to `<jira_key>` describing the blocker: "[automated] Autonomous run `<run-id>` blocked. Reason: `<one-line>`. See `docs/autonomous/<run-id>/state.yaml` blockers section. Card left in In Progress."

### 10. Final report

When the flow returns, append a final entry to the state file (`status: completed` or `status: blocked`), and reply to the user with:

- **Run id:** <run-id>
- **Topology / flow:** <topology> / <flow>
- **Jira:** `<key>` → moved to In Review (with summary comment) / left in In Progress (blocked) / not Jira-tracked
- **Outcome:** what completed, what's blocked
- **State file:** `docs/autonomous/<run-id>/state.yaml`
- **Decisions made:** count + a pointer to where in the artifacts they live
- **Recommended next step:** `/common:debrief <run-id>` if there are decisions to review, or "safe to ship" if not.

## Constraints

- **Don't dispatch into multiple flows.** One autonomous-start = one flow. If the description spans both a bug and a feature, ask the user (yes — at the very start, before autonomous-mode activates) which to prioritize, and run the other separately later.
- **Don't override the green-build rule.** The skill explicitly preserves it.
- **State file is the source of truth.** Anything the user needs to know about this run lives in `docs/autonomous/<run-id>/state.yaml` or in the artifacts referenced from it. Don't bury status in chat.
- **Jira lifecycle is best-effort, not load-bearing.** If `atlassian-expert` returns BLOCKED on the In Progress transition (e.g., card already advanced past it, transition not available, MCP auth dropout), record the blocker and run the flow anyway. The opposite — refusing to do work because Jira state isn't perfect — would be worse. The In Review transition is conditional on the flow succeeding; a blocked flow leaves the card in In Progress with a blocker comment.
- **No double-tracking.** If the underlying topology flow already transitions the card itself (e.g., user passes a description that explicitly invokes `/jira-flow:execute`), this command will double-transition. autonomous-start dispatches into raw topology commands (`/hex-backend:plan-build-validate`, etc.), which are Jira-agnostic — so this shouldn't happen in practice. If you find yourself running autonomous-start with a `/jira-flow:*` command in the description, drop the slash-command prefix; let autonomous-start own the Jira side.
