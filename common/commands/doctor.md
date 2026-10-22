---
description: Validates the harness installation against reality in 30 seconds — plugins enabled and at the installed version, hooks compiling, board-flow.yaml structure, build baseline (status + age), stale/orphan worktrees (including the forgotten agent worktree inside the repo, which duplicates the source code), expired handoffs and the single-track queue (queue.yaml) diverging from BACKLOG.md. With --live, also checks board-flow.yaml and the queue against live Jira via atlassian-expert. Run it at the start of the day or when something in the harness looks wrong — each check exists because the matching failure has already cost a task.
argument-hint: [--live] [--no-fix] [--projeto]
interaction: routine
---

# /common:doctor

## Purpose

Almost every harness infrastructure failure used to be discovered in the middle
of a task: a plugin not loaded producing cards without custom fields, a
board-flow.yaml from another module, a weeks-old FAILURE baseline blocking
push, an orphan worktree, a stale handoff feeding false claims. This command
brings all of that forward to a moment when fixing is cheap.

## Steps

1. Run the diagnosis **already fixing what is mechanical** (default; use
   `--no-fix` to only diagnose):

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-doctor" --fix
   ```

   `--projeto` cuts the global checks (settings, plugins, hooks, telemetry) and
   looks only at this project — useful when the question is "is this repo
   sound?" and not "is this machine sound?".

   `--fix` applies, in a batch and without asking, only what is mechanical AND
   reversible (reinstall plugins when the cache diverges from the repo, archive
   an expired handoff — moves, does not delete —, clear the registration of a
   worktree whose directory is gone, remove a forgotten agent worktree that is
   already contained in the integration branch and holds no file), and re-runs
   the diagnosis until it stops changing. This exists because the alternative
   was one finding at a time, each costing a confirmation: the preparation used
   up more attention than the session's task.

   Reinstalling is the only fix that leaves the project and touches the
   machine's installation, so it has two locks: `CEPA_DOCTOR_INSTALL=off` turns
   it off, and the doctor called from inside a temporary directory never
   reinstalls (that is where the suites run — on 2026-08-19 the doctor's own
   suite swapped the owner's live installation in the middle of a
   `python3 tests/...`).

2. Show the output to the user in full (✓/⚠/✗ per area, already in pt-BR),
   including the final blocks **Corrigido automaticamente** (fixed
   automatically) and **Precisa de você** (needs you).

   The `plano` area (when it shows up) is the single-track queue
   (`.claude/queues/<fila>/queue.yaml`) compared with the project's
   `BACKLOG.md` — the `cepa-plan divergencia` the script already ran on its
   own: BACKLOG.md sections without `**Plano:**` and a `**Plano:**` citing an id
   that does not exist in that queue. It only shows up when the repo has
   `BACKLOG.md` AND a queue that resolves without ambiguity (via
   `board-flow.yaml` → `defaults.project_key`, or exactly one `single-track`
   queue in `.claude/queues/*/queue.yaml`); with more than one possible queue
   the script stays quiet — it does not guess which one the owner wants to see.
   It is a report, never a fix: no `--fix` touches it.

   The `maestro` area (when it shows up) is a Maestro wave that finished and
   nobody landed: a `DONE` slice in `wave-state.yaml` that is not `LANDED`. The
   merge train only runs while the `/maestro:run` session is alive; when it dies
   first, the ready branches sit idle with nothing on disk saying they are
   waiting (wave 1 of WEGO-paralelo, 2026-08-24). The route is
   `/maestro:resume <programa>`, which goes straight to the merge train. Also
   report only.

3. **If `--live` was passed** and there is a `board-flow.yaml` in the project:
   delegate to `board-flow:atlassian-expert` (if the board-flow plugin is
   installed):

   > Sanity-check board-flow.yaml against live Jira (no mutation):
   > confirm that the project_key is visible, that each status_map value
   > exists as a real status of the project, and that each required_field
   > exists in the issue type's metadata. Answer OK or the list of divergences.

   Attach the result to the report.

   If the same queue resolved in step 2 (`plano`) exists, also ask
   `atlassian-expert` for the project's list of cards (`key` + `status`), save
   it to a temporary file and run:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-plan" divergencia <fila> \
     --board <arquivo-temporário> --backlog BACKLOG.md --repo . --json
   ```

   This completes the step 1 report (which only compares queue × BACKLOG.md)
   with the half that depends on Jira: `cards_sem_item` (open cards on the
   board with no item in the queue) and `itens_com_card_done` (unclosed items
   whose card Jira already shows as done). Attach it to the report the same
   way: read, never fix.

4. What is left in the **Precisa de você** block are the fixes that involve a
   choice (discard a worktree with work inside — including the agent worktree
   that still has a commit or an untracked file —, edit `board-flow.yaml`, run
   the project's verify, create `.claude/no-build`). Apply the `default-yes`
   skill: gather ALL of them into a single list, with your recommendation per
   item, and ask for **one** batch confirmation at the end — never one question
   per finding, and never a cascade where one answer produces the next
   question. The list and the question are in pt-BR.

   **`ops` area — treat it with priority over the others.** It answers "is the
   harness that is running the one I think it is?", and a ✗ there contaminates
   the whole rest of the report: if the last install did not finish, the live
   hooks are not the repo's, and any other check may be measuring the wrong
   thing. Translate it without jargon — in pt-BR, along the lines of "the last
   installation died midway, so what is in effect now is neither the old one
   nor the new one" — and offer the two explicit ways out: redo
   (`bin/install.sh --clean`) or go back (`bin/install.sh --rollback`). See
   `docs/harness-ops.md`.

5. The script's exit code: 0 = healthy, 1 = warnings only, 2 = failures. If 2,
   suggest resolving them before starting new work.

## Notes

- Without `--fix` the script is 100% read-only (the telemetry probe creates and
  deletes a file of its own) and lists, at the end, which findings would have a
  mechanical fix. With `--fix` it mutates **only** the three kinds above;
  everything else still goes through step 4.
- Project checks run on the cwd; run the command from inside the repo you want
  to diagnose.
- The `ops` check is the exception: it reads `~/.claude/ops/last-install.json`,
  which is **global** — it describes the machine's plugin cache, not this
  repository. That is why it applies the same in any cwd, and why it keeps
  `repo_dir` (which clone what is installed came from).
