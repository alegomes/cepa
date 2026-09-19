# Command reference

Two ways in. **Part 1** is organised by what you are trying to do and points at the command.
**Part 2** is the full reference, one table per plugin, with arguments and behaviour.

Command namespacing: every command is `/<plugin>:<command>`. The bare
form (`/plan-build-validate`) returns "Unknown command".

# Part 1: what are you trying to do?

### "I want to implement a new feature"

- Known requirements, no Jira → `/build-hex:plan-build-validate <description>` (or `/build-team:plan-build-validate` for non-hex projects).
- Known requirements, Jira-tracked → `/board-flow:plan-track-build-validate <description>` (creates Epic + Stories, runs one Story end-to-end).
- Existing Jira card with the description (Story/Task/Epic) → `/board-flow:execute <KEY>` (auto-routes Bug cards to `/board-flow:fix`).
- Existing Jira card known to be a Bug → `/board-flow:fix <KEY>` (skip the auto-detect; go straight to reproduce-fix-verify).
- Unattended → `/common:autonomous-start "<KEY> <description>"` (auto-detects key, wraps with lifecycle).

### "I want to fix a bug"

- Local, no Jira → `/build-hex:reproduce-fix-verify <description>` (or describe in chat for `build-solo`).
- Jira-tracked → still `/build-hex:reproduce-fix-verify` directly, or wrap with `/common:autonomous-start "<KEY> bug: <description>"`.

### "I'm not sure if X is a problem"

- `/build-hex:investigate <hypothesis>`. Read-only. Outputs a findings report with a recommended next command.

### "I want to design a new endpoint's behavior"

- `/build-hex:spec-e2e <METHOD /path> "<intent>"` — prescriptive, intent-driven. Spec describes what the endpoint *should* do.

### "I want to document an existing endpoint's behavior"

- `/build-hex:document-e2e <METHOD /path>` — descriptive, code-driven. Spec captures what the endpoint *currently does*.

### "I edited the spec; tests need to follow"

- `/build-hex:resync-e2e <METHOD /path>` (or `--all`). Spec → tests propagation.

### "Spec, code, and tests might disagree"

- `/build-hex:audit-e2e <METHOD /path>` (or `--all`). 3-way diff, no propagation. You pick the fix direction.

### "I want to step away while it works"

- `/common:autonomous-start "<task or Jira key>"`. Comes back later, runs `/common:debrief` to review decisions.

### "I lost the thread of what's been done"

- `/common:recap`. Reads the session log + conversation context, renders "Asked / Status / Delivered" table.

### "I want to stop and pick up cleanly in a new session"

- `/common:handoff`. Writes the rich handoff; the next session resumes from it automatically (no need to mention it). The `session-checkpoint` Stop hook already keeps a mechanical skeleton current every turn, so even a token-limit kill leaves something to resume from. See [handoff.md](handoff.md).

### "I want to branch off into a side topic, then come back"

- `/common:branch <assunto>` in the origin session, discuss it in a fresh session via `/common:branch resume`, then `/common:return` to bring back only the conclusion. Nested forks unwind LIFO. For a self-contained side task with no human in the loop, spawn a subagent instead — it's the non-interactive sibling. See [`context-forking.md`](context-forking.md).

### "I want to track work in Jira"

- First time: `/board-flow:configure`. Walks you through the config.
- New work item, no detail yet: `/board-flow:capture "<description>"`. Just registers, doesn't execute.
- Drain a column: `/board-flow:drain` (default column = `to_do` from `status_map`).
- Custom lifecycle column transition: `/board-flow:advance <KEY>`.

### "I have ≥4 independent demands to run in parallel"

- `/maestro:program-plan <name>` to turn them into a wave plan (`plan.yaml`),
  gated by the intake check until every slice is `READY`. Then `/maestro:run
  <name>` to execute the wave with one action, and `/maestro:resume <name>` if
  the session dies mid-wave. With 3 demands or fewer, use `/board-flow:drain` or
  a single session instead — the orchestration overhead isn't worth it. See
  [maestro.md](maestro.md). (Not yet live end-to-end — needs `bin/install.sh
  --clean` + `herdr`.)

