#!/usr/bin/env python3
"""Regression tests for common/hooks/reflection-gate.py.

The Reflection closes when NO finding was left loose: each one became a card or was
discarded with a written reason (docs/modos-de-trabalho.md). A loose finding does not
vanish — it comes back as a micro-adjustment in the middle of the next construction, which is the
leak the modes exist to prevent.

Contracts guarded here:
  - `fechado: true` with a finding without destination or discard → blocks (rc=2);
  - a discard with a decorative reason ("n/a", "-", "ok") or too short also
    blocks — a symbolic reason is the same as no reason, and gives the
    impression that the triage happened;
  - a finding with a destination, or with a discard of a real reason, passes;
  - `fechado: false` always passes — triage in progress is not a violation;
  - fail-open: a file outside .claude/reflection/, broken YAML, missing
    content → lets it pass, never invents a block;
  - CEPA_MODO=off turns it off.

No deps beyond PyYAML (which the hook already requires) — run with
`python3 tests/test_reflection_gate.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "common" / "hooks" / "reflection-gate.py"

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def run(content, path=".claude/reflection/fronteiras-2026-08-18.yaml", env=None):
    e = {**os.environ}
    e.update(env or {})
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(
            [sys.executable, str(GATE)],
            input=json.dumps({"cwd": tmp, "tool_name": "Write",
                              "tool_input": {"file_path": path,
                                             "content": content}}),
            capture_output=True, text=True, timeout=15, env=e,
        )


OPEN = """recorte: fronteiras
lente: contrarian
fechado: false
achados:
  - o_que: "o resolver duplica a query"
"""

WITHOUT_DESTINATION = """recorte: fronteiras
fechado: true
achados:
  - o_que: "o resolver duplica a query"
    onde: "ContactResolver.java:88"
"""

WITH_DESTINATION = """recorte: fronteiras
fechado: true
achados:
  - o_que: "o resolver duplica a query"
    destino: WEGO-1234
  - o_que: "README aponta endpoint antigo"
    descartado: "o endpoint sai no proximo release, nao vale card agora"
"""


def test_blocks_loose_finding():
    p = run(WITHOUT_DESTINATION)
    check("solto: bloqueia", p.returncode == 2, str(p.returncode))
    check("solto: nomeia o achado", "duplica a query" in p.stderr, p.stderr)
    check("solto: ensina as duas saídas",
          "destino:" in p.stderr and "descartado:" in p.stderr, p.stderr)
    check("solto: oferece fechado: false", "fechado: false" in p.stderr, p.stderr)


def test_blocks_decorative_reason():
    for reason in ('"n/a"', '"-"', '"ok"', '"tbd"', '"curto"'):
        doc = WITHOUT_DESTINATION.rstrip() + f"\n    descartado: {reason}\n"
        p = run(doc)
        check(f"motivo decorativo {reason}: bloqueia", p.returncode == 2,
              str(p.returncode))
    doc = WITHOUT_DESTINATION.rstrip() + '\n    descartado: "ja existe o card WEGO-99 para isso"\n'
    p = run(doc)
    check("motivo real: passa", p.returncode == 0, p.stderr)


def test_passes_when_everything_has_destination():
    p = run(WITH_DESTINATION)
    check("todos com destino: passa", p.returncode == 0, p.stderr)


def test_blocks_on_new_path_and_on_legacy():
    p = run(WITHOUT_DESTINATION, path=".claude/reflection/x.yaml")
    check("caminho novo .claude/reflection/: bloqueia", p.returncode == 2, str(p.returncode))
    p = run(WITHOUT_DESTINATION, path=".claude/reflexao/x.yaml")
    check("caminho legado .claude/reflexao/: bloqueia", p.returncode == 2, str(p.returncode))


def test_open_passes():
    p = run(OPEN)
    check("fechado: false passa", p.returncode == 0, p.stderr)


def test_fail_open():
    p = run(WITHOUT_DESTINATION, path="docs/notas.yaml")
    check("fora de .claude/reflection: passa", p.returncode == 0, p.stderr)
    p = run("isto: [não é: yaml válido\n  ::", )
    check("yaml quebrado: passa", p.returncode == 0, p.stderr)
    p = run("fechado: true\nachados: []\n")
    check("sem achados: passa", p.returncode == 0, p.stderr)


def test_kill_switch():
    p = run(WITHOUT_DESTINATION, env={"CEPA_MODO": "off"})
    check("CEPA_MODO=off desliga", p.returncode == 0, p.stderr)


def main():
    print("test_reflection_gate")
    for fn in (test_blocks_loose_finding, test_blocks_decorative_reason,
               test_passes_when_everything_has_destination,
               test_blocks_on_new_path_and_on_legacy, test_open_passes,
               test_fail_open, test_kill_switch):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
