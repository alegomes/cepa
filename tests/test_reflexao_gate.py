#!/usr/bin/env python3
"""Regression tests for common/hooks/reflexao-gate.py.

A Reflexão fecha quando NENHUM achado ficou solto: cada um virou card ou foi
descartado com motivo escrito (docs/modos-de-trabalho.md). Achado solto não
some — volta como micro-ajuste no meio da próxima construção, que é o
vazamento que os modos existem para impedir.

Contratos guardados aqui:
  - `fechado: true` com achado sem destino nem descarte → bloqueia (rc=2);
  - descarte com motivo decorativo ("n/a", "-", "ok") ou curto demais também
    bloqueia — motivo simbólico é o mesmo que motivo nenhum, e passa a
    impressão de que a triagem aconteceu;
  - achado com destino, ou com descarte de motivo real, passa;
  - `fechado: false` passa sempre — triagem em andamento não é violação;
  - fail-open: arquivo fora de .claude/reflexao/, YAML quebrado, conteúdo
    ausente → deixa passar, nunca inventa bloqueio;
  - CEPA_MODO=off desliga.

Sem deps além de PyYAML (que o hook já exige) — rode com
`python3 tests/test_reflexao_gate.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "common" / "hooks" / "reflexao-gate.py"

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def run(conteudo, path=".claude/reflexao/fronteiras-2026-08-18.yaml", env=None):
    e = {**os.environ}
    e.update(env or {})
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(
            [sys.executable, str(GATE)],
            input=json.dumps({"cwd": tmp, "tool_name": "Write",
                              "tool_input": {"file_path": path,
                                             "content": conteudo}}),
            capture_output=True, text=True, timeout=15, env=e,
        )


ABERTO = """recorte: fronteiras
lente: contrarian
fechado: false
achados:
  - o_que: "o resolver duplica a query"
"""

SEM_DESTINO = """recorte: fronteiras
fechado: true
achados:
  - o_que: "o resolver duplica a query"
    onde: "ContactResolver.java:88"
"""

COM_DESTINO = """recorte: fronteiras
fechado: true
achados:
  - o_que: "o resolver duplica a query"
    destino: WEGO-1234
  - o_que: "README aponta endpoint antigo"
    descartado: "o endpoint sai no proximo release, nao vale card agora"
"""


def test_bloqueia_achado_solto():
    p = run(SEM_DESTINO)
    check("solto: bloqueia", p.returncode == 2, str(p.returncode))
    check("solto: nomeia o achado", "duplica a query" in p.stderr, p.stderr)
    check("solto: ensina as duas saídas",
          "destino:" in p.stderr and "descartado:" in p.stderr, p.stderr)
    check("solto: oferece fechado: false", "fechado: false" in p.stderr, p.stderr)


def test_bloqueia_motivo_decorativo():
    for motivo in ('"n/a"', '"-"', '"ok"', '"tbd"', '"curto"'):
        doc = SEM_DESTINO.rstrip() + f"\n    descartado: {motivo}\n"
        p = run(doc)
        check(f"motivo decorativo {motivo}: bloqueia", p.returncode == 2,
              str(p.returncode))
    doc = SEM_DESTINO.rstrip() + '\n    descartado: "ja existe o card WEGO-99 para isso"\n'
    p = run(doc)
    check("motivo real: passa", p.returncode == 0, p.stderr)


def test_passa_quando_tudo_tem_destino():
    p = run(COM_DESTINO)
    check("todos com destino: passa", p.returncode == 0, p.stderr)


def test_aberto_passa():
    p = run(ABERTO)
    check("fechado: false passa", p.returncode == 0, p.stderr)


def test_fail_open():
    p = run(SEM_DESTINO, path="docs/notas.yaml")
    check("fora de .claude/reflexao: passa", p.returncode == 0, p.stderr)
    p = run("isto: [não é: yaml válido\n  ::", )
    check("yaml quebrado: passa", p.returncode == 0, p.stderr)
    p = run("fechado: true\nachados: []\n")
    check("sem achados: passa", p.returncode == 0, p.stderr)


def test_kill_switch():
    p = run(SEM_DESTINO, env={"CEPA_MODO": "off"})
    check("CEPA_MODO=off desliga", p.returncode == 0, p.stderr)


def main():
    print("test_reflexao_gate")
    for fn in (test_bloqueia_achado_solto, test_bloqueia_motivo_decorativo,
               test_passa_quando_tudo_tem_destino, test_aberto_passa,
               test_fail_open, test_kill_switch):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
