#!/usr/bin/env python3
"""O exemplo de `required_fields` mostra os dois formatos de valor do Jira.

fb-20260902-1: Team (customfield_10001) é campo Atlassian Teams e só aceita o
UUID puro; mandar o nome ou `{id: uuid}` dá HTTP 400 `Team id ... is not valid`.
O campo vizinho de select de opção usa `{ id: "<optionId>" }`. O exemplo antigo
mostrava o NOME do time, exatamente o formato que o Jira recusa.

Run: python3 tests/test_board_flow_example_team_format.py
"""

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
EXEMPLO = REPO / "discovery" / "board-flow.example.yaml"
DOC = REPO / "docs" / "board-flow.md"
AGENTE = REPO / "board-flow" / "agents" / "atlassian-expert.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def team_values(node):
    """Todos os `value` de entradas com name == "Team", em qualquer nível."""
    if isinstance(node, dict):
        if node.get("name") == "Team" and "value" in node:
            yield node["value"]
        for v in node.values():
            yield from team_values(v)
    elif isinstance(node, list):
        for v in node:
            yield from team_values(v)


def main():
    texto = EXEMPLO.read_text(encoding="utf-8")
    dados = yaml.safe_load(texto)
    check("exemplo continua YAML válido", isinstance(dados, dict))
    valores = list(team_values(dados))
    check("exemplo tem entradas Team em topologies", len(valores) >= 2, repr(valores))
    nomes = [v for v in valores if not (isinstance(v, str) and re.fullmatch(r"<uuid[^>]*>", v))]
    check("nenhum Team usa nome como value", not nomes, repr(nomes))
    for nome in ("Engineering", "Product", "Platform"):
        check(f"value nunca é o nome {nome}", f'value: "{nome}"' not in texto)
    check("comentário traz o 400 do Team", "Team id ... is not valid" in texto)
    check("comentário traz o formato do select", '{ id: "<optionId>" }' in texto)
    check("doc traz os dois formatos", "Team id ... is not valid" in DOC.read_text(encoding="utf-8")
          and '{ id: "<optionId>" }' in DOC.read_text(encoding="utf-8"))
    check("atlassian-expert traz a frase do Team", "Team id ... is not valid" in AGENTE.read_text(encoding="utf-8"))
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
