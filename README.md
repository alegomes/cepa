# claude-harness — multi-team agent plugin for Claude Code

A 9-agent topology for Claude Code: one orchestrator (the main session),
three leads (Opus, delegate-only), six workers (Sonnet, domain-locked
via tool allowlists + a path-lock hook).

Edit once here, install in any project, version like normal code.

```
claude-harness/
├── .claude-plugin/
│   ├── plugin.json          # plugin manifest (with hook registration)
│   └── marketplace.json     # makes this directory a 1-plugin marketplace
├── agents/                  # 9 subagent system prompts
├── skills/                  # 4 skills (mental-model, etc.)
├── commands/                # /plan-build-validate
├── hooks/path-lock.py       # PreToolUse path enforcement
├── agent-topology.md        # snippet for host project's CLAUDE.md
└── README.md                # you are here
```

---

## Setup

### One-time: register this plugin's marketplace in Claude Code

In any Claude Code session, run:

```
/plugin marketplace add ~/coding/harnessing/claude-harness
/plugin install multi-team@alegomes-multi-team
```

That's it for the plugin install — agents, skills, slash commands, and the
path-lock hook are now active in this session.

If `~` doesn't expand for your CC version, use the absolute path:

```
/plugin marketplace add /Users/alegomes/coding/harnessing/claude-harness
```

### Per host project: activate orchestrator mode

The plugin ships the *agents*, but the **main session's** orchestrator
behavior comes from the host project's `CLAUDE.md`. Two-line setup in
each project where you want this:

```sh
# from the host project root
mkdir -p .claude
cp ~/coding/harnessing/claude-harness/agent-topology.md .claude/
```

Then add one line to the project's `CLAUDE.md` (create it if it doesn't
exist):

```markdown
@.claude/agent-topology.md
```

If the project already has a `CLAUDE.md`, just append that one `@-import`
line to the bottom — it composes with whatever else is in there.

---

## Verify the install

In the host project, in Claude Code:

```
/agents          # should list all 9 multi-team agents
/plugin list     # should show multi-team v0.1.0
```

Then try the canonical workflow:

```
/plan-build-validate add a --json output flag to predict
```

The orchestrator should fan out to `planning-lead`, `engineering-lead`,
and `validation-lead` in sequence, with each lead delegating to its
workers. If you see the main session writing code itself instead of
delegating, the orchestrator instructions need tightening — edit
`agent-topology.md`, bump the version, and `/plugin update multi-team`.

---

## Iteration workflow

This is the whole point of using a plugin instead of copy-pasting `.claude/`:

1. **Edit centrally** in `~/coding/harnessing/claude-harness/`
   — agents, skills, commands, hooks, or the topology snippet.
2. **Bump the version** in two places:
   - `.claude-plugin/plugin.json` → `"version"`
   - `.claude-plugin/marketplace.json` → the matching entry's `"version"`

   Semver:
   - `0.1.0 → 0.1.1` for prompt tweaks (patch)
   - `0.1.0 → 0.2.0` for new agents/skills/commands (minor)
   - `0.x → 1.0.0` when stable
3. **Commit** the change locally:

   ```sh
   cd ~/coding/harnessing/claude-harness
   git add .
   git commit -m "v0.1.1 — <what changed>"
   ```
4. **Update each project**: in Claude Code, `/plugin update multi-team`.

Projects that need a specific version pin to it explicitly:
`/plugin install multi-team@0.1.0`.

---

## Per-project overrides

A worker's domain glob (`apps/*/api/**`, etc.) won't match every project.

### Override a subagent locally

Drop a `.claude/agents/backend-dev.md` in the host project. **Project-local
agents win over plugin-shipped ones** — keep the plugin's prompt as a base,
just change the `tools:` allowlist or the prose `Domain` block to match
your layout.

### Adjust the path-lock hook for your project layout

The hook's `ALLOWED_WRITES` table in `hooks/path-lock.py` is the source
of truth for write-glob enforcement. If you need different paths for one
project, the cleanest options are:

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
Check: `ls ~/coding/harnessing/claude-harness/.claude-plugin/` should
list `plugin.json` and `marketplace.json`.

**`/agents` doesn't show the multi-team agents after install**
Run `/plugin list` — the plugin should be active. If it's not, try
`/plugin install multi-team@alegomes-multi-team` again. If the
marketplace isn't listed, re-add it with the absolute path (no `~`).

**Hook blocks a legitimate write**
The `ALLOWED_WRITES` table in `hooks/path-lock.py` is mismatched with
the agent's prose. Either widen the glob (and bump version) or override
the agent locally.

**Hook fails to detect agent name**
Run `claude --debug` in the host project. The hook prints to stderr;
check whether it's falling back to `"orchestrator"` for delegated calls.
If so, the agent identity isn't in the payload format the hook expects
— inspect the payload by adding a `print(payload, file=sys.stderr)` at
the top of `path-lock.py`'s `main()` and re-run.
