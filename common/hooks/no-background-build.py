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

AS OUTRAS DUAS PORTAS PARA O MESMO EFEITO (04/09/2026)
-------------------------------------------------------
O run de 2026-09-03 perdeu 6h54 de uma janela de 8h sem passar por nenhuma
delas: o item WEGO-2224 armou um `Monitor` com `while true` (um vigia que
observa branches e NUNCA termina sozinho) e encerrou o turno escrevendo
"Aguardo", com subagentes ainda rodando. O `claude -p` esperou o segundo plano,
bateu o teto de 600s e se matou — exit 0, item pela metade, clone principal
parado numa branch de integração. A conferência de branch do `cepa-until` leu
isso como troca de branch e encerrou a janela inteira.

Barrar só o `Bash` era barrar por MECANISMO. O efeito é `o turno acaba com
trabalho de segundo plano que ninguém vai colher`, e ele tem três portas:

  Bash      — build desanexado (a porta original, acima);
  Monitor   — vigia sem fim: `persistent: true`, `ws:`, ou comando que não
              retorna (`while true`, `tail -f`, `inotifywait -m`). Dentro da
              janela ele só segura o turno até o relógio do item matar tudo.
              Vigia com fim declarado continua liberado: ele termina e é colhido;
  Stop      — a parada em si. Se ficou subagente despachado sem resultado no
              transcript, ou vigia armado sem `TaskStop`, a parada é bloqueada
              uma vez com a lista do que falta colher.

O par com o `cepa-until`: o supervisor agora exporta
`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` para o item esperar o segundo plano em
vez de morrer aos 10 minutos. Isso só é seguro porque estas duas portas novas
barram o segundo plano que nunca termina — sem elas, esperar sem teto trocaria
um corte de 10 min pelo limite do item inteiro.

ESCAPE HATCH: `# fundo-ok` no comando (Bash e Monitor).

Exit codes:
  0 — liberado (e, no Stop, o bloqueio viaja no JSON de stdout)
  2 — bloqueado: trabalho em segundo plano dentro de uma janela do cepa-until
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


# ── porta 2: o vigia que não termina (Monitor) ──────────────────────────────
# Um `Monitor` só é colhível dentro da janela se ele ACABA. Estes são os jeitos
# de escrever um que não acaba — o de cima é o do run de 2026-09-03.
_VIGIA_SEM_FIM = re.compile(
    r"\bwhile\s+(?:true|:)\b"
    r"|\buntil\s+false\b"
    r"|\bfor\s*\(\s*;\s*;\s*\)"
    r"|\btail\s+-[A-Za-z]*f\b"
    r"|\binotifywait\b[^;|]*\s-m\b",
    re.I)


def vigia_bloqueia(entrada, ambiente=None):
    """(via, trecho) se este Monitor não termina sozinho dentro da janela."""
    env = os.environ if ambiente is None else ambiente
    if not env.get(ENV_JANELA):
        return None
    entrada = entrada or {}
    comando = entrada.get("command") or ""
    rotulo = (entrada.get("description") or comando).strip()[:90]
    if _ESCAPE in comando:
        return None
    if entrada.get("persistent"):
        return ("persistent: true", rotulo)
    if entrada.get("ws"):
        # O socket só fecha quando o outro lado fecha: do lado de cá não há fim.
        return ("ws (o socket não fecha sozinho)", rotulo)
    m = _VIGIA_SEM_FIM.search(_unquoted_view(comando))
    if m:
        return ("comando sem fim", comando[max(0, m.start() - 40):m.end() + 20].strip())
    return None


# ── porta 3: a parada com trabalho pendente (Stop) ──────────────────────────
_VIGIA_ARMADO = re.compile(r"Monitor started \(task ([A-Za-z0-9_-]{4,})")
_VIGIA_PARADO = re.compile(r"[Ss]topped task:? ([A-Za-z0-9_-]{4,})")
_DESPACHO = ("Agent", "Task")


def _blocos(linha):
    conteudo = ((linha.get("message") or {}).get("content"))
    return conteudo if isinstance(conteudo, list) else []


