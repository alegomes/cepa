#!/usr/bin/env python3
"""Tests of the per-session token measurement (cepa-tokens + section of cepa-metrics).

It exists because, on 12/09/2026, the decision "copy Spotify Portal's read
detour?" depended on knowing whether reading weighs on Cepa's spend, and the ledger
had 0 events with tokens.

What the tests pin:
  - the same response repeated on several lines counts ONCE, with the usage of the
    last line (the first ones carry a partial count);
  - each subagent's spend goes to its type, read from .meta.json;
  - the size of each tool's result is attributed to the right tool;
  - the event falls in the month the session ended, not on the day of the sweep;
  - cepa-metrics counts a session recorded twice only once;
  - the SessionEnd of session-registry records the event by itself.

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


def _write(f, lines):
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(json.dumps(l) for l in lines) + "\n", encoding="utf-8")


def build_session(root: Path, cwd: str) -> Path:
    """Main session with 2 responses and 1 subagent; values chosen by hand."""
    sess = root / "proj" / "aaaabbbb-0000.jsonl"
    ts = "2026-07-15T10:00:00.000Z"
    _write(sess, [
        # response m1 on two lines (thinking + tool_use), same usage
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
    sub = root / "proj" / "aaaabbbb-0000" / "subagents" / "agent-s1.jsonl"
    _write(sub, [
        # subagent: first line partial (output 1), last with the final value (output 50)
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


def test_measurement():
    with tempfile.TemporaryDirectory() as tmp:
        sess = build_session(Path(tmp), tmp)
        p = subprocess.run([sys.executable, str(TOKENS), "--file", str(sess), "--json"],
                           capture_output=True, text=True)
        check("roda sem erro", p.returncode == 0, p.stderr)
        r = json.loads(p.stdout)[0]
        # main: m1 (10+1000 new, 5 output) + m2 (20 new, 7 output, 5000 read)
        # sub:  s1 last line (3+200 new, 50 output)
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
        subprocess.run([sys.executable, str(TOKENS), "--file", str(sess), "--emit"],
                       capture_output=True, text=True, env=env)
        file = tel / "events-2026-07.jsonl"
        check("evento cai no mês em que a sessão acabou", file.exists(),
              [f.name for f in tel.glob("*")])
        if file.exists():
            ev = json.loads(file.read_text().splitlines()[-1])
            check("evento token_usage com a chave curta da sessão",
                  ev["event"] == "token_usage" and ev["sessao"] == "aaaabbbb", ev)


def test_metrics_dedupe():
    with tempfile.TemporaryDirectory() as tmp:
        sess = build_session(Path(tmp), tmp)
        tel = Path(tmp) / "tel"
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tel))
        for _ in range(2):   # automatic end + manual sweep
            subprocess.run([sys.executable, str(TOKENS), "--file", str(sess), "--emit"],
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


def test_session_end_writes_by_itself():
    with tempfile.TemporaryDirectory() as tmp:
        sess = build_session(Path(tmp), tmp)
        tel = Path(tmp) / "tel"
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tel))
        payload = json.dumps({"session_id": "aaaabbbb-0000", "cwd": tmp,
                              "hook_event_name": "SessionEnd", "transcript_path": str(sess)})
        p = subprocess.run([sys.executable, str(REGISTRY)], input=payload,
                           capture_output=True, text=True, env=env)
        check("hook sai 0", p.returncode == 0, p.stderr)
        file = tel / "events-2026-07.jsonl"
        deadline = time.time() + 15   # the emitter runs detached from the hook
        while time.time() < deadline and not (file.exists() and "token_usage" in file.read_text()):
            time.sleep(0.2)
        check("SessionEnd grava token_usage sem ninguém pedir",
              file.exists() and "token_usage" in file.read_text())


def test_session_end_does_not_break_nor_delay():
    """The emitter may fail or be slow: the hook exits 0 and returns fast anyway.

    A large file does not serve as proof: 50 MB of transcript parse in 0.3s and
    a synchronous emitter would pass. That is why the hook runs on a copy whose
    bin/cepa-tokens is a fake that sleeps 10s or breaks."""
    import shutil
    with tempfile.TemporaryDirectory() as tmp:
        tel = Path(tmp) / "tel"
        env = dict(os.environ, CEPA_TELEMETRY_DIR=str(tel))
        transcript = Path(tmp) / "t.jsonl"
        transcript.write_bytes(b"\x00\xff{nao e json\n" * 100)
        fake_ones = {"lento": "import time\ntime.sleep(10)\n",
                  "quebrado": "raise SystemExit('cepa-tokens quebrou')\n"}
        for given_name, body in fake_ones.items():
            copy = Path(tmp) / given_name / "common"
            shutil.copytree(REGISTRY.parent, copy / "hooks")
            (copy / "bin").mkdir()
            (copy / "bin" / "cepa-tokens").write_text(body, encoding="utf-8")
            payload = json.dumps({"session_id": f"sess-{given_name}", "cwd": tmp,
                                  "hook_event_name": "SessionEnd",
                                  "transcript_path": str(transcript)})
            t0 = time.time()
            p = subprocess.run([sys.executable, str(copy / "hooks" / "session-registry.py")],
                               input=payload, capture_output=True, text=True, env=env)
            dt = time.time() - t0
            check(f"emissor {given_name}: hook sai 0", p.returncode == 0, p.stderr)
            check(f"emissor {given_name}: hook volta em menos de 3s ({dt:.1f}s)", dt < 3)
        payload = json.dumps({"session_id": "sess-ausente", "cwd": tmp,
                              "hook_event_name": "SessionEnd",
                              "transcript_path": str(Path(tmp) / "nao-existe.jsonl")})
        p = subprocess.run([sys.executable, str(REGISTRY)], input=payload,
                           capture_output=True, text=True, env=env)
        check("transcript ausente: hook sai 0", p.returncode == 0, p.stderr)


def main():
    test_measurement()
    test_metrics_dedupe()
    test_session_end_writes_by_itself()
    test_session_end_does_not_break_nor_delay()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
