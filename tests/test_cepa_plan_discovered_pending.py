#!/usr/bin/env python3
"""An item that carries a pending point discovered during its execution is
not reported as ready (owner, 2026-11-10, fb-20261110-1).

The case: C1-18 of wego-faturamento-backend went `blocked` with the validation
caveats and two owner decisions buried in the prose of `evidence`. The owner
answered "sim" to the route, the item went back to `pending`, and `cepa queue
status` said "pronto: o próximo cepa-until pega". When the owner asked what was
left to unblock it, several pending points came up that no field of the item
carried.

Red test (BACKLOG.md § `cepa-queue status` diz que o item está pronto e a
pergunta sobre o desbloqueio revela pendências que nunca apareceram):

  - `cepa-queue finish ... --pendencia "<texto>"` (repeatable) records each one
    in the item's `pendencias`, open;
  - an item with an open pending point is NOT `pronto` in `status` (JSON and
    text), even after the owner's answer returns it to `pending`; it stays
    `pegavel` (a run still takes it, and resolves them);
  - `status` (text), `show` and `start` print each open point verbatim, and
    `queue --json` hands them to the run in the batch entry;
  - `finish ... --resolve-pendencia N` closes point N (1-based, among the open
    ones) with the finish evidence; with none left open the item is `pronto`
    again;
  - `--resolve-pendencia` with a number that does not exist is refused and
    writes nothing.

Run: python3 tests/test_cepa_plan_discovered_pending.py
"""
import json
import re
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import build_repo, item  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, on_tty  # noqa: E402

FAILURES = []
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t", NO_COLOR="1")
for v in ("CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"):
    ENV.pop(v, None)

P1 = "a fila de leituras trava com 20 lotes aguardando conferência"
P2 = "ler de novo o lote real custa uma chamada paga ao provedor de imagem"


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def cli(root, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN), *args, "--repo", str(root)],
                          capture_output=True, text=True, cwd=root, env=ENV,
                          timeout=60)


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, env=ENV,
                   capture_output=True)


def commit_all(root, msg="x"):
    git(root, "add", "-A")
    git(root, "commit", "-qm", msg, "--allow-empty")


def item_of(root, ident="a1"):
    plan = Path(root) / ".claude" / "programs" / "fila" / "plan.yaml"
    return {i["id"]: i for i in yaml.safe_load(plan.read_text())["items"]}[ident]


def status_json(root):
    p = cli(root, "status", "fila", "--json")
    assert p.returncode == 0, p.stderr
    data = json.loads(p.stdout)
    return data, {i["id"]: i for i in data["items"]}


def blocked_with_points(root):
    p = cli(root, "start", "fila", "a1")
    assert p.returncode == 0, p.stderr
    commit_all(root, "start")
    return cli(root, "finish", "fila", "a1", "--status", "blocked",
               "--evidence", "AC6 sem prova real; ressalvas N1 e N2 da validação",
               "--blocker", "a prova com login real exige criar um acesso novo",
               "--question", "Crio o acesso e leio um lote real? Recomendo sim",
               "--pendencia", P1, "--pendencia", f"  {P2}  ", "--pendencia", P1)


