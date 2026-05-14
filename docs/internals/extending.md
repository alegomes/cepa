# Extending the marketplace

Cookbook for adding new things. Each section has a minimal checklist
and the gotchas that bit us in the past.

## Add a new agent

1. **Pick a plugin** — which topology owns this agent.
2. **Pick a name** — lowercase + hyphens, matches the filename, fits
   the role.
3. **Author the spec** — `<plugin>/agents/<name>.md`. Follow
   [`agent-anatomy.md`](agent-anatomy.md):
   - YAML frontmatter (`name`, `description`, `tools`, `model`,
     `color`).
   - Body header with the 6-row table (Reports to / Delegates to /
     Skills / Reads / Writes / Output).
   - Purpose paragraph.
   - Rules with bold lead-ins + "why" embedded.
   - Workflow (if non-trivial).
   - Output shape (if it produces a file artifact).
4. **Update `path-lock.py`** — add an entry to `ALLOWED_WRITES`
   matching the `Writes` row in the spec. Keep prose and hook in sync.
5. **Create the expertise stub** — `common/expertise/<name>-mental-model.yaml`
   with the minimal header (see [`expertise.md`](expertise.md)).
6. **Update `agents-overview.md`** — add a row to the relevant topology
   table.
7. **Cross-references** — if the new agent delegates to others or is
   delegated to, update the related agents' `Delegates to` /
   `Reports to` rows.
8. **`bin/install.sh --clean`** — refresh the cache.
9. **Test** — in a fresh CC session against a host project: `/agents`
   should list it; invoke it; verify path-lock allows expected writes
   and blocks others.

Gotchas:

- **Description matters for triggering.** If CC isn't picking up the
  agent when expected, the description is too vague. Rewrite from the
  caller's perspective.
- **Tools enforce hard.** Forgetting `Bash` in `tools:` means the
  agent can't run `./mvnw verify`. CC's tool allowlist is
  non-bypassable.
- **`name` MUST match what CC sends in `agent_type`.** Watch out for
  typos between frontmatter, filename, path-lock entry, and
  cross-references.

## Add a new command (slash command)

