# Hooks reference

Every hook the marketplace ships, what fires it, what it reads, what it
writes, and how to debug it.

## Hook events used

CC supports several PreToolUse / PostToolUse / etc. hook events. This
marketplace uses four:

| Event | Fires | Marketplace usage |
|---|---|---|
| `PreToolUse` | Before a tool call lands. Hook can exit 2 to BLOCK the call. | `path-lock.py` (every topology), `gate-advance.py` (common) |
| `PostToolUse` | After a tool call returns. Hook can observe + write to disk. Cannot block (the call already happened). | `autonomous-checkpoint.py`, `mark-build-stale.py`, `capture-build-result.py` (common) |
| `UserPromptSubmit` | When the user submits a prompt. Hook can observe; can inject system reminders. | `session-log.py` (common) |
| `SessionStart` | Session boot. Hook can inject context. | Not currently used. |

## Hook payload anatomy

CC pipes a JSON payload to the hook's stdin. The shape varies by event;
common keys we rely on:

```json
{
  "tool_name": "Edit",
  "tool_input": {
    "file_path": "/abs/path/to/file.java",
    "old_string": "...",
    "new_string": "..."
  },
  "tool_response": {                     // PostToolUse only
    "content": "...",
    "is_error": false,
    "exit_code": 0
  },
  "agent_type": "hex-backend:domain-dev",  // Subagent caller, plugin-namespaced.
                                             // Empty string when called from main session.
                                             // BUILT-IN CC AGENTS (statusline-setup,
                                             // Explore, Plan, general-purpose) arrive
                                             // with bare name, NO colon prefix.
  "cwd": "/abs/path/to/project",
  "session_id": "...",
  "hook_event_name": "PreToolUse"
}
```

`agent_type` resolution rules (see [`path-lock.md`](path-lock.md) for
the full design):

| Form | Source | Path-lock treatment |
|---|---|---|
| `<plugin>:<agent>` matching `PLUGIN_NAME` | Our subagent | Check `ALLOWED_WRITES` |
| `<plugin>:<agent>` with foreign prefix | Another plugin's subagent | Exit 0 (foreign — not our concern) |
| `<bare-name>` (no colon) | CC built-in (statusline-setup, etc.) | Exit 0 (foreign) |
| `""` (empty) | Main session orchestrator | Exit 0 (not gated) |

## Hook exit codes

