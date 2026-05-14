# path-lock deep dive

The PreToolUse hook that enforces per-agent write allowlists. Four
instances ship across topologies (`multi-team`, `hex-backend`,
`discovery`, `book`); each has the same structure with a different
`PLUGIN_NAME` constant and `ALLOWED_WRITES` table.

This page covers the design history (every bug we hit and fixed), the
current logic flow, and how to debug when something blocks
unexpectedly.

## Why the hook exists

Workers' system prompts say things like "you write to `domain/src/main/**`".
But the prompt is soft — a confused agent will write wherever it wants
and hope the tool succeeds. The path-lock hook is the hard guarantee:
the file write actually fails with exit code 2 and the agent receives
a clear stderr message explaining why.

The combination — soft prompt for human-readable intent + hard hook for
deterministic enforcement — keeps every worker domain-locked even when
its prompt drifts.

## Logic flow (current, post all bugfixes)

```python
def main():
    payload = json.loads(sys.stdin.read())

    # Only gate Edit/Write/MultiEdit/NotebookEdit.
    if payload["tool_name"] not in GATED_TOOLS:
        sys.exit(0)

    file_path = payload["tool_input"].get("file_path", "")
    if not file_path:
        sys.exit(0)

    # Prefix scope: only enforce on agents from MY plugin.
    raw_agent_type = payload.get("agent_type", "") or ""
    if ":" in raw_agent_type:
        prefix = raw_agent_type.split(":", 1)[0]
        if prefix != PLUGIN_NAME:
            sys.exit(0)              # Foreign plugin's subagent.
    else:
        sys.exit(0)                  # Main session (empty) OR built-in CC agent (no colon).

    # Now we know the call is from our plugin. Resolve the agent name.
    agent = detect_agent(payload)    # Strips prefix; falls back to legacy keys.

    # Structural exemption: every agent can write its own expertise file.
    if is_own_expertise_file(file_path, agent):
        sys.exit(0)

    # Look up agent in allowlist.
    allowed = ALLOWED_WRITES.get(agent)
    if allowed is None:
        # Unknown agent within our plugin — fail closed. Likely a typo
        # in the agent's frontmatter or a forgotten allowlist entry.
        block(f"unknown agent {agent!r}")

    # Match the file path against allowed globs.
    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()
    if path_matches(file_path, allowed, project_root):
        sys.exit(0)

    block(f"agent {agent!r} cannot write {file_path}", allowed)
```

## The bugs we fixed

### Bug 1: Multi-plugin hook collision (fixed in commit `0284825`)

**Symptom.** `hex-backend:engineering-lead` blocked from writing
`docs/tasks/**/TASK.md` because `multi-team`'s path-lock fired on the
same call and `multi-team`'s `ALLOWED_WRITES["engineering-lead"]` is
`[]`.

**Cause.** CC fires every registered hook on a matching event. Without
prefix scoping, each path-lock treated foreign agents as
"unknown agent in my plugin" and blocked.

**Fix.** Added `PLUGIN_NAME` constant + prefix scope: each hook exits
0 when the call's `agent_type` belongs to a different plugin. The
strictest verdict no longer wins by default — each hook only enforces
on its own agents.

### Bug 2: Cache survives uninstall

**Symptom.** Edited path-lock.py source; CC still ran the old version.

**Cause.** `claude plugin uninstall` doesn't remove
`~/.claude/plugins/cache/<marketplace>/`. Without a version bump, CC
re-reads from the cache.

**Fix.** `bin/install.sh --clean` removes the cache directory before
reinstalling. The user must remember to use it after edits.

### Bug 3: Stale debug + agent identity surprise

**Symptom.** Hook saw `agent_type` as empty for an actual subagent call.

**Cause.** Early CC versions used different payload fields
(`agent_name`, `subagent_name`, etc.) before settling on `agent_type`.

**Fix.** `detect_agent` has a fallback chain:

```python
def detect_agent(payload):
    if payload.get("agent_type"):
        return payload["agent_type"].split(":", 1)[-1]  # strip prefix
    for key in ("agent_name", "subagent_name", "agent", "subagent_type"):
        if payload.get(key):
            return payload[key]
    for env_key in ("CLAUDE_AGENT_NAME", "CLAUDE_SUBAGENT_NAME"):
        if os.environ.get(env_key):
            return os.environ[env_key]
    return "orchestrator"
```

If CC moves the field again, add the new key to the fallback list.

### Bug 4: Built-in CC agents blocked unfairly (fixed in commit `7c9d597`)

**Symptom.** `statusline-setup` (a CC built-in agent) was BLOCKED
trying to edit a config file in a hex-backend project. The hook saw
`agent_type: "statusline-setup"` (no colon, no plugin prefix), fell
through to `ALLOWED_WRITES.get("statusline-setup")` → `None`, and
refused.

**Cause.** The prefix-scope logic only treated two cases — "has colon
AND matches our prefix" (check table) and "empty" (main session). The
third case — "set, but no colon at all" — fell through to the
allowlist lookup.

