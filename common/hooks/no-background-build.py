#!/usr/bin/env python3
"""PreToolUse hook (common) — dentro do `cepa-until`, jogar build para segundo
plano é perder o item. Bloqueia.

WHY THIS EXISTS
---------------
O `cepa-until` roda cada item da fila como um `claude -p` separado. Nesse modo
**não existe turno seguinte**: o processo morre quando o turno acaba. Um build
disparado em segundo plano nunca é colhido — vira processo órfão, o item fica
`in_progress` sem desfecho e a próxima janela o encontra como reserva órfã e
recomeça do zero.

Medido no run de 2026-08-30 (`WEGO`, janela de 2h):

| tentativa | item      | gasto  | exit | como acabou                                   |
|-----------|-----------|--------|------|-----------------------------------------------|
| 1         | WEGO-2206 | 10m50s |    0 | "aguardo a notificação do `clean verify`"      |
| 3         | WEGO-1941 | 23m46s |    0 | "está compilando em segundo plano... quando    |
|           |           |        |      |  ficar verde: push, `finish`, transição"       |

34 dos 49 minutos da janela, e as duas ÚNICAS falhas que não foram teto de uso
da conta. As duas saíram 0: do lado de fora é indistinguível de trabalho feito.

E o agente não estava sendo criativo — estava seguindo conselho da casa. O
`no-busy-wait` bloqueia esperar, e a saída dele sugere `run_in_background` como
alternativa. Isso vale numa sessão interativa, onde a notificação de término
REINVOCA a sessão. Sob `claude -p` não vale, e é justamente onde o `cepa-until`
roda. Este hook fecha essa porta só onde ela é armadilha.

ESCOPO — só dispara com `CEPA_UNTIL_RUN` no ambiente, que o `cepa-until`
exporta para cada subprocesso. Fora dele o hook não existe: numa sessão
interativa mandar o build para o segundo plano é a coisa certa.

Bloqueia um comando de BUILD/TESTE que vá para segundo plano, pelas duas vias:
  1. `run_in_background: true` no próprio Bash;
  2. desanexação no shell (`&` final, `nohup`, `disown`, `setsid`), fora de
     aspas — porque barrar só o nome da ferramenta faz nascer o próximo
     mecanismo para o mesmo efeito (memória `gate-por-nome-de-ferramenta-falha-
     aberto`).

NÃO bloqueia subir servidor/serviço em segundo plano (`quarkus:dev`, `npm run
dev`, `serve`, `docker compose up`): esses são processos de apoio que PRECISAM
ficar de lado, e o gate de prova de UI depende deles. O que este hook cobra é o
comando que produz um VEREDITO que alguém tem de colher.

ESCAPE HATCH: `# fundo-ok` no comando.

Exit codes:
  0 — liberado
  2 — bloqueado: build em segundo plano dentro de uma janela do cepa-until
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


_ESCAPE = "fundo-ok"
ENV_JANELA = "CEPA_UNTIL_RUN"

# Comandos que produzem um VEREDITO — alguém tem de ler o resultado, e é
# exatamente esse alguém que não existe no turno seguinte.
_BUILD = re.compile(
    r"\b(?:\./)?mvnw?\b(?!.*\b(?:quarkus:dev|spring-boot:run)\b)"
    r"|\bgradlew?\b(?!.*\bbootRun\b)"
    r"|\bnpm\s+(?:run\s+)?(?:test|build|ci)\b"
    r"|\b(?:pnpm|yarn)\s+(?:run\s+)?(?:test|build)\b"
    r"|\bpytest\b|\bpython3?\s+-m\s+pytest\b"
    r"|\bcargo\s+(?:test|build)\b"
    r"|\bgo\s+(?:test|build)\b"
    r"|\bmake\s+(?:test|check|build|verify)\b"
    r"|\bctest\b|\btox\b",
    re.I)

# Desanexação escrita no shell. O `&` só conta quando não é `&&` nem `2>&1`.
_DESANEXA = re.compile(r"\bnohup\b|\bdisown\b|\bsetsid\b|(?<![&>])&\s*(?:$|[;\n])")


def desanexa(command: str, background: bool):
    """(via, trecho) de como o comando vai para segundo plano, ou None."""
    if background:
        return ("run_in_background", command.strip()[:90])
    v = _unquoted_view(command)
    m = _DESANEXA.search(v)
    if m:
        return ("desanexado no shell", v[max(0, m.start() - 60):m.end()].strip())
    return None


def bloqueia(command: str, background: bool, ambiente=None):
    """A decisão completa: (via, trecho) ou None.

    O ambiente entra por parâmetro para o teste conseguir exercer as duas
    metades — dentro e fora da janela — sem mexer no processo dele.
    """
    env = os.environ if ambiente is None else ambiente
    if not env.get(ENV_JANELA):
        return None
    if not command or _ESCAPE in command:
        return None
    if not _BUILD.search(_unquoted_view(command)):
        return None
    return desanexa(command, background)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[no-background-build] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    entrada = payload.get("tool_input") or {}
    achado = bloqueia(entrada.get("command", "") or "",
                      bool(entrada.get("run_in_background")))
    if not achado:
        sys.exit(0)

    via, trecho = achado
    T.emit("background_build_block", reason=via)
    print(
        f"[no-background-build] BLOQUEADO: build em segundo plano ({via}).\n"
        f"  Trecho: {trecho}\n\n"
        "  Você está dentro de uma janela do `cepa-until`: este processo é um\n"
        "  `claude -p` e NÃO HÁ TURNO SEGUINTE. O turno acaba, o processo morre,\n"
        "  o build vira órfão e o item fica `in_progress` sem desfecho — a\n"
        "  próxima janela o encontra como reserva órfã e recomeça do zero.\n"
        "  Foi assim que 34 dos 49 minutos do run de 2026-08-30 foram perdidos.\n\n"
        "  Faça uma destas, na ordem:\n"
        "    1. Rode o build em PRIMEIRO PLANO e colha o resultado agora. Build\n"
        "       em primeiro plano não é espera ativa: o `no-busy-wait` não o\n"
        "       bloqueia, ele barra laço com `sleep`.\n"
        "    2. Se o build não cabe no turno, NOMEIE O DESFECHO antes de parar:\n"
        "       `cepa-plan finish <fila> <id> --status blocked --evidence`\n"
        "       \"build disparado e não colhido: <comando>, log em <caminho>\".\n"
        "       Um item com desfecho volta sabendo onde parou.\n"
        "    3. Se o comando NÃO produz veredito (subir servidor, serviço de\n"
        "       apoio), acrescente `# fundo-ok`.\n\n"
        "  A opção 3 é uma afirmação sua de que ninguém precisa ler a saída.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
