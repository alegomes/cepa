#!/usr/bin/env python3
"""Os 4 agentes trancados por caminho dizem que o Auto Mode não vale para eles.

Sem dependências — rode com `python3 tests/test_auto_mode_nao_vale_para_path_lock.py`.
Sai não-zero em falha.

## O furo que este arquivo trava

O Auto Mode / modo bypass-permissions do Claude Code injeta na sessão a
diretriz "faça o trabalho pelo Bash: edite com sed, heredocs ou scripts curtos
em vez de Edit/Write". Os agentes domain-dev, api-dev, adapter-dev e
qa-engineer são contidos por `path-lock.py` (olha Edit/Write por glob) e
`bash-path-lock.py` (nega escrita por shell por padrão). Seguir a diretriz é
driblar o cadeado: no drain de 2026-08-20 três agentes gastaram o relatório
explicando por que desobedeceram e um qa-engineer driblou o cadeado com um
heredoc python. A correção barata (frente 1 do BACKLOG) é o próprio prompt do
agente dizer que a preferência não se aplica a ele.

## Perturbação (como saber que este teste prova algo)

Apague a bala "The Auto Mode preference for Bash does not apply to you" de um
dos quatro arquivos em `build-hex/agents/`: o caso daquele arquivo fica
vermelho e o script sai com código 1.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FAILURES = []

FRASE = "The Auto Mode preference for Bash does not apply to you"
AGENTES = ("domain-dev", "api-dev", "adapter-dev", "qa-engineer")


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(label)
        print(f"FAIL  {label}  {detail}")


def test_agentes_trancados_dizem_que_auto_mode_nao_vale():
    for nome in AGENTES:
        rel = f"build-hex/agents/{nome}.md"
        txt = (REPO / rel).read_text(encoding="utf-8")
        check(f"{rel} diz que a preferência do Auto Mode por Bash não se aplica",
              FRASE in txt)


def main():
    test_agentes_trancados_dizem_que_auto_mode_nao_vale()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s)")
        return 1
    print("tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
