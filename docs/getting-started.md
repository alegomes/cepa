# Getting started

The first 10 minutes with the marketplace. By the end you'll have one
topology installed, the right files wired into a project's `CLAUDE.md`,
and a real command running.

## 1. Prerequisites

- **Claude Code** installed: <https://docs.anthropic.com/en/docs/claude-code>
- **A host project** (a git repo where you want the agents to work).
  Greenfield is fine.
- **Python 3** on `PATH` — the hooks (`path-lock.py`, `gate-advance.py`,
  etc.) shell out via `python3`.
- **Optional but recommended:** if you want Jira integration, the
  Atlassian MCP connector configured in your Claude session
  (`/web-setup` connects it).

## 2. Install the marketplace

Clone this repo somewhere stable on your machine, then run the installer
from inside (or pointed at) your host project:

```sh
git clone https://github.com/alegomes/claude-multi-team-plugin.git \
  ~/coding/harnessing/claude/claude-multi-team-plugin

cd /path/to/your/host-project
~/coding/harnessing/claude/claude-multi-team-plugin/bin/install.sh \
  --topology=build-hex
```

That single command:

1. Registers this repo as a Claude Code plugin marketplace.
2. Installs all seven plugins (`common`, `build-team`, `build-solo`,
   `build-hex`, `discovery`, `board-flow`, `docs`).
3. Symlinks `./.claude/expertise/` → the plugin's centralized expertise
   directory (accumulated agent learnings follow you across projects).
4. Copies `build-hex-topology.md` into your `.claude/` and appends
   `@.claude/build-hex-topology.md` to your `CLAUDE.md` (creating it
   if absent).
5. Seeds `board-flow.yaml` at project root with placeholder values
   (you'll fix those next).
6. Writes `.claude/topology` (one-line marker so the cross-topology
   commands know which flow to dispatch into).

Re-run with `--clean` whenever you've edited the plugin source and want
CC to pick up the changes without a version bump.

Pick a different topology by changing `--topology=NAME`. See
[`topologies.md`](topologies.md) for the choice guide. The
`build-hex` topology in this guide assumes a Java/Quarkus hexagonal
project; for anything else use `build-team` (generic) or `build-solo`
(lightweight).

## 3. (Jira projects only) configure board-flow

If you'll use any `/board-flow:*` command:

```sh
# In Claude Code, in your host project:
/board-flow:configure
```

This walks you through site / project / board / status names / issue
types, validates the site via the Atlassian MCP, and runs a smoke test
to prove the config works end-to-end. Replaces the placeholder values
seeded by `install.sh`.

Without this step, every Jira write refuses with `BLOCKED: site not
found in board-flow.yaml defaults block; cannot infer.` — the
`atlassian-expert` agent will not fabricate a URL from your repo name.
That's intentional; see [`board-flow.md`](board-flow.md) for the full
contract.

## 4. Verify the install

```
/plugin list     # should show 7 alegomes plugins, all enabled
/agents          # should list the topology's agents (13 for build-hex)
```

If `/agents` is empty, you probably forgot `common@cepa` (required by
every topology) or installed without `--topology` and forgot to add the
`@.claude/<topology>-topology.md` line to `CLAUDE.md`. Re-run
`bin/install.sh --topology=NAME` against your project.

## 5. First command

The canonical command in `build-hex`:

```
/build-hex:plan-build-validate add a /users endpoint returning the current user's profile
```

What happens:

- Orchestrator delegates to `planning-lead` → spec gets written under
  `spec/<slug>.md` after `product-manager` + `epic-author` +
  `integration-analyst` run in parallel.
- Orchestrator delegates to `engineering-lead` → it decomposes the
  Story into atomic Tasks (TASK.md per Task under `docs/tasks/`), then
  runs the per-Task quality loop: `domain-dev`/`api-dev`/`adapter-dev` →
  `qa-engineer` → `refactor-advisor` → `code-reviewer`. Tasks merge to
  a per-Story integration branch.
- Orchestrator delegates to `validation-lead` → security review + full
  build verify (`./mvnw verify` with BUILD SUCCESS evidence).
- Orchestrator reports back: paths touched, integration risks,
  refactor-advisor findings, verdict.

Expect ~10-15 minutes for a small Story, depending on Task count and
how many quality-loop iterations qa or code-reviewer trigger.

## 6. (Optional) Jira-tracked autonomous run

If you'll step away while it works:

```
/common:autonomous-start "WEGO-1234 implement /users endpoint"
```

The Jira key in `$ARGUMENTS` is auto-detected. The orchestrator:

1. Transitions `WEGO-1234` to In Progress (with a comment naming the
   run ID).
2. Activates the `autonomous-mode` skill: no questions to you,
   ambiguities decided + logged with rationale.
3. Dispatches into `/build-hex:plan-build-validate`.
4. On completion, transitions the card to In Review with an
   Implementation Summary comment (files touched, BUILD SUCCESS
   commit, caveats).
5. Survives session crashes via `docs/autonomous/<run-id>/state.yaml`
   — pick up where it left off with `/common:autonomous-resume`.

After it finishes, walk the decisions it made:

```
/common:debrief
```

Verdicts you give (`keep` / `overrule: <reason>` / `refine: <rationale>`)
land in the agent's `common/expertise/<agent>-mental-model.yaml` —
next autonomous run reads them and biases toward your preferences.

See [`autonomous-mode.md`](autonomous-mode.md) for the full lifecycle.

## What's next

- Hit a wall? [`troubleshooting.md`](troubleshooting.md).
- Want to know which command to use when? [`commands.md`](commands.md).
- Editing a spec and want the tests to follow?
  [`e2e-cycle.md`](e2e-cycle.md).
- Bugged by mysterious "BLOCKED: build is STALE" messages?
  [`green-or-revert.md`](green-or-revert.md).
