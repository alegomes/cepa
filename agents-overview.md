# Agents — at a glance

A denormalized view of every agent across all topologies in this
marketplace. Source of truth for each agent's prose is its own file
under `<topology>/agents/`. Source of truth for write-glob enforcement
is each topology's own `hooks/path-lock.py` (build-team, build-hex,
discovery, design, and docs have one; build-solo doesn't, by design).

The marketplace ships **nine plugins**: `common` (skills + expertise),
six topologies (`build-team`, `build-solo`, `build-hex`, `discovery`,
`design`, `docs`), and two cross-cutting layers (`board-flow`,
`review-gate`) — every one of which is documented below.

---

## build-team

Three teams, each with one Opus lead and two Sonnet workers, plus the
orchestrator (the main session itself). Canonical workflow: plan → build → validate.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| (orchestrator — main session) | apex | user | three leads in parallel | Task | (none — orchestrator runs in the host CC session) |
| `planning-lead` | lead | orchestrator | `product-manager`, `ux-researcher` | Read, Glob, Grep, Task, Write | `specs/**`, own expertise |
| `engineering-lead` | lead | orchestrator | `frontend-dev`, `backend-dev` | Read, Glob, Grep, Task, Bash (RO) | own expertise only |
| `validation-lead` | lead | orchestrator | `qa-engineer`, `security-reviewer` | Read, Glob, Grep, Task, Bash (RO) | own expertise only |
| `product-manager` | worker | `planning-lead` | — | Read, Glob, Grep, Write | `specs/**`, own expertise |
| `ux-researcher` | worker | `planning-lead` | — | Read, Glob, Grep, Write | `specs/**`, own expertise |
| `frontend-dev` | worker | `engineering-lead` | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | `apps/*/web/**`, `apps/*/frontend/**`, own expertise |
| `backend-dev` | worker | `engineering-lead` | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | `apps/*/api/**`, `apps/*/backend/**`, `apps/*/migrations/**`, `apps/classifier/**`, own expertise |
| `qa-engineer` | worker | `validation-lead` | — | Read, Glob, Grep, Edit, Write, Bash | `tests/**`, `apps/*/tests/**`, `apps/*/__tests__/**`, own expertise |
| `security-reviewer` | worker | `validation-lead` | — | Read, Glob, Grep, Write | `specs/security-reviews/**`, own expertise |

**Models:** orchestrator + leads = `opus`; workers = `sonnet`. Splits
cost-and-quality the way indydev Dan's source intends (better reasoning
for delegation/synthesis at the top, faster instruction-following at the
bottom).

**Hook:** `build-team/hooks/path-lock.py` enforces the *Writes* column on every
`Edit` / `Write` / `MultiEdit` / `NotebookEdit` call. Identifies the calling
subagent via the `agent_type` field in CC's PreToolUse payload (sent as
`<plugin>:<agent>` — the hook strips the prefix). Verified empirically in
CC 2.1.x. Drift between this file and the hook will silently break things
at runtime.

---

## build-solo

Lightweight 2-agent topology for tasks where build-team's overhead isn't
worth it. Sequential dev → reviewer; no leads.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| (orchestrator — main session) | apex | user | dev → reviewer (sequential) | Task | (none) |
| `pair-dev` | worker | orchestrator | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | host project source (no path-lock) |
| `pair-reviewer` | worker | orchestrator | — | Read, Glob, Grep, Bash | — (read-only via tool allowlist) |

**Models:** workers = `sonnet`. No leads.

**Hook:** none. build-solo relies on `pair-reviewer`'s tool allowlist
(no Edit/Write) for read-only enforcement; `pair-dev` is unrestricted by
design — the topology is for small tasks where domain locks don't earn
their complexity.

---

## build-hex

