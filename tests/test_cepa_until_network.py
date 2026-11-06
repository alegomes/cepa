#!/usr/bin/env python3
"""`cepa-until` facing a network drop.

## Why it exists

On 2026-09-18 the internet dropped at 11:32 in the middle of WEGO-2293. `claude` exited 1
with "Can't reach the API server (ENOTFOUND)"; the next two attempts
died the same way in 3 minutes. The supervisor read three "no progress",
marked the item `blocked` and shut down through the circuit breaker. This file proves the rule
that was born from it:

  - a network drop is not the item's failure: it does not spend its turn nor count toward the
    circuit breaker;
  - the supervisor probes the network and resumes the SAME item when it comes back;
  - if it does not come back within the window, or drops three times in a row without progress
    between them, the run stops with reason `sem-rede`.

The fake `claude` prints the final `result` in the real format, copied from the `.log`
of the 2026-09-18 run.

Run: python3 tests/test_cepa_until_network.py
"""

import json
import socket
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    fake_claude, item, ledger_of, build_repo, run_until)
from test_cepa_until_quota import load_module  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# The real `result` of 2026-09-18 (fields that matter).
RESULT_WITHOUT_NETWORK = {
    "type": "result", "subtype": "success", "is_error": True,
    "terminal_reason": "api_error", "api_error_status": None,
    "stop_reason": "stop_sequence", "num_turns": 1,
    "result": "API Error: Can't reach the API server — check your internet "
              "or DNS (ENOTFOUND)"}

BODY = (
    "def sem_rede():\n"
    f"    print(json.dumps({RESULT_WITHOUT_NETWORK!r}), flush=True)\n"
    "    sys.exit(1)\n"
    "N = len(open(os.environ['FAKE_CHAMADAS']).read().splitlines())\n"
)


def plan_of(root):
    return root / ".claude" / "programs" / "fila" / "plan.yaml"


def status(plan):
    return {it["id"]: it["status"]
            for it in yaml.safe_load(plan.read_text())["items"]}


def run_end(root):
    return [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def listens_after(port, secs, by=30):
    """A local port that only starts accepting connections after `seconds`:
    the network "coming back"."""
    def body():
        time.sleep(secs)
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("127.0.0.1", port))
            s.listen(8)
            s.settimeout(0.5)
            end = time.monotonic() + by
            while time.monotonic() < end:
                try:
                    c, _ = s.accept()
                    c.close()
                except socket.timeout:
                    pass
    t = threading.Thread(target=body, daemon=True)
    t.start()
    return t


def environment(port, interval="0.5"):
    return {"CEPA_UNTIL_SONDA_REDE": f"127.0.0.1:{port}",
            "CEPA_UNTIL_SONDA_INTERVALO": interval}


# ── 1. the network drops and comes back: resumes the same item without spending its turn ─

def test_network_drop_waits_for_the_return_and_resumes_the_same_item():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = BODY + (
            "if N == 1:\n"
            "    sem_rede()\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        port = free_port()
        listens_after(port, 2)
        began = time.monotonic()
        # Ceiling of ONE attempt per item: if the drop counted as an attempt,
        # a1 would become `blocked` right away and would never be resumed.
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--attempts-per-item", "1"],
                    extra_env=environment(port))
        spent = time.monotonic() - began
        ev = ledger_of(root)
        starts = [e["id"] for e in ev if e.get("evento") == "item_start"]
        check("o a1 foi retomado quando a rede voltou",
              starts == ["a1", "a1", "a2"], str(starts))
        check("...e fechou, não virou `blocked` (a queda não gastou a vez)",
              status(plan_of(root)) == {"a1": "done", "a2": "done"},
              str(status(plan_of(root))))
        check("...o supervisor esperou a rede", spent >= 2, f"{spent:.1f}s")
        drop = [e for e in ev if e.get("evento") == "queda_de_rede"]
        check("o registro tem a queda com espera=True",
              len(drop) == 1 and drop[0]["espera"] is True
              and drop[0]["id"] == "a1", str(drop))
        check("...e a volta da rede",
              any(e.get("evento") == "rede_voltou" for e in ev), str(ev))
        check("o run terminou pela fila, não pelo disjuntor",
              run_end(root)["motivo"] == "end-of-queue"
              and run_end(root)["quedas_de_rede"] == 1, str(run_end(root)))
        check("o relatório lista a queda como não-falha",
              "Network drops (1)" in p.stdout and "NO NETWORK" in p.stdout,
              p.stdout[-800:])


