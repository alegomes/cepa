#!/usr/bin/env python3
"""Verde sem teste nenhum não é verde (item `gate-verde-sem-teste`, BACKLOG).

Sem dependências — `python3 tests/test_verde_sem_teste.py`. Sai não-zero em falha.

O defeito, medido no wego em 2026-08-24: com `surefire.failIfNoSpecifiedTests=false`
no pom, `./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest` imprime
BUILD SUCCESS sem nenhuma linha "Tests run:". O capture-build-result gravava isso
como SUCCESS, o gate-advance liberava o commit, e o card virava feito sem que um
teste sequer tivesse rodado. O mesmo vale para `pytest -k NomeErrado`,
`go test -run NomeErrado` e `npm test -- -t NomeErrado`.

O contrato que este arquivo guarda:

  capture-build-result.py
    - comando COM filtro de teste + saída verde + zero teste executado → EMPTY
      (não SUCCESS), com `tests_run: 0` e motivo nomeado;
    - comando COM filtro + contagem > 0 → SUCCESS, com `tests_run`;
    - comando SEM filtro → comportamento de antes (não exige contagem).

  gate-advance.py (critério de pronto, ponta a ponta)
    - depois de uma captura EMPTY, `git commit` é BARRADO, e a mensagem diz que
      o filtro casou zero teste e como corrigir.

  acceptance-gate.py e cepa-plan finish (a outra metade: "nem declarar feito")
    - depois de uma captura EMPTY, a transição do card para in_review/done é
      BARRADA mesmo com auditoria `complete`; voltar para in_progress passa;
    - `cepa-plan finish --status done` recusa; blocked/pending aceitam;
    - depois de um verde com teste executado, as duas portas liberam.

  prompts
    - proof-reviewer e completion-auditor exigem N > 0 testes executados.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Este teste executa hooks que emitem telemetria. Ver tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"
CAPTURE = HOOKS / "capture-build-result.py"
GATE = HOOKS / "gate-advance.py"
ACCEPTANCE = HOOKS / "acceptance-gate.py"
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(script, payload):
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)


def make_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "-q", "-b", "main"], path)
    (path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    return path


def capture(repo, command, output, exit_code=None):
    resp = {"stdout": output}
    if exit_code is not None:
        resp["exit_code"] = exit_code
    return run_hook(CAPTURE, {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": resp,
        "cwd": str(repo),
    })


KEY = "WEGO-2100"

BOARD_FLOW = """\
defaults:
  project_key: WEGO
  transition_ids:
    "31": in_progress
    "41": in_review
    "51": done
