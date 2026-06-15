---
description: Phase 4 — write the grounded Diátaxis tree from the survey ledgers. doc-author writes how-to/reference/explanation; tutorial-author writes the Tutorial last (it needs a real first-run). Every WHY traces to a source or is flagged UNSOURCED — never guessed. Preserves existing ADRs.
argument-hint: "[optional — a single shelf or doc to (re)author, e.g. 'explanation/flows']"
---

# /docs:author

## Purpose

Write the documentation a newcomer reads — on the right Diátaxis shelf, grounded in
the survey ledgers, in the project's voice. The HOW comes from the extracted
ledgers; the WHY comes only from a source (code / ADR / commit / Jira / the
checkpoint's `SOURCED: owner`). No source → flagged, never guessed.

## Variables

- `$ARGUMENTS` — optional. A single shelf or doc to (re)author. Omit to author the
  whole tree.

## Workflow

### 1. Require a grounded survey

Read `docs/_survey/gap-report.md`. Confirm the **checkpoint** has run — the §3
WHY-gaps should be answered (`SOURCED: owner`) or explicitly deferred. Authoring
rationale that's still an open question would force a guess. If the checkpoint
hasn't run, do that first (`/docs:checkpoint`).

### 2. Delegate authoring to docs-lead

> Run the **author** phase. Scope: $ARGUMENTS (or "whole tree").
> - doc-author writes `docs/how-to/**`, `docs/reference/**`, `docs/explanation/**`
>   (including `explanation/flows/*`) from the grounded ledgers; preserves existing
>   `explanation/adr/*`; every WHY cited or flagged `<!-- UNSOURCED -->`.
> - tutorial-author writes `docs/tutorial/**` **last** — a real first-day path,
>   with `<!-- VERIFY -->` on any step that needs a live run to confirm.
> Reply with a shelf-by-shelf, one-line-per-file summary.

### 3. Surface flags to the owner

Collect and show the owner every `<!-- UNSOURCED -->`, `<!-- GAP -->`, and
`<!-- VERIFY -->` the authors emitted. These are decisions for the owner:
- `UNSOURCED` — supply the source, rephrase as opinion, or cut the claim.
- `VERIFY` — confirm the tutorial step on a real machine.

### 4. Report next step

- **Authored:** <file count by shelf>
- **Open flags:** <count of UNSOURCED / VERIFY for the owner>
- **Next:** `/docs:finalize` — whole-tree consistency review.

## Constraints

- **Grounding is the gate.** Don't let a plausible-but-unsourced rationale ship. A
  flag is correct; a guess is a defect.
- **One mode per doc.** How-to = steps; reference = lookup; explanation = rationale;
  tutorial = one happy path. Don't re-mix the modes the declutter phase separated.
- **Tutorial last and real.** It depends on the rest of the tree and on a true
  first-run. Don't assert a success signal you can't ground.
- **Preserve ADRs.** Link to them; don't rewrite them.
