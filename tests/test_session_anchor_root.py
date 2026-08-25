#!/usr/bin/env python3
"""Contract tests: estado por sessão ancora na RAIZ da worktree, não no cwd cru.

Sem dependência de terceiros — rode com
`python3 tests/test_session_anchor_root.py`.

O defeito, medido duas vezes neste repo (2026-08-04 e 2026-08-18): os hooks
recebem `cwd` como o diretório CORRENTE do shell, e o diretório do Bash PERSISTE
entre chamadas. Um único `cd common/hooks` dentro de um comando desvia o resto
da sessão inteira: o `session-log.md` passou a ser gravado em
`common/hooks/.claude/session-log.md` e os turnos desviados SUMIRAM do log real
— não era cópia, era perda, invisível ao git porque o `.gitignore` cobre
`.claude/`. Só apareceu porque o diretório órfão saltou no `git status`.

Não é um arquivo, é uma CLASSE. Os hooks que ancoram estado no cwd cru falham
todos do mesmo jeito, e três deles falham ABRINDO um portão em silêncio:

  session-log.py        log da sessão vai para o subdiretório  → /common:recap
                        monta "você pediu / eu entreguei" com meia sessão
  capture-build-result  baseline de build gravada no subdiretório
  mark-build-stale      edição na raiz vira `relative_to` inválido → o hook sai
                        em silêncio e a baseline NUNCA fica STALE
  gate-advance          não acha baseline no subdiretório → push liberado
  acceptance-gate       não acha o artefato de aceite → transição liberada
  loop-budget           contagem de repetição zera → o teto de 3 nunca dispara
  session-checkpoint    lê o log no lugar errado → checkpoint volta vazio

A âncora certa é `_wtlib.session_root` (raiz da worktree), NÃO `main_root`:
estado que pertence a esta worktree tem de seguir a worktree — ler o build de
uma worktree como baseline de outra é a mesma mentira ao contrário.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(script, payload):
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=str(cwd),
                          capture_output=True, text=True)


def make_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "-q", "-b", "main"], path)
    git(["config", "user.email", "t@t"], path)
    git(["config", "user.name", "t"], path)
    (path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (path / "README.md").write_text("x", encoding="utf-8")
    git(["add", "-A"], path)
    git(["commit", "-qm", "seed"], path)
    return path


def stray_dirs(root, sub):
    """Todo `.claude/` que apareceu fora da raiz — a assinatura do defeito."""
    return [str(p) for p in Path(root).rglob(".claude")
            if p.parent.resolve() != Path(root).resolve()]


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # ─────────────────────────────────────────────────────────────────────
    print("\n# session-log.py — o defeito original")
    # ─────────────────────────────────────────────────────────────────────
    r1 = make_repo(tmp / "r1")
    sub = r1 / "common" / "hooks"
    sub.mkdir(parents=True)

    r = run_hook("session-log.py", {"prompt": "pedido do usuário", "cwd": str(sub)})
    check("hook sai 0", r.returncode == 0, r.stderr)
    log = r1 / ".claude" / "session-log.md"
    check("log gravado na RAIZ", log.exists(), f"não existe: {log}")
    check("prompt está no log",
          log.exists() and "pedido do usuário" in log.read_text(encoding="utf-8"))
    check("nenhum .claude órfão no subdiretório",
          not stray_dirs(r1, sub), stray_dirs(r1, sub))

    # Dois turnos, um da raiz e um do subdiretório, no MESMO arquivo: é isto
    # que "não era cópia, era perda" significa — o log não pode partir em dois.
    run_hook("session-log.py", {"prompt": "turno da raiz", "cwd": str(r1)})
    text = log.read_text(encoding="utf-8")
    check("os dois turnos moram no mesmo log",
          "pedido do usuário" in text and "turno da raiz" in text)

    # ─────────────────────────────────────────────────────────────────────
    print("\n# worktree ligada — o estado segue a WORKTREE, não o clone principal")
    # ─────────────────────────────────────────────────────────────────────
    wt = tmp / "wt1"
    git(["worktree", "add", "-q", "-b", "session/x", str(wt)], r1)
    wtsub = wt / "common" / "hooks"
    wtsub.mkdir(parents=True, exist_ok=True)
    run_hook("session-log.py", {"prompt": "turno da worktree", "cwd": str(wtsub)})
    wtlog = wt / ".claude" / "session-log.md"
    check("log da worktree fica na raiz DELA", wtlog.exists(), f"não existe: {wtlog}")
    check("não vazou para o clone principal",
          "turno da worktree" not in log.read_text(encoding="utf-8"))

    # ─────────────────────────────────────────────────────────────────────
    print("\n# capture-build-result.py — baseline de build")
    # ─────────────────────────────────────────────────────────────────────
    r2 = make_repo(tmp / "r2")
    sub2 = r2 / "src" / "main"
    sub2.mkdir(parents=True)
    r = run_hook("capture-build-result.py", {
        "tool_name": "Bash",
        "tool_input": {"command": "./mvnw verify"},
        "tool_response": {"stdout": "BUILD SUCCESS\nTests run: 12, Failures: 0"},
        "cwd": str(sub2),
    })
    state = r2 / ".claude" / "last-build.json"
    check("baseline gravada na RAIZ", state.exists(), f"não existe: {state}")
    check("nenhum .claude órfão", not stray_dirs(r2, sub2), stray_dirs(r2, sub2))

    # ─────────────────────────────────────────────────────────────────────
    print("\n# mark-build-stale.py — invalidar a baseline (falha ABRINDO portão)")
    # ─────────────────────────────────────────────────────────────────────
    # cwd no subdiretório, edição num arquivo da RAIZ: com o cwd cru o
    # `relative_to` estourava ValueError e o hook saía em silêncio, deixando a
    # baseline verde para sempre.
    r = run_hook("mark-build-stale.py", {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(r2 / "src" / "App.java")},
        "cwd": str(sub2),
    })
    check("hook sai 0", r.returncode == 0, r.stderr)
    st = json.loads(state.read_text(encoding="utf-8")) if state.exists() else {}
    check("baseline virou STALE", st.get("status") == "STALE", st.get("status"))

    # ─────────────────────────────────────────────────────────────────────
    print("\n# gate-advance.py — barrar push com baseline vermelha")
    # ─────────────────────────────────────────────────────────────────────
    r3 = make_repo(tmp / "r3")
    sub3 = r3 / "api" / "src"
    sub3.mkdir(parents=True)
    (r3 / ".claude").mkdir(exist_ok=True)
    (r3 / ".claude" / "last-build.json").write_text(json.dumps({
        "status": "FAILURE", "at": "2026-08-25T10:00:00+00:00",
        "command": "./mvnw verify", "kind": "maven",
    }), encoding="utf-8")
    r = run_hook("gate-advance.py", {
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
        "cwd": str(sub3),
    })
    check("push BARRADO mesmo com o cwd no subdiretório",
          r.returncode == 2, f"exit={r.returncode} stderr={r.stderr[:200]}")

    # E o opt-out honesto continua sendo lido da raiz.
    r4 = make_repo(tmp / "r4")
    sub4 = r4 / "docs"
    sub4.mkdir(parents=True)
    (r4 / ".claude").mkdir(exist_ok=True)
    (r4 / ".claude" / "no-build").write_text("", encoding="utf-8")
    r = run_hook("gate-advance.py", {
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
        "cwd": str(sub4),
    })
    check("`.claude/no-build` da raiz vale no subdiretório", r.returncode == 0, r.stderr[:200])

    # ─────────────────────────────────────────────────────────────────────
    print("\n# loop-budget.py — o teto de repetição de falha")
    # ─────────────────────────────────────────────────────────────────────
    r5 = make_repo(tmp / "r5")
    sub5 = r5 / "pkg"
    sub5.mkdir(parents=True)
    run_hook("loop-budget.py", {
        "tool_name": "Task",
        "tool_input": {"subagent_type": "x", "prompt": "y"},
        "tool_response": {"content": "erro: NullPointerException em Foo.java:42"},
        "cwd": str(sub5),
    })
    check("estado do loop gravado na RAIZ",
          (r5 / ".claude" / "loop-state.json").exists()
          or not stray_dirs(r5, sub5),
          stray_dirs(r5, sub5))
    check("nenhum .claude órfão", not stray_dirs(r5, sub5), stray_dirs(r5, sub5))

    # ─────────────────────────────────────────────────────────────────────
    print("\n# acceptance-gate.py — barrar transição com aceite INCOMPLETE")
    # ─────────────────────────────────────────────────────────────────────
    # O artefato de aceite mora na raiz; com o cwd cru o gate não o achava e
    # saía em silêncio (`sys.exit(0)`) — portão aberto sem uma linha de aviso.
    r6 = make_repo(tmp / "r6")
    sub6 = r6 / "api"
    sub6.mkdir(parents=True)
    acc = r6 / ".claude" / "acceptance"
    acc.mkdir(parents=True)
    (acc / "WEGO-1234.yaml").write_text(
        "key: WEGO-1234\nstatus: INCOMPLETE\ncriteria:\n"
        "  - id: AC1\n    gap: nenhum teste exercita o endpoint\n",
        encoding="utf-8")
    r = run_hook("acceptance-gate.py", {
        "tool_name": "mcp__mcp-atlassian__jira_transition_issue",
        "tool_input": {"issue_key": "WEGO-1234", "transition_id": "351"},
        "cwd": str(sub6),
    })
    check("transição BARRADA com o cwd no subdiretório",
          r.returncode == 2, f"exit={r.returncode} stderr={r.stderr[:200]}")
    check("a lacuna aparece na mensagem",
          "nenhum teste exercita o endpoint" in r.stderr, r.stderr[:200])

    # ─────────────────────────────────────────────────────────────────────
    print("\n# session-checkpoint.py — o rastro de intenção não pode voltar vazio")
    # ─────────────────────────────────────────────────────────────────────
    # `recent_intents` LÊ o mesmo arquivo que o session-log GRAVA. Se escritor e
    # leitor usarem âncoras diferentes, o checkpoint volta vazio em silêncio.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "session_checkpoint", HOOKS / "session-checkpoint.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(HOOKS))
    spec.loader.exec_module(mod)

    r7 = make_repo(tmp / "r7")
    sub7 = r7 / "deep" / "nested"
    sub7.mkdir(parents=True)
    run_hook("session-log.py", {"prompt": "intenção do turno", "cwd": str(sub7)})
    intents = mod.recent_intents(str(sub7))
    check("checkpoint acha a intenção lida do subdiretório",
          any("intenção do turno" in i for i in intents), intents)

    # ─────────────────────────────────────────────────────────────────────
    print("\n# fora de um repo git — o hook não pode morrer por isto")
    # ─────────────────────────────────────────────────────────────────────
    bare = tmp / "sem-git"
    bare.mkdir()
    r = run_hook("session-log.py", {"prompt": "sem repo", "cwd": str(bare)})
    check("hook sai 0 fora de repo", r.returncode == 0, r.stderr)
    check("cai no próprio cwd", (bare / ".claude" / "session-log.md").exists())


# ─────────────────────────────────────────────────────────────────────────
print("\n# guarda de deriva — nenhum hook novo pode voltar a ancorar no cwd cru")
# ─────────────────────────────────────────────────────────────────────────
# A lista de hooks que ancoram estado sob `.claude/`. Um hook novo que grave
# estado e não esteja aqui é omissão; um hook daqui que volte ao cwd cru é
# regressão. As duas coisas ficam vermelhas.
ANCORADOS = [
    "session-log.py", "session-checkpoint.py", "capture-build-result.py",
    "gate-advance.py", "mark-build-stale.py", "loop-budget.py",
    "acceptance-gate.py",
]

for name in ANCORADOS:
    src = (HOOKS / name).read_text(encoding="utf-8")
    check(f"{name}: usa session_root", "session_root(" in src)

# O padrão cru: `Path(payload.get("cwd") ...)` sem passar pelo helper.
CRU = re.compile(r'Path\(\s*payload\.get\(\s*["\']cwd["\']')
for name in ANCORADOS:
    src = (HOOKS / name).read_text(encoding="utf-8")
    hits = [ln for ln in src.splitlines() if CRU.search(ln)]
    check(f"{name}: nenhum Path(payload['cwd']) cru", not hits, hits)

check("_wtlib expõe session_root",
      "def session_root(" in (HOOKS / "_wtlib.py").read_text(encoding="utf-8"))


print()
if FAILURES:
    print(f"{len(FAILURES)} FALHA(S): {', '.join(FAILURES)}")
    sys.exit(1)
print("todos os casos verdes")
