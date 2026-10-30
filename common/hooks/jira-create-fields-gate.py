#!/usr/bin/env python3
"""PreToolUse (common): a new Jira card is born with the `required_fields` of board-flow.yaml.

## Why it exists

Each WeGo repo's `board-flow.yaml` declares, in `required_fields`, the fields
every card of the project must have (Team and system Module). Jira does NOT
refuse a card without them: the creation goes through, and the card vanishes
from the boards filtered by Team. The only thing guaranteeing they were filled
in was a sentence in `atlassian-expert.md` ("Read project config first, every
time").

It was not enough. On 14/09 and 22/09/2026 atlassian-expert itself created 35
cards (WEGO-2273 to 2278, WEGO-2302 to 2330) without the two fields: the request
it received did not mention the fields, said "don't invent a custom field", and
it never opened board-flow.yaml. The owner filled in the 35 by hand afterwards.
On 17/09 the same agent created with the fields. A rule that depends on the
agent remembering fails now and then.

This hook takes the decision away from the agent: every card creation is checked
against the file, whatever the path.

## What it checks

Creation paths covered:
- `twg jira workitem create` (Bash): reads `--field id=value`, `--fields-json`
  and `--variables-json`.
- MCP from any server (`createJiraIssue`, `jira_create_issue`,
  `jira_batch_create_issues`): looks for the fields at any level of the input
  (`additional_fields`, `fields`, or loose), including JSON inside a string.
- `twg api -X POST .../rest/api/N/issue` (raw REST): always blocked when there
  are `required_fields`, because the body may be in a file the hook does not
  read.

For each `required_fields` entry (by `id` or by `name`), the passed value must
match the file's `value`. A raw UUID and `{"id": "..."}` count as the same
value.

`required_fields` follows the same resolution as atlassian-expert:
`topologies.<active>.required_fields` replaces `defaults.required_fields`, with
the active topology coming from `.claude/topology`, then `default_topology`.

## What passes

- A repo without board-flow.yaml, or with empty `required_fields`.
- A card from another project (the project key in the call differs from the
  file's): this file's rules do not hold there.
- Any call that does not create a card.

It applies to the main session too: the owner's request is that EVERY card be
born according to the file, in any mode.
"""

import json
import os
import re
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _shellscan as S  # noqa: E402

_CONFIG_NAMES = ("board-flow.yaml", ".claude/board-flow.lifecycle.yaml")
_MCP_CREATE = re.compile(r"(createJiraIssue|jira_create_issue|jira_batch_create_issues)$")
_REST_CREATE = re.compile(r"/rest/api/\d+/issue(/bulk)?/?$")
_WRITE_METHODS = {"POST", "PUT", "PATCH"}


# ---------------------------------------------------------------- config

def _find_config(cwd):
    """Climbs from cwd until it finds board-flow.yaml, stopping at the git root."""
    d = os.path.abspath(cwd or ".")
    while True:
        for name in _CONFIG_NAMES:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return d, p
        if os.path.exists(os.path.join(d, ".git")):
            return None, None
        parent = os.path.dirname(d)
        if parent == d:
            return None, None
        d = parent


def _load_rules(cwd):
    """(project_key, required_fields, config_path) or None when there is no rule.

    Raises RuntimeError when the file exists but cannot be read: in that case
    the gate blocks, because allowing would repeat the hole it exists to close.
    """
    root, path = _find_config(cwd)
    if not path:
        return None
    try:
        import yaml
    except ImportError:
        raise RuntimeError("o módulo pyyaml não está instalado no python3 dos hooks "
                           "(instale com `python3 -m pip install pyyaml`)")
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"{path} não é YAML válido: {e}")

    defaults = data.get("defaults") or {}
    topology = None
    marker = os.path.join(root, ".claude", "topology")
    if os.path.isfile(marker):
        try:
            topology = open(marker, encoding="utf-8").read().strip() or None
        except OSError:
            topology = None
    topology = topology or defaults.get("default_topology") or data.get("default_topology")
    override = ((data.get("topologies") or {}).get(topology) or {}) if topology else {}

    fields = override.get("required_fields", defaults.get("required_fields")) or []
    project = override.get("project_key") or defaults.get("project_key")
    fields = [f for f in fields if isinstance(f, dict) and f.get("id")]
    if not fields:
        return None
    return project, fields, path


# ---------------------------------------------------------------- values

def _parse_json(v):
    if isinstance(v, str):
        s = v.strip()
        if s[:1] in ("{", "[", '"'):
            try:
                return json.loads(s)
            except ValueError:
                return v
    return v


def _norm(v):
    """Comparable form of a field value: raw UUID == {"id": UUID}."""
    v = _parse_json(v)
    if isinstance(v, dict):
        for k in ("id", "value", "accountId", "key", "name"):
            if v.get(k) not in (None, ""):
                return str(v[k]).strip()
        return json.dumps(v, sort_keys=True)
    if isinstance(v, list):
        return sorted(_norm(x) for x in v)
    return str(v).strip() if v is not None else ""


