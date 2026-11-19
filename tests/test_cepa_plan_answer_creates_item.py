#!/usr/bin/env python3
"""CS-2 of docs/spec/resposta-do-decide-vira-trabalho.md: the owner's "sim" to a
route that declares an item creates that item at the end of the same queue.

Origin (2026-11-18, kairos-etapa-1 queue of wego-digitacao-backend): the owner
answered "sim" to "Ponho na fila um item para ...?" and the answer only closed the
human route; the promised item was never born and the next run found nothing.

Against the real CLI, in a real git repo, in a PTY (`answer` only runs on a TTY):
  - red test: `done` item whose route declares "calibrar X" for the "sim":
    `answer --answer "sim: ..."` leaves the queue with one more item, at the end,
    `pending`, title "calibrar X", evidence citing the origin id, the date, the
    question and the answer; the output prints the new id;
  - the new id never collides with an existing one;
  - `nenhum`, `--keep`, `--drop`, a "não" and the "sim" of a `blocked` item
    (which returns the item itself to the queue) create nothing;
  - the queue still validates afterwards (`cepa-plan queue` exits 0 and returns
    the new item).
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime

import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import item, build_repo  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, on_tty, items_of  # noqa: E402

FAILURES = []

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
for v in ("CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"):
    ENV.pop(v, None)

QUESTION = "Ponho na fila um item para calibrar X?"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def routed(ident, status="done", yes_item=None, no_item="nenhum"):
    it = item(ident, status=status, human_pending="decidir se calibra X")
    it["route_kind"] = "open-question"
    it["owner_question"] = QUESTION
    summary = {"se_sim": "um item novo calibra X", "se_nao": "X fica como está"}
    if yes_item is not None:
        summary["item_se_sim"] = yes_item
    if no_item is not None:
        summary["item_se_nao"] = no_item
    it["owner_summary"] = summary
    return it


def answer(root, ident, text, *extra):
    return on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila", ident,
                   "--answer", text, "--repo", str(root), "--no-commit"]
                  + list(extra), str(root), env=ENV)


def ordered(root):
    plan = yaml.safe_load(
        (root / ".claude" / "programs" / "fila" / "plan.yaml").read_text())
    return plan["items"]


def test_red_test_yes_creates_the_declared_item_at_the_end():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item={"titulo": "calibrar X",
                                                        "precisa_do_dono": False}),
                                item("a2")])
        rc, out = answer(root, "a1", "sim: pode calibrar")
        check("answer sai 0", rc == 0, out)
        items = ordered(root)
        check("a fila ganha um item", len(items) == 3, [i["id"] for i in items])
        new = items[-1]
        check("o item novo está no fim e com o título declarado",
              new.get("title") == "calibrar X", new)
        check("o item novo nasce `pending`", new.get("status") == "pending", new)
        check("o item novo nasce sem rota humana", new.get("human_pending") is None, new)
        ev = str(new.get("evidence") or "")
        today = datetime.now().strftime("%Y-%m-%d")
        check("a evidência cita o item de origem", "a1" in ev, ev)
        check("a evidência cita a data", today in ev, ev)
        check("a evidência cita a pergunta", QUESTION in ev, ev)
        check("a evidência cita a resposta", "sim: pode calibrar" in ev, ev)
        check("a saída imprime o id do item novo", str(new["id"]) in out, out)
        check("o `why` do item novo diz que ele ainda não foi priorizado",
              "ainda não priorizado" in str(new.get("why")), new)
        check("o item novo leva a marca de item sem Epic", new.get("sem_epic") is True, new)
        check("o id novo não repete nenhum id da fila",
              len({str(i["id"]) for i in items}) == 3, [i["id"] for i in items])
        origin = items_of(root)["a1"]
        check("o item de origem segue `done` com a rota fechada",
              origin["status"] == "done" and origin["human_pending"] is None, origin)
        check("a evidência do item de origem nomeia o item criado",
              str(new["id"]) in str(origin.get("evidence") or ""), origin)
        q = subprocess.run([sys.executable, str(CEPA_PLAN), "queue", "fila",
                            "--max", "5", "--repo", str(root), "--json"],
                           capture_output=True, text=True, env=ENV)
        check("a fila continua válida (`queue` sai 0)", q.returncode == 0, q.stderr)
        batch = [b["id"] for b in json.loads(q.stdout or "{}").get("batch", [])]
        check("`queue` devolve o item novo no lote", str(new["id"]) in batch, batch)


def test_new_id_skips_an_existing_one():
    with tempfile.TemporaryDirectory() as tmp:
        taken = item("a1-sim")
        root = build_repo(tmp, [routed("a1", yes_item={"titulo": "calibrar X",
                                                        "precisa_do_dono": False}),
                                taken])
        rc, out = answer(root, "a1", "sim: pode calibrar")
        items = ordered(root)
        check("com o id óbvio ocupado, ainda cria", len(items) == 3 and rc == 0, out)
        check("o item que já existia não muda", items[1] == {**taken, **items[1]}
              and items[1]["title"] == "item a1-sim", items[1])
        check("o id novo é outro", items[-1]["id"] != "a1-sim", items[-1])


def creates_nothing(name, it, text, *extra):
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [it, item("a2")])
        rc, out = answer(root, "a1", text, *extra)
        check(f"{name}: answer sai 0", rc == 0, out)
        check(f"{name}: a fila fica com os mesmos itens",
              [i["id"] for i in ordered(root)] == ["a1", "a2"],
              [i["id"] for i in ordered(root)])


def test_answers_that_create_nothing():
    declared = {"titulo": "calibrar X", "precisa_do_dono": False}
    creates_nothing("`nenhum` no sim", routed("a1", yes_item="nenhum"),
                    "sim: pode seguir")
    creates_nothing("--keep", routed("a1", yes_item=declared), "sim: depois", "--keep")
    creates_nothing("--drop", routed("a1", yes_item=declared), "encerrada: não vale", "--drop")
    creates_nothing("--drop com resposta que começa por sim",
                    routed("a1", yes_item=declared), "sim, mas encerra", "--drop")
    creates_nothing("não em rota com sim declarado", routed("a1", yes_item=declared),
                    "não: deixa assim")
    creates_nothing("sim em item `blocked` (o próprio item volta à fila)",
                    routed("a1", status="blocked", yes_item=declared),
                    "sim: destrava")


def main():
    test_red_test_yes_creates_the_declared_item_at_the_end()
    test_new_id_skips_an_existing_one()
    test_answers_that_create_nothing()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\ntudo ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
