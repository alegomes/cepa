#!/usr/bin/env python3
"""Prose contract: the three callers of the "single queue" cite the right `cepa-plan`,
with the right flag, in the right rule.

## Why this file exists

`board-flow/commands/capture.md`, `board-flow/commands/drain.md` and
`common/commands/doctor.md` are `.md` files that an orchestrator READS and follows — there is no
interpreter that fails if a sentence is rewritten in silence. Without a test
that locks ON TOP of the text, a prose editor (human or agent) can swap
"cepa-plan orders" for "reorder by the queue" and the change goes unnoticed until
someone notices that `--max` went back to cutting the queue before the reordering. Each
`check` below pins one clause of the rule R1–R4 / A1–A3 of the single queue
("Single queue: Jira, BACKLOG.md and plan.yaml converge on plan.yaml",
BACKLOG.md) to a stable ANCHOR — a command name, flag, or short phrase that only
exists if the rule is still written — never the whole sentence, which any
style rewrite would change without changing the promised behavior.

Each assertion was verified RED-then-GREEN by hand (removing the clause from the
`.md`, running the test, restoring) before entering here — see the report of the
session that introduced this file.

Run: python3 tests/test_single_track_contracts.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def read_rel(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def test_capture_add():
    f = read_rel("board-flow/commands/capture.md")
    check("chama cepa-plan add <project_key> <KEY> --title",
          "cepa-plan\" add <project_key> <KEY> --title" in f,
          "sem o comando exato, o card pode nascer e nunca entrar na fila")
    check("exit 4 (já na fila) é tratado como normal, não erro",
          "Exit 4" in f and "not an error" in f,
          "sem isso um id repetido vira BLOCKED indevido em vez de aviso")
    check("falha do add NÃO desfaz o card (não faz rollback da criação)",
          "do **not** roll back" in f,
          "sem a proibição, uma falha mecânica do cepa-plan apagaria um card "
          "real do Jira")
    check("relatório nomeia o card como fora da fila quando o add falha",
          "out of the queue" in f,
          "sem a frase, a falha do add fica muda no relatório final")


def test_drain_orders():
    f = read_rel("board-flow/commands/drain.md")
    check("chama cepa-plan order <project_key> --keys",
          "cepa-plan\" order <project_key> --keys" in f,
          "sem o comando exato, o drain volta a ordenar só pelo rank do Jira")
    check("pede a coluna inteira ao Jira quando a fila existe",
          "the whole column, no limit, if the single-track queue exists" in f,
          "sem isso o --max corta a coluna ANTES de reordenar, e os primeiros "
          "itens da fila podem nunca ser vistos")
    check("--max é aplicado DEPOIS de reordenar, não na listagem crua",
          "Apply `--max` to the reordered list now, not to the raw Jira listing" in f,
          "aplicar o teto antes de reordenar é o mesmo bug que a coluna "
          "inteira existe para evitar")
    check("sem fila, mantém a ordem de prioridade/rank do Jira",
          "keep Jira's priority/rank order" in f,
          "sem a cláusula de fallback, o drain fica sem definição quando não "
          "há plan.yaml")
    check("cards fora do plano são nomeados no relatório final",
          "Out of the queue (drained in Jira order, after the queued ones)" in f,
          "sem a linha do relatório, um card fora do plano é drenado calado")


def test_doctor_live():
    f = read_rel("common/commands/doctor.md")
    check("passa o board lido pelo atlassian-expert ao cepa-plan divergence",
          "cepa-plan\" divergence <fila>" in f and "--board <arquivo-temporário>" in f,
          "sem o --board, cards_sem_item e itens_com_card_done saem vazios "
          "(o próprio cepa-plan divergence se recusa a inferi-los sem quadro)")
    check("lista cards_sem_item e itens_com_card_done",
          "cards_sem_item" in f and "itens_com_card_done" in f,
          "sem nomear os dois campos, o passo --live não diz o que a fila "
          "compara contra o Jira")
    check("declara que o passo é leitura, nunca correção",
          "read, never fix" in f,
          "sem a frase, um agente lendo a prosa pode achar que deve corrigir "
          "a divergência sozinho")


def main():
    print("contratos da fila única (capture/drain/doctor × cepa-plan)\n")
    for fn in (test_capture_add, test_drain_orders, test_doctor_live):
        print(fn.__name__)
        fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