### "I know the order I want to work in, and there is no tracker here"

- `/common:plan <nome>` writes the queue: `--from-spec docs/spec/<slug>.md` when
  a `/common:spec` specification already closed (one item per success criterion,
  order inherited from the text and said so), or dictated by hand when the
  demands live in `BACKLOG.md` or in your head, or `--from-jira` with a board —
  `/board-flow:triage` classifies the column and hands the order over, and
  `/common:plan` is the one that writes it. Then `/common:next` names ONE step
  at a time from it.
- `/common:drain-plan <nome>` runs several of them in a row, in the queue's own
  order — `--max` caps the batch (default 3) and it stops at the first item it
  cannot resolve alone (an open `human_pending`, a blocked item, one reserved by
  another session). Use it when you already know the next few items are yours to
  build; use `/common:next` when you only want to know what comes next.

### "I have a vague idea and want a spec before any code"

- `/common:spec`. Interviews you in rounds until every success criterion has an observable surface and a failing test declared. Writes no code. Resumable.

### "I have an old backlog and don't know what is still valid"

- `/board-flow:triage [column]`. Classifies every card (already built, ready, obsolete, needs your decision) from evidence in the code. Writes nothing until you confirm.

### "I want to clear the Review column"

- `/board-flow:prove <KEY>` for one card, `/board-flow:prove-drain` for the column. Then `/board-flow:decide` turns whatever stayed `NEEDS-HUMAN` into a few yes/no questions.
- UI or browser extension: `/common:prove-ui`.

### "I want to run the queue overnight"

- `cepa-until <queue> --for 8h` from the terminal. See [cepa-until.md](cepa-until.md).

### "I want a session that doesn't ping-pong with me"

- `/common:session <routine>`. All questions at the start, the routine runs to the end, one final report.
- Closing: `/common:wrap-up` (commit, handoff, merge, push behind one confirmation).

### "I want a second opinion on a decision before closing it"

- `/common:advisors <artifact>`. Isolated review lenses, then a synthesis that names the disagreements.

### "I want to open or merge a pull request through the gates"

- First time: `/review-gate:configure`. Then `/review-gate:open`, and `/review-gate:merge` (merges only on PROVEN). `/review-gate:review` runs just the hygiene check.

### "I want to design a feature before engineering builds it"

- `/design:explore-critique-spec <feature>`.

### "I want to document an existing project for onboarding"

- `/docs:survey`, then `/docs:declutter`, `/docs:checkpoint`, `/docs:author`, `/docs:finalize`. `/docs:status` shows where you are.

### "Something in the tooling looks wrong"

- `/common:doctor` checks the install against reality. `/common:metrics` shows where the harness blocks or costs you. `/common:feedback "<complaint>"` records it so it becomes a backlog item. `/common:modos` reminds you which mode the session is in.

# Part 2: reference by plugin

## common

Cross-topology commands. Work in any project regardless of which
topology is wired.

