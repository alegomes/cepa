---
description: Start an autonomous (unattended) run on whichever topology this project is wired to. Reads .claude/topology to dispatch into the right plan-build-validate / reproduce-fix-verify / investigate flow. Generates a run-id, writes the initial state file, activates autonomous-mode, and dispatches. Use when you'll be away and want the team to keep working without you.
argument-hint: [--topology=NAME] [--flow=plan-build-validate|reproduce-fix-verify|investigate] <task description>
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

> Reply with: "No topology configured. Run `bin/install.sh --topology=NAME` from the plugin repo (NAME = `hex-backend` | `multi-team` | `discovery` | `solo-pair`), or pass `--topology=NAME` to this command. Aborting." Stop.

If the topology name doesn't match any installed plugin, surface that and abort. Don't guess.

### 2. Resolve flow

Parse `--flow=NAME` from `$ARGUMENTS` if present. Otherwise infer from the description:

- Mentions of "bug", "broken", "fails", "error", "regression" → `reproduce-fix-verify`.
- Mentions of "investigate", "look into", "not sure", "might be", "is X duplicated", "why does Y" → `investigate`.
- Anything else → `plan-build-validate` (default).

If the chosen flow doesn't exist for the chosen topology (e.g., `discovery` doesn't have `reproduce-fix-verify`), surface and abort with a one-line explanation.

### 3. Generate run-id

Format: `<YYYY-MM-DD>-<short-slug>` where short-slug is a 3-5 word kebab-case summary of the description. Example: `2026-05-06-overlapping-endpoints`. If a state file with that id already exists, append `-2`, `-3`, etc.

### 4. Write initial state file

Write `docs/autonomous/<run-id>/state.yaml`:

```yaml
schema_version: 1
run_id: <run-id>
topology: <topology>
flow: <flow>
started_at: <ISO 8601 timestamp>
description: |
  <verbatim task description, with flags stripped>
status: in-progress
blockers: []
log: []
```

Create the directory if it doesn't exist.

### 5. Export run-id

Run a Bash command to write the run-id to a session-local marker file at `docs/autonomous/<run-id>/.run-id` AND set `CLAUDE_AUTONOMOUS_RUN_ID=<run-id>` for the rest of this session via `export`. The hook reads the env var; the marker file is a fallback for resume.

### 6. Dispatch

Hand off to the chosen flow's slash command, prefixing the description as if the user had run it directly. Examples:

- topology=hex-backend, flow=plan-build-validate → invoke `/hex-backend:plan-build-validate <description>`
- topology=hex-backend, flow=reproduce-fix-verify → invoke `/hex-backend:reproduce-fix-verify <description>`
- topology=hex-backend, flow=investigate → invoke `/hex-backend:investigate <description>`
- topology=multi-team, flow=plan-build-validate → invoke `/multi-team:plan-build-validate <description>`
- topology=discovery, flow=investigate → invoke `/discovery:investigate <description>` (when/if it exists)

The autonomous-mode skill is now in effect; the called command's orchestrator inherits the no-questions discipline. The checkpoint hook captures every subagent call.

### 7. Final report

When the flow returns, append a final entry to the state file (`status: completed` or `status: blocked`), and reply to the user with:

- **Run id:** <run-id>
- **Topology / flow:** <topology> / <flow>
- **Outcome:** what completed, what's blocked
- **State file:** `docs/autonomous/<run-id>/state.yaml`
- **Decisions made:** count + a pointer to where in the artifacts they live
- **Recommended next step:** `/common:debrief <run-id>` if there are decisions to review, or "safe to ship" if not.

## Constraints

- **Don't dispatch into multiple flows.** One autonomous-start = one flow. If the description spans both a bug and a feature, ask the user (yes — at the very start, before autonomous-mode activates) which to prioritize, and run the other separately later.
- **Don't override the green-build rule.** The skill explicitly preserves it.
- **State file is the source of truth.** Anything the user needs to know about this run lives in `docs/autonomous/<run-id>/state.yaml` or in the artifacts referenced from it. Don't bury status in chat.
