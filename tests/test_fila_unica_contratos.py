#!/usr/bin/env python3
"""Contrato em prosa: os três chamadores da "Fila única" citam o `cepa-plan`
certo, com o flag certo, na regra certa.

## Por que este arquivo existe

`board-flow/commands/capture.md`, `board-flow/commands/drain.md` e
`common/commands/doctor.md` são `.md` que um orquestrador LÊ e segue — não há
interpretador que falhe se uma frase for reescrita em silêncio. Sem um teste
que trava em CIMA do texto, um editor de prosa (humano ou agente) pode trocar
"cepa-plan ordena" por "reordene pela fila" e a mudança passa despercebida até
alguém notar que o `--max` voltou a cortar a fila antes do reordenamento. Cada
`check` abaixo prende uma cláusula da regra R1–R4 / A1–A3 da fila única
("Fila única: Jira, BACKLOG.md e plan.yaml convergem no plan.yaml",
BACKLOG.md) num ANCORA estável — nome de comando, flag, ou frase curta que só
existe se a regra ainda está escrita — nunca a sentença inteira, que qualquer
reescrita de estilo mudaria sem mudar o comportamento prometido.

Cada asserção foi verificada RED-then-GREEN à mão (removendo a cláusula do
`.md`, rodando o teste, restaurando) antes de entrar aqui — ver o relatório da
sessão que introduziu este arquivo.

Run: python3 tests/test_fila_unica_contratos.py
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


def ler(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def test_capture_add():
    f = ler("board-flow/commands/capture.md")
    check("chama cepa-plan add <project_key> <KEY> --title",
          "cepa-plan add <project_key> <KEY> --title" in f,
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


def test_drain_ordena():
    f = ler("board-flow/commands/drain.md")
    check("chama cepa-plan ordena <project_key> --keys",
          "cepa-plan ordena <project_key> --keys" in f,
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
    f = ler("common/commands/doctor.md")
    check("passa o board lido pelo atlassian-expert ao cepa-plan divergencia",
          "cepa-plan\" divergencia <fila>" in f and "--board <arquivo-temporário>" in f,
          "sem o --board, cards_sem_item e itens_com_card_done saem vazios "
          "(o próprio cepa-plan divergencia se recusa a inferi-los sem quadro)")
    check("lista cards_sem_item e itens_com_card_done",
          "cards_sem_item" in f and "itens_com_card_done" in f,
          "sem nomear os dois campos, o passo --live não diz o que a fila "
          "compara contra o Jira")
    check("declara que o passo é leitura, nunca correção",
          "leitura, nunca correção" in f,
          "sem a frase, um agente lendo a prosa pode achar que deve corrigir "
          "a divergência sozinho")


def main():
    print("contratos da fila única (capture/drain/doctor × cepa-plan)\n")
    for fn in (test_capture_add, test_drain_ordena, test_doctor_live):
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
