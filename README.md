# claude-multi-team-plugin

A Claude Code plugin marketplace shipping a multi-agent setup as **seven**
composable plugins.

## Documentation

| Document | Read it for |
|---|---|
| **[docs/getting-started.md](docs/getting-started.md)** | First 10 minutes: install, pick a topology, run your first command. |
| **[docs/topologies.md](docs/topologies.md)** | Choosing between `hex-backend`, `multi-team`, `solo-pair`, `discovery`, `book`. Composition rules with `jira-flow`. |
| **[docs/commands.md](docs/commands.md)** | Full reference for every slash command, grouped by plugin. |
| **[docs/jira-flow.md](docs/jira-flow.md)** | `jira-flow.yaml` schema (`defaults`, `status_map`, `lifecycles`), `/configure` walkthrough, Implementation Summary contract, read-back verification. |
| **[docs/autonomous-mode.md](docs/autonomous-mode.md)** | Unattended-operation lifecycle: `/autonomous-start` → checkpoint hook → `/autonomous-resume` → `/debrief`. Survives token-limit hits and session crashes. |
| **[docs/green-or-revert.md](docs/green-or-revert.md)** | Build-state machine (`UNKNOWN`/`SUCCESS`/`STALE`/`FAILURE`). Hard gate on commits/pushes/PRs while build is broken. Stops the "I think the test passes" failure mode. |
| **[docs/context-forking.md](docs/context-forking.md)** | Fork a discussion into an isolated context and return with only the conclusion: `/branch` + `/return`, the two-session isolation model, the `.claude/forks/` LIFO stack, and when to use a subagent instead. |
| **[docs/e2e-cycle.md](docs/e2e-cycle.md)** | The four E2E spec commands (`/spec-e2e`, `/document-e2e`, `/resync-e2e`, `/audit-e2e`) and how they relate (intent ↔ spec ↔ code ↔ tests). |
| **[docs/troubleshooting.md](docs/troubleshooting.md)** | Common errors: path-lock blocks, gate-advance blocks, cache staleness, MCP auth dropout, worktree-strips-Task quirk. |
| **[docs/internals/](docs/internals/)** | For extending or debugging the marketplace itself: architecture, hooks reference, path-lock design, build-state machine, agent anatomy, expertise files, extension cookbook, CC quirks. |
| **[agents-overview.md](agents-overview.md)** | Per-agent reference: role, delegations, write allowlist, when-to-use. The cross-plugin matrix. |

## Plugins

- **`common`** — eight shared mindset skills (`mental-model`,
  `active-listener`, `zero-micromanagement`, `conversational-response`,
  `till-done`, `scope-discipline`, `evidence-over-assumption`,
  `name-the-disagreement`) plus the `autonomous-mode` and
  `green-or-revert` skills. Cross-topology commands: `/autonomous-start`,
  `/autonomous-resume`, `/debrief`, `/recap`. Hooks: session-log,
  autonomous-checkpoint, mark-build-stale, capture-build-result,
  gate-advance. Required by every topology.
- **`multi-team`** — the generic 9-agent topology: orchestrator + 3
  leads (Opus, delegate-only) + 6 workers (Sonnet, domain-locked).
  For plan → build → validate workflows.
- **`solo-pair`** — a lightweight 2-agent topology: dev + reviewer.
  For small tasks where multi-team's overhead isn't worth it.
- **`hex-backend`** — a 13-agent hexagonal-architecture topology
  with a per-Task quality loop (qa → refactor-advisor → code-reviewer).
  Path-lock keyed to the canonical `domain/application/api-rest/
  infrastructure/bootstrap` Maven layout. Ships three flow commands
  (`plan-build-validate`, `reproduce-fix-verify`, `investigate`) plus
  a four-command E2E spec cycle
  (`spec-e2e` / `document-e2e` / `resync-e2e` / `audit-e2e`).
