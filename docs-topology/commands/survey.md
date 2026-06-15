---
description: Phase 1 — read-only archaeology of an existing project. Runs the four survey fronts in parallel (Diátaxis inventory · HOW extraction · flow tracing · WHY archaeology) and synthesizes them into docs/_survey/gap-report.md. Touches no source, moves no file. The anchor for the whole effort.
argument-hint: "[optional scope note — e.g. 'focus on the signature flows']"
---

# /docs:survey

## Purpose

Produce the **gap-report** — the source of truth for the documentation overhaul.
Read-only: it classifies what exists, extracts the HOW from code, traces the flows,
and digs the WHY from the record — surfacing where the rationale is genuinely
missing (the owner checkpoint) without inventing any of it.

Run this first. Every later phase reads `docs/_survey/gap-report.md`.

## Variables

- `$ARGUMENTS` — optional scope note to focus the survey (which flows/areas matter
  most). Omit to survey the whole project.

## Workflow

### 1. Confirm the target

Confirm you're at the root of the project to be documented (not the plugin repo).
Ensure `docs/_survey/` can be created.

### 2. Delegate the survey to docs-lead

> Run the **survey** phase on this project. Scope note: $ARGUMENTS (or "whole
> project" if empty).
>
> Run the four fronts in parallel (diataxis-inventory, how-extractor, flow-tracer,
> rationale-archaeologist), enforce the grounding discipline (no invented WHY —
> un-sourced rationale becomes an owner question), then synthesize
> `docs/_survey/gap-report.md`.
>
> Reply with: the one-sentence diagnosis, the count of WHY-gaps and drifts, and the
> path to the gap-report.

### 3. Surface the gap-report to the owner

Show the owner:
- The diagnosis (§0).
- The **WHY-gaps** (§3) and "expected-or-deviation?" items (§4) — these are their
  checkpoint, coming up in `/docs:checkpoint`.
- Any **drift** (§5) and, prominently, any **security/correctness gap** the survey
  surfaced.
- The proposed structural moves (§1) — the input to `/docs:declutter`.

### 4. Report next step

- **Gap-report:** `docs/_survey/gap-report.md`
- **Next:** `/docs:declutter` (if the owner approves the structural moves) — or go
  straight to `/docs:checkpoint` to answer the WHY-gaps first. Authoring comes
  after the WHYs are grounded.

## Constraints

- **Read-only.** This phase moves and rewrites nothing. If you feel the urge to fix
  a doc or move a file, stop — that's `/docs:declutter` / `/docs:author`.
- **No invented rationale.** If the survey states a WHY, it has a source. Verify the
  gap-report's §3 are framed as questions, not answers.
- **Don't author.** The gap-report is a map, not documentation.