def _collect(obj, out):
    """Gathers into `out` every key->value pair, at any level, opening JSON in strings."""
    obj = _parse_json(obj)
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.setdefault(str(k).casefold(), v)
            _collect(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _collect(x, out)


def _project_of(found):
    for k in ("project_key", "projectkey", "space"):
        if k in found and isinstance(found[k], str):
            return found[k]
    proj = found.get("project")
    if isinstance(proj, dict):
        return proj.get("key")
    if isinstance(proj, str):
        return proj
    return None


def _missing(found, fields):
    """List of (field, got|None) that do not match."""
    bad = []
    for f in fields:
        keys = [str(f["id"]).casefold()]
        if f.get("name"):
            keys.append(str(f["name"]).casefold())
        got = next((found[k] for k in keys if k in found), None)
        if got is None or _norm(got) != _norm(f.get("value")):
            bad.append((f, got))
    return bad


# ---------------------------------------------------------------- paths

def _twg_creates(command):
    """Each creation readable through `twg`, as a dict of found fields, or "opaque"."""
    out = []
    for seg in S._split_segments(command):
        seg = seg.strip()
        if not seg or "twg" not in seg:
            continue
        try:
            argv = shlex.split(seg)
        except ValueError:
            if re.search(r"(^|/)twg\b", seg) and "create" in seg:
                out.append("opaque")
            continue
        while argv and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
            argv.pop(0)
        if not argv or os.path.basename(argv[0]) != "twg":
            continue
        rest = argv[1:]
        if "--help" in rest or "-h" in rest:
            continue
        if rest[:1] == ["api"]:
            method = "GET"
            for i, t in enumerate(rest):
                if t in ("-X", "--method") and i + 1 < len(rest):
                    method = rest[i + 1].upper()
                elif t.startswith("--method="):
                    method = t.split("=", 1)[1].upper()
            target = next((t for t in rest[1:] if not t.startswith("-")), "")
            if method in _WRITE_METHODS and "jira" in target and _REST_CREATE.search(target.split("?")[0]):
                out.append("opaque")
            continue
        words = [a for a in rest if not a.startswith("-")]
        if words[:3] != ["jira", "workitem", "create"]:
            continue
        found = {}
        for i, t in enumerate(rest):
            val = None
            if t in ("--field", "--fields-json", "--variables-json", "--space") and i + 1 < len(rest):
                val = rest[i + 1]
            elif "=" in t and t.split("=", 1)[0] in ("--field", "--fields-json", "--variables-json", "--space"):
                t, val = t.split("=", 1)
            if val is None:
                continue
            if t == "--field" and "=" in val:
                k, v = val.split("=", 1)
                found.setdefault(k.strip().casefold(), v)
            elif t == "--space":
                found.setdefault("space", val)
            elif t in ("--fields-json", "--variables-json"):
                _collect(val, found)
        out.append(found)
    return out


def _mcp_creates(tool_name, tool_input):
    if tool_name.endswith("jira_batch_create_issues"):
        issues = _parse_json((tool_input or {}).get("issues"))
        if isinstance(issues, list):
            res = []
            for it in issues:
                found = {}
                _collect(it, found)
                res.append(found)
            return res
    found = {}
    _collect(tool_input or {}, found)
    return [found]


# ---------------------------------------------------------------- main

def _example(fields, mechanism):
    if mechanism == "twg":
        return " ".join(
            f"--field '{f['id']}={json.dumps(f.get('value'), ensure_ascii=False)}'" for f in fields
        )
    return "additional_fields: " + json.dumps(
        {f["id"]: f.get("value") for f in fields}, ensure_ascii=False
    )


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    tool = payload.get("tool_name", "") or ""
    ti = payload.get("tool_input") or {}

    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        if "twg" not in cmd:
            sys.exit(0)
        creates = _twg_creates(cmd)
        mechanism = "twg"
    elif tool.startswith("mcp__") and _MCP_CREATE.search(tool):
        creates = _mcp_creates(tool, ti)
        mechanism = "mcp"
    else:
        sys.exit(0)

    if not creates:
        sys.exit(0)

    try:
        rules = _load_rules(payload.get("cwd") or os.getcwd())
    except RuntimeError as e:
        print(f"[jira-create-fields-gate] BLOCKED: não consegui ler as regras de criação: {e}.",
              file=sys.stderr)
        sys.exit(2)
    if rules is None:
        sys.exit(0)
    project, fields, path = rules

    problems = []
    for n, found in enumerate(creates, 1):
        if found == "opaque":
            problems.append(
                f"  card {n}: criação por REST cru (`twg api`) ou linha ilegível; não dá "
                "para conferir os campos. Use `twg jira workitem create` com `--field`."
            )
            continue
        target = _project_of(found)
        if target and project and str(target).strip().upper() != str(project).strip().upper():
            continue
        for f, got in _missing(found, fields):
            label = f.get("name") or f["id"]
            expected = json.dumps(f.get("value"), ensure_ascii=False)
            if got is None:
                problems.append(f"  card {n}: falta {label} ({f['id']}), esperado {expected}")
            else:
                problems.append(
                    f"  card {n}: {label} ({f['id']}) veio "
                    f"{json.dumps(_parse_json(got), ensure_ascii=False)}, esperado {expected}"
                )

    if not problems:
        sys.exit(0)

    print(
        "[jira-create-fields-gate] BLOCKED: card criado fora das regras do board-flow.yaml.\n"
        f"  {path} exige em todo card novo do projeto {project}:\n"
        + "\n".join(f"    - {f.get('name') or f['id']} ({f['id']}) = "
                    f"{json.dumps(f.get('value'), ensure_ascii=False)}" for f in fields)
        + "\n  O que faltou:\n" + "\n".join(problems)
        + f"\n  Refaça a criação incluindo: {_example(fields, mechanism)}\n"
        "  Esses campos não são 'campo inventado': vêm do arquivo e valem mesmo que o\n"
        "  pedido não os cite.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
