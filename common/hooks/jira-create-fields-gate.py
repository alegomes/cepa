#!/usr/bin/env python3
"""PreToolUse (common) — card novo no Jira nasce com os `required_fields` do board-flow.yaml.

## Por que existe

O `board-flow.yaml` de cada repo WeGo declara, em `required_fields`, os campos
que todo card do projeto precisa ter (Team e Módulo do sistema). O Jira NÃO
recusa um card sem eles: a criação passa, e o card some dos quadros filtrados
por Team. A única coisa que garantia o preenchimento era uma frase no
`atlassian-expert.md` ("Read project config first, every time").

Não bastou. Em 14/09 e 22/09/2026 o próprio atlassian-expert criou 35 cards
(WEGO-2273 a 2278, WEGO-2302 a 2330) sem os dois campos: o pedido que recebeu
não citava os campos, dizia "não invente campo customizado", e ele nunca abriu o
board-flow.yaml. O dono preencheu os 35 à mão depois. Em 17/09 o mesmo agente
criou com os campos. Regra que depende do agente lembrar falha de vez em quando.

Este hook tira a decisão do agente: toda criação de card é conferida contra o
arquivo, qualquer que seja o caminho.

## O que ele confere

Caminhos de criação cobertos:
- `twg jira workitem create` (Bash): lê `--field id=valor`, `--fields-json` e
  `--variables-json`.
- MCP de qualquer servidor (`createJiraIssue`, `jira_create_issue`,
  `jira_batch_create_issues`): procura os campos em qualquer nível do input
  (`additional_fields`, `fields`, ou solto), inclusive JSON dentro de string.
- `twg api -X POST .../rest/api/N/issue` (REST cru): barrado sempre que há
  `required_fields`, porque o corpo pode estar num arquivo que o hook não lê.

Para cada campo de `required_fields` (por `id` ou por `name`), o valor passado
precisa bater com o `value` do arquivo. UUID cru e `{"id": "..."}` contam como o
mesmo valor.

`required_fields` segue a mesma resolução do atlassian-expert:
`topologies.<ativa>.required_fields` substitui `defaults.required_fields`, com a
topologia ativa vinda de `.claude/topology`, depois `default_topology`.

## O que passa

- Repo sem board-flow.yaml, ou com `required_fields` vazio.
- Card de outro projeto (a chave do projeto na chamada difere da do arquivo):
  as regras deste arquivo não valem lá.
- Qualquer chamada que não cria card.

Vale para a sessão principal também: o pedido do dono é que TODO card nasça
conforme o arquivo, em qualquer modo.
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
    """Sobe de cwd até achar o board-flow.yaml, parando na raiz do git."""
    d = os.path.abspath(cwd or ".")
    while True:
        for nome in _CONFIG_NAMES:
            p = os.path.join(d, nome)
            if os.path.isfile(p):
                return d, p
        if os.path.exists(os.path.join(d, ".git")):
            return None, None
        parent = os.path.dirname(d)
        if parent == d:
            return None, None
        d = parent


def _load_rules(cwd):
    """(project_key, required_fields, config_path) ou None quando não há regra.

    Levanta RuntimeError quando o arquivo existe mas não dá para ler: nesse caso
    o gate barra, porque liberar seria repetir o furo que ele existe para fechar.
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
    topo = None
    marker = os.path.join(root, ".claude", "topology")
    if os.path.isfile(marker):
        try:
            topo = open(marker, encoding="utf-8").read().strip() or None
        except OSError:
            topo = None
    topo = topo or defaults.get("default_topology") or data.get("default_topology")
    override = ((data.get("topologies") or {}).get(topo) or {}) if topo else {}

    fields = override.get("required_fields", defaults.get("required_fields")) or []
    project = override.get("project_key") or defaults.get("project_key")
    fields = [f for f in fields if isinstance(f, dict) and f.get("id")]
    if not fields:
        return None
    return project, fields, path


# ---------------------------------------------------------------- valores

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
    """Forma comparável de um valor de campo: UUID cru == {"id": UUID}."""
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
    """Junta em `out` todo par chave→valor, em qualquer nível, abrindo JSON em string."""
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
    """Lista de (campo, esperado, recebido|None) que não batem."""
    bad = []
    for f in fields:
        keys = [str(f["id"]).casefold()]
        if f.get("name"):
            keys.append(str(f["name"]).casefold())
        got = next((found[k] for k in keys if k in found), None)
        if got is None or _norm(got) != _norm(f.get("value")):
            bad.append((f, got))
    return bad


# ---------------------------------------------------------------- caminhos

def _twg_creates(command):
    """Cada criação legível pela `twg`, como dict de campos achados, ou "opaque"."""
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

def _exemplo(fields, mecanismo):
    if mecanismo == "twg":
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
        mecanismo = "twg"
    elif tool.startswith("mcp__") and _MCP_CREATE.search(tool):
        creates = _mcp_creates(tool, ti)
        mecanismo = "mcp"
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

    problemas = []
    for n, found in enumerate(creates, 1):
        if found == "opaque":
            problemas.append(
                f"  card {n}: criação por REST cru (`twg api`) ou linha ilegível; não dá "
                "para conferir os campos. Use `twg jira workitem create` com `--field`."
            )
            continue
        alvo = _project_of(found)
        if alvo and project and str(alvo).strip().upper() != str(project).strip().upper():
            continue
        for f, got in _missing(found, fields):
            nome = f.get("name") or f["id"]
            esperado = json.dumps(f.get("value"), ensure_ascii=False)
            if got is None:
                problemas.append(f"  card {n}: falta {nome} ({f['id']}), esperado {esperado}")
            else:
                problemas.append(
                    f"  card {n}: {nome} ({f['id']}) veio "
                    f"{json.dumps(_parse_json(got), ensure_ascii=False)}, esperado {esperado}"
                )

    if not problemas:
        sys.exit(0)

    print(
        "[jira-create-fields-gate] BLOCKED: card criado fora das regras do board-flow.yaml.\n"
        f"  {path} exige em todo card novo do projeto {project}:\n"
        + "\n".join(f"    - {f.get('name') or f['id']} ({f['id']}) = "
                    f"{json.dumps(f.get('value'), ensure_ascii=False)}" for f in fields)
        + "\n  O que faltou:\n" + "\n".join(problemas)
        + f"\n  Refaça a criação incluindo: {_exemplo(fields, mecanismo)}\n"
        "  Esses campos não são 'campo inventado': vêm do arquivo e valem mesmo que o\n"
        "  pedido não os cite.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
