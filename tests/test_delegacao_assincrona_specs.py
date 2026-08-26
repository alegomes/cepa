#!/usr/bin/env python3
"""Todo agente que delega carrega a seção de delegação assíncrona.

Sem dependência externa — rode com `python3 tests/test_delegacao_assincrona_specs.py`.

## Por que existe

A ferramenta `Agent` deste harness devolve `Async agent launched successfully`, não o
resultado: o subagente roda em segundo plano e o resultado chega depois, como notificação
que reinvoca quem delegou. As 10 specs que delegam eram silenciosas sobre isso — nenhuma
dizia onde o turno termina — e os leads preenchiam o silêncio sondando o disco atrás do
arquivo do worker. Medição de 2026-08-26 sobre 5 runs: 912 minutos (15 horas) em comando
que não fazia nada, entre 19% e 52% do relógio de cada run.

A seção entrou nas 10. O buraco que sobra é o próximo agente: quem criar o 11º lead, ou
uma topologia nova, não tem como saber que essa seção precisa existir — e a ausência não
falha nada, ela só devolve a sondagem em silêncio. É o padrão que este repo já catalogou
três vezes (memória `gate-por-nome-de-ferramenta-falha-aberto`): conserto aplicado em N
cópias, cópia N+1 nasce sem ele.

Este teste é o radar. A regra é mecânica e derivada do frontmatter, não de uma lista fixa:
**se o agente tem `Task` nas ferramentas, ele delega; se delega, precisa da seção.** Uma
lista fixa envelheceria exatamente como as 10 specs envelheceram.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TITULO = "## Delegação é assíncrona"

# O que a seção tem que dizer, além de existir. Cada marca é uma das três coisas
# que o lead precisa saber; uma seção que perdeu qualquer uma delas parou de ensinar.
# As specs quebram linha no meio das frases, então cada marca tolera espaço em
# branco onde houver espaço — casar com `\s+` e não com " " literal.
MARCAS = [
    ("o retorno real da chamada", re.compile(r"Async\s+agent\s+launched\s+successfully")),
    ("o que fazer no lugar", re.compile(r"[Ee]ncerre\s+o\s+turno")),
    ("o antipadrão medido", re.compile(r"until\s+\[\s+-f")),
]


def delega(texto: str) -> bool:
    """O agente declara `Task` no campo `tools:` do frontmatter."""
    m = re.search(r"^tools:.*$", texto, flags=re.M)
    return bool(m) and re.search(r"\bTask\b", m.group(0)) is not None


def main():
    specs = sorted(REPO.glob("*/agents/*.md"))
    if not specs:
        print(f"FAIL: nenhum */agents/*.md sob {REPO}", file=sys.stderr)
        return 1

    delegantes = [p for p in specs if delega(p.read_text(encoding="utf-8"))]
    if not delegantes:
        print("FAIL: nenhum agente com Task encontrado — o detector quebrou, "
              "não o repo", file=sys.stderr)
        return 1

    falhas = []
    for p in delegantes:
        texto = p.read_text(encoding="utf-8")
        rel = p.relative_to(REPO)
        if TITULO not in texto:
            falhas.append(f"{rel}: delega (tem Task) e NÃO tem a seção "
                          f"'{TITULO}'")
            continue
        for nome, marca in MARCAS:
            if not marca.search(texto):
                falhas.append(f"{rel}: tem a seção mas perdeu {nome} "
                              f"({marca.pattern})")

    for f in falhas:
        print("FAIL:", f, file=sys.stderr)
    if falhas:
        print(f"\n{len(falhas)} falha(s) em {len(delegantes)} agentes que delegam.\n"
              "Todo agente com `Task` precisa da seção — copie de "
              "build-hex/agents/engineering-lead.md.", file=sys.stderr)
        return 1

    print(f"ok — {len(delegantes)} agentes que delegam, todos com a seção completa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
