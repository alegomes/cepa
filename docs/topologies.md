# Choosing a topology

The marketplace ships six topology plugins, plus `common` (required)
and `board-flow` (optional Jira layer). Pick **one topology per project**
— importing two snippets gives the orchestrator conflicting instructions.

| Topology | Agents | Best for | Path-lock | Commands |
|---|---|---|---|---|
| **build-hex** | 14 | Java/Quarkus hexagonal backends. Per-Task quality loop. | `domain/`, `application/`, `api-rest/`, `infrastructure/`, `bootstrap/` Maven layout | `plan-build-validate`, `reproduce-fix-verify`, `investigate`, `spec-e2e`, `document-e2e`, `resync-e2e`, `audit-e2e` (+ `proof-reviewer` agent for `/board-flow:prove`) |
| **build-team** | 9 | Greenfield apps with frontend + backend. Generic plan→build→validate. | `apps/*/api/**`, `apps/*/web/**`, `tests/**` | `plan-build-validate` |
| **build-solo** | 2 | One-file tweaks, bug fixes, small refactors. No leads, no per-Task loop. | tool-allowlist only (`pair-reviewer` is read-only via tools) | none — describe in chat |
| **discovery** | 6 | Continuous product discovery: signals → opportunities → validated bets → engineering brief. Sits *upstream* of build topologies. | `docs/discovery/**` | `capture` (plus generic `/board-flow:advance` for column transitions) |
| **design** | 6 | Product design: a feature brief → a build-ready design spec, before engineering builds. Upstream of the build teams. | `docs/design/**` | `explore-critique-spec` (+ per-column lifecycle via `/board-flow:advance`) |
| **docs** | 9 | Sweep an existing project into a grounded Diátaxis doc tree for onboarding. | `docs/**`, `docs/_survey/**` | `survey`, `declutter`, `checkpoint`, `author`, `finalize` |

## How to choose

Two questions to answer in order:

### 1. Is it a Java/Quarkus hexagonal backend, or some other layout?

- **Hexagonal Java/Quarkus** with the `domain/application/api-rest/
  infrastructure/bootstrap` module layout → `build-hex`. The
  per-Task quality loop and worker domain-locks are tuned for this
  layout specifically.
- **Anything else** (Node app, Python service, fullstack with
  frontend, etc.) → continue.

### 2. How much overhead can I tolerate?

- **Small task, obvious scope** (one-file fix, rename, small refactor)
  → `build-solo`. 2 agents, no fan-out, no per-Task ceremony. Fast.
- **Bigger task that benefits from product/UX framing before code** →
  `build-team`. 3 leads + 6 workers, generic enough for most stacks.
  Less specialized than `build-hex` but covers more ground.

### Aside: Product discovery

If your project does product/research work *upstream* of engineering —
opportunity framing, user research, assumption testing, evidence-based
validation — `discovery` covers that. It's not an alternative to the
build topologies; it's complementary. Common setup:

- `discovery` + `build-hex` + `board-flow`: continuous discovery on one
  Jira board, validated opportunities hand off via `epic-briefer` to
  engineering's `epic-author` on the build board.

## Composition rules

- **One topology per project.** The topology snippet in
  `CLAUDE.md` (`@.claude/<topology>-topology.md`) tells the orchestrator
  how to behave. Two snippets = contradictory instructions.
- **`common` is required by every topology.** The 8 mindset skills are
  referenced in agent bodies; without `common` the references go
  nowhere.
- **`board-flow` requires a 3-lead topology** for its lead-based commands
  (`/board-flow:execute`, `/board-flow:plan-track-build-validate`).
  `build-hex` and `build-team` ship those leads; `build-solo` doesn't.
  Trying board-flow lead-based commands on a `build-solo`-only project
  fails at the first delegation. `/board-flow:advance` is generic and
  works with any topology that ships a lifecycle file.