def test_network_drop_does_not_count_toward_the_per_item_ceiling():
    """drop, REAL failure, closes — with a ceiling of 2 per item. If the drop counted,
    the real failure would already be the 2nd time and a1 would become `blocked`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = BODY + (
            "if N == 1:\n"
            "    sem_rede()\n"
            "if N == 2:\n"
            "    sys.exit(1)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        port = free_port()
        listens_after(port, 0)
        time.sleep(0.3)
        p, calls = run_until(root, binv, plan_of(root),
                           ["--for", "2h", "--attempts-per-item", "2"],
                           extra_env=environment(port))
        check("3 chamadas: queda, falha real, fechou",
              len(calls) == 3, str(len(calls)))
        check("o a1 fechou — a queda não gastou uma das 2 vezes",
              status(plan_of(root)) == {"a1": "done"},
              str(status(plan_of(root))))
        end = run_end(root)
        check("só a falha real conta como sem progresso",
              end["sem_progresso"] == 1 and end["esgotados"] == 0
              and end["motivo"] == "end-of-queue", str(end))


# ── 2. three drops in a row without progress stop the run ───────────────────

def test_three_drops_in_a_row_stop_the_run_without_blaming_the_item():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, BODY + "sem_rede()\n")
        port = free_port()
        listens_after(port, 0)  # the probe always sees the network
        time.sleep(0.3)
        p, calls = run_until(root, binv, plan_of(root),
                           ["--for", "2h", "--attempts-per-item", "2",
                            "--max-failures", "2"],
                           extra_env=environment(port))
        end = run_end(root)
        check("3 quedas e parou com motivo `sem-rede`",
              len(calls) == 3 and end["motivo"] == "sem-rede",
              f"{len(calls)} chamadas · {end}")
        check("...não pelo disjuntor de 2 nem pelo teto de 2 por item",
              end["sem_progresso"] == 0 and end["esgotados"] == 0, str(end))
        check("o a1 continua `pending`, sem culpa",
              status(plan_of(root)) == {"a1": "pending"},
              str(status(plan_of(root))))
        check("o detalhe explica que a sonda vê rede e o claude não",
              "drop 3 in a row" in end["detalhe"], end["detalhe"])
        events = [e for e in ledger_of(root) if e.get("evento") == "queda_de_rede"]
        check("run_end conta as 3 quedas, inclusive a que parou o run",
              end["quedas_de_rede"] == len(events) == 3,
              f"run_end={end['quedas_de_rede']} eventos={len(events)}")


# ── 3. the network does not come back in time: stops with `sem-rede` ────────

def test_network_that_does_not_return_within_the_window_stops_the_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, BODY + "sem_rede()\n")
        port = free_port()  # nobody listens: the network never comes back
        began = time.monotonic()
        # 12s window with a 3s reserve: the wait goes up to ~9s from the launch.
        p, calls = run_until(root, binv, plan_of(root),
                           ["--for", "0.2m", "--min-reserve", "0.05m"],
                           extra_env=environment(port))
        spent = time.monotonic() - began
        end = run_end(root)
        check("uma chamada só, e parou com `sem-rede`",
              len(calls) == 1 and end["motivo"] == "sem-rede",
              f"{len(calls)} chamadas · {end}")
        check("esperou até o prazo menos a reserva, não além",
              5 <= spent <= 14, f"{spent:.1f}s")
        check("o detalhe diz até quando esperou",
              "was not back by" in end["detalhe"], end["detalhe"])
        check("run_end conta a queda da qual a rede não voltou",
              end["quedas_de_rede"] == 1, str(end))
        check("o resumo do fim lista a queda sem volta",
              "not back" in p.stdout and "Network drops (1)" in p.stdout,
              p.stdout[-600:])


def test_drop_near_the_end_of_the_window_stops_without_probing():
    """The network drops when less than the minimum reserve is already left: there is nothing to
    wait for, stops right away with `sem-rede`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        # 12s window, 9s reserve: it fits to start (12 >= 9). The item spends
        # 4s and drops; by then the last useful instant (deadline - reserve = 3s) has passed.
        binv = fake_claude(tmp, BODY + "time.sleep(4)\nsem_rede()\n")
        port = free_port()  # nobody listens
        began = time.monotonic()
        p, calls = run_until(root, binv, plan_of(root),
                           ["--for", "0.2m", "--min-reserve", "0.15m"],
                           extra_env=environment(port))
        spent = time.monotonic() - began
        end = run_end(root)
        drop = [e for e in ledger_of(root) if e.get("evento") == "queda_de_rede"]
        check("parou com `sem-rede` sem tentar esperar",
              len(calls) == 1 and end["motivo"] == "sem-rede"
              and drop and drop[0]["espera"] is False,
              f"{len(calls)} chamadas · {end} · {drop}")
        check("o detalhe diz que não sobra tempo, não que esperou",
              "no time is left" in end["detalhe"], end["detalhe"])
        check("run_end conta a queda mesmo sem ter esperado",
              end["quedas_de_rede"] == 1, str(end))
        check("não ficou sondando", spent < 9, f"{spent:.1f}s")


