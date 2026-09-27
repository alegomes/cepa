#!/usr/bin/env python3
"""Regression tests for the `.claude/last-root-install.json` marker written by
`common/hooks/capture-build-result.py` (liberação 2 do maven-reactor-guard,
2026-09-27).

No third-party deps — run with `python3 tests/test_capture_build_result_root_install.py`.
Exits non-zero on failure.

Guards the contract:
  - Maven SUCCESS que roda `install` sobre o reator inteiro (sem `-pl`/`--projects`)
    grava `.claude/last-root-install.json` = {"at": <iso utc>, "command": <cmd[:200]>};
  - `-pl x install` (um módulo só) NÃO grava — não instalou o reator inteiro;
  - `cd domain && ./mvnw install` (sem `-f`) NÃO grava — o pom efetivo é o de
    `domain` (build_dir), não o da raiz da sessão;
  - FAILURE não grava, mesmo com `install` sobre o reator inteiro;
  - o arquivo é SEPARADO de last-build.json: um `-pl` SUCCESS posterior não
    apaga o marcador de install da raiz que já existia.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Este teste executa hook que emite telemetria; sem isto os eventos cairiam
# em ~/.claude/cepa-telemetry/ e entrariam no relatório do /common:metrics
# como se fossem uso real. Ver tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()

REPO = Path(__file__).resolve().parent.parent
CAPTURE = REPO / "common" / "hooks" / "capture-build-result.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(payload):
    return subprocess.run(
        [sys.executable, str(CAPTURE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def bash_payload(cwd, command, output, exit_code=None):
    resp = {"stdout": output}
    if exit_code is not None:
        resp["exit_code"] = exit_code
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": resp,
        "cwd": str(cwd),
    }


def read_marker(root):
    p = Path(root) / ".claude" / "last-root-install.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


BUILD_SUCCESS = "... [INFO] BUILD SUCCESS ..."
BUILD_FAILURE = "... [INFO] BUILD FAILURE ..."


def main():
    with tempfile.TemporaryDirectory() as td:
        # ── install da raiz, SUCCESS → grava o marcador ─────────────────────
        r = Path(td) / "root-install"
        r.mkdir()
        res = run_hook(bash_payload(r, "./mvnw install -DskipTests", BUILD_SUCCESS))
        check("hook exits 0", res.returncode == 0, res.stderr)
        m = read_marker(r)
        check("install da raiz SUCCESS grava last-root-install.json",
              m is not None, str(m))
        check("marcador grava `at` e `command`",
              m is not None and "at" in m and "command" in m, str(m))
        check("marcador grava o comando (truncado em 200)",
              m is not None and m["command"] == "./mvnw install -DskipTests", str(m))

        # ── -pl x install (um módulo só) → NÃO grava ────────────────────────
        r2 = Path(td) / "pl-install"
        r2.mkdir()
        run_hook(bash_payload(r2, "./mvnw -pl domain install -DskipTests", BUILD_SUCCESS))
        check("-pl <modulo> install NÃO grava o marcador (não é a raiz inteira)",
              read_marker(r2) is None)

        # ── -f/--file apontando para submódulo ou raiz ──────────────────────
        # Bypass reproduzido pelo pair-reviewer em 2026-09-27: `-f` sozinho
        # (sem `-pl`) resolvia para "instalou o reator inteiro" mesmo quando
        # o pom.xml apontado era de um submódulo.
        r5 = Path(td) / "f-submodule"
        r5.mkdir()
        run_hook(bash_payload(r5, "./mvnw -f domain/pom.xml install", BUILD_SUCCESS))
        check("-f domain/pom.xml install NÃO grava o marcador (pom de submódulo)",
              read_marker(r5) is None)

        r6 = Path(td) / "f-root"
        r6.mkdir()
        run_hook(bash_payload(r6, "./mvnw -f pom.xml install", BUILD_SUCCESS))
        check("-f pom.xml install grava o marcador (pom da raiz)",
              read_marker(r6) is not None)

        # ── cd para submódulo sem -f (bypass reproduzido pelo pair-reviewer
        # em 2026-09-27): build_dir vira <raiz>/domain, mas o marcador ainda
        # vai para <raiz>/.claude — o pom efetivo (o de domain, por default,
        # já que não há -f) tem de ser comparado contra o da raiz da SESSÃO,
        # não contra o do próprio build_dir. ─────────────────────────────
        r8 = Path(td) / "cd-submodule"
        r8.mkdir()
        (r8 / "domain").mkdir()
        run_hook(bash_payload(r8, "cd domain && ./mvnw install", BUILD_SUCCESS))
        check("cd domain && ./mvnw install NÃO grava o marcador na raiz da sessão",
              read_marker(r8) is None)
        check("cd domain && ./mvnw install também não grava sob domain/.claude",
              read_marker(r8 / "domain") is None)

        r9 = Path(td) / "cd-submodule-f-root"
        r9.mkdir()
        (r9 / "domain").mkdir()
        run_hook(bash_payload(r9, "cd domain && ./mvnw -f ../pom.xml install", BUILD_SUCCESS))
        check("cd domain && ./mvnw -f ../pom.xml install grava o marcador (pom da raiz da sessão)",
              read_marker(r9) is not None)

        # ── -rf/--resume-from (reator parcial mesmo sem -pl) ────────────────
        r7 = Path(td) / "resume-from"
        r7.mkdir()
        run_hook(bash_payload(r7, "./mvnw -rf :bootstrap install", BUILD_SUCCESS))
        check("-rf :bootstrap install NÃO grava o marcador (retomada parcial)",
              read_marker(r7) is None)

        # ── FAILURE não grava, mesmo com install da raiz inteira ────────────
        r3 = Path(td) / "root-install-red"
        r3.mkdir()
        run_hook(bash_payload(r3, "./mvnw install -DskipTests", BUILD_FAILURE))
        check("install da raiz com BUILD FAILURE NÃO grava o marcador",
              read_marker(r3) is None)

        # ── o marcador é SEPARADO de last-build.json ────────────────────────
        r4 = Path(td) / "separate-file"
        r4.mkdir()
        run_hook(bash_payload(r4, "./mvnw install -DskipTests", BUILD_SUCCESS))
        first = read_marker(r4)
        check("pré-condição: marcador da raiz gravado", first is not None, str(first))
        # um -pl SUCCESS depois não deveria apagar o marcador (não escreve nele)
        run_hook(bash_payload(r4, "./mvnw -pl domain -am test", BUILD_SUCCESS))
        second = read_marker(r4)
        check("um -pl SUCCESS depois não apaga o marcador da raiz",
              second is not None and second == first, f"{first} -> {second}")
        last_build = json.loads((r4 / ".claude" / "last-build.json").read_text())
        check("last-build.json, por outro lado, foi sobrescrito pelo -pl",
              "domain" in last_build.get("command", ""), str(last_build))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
