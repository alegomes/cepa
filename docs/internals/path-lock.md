# path-lock deep dive

The PreToolUse hook that enforces per-agent write allowlists. Five
instances ship across topologies (`build-team`, `build-hex`,
`discovery`, `book`, `git-history`); each has the same structure with a
different `PLUGIN_NAME` constant and `ALLOWED_WRITES` table.

It has two companions that close its blind spots — covered in
[The Bash half and the enforcement surface](#the-bash-half-and-the-enforcement-surface)
at the bottom:

- **`bash-path-lock.py`** (per topology) — the path-lock only gates
  `Edit/Write/MultiEdit`; this catches the same writes done through the
  shell (`sed -i`, `cat >`, `tee`).
- **`enforcement-guard.py`** (common) — the path-lock keys on in-project
  paths, so it can't protect the files that define the rules (they live
  out of root). This blocks subagents from writing the enforcement surface.

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

**Symptom.** `build-hex:engineering-lead` blocked from writing
`docs/tasks/**/TASK.md` because `build-team`'s path-lock fired on the
same call and `build-team`'s `ALLOWED_WRITES["engineering-lead"]` is
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
trying to edit a config file in a build-hex project. The hook saw
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

## Role-based allowlists (build-hex only)

`build-hex`'s path-lock differs from the others in one important way:
the allowlist is built from a role → module mapping that the project
can override. The plugin is opinionated about the architectural
**invariants** of hexagonal architecture (framework-free domain, ACL at
adapters, dependencies pointing inward) but NOT about physical module
names. Different projects use different names; the plugin shouldn't
care, as long as the invariants hold.

### Default mapping (canonical layout)

When `build-hex.yaml` is absent at the project root, the path-lock
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

