#!/usr/bin/env python3
"""Testes da medição de tokens por sessão (cepa-tokens + seção do cepa-metrics).

Existe porque, em 12/09/2026, a decisão "copiar o desvio de leitura do Portal
da Spotify?" dependia de saber se leitura pesa no gasto do Cepa, e o ledger
tinha 0 eventos com token.

O que os testes fixam:
  - a mesma resposta repetida em várias linhas conta UMA vez, com o usage da
    última linha (as primeiras trazem contagem parcial);
  - o gasto de cada subagente vai para o tipo dele, lido do .meta.json;
  - o tamanho do resultado de cada ferramenta é atribuído à ferramenta certa;
  - o evento cai no mês em que a sessão acabou, não no dia da varredura;
  - o cepa-metrics conta uma sessão gravada duas vezes só uma vez;
  - o SessionEnd do session-registry grava o evento sozinho.

Run: python3 tests/test_cepa_tokens.py
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from _telemetria_isolada import isola

isola()

REPO = Path(__file__).resolve().parent.parent
TOKENS = REPO / "common" / "bin" / "cepa-tokens"
METRICS = REPO / "common" / "bin" / "cepa-metrics"
REGISTRY = REPO / "common" / "hooks" / "session-registry.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def _usage(i, o, cw=0, cr=0):
    return {"input_tokens": i, "output_tokens": o,
            "cache_creation_input_tokens": cw, "cache_read_input_tokens": cr}


def _escreve(f, linhas):
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(json.dumps(l) for l in linhas) + "\n", encoding="utf-8")


def monta_sessao(raiz: Path, cwd: str) -> Path:
    """Sessão principal com 2 respostas e 1 subagente; valores escolhidos à mão."""
    sess = raiz / "proj" / "aaaabbbb-0000.jsonl"
    ts = "2026-07-15T10:00:00.000Z"
    _escreve(sess, [
        # resposta m1 em duas linhas (thinking + tool_use), mesmo usage
        {"type": "assistant", "cwd": cwd, "timestamp": ts,
         "message": {"id": "m1", "model": "claude-opus-5", "usage": _usage(10, 5, cw=1000),
                     "content": [{"type": "thinking", "thinking": ""}]}},
        {"type": "assistant", "cwd": cwd, "timestamp": ts,
         "message": {"id": "m1", "model": "claude-opus-5", "usage": _usage(10, 5, cw=1000),
                     "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}]}},
        {"type": "user", "cwd": cwd, "timestamp": ts,
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t1", "content": "x" * 300}]}},
        {"type": "assistant", "cwd": cwd, "timestamp": ts,
         "message": {"id": "m2", "model": "claude-opus-5", "usage": _usage(20, 7, cr=5000),
                     "content": [{"type": "tool_use", "id": "t2", "name": "Agent", "input": {}}]}},
        {"type": "user", "cwd": cwd, "timestamp": "2026-07-15T11:00:00.000Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "t2",
              "content": [{"type": "text", "text": "y" * 40}]}]}},
    ])
    sub = raiz / "proj" / "aaaabbbb-0000" / "subagents" / "agent-s1.jsonl"
    _escreve(sub, [
        # subagente: primeira linha parcial (saída 1), última com o valor final (saída 50)
        {"type": "assistant", "timestamp": ts, "isSidechain": True,
         "message": {"id": "s1", "model": "claude-sonnet-5", "usage": _usage(3, 1, cw=200),
                     "content": [{"type": "thinking", "thinking": ""}]}},
        {"type": "assistant", "timestamp": ts, "isSidechain": True,
         "message": {"id": "s1", "model": "claude-sonnet-5", "usage": _usage(3, 50, cw=200),
                     "content": [{"type": "tool_use", "id": "u1", "name": "Bash", "input": {}}]}},
        {"type": "user", "timestamp": ts,
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "u1", "content": "z" * 60}]}},
    ])
    (sub.parent / "agent-s1.meta.json").write_text(
        json.dumps({"agentType": "build-hex:qa-engineer"}), encoding="utf-8")
    return sess


def test_medicao():
    with tempfile.TemporaryDirectory() as tmp:
        sess = monta_sessao(Path(tmp), tmp)
        p = subprocess.run([sys.executable, str(TOKENS), "--arquivo", str(sess), "--json"],
                           capture_output=True, text=True)
        check("roda sem erro", p.returncode == 0, p.stderr)
        r = json.loads(p.stdout)[0]
        # main: m1 (10+1000 novo, 5 saída) + m2 (20 novo, 7 saída, 5000 lido)
        # sub:  s1 última linha (3+200 novo, 50 saída)
        check("resposta repetida conta uma vez, com a última linha",
              r["total"] == {"entrada": 33, "cache_w": 1200, "cache_r": 5000, "saida": 62},
              r["total"])
        check("gasto do subagente vai para o tipo lido do .meta.json",
              r["por_agente"]["build-hex:qa-engineer"] ==
              {"entrada": 3, "cache_w": 200, "cache_r": 0, "saida": 50, "n": 1},
              r["por_agente"])
        check("main fica com o resto",
              r["por_agente"]["main"] == {"entrada": 30, "cache_w": 1000, "cache_r": 5000, "saida": 12},
              r["por_agente"])
        check("caracteres por ferramenta, texto em string e em lista",
              r["resultado_chars"] == {"Read": 300, "Bash": 60, "Agent": 40},
              r["resultado_chars"])

        tel = Path(tmp) / "tel"
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tel))
        subprocess.run([sys.executable, str(TOKENS), "--arquivo", str(sess), "--emit"],
                       capture_output=True, text=True, env=env)
        arq = tel / "events-2026-07.jsonl"
        check("evento cai no mês em que a sessão acabou", arq.exists(),
              [f.name for f in tel.glob("*")])
        if arq.exists():
            ev = json.loads(arq.read_text().splitlines()[-1])
            check("evento token_usage com a chave curta da sessão",
                  ev["event"] == "token_usage" and ev["sessao"] == "aaaabbbb", ev)


def test_metrics_dedupe():
    with tempfile.TemporaryDirectory() as tmp:
        sess = monta_sessao(Path(tmp), tmp)
        tel = Path(tmp) / "tel"
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tel))
        for _ in range(2):   # fim automático + varredura manual
            subprocess.run([sys.executable, str(TOKENS), "--arquivo", str(sess), "--emit"],
                           capture_output=True, text=True, env=env)
        p = subprocess.run([sys.executable, str(METRICS), "--month", "2026-07", "--json"],
                           capture_output=True, text=True, env=env)
        t = json.loads(p.stdout)["tokens"]
        check("sessão gravada duas vezes conta uma", t["sessoes_medidas"] == 1, t)
        check("contexto novo total = 33 + 1200", t["total"].get("novo") == 1233, t)
        check("subagente somado por tipo",
              t["por_agente"].get("build-hex:qa-engineer") == {"novo": 203, "n": 1}, t)

        p2 = subprocess.run([sys.executable, str(METRICS), "--month", "2026-07"],
                            capture_output=True, text=True, env=env)
        check("relatório traz a seção com memória de cálculo",
              "## Tokens" in p2.stdout and "memória de cálculo: contexto novo" in p2.stdout,
              p2.stdout[-600:])


def test_session_end_grava_sozinho():
    with tempfile.TemporaryDirectory() as tmp:
        sess = monta_sessao(Path(tmp), tmp)
        tel = Path(tmp) / "tel"
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tel))
        payload = json.dumps({"session_id": "aaaabbbb-0000", "cwd": tmp,
                              "hook_event_name": "SessionEnd", "transcript_path": str(sess)})
        p = subprocess.run([sys.executable, str(REGISTRY)], input=payload,
                           capture_output=True, text=True, env=env)
        check("hook sai 0", p.returncode == 0, p.stderr)
        arq = tel / "events-2026-07.jsonl"
        prazo = time.time() + 15   # o emissor roda destacado do hook
        while time.time() < prazo and not (arq.exists() and "token_usage" in arq.read_text()):
            time.sleep(0.2)
        check("SessionEnd grava token_usage sem ninguém pedir",
              arq.exists() and "token_usage" in arq.read_text())


def test_session_end_nao_quebra_nem_atrasa():
    """O emissor pode falhar ou demorar: o hook sai 0 e volta rápido mesmo assim.

    Arquivo grande não serve de prova: 50 MB de transcript parseiam em 0,3s e
    um emissor síncrono passaria. Por isso o hook roda numa cópia cujo
    bin/cepa-tokens é um falso que dorme 10s ou quebra."""
    import shutil
    with tempfile.TemporaryDirectory() as tmp:
        tel = Path(tmp) / "tel"
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tel))
        transcript = Path(tmp) / "t.jsonl"
        transcript.write_bytes(b"\x00\xff{nao e json\n" * 100)
        falsos = {"lento": "import time\ntime.sleep(10)\n",
                  "quebrado": "raise SystemExit('cepa-tokens quebrou')\n"}
        for nome, corpo in falsos.items():
            copia = Path(tmp) / nome / "common"
            shutil.copytree(REGISTRY.parent, copia / "hooks")
            (copia / "bin").mkdir()
            (copia / "bin" / "cepa-tokens").write_text(corpo, encoding="utf-8")
            payload = json.dumps({"session_id": f"sess-{nome}", "cwd": tmp,
                                  "hook_event_name": "SessionEnd",
                                  "transcript_path": str(transcript)})
            t0 = time.time()
            p = subprocess.run([sys.executable, str(copia / "hooks" / "session-registry.py")],
                               input=payload, capture_output=True, text=True, env=env)
            dt = time.time() - t0
            check(f"emissor {nome}: hook sai 0", p.returncode == 0, p.stderr)
            check(f"emissor {nome}: hook volta em menos de 3s ({dt:.1f}s)", dt < 3)
        payload = json.dumps({"session_id": "sess-ausente", "cwd": tmp,
                              "hook_event_name": "SessionEnd",
                              "transcript_path": str(Path(tmp) / "nao-existe.jsonl")})
        p = subprocess.run([sys.executable, str(REGISTRY)], input=payload,
                           capture_output=True, text=True, env=env)
        check("transcript ausente: hook sai 0", p.returncode == 0, p.stderr)


def main():
    test_medicao()
    test_metrics_dedupe()
    test_session_end_grava_sozinho()
    test_session_end_nao_quebra_nem_atrasa()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
