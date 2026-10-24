#!/usr/bin/env python3
"""The atlassian-expert spec fits the budget and loses no rule.

Measured on 13/09/2026 with cepa-tokens: in the agent's 684 executions in the previous
30 days, the first request to the model (system prompt + spec +
tools, before any work) had a median of 34,469 tokens, 73% of the
median spend of an execution. The spec had 34,561 bytes, the largest in the repo. It
was condensed; this test keeps it from growing again unseen and keeps the
cut from taking a refusal or a rule along with it.

Run: python3 tests/test_atlassian_expert_spec.py
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPEC = REPO / "board-flow" / "agents" / "atlassian-expert.md"
# Half of the 34,561 bytes from before the cut (34,561 ÷ 2 = 17,280), whole
# file. On 24/09/2026 (O0 + O3) the `tools:` line lost the 32 names of the two
# local servers and the spec gained the `twg` command map in their place.
BUDGET_BYTES = 17280

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


# Each rule, by the excerpt that identifies it. Losing one of these is losing the rule.
RULES = {
    "preflight de conexão": "failed preflight",
    "drift do board-flow.yaml": "board-flow.yaml drift",
    "override por topologia substitui listas inteiras": "replaced whole",
    "escopo com precedência": "first match wins",
    "escopo rejeitado pelo Jira": "scope JQL fragment rejected",
    "guard op nunca bloqueia": "Never block on a guard op",
    "nunca inferir identificador": "Never infer or construct any Jira identifier",
    "site ausente não vira pedido de auth": "never an auth request",
    "transição só por transitionJiraIssue": "Never set status through `editJiraIssue`",
    "read-back de create": "confirms it does not exist",
    "read-back de transição": "not <target>",
    "read-back de comentário não julga formatação": "never to judge its formatting",
    "summary obrigatório em review": "requires Implementation Summary",
    "quatro campos nulos explícitos": "missing explicit-null field",
    "motivo estruturado em bounce": "bounce-back requires a structured Reason",
    "motivo por card em lote": "one reason pasted across N cards",
    "attention não é estado": '"Attention" is not a state',
    "tipo de link validado no site": "not found on this site",
    "comentário nunca é reescrito por defeito não visto": "Never rewrite or repost the comment",
    "cascata só propõe": "Never transition a sibling in the same run",
    "proposta de cascata só com irmão aberto": "only if at least one sibling is still open",
    "claim reporta ausência": "claim: none",
    "vocabulário da UI": "work item",
    "palavra na URL não prova o texto da UI": "inside a URL is not evidence",
    "erro de tela que mente": "field configuration",
    # 24/09/2026 (O3): the local path is `twg`, the cloud stays on MCP.
    "detector de caminho é um comando só": "command -v twg >/dev/null && twg --version",
    "sem caminho nenhum vira BLOCKED": "BLOCKED: no Jira path",
    "nunca instalar nem caçar a twg": "never install, hunt for or retry",
    "twg api é proibido": "Never `twg api`",
    "corpo do comentário na linha de comando": "inline in `--body`",
    # 13/09/2026: 158 calls failed with an invented cloudId; the literal site
    # name never failed (2,648 calls).
    "cloudId é o defaults.site literal": "copied literally (a hostname works as cloudId)",
    "erro de cloudId não troca de servidor": "never by switching servers",
    # 25/09/2026: 35 WEGO cards were born without the system's Team and Module.
    "todo create leva os required_fields": "Every create sends every resolved `required_fields`",
}


def main():
    text = SPEC.read_text(encoding="utf-8")
    size = len(text.encode("utf-8"))
    check(f"spec cabe em {BUDGET_BYTES} bytes ({size})", size <= BUDGET_BYTES)
    for given_name, excerpt in RULES.items():
        check(f"regra presente: {given_name}", excerpt in text, repr(excerpt))
    tools = re.search(r"^tools:(.*)$", text, re.M).group(1)
    names = [t.strip() for t in tools.split(",")]
    check("rotina cloud segue ligada: mcp__Atlassian__", any(n.startswith("mcp__Atlassian__") for n in names))
    check("Bash ligado para a twg", "Bash" in names)
    for prefix in ("mcp__claude_ai_Atlassian__", "mcp__mcp-atlassian__"):
        check(f"servidor local desligado (O0/O3): {prefix}", prefix not in tools)
    sys.path.insert(0, str(REPO / "common" / "hooks"))
    import _jiramut
    check(f"versão verificada da twg igual à do _jiramut ({_jiramut.TWG_VERIFIED})",
          f"verified version: **{_jiramut.TWG_VERIFIED}**" in text)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
