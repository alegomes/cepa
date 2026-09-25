#!/usr/bin/env python3
"""Regressão do common/hooks/jira-create-fields-gate.py.

Roda com `python3 tests/test_jira_create_fields_gate.py`; sai não-zero em falha.

O caso-âncora é a chamada real de 22/09/2026 (WEGO-2303): o atlassian-expert
criou a Story pelo MCP sem `additional_fields`, e o card nasceu sem Team e sem
Módulo do sistema. Com o hook, essa chamada tem de ser barrada.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "jira-create-fields-gate.py"
FAILURES = []

TEAM = "76bd2859-3b45-4c1d-b125-24fccb27a1b4"
CONFIG = f"""schema_version: 1
defaults:
  project_key: WEGO
  required_fields: [
      {{ id: customfield_10001, name: "Team", value: "{TEAM}" }},
      {{ id: customfield_10414, name: "Módulo do sistema", value: {{ id: "10372" }} }},
    ]
default_topology: build-hex
topologies:
  discovery:
    required_fields:
      - {{ id: customfield_10001, name: "Team", value: "product-team" }}
"""


def make_repo(config=CONFIG, topology=None):
    d = Path(tempfile.mkdtemp())
    (d / ".git").mkdir()
    if config is not None:
        (d / "board-flow.yaml").write_text(config, encoding="utf-8")
    if topology:
        (d / ".claude").mkdir()
        (d / ".claude" / "topology").write_text(topology)
    (d / "src" / "main").mkdir(parents=True)
    return d


def run(tool, tool_input, cwd, agent_type="board-flow:atlassian-expert"):
    payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(cwd)}
    if agent_type:
        payload["agent_type"] = agent_type
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


MCP = "mcp__mcp-atlassian__jira_create_issue"
CLOUD = "mcp__Atlassian__createJiraIssue"
BATCH = "mcp__mcp-atlassian__jira_batch_create_issues"
OK_FIELDS = {"customfield_10001": TEAM, "customfield_10414": {"id": "10372"}}
repo = make_repo()

# ── caso-âncora: a chamada de 22/09 ─────────────────────────────────────────
r = run(MCP, {"project_key": "WEGO", "summary": "Lote de concessão habilita várias pessoas numa chamada",
              "issue_type": "Story", "description": "CS-1: ..."}, repo)
check("chamada de 22/09 sem campos BLOQUEIA", r.returncode == 2, f"rc={r.returncode} {r.stderr[:200]}")
check("a mensagem nomeia os dois campos e o valor",
      "Team" in r.stderr and "Módulo do sistema" in r.stderr and TEAM in r.stderr, r.stderr[:400])
check("a mensagem diz que o campo não é inventado", "inventado" in r.stderr, r.stderr[-300:])

# ── MCP com os campos (formato que funcionou em 17/09) ──────────────────────
r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Story",
              "additional_fields": json.dumps({"parent": "WEGO-2221", **OK_FIELDS})}, repo)
check("MCP com additional_fields em string passa", r.returncode == 0, r.stderr[:300])

r = run(CLOUD, {"projectKey": "WEGO", "summary": "x", "issueTypeName": "Story",
                "additional_fields": {"customfield_10001": {"id": TEAM}, "customfield_10414": {"id": "10372"}}}, repo)
check("MCP da nuvem com Team como objeto {id} passa", r.returncode == 0, r.stderr[:300])

r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Story",
              "additional_fields": {"customfield_10001": TEAM}}, repo)
check("só o Team, sem o Módulo, BLOQUEIA", r.returncode == 2 and "Módulo" in r.stderr, r.stderr[:300])

r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Story",
              "additional_fields": {"customfield_10001": "00000000-0000-0000-0000-000000000000",
                                    "customfield_10414": {"id": "10372"}}}, repo)
check("Team de outro time BLOQUEIA", r.returncode == 2 and "veio" in r.stderr, r.stderr[:300])

r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Story",
              "additional_fields": {"Team": TEAM, "Módulo do sistema": {"id": "10372"}}}, repo)
check("campos pelo nome em vez do id passam", r.returncode == 0, r.stderr[:300])

# ── lote ────────────────────────────────────────────────────────────────────
issues = [{"project_key": "WEGO", "summary": "a", "issue_type": "Story", **OK_FIELDS},
          {"project_key": "WEGO", "summary": "b", "issue_type": "Story"}]
r = run(BATCH, {"issues": json.dumps(issues)}, repo)
check("lote com um card sem campo BLOQUEIA e aponta o card 2",
      r.returncode == 2 and "card 2" in r.stderr and "card 1" not in r.stderr, r.stderr[:400])
r = run(BATCH, {"issues": json.dumps([issues[0], issues[0]])}, repo)
check("lote completo passa", r.returncode == 0, r.stderr[:300])

# ── twg ─────────────────────────────────────────────────────────────────────
base = "twg jira workitem create --space WEGO --type Story --summary 'x' --description 'y'"
r = run("Bash", {"command": base}, repo)
check("twg sem --field BLOQUEIA", r.returncode == 2, r.stderr[:300])
check("a mensagem do twg ensina o --field", "--field 'customfield_10001=" in r.stderr, r.stderr[-400:])

cmd = base + f" --field 'customfield_10001=\"{TEAM}\"' --field 'customfield_10414={{\"id\":\"10372\"}}'"
r = run("Bash", {"command": cmd}, repo)
check("twg com os dois --field passa", r.returncode == 0, r.stderr[:300])

cmd = base + f" --field customfield_10001={TEAM} --field 'customfield_10414={{\"id\":\"10372\"}}'"
r = run("Bash", {"command": cmd}, repo)
check("twg com UUID sem aspas JSON passa", r.returncode == 0, r.stderr[:300])

cmd = base + " --fields-json '" + json.dumps(OK_FIELDS) + "'"
r = run("Bash", {"command": cmd}, repo)
check("twg com --fields-json passa", r.returncode == 0, r.stderr[:300])

r = run("Bash", {"command": "cd /tmp && " + base + " && echo ok"}, repo)
check("twg sem campo no meio de uma cadeia BLOQUEIA", r.returncode == 2, r.stderr[:200])

r = run("Bash", {"command": "twg api jira:/rest/api/3/issue -X POST --input body.json"}, repo)
check("twg api POST em /issue BLOQUEIA", r.returncode == 2 and "REST cru" in r.stderr, r.stderr[:300])

r = run("Bash", {"command": "twg api jira:/rest/api/3/issue/WEGO-1 -X GET"}, repo)
check("twg api GET passa", r.returncode == 0, r.stderr[:200])

for c in ("twg jira workitem create --help", "twg jira workitem get WEGO-1",
          "twg jira workitem field create-metadata --space WEGO --type Story",
          "echo 'twg jira workitem create --space WEGO'"):
    r = run("Bash", {"command": c}, repo)
    check(f"não é criação, passa: {c[:50]}", r.returncode == 0, r.stderr[:200])

# ── sessão principal também é conferida ─────────────────────────────────────
r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Task"}, repo, agent_type=None)
check("sessão principal sem campo BLOQUEIA", r.returncode == 2, r.stderr[:200])

# ── escopo ──────────────────────────────────────────────────────────────────
r = run(MCP, {"project_key": "WGD", "summary": "x", "issue_type": "Story"}, repo)
check("card de outro projeto passa", r.returncode == 0, r.stderr[:200])

r = run("Bash", {"command": base}, repo / "src" / "main")
check("cwd em subdiretório acha o board-flow.yaml", r.returncode == 2, r.stderr[:200])

r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Story"}, make_repo(config=None))
check("repo sem board-flow.yaml passa", r.returncode == 0, r.stderr[:200])

empty = "defaults:\n  project_key: WEGO\n  required_fields: []\n"
r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Story"}, make_repo(config=empty))
check("required_fields vazio passa", r.returncode == 0, r.stderr[:200])

r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Story"}, make_repo(config="defaults: [unclosed"))
check("board-flow.yaml ilegível BLOQUEIA", r.returncode == 2, r.stderr[:200])

# ── topologia substitui a lista inteira ─────────────────────────────────────
disc = make_repo(topology="discovery")
r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Story",
              "additional_fields": {"customfield_10001": "product-team"}}, disc)
check("topologia discovery: só o Team dela basta", r.returncode == 0, r.stderr[:300])
r = run(MCP, {"project_key": "WEGO", "summary": "x", "issue_type": "Story",
              "additional_fields": OK_FIELDS}, disc)
check("topologia discovery: Team do defaults BLOQUEIA", r.returncode == 2, r.stderr[:300])

# ── ferramentas que não criam ───────────────────────────────────────────────
r = run("mcp__mcp-atlassian__jira_update_issue", {"issue_key": "WEGO-1"}, repo)
check("update pelo MCP não é conferido", r.returncode == 0, r.stderr[:200])
r = run("Bash", {"command": "ls"}, repo)
check("Bash sem twg passa", r.returncode == 0)
r = subprocess.run([sys.executable, str(HOOK)], input="{not json", capture_output=True, text=True)
check("payload ilegível passa", r.returncode == 0)

print()
if FAILURES:
    print(f"{len(FAILURES)} falha(s)")
    sys.exit(1)
print("todos passaram")
