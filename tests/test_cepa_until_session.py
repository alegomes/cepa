#!/usr/bin/env python3
"""`cepa-until` records WHICH session ran each attempt, WHY it ended, and that it is alive.

## Why it exists

A run that dies at 3am leaves the morning with three questions the record could not
answer: which `claude` conversation was that (to find its transcript), did it end
because of quota, network, context or a hook, and is the reservation it holds on
another machine still alive. This file proves the answers are written:

  - `--session-id <uuid>` goes to `claude`, fresh per attempt, and `item_start` /
    `item_end` record the same id; `run_start` says `versao_registro: 2`;
  - `end_reason_of` returns one member of the closed set, in the documented precedence;
  - `estado.json` gets a `heartbeat` that advances while an item runs;
  - `cepa-plan` decides a reservation held from ANOTHER host by the heartbeat's age;
  - a `reservado` deferral lands in the record as `item_pulado`, once per item.

Run: python3 tests/test_cepa_until_session.py
"""

import importlib.machinery
import importlib.util
import json
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    fake_claude, item, ledger_of, build_repo, run_until)
from test_cepa_until_quota import (  # noqa: E402
    load_module, EVENT, CEILING_TEXT, MARGIN)

REPO = Path(__file__).resolve().parents[1]
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
FAILURES = []
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


BODY = (
    "def primeiro():\n"
    "    return primeiro_pendente()\n"
)


def plan_of(root):
    return root / ".claude" / "programs" / "fila" / "plan.yaml"


def stream(*objs):
    return "\n".join(json.dumps(o) for o in objs) + "\n"


def result(text, is_error=True, terminal=None):
    r = {"type": "result", "subtype": "success", "is_error": is_error,
         "result": text}
    if terminal:
        r["terminal_reason"] = terminal
    return r


# ── 1. session id per attempt ───────────────────────────────────────────────

def test_session_id_goes_to_claude_and_to_the_record():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, BODY + "marca(primeiro(), status='done')\n")
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"])
        ids = [c[c.index("--session-id") + 1] for c in calls if "--session-id" in c]
        check("cada chamada recebeu --session-id", len(ids) == 2 == len(calls),
              str(calls))
        check("...e é um uuid, diferente a cada chamada",
              all(UUID.match(i) for i in ids) and len(set(ids)) == 2, str(ids))
        ev = ledger_of(root)
        starts = [e for e in ev if e.get("evento") == "item_start"]
        ends = [e for e in ev if e.get("evento") == "item_end"]
        check("item_start grava o mesmo id que o claude recebeu",
              [e.get("session_id") for e in starts] == ids, str(starts))
        check("item_end grava o mesmo id",
              [e.get("session_id") for e in ends] == ids, str(ends))
        check("item_end de saída 0 traz motivo_fim `ok`",
              [e.get("motivo_fim") for e in ends] == ["ok", "ok"], str(ends))
        rs = [e for e in ev if e.get("evento") == "run_start"][0]
        check("run_start diz versao_registro 2", rs.get("versao_registro") == 2, str(rs))


# ── 2. end_reason_of ────────────────────────────────────────────────────────

def test_end_reason_covers_the_closed_set_in_precedence_order():
    m = load_module()
    f = m.end_reason_of
    rejected = stream({"type": "rate_limit_event", "rate_limit_info": {
        "status": "rejected", "resetsAt": 4102444800}})
    net = stream(result("API Error: Can't reach the API server (ENOTFOUND)",
                        terminal="api_error"))
    ctx = stream(result("Prompt is too long"))
    hook = stream(result("Stop hook blocked: o build não passou"))
    check("killed -> folga", f(-15, True, "") == "folga")
    check("code -15 -> sinal", f(-15, False, "") == "sinal")
    check("code 143 sem killed -> sinal", f(143, False, "") == "sinal")
    check("spawn falho (-2) não é sinal", f(-2, False, "") == "desconhecido")
    check("rate_limit_event rejected -> cota", f(1, False, rejected) == "cota")
    check("ENOTFOUND com api_error -> rede", f(1, False, net) == "rede")
    check("Prompt is too long -> contexto", f(1, False, ctx) == "contexto")
    check("result de erro citando hook que bloqueou -> hook",
          f(1, False, hook) == "hook")
    check("hook citado em resultado sem erro e saída 0 -> ok",
          f(0, False, stream(result("o hook blocked algo antes", is_error=False))) == "ok")
    check("saída 0 com 'context window' na prosa -> ok, não contexto",
          f(0, False, stream(result("the context window is wide enough",
                                    is_error=False))) == "ok")
    check("code 0 -> ok", f(0, False, stream(result("pronto", is_error=False))) == "ok")
    check("code 1 sem nada reconhecível -> desconhecido",
          f(1, False, stream(result("deu ruim"))) == "desconhecido")
    check("folga ganha de cota", f(1, True, rejected) == "folga")
    check("cota ganha de rede", f(1, False, rejected + net) == "cota")
    check("rede ganha de contexto",
          f(1, False, stream(result("Can't reach the API server; prompt is too long",
                                    terminal="api_error"))) == "rede")


