# Troubleshooting

Common errors and their fixes. If your symptom isn't here, check
`agents-overview.md` (failure-modes table near the bottom) and
`README.md` (Troubleshooting section).

## Install / wiring

### `/plugin marketplace add` says "not found"

The path must point at the directory containing `.claude-plugin/`.
Check:

```sh
ls ~/coding/harnessing/claude/claude-multi-team-plugin/.claude-plugin/
# should list plugin.json and marketplace.json
```

If you used `~` in the path, replace with the absolute path.

### `/agents` doesn't list any agents after install

Three common causes:

1. **`common@alegomes` missing** — required by every topology because
   skills are referenced in agent bodies.
2. **Topology snippet not imported in `CLAUDE.md`** — agents are
   installed but the orchestrator doesn't know to use them.
3. **`.claude/topology` file missing** — cross-topology commands
   (`/common:autonomous-start`) can't dispatch without it.

Fix: re-run `bin/install.sh --topology=NAME` against your project. It
handles all three.

### `Unknown command: /plan-build-validate`

CC plugin commands are namespaced. Use the namespaced form:

```
/hex-backend:plan-build-validate    # not /plan-build-validate
/jira-flow:execute WEGO-1234
/common:autonomous-start "..."
```

### Edited the plugin source and CC isn't picking up changes

Plugin cache survives `claude plugin uninstall`. Force-refresh:

```sh
bin/install.sh --clean
```

`--clean` removes `~/.claude/plugins/cache/alegomes/` entirely before
reinstalling. Required after editing without a version bump.

## path-lock hook blocks

### `[hex-backend path-lock] BLOCKED: agent 'X' cannot Edit Y`

Worker tried to write outside its allowlist. Two cases:

1. **Right agent, wrong project layout.** `hex-backend`'s path-lock
   defaults to the canonical Maven layout (`domain/`, `application/`,
   `api-rest/`, `infrastructure/`, `bootstrap/`), but your project
   uses different module names (e.g., `tenancy-core/tenancy-api/...`).
   The error message includes the active role → module mapping; if it
   shows the canonical layout but your project doesn't use it, create
   `hex-backend.yaml` at project root mapping each role to your
   module:

   ```yaml
   schema_version: 1
   roles:
     domain:       tenancy-core
     application:  tenancy-core
     api:          tenancy-api
     adapter:      tenancy-adapter
     bootstrap:    tenancy-app
   ```

   `bin/install.sh --topology=hex-backend` seeds this file by default.
   If you have it, edit; if not, copy from
   `<plugin-repo>/hex-backend/hex-backend.example.yaml`.

2. **Right agent, right layout, wrong file.** The agent is writing the
   wrong file. Maybe the right answer is to delegate; check the
   agent's spec to see whose lane this should be.

### `[hex-backend path-lock] BLOCKED: unknown agent 'orchestrator' attempted Edit`

The hook couldn't identify the calling agent and fell back to
`"orchestrator"` (which has empty allowlist). Reasons:

- **Built-in CC agents (`statusline-setup`, `Explore`, `Plan`).** These
  have no `<plugin>:` prefix in `agent_type`. Fixed in commit `7c9d597`
  (no-colon agent_type treated as foreign, exit 0). If you're on an
  older plugin version, run `bin/install.sh --clean`.
- **CC version mismatch.** If you're on a CC version that uses a
  different field name for subagent identity, the hook's
  `detect_agent` function returns the wrong value. Inspect with:

  ```sh
  export HEX_PATHLOCK_DEBUG=1
  # re-run the operation; log lands at /tmp/hex-pathlock-debug.log
  ```

  Add the field name to `detect_agent`'s fallback list.

### Multi-plugin hook collision

Multiple plugins each register path-lock hooks → all fire on every
write → strictest wins. Symptom: an agent from plugin A is blocked by
plugin B's hook.

Fixed in commit `0284825` (each hook scopes to its own plugin's
agents via `PLUGIN_NAME` prefix check). If you're seeing this, your
plugins are stale. Run `bin/install.sh --clean`.

## gate-advance hook blocks

### `BLOCKED: build is STALE since edit to <path>`

You edited source code; the gate is refusing to let you commit / push
/ PR / deploy until verify proves the edit didn't break anything.

Fix:

```sh
./mvnw -pl <scope> verify
# Wait for BUILD SUCCESS. The capture-build-result hook will clear STALE.
git commit -m "..."   # now allowed
```

If verify fails, see next entry.

### `BLOCKED: build is FAILURE`

Last verify failed. Two valid responses:

- **Fix forward** if the failure is small and you know the cause.
  Apply the fix, re-run verify, repeat until green.
