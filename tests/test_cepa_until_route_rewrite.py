#!/usr/bin/env python3
"""CS-4 of docs/spec/perguntas-da-largada-legiveis.md: the launch rewrites an old route
(an open `human_pending` with no written question or no kind) as a closed question and
records the result in the item, through `cepa-plan reword-route`.

What these cases prove:

  - on a terminal, the launch shows the reader's question (not today's fallback) and,
    afterwards, `queue.yaml` carries `route_kind`, `owner_question` and the yes/no effects
    on that item, with `human_pending`, `status` and `evidence` unchanged;
  - without a terminal the rewrite is recorded too, and nothing is asked;
  - a reader that prints garbage or fails leaves the item as it was and the launch goes on;
  - a route that already has question and kind never reaches the reader;
  - `cepa-plan reword-route` refuses what it must, fills only what is missing and never
    touches `human_pending`, `status` nor `evidence`.

Its own file (helpers borrowed from test_cepa_until_decide.py) so the proof gate can run
it alone: `python3 tests/test_cepa_until_route_rewrite.py`, exit 1 on any failure.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until_decide as base  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    check, item, build_repo, fake_claude, env_do_run, on_tty, items_of, CEPA_UNTIL,
    CEPA_PLAN)

QUESTION = "Você já liberou o acesso ao ambiente de homologação?"
IF_YES = "O item volta para a fila e o próximo run tenta de novo."
IF_NO = "O item continua esperando o acesso."
ROUTE = "falta o acesso ao ambiente de homologação"


LAST_EVENTS = []  # the run ledger's events of the last `_launch`


def old_route(ident="r1"):
    it = item(ident, human_pending=ROUTE)
    it["evidence"] = "x"
    return it


def _route_reader(tmp, mode="ok"):
    """A fake reader: for the route job (`tarefa` = reescrever-rota) it answers by `mode`;
    for the item job it answers no finding. Every call is logged as `id tarefa`."""
    script = Path(tmp) / "leitor-rota.py"
    log = Path(tmp) / "leitor-rota-chamadas.txt"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "it = json.load(sys.stdin)\n"
        f"open({str(log)!r}, 'a').write(it['id'] + ' ' + str(it.get('tarefa')) + '\\n')\n"
        f"mode = {mode!r}\n"
        "if it.get('tarefa') != 'reescrever-rota' and mode == 'itemslow':\n"
        "    import time; time.sleep(3)\n"
        "    print(json.dumps({'tipo': 'preferencia', 'texto': 'PREFTEXTO sobre o item',\n"
        "        'pergunta': 'Qual formato?', 'padrao': 'o formato curto'}))\n"
        "elif it.get('tarefa') != 'reescrever-rota':\n"
        "    print(json.dumps({'tipo': None}))\n"
        "elif mode in ('ok', 'itemslow'):\n"
        f"    print(json.dumps({{'route_kind': 'external-block', 'question': {QUESTION!r},\n"
        f"        'if_yes': {IF_YES!r}, 'if_no': {IF_NO!r}}}))\n"
        "elif mode == 'slow':\n"
        "    import time; time.sleep(3)\n"
        f"    print(json.dumps({{'route_kind': 'external-block', 'question': {QUESTION!r},\n"
        f"        'if_yes': {IF_YES!r}, 'if_no': {IF_NO!r}}}))\n"
        "elif mode == 'garbage':\n"
        "    print('this is not json')\n"
        "elif mode == 'noquestion':\n"
        f"    print(json.dumps({{'route_kind': 'external-block', 'question': 'Sem interrogação',\n"
        f"        'if_yes': {IF_YES!r}, 'if_no': {IF_NO!r}}}))\n"
        "elif mode == 'nul':\n"
        "    sys.stdout.write('{\"route_kind\":\"external-block\",\"question\":\"a\\\\u0000b?\",'\n"
        "        '\"if_yes\":\"a\",\"if_no\":\"b\"}')\n"
        "elif mode == 'surrogate':\n"
        "    sys.stdout.write('{\"route_kind\":\"external-block\",\"question\":\"a\\\\ud800b?\",'\n"
        "        '\"if_yes\":\"a\",\"if_no\":\"b\"}')\n"
        "elif mode == 'fail':\n"
        "    sys.exit(3)\n"
        "elif mode == 'hang':\n"
        "    import time; time.sleep(60)\n")
    script.chmod(0o755)
    return script, log


def _launch(items, mode="ok", tty=True, inputs=(), ceiling=None):
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, items)
        before = {k: dict(v) for k, v in items_of(root).items()}
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        reader, log = _route_reader(tmp, mode)
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(reader)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "5"
        if ceiling is not None:
            env["CEPA_UNTIL_TETO_LEITURA"] = str(ceiling)
        cmd = [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
               "--for", "2h", "--no-verify", "--no-analysis"]
        if tty:
            rc, out = on_tty(cmd, str(root), env=env, timeout=120, inputs=list(inputs))
        else:
            p = subprocess.run(cmd, capture_output=True, text=True, env=env,
                               timeout=120, stdin=subprocess.DEVNULL, cwd=str(root))
            rc, out = p.returncode, p.stdout + p.stderr
        calls = log.read_text().splitlines() if log.exists() else []
        LAST_EVENTS[:] = base._launch_events(root)
        return rc, out, before, items_of(root), calls


def _same_core(label, before, after):
    for key in ("human_pending", "status", "evidence"):
        check(f"{label}: `{key}` is unchanged", before.get(key) == after.get(key),
              f"{before.get(key)!r} -> {after.get(key)!r}")


def test_tty_launch_shows_the_readers_question_and_records_it():
    rc, out, before, after, calls = _launch(
        [old_route(), item("y1")], tty=True,
        inputs=[("homologação?", "")])  # Enter = later: the item must not change
    check("tty: the launch exits 0", rc == 0, out[-1500:])
    # on_tty rewrites the trigger it answered, so the check looks at the start of it.
    check("tty: the screen shows the reader's question",
          "Você já liberou o acesso ao ambiente de" in out, out[-1500:])
    check("tty: today's fallback is gone", "Send this item back to the queue" not in out,
          out[-1500:])
    r1 = after["r1"]
    check("tty: route_kind recorded", r1.get("route_kind") == "external-block", str(r1))
    check("tty: owner_question recorded", r1.get("owner_question") == QUESTION, str(r1))
    summary = r1.get("owner_summary") or {}
    check("tty: yes/no effects recorded",
          summary.get("se_sim") == IF_YES and summary.get("se_nao") == IF_NO, str(r1))
    _same_core("tty", before["r1"], r1)
    check("tty: the route job reached the reader", "r1 reescrever-rota" in calls,
          str(calls))


def test_launch_without_terminal_records_the_rewrite_and_asks_nothing():
    rc, out, before, after, calls = _launch([old_route(), item("y1")], tty=False)
    check("no tty: the launch exits 0", rc == 0, out[-1500:])
    r1 = after["r1"]
    check("no tty: route_kind and question recorded",
          r1.get("route_kind") == "external-block"
          and r1.get("owner_question") == QUESTION, str(r1))
    _same_core("no tty", before["r1"], r1)
    check("no tty: one line says how many routes were rewritten",
          "1 route" in out and "rewritten" in out, out[-1500:])
    check("no tty: the other item still ran", after["y1"]["status"] == "done",
          str(after["y1"]))


def test_a_reader_that_prints_garbage_or_fails_changes_nothing():
    for mode in ("garbage", "fail", "noquestion"):
        rc, out, before, after, calls = _launch([old_route(), item("y1")], mode=mode,
                                                tty=False)
        check(f"{mode}: the launch goes on and exits 0", rc == 0, out[-1500:])
        check(f"{mode}: the route item is exactly as it was", before["r1"] == after["r1"],
              f"{before['r1']} -> {after['r1']}")
        check(f"{mode}: the other item ran", after["y1"]["status"] == "done",
              str(after["y1"]))


def test_a_slow_route_reader_survives_the_item_pre_read_finishing_first():
    """The item pre-read answers at once and its pool ends while the route reader is
    still sleeping: it must not kill the other pool's reader (global _LIVE_READERS)."""
    rc, out, before, after, calls = _launch(
        [old_route(), item("y1")], mode="slow", tty=True,
        inputs=[("homologação?", "")])
    check("slow tty: the route was recorded", after["r1"].get("owner_question") == QUESTION
          and after["r1"].get("route_kind") == "external-block", str(after["r1"]))
    _same_core("slow tty", before["r1"], after["r1"])
    rc, out, before, after, calls = _launch([old_route(), item("y1")], mode="slow",
                                            tty=False)
    check("slow no tty: the route was recorded",
          after["r1"].get("owner_question") == QUESTION, str(after["r1"]))


