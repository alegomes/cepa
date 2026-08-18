#!/usr/bin/env python3
"""Testes das duas medidas de atrito das pontas da sessão.

A queixa que originou isto ("gasto 15-20% do contexto só em preparação, e
depois mais um vaivém até ter certeza de que acabou") era anedótica. Estas
duas medidas existem para que a próxima conversa sobre atrito seja evidência
contra evidência, e não memória contra memória:

  - turnos ANTES do primeiro comando de rotina (preparação);
  - turnos DEPOIS do último, até o /wrap-up ou /handoff (fechamento).

O que os testes fixam:
  - o hook de prompt classifica rotina / fechamento / prosa / outro comando;
  - o hook NUNCA grava o texto do prompt no ledger (só o nome do comando);
  - a agregação conta o que uma pessoa contaria à mão, e ignora sessão sem
    rotina (nela as medidas não significam nada);
  - o próprio /wrap-up não conta como atrito — ele é o encerramento.

Run: python3 tests/test_atrito_pontas.py
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "session-log.py"
METRICS = REPO / "common" / "bin" / "cepa-metrics"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def load_hook():
    spec = importlib.util.spec_from_loader(
        "session_log",
        importlib.machinery.SourceFileLoader("session_log", str(HOOK)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_classificacao():
    h = load_hook()
    casos = [
        ("/board-flow:prove-drain --max 5", "rotina", "board-flow:prove-drain"),
        ("/common:session prove-drain", "rotina", "common:session"),
        ("/common:wrap-up", "fechamento", "common:wrap-up"),
        ("/common:doctor", "comando", "common:doctor"),
        ("por que o card travou?", "prosa", None),
        ("  /BOARD-FLOW:DRAIN", "rotina", "board-flow:drain"),
    ]
    for prompt, kind, cmd in casos:
        k, c = h.classify(prompt)
        check(f"classifica {prompt[:28]!r} como {kind}", (k, c) == (kind, cmd), (k, c))


def test_hook_nao_vaza_o_prompt():
    with tempfile.TemporaryDirectory() as tmp:
        tel = Path(tmp) / "tel"
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tel))
        payload = json.dumps({"prompt": "/board-flow:drain senha=hunter2 WEGO-999",
                              "cwd": tmp, "session_id": "abcdef123456"})
        p = subprocess.run([sys.executable, str(HOOK)], input=payload,
                           capture_output=True, text=True, env=env)
        check("hook nunca falha (exit 0)", p.returncode == 0, p.stderr)
        blob = "".join(f.read_text() for f in tel.glob("*.jsonl")) if tel.is_dir() else ""
        check("evento gravado com o nome do comando",
              '"cmd": "board-flow:drain"' in blob, blob)
        check("o texto do prompt NÃO vai para o ledger",
              "hunter2" not in blob and "WEGO-999" not in blob, blob)


def test_agregacao():
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory() as tmp:
        tel = Path(tmp) / "tel"
        tel.mkdir()
        rows, i = [], 0

        def ev(session, kind, cmd=""):
            nonlocal i
            i += 1
            return {"ts": (now - timedelta(minutes=500 - i)).isoformat(),
                    "repo": "cepa", "event": "prompt",
                    "session": session, "kind": kind, "cmd": cmd}

        # A: 3 de preparação → rotina → 2 de vaivém → wrap-up
        for k in ("prosa", "comando", "prosa"):
            rows.append(ev("AAAA", k))
        rows.append(ev("AAAA", "rotina", "board-flow:prove-drain"))
        rows += [ev("AAAA", "prosa"), ev("AAAA", "prosa")]
        rows.append(ev("AAAA", "fechamento", "common:wrap-up"))
        # B: rotina de cara, encerrou — o ideal, zero e zero
        rows.append(ev("BBBB", "rotina", "common:session"))
        rows.append(ev("BBBB", "fechamento", "common:wrap-up"))
        # C: sessão sem rotina — não deve entrar na conta
        rows.append(ev("CCCC", "prosa"))

        (tel / f"events-{now:%Y-%m}.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tel))
        p = subprocess.run([sys.executable, str(METRICS), "--json"],
                           capture_output=True, text=True, env=env)
        data = json.loads(p.stdout)["atrito"]

        check("mede só as sessões que rodaram uma rotina",
              data["sessoes_medidas"] == 2, data)
        check("conta 3 turnos de preparação na sessão que teve 3",
              sorted(data["turnos_antes_da_rotina"]) == [0, 3], data)
        check("conta 2 turnos de fechamento, sem contar o próprio wrap-up",
              sorted(data["turnos_depois_da_rotina"]) == [0, 2], data)
        check("mediana calculada", data["mediana_antes"] == 1.5
              and data["mediana_depois"] == 1.0, data)

        p2 = subprocess.run([sys.executable, str(METRICS)],
                            capture_output=True, text=True, env=env)
        check("o relatório traz a memória de cálculo junto do número",
              "memória de cálculo" in p2.stdout and "Atrito das pontas" in p2.stdout,
              p2.stdout[-400:])


def main():
    test_classificacao()
    test_hook_nao_vaza_o_prompt()
    test_agregacao()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
