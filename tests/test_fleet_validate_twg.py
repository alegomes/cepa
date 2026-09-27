#!/usr/bin/env python3
"""board-flow-fleet-validate.sh valida o caminho que o atlassian-expert usa: a `twg`.

Até 2026-09 o script rodava `claude -p` restrito ao `mcp-atlassian` (token
estático em ~/.zsecrets). O agente passou a falar com o Jira pela `twg`, então
um PASS provava um caminho que nenhum run percorre e uma `twg` quebrada passava
sem aviso. Aqui um `twg` falso registra cada chamada e responde conforme
FAKE_MODE; o teste confere que o PASS depende da `twg` e que falha dela vira
BLOCKED, sem `claude` e sem `JIRA_API_TOKEN` no ambiente.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "board-flow" / "board-flow-fleet-validate.sh"

FAKE_TWG = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
mode = os.environ.get("FAKE_MODE", "ok")
if args[0] == "doctor":
    ok = mode != "auth"
    print(json.dumps({"data": {"connectivity": {"ok": ok,
          "message": "ok" if ok else "OAuth token expired"}}}))
    sys.exit(0)
if args[:3] == ["jira", "space", "get"]:
    if mode == "noproject":
        print(json.dumps({"ok": False, "error": {"message": "No project could be found"}}))
        sys.exit(1)
    print(json.dumps({"data": [{"key": args[3]}]}))
    sys.exit(0)
if args[:3] == ["jira", "workitem", "query"]:
    if mode == "badquery":
        print(json.dumps({"ok": True, "data": {}}))
        sys.exit(0)
    print(json.dumps({"data": {"issues": [
        {"key": "ABC-1", "summary": "primeiro", "priority": {"name": "Alta"}},
        {"key": "ABC-2", "summary": "segundo"}]}}))
    sys.exit(0)
sys.exit(9)
'''

falhas = []


def check(nome, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + nome + ("" if cond else f"  {extra}"))
    if not cond:
        falhas.append(nome)


def run(mode, repo, env_extra=None):
    tmp = Path(tempfile.mkdtemp())
    twg = tmp / "twg"
    twg.write_text(FAKE_TWG)
    twg.chmod(twg.stat().st_mode | stat.S_IEXEC)
    log = tmp / "calls.jsonl"
    log.touch()
    env = {k: v for k, v in os.environ.items()
           if k not in ("JIRA_API_TOKEN", "PROJECT_KEY", "TODO_STATUS")}
    # Sem `claude` alcançável: se o script ainda chamasse `claude -p`, falharia.
    env.update(TWG_BIN=str(twg), FAKE_LOG=str(log), FAKE_MODE=mode,
               CLAUDE_BIN="/nonexistent/claude", HOME=str(tmp))
    env.update(env_extra or {})
    r = subprocess.run(["bash", str(SCRIPT), str(repo)], env=env,
                       capture_output=True, text=True, timeout=60)
    calls = [json.loads(l) for l in log.read_text().splitlines()]
    return r, calls


repo = Path(tempfile.mkdtemp())
(repo / "board-flow.yaml").write_text(
    'defaults:\n  project_key: ABC\n  status_map:\n    to_do: "A fazer"\n')

# 1. Caminho feliz: PASS vem da twg, com key e status lidos do board-flow.yaml.
r, calls = run("ok", repo)
check("PASS com twg saudável sai 0", r.returncode == 0, r.stderr)
check("PASS nomeia twg e conta os cards",
      'VALIDATION PASS: twg authenticated, ABC visible, To-Do "A fazer" listed (2 cards).' in r.stdout,
      r.stdout)
check("lista card com prioridade", "ABC-1 — primeiro — Alta" in r.stdout, r.stdout)
check("preflight é twg doctor", calls and calls[0][0] == "doctor", calls)
check("confere o projeto com twg jira space get ABC",
      any(c[:4] == ["jira", "space", "get", "ABC"] for c in calls), calls)
q = [c for c in calls if c[:3] == ["jira", "workitem", "query"]]
check("consulta a coluna To-Do do board-flow.yaml",
      bool(q) and q[0][3] == 'project = ABC AND status = "A fazer" ORDER BY priority DESC', q)

# 2. twg sem autenticação: BLOCKED de AUTH, e não chega a consultar o quadro.
r, calls = run("auth", repo)
check("twg sem auth sai 1", r.returncode == 1, r.stdout + r.stderr)
check("BLOCKED diz que é auth, não quadro vazio",
      "BLOCKED: twg preflight failed" in r.stderr and "NOT an empty board" in r.stderr
      and "OAuth token expired" in r.stderr, r.stderr)
check("sem auth não consulta o quadro",
      not any(c[:2] == ["jira", "workitem"] for c in calls), calls)
check("sem auth não imprime PASS", "VALIDATION PASS" not in r.stdout, r.stdout)

# 3. Projeto invisível: BLOCKED.
r, calls = run("noproject", repo)
check("projeto invisível sai 1 com BLOCKED",
      r.returncode == 1 and "BLOCKED: project ABC not visible via twg" in r.stderr, r.stderr)

# 4. Resposta sem data.issues não vira "0 cards".
r, calls = run("badquery", repo)
check("query sem data.issues é BLOCKED, não PASS vazio",
      r.returncode == 1 and "VALIDATION PASS" not in r.stdout, r.stdout + r.stderr)

# 5. Sem board-flow.yaml e sem override: BLOCKED antes de chamar a twg.
vazio = Path(tempfile.mkdtemp())
r, calls = run("ok", vazio)
check("sem config sai 1", r.returncode == 1 and "no board-flow.yaml" in r.stderr, r.stderr)
check("sem config não chama a twg", calls == [], calls)

# 6. Override por env dispensa o board-flow.yaml.
r, calls = run("ok", vazio, {"PROJECT_KEY": "WEGO", "TODO_STATUS": "To Do"})
check("override PROJECT_KEY/TODO_STATUS passa",
      r.returncode == 0 and 'WEGO visible, To-Do "To Do"' in r.stdout, r.stdout + r.stderr)

# 7. twg ausente: BLOCKED nomeando a twg.
r = subprocess.run(["bash", str(SCRIPT), str(repo)],
                   env={**os.environ, "TWG_BIN": "/nonexistent/twg"},
                   capture_output=True, text=True, timeout=30)
check("twg ausente é BLOCKED", r.returncode == 1 and "twg not found" in r.stderr, r.stderr)

# 8. O script não depende mais do mcp-atlassian nem do token estático.
src = SCRIPT.read_text()
codigo = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
check("código não chama claude -p",
      "CLAUDE_BIN" not in codigo and "claude -p" not in codigo
      and "--allowedTools" not in codigo, "")
check("código não usa mcp-atlassian nem JIRA_API_TOKEN",
      "mcp-atlassian" not in codigo and "JIRA_API_TOKEN" not in codigo, "")

print(f"\n{len(falhas)} falha(s)")
sys.exit(1 if falhas else 0)