def test_a_slow_item_pre_read_survives_the_route_reader_finishing_first():
    """The reverse: the route reader answers at once, the item reader is slow and finds a
    preference. Its finding must still come out (no tty: listed as text)."""
    rc, out, before, after, calls = _launch([old_route(), item("y1")], mode="itemslow",
                                            tty=False)
    check("item slow: the route was recorded",
          after["r1"].get("owner_question") == QUESTION, str(after["r1"]))
    check("item slow: the pre-read finding was not lost", "PREFTEXTO" in out,
          out[-1500:])


def test_a_reader_that_fails_on_a_terminal_leaves_todays_question():
    rc, out, before, after, calls = _launch(
        [old_route(), item("y1")], mode="garbage", tty=True,
        inputs=[("Send this item back to the queue", "")])
    check("tty garbage: the launch exits 0", rc == 0, out[-1500:])
    check("tty garbage: the route is still asked, with today's question",
          "Send this item back to the queue" in out, out[-1500:])
    check("tty garbage: the item is unchanged", before["r1"] == after["r1"],
          str(after["r1"]))


def test_a_route_the_reader_does_not_rewrite_within_the_ceiling_gets_the_neutral_question():
    """CS-5: the CS-4 scenario with a reader that does not answer within the ceiling.
    The old route is still asked at the launch, with the neutral question and the
    "Left for you" label (it has no kind, so no kind label applies); never with
    "done already?". The item is left exactly as it was."""
    rc, out, before, after, calls = _launch(
        [old_route(), item("y1")], mode="hang", tty=True, ceiling=2,
        inputs=[("Send this item back", "")])
    # on_tty wraps the trigger it answered in <>; colours are stripped to read the labels.
    screen = re.sub(r"\x1b\[[0-9;]*m", "", out).replace("<Send this item back>",
                                                         "Send this item back")
    check("ceiling: the launch exits 0", rc == 0, screen[-1500:])
    check("ceiling: the route job reached the reader", "r1 reescrever-rota" in calls,
          str(calls))
    check("ceiling: the screen shows the neutral question",
          "Send this item back to the queue for the next run to try again?" in screen,
          screen[-2500:])
    check("ceiling: 'Left for you' labels the route text",
          re.search(r"Left for you\s+falta o acesso", screen) is not None, screen[-2500:])
    check("ceiling: the old 'Task' label no longer stands beside the route",
          re.search(r"Task\s+falta o acesso", screen) is None, screen[-2500:])
    check("ceiling: no 'done already?'", "done already" not in out, out[-2500:])
    check("ceiling: the item is exactly as it was", before["r1"] == after["r1"],
          f"{before['r1']} -> {after['r1']}")
    check("ceiling: the other item still ran", after["y1"]["status"] == "done",
          str(after["y1"]))


