---
description: Walk through autonomous-mode decisions from a run with the user — keep / overrule / refine each one. By default surfaces only strategic-altitude decisions (scope, contract, breaking change, user-facing naming); pass --all to include tactical and implementation decisions too. Verdicts get written to the relevant agent's expertise file as feedback so future runs are biased toward your preferences. Run after /common:autonomous-resume reports a completed run.
argument-hint: [run-id] [--all]   (run-id defaults to most recent completed-but-not-debriefed run)
---

# /common:debrief

## Purpose

Human-in-the-loop reinforcement. The autonomous run logged every ambiguous decision with rationale. This command surfaces them one at a time, takes the user's verdict, and writes overruled / refined entries to the relevant agent's `<agent>-mental-model.yaml` so the agent reads them on its next boot — biasing future decisions toward what the user actually wants.

It's not real RL (no weight updates), it's persistent-context reinforcement. In practice that's enough.

## Variables

- `$ARGUMENTS` — `[run-id]` and/or `[--all]`. Run-id may be omitted (defaults to most recent completed-but-not-debriefed). `--all` includes tactical and implementation decisions; without it, debrief walks only `strategic` altitude.

## Instructions

You are the orchestrator. Drive the user through the relevant decisions in the run. **You may ask the user questions in this command — debrief is the explicit human-in-the-loop ceremony.** The autonomous-mode skill does NOT apply here.

## Workflow

### 1. Parse arguments

- Detect `--all` flag (anywhere in `$ARGUMENTS`). If present, `mode = all`; default `mode = strategic-only`.
- Remaining tokens after removing flags are treated as the run-id (or empty).

### 2. Resolve run-id

If no run-id (after flag parsing):

- List `docs/autonomous/*/state.yaml`.
- Filter to `status: completed` AND not `debriefed`.
- Pick most recent. If zero match → reply: "No runs awaiting debrief. Use `/common:debrief <run-id>` to debrief a specific run, or check `docs/autonomous/`." Stop.

### 3. Collect every Decision — formal first, then drift-detect.

Walk every artifact produced during the run. The state file's `log` lists subagent calls; from those, infer the artifacts touched (`docs/tasks/<story>/**`, `docs/investigations/**`, RESULT.md siblings, MERGE.md, the spec file). Read each.

**Pass A — formal scan.** Extract every block matching the canonical pattern:

```markdown
### Decision: <topic>

**Options considered:** ...
**Chosen:** ...
**Rationale:** ...
```

