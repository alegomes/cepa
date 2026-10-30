#!/usr/bin/env python3
"""/common:gauntlet — the contract of the command and of the canonical script, by content.

The value of the Gauntlet lies in two guarantees that only exist in the text: isolated
builders (they never see each other) and blind judges (only objective + bar +
anonymized designs, in rotated order). If an edit erased that, the
command would become "3 opinions from the same agent" and no other test would flag it.
It also locks that the script does not go back to having an absolute path, Date.now or
Math.random (the script runs in the deterministic dialect of the Workflow tool).
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CMD = REPO / "common" / "commands" / "gauntlet.md"
SCRIPT = REPO / "common" / "gauntlet" / "gauntlet.workflow.js"
ANGLES = REPO / "common" / "gauntlet" / "angulos.md"
FAILURES = []


def check(name, cond, detail=""):
    print(("  ok  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def command():
    check("o comando existe", CMD.is_file(), str(CMD))
    if not CMD.is_file():
        return
    f = CMD.read_text(encoding="utf-8")
    clean = f.replace("`", "").lower()
    for step in ("bar", "isolated builders", "blind judges", "borda",
                  "revision", "final check"):
        check(f"nomeia o passo '{step}'", step in clean)
    check("argument-hint com as flags",
          "argument-hint: <target> [--builders=3] [--angulos=a,b,c] [--slug=<slug>]" in f)
    check("declara custo opt-in", "opt-in" in clean and "600k" in clean
          and "9 agents" in clean)
    check("recusa código provável / tarefa mecânica",
          "refuse" in clean and "provable" in clean and "mechanical task" in clean)
    check("declara o caminho de saída",
          "docs/internals/gauntlet-<slug>.md" in f)
    check("cita o script canônico",
          "gauntlet/gauntlet.workflow.js" in f and "CLAUDE_PLUGIN_ROOT" in f)
    check("manda não reescrever o script", "do not rewrite the script" in clean)
    check("cita o registry de ângulos", "gauntlet/angulos.md" in f)
    plan_text = " ".join(clean.split())  # phrases broken across lines
    check("builders isolados e sem ver uns aos outros",
          "builders never see each other" in plan_text
          and "none sees another's output" in plan_text)
    check("juízes cegos veem só objetivo + barra + designs anonimizados",
          "judges see only goal + bar + anonymized designs" in plan_text)
    check("ordem rotacionada por juiz",
          "in an order rotated per judge" in plan_text)
    check("fórmula Borda: 1º lugar = N pontos",
          "(1st place = n points, where n is the number of designs)" in plan_text)
    check("desempate: mais 1º lugares, depois ordem dos designs, nomeado",
          "tie: the design ranked 1st by the most judges wins" in plan_text
          and "the first in the order of the designs" in plan_text
          and "names the tie" in plan_text)
    i4 = plan_text.find("### 4. write the durable output")
    j4 = plan_text.find("### 5.", i4)
    p4 = plan_text[i4:j4] if i4 != -1 and j4 != -1 else ""
    check("passo 4 existe e grava o caminho da saída",
          bool(p4) and "docs/internals/gauntlet-<slug>.md" in p4)
    for title in ("## barra de qualidade (escrita antes de qualquer design)",
                   "## designs concorrentes e julgamento",
                   "### design a (<ângulo>) — <título>",
                   "### vereditos dos n juízes cegos",
                   "## design final (vencedor x revisado, com enxertos de ...)",
                   "## checagem final contra a barra"):
        check(f"passo 4 nomeia o título '{title}'", title in p4)
    check("passo 4 pede a tabela Borda com a conta mostrada",
          "a borda points table with the arithmetic shown" in p4
          and "(1st = n points, 2nd = n-1, ...; sum per design)" in p4)
    check("passo 4 pede ranking de cada juiz e maiores lacunas",
          "each judge's ranking" in p4 and "the biggest gaps" in p4)
    check("nunca implementa o design vencedor",
          "never implements" in clean)
    check("relata em plain-report", "plain-report" in f)
    check("emite telemetria gauntlet_run", "emit gauntlet_run" in f)
    check("compara com /common:advisors", "/common:advisors" in f)
    check("degrada sem a Workflow tool", "workflow tool" in clean
          and "is not available" in clean)


def script():
    check("o script existe", SCRIPT.is_file(), str(SCRIPT))
    if not SCRIPT.is_file():
        return
    s = SCRIPT.read_text(encoding="utf-8")
    check("guarda de args string",
          'typeof args === "string" ? JSON.parse(args) : args' in s)
    check("export const meta", "export const meta" in s)
    for phase in ("Barra", "Builders", "Julgamento", "Revisão"):
        check(f"fase '{phase}'", f"title: '{phase}'" in s or f'title: "{phase}"' in s)
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


def angles():
    check("registry de ângulos existe", ANGLES.is_file(), str(ANGLES))
    if not ANGLES.is_file():
        return
    a = ANGLES.read_text(encoding="utf-8")
    for key in ("mecanismo-novo", "estender-o-que-existe", "livre"):
        check(f"ângulo default '{key}'", key in a)


def main():
    print("/common:gauntlet — contrato\n")
    command()
    script()
    angles()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\ntudo ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
