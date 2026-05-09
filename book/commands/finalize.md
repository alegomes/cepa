---
description: Finalize the book — whole-manuscript continuity review, author sign-off on findings, then compile all chapters into manuscript/compiled/book.md and manuscript/compiled/book.tex. Run after all chapters are written.
argument-hint: ""
---

# /book:finalize

## Purpose

The last step before the manuscript leaves the writing team. Three things happen:

1. **Continuity review** — the whole book is read in chapter order and checked for terminology drift, broken cross-references, and arc gaps.
2. **Author sign-off** — findings are surfaced; the author decides what to fix.
3. **Compilation** — all drafts are assembled in order and converted to LaTeX.

## Workflow

### 1. Check all chapters are written

Read `manuscript/BOOK.md`. For each chapter slug, verify `manuscript/<slug>/draft.md` exists.

If any chapter is missing a draft:

> The following chapters have no draft yet: <list>.
> Run /book:write-chapter <slug> for each before finalizing.

Abort until all chapters have drafts.

### 2. Continuity review

Delegate to `continuity-reviewer`:

> Read all chapter drafts in BOOK.md order. Build a running glossary and cross-reference map as you go. Produce `manuscript/continuity-review.md` covering:
> - Terminology drift (same term defined differently across chapters)
> - Broken cross-references ("as covered in the previous chapter" pointing at the wrong place)
> - Learning arc gaps (BOOK.md promises an objective that the draft doesn't deliver)
> - Prior knowledge assumed but never established in earlier chapters
> - A complete glossary as a deliverable artifact

Wait for `manuscript/continuity-review.md`.

### 3. Surface findings to author

Show the author the continuity review summary. For each BLOCKER finding:

> The continuity review found N blocker(s) that should be resolved before compilation:
>
> **[BLOCKER 1]** <summary> — affects <chapter slug(s)>
> **[BLOCKER 2]** ...
>
> For each blocker: fix it now via `/book:write-chapter <slug>` (re-runs the chapter loop),
> or override and compile anyway (not recommended).
>
> NOTE-level findings:
> **[NOTE 1]** <summary>
> ...
> Notes are advisory — compile now and address later, or fix first. Your call.

Wait for the author's decision before proceeding.

### 4. (Conditional) Re-run chapters for blockers

If the author chooses to fix blockers before compiling:

For each chapter the author flags for revision, instruct them:

> Run `/book:write-chapter <slug>` to re-enter the production loop for that chapter.
> Come back to `/book:finalize` when done.

Stop here. The author re-runs the affected chapters and then re-invokes `/book:finalize`.

### 5. Compile

Once the author approves (blockers resolved or explicitly overridden), delegate to `manuscript-compiler`:

> Assemble all chapter drafts from `manuscript/BOOK.md` in chapter order.
> Prepend title-page front matter (with author and date placeholders).
> Write the assembled manuscript to `manuscript/compiled/book.md`.
> Convert to LaTeX via pandoc: `manuscript/compiled/book.tex`.
> Report chapter count, word count estimate, and any pandoc errors.

### 6. Report to author

- **Continuity review:** N blockers (resolved / overridden), M notes (list)
- **Chapters compiled:** N (in order)
- **Markdown:** `manuscript/compiled/book.md`
- **LaTeX:** `manuscript/compiled/book.tex` — success | failed (reason + fallback instructions)
- **Glossary:** `manuscript/continuity-review.md` contains a full term list — consider adding it as an appendix
- **Placeholders to fill:** title, author, date in the compiled front matter
- **Next step:** open `manuscript/compiled/book.tex` in your LaTeX editor

## Constraints

- Don't compile with unresolved blockers unless the author explicitly says to override.
- Don't re-run the continuity review after compilation — if the author edits chapters post-compile, they should re-run `/book:finalize` from the top.
- `manuscript-compiler` does not edit chapter content — only assembles. Content changes go through `/book:write-chapter`.