| Command | Argument | What it does |
|---|---|---|
| `/common:autonomous-start` | `[--topology=X] [--flow=NAME] [--no-jira] <description, may include Jira key>` | Generates a run-id, writes initial `docs/autonomous/<run-id>/state.yaml`, activates `autonomous-mode` skill, dispatches into the right topology flow. Auto-detects Jira key (`[A-Z]{2,}-\d+`); if found AND `board-flow.yaml` exists, wraps the run with Jira lifecycle (In Progress → flow → In Review with Implementation Summary). |
| `/common:autonomous-resume` | `[run-id]` (defaults to most recent in-progress) | Reads `state.yaml`, reconstructs topology + flow + last position, re-activates `autonomous-mode`, continues from next pending step. Won't fabricate progress on ambiguous state. |
| `/common:debrief` | `[run-id]` (defaults to most recent completed-but-not-debriefed) | Human-in-the-loop ceremony. Walks every `### Decision:` block from the run's artifacts, takes your verdict (`keep` / `overrule: <reason>` / `refine: <new rationale>`), writes to `common/expertise/<agent>-mental-model.yaml` under `feedback`. Dual-scan also flags format drift (informal-prose decisions vs. formal Decision blocks). |
| `/common:recap` | `[--since=YYYY-MM-DD]` (default: today) | Renders an "Asked / Status / Delivered" table for the current session. Reads `.claude/session-log.md` (intent log from `session-log` hook) and reasons over conversation context for delivery evidence. Read-only. |
| `/common:handoff` | (none) | Saves a rich session handoff for seamless resume. Writes the narrative (decisions, current state, next concrete step, caveats, open threads) into this branch's `.claude/handoffs/<branch-slug>.md`, on top of the mechanical skeleton the `session-checkpoint` Stop hook keeps current every turn. The next session's `SessionStart` (`session-registry`) surfaces it automatically. Replaces hand-writing "salve a memória de handoff". See [handoff.md](handoff.md). |
| `/common:next` | `[--plan NOME] [--offline] [--sync]` | Answers "what do I do next?" at any moment — the middle-of-session counterpart to `/common:recap`, which only reconstructs what was *done*. Reads the single-track execution plan (`.claude/programs/<nome>/plan.yaml`, schema `common/plan-schema.yaml`) and names **one** next step with the `why` recorded when it was prioritised — never a menu, since a list of equal options is the state you're stuck in when you run it. Separates the two kinds of "next" that compete in silence: **pending human action** (the aggregated `Human validation route` — validate by hand, approve a PR, rotate a secret) and **the next item**. **A tracker is optional**: with `board-flow.yaml` it reconciles against the live board and names every divergence; without one it answers from the plan and says the statuses are self-reported. Read-only unless `--sync`. Never invents an order — with no plan it offers to write one (`/board-flow:triage` where a tracker exists). See [execution-plan.md](execution-plan.md). |
| `/common:plan` | `<nome> [--from-spec docs/spec/<slug>.md \| --from-jira [coluna\|repasse.json]] [--dry-run] [--on-missing refuse\|keep\|drop]` | Writes the repo's **single-track execution queue** — `<main-root>/.claude/programs/<nome>/plan.yaml`, the document that keeps the ORDER and the `why` behind each position, which is exactly what a tracker does not keep. Three sources: `--from-spec` turns each success criterion of a `/common:spec` specification into an item, inheriting the order of the text **and saying that it inherited** (a spec's criteria are not prioritised against each other); `--from-jira` writes the queue from a `/board-flow:triage` classification — triage reads the cards, hunts code evidence and proposes the order, and since stage 2 hands it here instead of writing the file itself, so the queue has exactly one writer; with no flag, the queue is dictated by hand — the case of a repo with no tracker and no spec. **No Jira required** for the other two. Writing is mechanical (`common/bin/cepa-plan`): it refuses an empty `why`, a duplicate `id`, a `blocked_by` pointing at a ghost item, a blocking cycle, and — the mirror of `maestro-programs --check-name` — refuses to write the queue over a `parallel-waves` plan. On a rewrite the new list rules the order/title/`why` while the disk keeps `status` and any OPEN `human_pending`, because only the human closes that one. See [execution-plan.md](execution-plan.md). |
| `/common:drain-plan` | `<nome> [--max N] [--dry-run]` | Executes the repo's **single-track queue in the order the queue keeps** — stage 3 of "one writer, three sources", closing the trackerless cycle: `/common:plan` writes it, `/common:next` names one step, this one runs several. **No Jira, ever**: the only bulk executor before it, `/board-flow:drain`, takes its order from the board's `priority and rank` — the very order the plan exists to replace. Which items are runnable now is mechanical (`cepa-plan queue`): the batch walks the list from the top and **stops** at the first thing it cannot resolve alone — an open `human_pending` (the owner's call, 2026-08-25), an item blocked by something outside the batch, one already `blocked` by an earlier run, one reserved by another session, or `--max` (default **3**, lower than drain's 5 because each item is a full topology flow plus the acceptance and proof gates). It never skips a stuck item to reach the one below — that is reordering the queue in silence. Each item is reserved before it is touched (`cepa-plan start`) and leaves with a named terminal outcome plus evidence (`cepa-plan finish`); only the human ever closes a `human_pending`. Refuses a `parallel-waves` plan — that one is `/maestro:run`'s. See [execution-plan.md](execution-plan.md). |
| `/common:feedback` | `[<texto>] [--alvo X] [--listar [--todos]] [--triar]` | Records feedback about **the harness itself**, at any point of any session — the command that asked one question too many, the gate that blocked a legitimate commit, the unreadable report. The ledger is **global** (`~/.claude/cepa-feedback/feedback-YYYY-MM.jsonl`, append-only, `CEPA_FEEDBACK_DIR` overrides), because the target is Cepa while the irritation happens in the client's repo — one file per project would scatter the same complaint across five places nobody re-reads. The text is stored **verbatim** and repo, branch and session mode are captured for you: a complaint you cannot place back in its episode is an anecdote, not a card. Writing is mechanical (`common/bin/cepa-feedback`): it refuses an empty or one-word entry, a triage with no destination, an unknown id, and a **second** triage of the same id (which would silently erase the first decision). No argument lists what is open; `--triar` (only inside the Cepa repo) turns the open ones into `BACKLOG.md` items and marks each destination. The prose path is the `common:feedback-capture` skill plus the `feedback-nudge` hook — you complain in your own words and it gets recorded without a command. |
| `/common:branch` | `<assunto>` \| `resume [<fork-id>]` | Fork the current discussion into an isolated context. `<assunto>` (origin session): snapshots the thread to `.claude/forks/<id>/context.md` and pushes an `open` frame — then stops, without discussing the topic. `resume [<id>]` (fresh session): loads the snapshot, marks `active`, starts the interactive side discussion. No id = top-most `open`/`active` frame. Pairs with `/common:return`. See [`context-forking.md`](context-forking.md). |
| `/common:return` | `[<fork-id>]` (default: top of stack) | Close a fork. In the **side** session: distills the discussion into `resolution.md`, marks `resolved`. In the **origin** session: ingests only that resolution into the main thread, marks the frame `closed` in place (LIFO pop). Picks save-vs-ingest by reading its own conversation; asks if ambiguous. "Top of stack" = top-most non-`closed` frame, which drives both the nested-unwind order and re-ingest idempotence. |
| `/common:session` | `<routine> [routine args]` \| `--help [routine]` | Opens a session with a declared purpose and takes it end to end: gets the harness ready (`doctor --fix`), asks **all** questions at the start, runs the routine without stopping, delivers one final report and offers the wrap-up. |
| `/common:wrap-up` | `[--discard] [commit message]` | End-of-session one-shot behind a single confirmation: commits the session worktree, writes the handoff, then lands the branch (merge + push + prune). `--discard` throws a dead-end worktree away. Reuses `worktree-merge`'s guards. |
| `/common:doctor` | `[--live] [--no-fix] [--projeto]` | Validates the install against reality in about 30 seconds: plugins enabled and at the installed version, hooks compiling, `board-flow.yaml` structure, build baseline, stale or orphaned worktrees, overdue handoffs. `--live` also checks `board-flow.yaml` against live Jira. |
| `/common:metrics` | `[--days N \| --month YYYY-MM] [--repo <name>]` | Telemetry report on the harness itself, from `~/.claude/cepa-telemetry/`: sessions per repo, red-build rate, gate blocks by reason, proof verdicts, over-declared `proven` refused by the guard, and how many turns you spend before and after a routine. |
| `/common:modos` | `[mode-name]` | Shows the table of working modes (what each asks to enter, what it produces, what must be true to close) and marks the current session's mode. Read-only. |
| `/common:advisors` | `<artifact> [--area=…] [--lentes=a,b,c]` | Advisor panel on a decision artifact (design doc, ADR, plan, PR): isolated parallel review lenses, then a synthesis that **names** the disagreements instead of averaging them. Runs before the decision is closed. |
| `/common:prove-ui` | `[flow \| --all \| --draft]` | Proves the UI/extension surface through the mechanical gate: brings the app up, runs the flows declared in `docs/ui-proof.yaml` via Playwright and requires a verifiable backend effect. Returns PROVEN / UNPROVEN / NEEDS-HUMAN. `--draft` proposes a manifest skeleton. |
| `/common:consolidate` | `[agent \| --all]` | Periodic consolidation of the agents' expertise files: merges redundant entries and retires the ones current code contradicts (always verified against the repo). Shows a before/after diff and writes only after your approval. |

