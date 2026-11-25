#!/usr/bin/env python3
"""CS-5 of docs/spec/resposta-do-decide-vira-trabalho.md: an answer with no way
back, on an old route that declares no item, warns instead of staying silent.

Origin (2026-11-18, kairos-etapa-1 queue of wego-digitacao-backend): the owner
answered "sim" to "Ponho na fila um item para ...?" on routes written before the
item declaration existed; the answer only closed the route and the output said
"rota humana fechada", nothing more. CS-2 creates the declared item; a route with
no declaration has nothing to create, so the least it owes the owner is to say so.

Against the real CLI, in a real git repo, in a PTY (`answer` only runs on a TTY):
  - red test: `done` item with an old route (no `item_se_sim`/`item_se_nao`):
    `answer --answer "sim: ..."` records the answer, creates nothing, and prints
    "esta resposta não cria trabalho" with a `cepa-queue add <fila> ...` line ready
    to copy, which, run as printed, adds a valid item;
  - the same for a route with no `owner_summary` at all, and for a "não" that
    closes the route;
  - no warning when the route declares `nenhum`, when the declared item is
    created, on `--keep` (the question stays open), on `--drop` (the owner gave
    the leftover up) and on a `blocked` item (its "sim" returns it to the queue);
  - the closing of `cepa-run decide` repeats the warning for each such item.
"""
import importlib.machinery
import importlib.util
import os
import shlex
import subprocess
import sys
import tempfile

import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import item, build_repo, CEPA_UNTIL  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, on_tty, items_of  # noqa: E402

FAILURES = []

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
for v in ("CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"):
    ENV.pop(v, None)

WARNING = "esta resposta não cria trabalho"
ROUTE = "decidir se calibra X"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def old_route(ident, status="done", summary=True, yes_item=None, no_item=None):
    """A route as written before CS-1: question and effects, no item declared."""
    it = item(ident, status=status, human_pending=ROUTE)
    it["route_kind"] = "open-question"
    it["owner_question"] = "Ponho na fila um item para calibrar X?"
    if summary:
        s = {"se_sim": "um item novo calibra X", "se_nao": "X fica como está"}
        if yes_item is not None:
            s["item_se_sim"] = yes_item
        if no_item is not None:
            s["item_se_nao"] = no_item
        it["owner_summary"] = s
    return it


def answer(root, ident, text, *extra):
    return on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila", ident,
                   "--answer", text, "--repo", str(root), "--no-commit"]
                  + list(extra), str(root), env=ENV)


def ordered(root):
    plan = yaml.safe_load(
        (root / ".claude" / "programs" / "fila" / "plan.yaml").read_text())
    return plan["items"]


def add_line(out):
    lines = [l.strip() for l in out.replace("\r", "").splitlines()
             if l.strip().startswith("cepa-queue add ")]
    return lines[0] if lines else None


def test_red_test_old_route_yes_warns_with_the_add_command():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [old_route("a1"), item("a2")])
        rc, out = answer(root, "a1", "sim: pode calibrar")
        check("answer sai 0", rc == 0, out)
        items = ordered(root)
        check("nada é criado", len(items) == 2, [i["id"] for i in items])
        a1 = items_of(root)["a1"]
        check("a resposta é gravada e a rota fecha",
              "sim: pode calibrar" in str(a1.get("evidence"))
              and a1["human_pending"] is None and a1["status"] == "done", a1)
        check("a evidência registra que a resposta não criou item",
              "A resposta não criou item" in str(a1.get("evidence")), a1)
        check("a saída diz que a resposta não cria trabalho", WARNING in out, out)
        line = add_line(out)
        check("a saída traz um `cepa-queue add` da mesma fila",
              line is not None and line.startswith("cepa-queue add fila "), out)
        if line is None:
            return
        argv = shlex.split(line)
        p = subprocess.run([sys.executable, str(CEPA_PLAN)] + argv[1:]
                           + ["--repo", str(root), "--no-commit"],
                           capture_output=True, text=True, env=ENV)
        check("o comando, copiado como está, adiciona o item (sai 0)",
              p.returncode == 0, p.stderr + p.stdout)
        items = ordered(root)
        check("...no fim da fila, `pending`",
              len(items) == 3 and items[-1]["status"] == "pending", items[-1:])
        check("...com o título da rota, que o dono edita se quiser",
              items[-1].get("title") == ROUTE, items[-1])
        check("...e o `why` diz que veio da resposta ao item respondido",
              "pedido pela resposta do dono a a1" in str(items[-1].get("why")),
              items[-1])


def test_route_without_owner_summary_also_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [old_route("a1", summary=False)])
        rc, out = answer(root, "a1", "sim: feito")
        check("sem owner_summary: sai 0 e avisa", rc == 0 and WARNING in out, out)
        check("sem owner_summary: traz o comando", add_line(out) is not None, out)


def test_no_that_closes_an_old_route_also_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [old_route("a1", yes_item="nenhum")])
        rc, out = answer(root, "a1", "não: deixa assim")
        check("'não' sem item declarado para o 'não': avisa",
              rc == 0 and WARNING in out, out)


