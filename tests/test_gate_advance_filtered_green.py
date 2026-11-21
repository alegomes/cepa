#!/usr/bin/env python3
"""Contract tests: a filtered green (`-Dtest=A`) does not release a commit that B covers.

No third-party dependency — run with `python3 tests/test_gate_advance_filtered_green.py`.

The defect (fb-20261109-2, wego-digitacao-backend, C1-17): an agent ran `verify`
with `-Dtest=OpenApiFechadoParaAnonimoE2ETest` only, the green released commit
08a623f, and `ContratoDaLeituraPublicadoTest` was red. gate-advance read the
status of the last build, never what that build covered.

The rule (2026-11-21):
  - capture-build-result records the Maven test filter (`-Dtest=` / `-Dit.test=`,
    comma-separated, as typed) in last-build.json as `test_filter`;
  - with a SUCCESS baseline that carries `test_filter`, a LOCAL `git commit` is
    refused when a test the filter did not run covers the commit: a JVM test file
    in the commit, or a JVM test that names (whole word) the class of a JVM
    production file in the commit;
  - an unfiltered SUCCESS, a production file no test names, and every SHARING
    operation keep today's behavior.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from _isolated_telemetry import isolate

isolate()

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(args, cwd):
    return subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, text=True)


PROD = "src/main/java/app/LeituraLote.java"
OTHER_PROD = "src/main/java/app/Isolada.java"
E2E = "src/test/java/app/OpenApiFechadoParaAnonimoE2ETest.java"
CONTRATO = "src/test/java/app/ContratoDaLeituraPublicadoTest.java"
HELPER = "src/test/java/app/LeituraFixtures.java"


def make_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "-q", "-b", "main"], path)
    git(["config", "user.email", "t@t"], path)
    git(["config", "user.name", "t"], path)
    files = {
        "pom.xml": "<project/>",
        ".gitignore": ".claude/\n",
        PROD: "package app; public class LeituraLote { }",
        OTHER_PROD: "package app; public class Isolada { }",
        E2E: "package app; class OpenApiFechadoParaAnonimoE2ETest { void t() { } }",
        CONTRATO: "package app; class ContratoDaLeituraPublicadoTest { LeituraLote l; LeituraFixtures f; }",
        # a helper under the test tree is not a test surefire runs
        HELPER: "package app; class LeituraFixtures { LeituraLote l; }",
    }
    for rel, text in files.items():
        p = path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(["add", "-A"], path)
    git(["commit", "-qm", "seed"], path)
    return path


def baseline(repo, status="SUCCESS", **extra):
    (repo / ".claude").mkdir(exist_ok=True)
    state = {"status": status, "at": "2026-11-21T10:00:00+00:00",
             "command": "./mvnw verify", "kind": "maven", "tail": "BUILD SUCCESS"}
    state.update(extra)
    (repo / ".claude" / "last-build.json").write_text(json.dumps(state), encoding="utf-8")


def edit(repo, rel, text, add=True):
    p = repo / rel
    p.write_text(text, encoding="utf-8")
    if add:
        git(["add", rel], repo)


def gate(command, cwd):
    return subprocess.run(
        [sys.executable, str(HOOKS / "gate-advance.py")],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                          "cwd": str(cwd)}),
        capture_output=True, text=True)


def capture(command, stdout, cwd):
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd),
               "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False,
                                 "exitCode": 0}}
    subprocess.run([sys.executable, str(HOOKS / "capture-build-result.py")],
                   input=json.dumps(payload), text=True, capture_output=True, cwd=str(cwd))
    return json.loads((cwd / ".claude" / "last-build.json").read_text(encoding="utf-8"))


MVN_GREEN = (
    "[INFO] Tests run: 3, Failures: 0, Errors: 0, Skipped: 0\n"
    "[INFO] BUILD SUCCESS\n"
)

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp).resolve()

    print("\n# a. capture grava o filtro -Dtest= / -Dit.test= no last-build.json")
    r = make_repo(tmp / "a")
    st = capture('./mvnw -pl api -am verify -Dtest="OpenApiFechadoParaAnonimoE2ETest,Foo#bar"'
                 " -Dit.test=BarIT -Dsurefire.failIfNoSpecifiedTests=false", MVN_GREEN, r)
    check("a: SUCCESS", st.get("status") == "SUCCESS", json.dumps(st)[:300])
    check("a: test_filter com os três padrões, como digitados",
          st.get("test_filter") == ["OpenApiFechadoParaAnonimoE2ETest", "Foo#bar", "BarIT"],
          json.dumps(st)[:300])
    st = capture("./mvnw verify", MVN_GREEN, r)
    check("a: build sem filtro não grava test_filter", "test_filter" not in st,
          json.dumps(st)[:300])

    print("\n# b. o caso do C1-17: -Dtest=A verde, commit muda código que B usa")
    r = make_repo(tmp / "b")
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    edit(r, PROD, "package app; public class LeituraLote { int x; }")
    res = gate('git commit -m "feat: leitura"', r)
    check("b: exit 2", res.returncode == 2, f"exit={res.returncode} {res.stderr[:400]}")
    check("b: nomeia o teste que não rodou",
          "ContratoDaLeituraPublicadoTest" in res.stderr, res.stderr[:600])
    check("b: helper do diretório de teste não é cobrado",
          "LeituraFixtures" not in res.stderr, res.stderr[:600])
    check("b: diz qual arquivo do commit ele cobre", PROD in res.stderr, res.stderr[:600])

    print("\n# c. o filtro inclui B (lista, curinga, Classe#metodo) -> liberado")
    for i, flt in enumerate((["OpenApiFechadoParaAnonimoE2ETest", "ContratoDaLeituraPublicadoTest"],
                             ["Contrato*"], ["ContratoDaLeituraPublicadoTest#deveX"],
                             ["app/**/*Test"])):
        r = make_repo(tmp / f"c{i}")
        baseline(r, test_filter=flt)
        edit(r, PROD, "package app; public class LeituraLote { int x; }")
        res = gate('git commit -m "feat"', r)
        check(f"c{i}: {flt} exit 0", res.returncode == 0,
              f"exit={res.returncode} {res.stderr[:300]}")

    print("\n# d. exclusão no filtro (!B) não cobre B")
    r = make_repo(tmp / "d")
    baseline(r, test_filter=["*Test", "!ContratoDaLeituraPublicadoTest"])
    edit(r, PROD, "package app; public class LeituraLote { int x; }")
    res = gate('git commit -m "feat"', r)
    check("d: exit 2", res.returncode == 2, f"exit={res.returncode} {res.stderr[:300]}")

    print("\n# e. baseline verde sem filtro -> como hoje")
    r = make_repo(tmp / "e")
    baseline(r)
    edit(r, PROD, "package app; public class LeituraLote { int x; }")
    res = gate('git commit -m "feat"', r)
    check("e: exit 0", res.returncode == 0, f"exit={res.returncode} {res.stderr[:300]}")

    print("\n# f. arquivo de produção que nenhum teste nomeia -> liberado")
    r = make_repo(tmp / "f")
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    edit(r, OTHER_PROD, "package app; public class Isolada { int x; }")
    res = gate('git commit -m "feat"', r)
    check("f: exit 0", res.returncode == 0, f"exit={res.returncode} {res.stderr[:300]}")

    print("\n# g. commit muda um teste que o filtro não rodou")
    r = make_repo(tmp / "g")
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    edit(r, CONTRATO, "package app; class ContratoDaLeituraPublicadoTest { int y; }")
    res = gate('git commit -m "test"', r)
    check("g: exit 2", res.returncode == 2, f"exit={res.returncode} {res.stderr[:300]}")
    check("g: nomeia o teste", "ContratoDaLeituraPublicadoTest" in res.stderr, res.stderr[:400])

    print("\n# h. git commit -am (lista de arquivos não inspecionável) -> usa o diff contra HEAD")
    r = make_repo(tmp / "h")
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    edit(r, PROD, "package app; public class LeituraLote { int x; }", add=False)
    res = gate('git commit -am "feat"', r)
    check("h: exit 2", res.returncode == 2, f"exit={res.returncode} {res.stderr[:300]}")

    print("\n# i. git add + commit no mesmo comando")
    r = make_repo(tmp / "i")
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    edit(r, PROD, "package app; public class LeituraLote { int x; }", add=False)
    res = gate(f'git add {PROD} && git commit -m "feat"', r)
    check("i: exit 2", res.returncode == 2, f"exit={res.returncode} {res.stderr[:300]}")

    print("\n# j. push não muda (o commit já passou pela trava), mesmo com árvore suja")
    r = make_repo(tmp / "j")
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    edit(r, PROD, "package app; public class LeituraLote { int x; }", add=False)
    res = gate("git push origin main", r)
    check("j: exit 0", res.returncode == 0, f"exit={res.returncode} {res.stderr[:300]}")

    print("\n# l. nome de classe contido em outro (Leitura x LeituraLote) não casa")
    r = make_repo(tmp / "l")
    edit(r, "src/main/java/app/Leitura.java", "package app; public class Leitura { }")
    git(["commit", "-qm", "leitura"], r)
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    edit(r, "src/main/java/app/Leitura.java", "package app; public class Leitura { int x; }")
    res = gate('git commit -m "feat"', r)
    check("l: exit 0", res.returncode == 0, f"exit={res.returncode} {res.stderr[:300]}")

    print("\n# m. --amend carrega os arquivos do commit anterior")
    r = make_repo(tmp / "m")
    edit(r, PROD, "package app; public class LeituraLote { int x; }")
    git(["commit", "-qm", "feat"], r)
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    res = gate('git commit --amend -m "feat"', r)
    check("m: exit 2", res.returncode == 2, f"exit={res.returncode} {res.stderr[:300]}")

    print("\n# n. erro dentro da checagem libera, com aviso (como um verde fazia antes)")
    r = make_repo(tmp / "n")
    baseline(r, test_filter=[123])
    edit(r, PROD, "package app; public class LeituraLote { int x; }")
    res = gate('git commit -m "feat"', r)
    check("n: exit 0", res.returncode == 0, f"exit={res.returncode} {res.stderr[:300]}")
    check("n: avisa que não conseguiu checar", "could not check" in res.stderr, res.stderr[:300])

    print("\n# k. a mensagem diz como sair: incluir o teste no filtro ou rodar sem filtro")
    r = make_repo(tmp / "k")
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    edit(r, PROD, "package app; public class LeituraLote { int x; }")
    res = gate('git commit -m "feat"', r)
    check("k: sugere -Dtest com o teste que falta",
          "-Dtest=OpenApiFechadoParaAnonimoE2ETest,ContratoDaLeituraPublicadoTest" in res.stderr,
          res.stderr[:700])

    print("\n# o. helper do diretório de teste alterado cobra os testes que o usam")
    r = make_repo(tmp / "o")
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest"])
    edit(r, HELPER, "package app; class LeituraFixtures { LeituraLote l; int y; }")
    res = gate('git commit -m "test: fixtures"', r)
    check("o: exit 2", res.returncode == 2, f"exit={res.returncode} {res.stderr[:300]}")
    check("o: nomeia o teste que usa o helper",
          "ContratoDaLeituraPublicadoTest" in res.stderr, res.stderr[:400])

    print("\n# p. teste novo, ainda fora do git, que usa a classe alterada também conta")
    r = make_repo(tmp / "p")
    baseline(r, test_filter=["OpenApiFechadoParaAnonimoE2ETest", "ContratoDaLeituraPublicadoTest"])
    (r / "src/test/java/app/LeituraNovaTest.java").write_text(
        "package app; class LeituraNovaTest { LeituraLote l; }", encoding="utf-8")
    edit(r, PROD, "package app; public class LeituraLote { int x; }")
    res = gate('git commit -m "feat"', r)
    check("p: exit 2", res.returncode == 2, f"exit={res.returncode} {res.stderr[:300]}")
    check("p: nomeia o teste fora do git", "LeituraNovaTest" in res.stderr, res.stderr[:400])

    print("\n# q. teste alterado que está no filtro não cobra quem só cita o nome dele")
    r = make_repo(tmp / "q")
    edit(r, "src/test/java/app/IndiceTest.java",
         "package app; class IndiceTest { /* ver ContratoDaLeituraPublicadoTest */ }")
    git(["commit", "-qm", "indice"], r)
    baseline(r, test_filter=["ContratoDaLeituraPublicadoTest"])
    edit(r, CONTRATO, "package app; class ContratoDaLeituraPublicadoTest { int z; }")
    res = gate('git commit -m "test"', r)
    check("q: exit 0", res.returncode == 0, f"exit={res.returncode} {res.stderr[:300]}")

if FAILURES:
    print(f"\n{len(FAILURES)} falha(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("\nok")
