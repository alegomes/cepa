#!/usr/bin/env python3
"""Prose contract of /common:next — the READER half of the reconciliation.

Run with `python3 tests/test_common_next.py` (needs nothing installed).

Why it exists: the "the plan says / the board says" comparison lived only in the prose
of this command. On 2026-08-28 it became `cepa-plan reconcile`, code with a test,
precisely so the batch executor (/common:drain-plan) uses the SAME rule instead
of a second copy that drifts. Only that the `drain-plan.md` side gained a contract
test and this one did not: if someone rewrites this file to go back to
eyeballing the comparison, the two commands diverge again and nothing goes red.
The completeness auditor blocked commit b71a404 for exactly this gap.

What these tests do NOT prove: that the reconciliation is right. That is
tests/test_common_drain_plan.py, which exercises the real `cepa-plan reconcile`.
Here the question is only whether the command CALLS the comparator.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CMD = REPO / "common" / "commands" / "next.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def test_calls_the_comparator_instead_of_eyeballing():
    f = CMD.read_text(encoding="utf-8")
    clean = f.replace("`", "").lower()
    check("o comando existe", CMD.is_file(), str(CMD))
    check("a leitura do quadro é delegada a quem tem as ferramentas",
          "atlassian-expert" in f,
          "este comando não pode chamar ferramenta do Atlassian direto")
    check("e a comparação passa pelo `cepa-plan reconcile`",
          "cepa-plan reconcile" in f,
          "sem isso a tabela plano × quadro volta a ser interpretada a cada "
          "run, e o /common:drain-plan passa a usar uma regra diferente da "
          "deste comando")
    check("o passo Sync grava pelo mesmo comparador, com --apply",
          "cepa-plan reconcile" in f and "--apply" in f,
          "gravar por fora do cepa-plan contorna todas as recusas dele")
    check("e proíbe editar o YAML à mão",
          "editing the yaml by hand" in clean or "à mão" in clean)


def test_the_limits_reconciliation_cannot_cross():
    f = CMD.read_text(encoding="utf-8")
    clean = f.replace("`", "").lower()
    check("diz que o comparador NUNCA fecha uma rota humana",
          "never touches `human_pending`" in f
          or "reconcile never touches" in clean,
          "uma lista que se fecha sozinha é decoração, e a dívida volta a sumir")
    check("e que só o usuário fecha uma",
          "only the user clears it" in clean)
    check("card do quadro ausente do plano NÃO é anexado",
          "are **not** appended" in f or "not appended" in clean,
          "posição sem `why` é a decisão que a fila existe para guardar")
    check("e diz quem os coloca",
          "--from-jira" in f)
    check("sem --sync o comando é read-only",
          "read-only" in clean and "--sync" in f,
          "um leitor que grava calado é como o plano começa a mentir")
    check("sem tracker, o status é declaradamente auto-declarado",
          "self-reported" in clean or "auto-declarado" in clean)


def test_done_item_does_not_drop_category():
    f = CMD.read_text(encoding="utf-8")
    clean = f.replace("`", "").lower()
    check("a tabela diz que item done continua done contra o quadro (R3)",
          "stays done" in clean and "r3" in clean,
          "o rebaixamento antigo reabriu 11 cards prontos no wego-acesso-backend")
    check("e que reabrir é decisão do usuário, pelo /common:queue",
          "reopening it is the user's call" in clean
          and "through /common:queue" in clean,
          "se o comando voltar a reabrir sozinho, a regra R3 some do leitor")


def main():
    for fn in (test_calls_the_comparator_instead_of_eyeballing,
               test_the_limits_reconciliation_cannot_cross,
               test_done_item_does_not_drop_category):
        print(f"\n{fn.__name__}")
        fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