14-agent hexagonal-architecture topology. Three teams, each with one
Opus lead and 2-4 Sonnet workers, plus the standalone `proof-reviewer`
gate. Per-Task quality loop runs inside engineering-lead (qa →
refactor-advisor → code-reviewer). Cross-cutting validation runs through
validation-lead. Canonical workflow:
plan → (per-Task: build → qa → housekeeping → review) → cross-cutting validate.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| (orchestrator — main session) | apex | user | three leads | Task | (none — runs in host CC session) |
| `planning-lead` | lead (DISCOVERY) | orchestrator | `epic-author`, `product-manager`, `integration-analyst` (parallel) | Read, Glob, Grep, Task, Write | `spec/**`, `specs/**`, `docs/**`, own expertise |
| `epic-author` | worker | `planning-lead` | — | Read, Glob, Grep, Write | `spec/**`, `specs/**`, `docs/**`, own expertise |
| `product-manager` | worker | `planning-lead` | — | Read, Glob, Grep, Write | `spec/**`, `specs/**`, `docs/**`, own expertise |
| `integration-analyst` | worker (also E2E spec author, Mode A descriptive + Mode B prescriptive) | `planning-lead`, `engineering-lead` (for E2E spec authoring) | — | Read, Glob, Grep, Write | `spec/**`, `specs/**`, `docs/**`, own expertise |
| `engineering-lead` | lead (ARCHITECT + EXECUTOR) | orchestrator | dev workers + per-Task quality loop (qa, refactor-advisor, code-reviewer); routes ARCHITECT to `integration-analyst` for E2E spec authoring on endpoint Tasks | Read, Glob, Grep, Task, Write, Bash (RO + branch reconciliation: `git checkout -b`, `git merge --no-ff`, `git branch -d`, `git worktree remove`) | `docs/tasks/**`, `docs/investigations/**`, `pom.xml`, `**/pom.xml`, own expertise |
| `domain-dev` | worker | `engineering-lead` | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | `domain/src/main/**`, `application/src/main/**`, own expertise |
| `api-dev` | worker | `engineering-lead` | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | `api-rest/src/main/**`, own expertise |
| `adapter-dev` | worker | `engineering-lead` | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | `infrastructure/src/main/**`, `bootstrap/src/main/**`, own expertise |
| `validation-lead` | lead (VALIDATION + GATE) | orchestrator | `security-reviewer`; runs `./mvnw verify` directly | Read, Glob, Grep, Task, Bash | own expertise only |
| `qa-engineer` | worker (Tester; reads `specs/e2e-assertions.md` as authoritative for E2E tests; requires literal BUILD SUCCESS evidence for PASS verdicts) | `engineering-lead` | — | Read, Glob, Grep, Edit, Write, Bash | `*/src/test/**`, own expertise |
| `refactor-advisor` | worker (Housekeeping, advisory) | `engineering-lead` | — | Read, Glob, Grep, Write | `docs/housekeeping/**`, own expertise (no source edits) |
| `security-reviewer` | worker | `validation-lead` | — | Read, Glob, Grep, Write | `docs/security-reviews/**`, own expertise |
| `code-reviewer` | worker (final GATE) | `engineering-lead` | — | Read, Glob, Grep | — (advisory verdict only; no writes) |
| `proof-reviewer` | worker (change-driven Review gate; called by `/board-flow:prove`) | `/board-flow:prove`, `/board-flow:prove-drain` | — | Read, Glob, Grep, Bash, Write | `docs/proof/<KEY>.yaml` only (versionado; never code; works in a throwaway git worktree) |

**Models:** orchestrator + 3 leads = `opus`; 10 workers = `sonnet`.

**Hook:** `build-hex/hooks/path-lock.py` enforces the *Writes* column
on every `Edit` / `Write` / `MultiEdit` / `NotebookEdit` call. Same
agent-detection mechanism as build-team (PreToolUse `agent_type` field,
plugin-namespaced; hook strips the prefix).

