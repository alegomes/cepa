#!/usr/bin/env python3
"""PreToolUse hook (common) — espera ativa no Bash é o maior custo de relógio do
harness. Bloqueia.

WHY THIS EXISTS
---------------
Medição de 2026-08-26 sobre os transcripts gravados em ~/.claude/projects/:

| run                          | relógio | espera ativa | onde                    |
|------------------------------|---------|--------------|-------------------------|
| session/drain-plan-0840      |  299min |  155min (52%)| engineering-lead 149min |
| session/exec-17081128        |  636min |  146min (23%)| engineering-lead 114min |
| session/todo-21081818        |  924min |  194min (21%)| engineering-lead 190min |
| session/todo-1413            | 1098min |  241min (22%)| engineering-lead 232min |
| session/todo-22081827        |  913min |  176min (19%)| engineering-lead 161min |

Nos mesmos runs, o build Maven — que todo mundo supunha ser o gargalo — ficou
entre 3% e 17%. Runs que não usam lead (prove-drain puro) têm espera ZERO, o que
localiza o defeito: é o lead que espera, não a topologia.

O padrão, verbatim do transcript do drain-plan-0840:

    until grep -q "CredenciaisDoFuncionarioE2ETest" .claude/last-build.json; do sleep 20; done   601s
    until ls bootstrap/src/test/java/.../ | grep -q "Credenciais"; do sleep 10; done             543s
    until [ -f api-rest/.../CredencialHabilitadaResponse.java ]; do sleep 10; done               421s
    until [ -f /dev/null ]; do sleep 5; done; echo aguardando                                    120s
    for i in $(seq 1 6000); do git log --all --stat >/dev/null 2>&1; done; date                  590s  (x2)

Duas patologias distintas, as duas caras:

1. **Sondar o disco esperando o worker.** O lead delega e depois fica olhando o
   arquivo aparecer, em blocos de 5 a 10 minutos. A raiz é que a chamada `Agent`
   é assíncrona — devolve `Async agent launched successfully`, não o resultado —
   e as specs dos leads são SILENCIOSAS sobre isso: nenhuma das 10 menciona
   assincronia, notificação ou fim de turno, e todas descrevem delegar → ler o
   resultado → sintetizar como um fluxo contínuo. Sem um passo dizendo "seu
   turno acaba aqui", o lead preenche o silêncio com sondagem. (O que está
   verificado é o silêncio e o fluxo contínuo; o que o autor original acreditava
   não dá para saber.) O conserto da causa está
   na seção "Delegação é assíncrona" das 10 specs que delegam; este hook é a
   rede. `until [ -f /dev/null ]` é o caso
   extremo: espera por condição que já era verdadeira, ou seja, o agente já não
   sabia o que estava esperando.
2. **Laço de queima como `sleep` improvisado.** `sleep` em primeiro plano é
   bloqueado pelo harness; o agente contorna com um laço que roda `git log` seis
   mil vezes. Gasta CPU para não fazer nada. Isso é o padrão que a memória
   `gate-por-nome-de-ferramenta-falha-aberto` descreve: barrar um MECANISMO faz
   nascer o próximo. Por isso este hook barra o EFEITO — bloquear a sessão sem
   trabalho — e não uma lista de comandos.

ESCOPO — bloqueia quando o comando, fora de aspas, tem qualquer destes:
  1. laço (`until`/`while`/`for`) cujo corpo chama `sleep` (a sondagem —
     inclui `for i in $(seq 1 60); do ...; sleep 10; done`, que é a mesma
     coisa escrita com contador em vez de condição);
  2. `sleep N` com N >= 30 (a espera longa sem laço);
  3. laço de repetição sem trabalho real: `while true`, ou `for ... $(seq 1 N)`
     com N >= 200 (a queima).

O que NÃO bloqueia: `sleep 2` curto, laço pequeno, `until` sem `sleep` (que
termina por conta própria), e qualquer comando cujo `until`/`sleep` esteja
dentro de aspas — texto citado não é shell (WEGO-2087).

ESCAPE HATCH: `# espera-ok` no comando. Existe para o caso real de sondar estado
EXTERNO que o harness não notifica (um pipeline remoto, uma fila de terceiro).
Usar por reflexo, para se livrar do bloqueio, devolve exatamente os 150 minutos
que este guard existe para cortar.

Exit codes:
  0 — liberado
  2 — bloqueado: espera ativa
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import _telemetry as T
except Exception:  # telemetria nunca pode quebrar o gate

    class T:  # type: ignore
        @staticmethod
        def emit(*a, **k):
            pass


try:
    import _shellscan as S

    _unquoted_view = S._unquoted_view
except Exception:  # sem o motor compartilhado, analisa a linha crua

    def _unquoted_view(c):
        return c


_ESCAPE = "espera-ok"

# `sleep` com número (ou variável) dentro de um corpo de laço
_SLEEP = re.compile(r"\bsleep\s+[\d.$]")
_LOOP = re.compile(r"\b(until|while|for)\b")
_WHILE_TRUE = re.compile(r"\bwhile\s+(true|:)\b")
_SEQ = re.compile(r"\bseq\s+1\s+(\d+)")
_SLEEP_LONGO = re.compile(r"\bsleep\s+(\d+(?:\.\d+)?)")

TETO_SEQ = 200
TETO_SLEEP = 30


def motivo(command: str):
    """Devolve (rótulo, trecho) do primeiro padrão de espera ativa, ou None."""
    v = _unquoted_view(command)

    if _LOOP.search(v) and _SLEEP.search(v):
        m = _LOOP.search(v)
        return ("sondagem", v[m.start() : m.start() + 90].strip())

    if _WHILE_TRUE.search(v):
        m = _WHILE_TRUE.search(v)
        return ("laço infinito", v[m.start() : m.start() + 90].strip())

    m = _SEQ.search(v)
    if m and int(m.group(1)) >= TETO_SEQ:
        return ("laço de queima", v[max(0, m.start() - 20) : m.start() + 90].strip())

    for m in _SLEEP_LONGO.finditer(v):
        if float(m.group(1)) >= TETO_SLEEP:
            return ("espera longa", v[max(0, m.start() - 30) : m.end() + 20].strip())

    return None


def bloqueia(command: str):
    """A decisão completa sobre um comando: (rótulo, trecho) ou None.

    Separada de `motivo` porque o escape hatch faz parte da decisão, e um teste
    que só exercitasse `motivo` daria por bom um hook que ignora o `espera-ok`.
    """
    if not command or _ESCAPE in command:
        return None
    return motivo(command)


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
    achado = bloqueia(command)
    if not achado:
        sys.exit(0)

    rotulo, trecho = achado
    T.emit("busy_wait_block", reason=rotulo)
    print(
        f"[no-busy-wait] BLOQUEADO: espera ativa ({rotulo}).\n"
        f"  Trecho: {trecho}\n\n"
        "  Um comando que fica bloqueado sem trabalhar é o maior custo de relógio\n"
        "  medido neste harness: 19% a 52% do tempo de 5 runs, quase tudo em lead\n"
        "  sondando arquivo de worker (medição de 2026-08-26).\n\n"
        "  Faça uma destas, na ordem:\n"
        "    1. Se você está esperando um agente que VOCÊ delegou — ENCERRE O TURNO.\n"
        "       A chamada `Agent` é assíncrona: ela devolve `Async agent launched\n"
        "       successfully`, não o resultado. O subagente roda em segundo plano e\n"
        "       a notificação de término REINVOCA você com o resultado na mão. Não\n"
        "       há nada para fazer no meio, e sondar o disco não antecipa nada.\n"
        "    2. Se o trabalho é longo e você quer seguir enquanto ele roda, use\n"
        "       `run_in_background` no Bash: a sessão é reinvocada quando terminar.\n"
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