### Per-session worktree lifecycle

For running parallel `claude` windows on one repo without collisions. The `cepa`
launcher auto-isolates a session into its own worktree when another live session
already occupies the tree; these commands manage that lifecycle by hand. The
launcher also takes a custom system prompt — `cepa --prompt <nome|caminho>`, or
the `CEPA_PROMPT` default — see [system-prompt-customizado.md](system-prompt-customizado.md).

| Command | Argument | What it does |
|---|---|---|
| `/common:worktree-start` | `<slice>` | Creates `../<repo>-<slice>` on branch `session/<slice>` and tells you where to open the new session. The "spin up parallel work" half. |
| `/common:worktree-list` | (none) | Read-only dashboard of all session worktrees: commits ahead, clean/dirty, live/idle, age, areas touched, conflict prediction against base, build status. |
| `/common:worktree-merge` | `<slice>` | Verifies the branch is green, merges `session/<slice>` into the current branch (surfacing conflicts normally), then removes the worktree and deletes the branch. The "land it" half. |
| `/common:worktree-discard` | `<slice>` | Removes the worktree and deletes its branch after showing exactly what work would be lost. The "throw it away" half. |
| `/common:worktree-name` | `[<name>]` | Renames the current (or a named) session worktree to something readable (`session/<name>`). Optional — naming is never required. |
| `/common:worktree-label` | `[<purpose…>]` (no args = show; `--clear` to remove) | Gets or sets a free-text note of what a session worktree is *for*. Stored as the branch's git description, so it survives the session and never renames the branch. |

