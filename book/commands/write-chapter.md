---
description: Write one chapter end-to-end with author checkpoints at outline and draft. Resumable — re-running with the same slug detects existing artifacts and picks up where it left off.
argument-hint: "<chapter-slug>"
---

# /book:write-chapter

## Purpose

Drive the per-chapter production loop with two author checkpoints: after the outline (before writing) and after the draft (before review). Resumable across sessions via STATUS markers in artifact files.

**Requires** `manuscript/BOOK.md` and `manuscript/audience.md` from `/book:inception`.

## Variables

- `$ARGUMENTS` — the chapter slug (e.g., `ch03-rag-pipelines`). Must match an entry in `manuscript/BOOK.md`.

## STATUS marker system

Each artifact file ends with one of:
- `<!-- STATUS: complete -->` — agent finished writing; author has not yet reviewed
- `<!-- STATUS: approved -->` — author reviewed and approved; phase is locked

Phase detection reads these markers to decide where to resume.

## Workflow

### 1. Validate

Read `manuscript/BOOK.md`. Confirm `$ARGUMENTS` exists as a chapter slug. If not found, abort.
If `manuscript/audience.md` is missing, abort: "Run /book:inception first."

### 2. Prerequisite check

Read the chapter's `Prerequisites` field from BOOK.md. For each prerequisite slug, check that `manuscript/<prereq-slug>/draft.md` exists and has `STATUS: approved`. If not:

> Warning: prerequisite chapter <prereq-slug> has not been completed yet.
> Its draft may be missing or not yet approved. Proceed anyway? (yes/no)

Wait for confirmation.

### 3. Phase detection

Read the following files and their STATUS markers to determine where to resume:

| Condition | Resume at |
|---|---|
| `outline.md` missing or no STATUS marker | **Outline phase** |
| `outline.md` STATUS: complete | **Outline checkpoint** (show to author) |
| `outline.md` STATUS: approved + `draft.md` missing or no STATUS marker | **Draft phase** |
| `outline.md` STATUS: approved + `draft.md` STATUS: complete | **Draft checkpoint** (show to author) |
| `draft.md` STATUS: approved + `review-technical.md` missing | **Code + exercises + review phase** |
| `review-technical.md` STATUS: complete | **Review findings** (surface to author) |
| `review-technical.md` STATUS: complete + author has seen findings | **Chapter complete** |

Report to the author where you're resuming from: "Resuming from draft checkpoint — found approved outline, complete draft awaiting your review."

---

### OUTLINE PHASE

Delegate to `writing-lead`:

> Phase: outline
> Chapter: $ARGUMENTS
> Book map: `manuscript/BOOK.md`
> Audience: `manuscript/audience.md`
>
> Run chapter-outliner. Write `manuscript/$ARGUMENTS/outline.md` ending with `<!-- STATUS: complete -->`.
> Return the full outline content.

#### Outline checkpoint

Show the outline to the author:

> **Outline for $ARGUMENTS**
> <outline content>
>
> Reply with:
> - **"approved"** (or similar) to lock this outline and move to drafting
> - **Your feedback** to request changes — I'll revise and show you again

Loop:
- If the reply sounds like approval → **confirm before acting**:
  > I'll mark this outline as approved and move to drafting. Confirm? (yes / no)
  - **yes** → delegate to `writing-lead`: "Approve outline for $ARGUMENTS — update `manuscript/$ARGUMENTS/outline.md` STATUS: complete → STATUS: approved." Then advance.
  - **no** → stay in loop, ask what they'd like to change instead.
- If the reply is feedback → delegate to `writing-lead`: "Revise outline for $ARGUMENTS based on this feedback: <feedback>. Keep STATUS: complete at the end." Show revised outline. Pause again.

---

### DRAFT PHASE

Delegate to `writing-lead`:

> Phase: draft
> Chapter: $ARGUMENTS
> Approved outline: `manuscript/$ARGUMENTS/outline.md`
> Audience: `manuscript/audience.md`
>
> Run researcher (→ research.md + references.md) then technical-writer (→ draft.md).
> draft.md must end with `<!-- STATUS: complete -->`.
> Return a section-by-section summary of the draft (one sentence per section — do not return the full text).

