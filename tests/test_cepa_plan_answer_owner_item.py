#!/usr/bin/env python3
"""CS-3 of docs/spec/resposta-do-decide-vira-trabalho.md: the item a "sim" creates,
when declared "precisa do dono", is born with an open human route and shows up as
an owner action.

Against the real CLI, in a real git repo, in a PTY (`answer` only runs on a TTY):
  - red test: declaration with `precisa_do_dono: true`; after `answer --answer
    "sim: ..."` the new item has `human_pending` filled and `cepa-queue queue
    --json` lists it among the deferred with reason `human_pending`;
  - the route is the one the spec decided without asking: `route_kind:
    owner-task`, the declared title as the pending text, a closed question, and
    "nenhum" for both of its own answers (no chain of declarations);
  - the owner's later "sim" to that route closes it and the item enters the
    batch; the output says the item waits for the owner;
  - without the mark, the new item is still born with no route (CS-2 unchanged).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import item, build_repo  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, items_of  # noqa: E402
from test_cepa_plan_answer_creates_item import (  # noqa: E402
    ENV, routed, answer, ordered)

FAILURES = []
TITLE = "pedir ao fornecedor a chave nova de acesso"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def queue_json(root):
    q = subprocess.run([sys.executable, str(CEPA_PLAN), "batch", "fila",
                        "--max", "5", "--repo", str(root), "--json"],
                       capture_output=True, text=True, env=ENV)
    return q.returncode, json.loads(q.stdout or "{}"), q.stderr


def test_red_test_needs_owner_item_is_born_with_an_open_route():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item={"titulo": TITLE,
                                                        "precisa_do_dono": True})])
        rc, out = answer(root, "a1", "sim: eu peço")
        check("answer sai 0", rc == 0, out)
        items = ordered(root)
        check("a fila ganha um item", len(items) == 2, [i["id"] for i in items])
        new = items[-1]
        check("o item novo tem o título declarado", new.get("title") == TITLE, new)
        check("o item novo nasce `pending`", new.get("status") == "pending", new)
        check("o item novo tem `human_pending` preenchido",
              str(new.get("human_pending") or "").strip() != "", new)
        check("a pendência humana é o título declarado",
              new.get("human_pending") == TITLE, new)
        check("a rota é tarefa do dono (`owner-task`)",
              new.get("route_kind") == "owner-task", new)
        q = str(new.get("owner_question") or "")
        check("a rota tem pergunta fechada", "?" in q and TITLE in q, new)
        summary = new.get("owner_summary") or {}
        check("a rota diz o que o sim e o não fazem",
              bool(summary.get("se_sim")) and bool(summary.get("se_nao")), summary)
        check("as respostas da rota nova declaram `nenhum`",
              summary.get("item_se_sim") == "nenhum"
              and summary.get("item_se_nao") == "nenhum", summary)
        check("a saída diz que o item novo espera o dono",
              str(new["id"]) in out and "esperando você" in out, out)
        origin_ev = str(items_of(root)["a1"].get("evidence") or "")
        check("a evidência do item de origem diz que o item novo espera o dono",
              f"{new['id']} no fim da fila: {TITLE}, esperando o dono." in origin_ev,
              origin_ev)
        rc, data, err = queue_json(root)
        check("a fila continua válida (`queue` sai 0)", rc == 0, err)
        deferred = {d.get("id"): d for d in data.get("deferred", [])}
        check("`queue` lista o item novo entre os adiados",
              str(new["id"]) in deferred, data.get("deferred"))
        check("o motivo do adiamento é `human_pending`",
              deferred.get(str(new["id"]), {}).get("reason") == "human_pending",
              deferred.get(str(new["id"])))
        check("o item novo não entra no lote",
              str(new["id"]) not in [b["id"] for b in data.get("batch", [])],
              data.get("batch"))

        # The owner later says the task is done: the route closes, the item runs.
        rc, out = answer(root, str(new["id"]), "sim: já pedi e recebi")
        check("o sim do dono à rota nova sai 0", rc == 0, out)
        after = items_of(root)[str(new["id"])]
        check("a rota nova fecha e o item segue `pending`",
              after["human_pending"] is None and after["status"] == "pending", after)
        check("o sim à rota nova não cria outro item",
              len(ordered(root)) == 2, [i["id"] for i in ordered(root)])
        rc, data, _ = queue_json(root)
        check("depois do sim, o item entra no lote",
              str(new["id"]) in [b["id"] for b in data.get("batch", [])], data)


def test_without_the_mark_no_route():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", yes_item={"titulo": TITLE,
                                                        "precisa_do_dono": False})])
        rc, out = answer(root, "a1", "sim: pode")
        new = ordered(root)[-1]
        check("sem a marca, o item novo nasce sem rota",
              rc == 0 and new.get("human_pending") is None
              and "route_kind" not in new and "owner_summary" not in new, new)
        check("sem a marca, a saída não diz que espera o dono",
              "esperando você" not in out, out)
        origin_ev = str(items_of(root)["a1"].get("evidence") or "")
        check("sem a marca, a evidência de origem não diz que espera o dono",
              f"no fim da fila: {TITLE}." in origin_ev
              and "esperando o dono" not in origin_ev, origin_ev)


def main():
    test_red_test_needs_owner_item_is_born_with_an_open_route()
    test_without_the_mark_no_route()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\ntudo ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
