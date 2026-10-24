#!/usr/bin/env python3
"""Green without any test is not green (item `gate-verde-sem-teste`, BACKLOG).

No dependencies — `python3 tests/test_green_without_test.py`. Exits non-zero on failure.

The defect, measured in wego on 2026-08-24: with `surefire.failIfNoSpecifiedTests=false`
in the pom, `./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest` prints
BUILD SUCCESS without any "Tests run:" line. capture-build-result recorded that
as SUCCESS, gate-advance released the commit, and the card became done without a single
test having run. The same applies to `pytest -k NomeErrado`,
`go test -run NomeErrado` and `npm test -- -t NomeErrado`.

The contract this file guards:

  capture-build-result.py
    - command WITH a test filter + green output + zero tests executed → EMPTY
      (not SUCCESS), with `tests_run: 0` and a named reason;
    - command WITH filter + count > 0 → SUCCESS, with `tests_run`;
    - command WITHOUT filter → behavior as before (does not require a count).

  gate-advance.py (done criterion, end to end)
    - after an EMPTY capture, `git commit` is BLOCKED, and the message says that
      the filter matched zero tests and how to fix it.

  acceptance-gate.py and cepa-plan finish (the other half: "not even declare done")
    - after an EMPTY capture, the card transition to in_review/done is
      BLOCKED even with a `complete` audit; going back to in_progress passes;
    - `cepa-plan finish --status done` refuses; blocked/pending accept;
    - after a green with an executed test, both doors release.

  prompts
    - proof-reviewer and completion-auditor require N > 0 tests executed.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# This test executes hooks that emit telemetry. See tests/_isolated_telemetry.py.
from _isolated_telemetry import isolate

isolate()

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
    """Card transition through mcp-atlassian, in the real acceptance-gate hook."""
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


# ── realistic outputs ─────────────────────────────────────────────────────

MAVEN_EMPTY = """\
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

MAVEN_WITH_TEST = """\
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

MAVEN_EXPLICIT_ZERO = """\
[INFO] Results:
[INFO]
[INFO] Tests run: 0, Failures: 0, Errors: 0, Skipped: 0
[INFO]
[INFO] BUILD SUCCESS
"""

PYTEST_EMPTY = """\
============================= test session starts ==============================
platform darwin -- Python 3.12.4, pytest-8.2.0, pluggy-1.5.0
rootdir: /repo
collected 5 items / 5 deselected / 0 selected

============================ 5 deselected in 0.02s =============================
"""

PYTEST_WITH_TEST = """\
============================= test session starts ==============================
collected 5 items / 3 deselected / 2 selected

tests/test_cpf.py ..                                                     [100%]

======================= 2 passed, 3 deselected in 0.03s ========================
"""

GO_EMPTY = """\
ok  \tgithub.com/wego/acesso/domain\t0.012s [no tests to run]
?   \tgithub.com/wego/acesso/cmd\t[no test files]
"""

GO_WITH_TEST = """\
ok  \tgithub.com/wego/acesso/domain\t0.015s
"""

JEST_EMPTY = """\
> acesso-web@1.0.0 test
> jest -t NomeErrado