## build-hex

The 14-agent hexagonal-architecture topology. Three end-to-end flow
commands + four E2E spec commands.

### Flow commands

| Command | Argument | What it does |
|---|---|---|
| `/build-hex:plan-build-validate` | `<task description>` | Canonical feature flow. `planning-lead` writes spec; `engineering-lead` decomposes into Tasks, runs per-Task quality loop (dev → qa → refactor-advisor → code-reviewer), merges to per-Story integration branch; `validation-lead` cross-cutting verify. |
| `/build-hex:reproduce-fix-verify` | `<bug description / error / repro steps>` | Bug-fix flow. `qa-engineer` writes failing regression test; right dev worker fixes; `qa-engineer` verifies with BUILD SUCCESS evidence; `code-reviewer` APPROVE/REJECT. No planning phase (the failing test is the spec). NOT-A-BUG is a valid outcome. |
| `/build-hex:investigate` | `<question / hypothesis>` | Read-only analysis flow. `engineering-lead` reads (or routes to `integration-analyst` for API questions), writes findings to `docs/investigations/<slug>.md` with `file:line` citations, concludes with `NOT-AN-ISSUE` / `BUG` / `FEATURE-OR-REFACTOR` / `DESIGN-DECISION-NEEDED` + recommended next command. |

### E2E spec commands

Four commands forming the spec lifecycle. See
[`e2e-cycle.md`](e2e-cycle.md) for the full picture.

