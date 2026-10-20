#!/usr/bin/env python3
"""Todo comando dos plugins está em inglês — fora do que é contrato.

Sem dependência de terceiros — rode com `python3 tests/test_commands_english.py`.

Decisão do dono em 2026-10-20 (item `comandos-em-ingles` da fila cepa):
descrição, argument-hint e corpo de todo `*/commands/*.md` em inglês, com o
vocabulário de docs/how-it-fits.md. A tradução tirou 2087 linhas com português
dos comandos; sem uma guarda, a próxima edição em pt-BR passa calada e o
arquivo volta a ser bilíngue aos poucos.

O que pode continuar em português é contrato, e contrato sempre vem citado:
entre crases (`**Próximo:**`, nomes de campo, saída do cepa-plan), entre aspas
("sim = o item volta para a fila", frases que um script imprime) ou como rótulo
em negrito que o dono lê (**Pra você:**, **Precisa de você**). Blocos de código
também ficam de fora — são o que um script lê ou o que o dono vê. Por isso a
varredura apaga esses trechos e procura palavra portuguesa no que sobra: prosa
solta em português é o que esta guarda barra.

Conferido ao escrever: o mesmo critério acusa 1443 linhas nos comandos de
3569aaa (antes da tradução) e zero depois dela.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Palavras que só existem em português — nenhuma é palavra inglesa.
PT = re.compile(
    r"(?i)(?<![\w`<-])(não|você|está|são|também|quando|então|uma|isso|pelo|"
    r"pela|já|só|aqui|depois|antes|sempre|nunca|porque|é|à|ção|ções|ões)"
    r"(?![\w>-])")

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def sem_citacoes(texto):
    """Apaga o que é citado: código, crases, aspas e rótulos em negrito."""
    texto = re.sub(r"```.*?```", "", texto, flags=re.S)
    texto = re.sub(r"`[^`]*`", "", texto, flags=re.S)
    texto = re.sub(r'"[^"]{0,400}"', "", texto, flags=re.S)
    texto = re.sub(r"\*\*[^*\n]{1,80}\*\*", "", texto)
    return texto


def linhas_em_portugues(texto):
    return [l.strip() for l in sem_citacoes(texto).split("\n") if PT.search(l)]


def test_guarda_distingue_prosa_de_citacao():
    check("prosa solta em português é acusada",
          linhas_em_portugues("Não rode o build completo aqui.\n"))
    check("frase portuguesa sem acento também",
          linhas_em_portugues("Leia a fila e diga quando parar.\n"))
    check("citação entre crases passa",
          not linhas_em_portugues("The hook parses `**Próximo:**` here.\n"))
    check("citação entre aspas passa, mesmo quebrando a linha",
          not linhas_em_portugues(
              'The menu says "sim = o item volta\npara a fila" verbatim.\n'))
    check("rótulo em negrito que o dono lê passa",
          not linhas_em_portugues("End with **Pra você:** and the count.\n"))
    check("bloco de código passa",
          not linhas_em_portugues("Run:\n```\ncepa-plan finish --evidence "
                                  "\"não colhido\"\n```\n"))
    check("prosa inglesa passa",
          not linhas_em_portugues("Never edit plan.yaml by hand; the queue "
                                  "is the only truth.\n"))


def test_comandos_em_ingles():
    arquivos = sorted(REPO.glob("*/commands/*.md"))
    check("há comandos para varrer", len(arquivos) >= 60, str(len(arquivos)))
    for arq in arquivos:
        rel = arq.relative_to(REPO)
        achados = linhas_em_portugues(arq.read_text(encoding="utf-8"))
        check(f"{rel} sem prosa em português", not achados,
              " | ".join(a[:100] for a in achados[:3]))


def main():
    test_guarda_distingue_prosa_de_citacao()
    test_comandos_em_ingles()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\ntudo ok")


if __name__ == "__main__":
    main()
