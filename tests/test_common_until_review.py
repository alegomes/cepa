#!/usr/bin/env python3
"""/common:until-review — the command's contract, by content.

It runs in a `claude -p` at the end of the run, with nobody watching. If an edit
deleted the "read-only" clause, the next run could merge, tamper with the queue or
transition a card at 4am, and no other test would accuse it.
"""

import sys
from pathlib import Path

CMD = Path(__file__).resolve().parents[1] / "common" / "commands" / "until-review.md"
FAILURES = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def main():
    print("/common:until-review — contrato\n")
    check("o comando existe", CMD.is_file(), str(CMD))
    if not CMD.is_file():
        return 1
    f = CMD.read_text(encoding="utf-8")
    clean = f.replace("`", "").lower()
    i = clean.find("**read-only.**")
    excerpt = " ".join(clean[i:i + 600].split()) if i != -1 else ""
    check("declara só leitura nas instruções", bool(excerpt))
    for forbidden in ("git merge", "cepa-plan finish", "card transition",
                     "build", "push", "file edit"):
        check(f"...e proíbe {forbidden}", forbidden in excerpt, excerpt[:200])
    check("proíbe executar providência mesmo reversível",
          "never execute a course of action, even a reversible one" in clean)
    check("lê o resumo do cepa-until-digest, não o .log inteiro",
          "cepa-until-digest" in f and "read the digest, not the .log" in clean)
    check("manda conferir no git antes de afirmar",
          "check before you state" in clean)
    check("relata em plain-report", "plain-report" in f)
    check("lê o estado do run e comenta cada ação pelo id",
          ".estado.json" in f and "by its id" in clean)
    check("não numera as ações por conta própria",
          "with no numbering of your own" in clean)
    check("repete o bloco 'fica com você'", "left with you" in clean)
    check("tarefa do dono traz 'Done when'", "done when" in clean)
    j = clean.find("left with you")
    check("'Left with you' manda escrever o cepa-plan answer colável",
          "cepa-plan answer" in clean[j:j + 2500], clean[j:j + 200])
    check("fecha com perguntas fechadas com recomendação",
          "closed questions" in clean and "i recommend yes/no" in clean)
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