def test_point_survives_the_answer_and_item_is_not_ready():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        p = blocked_with_points(root)
        check("finish --pendencia sai 0", p.returncode == 0, p.stderr + p.stdout)
        it = item_of(root)
        points = it.get("pendencias") or []
        check("grava as duas pendências, texto achatado, repetida uma vez só",
              [x.get("texto") for x in points] == [P1, P2], str(points))
        check("cada pendência nasce aberta",
              all(x.get("resolvida_em") is None for x in points), str(points))
        check("a saída do finish lista as pendências",
              P1 in p.stdout and P2 in p.stdout, p.stdout)
        commit_all(root, "finish")

        rc, out = on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila", "a1",
                          "--answer", "sim: crie o acesso", "--repo", str(root),
                          "--no-commit"], str(root), env=ENV)
        check("answer sim sai 0", rc == 0, out)
        commit_all(root, "answer")
        it = item_of(root)
        check("a resposta devolve a pending e mantém as pendências",
              it["status"] == "pending" and len(it.get("pendencias") or []) == 2,
              str(it))

        data, by_id = status_json(root)
        a1 = by_id["a1"]
        check("status --json: a1 não é pronto", a1["pronto"] is False, str(a1))
        check("status --json: a1 continua pegável", a1["pegavel"] is True, str(a1))
        check("status --json: a1 carrega as pendências abertas",
              a1.get("pendencias") == [P1, P2], str(a1.get("pendencias")))
        check("status --json: a contagem de prontos não conta a1",
              data["prontos"] == 1, str(data["prontos"]))
        check("status --json: a2, sem pendência, segue pronto",
              by_id["a2"]["pronto"] is True and by_id["a2"].get("pendencias") == [],
              str(by_id["a2"]))

        text = cli(root, "status", "fila").stdout
        a1_block = text.split("a1 —", 1)[1].split("a2 —", 1)[0] if "a1 —" in text else ""
        check("status texto: a1 não diz 'pronto: o próximo cepa-until pega'",
              "pronto: o próximo" not in a1_block, a1_block)
        check("status texto: a1 mostra cada pendência",
              P1 in a1_block and P2 in a1_block, a1_block)
        check("status texto: o resumo diz que a1 tem pendência descoberta",
              "pendência descoberta" in text.split("\n\n", 1)[0]
              and "a1" in text.split("\n\n", 1)[0], text.split("\n\n", 1)[0])

        check("status texto: a linha pegável diz o motivo real",
              "mesmo com pendência aberta" in a1_block, a1_block)

        screen = subprocess.run(
            [sys.executable, str(CEPA_PLAN), "status", "fila", "--repo", str(root)],
            capture_output=True, text=True, cwd=root, timeout=60,
            env={k: v for k, v in dict(ENV, CEPA_COR="sempre", COLUMNS="200").items()
                 if k != "NO_COLOR"})
        flat = re.sub(r"\x1b\[[0-9;]*m", "", screen.stdout)
        a1_screen = flat.split("a1", 1)[-1].split("a2", 1)[0]
        check("tela do terminal: a1 lista cada pendência descoberta",
              "pendência descoberta 1" in a1_screen and P1 in a1_screen
              and "pendência descoberta 2" in a1_screen, flat)
        check("tela do terminal: a1 não diz pronto, diz pegável com pendência",
              "pronto: o próximo" not in a1_screen
              and "mesmo com pendência aberta" in a1_screen, a1_screen)

        shown = cli(root, "show", "fila", "a1").stdout
        check("show lista as pendências abertas", "pendências descobertas" in shown
              and P1 in shown and P2 in shown, shown)
        check("show: o status diz pegável com pendência aberta",
              "mesmo com pendência aberta" in shown, shown)

        q = cli(root, "queue", "fila", "--max", "5", "--json")
        batch = {b["id"]: b for b in json.loads(q.stdout)["batch"]}
        check("queue --json: a1 segue no lote, com as pendências",
              batch.get("a1", {}).get("pendencias") == [P1, P2], q.stdout)

        s = cli(root, "start", "fila", "a1")
        check("start imprime as pendências para quem reservou",
              s.returncode == 0 and "pendências descobertas" in s.stdout
              and P1 in s.stdout and P2 in s.stdout, s.stdout + s.stderr)


def test_resolve_closes_a_point_and_bad_number_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        p = cli(root, "start", "fila", "a1")
        assert p.returncode == 0, p.stderr
        commit_all(root, "start")
        p = cli(root, "finish", "fila", "a1", "--status", "pending",
                "--evidence", "achei duas pendências", "--pendencia", P1,
                "--pendencia", P2)
        check("finish pending com pendências sai 0", p.returncode == 0, p.stderr)
        commit_all(root, "finish")
        check("pending com pendência aberta não é pronto",
              status_json(root)[1]["a1"]["pronto"] is False)

        p = cli(root, "start", "fila", "a1")
        commit_all(root, "start2")
        before = item_of(root)
        bad = cli(root, "finish", "fila", "a1", "--status", "pending",
                  "--evidence", "resolvi", "--resolve-pendencia", "3")
        check("--resolve-pendencia 3 com duas abertas é recusado",
              bad.returncode == 2 and "3" in bad.stderr, bad.stderr + bad.stdout)
        check("a recusa não escreve nada", item_of(root) == before, str(item_of(root)))

        ok = cli(root, "finish", "fila", "a1", "--status", "pending",
                 "--evidence", "fila de leituras destravada no commit abc",
                 "--resolve-pendencia", "1")
        check("--resolve-pendencia 1 sai 0", ok.returncode == 0, ok.stderr)
        commit_all(root, "resolve1")
        points = item_of(root)["pendencias"]
        check("a pendência 1 fecha com a evidência do finish",
              points[0].get("resolvida_em") and "commit abc" in points[0].get("como", "")
              and points[1].get("resolvida_em") is None, str(points))
        a1 = status_json(root)[1]["a1"]
        check("com uma aberta, segue não pronto e lista só a aberta",
              a1["pronto"] is False and a1["pendencias"] == [P2], str(a1))

        cli(root, "start", "fila", "a1")
        commit_all(root, "start3")
        ok = cli(root, "finish", "fila", "a1", "--status", "pending",
                 "--evidence", "custo aceito pelo dono", "--resolve-pendencia", "1")
        check("a numeração conta só as abertas: 1 agora é a segunda",
              ok.returncode == 0, ok.stderr)
        commit_all(root, "resolve2")
        a1 = status_json(root)[1]["a1"]
        check("sem pendência aberta, o item volta a ser pronto",
              a1["pronto"] is True and a1["pendencias"] == [], str(a1))


def main():
    for t in (test_point_survives_the_answer_and_item_is_not_ready,
              test_resolve_closes_a_point_and_bad_number_is_refused):
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\nok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
