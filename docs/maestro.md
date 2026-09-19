# maestro

Multi-harness orchestration: plan a universe of demands into **waves** of
concurrent Claude Code sessions and land them with one action. Where the build
topologies run *one* agent team in *one* session, Maestro runs *N real
sessions* in parallel — each on its own worktree, each mediated by a permission
gatekeeper — and integrates their results with a verified merge train.

> **Status (2026-09-19, maestro 0.5.0): experimental, not yet proven end to end.**
> Construction steps 1–3 are done and tested (the design, the intake gate, the
> deterministic run cores, and the `run`/`resume` commands). Step 4 ran once on
> real work: wave 1 of `WEGO-paralelo` (2026-08-24, in `wego-acesso-backend`)
> forked 5 children through `herdr` with the gatekeeper in shadow-mode. It
> exposed four defects (gatekeeper config in the wrong file, poll reading the
> wrong path, `Write(path)` rules rejected, gatekeeper letting writes pass as
> reads), fixed in 0.4.3, and the maestro session died before the merge train,
> so all 5 branches were merged by hand. **Still unproven:** a full wave on
> 0.4.3+ that lands through the merge train on its own, and the gatekeeper in
> active-deny mode. And nothing here works until you reinstall
> (`bin/install.sh --clean`) and have `herdr` running. Full design and decisions:
> [`.claude/programs/maestro/design.md`](../.claude/programs/maestro/design.md).

## When to use it (and when not)

Use Maestro when you have **≥4 independent demands** that split into ≥2 waves or
≥2 parallel slices with room to spare — a multi-item push where the overhead of
planning + intake + merge train (~1 session) stays under ~25% of the total work.
This is the `D7` floor, and the intake gate enforces it.

With 3 demands or fewer, `/board-flow:drain` or a single session beats the
orchestration overhead — don't reach for Maestro.

## Vocabulary

| Term | Meaning |
|---|---|
| **Program** | A universe of demands approved as a unit (e.g. `melhorias-2026-07`). Lives at `.claude/programs/<name>/`. |
| **Demand** | One backlog item in the program (P1, P2…). |
| **Slice** | The unit of execution: one demand packaged for **one session** in **one worktree**. Usually 1 demand = 1 slice; a big demand may split into 2+. |
| **Wave** | A group of slices that run in parallel from the same fork point. Wave N+1 forks only after wave N lands on main. |
| **Gatekeeper** | A small separate process that decides each child session's permissions. See [The gatekeeper](#the-gatekeeper). |
| **herdr** | Local terminal/session manager (panes + worktrees) used as Maestro's control plane. Must be running. |

## The three commands

```
/maestro:program-plan   →   /maestro:run   →   (/maestro:resume if interrupted)
    write plan.yaml           execute a wave        rebuild a dead wave
```

### 1. `/maestro:program-plan <name>`

Conversational. Reads a source (default `BACKLOG.md`, or `--source FILE`),
analyzes each demand's **file surface**, dependencies, and human gates, proposes
waves with disjoint surfaces, and writes `.claude/programs/<name>/plan.yaml`.
Then it runs the intake gate (`cepa-dor`) and iterates *with you* until every
slice is `READY`.

Two alternative source modes:

- `--sweep` — instead of a hand-picked list of demands (`--demandas`), reads the
  whole source and proposes the next 2–3 waves itself. Still a proposal: nothing
  is written without the conversation.
- `--from-plan NAME` — the source is the repo's `single-track` queue
  (`.claude/programs/NAME/plan.yaml`, written by `/common:plan`) instead of a
  prose file. This is the queue → waves promotion, and the way to use Maestro in
  a Jira repo (the queue accepts the board as a source; `--source` does not).
  The queue itself is read by `common/bin/cepa-plan promote` and left untouched;
  the wave plan needs its own name, different from the queue's.

This is the **only** command that reads the BACKLOG (or any other source).
Everything downstream reads only `plan.yaml` (the seam invariant — see below).

### 2. `/maestro:run [<name>] [--wave N] [--shadow] [--port P]`

The single action. For the current wave: gc of orphans → intake gate → bring up
the gatekeeper (on `--port`, default 8765) → fork each slice into a `herdr`
worktree with generated settings + the normative wrapper → run the file-based
event loop → land the wave with the merge train → report. Reads only
`plan.yaml`.

With no program name it runs nothing: `maestro-programs` lists what this repo
can run (mode, next pending wave, `RODA` or the reason it can't, plus leftovers
of an earlier run such as a `wave-state.yaml` or an orphan gatekeeper) and stops.
This listing mode needs neither `herdr` nor a reinstall.

### 3. `/maestro:resume <name>`

Rebuild an interrupted wave from `wave-state.yaml` (written on every transition)
and continue the event loop / merge train from where it died. Death of the
maestro session is the most likely failure of a long run, so this is a
first-class path, not an afterthought. Modeled on `/common:autonomous-resume`.

## The plan.yaml (schema v2)

