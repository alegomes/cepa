---
description: "[frozen since 2026-10-08: the cepa-until conductor will absorb fork and merge train (decision 1 of docs/estrategia-cepa-proximo-nivel.md); do not use for new work] Recovers an interrupted Maestro wave — rebuilds the state from .claude/programs/<name>/wave-state.yaml (live children, per-slice state, gatekeeper, pending escalations, merges already landed) and continues the event loop / merge train from where it stopped. Modeled on /common:autonomous-resume. Use after the session died, crashed or hit the token limit in the middle of a /maestro:run."
argument-hint: <program-name>
interaction: routine
---

# /maestro:resume

## Purpose

The death of the maestro session is the most likely failure mode of a long
session. `/maestro:run` writes `wave-state.yaml` at every transition precisely so
that this resume is possible without re-forking what is already running or
re-merging what has already landed. It reuses the `/common:autonomous-resume`
pattern — it does not invent another one.

## Steps

1. **Read the state.**
   `python3 maestro/bin/maestro-wave-state get <main-root>/.claude/programs/$1 --json`
   — `<main-root>` is the parent of `git rev-parse --git-common-dir`
   without the trailing `/.git` (the main clone, when you are in a linked
   worktree); the program's state belongs to the repo, not to this tree.
   If it does not exist, stop: there is no wave in progress for this program
   (maybe you want `/maestro:run $1`).

2. **Reconcile against reality** (the wave-state describes the past — CLAUDE.md
   says to verify before asserting):
   - **gatekeeper**: `GET /health` on the recorded URL. Dead → bring it back up
     (`maestro-gatekeeper --state-dir .../gatekeeper --port <P>` in the same mode)
     and update the pid via `set-gk`.
   - **`running` children**: check whether the pane is still alive with
     `herdr pane get <pane>` (the id recorded in `slices.<slice>.pane`; liveness
     is NO longer checked per agent — herdr 0.9 no longer has that agent
     command for this) AND whether `resultado.txt` already
     has `MAESTRO-EXIT`. Dead child without the marker → treat it as the next
     poll iteration will decide (TIMEOUT if it blew the deadline); live child →
     stays in the loop. Any re-spawn (dead child, answered escalation)
     uses the home pane recorded in the wave-state
     (`maestro-wave-state get <PROGDIR> --json` → `home.pane`/`home.tab`/
     `home.workspace`), with the same `herdr pane split` + rename +
     `herdr pane run` recipe as `/maestro:run` (step 6c) — never the current
     focus of this resume session, which may not even be the same tab as the
     original wave.
   - **merges**: a `LANDED` slice (or, in an old wave-state, a name in the
     `landed:` list) is already in main; do not re-merge it.

3. **A wave that finished without merging goes straight to the merge train.** If
   `maestro-wave-state check-terminal` exits 0 and
   `maestro-wave-state aguardando-merge` lists slices, the wave is not "with nothing
   running": it is waiting for you. Skip the event loop and resume `/maestro:run` at
   Step 9 (merge train) with those slices. Concluding "nothing is running" and
   stopping is what left five ready branches parked in wave 1 of WEGO-paralelo.

4. **Continue.** In the other cases, resume `/maestro:run` from Step 7 (event loop):
   `maestro-poll` in rotation → transitions → escalations → merge train of the DONE
   slices not yet in `landed`. FAIL/TIMEOUT/ESCALATED slices of the wave re-fork in
   the next wave, as in the normal flow.

5. **Report** what was rebuilt (gatekeeper resurrected? children still
   alive? merges already done?) before proceeding, so the user sees the
   inherited state — do not claim "resumed" without showing the reconciliation.
   Write this report to the user in Brazilian Portuguese (pt-BR).

## Notes

- Idempotent by design: reprocessing a `resultado.txt` that was already read only
  reaffirms the same terminal state; retrying a merge already in `landed` is skipped.
- If the plan itself changed since the interruption, STOP and warn — resume assumes
  the same plan.yaml as the recorded wave.
