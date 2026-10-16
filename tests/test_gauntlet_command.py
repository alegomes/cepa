#!/usr/bin/env python3
"""/common:gauntlet — o contrato do comando e do script canônico, por conteúdo.

O valor do Gauntlet está em duas garantias que só existem no texto: builders
isolados (nunca veem uns aos outros) e juízes cegos (só objetivo + barra +
designs anonimizados, em ordem rotacionada). Se uma edição apagar isso, o
comando vira "3 opiniões do mesmo agente" e nenhum outro teste acusaria.
Também trava que o script não volte a ter caminho absoluto, Date.now ou
Math.random (o script roda no dialeto determinístico da Workflow tool).
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CMD = REPO / "common" / "commands" / "gauntlet.md"
SCRIPT = REPO / "common" / "gauntlet" / "gauntlet.workflow.js"
ANGULOS = REPO / "common" / "gauntlet" / "angulos.md"
FAILURES = []


def check(nome, cond, detalhe=""):
    print(("  ok  " if cond else "FAIL  ") + nome + ("" if cond else f"  {detalhe}"))
    if not cond:
        FAILURES.append(nome)


def comando():
    check("o comando existe", CMD.is_file(), str(CMD))
    if not CMD.is_file():
        return
    f = CMD.read_text(encoding="utf-8")
    limpo = f.replace("`", "").lower()
    for passo in ("barra", "builders isolados", "juízes cegos", "borda",
                  "revisão", "checagem"):
        check(f"nomeia o passo '{passo}'", passo in limpo)
    check("argument-hint com as flags",
          "argument-hint: <alvo> [--builders=3] [--angulos=a,b,c] [--slug=<slug>]" in f)
    check("declara custo opt-in", "opt-in" in limpo and "600k" in limpo
          and "9 agentes" in limpo)
    check("recusa código provável / tarefa mecânica",
          "recuse" in limpo and "provável" in limpo and "mecânic" in limpo)
    check("declara o caminho de saída",
          "docs/internals/gauntlet-<slug>.md" in f)
    check("cita o script canônico",
          "gauntlet/gauntlet.workflow.js" in f and "CLAUDE_PLUGIN_ROOT" in f)
    check("manda não reescrever o script", "não reescreva o script" in limpo)
    check("cita o registry de ângulos", "gauntlet/angulos.md" in f)
    plano = " ".join(limpo.split())  # frases quebradas em linhas
    check("builders isolados e sem ver uns aos outros",
          "builders nunca veem uns aos outros" in plano
          and "nenhum vê a saída de outro" in plano)
    check("juízes cegos veem só objetivo + barra + designs anonimizados",
          "juízes só veem objetivo + barra + designs anonimizados" in plano)
    check("ordem rotacionada por juiz",
          "em ordem rotacionada por juiz" in plano)
    check("fórmula Borda: 1º lugar = N pontos",
          "(1º lugar = n pontos, onde n é o número de designs)" in plano)
    check("desempate: mais 1º lugares, depois ordem dos designs, nomeado",
          "empate: vence o design que ficou em 1º lugar com mais juízes" in plano
          and "o primeiro na ordem dos designs" in plano
          and "nomeia o empate" in plano)
    check("nunca implementa o design vencedor",
          "nunca implementa" in limpo)
    check("relata em plain-report", "plain-report" in f)
    check("emite telemetria gauntlet_run", "emit gauntlet_run" in f)
    check("compara com /common:advisors", "/common:advisors" in f)
    check("degrada sem a Workflow tool", "workflow tool" in limpo
          and "não estiver disponível" in limpo)


def script():
    check("o script existe", SCRIPT.is_file(), str(SCRIPT))
    if not SCRIPT.is_file():
        return
    s = SCRIPT.read_text(encoding="utf-8")
    check("guarda de args string",
          'typeof args === "string" ? JSON.parse(args) : args' in s)
    check("export const meta", "export const meta" in s)
    for fase in ("Barra", "Builders", "Julgamento", "Revisão"):
        check(f"fase '{fase}'", f"title: '{fase}'" in s or f'title: "{fase}"' in s)
    check("sem Date.now", "Date.now" not in s)
    check("sem Math.random", "Math.random" not in s)
    check("sem caminho absoluto", "/Users/" not in s)
    check("calcula Borda", "ranking.forEach" in s and "designs.length - idx" in s)
    check("rotaciona a ordem por juiz", "(i + j) % designs.length" in s)
    check("erro com menos de 2 designs", "designs.length < 2" in s)
    check("erro sem veredito", "nenhum juiz" in s)
    check("lê brief do ângulo", ".brief" in s)
    check("lê reads/goal/context de args",
          "A.reads" in s and "A.goal" in s and "A.context" in s)


def angulos():
    check("registry de ângulos existe", ANGULOS.is_file(), str(ANGULOS))
    if not ANGULOS.is_file():
        return
    a = ANGULOS.read_text(encoding="utf-8")
    for chave in ("mecanismo-novo", "estender-o-que-existe", "livre"):
        check(f"ângulo default '{chave}'", chave in a)


def main():
    print("/common:gauntlet — contrato\n")
    comando()
    script()
    angulos()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\ntudo ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