Copy the `mode: parallel-waves` block from
[`common/plan-schema.yaml`](../common/plan-schema.yaml) — it's the annotated
source of truth, shared with board-flow's `single-track` mode.

Versions: **1** is the legacy shape (waves only, no `mode`) and is still read by
every consumer — existing plans need no migration. **2** makes `mode` explicit
and required, so a wave-only consumer can refuse a document it cannot read
instead of treating a missing `waves` as an empty plan. The shape:

```yaml
schema_version: 2               # required; consumers accept 1 (legacy) and 2
mode: parallel-waves            # required in v2; single-track = board-flow
program: exemplo
source: BACKLOG.md
max_concurrent_slices: 3        # ceiling = human attention, not the machine
waves:
  - id: 1
    mode: parallel-worktrees
    fork_after: null            # null = fork from current main; "wave-1" = after wave 1 lands
    slices: [S1, S2]
    status: pending
slices:
  S1:
    demanda: "P9 do BACKLOG"    # anchor in the source (D7 counts distinct demandas)
    surface:                    # globs, expanded at the fork point; DISJOINT across
      - "common/hooks/foo*.py"  # slices in the wave; the enforcement zone is an
      - "docs/foo.md"           # unconditional veto
    human_gate: none            # 'none' OR the already-made strategic decision, recorded
    acceptance: "pytest tests/test_foo.py green + hook fires in scenario X"
    acceptance_cmd: "python3 tests/test_foo.py"   # REQUIRED in a .claude/no-build repo
    context: ["BACKLOG.md#p9", "docs/foo-notes.md"]
    bash_extra: ["pytest"]      # Bash allows beyond the generated base set
    timeout_min: 45
    status: pending
```

### The seam invariant

`/maestro:run` reads **exclusively** `plan.yaml`. Any future source — Jira via
board-flow, discovery — plugs in by *writing a valid plan.yaml*, never by
touching the engine. This is what keeps the orchestrator decoupled from where
demands come from.

## The intake gate (`cepa-dor`)

Before any slice forks, `common/bin/cepa-dor` gives a `READY` / `NOT-READY`
verdict per slice with named gaps. It's an **invocable primitive** (Maestro is
its first client; `/board-flow:triage` and `/board-flow:drain` are foreseen
consumers), so you can run it by hand:

```
python3 common/bin/cepa-dor .claude/programs/<name>/plan.yaml --wave 1 --repo .
```

A slice is `NOT-READY` if any of these fail (each check exists because the
corresponding failure once cost a wave):

- **surface declared and disjoint** — globs are expanded against the file tree
  at the fork point and intersected; a non-empty intersection downs **both**
  slices (the v0 merge-conflict lesson: two slices silently touched
  `atlassian-expert.md`);
- **surface doesn't touch the enforcement zone** (`plugins/`, `hooks/`,
  `.claude/settings*`, plugin cache) — unconditional veto;
- **testable acceptance declared**; in a `.claude/no-build` repo, an executable
  `acceptance_cmd` is mandatory (the merge train can't land N slices with zero
  verification);
- **zero open strategic decision** (`human_gate: none` or a recorded decision) —
  the #1 predictor of mid-wave mediation;
- **minimal context** pointed to (spec/card/doc links);
- **green baseline** at the fork point (same `last-build.json` signal as
  green-or-revert);
- **program has ≥4 demands** (D7).

High-friction files nobody declared (lockfiles, migrations, barrel/index) become
a **named warning**, not a veto — the post-merge verify in the merge train
catches incidental conflicts.

## Enforcement: three named layers

A single-layer gate is bypassable (a lesson this repo paid for more than once).
Each child session runs under three layers:

1. **Generated settings** (`maestro-fork-settings`, the primary layer): from the
   slice's `plan.yaml`, Maestro writes the worktree's `settings.json` —
   deny-by-default; file edits allowed only on the declared surface globs;
   `Bash` allowed to a conservative base set + the slice's `bash_extra`.
   Path rules are emitted as `Edit(glob)` only: Claude Code rejects `Write(glob)`
   ("only Edit(path) rules are matched by file permission checks") and `Edit`
   already covers every file-editing tool.
   **Critically, it emits `ask` rules** that route everything else to the
   gatekeeper — without them the headless default pre-approves "safe" commands
   and the gatekeeper is never consulted (a real finding from the spike).
2. **Harness hooks** inherited in the worktree (path-lock, bash-path-lock,
   enforcement-guard, gate-advance), with an **unconditional deny** on the
   enforcement surface.
3. **The gatekeeper** — the judgment layer, receiving only what layers 1–2 did
   not pre-decide.

## The gatekeeper

`maestro-gatekeeper` is a small **separate process** (an interactive session
can't serve an MCP endpoint while it's talking to you). It serves the
`--permission-prompt-tool` MCP contract over **loopback HTTP**, one server per
wave shared by all N children. Each child reaches it through a generated `.mcp.json` and is launched with
`--mcp-config .mcp.json --strict-mcp-config --permission-prompt-tool
mcp__gatekeeper__permission_prompt`, with the slice identity carried in the URL
(`?slice=S1`) — because the permission payload itself doesn't name the child.
**`mcpServers` inside `settings.json` is not read.** Declaring the gatekeeper
there (and dropping the `--mcp-config` flag) is what killed wave 1 of
WEGO-paralelo on 2026-08-24: every child aborted at startup with
`MCP tool mcp__gatekeeper__permission_prompt not found` and exit 1.

