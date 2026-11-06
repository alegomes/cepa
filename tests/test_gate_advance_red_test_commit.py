#!/usr/bin/env python3
"""Contract tests: gate-advance lets a tests-only LOCAL commit through on a red TEST baseline.

No third-party dependency — run with `python3 tests/test_gate_advance_red_test_commit.py`.

The defect, seen on 2026-11-04 (run WEGOP1/2026-11-04-2112, cards WEGO-2511, 2513,
2514, 2515): the test-first rule says to commit the red regression test BEFORE the
fix, but gate-advance blocked every `git commit` while `.claude/last-build.json` was
FAILURE. The agent committed the tests only after green, destroying the
"regression red at base" evidence that proof-reviewer demands for bugs.

The rule (2026-11-05): a LOCAL `git commit` is allowed (with a loud warning) when the
baseline is FAILURE of TESTS (read from the state's `tail`; `kind` is the build tool,
not the failure type) and every file the commit would include is a test file.
Compilation/collection failures, production files in the commit, undeterminable file
lists, STALE/EMPTY and any SHARING operation (push/PR/deploy) keep the block.
"""

import importlib.util
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


def make_repo(path):
    path.mkdir(parents=True, exist_ok=True)
    git(["init", "-q", "-b", "main"], path)
    git(["config", "user.email", "t@t"], path)
    git(["config", "user.name", "t"], path)
    (path / "pom.xml").write_text("<project/>", encoding="utf-8")
    (path / ".gitignore").write_text(".claude/\n", encoding="utf-8")  # the state file is not content
    (path / "src/main/java").mkdir(parents=True)
    (path / "src/main/java/Foo.java").write_text("class Foo {}", encoding="utf-8")
    git(["add", "-A"], path)
    git(["commit", "-qm", "seed"], path)
    return path


def baseline(repo, status, tail="", **extra):
    (repo / ".claude").mkdir(exist_ok=True)
    state = {"status": status, "at": "2026-11-05T10:00:00+00:00",
             "command": "./mvnw verify", "kind": "maven", "tail": tail}
    state.update(extra)
    (repo / ".claude" / "last-build.json").write_text(json.dumps(state), encoding="utf-8")


def stage(repo, rel, text="x"):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    git(["add", rel], repo)


def gate(command, cwd):
    return subprocess.run(
        [sys.executable, str(HOOKS / "gate-advance.py")],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command},
                          "cwd": str(cwd)}),
        capture_output=True, text=True)


MVN_TEST_TAIL = (
    "[ERROR] Tests run: 1, Failures: 1, Errors: 0, Skipped: 0\n"
    "[ERROR] FooTest.shouldWork  Time elapsed: 0.01 s  <<< FAILURE!\n"
    "[ERROR] Failed to execute goal org.apache.maven.plugins:maven-surefire-plugin:3.0.0:test\n"
    "[INFO] BUILD FAILURE"
)
MVN_COMPILE_TAIL = (
    "[ERROR] COMPILATION ERROR :\n"
    "[ERROR] /x/FooTest.java:[3,9] cannot find symbol\n"
    "[ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:3.8.1:testCompile\n"
    "[INFO] BUILD FAILURE"
)
PYTEST_TAIL = "FAILED tests/test_x.py::test_a - assert 1 == 2\n== 1 failed, 9 passed in 0.02s =="
PYTEST_COLLECT_TAIL = (
    "ERROR tests/test_x.py\n!!!! Interrupted: 1 error during collection !!!!\n"
    "== 1 error in 0.10s =="
)

