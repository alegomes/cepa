#!/usr/bin/env python3
"""A descrição do plugin common no marketplace cita todo comando do common.

Sem dependência de terceiros — rode com `python3 tests/test_marketplace_descricao_common.py`.
Sai não-zero se algum comando faltar.

A dor: o guard de catálogo (test_catalogo_comandos.py) cobria só o
docs/commands.md. A descrição do common em .claude-plugin/marketplace.json
ficou parada nas skills de mentalidade enquanto o plugin ganhava /plan, /spec,
/session, /doctor e mais duas dúzias de comandos (desvios.md 2026-08-25). Quem
olhava a vitrine do marketplace não via metade do que o plugin entrega.

Vale `/<comando>` com fronteira de palavra: o caractere depois do nome não pode
ser [A-Za-z0-9_-], para `/plan` não contar por `/plan-x` nem `/worktree-list`
por `/worktree`.

Um argumento opcional aponta outro marketplace.json (usado para mostrar o
teste vermelho contra a descrição antiga).
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARKETPLACE = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / ".claude-plugin" / "marketplace.json"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def comandos(repo):
    """Todo stem de common/commands/*.md."""
    return [a.stem for a in sorted((repo / "common" / "commands").glob("*.md"))]


def faltando(stems, descricao):
    """Os comandos que a descrição não cita como `/<stem>` inteiro."""
    return [
        s for s in stems
        if not re.search(r"(?<![A-Za-z0-9_-])/" + re.escape(s) + r"(?![A-Za-z0-9_-])", descricao)
    ]


def descricao_common(caminho):
    for p in json.loads(caminho.read_text())["plugins"]:
        if p["name"] == "common":
            return p["description"]
    return None


def main():
    stems = comandos(REPO)
    descricao = descricao_common(MARKETPLACE)

    check("a varredura acha comandos", len(stems) > 20, f"achou {len(stems)}")
    check("o marketplace tem a entrada do common", descricao is not None)
    descricao = descricao or ""

    fora = faltando(stems, descricao)
    check("todo comando do common está na descrição", not fora,
          "fora da descrição: " + ", ".join("/" + s for s in fora))

    # O teste tem que conseguir ficar vermelho.
    alvo = "worktree-list"
    sem_alvo = descricao.replace("/" + alvo, "")
    check("tirar um comando da descrição faz ele faltar",
          faltando([alvo], sem_alvo) == [alvo])
    check("prefixo de outro comando não conta",
          faltando(["plan"], "cobre /plan-x e /planner") == ["plan"]
          and faltando(["worktree-list"], "cobre /worktree e /worktree-listar") == ["worktree-list"])
    check("o comando com pontuação em volta conta",
          faltando(["plan"], "(/plan, /spec).") == [])

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print(f"\ntudo ok ({len(stems)} comandos na descrição)")


if __name__ == "__main__":
    main()
