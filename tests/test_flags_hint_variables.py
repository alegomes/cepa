#!/usr/bin/env python3
"""Toda flag de um comando está nos dois lugares: `argument-hint:` e `## Variables`.

Sem dependência de terceiros — rode com `python3 tests/test_flags_hint_variables.py`.
Sai não-zero na primeira varredura com falha.

A dor: cada comando descreve os parâmetros duas vezes. O `argument-hint:` do
frontmatter é o que o autocompletar mostra; a seção `## Variables` é o que o
agente lê. No levantamento de 2026-09-16 três divergiam — `--offline` do
/common:drain-plan só em Variables (o autocompletar não o mostrava),
`--no-jira` do /common:autonomous-start e `--force-feature-flow` do
/board-flow:execute só no hint (o agente não tinha a definição). O
/common:session --help já acusava ao ler os dois lugares, mas a fonte seguia
errada, e nada impedia a próxima.

Comando sem seção `## Variables` fica fora: não há o que comparar. A exceção
conhecida entra em EXCECOES com o motivo escrito — nunca como omissão calada.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

FLAG = re.compile(r"--[a-z][a-z0-9-]*")

# (arquivo relativo, flag) → por que a divergência é aceita hoje.
EXCECOES = {
    ("common/commands/session.md", "--max"):
        "no hint é exemplo de argumento de OUTRA rotina "
        "(`/common:session prove-drain --max 5`), não flag do session",
    ("common/commands/plan.md", "--source"):
        "divergência real, fora do escopo do item parametros-de-comando-pela-metade "
        "(que nomeou três comandos); só em Variables",
    ("common/commands/worktree-label.md", "--branch"):
        "divergência real, fora do escopo do item parametros-de-comando-pela-metade "
        "(que nomeou três comandos); só em Variables",
}

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def flags(texto):
    """(flags do argument-hint, flags de ## Variables ou None se não há a seção)."""
    m = re.search(r"^argument-hint:(.*)$", texto, re.M)
    hint = set(FLAG.findall(m.group(1))) if m else set()
    v = re.search(r"^## Variables\n(.*?)(?=^## |\Z)", texto, re.M | re.S)
    var = set(FLAG.findall(v.group(1))) if v else None
    return hint, var


def divergencias(rel, texto):
    """Lista de (rel, flag, lado-que-tem) que não está nos dois lugares."""
    hint, var = flags(texto)
    if var is None:
        return []
    out = [(rel, f, "só no argument-hint") for f in sorted(hint - var)]
    out += [(rel, f, "só em Variables") for f in sorted(var - hint)]
    return [d for d in out if (d[0], d[1]) not in EXCECOES]


def main():
    arquivos = sorted(REPO.glob("*/commands/*.md"))
    check("a varredura acha comandos", len(arquivos) > 20, f"achou {len(arquivos)}")

    achadas = []
    for arq in arquivos:
        rel = str(arq.relative_to(REPO))
        achadas += divergencias(rel, arq.read_text())
    check("toda flag está no argument-hint e em ## Variables", not achadas,
          "; ".join(f"{r} {f} ({lado})" for r, f, lado in achadas))

    for rel in ("common/commands/drain-plan.md",
                "common/commands/autonomous-start.md",
                "board-flow/commands/execute.md"):
        hint, var = flags((REPO / rel).read_text())
        check(f"{rel} tem Variables e flags nos dois lados",
              var is not None and hint and hint == var, f"hint={hint} var={var}")

    fantasmas = []
    for (rel, flag), _ in EXCECOES.items():
        p = REPO / rel
        if not p.exists():
            fantasmas.append(f"{rel} (sumiu)")
            continue
        hint, var = flags(p.read_text())
        if var is None or (flag in hint) == (flag in var):
            fantasmas.append(f"{rel} {flag} (não diverge mais)")
    check("toda exceção em EXCECOES ainda diverge", not fantasmas,
          "tire de EXCECOES: " + ", ".join(fantasmas))

    # O teste tem que conseguir ficar vermelho.
    base = ("---\nargument-hint: <x> [--a] [--b N]\n---\n\n## Variables\n\n"
            "- `--a` — um.\n- `--b N` — dois.\n\n## Instructions\n\n`--c` na prosa.\n")
    check("os dois lados iguais não acusam nada", divergencias("x.md", base) == [])
    check("flag só no hint é acusada",
          divergencias("x.md", base.replace("- `--b N` — dois.\n", ""))
          == [("x.md", "--b", "só no argument-hint")])
    check("flag só em Variables é acusada",
          divergencias("x.md", base.replace(" [--b N]", ""))
          == [("x.md", "--b", "só em Variables")])
    check("flag na prosa fora de Variables não conta como definida",
          divergencias("x.md", base.replace("[--b N]", "[--b N] [--c]")
                       ) == [("x.md", "--c", "só no argument-hint")])
    check("Variables como última seção também é lida",
          divergencias("x.md", "argument-hint: [--a]\n## Variables\n- `--a` x\n") == [])
    check("comando sem Variables fica fora",
          divergencias("x.md", "argument-hint: [--a]\n## Instructions\n") == [])

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print(f"\ntudo ok ({len(arquivos)} comandos varridos)")


if __name__ == "__main__":
    main()
