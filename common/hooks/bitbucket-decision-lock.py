#!/usr/bin/env python3
"""PreToolUse (common) — só o bitbucket-expert decide o destino de um pull request.

## Por que existe

O `review-gate` existe para que a decisão sobre um PR — aprovar, mergear, recusar,
pedir mudanças — não seja tomada por quem escreveu o código. Até 2026-08 isso se
sustentava por obscuridade: o único caminho até o Bitbucket eram dois scripts
empacotados (`review-gate/bin/open-pr.sh`, `merge-pr.sh`), e o
`bitbucket-expert` era o único agente que sabia deles.

A CLI `twg` da Atlassian destrói essa obscuridade. Ela vem autenticada
(`twg doctor` reporta `Bitbucket token: present`), está instalada, e expõe

    twg bitbucket pull-requests approve <id>
    twg bitbucket pull-requests merge  <id>

em uma linha. **18 dos 50 agentes deste repo têm `Bash`** — inclusive os que
escrevem o código. Sem este hook, qualquer um deles aprova e mergeia o próprio
PR, e o gate de revisão vira decoração.

É a mesma lição do `_jiramut.py`, uma superfície adiante: enforcement amarrado ao
*caminho* vale só enquanto ninguém inventa um caminho novo. Aqui a amarra é o
**efeito** (decidir sobre um PR), e a autorização é a **identidade do agente**.

## O que passa e o que não passa

- Leitura de PR (`get`, `query`, `diff`, `activity`, …) → passa para qualquer um.
  Ler o próprio PR é bom; decidir sobre ele é que não.
- Escrita que não decide (`comment`, `task`, `update`) → passa, com aviso.
- **Decisão** (`approve`, `merge`, `decline`, `request-changes`) → só
  `review-gate:bitbucket-expert`. Qualquer outro agente é barrado.
- A sessão principal (payload sem `agent_type`) passa: é o humano, e o humano
  sempre pôde aprovar o próprio PR se quisesse.
- Agente embutido sem prefixo de plugin (`general-purpose`, `Explore`) NÃO
  passa: ele não é o humano, só não tem dono. Até 2026-09-24 este hook o tratava
  como sessão principal, e um `general-purpose` podia aprovar e mergear PR.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _jiramut as J  # noqa: E402

# O único agente cuja função É decidir sobre PR.
AUTHORIZED = "review-gate:bitbucket-expert"


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "") or ""
    hit = J.classify_bitbucket(command)
    if hit is None:
        sys.exit(0)

    agent_type = payload.get("agent_type", "") or ""

    # Sem agent_type → sessão principal. É o humano.
    if not agent_type:
        sys.exit(0)

    if agent_type == AUTHORIZED:
        sys.exit(0)

    if not hit["decides"]:
        # Escrita que não decide o destino do código: avisa e deixa passar.
        print(
            f"[bitbucket-decision-lock] {agent_type} está escrevendo no Bitbucket "
            f"({hit['verb']}). Não é uma decisão de merge, então passa — mas o dono "
            f"dessa superfície é o {AUTHORIZED}.",
        )
        sys.exit(0)

    print(
        f"[bitbucket-decision-lock] BLOCKED: o agente {agent_type!r} tentou "
        f"DECIDIR o destino de um pull request (`{hit['verb']}`).\n"
        f"  Motivo: {hit['reason']}\n"
        f"  Aprovar, mergear ou recusar um PR é o ato que o review-gate existe para\n"
        f"  separar de quem escreveu o código. Um agente que implementa e depois\n"
        f"  aprova o próprio trabalho não passou por revisão nenhuma — só registrou\n"
        f"  que passou.\n"
        f"  O caminho correto: devolva a decisão ao comando que te chamou, e deixe o\n"
        f"  {AUTHORIZED} executá-la. Se a revisão precisa mesmo ser dispensada, quem\n"
        f"  dispensa é uma pessoa, não um agente.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