Tag each with: which agent wrote it (from the artifact's owner per path-lock rules), which Task / phase it belongs to, the artifact's path, and **the altitude** (read the `**Altitude:**` field from the block — `strategic`, `tactical`, or `implementation`). Blocks without an Altitude field (legacy or omitted) default to `tactical`.

**Pass B — drift detection.** Re-scan the same artifacts looking for *informal* decision content the agent failed to put in a Decision block. Heuristics for "decision-like prose":

- Sentences containing "I decided", "I chose", "we went with", "opted for", "picked X over Y", "rejected", "trade-off was".
- Bullet lists with explicit pros/cons that aren't inside a Decision block.
- Sections titled "Choice", "Approach", "Rationale" (lowercase or otherwise) without the formal heading.

For each candidate, capture: artifact path, line range, the prose, and a one-line guess at what the topic + chosen option was.

**Compare the two passes:**

- If formal count == informal count → the agent was disciplined. Proceed normally.
- If informal > formal → **format drift**. Surface this loudly to the user (see step 3).
- If both are zero → reply: "Run `<run-id>` had no logged decisions. Either it was simple work without ambiguity, or the agents skipped the logging discipline. No debrief needed." Mark `status: debriefed` in state.yaml. Stop.

### 4. Apply altitude filter

Filter the collected decisions according to the mode parsed in step 1:

- **`mode = strategic-only`** (default): keep only decisions where `altitude == "strategic"`. Set aside tactical and implementation ones — they're still in the artifacts on disk; the user can re-run with `--all` later to revisit.
- **`mode = all`**: keep all decisions regardless of altitude.

Report the filtering result up front before walking. Example:

> **Run `<run-id>` produced M decisions** (F formal + I informal):
> - strategic: S
> - tactical: T
> - implementation: P
>
> Walking S strategic decisions in this debrief. Re-run with
> `/common:debrief <run-id> --all` to include the T tactical + P
> implementation decisions.

If `mode = strategic-only` AND S == 0 (no strategic decisions found): tell the user this run had no user-altitude decisions worth reviewing. Suggest running `--all` if they want to audit the tactical/implementation choices. Mark `status: debriefed` in state.yaml. Stop. (The run's choices live in code + commit messages; no further reinforcement needed at user level.)

If `mode = strategic-only` AND S > 0: proceed to step 5.

If `mode = all` AND there are zero decisions of any altitude: same as step 3's empty-both-passes case — mark debriefed, stop.

### 5a. Surface format drift (only when informal > formal)

Before walking individual decisions, tell the user:

> **Format drift detected.** The autonomous-mode skill requires every decision to use the formal `### Decision:` block (`Options considered` / `Chosen` / `Rationale`). This run has F formal blocks and I informal decision-like passages — the agents drifted from the format for at least (I - F) decisions.
>
> Your verdict on the drift itself counts as feedback. Want me to:
> - record a `principle`-tagged feedback entry on each agent that drifted, telling them "use the formal Decision block, no inline prose"? (recommended)
> - skip the format feedback and only walk individual decisions? (you'll see the drift again next run)

If the user picks "record": for each agent that produced informal-only decisions, append this entry to `common/expertise/<agent>-mental-model.yaml` — via the lock helper described in step 6, **not** by hand-editing the file:

```bash
printf '  - run_id: <run-id>\n    date: <YYYY-MM-DD>\n    topic: format compliance\n    user_verdict: overrule\n    user_reason: "Used inline prose for decisions instead of the required ### Decision: block. Future runs MUST use the formal block — Options considered / Chosen / Rationale — even for single-option decisions."\n    tag: principle' \
  | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/expertise-append.py" \
      --file common/expertise/<agent>-mental-model.yaml --cap 20
```

`principle`-tagged entries are exempt from the 20-entry auto-prune cap. Then proceed to step 5b walking each decision (filtered by altitude per step 4; formal blocks first, then any informal-detected passages that survived the filter).

### 5b. Walk decisions one at a time

For each decision (filtered by altitude per step 4; formal blocks first, then informal-detected passages, in chronological order — read order = run order):

> **Decision N of M** (agent: `<agent>`, altitude: `<altitude>`, in `<artifact path>`)
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
> Verdict — or talk it through first?
> - `keep` — the call was right.
> - `overrule: <reason>` — wrong call; tell me what you would have done and why.
> - `refine: <new rationale>` — right call but the rationale needs sharpening.
> - `skip` — defer; we'll come back to this one.
> - `batch-keep` — keep this AND all remaining tactical/implementation decisions in a single sweep. Reason: "batch-keep — debrief pace decision: only strategic gets individual review". Strategic decisions remain individually reviewed.
> - **or just ask** — not ready to verdict? Ask me anything about this decision (why this option, what the rejected one would have cost, what it touched downstream, how it interacts with another decision) and I'll answer before you decide.

Wait for the user's response, then branch on what they gave you:

- **Terminal verdict** (`keep` / `overrule:` / `refine:` / `skip` / `batch-keep`) → record it (step 6) and advance to the next decision. Don't infer a verdict the user didn't actually give.
- **A question or anything that isn't one of those verdicts** → you're in the **discussion loop**. Answer it, grounded in the run's artifacts — the Decision block itself, the surrounding RESULT.md / spec / MERGE.md, what the chosen option touched downstream, and any related decision the user references. Don't hand-wave; if the artifacts don't say, say so. Then **re-present the verdict prompt for this same decision** and wait again. Stay on this decision — looping through as many questions as the user has — until they give a terminal verdict. Never advance to the next decision off the back of a question.

The discussion loop is not a detour from the ceremony — it *is* the ceremony. Debrief is the one command where you may freely converse with the user (step 0); a decision the user understood before keeping or overruling produces sharper feedback than a reflexive `keep`. If a discussion changes the user's mind, the verdict they land on (`overrule:` / `refine:`) carries the reasoning you surfaced together — capture their words, not your summary (see step 6's verbatim rule).

**`batch-keep` mode** — once the user says `batch-keep` on any tactical or implementation decision, switch to batch-mode for the remainder of that altitude group. Every remaining `tactical` and `implementation` decision auto-keeps with the same reason. Continue walking `strategic` decisions individually (those still need attention). At the end of the walk, the report names how many were batch-kept so the user knows the count.

This mode codifies the observed pattern from wego-1682 and wego-1683 runs: user wants individual review on strategic, but tactical and implementation rarely raise individual reservations and going one-by-one wastes attention. `batch-keep` makes the pattern explicit; user can pick it once and the rest of the lower-altitude walk flows.

**`batch-keep` is only available when `mode = all`** (the default `strategic-only` mode never touches tactical/implementation, so there's nothing to batch). If user says `batch-keep` in `strategic-only` mode, treat as `keep` (strategic still gets individual attention; nothing else to batch).

### 6. Persist verdicts

For each decision walked, append an entry to `common/expertise/<agent>-mental-model.yaml` under its `feedback` section. The entry shape is:

```yaml
  - run_id: <run-id>
    date: <YYYY-MM-DD>
    topic: <topic>
    altitude: strategic | tactical | implementation
    original_choice: <Option X — description>
    user_verdict: keep | overrule | refine
    user_reason: <verbatim from user, or "(no reason given)">
    refined_rationale: <only present if verdict was 'refine'>
    tag: principle | example   # default: example. user can override.
```

**Do not hand-edit the YAML file.** These expertise files are symlinked from the plugin source and shared across every project and every concurrent `claude` session — two debriefs editing the same agent file at once would clobber each other. Append through the lock helper instead, which serializes the write with an `flock` and handles the 20-entry cap for you:

```bash
printf '  - run_id: ...\n    date: ...\n    topic: ...\n    user_verdict: ...\n    user_reason: "..."\n    tag: example' \
  | python3 "${CLAUDE_PLUGIN_ROOT}/hooks/expertise-append.py" \
      --file common/expertise/<agent>-mental-model.yaml --cap 20
```

Pass the item block on stdin exactly as it should appear under `feedback:` (two-space indent, leading `- `). The helper appends it atomically and, when the file would exceed **20** entries, prunes the oldest non-`principle` entries first — `principle`-tagged entries are never auto-pruned. One invocation per entry. (If `${CLAUDE_PLUGIN_ROOT}` isn't set in your shell, use the absolute path to `common/hooks/expertise-append.py`.)

The agent reads this file at boot via the `mental-model` skill. Future autonomous runs see "user overruled X in similar situation; consider Y instead."

### 7. Mark the run debriefed

Update `docs/autonomous/<run-id>/state.yaml`:

```yaml
status: debriefed
debriefed_at: <ISO 8601>
debrief_mode: strategic-only | all
debrief_summary:
  decisions_total: M
  by_altitude:
    strategic: S
    tactical: T
    implementation: P
  formal_blocks: F          # passed Pass A
  informal_detected: I      # found by Pass B heuristics only
  format_drift: <true|false>  # true if I > F
  walked: W                  # how many decisions actually walked (after altitude filter)
  kept: K
  overruled: O
  refined: R
  skipped: S
  batch_kept: B              # how many auto-kept via batch-keep mode
```

Note: if `debrief_mode == strategic-only` and tactical/implementation decisions exist, the run is still considered debriefed for state-tracking purposes. The user can re-run with `--all` later if they want to revisit lower-altitude decisions; the artifacts on disk stay available indefinitely.

### 8. Final report

A single concise summary:

- **Run:** `<run-id>` — mode: `<strategic-only | all>`
- **Decisions in run:** M total (strategic S, tactical T, implementation P)
- **Reviewed this debrief:** W (kept K, overruled O, refined R, skipped Sk, batch-kept B)
- **Format compliance:** F formal blocks / I informal-only. If `format_drift: true`, add: "Recorded `principle` feedback on N agent(s) for the next run."
- **Updated expertise files:** list of `<agent>-mental-model.yaml` paths.
- **Not reviewed (filtered out):** if mode was `strategic-only`, mention the count of tactical+implementation decisions that were skipped and how to re-debrief: `/common:debrief <run-id> --all`.
- **Skipped decisions:** if any (user said `skip` during walk), list them so user can return later.

## Constraints

- **Don't paraphrase the user's verdict.** If they wrote "wrong, we don't use Lombok in this project", that exact reason gets written to the feedback entry. The next autonomous run reads it verbatim; paraphrasing loses signal.
- **Skipped decisions stay in the artifacts** but don't get a feedback entry. The user can re-run debrief later targeting just the skipped ones (future enhancement; not in scope yet).
- **Never auto-overrule.** The user's verdict is required. If they didn't answer clearly for a decision, treat it as `skip`, not `keep`.
- **One decision at a time.** Don't batch the whole list and ask for verdicts en masse — the point is forced reflection on each.
- **Default mode is strategic-only.** If the user wants to audit tactical/implementation decisions, they pass `--all` explicitly. Don't flood their attention with implementation choices by default.
- **Altitude misclassification detection** (optional heuristic): if a Decision block's topic mentions "scope", "spec", "API", "contract", "breaking", "rename", "defer" but `Altitude: implementation` is set, flag it during the walk as "possibly misclassified — likely strategic". Don't auto-promote; surface to user for awareness.