#### Draft checkpoint

Show the draft summary to the author:

> **Draft summary for $ARGUMENTS**
> <section-by-section summary>
>
> The full draft is at `manuscript/$ARGUMENTS/draft.md` — open it to read the prose.
>
> Reply with:
> - **"approved"** to move to technical review
> - **Your feedback** (e.g., "section 2 is too shallow", "remove the sidebar on X") — I'll revise and show you the updated summary

Loop:
- If the reply sounds like approval → **confirm before acting**:
  > I'll mark this draft as approved and move to technical review. Confirm? (yes / no)
  - **yes** → delegate to `writing-lead`: "Approve draft for $ARGUMENTS — update `manuscript/$ARGUMENTS/draft.md` STATUS: complete → STATUS: approved." Then advance.
  - **no** → stay in loop, ask what they'd like to change instead.
- If the reply is feedback → delegate to `writing-lead`: "Revise draft for $ARGUMENTS: <feedback>. technical-writer should revise draft.md keeping STATUS: complete at the end." Show updated summary. Pause again.

---

### CODE + EXERCISES + REVIEW PHASE

No author checkpoint — these are mechanical (code, exercises) and quality-gated (reviews).

Delegate to `writing-lead`:

> Phase: code-exercises-review
> Chapter: $ARGUMENTS
> Approved draft: `manuscript/$ARGUMENTS/draft.md`
> Book map: `manuscript/BOOK.md` (check code-examples and exercises flags)
>
> Run in sequence:
> 1. code-author (if chapter has code examples) → `code/$ARGUMENTS/`
> 2. exercise-designer (if chapter has exercises) → `manuscript/$ARGUMENTS/exercises.md`
> 3. technical-reviewer → `manuscript/$ARGUMENTS/review-technical.md` ending with `<!-- STATUS: complete -->`
>    If FAIL: route back to technical-writer. Iterate until PASS or PASS-WITH-NOTES.
> 4. copy-editor → `manuscript/$ARGUMENTS/review-copy.md` ending with `<!-- STATUS: complete -->`
>    If FAIL: route back to technical-writer. Iterate until PASS or PASS-WITH-EDITS.
>
> Return: review verdicts + all PASS-WITH-NOTES/EDITS findings verbatim.

#### Review findings

Surface findings to the author:

> **Reviews complete for $ARGUMENTS**
>
> Technical review: <verdict> — <one-line summary>
> <PASS-WITH-NOTES findings if any>
>
> Copy edit: <verdict> — <one-line summary>
> <PASS-WITH-EDITS suggestions if any>
>
> These are advisory — apply what you agree with, ignore the rest.
> The chapter is complete. You can edit `manuscript/$ARGUMENTS/draft.md` directly.

---

### 4. Final report

- **Chapter:** $ARGUMENTS — <title>
- **Resumed from:** <phase name or "fresh start">
- **Files produced:** outline.md, research.md, draft.md, exercises.md (if any), review-technical.md, review-copy.md; code/$ARGUMENTS/ (if any)
- **Technical review:** <verdict + one-line summary>
- **Copy edit:** <verdict + one-line summary>
- **Author decisions:** <PASS-WITH-NOTES/EDITS items, or "none">
- **Now unblocked:** <chapter slugs whose prerequisites are now satisfied>

## Constraints

- Never skip the outline checkpoint. Never skip the draft checkpoint. Both are mandatory.
- Approval requires explicit confirmation ("yes") after the confirm prompt. Silence, ambiguity, and "proceed anyway" do not count — always show the confirm prompt.
- Don't advance from a phase if the author gave feedback — iterate until they confirm approval.
- On resume: always tell the author what was found and where you're picking up. Never silently skip a phase.

## Revising an approved artifact

If the author wants to revisit something already approved (e.g., "I changed my mind about the outline"), delegate to `writing-lead`:

> Revise approved outline for $ARGUMENTS: <feedback>. This is an explicit author unlock.

or

> Revise approved draft for $ARGUMENTS: <feedback>. This is an explicit author unlock.

The "explicit author unlock" phrasing signals the worker to overwrite despite the `STATUS: approved` marker. After revision, the artifact returns to `STATUS: complete` and goes through the checkpoint again.
