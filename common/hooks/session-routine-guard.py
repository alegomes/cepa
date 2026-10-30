#!/usr/bin/env python3
"""UserPromptSubmit hook: refuses at launch a CONVERSATIONAL routine passed to
/common:session.

/common:session has a rule it calls "the rule that governs this command":
between launch and report, nothing is asked. It activates the default-yes skill
and, in step 3, reads the target command's file to ANTICIPATE, in a single round
of at most four questions, everything that command would ask later. That works
for /board-flow:prove-drain, whose questions are knowable beforehand (how many
cards, what to do with the ones that get stuck).

It does not work for /common:spec, which runs an interrogation: there the next
questions depend on what the owner answered to the previous one; nobody asks
about data migration before knowing where the scope boundary is. And the
guided-interrogation skill SUSPENDS the default-yes that session has just
activated. One orders to activate, the other orders to suspend, in the same
session; which one wins is luck.

What would happen without this gate: session squeezes four generic questions
into the launch, enters step 4 ("execution, no interruptions") and the rest of
the specification is GUESSED. Out comes a well-formatted docs/spec/<slug>.md,
with Surface and Red test on every criterion, passing the spec-readiness-gate,
because that gate checks that the fields exist, not that the answers came from
the owner. It is the failure mode the gate exists to prevent, entering through
the door it does not watch, and the session ends saying "done".

Mechanism:
  - Fires on UserPromptSubmit; exits right away if the prompt does not start
    with /common:session (the cost of the scan is only paid on that very rare
    occasion).
  - Resolves the first token to the real command, with the same aliases as
    session.md; a name with ":" is used literally.
  - Finds the command's file in the installed source (or in the repo), checks
    that the owning plugin matches the requested prefix (`capture.md` exists in
    board-flow AND in discovery, and `docs` lives in the `docs-topology/`
    directory) and reads the `interaction:` field of the frontmatter.
  - Which COPY to read is not a detail: the CC cache keeps the versions side by
    side (cache/cepa/common/1.4.0, 1.5.0, 1.6.0), and scanning in alphabetical
    order reads the old one. That is what happened in this hook's first version:
    it read the 1.5.0 spec.md, from before the marker, and silently let through
    the invocation it should have blocked. So the order is: CC's
    installed_plugins.json, which knows which copy is alive; then
    CLAUDE_PLUGIN_ROOT itself when the requested plugin is this one; and only
    then the scan, from the highest version to the lowest.
  - `interaction: conversational` -> blocks, telling to run it directly.
  - Anything unexpected (command not found, unreadable frontmatter, unknown
    root) -> ALLOWS. This gate asserts a positive fact about a file; when in
    doubt it does not know, and not knowing is no reason to block.

Exit codes:
  0 - allowed
  2 - blocked (stderr reaches the agent, which explains it to the owner)
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _cmdmeta import CONVERSATIONAL, find_command, interaction
except Exception:  # noqa: BLE001 — without the helper this gate knows nothing, and
    CONVERSATIONAL = find_command = interaction = None  # not knowing does not block.

# The aliases that step 1 of session.md maps to real commands.
APELIDOS = {
    "prove-drain": "board-flow:prove-drain",
    "drain": "board-flow:drain",
    "drain-plan": "common:drain-plan",
    "triage": "board-flow:triage",
    "decide": "board-flow:decide",
    "execute": "board-flow:execute",
    "autonomous": "common:autonomous-start",
    "docs": "docs:survey",
}

INVOCATION_RE = re.compile(r"^\s*/common:session\s+(\S+)", re.IGNORECASE)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    if find_command is None:
        sys.exit(0)          # helper missing: does not know, does not block

    prompt = payload.get("prompt") or ""
    m = INVOCATION_RE.match(prompt)
    if not m:
        sys.exit(0)          # the cost of the scan is only paid here

    token = m.group(1).lstrip("/")
    target = token if ":" in token else APELIDOS.get(token)
    if not target or ":" not in target:
        sys.exit(0)          # unknown routine is session's problem, not this gate's

    plugin, _, cmd = target.partition(":")
    cmd_file = find_command(plugin, cmd)
    if cmd_file is None:
        sys.exit(0)          # file not found: does not know, does not block

    if interaction(cmd_file) != CONVERSATIONAL:
        sys.exit(0)

    print(
        f"[session-routine-guard] BLOQUEADO: /{target} conversa com você, e "
        "/common:session foi feito para não conversar.\n"
        "  A regra que rege o /common:session é 'entre a largada e o relatório, "
        "você não pergunta nada': ele ativa a skill default-yes e, no passo 3, "
        f"antecipa numa rodada só tudo que /{target} perguntaria depois.\n"
        f"  /{target} não é antecipável: cada resposta sua decide quais são as "
        "próximas perguntas. Espremido numa rodada, o resto seria ADIVINHADO — "
        "e o resultado sai bem formatado, passa nos gates, e ninguém percebe "
        "que as respostas não vieram de você.\n"
        f"  Rode direto:  /{target} <seus argumentos>\n"
        "  Ele já cuida sozinho de parar e retomar; não precisa do session "
        "em volta.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