- **`discovery`** — a 6-agent continuous product-discovery topology
  (discovery-lead + opportunity-framer + user-researcher +
  assumption-tester + evidence-auditor + epic-briefer). Sits *upstream*
  of the build topologies — translates raw signals into validated
  opportunities, hands off to engineering via a delivery brief.
- **`jira-flow`** — adds an `atlassian-expert` worker plus Jira-aware
  slash commands (`configure`, `capture`, `plan-track-build-validate`,
  `execute`, `drain`, `advance`). Layers on top of any topology that
  ships the standard 3-lead set, OR any topology with a custom lifecycle
  declared in `jira-flow.yaml` (used by `/advance` — discovery's column
  flow rides on this). Project Jira config lives at `jira-flow.yaml` in
  the project root: `defaults` block (site / project_key / board_id /
  status_map / issue_types), plus `default_topology` and per-topology
  lifecycles. `atlassian-expert` enforces anti-hallucination (refuses
  to infer site URLs from repo names) and read-back verification on
  every Jira write.
- **`book`** — a 10-agent book-writing topology. Outside the
  software-engineering surface area; documented in
  `book/book-topology.md`.

Edit once here, install in any project, version like normal code.

## Why a multi-agent system

We are building **a system that will build systems**. Software worth
shipping needs more than one perspective — a planner, an implementer,
a reviewer — and trying to compress all three into one agent gets you
mediocre versions of all three. This plugin packages the three-tier
pattern (orchestrator → leads → workers) so any Claude Code project
can install a team rather than hire one.

The mindset comes from indydev Dan's `lead-agents` pattern (the second
asset in his Agentic Horizon trilogy). The Claude Code adaptation here
ports the agents, the path-lock hook, and the eight mindset skills
(`mental-model`, `active-listener`, `zero-micromanagement`,
`conversational-response`, `till-done`, `scope-discipline`,
`evidence-over-assumption`, `name-the-disagreement`). Some Pi-format
features (machine-readable team-config YAML, runtime env-var injection
into agents) don't have direct CC equivalents and live as conventions
instead. See `agents-overview.md` for the full audit and per-topology
agent matrices.

```
claude-multi-team-plugin/
├── .claude-plugin/marketplace.json  # 6-plugin marketplace: common + multi-team + solo-pair + hex-backend + discovery + jira-flow
├── bin/install.sh                   # one-command installer for all six plugins
├── common/                          # shared mindset skills + centralized expertise (required by every topology)
│   ├── .claude-plugin/plugin.json
│   ├── expertise/                   # per-agent mental-model.yaml stubs (centralized via host symlink)
│   └── skills/                      # 8 mindset skills
├── multi-team/                      # generic 9-agent topology (frontend-dev / backend-dev / etc.)
│   ├── .claude-plugin/plugin.json
│   ├── agents/                      # 9 subagent system prompts
│   ├── commands/                    # /multi-team:plan-build-validate
│   ├── hooks/path-lock.py
│   └── multi-team-topology.md
├── solo-pair/                       # 2-agent dev/reviewer pair
│   ├── .claude-plugin/plugin.json
│   ├── agents/
│   └── solo-pair-topology.md
├── hex-backend/                     # 13-agent hexagonal-architecture backend topology
│   ├── .claude-plugin/plugin.json
│   ├── agents/                      # planning team (4) + engineering team (4) + validation team (5)
│   ├── commands/                    # /hex-backend:plan-build-validate
│   ├── hooks/path-lock.py           # keyed to */src/main and */src/test
│   └── hex-backend-topology.md
├── discovery/                       # 6-agent continuous product-discovery topology
│   ├── .claude-plugin/plugin.json
│   ├── agents/                      # discovery-lead + 5 workers (framer, researcher, tester, auditor, briefer)
│   ├── commands/                    # /discovery:capture
│   ├── hooks/path-lock.py           # keyed to docs/discovery/**
│   ├── jira-flow.lifecycle.example.yaml
│   └── discovery-topology.md
├── jira-flow/                       # Jira lifecycle layer (pair with any topology)
│   ├── .claude-plugin/plugin.json
│   ├── agents/atlassian-expert.md
│   └── commands/                    # /jira-flow:{capture,plan-track-build-validate,execute,drain,advance}
├── agents-overview.md               # cross-agent matrix + indydev-Dan idea audit
└── README.md                        # you are here
```

