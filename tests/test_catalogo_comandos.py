#!/usr/bin/env python3
"""Todo comando que existe está em docs/commands.md.

Sem dependência de terceiros — rode com `python3 tests/test_catalogo_comandos.py`.
Sai não-zero na primeira varredura com falha.

A dor: oito comandos (spec, session, doctor, metrics, advisors, consolidate,
prove-ui, decide) sumiram do catálogo sem que nenhum teste piscasse, porque nada
relacionava os arquivos `*/commands/*.md` com as tabelas do doc. Corrigir a
lista à mão conserta o sintoma de hoje; este teste impede o de amanhã. Na
conferência de 2026-09-25 já eram outros três fora (os dois flows do
build-solo e o /common:until-review) — o sintoma volta sozinho.

O nome publicado vem do `name` do `.claude-plugin/plugin.json`, não do nome da
pasta: a pasta `docs-topology/` publica `/docs:*`.

Comando interno de propósito entra em INTERNOS com o motivo escrito — a exceção
fica no teste, nunca como omissão calada no doc.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CATALOGO = REPO / "docs" / "commands.md"

# "/plugin:comando" → por que não está no catálogo. Vazio hoje.
INTERNOS = {}

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def comandos(repo):
    """Todo `/plugin:comando` que o repo publica."""
    achados = []
    for arq in sorted(repo.glob("*/commands/*.md")):
        manifesto = arq.parent.parent / ".claude-plugin" / "plugin.json"
        if not manifesto.exists():
            continue
        plugin = json.loads(manifesto.read_text())["name"]
        achados.append(f"/{plugin}:{arq.stem}")
    return achados


def faltando(cmds, texto):
    """Os comandos que não aparecem citados no texto do catálogo."""
    return [
        c for c in cmds
        if c not in INTERNOS and not re.search(re.escape(c) + r"(?![\w-])", texto)
    ]


def main():
    cmds = comandos(REPO)
    texto = CATALOGO.read_text()

    check("a varredura acha comandos", len(cmds) > 20, f"achou {len(cmds)}")
    check("a pasta docs-topology publica /docs:*",
          any(c.startswith("/docs:") for c in cmds),
          "nome do plugin não veio do plugin.json")

    fora = faltando(cmds, texto)
    check("todo comando está em docs/commands.md", not fora,
          "fora do catálogo: " + ", ".join(fora))

    fantasmas = [c for c in INTERNOS if c not in cmds]
    check("toda exceção em INTERNOS ainda existe", not fantasmas,
          "exceção para comando que sumiu: " + ", ".join(fantasmas))

    # O teste tem que conseguir ficar vermelho: tirar uma linha acusa ela,
    # e um prefixo não vale pelo comando inteiro (/common:worktree-list não
    # cobre /common:worktree-lis, nem /common:plan cobre /common:plan-x).
    alvo = "/common:until-review"
    sem_linha = "\n".join(l for l in texto.splitlines() if alvo not in l)
    check("tirar a linha de um comando faz ele faltar",
          faltando([alvo], sem_linha) == [alvo])
    check("prefixo de outro comando não conta como citação",
          faltando(["/common:plan-x"], "`/common:plan-xyz`") == ["/common:plan-x"]
          and faltando(["/common:plan"], "`/common:plan-x`") == ["/common:plan"])

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print(f"\ntudo ok ({len(cmds)} comandos no catálogo)")


if __name__ == "__main__":
    main()