- **Revert** if you don't immediately see the cause. `git checkout --
  <files>` to discard the edit, re-run verify to confirm green, then
  approach the problem fresh.

Do NOT continue editing other files while build is FAILURE — each new
edit adds a confound to the failure surface.

### Gate fires for `./mvnw` itself

Shouldn't happen — the gate exempts verify/test invocations. If you
see it, check that `bin/install.sh --clean` actually ran (the exempt
list lives in `common/hooks/gate-advance.py`).

### I need to bypass the gate, just this once

Don't. The recovery is to re-establish green, not to silence the gate.

If you genuinely must commit broken state (one-off rescue commit on a
known-broken known-state):

```sh
echo '{"status": "SUCCESS", "at": "<now>", "command": "<override>", "kind": "manual", "tail": "manually overridden"}' \
  > .claude/last-build.json
```

The skill will flag that you cheated.

## Jira / atlassian-expert

### `BLOCKED: site not found in jira-flow.yaml defaults block`

`atlassian-expert` refused to infer the site URL. Fix:

```
/jira-flow:configure
```

Interactive walkthrough — validates the site against your accessible
Atlassian sites via MCP, asks for project_key / board_id / status_map,
runs smoke test.

If the MCP itself is dropped, see next entry.

### "Capture reported success but the card doesn't exist on Jira"

The `atlassian-expert` agent's read-back rule caught a lie — write
returned 200 but the card isn't there. Likely causes:

- **Required field missing.** Jira refused the create; the response
  was malformed in a way that the create call interpreted as success.
  Add the field to `defaults.required_fields` in `jira-flow.yaml`.
- **Permissions on the project.** Your Atlassian account doesn't have
  permission to create issues in the target project.
- **MCP transient failure.** Retry; if recurrent, reauthorize the
  connector.

### Atlassian MCP authorization dropped

CC's Atlassian MCP loses auth periodically. Symptom: MCP calls fail
with "not authorized for X." Fix:

```
/web-setup
```

Reconnects the Atlassian connector. Then retry whatever was running.

### `BLOCKED: review-style transition requires Implementation Summary`

A command tried to transition a card to `in_review` (or any
`requires_summary: true` column) without the Implementation Summary
comment. Agent-level enforcement; not bypassable.

Likely cause: you invoked `atlassian-expert` directly (or via a
non-standard command) without supplying the summary. Use the
canonical commands (`/jira-flow:execute`, `/jira-flow:advance`,
`/common:autonomous-start`) — they assemble the summary from the flow
output before delegating.

## autonomous-mode

### "No in-progress autonomous runs found"

`/common:autonomous-resume` couldn't find a `state.yaml` to resume.
Check `docs/autonomous/` — if empty, no run was ever started. If
present, the run may have completed or been debriefed (resume won't
re-run completed work).

### `/common:debrief` reports format drift on every run

Agents wrote decisions as inline prose instead of formal `### Decision:`
blocks. The dual-scan caught it. Accept the offer to record a
`principle`-tagged feedback entry on the drifting agent — the next run
reads its expertise file at boot and (hopefully) uses the formal block.

This is the reinforcement loop working as designed. Don't try to
silence the drift detection.

### Resume picks up at the wrong place

Open `docs/autonomous/<run-id>/state.yaml` and read the `log` tail.
The hook records every subagent call; if the last entry is misleading
(e.g., a sub-task that didn't actually complete), edit the file
manually before re-running resume.

If the file is corrupted, manual recovery is the only option — the
skill explicitly says corrupted state is the one place where asking
is OK.

## Worktrees + leads

### "engineering-lead has no Task tool" (lead can't delegate)

You invoked a lead with `isolation: "worktree"`. CC 2.1.x strips the
`Task` tool from worktreed subagents — a lead that can't delegate is
useless.

Fix: **leads never get worktree isolation.** They run in the main
session. Only dev workers (leaf agents that don't delegate further)
can use worktree.

`/hex-backend:plan-build-validate` enforces this. If you're invoking
leads ad-hoc, don't pass `isolation: "worktree"`.

See `cc_plugin_quirks` memory for the full empirical write-up.

## Discovery handoff

### `/discovery:capture` succeeds but the card isn't on the discovery board

Check `jira-flow.yaml` — `lifecycles[]` must have a `discovery` entry
with `project_key` matching your discovery board's project. If the
project key in `defaults.project_key` differs from the discovery
project, you need both (defaults for build topology, lifecycles entry
for discovery).

## When all else fails

1. `bin/install.sh --clean` — clears every cache, reinstalls, re-wires
   the topology snippet.
2. `/plugin list` — confirm all 7 plugins are enabled.
3. `claude --debug` — runs your session with verbose logging; hooks
   print to stderr.
4. Check `agents-overview.md`'s "Failure modes you'll actually hit"
   table for symptom matches.
5. Check `common/expertise/<agent>-mental-model.yaml` if a specific
   agent is misbehaving — feedback entries there can override default
   behavior.
