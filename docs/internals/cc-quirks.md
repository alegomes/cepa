# Claude Code quirks (empirical)

The "wish I'd known this before building" list. Verified against CC
2.1.x while building this marketplace.

Mirror of the `cc_plugin_quirks` memory in
`~/.claude/projects/.../memory/`. The memory file is the live working
copy (frequently updated); this page is the published, version-
controlled snapshot.

## Marketplace + plugin.json

### `marketplace.json` source field

For local plugins, `source` must be a **bare string** (e.g.,
`"./multi-team"`). The object form `{ "type": "local", "path": "..." }`
is rejected by validation. That form is reserved for `git-subdir`
plugins, not local.

```json
{
  "plugins": [
    { "name": "common", "source": "./common" },      // ✓
    { "name": "common", "source": { "type": "local", "path": "./common" } }  // ✗ rejected
  ]
}
```

### `plugin.json` skill discovery

Skills require explicit declaration:

```json
{
  "skills": "./skills/"  // REQUIRED
}
```

Without it, skills won't load even if they're physically present in
the directory. Agents and commands auto-discover from `agents/` and
`commands/` — declaring `"agents": "./agents/"` or `"commands":
"./commands/"` causes validation failure.

Asymmetric. Annoying. Just declare skills explicitly and move on.

## Hooks

### Subagent identity in PreToolUse payloads

CC sends `agent_type: "<plugin>:<agent-name>"` in PreToolUse payloads
when a subagent is the caller. Strip the `<plugin>:` prefix to match
your `ALLOWED_WRITES` table.

Other field names (`agent_name`, `subagent_name`, `subagent_type`)
were used in pre-2.1 versions and are no longer populated. The
defensive fallback chain in `detect_agent` covers version drift.

### Built-in CC agents have no plugin prefix

CC's own agents (`statusline-setup`, `Explore`, `Plan`,
`general-purpose`, `code-reviewer`) arrive with bare `agent_type`
(no `<plugin>:` prefix). A path-lock that only handles "empty
agent_type = main session" and "prefix matches ours" will fail-close
on built-ins.

Fix: treat no-colon agent_type as foreign (same as foreign-prefix) —
exit 0 without consulting `ALLOWED_WRITES`.

```python
# CORRECT
if ":" in raw_agent_type:
    prefix = raw_agent_type.split(":", 1)[0]
    if prefix != PLUGIN_NAME:
        sys.exit(0)
else:
    # main session, foreign plugin, OR built-in CC agent — all
    # treated as "not ours; fail-open"
    sys.exit(0)
```

See [`path-lock.md`](path-lock.md) Bug 4.

### Multi-plugin PreToolUse hook collision

When multiple plugins each register a `PreToolUse` hook on the same
event + matcher, **all of them fire**, and the strictest verdict wins
(any exit 2 blocks the call). A subagent from plugin A can be blocked
by plugin B's hook even though A's own allowlist permits the write.

Fix: each hook must scope itself to its own plugin's agents via a
`PLUGIN_NAME` constant + prefix check (above). See [`path-lock.md`](
path-lock.md) Bug 1 for the empirical write-up.

### Tool allowlist as enforcement

A subagent's `tools:` frontmatter is the HARD guarantee — CC enforces
tool allowlists. A lead with no `Edit`/`Write`/`MultiEdit` in `tools:`
cannot write source code, no matter what its prompt says.

Prompt-only "leads delegate, don't execute" rules are NOT a hard
guarantee. Use them in combination with tool allowlists, never as a
substitute.

## Cache invalidation

`claude plugin uninstall` does NOT remove the marketplace cache at
`~/.claude/plugins/cache/<marketplace>/`. To force-pick-up edits
without a version bump:

```sh
rm -rf ~/.claude/plugins/cache/alegomes/
```

`bin/install.sh --clean` does this automatically (plus the explicit
uninstall/reinstall cycle). Required after editing plugin source
without a version bump.

## Subagent path sandboxing

Subagents resolve relative paths against the host project cwd, not the
plugin directory. Workaround used here: keep expertise files in
`common/expertise/` (plugin source) and expose them via a host-level
symlink at `.claude/expertise/` (created by `bin/install.sh`). Agents
reference the host-relative path; CC's path resolution finds the
symlinked file.

This is what makes accumulated agent learnings persist across
projects.

## Slash command namespacing

The bare command form (`/plan-build-validate`) returns
`Unknown command`. Use `/<plugin>:<command>`:

- `/multi-team:plan-build-validate`
- `/hex-backend:plan-build-validate`
- `/jira-flow:execute`
- `/common:autonomous-start`

CC has no convention for "default plugin"; the namespace is always
required.

