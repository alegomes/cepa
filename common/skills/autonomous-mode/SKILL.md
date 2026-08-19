---
name: autonomous-mode
description: Use when the user has invoked /common:autonomous-start, when CLAUDE_AUTONOMOUS_RUN_ID is set in the environment, or when the user explicitly says they want autonomous / unattended operation ("go autonomous", "I'll be away", "don't ask me, just decide"). Triggers a session-wide behavioral discipline: no questions to the user, every ambiguous decision logged with rationale, state checkpoints are written automatically by hook.
---

# Autonomous mode

You are operating in **autonomous mode**. The user has stepped away. Your job is to make progress without bouncing back to them, while leaving a clear audit trail they can review when they return.

## Rules

### 1. Never ask the user a question.

Not "should I do X or Y?", not "is this the right approach?", not "want me to continue?". Decide and continue. The exception is **catastrophic ambiguity** — e.g., the user's request literally has two contradictory interpretations and you can't infer from context which one they meant. In that case, document both interpretations in `docs/autonomous/<run-id>/state.yaml` under `blockers`, pick the more conservative one, and proceed. Tell them in the final report.

### 2. Log decisions worth the user's time — using the literal Decision block.

Not every choice you make during a run is a Decision. **The threshold for logging matters.** Logging too much creates noise the user can't engage with; logging too little loses signal.

**What counts as a Decision worth logging:** the trade-off crosses a Task boundary — i.e., the choice affects something OUTSIDE your immediate implementation lane. Concretely:

- **Scope** — should this Story include X, defer X, or drop X.
- **Contract** — API shape, request/response schema, error codes, public method signatures, OpenAPI changes.
- **Spec** — behavior visible to users or to other services (validation rules, status transitions, ordering guarantees, retry semantics).
- **Cross-lane interaction** — the choice affects another worker's work (domain port shape that adapter-dev will implement, test fixture shape that qa-engineer will use).
- **Naming** — public-facing names: endpoint paths, field names in DTOs, table/column names, event types. Internal names don't count.
- **Strategy** — rename strategy (big-bang vs deprecation), migration approach, breaking-change handling.

**What does NOT count** (don't log these):

- Local code organization (where to extract a method, which package a class lives in).
- Library/framework micro-choices that any competent engineer would resolve the same way (Optional<T> vs nullable T, StringBuilder vs concat, buffer size).
- Test-internal choices (wiremock vs Testcontainers, fixture filenames, assertion granularity) — unless the choice changes what the test covers, in which case it's a Spec decision.
- Pattern application (this is a Builder, that's a Factory) — unless the choice has user-visible consequences.
- Anything you'd resolve identically next week without re-deliberating.

In short: if the answer to "would a competent peer in my role resolve this the same way?" is "yes, almost certainly" — it's not a Decision. Just do it.

**Block format (when you do log):**

```markdown
### Decision: <one-line topic>

**Altitude:** <strategic|tactical|implementation>   ← exatamente uma destas três palavras

**Options considered:**
- Option A: <description> — pros: ... | cons: ...
- Option B: <description> — pros: ... | cons: ...

**Chosen:** Option <X>

**Rationale:** <why this option, what trade-off you accepted, what evidence supported it>
```

**Altitude field** classifies WHO should review the decision at debrief time. It
is a closed vocabulary of exactly three words — never a free-text description of
what the decision is about. The subject of the decision belongs in the heading
(`### Decision: <topic>`); writing it here ("contract", "schema", "retention")
looks harmless and silently disables the debrief filter, which matches on these
three literals. Measured on 2026-08-19: four autonomous runs wrote 57 decision
blocks, 51 of them carried a free-text word in this field across 35 distinct
values, and the debrief consequently offered the owner 3 decisions — all from
the first card — while the highest-consequence ones stayed invisible. The
`decision-altitude-gate` hook now blocks the write, so this can only be a
transient mistake:

- **`strategic`** — user / product / external-contract concerns. Scope, breaking changes, public naming, spec semantics, deferrals. The user reviews these at debrief.
- **`tactical`** — orchestrator / lead concerns. Task decomposition, integration seams, merge strategy, dependency curation. Lead reviews; user may audit if interested.
- **`implementation`** — worker-internal concerns that still crossed the "wouldn't a peer resolve identically?" line for some reason (rare). Logged for completeness but **debrief skips by default**; surfaced only with `--all`.

When in doubt between `strategic` and `tactical`: prefer `tactical`. The user can opt to see them; defaulting to flooding their attention is worse than defaulting to silence with an audit trail they can pull on demand.

**Format is non-negotiable.** `/common:debrief` matches on the literal `### Decision:` heading and the four labeled fields (`**Altitude:**`, `**Options considered:**`, `**Chosen:**`, `**Rationale:**`). Inline prose like "I decided X because Y" is **insufficient** — debrief either misses it entirely (no audit trail) or reduces to fragile heuristics (less signal in the reinforcement loop).

**Backward compat:** older Decision blocks without the `**Altitude:**` field will be treated as `tactical` by debrief (a reasonable default — they were probably worth surfacing but not necessarily user-facing).

**Single-option decisions still get logged when they're worth logging.** If only one approach was viable AND the trade-off crosses a Task boundary (per the criteria above), write the block with `**Options considered:** Only one viable approach: <X>. Alternatives rejected because <reason>.` Don't log single-option decisions for internal implementation choices.

**Multi-artifact decisions:** if the choice affects multiple artifacts (e.g., api-dev's RESULT.md and adapter-dev's), log the full block once in the most central artifact and add a one-line reference in the others: `> See decision "<topic>" in <path>:<heading>`.

**Path-locked workers:** if you can't write to any of `docs/**` / `spec/**` / TASK.md / RESULT.md paths, include a `### Decision: ...` block as text in your reply to the lead (with the full canonical format above), explicitly labeled `Decisions to transcribe:`. The lead is responsible for persisting it to a path it can write (e.g., into the TASK.md / RESULT.md). This isn't a workaround — it's the protocol. Worker reports up; lead transcribes. Decisions that stay only in chat replies are lost at session end.

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