def pendencias(transcript_path):
    """(subagentes despachados sem resultado, vigias armados sem parada).

    Lê o transcript porque é a ÚNICA fonte que sabe o que foi despachado: o
    payload do Stop não lista tarefa de segundo plano nenhuma.
    """
    despachados, respondidos, armados, parados = {}, set(), {}, set()
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            for bruta in f:
                bruta = bruta.strip()
                if not bruta:
                    continue
                try:
                    linha = json.loads(bruta)
                except json.JSONDecodeError:
                    continue
                for b in _blocos(linha):
                    tipo = b.get("type")
                    if tipo == "tool_use" and b.get("name") in _DESPACHO:
                        rotulo = (b.get("input") or {}).get("description") or b.get("name")
                        despachados[b.get("id")] = str(rotulo)[:80]
                    elif tipo == "tool_result":
                        alvo = b.get("tool_use_id")
                        if alvo:
                            respondidos.add(alvo)
                        texto = b.get("content")
                        if not isinstance(texto, str):
                            texto = json.dumps(texto, ensure_ascii=False)
                        for m in _VIGIA_ARMADO.finditer(texto):
                            armados[m.group(1)] = m.group(1)
                        for m in _VIGIA_PARADO.finditer(texto):
                            parados.add(m.group(1))
    except OSError:
        return [], []
    subagentes = [r for i, r in despachados.items() if i not in respondidos]
    vigias = [v for v in armados if v not in parados]
    return subagentes, vigias


def motivo_da_parada(payload, ambiente=None):
    """O texto do bloqueio da parada, ou None se não há o que colher."""
    env = os.environ if ambiente is None else ambiente
    if not env.get(ENV_JANELA):
        return None
    # Anti-loop: se esta parada JÁ veio de um bloqueio, não bloqueia de novo.
    # Uma chance de colher é o aperto; prender a sessão seria trocar um item
    # perdido por uma janela travada.
    if payload.get("stop_hook_active"):
        return None
    caminho = payload.get("transcript_path")
    if not caminho:
        return None
    subagentes, vigias = pendencias(caminho)
    if not subagentes and not vigias:
        return None
    partes = []
    if subagentes:
        partes.append("subagente(s) despachado(s) e sem resultado no "
                      "transcript: " + ", ".join(subagentes[:5]))
    if vigias:
        partes.append("vigia(s) do Monitor ainda armado(s): " + ", ".join(vigias[:5]))
    return (
        "[no-background-build] Você está numa janela do `cepa-until` e NÃO HÁ "
        "TURNO SEGUINTE: parar agora mata o processo com trabalho por colher.\n"
        + "".join(f"  - {p}\n" for p in partes) +
        "\n  Faça uma destas, na ordem:\n"
        "    1. Colha agora: espere o resultado do subagente e siga o item até "
        "o fim neste turno.\n"
        "    2. Se um vigia já cumpriu o papel, encerre-o com `TaskStop` antes "
        "de parar.\n"
        "    3. Se o item não cabe no turno, NOMEIE O DESFECHO antes de parar: "
        "`cepa-plan finish <fila> <id> --status blocked --evidence \"...\"`, e "
        "deixe o clone na branch da largada — foi a branch parada numa "
        "integração que encerrou a janela de 2026-09-03 com 6h54 de sobra.")


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[no-background-build] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if (payload.get("hook_event_name") or "") == "Stop":
        try:
            motivo = motivo_da_parada(payload)
        except Exception:
            motivo = None  # o gate nunca derruba o turno por erro próprio
        if motivo:
            T.emit("background_pending_stop_block")
            print(json.dumps({"decision": "block", "reason": motivo},
                             ensure_ascii=False))
        sys.exit(0)

    ferramenta = payload.get("tool_name")
    entrada = payload.get("tool_input") or {}

    if ferramenta == "Monitor":
        achado = vigia_bloqueia(entrada)
        if not achado:
            sys.exit(0)
        via, trecho = achado
        T.emit("background_monitor_block", reason=via)
        print(
            f"[no-background-build] BLOQUEADO: vigia sem fim ({via}).\n"
            f"  Trecho: {trecho}\n\n"
            "  Você está dentro de uma janela do `cepa-until`: este processo é\n"
            "  um `claude -p` e NÃO HÁ TURNO SEGUINTE. Um vigia que não termina\n"
            "  sozinho segura o turno até o relógio do item matar tudo — foi\n"
            "  assim que o WEGO-2224 morreu pela metade em 2026-09-03, e a\n"
            "  branch em que ele parou encerrou a janela com 6h54 de sobra.\n\n"
            "  Faça uma destas, na ordem:\n"
            "    1. Colha em PRIMEIRO PLANO: espere o resultado agora, no turno.\n"
            "    2. Se precisa mesmo de um vigia, escreva um que TERMINE — laço\n"
            "       que sai no primeiro estado terminal (`break`), sem\n"
            "       `persistent: true`.\n"
            "    3. Se o comando não produz veredito para ninguém colher,\n"
            "       acrescente `# fundo-ok`.",
            file=sys.stderr,
        )
        sys.exit(2)

    if ferramenta != "Bash":
        sys.exit(0)

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
