#!/usr/bin/env python3
"""Regression tests for common/hooks/maven-reactor-guard.py (WEGO-1949).

No third-party deps — run with `python3 tests/test_maven_reactor_guard.py`.
Exits non-zero on failure.

Guards the contracts of the guard:
  - `-pl` without `-am` in a multi-module reactor is BLOCKED (exit 2);
  - `-am` / `--also-make` release; `-amd` (also-make-DEPENDENTS) does NOT;
  - `--projects` (long form) and `-pl=x` / `--projects=x` are detected;
  - a single-module repo is never blocked;
  - env prefix (`FOO=bar ./mvnw`) and wrapper (`timeout 600 mvn`) still count
    as a real invocation — it is the pattern in wego-assinatura's README;
  - Maven inside `echo`/`grep` is text, not execution: does NOT block;
  - the `# stale-ok` escape hatch releases;
  - a chained segment (`cd x && ./mvnw test -pl y`) is inspected;
  - other tools, empty command and unreadable payload fail OPEN.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

# This test executes a hook that emits telemetry; without this the events would fall
# in ~/.claude/cepa-telemetry/ and enter the /common:metrics report
# as if they were real use. See tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()


REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "maven-reactor-guard.py"

FAILURES = []

MULTI_POM = """<project>
  <artifactId>root</artifactId>
  <modules>
    <module>domain</module>
    <module>bootstrap</module>
  </modules>
</project>
"""

SINGLE_POM = """<project>
  <artifactId>solo</artifactId>
