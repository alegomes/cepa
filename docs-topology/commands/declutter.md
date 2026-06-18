---
description: Phase 2 — structural ROI moves. Archives process-exhaust out of docs/, demotes rival front-doors to links, consolidates doc chains. Moves files (git history preserved), rewrites no prose. Mutating — requires explicit owner approval of the gap-report's move list, and lands as its own commit(s).
argument-hint: "(none — operates from the gap-report's move list)"
---

# /docs:declutter

## Purpose

Execute the high-ROI structural moves the survey identified — *before* a single new
line is written. Get the process-exhaust out of the newcomer's path, collapse rival
front-doors into one, and merge fragmented doc chains. These are **moves, not
rewrites**: history is preserved, nothing is deleted, no prose is re-worded.

## Workflow

### 1. Require the gap-report and owner approval

Read `docs/_survey/gap-report.md` §1 (structural moves). If it's missing, stop and
run `/docs:survey` first.

Show the owner the exact move list:
- Process-exhaust → `archive/` (which files/dirs).
- Rival front-door demotion (which file stays, which becomes links).
- Doc-chain consolidations (which files merge into which target).

**Get explicit approval before anything moves.** This is mutating and high-impact.

### 2. Delegate to docs-lead

> Run the **declutter** phase. The owner approved the gap-report §1 move list.
> Delegate to structure-surgeon: archive process-exhaust with `git mv`, demote the
> rival front-door to links (preserving non-documentation content), consolidate the
> named doc chains by moving/merging (no rewriting).
> Reply with the full `from → to` move list and anything preserved-not-moved.

### 3. Land it as a reviewable commit

Show the owner the applied moves. Commit them as their own change (one commit, or
one per category) so it's reviewable and reversible. Suggested message shape:
`docs(declutter): archive process-exhaust + demote AGENTS front-door`.

### 4. Report next step

- **Moves applied:** <count>
- **Next:** `/docs:checkpoint` — answer the WHY-gaps before authoring.

## Constraints

- **Owner-gated.** Never move files without the owner approving the list.
- **Move, never delete.** `git mv` to `archive/`. Anything that "looks redundant"
  might be unique (the pilot's `spec/` was) — archive, don't delete.
- **No rewriting.** Demotion = replace duplicated fact-tables with links. Merge =
  concatenate under headings. Re-wording is `/docs:author`.
- **Preserve behavioral content.** A rival front-door may carry agent instructions,
  not just docs — keep those.
