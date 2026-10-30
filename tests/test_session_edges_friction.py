#!/usr/bin/env python3
"""Tests of the two friction measures at the edges of the session.

The complaint that originated this ("I spend 15-20% of the context only on preparation, and
then one more back-and-forth until I am sure it is over") was anecdotal. These
two measures exist so that the next conversation about friction is evidence
against evidence, and not memory against memory:

  - turns BEFORE the first routine command (preparation);
  - turns AFTER the last one, until /wrap-up or /handoff (closing).

What the tests pin down:
  - the prompt hook classifies routine / closing / prose / other command;
  - the hook NEVER records the prompt text in the ledger (only the command name);
  - the aggregation counts what a person would count by hand, and ignores a session
    without a routine (in it the measures mean nothing);
  - /wrap-up itself does not count as friction — it is the closing.

Run: python3 tests/test_session_edges_friction.py
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


def test_classification():
    h = load_hook()
    cases = [
        ("/board-flow:prove-drain --max 5", "rotina", "board-flow:prove-drain"),
        ("/common:session prove-drain", "rotina", "common:session"),
        ("/common:wrap-up", "fechamento", "common:wrap-up"),
        ("/common:doctor", "comando", "common:doctor"),
        ("por que o card travou?", "prosa", None),
        ("  /BOARD-FLOW:DRAIN", "rotina", "board-flow:drain"),
    ]
    for prompt, kind, cmd in cases:
        k, c = h.classify(prompt)
        check(f"classifica {prompt[:28]!r} como {kind}", (k, c) == (kind, cmd), (k, c))


def test_hook_does_not_leak_the_prompt():
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


def test_aggregation():
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

        # A: 3 of preparation → routine → 2 of back-and-forth → wrap-up
        for k in ("prosa", "comando", "prosa"):
            rows.append(ev("AAAA", k))
        rows.append(ev("AAAA", "rotina", "board-flow:prove-drain"))
        rows += [ev("AAAA", "prosa"), ev("AAAA", "prosa")]
        rows.append(ev("AAAA", "fechamento", "common:wrap-up"))
        # B: routine right away, closed — the ideal, zero and zero
        rows.append(ev("BBBB", "rotina", "common:session"))
        rows.append(ev("BBBB", "fechamento", "common:wrap-up"))
        # C: session without a routine — must not enter the count
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
    test_classification()
    test_hook_does_not_leak_the_prompt()
    test_aggregation()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