def test_a_raising_on_tick_does_not_break_the_wait():
    m = load_module()
    import subprocess as sp
    m.HEARTBEAT_INTERVAL = 0.05
    proc = sp.Popen([sys.executable, "-c", "import time; time.sleep(1.6)"])
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("heartbeat quebrou")
    done = m.wait_for_child(proc, 10, "teste", boom)
    check("on_tick que levanta não derruba a espera do filho",
          done is True and proc.returncode == 0 and len(calls) >= 1, str(calls))


def ledger_ends(root):
    return [e for e in ledger_of(root) if e.get("evento") == "item_end"]


def test_quota_ceiling_ends_with_motivo_fim_cota_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        # Reset 5h away: outside the 2h window, so the supervisor stops instead of sleeping.
        body = EVENT + (
            "evento(1.0, int(time.time()) + 5 * 3600, 'rejected')\n"
            f"resultado({CEILING_TEXT!r}, True)\n"
            "sys.exit(1)\n")
        binv = fake_claude(tmp, body)
        run_until(root, binv, plan_of(root), ["--for", "2h"], extra_env=MARGIN)
        ends = ledger_ends(root)
        check("item_end de teto de uso grava motivo_fim `cota`",
              len(ends) == 1 and ends[0].get("motivo_fim") == "cota", str(ends))


def test_prompt_too_long_ends_with_motivo_fim_contexto_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = (
            "print(json.dumps({'type': 'result', 'subtype': 'success', "
            "'is_error': True, 'result': 'Prompt is too long'}), flush=True)\n"
            "sys.exit(1)\n")
        binv = fake_claude(tmp, body)
        run_until(root, binv, plan_of(root),
                  ["--for", "2h", "--attempts-per-item", "1"])
        ends = ledger_ends(root)
        check("item_end de 'Prompt is too long' grava motivo_fim `contexto`",
              len(ends) >= 1 and ends[0].get("motivo_fim") == "contexto", str(ends))


# ── 3. heartbeat ────────────────────────────────────────────────────────────

def test_heartbeat_advances_while_the_item_runs():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        seen = Path(tmp) / "vistos.jsonl"
        body = BODY + (
            "import glob\n"
            "def estado():\n"
            "    f = glob.glob(os.path.join(os.path.dirname(PLANO), 'until', '*.estado.json'))[0]\n"
            "    return json.load(open(f))\n"
            f"SEEN = {str(seen)!r}\n"
            "open(SEEN, 'a').write(json.dumps(estado()) + '\\n')\n"
            "time.sleep(3.3)\n"
            "open(SEEN, 'a').write(json.dumps(estado()) + '\\n')\n"
            "marca(primeiro(), status='done')\n")
        binv = fake_claude(tmp, body)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h"],
                         extra_env={"CEPA_UNTIL_HEARTBEAT": "1"})
        views = [json.loads(l) for l in seen.read_text().splitlines()]
        check("o fake leu o estado duas vezes", len(views) == 2, p.stdout[-400:] + p.stderr[-400:])
        a, b = views
        check("heartbeat avançou durante o item", a["heartbeat"] < b["heartbeat"],
              f"{a['heartbeat']} -> {b['heartbeat']}")
        check("heartbeat gravado com fuso (tzinfo presente)",
              datetime.fromisoformat(b["heartbeat"]).tzinfo is not None
              and datetime.fromisoformat(a["heartbeat"]).tzinfo is not None,
              f"{a['heartbeat']} {b['heartbeat']}")
        check("...com estado rodando e o item em voo",
              b["estado"] == "rodando" and b.get("item") == "a1"
              and b.get("fase") == "item" and UUID.match(b.get("session_id", "")),
              str(b))


# ── 4. orphan by heartbeat age (cepa-plan) ──────────────────────────────────

