---
description: "[frozen since 2026-10-08: the cepa-until conductor will absorb fork and merge train (decision 1 of docs/estrategia-cepa-proximo-nivel.md); do not use for new work] Runs the current wave of a Maestro plan in one action — gc of orphans, intake gate (cepa-dor), brings up the gatekeeper (shadow-mode on the 1st program), forks each slice into a herdr worktree with generated settings + normative wrapper, runs the file-based event loop, lands the wave through the merge train (reuses the worktree-merge guards with verify after each merge) and reports. Session death is recoverable with /maestro:resume. Reads EXCLUSIVELY the plan.yaml (seam invariant). ⚠ Needs herdr running and the plugin installed (bin/install.sh --clean)."
argument-hint: [program-name] [--wave N] [--shadow] [--port P] · with no argument, lists what can run
interaction: routine
---

# /maestro:run

## Purpose

Maestro's single action: go from an approved `plan.yaml` to N real sessions
created, managed and integrated. This command does NOT plan (that is
`/maestro:program-plan`) and does NOT interpret the BACKLOG — it reads only
`PROGDIR/plan.yaml`.

**`PROGDIR` = `<main-root>/.claude/programs/<name>`**, and `<main-root>`
is the parent of `git rev-parse --git-common-dir` without the
trailing `/.git` — in a linked worktree this points to the MAIN CLONE, not to the
current tree; outside one it is the same as `git rev-parse --show-toplevel`. The plan
is repo state, not session state: written inside a session worktree, it dies with
it (and in a repo whose `.gitignore` covers all of `.claude/`, no guard on the
removal path sees the file). This holds for reading and for writing. See
`docs/execution-plan.md`, "Where the file lives".

**Preconditions** (stop and tell the user if any is missing): herdr running
(`herdr agent list` answers); plugin installed after `bin/install.sh --clean`;
plan exists and passes intake. `.claude/no-build` repo: each slice carries an
`acceptance_cmd`. **Listing mode (Step 0) requires none of this** — it only reads
files, and it is exactly what answers before the user has a name in hand.

## Variables

- `PROG` = `$1` (program name). **Absent = listing mode, see Step 0** —
  the command runs nothing and prints the options. · `PROGDIR` =
  `<main-root>/.claude/programs/$PROG`
- `--wave N` (default: first wave with `status: pending`)
- `--shadow` — forces the gatekeeper's shadow-mode (default: shadow IF this is the
  1st program executed, otherwise active deny — see Step 3)
- `--port` (default 8765) — gatekeeper port

## Steps

0. **No `$1`: list and stop.** Discovering the options used to cost two shell
   commands and knowledge of two fields that an `ls` does not show — `mode` (a
   `single-track` plan does not run here) and the waves' `status` (which is the
   next pending one). Run:
   ```
   python3 maestro/bin/maestro-programs .
   ```
   It reads the SAME root as the steps below (the main clone), prints per
   program the mode, the next pending wave and the verdict `RODA` (runs) / `não roda:
   <motivo>` (does not run: <reason>) — with the command line ready to copy — and
   flags leftovers from a previous execution (`wave-state.yaml`, orphan gatekeeper).
   Show the output to the user and **stop here**: without a program name there is
   no wave to fork. Do not pick a program on your own.

