#!/usr/bin/env python3
"""PreToolUse hook for the hex-backend topology.

Enforces per-agent write allowlists keyed to hexagonal-architecture
ROLES (domain / application / api / adapter / bootstrap), not to
specific module names. The mapping from role → physical module name
is per-project, read from `hex-backend.yaml` at project root.

The canonical mapping (used when no config file is present):

  role            module          src/main path
  ─────────────   ─────────────   ────────────────────────
  domain          domain          domain/src/main/**
  application     application     application/src/main/**
  api             api-rest        api-rest/src/main/**
  adapter         infrastructure  infrastructure/src/main/**
  bootstrap       bootstrap       bootstrap/src/main/**

Projects whose modules are named differently (e.g.,
`tenancy-core` instead of `domain`) override via
`hex-backend.yaml`:

  schema_version: 1
  roles:
    domain:       tenancy-core
    application:  tenancy-core    # roles may share a module
    api:          tenancy-api
    adapter:      tenancy-adapter
    bootstrap:    tenancy-app

The plugin is still opinionated about the architectural INVARIANTS
(domain is framework-free, dependencies point inward, ACL keeps
externals out of the core, etc.). It is no longer opinionated about
the directory layout that implements those invariants — that's
project convention.

Exit codes:
  0 — allowed
  2 — blocked (stderr message reaches the agent so it can self-correct)
"""

import fnmatch
import json
import os
import sys
from pathlib import Path

PLUGIN_NAME = "hex-backend"

# Canonical role → module mapping. Used when `hex-backend.yaml` is
# absent or doesn't override a role.
DEFAULT_ROLES = {
    "domain":      "domain",
    "application": "application",
    "api":         "api-rest",
    "adapter":     "infrastructure",
    "bootstrap":   "bootstrap",
}

GATED_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


# ─── role / module config ─────────────────────────────────────────────

def _parse_scalar_or_list(value: str):
    """Parse a YAML scalar value. Recognizes inline flow lists
    [a, b, c] (quoted or unquoted items) and returns them as a Python
    list. Plain scalars come back as a single string."""
    v = value.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        if not inner:
            return []
        items = [item.strip().strip('"').strip("'") for item in inner.split(",")]
        return [i for i in items if i]
    return v.strip('"').strip("'")


def parse_minimal_yaml(text: str) -> dict:
    """Parse a flat 2-level YAML for hex-backend.yaml. Pure stdlib;
    doesn't handle quoted multi-line strings, multi-line lists, or
    anchors. Inline flow lists like `[a, b, c]` ARE handled. Good
    enough for the schema we own.

    Recognized shape:
        schema_version: 1
        roles:
          domain: tenancy-core
          api: tenancy-api
        extra_write_globs:
          adapter-dev: scripts/foo/**,scripts/bar/**            # CSV string
          qa-engineer: ["e2e-fixtures/**", "tests-extra/**"]    # inline list
    """
    result: dict = {}
    current_section_key = None
    for line in text.splitlines():
        # Strip comments. Care: don't strip a `#` inside an inline list
        # (e.g., quoted string with `#`). Cheap heuristic: only strip
        # comments when the `#` is preceded by whitespace OR is at line
        # start. This is fine for the schemas we own.
        if "#" in line:
            for i, ch in enumerate(line):
                if ch == "#" and (i == 0 or line[i-1].isspace()):
                    line = line[:i]
                    break
        stripped = line.strip()
        if not stripped:
            continue

        if not line.startswith((" ", "\t")):
            # top-level key
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                result[key] = _parse_scalar_or_list(value)
                current_section_key = None
            else:
                result[key] = {}
                current_section_key = key
        else:
            # indented (assumed to be inside current_section_key)
            if current_section_key is None:
                continue
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            result[current_section_key][key.strip()] = _parse_scalar_or_list(value)
    return result


