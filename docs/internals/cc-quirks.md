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
`"./build-team"`). The object form `{ "type": "local", "path": "..." }`
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
rm -rf ~/.claude/plugins/cache/cepa/
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

- `/build-team:plan-build-validate`
- `/build-hex:plan-build-validate`
- `/board-flow:execute`
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

Empirically reproduced twice on build-hex Stories WEGO-1567 and
WEGO-1566 — both stalled at ARCHITECT phase before the workaround.
Documented in `build-hex/commands/plan-build-validate.md`'s
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

## Launcher scripts vs. plugin cache

`ccw`-style launchers (`bin/` scripts symlinked onto `PATH`) are LIVE
immediately on commit, no `--clean`, no reinstall. Unlike plugin
commands/hooks/skills, which are read from
`~/.claude/plugins/cache/cepa/`, a `PATH` symlink resolves straight to
the repo file. If the launcher and the repo share the same `.git` (e.g.
a second path onto the same working tree), a merge to `main` changes
what the live symlink executes on its very next invocation. Rule of
thumb when shipping a launcher change vs. a command/hook change:
launcher = live now; anything routed through the plugin cache = needs
`bin/install.sh --clean` + a fresh session.

## Warp doesn't honor zsh completion functions

A `#compdef` completion function (e.g. a custom `_ccw` for a `ccw`
launcher) works via TAB in Terminal.app, iTerm2, VS Code's terminal, and
tmux, but not in Warp: Warp uses its own Fig-style completion-spec
engine and has an open feature request for honoring shell completions.
If a CLI affordance must work IN Warp, don't rely on zsh completion;
build something terminal-agnostic instead (e.g. an explicit `-s` flag
with no argument that opens an fzf/numbered picker).

## A hook can't spawn once its session's cwd is deleted

Symptom: `Stop hook error: … ENOENT … posix_spawn '/bin/sh'`. CC
launches every hook command via `/bin/sh -c "<cmd>"` with `cwd` set to
the session's launch directory. If that directory no longer exists, the
spawn fails naming `/bin/sh` (the shell CC tried to launch), not the
missing directory, which is misleading since `/bin/sh` obviously exists. A
slash command must never delete the cwd of the live session running it;
defer any self-directed worktree removal to `SessionEnd` (or an
auto-clean sweep) instead of doing it inline before the turn ends.

## MCP servers in `.claude/settings.json` are silently ignored

An `mcpServers` block declared inside `.claude/settings.json` is NOT
read; MCP servers only load from `.mcp.json` (or `--mcp-config` on the
CLI). A headless child launched with
`--permission-prompt-tool mcp__<server>__<tool>` and no matching
`.mcp.json` next to it aborts at startup with `Error: MCP tool … not
found`; the tell is that the error's "available tools" list only shows
user-scope servers, meaning the project server never loaded (not that
it crashed). Fix: emit an explicit `.mcp.json` and spawn with
`--mcp-config .mcp.json --strict-mcp-config`.

Related, same settings file: a permission rule only matches as
`Edit(path)`, never `Write(path)`. `Edit(path)` already covers every
file-editing tool including `Write`, so generating both is pure noise.
Bare tool names (e.g. `"Write"` in an `ask` catch-all) are fine; it's
only the `(path)`-scoped form that's Edit-only.

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
~/.claude/projects/-Users-alegomes-Insync-alegomes-gmail-com-GoogleDrive-2026-coding-cepa/memory/cc_plugin_quirks.md
```

The memory file is updated more often than this docs page. When in
doubt, the memory wins (it has timestamps and references to specific
commits where each fix landed).

To keep them in sync: every time you discover a new quirk and add to
the memory, also append to this page. The memory is the working draft;
this page is the published snapshot.
