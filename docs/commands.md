# Command reference

Every slash command shipped by the marketplace, grouped by plugin. For
when-to-use guidance see [`workflows`](#when-to-use-which-command) at the
bottom.

Command namespacing: every command is `/<plugin>:<command>`. The bare
form (`/plan-build-validate`) returns "Unknown command".

## common

Cross-topology commands. Work in any project regardless of which
topology is wired.

| Command | Argument | What it does |
|---|---|---|
| `/common:autonomous-start` | `[--topology=X] [--flow=NAME] [--no-jira] <description, may include Jira key>` | Generates a run-id, writes initial `docs/autonomous/<run-id>/state.yaml`, activates `autonomous-mode` skill, dispatches into the right topology flow. Auto-detects Jira key (`[A-Z]{2,}-\d+`); if found AND `jira-flow.yaml` exists, wraps the run with Jira lifecycle (In Progress → flow → In Review with Implementation Summary). |
| `/common:autonomous-resume` | `[run-id]` (defaults to most recent in-progress) | Reads `state.yaml`, reconstructs topology + flow + last position, re-activates `autonomous-mode`, continues from next pending step. Won't fabricate progress on ambiguous state. |
| `/common:debrief` | `[run-id]` (defaults to most recent completed-but-not-debriefed) | Human-in-the-loop ceremony. Walks every `### Decision:` block from the run's artifacts, takes your verdict (`keep` / `overrule: <reason>` / `refine: <new rationale>`), writes to `common/expertise/<agent>-mental-model.yaml` under `feedback`. Dual-scan also flags format drift (informal-prose decisions vs. formal Decision blocks). |
| `/common:recap` | `[--since=YYYY-MM-DD]` (default: today) | Renders an "Asked / Status / Delivered" table for the current session. Reads `.claude/session-log.md` (intent log from `session-log` hook) and reasons over conversation context for delivery evidence. Read-only. |

## hex-backend

The 13-agent hexagonal-architecture topology. Three end-to-end flow
commands + four E2E spec commands.

### Flow commands

| Command | Argument | What it does |
|---|---|---|
| `/hex-backend:plan-build-validate` | `<task description>` | Canonical feature flow. `planning-lead` writes spec; `engineering-lead` decomposes into Tasks, runs per-Task quality loop (dev → qa → refactor-advisor → code-reviewer), merges to per-Story integration branch; `validation-lead` cross-cutting verify. |
| `/hex-backend:reproduce-fix-verify` | `<bug description / error / repro steps>` | Bug-fix flow. `qa-engineer` writes failing regression test; right dev worker fixes; `qa-engineer` verifies with BUILD SUCCESS evidence; `code-reviewer` APPROVE/REJECT. No planning phase (the failing test is the spec). NOT-A-BUG is a valid outcome. |
| `/hex-backend:investigate` | `<question / hypothesis>` | Read-only analysis flow. `engineering-lead` reads (or routes to `integration-analyst` for API questions), writes findings to `docs/investigations/<slug>.md` with `file:line` citations, concludes with `NOT-AN-ISSUE` / `BUG` / `FEATURE-OR-REFACTOR` / `DESIGN-DECISION-NEEDED` + recommended next command. |

### E2E spec commands

Four commands forming the spec lifecycle. See
[`e2e-cycle.md`](e2e-cycle.md) for the full picture.

| Command | Direction | What it does |
|---|---|---|
| `/hex-backend:spec-e2e` | **intent → spec** (prescriptive) | `<METHOD /path>` + freeform intent OR `--task <path-to-TASK.md>`. Authors a spec section from your description, not from existing code. Code may not exist yet. Uses `<TBD>` markers for unknown seed values — never fabricates. |
| `/hex-backend:document-e2e` | **code → spec** (descriptive) | `<METHOD /path>`. Reads controller + use case + adapter + seed; documents what the code *currently does*. For backfilling specs on shipped endpoints, or freezing behavior before refactor. |
| `/hex-backend:resync-e2e` | **spec → tests** | `<METHOD /path>` or `--all`. After spec edits, propagates changes to E2E tests: adds missing, updates value mismatches, removes obsolete. Runs `./mvnw verify` after edits with green-build evidence rule. Stop-on-first-BLOCKED in sweep mode. |
| `/hex-backend:audit-e2e` | **read-only 3-way diff** | `<METHOD /path>` or `--all`. Reports drift across Spec↔Code, Spec↔Tests, Code↔Tests for each endpoint. Single-line verdict per endpoint (`ALIGNED` / `MINOR-DRIFT` / `MAJOR-DRIFT`). Doesn't propagate anything; you pick which side to fix. |

## multi-team

The generic 9-agent topology.

| Command | Argument | What it does |
|---|---|---|
| `/multi-team:plan-build-validate` | `<task description>` | Generic plan → build → validate. `planning-lead` (`product-manager` + `ux-researcher`) → `engineering-lead` (`frontend-dev` + `backend-dev`) → `validation-lead` (`qa-engineer` + `security-reviewer`). No per-Task loop. |

## solo-pair

No commands. Describe the task in chat; orchestrator dispatches
`pair-dev` then `pair-reviewer`.

## discovery

| Command | Argument | What it does |
|---|---|---|
| `/discovery:capture` | `"<raw signal>"` | Creates a Jira card on the discovery board in the project's default status (Inbox). Lightweight — no framing, no research, just tracking. Discovery board is configured in `jira-flow.yaml`'s `discovery` lifecycle entry. |

Discovery cards advance column-by-column via `/jira-flow:advance` (no
`/discovery:plan-build-validate` — discovery is continuous, not phased).

## jira-flow

The Jira lifecycle layer. Pairs with any topology.

| Command | Argument | What it does |
|---|---|---|
| `/jira-flow:configure` | `[--migrate]` | Interactive setup of `jira-flow.yaml` at project root. Validates site against your accessible Atlassian sites (via `getAccessibleAtlassianResources` — no guessing), asks for project_key / board_id / status_map / issue_types / default_topology. Runs smoke test against live Jira at the end. `--migrate` moves legacy `.claude/jira-flow.lifecycle.yaml` to the new location. |
| `/jira-flow:capture` | `[Epic\|Bug\|Task]: <description>` | Lightweight register. Creates one Jira issue (default type: Story) and stops — no planning, no execution, no transitions. Reads `defaults.project_key` from `jira-flow.yaml`. Verifies the card actually exists via read-back before reporting success. |
| `/jira-flow:execute` | `<jira-key> [--force-feature-flow]` | Single existing card. Auto-detects issue type: **Bug** cards dispatch to `/jira-flow:fix` (reproduce-fix-verify); **Story / Task / Epic** cards run the canonical detail-audit + build + validate flow. `--force-feature-flow` overrides auto-dispatch on Bug. Transitions through `status_map.in_progress` → flow → `status_map.in_review` with Implementation Summary. |
| `/jira-flow:fix` | `<jira-key>` | Bug-flow wrapper around the topology's `reproduce-fix-verify` command (failing test first → fix → verify with BUILD SUCCESS evidence → APPROVE). Lighter than `/jira-flow:execute` — skips planning enrichment because the failing test IS the spec. Requires a topology with `reproduce-fix-verify` (currently `hex-backend` only). NOT-A-BUG is a valid outcome. |
| `/jira-flow:plan-track-build-validate` | `<abstract task description>` | Full plan + Jira lifecycle. Registers Epic + 1-3 candidate Stories; executes one Story end-to-end; transitions through `to_do` → `in_progress` → `in_review`. |
| `/jira-flow:drain` | `[column] [--max N]` | Bulk-execute cards from a column (default: `defaults.status_map.to_do`, fallback `"To Do"`). User confirmation required before starting. Stops on first BLOCKED card. `--max` defaults to 5. |
| `/jira-flow:advance` | `<jira-key>` | Generic column-by-column transition driven by `lifecycles[]` in `jira-flow.yaml`. Used by discovery (and any topology with a custom lifecycle). Runs the column's `on_enter` agent if declared, confirms `enter_gate` precondition with you if declared, transitions with Implementation Summary if `requires_summary: true` (or status name contains `review`/`qa`). |

## book

| Command | Argument | What it does |
|---|---|---|
| `/book:outline` | `<concept>` | Authors the book outline from your concept. |
| `/book:draft` | `<chapter spec>` | Drafts a chapter against an approved outline. |
| `/book:revise` | `<chapter>` | Revision pass on an existing chapter draft. |
| `/book:finalize` | (none) | Final continuity review + manuscript compile across all chapters. |
| `/book:status` | (none) | Reports progress against the outline (which chapters drafted, revised, finalized). |

See `book/commands/` for argument details and `book/agents/` for the
agent matrix.

## When to use which command

### "I want to implement a new feature"

- Known requirements, no Jira → `/hex-backend:plan-build-validate <description>` (or `/multi-team:plan-build-validate` for non-hex projects).
- Known requirements, Jira-tracked → `/jira-flow:plan-track-build-validate <description>` (creates Epic + Stories, runs one Story end-to-end).
- Existing Jira card with the description (Story/Task/Epic) → `/jira-flow:execute <KEY>` (auto-routes Bug cards to `/jira-flow:fix`).
- Existing Jira card known to be a Bug → `/jira-flow:fix <KEY>` (skip the auto-detect; go straight to reproduce-fix-verify).
- Unattended → `/common:autonomous-start "<KEY> <description>"` (auto-detects key, wraps with lifecycle).

### "I want to fix a bug"

- Local, no Jira → `/hex-backend:reproduce-fix-verify <description>` (or describe in chat for `solo-pair`).
- Jira-tracked → still `/hex-backend:reproduce-fix-verify` directly, or wrap with `/common:autonomous-start "<KEY> bug: <description>"`.

### "I'm not sure if X is a problem"

- `/hex-backend:investigate <hypothesis>`. Read-only. Outputs a findings report with a recommended next command.

### "I want to design a new endpoint's behavior"

- `/hex-backend:spec-e2e <METHOD /path> "<intent>"` — prescriptive, intent-driven. Spec describes what the endpoint *should* do.

### "I want to document an existing endpoint's behavior"

- `/hex-backend:document-e2e <METHOD /path>` — descriptive, code-driven. Spec captures what the endpoint *currently does*.

### "I edited the spec; tests need to follow"

- `/hex-backend:resync-e2e <METHOD /path>` (or `--all`). Spec → tests propagation.

### "Spec, code, and tests might disagree"

- `/hex-backend:audit-e2e <METHOD /path>` (or `--all`). 3-way diff, no propagation. You pick the fix direction.

### "I want to step away while it works"

- `/common:autonomous-start "<task or Jira key>"`. Comes back later, runs `/common:debrief` to review decisions.

### "I lost the thread of what's been done"

- `/common:recap`. Reads the session log + conversation context, renders "Asked / Status / Delivered" table.

### "I want to track work in Jira"

- First time: `/jira-flow:configure`. Walks you through the config.
- New work item, no detail yet: `/jira-flow:capture "<description>"`. Just registers, doesn't execute.
- Drain a column: `/jira-flow:drain` (default column = `to_do` from `status_map`).
- Custom lifecycle column transition: `/jira-flow:advance <KEY>`.