def test_a_route_that_already_has_question_and_kind_is_not_read():
    done_route = old_route("r2")
    done_route.update(route_kind="owner-task", owner_question="Você já rodou a rota?",
                      owner_summary={"se_sim": IF_YES, "se_nao": IF_NO})
    rc, out, before, after, calls = _launch([done_route, item("y1")], tty=False)
    check("complete: the launch exits 0", rc == 0, out[-1500:])
    check("complete: the reader never got a route job for r2",
          not any(c.startswith("r2 ") for c in calls), str(calls))
    check("complete: the item is untouched", before["r2"] == after["r2"],
          str(after["r2"]))


def test_a_route_with_a_question_but_no_kind_is_read_and_keeps_its_question():
    half = old_route("r3")
    half["owner_question"] = "Você já rodou a rota?"
    rc, out, before, after, calls = _launch([half, item("y1")], tty=False)
    check("half: the route job reached the reader", "r3 reescrever-rota" in calls,
          str(calls))
    check("half: the kind was filled in", after["r3"].get("route_kind") == "external-block",
          str(after["r3"]))
    check("half: the written question was kept",
          after["r3"].get("owner_question") == "Você já rodou a rota?", str(after["r3"]))


def test_the_run_ledger_records_the_rewrite_and_its_failures():
    rc, out, before, after, calls = _launch([old_route(), item("y1")], tty=False)
    events = [e for e in LAST_EVENTS if e.get("evento") == "rotas_reescritas"]
    check("ledger ok: one rotas_reescritas event", len(events) == 1, str(LAST_EVENTS))
    if events:
        check("ledger ok: `reescritas` has the rewritten id and `falhas` is empty",
              events[0].get("reescritas") == ["r1"] and events[0].get("falhas") == [],
              str(events[0]))
    rc, out, before, after, calls = _launch([old_route(), item("y1")], mode="fail",
                                            tty=False)
    events = [e for e in LAST_EVENTS if e.get("evento") == "rotas_reescritas"]
    check("ledger fail: one rotas_reescritas event", len(events) == 1, str(LAST_EVENTS))
    if events:
        falhas = events[0].get("falhas") or []
        check("ledger fail: nothing rewritten and the failing reader is in `falhas`",
              events[0].get("reescritas") == [] and len(falhas) == 1
              and falhas[0].get("id") == "r1" and falhas[0].get("erro"), str(events[0]))