def load_config(project_root: Path) -> tuple:
    """Read hex-backend.yaml from project root.

    Returns (roles, extra_write_globs) where:
      - roles: dict mapping role names to module names
      - extra_write_globs: dict mapping agent names to list of additional glob patterns

    extra_write_globs section in hex-backend.yaml:
      extra_write_globs:
        adapter-dev: scripts/fase0-concierge/**,scripts/other/**

    Multiple globs per agent are comma-separated.

    Falls back to defaults silently on missing file; loudly on parse error.
    """
    config_path = project_root / "hex-backend.yaml"
    if not config_path.exists():
        return DEFAULT_ROLES.copy(), {}
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as e:
        print(
            f"[hex-backend path-lock] could not read {config_path}: {e}; "
            f"falling back to canonical layout.",
            file=sys.stderr,
        )
        return DEFAULT_ROLES.copy(), {}

    try:
        parsed = parse_minimal_yaml(text)
    except Exception as e:
        print(
            f"[hex-backend path-lock] could not parse {config_path}: {e}; "
            f"falling back to canonical layout.",
            file=sys.stderr,
        )
        return DEFAULT_ROLES.copy(), {}

    overrides = parsed.get("roles")
    if not isinstance(overrides, dict):
        overrides = {}

    roles = DEFAULT_ROLES.copy()
    for role, module in overrides.items():
        if role in DEFAULT_ROLES and isinstance(module, str) and module:
            roles[role] = module

    extra_write_globs: dict = {}
    extra_section = parsed.get("extra_write_globs")
    if isinstance(extra_section, dict):
        for agent_name, globs_value in extra_section.items():
            if isinstance(globs_value, list):
                globs = [g.strip() for g in globs_value if isinstance(g, str) and g.strip()]
            elif isinstance(globs_value, str) and globs_value:
                globs = [g.strip() for g in globs_value.split(",") if g.strip()]
            else:
                globs = []
            if globs:
                extra_write_globs[agent_name] = globs

    return roles, extra_write_globs


def load_roles(project_root: Path) -> dict:
    """Backward-compat wrapper. Returns only the roles dict."""
    roles, _ = load_config(project_root)
    return roles


def build_allowed_writes(roles: dict, extra_write_globs: dict = None) -> dict:
    """Construct the per-agent write allowlist from the role → module mapping.

    When two roles map to the same module (e.g., domain and application both
    map to `tenancy-core`), the resulting globs are deduplicated.

    Single-module projects use module value `.` (or empty string) to mean
    "no module prefix — sources live directly under project root". The
    resulting glob is `src/main/**` (NOT `./src/main/**` — fnmatch and the
    fallback path comparison don't normalize `./` prefixes).
    """
    def _prefix(module_name: str) -> str:
        m = (module_name or "").strip()
        # Single-module projects: "." or "" means "no module-level prefix";
        # sources are at project root.
        if m in ("", "."):
            return ""
        return m.rstrip("/") + "/"

    def main_globs(*role_keys):
        modules = {roles[r] for r in role_keys}
        return sorted({f"{_prefix(m)}src/main/**" for m in modules})

    def test_globs(*role_keys):
        modules = {roles[r] for r in role_keys}
        return sorted({f"{_prefix(m)}src/test/**" for m in modules})

    result = {
        # Orchestrator + leads — no source writes; only own expertise file.
        "orchestrator":      [],
        "planning-lead":     ["spec/**", "specs/**", "docs/**"],
        "engineering-lead":  ["docs/tasks/**", "docs/investigations/**",
                              "pom.xml", "**/pom.xml"],
        "validation-lead":   [],

        # Planning workers — write specs and decomposition artifacts.
        "epic-author":         ["spec/**", "specs/**", "docs/**"],
        "product-manager":     ["spec/**", "specs/**", "docs/**"],
        "integration-analyst": ["spec/**", "specs/**", "docs/**"],

        # Engineering workers — role-aware writes, mapped via hex-backend.yaml.
        "domain-dev":          main_globs("domain", "application"),
        "api-dev":             main_globs("api"),
        "adapter-dev":         main_globs("adapter", "bootstrap"),

        # Validation workers.
        "qa-engineer":         test_globs("domain", "application", "api",
                                          "adapter", "bootstrap"),
        "refactor-advisor":    ["docs/housekeeping/**"],
        "security-reviewer":   ["docs/security-reviews/**"],
        "code-reviewer":       [],  # advisory only, no writes
    }
    if extra_write_globs:
        for agent_name, globs in extra_write_globs.items():
            existing = result.get(agent_name, [])
            result[agent_name] = existing + [g for g in globs if g not in existing]
    return result


# ─── agent detection (unchanged) ──────────────────────────────────────

def detect_agent(payload: dict) -> str:
    """Figure out which agent triggered this tool call.

    CC sends `agent_type` in PreToolUse payloads when a subagent is the caller.
    Plugin-namespaced as `<plugin>:<agent>`; we strip the prefix.
    """
    agent_type = payload.get("agent_type", "")
    if agent_type:
        return agent_type.split(":", 1)[1] if ":" in agent_type else agent_type
    for key in ("agent_name", "subagent_name", "agent", "subagent_type"):
        if key in payload and payload[key]:
            return payload[key]
    for env_key in ("CLAUDE_AGENT_NAME", "CLAUDE_SUBAGENT_NAME"):
        v = os.environ.get(env_key)
        if v:
            return v
    return "orchestrator"


