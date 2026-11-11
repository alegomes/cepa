#!/usr/bin/env python3
"""cepa-until — an answer given in the owner panel resumes the SAME run (LL-1).

Measurement of 2026-11-10 (docs/estrategia-loops-longos.md, section 4.1): in 5
of 37 queue-empty runs the owner answered before the deadline. In 4 of them he
relaunched by hand (gaps of 8 min, 7 min, 48 min and 2h08, 3h11 in total) and
in the fifth he did not relaunch, with 11.1h of window left. The answers came
minutes after the end, at the terminal, through the end-of-run question panel,
which already runs inside the supervisor's own process.

What these cases pin:

  - in a terminal, when the queue runs dry with an item waiting on the owner
    and the window still holds `--min-reserve`, the run asks BEFORE closing,
    and a `yes` puts the item back into this same run: one `run_start`, one
    `run_end`, the item `done` in the third round;
  - an item already asked in this run is not asked again at the end;
  - `--no-resume-on-answer` keeps the old behavior (the answer applies, the
    run ends);
  - nobody answering (or the terminal closing the input) closes the run, and
    the end then LISTS what waits on the owner instead of waiting a second
    time; while the panel waits the state says `fase: aguardando-dono`;
  - a window already under `--min-reserve` ends by `prazo`, and the question
    comes only at the end, with no resume;
  - the decision of asking mid-run is a pure function, tested apart: no
    terminal, no window, a stop reason other than `end-of-queue`, or no owner
    question left means no mid-run panel.

Run with `python3 tests/test_cepa_until_resume_on_answer.py`.
"""

import json
import subprocess
import sys
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, FAILURES, check, fake_claude, item, ledger_of, build_repo)
from test_cepa_until_decide import (  # noqa: E402
    env_do_run, load_module, on_tty, plan_of)

# a1 blocks with a question on its first attempt; once the owner's answer is in
# its evidence, it closes. a2 always closes.
BLOCKS_THEN_CLOSES = (
    "ident = primeiro_pendente()\n"
    "if ident == 'a1':\n"
    "    ev = ''\n"
    "    for it in carrega()['items']:\n"
    "        if it['id'] == 'a1':\n"
    "            ev = it.get('evidence') or ''\n"
    "    if 'sim:' in ev:\n"
    "        marca(ident, status='done')\n"
    "    else:\n"
    "        marca(ident, status='blocked', evidence='não há produção',\n"
    "              owner_question='Fecho o card como medir depois do go-live?')\n"
    "elif ident:\n"
    "    marca(ident, status='done')\n")

QUESTION = "Fecho o card como medir depois do go-live?"


def items_of(root):
    return {it["id"]: it for it in
            yaml.safe_load(plan_of(root).read_text())["items"]}


def run_on_tty(tmp, root, extra=(), inputs=()):
    binv = fake_claude(tmp, BLOCKS_THEN_CLOSES)
    return on_tty(
        [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
         "--for", "2h", "--no-verify", "--no-analysis", *extra], str(root),
        inputs=list(inputs), env=env_do_run(tmp, root, binv), timeout=180)


def test_yes_in_the_panel_resumes_the_same_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        rc, out = run_on_tty(tmp, root, inputs=[
            ("[s] yes", "s"), ("Anything to add", "")])
        check("o run sai 0", rc == 0, out[-2000:])
        a1 = items_of(root)["a1"]
        check("a resposta devolve o item e o mesmo run o fecha",
              a1["status"] == "done", a1)
        events = ledger_of(root)
        kinds = [e.get("evento") for e in events]
        check("um só run: um run_start e um run_end",
              kinds.count("run_start") == 1 and kinds.count("run_end") == 1,
              kinds)
        resumed = [e for e in events if e.get("evento") == "retomada_pelo_dono"]
        check("o registro marca a retomada com o item que volta",
              len(resumed) == 1 and resumed[0].get("proximo") == "a1", resumed)
        starts = [e.get("id") for e in events if e.get("evento") == "item_start"]
        check("a1 roda de novo depois de a2", starts[-1:] == ["a1"], starts)
        check("a pergunta aparece uma vez só (o fim não repete)",
              out.count(QUESTION) == 1, out.count(QUESTION))
        end = [e for e in events if e.get("evento") == "run_end"][0]
        check("o run termina pela fila vazia, sem nada adiado",
              end.get("motivo") in ("end-of-queue", "fim-da-fila"), end)


def test_no_does_not_resume_and_is_not_asked_again():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        rc, out = run_on_tty(tmp, root, inputs=[
            ("[s] yes", "n"), ("Anything to add", "")])
        check("o run sai 0", rc == 0, out[-2000:])
        kinds = [e.get("evento") for e in ledger_of(root)]
        check("sem retomada", "retomada_pelo_dono" not in kinds, kinds)
        check("a1 continua travado", items_of(root)["a1"]["status"] == "blocked",
              items_of(root)["a1"])
        check("a pergunta aparece uma vez só", out.count(QUESTION) == 1,
              out.count(QUESTION))


def test_switch_off_keeps_the_old_end():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        rc, out = run_on_tty(tmp, root, extra=["--no-resume-on-answer"], inputs=[
            ("[s] yes", "s"), ("Anything to add", "")])
        check("o run sai 0", rc == 0, out[-2000:])
        kinds = [e.get("evento") for e in ledger_of(root)]
        check("sem retomada com a chave desligada",
              "retomada_pelo_dono" not in kinds, kinds)
        check("a resposta vale, o item volta para a fila e espera o próximo run",
              items_of(root)["a1"]["status"] == "pending", items_of(root)["a1"])