def test_a_reader_with_nul_or_a_lone_surrogate_does_not_kill_the_launch():
    for mode in ("nul", "surrogate"):
        rc, out, before, after, calls = _launch([old_route(), item("y1")], mode=mode,
                                                tty=False)
        check(f"{mode}: the launch exits 0", rc == 0, out[-1500:])
        check(f"{mode}: the route item is exactly as it was",
              before["r1"] == after["r1"], f"{before['r1']} -> {after['r1']}")
        check(f"{mode}: the other item ran", after["y1"]["status"] == "done",
              str(after["y1"]))


def test_parse_route_needs_owner_only_for_a_real_true():
    mod = base.load_module()
    head = '{"route_kind":"external-block","question":"a?","if_yes":"b","if_no":"c",'
    for raw, want in (('true', True), ('"false"', False), ('"true"', False), ('1', False)):
        r = mod.parse_route(head + '"item_se_nao":{"titulo":"Fazer X","precisa_do_dono":'
                            + raw + '}}')
        check(f"parse_route: precisa_do_dono {raw} -> {want}",
              r is not None and r["item_se_nao"]["precisa_do_dono"] is want, str(r))


def test_parse_route_rejects_bad_characters_and_non_strings():
    mod = base.load_module()
    for label, bad in (("NUL", "a\x00b?"), ("lone surrogate", "a\ud800b?"),
                       ("ESC sequence", "\x1b[31mred?"), ("BEL", "a\x07b?"),
                       ("DEL", "a\x7fb?"), ("bidi override", "a\u202eb?")):
        for key in ("question", "if_yes", "if_no"):
            text = bad if key == "question" else "ok " + bad
            raw = _good(**{key: text})  # json.dumps escapes the character
            check(f"parse_route: {label} in {key} is rejected",
                  mod.parse_route(raw) is None, raw)
    check("parse_route: a raw JSON \\u0000 escape is rejected",
          mod.parse_route('{"route_kind":"external-block","question":"a\\u0000b?",'
                          '"if_yes":"a","if_no":"b"}') is None)
    check("parse_route: a raw JSON \\ud800 escape is rejected",
          mod.parse_route('{"route_kind":"external-block","question":"a\\ud800b?",'
                          '"if_yes":"a","if_no":"b"}') is None)
    for label, val in (("list", ["a?"]), ("dict", {"a": "b?"}), ("number", 5),
                       ("inf", float("inf"))):
        for key in ("question", "if_yes", "if_no"):
            check(f"parse_route: a {label} in {key} is rejected",
                  mod.parse_route(_good(**{key: val})) is None)


def test_reword_route_returns_a_failure_for_arguments_subprocess_refuses():
    mod = base.load_module()
    for label, q in (("NUL", "a\x00b?"), ("lone surrogate", "a\ud800b?")):
        route = {"route_kind": "external-block", "question": q, "if_yes": "a",
                 "if_no": "b"}
        try:
            err = mod.reword_route("/nonexistent/queue.yaml", "/nonexistent", "r1", route)
        except Exception as e:  # noqa: BLE001
            err = None
            check(f"reword_route: {label} does not raise", False, repr(e))
            continue
        check(f"reword_route: {label} comes back as a failure text",
              isinstance(err, str) and err, repr(err))


def _good(**over):
    body = {"route_kind": "external-block", "question": QUESTION, "if_yes": IF_YES,
            "if_no": IF_NO}
    body.update(over)
    return json.dumps(body)


