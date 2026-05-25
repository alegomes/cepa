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

## Role-based allowlists (hex-backend only)

`hex-backend`'s path-lock differs from the others in one important way:
the allowlist is built from a role → module mapping that the project
can override. The plugin is opinionated about the architectural
**invariants** of hexagonal architecture (framework-free domain, ACL at
adapters, dependencies pointing inward) but NOT about physical module
names. Different projects use different names; the plugin shouldn't
care, as long as the invariants hold.

### Default mapping (canonical layout)

When `hex-backend.yaml` is absent at the project root, the path-lock
uses these defaults:

```python
DEFAULT_ROLES = {
    "domain":      "domain",
    "application": "application",
    "api":         "api-rest",
    "adapter":     "infrastructure",
    "bootstrap":   "bootstrap",
}
```

### Override via `hex-backend.yaml` at project root

```yaml
schema_version: 1

roles:
  domain:       tenancy-core
  application:  tenancy-core      # roles may share a module
  api:          tenancy-api
  adapter:      tenancy-adapter
  bootstrap:    tenancy-app
```

The path-lock reads this on every invocation, merges with defaults
(absent keys fall back to canonical), and builds `ALLOWED_WRITES`
dynamically:

```python
"domain-dev":   sorted({"<domain-module>/src/main/**", "<application-module>/src/main/**"})
"api-dev":      sorted({"<api-module>/src/main/**"})
"adapter-dev":  sorted({"<adapter-module>/src/main/**", "<bootstrap-module>/src/main/**"})
"qa-engineer":  sorted({"<each-module>/src/test/**"})
```

Modules deduplicate via `set` — so if `domain` and `application` both
map to `tenancy-core`, `domain-dev`'s allowlist contains
`tenancy-core/src/main/**` once, not twice.

### YAML parser

The hook uses a minimal pure-stdlib YAML parser (no PyYAML
dependency) that handles the 2-level shape:

```python
def parse_minimal_yaml(text):
    # Returns {"schema_version": "1", "roles": {"domain": "tenancy-core", ...}}
```

Doesn't handle quoted multi-line strings, lists, or anchors. Fine for
the schema we own. If `hex-backend.yaml` exists but doesn't parse, the
hook logs a stderr warning and falls back to defaults (fail-safe, not
fail-closed — config bugs shouldn't deadlock the user).

### Error message includes layout context

When the hook blocks, the error message tells you which layout is
active:

```
[hex-backend path-lock] BLOCKED: agent 'domain-dev' cannot Edit ...
  Allowed write globs for 'domain-dev':
  - tenancy-core/src/main/**
  Plus its own expertise file: .claude/expertise/domain-dev-mental-model.yaml
  Active role → module mapping (from hex-backend.yaml):
    domain: tenancy-core
    application: tenancy-core
    api: tenancy-api
    adapter: tenancy-adapter
    bootstrap: tenancy-app
  (Edit hex-backend.yaml at project root to remap roles.)
```

So the diagnostic is one read away — no need to dig into the source
to understand why a path didn't match.

### When this matters

- Project follows canonical layout → no `hex-backend.yaml` needed.
- Project has different module names → seed `hex-backend.yaml`
  (`bin/install.sh --topology=hex-backend` does this; or copy
  `hex-backend/hex-backend.example.yaml` manually).
- Project shares modules across roles (e.g., domain + application in
  one module) → set both keys to the same value; the dedup handles
  the rest.
- **Single-module project** (no per-role module subdirectory; all
  sources directly under `src/main/`) → set every role to `.` (or
  empty string). The hook recognizes `.`/`""` as "no module prefix"
  and produces globs of the form `src/main/**` instead of
  `./src/main/**`. This matters because `fnmatch` doesn't normalize
  the `./` prefix — without the special-casing, the glob wouldn't
  match relativized paths like `src/main/java/.../X.java`.

### `extra_write_globs` — additive per-agent overrides

For paths that fall outside the canonical role-based allowlist but
that an agent legitimately needs to write — one-off migration
scripts, project-specific tooling dirs, integration test fixtures —
add an `extra_write_globs:` block:

```yaml
extra_write_globs:
  adapter-dev: scripts/fase0-concierge/**,scripts/other-migration/**
  qa-engineer: e2e-fixtures/**
```

Format accepts **two equivalent syntaxes** for the value:

- **Comma-separated string** (concise, no quoting):
  ```yaml
  extra_write_globs:
    adapter-dev: scripts/fase0-concierge/**,scripts/other-migration/**
  ```
- **Inline flow list** (readable when items have special chars):
  ```yaml
  extra_write_globs:
    adapter-dev: ["scripts/fase0-concierge/**", "scripts/other-migration/**"]
  ```

Both are parsed equivalently — the minimal YAML parser recognizes
`[a, b]` flow lists and treats the result identically to CSV. Multi-line
YAML lists (with `-` items on separate lines) are NOT supported; stick
to one of the inline forms above.

Each agent's extras are stripped and **appended** to the canonical
allowlist computed from `roles:`.

Semantics:

- **Additive, not replacing.** `adapter-dev` keeps its canonical
  `infrastructure/src/main/**` + `bootstrap/src/main/**` AND gains
  `scripts/fase0-concierge/**`. Extras are deduped against existing
  entries.
- **Per-agent.** Different agents have different extras; no cross-
  agent sharing.
- **Order doesn't matter for matching** (`path_matches` checks each
  glob independently and short-circuits on first match).
- **Empty / absent block** → no extras. Allowlist is purely
  role-based.

When to use:

- **Yes:** a Story needs `adapter-dev` to drop a Flyway/Liquibase
  migration script into `scripts/migrations/` for a one-shot DB op.
- **Yes:** a project has integration test fixtures under
  `e2e-fixtures/` that `qa-engineer` legitimately owns.
- **No:** the project's domain code lives in `tenancy-core/` instead
  of `domain/`. That's a `roles:` remap, not an extras append.
- **No:** the project has many extras for one agent. That signals
  either the topology is wrong (consider `multi-team`) or the project
  layout fights the architecture. Don't paper it over with extras.

Error messages already list the merged allowlist (canonical + extras),
so when a write is blocked the user sees their extras among the
allowed globs and can diagnose whether the missing path needs to be
added.

The other topologies (`multi-team`, `discovery`, `book`) don't have
role-based mapping — their allowlists are direct globs. If a future
topology adopts the role pattern, mirror this design.

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
