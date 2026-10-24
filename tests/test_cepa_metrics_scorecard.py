#!/usr/bin/env python3
"""Tests for `cepa-metrics scorecard` (CS-2 of cycle 1 of Cepa in a spiral).

The scorecard prints the three numbers that the strategy
(docs/estrategia-cepa-proximo-nivel.md, F3, F8 and F10) set as the comparison
baseline: turns after routine per session, red builds and sessions in the cepa
repo. Each line must bring numerator, denominator and result, in both
windows (last 7 days and since the beginning), because a number without its calculation cannot be
checked.

The test ledger has events of two ages: 2 days ago (they enter both
windows) and 40 days ago (only in "since the beginning"). The expected values were
counted by hand over this ledger.

Run: python3 tests/test_cepa_metrics_scorecard.py
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
METRICS = REPO / "common" / "bin" / "cepa-metrics"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def ledger(tmp):
    now = datetime.now(timezone.utc)
    rec, old = now - timedelta(days=2), now - timedelta(days=40)

    def ts(base, mins):
        return (base + timedelta(minutes=mins)).isoformat()

    ev = []
    # Recent session with routine: 1 prose before, routine, 2 prose, another routine,
    # 3 after the LAST one (includes a closing, which also counts: F3 sums everything).
    kinds = ["prosa", "rotina", "prosa", "prosa", "rotina", "prosa", "prosa", "fechamento"]
    for i, k in enumerate(kinds):
        ev.append({"ts": ts(rec, i), "event": "prompt", "session": "r1", "kind": k})
    # The ledger is read one file per month, so the session that crosses the
    # month boundary arrives out of order: writes r1 backwards to require
    # the count to sort by time before finding the last routine.
    ev.reverse()
    # Prompt without session (old hook, truncated event): does not form a session. A
    # routine followed by prose, so that counting it would change both sides of the calculation.
    for i, k in enumerate(["rotina", "prosa"]):
        ev.append({"ts": ts(rec, 10 + i), "event": "prompt", "kind": k})
    # Recent session without routine: does not enter the denominator.
    for i in range(4):
        ev.append({"ts": ts(rec, 20 + i), "event": "prompt", "session": "r2", "kind": "prosa"})
    # Old session with routine and 5 prompts after it.
    for i, k in enumerate(["rotina"] + ["prosa"] * 5):
        ev.append({"ts": ts(old, i), "event": "prompt", "session": "o1", "kind": k})
    # Builds: recent 1 FAILURE, 2 SUCCESS, 1 EMPTY; old 2 FAILURE, 1 SUCCESS.
    for i, st in enumerate(["FAILURE", "SUCCESS", "SUCCESS", "EMPTY"]):
        ev.append({"ts": ts(rec, 40 + i), "event": "build_result", "repo": "x", "status": st})
    for i, st in enumerate(["FAILURE", "FAILURE", "SUCCESS"]):
        ev.append({"ts": ts(old, 40 + i), "event": "build_result", "repo": "x", "status": st})
    # Sessions: recent cepa, wego, wego, wego; old cepa, cepa.
    for i, r in enumerate(["cepa", "wego", "wego", "wego"]):
        ev.append({"ts": ts(rec, 60 + i), "event": "session_start", "repo": r})
    for i, r in enumerate(["cepa", "cepa"]):
        ev.append({"ts": ts(old, 60 + i), "event": "session_start", "repo": r})

    by_month = {}
    for e in ev:
        by_month.setdefault(e["ts"][:7], []).append(e)
    for m, es in by_month.items():
        (tmp / f"events-{m}.jsonl").write_text(
            "\n".join(json.dumps(e) for e in es) + "\n", encoding="utf-8")


def run(tmp, *args):
    env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tmp))
    return subprocess.run([sys.executable, str(METRICS), "scorecard", *args],
                          capture_output=True, text=True, env=env)


def section(out, title):
    """The lines of the `## title` section, up to the next blank line."""
    lines = out.splitlines()
    i = lines.index(f"## {title}")
    block = []
    for l in lines[i + 1:]:
        if not l.strip():
            break
        block.append(l.strip())
    return block


def test_text():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ledger(tmp)
        p = run(tmp)
        check("scorecard sai com 0", p.returncode == 0, p.stderr)
        out = p.stdout
        try:
            rec = section(out, "últimos 7 dias")
            ini = section(out, "desde o início")
        except ValueError:
            check("as duas janelas aparecem", False, out)
            return
        expected = {
            "últimos 7 dias": (rec, [
                ("turnos após rotina por sessão", "3.0", "3 prompts", "1 sessões"),
                ("builds vermelhos", "25.0%", "1 builds FAILURE", "4 builds"),
                ("sessões no repo cepa", "25.0%", "1 sessões no cepa", "4 sessões"),
            ]),
            "desde o início": (ini, [
                ("turnos após rotina por sessão", "4.0", "8 prompts", "2 sessões"),
                ("builds vermelhos", "42.9%", "3 builds FAILURE", "7 builds"),
                ("sessões no repo cepa", "50.0%", "3 sessões no cepa", "6 sessões"),
            ]),
        }
        for window, (block, lines) in expected.items():
            check(f"{window}: exatamente três linhas", len(block) == 3, block)
            for given_name, res, num, den in lines:
                l = next((x for x in block if x.startswith(given_name + ":")), "")
                check(f"{window} · {given_name}: resultado {res}", f": {res} " in l, l)
                check(f"{window} · {given_name}: numerador e denominador", num in l and den in l, l)
        check("memória de cálculo impressa", "memória de cálculo" in out, out)


def test_json():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ledger(tmp)
        p = run(tmp, "--json")
        check("--json sai com 0", p.returncode == 0, p.stderr)
        try:
            j = json.loads(p.stdout)
        except json.JSONDecodeError:
            check("--json é JSON", False, p.stdout)
            return
        b = j["desde o início"]["builds vermelhos"]
        check("--json traz numerador/denominador", (b["numerador"], b["denominador"]) == (3, 7), b)


def test_empty_ledger():
    with tempfile.TemporaryDirectory() as d:
        p = run(Path(d))
        check("ledger vazio sai com 0", p.returncode == 0, p.stderr)
        check("ledger vazio diz sem dados", "sem dados" in p.stdout, p.stdout)


def test_old_report_intact():
    # The new subcommand must not break the usual report.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ledger(tmp)
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tmp))
        p = subprocess.run([sys.executable, str(METRICS), "--days", "90"],
                           capture_output=True, text=True, env=env)
        check("cepa-metrics sem subcomando continua saindo com 0", p.returncode == 0, p.stderr)
        check("relatório de sempre continua", "# Telemetria do harness" in p.stdout, p.stdout)


if __name__ == "__main__":
    test_text()
    test_json()
    test_empty_ledger()
    test_old_report_intact()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\nok")
