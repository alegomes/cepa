# Autonomous mode

For when you want the agent team to keep working while you step away.
Five pieces:

- **Skill `autonomous-mode`** — behavioral discipline (no questions to
  the user, every ambiguity logged with rationale).
- **`/common:autonomous-start`** — entry point, generates run-id,
  dispatches into the topology flow.
- **PostToolUse hook `autonomous-checkpoint.py`** — out-of-band state
  writes after every subagent call. Orchestrator cannot forget.
- **`/common:autonomous-resume`** — picks up after compaction / session
  restart from `docs/autonomous/<run-id>/state.yaml`.
- **`/common:debrief`** — human-in-the-loop ceremony to review
  decisions and feed verdicts back into agent expertise.

## Lifecycle at a glance

```
                /common:autonomous-start
                          │
                          ▼
            generates run-id + state.yaml
                          │
                          ▼
          (optional) Jira: transition to In Progress
                          │
                          ▼
             dispatches into topology flow
                          │
                          ▼          ← autonomous-checkpoint hook
       per-Task quality loop          appends to state.yaml.log
                          │            after every subagent call
                          ▼
       (token limit hit?)─yes──→ session ends; resume later via
                          │     /common:autonomous-resume
                          no
                          ▼
              (optional) Jira: In Review with Implementation Summary
                          │
                          ▼
             /common:debrief — verdict each decision
                          │
                          ▼
        decisions land in <agent>-mental-model.yaml as feedback
```

## The state file

`docs/autonomous/<run-id>/state.yaml` is the authoritative source of
truth for the run. The orchestrator does not own the writes;
`autonomous-checkpoint.py` (PostToolUse on Task) appends entries
after every subagent call.

Shape:

```yaml
schema_version: 1
run_id: 2026-05-09-wego-1567
topology: build-hex
flow: plan-build-validate
jira_key: WEGO-1567                  # null if not Jira-tracked
started_at: 2026-05-09T08:15:00Z
description: |
  Implement /users endpoint returning current user's profile
status: in-progress | completed | blocked | debriefed
blockers:
  - { task: 3, reason: "missing X cred" }
log:
  - timestamp: 2026-05-09T08:16:12Z
    subagent: build-hex:planning-lead
    prompt_summary: "Produce one-page spec for /users endpoint..."
    result_summary: "Wrote spec/users-endpoint.md. Decomposed into 4 Stories..."
    exit_status: ok
  # ... many more entries from the checkpoint hook ...
```

Run-id format: `<YYYY-MM-DD>-<slug>`. If a Jira key is in the
description, the slug is the key lowercased (e.g.,
`2026-05-09-wego-1567`) so state file ↔ card correlation is direct.

## The autonomous-mode skill

Activated by `/common:autonomous-start`. It is a session-wide behavioural override with six
rules. The rules, the exact Decision block format and the list of what not to log live in
[`common/skills/autonomous-mode/SKILL.md`](../common/skills/autonomous-mode/SKILL.md), which
is the source of truth. In short:

1. **Never ask the user a question.** Decide and continue. Only a truly contradictory request
   becomes a blocker, resolved conservatively and surfaced in the final report.
2. **Log the decisions worth your time, in the literal `### Decision:` block.** Not every
   ambiguous choice: only the ones that cross a Task boundary (scope, contract, public
   naming, strategy). The block carries an `**Altitude:**` field, and the
   `decision-altitude-gate` hook refuses a block without it. `/common:debrief` matches on
   that format.
3. **Don't fabricate green builds.** If a build cannot run, the verdict is BLOCKED, never an
   optimistic PASS.
4. **Blocked work does not stop independent work.**
5. **The state file is maintained by the hook, not by the agent.**
6. **End cleanly.** Write the final summary in the response and stop. Don't loop.

## The checkpoint hook

`common/hooks/autonomous-checkpoint.py` runs as a PostToolUse hook on
the `Task` tool. When `CLAUDE_AUTONOMOUS_RUN_ID` is set in the
environment, it appends a log entry to `state.yaml` after every
subagent call: timestamp, subagent name, prompt summary (truncated
~200 chars), result summary (truncated), exit status.

Outside autonomous mode (env var unset), the hook is a fast no-op.

Failures are stderr-warnings, never blocking — a malformed state file
must never break the workflow.

## Resume after session interruption

Two common interruption scenarios:

