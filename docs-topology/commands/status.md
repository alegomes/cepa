---
description: Show the current state of the documentation effort — which phases are done, in progress, awaiting owner review, or not started. Reads artifact STATUS markers and the gap-report from disk. No agents needed.
argument-hint: "(none)"
interaction: routine
---

# /docs:status

## Purpose

A read-only dashboard of where the documentation effort stands. No agents, no
delegation — just read the `docs/_survey/` artifacts and the `docs/` tree from disk
and report.

## Workflow

### 1. Read the survey artifacts

For each, report present/absent and its trailing `<!-- STATUS: ... -->` marker:
- `docs/_survey/inventory.md`, `how-ledger.md`, `flows.md`, `why-ledger.md`,
  `open-questions.md` — the survey fronts.
- `docs/_survey/gap-report.md` — the anchor; also report whether it has a
  "Checkpoint — owner answers" section (→ checkpoint done) and the count of still-open
  WHY-gaps.
- `docs/_survey/consistency-review.md` — the finalize verdict, if present.

### 2. Read the tree

Count files under each shelf: `docs/tutorial/`, `docs/how-to/`, `docs/reference/`,
`docs/explanation/` (and `explanation/adr/`, `explanation/flows/`).

Scan the authored files for open flags: `<!-- UNSOURCED -->`, `<!-- GAP -->`,
`<!-- VERIFY -->`.

### 3. Report the phase

Map state to phase and name the next command:

| Phase | Done when | Next |
|---|---|---|
| survey | gap-report.md exists, STATUS complete | `/docs:declutter` or `/docs:checkpoint` |
| declutter | exhaust archived (inventory's flagged files gone from docs/) | `/docs:checkpoint` |
| checkpoint | gap-report has "Checkpoint — owner answers"; §3 grounded | `/docs:author` |
| author | shelves populated; flags surfaced | `/docs:finalize` |
| finalize | consistency-review PASS; scratch deletable | (sign-off) |

Report: current phase, what's blocking, count of open flags/WHY-gaps, and the single
next command to run.

## Constraints

- **Read-only.** Never write or move anything. This is a report.
- **Don't infer beyond the markers.** If an artifact is absent, the phase isn't
  done — say so plainly.
