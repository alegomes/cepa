#!/usr/bin/env python3
"""Contrato de prosa do /common:next — a metade LEITORA da reconciliação.

Rode com `python3 tests/test_common_next.py` (não precisa de nada instalado).

Por que existe: a comparação "o plano diz / o quadro diz" morava só na prosa
deste comando. Em 2026-08-28 ela virou `cepa-plan reconcile`, código com teste,
justamente para o executor em lote (/common:drain-plan) usar a MESMA regra em
vez de uma segunda cópia que deriva. Só que o lado `drain-plan.md` ganhou teste
de contrato e este não: se alguém reescrever este arquivo para voltar a
comparar de olho, os dois comandos divergem outra vez e nada fica vermelho.
O auditor de completude barrou o commit b71a404 por exatamente esta lacuna.

O que estes testes NÃO provam: que a reconciliação está certa. Isso é
tests/test_common_drain_plan.py, que exercita o `cepa-plan reconcile` de
verdade. Aqui a pergunta é só se o comando CHAMA o comparador.
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


def test_chama_o_comparador_em_vez_de_comparar_de_olho():
    f = CMD.read_text(encoding="utf-8")
    limpo = f.replace("`", "").lower()
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
          "editing the yaml by hand" in limpo or "à mão" in limpo)


def test_os_limites_que_a_reconciliacao_nao_pode_cruzar():
    f = CMD.read_text(encoding="utf-8")
    limpo = f.replace("`", "").lower()
    check("diz que o comparador NUNCA fecha uma rota humana",
          "never touches `human_pending`" in f
          or "reconcile never touches" in limpo,
          "uma lista que se fecha sozinha é decoração, e a dívida volta a sumir")
    check("e que só o usuário fecha uma",
          "only the user clears it" in limpo)
    check("card do quadro ausente do plano NÃO é anexado",
          "are **not** appended" in f or "not appended" in limpo,
          "posição sem `why` é a decisão que a fila existe para guardar")
    check("e diz quem os coloca",
          "--from-jira" in f)
    check("sem --sync o comando é read-only",
          "read-only" in limpo and "--sync" in f,
          "um leitor que grava calado é como o plano começa a mentir")
    check("sem tracker, o status é declaradamente auto-declarado",
          "self-reported" in limpo or "auto-declarado" in limpo)


def main():
    for fn in (test_chama_o_comparador_em_vez_de_comparar_de_olho,
               test_os_limites_que_a_reconciliacao_nao_pode_cruzar):
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
