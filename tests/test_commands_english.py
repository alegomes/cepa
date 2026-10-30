#!/usr/bin/env python3
"""Every plugin command is in English — outside what is contract.

No third-party dependency — run with `python3 tests/test_commands_english.py`.

Owner's decision on 2026-10-20 (item `comandos-em-ingles` of the cepa queue):
description, argument-hint and body of every `*/commands/*.md` in English, with the
vocabulary of docs/how-it-fits.md. The translation removed 2087 lines with Portuguese
from the commands; without a guard, the next pt-BR edit passes silently and
the file gradually becomes bilingual again.

What may stay in Portuguese is contract, and contract always comes quoted:
between backticks (`**Próximo:**`, field names, cepa-plan output), between quotes
("sim = o item volta para a fila", sentences a script prints) or as a
bold label that the owner reads (**Pra você:**, **Precisa de você**). Code blocks
are also left out — they are what a script reads or what the owner sees. That is why the
sweep deletes those passages and looks for a Portuguese word in what remains: loose
prose in Portuguese is what this guard blocks.

Checked when writing: the same criterion accuses 1443 lines in the commands of
3569aaa (before the translation) and zero after it.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Words that only exist in Portuguese — none is an English word.
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


def without_quotations(text):
    """Deletes what is quoted: code, backticks, quotes and bold labels."""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text, flags=re.S)
    text = re.sub(r'"[^"]{0,400}"', "", text, flags=re.S)
    text = re.sub(r"\*\*[^*\n]{1,80}\*\*", "", text)
    return text


def portuguese_lines(text):
    return [l.strip() for l in without_quotations(text).split("\n") if PT.search(l)]


def test_guard_distinguishes_prose_from_quotation():
    check("prosa solta em português é acusada",
          portuguese_lines("Não rode o build completo aqui.\n"))
    check("frase portuguesa sem acento também",
          portuguese_lines("Leia a fila e diga quando parar.\n"))
    check("citação entre crases passa",
          not portuguese_lines("The hook parses `**Próximo:**` here.\n"))
    check("citação entre aspas passa, mesmo quebrando a linha",
          not portuguese_lines(
              'The menu says "sim = o item volta\npara a fila" verbatim.\n'))
    check("rótulo em negrito que o dono lê passa",
          not portuguese_lines("End with **Pra você:** and the count.\n"))
    check("bloco de código passa",
          not portuguese_lines("Run:\n```\ncepa-plan finish --evidence "
                                  "\"não colhido\"\n```\n"))
    check("prosa inglesa passa",
          not portuguese_lines("Never edit plan.yaml by hand; the queue "
                                  "is the only truth.\n"))


def test_commands_in_english():
    files = sorted(REPO.glob("*/commands/*.md"))
    check("há comandos para varrer", len(files) >= 60, str(len(files)))
    for file in files:
        rel = file.relative_to(REPO)
        findings = portuguese_lines(file.read_text(encoding="utf-8"))
        check(f"{rel} sem prosa em português", not findings,
              " | ".join(a[:100] for a in findings[:3]))


def main():
    test_guard_distinguishes_prose_from_quotation()
    test_commands_in_english()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\ntudo ok")


if __name__ == "__main__":
    main()