---

## Setup

### Install + per-project setup (one command)

From inside the host project where you want to use the agents:

```sh
cd /path/to/your/host-project
~/coding/harnessing/claude/claude-multi-team-plugin/bin/install.sh --topology=multi-team
```

That single command does **all three** setup steps:

1. Registers this repo as a Claude Code plugin marketplace and installs
   all six plugins (`common` + `multi-team` + `solo-pair` +
   `hex-backend` + `discovery` + `jira-flow`).
2. Sets up the current directory as a host project by creating
   `.claude/expertise` as a **symlink** to the plugin's centralized
   expertise directory (so accumulated agent knowledge follows you
   across projects).
3. With `--topology=NAME` (one of `multi-team`, `solo-pair`,
   `hex-backend`, `discovery`), copies the topology snippet into
   `.claude/` and appends `@.claude/<topology>-topology.md` to
   `CLAUDE.md` (creating `CLAUDE.md` if missing). For
   `--topology=discovery`, the lifecycle template is also seeded to
   `jira-flow.yaml` (edit project_key, issue_type,
   and status names to match your discovery board). The append is
   idempotent — re-running
   doesn't duplicate the line.

If you skip `--topology`, the plugins install but you'll need to wire
`CLAUDE.md` yourself (see the "Per host project: activate orchestrator
mode" subsection below).

You only *use* one topology per project (the one you `@-import` from
your `CLAUDE.md`), but installing all of them is harmless — agents
only consume context when invoked.

To install for a different host project from anywhere:

```sh
~/coding/harnessing/claude/claude-multi-team-plugin/bin/install.sh /path/to/host-project
```

Re-running the script is safe — marketplace re-registration is
idempotent and the symlink check refuses to clobber existing files.

If you've **edited the plugin source without bumping a version** and
want CC to pick up the changes, add `--clean` to force a full
teardown + reinstall (uninstalls each plugin, nukes
`~/.claude/plugins/cache/alegomes/`, then re-registers and installs):

```sh
~/coding/harnessing/claude/claude-multi-team-plugin/bin/install.sh --clean
```

### Manual install (one slash command per plugin)

If you'd rather see each step, run these in any Claude Code session:

```
/plugin marketplace add /path/to/claude-multi-team-plugin
/plugin install common@alegomes        # required by every topology — 8 mindset skills
/plugin install multi-team@alegomes    # generic 9-agent topology
/plugin install solo-pair@alegomes     # 2-agent dev/reviewer pair
/plugin install hex-backend@alegomes   # 13-agent hexagonal-architecture topology
/plugin install jira-flow@alegomes     # Jira lifecycle layer (pair with a topology)
```

Then create the expertise symlink manually in your host project:

```sh
ln -s /path/to/claude-multi-team-plugin/common/expertise \
      /path/to/host-project/.claude/expertise
```

`common@alegomes` is required by every topology — it ships the eight
mindset skills (`mental-model`, `active-listener`, `zero-micromanagement`,
`conversational-response`, `till-done`, `scope-discipline`,
`evidence-over-assumption`, `name-the-disagreement`). The agents reference
these skills in their bodies; without `common` installed, the references
go nowhere.

**`jira-flow` requires a topology** — its commands delegate to
`planning-lead`, `engineering-lead`, `validation-lead` by name.
`hex-backend` and `multi-team` both ship those leads; `solo-pair`
doesn't, so jira-flow + solo-pair-only would fail.

The expertise symlink is what makes accumulated agent learnings persist
*across* projects — agents read and write to a single shared location
inside the plugin, regardless of which host project they're running in.
See `common/skills/mental-model/SKILL.md` for the agent-global vs
project-specific guardrail.

### Per host project: activate orchestrator mode

The plugin ships the *agents*, but the **main session's** orchestrator
behavior comes from the host project's `CLAUDE.md`. Two-line setup in
each project where you want this:

```sh
# from the host project root, pick ONE topology:
mkdir -p .claude

# OPTION A — multi-team (3 leads + 6 workers, generic):
cp ~/coding/harnessing/claude/claude-multi-team-plugin/multi-team/multi-team-topology.md .claude/

# OPTION B — solo-pair (1 dev + 1 reviewer, lightweight):
cp ~/coding/harnessing/claude/claude-multi-team-plugin/solo-pair/solo-pair-topology.md .claude/

# OPTION C — hex-backend (3 teams · 13 agents · per-Task quality loop):
cp ~/coding/harnessing/claude/claude-multi-team-plugin/hex-backend/hex-backend-topology.md .claude/
```

Then add one line to the project's `CLAUDE.md` (create it if it doesn't
exist), referencing the snippet you copied:

```markdown
@.claude/multi-team-topology.md     # or solo-pair-topology.md, or hex-backend-topology.md
```

Each topology snippet is self-contained, so you can swap between them
by changing the `@-import` line. Don't import more than one at once —
orchestrator instructions conflict across topologies.

If the project already has a `CLAUDE.md`, just append that one `@-import`
line to the bottom — it composes with whatever else is in there.

---

## Verify the install

In the host project, in Claude Code:

```
/agents          # should list the agents for your installed topology
/plugin list     # should show common + your topology plugin(s)
```

For `multi-team`, `/agents` lists all 9 agents (3 leads + 6 workers).
For `solo-pair`, 2 agents. For `hex-backend`, all 13. Plus
`atlassian-expert` from `jira-flow` if installed. Either way the eight
`common` skills should be auto-loaded into the session.

Then try a canonical workflow (use the right namespaced command for
your installed topology):

```
/multi-team:plan-build-validate add a --json output flag to predict
# OR — if jira-flow is also installed:
/jira-flow:plan-track-build-validate add a --json output flag to predict
# OR — for hex-backend:
/hex-backend:plan-build-validate <task>
```

The orchestrator should fan out to `planning-lead`, `engineering-lead`,
and `validation-lead` in sequence, with each lead delegating to its
workers. If you see the main session writing code itself instead of
delegating, the orchestrator instructions need tightening — edit the
relevant `*-topology.md`, bump the version, and `/plugin update <name>`.

---

## How it works

### The three-tier model

Every topology (except solo-pair) follows the same shape:

```
        ┌─────────────────────────────┐
        │  orchestrator (main session) │   delegate-only, no Edit/Write
        └──────────────┬──────────────┘
                       │ Task tool
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
  planning-lead   engineering-lead   validation-lead    Opus, delegate-only
       │               │               │
       ▼               ▼               ▼
   PM, UX, …      dev workers      qa, security, …    Sonnet, write code
```

- **Orchestrator** = the Claude Code session you're typing into. It
  doesn't write code; it decomposes the request and dispatches leads.
  Behavior comes from the topology snippet you imported into `CLAUDE.md`.
- **Leads** are Opus subagents with **no `Edit`/`Write`/`MultiEdit`
  tools**. They can `Read`, `Grep`, run `Task` (to call workers), and
  write specs/task docs only. The lack of edit tools is the enforcement —
  a lead literally cannot write source code.
- **Workers** are Sonnet subagents with edit tools but **domain-locked
  write globs**. The `path-lock.py` hook (multi-team, hex-backend)
  blocks writes outside each worker's allowlist with exit code 2; the
  agent receives the blocked message on stderr and self-corrects (or
  delegates to the right peer).

`solo-pair` skips the lead tier — `pair-dev` writes, `pair-reviewer` is
read-only via tool allowlist (no path-lock hook). It's the right choice
when fan-out overhead would dwarf the task.