- **Auto-compaction mid-run.** CC summarizes the conversation when
  context fills. The orchestrator's mental model resets, but the state
  file on disk survives.
- **Session crash / new session.** You closed the terminal. New
  session, no in-conversation context.

In both cases:

```
/common:autonomous-resume
```

Defaults to the most recent in-progress run. Reads the log, reconstructs
topology + flow + last position, re-activates the `autonomous-mode`
skill, re-dispatches into the active flow at the next pending step.

What resume **won't** do:

- Re-transition a Jira card to In Progress (it's already there from the
  initial `/autonomous-start`).
- Re-run completed Tasks (artifacts on disk are authoritative; if a
  TASK.md says APPROVED in its Decisions block, trust it).
- Fabricate progress on ambiguous state. If the log doesn't clearly
  identify a next step, resume reports what it found and stops.
- Auto-unblock external blockers (missing creds, system down). Those
  stay listed; the user resolves them and re-runs resume.

## Debrief: closing the loop

After a run completes, `/common:debrief` walks the run's `strategic`
Decision blocks (those whose `**Altitude:**` field says `strategic`: scope,
contract, breaking change, public naming) and asks for your verdict. Pass
`--all` to also walk the `tactical` and `implementation` ones:

- **`keep`** — the agent's call was right.
- **`overrule: <reason>`** — wrong call; tell it what you'd have done
  and why. Goes into the agent's expertise file under `feedback`.
- **`refine: <new rationale>`** — right call, weak rationale. New
  rationale replaces the original.
- **`skip`** — defer.
- **`batch-keep`** (only available with `--all`) — keep this AND all
  remaining tactical/implementation decisions in a single sweep with
  reason "batch-keep — debrief pace decision: only strategic gets
  individual review". Strategic decisions continue being walked
  individually. Useful when the tactical/implementation pile is
  mostly fine and going one-by-one wastes attention.

Verdicts get written to `common/expertise/<agent>-mental-model.yaml`:

```yaml
feedback:
  - run_id: 2026-05-09-wego-1567
    date: 2026-05-09
    topic: "Rename strategy — big-bang vs deprecation window"
    user_verdict: refine
    user_reason: "We don't have active clients yet. Time to keep the house clean."
    refined_rationale: "When no active external clients, prefer big-bang rename..."
    tag: principle
```

The agent reads its expertise file at boot via the `mental-model`
skill. Future runs see your verdict and bias toward your preference.
This is the reinforcement loop — not weight updates, but persistent
context.

### Format drift detection

If agents wrote decisions as inline prose instead of formal `###
Decision:` blocks, `/common:debrief` detects the drift via a heuristic
second-pass scan and offers to record a `principle`-tagged feedback
entry on the offending agent: "use the formal block, no inline prose."
`principle`-tagged entries are exempt from the 20-entry auto-prune cap.

### Pruning

Each agent's `feedback` list caps at **20 entries**. When at cap, the
debrief command prunes the oldest non-`principle` entries first;
`principle`-tagged entries never auto-prune.

## Jira-tracked autonomous runs

If a Jira key is in `$ARGUMENTS` and `board-flow.yaml` exists,
`/common:autonomous-start` wraps the run with full lifecycle:

1. **Step 7 — In Progress transition.** Posts a comment with the run-id
   and state file path; transitions to `status_map.in_progress`. If
   `atlassian-expert` returns BLOCKED (card already advanced, MCP auth
   dropout), records the blocker but continues the flow — work is more
   valuable than ceremony.
2. **Step 9 — In Review transition.** On flow completion, assembles
   the Implementation Summary (files touched, BUILD SUCCESS evidence,
   caveats, run-id reference) and delegates to `atlassian-expert` to
   post the comment then transition.
3. **On BLOCKED flow exit.** Card stays in `in_progress` with a
   blocker comment naming the reason and pointing to `state.yaml`.

Override with `--no-jira` if you want unattended without Jira wrapping.

## What this protects against vs. doesn't

**Protects:**
- Token-limit interruptions mid-run (state file + resume).
- Forgetting what was decided (debrief surfaces every Decision).
- Drift between runs (feedback entries bias future decisions).

**Doesn't protect:**
- A genuinely wrong topology choice (the run will execute the wrong
  flow).
- Bad initial requirements (autonomous mode doesn't add product
  judgment; garbage in, garbage out).
- Build infrastructure breakage (mvnw broken, MCP down). Those surface
  as blockers; user resolves on return.
