#!/usr/bin/env python3
"""PreToolUse (common) — só o atlassian-expert escreve no Jira pela CLI `twg`.

## Por que existe

Pelo MCP, a regra "um só agente muda o Jira" se sustenta pelo campo `tools:` do
frontmatter: só o `board-flow:atlassian-expert` tem as ferramentas de escrita.
Em 2026-09-24 o caminho local do atlassian-expert passou a ser a CLI `twg`
(caminho O3 de `docs/archive/estrategia-twg-vs-mcp.md`), e a CLI chega por
`Bash` — ferramenta que dezenas de agentes têm. Sem este hook, qualquer um deles
cria card, edita campo e transiciona com uma linha.

É o risco R2 do documento, e a mesma lição do `bitbucket-decision-lock`: a
amarra é o **efeito** (mutar o Jira, reconhecido pelo `_jiramut`) e a
autorização é a **identidade do agente**.

## O que passa e o que não passa

- Leitura (`get`, `query`, `transition` sem `--transition-id`, ajuda) → passa
  para qualquer um.
- Qualquer escrita no Jira pela `twg`, legível ou opaca → só
  `board-flow:atlassian-expert`.
- A sessão principal (payload sem `agent_type`) passa: é o humano.

Agente embutido sem prefixo de plugin (`general-purpose`, `Explore`) NÃO passa:
ele não é o humano, só não tem dono. O `bitbucket-decision-lock` segue a mesma
regra desde 2026-09-24.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _jiramut as J  # noqa: E402

AUTHORIZED = "board-flow:atlassian-expert"


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    hit = J.classify(payload)
    if hit is None:
        sys.exit(0)

    agent_type = payload.get("agent_type", "") or ""
    if not agent_type or agent_type == AUTHORIZED:
        sys.exit(0)

    print(
        f"[jira-write-lock] BLOCKED: o agente {agent_type!r} tentou escrever no "
        f"Jira pela `twg` ({hit['kind']}).\n"
        f"  Só o {AUTHORIZED} muda o Jira. É ele que lê o board-flow.yaml, confere\n"
        f"  a escrita com uma releitura e passa pelos gates de aceite, de sumário e\n"
        f"  de motivo de devolução.\n"
        f"  O caminho correto: devolva o pedido ao comando que te chamou, ou delegue\n"
        f"  ao {AUTHORIZED}.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
