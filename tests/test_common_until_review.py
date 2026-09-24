#!/usr/bin/env python3
"""/common:until-review — o contrato do comando, por conteúdo.

Ele roda num `claude -p` no fim do run, sem ninguém olhando. Se uma edição
apagar a cláusula "só leitura", o próximo run pode mesclar, mexer na fila ou
transicionar card às 4h da manhã, e nenhum outro teste acusaria.
"""

import sys
from pathlib import Path

CMD = Path(__file__).resolve().parents[1] / "common" / "commands" / "until-review.md"
FAILURES = []


def check(nome, cond, detalhe=""):
    print(("  ok  " if cond else "FAIL  ") + nome + ("" if cond else f"  {detalhe}"))
    if not cond:
        FAILURES.append(nome)


def main():
    print("/common:until-review — contrato\n")
    check("o comando existe", CMD.is_file(), str(CMD))
    if not CMD.is_file():
        return 1
    f = CMD.read_text(encoding="utf-8")
    limpo = f.replace("`", "").lower()
    i = limpo.find("**só leitura.**")
    trecho = limpo[i:i + 600] if i != -1 else ""
    check("declara só leitura nas instruções", bool(trecho))
    for proibido in ("git merge", "cepa-plan finish", "transição de card",
                     "build", "push", "edição de arquivo"):
        check(f"...e proíbe {proibido}", proibido in trecho, trecho[:200])
    check("proíbe executar providência mesmo reversível",
          "nunca execute uma providência, mesmo reversível" in limpo)
    check("lê o resumo do cepa-until-digest, não o .log inteiro",
          "cepa-until-digest" in f and "leia o resumo, não o .log" in limpo)
    check("manda conferir no git antes de afirmar",
          "confira antes de afirmar" in limpo)
    check("relata em plain-report", "plain-report" in f)
    check("fecha com perguntas fechadas com recomendação",
          "perguntas" in limpo and "recomendo sim/não" in limpo)
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
