#!/usr/bin/env python3
"""The end-of-run screen has no Portuguese left — CS-5 of
docs/spec/fim-do-until-sem-espera.md.

The landing action is shown as "merge into `<branch>`" wherever it is printed, never
as `aterrissar` (the id stored in `.estado.json` and the CLI alias stay), and the
`cepa-plan` stop details are in English.

Run with `python3 tests/test_cepa_until_screen_english.py`.
"""

import importlib.machinery
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, FAILURES, check, fake_claude, item, build_repo, run_until)
from test_cepa_until_run_branch import WORKS, VERIFY, plan_of  # noqa: E402
from test_cepa_until_decide import load_module  # noqa: E402

CEPA_PLAN = CEPA_UNTIL.parent / "cepa-plan"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def load_plan():
    loader = importlib.machinery.SourceFileLoader("cepa_plan", str(CEPA_PLAN))
    spec = importlib.util.spec_from_loader("cepa_plan", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_end_of_a_run_with_one_deferred_item_has_no_portuguese():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"),
                                item("a2", human_pending="rode o login real")])
        binv = fake_claude(root.parent, WORKS)
        p, _ = run_until(root, binv, plan_of(root),
                         ["--for", "2h", "--verify", VERIFY, "--no-analysis"])
        out = ANSI.sub("", p.stdout + p.stderr)
        check("a run termina", p.returncode == 0, out[-1500:])
        check("a tela não diz aterrissar", "aterrissar" not in out, out[-1500:])
        check("a tela não diz a fila acabou", "a fila acabou" not in out, out[-1500:])
        check("a ação aparece como merge into `<branch>`",
              re.search(r"merge into `\S+`", out) is not None, out[-1500:])
        check("o detalhe de parada está em inglês, com a contagem",
              "the queue is finished: no runnable item is left, and 1 were "
              "deferred (each with its reason in the report)" in out, out[-1500:])


def test_every_other_site_that_prints_the_action():
    m = load_module()
    action = {"id": "aterrissar", "frase": "leva 3", "destino": "main"}
    old = {"id": "aterrissar", "frase": "leva 3"}

    check("o rótulo traz a branch de destino",
          m.action_label(action) == "merge into `main`", m.action_label(action))
    check("estado antigo sem destino cai para 'the clone's branch'",
          m.action_label(old) == "merge into the clone's branch", m.action_label(old))
    check("ação que não é o merge mantém o id",
          m.action_label({"id": "outra"}) == "outra")

    screen = []
    m.pending_as_text("fila", "run1", {"acoes": [action]}, [], {}, output=screen.append)
    text = "\n".join(screen)
    check("pending_as_text mostra merge into e não aterrissar",
          "merge into `main`: leva 3" in text and "aterrissar" not in text, text)

    screen = []
    state_dict = {"estado": "fim", "acoes": [action]}
    answers = iter(["s"])
    applied, after = m.decide(
        Path("/nao/existe"), "fila", "run1", state_dict, [], {},
        question=lambda _p: next(answers), output=screen.append,
        answer=lambda i, t, keep=False: (0, "ok"), land=lambda: 0)
    text = ANSI.sub("", "\n".join(screen))
    check("o cartão do decide não diz aterrissar",
          "aterrissar" not in text and "merge into `main`" in text, text)
    check("o aplicado diz merge into", applied == ["merge into `main`"], applied)

    screen = []
    answers = iter(["n"])
    applied, after = m.decide(
        Path("/nao/existe"), "fila", "run1", state_dict, [], {},
        question=lambda _p: next(answers), output=screen.append,
        answer=lambda i, t, keep=False: (0, "ok"), land=lambda: 0)
    check("o que fica para depois diz merge into e mantém o comando",
          any(x.startswith("merge into `main`: cepa-until land fila/run1 --yes")
              for x in after), after)


def test_land_refusal_does_not_print_the_id():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "land", "fila/nao-existe"],
                           cwd=str(root), capture_output=True, text=True)
        check("land de run inexistente não imprime aterrissar",
              "aterrissar" not in p.stdout + p.stderr, p.stdout + p.stderr)


def test_cepa_plan_stop_details_are_in_english():
    mod = load_plan()
    items = [{"id": "A", "title": "a", "why": "porque", "status": "pending",
              "blocked_by": [], "human_pending": None},
             {"id": "B", "title": "b", "why": "porque", "status": "pending",
              "blocked_by": [], "human_pending": "rode o login"}]
    _, stop, _, deferred = mod.build_batch(items, 10)
    check("com adiado: o detalhe em inglês",
          stop["detail"] == "the queue is finished: no runnable item is left, and "
          f"{len(deferred)} were deferred (each with its reason in the report)",
          stop["detail"])
    _, stop, _, _ = mod.build_batch([items[0]], 10)
    check("sem adiado: o detalhe em inglês",
          stop["detail"] == "the queue is finished: no pending item is left",
          stop["detail"])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    sys.exit(1 if FAILURES else 0)