Its engine (decision `D5`): **mechanical rules; the gray zone always escalates**
(no LLM in the permission path in v1). Explicit strategic patterns (editing a
contract/OpenAPI, push/publish, broad delete, writing the enforcement surface)
escalate; a denied child ends its turn immediately reporting
`MAESTRO-EXIT:ESCALATED:<id>` (it does **not** loop waiting) and the maestro
session drains the escalation queue, gets your decision, and re-spawns the child
with the decision injected.

### Shadow-mode (first program)

On your **first** program the gatekeeper runs in **shadow-mode**: it approves
everything and *logs what it would have denied or escalated*. This measures
whether the intake gate actually zeroes out escalations, instead of forcing you
to plant a synthetic one. Active deny starts on the second program, with rules
calibrated from the first program's log. Force it any time with `--shadow`.

## The event loop and merge train

**Event loop** (`maestro-poll`, run in rotation): synchronization is **by file**
(each child's `resultado.txt` + `wave-state.yaml`), never by the herdr pane (the
pane is cosmetic). Each running slice reaches exactly one terminal state —
`DONE` / `FAIL` / `TIMEOUT` / `ESCALATED`, never "hung" — decided by the
`MAESTRO-EXIT:*` marker the normative wrapper guarantees. The loop also drains
escalations, heartbeats on file mtime, and resurrects a dead gatekeeper.

**Merge train** (reuses `/common:worktree-merge`'s guards — green-gate,
single-owner, conflict-stop — never reimplements them): only `DONE` slices
merge, one at a time in plan order, **with a full verify on the integrated main
after *each* merge** (a semantic conflict between disjoint surfaces only shows up
here). Red after a merge → revert it, the slice becomes `FAIL`. A conflict →
**stop and show you** (never auto-resolve). `FAIL`/`TIMEOUT`/`ESCALATED` slices
re-fork in the next wave from the new main — the wave does not stall. Worktrees
are pruned only after the whole wave lands (a worktree is cheap; lost evidence
isn't).

## Crash recovery

`wave-state.yaml` is written on every transition (live children with pane/PID,
per-slice state, gatekeeper pid/lease, pending escalations, landed merges). If
the maestro session dies, `/maestro:resume <name>` reconstructs the wave,
**reconciles against reality** (health-checks the gatekeeper, confirms live
panes, re-reads markers) before asserting anything, and continues. It's
idempotent by design: re-reading a finished `resultado.txt` reaffirms the same
terminal state; a merge already in `landed` is skipped.

## Files at a glance

| Path | What |
|---|---|
| `maestro/commands/{program-plan,run,resume}.md` | The three commands. |
| `common/plan-schema.yaml` | Annotated plan.yaml (schema v2; v1 still read) — canonical, both modes. |
| `maestro/plan-template.yaml` | Pointer to the above (kept so old links resolve). |
| `maestro/bin/maestro-programs` | Read-only listing of runnable programs (`/maestro:run` with no name); `--check-name` guards new plan names. |
| `maestro/bin/maestro-fork-settings` | Generates a child's `settings.json` + `.mcp.json` pair (layer 1); `--out-dir <worktree>` writes both. |
| `maestro/bin/maestro-gatekeeper` | The permission gatekeeper (MCP over loopback HTTP). |
| `maestro/bin/maestro-poll` | One event-loop iteration (by file marker). |
| `maestro/bin/maestro-wave-state` | Crash-recovery state store. |
| `common/bin/cepa-dor` | The invocable intake gate (Definition of Ready). |
| `.claude/programs/<name>/` | Per-program: `plan.yaml`, `wave-state.yaml`, `gatekeeper/`, `slices/`. |
| `.claude/programs/maestro/design.md` | Full design + the 7 owner decisions. |

## Known debts (named, not hidden)

- The wrapper's `MAESTRO-EXIT:*` markers are string-matched — versioned with the
  plugin and smoke-tested against every `herdr` **and** Claude Code upgrade
  (`--permission-prompt-tool` was undocumented in the CLI `--help` as of 2.1.210
  but functional).
- Two worktree homes exist (`~/.herdr/worktrees` vs `~/cepa-worktrees`); the herdr
  worktree inherits the single-owner guard and `.env` seeding from the cepa model.
- Step 4 has run once (wave 1 of `WEGO-paralelo`, 2026-08-24) and did not land
  on its own: the merge train only runs while the maestro session is alive, and
  `wave-state.yaml` does not tell "still running" from "finished, waiting to be
  merged". Tracked in `BACKLOG.md` ("Onda termina e ninguém aterrissa"). No wave
  has run on 0.4.3+ yet.
