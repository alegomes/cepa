#!/usr/bin/env python3
"""A fila do cepa tem por onde ser executada (item topologia-do-cepa, 2026-09-25).

Sem dependências — rode com `python3 tests/test_topologia_do_cepa.py`.
Sai não-zero em falha.

O `/common:drain-plan` executa cada item como o `/common:autonomous-start`
despacha: lê `.claude/topology` e chama `/<topologia>:plan-build-validate`, ou
`/<topologia>:reproduce-fix-verify` quando o item é defeito. O cepa não tinha o
arquivo, e o passo 1 do autonomous-start abortava ("No topology configured").
Nenhuma topologia servia: o build-solo, a única sem path-lock em apps/* ou em
camadas Maven, não tinha comando de flow.

O que está travado:

  - **O cepa declara topologia.** Sem o arquivo, volta o aborto do passo 1.
  - **A topologia declarada é um plugin deste repo.** Nome que não casa plugin
    instalado também aborta ("doesn't match any installed plugin").
  - **Ela tem os dois flows que o drain-plan despacha.** Ter só um faz o
    primeiro item de defeito (ou o primeiro de feature) abortar no passo 2.
  - **Os flows rodam a suíte e commitam na branch.** Sob o `cepa-until` o item
    trabalha na branch da noite e o supervisor espera commit, não árvore suja.
"""

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FLOWS = ("plan-build-validate", "reproduce-fix-verify")

falhas = []


def caso(nome, cond, detalhe=""):
    print(("ok   " if cond else "FAIL ") + nome + ("" if cond else f" — {detalhe}"))
    if not cond:
        falhas.append(nome)


marcador = RAIZ / ".claude" / "topology"
caso("o cepa declara topologia em .claude/topology", marcador.is_file(),
     "arquivo ausente: o autonomous-start aborta no passo 1")
topologia = marcador.read_text().strip() if marcador.is_file() else ""

manifesto = RAIZ / topologia / ".claude-plugin" / "plugin.json"
nome_plugin = (json.loads(manifesto.read_text()).get("name")
               if topologia and manifesto.is_file() else None)
caso("a topologia é um plugin deste repo", nome_plugin == topologia,
     f"{topologia!r} não tem {manifesto.relative_to(RAIZ) if topologia else 'manifesto'}")

for flow in FLOWS:
    cmd = RAIZ / topologia / "commands" / f"{flow}.md"
    caso(f"{topologia} tem /{topologia}:{flow}", bool(topologia) and cmd.is_file(),
         f"{cmd.relative_to(RAIZ)} ausente: o drain-plan aborta no passo 2")
    if cmd.is_file():
        texto = cmd.read_text()
        caso(f"/{topologia}:{flow} roda a suíte em primeiro plano",
             "tests/run-all.sh" in texto and "foreground" in texto,
             "sem suíte colhida no mesmo turno, o item fecha sem prova")
        caso(f"/{topologia}:{flow} commita na branch atual, sem push",
             "Commit" in texto and "No push" in texto,
             "o supervisor do cepa-until espera commit na branch da noite")

sys.exit(1 if falhas else 0)
