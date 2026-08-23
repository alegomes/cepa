#!/usr/bin/env python3
"""Regressão do modo `--sweep` de /maestro:program-plan (P1, CS-1).

No third-party deps — run with `python3 tests/test_program_plan_sweep.py`.
Exits non-zero on the first failure.

`program-plan.md` é um comando conversacional (o passo-a-passo é seguido por um
agente Claude, não executado por interpretador) — não há função Python para
chamar. O que ESTE teste guarda é a regressão mais barata e real: que as
instruções do modo sweep continuam no arquivo, nomeando as 5 peças que CS-1
exige (docs/spec/planejador-de-lotes-paralelos.md):
  1. varre a fonte INTEIRA, não só `--demandas`;
  2. para nas próximas 2-3 ondas (não tenta particionar o backlog inteiro);
  3. demanda com superfície indeterminável entra sozinha na própria onda;
  4. sugere o teto de slices em vez de fixar 3;
  5. grava `cartorios:` no plano a partir de `common/bin/cepa-hotspots`.

A PROVA de que o mecanismo funciona (não só que a prosa existe) é o run real
registrado em `.claude/programs/lotes-2026-08-23/plan.yaml` + o veredito do
`cepa-dor --wave 1` sobre ele, documentado no commit desta mudança — este
arquivo não repete essa prova, só impede a prosa de regredir calada.

Cada `check()` abaixo tem o `id` do bloco `**[sweep:id]**` que ela cobre
embutido no nome (`[sweep:id] ...`). É esse embutimento que
`common/bin/cepa-promptcov` lê para cruzar contra os blocos do comando e
apontar peça sem cobertura — ver docs/promptcov.md.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CMD = REPO / "maestro" / "commands" / "program-plan.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def main():
    if not CMD.is_file():
        print(f"FAIL: {CMD} não existe")
        return 1

    text = CMD.read_text(encoding="utf-8")

    check("--sweep está no argument-hint", "--sweep" in text.splitlines()[2])
    check("[sweep:full-source] varre a fonte inteira (não só --demandas)",
          "Leia a fonte INTEIRA" in text)
    check("[sweep:full-source] para nas próximas 2-3 ondas",
          "**2-3 ondas**" in text)
    check("[sweep:full-source] nomeia a zona de enforcement como não-candidata a fork autônomo",
          "não é candidata a fork autônomo" in text)
    check("[sweep:solo-wave] demanda indeterminável entra sozinha na própria onda",
          "sozinha para sua própria onda" in text)
    check("[sweep:wave-cap] sugere o teto de slices em vez de fixar 3",
          "não é fixo em 3" in text and "sugira" in text.lower())
    check("[sweep:cartorios] invoca cepa-hotspots para popular cartorios",
          "cepa-hotspots" in text and "cartorios:" in text)
    check("[sweep:cartorios] aponta o campo cartorios como opcional e no topo do plano",
          "campo novo e\n   opcional" in text or "campo novo e opcional" in text)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
