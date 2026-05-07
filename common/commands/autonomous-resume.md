---
description: Resume an interrupted autonomous run. Reads docs/autonomous/<run-id>/state.yaml, restores topology + flow + last position, re-activates autonomous-mode, and continues from the next pending step. Use after a token-limit hit, a session crash, or when you start a fresh session and want the team to pick up where they left off.
argument-hint: [run-id]   (defaults to most recent in-progress run)
---

# /common:autonomous-resume

## Purpose

Pick up an autonomous run that was interrupted (auto-compaction, session ended, token cap hit, machine restart). The state file on disk is the source of truth; this command reads it and re-dispatches into the active flow at the next pending step.

## Variables

- `$ARGUMENTS` — the run-id, or empty for "most recent in-progress run."

## Instructions

You are the orchestrator. Activate the `autonomous-mode` skill for the rest of this session before doing anything else (the resumed run inherits the same no-questions discipline). Apply `till-done`.

## Workflow

### 1. Resolve run-id

If `$ARGUMENTS` is empty:

- List `docs/autonomous/*/state.yaml`.
- Filter to runs where `status: in-progress` (or `status: blocked` — those can also be resumed if the user has unblocked the external dependency).
- Pick the one with the most recent `started_at`. If multiple match within seconds, prefer the one with the most recent `log` entry timestamp.
- If zero match → reply: "No in-progress autonomous runs found in `docs/autonomous/`. Use `/common:autonomous-start <description>` to start one." Stop.

If `$ARGUMENTS` is a run-id:

- Read `docs/autonomous/<run-id>/state.yaml`.
- If it doesn't exist → reply: "No state file at `docs/autonomous/<run-id>/state.yaml`. Check the run-id." Stop.
- If `status: completed` or `status: debriefed` → reply: "Run `<run-id>` already <status>. Nothing to resume. Run `/common:debrief <run-id>` to review decisions if you haven't." Stop.

### 2. Restore context

From the state file, capture:
- `topology` and `flow` — these tell you which command to re-enter.
- `description` — the original task description.
- `log` (last ~20 entries) — what's been done. Read this carefully.
- `blockers` — what couldn't proceed and why. Don't try to unblock unless the user has explicitly indicated the blocker is resolved.
- The last artifact paths the log mentions (TASK.md / RESULT.md / etc.) — read those to understand where the work left off.

### 3. Reconstruct progress and identify next step

Based on the log + artifacts, decide what's next. Patterns:

- **Last action was a successful APPROVE on Task N of M, with M > N** → continue to Task N+1.
- **Last action was a qa REJECT or BLOCKED** → re-delegate to the responsible dev worker with the prior failure context.
- **Last action was integration merge in progress and incomplete** → continue from the next worker branch to merge.
- **Last action was validation-lead returning a verdict** → flow is done; mark `status: completed` and write final report.
- **Ambiguous (log doesn't clearly identify a next step)** → reply with what you found, the artifacts you read, and a one-line recommendation. Then stop. Do NOT fabricate progress.

### 4. Re-export run-id and resume

Set `CLAUDE_AUTONOMOUS_RUN_ID=<run-id>` for this session (so the checkpoint hook continues logging to the same state file).

Re-enter the active flow's command at the next pending step. Concretely: invoke the relevant subagent (e.g., `<topology>:engineering-lead` for a build-phase resume, `<topology>:validation-lead` for a validation-phase resume) with a prompt that includes:

- The original description.
- A `Resuming from:` block summarizing what's already been done (paths built, Tasks APPROVED, etc.).
- The specific next step you're asking it to take.

Don't re-run completed work. The artifacts on disk are authoritative — if a TASK.md says APPROVED in its Decisions block, trust it.

### 5. Append a resume marker to the state file

Add an entry to the `log` array:

```yaml
- timestamp: <ISO 8601>
  event: resumed
  resumed_by: orchestrator
  resumed_from: <one-line description of last action found>
  resumed_at_step: <the next step>
```

The checkpoint hook will continue from there.

### 6. Final report

Same shape as `/common:autonomous-start`'s final report — outcome, state file path, decisions made, recommended next step.

## Constraints

- **Don't unblock external blockers automatically.** If the state file lists a blocker (missing creds, external system down), don't pretend it's resolved. Surface it in the final report and skip dependent work.
- **Don't mutate the artifacts of completed Tasks.** Their Decisions blocks are part of the audit trail; the user reviews them at debrief time.
- **If the log is unreadable or the state file is corrupted**, reply with what you can salvage and ask the user to confirm intent. This is the one place where asking is OK — corrupted state is catastrophic ambiguity.
