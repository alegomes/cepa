---
description: Merge the open PR for the current branch, gated by the QA gate. Finds the PR, runs the QA gate (the topology's proof-reviewer — proves every changed line is load-bearing at the surface), and on PROVEN merges via bitbucket-expert. With auto_merge:true it merges immediately on PROVEN; otherwise it stops at PROVEN and waits for your go-ahead. If jira-flow is wired, also transitions the card In Review → Done.
argument-hint: [pr-id]   (optional: merge this PR id instead of auto-detecting from the current branch)
---

# /review-gate:merge

## Purpose

The second door (Porta 2): **QA**, then merge. This is where "is it correct?" is answered — distinct from `/review-gate:open`, which answered "is it clean?". The QA gate is the heavier, behavior-level check; it lives here, at the merge boundary, by design.

This command owns the QA gate + the merge transport. It does NOT re-run hygiene (that was the open gate's job).

## Variables

- `$ARGUMENTS` — optional PR id. Default: detect the open PR whose source is the current branch.

## Instructions

You are the orchestrator. You delegate the proof (to the topology's `proof-reviewer`) and the Bitbucket call (to `bitbucket-expert`). You do not prove or merge yourself.

### 1. Preconditions

- Read `review-gate.yaml` for `host`, `auto_merge`, `jira` seam, and the merge `strategy`.
- Identify the PR id, in order: `$ARGUMENTS` if given; else the id `/review-gate:open` printed earlier in this session. Auto-detecting the PR from the current branch needs a GET helper that is **not bundled in v1** — if you have no id, ask the user for it (or point them at the PR list). Don't guess an id.

### 2. QA gate

Run the **QA axis**, not hygiene:
- If a topology with a `proof-reviewer` is installed (e.g. `build-hex:proof-reviewer`), delegate the change-driven proof on `base..HEAD` to it. It returns **PROVEN / UNPROVEN / NEEDS-HUMAN**.
- This is the same reviewer `/jira-flow:prove` uses — same gate, different entry point. Do not duplicate the proof logic; delegate to the one reviewer.
- No topology / no proof-reviewer available → there is no QA gate to run. Say so explicitly (don't pretend one passed), fall back to the project's own verify (build/tests green per `.claude/last-build.json`), and treat a missing baseline as NOT proven.

Route the verdict:
- **UNPROVEN** → STOP. Report what failed. Do not merge.
- **NEEDS-HUMAN** → STOP. Surface it for the user; do not merge on your own.
- **PROVEN** → continue.

### 3. Merge (honors auto_merge)

- `auto_merge: true` → on PROVEN, delegate the merge to `bitbucket-expert` immediately (strategy from config). This is "auto-merge on green": the gate passing IS the go-ahead.
- `auto_merge: false` (default) → STOP at PROVEN. Report "QA gate PROVEN — ready to merge" and the exact command/confirmation needed. Merging stays a human decision. Only merge after the user confirms.

`bitbucket-expert` runs `bin/merge-pr.sh` and returns the merged state + URL (or relays a conflict / pending-check / permission error — those are NOT "proven failures", they're transport failures; report them as such).

### 4. Jira seam (only if configured)

If the **jira-flow plugin is installed** AND `review-gate.yaml` has a `jira:` block with `on_merge`:
- After a successful merge, delegate to jira-flow's `atlassian-expert` to transition the card per `on_merge` (e.g. In Review → Done).
- jira-flow not installed (even if a stray `jira-flow.yaml` exists) / no block → skip silently. Don't delegate to an absent `atlassian-expert`.

### 5. Report

Merged PR URL + the QA verdict (PROVEN), the strategy used, and — if applicable — the Jira transition. If you stopped (UNPROVEN / NEEDS-HUMAN / auto_merge off), say exactly why and what the next step is.

## Notes

- Do not touch Bitbucket directly — `bitbucket-expert`'s lane.
- Do not transition Jira directly — `atlassian-expert`'s lane.
- A transport failure (merge conflict, pending required check, no permission) is not a QA failure. Keep the two distinct in the report so the user knows whether to fix code or fix the PR.
