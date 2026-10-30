#!/usr/bin/env python3
"""PreToolUse hook (common): busy-waiting in Bash is the harness's biggest
wall-clock cost. Blocks it.

WHY THIS EXISTS
---------------
Measurement of 2026-08-26 over the transcripts recorded in ~/.claude/projects/:

| run                          | clock   | busy wait    | where                   |
|------------------------------|---------|--------------|-------------------------|
| session/drain-plan-0840      |  299min |  155min (52%)| engineering-lead 149min |
| session/exec-17081128        |  636min |  146min (23%)| engineering-lead 114min |
| session/todo-21081818        |  924min |  194min (21%)| engineering-lead 190min |
| session/todo-1413            | 1098min |  241min (22%)| engineering-lead 232min |
| session/todo-22081827        |  913min |  176min (19%)| engineering-lead 161min |

In the same runs, the Maven build, which everyone assumed to be the bottleneck,
stayed between 3% and 17%. Runs that do not use a lead (pure prove-drain) have
ZERO waiting, which pins down the defect: it is the lead that waits, not the
topology.

The pattern, verbatim from the drain-plan-0840 transcript:

    until grep -q "CredenciaisDoFuncionarioE2ETest" .claude/last-build.json; do sleep 20; done   601s
    until ls bootstrap/src/test/java/.../ | grep -q "Credenciais"; do sleep 10; done             543s
    until [ -f api-rest/.../CredencialHabilitadaResponse.java ]; do sleep 10; done               421s
    until [ -f /dev/null ]; do sleep 5; done; echo aguardando                                    120s
    for i in $(seq 1 6000); do git log --all --stat >/dev/null 2>&1; done; date                  590s  (x2)

Two distinct pathologies, both expensive:

1. **Probing the disk waiting for the worker.** The lead delegates and then
   watches the file appear, in blocks of 5 to 10 minutes. The root is that the
   `Agent` call is asynchronous (it returns `Async agent launched successfully`,
   not the result) and the leads' specs are SILENT about that: none of the 10
   mentions asynchrony, notification or end of turn, and all describe delegate
   -> read the result -> synthesize as a continuous flow. Without a step saying
   "your turn ends here", the lead fills the silence with probing. (What is
   verified is the silence and the continuous flow; what the original author
   believed cannot be known.) The fix for the cause is in the "Delegation is
   asynchronous" section of the 10 specs that delegate; this hook is the net.
   `until [ -f /dev/null ]` is the extreme case: waiting for a condition that
   was already true, that is, the agent no longer knew what it was waiting for.
2. **Burn loop as an improvised `sleep`.** A foreground `sleep` is blocked by
   the harness; the agent works around it with a loop that runs `git log` six
   thousand times. It spends CPU to do nothing. That is the pattern the memory
   `gate-por-nome-de-ferramenta-falha-aberto` describes: blocking one MECHANISM
   gives birth to the next. That is why this hook blocks the EFFECT (holding
   the session without work) and not a list of commands.

SCOPE: blocks when the command, outside quotes, has any of these:
  1. a loop (`until`/`while`/`for`) whose body calls `sleep` (the probing;
     includes `for i in $(seq 1 60); do ...; sleep 10; done`, which is the same
     thing written with a counter instead of a condition);
  2. `sleep N` with N >= 30 (the long wait without a loop);
  3. a repetition loop without real work: `while true`, or `for ... $(seq 1 N)`
     with N >= 200 (the burn).

What does NOT block: a short `sleep 2`, a small loop, `until` without `sleep`
(which ends on its own), and any command whose `until`/`sleep` is inside quotes:
quoted text is not shell (WEGO-2087).

ESCAPE HATCH: `# espera-ok` in the command. It exists for the real case of
probing EXTERNAL state the harness does not notify (a remote pipeline, a
third-party queue). Using it by reflex, to get rid of the block, returns
exactly the 150 minutes this guard exists to cut.

Exit codes:
  0 - allowed
  2 - blocked: busy wait
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _telemetry as T
except Exception:  # telemetry must never break the gate

    class T:  # type: ignore
        @staticmethod
        def emit(*a, **k):
            pass


try:
    import _shellscan as S

    _unquoted_view = S._unquoted_view
except Exception:  # without the shared engine, analyzes the raw line

    def _unquoted_view(c):
        return c


_ESCAPE = "espera-ok"

# `sleep` with a number (or variable) inside a loop body
_SLEEP = re.compile(r"\bsleep\s+[\d.$]")
_LOOP = re.compile(r"\b(until|while|for)\b")
_WHILE_TRUE = re.compile(r"\bwhile\s+(true|:)\b")
_SEQ = re.compile(r"\bseq\s+1\s+(\d+)")
_SLEEP_LONG = re.compile(r"\bsleep\s+(\d+(?:\.\d+)?)")

SEQ_CEILING = 200
SLEEP_CEILING = 30


def reason_for(command: str):
    """Returns (label, excerpt) of the first busy-wait pattern, or None."""
    v = _unquoted_view(command)

    if _LOOP.search(v) and _SLEEP.search(v):
        m = _LOOP.search(v)
        return ("sondagem", v[m.start() : m.start() + 90].strip())

    if _WHILE_TRUE.search(v):
        m = _WHILE_TRUE.search(v)
        return ("laço infinito", v[m.start() : m.start() + 90].strip())

    m = _SEQ.search(v)
    if m and int(m.group(1)) >= SEQ_CEILING:
        return ("laço de queima", v[max(0, m.start() - 20) : m.start() + 90].strip())

    for m in _SLEEP_LONG.finditer(v):
        if float(m.group(1)) >= SLEEP_CEILING:
            return ("espera longa", v[max(0, m.start() - 30) : m.end() + 20].strip())

    return None


def blocks(command: str):
    """The complete decision about a command: (label, excerpt) or None.

    Separate from `reason_for` because the escape hatch is part of the decision,
    and a test that only exercised `reason_for` would pass a hook that ignores
    `espera-ok`.
    """
    if not command or _ESCAPE in command:
        return None
    return reason_for(command)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[no-busy-wait] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "") or ""
    hit = blocks(command)
    if not hit:
        sys.exit(0)

    label, excerpt = hit
    T.emit("busy_wait_block", reason=label)
    print(
        f"[no-busy-wait] BLOQUEADO: espera ativa ({label}).\n"
        f"  Trecho: {excerpt}\n\n"
        "  Um comando que fica bloqueado sem trabalhar é o maior custo de relógio\n"
        "  medido neste harness: 19% a 52% do tempo de 5 runs, quase tudo em lead\n"
        "  sondando arquivo de worker (medição de 2026-08-26).\n\n"
        "  Faça uma destas, na ordem:\n"
        "    1. Se você está esperando um agente que VOCÊ delegou — ENCERRE O TURNO.\n"
        "       A chamada `Agent` é assíncrona: ela devolve `Async agent launched\n"
        "       successfully`, não o resultado. O subagente roda em segundo plano e\n"
        "       a notificação de término REINVOCA você com o resultado na mão. Não\n"
        "       há nada para fazer no meio, e sondar o disco não antecipa nada.\n"
        "       EXCEÇÃO: dentro de uma janela do `cepa-until` (CEPA_UNTIL_RUN no\n"
        "       ambiente) ou de run autônomo (CLAUDE_AUTONOMOUS_RUN_ID), você é\n"
        "       subagente do orquestrador e encerrar o turno DEVOLVE o item pela\n"
        "       metade. Lá, delegue com `run_in_background: false` e receba o\n"
        "       resultado no mesmo turno.\n"
        "    2. Se o trabalho é longo e você quer seguir enquanto ele roda, use\n"
        "       `run_in_background` no Bash: a sessão é reinvocada quando terminar.\n"
        "       EXCEÇÃO: dentro de uma janela do `cepa-until` (a variável\n"
        "       CEPA_UNTIL_RUN no ambiente) isso NÃO vale — cada item é um\n"
        "       `claude -p` e não há turno seguinte para colher o resultado.\n"
        "       Lá, build roda em primeiro plano; quem cobra é o\n"
        "       `no-background-build`.\n"
        "    3. Se você precisa aguardar uma CONDIÇÃO, use a ferramenta `Monitor`\n"
        "       em vez de laço com sleep.\n"
        "    4. Se é mesmo estado externo que ninguém notifica (pipeline remoto,\n"
        "       fila de terceiro), acrescente `# espera-ok` ao comando.\n\n"
        "  A opção 4 é uma afirmação sua de que não existe notificação para isso.\n"
        "  Usá-la por reflexo devolve os 150 minutos por run que este guard corta.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
