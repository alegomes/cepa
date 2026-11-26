#!/usr/bin/env python3
"""cepa-run — Gradle and Maven builds get the same two savings as `tests/run-all.sh`.

Owner, 2026-11-26: "the slowness is not the cepa build alone; Java/Gradle/Maven
projects are hit the most". Contract guarded here:

  - a red `./gradlew ...` that names failed tests repeats only them:
    `./gradlew <task> --tests <Class>`; a red `./mvnw ...` repeats the same
    command with `-Dtest=` and `-Dit.test=` set to the failed classes;
  - a red that names no test (compilation) repeats the whole build;
  - Gradle and Maven stop at the first module that fails, so green on the
    failed tests alone is not green: the whole build runs once more to cover
    the modules that never ran;
  - the full build runs once per pair of `done` items, as with run-all.sh;
  - any other `--verify` keeps one whole build per item and repeats it whole.

The outputs below are cut from real runs (Gradle 9.8.2, Maven 3.10.0 with
surefire 3.2.5, JUnit 5.10.2) of a project with one failing class.

No third-party deps beyond PyYAML — run with `python3 tests/test_cepa_run_java_builds.py`.
"""

import importlib.machinery
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)
from test_cepa_until_run_branch import WORKS, _commits, plan_of, status  # noqa: E402

GRADLE_RED = """\
> Task :app:compileTestJava
> Task :app:processTestResources NO-SOURCE
> Task :app:testClasses

> Task :app:test FAILED

FooTest > bad() FAILED
    org.opentest4j.AssertionFailedError at FooTest.java:5

FooTest > Inner > innerBad() FAILED
    org.opentest4j.AssertionFailedError at FooTest.java:6

3 tests completed, 2 failed

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':app:test'.
> There were failing tests. See the report at: file:///x/index.html

BUILD FAILED in 5s
3 actionable tasks: 3 executed
"""

GRADLE_COMPILE_RED = """\
> Task :app:compileJava FAILED
/x/Foo.java:3: error: ';' expected

FAILURE: Build failed with an exception.

* What went wrong:
Execution failed for task ':app:compileJava'.

BUILD FAILED in 1s
"""

MAVEN_RED = """\
[INFO] Running com.x.FooTest
[INFO] Running com.x.FooTest$Inner
[ERROR] Tests run: 3, Failures: 2, Errors: 0, Skipped: 0, Time elapsed: 0.003 s <<< FAILURE! -- in com.x.FooTest$Inner
[ERROR] com.x.FooTest.bad -- Time elapsed: 0.004 s <<< FAILURE!
org.opentest4j.AssertionFailedError: expected: <1> but was: <2>
[INFO] Tests run: 0, Failures: 0, Errors: 0, Skipped: 0, Time elapsed: 0.025 s -- in com.x.FooTest
[INFO]
[INFO] Results:
[INFO]
[ERROR] Failures:
[ERROR]   FooTest$Inner.innerBad:6 expected: <false> but was: <true>
[ERROR]   FooTest.bad:5 expected: <1> but was: <2>
[ERROR] Errors:
[ERROR]   ChildTest>BaseTest.setUp:12 » Runtime boom
[INFO]
[ERROR] Tests run: 3, Failures: 2, Errors: 0, Skipped: 0
[INFO] ------------------------------------------------------------------------
[ERROR] BUILD FAILURE
[ERROR] Failed to execute goal org.apache.maven.plugins:maven-surefire-plugin:3.2.5:test (default-test) on project m: There are test failures.
[ERROR] -> [Help 1]
"""

# Real: two modules red, `gradle build --continue --parallel`.
GRADLE_RED_TWO_MODULES = """\
> Task :app:testClasses UP-TO-DATE
> Task :lib:compileTestJava
> Task :lib:processTestResources NO-SOURCE
> Task :lib:testClasses

> Task :app:test FAILED

FooTest > bad() FAILED
    org.opentest4j.AssertionFailedError at FooTest.java:5

FooTest > Inner > innerBad() FAILED
    org.opentest4j.AssertionFailedError at FooTest.java:6

3 tests completed, 2 failed

> Task :lib:test FAILED

BarTest > bad() FAILED
    org.opentest4j.AssertionFailedError at BarTest.java:3

1 test completed, 1 failed

FAILURE: Build completed with 2 failures.

1: Task failed with an exception.
-----------
* What went wrong:
Execution failed for task ':app:test'.

* Try:
> Run with --scan to get full insights from a Build Scan (powered by Develocity).
==============================================================================

2: Task failed with an exception.
-----------
* What went wrong:
Execution failed for task ':lib:test'.

* Try:
> Run with --scan to get full insights from a Build Scan (powered by Develocity).
==============================================================================

BUILD FAILED in 1s
6 actionable tasks: 4 executed, 2 up-to-date
"""