# a1 blocks with a question; a2 commits, so the run branch has a landing to offer.
BLOCKS_A1_COMMITS_A2 = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "if ident == 'a1':\n"
    "    marca(ident, status='blocked', evidence='não há produção',\n"
    "          owner_question='Fecho o card como medir depois do go-live?')\n"
    "elif ident:\n"
    "    open(ident + '.txt', 'w').write('feito')\n"
    "    subprocess.run(['git', 'add', '-A'], check=True)\n"
    "    subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                    'commit', '-qm', ident], check=True)\n"
    "    marca(ident, status='done')\n")


def watch_phases(root, seen, stop):
    """Polls the run state while the run is alive and keeps every `fase` seen:
    the panel's phase only exists while it waits."""
    d = root / ".claude" / "programs" / "fila" / "until"
    while not stop.is_set():
        for f in d.glob("*.estado.json"):
            try:
                seen.add(json.loads(f.read_text()).get("fase"))
            except (OSError, ValueError):
                pass
        time.sleep(0.1)


def silent_run(tmp, root, inputs=()):
    binv = fake_claude(tmp, BLOCKS_A1_COMMITS_A2)
    env = env_do_run(tmp, root, binv)
    env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "3"
    seen, stop = set(), threading.Event()
    t = threading.Thread(target=watch_phases, args=(root, seen, stop), daemon=True)
    t.start()
    try:
        rc, out = on_tty(
            [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
             "--for", "2h", "--no-verify", "--no-analysis"], str(root),
            inputs=list(inputs), env=env, timeout=120)
    finally:
        stop.set()
        t.join(2)
    return rc, out, seen


def test_nobody_answers_closes_and_the_end_does_not_wait_again():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        rc, out, seen = silent_run(tmp, root)
        check("o run sai 0", rc == 0, out[-2000:])
        check("o painel antes de fechar mostrou a pergunta",
              QUESTION in out, out[-2000:])
        check("diz que ninguém respondeu, uma vez só",
              out.count("nobody answered") == 1, out[-2000:])
        check("o fim não pergunta de novo (nem a aterrissagem): lista",
              "Land now?" not in out and "waiting on you" in out
              and "aterrissar" in out, out[-2000:])
        events = ledger_of(root)
        panel = [e for e in events if e.get("evento") == "painel_antes_de_fechar"]
        check("o registro marca o painel com o item perguntado",
              len(panel) == 1 and panel[0].get("itens") == ["a1"], panel)
        check("sem retomada", not any(e.get("evento") == "retomada_pelo_dono"
                                      for e in events))
        check("durante a espera o estado diz aguardando-dono",
              "aguardando-dono" in seen, seen)
        check("a1 continua travado", items_of(root)["a1"]["status"] == "blocked")


def test_terminal_closing_the_input_closes_the_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        rc, out, _seen = silent_run(tmp, root, inputs=[("[s] yes", b"\x04")])
        check("o run sai 0", rc == 0, out[-2000:])
        check("diz que a entrada fechou",
              "the terminal closed the input" in out, out[-2000:])
        check("o fim lista em vez de perguntar",
              "Land now?" not in out and "waiting on you" in out, out[-2000:])


def test_window_under_the_reserve_ends_by_deadline_and_asks_at_the_end():
    with tempfile.TemporaryDirectory() as tmp:
        stuck = item("a1", status="blocked")
        stuck["owner_question"] = QUESTION
        stuck["evidence"] = "não há produção"
        # a2 pending: with nothing runnable the launcher exits before the loop.
        root = build_repo(tmp, [stuck, item("a2")])
        rc, out = run_on_tty(tmp, root, extra=["--min-reserve", "3h"], inputs=[
            ("[s] yes", "s"), ("Anything to add", "")])
        check("o run sai 0", rc == 0, out[-2000:])
        events = ledger_of(root)
        end = [e for e in events if e.get("evento") == "run_end"]
        check("termina pelo prazo", end and end[0].get("motivo") == "prazo", end)
        check("sem painel antes de fechar e sem retomada",
              not any(e.get("evento") in ("painel_antes_de_fechar",
                                          "retomada_pelo_dono") for e in events))
        check("a pergunta veio no fim e a resposta vale para o próximo run",
              QUESTION in out and items_of(root)["a1"]["status"] == "pending",
              items_of(root)["a1"])


def test_when_to_ask_mid_run():
    m = load_module()
    q = [{"id": "a1", "reason": "blocked-before"}]
    hour, reserve = timedelta(hours=1), timedelta(minutes=45)
    check("fila vazia + terminal + janela + pergunta: pergunta",
          m.ask_mid_run("end-of-queue", hour, reserve, True, False, q))
    check("nome antigo do motivo também vale",
          m.ask_mid_run("fim-da-fila", hour, reserve, True, False, q))
    check("sem terminal: não pergunta no meio",
          not m.ask_mid_run("end-of-queue", hour, reserve, False, False, q))
    check("chave desligada: não pergunta",
          not m.ask_mid_run("end-of-queue", hour, reserve, True, True, q))
    check("janela menor que a reserva: não pergunta",
          not m.ask_mid_run("end-of-queue", timedelta(minutes=30), reserve,
                            True, False, q))
    check("parada por dependência: não pergunta",
          not m.ask_mid_run("blocked", hour, reserve, True, False, q))
    check("sem pergunta do dono: não pergunta",
          not m.ask_mid_run("end-of-queue", hour, reserve, True, False, []))
    deferred = [{"id": "a1", "reason": "blocked-before"},
                {"id": "a2", "reason": "human_pending"},
                {"id": "a3", "reason": "depends-on-deferred"},
                {"id": "a4", "reason": "reserved"}]
    picked = [d["id"] for d in m.owner_questions(deferred, asked={"a2"})]
    check("só as do dono, e ainda não perguntadas neste run",
          picked == ["a1"], picked)


def main():
    print("cepa-until — a resposta no painel retoma o mesmo run\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
