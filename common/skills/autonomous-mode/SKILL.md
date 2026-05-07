---
name: autonomous-mode
description: Use when the user has invoked /common:autonomous-start, when CLAUDE_AUTONOMOUS_RUN_ID is set in the environment, or when the user explicitly says they want autonomous / unattended operation ("go autonomous", "I'll be away", "don't ask me, just decide"). Triggers a session-wide behavioral discipline: no questions to the user, every ambiguous decision logged with rationale, state checkpoints are written automatically by hook.
---

# Autonomous mode

You are operating in **autonomous mode**. The user has stepped away. Your job is to make progress without bouncing back to them, while leaving a clear audit trail they can review when they return.

## Rules

### 1. Never ask the user a question.

Not "should I do X or Y?", not "is this the right approach?", not "want me to continue?". Decide and continue. The exception is **catastrophic ambiguity** — e.g., the user's request literally has two contradictory interpretations and you can't infer from context which one they meant. In that case, document both interpretations in `docs/autonomous/<run-id>/state.yaml` under `blockers`, pick the more conservative one, and proceed. Tell them in the final report.

### 2. For every ambiguous decision, log it.

Whatever artifact is current (TASK.md, RESULT.md, MERGE.md, investigation report, integration spec — whatever you're writing right now), append a block:

```markdown
### Decision: <one-line topic>

**Options considered:**
- Option A: <description> — pros: ... | cons: ...
- Option B: <description> — pros: ... | cons: ...
- (more if relevant)

**Chosen:** Option <X>

**Rationale:** <why this option, what trade-off you accepted, what evidence supported it>
```

If a decision spans multiple artifacts (e.g., the choice affected both api-dev's RESULT.md and adapter-dev's), log it once in the artifact most central to the decision and reference it from the others.

### 3. Don't fabricate green builds.

Autonomous mode does **not** weaken the green-build-evidence rule. qa-engineer still requires `BUILD SUCCESS` output to PASS; engineering-lead still rejects unsubstantiated PASS verdicts; code-reviewer still REJECTs without build evidence. If a build genuinely cannot be run (sandbox, missing deps), the verdict is BLOCKED — not an optimistic PASS to "keep moving."

### 4. Genuine blockers don't stop progress on independent work.

If Task 3 is blocked on external creds, but Tasks 1, 2, and 4 are independent, finish them. Document the blocked Task in the state file (`blockers: [{ task: 3, reason: "missing X cred" }]`). The user resolves blockers when they return; the rest of the work isn't held hostage.

### 5. The state file is maintained by hook, not by you.

`docs/autonomous/<run-id>/state.yaml` is updated automatically after every subagent call by `common/hooks/autonomous-checkpoint.py`. Do not write to it manually. Just keep working; the hook handles the bookkeeping. If you need to record something the hook wouldn't (e.g., a high-level milestone, a blocker, a debriefable decision-with-rationale), put it in the relevant *artifact* (TASK.md, RESULT.md, etc.) — that's what `/common:debrief` reads.

### 6. End the run cleanly.

When the flow finishes (all Tasks APPROVED, integration merged, validation done) — or when you've run as far as you can given blockers — write a final summary as the last entry in your reply to the user. The summary names: what completed, what's blocked and why, where the state file is, and a one-line recommendation ("safe to ship", "needs your input on X", "all blockers documented in state.yaml"). Then stop. Don't loop.

## What this skill does NOT change

- Path-lock rules still apply (workers can only write where their topology says).
- Worktree policy still applies (leads in main, workers may worktree).
- The per-Task quality loop is still mandatory (qa → refactor-advisor → code-reviewer).
- `scope-discipline` still applies (no drive-by refactors, even autonomously).

Autonomous mode is about **who decides**, not about **what's allowed**.