# Real: Maven reactor of two modules, `--fail-at-end`; BTest breaks in @BeforeAll.
MAVEN_RED_REACTOR = """\
[INFO] Reactor Build Order:
[INFO]   from pom.xml
[INFO]   from a/pom.xml
[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.019 s <<< FAILURE! -- in com.a.ATest
[INFO] Results:
[ERROR] Failures: 
[ERROR]   ATest.bad:3 x
[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0
[INFO]   from b/pom.xml
[ERROR] Tests run: 1, Failures: 0, Errors: 1, Skipped: 0, Time elapsed: 0.011 s <<< FAILURE! -- in com.b.BTest
[INFO] Results:
[ERROR] Errors: 
[ERROR]   BTest.up:3 IllegalState no
[ERROR] Tests run: 1, Failures: 0, Errors: 1, Skipped: 0
[INFO] Reactor Summary for mm 1:
[INFO] mm ................................................. SUCCESS [  0.119 s]
[ERROR] a .................................................. FAILURE [  1.668 s]
[ERROR] b .................................................. FAILURE [  0.263 s]
[ERROR] BUILD FAILURE
[ERROR]   mvn <args> -rf :a
"""

# Fake build tool: notes (argv, a*.txt it sees); red while `quebra.txt` is in
# the tree it runs in, printing RED_OUTPUT (real tool output).
FAKE_BUILD = (
    "#!/usr/bin/env python3\n"
    "import json, sys\n"
    "from pathlib import Path\n"
    "calls = Path({calls!r})\n"
    "first = not calls.exists()\n"
    "broken = Path('quebra.txt').exists() or ({flaky!r} and first)\n"
    "files = sorted(p.name for p in Path('.').glob('a*.txt'))\n"
    "with calls.open('a') as f:\n"
    "    f.write(json.dumps({{'argv': sys.argv[1:], 'files': files}}) + '\\n')\n"
    "if broken:\n"
    "    print({red!r})\n"
    "    sys.exit(1)\n"
    "print('BUILD SUCCESSFUL')\n")


def module():
    here = Path(__file__).resolve().parent
    loader = importlib.machinery.SourceFileLoader(
        "cepa_run_java", str(here.parent / "common" / "bin" / "cepa-run"))
    spec = importlib.util.spec_from_loader("cepa_run_java", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def run(tmp, ids, tool, verify, red, breaks="", flaky=False):
    root = build_repo(tmp, [item(i) for i in ids])
    calls = Path(tmp) / "build-calls"
    script = root / tool
    script.write_text(FAKE_BUILD.format(calls=str(calls), red=red, flaky=flaky))
    script.chmod(0o755)
    _commits(root, "build tool")
    binv = fake_claude(tmp, WORKS)
    p, _ = run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", verify],
                     extra_env={"FAKE_QUEBRA": breaks})
    seen = ([json.loads(l) for l in calls.read_text().splitlines()]
            if calls.exists() else [])
    return root, p, seen, ledger_of(root)


def ev(ledger, kind, **match):
    return [e for e in ledger if e.get("evento") == kind
            and all(e.get(k) == v for k, v in match.items())]