def load_plan_module():
    loader = importlib.machinery.SourceFileLoader("cepa_plan", str(CEPA_PLAN))
    spec = importlib.util.spec_from_loader("cepa_plan", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


OTHER_HOST = "outra-maquina.exemplo"
OTHER_TREE = "/noite/arvore-x"


def claimed(started=None):
    return {"session_id": "s-1", "pid": 4242, "hostname": OTHER_HOST,
            "cwd": OTHER_TREE, "branch": "until/x",
            "started_at": started or datetime.now().astimezone().isoformat()}


def write_state(root, heartbeat, estado="rodando", host=OTHER_HOST, tree=OTHER_TREE,
                layout="queues"):
    d = Path(root) / ".claude" / layout / "fila" / "until"
    d.mkdir(parents=True, exist_ok=True)
    body = {"run": "r", "estado": estado, "host": host, "arvore": tree,
            "heartbeat": heartbeat}
    (d / "r.estado.json").write_text(json.dumps(body), encoding="utf-8")


def ago(seconds):
    return (datetime.now() - timedelta(seconds=seconds)).isoformat(timespec="seconds")


def test_reservation_from_another_host_follows_the_heartbeat():
    m = load_plan_module()
    it = {"id": "a1", "status": "in_progress", "claimed_by": claimed()}
    with tempfile.TemporaryDirectory() as tmp:
        write_state(tmp, ago(3600))
        st, detail = m.reservation_of(it, tmp)
        check("heartbeat velho de run `rodando` -> órfã", st == "orfa", detail)
        check("...e o detalhe nomeia o arquivo e a idade",
              "r.estado.json" in detail and "heartbeat" in detail, detail)
    with tempfile.TemporaryDirectory() as tmp:
        write_state(tmp, ago(5))
        check("heartbeat fresco e rodando -> viva",
              m.reservation_of(it, tmp)[0] == "viva")
    with tempfile.TemporaryDirectory() as tmp:
        aware = (datetime.now().astimezone() - timedelta(seconds=5)).isoformat(
            timespec="seconds")
        write_state(tmp, aware)
        check("heartbeat com fuso, fresco e rodando -> viva",
              m.reservation_of(it, tmp)[0] == "viva")
        write_state(tmp, (datetime.now().astimezone()
                          - timedelta(hours=1)).isoformat(timespec="seconds"))
        check("heartbeat com fuso, velho -> órfã",
              m.reservation_of(it, tmp)[0] == "orfa")
    with tempfile.TemporaryDirectory() as tmp:
        write_state(tmp, ago(5), estado="interrompido")
        check("heartbeat fresco mas o run não está rodando -> órfã",
              m.reservation_of(it, tmp)[0] == "orfa")
    with tempfile.TemporaryDirectory() as tmp:
        write_state(tmp, ago(5), layout="programs")
        check("layout antigo (programs) também vale",
              m.reservation_of(it, tmp)[0] == "viva")
    with tempfile.TemporaryDirectory() as tmp:
        write_state(tmp, ago(3600), tree="/outra/arvore")
        check("estado de outra árvore não conta: regra de 24h -> viva",
              m.reservation_of(it, tmp)[0] == "viva")
    with tempfile.TemporaryDirectory() as tmp:
        check("sem arquivo de estado: regra de 24h, reserva recente -> viva",
              m.reservation_of(it, tmp)[0] == "viva")
        old = {"id": "a1", "status": "in_progress", "claimed_by": claimed(
            (datetime.now().astimezone() - timedelta(hours=30)).isoformat())}
        check("...e de 30h -> órfã", m.reservation_of(old, tmp)[0] == "orfa")
        check("sem root o comportamento é o de antes",
              m.reservation_of(it)[0] == "viva")


def test_reservation_messages_carry_the_heartbeat_age_and_future_falls_through():
    import re as _re
    m = load_plan_module()
    it = {"id": "a1", "status": "in_progress", "claimed_by": claimed()}
    with tempfile.TemporaryDirectory() as tmp:
        write_state(tmp, ago(300))
        st, detail = m.reservation_of(it, tmp)
        n = _re.search(r"bateu o coração há (\d+)s", detail)
        check("viva: o detalhe traz a idade do heartbeat (~300s)",
              st == "viva" and n and 300 <= int(n.group(1)) <= 310, detail)
    with tempfile.TemporaryDirectory() as tmp:
        write_state(tmp, ago(3600))
        st, detail = m.reservation_of(it, tmp)
        n = _re.search(r"tem (\d+)s", detail)
        check("órfã: o detalhe traz a idade do heartbeat (~3600s)",
              st == "orfa" and n and 3600 <= int(n.group(1)) <= 3610, detail)
    with tempfile.TemporaryDirectory() as tmp:
        write_state(tmp, ago(-7200))  # a heartbeat 2h in the future: clock skew
        check("heartbeat no futuro: não recupera a reserva, cai na regra de 24h -> viva",
              m.reservation_of(it, tmp)[0] == "viva")
        old = {"id": "a1", "status": "in_progress", "claimed_by": claimed(
            (datetime.now().astimezone() - timedelta(hours=30)).isoformat())}
        check("...e com reserva de 30h cai na regra de 24h -> órfã",
              m.reservation_of(old, tmp)[0] == "orfa")


# ── 5. item_pulado ──────────────────────────────────────────────────────────

def test_item_reserved_by_a_live_run_elsewhere_is_logged_once_as_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        reserved = item("a1", status="in_progress")
        reserved["claimed_by"] = claimed()
        root = build_repo(tmp, [reserved, item("a2")])
        write_state(root, ago(0), layout="programs")
        binv = fake_claude(tmp, BODY + "marca(primeiro(), status='done')\n")
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        ev = ledger_of(root)
        skipped = [e for e in ev if e.get("evento") == "item_pulado"]
        check("a1 reservado em outro host: um item_pulado", len(skipped) == 1
              and skipped[0]["id"] == "a1" and skipped[0]["motivo"] == "reservado",
              str(skipped))
        check("...com o detalhe que o cepa-plan devolveu",
              OTHER_HOST in str(skipped[0].get("detalhe")), str(skipped))
        check("...e o a2 rodou normalmente",
              [e["id"] for e in ev if e.get("evento") == "item_start"] == ["a2"])


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