- **`discovery` is upstream, not competing.** Run discovery and a build
  topology in the same project — they coordinate via the engineer-board
  Epic, not the same `CLAUDE.md` snippet.

## Switching topologies

Change `CLAUDE.md`'s `@-import` line and also update `.claude/topology`:

```sh
# from project root
echo "build-team" > .claude/topology

# in CLAUDE.md, change the import line:
# @.claude/build-hex-topology.md   →  @.claude/build-team-topology.md
```

Then `bin/install.sh --topology=build-team` to copy the new snippet over.
The plugins themselves don't need reinstalling — they're all already
present.

## Per-topology details

### build-hex (the deepest specialization)

**About the name.** "Hexagonal" here refers to the architectural style
(Cockburn's Ports & Adapters): framework-free domain, dependencies
pointing inward, Anti-Corruption Layer at adapters. The topology is
opinionated about those invariants but NOT about physical module
names. The default layout uses
`domain/application/api-rest/infrastructure/bootstrap`, but if your
project names its modules `tenancy-core/tenancy-api/tenancy-adapter/
tenancy-app` (or any other convention), edit `build-hex.yaml` at
project root to remap each architectural role to your module:

```yaml
schema_version: 1
roles:
  domain:       tenancy-core
  application:  tenancy-core
  api:          tenancy-api
  adapter:      tenancy-adapter
  bootstrap:    tenancy-app
```

`bin/install.sh --topology=build-hex` seeds this file with canonical
defaults. Roles may share a module (common when domain and application
code live together). The same file also supports an optional
`extra_write_globs:` block for project-specific paths an agent
legitimately needs outside the role-based allowlist (e.g., one-off
migration scripts). See `docs/internals/path-lock.md` for the full
schema and behavior.

Three teams:

- **Planning team** (4 agents): `planning-lead` + `epic-author` +
  `product-manager` + `integration-analyst`.
- **Engineering team** (4): `engineering-lead` + `domain-dev` +
  `api-dev` + `adapter-dev`. Workers domain-locked by hex layer.
- **Validation team** (5): `validation-lead` + `qa-engineer` +
  `refactor-advisor` + `security-reviewer` + `code-reviewer`.

Per-Task quality loop (mandatory inside `plan-build-validate`):

```
dev worker → qa-engineer → refactor-advisor → code-reviewer
                  ↓ FAIL                          ↓ REJECT
              back to dev                    back to dev
```

`qa-engineer` requires literal `BUILD SUCCESS` output in its reply for
PASS verdicts. `code-reviewer` auto-REJECTs missing build evidence.
`engineering-lead` rejects unsubstantiated PASS. Three layers of
defense; see `build-hex/agents/qa-engineer.md` for the spec.

### build-team (the generic shape)

3 leads + 6 workers:

- **Leads**: `planning-lead`, `engineering-lead`, `validation-lead`.
- **Workers**: `product-manager`, `ux-researcher`, `frontend-dev`,
  `backend-dev`, `qa-engineer`, `security-reviewer`.

No per-Task quality loop (lighter than `build-hex`). Use when you
want plan → build → validate ordering but don't need the hexagonal
specifics.

### build-solo (the small-task option)

2 agents, no leads, no path-lock hook:

- `pair-dev` — writes code. Domain not locked.
- `pair-reviewer` — read-only via tool allowlist. Reviews `pair-dev`'s
  output.

Driven by conversational prompt to the orchestrator, no dedicated
command. Use for one-file changes, bug fixes, small refactors where
fan-out overhead would dwarf the task.

### discovery (continuous product discovery)

6 agents arranged around a 7-column lifecycle (Inbox → Framing →
Researching → Validating → Validated → Handed off / Discarded). Each
column has an `on_enter` agent and optional `enter_gate` precondition,
declared in `board-flow.yaml`'s `lifecycles[]` block.

Use `/discovery:capture "<raw signal>"` to land a card in Inbox, then
`/board-flow:advance <KEY>` to walk it column by column.
