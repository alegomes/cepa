---
description: Write one chapter end-to-end — outline, research, draft, code examples, exercises, technical review, copy edit. Argument is the chapter slug from BOOK.md (e.g., ch03-rag-pipelines).
argument-hint: "<chapter-slug>"
---

# /book:write-chapter

## Purpose

Drive the full per-chapter production loop for one chapter. Delegates everything to `writing-lead`; returns file paths and review verdicts.

**Requires** `manuscript/BOOK.md` and `manuscript/audience.md` from `/book:inception`.

## Variables

- `$ARGUMENTS` — the chapter slug (e.g., `ch03-rag-pipelines`). Must match an entry in `manuscript/BOOK.md`.

## Workflow

### 1. Validate

Read `manuscript/BOOK.md`. Confirm `$ARGUMENTS` exists as a chapter slug.

If not found: abort with "Chapter '$ARGUMENTS' not found in manuscript/BOOK.md. Check the slug or run /book:inception first."

If `manuscript/audience.md` is missing: abort with "manuscript/audience.md not found. Run /book:inception first."

### 2. Check prerequisites

Read the chapter's `Prerequisites` field from BOOK.md. For each prerequisite chapter slug, check whether `manuscript/<prereq-slug>/draft.md` exists. If a prerequisite chapter hasn't been written yet, warn the author:

> Warning: chapter $ARGUMENTS lists <prereq-slug> as a prerequisite, but that chapter hasn't been written yet (no draft.md). Concepts from <prereq-slug> may need to be explained inline or the reader may be left without required context. Proceed anyway? (yes/no)

Wait for confirmation before continuing.

### 3. Delegate to writing-lead

> Write chapter: **$ARGUMENTS**
>
> Book map: `manuscript/BOOK.md` (read the entry for $ARGUMENTS)
> Audience profile: `manuscript/audience.md`
>
> Run the full per-chapter loop:
> - chapter-outliner → `manuscript/$ARGUMENTS/outline.md`
> - researcher → `manuscript/$ARGUMENTS/research.md` + `references.md`
> - technical-writer → `manuscript/$ARGUMENTS/draft.md`
> - code-author → `code/$ARGUMENTS/` (if chapter has code examples)
> - exercise-designer → `manuscript/$ARGUMENTS/exercises.md` (if chapter has exercises)
> - technical-reviewer → `manuscript/$ARGUMENTS/review-technical.md` (PASS required to advance)
> - copy-editor → `manuscript/$ARGUMENTS/review-copy.md` (PASS required to advance)
>
> Iterate until both reviews pass. Reply with files produced, review verdicts, and any open author-decision items.

### 4. Report to author

- **Chapter:** $ARGUMENTS — <title from BOOK.md>
- **Files produced:**
  - `manuscript/$ARGUMENTS/outline.md`
  - `manuscript/$ARGUMENTS/research.md` + `references.md`
  - `manuscript/$ARGUMENTS/draft.md`
  - `manuscript/$ARGUMENTS/exercises.md` (if applicable)
  - `code/$ARGUMENTS/` (if applicable) — list scripts
  - `manuscript/$ARGUMENTS/review-technical.md` — verdict
  - `manuscript/$ARGUMENTS/review-copy.md` — verdict
- **Technical review:** PASS | PASS-WITH-NOTES — <one-line summary>
- **Copy edit:** PASS | PASS-WITH-EDITS — <one-line summary>
- **Author decisions needed:** <list from PASS-WITH-NOTES or PASS-WITH-EDITS, or "none">
- **Next chapter suggestions:** based on BOOK.md prerequisites, which chapters are now unblocked?

## Constraints

- Don't skip prerequisite check. Dependency order matters for content quality.
- writing-lead owns the quality gate — don't accept a chapter that hasn't passed both reviews.
- The author's draft is the source of truth. Don't silently apply copy-edit suggestions; surface them so the author decides.