1. **Pick a plugin** — which surface area owns this command.
2. **Author the spec** — `<plugin>/commands/<name>.md`. Convention:
   - YAML frontmatter (`description`, `argument-hint`).
   - `# /<plugin>:<name>` heading.
   - Purpose section.
   - Variables section (what `$ARGUMENTS` looks like).
   - Instructions section (the orchestrator's role).
   - Workflow section (numbered steps, each with explicit
     delegations).
   - Constraints section (what NOT to do).
3. **Update `agents-overview.md`** — add the command to the plugin's
   commands table.
4. **Update `docs/commands.md`** — add to the reference + the
   "when to use" section.
5. **`bin/install.sh --clean`** — refresh.
6. **Test** — `/plugin:command-name args` in a session.

Gotchas:

- **Bare command name fails.** `/command-name` doesn't work; only
  `/<plugin>:<command>` does.
- **Frontmatter `description` is the help text in `/help`.** Make it
  clear about when to use vs. similar commands.
- **`argument-hint` shapes the inline prompt.** Match the parsing
  rules in your Workflow's "Parse arguments" step.

## Add a new skill

1. **Pick a plugin** — usually `common` (cross-topology). Topology-
   specific skills exist (book has 2) but most belong in common.
2. **Author the spec** — `<plugin>/skills/<name>/SKILL.md`. The
   directory + `SKILL.md` filename are conventional; CC discovers them.
   - YAML frontmatter (`name`, `description`).
   - Body: rules, examples, when-it-fires, when-it-doesn't-fire.
3. **Declare in `plugin.json`** — `"skills": "./skills/"` MUST be in
   `<plugin>/.claude-plugin/plugin.json`. Unlike agents and commands,
   skills need explicit declaration.
4. **Reference from agents** — agents that should honor the skill list
   it in their body's `Skills` table row.
5. **`bin/install.sh --clean`** — refresh.
6. **Test** — in a session, see if the skill auto-fires when its
   description matches. Or invoke via `/skill <name>` (if CC version
   supports).

Gotchas:

- **Forgot `"skills": "./skills/"`?** Skills won't load. Symptom:
  agents reference the skill but it has no effect.
- **Description = trigger heuristic.** Like agents, CC matches user
  context against skill descriptions. Vague descriptions don't fire.
- **Skills are auto-loaded session-wide.** No need to install per
  agent — install the plugin and all skills are available.

## Add a new hook

1. **Pick a plugin** — usually `common` (cross-topology hooks like
  `gate-advance`) or the topology that owns the enforcement (e.g.,
  `hex-backend/hooks/path-lock.py` is topology-specific).
2. **Author the script** — `<plugin>/hooks/<name>.py`. Must be
   executable (`chmod +x`). Conventional shape:

   ```python
   #!/usr/bin/env python3
   """Brief description of what the hook does."""

   import json, os, sys

   def main():
       raw = sys.stdin.read()
       try:
           payload = json.loads(raw) if raw.strip() else {}
       except json.JSONDecodeError:
           print("[<name>] could not parse payload", file=sys.stderr)
           sys.exit(0)  # Fail-open on parse error.

       # ... hook logic ...

       sys.exit(0)  # or sys.exit(2) for PreToolUse BLOCK

   if __name__ == "__main__":
       main()
   ```

3. **Register in `plugin.json`** — under `hooks.<EventName>`:

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Bash",
           "hooks": [
             {
               "type": "command",
               "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py\""
             }
           ]
         }
       ]
     }
   }
   ```

4. **`bin/install.sh --clean`** — refresh.
5. **Test** — trigger the hook event, observe expected behavior.
   `claude --debug` for stderr visibility.

Gotchas:

- **Multi-plugin collision.** If your hook is `PreToolUse` on a tool
  another plugin also gates, both fire. If yours can refuse on agents
  another plugin owns, you'll cross-block. Scope to your plugin's
  agents via a `PLUGIN_NAME` constant + prefix check (see
  [`path-lock.md`](path-lock.md)).
- **Fail-open vs. fail-closed defaults.** PostToolUse hooks should
  never block (exit 0 always). PreToolUse hooks should fail-open on
  parse errors (don't break the session because of bad JSON).
- **Hook isn't being called?** Check `bin/install.sh --clean` ran, the
  matcher regex is right (it's against `tool_name`), and the script
  is executable.
- **Don't use external Python deps.** The hook runs against whatever
  Python is on PATH. Stick to stdlib (`json`, `os`, `sys`, `re`,
  `pathlib`, `datetime`). PyYAML is tempting but adds an install
  dependency.

## Add a new plugin

Larger surface; comes up rarely but worth documenting.

1. **Decide it's a plugin, not a folder.** A new plugin is justified
   if:
   - It has its own composability constraints (different topologies
     ship it differently).
   - It has its own version cadence.
   - It's optional (users may want to skip it).

   If none apply, maybe it's just a new agent or command in an
   existing plugin.

2. **Create the directory structure**:

   ```
   <new-plugin>/
   ├── .claude-plugin/
   │   └── plugin.json
   ├── agents/
   ├── commands/
   ├── skills/        # if applicable
   ├── hooks/          # if applicable
   └── <new-plugin>-topology.md  # if it's a topology plugin
   ```

3. **Author `plugin.json`**:

   ```json
   {
     "name": "<new-plugin>",
     "version": "0.1.0",
     "description": "<one-line description of what this plugin adds>",
     "author": { "name": "alegomes" },
     "keywords": ["agents", "..."],
     "skills": "./skills/",
     "hooks": { ... }
   }
   ```

4. **Register in `marketplace.json`**:

   ```json
   {
     "plugins": [
       { "name": "<new-plugin>", "source": "./<new-plugin>" },
       ...
     ]
   }
   ```

   Source must be a **bare string** for local plugins (the object form
   `{ "type": "local", "path": "..." }` is for git-subdir only and
   triggers validation failure — see `cc_plugin_quirks` memory).

5. **Update `bin/install.sh`** — add the plugin install line and any
   per-topology wiring (if it's a topology plugin):

   ```sh
   echo "▶ Installing <new-plugin>@alegomes (...)"
   claude plugin install <new-plugin>@alegomes
   ```

   Also add to the topology validation (`case "${TOPOLOGY}" in
   ""|multi-team|...|<new-plugin>) ;;`).

6. **Author the plugin contents** — agents, commands, hooks per the
   recipes above.

7. **Update top-level README + agents-overview** — plugin list +
   structure tree.

8. **Update docs** — at minimum, `docs/topologies.md` (if it's a new
   topology) or `docs/commands.md` (always).

9. **`bin/install.sh --clean`** — verify the install works.

## Add to the topology snippet

Topology snippets (`<plugin>/<topology>-topology.md`) are imported into
the host's `CLAUDE.md`. They set orchestrator behavior for the
session.

To add a new instruction (e.g., "always run audit-e2e after a Story"):

1. Edit `<plugin>/<topology>-topology.md`.
2. `bin/install.sh --clean` against the host project (the snippet is
   COPIED at install time, not linked — edits don't propagate
   automatically).
3. Test in a session.

## Per-project overrides

For when a topology's defaults don't match this project:

### Override a subagent locally

Drop `.claude/agents/<agent-name>.md` in the host project. Project-
local agents win over plugin-shipped ones. Keep the plugin's prompt
as a base; just change the `tools:` allowlist or write-globs.

Don't forget to update `.claude/hooks/path-lock.py` if the local
override changes write paths.

### Add a project-specific hook

Drop `.claude/hooks/<name>.py` and register it in
`.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ./.claude/hooks/<name>.py"
          }
        ]
      }
    ]
  }
}
```

Project hooks run alongside plugin hooks — both must pass for the
operation to land.

## Iteration workflow

After any edit:

1. Bump the plugin's version (`plugin.json` + the `marketplace.json`
   entry). For early development at `0.1.0`, version stays at `0.1.0`
   until first public release.
2. Commit (per the `user_preferences` "split commits along feature/doc
   lines" rule).
3. `bin/install.sh --clean` in every host project that uses the
   plugin.
4. Test in CC.

## What to read before extending

- [`agent-anatomy.md`](agent-anatomy.md) — spec conventions.
- [`hooks.md`](hooks.md) — hook lifecycle, payload, exit codes.
- [`path-lock.md`](path-lock.md) — the prefix-scope and built-in-agent
  patterns.
- [`build-state.md`](build-state.md) — the three hooks behind
  `last-build.json`.
- [`expertise.md`](expertise.md) — file shape + lifecycle.
- [`cc-quirks.md`](cc-quirks.md) — empirical findings before stepping
  on the same mines.
- Memory file `cc_plugin_quirks.md` — the live, frequently-updated
  version of the quirks list.
