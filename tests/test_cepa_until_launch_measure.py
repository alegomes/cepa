#!/usr/bin/env python3
"""CS-13 of docs/spec/perguntar-antes-do-run.md: the launch records its measurement in the
run ledger. After a launch with 1 route answered, 1 route summarized (answered "no"
before) and 1 pre-read finding, `<run>.jsonl` carries a `largada` event with the items
that run, the items that wait, questions shown, questions answered, routes summarized,
items read, findings by kind and seconds spent.

Its own file (helpers borrowed from test_cepa_until_decide.py) so the proof gate can run
it alone: `python3 tests/test_cepa_until_launch_measure.py`, exit 1 on any failure.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until_decide as base  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    check, item, build_repo, fake_claude, env_do_run, on_tty, _fake_reader,
    _launch_events, _answered, CEPA_UNTIL)

FIELDS = ("rodam", "esperam", "perguntas_mostradas", "perguntas_respondidas",
          "rotas_resumidas", "itens_lidos", "achados", "segundos")


def _queue():
    r1 = item("r1", human_pending="provision the Keycloak role")
    n1 = item("n1", human_pending="old route text")
    n1["evidence"] = _answered("2026-11-02")
    return [r1, n1, item("x1"), item("y1")]


def _launch(tty):
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, _queue())
        binv = fake_claude(tmp, "pass")
        reader, _ = _fake_reader(tmp, "pref")  # x1 -> one preference, y1 -> nothing
        env = env_do_run(tmp, root, binv)
        env["CEPA_UNTIL_LEITOR"] = str(reader)
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "5"
        cmd = [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
               "--for", "2h", "--no-verify", "--no-analysis"]
        if tty:
            # r1's route: "y" (answered); the preference on x1: Enter (default kept,
            # not answered by the owner).
            rc, out = on_tty(cmd, str(root), env=env, timeout=120, inputs=[
                ("[t] I write the answer", "y"), ("Anything to add", ""),
                ("Your choice, in one line", "")])
        else:
            p = subprocess.run(cmd, capture_output=True, text=True, env=env,
                               timeout=120, stdin=subprocess.DEVNULL)
            rc, out = p.returncode, p.stdout + p.stderr
        return rc, out, _launch_events(root)


def _the_event(label, rc, out, events):
    check(f"{label}: the run exits 0", rc == 0, out[-1500:])
    found = [e for e in events if e.get("evento") == "largada"]
    check(f"{label}: exactly one `largada` event in the ledger", len(found) == 1,
          str([e.get("evento") for e in events]) + out[-1500:])
    if not found:
        return {}
    ev = found[0]
    names = [e.get("evento") for e in events]
    check(f"{label}: it comes after run_start and before the first item",
          names.index("run_start") < names.index("largada")
          < (names.index("item_start") if "item_start" in names else len(names)),
          str(names))
    check(f"{label}: it carries every field", all(k in ev for k in FIELDS), str(ev))
    check(f"{label}: seconds spent is a non-negative number",
          isinstance(ev.get("segundos"), (int, float)) and ev["segundos"] >= 0, str(ev))
    return ev


def test_launch_measure_cs13_on_terminal():
    """The declared red test: 1 route answered, 1 summarized, 1 pre-read finding."""
    ev = _the_event("cs13 tty", *_launch(tty=True))
    if not ev:
        return
    check("cs13 tty: 2 items run at the launch (x1, y1)", ev.get("rodam") == 2, str(ev))
    check("cs13 tty: 2 items wait for the owner (r1, n1)", ev.get("esperam") == 2, str(ev))
    check("cs13 tty: 2 questions shown (r1's route and x1's preference)",
          ev.get("perguntas_mostradas") == 2, str(ev))
    check("cs13 tty: 1 question answered (r1; Enter on the preference is not an answer)",
          ev.get("perguntas_respondidas") == 1, str(ev))
    check("cs13 tty: 1 route summarized (n1, answered no before)",
          ev.get("rotas_resumidas") == 1, str(ev))
    check("cs13 tty: 2 items read (x1, y1)", ev.get("itens_lidos") == 2, str(ev))
    check("cs13 tty: findings by kind: 1 preference, 0 pre-condition",
          ev.get("achados") == {"pre-condicao": 0, "preferencia": 1}, str(ev))


def test_launch_measure_cs13_without_terminal_records_no_panel():
    """No terminal: the pre-read runs, the panel does not; the event still says so."""
    ev = _the_event("cs13 no tty", *_launch(tty=False))
    if not ev:
        return
    check("cs13 no tty: 2 run, 2 wait", ev.get("rodam") == 2 and ev.get("esperam") == 2,
          str(ev))
    check("cs13 no tty: no question shown nor answered, no route summarized",
          ev.get("perguntas_mostradas") == 0 and ev.get("perguntas_respondidas") == 0
          and ev.get("rotas_resumidas") == 0, str(ev))
    check("cs13 no tty: 2 items read, 1 preference found",
          ev.get("itens_lidos") == 2
          and ev.get("achados") == {"pre-condicao": 0, "preferencia": 1}, str(ev))


def test_launch_measure_cs13_panel_cut_after_the_first_answer():
    """The common case (32 of 37 runs with no answer): three routes, the owner answers
    the first and then is gone. Only the two questions that reached the screen count as
    shown, and the answer given before the cut still counts (pair review finding)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item(f"r{i}", human_pending=f"route number {i}")
                                for i in (1, 2, 3)] + [item("y1")])
        binv = fake_claude(tmp, "pass")
        env = env_do_run(tmp, root, binv)  # pre-read off
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "3"
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"], str(root), env=env,
            timeout=120, inputs=[("[t] I write the answer", "y"), ("Anything to add", "")])
        events = _launch_events(root)
    ev = _the_event("cs13 cut", rc, out, events)
    if not ev:
        return
    check("cs13 cut: the panel really was cut by the wait", "nobody answered" in out,
          out[-1500:])
    check("cs13 cut: 2 questions shown (r1 answered, r2 unanswered; r3 never shown)",
          ev.get("perguntas_mostradas") == 2, str(ev))
    check("cs13 cut: the answer given before the cut counts",
          ev.get("perguntas_respondidas") == 1, str(ev))
    check("cs13 cut: forecast 1 runs, 3 wait",
          ev.get("rodam") == 1 and ev.get("esperam") == 3, str(ev))


def main():
    print("cepa-until — a largada grava a medição no registro do run (CS-13)\n")
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
