#!/usr/bin/env python3
"""UserPromptSubmit: activates the default-yes skill when the prompt triggers a
ROUTINE command, and keeps it active throughout the run.

## The failure mode this hook exists to kill

The `default-yes` skill (common/skills/default-yes/SKILL.md) says what to do
with a recommendation: if the action is reversible or merely records something,
execute it and account for it in the report; ask only about the irreversible,
and in batches at the ends. It was written at the request of the harness owner
on 2026-08-18.

But a skill does not activate itself; it enters the scene when the running
command orders it activated. And on 2026-08-22 the count was this: of 56 repo
commands, 6 cited the skill (`triage`, `execute`, `drain`, `prove-drain`,
`doctor`, `session`). The other 50 did not.

The practical effect was not 50 slightly chattier commands. It was this:
`/board-flow:drain` cites the skill, but per card it calls
`/board-flow:execute`, which dispatches to the topology's `plan-build-validate`
or `reproduce-fix-verify`, which in turn call `prove` and `advance`, and none of
those four cited the skill. The policy held in the shell of the run and
evaporated as soon as it entered a card. That is: it held exactly where a
question would be cheap (the start) and vanished exactly where it is expensive
(the middle of the drain, when answering costs reloading the whole context).

## Mechanism

  - Fires on UserPromptSubmit. Exits at once if the prompt does not start with a
    `<plugin>:<cmd>` command; the scan cost is only paid on that occasion.
  - Resolves the command file and reads the frontmatter `interaction:` field,
    through the `_cmdmeta.py` helper (shared with session-routine-guard, which
    reads the same field for the opposite decision).
  - `routine`         -> injects the policy as turn context.
  - `conversational`  -> injects NOTHING. This is the case of /common:spec,
    where the guided-interrogation skill suspends default-yes on purpose: in
    construction guessing saves a turn, in specification it produces a
    plausible and wrong spec. Injecting here would reopen the contradiction that
    session-routine-guard closes.
  - Field missing, file not found, any surprise -> injects nothing. This hook
    grants autonomy; when in doubt it does not grant.

## Why inject instead of editing the 50 files

The injected text holds for the TURN, which includes the commands and subagents
the launching command invokes, which is precisely where writing into the files
would not reach without editing each one of them and every future one. The four
internal commands on the drain path also got the mention in writing, as a net:
the hook covers those without it, and the text covers the case of the hook not
being installed.

This hook never blocks: only exit 0, with or without context.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _cmdmeta import ROUTINE, find_command, interaction
except Exception:  # noqa: BLE001 — without the helper there is nothing to inject
    ROUTINE = find_command = interaction = None

# The first token of the prompt, when it is a plugin command invocation.
COMMAND_RE = re.compile(r"^\s*/([A-Za-z0-9_-]+:[A-Za-z0-9_-]+)")

# /common:session receives the target routine as its first argument. What
# governs the run's policy is the TARGET, not the wrapper.
SESSION_TARGET_RE = re.compile(
    r"^\s*/common:session\s+/?(\S+)", re.IGNORECASE
)
ALIASES = {
    "prove-drain": "board-flow:prove-drain",
    "drain": "board-flow:drain",
    "drain-plan": "common:drain-plan",
    "triage": "board-flow:triage",
    "decide": "board-flow:decide",
    "execute": "board-flow:execute",
    "autonomous": "common:autonomous-start",
    "docs": "docs:survey",
}

POLICY = (
    "[default-yes] /{target} é um comando de rotina: a skill `default-yes` está "
    "ATIVA neste turno, e vale para o run inteiro — inclusive para os comandos "
    "e subagentes que ele invocar (é aí que ela sumia). "
    "Ação reversível, que só registra algo, ou de investigação, e você já tem "
    "recomendação: EXECUTE e preste contas no relatório final; não pergunte. "
    "Pergunta só sobrevive para o irreversível (apagar trabalho, Won't Do, "
    "force-push, publicar para fora), para custo real (rodar N provas caras) e "
    "para bifurcação de preferência sem default defensável — e vai para uma "
    "das pontas: na largada, se a resposta muda o plano inteiro, ou no "
    "relatório final, em lista numerada com `I recommend yes/no`. "
    "Nunca no meio da execução. "
    "Toda decisão que você tomar sozinho é NOMEADA no relatório final — é isso "
    "que torna a autonomia revisável em vez de temerária."
)


def target_of(prompt: str):
    """The `<plugin>:<cmd>` that governs this turn's policy, or None."""
    m = SESSION_TARGET_RE.match(prompt)
    if m:
        token = m.group(1)
        target = token if ":" in token else ALIASES.get(token)
        if target and ":" in target:
            return target
        return "common:session"
    m = COMMAND_RE.match(prompt)
    return m.group(1) if m else None


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict) or find_command is None:
            sys.exit(0)

        target = target_of(payload.get("prompt") or "")
        if not target:
            sys.exit(0)      # the scan cost is only paid on an invocation

        plugin, _, cmd = target.partition(":")
        cmd_file = find_command(plugin, cmd)
        if cmd_file is None or interaction(cmd_file) != ROUTINE:
            sys.exit(0)      # unknown, or conversational: grants no autonomy

        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": POLICY.format(target=target),
        }}))
    except Exception as e:  # noqa: BLE001
        print(f"[default-yes-inject] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