### What's enforced vs. what's convention

| Guarantee | How | Bypassable? |
|---|---|---|
| Leads can't write code | tool allowlist (no `Edit`/`Write`/`MultiEdit`) | No — CC enforces tool allowlists |
| Workers stay in their domain | `path-lock.py` PreToolUse hook, exit 2 | No (multi-team, hex-backend); solo-pair has no hook |
| Orchestrator delegates instead of coding | prompt-only (`zero-micromanagement` skill + topology snippet) | **Yes** — strong tendency, not a hard block |
| Plan → build → validate ordering | prompt-only (in command + topology) | Yes — orchestrator can reorder if user pushes |
| jira-flow only mutates Jira via MCP | tool allowlist (`atlassian-expert` is the only agent with Atlassian MCP tools) | No |

If you see the main session writing code, that's a *prompt* failure —
tighten the topology snippet, bump the version, `/plugin update`. The
hard guardrails (tool allowlist + path-lock) catch worker misbehavior.

### Per-topology workflow at a glance

**multi-team** — `/multi-team:plan-build-validate <task>`:

```
orchestrator
  → planning-lead → product-manager + ux-researcher  (specs/**)
  → engineering-lead → frontend-dev + backend-dev    (apps/**)
  → validation-lead → qa-engineer + security-reviewer
  → orchestrator synthesizes verdict for user
```

≈9 subagent invocations per run. Use for greenfield features that
need product/UX framing before code.

**solo-pair** — describe the task in chat:

```
orchestrator → pair-dev → pair-reviewer → orchestrator reports
```

2 subagent invocations. Use for one-file tweaks, bug fixes,
refactors with obvious scope.

**hex-backend** — `/hex-backend:plan-build-validate <task>`:

```
orchestrator
  → planning-lead → epic-author + product-manager + integration-analyst (parallel)
  → engineering-lead, per Task:
       → domain-dev / api-dev / adapter-dev (the right one for that Task)
       → qa-engineer (gap scan; CRITICAL/HIGH blocks → back to dev)
       → refactor-advisor (housekeeping report, advisory only)
       → code-reviewer (APPROVE/REJECT vs TASK.md → REJECT loops back)
  → validation-lead → security-reviewer + ./mvnw verify
  → orchestrator reports
```

≈13 subagents + a per-Task quality loop that may iterate. Use for
hexagonal Java/Quarkus backends. Cost scales with Task count, not
just topology size.

**discovery** — continuous, no `plan-build-validate` equivalent. One
column at a time:

```
/discovery:capture "raw signal"     → card lands in Inbox
/jira-flow:advance <KEY>            → discovery-lead routes to opportunity-framer (Framing)
/jira-flow:advance <KEY>            → user-researcher (Researching)
... human collects evidence ...
/jira-flow:advance <KEY>            → assumption-tester writes test plan; gate on Validating
... human runs tests, drops evidence in docs/discovery/<KEY>/evidence/ ...
/jira-flow:advance <KEY>            → evidence-auditor returns verdicts
/jira-flow:advance <KEY>            → epic-briefer writes handoff brief, links to engineer board
```

6 agents, but each card invokes them sequentially (or loops back). The
`/jira-flow:advance` command reads `jira-flow.yaml` to
know which agent to invoke per column. Use for product-discovery work
*upstream* of any build topology.

**jira-flow** layers on top of any topology — its commands delegate to
`planning-lead`/`engineering-lead`/`validation-lead` (for the lead-based
flows) or to `on_enter` agents declared in `jira-flow.yaml`
(for `/advance`). Adds Jira lifecycle: Epic + Stories registered for build
topologies; column-by-column transitions for discovery (or any custom
lifecycle). See `agents-overview.md` §"Workflow walkthroughs" for a
turn-by-turn narrative.

### Composition rules

