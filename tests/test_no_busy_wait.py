#!/usr/bin/env python3
"""Regression tests for the no-busy-wait hook.

No third-party deps — run with `python3 tests/test_no_busy_wait.py`.
Exits non-zero on the first failure.

Guards the biggest clock cost measured in this harness (2026-08-26): leads
polling the disk for a worker's file, and burn loops standing in for the
`sleep` the harness blocks. Between 19% and 52% of five real runs' wall clock.

The BLOCK cases are verbatim from the transcripts of session/drain-plan-0840,
session/todo-1413 and session/todo-21081818 — if the detector stops catching
one of them, the 150-minutes-per-run leak is back. The RELEASE cases guard the
other direction: quoted text is not shell (WEGO-2087), a real build is not a
wait, and a short sleep is not a stall.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "no-busy-wait.py"


def load():
    spec = importlib.util.spec_from_file_location("no_busy_wait", str(HOOK))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# (rótulo, comando) — todos verbatim de transcript real, salvo onde marcado
BLOQUEIA = [
    ("sondagem por arquivo",
     'until [ -f api-rest/src/test/java/com/wego/acesso/api/rest/dto/'
     'CredencialHabilitadaResponse.java ]; do sleep 10; done'),
    ("sondagem por conteudo de build",
     'until grep -q "CredenciaisDoFuncionarioE2ETest" .claude/last-build.json; '
     'do sleep 20; done'),
    ("sondagem por git status",
     'until git status --short | grep -q "CofrePortFalhaGenuina"; do sleep 10; done'),
    ("sondagem de condicao ja verdadeira",
     'until [ -f /dev/null ]; do sleep 5; done; echo aguardando'),
    ("laco de queima como sleep improvisado",
     'for i in $(seq 1 6000); do git log --all --stat >/dev/null 2>&1; done; date'),
    ("laco contado com sleep no corpo",
     'for i in $(seq 1 60); do\n  if [ -f .claude/acceptance/WEGO-2112.yaml ]; '
     'then break; fi\n  sleep 10\ndone'),
    ("sleep longo solto",
     'sleep 60; git status --short | head -12'),
    ("while true", 'while true; do echo x; done'),  # sintetico
]

LIBERA = [
    ("build de verdade", './mvnw -pl bootstrap -am verify'),
    ("build longo com tee", './mvnw clean verify 2>&1 | tail -40'),
    ("texto citado nao e shell",
     'git commit -m "fix: remove o until/sleep do lead"'),
    ("comando dentro de echo",
     'echo "for i in $(seq 1 6000); do git log; done"'),
    ("sleep curto", 'sleep 2 && echo pronto'),
    ("laco pequeno sem sleep", 'for f in *.java; do wc -l "$f"; done'),
    ("until que termina sozinho", 'until git diff --quiet; do break; done'),
    ("leitura normal", "sed -n '1,50p' arquivo.md"),
    ("escape hatch", 'until curl -sf https://ci/status; do sleep 30; done  # espera-ok'),
]


def main():
    mod = load()
    falhas = []

    for rotulo, cmd in BLOQUEIA:
        if mod.bloqueia(cmd) is None:
            falhas.append(f"DEVIA BLOQUEAR ({rotulo}): {cmd[:70]!r}")

    for rotulo, cmd in LIBERA:
        r = mod.bloqueia(cmd)
        if r is not None:
            falhas.append(f"DEVIA LIBERAR ({rotulo}): {cmd[:70]!r} — pegou {r[0]}")

    if falhas:
        for f in falhas:
            print("FAIL:", f, file=sys.stderr)
        print(f"\n{len(falhas)} falha(s) de {len(BLOQUEIA) + len(LIBERA)} casos",
              file=sys.stderr)
        return 1

    print(f"ok — {len(BLOQUEIA)} bloqueios e {len(LIBERA)} liberações conferidos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
