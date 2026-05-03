# claude-multi-team-plugin

A Claude Code plugin marketplace shipping a multi-agent setup as five
composable plugins:

- **`common`** — eight shared mindset skills (`mental-model`,
  `active-listener`, `zero-micromanagement`, `conversational-response`,
  `till-done`, `scope-discipline`, `evidence-over-assumption`,
  `name-the-disagreement`). Required by every topology.
- **`multi-team`** — the generic 9-agent topology: orchestrator + 3
  leads (Opus, delegate-only) + 6 workers (Sonnet, domain-locked).
  For plan → build → validate workflows.
- **`solo-pair`** — a lightweight 2-agent topology: dev + reviewer.
  For small tasks where multi-team's overhead isn't worth it.
- **`hex-backend`** — a 13-agent hexagonal-architecture topology
  with a per-Task quality loop (qa → refactor-advisor → code-reviewer).
  Path-lock keyed to the canonical `domain/application/api-rest/
  infrastructure/bootstrap` Maven layout.
- **`jira-flow`** — adds an `atlassian-expert` worker plus Jira-aware
  slash commands (`plan-track-build-validate`, `execute`, `drain`).
  Layers on top of any topology that ships the standard 3-lead set
  (multi-team or hex-backend).

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
├── .claude-plugin/marketplace.json  # 5-plugin marketplace: common + multi-team + solo-pair + hex-backend + jira-flow
├── bin/install.sh                   # one-command installer for all five plugins
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
├── jira-flow/                       # Jira lifecycle layer (pair with multi-team or hex-backend)
│   ├── .claude-plugin/plugin.json
│   ├── agents/atlassian-expert.md
│   └── commands/                    # /jira-flow:{plan-track-build-validate,execute,drain}
├── agents-overview.md               # cross-agent matrix + indydev-Dan idea audit
└── README.md                        # you are here
```

---

## Setup

### Install + per-project setup (one command)

From inside the host project where you want to use the agents:

```sh
cd /path/to/your/host-project
~/coding/harnessing/claude/claude-multi-team-plugin/bin/install.sh
```

That single command does **both**:

1. Registers this repo as a Claude Code plugin marketplace and installs
   all five plugins (`common` + `multi-team` + `solo-pair` +
   `hex-backend` + `jira-flow`).
2. Sets up the current directory as a host project by creating
   `.claude/expertise` as a **symlink** to the plugin's centralized
   expertise directory (so accumulated agent knowledge follows you
   across projects).

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