## Worktree-isolated subagents lose the `Task` tool

When you invoke a subagent with `isolation: "worktree"` (via the
`Agent` tool), CC strips its ability to call `Task` to delegate
further. Leads that need to delegate (e.g., `engineering-lead`
invoking dev workers, `planning-lead` fanning out to planning workers)
cannot run worktreed.

Workaround used in this marketplace: leads run in main session; only
leaf workers (dev workers, qa, code-reviewer) can be worktreed.

Empirically reproduced twice on hex-backend Stories WEGO-1567 and
WEGO-1566 — both stalled at ARCHITECT phase before the workaround.
Documented in `hex-backend/commands/plan-build-validate.md`'s
"Worktree policy" section.

Worth re-verifying on CC version bumps — could be fixed upstream
eventually.

## CCR (remote routines) auto-disable on missing repo access

When a `/schedule` routine targets a GitHub repo and the user hasn't
connected GitHub via `/web-setup` (or installed the Claude GitHub App
on the repo), the routine fires once, fails to clone, and gets
`enabled: false` with `ended_reason: "auto_disabled_repo_access"`.

Re-arm via `RemoteTrigger update` with a new `run_once_at` and
`enabled: true` after running `/web-setup`. Don't just toggle
`enabled` without a new schedule — the previous timestamp may be in
the past.

## PostToolUse `tool_response` shape varies — defensive extraction required

PostToolUse hooks receive a `tool_response` field whose shape varies
across CC versions, MCP wrappers (like context-mode that redirects
Bash → ctx_execute), and tool types. A hook that reads only the most
common shape (`{"stdout": "..."}` or `{"content": [...]}`) silently
fails when CC sends a different envelope.

Symptom: the hook runs successfully (exit 0), but the state it should
update doesn't change. Reproduced in 2026-05-17: `mvnw verify`
returned BUILD SUCCESS but `capture-build-result.py` did not write
`SUCCESS` to `.claude/last-build.json` — the hook's `extract_text`
returned empty because the `tool_response` shape on that CC build
wasn't in the recognized list, and `classify()` couldn't find the
"BUILD SUCCESS" marker in an empty string.

Shapes the marketplace's `capture-build-result.py` now handles
(post-fix):

- Top-level `str` — raw text.
- Top-level `list` — content blocks.
- `dict` with any of: `stdout`, `output`, `result`, `content`, `text`,
  `data`, `message` — each may be str OR list-of-content-blocks.
- Nested envelope: `dict.output` itself a `dict` with `stdout` /
  `content` / `text` / `result` inside.
- Anthropic SDK envelope: `dict.tool_use_result.content`.
- Fallback: `dict.stderr` only.

Content-block lists are flattened with handling for `{type: text,
text: ...}` AND `{type: tool_result, content: ...}` (the latter may
itself nest a list).

Pattern lesson: when writing a PostToolUse hook that reads
`tool_response`, gate everything on a `CAPTURE_BUILD_DEBUG`-style env
var that dumps the actual payload shape to a file on every invocation.
You will hit shape drift; observability built in from day one beats
guessing later.

## MCP auth dropouts

The Atlassian (and other) MCP connectors lose authorization
periodically — typically after CC session restarts or extended idle
time. Symptom: MCP calls fail with "not authorized for X."

Fix:

```
/web-setup
```

Reconnects the connector. Then retry. If a CCR routine relies on the
connector, re-arming alone won't help — the routine needs the auth in
place before it fires.

## When CC version bumps

After upgrading Claude Code:

1. Re-run `bin/install.sh --clean` against your host project(s).
   Marketplace cache shape can change between versions.
2. Re-test path-lock with `HEX_PATHLOCK_DEBUG=1` — the `agent_type`
   payload field might have moved. Update `detect_agent`'s fallback
   list if so.
3. Re-test hook lifecycle (`PreToolUse`, `PostToolUse`,
   `UserPromptSubmit`) — names sometimes change.
4. Update memory: `~/.claude/projects/.../memory/cc_plugin_quirks.md`.
5. If you find a new quirk, add it both to the memory and to this
   page.

## Reading the memory

The live working copy of these quirks lives in:

```
~/.claude/projects/-Users-alegomes-Insync-alegomes-gmail-com-GoogleDrive-2026-coding-harnessing-claude-claude-multi-team-plugin/memory/cc_plugin_quirks.md
```

The memory file is updated more often than this docs page. When in
doubt, the memory wins (it has timestamps and references to specific
commits where each fix landed).

To keep them in sync: every time you discover a new quirk and add to
the memory, also append to this page. The memory is the working draft;
this page is the published snapshot.