1. **Load and validate the plan.** Read `PROGDIR/plan.yaml`. Accept
   `schema_version` 1 (legacy, waves only) and 2 (explicit `mode`); refuse
   any other. Check `mode`: absent (only in v1) or `parallel-waves` follows the
   flow; **`single-track` is not executable here** — stop and say that this
   plan is one item at a time (`/common:next` answers which one is next),
   and that promoting it to waves requires declaring surface and acceptance per item,
   with `/maestro:program-plan`. Any other value is an error (see
   `common/plan-schema.yaml`). Select the target wave (`--wave` or the first
   pending one).

   **Capture the wave's home pane NOW — not at fork time.** Run
   `herdr pane current` and keep `pane_id`, `tab_id` and `workspace_id` (this is
   the tab/Space that will receive ALL the children of this wave). The reason to
   capture it here, before even the intake gate, and not in step 6 (spawn):
   minutes go by between this point and the first fork (gc of orphans, intake gate,
   gatekeeper startup), and the focus changes in that interval with any click by the
   owner — the focus at spawn time is exactly the wrong value. In the
   WEGO-paralelo wave (2026-08-24) the spawn received no `--tab`/`--workspace`
   at all and forked whatever tab was in focus at the moment; the evidence in
   `herdr-server.log` was five successive `pane.spawn.start` with the width
   halving each time (173 → 87 → 44 → 22 → 11 columns) — the
   signature of five splits of the SAME tab, which was not the `/maestro:run` one.
   If `herdr pane current` fails (session outside herdr), the home pane is not "the
   tab that has focus when someone notices": open a new, predictable tab,
   `herdr tab create --label <PROG> --no-focus`, and use its `root_pane`.
   This home pane is persisted in step 5 (`maestro-wave-state set-home`) and it is
   against it — never against the current focus — that step 6c splits.

2. **gc of orphans** (the analogue of what cepa-doctor does for cepa-worktrees —
   leftovers from previous programs cost the next wave):
   - `herdr worktree list --cwd <main-root> --json` → worktrees of programs
     already finished (`--cwd` is mandatory: without it herdr 0.9.1 lists the repo
     of the Space in FOCUS, not that of the current directory);
   - orphan gatekeeper: `PROGDIR/gatekeeper/gatekeeper.pid` with a dead PID;
   - zombie panes (`herdr agent list` with no live process);
   - expired escalations (`estado: pending`, `ttl` expired).
   List what you found and offer to clean up. Only remove what the user confirms
   (except leftovers clearly from the SAME program in this re-run). A worktree of a
   finished program with an `open_workspace_id` in that list:
   remove it with `herdr worktree remove --workspace <open_workspace_id>` — that is
   what takes the Space down with it (a plain `git worktree remove` takes the worktree
   out of git and leaves a ghost Space in the herdr sidebar). Only without an
   `open_workspace_id` (the owner already closed the Space by hand) use a plain
   `git worktree remove`.

3. **Intake gate.** Run
   `python3 common/bin/cepa-dor PROGDIR/plan.yaml --wave N --repo .`.
   Any NOT-READY **blocks the wave** — show the named gaps and stop;
   the fix is in `/maestro:program-plan`, not here. ⚠ warnings pass.

4. **Bring up the gatekeeper.** Decide the mode: **shadow-mode** if this is Maestro's
   1st program (there is no `~/.claude/cepa-telemetry` with a previous `program_done`)
   OR `--shadow` was passed; otherwise active deny. Start it:
   ```
   python3 maestro/bin/maestro-gatekeeper --state-dir PROGDIR/gatekeeper \
     --port <P> [--shadow] &
   ```
   Confirm `GET http://127.0.0.1:<P>/health` = 200. Record:
   `maestro-wave-state set-gk PROGDIR --pid <PID> --url http://127.0.0.1:<P>/mcp`.

5. **Initialize the wave state.**
   `python3 maestro/bin/maestro-wave-state init PROGDIR --plan PROGDIR/plan.yaml --wave N`.
   Right after, persist the home pane captured in step 1:
   `python3 maestro/bin/maestro-wave-state set-home PROGDIR --pane <pane_id> --tab <tab_id> --workspace <workspace_id>`.
   It is this record on disk — not a session variable — that step 6c and
   `/maestro:resume` consult to know where the children are born.

