#!/usr/bin/env python3
"""Regression of the card reservation (claim) in /board-flow:drain and :prove-drain.

Why it exists: on 17/08/2026 two parallel sessions of the same user proved
the same 4 cards in the Review column — about 40 minutes of redone review. A
column's list is a snapshot; the contested resource is the board's queue, and the
reservation is now made there, with a `🔒 claim:` comment re-read card by card.

Two contracts are checked here:
  1. structural — both commands say to reserve BEFORE working the card,
     with a claim id per run, an expiry window and explicit release;
  2. functional — the claim comment (and the release one) crosses both
     comment gates of the harness. If someone rewrites the claim text as
     "returning the card", the bounce-reason-gate starts blocking the reservation and the
     drain jams without any structural test noticing.

No dependencies — run with `python3 tests/test_card_claim.py`.
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


# ── 1. structural ───────────────────────────────────────────────────────────

def test_structure():
    for given_name in ("drain.md", "prove-drain.md"):
        txt = (CMDS / given_name).read_text(encoding="utf-8")
        check(f"{given_name}: seção de reserva", "## Card reservation" in txt)
        check(f"{given_name}: claim id por run", "The run's claim id" in txt)
        check(f"{given_name}: marcador de reserva", "🔒 claim:" in txt)
        check(f"{given_name}: liberação explícita", "🔓 claim" in txt)
        check(f"{given_name}: janela de expiração", "90 minutes" in txt)
        check(f"{given_name}: liberação em inglês", "released — <reason>" in txt and "liberado — <motivo>" not in txt)
        check(f"{given_name}: pula card fora da coluna", "SKIPPED" in txt)
        # the reservation has to be step (a) of the loop — reserving after
        # building saves nothing, which is the original defect.
        loop = txt.split("### 4. Iterate", 1)[1] if "### 4. Iterate" in txt else ""
        first_ = next(
            (ln.strip() for ln in loop.splitlines() if re.match(r"\s*a\. ", ln)), ""
        )
        check(
            f"{given_name}: reserva é o primeiro passo do laço",
            first_.startswith("a. **Reserve the card first**"),
            f"achei: {first_[:60]!r}",
        )

    agent_text = AGENT.read_text(encoding="utf-8")
    check("atlassian-expert: rotina de claim", "### Claim de card" in agent_text)
    check("atlassian-expert: reporta ausência", "claim: none" in agent_text)


# ── 2. functional: the claim text passes through the comment gates ──────────

CLAIM = (
    "🔒 claim: wego-acesso-backend-3f9a1c2d — /board-flow:prove-drain in progress "
    "since 2026-08-18 09:45. Another session must skip this card. "
    "The reservation expires in 90 minutes."
)
RELEASE = "🔓 claim wego-acesso-backend-3f9a1c2d released — ERROR: Docker down on the host."
# Old fixed text (pt-BR): the readers keep accepting it during the transition.
CLAIM_PTBR = (
    "🔒 claim: wego-acesso-backend-3f9a1c2d — /board-flow:prove-drain em andamento "
    "desde 2026-08-18 09:45. Outra sessão deve pular este card. "
    "A reserva expira em 90 minutos."
)
RELEASE_PTBR = "🔓 claim wego-acesso-backend-3f9a1c2d liberado — ERROR: Docker fora no host."


def test_gates():
    for label, body_text in (("claim", CLAIM), ("liberação", RELEASE),
                          ("claim pt-BR antigo", CLAIM_PTBR),
                          ("liberação pt-BR antiga", RELEASE_PTBR)):
        r = run_hook(BOUNCE_HOOK, body_text)
        check(f"bounce-reason-gate deixa passar a {label}", r.returncode == 0, r.stderr.strip())
        r = run_hook(NULLS_HOOK, body_text)
        check(f"summary-nulls-gate deixa passar a {label}", r.returncode == 0, r.stderr.strip())


def main():
    test_structure()
    test_gates()
    if FAILURES:
        print(f"\n{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
