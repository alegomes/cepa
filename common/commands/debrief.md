---
description: Walk through every autonomous-mode decision from a run with the user — keep / overrule / refine each one. Verdicts get written to the relevant agent's expertise file as feedback so future autonomous runs by that agent are biased toward the user's preferences. Run after /common:autonomous-resume reports a completed run, or anytime you want to review what the team decided while you were away.
argument-hint: [run-id]   (defaults to most recent completed-but-not-debriefed run)
---

# /common:debrief

## Purpose

Human-in-the-loop reinforcement. The autonomous run logged every ambiguous decision with rationale. This command surfaces them one at a time, takes the user's verdict, and writes overruled / refined entries to the relevant agent's `<agent>-mental-model.yaml` so the agent reads them on its next boot — biasing future decisions toward what the user actually wants.

It's not real RL (no weight updates), it's persistent-context reinforcement. In practice that's enough.

## Variables

- `$ARGUMENTS` — the run-id, or empty for "most recent completed-but-not-debriefed run."

## Instructions

You are the orchestrator. Drive the user through every decision in the run. **You may ask the user questions in this command — debrief is the explicit human-in-the-loop ceremony.** The autonomous-mode skill does NOT apply here.

## Workflow

### 1. Resolve run-id

If `$ARGUMENTS` is empty:

- List `docs/autonomous/*/state.yaml`.
- Filter to `status: completed` AND not `debriefed`.
- Pick most recent. If zero match → reply: "No runs awaiting debrief. Use `/common:debrief <run-id>` to debrief a specific run, or check `docs/autonomous/`." Stop.

### 2. Collect every Decision — formal first, then drift-detect.

Walk every artifact produced during the run. The state file's `log` lists subagent calls; from those, infer the artifacts touched (`docs/tasks/<story>/**`, `docs/investigations/**`, RESULT.md siblings, MERGE.md, the spec file). Read each.

**Pass A — formal scan.** Extract every block matching the canonical pattern:

```markdown
### Decision: <topic>

**Options considered:** ...
**Chosen:** ...
**Rationale:** ...
```

Tag each with: which agent wrote it (from the artifact's owner per path-lock rules), which Task / phase it belongs to, the artifact's path.

**Pass B — drift detection.** Re-scan the same artifacts looking for *informal* decision content the agent failed to put in a Decision block. Heuristics for "decision-like prose":

- Sentences containing "I decided", "I chose", "we went with", "opted for", "picked X over Y", "rejected", "trade-off was".
- Bullet lists with explicit pros/cons that aren't inside a Decision block.
- Sections titled "Choice", "Approach", "Rationale" (lowercase or otherwise) without the formal heading.

For each candidate, capture: artifact path, line range, the prose, and a one-line guess at what the topic + chosen option was.

**Compare the two passes:**

- If formal count == informal count → the agent was disciplined. Proceed normally.
- If informal > formal → **format drift**. Surface this loudly to the user (see step 3).
- If both are zero → reply: "Run `<run-id>` had no logged decisions. Either it was simple work without ambiguity, or the agents skipped the logging discipline. No debrief needed." Mark `status: debriefed` in state.yaml. Stop.

### 3a. Surface format drift (only when informal > formal)

Before walking individual decisions, tell the user:

> **Format drift detected.** The autonomous-mode skill requires every decision to use the formal `### Decision:` block (`Options considered` / `Chosen` / `Rationale`). This run has F formal blocks and I informal decision-like passages — the agents drifted from the format for at least (I - F) decisions.
>
> Your verdict on the drift itself counts as feedback. Want me to:
> - record a `principle`-tagged feedback entry on each agent that drifted, telling them "use the formal Decision block, no inline prose"? (recommended)
> - skip the format feedback and only walk individual decisions? (you'll see the drift again next run)

If the user picks "record": for each agent that produced informal-only decisions, append to `common/expertise/<agent>-mental-model.yaml` under `feedback`:

```yaml
- run_id: <run-id>
  date: <YYYY-MM-DD>
  topic: format compliance
  user_verdict: overrule
  user_reason: "Used inline prose for decisions instead of the required ### Decision: block. Future runs MUST use the formal block — Options considered / Chosen / Rationale — even for single-option decisions."
  tag: principle
```

`principle`-tagged entries are exempt from the 20-entry auto-prune cap. Then proceed to step 3b walking each decision (formal + informal alike).

### 3b. Walk decisions one at a time

For each decision (formal blocks first, then informal-detected passages, in chronological order — read order = run order):

> **Decision N of M** (agent: `<agent>`, in `<artifact path>`)
>
> **Topic:** <topic>
>
> **Options:**
> - A: <description>
> - B: <description>
>
> **Chosen:** <which option>
> **Rationale:** <verbatim>
>
> Verdict?
> - `keep` — the call was right.
> - `overrule: <reason>` — wrong call; tell me what you would have done and why.
> - `refine: <new rationale>` — right call but the rationale needs sharpening.
> - `skip` — defer; we'll come back to this one.

Wait for the user's response. Parse the verdict. Don't infer.

### 4. Persist verdicts

For each decision, append an entry to `common/expertise/<agent>-mental-model.yaml` under a `feedback` section (create the section if it doesn't exist):

```yaml
feedback:
  - run_id: <run-id>
    date: <YYYY-MM-DD>
    topic: <topic>
    original_choice: <Option X — description>
    user_verdict: keep | overrule | refine
    user_reason: <verbatim from user, or "(no reason given)">
    refined_rationale: <only present if verdict was 'refine'>
    tag: principle | example   # default: example. user can override.
```

Cap entries per agent at **20**. When at cap, prune the oldest non-`principle` entries first; never auto-prune `principle`-tagged entries.

The agent reads this file at boot via the `mental-model` skill. Future autonomous runs see "user overruled X in similar situation; consider Y instead."

### 5. Mark the run debriefed

Update `docs/autonomous/<run-id>/state.yaml`:

```yaml
status: debriefed
debriefed_at: <ISO 8601>
debrief_summary:
  decisions_total: M
  formal_blocks: F          # passed Pass A
  informal_detected: I      # found by Pass B heuristics only
  format_drift: <true|false>  # true if I > F
  kept: K
  overruled: O
  refined: R
  skipped: S
```

### 6. Final report

A single concise summary:

- **Run:** `<run-id>`
- **Decisions reviewed:** M (kept K, overruled O, refined R, skipped S)
- **Format compliance:** F formal blocks / I informal-only. If `format_drift: true`, add: "Recorded `principle` feedback on N agent(s) for the next run."
- **Updated expertise files:** list of `<agent>-mental-model.yaml` paths.
- **Skipped decisions:** if any, list them so user can return later.

## Constraints

- **Don't paraphrase the user's verdict.** If they wrote "wrong, we don't use Lombok in this project", that exact reason gets written to the feedback entry. The next autonomous run reads it verbatim; paraphrasing loses signal.
- **Skipped decisions stay in the artifacts** but don't get a feedback entry. The user can re-run debrief later targeting just the skipped ones (future enhancement; not in scope yet).
- **Never auto-overrule.** The user's verdict is required. If they didn't answer clearly for a decision, treat it as `skip`, not `keep`.
- **One decision at a time.** Don't batch the whole list and ask for verdicts en masse — the point is forced reflection on each.