| Command | Direction | What it does |
|---|---|---|
| `/build-hex:spec-e2e` | **intent → spec** (prescriptive) | `<METHOD /path>` + freeform intent OR `--task <path-to-TASK.md>`. Authors a spec section from your description, not from existing code. Code may not exist yet. Uses `<TBD>` markers for unknown seed values — never fabricates. |
| `/build-hex:document-e2e` | **code → spec** (descriptive) | `<METHOD /path>`. Reads controller + use case + adapter + seed; documents what the code *currently does*. For backfilling specs on shipped endpoints, or freezing behavior before refactor. |
| `/build-hex:resync-e2e` | **spec → tests** | `<METHOD /path>` or `--all`. After spec edits, propagates changes to E2E tests: adds missing, updates value mismatches, removes obsolete. Runs `./mvnw verify` after edits with green-build evidence rule. Stop-on-first-BLOCKED in sweep mode. |
| `/build-hex:audit-e2e` | **read-only 3-way diff** | `<METHOD /path>` or `--all`. Reports drift across Spec↔Code, Spec↔Tests, Code↔Tests for each endpoint. Single-line verdict per endpoint (`ALIGNED` / `MINOR-DRIFT` / `MAJOR-DRIFT`). Doesn't propagate anything; you pick which side to fix. |

## build-team

The generic 9-agent topology.

| Command | Argument | What it does |
|---|---|---|
| `/build-team:plan-build-validate` | `<task description>` | Generic plan → build → validate. `planning-lead` (`product-manager` + `ux-researcher`) → `engineering-lead` (`frontend-dev` + `backend-dev`) → `validation-lead` (`qa-engineer` + `security-reviewer`). No per-Task loop. |

## build-solo

No commands. Describe the task in chat; orchestrator dispatches
`pair-dev` then `pair-reviewer`.

## discovery

| Command | Argument | What it does |
|---|---|---|
| `/discovery:capture` | `"<raw signal>"` | Creates a Jira card on the discovery board in the project's default status (Inbox). Lightweight — no framing, no research, just tracking. Discovery board is configured in `board-flow.yaml`'s `discovery` lifecycle entry. |

Discovery cards advance column-by-column via `/board-flow:advance` (no
`/discovery:plan-build-validate` — discovery is continuous, not phased).

## design

| Command | Argument | What it does |
|---|---|---|
| `/design:explore-critique-spec` | `<feature description or docs/design/<slug>/ path>` | The canonical design flow: explore (flows and visual in parallel), reconcile against the design system, prototype via Gamma/Canva, critique, and assemble a build-ready design spec. |

## docs

Five phases, driven one at a time with an owner checkpoint between them.

| Command | Argument | What it does |
|---|---|---|
| `/docs:survey` | `[scope note]` | Phase 1. Read-only archaeology: inventory, HOW extraction, flow tracing and WHY archaeology in parallel, synthesized into `docs/_survey/gap-report.md`. Touches no source. |
| `/docs:declutter` | (none) | Phase 2. Structural moves from the gap-report's approved list: archives process output out of `docs/`, demotes rival front doors to links. Moves files, rewrites no prose. |
| `/docs:checkpoint` | (none) | Phase 3. Walks the owner through the WHY gaps and drifts. The answers become sourced rationale. No authoring happens before this. |
| `/docs:author` | `[shelf or doc]` | Phase 4. Writes the Diátaxis tree from the survey ledgers. Every WHY traces to a source or is flagged `UNSOURCED`, never guessed. |
| `/docs:finalize` | (none) | Phase 5. Whole-tree consistency review, then owner sign-off. On PASS the `docs/_survey/` scratch is deleted. |
| `/docs:status` | (none) | Shows which phases are done, in progress, awaiting review or not started. No agents. |

## review-gate

The pre-merge gate. Code reaches main only through a reviewed, proven pull request.

| Command | Argument | What it does |
|---|---|---|
| `/review-gate:configure` | (none) | Interactive setup of `review-gate.yaml`: host, default destination branch, close-source behavior, review policy. Offers to wire the Jira seam if `board-flow.yaml` exists. |
| `/review-gate:review` | `[base-ref]` | Runs only the hygiene gate (`/code-review`) on the local diff, without opening a PR. |
| `/review-gate:open` | `[dest-branch]` | Runs the hygiene gate, drafts the PR title and body from the diff, and opens the PR through `bitbucket-expert`. With board-flow wired, also moves the card to In Review. |
| `/review-gate:merge` | `[pr-id]` | Finds the open PR for the branch, runs the topology's `proof-reviewer` as the QA gate, and merges on PROVEN (immediately with `auto_merge: true`, otherwise after your go-ahead). |

