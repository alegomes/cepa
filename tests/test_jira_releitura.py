#!/usr/bin/env python3
"""Leitura de card que a sessão já tinha não volta para as specs.

Medido em 13/09/2026 nos transcripts de 30 dias: 924 releituras de card, das
quais 277 buscavam no Jira algo que a sessão já tinha em mãos. Cada chamada ao
atlassian-expert custa mediana de ~47 mil tokens. Três origens foram cortadas:

  - o agente lia o status antes de transicionar ou comentar (156 releituras),
    embora a lista de transições e o read-back já tragam o estado atual;
  - `/board-flow:prove` (dentro do prove-drain) e `/board-flow:fix` (vindo do
    execute) buscavam de novo o card que o passo anterior acabara de ler;
  - `/board-flow:capture` delegava uma segunda checagem de existência depois
    do read-back que o agente já é obrigado a fazer.

O que NÃO pode sair junto: o read-back depois de cada escrita e a leitura de
reserva (claim), que precisam do Jira atualizado.

Run: python3 tests/test_jira_releitura.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BF = REPO / "board-flow"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def ler(rel):
    return (BF / rel).read_text(encoding="utf-8")


def main():
    agente = ler("agents/atlassian-expert.md")
    check("agente não lê o card só para olhar antes de escrever",
          "No read just to look before a write" in agente)
    check("agente mantém o read-back depois de cada escrita",
          "Verify every write with a read-back" in agente)
    check("a regra antiga de ler antes de agir saiu",
          "Read, then act" not in agente)

    drain = ler("commands/prove-drain.md")
    check("claim do prove-drain lê também o que a prova precisa",
          "Implementation Summary mais recente" in drain)
    check("prove-drain entrega o conteúdo à prova sem buscar de novo",
          "skip\n     prove's step 1 fetch" in drain or "skip prove's step 1 fetch" in drain)

    prove = ler("commands/prove.md")
    check("prove reaproveita o card lido pelo claim do prove-drain",
          "Already have the card?" in prove and "prove-drain" in prove)

    fix = ler("commands/fix.md")
    check("fix reaproveita o card lido pelo execute",
          "Already have the card?" in fix and "/board-flow:execute" in fix)
    execute = ler("commands/execute.md")
    check("execute entrega o card ao fix",
          "Hand `fix` the card content" in execute and "re-fetches" not in execute)

    capture = ler("commands/capture.md")
    check("capture não delega segunda checagem de existência",
          "Confirm Jira issue" not in capture)
    check("capture ainda exige o read-back do agente",
          "Apply your read-back verification rule" in capture)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
