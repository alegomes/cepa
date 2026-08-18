#!/usr/bin/env python3
"""Regressão da reserva de card (claim) em /board-flow:drain e :prove-drain.

Por que existe: em 17/08/2026 duas sessões paralelas do mesmo usuário provaram
os mesmos 4 cards da coluna Review — cerca de 40 minutos de revisão refeita. A
lista de uma coluna é uma foto; o recurso disputado é a fila do board, e a
reserva passou a ser feita lá, com um comentário `🔒 claim:` relido card a card.

Dois contratos são checados aqui:
  1. estrutural — os dois comandos mandam reservar ANTES de trabalhar o card,
     com claim id por run, janela de expiração e liberação explícita;
  2. funcional — o comentário de claim (e o de liberação) atravessa os dois
     gates de comentário do harness. Se alguém reescrever o texto do claim como
     "devolvendo o card", o bounce-reason-gate passa a bloquear a reserva e o
     drain trava sem que nenhum teste estrutural perceba.

Sem dependências — rode com `python3 tests/test_card_claim.py`.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CMDS = REPO / "board-flow" / "commands"
AGENT = REPO / "board-flow" / "agents" / "atlassian-expert.md"
BOUNCE_HOOK = REPO / "common" / "hooks" / "bounce-reason-gate.py"
NULLS_HOOK = REPO / "common" / "hooks" / "summary-nulls-gate.py"

CLOUD_TOOL = "mcp__claude_ai_Atlassian__addCommentToJiraIssue"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(hook, body):
    payload = json.dumps(
        {"tool_name": CLOUD_TOOL, "tool_input": {"issueIdOrKey": "WEGO-1", "commentBody": body}}
    )
    return subprocess.run(
        [sys.executable, str(hook)], input=payload, capture_output=True, text=True
    )


# ── 1. estrutural ───────────────────────────────────────────────────────────

def test_estrutura():
    for nome in ("drain.md", "prove-drain.md"):
        txt = (CMDS / nome).read_text(encoding="utf-8")
        check(f"{nome}: seção de reserva", "## Reserva do card" in txt)
        check(f"{nome}: claim id por run", "Claim id do run" in txt)
        check(f"{nome}: marcador de reserva", "🔒 claim:" in txt)
        check(f"{nome}: liberação explícita", "🔓 claim" in txt)
        check(f"{nome}: janela de expiração", "90 minutos" in txt)
        check(f"{nome}: pula card fora da coluna", "SKIPPED" in txt)
        # a reserva tem que ser o passo (a) do laço — reservar depois de
        # construir não economiza nada, que é o defeito original.
        laco = txt.split("### 4. Iterate", 1)[1] if "### 4. Iterate" in txt else ""
        primeira = next(
            (ln.strip() for ln in laco.splitlines() if re.match(r"\s*a\. ", ln)), ""
        )
        check(
            f"{nome}: reserva é o primeiro passo do laço",
            primeira.startswith("a. **Reserve o card primeiro**"),
            f"achei: {primeira[:60]!r}",
        )

    agente = AGENT.read_text(encoding="utf-8")
    check("atlassian-expert: rotina de claim", "### Claim de card" in agente)
    check("atlassian-expert: reporta ausência", "claim: none" in agente)


# ── 2. funcional: o texto do claim passa pelos gates de comentário ──────────

CLAIM = (
    "🔒 claim: wego-acesso-backend-3f9a1c2d — /board-flow:prove-drain em andamento "
    "desde 2026-08-18 09:45. Outra sessão deve pular este card. "
    "A reserva expira em 90 minutos."
)
RELEASE = "🔓 claim wego-acesso-backend-3f9a1c2d liberado — ERROR: Docker fora no host."


def test_gates():
    for rotulo, corpo in (("claim", CLAIM), ("liberação", RELEASE)):
        r = run_hook(BOUNCE_HOOK, corpo)
        check(f"bounce-reason-gate deixa passar a {rotulo}", r.returncode == 0, r.stderr.strip())
        r = run_hook(NULLS_HOOK, corpo)
        check(f"summary-nulls-gate deixa passar a {rotulo}", r.returncode == 0, r.stderr.strip())


def main():
    test_estrutura()
    test_gates()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