## board-flow

The card-lifecycle workflow plugin (talks to Jira today). Pairs with any team.

| Command | Argument | What it does |
|---|---|---|
| `/board-flow:configure` | `[--migrate]` | Interactive setup of `board-flow.yaml` at project root. Validates site against your accessible Atlassian sites (via `getAccessibleAtlassianResources` — no guessing), asks for project_key / board_id / status_map / issue_types / default_topology. Runs smoke test against live Jira at the end. `--migrate` moves legacy `.claude/board-flow.lifecycle.yaml` to the new location. |
| `/board-flow:capture` | `[Epic\|Bug\|Task]: <description>` | Lightweight register. Creates one Jira issue (default type: Story) and stops — no planning, no execution, no transitions. Reads `defaults.project_key` from `board-flow.yaml`. Verifies the card actually exists via read-back before reporting success. |
| `/board-flow:execute` | `<jira-key> [--force-feature-flow]` | Single existing card. Auto-detects issue type: **Bug** cards dispatch to `/board-flow:fix` (reproduce-fix-verify); **Story / Task / Epic** cards run the canonical detail-audit + build + validate flow. `--force-feature-flow` overrides auto-dispatch on Bug. Transitions through `status_map.in_progress` → flow → `status_map.in_review` with Implementation Summary. |
| `/board-flow:fix` | `<jira-key>` | Bug-flow wrapper around the topology's `reproduce-fix-verify` command (failing test first → fix → verify with BUILD SUCCESS evidence → APPROVE). Lighter than `/board-flow:execute` — skips planning enrichment because the failing test IS the spec. Requires a topology with `reproduce-fix-verify` (currently `build-hex` only). NOT-A-BUG is a valid outcome. |
| `/board-flow:plan-track-build-validate` | `<abstract task description>` | Full plan + Jira lifecycle. Registers Epic + 1-3 candidate Stories; executes one Story end-to-end; transitions through `to_do` → `in_progress` → `in_review`. |
| `/board-flow:drain` | `[column] [--max N]` | Bulk-execute cards from a column (default: `defaults.status_map.to_do`, fallback `"To Do"`). User confirmation required before starting. Stops on first BLOCKED card. `--max` defaults to 5. |
| `/board-flow:triage` | `[source-column] [--max N] [--dry-run]` | Groom a backlog column (default `"Backlog"`). Classifies each card into one of four buckets and routes it: **ALREADY-IMPLEMENTED** → `status_map.in_review` (with a triage-sourced Implementation Summary; the proof gate still applies), **READY** → `status_map.to_do`, **OBSOLETE** → Won't Do (per-card confirm, never batch), **NEEDS-DECISION** → grills you interactively, re-routing on your answer. Implementation evidence comes from a per-card read-only `Explore` over the codebase + git (`file:line` + commit). Read-heavy; writes nothing until you confirm the plan (`--dry-run` writes nothing at all). **Does not write `plan.yaml`**: since stage 2 of "one writer, three sources" it emits a handoff (`<programs>/<project_key>/triagem-<YYYY-MM-DD>.json`) and the queue is written by `/common:plan --from-jira`, so the rules that turn a classified card into an item are code instead of this command's prose. Scope-aware like `*-drain`. `--max` defaults to 15. Routes by evidence — it does **not** prove; follow with `/board-flow:prove-drain`. |
| `/board-flow:prove` | `<jira-key>` | Change-driven proof gate for a card already in `status_map.in_review`. Delegates to the topology's `proof-reviewer` (currently `build-hex`), which proves every changed line is load-bearing at the external surface — IT coverage of the diff, diff-scoped mutation, adversarial input, and (for bugs) regression-red-at-base. Verdict drives the transition: **PROVEN** advances to `status_map.done` (if set), **UNPROVEN** returns to `in_progress` with the gap, **NEEDS-HUMAN** stays in Review. See [proof-gate](proof-gate.md). |
| `/board-flow:prove-drain` | `[--max N]` | Bulk-prove the Review column (`status_map.in_review`). Runs `/board-flow:prove` per card in priority order. Unlike `/board-flow:drain`, does NOT stop on a failed card — UNPROVEN bounces back and the drain continues. User confirmation required. `--max` defaults to 5. |
| `/board-flow:decide` | `[--max N] [--scope "<jql>"] [--no-scope] [--dry-run]` | Turns the Review column into a short list of closed questions. Reads each card's proof artifact, classifies the NEEDS-HUMAN reason (see [needs-human-motivos.md](needs-human-motivos.md)), removes what is nobody's decision (Docker down, missing tool), groups the rest by reason and asks **one** question per group with a recommendation. You answer in a batch and it applies. Runs no proof. |
| `/board-flow:advance` | `<jira-key>` | Generic column-by-column transition driven by `lifecycles[]` in `board-flow.yaml`. Used by discovery (and any topology with a custom lifecycle). Runs the column's `on_enter` agent if declared, confirms `enter_gate` precondition with you if declared, transitions with Implementation Summary if `requires_summary: true` (or status name contains `review`/`qa`). |