**Fix.** Convert `elif not raw_agent_type` to `else` — any
`agent_type` that doesn't start with our `PLUGIN_NAME:` exits 0. This
covers main session, foreign plugins, AND built-in CC agents (who
arrive bare-named without a plugin namespace).

```python
# Before
elif not raw_agent_type:
    sys.exit(0)  # only main session

# After
else:
    # No colon → main session, foreign plugin, OR built-in CC agent.
    # Either way, not ours; fail-open.
    sys.exit(0)
```

## The structural-exemption rule

Every agent can write its own `<agent>-mental-model.yaml` regardless
of where it lives on disk:

```python
def is_own_expertise_file(file_path, agent):
    p = Path(file_path)
    return (
        p.name == f"{agent}-mental-model.yaml"
        and p.parent.name == "expertise"
    )
```

This bypasses the allowlist check. Why structural rather than path-glob:

- Expertise files live in `common/expertise/` in the plugin source,
  but the host project sees them via `.claude/expertise/` symlink.
- Both paths must work without per-path-allowlist maintenance.
- The agent's own filename is identifying; structurally checking is
  more robust than maintaining glob patterns that vary by install
  layout.

## Allowlist conventions

- **Source paths use forward slashes**, even on Windows. `fnmatch` is
  POSIX-style; the hook normalizes `os.sep` to `/` before matching.
- **`**` is supported by fallback expansion**, not by `fnmatch` natively.
  `path-lock.py`'s `path_matches` adds a second check:
  `g.endswith("/**") and (rel == g[:-3] or rel.startswith(g[:-2]))`.
  Effectively: `domain/src/main/**` matches `domain/src/main` AND
  `domain/src/main/foo/bar.java`.
- **Allowlist entries are project-relative.** The hook resolves
  `file_path` against `payload["cwd"]` and refuses paths that fall
  outside the project root.
- **Empty allowlist means delegate-only.** `engineering-lead`
  (multi-team) has `[]` because it never writes code; it writes
  TASK.md indirectly through worker delegations. `hex-backend`'s
  `engineering-lead` has writes for `docs/tasks/**` etc. since the
  hex topology needs the lead to write decomposition artifacts.

## Debugging in production

### Symptom: "BLOCKED: unknown agent X"

Either:

1. **Typo in agent frontmatter.** Check `agents/<name>.md` — the
   `name:` field must match the lookup key.
2. **Forgot to register.** Added a new agent without adding to
   `ALLOWED_WRITES`. Add it; `bin/install.sh --clean`.
3. **Built-in CC agent** trying to write. After commit `7c9d597`,
   built-ins should exit 0 — if you're still seeing this on a built-in,
   the plugin is stale; reinstall.

### Symptom: "BLOCKED: agent X cannot write Y"

The agent is the right one, the file path is wrong. Either:

1. **Project layout differs from topology assumption.** hex-backend's
   allowlist assumes Maven `<module>/src/main/**`. If your project
   uses `<module>/main/src/` or whatever, override locally (see
   [`extending.md`](extending.md)#per-project-overrides) or widen the
   allowlist centrally + `bin/install.sh --clean`.
2. **Agent is writing the wrong file.** Maybe the right answer is to
   delegate; check the agent's spec to see whose lane this should be.

### Symptom: "Hook didn't fire"

See [`hooks.md`](hooks.md)#hook-didnt-fire.

### Symptom: "Hook fires but blocks for no reason"

```sh
export HEX_PATHLOCK_DEBUG=1
# (or replace hex with multi-team/discovery/book per topology you're using)
```

Then read `/tmp/hex-pathlock-debug.log`. Each line is a JSON record:

```json
{
  "top_level_keys": [...],
  "identity_fields": {
    "agent_type": "hex-backend:domain-dev",
    "agent_name": null,
    "subagent_name": null,
    "agent": null,
    "subagent_type": null
  },
  "env_agent_vars": {},
  "resolved_agent": "domain-dev",
  "tool_name": "Edit",
  "file_path": "/path/to/file.java"
}
```

If `resolved_agent` is wrong, the hook's `detect_agent` fallback chain
needs updating.

## What the path-lock can't do

- **Block delete operations** outside `Edit`/`Write`/`MultiEdit`. The
  hook only gates these tools. A `Bash` `rm` command bypasses it.
  (For commit/push protections, see `gate-advance.py`.)
- **Prevent the orchestrator from writing.** Main session has empty
  `agent_type` → fail-open. Orchestrators don't normally write code
  (they delegate), but if they do, path-lock won't catch it. The tool
  allowlist on the topology snippet is supposed to prevent
  orchestrators from having `Edit`/`Write` in the first place.
- **Enforce read restrictions.** The hook only checks writes.
  Workers can read anywhere.

## Memory references

- `cc_plugin_quirks` memory entry "Multi-plugin PreToolUse hook
  collision" — full empirical write-up of bug 1.
- `cc_plugin_quirks` memory entry "Built-in CC agents have no plugin
  prefix" — bug 4 write-up.
- `cc_plugin_quirks` memory entry "Subagent identity in PreToolUse
  hooks" — `agent_type` payload shape discovery (bug 3).

When CC version changes, re-verify the `agent_type` field shape and
update the memory + `detect_agent` fallback list.