- **Pick exactly one topology per project.** Importing two topology
  snippets gives the orchestrator conflicting instructions. Exception:
  `discovery` is *upstream* of build topologies — they don't compete,
  they hand off via the engineer-board Epic. If you want continuous
  discovery and code delivery in the same project, install discovery
  + a build topology + jira-flow, and let the handoff cross the
  boundary explicitly via `epic-briefer` → `epic-author`.
- **`common` is required** for every topology. The skills are
  referenced in agent bodies.
- **`jira-flow`'s lead-based commands require a 3-lead topology**
  (multi-team or hex-backend). solo-pair has no leads → those commands
  fail at first delegation. `/jira-flow:advance` is generic: it works
  with discovery (or any topology that ships a lifecycle file).
- **You can swap topologies** — change the `@-import` line in
  `CLAUDE.md` and the orchestrator behavior swaps with it. Plugins
  installed but not imported don't consume context.

### Failure modes you'll actually hit

| Symptom | Cause | Fix |
|---|---|---|
| `Unknown command: /plan-build-validate` | bare command form | use namespaced: `/multi-team:plan-build-validate` |
| Main session writes code instead of delegating | weak topology snippet for this task class | tighten the snippet or restate the rule in chat |
| `[hex-backend path-lock] BLOCKED: agent 'X' cannot Edit Y` | worker writing outside its domain | correct — let it delegate, or check `ALLOWED_WRITES` if your layout differs |
| `[hex-backend path-lock] BLOCKED: unknown agent 'orchestrator'` on a worker tool call | hook can't read `agent_type` (CC version mismatch) | see Troubleshooting §"Hook fails to detect agent name" |
| `/agents` doesn't list a topology after install | `common@alegomes` missing, or topology not installed | re-run `bin/install.sh` |
| jira-flow commands hang on solo-pair | no leads exist | switch to multi-team or hex-backend |

### What it can't do

- **Run code on its own infrastructure.** Agents call `Bash` against
  *your* shell — they can run tests and tools you have installed, but
  there's no sandbox.
- **Persist memory between unrelated sessions** beyond what
  `expertise/<agent>-mental-model.yaml` files capture. Pick up where
  you left off lives in the host symlink, not magic.
- **Override CC's own guardrails.** If a tool requires user confirmation
  in your CC permission mode, the agent will pause for it.
- **Replace human review.** The `code-reviewer` agent (hex-backend) is
  an LLM verdict — useful, not authoritative. Treat it as a first pass.

---

## Iteration workflow

This is the whole point of using a plugin instead of copy-pasting `.claude/`:

1. **Edit centrally** in `~/coding/harnessing/claude/claude-multi-team-plugin/`
   — agents, skills, commands, hooks, or a topology snippet.

2. **Bump the version** of whichever plugin(s) you changed. Each plugin
   has *two* places that must match: its own `plugin.json` and its
   entry in the marketplace's `marketplace.json`.

   | What you touched | Plugin to bump | Both files to update |
   |---|---|---|
   | `multi-team/` (agents, commands, hooks, topology) | `multi-team` | `multi-team/.claude-plugin/plugin.json` + `multi-team` entry in `marketplace.json` |
   | `solo-pair/` | `solo-pair` | `solo-pair/.claude-plugin/plugin.json` + `solo-pair` entry in `marketplace.json` |
   | `hex-backend/` (agents, commands, hook, topology) | `hex-backend` | `hex-backend/.claude-plugin/plugin.json` + `hex-backend` entry in `marketplace.json` |
   | `jira-flow/` (agent, commands) | `jira-flow` | `jira-flow/.claude-plugin/plugin.json` + `jira-flow` entry in `marketplace.json` |
   | `common/skills/` or `common/expertise/` | `common` | `common/.claude-plugin/plugin.json` + `common` entry in `marketplace.json` |
   | Cross-cutting | all affected | bump each plugin's two files |

   Semver (currently at `0.1.0` — version stays at `0.1.0` until first
   public release; the marketplace is local-only for now):
   - `0.1.0 → 0.1.1` — prompt tweaks (patch), once we start versioning
   - `0.1.0 → 0.2.0` — new agents/skills/commands (minor)
   - `0.x → 1.0.0` — when stable and publicly released

