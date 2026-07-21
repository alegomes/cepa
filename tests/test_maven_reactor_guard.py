#!/usr/bin/env python3
"""Regression tests for common/hooks/maven-reactor-guard.py (WEGO-1949).

No third-party deps — run with `python3 tests/test_maven_reactor_guard.py`.
Exits non-zero on failure.

Guards the contracts of the guard:
  - `-pl` sem `-am` num reator multi-módulo é BLOQUEADO (exit 2);
  - `-am` / `--also-make` liberam; `-amd` (also-make-DEPENDENTS) NÃO;
  - `--projects` (forma longa) e `-pl=x` / `--projects=x` são detectados;
  - repo de módulo único nunca é bloqueado;
  - prefixo de env (`FOO=bar ./mvnw`) e wrapper (`timeout 600 mvn`) ainda contam
    como invocação real — é o padrão do README do wego-assinatura;
  - Maven dentro de `echo`/`grep` é texto, não execução: NÃO bloqueia;
  - o escape hatch `# stale-ok` libera;
  - segmento encadeado (`cd x && ./mvnw test -pl y`) é inspecionado;
  - outras tools, comando vazio e payload ilegível falham ABERTO.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

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

        # ── o caso que originou o card ──────────────────────────────────────
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

        # ── o que deve passar ───────────────────────────────────────────────
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

        # ── a armadilha do -amd ─────────────────────────────────────────────
        check(
            "-amd NÃO salva (constrói dependentes, não dependências)",
            blocked(run_hook("./mvnw test -pl domain -amd", multi)),
        )
        check(
            "--also-make-dependents NÃO salva",
            blocked(run_hook("./mvnw test -pl domain --also-make-dependents", multi)),
        )

        # ── formas alternativas do -pl ──────────────────────────────────────
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

        # ── escopo: só reator multi-módulo ──────────────────────────────────
        check(
            "repo single-module nunca bloqueia",
            not blocked(run_hook("./mvnw test -pl whatever", single)),
        )
        check(
            "sem pom.xml falha aberto",
            not blocked(run_hook("./mvnw test -pl whatever", nopom)),
        )

        # ── invocação real vs texto citado ──────────────────────────────────
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

        # ── encadeamento ────────────────────────────────────────────────────
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

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