def test_parsers_read_the_real_outputs():
    mod = module()
    check("gradle: tarefa e classe, uma vez por classe",
          mod.failed_gradle_tests(GRADLE_RED) == [":app:test FooTest"],
          str(mod.failed_gradle_tests(GRADLE_RED)))
    check("gradle: tarefa que falha sem nomear teste devolve lista vazia",
          mod.failed_gradle_tests(GRADLE_COMPILE_RED) == [],
          str(mod.failed_gradle_tests(GRADLE_COMPILE_RED)))
    check("gradle: teste nomeado + outra tarefa sem teste devolve lista vazia",
          mod.failed_gradle_tests(GRADLE_RED + "> Task :lib:compileJava FAILED\n") == [],
          "")
    got = mod.failed_maven_tests(MAVEN_RED)
    check("maven: classes simples, sem a classe interna, com a herdada",
          got == ["FooTest", "ChildTest"], str(got))
    check("maven: falha sem bloco de testes devolve lista vazia",
          mod.failed_maven_tests("[ERROR] BUILD FAILURE\n[ERROR] COMPILATION ERROR :\n") == [],
          "")
    check("gradle real, dois módulos com --continue: uma entrada por módulo",
          mod.failed_gradle_tests(GRADLE_RED_TWO_MODULES)
          == [":app:test FooTest", ":lib:test BarTest"],
          str(mod.failed_gradle_tests(GRADLE_RED_TWO_MODULES)))
    check("maven real, reactor de dois módulos: as classes dos dois",
          mod.failed_maven_tests(MAVEN_RED_REACTOR) == ["ATest", "BTest"],
          str(mod.failed_maven_tests(MAVEN_RED_REACTOR)))
    check("gradle: o comando repete só a tarefa e a classe",
          mod.repeat_command("./gradlew build", [":app:test FooTest", ":lib:test BarTest"])
          == "./gradlew :app:test --tests FooTest :lib:test --tests BarTest", "")
    check("maven: o comando ganha -Dtest e -Dit.test",
          mod.repeat_command("./mvnw -B clean verify", ["FooTest", "ChildTest"])
          == "./mvnw -B clean verify -Dtest=FooTest,ChildTest -Dit.test=FooTest,ChildTest "
             "-Dsurefire.failIfNoSpecifiedTests=false "
             "-Dfailsafe.failIfNoSpecifiedTests=false", "")
    check("gradle: a repetição guarda as opções do comando e troca só as tarefas",
          mod.repeat_command("./gradlew check -Pprofile=ci -x lint --no-daemon",
                             [":a:test FooTest"])
          == "./gradlew -Pprofile=ci -x lint --no-daemon :a:test --tests FooTest",
          mod.repeat_command("./gradlew check -Pprofile=ci -x lint --no-daemon",
                             [":a:test FooTest"]))
    block = "[ERROR] Errors:\n[ERROR]   BarTest.x:3 » Runtime boom\n"
    check("maven: classe que quebra inteira ('FooTest » ...') entra na lista",
          mod.failed_maven_tests(block + "[ERROR]   FooTest » IllegalState no\n")
          == ["BarTest", "FooTest"], "")
    check("maven: método com ponto nos parâmetros dá a classe",
          mod.failed_maven_tests("[ERROR] Failures:\n[ERROR]   FooTest.a(1.5):3 x\n")
          == ["FooTest"], "")
    check("maven: linha que o leitor não entende zera a lista (nunca lista parcial)",
          mod.failed_maven_tests(block + "[ERROR]   Run 1: FooTest.flaky:10 x\n") == [],
          "")
    check("comando composto é tratado como build desconhecido",
          mod.build_kind("./gradlew test && ./gradlew lint") is None
          and mod.build_kind("./mvnw verify && ./mvnw site") is None
          and mod.build_kind("./mvnw verify | tee x.log") is None, "")
    check("build desconhecido não é estreitado",
          mod.build_kind("test ! -f quebra.txt") is None
          and mod.build_kind("npm test") is None
          and mod.repeat_command("npm test", ["x"]) == "npm test", "")


def test_gradle_red_repeats_only_the_failed_class():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1"], "gradlew", "./gradlew build",
                                 GRADLE_RED, breaks="a1")
        check("1ª rodada é o build inteiro", seen[:1] and seen[0]["argv"] == ["build"],
              f"{seen} {p.stdout[-600:]}")
        check("2ª rodada é só a tarefa e a classe com falha",
              len(seen) >= 2 and seen[1]["argv"] == [":app:test", "--tests", "FooTest"],
              str(seen))
        rep = ev(led, "verify", id="a1", repeticao=2)
        check("o registro da repetição nomeia a tarefa e a classe",
              rep and rep[0].get("arquivos") == [":app:test FooTest"], str(rep))
        check("vermelho de novo: a1 não fica done",
              status(root, "a1")["status"] != "done", str(status(root, "a1")))