"""


def transition(repo, tid):
    """Transição do card pelo mcp-atlassian, no hook real do acceptance-gate."""
    return run_hook(ACCEPTANCE, {
        "tool_name": "mcp__mcp-atlassian__jira_transition_issue",
        "tool_input": {"issue_key": KEY, "transition_id": tid},
        "cwd": str(repo),
    })


def cepa_plan(repo, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(repo))


def state(repo):
    p = repo / ".claude" / "last-build.json"
    return json.loads(p.read_text()) if p.exists() else None


# ── saídas realistas ──────────────────────────────────────────────────────

MAVEN_VAZIO = """\
[INFO] Scanning for projects...
[INFO] ------------------------------------------------------------------------
[INFO] Reactor Build Order:
[INFO]
[INFO] wego-acesso-backend                                                [pom]
[INFO] domain                                                             [jar]
[INFO]
[INFO] --- maven-surefire-plugin:3.2.5:test (default-test) @ domain ---
[INFO] ------------------------------------------------------------------------
[INFO] Reactor Summary for wego-acesso-backend 1.0.0-SNAPSHOT:
[INFO]
[INFO] wego-acesso-backend ................................ SUCCESS [  0.210 s]
[INFO] domain ............................................. SUCCESS [  2.114 s]
[INFO] ------------------------------------------------------------------------
[INFO] BUILD SUCCESS
[INFO] ------------------------------------------------------------------------
[INFO] Total time:  2.601 s
"""

MAVEN_COM_TESTE = """\
[INFO] --- maven-surefire-plugin:3.2.5:test (default-test) @ domain ---
[INFO] -------------------------------------------------------
[INFO]  T E S T S
[INFO] -------------------------------------------------------
[INFO] Running br.wego.domain.CpfTest
[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.041 s -- in br.wego.domain.CpfTest
[INFO]
[INFO] Results:
[INFO]
[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
[INFO]
[INFO] BUILD SUCCESS
"""

MAVEN_ZERO_EXPLICITO = """\
[INFO] Results:
[INFO]
[INFO] Tests run: 0, Failures: 0, Errors: 0, Skipped: 0
[INFO]
[INFO] BUILD SUCCESS
"""

PYTEST_VAZIO = """\
============================= test session starts ==============================
platform darwin -- Python 3.12.4, pytest-8.2.0, pluggy-1.5.0
rootdir: /repo
collected 5 items / 5 deselected / 0 selected

============================ 5 deselected in 0.02s =============================
"""

PYTEST_COM_TESTE = """\
============================= test session starts ==============================
collected 5 items / 3 deselected / 2 selected

tests/test_cpf.py ..                                                     [100%]

======================= 2 passed, 3 deselected in 0.03s ========================
"""

GO_VAZIO = """\
ok  \tgithub.com/wego/acesso/domain\t0.012s [no tests to run]
?   \tgithub.com/wego/acesso/cmd\t[no test files]
"""

GO_COM_TESTE = """\
ok  \tgithub.com/wego/acesso/domain\t0.015s
"""

JEST_VAZIO = """\
> acesso-web@1.0.0 test
> jest -t NomeErrado

No tests found, exiting with code 0
"""

JEST_TUDO_PULADO = """\
Test Suites: 3 skipped, 0 of 3 total
Tests:       14 skipped, 14 total
Snapshots:   0 total
Time:        1.2 s
"""

JEST_COM_TESTE = """\
PASS src/cpf.test.ts
Test Suites: 1 passed, 1 total
Tests:       2 passed, 12 skipped, 14 total
Snapshots:   0 total
Time:        1.1 s
"""


with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    print("\n# capture-build-result.py — filtro de teste que casou zero teste")

    r = make_repo(tmp / "mvn-vazio")
    capture(r, "./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest", MAVEN_VAZIO)
    s = state(r)
    check("maven -Dtest= com BUILD SUCCESS e nenhum 'Tests run:' → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))
    check("maven vazio grava tests_run 0",
          s is not None and s.get("tests_run") == 0, str(s))
    check("maven vazio nomeia o motivo (filtro casou zero teste)",
          s is not None and "zero" in (s.get("reason") or "").lower(), str(s))

    r = make_repo(tmp / "mvn-zero")
    capture(r, "./mvnw test -Dtest=Nada", MAVEN_ZERO_EXPLICITO)
    s = state(r)
    check("maven -Dtest= com 'Tests run: 0' explícito → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "mvn-ok")
    capture(r, "./mvnw -pl domain -am test -Dtest=CpfTest", MAVEN_COM_TESTE)
    s = state(r)
    check("maven -Dtest= com 'Tests run: 3' → SUCCESS",
          s is not None and s.get("status") == "SUCCESS", str(s))
    check("maven com teste grava tests_run > 0",
          s is not None and (s.get("tests_run") or 0) > 0, str(s))

    r = make_repo(tmp / "mvn-sem-filtro")
    capture(r, "./mvnw verify", MAVEN_VAZIO)
    s = state(r)
    check("maven SEM filtro e sem 'Tests run:' continua SUCCESS (fora de escopo)",
          s is not None and s.get("status") == "SUCCESS", str(s))

    r = make_repo(tmp / "py-vazio")
    capture(r, "pytest -k NomeErrado", PYTEST_VAZIO, exit_code=0)
    s = state(r)
    check("pytest -k com '5 deselected' e nada passou → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "py-exit5")
    capture(r, "pytest -k NomeErrado", PYTEST_VAZIO, exit_code=5)
    s = state(r)
    check("pytest -k saindo 5 (nada coletado) nunca vira SUCCESS",
          s is not None and s.get("status") != "SUCCESS", str(s))

    r = make_repo(tmp / "py-ok")
    capture(r, "pytest -k cpf", PYTEST_COM_TESTE, exit_code=0)
    s = state(r)
    check("pytest -k com '2 passed' → SUCCESS",
          s is not None and s.get("status") == "SUCCESS" and s.get("tests_run") == 2, str(s))

    r = make_repo(tmp / "go-vazio")
    capture(r, "go test ./... -run NomeErrado", GO_VAZIO, exit_code=0)
    s = state(r)
    check("go test -run com '[no tests to run]' → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "go-ok")
    capture(r, "go test ./domain -run=TestCpf", GO_COM_TESTE, exit_code=0)
    s = state(r)
    check("go test -run= com 'ok pkg' sem '[no tests to run]' → SUCCESS",
          s is not None and s.get("status") == "SUCCESS", str(s))

    r = make_repo(tmp / "jest-vazio")
    capture(r, "npm test -- -t NomeErrado", JEST_VAZIO, exit_code=0)
    s = state(r)
    check("jest -t com 'No tests found' → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "jest-pulado")
    capture(r, "npm test -- --testNamePattern=NomeErrado", JEST_TUDO_PULADO, exit_code=0)
    s = state(r)
    check("jest --testNamePattern= com tudo 'skipped' → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "jest-ok")
    capture(r, "npm test -- -t cpf", JEST_COM_TESTE, exit_code=0)
    s = state(r)
    check("jest -t com 'Tests: 2 passed' → SUCCESS",
          s is not None and s.get("status") == "SUCCESS" and s.get("tests_run") == 2, str(s))

    print("\n# critério de pronto — depois de um EMPTY, o commit não passa")

    r = make_repo(tmp / "e2e")
    capture(r, "./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest", MAVEN_VAZIO)
    g = run_hook(GATE, {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'feat: card feito'"},
        "cwd": str(r),
    })
    check("gate-advance BARRA git commit com baseline EMPTY",
          g.returncode == 2, f"exit={g.returncode} stderr={g.stderr[:300]}")
    check("mensagem diz que o filtro casou zero teste",
          "zero" in g.stderr.lower() and "test" in g.stderr.lower(), g.stderr[:400])
    check("mensagem ensina a corrigir (nome certo ou failIfNoSpecifiedTests=true)",
          "failIfNoSpecifiedTests=true" in g.stderr, g.stderr[:400])
    g = run_hook(GATE, {
        "tool_name": "Bash",
        "tool_input": {"command": "git push origin main"},
        "cwd": str(r),
    })
    check("gate-advance BARRA git push com baseline EMPTY", g.returncode == 2, g.stderr[:200])

    # Um verde de verdade depois limpa o bloqueio.
    capture(r, "./mvnw -pl domain -am test -Dtest=CpfTest", MAVEN_COM_TESTE)
    g = run_hook(GATE, {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'feat: card feito'"},
        "cwd": str(r),
    })
    check("verde com teste executado libera o commit de novo", g.returncode == 0, g.stderr[:200])

    print("\n# critério de pronto — depois de um EMPTY, o card não é declarado feito")

    # Os dois lugares onde "feito" se declara: a transição do card no Jira
    # (acceptance-gate) e o desfecho de item da fila (cepa-plan finish).
    r = make_repo(tmp / "e2e-feito")
    (r / "board-flow.yaml").write_text(BOARD_FLOW, encoding="utf-8")
    acc = r / ".claude" / "acceptance"
    acc.mkdir(parents=True)
    # Artefato COMPLETO: o bloqueio tem de vir do build vazio, não da auditoria.
    (acc / f"{KEY}.yaml").write_text(f"key: {KEY}\nstatus: complete\n", encoding="utf-8")
    itens = r / "itens.json"
    itens.write_text(json.dumps([
        {"id": i, "title": f"item {i}", "why": f"porque {i}", "status": "pending",
         "blocked_by": [], "human_pending": None} for i in ("A", "B")
    ]), encoding="utf-8")
    w = cepa_plan(r, "write", "fila", "--items", str(itens), "--source", "teste",
                  "--quando", "2026-09-25", "--repo", ".")
    check("fila de teste gravada", w.returncode == 0, w.stderr[:300])

    capture(r, "./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest", MAVEN_VAZIO)
    check("pré-condição: baseline EMPTY", (state(r) or {}).get("status") == "EMPTY",
          str(state(r)))

    g = transition(r, "41")
    check("acceptance-gate BARRA a ida para in_review com baseline EMPTY "
          "(mesmo com auditoria complete)", g.returncode == 2,
          f"exit={g.returncode} stderr={g.stderr[:300]}")
    check("…e a mensagem nomeia o build filtrado sem teste e como corrigir",
          "EMPTY" in g.stderr and "zero" in g.stderr.lower()
          and "failIfNoSpecifiedTests=true" in g.stderr, g.stderr[:400])
    g = transition(r, "51")
    check("acceptance-gate BARRA a ida para done com baseline EMPTY", g.returncode == 2,
          g.stderr[:200])
    g = transition(r, "31")
    check("acceptance-gate DEIXA o card voltar para in_progress com baseline EMPTY",
          g.returncode == 0, g.stderr[:200])

    f = cepa_plan(r, "finish", "fila", "A", "--status", "done",
                  "--evidence", "commit abc", "--repo", ".")
    check("cepa-plan finish --status done RECUSA com baseline EMPTY",
          f.returncode != 0, f"exit={f.returncode} out={f.stdout[:200]}")
    check("…e a recusa nomeia o build vazio",
          "EMPTY" in f.stderr and "zero" in f.stderr.lower(), f.stderr[:400])
    f = cepa_plan(r, "finish", "fila", "B", "--status", "blocked",
                  "--evidence", "travou no build vazio", "--repo", ".")
    check("cepa-plan finish --status blocked ACEITA com baseline EMPTY",
          f.returncode == 0, f.stderr[:300])
    f = cepa_plan(r, "finish", "fila", "B", "--status", "pending",
                  "--evidence", "volta para a fila", "--repo", ".")
    check("cepa-plan finish --status pending ACEITA com baseline EMPTY",
          f.returncode == 0, f.stderr[:300])

    # Um verde de verdade depois libera as duas portas.
    capture(r, "./mvnw -pl domain -am test -Dtest=CpfTest", MAVEN_COM_TESTE)
    g = transition(r, "41")
    check("depois de verde com teste, acceptance-gate libera in_review",
          g.returncode == 0, g.stderr[:200])
    f = cepa_plan(r, "finish", "fila", "A", "--status", "done",
                  "--evidence", "commit abc", "--repo", ".")
    check("depois de verde com teste, cepa-plan finish --status done aceita",
          f.returncode == 0, f.stderr[:300])

print("\n# prompts — 'o comando de aceite passou' só vale com N > 0")
for rel in ("build-hex/agents/proof-reviewer.md", "common/agents/completion-auditor.md"):
    text = (REPO / rel).read_text(encoding="utf-8")
    check(f"{rel} exige N > 0 testes executados",
          "N > 0" in text and "EMPTY" in text, "")

print("\n# consumidores em prosa — o green-gate recusa tudo que não é SUCCESS")
for rel in ("common/commands/worktree-merge.md", "common/commands/wrap-up.md"):
    text = (REPO / rel).read_text(encoding="utf-8")
    check(f"{rel} recusa EMPTY no green-gate", "EMPTY" in text, "")

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all verde-sem-teste tests passed")
