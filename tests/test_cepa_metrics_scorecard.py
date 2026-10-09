#!/usr/bin/env python3
"""Testes do `cepa-metrics scorecard` (CS-2 do ciclo 1 do Cepa em espiral).

O scorecard imprime os três números que a estratégia
(docs/estrategia-cepa-proximo-nivel.md, F3, F8 e F10) pôs como base de
comparação: turnos após rotina por sessão, builds vermelhos e sessões no repo
cepa. Cada linha tem que trazer numerador, denominador e resultado, nas duas
janelas (últimos 7 dias e desde o início), porque número sem conta não se
confere.

O ledger de teste tem eventos de duas idades: 2 dias atrás (entram nas duas
janelas) e 40 dias atrás (só em "desde o início"). Os valores esperados foram
contados à mão sobre esse ledger.

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

    def ts(base, minutos):
        return (base + timedelta(minutes=minutos)).isoformat()

    ev = []
    # Sessão recente com rotina: 1 prosa antes, rotina, 2 prosa, outra rotina,
    # 3 depois da ÚLTIMA (inclui um fechamento, que também conta: F3 soma tudo).
    kinds = ["prosa", "rotina", "prosa", "prosa", "rotina", "prosa", "prosa", "fechamento"]
    for i, k in enumerate(kinds):
        ev.append({"ts": ts(rec, i), "event": "prompt", "session": "r1", "kind": k})
    # O ledger é lido um arquivo por mês, então a sessão que atravessa a virada
    # de mês chega fora de ordem: grava a r1 de trás para frente para exigir
    # que a contagem ordene por horário antes de achar a última rotina.
    ev.reverse()
    # Prompt sem sessão (hook antigo, evento truncado): não forma sessão. Uma
    # rotina seguida de prosa, para que contá-lo mudasse os dois lados da conta.
    for i, k in enumerate(["rotina", "prosa"]):
        ev.append({"ts": ts(rec, 10 + i), "event": "prompt", "kind": k})
    # Sessão recente sem rotina: não entra no denominador.
    for i in range(4):
        ev.append({"ts": ts(rec, 20 + i), "event": "prompt", "session": "r2", "kind": "prosa"})
    # Sessão antiga com rotina e 5 prompts depois dela.
    for i, k in enumerate(["rotina"] + ["prosa"] * 5):
        ev.append({"ts": ts(old, i), "event": "prompt", "session": "o1", "kind": k})
    # Builds: recentes 1 FAILURE, 2 SUCCESS, 1 EMPTY; antigos 2 FAILURE, 1 SUCCESS.
    for i, st in enumerate(["FAILURE", "SUCCESS", "SUCCESS", "EMPTY"]):
        ev.append({"ts": ts(rec, 40 + i), "event": "build_result", "repo": "x", "status": st})
    for i, st in enumerate(["FAILURE", "FAILURE", "SUCCESS"]):
        ev.append({"ts": ts(old, 40 + i), "event": "build_result", "repo": "x", "status": st})
    # Sessões: recentes cepa, wego, wego, wego; antigas cepa, cepa.
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


def secao(out, titulo):
    """As linhas da seção `## titulo`, até a próxima linha em branco."""
    linhas = out.splitlines()
    i = linhas.index(f"## {titulo}")
    bloco = []
    for l in linhas[i + 1:]:
        if not l.strip():
            break
        bloco.append(l.strip())
    return bloco


def test_texto():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ledger(tmp)
        p = run(tmp)
        check("scorecard sai com 0", p.returncode == 0, p.stderr)
        out = p.stdout
        try:
            rec = secao(out, "últimos 7 dias")
            ini = secao(out, "desde o início")
        except ValueError:
            check("as duas janelas aparecem", False, out)
            return
        esperado = {
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
        for janela, (bloco, linhas) in esperado.items():
            check(f"{janela}: exatamente três linhas", len(bloco) == 3, bloco)
            for nome, res, num, den in linhas:
                l = next((x for x in bloco if x.startswith(nome + ":")), "")
                check(f"{janela} · {nome}: resultado {res}", f": {res} " in l, l)
                check(f"{janela} · {nome}: numerador e denominador", num in l and den in l, l)
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


def test_ledger_vazio():
    with tempfile.TemporaryDirectory() as d:
        p = run(Path(d))
        check("ledger vazio sai com 0", p.returncode == 0, p.stderr)
        check("ledger vazio diz sem dados", "sem dados" in p.stdout, p.stdout)


def test_relatorio_antigo_intacto():
    # O subcomando novo não pode quebrar o relatório de sempre.
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        ledger(tmp)
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tmp))
        p = subprocess.run([sys.executable, str(METRICS), "--days", "90"],
                           capture_output=True, text=True, env=env)
        check("cepa-metrics sem subcomando continua saindo com 0", p.returncode == 0, p.stderr)
        check("relatório de sempre continua", "# Telemetria do harness" in p.stdout, p.stdout)


if __name__ == "__main__":
    test_texto()
    test_json()
    test_ledger_vazio()
    test_relatorio_antigo_intacto()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\nok")