def test_parse_route_accepts_and_rejects():
    mod = base.load_module()
    ok = mod.parse_route(_good())
    check("parse_route: a complete route is accepted",
          ok == {"route_kind": "external-block", "question": QUESTION, "if_yes": IF_YES,
                 "if_no": IF_NO}, str(ok))
    check("parse_route: JSON wrapped in prose is accepted",
          mod.parse_route("Here it is:\n" + _good() + "\nDone.") is not None)
    check("parse_route: JSON in a code fence is accepted",
          mod.parse_route("```json\n" + _good() + "\n```") is not None)
    check("parse_route: a question without `?` is rejected",
          mod.parse_route(_good(question="Sem interrogação")) is None)
    check("parse_route: a kind outside the closed set is rejected",
          mod.parse_route(_good(route_kind="whatever")) is None)
    check("parse_route: a missing kind is rejected",
          mod.parse_route(json.dumps({"question": QUESTION, "if_yes": IF_YES,
                                      "if_no": IF_NO})) is None)
    for key in ("if_yes", "if_no"):
        check(f"parse_route: an empty {key} is rejected",
              mod.parse_route(_good(**{key: ""})) is None)
        check(f"parse_route: a blank {key} is rejected",
              mod.parse_route(_good(**{key: "   "})) is None)
    check("parse_route: text that is not JSON is rejected",
          mod.parse_route("this is not json") is None)


def test_is_old_route_selects_only_open_human_pending_routes():
    mod = base.load_module()

    def ad(**over):
        d = {"id": "r1", "reason": "human_pending", "human_pending": ROUTE}
        d.update(over)
        return d

    check("is_old_route: an open human_pending without question is old",
          mod.is_old_route(ad()) is True)
    check("is_old_route: a question without kind is old",
          mod.is_old_route(ad(question="Q?")) is True)
    check("is_old_route: a kind without question is old",
          mod.is_old_route(ad(route_kind="external-block")) is True)
    check("is_old_route: question and kind make it a current route",
          mod.is_old_route(ad(question="Q?", route_kind="external-block")) is False)
    for reason in ("blocked-before", "reserved", "depends-on-deferred"):
        check(f"is_old_route: reason `{reason}` is not an old route",
              mod.is_old_route(ad(reason=reason)) is False)
    for blank in (None, "", "   \n"):
        check(f"is_old_route: human_pending {blank!r} is not an old route",
              mod.is_old_route(ad(human_pending=blank)) is False)


# ── cepa-plan reword-route ───────────────────────────────────────────────────

def _reword(root, ident, kind="external-block", question=QUESTION, if_yes=IF_YES,
            if_no=IF_NO, no_item="nenhum"):
    cmd = [sys.executable, str(CEPA_PLAN), "reword-route", "fila", ident,
           "--route-kind", kind, "--repo", str(root)]
    for flag, val in (("--question", question), ("--if-yes", if_yes), ("--if-no", if_no),
                      ("--if-no-item", no_item)):
        if val is not None:
            cmd += [flag, val]
    return subprocess.run(cmd, capture_output=True, text=True)


def _plan_text(root):
    return base.plan_of(root).read_text()


def test_reword_route_refuses_and_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        done = old_route("d1")
        done["status"] = "done"
        none = item("n1")
        blocked = old_route("b1")
        blocked["status"] = "blocked"
        root = build_repo(tmp, [old_route(), done, none, blocked])
        text = _plan_text(root)
        cases = {
            "no question mark": _reword(root, "r1", question="Sem interrogação"),
            "no if-yes": _reword(root, "r1", if_yes=None),
            "no if-no": _reword(root, "r1", if_no=None),
            "no if-no-item (CS-1 of resposta-do-decide)": _reword(root, "r1", no_item=None),
            "done item": _reword(root, "d1"),
            "no human_pending": _reword(root, "n1"),
            "unknown item": _reword(root, "zz"),
            "code in the question": _reword(root, "r1",
                                            question="O commit abc1234 já passou?"),
        }
        for label, p in cases.items():
            check(f"refuses {label} with exit 2", p.returncode == 2,
                  f"{p.returncode} {p.stderr}")
            check(f"{label}: says why", bool(p.stderr.strip()), p.stderr)
        check("refusals write nothing", _plan_text(root) == text)
        ok = _reword(root, "b1")
        check("a blocked item (open) is accepted", ok.returncode == 0, ok.stderr)


