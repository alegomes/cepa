#!/usr/bin/env python3
"""UserPromptSubmit: ativa a skill default-yes quando o prompt dispara um
comando de ROTINA, e a mantém ativa run adentro.

## O modo de falha que este hook existe para matar

A skill `default-yes` (common/skills/default-yes/SKILL.md) diz o que fazer com
uma recomendação: se a ação é reversível ou só registra alguma coisa, execute e
preste contas no relatório; pergunte só o irreversível, e em lote nas pontas.
Ela foi escrita a pedido do dono do harness em 18/08/2026.

Só que uma skill não se ativa sozinha — ela entra em cena quando o comando que
está rodando manda ativá-la. E em 22/08/2026 a contagem era esta: de 56
comandos do repo, 6 citavam a skill (`triage`, `execute`, `drain`,
`prove-drain`, `doctor`, `session`). Os outros 50, não.

O efeito prático não era 50 comandos ligeiramente mais tagarelas. Era isto:
`/board-flow:drain` cita a skill, mas por card ele chama
`/board-flow:execute`, que despacha para `plan-build-validate` ou
`reproduce-fix-verify` da topologia, que por sua vez chamam `prove` e
`advance` — e nenhum desses quatro citava a skill. A política valia na casca do
run e evaporava assim que ele entrava num card. Ou seja: valia exatamente onde
uma pergunta seria barata (a largada) e sumia exatamente onde ela é cara (o
meio do drain, quando responder custa recarregar o contexto inteiro).

## Mecanismo

  - Fira em UserPromptSubmit. Sai na hora se o prompt não começa com um comando
    `<plugin>:<cmd>` — o custo do scan só é pago nessa ocasião.
  - Resolve o arquivo do comando e lê o campo `interaction:` do frontmatter,
    pelo helper `_cmdmeta.py` (compartilhado com o session-routine-guard, que
    lê o mesmo campo para a decisão oposta).
  - `routine`         → injeta a política como contexto do turno.
  - `conversational`  → NÃO injeta nada. É o caso do /common:spec, onde a skill
    guided-interrogation suspende a default-yes de propósito: na construção
    adivinhar economiza turno, na especificação produz uma spec plausível e
    errada. Injetar aqui seria reabrir a contradição que o session-routine-guard
    fecha.
  - Campo ausente, arquivo não encontrado, qualquer imprevisto → não injeta
    nada. Este hook concede autonomia; na dúvida ele não concede.

## Por que injetar em vez de editar os 50 arquivos

O texto injetado vale para o TURNO, o que inclui os comandos e subagentes que o
comando de largada invocar — que é justamente onde escrever nos arquivos não
alcançaria sem editar cada um deles e todos os futuros. Os quatro comandos
internos do caminho do drain ganharam a menção por escrito também, como rede: o
hook cobre quem não tem, e o texto cobre o caso de o hook não estar instalado.

Este hook nunca bloqueia: só exit 0, com ou sem contexto.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _cmdmeta import ROUTINE, acha_comando, interaction
except Exception:  # noqa: BLE001 — sem o helper não há o que injetar
    ROUTINE = acha_comando = interaction = None

# O primeiro token do prompt, quando ele é uma invocação de comando de plugin.
COMANDO_RE = re.compile(r"^\s*/([A-Za-z0-9_-]+:[A-Za-z0-9_-]+)")

# O /common:session recebe a rotina-alvo como primeiro argumento. Quem manda na
# política do run é o ALVO, não o invólucro.
ALVO_DO_SESSION_RE = re.compile(
    r"^\s*/common:session\s+/?(\S+)", re.IGNORECASE
)
APELIDOS = {
    "prove-drain": "board-flow:prove-drain",
    "drain": "board-flow:drain",
    "triage": "board-flow:triage",
    "decide": "board-flow:decide",
    "execute": "board-flow:execute",
    "autonomous": "common:autonomous-start",
    "docs": "docs:survey",
}

POLITICA = (
    "[default-yes] /{alvo} é um comando de rotina: a skill `default-yes` está "
    "ATIVA neste turno, e vale para o run inteiro — inclusive para os comandos "
    "e subagentes que ele invocar (é aí que ela sumia). "
    "Ação reversível, que só registra algo, ou de investigação, e você já tem "
    "recomendação: EXECUTE e preste contas no relatório final; não pergunte. "
    "Pergunta só sobrevive para o irreversível (apagar trabalho, Won't Do, "
    "force-push, publicar para fora), para custo real (rodar N provas caras) e "
    "para bifurcação de preferência sem default defensável — e vai para uma "
    "das pontas: na largada, se a resposta muda o plano inteiro, ou no "
    "relatório final, em lista numerada com `Recomendo sim/não`. "
    "Nunca no meio da execução. "
    "Toda decisão que você tomar sozinho é NOMEADA no relatório final — é isso "
    "que torna a autonomia revisável em vez de temerária."
)


def alvo_do(prompt: str):
    """`<plugin>:<cmd>` que rege a política deste turno, ou None."""
    m = ALVO_DO_SESSION_RE.match(prompt)
    if m:
        token = m.group(1)
        alvo = token if ":" in token else APELIDOS.get(token)
        if alvo and ":" in alvo:
            return alvo
        return "common:session"
    m = COMANDO_RE.match(prompt)
    return m.group(1) if m else None


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        if not isinstance(payload, dict) or acha_comando is None:
            sys.exit(0)

        alvo = alvo_do(payload.get("prompt") or "")
        if not alvo:
            sys.exit(0)      # o custo do scan só é pago numa invocação

        plugin, _, cmd = alvo.partition(":")
        cmd_file = acha_comando(plugin, cmd)
        if cmd_file is None or interaction(cmd_file) != ROUTINE:
            sys.exit(0)      # não sabe, ou é conversa: não concede autonomia

        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": POLITICA.format(alvo=alvo),
        }}))
    except Exception as e:  # noqa: BLE001
        print(f"[default-yes-inject] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
