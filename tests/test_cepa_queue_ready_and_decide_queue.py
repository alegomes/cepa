#!/usr/bin/env python3
"""Pending is not ready, and the owner answers the whole queue from cepa-until.

Origin (owner, 2026-11-02, WEGO queue with 11 pending, 5 blocked and "43 com
ação humana aberta"):
  - "Pendente ≠ Pronto pra ser feito. O cepa-until não deve perder tempo em
    itens que certamente não irão avançar" -> `cepa-plan status` tells, per
    item and in the summary, which `pending` the next run takes;
  - "eu odeio ter que usar qualquer outro comando cepa que não seja o
    cepa-until" -> `cepa-until decide <fila>` asks about everything the queue
    holds for the owner, including the leftover tasks of delivered items;
  - "descarto este pedido? sim" sent WEGO-2463 back to `pending` -> `[d]` and
    `cepa-plan answer --drop` take the item out of the queue.

Run with `python3 tests/test_cepa_queue_ready_and_decide_queue.py`.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import CEPA_UNTIL, item, build_repo  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    CEPA_PLAN, on_tty, items_of, load_module)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def queue_fixture(tmp):
    waiting = item("p2")
    waiting["blocked_by"] = ["b1"]
    return build_repo(tmp, [
        item("p1"),
        item("h1", human_pending="valide o login real"),
        item("b1", status="blocked"),
        waiting,
        item("d1", status="done", human_pending="crie o papel no Keycloak"),
        item("d2", status="done"),
    ])


def test_status_tells_ready_from_pending():
    with tempfile.TemporaryDirectory() as tmp:
        root = queue_fixture(tmp)
        p = subprocess.run([sys.executable, str(CEPA_PLAN), "status", "fila",
                            "--repo", str(root), "--json"],
                           capture_output=True, text=True)
        data = json.loads(p.stdout)
        ready = {i["id"]: i["pronto"] for i in data["items"]}
        check("só o pendente sem rota e sem espera fica pronto",
              ready == {"p1": True, "h1": False, "b1": False, "p2": False,
                        "d1": False, "d2": False}, ready)
        check("o resumo conta os prontos", data["prontos"] == 1, data)
        p = subprocess.run([sys.executable, str(CEPA_PLAN), "status", "fila",
                            "--repo", str(root)], capture_output=True, text=True)
        out = p.stdout
        check("o texto diz quantos pendentes estão prontos",
              "1 de 3 pendentes prontos para o agente: p1" in out, out)
        check("separa itens parados de tarefas em itens concluídos",
              "2 itens parados (h1, b1)" in out
              and "1 tarefas que sobraram em itens concluídos" in out, out)
        check("e aponta o comando que responde tudo",
              "cepa-until decide fila" in out, out)


def test_answer_drop():
    with tempfile.TemporaryDirectory() as tmp:
        root = queue_fixture(tmp)

        def answer(ident, *extra):
            return on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila",
                           ident, "--answer", "não vale mais", "--repo",
                           str(root), *extra], str(root))

        rc, out = answer("p1", "--drop")
        check("--drop descarta um pendente sem rota",
              rc == 0 and items_of(root)["p1"]["status"] == "dropped", out)
        rc, out = answer("h1", "--drop")
        h1 = items_of(root)["h1"]
        check("--drop num item com rota descarta e fecha a rota",
              rc == 0 and h1["status"] == "dropped"
              and h1["human_pending"] is None, h1)
        rc, out = answer("d1", "--drop")
        d1 = items_of(root)["d1"]
        check("--drop num done só fecha a tarefa que sobrou",
              rc == 0 and d1["status"] == "done" and d1["human_pending"] is None
              and "segue `done`" in d1["evidence"], d1)
        rc, out = answer("b1", "--drop", "--keep")
        check("--drop com --keep é recusado",
              rc != 0 and items_of(root)["b1"]["status"] == "blocked", out)
        rc, out = answer("d2", "--drop")
        check("done sem rota continua sem o que responder",
              rc != 0 and items_of(root)["d2"]["status"] == "done", out)


def test_decide_d_drops():
    m = load_module()
    deferred = [{"id": "W-1", "title": "juntar cards", "reason": "bloqueado-antes",
                 "question": "Descarto este pedido?", "human_pending": None,
                 "evidence": "perdeu o objeto"},
                {"id": "W-2", "title": "papel", "reason": "pos-entrega",
                 "question": None, "human_pending": "crie o papel",
                 "evidence": None}]
    answers = iter(["d", "já feito por outro card", "d", ""])
    calls, screen = [], []
    applied, _ = m.decide(
        Path("/nao/existe"), "fila", None, {}, deferred, {},
        question=lambda p: (screen.append(str(p)), next(answers))[1],
        output=screen.append,
        answer=lambda i, t, keep=False, drop=False: (
            calls.append((i, t, keep, drop)), (0, f"{i} ok"))[1])
    text = "\n".join(screen)
    check("[d] vai para o answer com drop",
          calls[0][0] == "W-1" and calls[0][3] is True
          and calls[0][1].startswith("descartado: Descarto este pedido?")
          and "já feito por outro card" in calls[0][1], calls)
    check("num item entregue, [d] encerra a tarefa",
          calls[1][0] == "W-2" and calls[1][3] is True
          and calls[1][1].startswith("tarefa encerrada"), calls)
    check("o menu nomeia as duas variantes",
          "descarta o item" in text and "a tarefa não vale mais" in text, text)
    check("no item entregue, sim não promete devolver à fila",
          "o item segue concluído" in text and "d = ela não vale mais" in text,
          text)
    check("o fecho do modo fila não cita run",
          "fila/" not in text, text)


def test_decide_queue_mode_as_process():
    with tempfile.TemporaryDirectory() as tmp:
        root = queue_fixture(tmp)
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila",
               "--repo", str(root)]
        p = subprocess.run(cmd, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        out = p.stdout
        check("sem terminal, lista a rota, o travado e a tarefa do concluído",
              p.returncode == 0 and "valide o login real" in out
              and "b1" in out and "crie o papel no Keycloak" in out,
              out + p.stderr)
        check("...e não pergunta sobre o pendente pronto nem o done limpo",
              "- p1" not in out and "- d2" not in out, out)
        rc, out = on_tty(cmd, str(root), inputs=[
            ("[t] escrevo a resposta", "s"), ("Quer acrescentar algo", ""),
            ("[t] escrevo a resposta", "n"), ("Quer acrescentar algo", ""),
            ("[t] escrevo a resposta", "s"), ("Quer acrescentar algo", "feito")])
        its = items_of(root)
        check("no terminal, sim fecha a tarefa do concluído",
              its["d1"]["human_pending"] is None and its["d1"]["status"] == "done"
              and "feito" in its["d1"]["evidence"], out[-1500:])


def main():
    print("fila: pronto ≠ pendente; decide <fila>\n")
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
