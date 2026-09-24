#!/usr/bin/env python3
"""cepa-until-digest — o resumo mecânico de um run do `cepa-until`.

O `.log` de um run real passa de 10 MB. O resumo tem de trazer, de cada
rodada, o relatório final, os agentes chamados, os erros de ferramenta e o
custo, e de cada item tocado o estado ATUAL na fila — e dizer quando o
pareamento registro↔log não fecha, em vez de parear errado calado.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
DIGEST = REPO / "common" / "bin" / "cepa-until-digest"
FAILURES = []


def check(nome, cond, detalhe=""):
    print(("  ok  " if cond else "FAIL  ") + nome + ("" if cond else f"  {detalhe}"))
    if not cond:
        FAILURES.append(nome)


def rodada(texto_final, agentes=(), erro=None, custo=0.5):
    linhas = [json.dumps({"type": "system", "subtype": "init"})]
    for a in agentes:
        linhas.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Agent",
             "input": {"subagent_type": a}}]}}))
    if erro:
        linhas.append(json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "is_error": True, "content": erro}]}}))
    linhas.append(json.dumps({"type": "result", "subtype": "success",
                              "result": texto_final, "total_cost_usd": custo,
                              "num_turns": 9}))
    return "\n".join(linhas) + "\n"


def monta_run(tmp, n_rodadas_no_log=2):
    fila = Path(tmp) / ".claude" / "programs" / "F"
    until = fila / "until"
    until.mkdir(parents=True)
    (fila / "plan.yaml").write_text(yaml.safe_dump({"items": [
        {"id": "A1", "status": "done", "blocked_by": [],
         "evidence": "commits abc; build verde"},
        {"id": "A2", "status": "blocked", "blocked_by": [],
         "evidence": "depende do A1 que não está na main"}]}), encoding="utf-8")
    ev = [{"evento": "run_start", "fila": "F", "branch": "until/r",
           "base": "deadbeef00", "verify": "./mvnw -B clean verify"},
          {"evento": "item_start", "id": "A1", "title": "um"},
          {"evento": "item_end", "id": "A1", "status": "done", "segundos": 10,
           "exit_code": 0, "commits": 3, "tentativa": 1},
          {"evento": "verify", "id": "A1", "verde": True, "segundos": 5},
          {"evento": "item_start", "id": "A2", "title": "dois"},
          {"evento": "item_end", "id": "A2", "status": "blocked", "segundos": 4,
           "exit_code": 0, "commits": 0, "tentativa": 1},
          {"evento": "run_end", "motivo": "fim-da-fila", "detalhe": "acabou",
           "itens": 2, "entregues": 1, "travados": 1}]
    ledger = until / "r.jsonl"
    ledger.write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    log = ("\n===== t · claude -p /common:drain-plan F --max 1\n"
           + rodada("RELATORIO A1 " + "x" * 50,
                    agentes=["build-hex:engineering-lead",
                             "common:completion-auditor"],
                    erro="Exit code 1 mvn quebrou", custo=1.25)
           + "\n===== t · verify · ./mvnw -B clean verify\n"
           + "\n".join(f"linha {i}" for i in range(40)) + "\nBUILD SUCCESS\n")
    if n_rodadas_no_log >= 2:
        log += ("\n===== t · claude -p /common:drain-plan F --max 1\n"
                + rodada("RELATORIO A2 travou", custo=0.25))
    (until / "r.log").write_text(log)
    return ledger


def roda(ledger, *args):
    return subprocess.run([sys.executable, str(DIGEST), str(ledger), *args],
                          capture_output=True, text=True, timeout=60)


def test_resumo_traz_o_que_cada_rodada_disse_e_fez():
    with tempfile.TemporaryDirectory() as tmp:
        p = roda(monta_run(tmp))
        out = p.stdout
        check("sai 0", p.returncode == 0, p.stderr)
        check("traz o relatório final de cada rodada",
              "RELATORIO A1" in out and "RELATORIO A2 travou" in out)
        check("pareia cada relatório com o item certo",
              out.index("RELATORIO A1") < out.index("### 2. A2"))
        check("conta os agentes por tipo",
              "build-hex:engineering-lead ×1" in out
              and "common:completion-auditor ×1" in out)
        check("traz os erros de ferramenta", "mvn quebrou" in out)
        check("traz a cauda do build do supervisor, não a saída inteira",
              "BUILD SUCCESS" in out and "linha 39" in out
              and "linha 5\n" not in out)
        check("traz o estado atual da fila com a evidence",
              "depende do A1 que não está na main" in out)
        check("soma o custo com a origem da conta",
              "US$ 1.50" in out and "total_cost_usd" in out, out[-300:])
        check("traz os commits de cada item na branch da noite",
              "commits na branch da noite: 3" in out)


def test_relatorio_longo_e_cortado_e_diz_que_cortou():
    with tempfile.TemporaryDirectory() as tmp:
        p = roda(monta_run(tmp), "--result-max", "20")
        check("o corte é declarado", "[… cortado]" in p.stdout)


def test_pareamento_que_nao_fecha_e_avisado():
    with tempfile.TemporaryDirectory() as tmp:
        p = roda(monta_run(tmp, n_rodadas_no_log=1))
        check("avisa quando registro e log discordam",
              "ATENÇÃO: 2 item_start" in p.stdout, p.stdout[:800])


def test_registro_inexistente_sai_2():
    p = roda("/nao/existe.jsonl")
    check("registro inexistente sai 2", p.returncode == 2, p.stderr)


def main():
    print("cepa-until-digest\n")
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"{nome}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