# ── 4. an item that closes resets the drop count ────────────────────────────

def test_item_that_closes_between_drops_resets_the_count():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        # drop, drop, a1 closes, drop, drop, a2 closes. Without resetting, the 3rd
        # drop (4th call) would end the run.
        body = BODY + (
            "if N in (1, 2, 4, 5):\n"
            "    sem_rede()\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        port = free_port()
        listens_after(port, 0)
        time.sleep(0.3)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env=environment(port))
        check("6 chamadas e os dois itens fechados",
              len(calls) == 6
              and status(plan_of(root)) == {"a1": "done", "a2": "done"},
              f"{len(calls)} · {status(plan_of(root))}")
        check("o run terminou pela fila",
              run_end(root)["motivo"] == "end-of-queue", str(run_end(root)))


# ── 5. the recognizer ───────────────────────────────────────────────────────

def test_network_drop_requires_api_error_and_network_message():
    m = load_module()
    real = json.dumps(RESULT_WITHOUT_NETWORK)
    check("o result real de 2026-09-18 é queda de rede",
          m.network_drop("lixo de hook\n" + real + "\n"))
    prose = json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "o teste falhou com ENOTFOUND no mock"}]}})
    ok = json.dumps({"type": "result", "subtype": "success", "is_error": False,
                     "result": "fechei o item"})
    check("prosa de agente com ENOTFOUND + result normal NÃO é queda",
          not m.network_drop(prose + "\n" + ok + "\n"))
    ceiling = json.dumps({"type": "result", "is_error": True,
                       "terminal_reason": "api_error",
                       "result": "You've hit your session limit · resets 3:20am"})
    check("erro de API que não é de rede NÃO é queda (é do teto)",
          not m.network_drop(ceiling + "\n"))
    check("saída vazia não é queda", not m.network_drop(""))
    success_with_word = json.dumps({
        "type": "result", "subtype": "success", "is_error": False,
        "result": "corrigi o timeout ECONNRESET no teste do cliente HTTP"})
    check("result de SUCESSO com palavra de rede NÃO é queda",
          not m.network_drop(success_with_word + "\n"))
    check("o último result é o que vale",
          not m.network_drop(real + "\n" + ok + "\n"))


def test_network_wait_respects_the_deadline_and_the_return():
    m = load_module()
    n = {"v": 0}

    def probe():
        n["v"] += 1
        return n["v"] >= 3
    until_ts = datetime.now() + timedelta(seconds=10)
    began = time.monotonic()
    check("volta na 3ª sonda", m.wait_for_network(until_ts, probe, 0.1) is True
          and n["v"] == 3 and time.monotonic() - began < 2)
    began = time.monotonic()
    check("prazo vencido devolve False",
          m.wait_for_network(datetime.now() + timedelta(seconds=0.5),
                          lambda: False, 0.1) is False
          and 0.4 <= time.monotonic() - began < 2)
    port = free_port()
    check("sonda TCP: porta fechada é sem rede",
          m.network_reachable(f"127.0.0.1:{port}", timeout=1) is False)
    check("sonda TCP: alvo mal formado é sem rede, não exceção",
          m.network_reachable("semporta", timeout=1) is False)
    listens_after(port, 0, by=3)
    time.sleep(0.3)
    check("sonda TCP: porta aberta é rede",
          m.network_reachable(f"127.0.0.1:{port}", timeout=1) is True)


def main():
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"\n{given_name}")
            fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FALHA(S): {', '.join(FAILURES)}")
        return 1
    print("todos passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
