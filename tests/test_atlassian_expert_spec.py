#!/usr/bin/env python3
"""A spec do atlassian-expert cabe no orçamento e não perde nenhuma regra.

Medido em 13/09/2026 com o cepa-tokens: nas 684 execuções do agente nos 30
dias anteriores, o primeiro pedido ao modelo (prompt de sistema + spec +
ferramentas, antes de qualquer trabalho) teve mediana de 34.469 tokens, 73% do
gasto mediano de uma execução. A spec tinha 34.561 bytes, a maior do repo. Ela
foi condensada; este teste impede que volte a crescer sem ninguém ver e que o
corte leve junto uma recusa ou uma regra.

Run: python3 tests/test_atlassian_expert_spec.py
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "board-flow" / "agents" / "atlassian-expert.md"
# Metade dos 34.561 bytes de antes do corte (34.561 ÷ 2 = 17.280), arquivo
# inteiro. Só a linha `tools:` ocupa ~3,3 KB e não pode encolher: os três
# servidores estão em uso.
ORCAMENTO_BYTES = 17280

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


# Cada regra, pelo trecho que a identifica. Sumir um destes é perder a regra.
REGRAS = {
    "preflight de conexão": "failed preflight",
    "drift do board-flow.yaml": "board-flow.yaml drift",
    "override por topologia substitui listas inteiras": "replaced whole",
    "escopo com precedência": "first match wins",
    "escopo rejeitado pelo Jira": "scope JQL fragment rejected",
    "guard op nunca bloqueia": "Never block on a guard op",
    "nunca inferir identificador": "Never infer or construct any Jira identifier",
    "site ausente não vira pedido de auth": "never an auth request",
    "transição só por transitionJiraIssue": "Never set status through `editJiraIssue`",
    "read-back de create": "confirms it does not exist",
    "read-back de transição": "not <target>",
    "read-back de comentário não julga formatação": "never to judge its formatting",
    "summary obrigatório em review": "requires Implementation Summary",
    "quatro campos nulos explícitos": "missing explicit-null field",
    "motivo estruturado em bounce": "bounce-back requires a structured Reason",
    "motivo por card em lote": "one reason pasted across N cards",
    "attention não é estado": '"Attention" is not a state',
    "tipo de link validado no site": "not found on this site",
    "comentário nunca é reescrito por defeito não visto": "Never rewrite or repost the comment",
    "cascata só propõe": "Never transition a sibling in the same run",
    "proposta de cascata só com irmão aberto": "only if at least one sibling is still open",
    "claim reporta ausência": "claim: none",
    "vocabulário da UI": "work item",
    "palavra na URL não prova o texto da UI": "inside a URL is not evidence",
    "erro de tela que mente": "field configuration",
    "terceiro servidor antes de BLOCKED": "before declaring BLOCKED",
    # 13/09/2026: 158 chamadas falharam com cloudId inventado; o nome literal
    # do site nunca falhou (2.648 chamadas).
    "cloudId é o defaults.site literal": "copied literally (a hostname works as cloudId)",
    "erro de cloudId não troca de servidor": "never by switching servers",
}


def main():
    texto = SPEC.read_text(encoding="utf-8")
    tamanho = len(texto.encode("utf-8"))
    check(f"spec cabe em {ORCAMENTO_BYTES} bytes ({tamanho})", tamanho <= ORCAMENTO_BYTES)
    for nome, trecho in REGRAS.items():
        check(f"regra presente: {nome}", trecho in texto, repr(trecho))
    ferramentas = re.search(r"^tools:(.*)$", texto, re.M).group(1)
    for prefixo in ("mcp__claude_ai_Atlassian__", "mcp__Atlassian__", "mcp__mcp-atlassian__"):
        check(f"os três servidores seguem ligados: {prefixo}", prefixo in ferramentas)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
