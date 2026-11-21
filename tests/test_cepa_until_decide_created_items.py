#!/usr/bin/env python3
"""CS-7 of docs/spec/resposta-do-decide-vira-trabalho.md: the closing of
`cepa-until decide` lists the items the owner's answers created.

Origin (2026-11-18, kairos-etapa-1 queue of wego-digitacao-backend): the owner
answered a run of "Ponho na fila um item para ...?" and nothing on screen said
which work those answers put on the queue. CS-2 creates the declared item and
`cepa-plan answer` prints it inside each answer's output; the closing is where the
owner reads the result of the whole panel, so it ends with one line
"itens criados pelas suas respostas:" followed by the id and title of each one.

Against the real `decide`, with the real `cepa-plan answer` behind it, in a PTY
(`answer` only runs on a TTY), in a real git repo:
  - red test: one answer that creates an item ends the closing with the line and
    the item's id and title, read back from the queue;
  - two items created, one of them waiting on the owner: both listed, in answer
    order, the second marked as waiting;
  - no answer creates an item (a declared `nenhum`, a "não" kept open): no line;
  - the same on a colored terminal (`CEPA_UNTIL_COR=sempre`);
  - the panel of `--all` (entries `<queue>/<id>: ...`) names the queue too.
"""
import importlib.machinery
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import item, build_repo, CEPA_UNTIL  # noqa: E402
from test_cepa_until_decide import on_tty  # noqa: E402

FAILURES = []

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
for v in ("CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"):
    ENV.pop(v, None)

HEADER = "itens criados pelas suas respostas:"
QUESTION = "Ponho na fila um item para calibrar X?"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def route(ident, yes_item, no_item="nenhum"):
    """A `done` item with an owner route that declares the item of each answer."""
    it = item(ident, status="done", human_pending=f"decidir se calibra {ident}")
    it["route_kind"] = "open-question"
    it["owner_question"] = QUESTION
    it["owner_summary"] = {"se_sim": "um item novo calibra X",
                           "se_nao": "X fica como está",
                           "item_se_sim": yes_item, "item_se_nao": no_item}
    return it


def load_until(color):
    before = os.environ.get("CEPA_UNTIL_COR")
    os.environ["CEPA_UNTIL_COR"] = color
    try:
        name = f"cepa_until_cs7_{color}"
        loader = importlib.machinery.SourceFileLoader(name, str(CEPA_UNTIL))
        spec = importlib.util.spec_from_loader(name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
    finally:
        if before is None:
            del os.environ["CEPA_UNTIL_COR"]
        else:
            os.environ["CEPA_UNTIL_COR"] = before
    return mod


def run_decide(items, answers, color="nunca"):
    """Runs `decide` over `items` (all deferred on their route) with the owner's
    keys in `answers`; returns (closing lines without ANSI, queue items after)."""
    m = load_until(color)
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, items)
        deferred = [{"id": it["id"], "title": it["title"], "reason": "human_pending",
                     "question": it.get("owner_question"),
                     "human_pending": it["human_pending"],
                     "route_kind": it.get("route_kind"),
                     "owner_summary": it.get("owner_summary"), "evidence": None}
                    for it in items]
        keys = iter(answers)
        screen = []
        orig_run = m.subprocess.run

        def run_on_tty(cmd, **kw):
            if len(cmd) > 2 and cmd[2] == "answer":
                rc, out = on_tty(list(cmd), str(root), env=ENV)
                return subprocess.CompletedProcess(cmd, rc, out, "")
            return orig_run(cmd, **kw)
        m.subprocess.run = run_on_tty
        try:
            m.decide(root, "fila", "run1", {}, deferred, {},
                     question=lambda _p: next(keys), output=screen.append)
        finally:
            m.subprocess.run = orig_run
        after = yaml.safe_load(
            (root / ".claude" / "programs" / "fila" / "plan.yaml").read_text())["items"]
    text = ANSI.sub("", "\n".join(screen)).replace("\r", "")
    low = text.lower()
    start = max(low.rfind("answered now"), low.rfind("closing"))
    closing = text[start:] if start >= 0 else ""
    lines = [l.rstrip() for l in closing.splitlines() if l.strip()]
    return lines, after


def listed(lines):
    """The lines after the header, as the owner reads them."""
    heads = [i for i, l in enumerate(lines) if l.strip() == HEADER]
    return [l.strip() for l in lines[heads[-1] + 1:]] if heads else None


def test_red_test_one_created_item_ends_the_closing():
    lines, after = run_decide(
        [route("a1", {"titulo": "calibrar X", "precisa_do_dono": False})],
        ["y", ""])
    created = [it for it in after if it["id"] not in ("a1",)]
    check("a resposta criou um item na fila", len(created) == 1, after)
    new_id = created[0]["id"] if created else "?"
    got = listed(lines)
    check("o fechamento tem a linha 'itens criados pelas suas respostas:'",
          got is not None, "\n".join(lines))
    check("...seguida do id e do título do item, e o fechamento acaba ali",
          got == [f"{new_id} — calibrar X"], got)


def test_two_items_in_answer_order_and_the_waiting_one_marked():
    lines, after = run_decide(
        [route("a1", {"titulo": "calibrar X", "precisa_do_dono": False}),
         route("a2", {"titulo": "criar a credencial Y", "precisa_do_dono": True})],
        ["y", "", "y", ""])
    ids = [it["id"] for it in after if it["id"] not in ("a1", "a2")]
    check("as duas respostas criaram item", len(ids) == 2, ids)
    got = listed(lines)
    check("os dois aparecem, na ordem das respostas, o segundo esperando o dono",
          len(ids) == 2 and got == [f"{ids[0]} — calibrar X",
                                    f"{ids[1]} — criar a credencial Y (esperando você)"],
          got)


def test_no_line_when_no_answer_creates_an_item():
    lines, after = run_decide(
        [route("a1", "nenhum"), route("a2", {"titulo": "calibrar X",
                                              "precisa_do_dono": False})],
        ["y", "", "n", ""])
    check("nenhum item novo na fila", len(after) == 2, [it["id"] for it in after])
    check("o fechamento existe", bool(lines), lines)
    check("...e não tem a linha de itens criados",
          not any(HEADER in l for l in lines), "\n".join(lines))


def test_colored_terminal_has_the_same_line():
    lines, after = run_decide(
        [route("a1", {"titulo": "calibrar X", "precisa_do_dono": False})],
        ["y", ""], color="sempre")
    new_id = next((it["id"] for it in after if it["id"] != "a1"), "?")
    check("no terminal colorido o fechamento também termina com o item criado",
          listed(lines) == [f"{new_id} — calibrar X"], "\n".join(lines))


def test_all_panel_names_the_queue():
    m = load_until("nunca")
    out = []
    applied = ["kairos/a1: a1 → `done` em x · rota humana fechada\n"
               "  item novo criado pela resposta: a1-sim — calibrar X "
               "(no fim da fila, `pending`)"]
    m.Panel(m.SCREEN, out.append).close_panel([], applied, [], "cepa-until decide")
    got = listed([l for l in "\n".join(out).splitlines() if l.strip()])
    check("no painel de --all o item leva o nome da fila",
          got == ["kairos/a1-sim — calibrar X"], got)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAIL")
        sys.exit(1)
    print("all ok")
