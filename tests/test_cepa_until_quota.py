#!/usr/bin/env python3
"""`cepa-until` facing the account's 5h quota.

## Why it exists

On 2026-09-17 the WEGO queue hit the usage ceiling at 01:00, with reset at 3:20 and
window until 06:17. The supervisor stopped there: ~3h of window unused, and WEGO-2291
cut in the middle lost what it had already done. Two rules were born from it, and this
file proves both:

  - hit the ceiling and the reset fits in the window → waits for the reset and resumes the SAME
    item, without blaming the item nor spending its turn;
  - the 5h quota does not hold the next item → waits for the reset BEFORE
    starting, instead of starting an item that will be cut in the middle.

The fake `claude` prints the stream-json `rate_limit_event` in the real format,
copied from an execution of `claude` 2.1.276 on 2026-09-18.

Run: python3 tests/test_cepa_until_quota.py
"""

import importlib.machinery
import importlib.util
import json
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, fake_claude, item, ledger_of, build_repo, run_until)

FAILURES = []

# Wait of 1s after the reset, instead of 2min: the case measures the decision, not
# the patience.
MARGIN = {"CEPA_UNTIL_MARGEM_RESET": "1"}


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def load_module():
    loader = importlib.machinery.SourceFileLoader("cepa_until", str(CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_until", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


# Code of the fake `claude`: prints a `rate_limit_event` in the real format.
EVENT = (
    "def evento(uso, reset, status='allowed'):\n"
    "    print(json.dumps({'type': 'rate_limit_event', 'rate_limit_info': {\n"
    "        'status': status, 'resetsAt': reset, 'rateLimitType': 'five_hour',\n"
    "        'isUsingOverage': False, 'unifiedWindows': {\n"
    "            'five_hour': {'utilization': uso, 'resetsAt': reset},\n"
    "            'seven_day': {'utilization': 0.6, 'resetsAt': reset + 400000}}},\n"
    "        'uuid': 'u', 'session_id': 's'}), flush=True)\n"
    "def resultado(texto, erro=False):\n"
    "    print(json.dumps({'type': 'result', 'subtype': 'success',\n"
    "        'is_error': erro, 'result': texto}), flush=True)\n"
    "N = len(open(os.environ['FAKE_CHAMADAS']).read().splitlines())\n"
)

CEILING_TEXT = "You've hit your session limit · resets 3:20am"


def plan_of(root):
    return root / ".claude" / "programs" / "fila" / "plan.yaml"


def status(plan):
    return {it["id"]: it["status"]
            for it in yaml.safe_load(plan.read_text())["items"]}


def run_end(root):
    return [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]


# ── O1: hit the ceiling, waits for the reset ────────────────────────────────

def test_hit_the_ceiling_waits_for_the_reset_and_resumes_the_same_item():
    """The case of the night of 2026-09-17, with the reset at 2s instead of 2h20."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = EVENT + (
            "if N == 1:\n"
            "    evento(1.0, int(time.time()) + 2, 'rejected')\n"
            f"    resultado({CEILING_TEXT!r}, True)\n"
            "    sys.exit(1)\n"
            "evento(0.02, int(time.time()) + 18000)\n"
            "if N >= 3:\n"
            "    marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        start = time.monotonic()
        # The 2nd attempt really fails and the 3rd closes. With a ceiling of 2 per item,
        # this only works if the attempt cut by the ceiling did NOT count: otherwise the
        # 2nd's failure would already be the last time and a1 would become `blocked`.
        p, calls = run_until(root, binv, plan_of(root),
                           ["--for", "2h", "--attempts-per-item", "2"],
                           extra_env=MARGIN)
        spent = time.monotonic() - start
        starts = [e["id"] for e in ledger_of(root) if e.get("evento") == "item_start"]
        check("o a1 foi retomado depois do reset",
              starts == ["a1", "a1", "a1", "a2"], str(starts))
        check("...e fechou, não virou `blocked`",
              status(plan_of(root)) == {"a1": "done", "a2": "done"},
              str(status(plan_of(root))))
        check("...o supervisor dormiu até o reset", spent >= 2, f"{spent:.1f}s")
        ev = [e for e in ledger_of(root) if e.get("evento") == "limite_de_uso"]
        check("...o registro diz que esperou", ev and ev[0].get("espera") is True,
              str(ev))
        end = run_end(root)
        check("...e o run acaba pela fila; só a falha real foi contada",
              end["motivo"] == "end-of-queue" and end["sem_progresso"] == 1
              and end["esperas_de_cota"] == 1, str(end))
        check("...o relatório lista a espera",
              "Waits for the 5h quota (1)" in p.stdout, p.stdout[-600:])


def test_reset_outside_the_window_stops_instead_of_waiting():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = EVENT + (
            "evento(1.0, int(time.time()) + 5 * 3600, 'rejected')\n"
            f"resultado({CEILING_TEXT!r}, True)\n"
            "sys.exit(1)\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env=MARGIN)
        check("uma tentativa só", len(calls) == 1, f"{len(calls)}x")
        end = run_end(root)
        check("...parou com motivo limite-de-uso",
              end["motivo"] == "limite-de-uso", str(end))
        check("...dizendo que o reset não cabe na janela",
              "does not leave the minimum reserve" in (end.get("detalhe") or ""),
              end.get("detalhe"))
        check("...e o item segue pendente",
              status(plan_of(root))["a1"] == "pending")


def test_three_cutoffs_in_a_row_end_the_run():
    """A reset that does not lift the ceiling would make the supervisor wait the whole
    night in cycles. Three cuts in a row without progress end it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = EVENT + (
            "evento(1.0, int(time.time()) + 1, 'rejected')\n"
            f"resultado({CEILING_TEXT!r}, True)\n"
            "sys.exit(1)\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env=MARGIN)
        check("três tentativas e para", len(calls) == 3, f"{len(calls)}x")
        end = run_end(root)
        check("...com o motivo dizendo que o reset não levanta o teto",
              end["motivo"] == "limite-de-uso"
              and "is not lifting" in (end.get("detalhe") or ""), str(end))
        check("...e o item NÃO foi bloqueado pelo teto de tentativas",
              status(plan_of(root))["a1"] == "pending",
              str(status(plan_of(root))))


def test_item_that_closes_between_cutoffs_resets_the_count():
    """On a long night the quota hits several times, with items closing between one
    reset and another. "Three cuts in a row" is without progress BETWEEN them: without
    the reset to zero, the night's 3rd cut would end the window as if the reset did not
    lift the ceiling. Sequence: cut, cut, a1 closes, cut, a2 closes —
    without the reset to zero, the cut of the 4th call is already the 3rd and the run stops there."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = EVENT + (
            "if N in (1, 2, 4):\n"
            "    evento(1.0, int(time.time()) + 1, 'rejected')\n"
            f"    resultado({CEILING_TEXT!r}, True)\n"
            "    sys.exit(1)\n"
            "evento(0.02, int(time.time()) + 18000)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env=MARGIN)
        check("as 5 chamadas aconteceram", len(calls) == 5, f"{len(calls)}x")
        end = run_end(root)
        check("...o run acaba pela fila, não pelo teto",
              end["motivo"] == "end-of-queue" and end["esperas_de_cota"] == 3,
              str(end))
        check("...e os dois itens fecharam",
              status(plan_of(root)) == {"a1": "done", "a2": "done"},
              str(status(plan_of(root))))


def test_prose_about_the_ceiling_mid_stream_is_not_a_ceiling():
    """In stream-json the text of all turns goes to the log. An agent that
    QUOTES the message in a middle turn is not the exhausted account."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = EVENT + (
            "evento(0.3, int(time.time()) + 18000)\n"
            "print(json.dumps({'type': 'assistant', 'message': {'content': [\n"
            f"    {{'type': 'text', 'text': {CEILING_TEXT!r}}}]}}}}))\n"
            "resultado('terminei sem fechar o item')\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env=MARGIN)
        end = run_end(root)
        check("a citação não vira teto de uso",
              end["limite_de_uso"] == 0 and end["sem_progresso"] >= 1, str(end))


# ── O2: does not start an item the quota does not hold ──────────────────────

def test_pause_before_the_item_the_quota_cannot_hold():
    """a1 launches at 50%, a2 at 75%: an item costs 25 points. The 75% reading
    is from a2's launch, so it does not yet include a2: the projection for a3
    is 75 + 25 + 25 = 125%, and a3 waits for the reset. Adding the cost only once
    would give 100% and a3 would launch only to be cut in the middle."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        # The reset is born at the 1st call of the fake `claude`, not at the start of the test:
        # with the clock started before git init and the launch, a slow machine
        # let the reset pass before a3 and the case measured something else.
        reset_guard = Path(tmp) / "reset"
        body = EVENT + (
            f"G = {str(reset_guard)!r}\n"
            "if N == 1: open(G, 'w').write(str(int(time.time()) + 10))\n"
            "R = int(open(G).read())\n"
            "if N == 1: evento(0.5, R)\n"
            "elif N == 2: evento(0.75, R)\n"
            "else: evento(0.05, R + 18000)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env=MARGIN)
        ev = ledger_of(root)
        order = [e["evento"] + (":" + e["id"] if "id" in e else "") for e in ev
                 if e["evento"] in ("item_start", "pausa_de_cota")]
        check("a pausa veio antes do a3, e só dele",
              order == ["item_start:a1", "item_start:a2", "pausa_de_cota",
                        "item_start:a3"], str(order))
        a3 = [e for e in ev if e.get("evento") == "item_start" and e["id"] == "a3"]
        check("...o a3 só largou depois do reset",
              a3 and datetime.fromisoformat(a3[0]["quando"]).timestamp()
              >= int(reset_guard.read_text()),
              str(a3))
        pause = [e for e in ev if e["evento"] == "pausa_de_cota"]
        check("...o registro guarda uso e custo medido",
              pause and pause[0]["uso"] == 0.75
              and abs(pause[0]["custo_item"] - 0.25) < 1e-9, str(pause))
        check("...e os três fecharam",
              set(status(plan_of(root)).values()) == {"done"},
              str(status(plan_of(root))))


def test_ample_quota_does_not_pause():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        body = EVENT + (
            f"R = {int(time.time()) + 18000}\n"
            "evento(0.1 * N, R)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env=MARGIN)
        ev = ledger_of(root)
        check("nenhuma pausa com a cota em 10-30%",
              not [e for e in ev if e["evento"] == "pausa_de_cota"], str(ev))
        check("...e os três rodaram", len(calls) == 3, f"{len(calls)}x")


def test_pause_that_does_not_fit_the_window_starts_anyway():
    """Reset outside the window: stopping would leave the whole window unused (19:45 of
    2026-09-18, 24% of quota and 1h35 left). The cut in the middle is recoverable,
    so the item starts, with a warning and a record."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        # A single reset, fixed here: computed at each call, two calls in
        # different seconds gave different resets, the item's cost was not
        # computed and the case started measuring something else (seen on 2026-09-18).
        body = EVENT + (
            f"R = {int(time.time()) + 3 * 3600}\n"
            "evento(0.5 if N == 1 else 0.8, R)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env=MARGIN)
        check("o a3 começou assim mesmo", len(calls) == 3, f"{len(calls)}x")
        end = run_end(root)
        check("...o run terminou pela fila, com 1 item apertado",
              end["motivo"] == "end-of-queue" and end["cota_apertada"] == 1,
              str(end))
        tight = [e for e in ledger_of(root) if e.get("evento") == "cota_apertada"]
        check("...o registro nomeia o item e o uso",
              len(tight) == 1 and tight[0]["id"] == "a3"
              and tight[0]["uso"] == 0.8, str(tight))
        check("...a tela avisou antes e listou no fim",
              "starting anyway" in p.stdout
              and "Started with the quota tight (1)" in p.stdout,
              p.stdout[-600:])
        check("...e o a3 fechou", status(plan_of(root))["a3"] == "done")


def test_without_history_quota_above_90_starts_if_the_reset_does_not_fit():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = EVENT + (
            "evento(0.95, int(time.time()) + 3 * 3600)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env=MARGIN)
        check("os dois rodaram: sem histórico e acima de 90%, mas o reset "
              "(3h) não cabe na janela (2h)", len(calls) == 2,
              f"{len(calls)}x")
        check("...com o a2 registrado como apertado",
              run_end(root)["cota_apertada"] == 1, str(run_end(root)))


def test_subprocess_runs_in_stream_json():
    """Without stream-json there is no `rate_limit_event`, and the quota rule goes blind."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"])
        args = calls[0] if calls else []
        check("o `claude` recebe --output-format stream-json --verbose",
              "stream-json" in args and "--verbose" in args
              and args[args.index("--output-format") + 1] == "stream-json",
              str(args))


# ── reset time as text ──────────────────────────────────────────────────────

def test_reset_time_as_text():
    m = load_module()
    now = datetime(2026, 9, 18, 1, 0)
    check("3:20am à 01:00 é hoje",
          m.reset_time("resets 3:20am", now) == datetime(2026, 9, 18, 3, 20))
    check("8pm às 21:00 é amanhã",
          m.reset_time("resets 8pm", datetime(2026, 9, 18, 21, 0))
          == datetime(2026, 9, 19, 20, 0))
    check("12:30pm é meio-dia e meia",
          m.reset_time("resets 12:30pm", now) == datetime(2026, 9, 18, 12, 30))
    check("reset de 5min atrás é o de agora, não o de amanhã",
          m.reset_time("resets 3:20am", datetime(2026, 9, 18, 3, 25))
          == datetime(2026, 9, 18, 3, 20))
    check("com data na frente (teto semanal) não vira horário",
          m.reset_time("resets Sep 22, 4pm", now) is None)
    check("com fuso entre parênteses vira horário",
          m.reset_time("resets 3:20am (America/Sao_Paulo)", now) is not None)
    check("hora impossível não vira horário",
          m.reset_time("resets 13:00pm", now) is None)


def test_item_cost_only_compares_the_same_window():
    m = load_module()
    check("dois pares na mesma janela: o maior salto",
          abs(m.item_cost([(0.1, 1), (0.3, 1), (0.35, 1)]) - 0.2) < 1e-9)
    check("par que atravessa o reset não conta",
          m.item_cost([(0.9, 1), (0.05, 2)]) is None)
    check("uma leitura só: sem custo", m.item_cost([(0.5, 1)]) is None)


# ── herdr: the pane keeps `working` during a quota pause (CS-2) ─────────────

HERDR_HEAD = ["pane", "report-agent", "w9:p9", "--source", "cepa-until",
              "--agent", "cepa-until", "--state", "working"]


def herdr_env(tmp):
    """A fake `herdr` that appends its argv as JSON to a log. Returns (env, log)."""
    herdr = Path(tmp) / "herdr"
    log = Path(tmp) / "herdr.log"
    herdr.write_text(f"#!{sys.executable}\n"
                     "import sys, json\n"
                     f"open({str(log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
    herdr.chmod(0o755)
    return ({**MARGIN, "HERDR_ENV": "1", "HERDR_PANE_ID": "w9:p9",
             "HERDR_BIN_PATH": str(herdr)}, log)


def herdr_messages(log):
    """[(state-head ok, message, seq)] per report, in order."""
    out = []
    for line in (log.read_text().splitlines() if log.exists() else []):
        a = json.loads(line)
        msg = a[a.index("--message") + 1] if "--message" in a else None
        seq = int(a[a.index("--seq") + 1]) if "--seq" in a else None
        out.append((a[:len(HERDR_HEAD)] == HERDR_HEAD, msg, seq))
    return out


def check_pause_report(label, reports, before, paused_hhmm, after):
    msgs = [m for _, m, _ in reports]
    check(f"herdr ({label}): todo relatório é `working` como cepa-until",
          reports and all(ok for ok, _, _ in reports), str(reports))
    pauses = [i for i, m in enumerate(msgs) if m and "paused" in m]
    check(f"herdr ({label}): um relatório de pausa", len(pauses) == 1, str(msgs))
    if len(pauses) != 1:
        return
    i = pauses[0]
    check(f"herdr ({label}): a pausa diz até quando ({paused_hhmm})",
          paused_hhmm in msgs[i], msgs[i])
    check(f"herdr ({label}): a pausa vem depois do relatório de {before!r}",
          i >= 1 and msgs[i - 1] == before, str(msgs))
    check(f"herdr ({label}): ...e antes do relatório de {after!r}",
          i + 1 < len(msgs) and msgs[i + 1] == after, str(msgs))
    seqs = [s for _, _, s in reports]
    check(f"herdr ({label}): --seq estritamente crescente",
          all(x < y for x, y in zip(seqs, seqs[1:])), str(seqs))


def test_herdr_keeps_working_and_says_until_when_during_the_pause_before_an_item():
    """CS-2 of docs/spec/herdr-agent-status.md, the pause `quota_pause` decides
    before a3 (same quota readings as test_pause_before_the_item_the_quota_cannot_hold):
    herdr gets a `working` report saying it is paused and the resume time, between
    a2's report and a3's."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        reset_guard = Path(tmp) / "reset"
        body = EVENT + (
            f"G = {str(reset_guard)!r}\n"
            "if N == 1: open(G, 'w').write(str(int(time.time()) + 10))\n"
            "R = int(open(G).read())\n"
            "if N == 1: evento(0.5, R)\n"
            "elif N == 2: evento(0.75, R)\n"
            "else: evento(0.05, R + 18000)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        env, log = herdr_env(tmp)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"], extra_env=env)
        pause = [e for e in ledger_of(root) if e["evento"] == "pausa_de_cota"]
        check("herdr (antes do item): houve a pausa", len(pause) == 1, str(pause))
        if pause:
            hhmm = datetime.fromisoformat(pause[0]["acorda"]).strftime("%H:%M")
            check_pause_report("antes do item", herdr_messages(log),
                               "fila: item 2/3 a2", hhmm, "fila: item 3/3 a3")


def test_herdr_keeps_working_and_says_until_when_after_hitting_the_ceiling():
    """CS-2, the other 5h quota pause: the item was cut by the usage ceiling and the
    supervisor waits for the reset to resume the SAME item. herdr gets the pause,
    with the resume time, between the cut attempt's report and the retry's."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = EVENT + (
            "if N == 1:\n"
            "    evento(1.0, int(time.time()) + 2, 'rejected')\n"
            f"    resultado({CEILING_TEXT!r}, True)\n"
            "    sys.exit(1)\n"
            "evento(0.02, int(time.time()) + 18000)\n"
            "marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        env, log = herdr_env(tmp)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"], extra_env=env)
        cut = [e for e in ledger_of(root) if e["evento"] == "limite_de_uso"]
        check("herdr (teto): houve a espera", cut and cut[0].get("espera") is True,
              str(cut))
        if cut and cut[0].get("reset_em"):
            wake = (datetime.fromisoformat(cut[0]["reset_em"]).timestamp()
                    + float(MARGIN["CEPA_UNTIL_MARGEM_RESET"]))
            hhmm = datetime.fromtimestamp(wake).strftime("%H:%M")
            check_pause_report("teto", herdr_messages(log),
                               "fila: item 1/1 a1", hhmm, "fila: item 1/1 a1")


def main():
    print("cepa-until — cota de 5h da conta\n")
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"{given_name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