def debug_log(payload: dict, resolved_agent: str, roles: dict) -> None:
    """When HEX_PATHLOCK_DEBUG=1, append a JSON line to the debug log so we can
    see what CC actually sends in the PreToolUse payload AND what role mapping
    is active. Default log path is /tmp/hex-pathlock-debug.log; override with
    HEX_PATHLOCK_DEBUG_LOG."""
    if os.environ.get("HEX_PATHLOCK_DEBUG") != "1":
        return
    log_path = os.environ.get("HEX_PATHLOCK_DEBUG_LOG", "/tmp/hex-pathlock-debug.log")
    identity_keys = ("agent_type", "agent_name", "subagent_name", "agent", "subagent_type")
    snapshot = {
        "top_level_keys": sorted(payload.keys()),
        "identity_fields": {k: payload.get(k) for k in identity_keys},
        "env_agent_vars": {
            k: os.environ.get(k)
            for k in ("CLAUDE_AGENT_NAME", "CLAUDE_SUBAGENT_NAME")
            if os.environ.get(k)
        },
        "resolved_agent": resolved_agent,
        "tool_name": payload.get("tool_name"),
        "file_path": (payload.get("tool_input") or {}).get("file_path"),
        "roles_in_use": roles,
    }
    try:
        with open(log_path, "a") as f:
            f.write(json.dumps(snapshot) + "\n")
    except OSError:
        pass


def is_own_expertise_file(file_path: str, agent: str) -> bool:
    """Each agent can write its own `<agent>-mental-model.yaml` regardless of
    where it lives on disk (host symlink to plugin source, or plugin cache)."""
    p = Path(file_path)
    return (
        p.name == f"{agent}-mental-model.yaml"
        and p.parent.name == "expertise"
    )


def path_matches(file_path: str, globs: list, project_root: Path) -> bool:
    try:
        rel = str(Path(file_path).resolve().relative_to(project_root))
    except ValueError:
        return False
    rel_posix = rel.replace(os.sep, "/")
    for g in globs:
        if fnmatch.fnmatchcase(rel_posix, g):
            return True
        if g.endswith("/**") and (rel_posix == g[:-3] or rel_posix.startswith(g[:-2])):
            return True
    return False


# ─── main ─────────────────────────────────────────────────────────────

def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(f"[hex-backend path-lock] could not parse hook payload; allowing", file=sys.stderr)
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    if tool_name not in GATED_TOOLS:
        sys.exit(0)

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    if not file_path:
        sys.exit(0)

    raw_agent_type = payload.get("agent_type", "") or ""
    if ":" in raw_agent_type:
        prefix = raw_agent_type.split(":", 1)[0]
        if prefix != PLUGIN_NAME:
            sys.exit(0)
    else:
        # No prefix at all — either main session (empty agent_type) or a
        # built-in CC agent (statusline-setup, Explore, Plan, general-purpose,
        # etc.). Neither is from our plugin; not our concern. Fail-open.
        sys.exit(0)

    project_root = Path(payload.get("cwd") or os.getcwd()).resolve()
    roles, extra_write_globs = load_config(project_root)
    allowed_writes = build_allowed_writes(roles, extra_write_globs)

    agent = detect_agent(payload)
    debug_log(payload, agent, roles)

    if is_own_expertise_file(file_path, agent):
        sys.exit(0)

    allowed = allowed_writes.get(agent)

    if allowed is None:
        print(
            f"[hex-backend path-lock] BLOCKED: unknown agent {agent!r} attempted "
            f"{tool_name} on {file_path}. Add {agent!r} to "
            f"hex-backend/hooks/path-lock.py if this is intentional.",
            file=sys.stderr,
        )
        sys.exit(2)

    if path_matches(file_path, allowed, project_root):
        sys.exit(0)

    # Build a layout-aware error message so the user can see why the path didn't match.
    non_default = [r for r, m in roles.items() if m != DEFAULT_ROLES[r]]
    layout_note = ""
    if non_default:
        layout_note = (
            f"\n  Active role → module mapping (from hex-backend.yaml):\n    "
            + "\n    ".join(f"{r}: {roles[r]}" for r in DEFAULT_ROLES.keys())
            + "\n  (Edit hex-backend.yaml at project root to remap roles.)"
        )
    else:
        layout_note = (
            f"\n  Using canonical layout (domain/application/api-rest/"
            f"infrastructure/bootstrap). If this project uses different "
            f"module names, create hex-backend.yaml at project root with "
            f"a `roles:` block."
        )

    print(
        f"[hex-backend path-lock] BLOCKED: agent {agent!r} cannot {tool_name} {file_path}.\n"
        f"  Allowed write globs for {agent!r}:\n  - "
        + "\n  - ".join(allowed or ["(none — only own expertise file)"])
        + f"\n  Plus its own expertise file: .claude/expertise/{agent}-mental-model.yaml"
        + layout_note +
        f"\n  Delegate to the appropriate worker instead.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