3. **Commit** the change locally:

   ```sh
   cd ~/coding/harnessing/claude/claude-multi-team-plugin
   git add .
   git commit -m "v0.1.1 — <what changed>"
   ```

4. **Update each project**: in Claude Code, `/plugin update <name>` per
   plugin you bumped (or `/plugin update` to refresh all installed).

Projects that need a specific version pin to it explicitly:
`/plugin install multi-team@0.1.0`.

---

## Per-project overrides

A worker's domain glob (`apps/*/api/**` for multi-team, `domain/src/main/**`
for hex-backend, etc.) won't match every project.

### Override a subagent locally

Drop a `.claude/agents/<agent-name>.md` in the host project. **Project-local
agents win over plugin-shipped ones** — keep the plugin's prompt as a
base, just change the `tools:` allowlist or the prose write-globs to
match your layout.

### Adjust the path-lock hook for your project layout

The hook's `ALLOWED_WRITES` table — `multi-team/hooks/path-lock.py` (for
multi-team) or `hex-backend/hooks/path-lock.py` (for hex-backend) — is
the source of truth for write-glob enforcement. If you need different
paths for one project:

1. **Edit centrally** if the new layout should be the new default for
   *all* projects (then bump version + update).
2. **Add a project-specific hook** at `.claude/hooks/path-lock.py` and
   register it in `.claude/settings.json`. Project hooks run alongside
   plugin hooks — both must pass.

---

## What's NOT in the plugin (intentionally)

- **Demo apps** — bring your own.
- **`justfile`** — keep your project's existing build tooling.
- **A Pi version** — Pi's adapter still lives in the original
  `lead-agents/` repo until we port it to a Pi extension.

---

## Versioning policy

- `0.x` — pre-stable, breaking changes allowed at any minor bump.
- `1.x` — stable, breaking changes only at major bumps.
- **Hooks that block previously-allowed paths are breaking changes.**
- Adding a new agent/skill/command is a minor bump.
- Prompt-only edits to existing agents are patches.

---

## Troubleshooting

**`/plugin marketplace add` says "not found"**
The path needs to point at the directory containing `.claude-plugin/`.
Check: `ls ~/coding/harnessing/claude/claude-multi-team-plugin/.claude-plugin/` should
list `plugin.json` and `marketplace.json`.

**`/agents` doesn't show your topology's agents after install**
Run `/plugin list` — the plugins you installed should be active.
Common cause: you installed a topology but forgot `common@alegomes`,
which is required-alongside. Re-run the install commands. If the
marketplace itself isn't listed, re-add it with the absolute path
(no `~`).

**Hook blocks a legitimate write**
The `ALLOWED_WRITES` table in `multi-team/hooks/path-lock.py` is mismatched with
the agent's prose. Either widen the glob (and bump version) or override
the agent locally.

**Hook fails to detect agent name**
Run `claude --debug` in the host project. The hook prints to stderr;
check whether it's falling back to `"orchestrator"` for delegated calls.
On CC 2.1.x the agent identity comes from the PreToolUse payload's
`agent_type` field (plugin-namespaced as `<plugin>:<agent>`); the hook
strips the prefix. If you're on a different CC version that uses a
different field name, inspect the payload by adding
`print(payload, file=sys.stderr)` at the top of `path-lock.py`'s
`main()` and add the right key to `detect_agent`.

**`/multi-team:plan-build-validate` says "Unknown command"**
CC plugin commands are namespaced by plugin. Use the namespaced form
(`/multi-team:plan-build-validate`, `/hex-backend:plan-build-validate`,
`/jira-flow:execute`, etc.) — the bare form (`/plan-build-validate`)
won't work.