No tests found, exiting with code 0
"""

JEST_ALL_SKIPPED = """\
Test Suites: 3 skipped, 0 of 3 total
Tests:       14 skipped, 14 total
Snapshots:   0 total
Time:        1.2 s
"""

JEST_WITH_TEST = """\
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
    capture(r, "./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest", MAVEN_EMPTY)
    s = state(r)
    check("maven -Dtest= com BUILD SUCCESS e nenhum 'Tests run:' → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))
    check("maven vazio grava tests_run 0",
          s is not None and s.get("tests_run") == 0, str(s))
    check("maven vazio nomeia o motivo (filtro casou zero teste)",
          s is not None and "zero" in (s.get("reason") or "").lower(), str(s))

    r = make_repo(tmp / "mvn-zero")
    capture(r, "./mvnw test -Dtest=Nada", MAVEN_EXPLICIT_ZERO)
    s = state(r)
    check("maven -Dtest= com 'Tests run: 0' explícito → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "mvn-ok")
    capture(r, "./mvnw -pl domain -am test -Dtest=CpfTest", MAVEN_WITH_TEST)
    s = state(r)
    check("maven -Dtest= com 'Tests run: 3' → SUCCESS",
          s is not None and s.get("status") == "SUCCESS", str(s))
    check("maven com teste grava tests_run > 0",
          s is not None and (s.get("tests_run") or 0) > 0, str(s))

    r = make_repo(tmp / "mvn-sem-filtro")
    capture(r, "./mvnw verify", MAVEN_EMPTY)
    s = state(r)
    check("maven SEM filtro e sem 'Tests run:' continua SUCCESS (fora de escopo)",
          s is not None and s.get("status") == "SUCCESS", str(s))

    r = make_repo(tmp / "py-vazio")
    capture(r, "pytest -k NomeErrado", PYTEST_EMPTY, exit_code=0)
    s = state(r)
    check("pytest -k com '5 deselected' e nada passou → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "py-exit5")
    capture(r, "pytest -k NomeErrado", PYTEST_EMPTY, exit_code=5)
    s = state(r)
    check("pytest -k saindo 5 (nada coletado) nunca vira SUCCESS",
          s is not None and s.get("status") != "SUCCESS", str(s))

    r = make_repo(tmp / "py-ok")
    capture(r, "pytest -k cpf", PYTEST_WITH_TEST, exit_code=0)
    s = state(r)
    check("pytest -k com '2 passed' → SUCCESS",
          s is not None and s.get("status") == "SUCCESS" and s.get("tests_run") == 2, str(s))

    r = make_repo(tmp / "go-vazio")
    capture(r, "go test ./... -run NomeErrado", GO_EMPTY, exit_code=0)
    s = state(r)
    check("go test -run com '[no tests to run]' → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "go-ok")
    capture(r, "go test ./domain -run=TestCpf", GO_WITH_TEST, exit_code=0)
    s = state(r)
    check("go test -run= com 'ok pkg' sem '[no tests to run]' → SUCCESS",
          s is not None and s.get("status") == "SUCCESS", str(s))

    r = make_repo(tmp / "jest-vazio")
    capture(r, "npm test -- -t NomeErrado", JEST_EMPTY, exit_code=0)
    s = state(r)
    check("jest -t com 'No tests found' → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "jest-pulado")
    capture(r, "npm test -- --testNamePattern=NomeErrado", JEST_ALL_SKIPPED, exit_code=0)
    s = state(r)
    check("jest --testNamePattern= com tudo 'skipped' → EMPTY",
          s is not None and s.get("status") == "EMPTY", str(s))

    r = make_repo(tmp / "jest-ok")
    capture(r, "npm test -- -t cpf", JEST_WITH_TEST, exit_code=0)
    s = state(r)
    check("jest -t com 'Tests: 2 passed' → SUCCESS",
          s is not None and s.get("status") == "SUCCESS" and s.get("tests_run") == 2, str(s))

    print("\n# critério de pronto — depois de um EMPTY, o commit não passa")

    r = make_repo(tmp / "e2e")
    capture(r, "./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest", MAVEN_EMPTY)
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

    # A real green afterwards clears the block.
    capture(r, "./mvnw -pl domain -am test -Dtest=CpfTest", MAVEN_WITH_TEST)
    g = run_hook(GATE, {
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'feat: card feito'"},
        "cwd": str(r),
    })
    check("verde com teste executado libera o commit de novo", g.returncode == 0, g.stderr[:200])

    print("\n# critério de pronto — depois de um EMPTY, o card não é declarado feito")

    # The two places where "done" is declared: the card transition in Jira
    # (acceptance-gate) and the queue item outcome (cepa-plan finish).
    r = make_repo(tmp / "e2e-feito")
    (r / "board-flow.yaml").write_text(BOARD_FLOW, encoding="utf-8")
    acc = r / ".claude" / "acceptance"
    acc.mkdir(parents=True)
    # COMPLETE artifact: the block must come from the empty build, not from the audit.
    (acc / f"{KEY}.yaml").write_text(f"key: {KEY}\nstatus: complete\n", encoding="utf-8")
    items = r / "itens.json"
    items.write_text(json.dumps([
        {"id": i, "title": f"item {i}", "why": f"porque {i}", "status": "pending",
         "blocked_by": [], "human_pending": None} for i in ("A", "B")
    ]), encoding="utf-8")
    w = cepa_plan(r, "write", "fila", "--items", str(items), "--source", "teste",
                  "--quando", "2026-09-25", "--repo", ".")
    check("fila de teste gravada", w.returncode == 0, w.stderr[:300])

    capture(r, "./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest", MAVEN_EMPTY)
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

    # A real green afterwards releases both doors.
    capture(r, "./mvnw -pl domain -am test -Dtest=CpfTest", MAVEN_WITH_TEST)
    g = transition(r, "41")
    check("depois de verde com teste, acceptance-gate libera in_review",
          g.returncode == 0, g.stderr[:200])
    f = cepa_plan(r, "finish", "fila", "A", "--status", "done",
                  "--evidence", "commit abc", "--repo", ".")
    check("depois de verde com teste, cepa-plan finish --status done aceita",
          f.returncode == 0, f.stderr[:300])

    print("\n# worktree ligada — a baseline é a da worktree, não a do clone principal")

    # The queue lives in the main clone (shared between worktrees); the
    # build baseline is of EACH worktree. Reading the main clone's one let
    # `finish done` pass in a linked worktree with an EMPTY build, and blocked
    # a green worktree because of another's EMPTY.
    main_clone = make_repo(tmp / "wt-principal")
    (main_clone / "board-flow.yaml").write_text(BOARD_FLOW, encoding="utf-8")
    (main_clone / "sub").mkdir()
    (main_clone / "sub" / "LEIAME").write_text("x\n", encoding="utf-8")
    git(["add", "-A"], main_clone)
    c = git(["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base"], main_clone)
    check("pré-condição: commit no clone principal", c.returncode == 0, c.stderr[:200])
    linked = tmp / "wt-ligada"
    a = git(["worktree", "add", "-q", str(linked), "-b", "x"], main_clone)
    check("pré-condição: worktree ligada criada", a.returncode == 0, a.stderr[:200])

    w = cepa_plan(linked, "write", "fila", "--items", str(items), "--source", "teste",
                  "--quando", "2026-09-25", "--repo", str(linked))
    check("fila gravada a partir da worktree ligada", w.returncode == 0, w.stderr[:300])
    check("…e mora no clone principal",
          (main_clone / ".claude" / "queues" / "fila" / "queue.yaml").exists()
          and not (linked / ".claude" / "queues" / "fila" / "queue.yaml").exists(), "")

    capture(linked, "./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest",
            MAVEN_EMPTY)
    check("pré-condição: EMPTY só na worktree ligada",
          (state(linked) or {}).get("status") == "EMPTY" and state(main_clone) is None,
          f"ligada={state(linked)} principal={state(main_clone)}")
    f = cepa_plan(linked, "finish", "fila", "A", "--status", "done",
                  "--evidence", "commit abc", "--repo", str(linked))
    check("finish done --repo <worktree ligada> RECUSA com EMPTY na worktree ligada",
          f.returncode == 2, f"exit={f.returncode} err={f.stderr[:300]}")
    check("…e a recusa cita o last-build.json da worktree ligada",
          str(linked / ".claude" / "last-build.json") in f.stderr
          or str((linked / ".claude" / "last-build.json").resolve()) in f.stderr,
          f.stderr[:400])
    f = cepa_plan(linked / "sub", "finish", "fila", "A", "--status", "done",
                  "--evidence", "commit abc", "--repo", str(linked / "sub"))
    check("finish done --repo <subdir da worktree ligada> também RECUSA",
          f.returncode == 2, f"exit={f.returncode} err={f.stderr[:300]}")

    (linked / ".claude" / "acceptance").mkdir(parents=True, exist_ok=True)
    (linked / ".claude" / "acceptance" / f"{KEY}.yaml").write_text(
        f"key: {KEY}\nstatus: complete\n", encoding="utf-8")
    g = transition(linked, "41")
    check("acceptance-gate BARRA in_review com EMPTY na worktree ligada (cwd = ela)",
          g.returncode == 2, f"exit={g.returncode} stderr={g.stderr[:300]}")
    g = transition(linked / "sub", "41")
    check("acceptance-gate BARRA in_review com cwd = subdir da worktree ligada",
          g.returncode == 2, f"exit={g.returncode} stderr={g.stderr[:300]}")

    # The inverse: green in the linked worktree, EMPTY only in the main clone.
    capture(linked, "./mvnw -pl domain -am test -Dtest=CpfTest", MAVEN_WITH_TEST)
    capture(main_clone, "./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest",
            MAVEN_EMPTY)
    check("pré-condição: SUCCESS na ligada, EMPTY só no principal",
          (state(linked) or {}).get("status") == "SUCCESS"
          and (state(main_clone) or {}).get("status") == "EMPTY",
          f"ligada={state(linked)} principal={state(main_clone)}")
    g = transition(linked, "41")
    check("acceptance-gate NÃO barra a worktree ligada verde pelo EMPTY do principal",
          g.returncode == 0, f"exit={g.returncode} stderr={g.stderr[:300]}")
    f = cepa_plan(linked, "finish", "fila", "A", "--status", "done",
                  "--evidence", "commit abc", "--repo", str(linked))
    check("finish done --repo <worktree ligada> ACEITA com EMPTY só no clone principal",
          f.returncode == 0, f"exit={f.returncode} err={f.stderr[:300]}")

    print("\n# EMPTY que virou STALE — editar depois do build vazio não limpa o bloqueio")

    MARK_STALE = HOOKS / "mark-build-stale.py"

    def edit(repo, rel):
        return run_hook(MARK_STALE, {
            "tool_name": "Edit",
            "tool_input": {"file_path": str(repo / rel)},
            "cwd": str(repo),
        })

    r = make_repo(tmp / "e2e-stale")
    (r / "board-flow.yaml").write_text(BOARD_FLOW, encoding="utf-8")
    acc = r / ".claude" / "acceptance"
    acc.mkdir(parents=True)
    (acc / f"{KEY}.yaml").write_text(f"key: {KEY}\nstatus: complete\n", encoding="utf-8")
    w = cepa_plan(r, "write", "fila", "--items", str(items), "--source", "teste",
                  "--quando", "2026-09-25", "--repo", ".")
    check("fila de teste gravada (stale)", w.returncode == 0, w.stderr[:300])

    capture(r, "./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest", MAVEN_EMPTY)
    edit(r, "domain/src/main/java/Cpf.java")
    s = state(r) or {}
    check("pré-condição: EMPTY + edição de fonte → STALE com last_known_status EMPTY",
          s.get("status") == "STALE" and s.get("last_known_status") == "EMPTY", str(s))
    g = transition(r, "41")
    check("acceptance-gate BARRA in_review com STALE herdado de EMPTY",
          g.returncode == 2, f"exit={g.returncode} stderr={g.stderr[:300]}")
    check("…e a mensagem diz que a última execução casou zero teste e o código mudou",
          "zero" in g.stderr.lower() and "changed" in g.stderr.lower(), g.stderr[:500])
    f = cepa_plan(r, "finish", "fila", "A", "--status", "done",
                  "--evidence", "commit abc", "--repo", ".")
    check("finish done RECUSA com STALE herdado de EMPTY",
          f.returncode == 2, f"exit={f.returncode} err={f.stderr[:300]}")
    check("…e a recusa diz que o código mudou desde o build vazio",
          "zero" in f.stderr.lower() and "mudou" in f.stderr.lower(), f.stderr[:500])
    f = cepa_plan(r, "finish", "fila", "B", "--status", "blocked",
                  "--evidence", "travou", "--repo", ".")
    check("finish blocked ACEITA com STALE herdado de EMPTY",
          f.returncode == 0, f.stderr[:300])

    # A second edit must not erase the lineage (STALE → STALE).
    edit(r, "domain/src/main/java/Rg.java")
    s = state(r) or {}
    check("segunda edição mantém last_known_status EMPTY (não vira STALE)",
          s.get("status") == "STALE" and s.get("last_known_status") == "EMPTY", str(s))
    g = transition(r, "51")
    check("acceptance-gate BARRA done depois de duas edições sobre um EMPTY",
          g.returncode == 2, f"exit={g.returncode} stderr={g.stderr[:300]}")
    f = cepa_plan(r, "finish", "fila", "A", "--status", "done",
                  "--evidence", "commit abc", "--repo", ".")
    check("finish done RECUSA depois de duas edições sobre um EMPTY",
          f.returncode == 2, f"exit={f.returncode} err={f.stderr[:300]}")

    # An ordinary STALE (last real run SUCCESS) is not the business of these doors:
    # whoever charges for a new build before the commit is gate-advance.
    capture(r, "./mvnw -pl domain -am test -Dtest=CpfTest", MAVEN_WITH_TEST)
    edit(r, "domain/src/main/java/Cpf.java")
    s = state(r) or {}
    check("pré-condição: SUCCESS + edição → STALE com last_known_status SUCCESS",
          s.get("status") == "STALE" and s.get("last_known_status") == "SUCCESS", str(s))
    g = transition(r, "41")
    check("acceptance-gate NÃO barra STALE herdado de SUCCESS",
          g.returncode == 0, f"exit={g.returncode} stderr={g.stderr[:300]}")
    f = cepa_plan(r, "finish", "fila", "A", "--status", "done",
                  "--evidence", "commit abc", "--repo", ".")
    check("finish done ACEITA STALE herdado de SUCCESS",
          f.returncode == 0, f"exit={f.returncode} err={f.stderr[:300]}")

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