def test_reword_route_fills_only_what_is_missing():
    with tempfile.TemporaryDirectory() as tmp:
        half = old_route("h1")
        half.update(owner_question="Pergunta antiga já escrita?", route_kind=None,
                    owner_summary={"pedido": "o pedido original",
                                   "se_sim": "o que o sim já dizia"})
        root = build_repo(tmp, [old_route(), half])
        p = _reword(root, "r1")
        check("fills a bare route: exit 0", p.returncode == 0, p.stderr)
        r1 = items_of(root)["r1"]
        check("bare route gets kind, question and both effects",
              r1.get("route_kind") == "external-block"
              and r1.get("owner_question") == QUESTION
              and r1["owner_summary"] == {"se_sim": IF_YES, "se_nao": IF_NO,
                                          "item_se_nao": "nenhum"}, str(r1))
        _same_core("bare", old_route(), r1)
        p = _reword(root, "h1")
        check("fills a half route: exit 0", p.returncode == 0, p.stderr)
        h1 = items_of(root)["h1"]
        check("half route keeps its question and its summary keys",
              h1["owner_question"] == "Pergunta antiga já escrita?"
              and h1["owner_summary"]["pedido"] == "o pedido original"
              and h1["owner_summary"]["se_sim"] == "o que o sim já dizia"
              and h1["owner_summary"]["se_nao"] == IF_NO
              and h1["route_kind"] == "external-block", str(h1))
        _same_core("half", {"human_pending": ROUTE, "status": "pending", "evidence": "x"},
                   h1)
        before = _plan_text(root)
        p = _reword(root, "r1", kind="owner-task", question="Outra pergunta qualquer?")
        check("a second call changes nothing and says so",
              p.returncode == 0 and _plan_text(root) == before
              and "nothing changed" in (p.stdout + p.stderr), p.stdout + p.stderr)


def test_an_interrupted_pool_kills_its_own_running_readers():
    """An exception (Ctrl-C) while a pool's readers run: the pool kills ITS OWN still
    running readers (no stray process), instead of waiting for their ceiling."""
    import os
    import time
    mod = base.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        pidfile = Path(tmp) / "leitor.pid"
        script = Path(tmp) / "leitor-longo.py"
        script.write_text(
            f"#!{sys.executable}\n"
            "import os, time\n"
            f"open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
            "time.sleep(30)\n")
        script.chmod(0o755)
        before = os.environ.get("CEPA_UNTIL_LEITOR")
        os.environ["CEPA_UNTIL_LEITOR"] = str(script)
        pid = None

        def one(it, deadline):
            if it["id"] == "boom":  # first in queue order: map raises it first
                end = time.monotonic() + 10
                while not pidfile.exists() and time.monotonic() < end:
                    time.sleep(0.02)
                time.sleep(0.2)  # let the reader write its pid fully
                raise KeyboardInterrupt
            return mod._run_reader(Path(tmp), it, deadline, "p", lambda out: out)

        raised = False
        started = time.monotonic()
        try:
            try:
                mod._read_in_parallel([{"id": "boom"}, {"id": "slow"}], one, 60)
            except KeyboardInterrupt:
                raised = True
            took = time.monotonic() - started
            check("the pool returns at once, not after the reader's 30 s",
                  took < 10, f"took {took:.1f}s")
            check("the interruption reaches the caller", raised)
            check("the long reader had started", pidfile.exists())
            pid = int(pidfile.read_text() or 0) if pidfile.exists() else None
            dead = False
            end = time.monotonic() + 5
            while pid and time.monotonic() < end:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    dead = True
                    break
                time.sleep(0.05)
            check("the pool killed its own running reader", dead,
                  f"pid {pid} still alive")
        finally:
            if pid:
                try:
                    os.killpg(pid, 9)
                except OSError:
                    pass
            if before is None:
                os.environ.pop("CEPA_UNTIL_LEITOR", None)
            else:
                os.environ["CEPA_UNTIL_LEITOR"] = before


def main():
    print("cepa-until: a largada reescreve a rota antiga e grava no item (CS-4)\n")
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"{given_name}:")
            fn()
    print()
    if base.FAILURES:
        print(f"✗ {len(base.FAILURES)} falha(s): {', '.join(base.FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