</project>
"""


def run_hook(command, cwd, tool_name="Bash", raw=None):
    payload = raw if raw is not None else json.dumps(
        {"tool_name": tool_name, "tool_input": {"command": command}, "cwd": str(cwd)}
    )
    return subprocess.run(
        [sys.executable, str(HOOK)], input=payload, capture_output=True, text=True
    )


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def blocked(res):
    return res.returncode == 2


def main():
    with tempfile.TemporaryDirectory() as td:
        multi = Path(td) / "multi"
        multi.mkdir()
        (multi / "pom.xml").write_text(MULTI_POM, encoding="utf-8")

        single = Path(td) / "single"
        single.mkdir()
        (single / "pom.xml").write_text(SINGLE_POM, encoding="utf-8")

        nopom = Path(td) / "nopom"
        nopom.mkdir()

        # ── the case that originated the card ───────────────────────────────
        check(
            "-pl sem -am bloqueia",
            blocked(run_hook("./mvnw test -pl bootstrap", multi)),
        )
        check(
            "mensagem cita o comando confiável",
            "-am" in run_hook("./mvnw test -pl bootstrap", multi).stderr,
        )
        check(
            "-pl multi-módulo com -Dtest ainda bloqueia",
            blocked(run_hook("./mvnw test -pl bootstrap -Dtest=ReenviarCascataE2ETest", multi)),
        )

        # ── what must pass ──────────────────────────────────────────────────
        check(
            "-am libera",
            not blocked(run_hook("./mvnw test -pl domain,application -am", multi)),
        )
        check(
            "--also-make libera",
            not blocked(run_hook("./mvnw test -pl domain --also-make", multi)),
        )
        check(
            "verify da raiz libera",
            not blocked(run_hook("./mvnw verify", multi)),
        )
        check(
            "install sem -pl libera",
            not blocked(run_hook("./mvnw install -DskipTests", multi)),
        )

        # ── the -amd trap ───────────────────────────────────────────────────
        check(
            "-amd NÃO salva (constrói dependentes, não dependências)",
            blocked(run_hook("./mvnw test -pl domain -amd", multi)),
        )
        check(
            "--also-make-dependents NÃO salva",
            blocked(run_hook("./mvnw test -pl domain --also-make-dependents", multi)),
        )

        # ── alternative forms of -pl ────────────────────────────────────────
        check(
            "--projects (forma longa) é detectado",
            blocked(run_hook("mvn test --projects bootstrap", multi)),
        )
        check(
            "-pl=x (com igual) é detectado",
            blocked(run_hook("mvn test -pl=bootstrap", multi)),
        )
        check(
            "--projects=x é detectado",
            blocked(run_hook("mvn test --projects=bootstrap", multi)),
        )

        # ── scope: only multi-module reactor ────────────────────────────────
        check(
            "repo single-module nunca bloqueia",
            not blocked(run_hook("./mvnw test -pl whatever", single)),
        )
        check(
            "sem pom.xml falha aberto",
            not blocked(run_hook("./mvnw test -pl whatever", nopom)),
        )

        # ── real invocation vs quoted text ──────────────────────────────────
        check(
            "prefixo de env conta como invocação (padrão do README)",
            blocked(run_hook("PLUGSIGN_API_KEY=xxx ./mvnw test -pl bootstrap", multi)),
        )
        check(
            "wrapper timeout conta como invocação",
            blocked(run_hook("timeout 600 ./mvnw test -pl bootstrap", multi)),
        )
        check(
            "echo com o comando dentro NÃO bloqueia",
            not blocked(run_hook('echo "./mvnw test -pl bootstrap"', multi)),
        )
        check(
            "grep pelo padrão no README NÃO bloqueia",
            not blocked(run_hook("grep -n 'mvnw test -pl bootstrap' README.md", multi)),
        )

        # ── chaining ────────────────────────────────────────────────────────
        check(
            "segmento após && é inspecionado",
            blocked(run_hook("cd /tmp && ./mvnw test -pl bootstrap", multi)),
        )
        check(
            "pipe para tail é inspecionado",
            blocked(run_hook("./mvnw test -pl bootstrap | tail -20", multi)),
        )

        # ── escape hatch ────────────────────────────────────────────────────
        check(
            "# stale-ok libera",
            not blocked(run_hook("./mvnw test -pl bootstrap # stale-ok", multi)),
        )

        # ── fail-open ───────────────────────────────────────────────────────
        check(
            "outra tool não é gated",
            not blocked(run_hook("./mvnw test -pl bootstrap", multi, tool_name="Read")),
        )
        check(
            "comando vazio libera",
            not blocked(run_hook("", multi)),
        )
        check(
            "payload ilegível falha aberto",
            not blocked(run_hook(None, multi, raw="{nao é json")),
        )
        check(
            "payload vazio falha aberto",
            not blocked(run_hook(None, multi, raw="")),
        )

        # ── automatic release 1: no goal of the segment compiles ────────────
        check(
            "-pl domain clean é liberado (clean não compila)",
            not blocked(run_hook("./mvnw -pl domain clean", multi)),
        )
        check(
            "-pl bootstrap dependency:tree é liberado (dependency: não compila)",
            not blocked(run_hook("./mvnw -pl bootstrap dependency:tree", multi)),
        )
        check(
            "-pl x clean test continua bloqueado (test compila)",
            blocked(run_hook("./mvnw -pl x clean test", multi)),
        )
        check(
            "-pl domain install continua bloqueado (install compila, de propósito)",
            blocked(run_hook("./mvnw -pl domain install", multi)),
        )

        # ── chained command with MORE THAN ONE offender (-pl without -am) ───
        # Bypass reproduced by the pair-reviewer on 2026-09-27: looking only at the
        # FIRST offending segment made rule 1 (no goal compiles) be
        # evaluated only on it — a harmless `clean` in the first segment
        # shielded a `test` that compiles in the second.
        check(
            "clean (não compila) seguido de test (compila) continua bloqueado",
            blocked(run_hook("./mvnw -pl a clean && ./mvnw -pl b test", multi)),
        )
        check(
            "clean seguido de dependency:tree (nenhum dos dois compila) é liberado",
            not blocked(
                run_hook("./mvnw -pl a clean && ./mvnw -pl b dependency:tree", multi)
            ),
        )

        # ── automatic release 2: fresh install of the root ──────────────────
        # Timestamps controlled EXPLICITLY by epoch, instead of
        # `time.sleep` + `datetime.now()`: `at` is recorded with SECOND
        # precision (`isoformat(timespec="seconds")`, same as the real hook), so
        # a file created in the same second in which `at` is truncated has an mtime
        # with a fraction > the truncated `at` even though it is "before" on the
        # wall clock — giving 10s of slack between the stamps eliminates this ambiguity
        # without depending on how fast the test runs.
        def write_root_install(root, at_epoch, command="./mvnw install -DskipTests"):
            claude = Path(root) / ".claude"
            claude.mkdir(parents=True, exist_ok=True)
            at_iso = datetime.fromtimestamp(at_epoch, tz=timezone.utc).isoformat(
                timespec="seconds"
            )
            (claude / "last-root-install.json").write_text(
                json.dumps({"at": at_iso, "command": command}), encoding="utf-8"
            )

        def clear_root_install(root):
            marker = Path(root) / ".claude" / "last-root-install.json"
            if marker.exists():
                marker.unlink()

        fresh_multi = Path(td) / "fresh-multi"
        fresh_multi.mkdir()
        (fresh_multi / "pom.xml").write_text(MULTI_POM, encoding="utf-8")
        (fresh_multi / "domain").mkdir()
        foo_java = fresh_multi / "domain" / "Foo.java"
        foo_java.write_text("class Foo {}\n", encoding="utf-8")

        now = time.time()
        # `pom.xml` is also a source (BUILD_FILES) — without pushing its mtime
        # into the past too, it stays "newer" than any `at` recorded
        # in the few milliseconds after the tree is created, and the
        # release never fires. Resets everything that already exists in the tree.
        for p in fresh_multi.rglob("*"):
            if p.is_file():
                os.utime(p, (now - 100, now - 100))

        old_at = now - 200  # `at` BEFORE the source → does not release
        write_root_install(fresh_multi, old_at)
        check(
            "install file presente mas fonte MAIS NOVA que `at` → continua bloqueado",
            blocked(run_hook("./mvnw test -pl bootstrap", fresh_multi)),
        )

        fresh_at = now  # `at` AFTER the source (100s of slack) → releases
        write_root_install(fresh_multi, fresh_at)
        check(
            "install fresco (fonte MAIS ANTIGA que `at`) → liberado",
            not blocked(run_hook("./mvnw test -pl bootstrap", fresh_multi)),
        )

        # editing a source file AFTER the `at` was recorded blocks again.
        os.utime(foo_java, (now + 100, now + 100))
        check(
            "editar fonte depois do install fresco volta a bloquear",
            blocked(run_hook("./mvnw test -pl bootstrap", fresh_multi)),
        )
        os.utime(foo_java, (now - 100, now - 100))  # returns to the "old" state

        # editing a TEST file after the install does not invalidate the release
        # (src/test does not count as a source — same criterion as mark-build-stale).
        (fresh_multi / "domain" / "src" / "test" / "java").mkdir(parents=True)
        test_file = fresh_multi / "domain" / "src" / "test" / "java" / "FooTest.java"
        test_file.write_text("class FooTest {}\n", encoding="utf-8")
        os.utime(test_file, (now + 100, now + 100))  # after the install, but it is a test
        check(
            "editar teste depois do install fresco NÃO bloqueia (src/test não é fonte)",
            not blocked(run_hook("./mvnw test -pl bootstrap", fresh_multi)),
        )

        clear_root_install(fresh_multi)
        check(
            "sem last-root-install.json → continua bloqueado",
            blocked(run_hook("./mvnw test -pl bootstrap", fresh_multi)),
        )

        # ── automatic release 3: quarkus:* never gets an -am suggestion ──────
        check(
            "-pl bootstrap quarkus:dev sem install é bloqueado",
            blocked(run_hook("./mvnw -pl bootstrap quarkus:dev", multi)),
        )
        check(
            "mensagem do quarkus:* NÃO sugere acrescentar -am",
            "acrescente `-am`" not in run_hook(
                "./mvnw -pl bootstrap quarkus:dev", multi
            ).stderr,
        )
        check(
            "mensagem do quarkus:* manda instalar a raiz",
            "install -DskipTests" in run_hook(
                "./mvnw -pl bootstrap quarkus:dev", multi
            ).stderr,
        )
        write_root_install(fresh_multi, time.time())
        check(
            "-pl bootstrap quarkus:dev com install fresco é liberado",
            not blocked(run_hook("./mvnw -pl bootstrap quarkus:dev", fresh_multi)),
        )
        clear_root_install(fresh_multi)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