**Per-Task quality loop** (inside `engineering-lead`'s phase, mandatory):

```
dev worker → RESULT.md
  → qa-engineer (gap scan; CRITICAL/HIGH blocks; literal BUILD SUCCESS required for PASS)
  → (if gaps) back to dev worker, iterate
  → refactor-advisor (housekeeping report; advisory, never blocks)
  → code-reviewer (APPROVE / REJECT vs. TASK.md + ACL compliance; auto-REJECT on missing build evidence)
  → (if REJECT) back to dev worker, iterate
  → next Task
```

**Commands** (all in `build-hex/commands/`):

| Command | Purpose |
|---|---|
| `/build-hex:plan-build-validate <task>` | Canonical feature flow: plan → build (per-Task loop) → validate. |
| `/build-hex:reproduce-fix-verify <bug>` | Confirmed-bug flow: failing test → fix → verify. NOT-A-BUG is a valid outcome. |
| `/build-hex:investigate <hypothesis>` | Read-only analysis. Writes `docs/investigations/<slug>.md` with conclusion + recommended next command. |
| `/build-hex:spec-e2e <METHOD /path>` | **Prescriptive** E2E spec (intent → spec). Takes freeform intent and/or `--task <TASK.md>`. |
| `/build-hex:document-e2e <METHOD /path>` | **Descriptive** E2E spec (code → spec). Reads controller + use case + adapter + seed. |
| `/build-hex:resync-e2e <ep>` or `--all` | Propagates spec edits to E2E tests. Runs verify with green-build evidence. |
| `/build-hex:audit-e2e <ep>` or `--all` | Read-only 3-way diff: Spec↔Code, Spec↔Tests, Code↔Tests. |

---

## discovery

Continuous product-discovery topology. **Upstream of the build
topologies** — translates raw signals into validated opportunities, hands
off to engineering via a delivery brief.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| `discovery-lead` | lead (orchestrator) | main session | the 5 workers below | Read, Glob, Grep, Task | nothing except own expertise |
| `opportunity-framer` | worker (Framing) | discovery-lead | — | Read, Glob, Grep, Write | `docs/discovery/<key>/framing.md` |
| `user-researcher` | worker (Researching) | discovery-lead | — | Read, Glob, Grep, Write | `docs/discovery/<key>/research.md` |
| `assumption-tester` | worker (Researching → Validating) | discovery-lead | — | Read, Glob, Grep, Write | `docs/discovery/<key>/assumptions.md` |
| `evidence-auditor` | worker (Validating → Validated/Discarded) | discovery-lead | — | Read, Glob, Grep, Write | `docs/discovery/<key>/audit.md` |
| `epic-briefer` | worker (Validated → Handed off) | discovery-lead | atlassian-expert (only for engineer-board card creation) | Read, Glob, Grep, Write, Task | `docs/discovery/<key>/handoff.md` |

**Commands:**

| Command | Purpose |
|---|---|
| `/discovery:capture <signal>` | Lightweight: register a raw signal as an Opportunity card on the discovery board, lands in Inbox. No framing or research. |

The lifecycle (Inbox → Framing → Researching → Validating → Validated →
Handed off / Discarded) is driven by `/board-flow:advance <KEY>`, which
reads `board-flow.yaml`. There is no
`/discovery:plan-build-validate` — discovery is continuous, not bounded.

**Path-lock** is keyed to `docs/discovery/**`. Discovery agents cannot
write code, only research artifacts.

**Hard rule:** Validation evidence is the human's job. Real users, real
data, real prototypes. The `evidence-auditor` does not synthesize evidence
— it judges what the human collected against the test plan's pre-declared
success criteria. The verdict is grounded in the criteria, not in
post-hoc rationalization.

---

## design

Product-design topology. **Upstream of the build topologies** — turns a
feature brief into a build-ready design spec (UX + visual) so engineering
implements from a spec instead of inventing one. Produces artifacts, never
code.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| `design-lead` | lead (orchestrator) | main session | the 5 workers below | Read, Glob, Grep, Task | nothing except own expertise |
| `ux-architect` | worker (Explore — how it works) | design-lead | — | Read, Glob, Grep, Write | `docs/design/**` |
| `visual-designer` | worker (Explore — how it looks) | design-lead | — | Read, Glob, Grep, Write | `docs/design/**` |
| `design-system-keeper` | worker (Systematize) | design-lead | — | Read, Glob, Grep, Write | `docs/design/**` |
| `prototyper` | worker (Prototype) — sole holder of Gamma/Canva MCP | design-lead | — | Read, Glob, Grep, Write, Gamma/Canva MCP | `docs/design/**` |
| `design-critic` | worker (Critique) — quality gate, SHIP / REVISE / BLOCK | design-lead | — | Read, Glob, Grep, Write | `docs/design/reviews/**` |

**Commands:**

| Command | Purpose |
|---|---|
| `/design:explore-critique-spec <feature>` | Run the canonical design loop: explore (flows ∥ visual) → systematize against the design system → prototype → critique → assemble a build-ready design spec. |

The lifecycle (Brief → Explore → Systematize → Prototype → Critique ⇄
Explore → Spec'd → Handed off) can also be driven per-column via
`/board-flow:advance`. Sits between `discovery` (upstream brief) and
`build-team`/`build-hex` (downstream build).

**Path-lock** is keyed to `docs/design/**` (the design-critic to
`docs/design/reviews/**`). Design agents cannot write code, only design
artifacts. `prototyper` is the only agent in the marketplace holding the
Gamma/Canva MCP tools.

---

## docs

Documentation/onboarding topology. Sweeps an EXISTING project and produces
a grounded Diátaxis doc tree (tutorial / how-to / reference / explanation)
for handing it off to engineers who weren't there for the decisions.
Central discipline: separate the **HOW** (extractable from code) from the
**WHY** (elicitable — owner / commit / ADR / tracker) and NEVER invent
rationale — a missing source becomes an owner question, not a guess.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| `docs-lead` | lead (orchestrator) | main session | the 8 workers below | Read, Glob, Grep, Task, Write | `docs/_survey/gap-report.md`, `docs/_survey/STATUS.md` |
| `diataxis-inventory` | worker (Survey) | docs-lead | — | Read, Glob, Grep, Write | `docs/_survey/inventory.md` |
| `how-extractor` | worker (Survey — the HOW) | docs-lead | — | Read, Glob, Grep, Write | `docs/_survey/how-ledger.md` |
| `flow-tracer` | worker (Survey — end-to-end flows) | docs-lead | — | Read, Glob, Grep, Write | `docs/_survey/flows.md` |
| `rationale-archaeologist` | worker (Survey — the WHY) | docs-lead | — | Read, Glob, Grep, Write | `docs/_survey/why-ledger.md`, `open-questions.md` |
| `structure-surgeon` | worker (Declutter) | docs-lead | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | `docs/**`, `archive/**`, `README.md` |
| `doc-author` | worker (Author) | docs-lead | — | Read, Glob, Grep, Write | `docs/how-to/**`, `reference/**`, `explanation/**` |
| `tutorial-author` | worker (Author — Tutorial last) | docs-lead | — | Read, Glob, Grep, Write | `docs/tutorial/**` |
| `consistency-reviewer` | worker (Finalize) | docs-lead | — | Read, Glob, Grep, Write | `docs/_survey/consistency-review.md` |

**Commands** (five owner-checkpointed phases + status):

| Command | Purpose |
|---|---|
| `/docs:survey` | Phase 1 — read-only 4-front archaeology (inventory ∥ how ∥ flows ∥ why) → gap-report. |
| `/docs:declutter` | Phase 2 — archive process-exhaust, demote rival front-doors (moves files, rewrites no prose). |
| `/docs:checkpoint` | Phase 3 — owner answers the WHY-gaps; answers become sourced rationale. |
| `/docs:author` | Phase 4 — write the grounded tree (Tutorial last, from a real first run). |
| `/docs:finalize` | Phase 5 — whole-tree consistency review + owner sign-off. |
| `/docs:status` | Show which phases are done / in progress / pending (reads STATUS markers). |

**Path-lock** is keyed to `docs/**` + `docs/_survey/**`. The
`structure-surgeon`'s lock is deliberately broad (it moves files across the
tree) — owner-gated by `/docs:declutter`, not by the glob.

---

## board-flow

Cross-cutting layer. **Not a topology** — adds Jira lifecycle to
whichever topology is also installed.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| `atlassian-expert` | worker (cross-cutting) | orchestrator (called from any Jira-aware command) | — | Atlassian MCP tools (createJiraIssue, getJiraIssue, editJiraIssue, transitionJiraIssue, etc.) + Read, Glob, Grep | Jira state via MCP only; own expertise |

**Commands** (all in `board-flow/commands/`):

| Command | Purpose |
|---|---|
| `/board-flow:configure [--migrate]` | Interactive setup of `board-flow.yaml` at project root. Validates site against accessible Atlassian sites, asks for project_key / board_id / default_topology, runs a smoke test. Run once after install. |
| `/board-flow:capture <description>` | Register a freeform request as a Jira Story (or Epic/Bug/Task via prefix). No planning, no execution. |
| `/board-flow:plan-track-build-validate <abstract task>` | Full discovery + Jira lifecycle. Registers Epic + Stories, executes one Story, transitions through To Do → In Progress → In Review. |
| `/board-flow:execute <jira-key> [--force-feature-flow]` | Single existing card. Auto-detects issue type: Bug → dispatches to `/board-flow:fix`; Story/Task/Epic → runs detail audit + build + validate. `--force-feature-flow` overrides Bug auto-dispatch. |
| `/board-flow:fix <jira-key>` | Bug-flow wrapper around the topology's `reproduce-fix-verify`: failing test first → fix → verify with green build evidence. Skips planning enrichment (failing test IS the spec). NOT-A-BUG is a valid outcome. Requires a topology with `reproduce-fix-verify` (build-hex). |
| `/board-flow:drain <column> [--max N]` | Bulk-execute up to N cards (default 5) from a column. Stops on first BLOCKED. User confirmation required. |
| `/board-flow:prove <jira-key>` | Change-driven proof gate for a card in `status_map.in_review`. Delegates to `<topology>:proof-reviewer` (build-hex ships it); verdict drives the transition — PROVEN → `status_map.done`, UNPROVEN → `in_progress` with the gap, NEEDS-HUMAN stays in Review. See [docs/proof-gate.md](docs/proof-gate.md). |
| `/board-flow:prove-drain [--max N]` | Bulk-prove the Review column. Runs `/board-flow:prove` per card. Unlike `/drain`, does NOT stop on a failed card — UNPROVEN bounces back and the drain continues. User confirmation required. |
| `/board-flow:advance <jira-key>` | Generic column-by-column transition driven by `board-flow.yaml`. Used by discovery (and any topology with a custom lifecycle). For default To Do → In Progress → In Review, prefer `/execute`. |

**Soft requirement:** board-flow's commands delegate to subagents named
`planning-lead`, `engineering-lead`, `validation-lead`. Both `build-team`
and `build-hex` ship those names; `build-solo` doesn't, so board-flow
doesn't work with build-solo-only. CC has no enforced plugin
dependencies — the soft requirement is documented in the plugin
descriptions and surfaces at first delegation if missing.

---

## review-gate

Cross-cutting layer. **Not a topology** — adds a pre-merge gate so code
reaches the default branch only through a reviewed, proven pull request,
never a direct push.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| `bitbucket-expert` | worker (cross-cutting) — the only agent allowed to touch the Bitbucket REST API | orchestrator (called from review-gate commands at the PR boundary) | — | Bash (bundled `bin/open-pr.sh` + `bin/merge-pr.sh`), Read, Glob, Grep | Bitbucket PR state via the bundled scripts; own expertise |

**Commands:**

| Command | Purpose |
|---|---|
| `/review-gate:open` | Open door — hygiene gate via `/code-review`, then opens a PR through `bitbucket-expert`. |
| `/review-gate:merge` | Merge door — QA gate via the topology's `proof-reviewer`; merges (optionally auto) on a PROVEN verdict. |
| `/review-gate:review` | Run the review pass on the current diff / PR. |
| `/review-gate:configure` | Set up the gate (Bitbucket workspace/repo, default branch, auto_merge). |

**Hooks:** `no-direct-main.py` (fence — blocks direct push/merge to the
default branch and redirects to the flow) and `push-nudge.py` (suggests a
PR after a feature-branch push). Optional `board-flow` seam maps
open → In Review, merge → Done.

---

## common (cross-topology layer)

The `common@cepa` plugin ships the shared mindset skills, the
autonomous-operation lifecycle, the session log, and the green-or-revert
build-state machine. `common` is a horizontal layer that every topology
rides on top of — and that is exactly why it DOES ship agents when the
concern is cross-topology: **`completion-auditor`** (independent last-mile
acceptance gate, used by every board-flow lifecycle) and
**`ui-proof-reviewer`** (independent proof gate for the UI/extension
surface, driven by the host repo's `.claude/ui-proof.yaml` — any topology
can have a SPA/extension in front of what it builds, so pinning it to one
topology would hide it from the rest). Agents whose knowledge is
topology-specific still live in their topologies.

**Commands** (all in `common/commands/`):

| Command | Purpose |
|---|---|
| `/common:autonomous-start [--topology=X] [--flow=NAME] [--no-jira] <description>` | Kick off an unattended run. Auto-detects Jira key in args; if found AND `board-flow.yaml` exists, wraps with In Progress → flow → In Review (Implementation Summary). Activates `autonomous-mode` skill. |
| `/common:autonomous-resume [run-id]` | Pick up after compaction / session crash from `docs/autonomous/<run-id>/state.yaml`. Defaults to most recent in-progress. |
| `/common:debrief [run-id]` | Walk every `### Decision:` block from the run with the user. Verdicts (`keep` / `overrule` / `refine` / `skip`) land in `<agent>-mental-model.yaml` under `feedback`. Dual-scan detects format drift. |
| `/common:recap [--since=YYYY-MM-DD]` | Render "Asked / Status / Delivered" table for the session. Reads `.claude/session-log.md` (intent) and the conversation (delivery). Read-only. |

**Hooks** (all in `common/hooks/`):

| Hook | Event | Purpose |
|---|---|---|
| `session-log.py` | UserPromptSubmit | Appends every user prompt to `.claude/session-log.md` with date/time headers. Survives auto-compaction. |
| `autonomous-checkpoint.py` | PostToolUse on `Task` | Appends to `docs/autonomous/<run-id>/state.yaml` after every subagent call when `CLAUDE_AUTONOMOUS_RUN_ID` is set. Out-of-band — orchestrator cannot forget. |
| `mark-build-stale.py` | PostToolUse on `Edit\|Write\|MultiEdit` | Marks `.claude/last-build.json` as STALE when source / build manifest / migration is edited. |
| `capture-build-result.py` | PostToolUse on `Bash` | Detects Maven/Gradle/npm/yarn/pytest/cargo/go-test invocations; writes SUCCESS or FAILURE with command + tail. |
| `gate-advance.py` | PreToolUse on `Bash` | Hard gate: refuses `git commit` / `git push` / `gh pr create` / `kubectl apply` / `terraform apply` / `docker push` / `aws\|gcloud\|az deploy` when build state is STALE or FAILURE. |

---

## Workflow walkthroughs

Turn-by-turn narratives showing what actually happens when you run the
canonical command for each topology. Useful for predicting cost, spotting
where a run went off-rails, and onboarding new users.

### build-team — `/build-team:plan-build-validate "add a --json flag to predict"`

1. **Orchestrator** (main session) reads the command, decomposes into
   plan / build / validate phases, calls `planning-lead` via Task.
2. **planning-lead** (Opus) delegates in parallel:
   - `product-manager` writes `specs/predict-json-flag.md` (user value, acceptance criteria).
   - `ux-researcher` writes `specs/predict-json-flag-ux.md` (CLI ergonomics).
   Synthesizes both into a brief, returns to orchestrator.
3. **Orchestrator** calls `engineering-lead` with the brief.
4. **engineering-lead** (Opus) delegates in parallel:
   - `backend-dev` edits `apps/predict/api/**` — adds the flag, JSON serializer.
   - `frontend-dev` is a no-op for this task; lead skips delegation.
   path-lock blocks any cross-domain write attempt with exit 2.
5. **engineering-lead** synthesizes (possibly: "backend done, no frontend changes needed"), returns to orchestrator.
6. **Orchestrator** calls `validation-lead`.
7. **validation-lead** delegates:
   - `qa-engineer` writes/extends tests in `tests/**`.
   - `security-reviewer` writes a review note in `specs/security-reviews/**` (e.g., "JSON output doesn't leak secrets").
8. **Orchestrator** synthesizes a final report for the user.

**Visible cost:** ~9 subagent invocations. **Visible artifacts:** spec
files, source edits, test files, security note.

### build-solo — "fix the off-by-one in `pagination.ts:42`"

1. **Orchestrator** sees a small, scoped task → calls `pair-dev` directly.
2. **pair-dev** edits `pagination.ts`, runs the existing test, reports.
3. **Orchestrator** calls `pair-reviewer`.
4. **pair-reviewer** reads the diff (Read/Grep, no Edit), reports
   approve/concerns.
5. **Orchestrator** reports to user.

**Visible cost:** 2 subagent invocations. **No path-lock**, no specs,
no validation phase. If a request grows mid-flight (e.g., "and refactor
the surrounding pagination logic"), the topology shape is wrong —
switch to build-team for that work.

### build-hex — `/build-hex:plan-build-validate "expose subscription status via REST"`

1. **Orchestrator** calls `planning-lead`.
2. **planning-lead** (Opus) delegates in parallel:
   - `epic-author` decomposes abstract → Epic + 3 Stories in `spec/epics/**`.
   - `product-manager` adds acceptance criteria.
   - `integration-analyst` writes the OpenAPI contract sketch in `spec/contracts/**`.
3. **Orchestrator** calls `engineering-lead` with the Stories.
4. **engineering-lead** writes `docs/tasks/TASK-001.md` … `TASK-003.md`
   (one per Story, broken to atomic units), then **for each Task**:
   - Delegates to the right dev (`domain-dev` for `domain/`+`application/`,
     `api-dev` for `api-rest/`, `adapter-dev` for `infrastructure/`+`bootstrap/`).
   - Dev writes `RESULT.md` summarizing what changed.
   - **`qa-engineer`** scans for gaps. CRITICAL/HIGH → loops back to dev.
   - **`refactor-advisor`** writes `docs/housekeeping/<task>.md`. Advisory; never blocks.
   - **`code-reviewer`** verdicts APPROVE / REJECT vs. TASK.md + ACL.
     REJECT → loops back to dev. APPROVE → next Task.
5. **engineering-lead** returns "all Tasks APPROVE" to orchestrator.
6. **Orchestrator** calls `validation-lead`.
7. **validation-lead** runs `./mvnw verify` directly (it has Bash) and
   delegates to `security-reviewer`.
8. **Orchestrator** reports.

**Visible cost:** 14 agents available (13 in the build flow + the
standalone `proof-reviewer` gate, which runs separately via
`/board-flow:prove`); per run ≈ planning-lead (3 workers) +
engineering-lead (N Tasks × 4 agents in the loop) + validation-lead
(1 worker + Bash). Scales with Task count.

**Visible artifacts:** Epic + Stories under `spec/`, TASK-NNN.md files,
RESULT.md per Task, housekeeping reports, security review, Maven
build output, source across all 5 modules.

### board-flow — `/board-flow:execute WEGO-1234`

(Assumes build-hex or build-team also installed.)

1. **Orchestrator** parses the Jira key, calls `atlassian-expert`.
2. **atlassian-expert** calls `getJiraIssue WEGO-1234`, returns the card body.
3. **Orchestrator** runs a **detail audit** on the card. If under-specified:
   - Calls `planning-lead` (from build-hex or build-team) to enrich.
   - Calls `atlassian-expert` again to `editJiraIssue` with the enriched description.
4. **Orchestrator** calls `atlassian-expert` to `transitionJiraIssue` → `In Progress`.
5. **Orchestrator** runs the topology's build phase (engineering-lead → workers → quality loop).
6. **Orchestrator** runs the validation phase.
7. **Orchestrator** calls `atlassian-expert` to:
   - `addCommentToJiraIssue` with the verdict + artifact links.
   - `transitionJiraIssue` → `In Review` (if PASS) or back to `To Do` with BLOCKED reason.
8. Reports to user.

**Visible cost:** topology cost + ~3-5 Atlassian MCP calls. Drain
multiplies by N cards; stops at first BLOCKED to cap cost.

### discovery — life of an Opportunity card (continuous)

Discovery is **continuous, not bounded** — there's no single command that
runs the whole flow. Each `/board-flow:advance <KEY>` invocation moves the
card forward one column. A card may take days or weeks across many
sessions; the timeline is shaped by how fast the human collects evidence.

The narrative below assumes discovery + board-flow are installed and
`board-flow.yaml` declares the WEGO discovery lifecycle.

1. **Capture.** User runs `/discovery:capture "Patients struggle to figure out which contract to sign first"`.
   - Orchestrator calls `atlassian-expert` to create a Story on the WEGO discovery board (status `To Do` = Inbox column).
   - Card lands. No agent runs. ~1 Atlassian MCP call.

2. **Inbox → Framing.** User runs `/board-flow:advance WEGO-2001`.
   - Orchestrator reads `board-flow.yaml`, matches the discovery lifecycle, identifies next column = Framing.
   - `atlassian-expert` transitions card to `Framing`.
   - `discovery-lead` is invoked, routes to `opportunity-framer`.
   - `opportunity-framer` writes `docs/discovery/WEGO-2001/framing.md` (problem statement, target user, outcome, IN/OUT scope, open questions).
   - Discovery-lead reports artifact path. Orchestrator updates the card with a comment linking to the brief.

3. **Framing → Researching.** User runs `/board-flow:advance WEGO-2001`.
   - Same routing pattern. `user-researcher` reads `framing.md`, inventories `evidence/` (probably empty on first pass), writes `docs/discovery/WEGO-2001/research.md`. On a first pass with no evidence yet, the report is mostly "gaps in evidence" — pointers for the human to go talk to users or pull data.

4. **Human collects evidence.** User runs interviews, drops transcripts in `docs/discovery/WEGO-2001/evidence/`. No agent run. Days may pass.

5. **Re-run user-researcher (loop).** User runs `/board-flow:advance WEGO-2001` while still in Researching, asking to re-synthesize with new evidence. Discovery-lead routes back to `user-researcher` (the column itself doesn't transition). Updated `research.md` shows patterns now that there's evidence.

6. **Researching → Validating (gated).** User runs `/board-flow:advance WEGO-2001`.
   - Orchestrator sees that the next column (Validating) has an `enter_gate`: "card has assumption-tester test plan". The plan doesn't exist yet → orchestrator invokes `assumption-tester` first.
   - `assumption-tester` writes `docs/discovery/WEGO-2001/assumptions.md` (ranked assumptions + per-assumption test plan + pre-declared success criteria).
   - Orchestrator confirms the gate is satisfied (test plan now exists), prompts user, then transitions to Validating.

7. **Human runs experiments.** Prototypes, more interviews, fake-door tests. Drops new evidence in `evidence/`. Days–weeks may pass.

8. **Validating → Validated (gated).** User runs `/board-flow:advance WEGO-2001`.
   - Next column (Validated) has an `enter_gate`: "evidence-auditor verdict = Validate". The audit doesn't exist yet → orchestrator invokes `evidence-auditor` first.
   - `evidence-auditor` reads `assumptions.md` (the rubric) + `evidence/` (the data), returns verdicts per assumption (Confirmed / Invalidated / Inconclusive), writes `docs/discovery/WEGO-2001/audit.md`. Recommended next move: Validate, Loop back, or Discard.
   - If Validate → orchestrator confirms gate, transitions to Validated.
   - If Loop back → orchestrator does NOT transition; reports back what to test next. The card stays in Validating; the human runs more tests.
   - If Discard → user runs `/board-flow:advance` to move to Discarded (terminal).

9. **Validated → Handed off.** User runs `/board-flow:advance WEGO-2001`.
   - Discovery-lead routes to `epic-briefer`.
   - `epic-briefer` reads framing + research + assumptions + audit; writes `docs/discovery/WEGO-2001/handoff.md` (delivery brief: validated assumptions, invalidated paths excluded, boundaries, suggested starter Stories).
   - `epic-briefer` calls `atlassian-expert` to create a linked Epic on the engineer board with the brief path embedded and a "relates to" link back to the discovery card.
   - Orchestrator reports the engineer-board Epic key + brief path.

10. **Handoff to build topology (out of discovery's scope).** Engineering's `planning-lead` (e.g., from build-hex) picks up the linked Epic, reads `handoff.md`, runs `epic-author` to author the Epic's full description and Stories on the engineer board. From here it's the build topology's normal flow (`/board-flow:execute <Epic-key>` → Stories → code → ship).

**Visible cost:** small per `/advance` invocation (1-2 agents + 1-2 Atlassian
MCP calls). Total cost across a card's life depends on how many loops the
Validating column takes — each test cycle is one human round-trip plus one
auditor pass. The discipline gate (`enter_gate` on Validated) is the
mechanism that prevents the card from advancing on optimism.

---

## Skills (loaded by description-match in CC)

| Skill | One-liner | Audience |
|---|---|---|
| `mental-model` | Read your expertise file at task start; update at task end. | every agent |
| `active-listener` | Read context (delegation prompt, prior worker output, conversation log) before responding. | every agent |
| `zero-micromanagement` | You delegate, you don't execute. The urge to fix it yourself is the signal to delegate. | leads + orchestrator only |
| `conversational-response` | Lead with the answer, bullets for parallels, file:line refs, single next-step close. | every agent that reports verbally |
| `till-done` | Don't stop until the job is fully complete. "Almost done" is the signal to keep going. | every agent |
| `scope-discipline` | Don't expand the work beyond what was asked. While-I-was-in-there findings are follow-ups, not silent inclusions. | every agent |
| `evidence-over-assumption` | Distinguish what you verified from what you assumed when reporting. "I checked X by running Y" vs. "I'm assuming X because Z." | every agent |
| `name-the-disagreement` | When synthesizing reports from multiple sub-agents that disagree, surface the disagreement explicitly — don't average or pick silently. | leads + orchestrator (synthesizers) |
| `autonomous-mode` | Activated by `/common:autonomous-start`. No questions to the user; every ambiguity logged in formal `### Decision:` block (Options / Chosen / Rationale). | orchestrator (session-wide) |
| `green-or-revert` | Never claim runtime state without consulting `.claude/last-build.json`. After meaningful edits, verify is the next action — don't wait to be asked. On FAILURE, fix or revert before any other action. | orchestrator + leads + dev workers |

The ten skills ship in the **`common@cepa` plugin**
(`common/skills/`). Every topology requires `common`; install it once
per project and the skills are available to every subagent via CC's
session-wide skill namespace.

---

## indydev Dan idea audit (against the canonical list)

Status legend: ✅ captured · 🟡 partial / convention only · 🔴 CC limitation

### Mindset and architecture

| Idea | Status | Where / how |
|---|---|---|
| Team of agents | ✅ | 9-agent build-team + 2-agent build-solo |
| 3 tiers (orchestrator / leaders / workers) | ✅ | topology snippets, agent files |
| Thinkers (orchestrator, leads) vs doers (workers) | ✅ | leads have no `Edit`/`Write` tools; workers do |
| Thinkers don't write code; they understand, refine, organize, delegate, aggregate | ✅ | `zero-micromanagement` skill + lead front-matter tool list |
| Specific model per agent | ✅ | front-matter `model:` (`opus` for thinkers, `sonnet` for doers) |
| Only worker agents write code | ✅ | path-lock hook + leads' tool allowlists exclude `Edit`/`Write`/`MultiEdit` |
| Highly specialized agents | ✅ | 9 distinct roles, each with a tight write-glob domain |
| Orchestrator must do prompt engineering | ✅ | "You are the team's prompt engineer" section in both topology snippets |
| Till-done — work until job is fully complete | ✅ | `common/skills/till-done/SKILL.md` + topology rule + command instruction |
| Building a system that will build systems | ✅ | framing in README + "Frame" section in both topology snippets |
| Agents must learn and improve themselves | ✅ | `mental-model` skill + per-agent `expertise/<name>-mental-model.yaml` |
| Mental model evolves over time | ✅ | `mental-model` skill describes read-at-start / update-at-end |

### Topology config (Pi has machine-readable YAML; we have CC-shaped conventions)

| Idea | Status | Where / how |
|---|---|---|
| Topology / build-team-config concept | 🟡 | We have `*-topology.md` snippets (CC orchestrator instructions). Pi has a YAML config the harness reads; CC has no equivalent. The snippet *is* the topology in CC. |
| Orchestrator name + path + color | 🟡 | Orchestrator = main CC session (no separate file/path). Color N/A for main session. |
| Agent paths | ✅ | `agents/` (build-team) and `build-solo/agents/` |
| Session paths | 🔴 | CC manages session storage internally; not exposed |
| Shared context (files all agents should know) | ✅ | "Shared context" section in both topology snippets |
| Teams[] declaration | 🟡 | Implicit in agent set + this matrix |

### Per-team

| Idea | Status | Where / how |
|---|---|---|
| `consult-when` (when to activate the team) | 🟡 | In each lead's front-matter `description:` |
| Lead: name + file + color | ✅ | front-matter `name:`, file path is the agent file, `color:` set on every agent |
| Members list | ✅ | encoded in topology snippet + each lead's `Delegates to` table row |

### Per-agent header (Pi YAML blocks vs CC front matter + tabular header)

| Idea | Status | Where / how |
|---|---|---|
| Agent name | ✅ | front-matter `name:` |
| Color | ✅ | front-matter `color:` set on all 11 agents |
| When to use | ✅ | front-matter `description:` |
| Which model | ✅ | front-matter `model:` |
| Expertise (path / use-when / updatable / max-lines) | 🟡 | Centralized expertise stubs ship in `common/expertise/<agent>-mental-model.yaml`. Agents reference them as `.claude/expertise/<agent>-mental-model.yaml` (host-relative — what CC subagents can resolve); `bin/install.sh` creates that path as a symlink to the plugin's central directory, so writes from any host project land in one shared location and follow the agent across projects. The path-lock hook allows each agent to write its own expertise file via a structural filename check. Pi's full schema (`use-when`, `updatable`, `max-lines`) isn't mirrored — CC has no harness layer to act on those fields. |
| Skills list with `use-when` per skill | 🟡 | tabular header lists skills by name; CC auto-loads them by description match (no per-agent `use-when` field) |
| Tools list | ✅ | front-matter `tools:` |
| Domain (path × read/upsert/delete) | 🟡 | path-lock hook enforces *writes* (Edit/Write/MultiEdit) per glob; doesn't distinguish create vs upsert vs delete |

### Per-agent body

| Idea | Status | Where / how |
|---|---|---|
| Purpose section | ✅ | `## Purpose` paragraph in every agent body, after the tabular header |
| Variables (env vars injected at startup) | 🔴 | CC only injects `${CLAUDE_PLUGIN_ROOT}` for hooks — no per-subagent env-var injection. `{{SESSION_DIR}}` and `{{CONVERSATION_LOG}}` from Pi don't translate. |
| Instructions section | ✅ | Body of each agent (currently labeled `## Rules` / `## Approach` / `## Workflow`) |

### Commands (slash commands ≈ Pi pre-saved prompts)

| Idea | Status | Where / how |
|---|---|---|
| Description + argument-hint | ✅ | front-matter |
| Purpose | ✅ | `## Purpose` section in `/plan-build-validate` |
| Variables | ✅ | `## Variables` section in `/plan-build-validate` (`$ARGUMENTS`) |
| Instructions | ✅ | `## Instructions` section in `/plan-build-validate` |
| Workflow (the most important part — talk-to-orchestrator) | ✅ | `## Workflow` heading in `/plan-build-validate` |
| Report (back to the user) | ✅ | `## Report` section in `/plan-build-validate` |

### Sharing across topologies

| Idea | Status | Where / how |
|---|---|---|
| Shared mindset skills available across topologies | ✅ | `common@cepa` plugin ships the five skills; required by both `build-team` and `build-solo` |

---

## Verified end-to-end (live in CC 2.1.126)

- **Plugin install** via `bin/install.sh` (with `--clean` for stale-cache
  recovery) against a local-path marketplace.
- **Skill auto-loading** — the five `common:*` mindset skills and the
  `build-team:plan-build-validate` slash command are discoverable in CC.
- **Subagent identity** in PreToolUse hook — CC sends `agent_type` as
  `<plugin>:<agent-name>` (e.g. `build-team:backend-dev`); the hook
  strips the prefix to match `ALLOWED_WRITES`.
- **Centralized expertise via host symlink** — `backend-dev` (subagent)
  read AND wrote `.claude/expertise/backend-dev-mental-model.yaml`; the
  symlink redirected the write to the central plugin source
  (`common/expertise/backend-dev-mental-model.yaml`), persisting across
  every project the symlink covers.
- **Per-agent path-lock enforcement** — the structural
  `is_own_expertise_file` check approved backend-dev's write to its own
  expertise file; the broader allowlist check would block writes
  outside its `apps/*/api/**` etc. domain.

## Outstanding work

- 🟡 **Real-task validation of `build-team`** — basic delegation flow
  was observed working (orchestrator → leads → workers → honest BLOCKED
  reply when target code wasn't present). Not yet exercised against a
  real codebase end-to-end.
- 🟡 **Real-task validation of `build-hex`** — the 14-agent topology
  was just built. The per-Task quality loop, refactor-advisor's
  housekeeping report shape, and code-reviewer's APPROVE/REJECT have
  not been observed live yet.
- 🟡 **Real-task validation of `board-flow`** — atlassian-expert and the
  three Jira-aware commands have not been run against a real Jira
  project. Atlassian MCP tools are available; the agent prompt is
  written but unverified.
- 🟡 **`proof-reviewer` / proof-gate unverified against a real pom** —
  the L2/L3/L4 mechanics assume specific JaCoCo (IT-isolated), PIT, and
  failsafe wiring that hasn't been run against a real `pom.xml` yet.
  Also: cards already in Review predate the `base_commit` capture, so
  they lack a `.claude/cards/<KEY>.yaml` baseline and will diff-scope
  from the touched-files list alone (weaker L3) — expect more
  NEEDS-HUMAN on the existing backlog than on cards run through the flow
  after the capture landed. Fire test before trusting `prove-drain`.
- 🟡 If you want to capture the team-topology config more strictly,
  add a non-driving `topology.yaml` per topology as documentation
  (CC won't read it; risk of drift). Recommend: skip until needed.
- 🟡 Consider extending the path-lock hooks to support
  read/upsert/delete granularity. Modest scope; only worth it if a real
  workflow demands the distinction.
- 🟡 Versioned changelog (separate `CHANGELOG.md`) — currently the git
  log fills this role. Worth adding before any public release.
- 🔴 Session env vars (`{{SESSION_DIR}}`, `{{CONVERSATION_LOG}}`) — not
  implementable in CC without harness changes.