## maestro

Multi-harness orchestration: plan a universe of ≥4 demands into waves of
concurrent Claude Code sessions and land them with one action. **Not yet live
end-to-end** — construction steps 1–3 done + tested, step 4 (first real wave via
`herdr`) unrun; nothing works until `bin/install.sh --clean` + `herdr` running.
Full guide: [maestro.md](maestro.md).

| Command | Argument | What it does |
|---|---|---|
| `/maestro:program-plan` | `<name> [--source FILE] [--demandas "P9,P10,…"] [--sweep] [--from-plan NOME]` | Conversational planning. Reads a source (default `BACKLOG.md`; with `--from-plan NOME` the source is the repo's **single-track queue**, read by `cepa-plan promote` — the queue → waves promotion, and the way to use this command on a Jira project, since the queue takes the board as a source and `--source` only takes a file: only `pending` items are promoted, `blocked_by` becomes a wave FLOOR, an open `human_pending` becomes an open `human_gate`, and below the D7 floor it stops and points at `/common:drain-plan`), analyzes each demand's file surface + dependencies + human gates, proposes waves with disjoint surfaces, writes `.claude/programs/<name>/plan.yaml` (schema v2; v1 plans still read, no migration), then iterates the intake gate (`cepa-dor`) with you until every slice is `READY`. The **only** command that reads the BACKLOG — everything downstream reads only `plan.yaml` (seam invariant). Floor: ≥4 demandas (D7). |
| `/maestro:run` | `<name> [--wave N] [--shadow] [--port P]` | The single action for the current wave: gc of orphans → intake gate → bring up the gatekeeper (shadow-mode on the 1st program) → fork each slice into a `herdr` worktree with generated settings + the normative wrapper → file-based event loop (`DONE`/`FAIL`/`TIMEOUT`/`ESCALATED` per slice) → merge train reusing `worktree-merge`'s guards with a verify after **each** merge → report. Reads only `plan.yaml`. Requires `herdr` running. |
| `/maestro:resume` | `<name>` | Rebuild an interrupted wave from `wave-state.yaml` (written on every transition), reconcile against reality (health-check gatekeeper, confirm live panes, re-read markers), continue the event loop / merge train. Idempotent. Modeled on `/common:autonomous-resume`. |

Three helpers you can run by hand: `python3 common/bin/cepa-dor <plan> --wave N`
(the intake gate — `READY`/`NOT-READY` per slice),
`python3 maestro/bin/maestro-fork-settings <plan> <slice>` (preview a child's
generated `settings.json`), and `python3 common/bin/cepa-plan validate <plan>`
(the single-track queue's own checks — empty `why`, ghost `blocked_by`, blocking
cycle; `check-name <nome>` answers whether a program name is free for a queue
before you write one).