def test_green_on_the_failed_class_is_followed_by_the_whole_build():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1"], "gradlew", "./gradlew build",
                                 GRADLE_RED, flaky=True)
        check("vermelho, depois só a classe, depois o build inteiro",
              [c["argv"] for c in seen] ==
              [["build"], [":app:test", "--tests", "FooTest"], ["build"]],
              f"{seen} {p.stdout[-600:]}")
        check("o registro marca a 3ª rodada como a que cobre o resto",
              ev(led, "verify", id="a1", repeticao=3, cobre_o_resto=True, verde=True),
              str(led))
        check("a1 fecha done", status(root, "a1")["status"] == "done",
              str(status(root, "a1")))


def test_gradle_compile_red_repeats_the_whole_build():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1"], "gradlew", "./gradlew build",
                                 GRADLE_COMPILE_RED, breaks="a1")
        check("sem teste nomeado a 2ª rodada é o build inteiro",
              [c["argv"] for c in seen[:2]] == [["build"], ["build"]], str(seen))


def test_maven_red_repeats_only_the_failed_classes():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1"], "mvnw", "./mvnw -B clean verify",
                                 MAVEN_RED, breaks="a1")
        check("1ª rodada é o build inteiro",
              seen[:1] and seen[0]["argv"] == ["-B", "clean", "verify"],
              f"{seen} {p.stdout[-600:]}")
        check("2ª rodada leva -Dtest e -Dit.test com as classes",
              len(seen) >= 2 and seen[1]["argv"][:5] ==
              ["-B", "clean", "verify", "-Dtest=FooTest,ChildTest",
               "-Dit.test=FooTest,ChildTest"], str(seen))


def test_gradle_build_runs_once_per_pair_and_blames_the_right_item():
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1", "a2", "a3"], "gradlew",
                                 "./gradlew build", GRADLE_RED)
        check("3 itens done", all(status(root, i)["status"] == "done"
                                  for i in ("a1", "a2", "a3")), p.stdout[-800:])
        check("o build rodou 2 vezes para 3 itens", len(seen) == 2, str(seen))
        check("a2 foi adiado", len(ev(led, "verify_adiado", id="a2")) == 1, str(led))
    with tempfile.TemporaryDirectory() as tmp:
        root, p, seen, led = run(tmp, ["a1", "a2", "a3"], "mvnw",
                                 "./mvnw -B clean verify", MAVEN_RED, breaks="a3")
        mid = ev(led, "verify", id="a2", no_meio=True)
        check("maven: par vermelho roda só as classes com falha no commit do meio",
              len(mid) == 2 and mid[0]["verde"] is True
              and mid[0].get("arquivos") == ["FooTest", "ChildTest"]
              and any(c["files"] == ["a1.txt", "a2.txt"]
                      and "-Dtest=FooTest,ChildTest" in c["argv"] for c in seen),
              f"{mid} {seen}")
        at_mid = [c["argv"] for c in seen if c["files"] == ["a1.txt", "a2.txt"]]
        check("maven: verde nas classes no meio é seguido do build inteiro no meio",
              len(mid) == 2 and mid[-1].get("cobre_o_resto") is True
              and mid[-1]["verde"] is True
              and at_mid[-1] == ["-B", "clean", "verify"], f"{mid} {at_mid}")
        check("maven: a2 fica done e só a3 tem volta vermelha",
              status(root, "a2")["status"] == "done"
              and ev(led, "volta_vermelha", id="a3")
              and not ev(led, "volta_vermelha", id="a2"), str(led))


def test_other_verify_keeps_one_build_per_item():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item(i) for i in ("a1", "a2", "a3")])
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", "test ! -f quebra.txt"])
        led = ledger_of(root)
        check("nenhum item é adiado", not ev(led, "verify_adiado"), str(led))
        firsts = [e for e in ev(led, "verify") if not e.get("repeticao")]
        check("um build por item", [e["id"] for e in firsts] == ["a1", "a2", "a3"],
              str(firsts))


def main():
    print("cepa-run — Gradle e Maven: repetir só o que falhou, um build por par\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
