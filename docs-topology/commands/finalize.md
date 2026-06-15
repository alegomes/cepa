---
description: Phase 5 — whole-tree consistency review then owner sign-off. consistency-reviewer checks terminology drift, broken cross-references, Diátaxis-shelf violations, and the critical check that every WHY is sourced (no surviving UNSOURCED). On PASS and owner sign-off, the docs/_survey/ scratch is deleted.
argument-hint: "(none — reviews the whole docs/ tree)"
---

# /docs:finalize

## Purpose

The last gate. Read the whole tree at once to catch what per-file authoring can't:
terminology that drifted between shelves, cross-references that broke when files
moved, shelf violations, and — the check this topology lives on — any rationale
that shipped without a source.

## Workflow

### 1. Delegate the review to docs-lead

> Run the **finalize** phase. consistency-reviewer reads the whole `docs/` tree and
> writes `docs/_survey/consistency-review.md` with a PASS | PASS-WITH-NOTES | FAIL
> verdict. The un-sourced-WHY check is non-negotiable: any surviving
> `<!-- UNSOURCED -->` or un-cited rationale is a FAIL.
> If FAIL, route findings back to the owning author, fix, and re-review until PASS
> or PASS-WITH-NOTES. Reply with the verdict and all findings verbatim.

### 2. Surface the verdict to the owner

- **PASS** — clean. Proceed to sign-off.
- **PASS-WITH-NOTES** — show the notes; the owner decides which to apply now vs.
  leave as follow-ups.
- **FAIL** — docs-lead should already have iterated; if a FAIL reaches you, surface
  the blockers (almost always an un-sourced WHY) and stop.

### 3. Owner sign-off + clean up the scratch

Once the owner signs off:
- Confirm the glossary (a deliverable in the review) is captured if they want it as
  a reference page.
- **Delete the `docs/_survey/` scratch** — it was the survey's working area, not
  living doc. Land the deletion as a commit (`docs: finalize — remove survey scratch`).

### 4. Report

- **Verdict:** <PASS / PASS-WITH-NOTES>
- **Tree:** `docs/` — tutorial / how-to / reference / explanation
- **Scratch removed:** `docs/_survey/`
- **Done.** The project is documented for handoff.

## Constraints

- **Un-sourced WHY = FAIL.** Don't sign off with any rationale lacking a source.
- **Review reads everything; authors fix.** consistency-reviewer reports; it doesn't
  rewrite.
- **Delete scratch only after sign-off.** The gap-report is the anchor until the
  tree is accepted.