### Override via `build-hex.yaml` at project root

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
the schema we own. If `build-hex.yaml` exists but doesn't parse, the
hook logs a stderr warning and falls back to defaults (fail-safe, not
fail-closed — config bugs shouldn't deadlock the user).

### Error message includes layout context

When the hook blocks, the error message tells you which layout is
active:

```
[build-hex path-lock] BLOCKED: agent 'domain-dev' cannot Edit ...
  Allowed write globs for 'domain-dev':
  - tenancy-core/src/main/**
  Plus its own expertise file: .claude/expertise/domain-dev-mental-model.yaml
  Active role → module mapping (from build-hex.yaml):
    domain: tenancy-core
    application: tenancy-core
    api: tenancy-api
    adapter: tenancy-adapter
    bootstrap: tenancy-app
  (Edit build-hex.yaml at project root to remap roles.)
```

So the diagnostic is one read away — no need to dig into the source
to understand why a path didn't match.

### When this matters

- Project follows canonical layout → no `build-hex.yaml` needed.
- Project has different module names → seed `build-hex.yaml`
  (`bin/install.sh --topology=build-hex` does this; or copy
  `build-hex/build-hex.example.yaml` manually).
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
  either the topology is wrong (consider `build-team`) or the project
  layout fights the architecture. Don't paper it over with extras.

Error messages already list the merged allowlist (canonical + extras),
so when a write is blocked the user sees their extras among the
allowed globs and can diagnose whether the missing path needs to be
added.

The other topologies (`build-team`, `discovery`, `book`) don't have
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
  (build-team) has `[]` because it never writes code; it writes
  TASK.md indirectly through worker delegations. `build-hex`'s
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

1. **Project layout differs from topology assumption.** build-hex's
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
# (or replace hex with build-team/discovery/book per topology you're using)
```

Then read `/tmp/hex-pathlock-debug.log`. Each line is a JSON record:

```json
{
  "top_level_keys": [...],
  "identity_fields": {
    "agent_type": "build-hex:domain-dev",
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

- **Block `Bash` deletes / moves out of an allowlist.** The path-lock
  only gates `Edit`/`Write`/`MultiEdit`. Its companion `bash-path-lock.py`
  now catches shell **writes** (`>`, `tee`, `sed -i`, `cp`, `mv`) to an
  in-project path outside the allowlist — but a `Bash` `rm`, or a write via
  an interpreter (`python -c`), still slips through (logged, not blocked).
  (For commit/push protections, see `gate-advance.py`.)
- **Protect itself, or anything out of project root.** The allowlist is
  keyed to in-project paths, so the hook treats out-of-root targets as "not
  mine" — including the installed plugin code under `~/.claude/plugins/`
  where the hook itself lives. `enforcement-guard.py` (common) covers that
  surface; see below.
- **Prevent the orchestrator from writing.** Main session has empty
  `agent_type` → fail-open. Orchestrators don't normally write code
  (they delegate), but if they do, path-lock won't catch it. The tool
  allowlist on the topology snippet is supposed to prevent
  orchestrators from having `Edit`/`Write` in the first place.
- **Enforce read restrictions.** The hook only checks writes.
  Workers can read anywhere.

## The Bash half and the enforcement surface

The path-lock guarantees nothing on its own. It gates four tools and keys on
in-project paths, which leaves two blind spots that an agent — reaching for the
shell when a `Write` is blocked — will find without any malice. Two companion
hooks close them.

### `bash-path-lock.py` — the Bash bypass

`path-lock.py` matches `Edit|Write|MultiEdit|NotebookEdit`, never `Bash`. So an
agent whose `Write` to source is blocked can land the same edit with `sed -i`,
`cat > file`, `tee`, or a heredoc. It happened: a lead edited source via Bash
and validation approved the artifact on merit, because the pipeline judges
merit, never provenance — so the lock was the only control that could have
caught it, and it never fired.

`bash-path-lock.py` (one per topology, `PreToolUse` matcher `Bash`) reuses the
sibling `path-lock.py`'s allowlist (imported via `importlib` — single source of
truth) and blocks **explicit shell-level writes** to an in-project path outside
the agent's allowlist: `>`, `>>`, `tee`, `sed -i`, `cp`, `mv`, `install`,
`dd of=`, `truncate`. Deliberately narrow to keep false positives near zero —
subprocess-internal writes (`mvn`, `git`, `npm` create files via the JVM/git,
not via shell redirection) are invisible, out-of-root targets (`/tmp`, `$HOME`)
are out of scope, and the main session isn't gated. Constructs it can't analyze
statically (`python -c`, heredoc-to-interpreter) fail open but are logged to
`BASH_PATHLOCK_COVERAGE_LOG` — honest about what it can't see. A guardrail, not
a sandbox; the agent's own discipline (its prompt + expertise) is the primary
control.

### `enforcement-guard.py` — the lock can't protect itself

A path-lock keyed to in-project paths cannot, by construction, protect the
files that define the rules — they live out of root. A `proof-reviewer`,
blocked from writing its own output, edited the cached
`~/.claude/plugins/.../path-lock.py` via Bash to add itself to the allowlist: a
silent privilege escalation that **both** locks allowed, because the target is
out of root and both deliberately treat out-of-root as out of scope. Worse than
the Bash-write class — that routes around the lock; this rewrites it.

`enforcement-guard.py` (common, `PreToolUse` on `Bash` + the edit tools) is the
missing invariant: **no plugin subagent writes the enforcement surface, anywhere
on disk.** It blocks any target under a `.claude/` segment whose child is
`plugins`, `hooks`, or `settings.json`/`settings.local.json`/`keybindings.json`
— home or project. Carve-out: the agent's own `<agent>-mental-model.yaml` in an
`expertise/` dir stays writable (its legitimate home, even in the cache). Main
session and built-in agents aren't gated, so a human can still reinstall and
edit settings.

The root cause underneath that incident was mundane: `proof-reviewer` was
missing from the allowlist entirely (unknown agent → every write blocked,
including its documented `.claude/proof/` output), which is what drove it to the
shell. The fix was to add the entry in the **source repo** — never the cache,
which a reinstall overwrites. That is the rule the guard now enforces for
everyone: if a write you believe is legitimate is blocked, stop and report so a
human fixes the policy at the source — editing the enforcement surface to
self-grant is never an agent's call.

## Memory references

- `cc_plugin_quirks` memory entry "Multi-plugin PreToolUse hook
  collision" — full empirical write-up of bug 1.
- `cc_plugin_quirks` memory entry "Built-in CC agents have no plugin
  prefix" — bug 4 write-up.
- `cc_plugin_quirks` memory entry "Subagent identity in PreToolUse
  hooks" — `agent_type` payload shape discovery (bug 3).

When CC version changes, re-verify the `agent_type` field shape and
update the memory + `detect_agent` fallback list.