def test_blank_declaration_counts_as_none_declared():
    """A blank declaration creates nothing (`answer_creates` wants a title), so
    it warns like an absent one: as a blank string and as a blank title."""
    for name, decl in (("texto em branco", "   "),
                       ("título em branco", {"titulo": "  ", "precisa_do_dono": False}),
                       ("título nulo", {"titulo": None, "precisa_do_dono": False})):
        with tempfile.TemporaryDirectory() as tmp:
            root = build_repo(tmp, [old_route("a1", yes_item=decl, no_item="nenhum")])
            rc, out = answer(root, "a1", "sim: ok")
            check(f"declaração com {name}: nada é criado e avisa",
                  rc == 0 and len(ordered(root)) == 1 and WARNING in out
                  and add_line(out) is not None, out)


def test_suggested_id_skips_one_the_queue_has():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [old_route("a1"), item("a1-sim")])
        rc, out = answer(root, "a1", "sim: pode calibrar")
        line = add_line(out) or ""
        check("com a1-sim ocupado, o comando sugere a1-sim-2",
              rc == 0 and shlex.split(line)[3:4] == ["a1-sim-2"], out)


def test_blank_route_gets_a_title_that_names_the_item():
    with tempfile.TemporaryDirectory() as tmp:
        it = old_route("a1")
        it["human_pending"] = "   "
        root = build_repo(tmp, [it])
        rc, out = answer(root, "a1", "sim: ok")
        argv = shlex.split(add_line(out) or "x")
        title = argv[argv.index("--title") + 1] if "--title" in argv else None
        check("rota em branco: o título do comando cita o item respondido",
              rc == 0 and title == "trabalho pedido pela resposta a a1", out)


def test_no_warning_when_the_answer_is_accounted_for():
    cases = [
        ("`nenhum` declarado", old_route("a1", yes_item="nenhum", no_item="nenhum"),
         "sim: ok", ()),
        ("`Nenhum ` editado à mão", old_route("a1", yes_item=" Nenhum ", no_item="nenhum"),
         "sim: ok", ()),
        ("item declarado e criado",
         old_route("a1", yes_item={"titulo": "calibrar X", "precisa_do_dono": False},
                   no_item="nenhum"), "sim: ok", ()),
        ("--keep deixa a pergunta aberta", old_route("a1"), "não: espera", ("--keep",)),
        ("--drop dá a tarefa por encerrada", old_route("a1"), "sim: esquece", ("--drop",)),
        ("item blocked volta para a fila", old_route("a1", status="blocked"),
         "sim: segue", ()),
    ]
    for name, it, text, extra in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = build_repo(tmp, [it])
            rc, out = answer(root, "a1", text, *extra)
            check(f"{name}: sai 0 sem o aviso", rc == 0 and WARNING not in out
                  and add_line(out) is None, out)


def load_until():
    before = os.environ.get("CEPA_UNTIL_COR")
    os.environ["CEPA_UNTIL_COR"] = "nunca"
    try:
        loader = importlib.machinery.SourceFileLoader("cepa_until_cs5",
                                                      str(CEPA_UNTIL))
        spec = importlib.util.spec_from_loader("cepa_until_cs5", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
    finally:
        if before is None:
            del os.environ["CEPA_UNTIL_COR"]
        else:
            os.environ["CEPA_UNTIL_COR"] = before
    return mod


def test_decide_closing_repeats_the_warning_for_each_item():
    """The real `cepa-queue answer` runs behind `decide` (no injected `answer`),
    so the closing reads what the owner's answer really printed."""
    m = load_until()
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [old_route("a1"), old_route("a2"),
                                old_route("a3", yes_item="nenhum", no_item="nenhum")])
        deferred = [{"id": i, "title": f"item {i}", "reason": "human_pending",
                     "question": "Ponho na fila um item para calibrar X?",
                     "human_pending": ROUTE, "evidence": None}
                    for i in ("a1", "a2", "a3")]
        answers = iter(["y", "", "y", "", "y", ""])
        screen = []
        # `cepa-queue answer` needs a TTY: run decide's own subprocess under one.
        orig_run = m.subprocess.run

        def run_on_tty(cmd, **kw):
            if len(cmd) > 2 and cmd[2] == "answer":
                rc, out = on_tty(list(cmd), str(root), env=ENV)
                return subprocess.CompletedProcess(cmd, rc, out, "")
            return orig_run(cmd, **kw)
        m.subprocess.run = run_on_tty
        try:
            m.decide(root, "fila", "run1", {}, deferred, {},
                     question=lambda _p: next(answers), output=screen.append)
        finally:
            m.subprocess.run = orig_run
        text = "\n".join(screen)
        closing = text.split("Answered now")[-1] if "Answered now" in text else ""
        check("o fechamento existe", bool(closing), text[-1500:])
        warned = [l for l in closing.splitlines() if WARNING in l]
        check("o fechamento repete o aviso para a1 e a2",
              any("a1" in l for l in warned) and any("a2" in l for l in warned),
              closing)
        check("...e não para a3, que declarou `nenhum`",
              not any("a3" in l for l in warned), closing)
        adds = [l.strip() for l in closing.splitlines()
                if l.strip().startswith("cepa-queue add fila ")]
        check("...com um `cepa-queue add` por item", len(adds) == 2, closing)


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