| Exit | Meaning |
|---|---|
| `0` | Allow / observe / no-op |
| `1` | Generic error (CC may log; doesn't block) |
| `2` | **Block** (PreToolUse only). Stderr message reaches the calling agent so it can self-correct. |

## Every hook the marketplace ships

### path-lock.py × 4 (PreToolUse, matcher `Edit\|Write\|MultiEdit\|NotebookEdit`)

Owners: `multi-team/hooks/`, `hex-backend/hooks/`, `discovery/hooks/`,
`book/hooks/`.

Enforces per-agent write allowlists. Each instance has a `PLUGIN_NAME`
constant and an `ALLOWED_WRITES` dict keyed by agent name.

**Logic (post-fix flow):**

```python
1. Parse stdin JSON; fail-open on parse error.
2. If tool_name not in {Edit, Write, MultiEdit, NotebookEdit}: exit 0.
3. If file_path missing: exit 0.
4. raw_agent_type = payload["agent_type"]
   If has colon:
     prefix = raw_agent_type.split(":")[0]
     If prefix != PLUGIN_NAME: exit 0  (foreign plugin)
   Else: exit 0  (main session, built-in CC agent, or no agent info)
5. agent = detect_agent(payload)  (strips prefix; falls back to legacy keys)
6. If is_own_expertise_file(file_path, agent): exit 0
7. allowed = ALLOWED_WRITES.get(agent)
   If allowed is None: BLOCK ("unknown agent X")
8. If path_matches(file_path, allowed, project_root): exit 0
   Else: BLOCK with allowlist contents.
```

See [`path-lock.md`](path-lock.md) for design rationale, the
multi-plugin collision fix (`PLUGIN_NAME` prefix scoping), the
built-in-agent fail-open fix, and debugging via
`HEX_PATHLOCK_DEBUG=1`.

### gate-advance.py (PreToolUse, matcher `Bash`)

Owner: `common/hooks/`.

Hard gate against advancement commands when build state is unsafe.

**Logic:**

```python
1. Parse stdin; tool_name must be Bash; fail-open on parse error.
2. command = tool_input["command"]
3. If command matches any EXEMPT_PATTERN (mvnw, gradle, npm, pytest,
   cargo, go test, read-only git): exit 0  (recovery path; never gate)
4. If command does NOT match any ADVANCE_PATTERN (git commit, git push,
   gh pr create, gh pr merge, gh release, kubectl apply, terraform
   apply, docker push, aws/gcloud/az deploy): exit 0
5. Read .claude/last-build.json
   If missing: exit 0 with stderr warning (no baseline)
   If parse error: exit 0 with stderr warning
   If status == SUCCESS: exit 0
   If status == STALE: BLOCK with edit path + suggestion
   If status == FAILURE: BLOCK with failure tail + suggestion
```

ADVANCE_PATTERNS use regex with separator-aware lookahead
(`(?:^|\s|&&\s|;\s)`) so compound shells (`git add foo && git commit
-m bar`) match correctly.

### mark-build-stale.py (PostToolUse, matcher `Edit|Write|MultiEdit`)

Owner: `common/hooks/`.

Marks `last-build.json` as STALE after source edits.

**Logic:**

```python
1. Parse stdin; tool_name must be Edit/Write/MultiEdit.
2. file_path = tool_input["file_path"]
3. If is_source(file_path):
     - Read current .claude/last-build.json (if present) for last_known_*
     - Write new state: { status: STALE, since: now, after_edit_to,
       last_known_status, last_known_at, last_known_command }
4. Else: exit 0 (not production code; docs/specs/tests don't invalidate)
```

`is_source` allowlist: source-language extensions (`.java`, `.ts`,
`.py`, `.go`, etc.), build manifests (`pom.xml`, `package.json`,
`Cargo.toml`, etc.), SQL migrations. Path exclusions: `.claude/`,
`docs/`, `spec/`, `specs/`, `*/src/test/`, `/test/`, `/tests/`,
`/__tests__/`.

### capture-build-result.py (PostToolUse, matcher `Bash`)

Owner: `common/hooks/`.

Detects build/test invocations and writes SUCCESS or FAILURE to
`last-build.json`.

**Logic:**

```python
1. Parse stdin; tool_name must be Bash.
2. command = tool_input["command"]
3. Match against PATTERNS list (maven, gradle, npm, yarn, pytest,
   cargo, go-test). If no match: exit 0 (don't classify).
4. For matched kind:
     - Extract response text from tool_response (handles dict shape
       variants: stdout/output/result/content/stderr)
     - Check for kind-specific marker: BUILD SUCCESS / BUILD SUCCESSFUL
       in success path; BUILD FAILURE / BUILD FAILED in failure path
     - Fallback: exit_code 0 → SUCCESS; non-zero → FAILURE
     - Ambiguous (marker missing, exit code unknown): exit 0
5. Write { status: SUCCESS|FAILURE, at: now, command, kind,
   tail: last ~12 lines of response_text }
```

Pattern list is extensible — add a `(regex, kind, success_marker,
failure_marker)` tuple to `PATTERNS`. `None` markers fall back to exit
code only.

### autonomous-checkpoint.py (PostToolUse, matcher `Task`)

Owner: `common/hooks/`.

Out-of-band state writes during autonomous runs. Active only when
`CLAUDE_AUTONOMOUS_RUN_ID` is set in env.

**Logic:**

```python
1. Read CLAUDE_AUTONOMOUS_RUN_ID env. If unset: fast no-op.
2. Parse stdin; tool_name must be Task.
3. Extract subagent_type, prompt summary (description or first ~200
   chars of prompt), result text (handles list-of-blocks shape).
4. Append YAML list item to docs/autonomous/<run-id>/state.yaml's
   "log:" section: { timestamp, subagent, prompt_summary,
   result_summary, exit_status }.
5. Failures stderr-only; never break the workflow.
```

Append uses raw file manipulation (not PyYAML — no external deps).
Trusts the file ends with a `log:` list created by
`/common:autonomous-start`.

### session-log.py (UserPromptSubmit)

Owner: `common/hooks/`.

Captures every user prompt to `.claude/session-log.md` with date and
UTC time headers.

**Logic:**

```python
1. Parse stdin.
2. prompt = payload["prompt"] or payload["message"] (handles dict
   content shape).
3. Skip empty/whitespace prompts (CC sometimes fires on internal
   events).
4. Append to .claude/session-log.md:
   - First write to file → "# Session log\n\n## YYYY-MM-DD\n\n"
   - New date → "\n## YYYY-MM-DD\n\n"
   - Entry → "### HH:MM:SS UTC\n\n<prompt>\n\n"
```

`/common:recap` reads this file to render its "Asked / Status /
Delivered" table.

## Hook ordering when multiple match

CC fires hooks in the order they appear in `plugin.json`. When multiple
plugins each register hooks on the same event + matcher, **all of them
fire**. Order across plugins is unspecified.

Practical implication: every hook that returns exit 2 on the same call
short-circuits the rest. The strictest verdict wins.

This was the bug behind the multi-plugin path-lock collision (commit
`0284825`). Every path-lock fires on every gated tool call; without
prefix scoping, plugin A would block plugin B's agents. Fix: each hook
exits 0 early when the calling agent isn't from its plugin.

## Debugging hooks

### Verbose CC debug mode

```sh
claude --debug
```

Hooks print stderr; messages surface in the debug log.

### Hook-specific debug logs

`hex-backend/hooks/path-lock.py` has a `HEX_PATHLOCK_DEBUG` env var:

```sh
export HEX_PATHLOCK_DEBUG=1
# Re-run the operation. Log lands at /tmp/hex-pathlock-debug.log.
```

Each entry: payload top-level keys, identity fields probed,
env-agent vars, resolved agent name, tool, file path.

Useful when CC version changes (the `agent_type` payload field might
move; debug log shows what's actually arriving).

### Adding your own debug print

Insert `print(payload, file=sys.stderr)` at the top of `main()` and
re-run. The payload goes to CC's debug output.

### Hook didn't fire

Three common causes:

1. **Plugin disabled.** `claude plugin list` should show enabled.
2. **Cache stale.** Edited the hook source but CC is using the cached
   copy. Run `bin/install.sh --clean`.
3. **Matcher mismatch.** The `"matcher"` field in `plugin.json`'s hook
   declaration uses a regex against `tool_name`. Common matchers:
   `Edit|Write|MultiEdit|NotebookEdit`, `Bash`, `Task`. Typo
   silently skips the hook.

### Hook fires but is wrong

```sh
HEX_PATHLOCK_DEBUG=1 claude --debug
```

Then read `/tmp/hex-pathlock-debug.log`. If `resolved_agent` is wrong,
check `detect_agent`'s fallback list — CC might be using a different
payload field in your version.

## Adding a new hook

See [`extending.md`](extending.md). Short version:

1. Write `<plugin>/hooks/<name>.py` (make executable: `chmod +x`).
2. Register in `<plugin>/.claude-plugin/plugin.json` under `hooks.<event>`:

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Bash",
           "hooks": [
             { "type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py\"" }
           ]
         }
       ]
     }
   }
   ```

3. `bin/install.sh --clean` (refreshes cache).
4. Test in a fresh CC session in a host project.

## Memory of past gotchas

These are documented in `cc_plugin_quirks` memory and in
[`cc-quirks.md`](cc-quirks.md). Read those before adding a new hook —
the failure modes are predictable.
