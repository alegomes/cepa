#!/usr/bin/env python3
"""The `required_fields` example shows the two Jira value formats.

fb-20260902-1: Team (customfield_10001) is an Atlassian Teams field and only accepts the
bare UUID; sending the name or `{id: uuid}` gives HTTP 400 `Team id ... is not valid`.
The neighbouring option-select field uses `{ id: "<optionId>" }`. The old example
showed the team NAME, exactly the format Jira refuses.

Run: python3 tests/test_board_flow_example_team_format.py
"""

import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "discovery" / "board-flow.example.yaml"
DOC = REPO / "docs" / "board-flow.md"
AGENT_NAME = REPO / "board-flow" / "agents" / "atlassian-expert.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def team_values(node):
    """All the `value`s of entries with name == "Team", at any level."""
    if isinstance(node, dict):
        if node.get("name") == "Team" and "value" in node:
            yield node["value"]
        for v in node.values():
            yield from team_values(v)
    elif isinstance(node, list):
        for v in node:
            yield from team_values(v)


def main():
    text = EXAMPLE.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    check("exemplo continua YAML válido", isinstance(data, dict))
    vals = list(team_values(data))
    check("exemplo tem entradas Team em topologies", len(vals) >= 2, repr(vals))
    names = [v for v in vals if not (isinstance(v, str) and re.fullmatch(r"<uuid[^>]*>", v))]
    check("nenhum Team usa nome como value", not names, repr(names))
    for given_name in ("Engineering", "Product", "Platform"):
        check(f"value nunca é o nome {given_name}", f'value: "{given_name}"' not in text)
    check("comentário traz o 400 do Team", "Team id ... is not valid" in text)
    check("comentário traz o formato do select", '{ id: "<optionId>" }' in text)
    check("doc traz os dois formatos", "Team id ... is not valid" in DOC.read_text(encoding="utf-8")
          and '{ id: "<optionId>" }' in DOC.read_text(encoding="utf-8"))
    check("atlassian-expert traz a frase do Team", "Team id ... is not valid" in AGENT_NAME.read_text(encoding="utf-8"))
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