TEST_FILE = "src/test/java/FooTest.java"

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp).resolve()

    print("\n# a. teste vermelho Maven, só o teste staged")
    r1 = make_repo(tmp / "a")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    stage(r1, TEST_FILE)
    r = gate('git commit -m "test: red"', r1)
    check("a: exit 0", r.returncode == 0, f"exit={r.returncode} {r.stderr[:300]}")
    check("a: aviso ALLOWED WITH WARNING + red",
          "ALLOWED WITH WARNING" in r.stderr and "red" in r.stderr, r.stderr[:300])

    print("\n# b. teste + arquivo de produção staged")
    r1 = make_repo(tmp / "b")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    stage(r1, TEST_FILE)
    stage(r1, "src/main/java/Foo.java", "class Foo { int x; }")
    r = gate('git commit -m "fix"', r1)
    check("b: exit 2", r.returncode == 2, f"exit={r.returncode} {r.stderr[:300]}")
    check("b: nomeia o arquivo de produção", "src/main/java/Foo.java" in r.stderr, r.stderr[:400])

    print("\n# c. falha de compilação")
    r1 = make_repo(tmp / "c")
    baseline(r1, "FAILURE", MVN_COMPILE_TAIL)
    stage(r1, TEST_FILE)
    r = gate('git commit -m "test"', r1)
    check("c: exit 2", r.returncode == 2, f"exit={r.returncode} {r.stderr[:300]}")
    check("c: menciona compilation", "compilation" in r.stderr, r.stderr[:400])

    print("\n# d. git push nunca é isento")
    r1 = make_repo(tmp / "d")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    stage(r1, TEST_FILE)
    r = gate("git push origin main", r1)
    check("d: push exit 2", r.returncode == 2, f"exit={r.returncode} {r.stderr[:300]}")

    print("\n# e. STALE")
    r1 = make_repo(tmp / "e")
    baseline(r1, "STALE", "", after_edit_to="x", since="2026-11-05T10:00:00+00:00")
    stage(r1, TEST_FILE)
    r = gate('git commit -m "test"', r1)
    check("e: STALE exit 2", r.returncode == 2, f"exit={r.returncode} {r.stderr[:300]}")

    print("\n# f. commit -am traz o arquivo de produção modificado e não staged")
    r1 = make_repo(tmp / "f")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    stage(r1, TEST_FILE)
    (r1 / "src/main/java/Foo.java").write_text("class Foo { int y; }", encoding="utf-8")
    r = gate('git commit -am "x"', r1)
    check("f: -am exit 2", r.returncode == 2, f"exit={r.returncode} {r.stderr[:300]}")
    r = gate('git commit -m "x"', r1)
    check("f: sem -a, o não staged fica de fora, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")

    print("\n# g. pytest com testes falhando")
    r1 = make_repo(tmp / "g")
    baseline(r1, "FAILURE", PYTEST_TAIL, kind="pytest")
    stage(r1, "tests/test_x.py")
    r = gate('git commit -m "test"', r1)
    check("g: exit 0", r.returncode == 0, f"exit={r.returncode} {r.stderr[:300]}")

    print("\n# h. pytest com erro de coleta")
    r1 = make_repo(tmp / "h")
    baseline(r1, "FAILURE", PYTEST_COLLECT_TAIL, kind="pytest")
    stage(r1, "tests/test_x.py")
    r = gate('git commit -m "test"', r1)
    check("h: exit 2", r.returncode == 2, f"exit={r.returncode} {r.stderr[:300]}")

    print("\n# i. nada staged, fail-closed")
    r1 = make_repo(tmp / "i")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    r = gate('git commit -m x', r1)
    check("i: exit 2", r.returncode == 2, f"exit={r.returncode} {r.stderr[:300]}")
    check("i: dica 'no files found'", "no files found for this commit" in r.stderr, r.stderr[:400])

    print("\n# extras: build parado pelo CC, tail ausente")
    r1 = make_repo(tmp / "k")
    baseline(r1, "FAILURE", MVN_TEST_TAIL, stopped_by="claude-code")
    stage(r1, TEST_FILE)
    r = gate('git commit -m x', r1)
    check("k: stopped_by claude-code exit 2", r.returncode == 2, f"exit={r.returncode}")
    r1 = make_repo(tmp / "l")
    baseline(r1, "FAILURE", "")
    stage(r1, TEST_FILE)
    r = gate('git commit -m x', r1)
    check("l: sem tail exit 2", r.returncode == 2, f"exit={r.returncode}")

    print("\n# m-q. git add + git commit no MESMO comando (índice vazio quando o hook roda)")
    def untracked(repo, rel, text="x"):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")

    r1 = make_repo(tmp / "m")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, TEST_FILE)
    r = gate(f"git add {TEST_FILE} && git commit -m x", r1)
    check("m: add + commit só de teste, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "n")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, TEST_FILE)
    (r1 / "src/main/java/Foo.java").write_text("class Foo { int z; }", encoding="utf-8")
    r = gate("git add -A && git commit -m x", r1)
    check("n: add -A traz a produção, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    check("n: nomeia o arquivo de produção", "src/main/java/Foo.java" in r.stderr, r.stderr[:400])

    r1 = make_repo(tmp / "o")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, "src/test/java/BarTest.java")
    r = gate("git add src/test && git commit -m x", r1)
    check("o: add de diretório, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "p")
    outside = tmp / "p_outside"
    outside.mkdir()
    baseline(r1, "FAILURE", PYTEST_TAIL, kind="pytest")
    untracked(r1, "tests/test_x.py")
    r = gate(f"cd {r1} && git add tests/test_x.py && git commit -m x", outside)
    check("p: cd repo && add && commit, cwd fora do repo, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")
    r1 = make_repo(tmp / "p2")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, TEST_FILE)
    untracked(r1, "src/main/java/New.java")
    r = gate(f"git -C {r1} add {TEST_FILE} src/main/java/New.java && git -C {r1} commit -m x", outside)
    check("p2: git -C add com produção, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")

    print("\n# r-w. endurecimento: renomeações, comandos não simuláveis, amend, expansão")
    PROD = "src/main/java/Foo.java"
    r1 = make_repo(tmp / "r")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    (r1 / "src/test/java").mkdir(parents=True)
    git(["mv", PROD, TEST_FILE], r1)
    r = gate("git commit -m x", r1)
    check("r: git mv prod->teste staged, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    check("r: nomeia a origem da renomeação", PROD in r.stderr, r.stderr[:400])

    r1 = make_repo(tmp / "s")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    (r1 / "src/test/java").mkdir(parents=True)
    (r1 / PROD).rename(r1 / TEST_FILE)
    r = gate("git add -A && git commit -m x", r1)
    check("s: mv na árvore + add -A, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    check("s: nomeia a origem", PROD in r.stderr, r.stderr[:400])

    r1 = make_repo(tmp / "t")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    (r1 / "src/test/java").mkdir(parents=True)
    r = gate(f"git mv {PROD} {TEST_FILE} && git commit -m x", r1)
    check("t: git mv no mesmo comando, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "u")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, TEST_FILE)
    (r1 / "list.txt").write_text(TEST_FILE + "\n", encoding="utf-8")
    r = gate("git add --pathspec-from-file=list.txt && git commit -m x", r1)
    check("u: --pathspec-from-file, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "v")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    stage(r1, TEST_FILE)
    r = gate("git commit --amend -m x", r1)
    check("v: --amend, exit 2", r.returncode == 2, f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "w")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, TEST_FILE)
    r = gate('git add "$(echo src/test/java/FooTest.java)" && git commit -m x', r1)
    check("w: expansão de shell no add, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")

    print("\n# x-z. segundo passe: git atrás de VAR=, rm antes de -a, /tmp vs /private/tmp")
    r1 = make_repo(tmp / "x")
    baseline(r1, "FAILURE", PYTEST_TAIL, kind="pytest")
    untracked(r1, "tests/new_test.py")
    r = gate("git add tests/new_test.py && FOO=1 git mv src/main/java/Foo.java tests/z "
             "&& git commit -qm r", r1)
    check("x: VAR=1 git mv antes do commit, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    r = gate("git add tests/new_test.py && sudo git rm src/main/java/Foo.java "
             "&& git commit -qm r", r1)
    check("x2: sudo git rm antes do commit, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "y")
    baseline(r1, "FAILURE", PYTEST_TAIL, kind="pytest")
    untracked(r1, "tests/new_test.py")
    r = gate("git add tests/new_test.py && rm src/main/java/Foo.java && git commit -qam r", r1)
    check("y: rm antes de commit -a, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    r = gate("git add tests/new_test.py && echo ok && git commit -m r", r1)
    check("y2: echo antes de commit simples, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")

    for label, cmd in (
            ("aa", "git add tests/new_test.py && echo x > src/main/java/Foo.java && git commit -qam r"),
            ("aa2", "git add tests/new_test.py && : > src/main/java/Foo.java && git commit -qam r"),
            ("aa3", "git add tests/new_test.py && echo x >> src/main/java/Foo.java && git commit -m r src")):
        r = gate(cmd, r1)
        check(f"{label}: redirecionamento em echo/: antes do commit, exit 2", r.returncode == 2,
              f"exit={r.returncode} {r.stderr[:300]}")

    r = gate("git add tests/new_test.py && export A=$(rm src/main/java/Foo.java) && git commit -qam r", r1)
    check("ab: export A=$(rm ...) antes de commit -a, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    r = gate("git add tests/new_test.py && echo `rm src/main/java/Foo.java` && git commit -qam r", r1)
    check("ac: echo com crase antes de commit -a, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")

    r = gate('git add tests/new_test.py && git commit -qam "$(rm src/main/java/Foo.java)"', r1)
    check("ad: substituição de comando no commit, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    check("ad: Foo.java segue existindo", (r1 / "src/main/java/Foo.java").exists())
    r = gate('git add tests/new_test.py && git commit -m "$(rm src/main/java/Foo.java)" src', r1)
    check("ad2: substituição + pathspec, exit 2", r.returncode == 2, f"exit={r.returncode}")

    r1 = make_repo(tmp / "ae")
    baseline(r1, "FAILURE", PYTEST_TAIL, kind="pytest")
    (r1 / "tests").mkdir()
    (r1 / "tests/test_x.py").write_text("x", encoding="utf-8")
    git(["add", "tests/test_x.py"], r1)
    git(["commit", "-qm", "t"], r1)
    (r1 / "tests/test_x.py").write_text("y", encoding="utf-8")
    r = gate("git commit -am x", r1)
    check("ae: commit -am, só teste modificado, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    check("ae: dica da forma não inspecionada",
          "-a / --include / pathspec forms are not inspected" in r.stderr, r.stderr[:500])
    for form in ("git commit -o tests/test_x.py -m x", "git commit --include -m x",
                 "git commit -m x tests/test_x.py"):
        r = gate(form, r1)
        check(f"ae: {form!r} exit 2", r.returncode == 2, f"exit={r.returncode}")

    r1 = make_repo(tmp / "af")
    baseline(r1, "FAILURE", PYTEST_TAIL, kind="pytest")
    untracked(r1, "tests/x_test.py")
    r = gate("git add tests/x_test.py && git commit -m x", r1)
    check("af: add simples + commit -m, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "ag")
    baseline(r1, "FAILURE", PYTEST_TAIL, kind="pytest")
    untracked(r1, "tests/test_x.py")
    r = gate("git add tests/test_x.py && git commit -qm r", r1)
    check("ag: cluster -qm consome a mensagem, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "ah")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, TEST_FILE)
    r = gate("rm src/main/java/Foo.java; git add -A && git commit -m x", r1)
    check("ah: rm antes de add -A, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    r = gate("rm src/main/java/Foo.java; git add src/test && git commit -m x", r1)
    check("ah2: rm antes de add de diretório, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    r = gate(f"rm src/main/java/Foo.java; git add {TEST_FILE} && git commit -m x", r1)
    check("ah3: rm antes de add de arquivo explícito, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "ai")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, TEST_FILE)
    r = gate("git add -A && git commit -m x", r1)
    check("ai: add -A sozinho com só teste novo, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")

    print("\n# aj-ao. cobertura adicional: formas amplas, sharing, EMPTY/STALE, $(date), -C")
    r1 = make_repo(tmp / "aj")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    stage(r1, TEST_FILE)
    (r1 / "src/main/java/Foo.java").write_text("class Foo { int w; }", encoding="utf-8")
    for form in ("git commit -a -m x", "git commit --all -m x",
                 "git commit --include -m x", "git commit --only -m x"):
        r = gate(form, r1)
        check(f"aj: {form!r} com teste staged, exit 2", r.returncode == 2,
              f"exit={r.returncode} {r.stderr[:300]}")
        check(f"aj: {form!r} traz a dica da forma não inspecionada",
              "forms are not inspected" in r.stderr, r.stderr[:400])

    r1 = make_repo(tmp / "ak")
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, "tests/x_test.py")
    r = gate("git add tests/x_test.py && git commit -m x && git push origin main", r1)
    check("ak: commit isento encadeado com push, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")
    for cmd in ("gh pr create --title x", "gh pr merge 1"):
        r = gate(cmd, r1)
        check(f"al: {cmd!r} com baseline vermelho de teste, exit 2", r.returncode == 2,
              f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "am")
    baseline(r1, "EMPTY", MVN_TEST_TAIL)
    stage(r1, TEST_FILE)
    r = gate("git commit -m x", r1)
    check("am: baseline EMPTY, exit 2", r.returncode == 2, f"exit={r.returncode} {r.stderr[:300]}")
    r1 = make_repo(tmp / "am2")
    baseline(r1, "STALE", MVN_TEST_TAIL, after_edit_to="x", since="2026-11-05T10:00:00+00:00")
    stage(r1, TEST_FILE)
    r = gate("git commit -m x", r1)
    check("am2: STALE com tail de teste vermelho, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "an")
    baseline(r1, "FAILURE", PYTEST_TAIL, kind="pytest")
    untracked(r1, "tests/x_test.py")
    r = gate('git add tests/x_test.py && git commit -m "$(date)"', r1)
    check("an: $(date) fora do git add, exit 2", r.returncode == 2,
          f"exit={r.returncode} {r.stderr[:300]}")

    r1 = make_repo(tmp / "ao")
    outside_ao = tmp / "ao_outside"
    outside_ao.mkdir()
    baseline(r1, "FAILURE", MVN_TEST_TAIL)
    untracked(r1, TEST_FILE)
    r = gate(f"git -C {r1} add {TEST_FILE} && git -C {r1} commit -m x", outside_ao)
    check("ao: git -C add + git -C commit de fora do repo, exit 0", r.returncode == 0,
          f"exit={r.returncode} {r.stderr[:300]}")

    import shutil
    tmp_real = Path(tempfile.mkdtemp(dir="/tmp"))
    try:
        r1 = make_repo(tmp_real / "z")
        baseline(r1, "FAILURE", PYTEST_TAIL, kind="pytest")
        untracked(r1, "tests/test_x.py")
        r = gate("git add tests/test_x.py && git commit -m x", tmp_real / "z")
        check("z: cwd via /tmp (symlink no macOS), exit 0", r.returncode == 0,
              f"exit={r.returncode} {r.stderr[:300]}")
    finally:
        shutil.rmtree(tmp_real, ignore_errors=True)

# j. unit checks
print("\n# j. is_test_path / failure_is_test_failure")
spec = importlib.util.spec_from_file_location("gate_advance", HOOKS / "gate-advance.py")
ga = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(HOOKS))
spec.loader.exec_module(ga)

POS = ["src/test/java/FooTest.java", "src/test/resources/data.sql", "conftest.py",
       "tests/test_x.py", "pkg/foo_test.py", "web/__tests__/a.js", "web/src/a.spec.ts",
       "web/src/a.test.jsx", "pkg/x_test.go", "spec/models/user_spec.rb",
       "src/main/kotlin/FooSpec.kt", "src/main/java/FooIT.java", "docs/testing/notes.md"]
NEG = ["src/main/java/com/x/TestHelper.java", "README.md", "src/main/java/Foo.java",
       "web/src/app.ts", "pkg/contest.py", "latest/readme.txt", ""]
for p in POS:
    check(f"is_test_path({p!r})", ga.is_test_path(p) is True)
for p in NEG:
    check(f"not is_test_path({p!r})", ga.is_test_path(p) is False)

f = ga.failure_is_test_failure
check("jest tail", f({"tail": "Tests:       2 failed, 3 passed, 5 total"}) is True)
check("go tail", f({"tail": "--- FAIL: TestX (0.00s)\nFAIL\tpkg\t0.01s"}) is True)
check("go build failed", f({"tail": "FAIL\tpkg [build failed]"}) is False)
check("cargo test", f({"tail": "test result: FAILED. 0 passed; 1 failed"}) is True)
check("cargo compile", f({"tail": "error[E0425]: cannot find value\ncould not compile"}) is False)
check("repo script style", f({"tail": "FAIL  test_something"}) is True)
check("empty state", f({}) is False)
check("unknown tail", f({"tail": "something happened"}) is False)

print()
if FAILURES:
    print(f"{len(FAILURES)} FALHA(S): {', '.join(FAILURES)}")
    sys.exit(1)
print("todos os casos verdes")
