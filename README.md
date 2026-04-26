# multi-team — Claude Code plugin

A 9-agent topology for Claude Code: one orchestrator (the main session),
three leads (Opus, delegate-only), six workers (Sonnet, domain-locked
via tool allowlists + a path-lock hook).

Edit once here, install in any project, version like normal code.

```
multi-team-plugin/
├── .claude-plugin/
│   ├── plugin.json          # the plugin manifest (with hook registration)
│   └── marketplace.json     # so this same repo IS a 1-plugin marketplace
├── agents/                  # 9 subagent system prompts
├── skills/                  # 4 skills (mental-model, etc.)
├── commands/                # /plan-build-validate
├── hooks/path-lock.py       # PreToolUse path enforcement
├── agent-topology.md        # snippet for host project's CLAUDE.md
└── README.md                # you are here
```

---

## Install in a project

You have three distribution options. Pick one based on how you want to share.

### Option A — Local path (single machine, fastest)

Best when both the plugin and the projects are on the same laptop and you
just want to iterate.

```sh
# In Claude Code, run:
/plugin marketplace add /absolute/path/to/multi-team-plugin
/plugin install multi-team@alegomes-multi-team
```

The plugin is now active in this project. To remove: `/plugin uninstall multi-team`.

### Option B — GitHub repo (multi-machine, multi-developer, recommended)

Best for sharing across machines or with teammates.

```sh
# Push this directory to a GitHub repo, then in any project:
/plugin marketplace add github.com/alegomes/multi-team-plugin
/plugin install multi-team@alegomes-multi-team
```

When you push updates to the repo: `/plugin update multi-team` in each project.

### Option C — Git submodule (locked version)

If you want each project to pin a specific version and update on its own
schedule:

```sh
# In your host project:
git submodule add <repo-url> .claude/plugins/multi-team
# Then in Claude Code:
/plugin marketplace add .claude/plugins/multi-team
/plugin install multi-team@alegomes-multi-team
```

---

## Activate orchestrator mode in the host project

Plugins ship the *agents*, but the **main session's** orchestrator behavior
is set by `CLAUDE.md` in the host project. One line in your project's
`CLAUDE.md` does it:

```markdown
@${CLAUDE_PLUGIN_ROOT}/agent-topology.md
```

Or, if `${CLAUDE_PLUGIN_ROOT}` substitution doesn't work in your CC version
(it varies), copy `agent-topology.md` into the project once:

```sh
cp /path/to/multi-team-plugin/agent-topology.md .claude/
# then in your CLAUDE.md:
# @.claude/agent-topology.md
```

If your project doesn't have a `CLAUDE.md` yet, just create one with that
single `@-import` line.

---

## Iteration workflow

This is the whole point of using a plugin instead of copy-pasting `.claude/`:

1. **Edit centrally** — change agents/skills/commands/hooks in `multi-team-plugin/`
2. **Bump version** in `.claude-plugin/plugin.json` and `marketplace.json`
   (semver — `0.1.0` → `0.1.1` for prompt tweaks, `0.2.0` for new agents,
   `1.0.0` when stable)
3. **Commit + push** (if using GitHub)
4. **Update each project**: `/plugin update multi-team`

Projects that need a different version pin to it explicitly:
`/plugin install multi-team@0.1.0`.

---

## Per-project overrides

A worker's domain glob (`apps/*/api/**`, etc.) won't match every project.
Two ways to override per-project:

### Override a subagent

Drop a `.claude/agents/backend-dev.md` in the host project. Project-local
agents win over plugin-shipped ones — you keep the plugin's prompt, just
change the `domain:` block (and the rest of the YAML/Markdown) for that
project's layout.

### Override the path-lock hook

Drop a project-specific `.claude/hooks/path-lock.py` (or extend it) and
register it in `.claude/settings.json`. Project hooks run alongside plugin
hooks — both must pass for the call to go through.

---

## What's NOT in the plugin (intentionally)

- **`apps/classifier/` demo** — that was a teaching example. Real projects
  bring their own apps.
- **`justfile`** — keep your project's existing build tooling.
- **`.pi/` adapter** — Pi version stays in the original `lead-agents/`
  repo until we port it to a Pi extension.

---

## Verify the install

After installing, in Claude Code:

```
/agents                     # should list all 9 multi-team agents
/plan-build-validate ...    # should run end-to-end
```

If `/agents` doesn't show them, the marketplace path is wrong; re-add it
with `/plugin marketplace list` to debug.

---

## Versioning policy

- `0.x` — pre-stable, breaking changes allowed at any minor bump
- `1.x` — stable, breaking changes only at major bumps
- Hooks that block previously-allowed paths are breaking changes
- Adding a new agent or skill is a minor bump
- Prompt-only edits to existing agents are patches