6. **Fork per slice** (respecting `max_concurrent_slices`):
   For each READY slice of the wave:
   a. **Worktree herdr** (herdr worktree), inheriting the model of the `cepa` launcher (single-owner guard + seed):
      `herdr worktree create --base <fork_point> --branch session/<PROG>-<slice> --json`.

      **Confirm through git before moving on — the success `--json` is not enough.**
      With the `path` returned by the command, run in the main clone
      (`<main-root>`, the parent of `git rev-parse --git-common-dir` without the `/.git`):
      ```
      git -C <main-root> worktree list --porcelain | grep -qx "worktree <path>"
      ```
      Only go on (seed, settings, spawn) if that line exists.
      Why the check exists: in 4 of 5 calls of the WEGO-paralelo wave
      (2026-08-24, herdr 0.7.3), `herdr worktree create` returned a COMPLETE
      success JSON — with `path`, `branch`, `workspace_id` and
      `"is_prunable": false` — and git registered no worktree at all; the
      directories did not exist either. `herdr worktree list` kept showing
      the ghosts, because it keeps its own registry. The trigger was not
      reproduced and is out of our reach; the fix from here is not to accept
      an external tool's word about an effect that git checks in one
      command — the same pattern as the `MAESTRO-EXIT` marker, which syncs by
      FILE and not by the pane. Without the check, the seed, the settings and
      `herdr agent start` run against a nonexistent path and the whole wave
      is born dead, failing as if it were the children's problem.

      If the line does not exist: remove the ghost record —
      `herdr worktree remove --workspace <workspace_id returned by create>
      --trust-repository`, tolerating errors (the positional form with the path
      directly does NOT exist in the installed herdr 0.9.1: "unknown option: <path>",
      only `--workspace ID` identifies the target) — and try **once** more.
      If it persists, the slice is **FAIL** with a named detail —
      `maestro-wave-state set-slice PROGDIR <slice> fail --detail "worktree create reported success but <path> does not appear in git worktree list (2 attempts)"`
      — and the other slices of the wave do **not** fork silently: stop forking,
      show the owner which slices were left out and why.

      Run the seed (`.env` etc.) copying from main — NOT a symlink (it re-couples to
      the synced tree). Named debt: the herdr worktree lives in `~/.herdr/...`,
      not `~/cepa-worktrees` — it inherits the guard and the seed; whatever does not
      inherit is an exception.
   b. **Generated settings** (layer 1) — the generator writes the PAIR of files:
      `python3 maestro/bin/maestro-fork-settings PROGDIR/plan.yaml <slice> --port <P> --out-dir <worktree>`
      → `<worktree>/.claude/settings.json` (permissions) **and** `<worktree>/.mcp.json`
      (gatekeeper address). Both are mandatory: without the `ask` rules the
      gatekeeper is never consulted (spike finding), and without `.mcp.json` the child
      does not see the gatekeeper tool and dies at the start (finding from the
      WEGO-paralelo wave, 2026-08-24 — `mcpServers` in settings.json is ignored).
   c. **Spawn against the home pane, with the normative wrapper** (pipefail +
      PIPESTATUS, otherwise every child that fails reports success — a real bug of
      rev1). The `herdr agent start` of the installed version (0.9.1) no longer accepts
      `--cwd`, `--env`, `--tab`, `--workspace` or a command after `--`
      ("Start a supported interactive agent in an existing pane" — it only
      starts an agent in a pane that already exists); that is why the spawn is
      split-and-run against the home pane recorded in step 5
      (`maestro-wave-state get PROGDIR`, field `home.pane`), NEVER against the
      pane that is in focus:
      ```
      herdr pane split <home.pane> --direction right --cwd <worktree> \
        --env MAESTRO_LINGER=600 --no-focus
      # → returns the new pane_id
      herdr pane rename <novo-pane> <PROG>-<slice>
      herdr pane run <novo-pane> "bash -c 'set -o pipefail; claude -p \"<slice-prompt>\" \
        --mcp-config .mcp.json --strict-mcp-config \
        --permission-prompt-tool mcp__gatekeeper__permission_prompt \
        2>&1 | tee resultado.txt; ec=\${PIPESTATUS[0]}; \
        echo \"MAESTRO-EXIT:\$ec\" | tee -a resultado.txt; \
        sleep \"\$MAESTRO_LINGER\"'"
      ```
      **The `\$` before `{PIPESTATUS[0]}`, `ec` and `MAESTRO_LINGER` is
      deliberate, not escaping debris.** The `herdr pane run` above runs in the
      double-quoted shell of the maestro session ITSELF (the one assembling the
      command), not in the child's shell. Without the `\`, these three variables
      expand HERE — empty, because they do not exist in this shell — before the text
      reaches the child pane: the result would be `ec=`, `MAESTRO-EXIT:` with no
      code and `sleep ""`, silently breaking the file-based synchronization that
      `maestro-poll` depends on (confirmed live: running the
      recipe without the `\` produces exactly that). Never "clean up" those backslashes
      thinking they were left by mistake.
      **Never split the pane that is in focus and never omit the home pane
      id** — `--no-focus` only prevents the new pane from STEALING focus after
      it is created, it does not choose where the pane is born (what chooses is the first
      argument of `herdr pane split`). `herdr pane split` creates the new pane IN THE
      TAB of the pane you point at, regardless of which tab is in focus at the
      moment — it is this property that solves the item (proven live: a
      tab without focus received the split and got the new pane; the tab with focus did
      not change).
      `--mcp-config .mcp.json --strict-mcp-config` is NOT optional: without it the
      child comes up without the gatekeeper, `--permission-prompt-tool` points to a
      nonexistent tool and the process aborts with
      `MCP tool mcp__gatekeeper__permission_prompt not found` / exit 1 — the whole wave
      is born dead (it happened in WEGO-paralelo, 2026-08-24). The
      `--strict-mcp-config` also keeps the owner's personal MCPs from leaking into
      the headless child.
      The marker's `tee -a` is what leaves `MAESTRO-EXIT:` in `resultado.txt`,
      not only in the panel — it is by file that `maestro-poll` syncs.
      The `<slice-prompt>` carries the demand, the surface, the `acceptance`/
      `acceptance_cmd`, the `context` and the autonomous-mode discipline.
      `maestro-wave-state set-slice PROGDIR <slice> running --pane <novo-pane> --worktree <path>`.

      **Fallback: dead home pane.** If `herdr pane split` returns
      `pane_not_found` (the home pane's tab was closed), do not fall back to the
      current focus — open a new, predictable tab in the same Space:
      `herdr tab create --workspace <home.workspace> --label <PROG> --cwd <worktree> --env MAESTRO_LINGER=600 --no-focus`,
      use the returned `root_pane` as this slice's pane (rename + run as
      above) and **update the home pane** with
      `maestro-wave-state set-home PROGDIR --pane <root_pane> --tab <tab-of-the-new-tab> --workspace <home.workspace>`
      so that the next slices of this wave are also born there, instead of each
      one opening its own new tab.

7. **Wave event loop** (mandatory — without it there is deadlock). In rotation, until the
   wave finishes:
   - `python3 maestro/bin/maestro-poll PROGDIR` (syncs by FILE, not
     by the pane). For each transition, `set-slice` the terminal state
     (DONE/FAIL/TIMEOUT/ESCALATED); on TIMEOUT, kill the child via herdr.
   - **Escalations**: for each pending one, present it to the human (action, slice,
     context, options). Record the decision in the `escalations/<id>.yaml` itself
     (`estado: answered`) and **re-spawn the child** injecting "owner's decision
     on <id>: ..." into the prompt — it continues from the worktree where it stopped. The
     re-spawn uses the SAME recipe as step 6c (`herdr pane split` against the
     home pane from `maestro-wave-state get PROGDIR` → `home.pane`, rename, `herdr
     pane run`) — never the focus of the moment.
   - **Retry under a new name** (`S-2067R` born from `S-2067`): fork it with the
     same step 6c recipe against the recorded home pane, and record it
     at the same instant you fork it,
     `maestro-wave-state set-slice PROGDIR <slice>R running --pane <id> --worktree <path>
     --detail "retry of <slice>"`. In wave 1 of WEGO-paralelo the
     retries only entered the wave-state in the following wave, and two sessions
     thought they owned them.
   - **Gatekeeper health**: if `poll` reports `gatekeeper.alive:false`,
     bring it back up (same port/state) and carry on — a child without the gatekeeper gets deny and
     escalates (declared fail-mode).
   - Wait between iterations (`poll` is cheap; do not do a tight busy-loop).

8. **Termination boundary** (before the merge train — mechanical, not the impression of
   whoever was driving):

   ```
   python3 maestro/bin/maestro-wave-state check-terminal PROGDIR
   ```

   Exit 0 = every slice in a terminal state (`DONE|LANDED|FAIL|TIMEOUT|ESCALATED`).
   Exit 2 = there is still a hanging slice, and the command names which ones. **With exit 2 do not
   go on to the merge train or to the report**: go back to the event loop, or force
   the honest terminal state (`set-slice PROGDIR <slice> ESCALATED --detail "<what
   was left unanswered>"`). `pending`/`running` are not results — they are the
   absence of one, and a wave that lands with a slice in there makes that slice
   vanish from the radar without anyone having decided anything about it.

9. **Merge train** (post-wave — REUSES the `/common:worktree-merge` guards,
   never reimplements them):
   - only DONE slices go in; FAIL/TIMEOUT/ESCALATED re-fork in the next wave
     from the new main (the wave does NOT stall);
   - deterministic order (plan order); for each: green-gate + single-owner
     + `git merge --no-ff`; **verify on the integrated main after EACH merge** (not only
     the slice's verify — a semantic conflict between disjoint surfaces only
     shows up here). Red after merge → revert the merge, the slice becomes FAIL;
   - conflict → STOP and show it (do not auto-resolve);
   - `maestro-wave-state landed PROGDIR <slice>` at each merge (the slice goes from
     `DONE` to `LANDED`). This is what lets `aguardando-merge` answer, after
     a dead session, what was left to land: `DONE` without `LANDED` is what
     `/common:next` and the doctor flag as your action;
   - **prune only at the end of the whole wave** (a worktree is cheap; evidence does not
     come back): `python3 maestro/bin/maestro-prune PROGDIR --repo <main-root>`.
     Each slice is a Space in the herdr sidebar (`herdr worktree create`
     creates worktree **and** Space); without prune a wave of 5 slices leaves 5 Spaces
     — on 2026-08-24 there were 11 left over from two waves. `maestro-prune` removes
     Space + worktree only for LANDED slices (`herdr worktree remove --workspace`
     takes both down in one go, and the result is confirmed by git — not
     by herdr's word, the same principle as step 6a); it keeps the others
     (DONE-not-landed, FAIL/TIMEOUT/ESCALATED, pending, running) because their
     evidence may still be useful; and it never forces a dirty worktree — it reports
     and lets the owner decide. Show its output in the step 10 report.

10. **Report + debrief.** Only after step 8 is green. Write the report to the user in
   Brazilian Portuguese (pt-BR). Summarize: intake verdict
   per slice, terminal states, escalations and how they were decided,
   merges landed, what re-forks. List the gatekeeper's gray-zone/escalated decisions (they go into
   the default debrief regardless of altitude). Emit the telemetry
   (`program_start/wave_done/...`) and state the next step (next wave or end).

## Notes

- **Seam invariant:** this command reads only the plan.yaml. Future sources
  (Jira/board-flow, discovery) come in by writing a valid plan.yaml.
- **Recovery:** the wave-state is written at every transition; if the session dies,
  `/maestro:resume <PROG>` rebuilds the wave from where it stopped.
- **Shadow-mode** (1st program): the gatekeeper approves everything and logs what it WOULD have
  denied/escalated — it measures whether intake can bring escalations to zero, instead of
  requiring one to be planted. Active deny from the 2nd on, with rules calibrated by the log.
- **Approval scope (gatekeeper and escalations):** each approval releases ONLY the
  command/request presented, never the child or the wave. An escalation decided
  by the human holds for that instance; the same class of request goes back to the
  gatekeeper on its next occurrence. "I approved it once" does not become an implicit allowlist
  — an allowlist is a rule change, made in the generated settings, with intent.
- Synchronization is by file (resultado.txt + wave-state); the herdr pane is
  observability. The contract of the `MAESTRO-EXIT:*` markers is a string-match
  versioned with the plugin — smoke-test it at every upgrade of herdr AND of Claude Code.
