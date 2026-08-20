#!/usr/bin/env python3
"""UserPromptSubmit hook: recusa na largada uma rotina CONVERSACIONAL passada
para /common:session.

O /common:session tem uma regra que ele mesmo chama de "a regra que rege este
comando": entre a largada e o relatório, não se pergunta nada. Ele ativa a skill
default-yes e, no passo 3, lê o arquivo do comando-alvo para ANTECIPAR numa
rodada só de no máximo quatro perguntas tudo que aquele comando perguntaria
depois. Isso funciona para /board-flow:prove-drain, cujas perguntas são
conhecíveis de antemão (quantos cards, o que fazer com quem trava).

Não funciona para /common:spec, que conduz um interrogatório: ali as próximas
perguntas dependem do que o dono respondeu na anterior — ninguém pergunta sobre
migração de dado antes de saber qual é a fronteira do escopo. E a skill
guided-interrogation SUSPENDE a default-yes que o session acabou de ativar. Um
manda ativar, o outro manda suspender, na mesma sessão; qual vence é sorte.

O que aconteceria sem este gate: o session espreme quatro perguntas genéricas na
largada, entra no passo 4 ("execução — sem interrupções") e o resto da
especificação é ADIVINHADO. Sai um docs/spec/<slug>.md bem formatado, com
Superfície e Teste vermelho em todo critério, passando no spec-readiness-gate —
porque aquele gate confere se os campos existem, não se as respostas vieram do
dono. É o modo de falha que o gate existe para impedir, entrando pela porta que
ele não vigia, e a sessão termina dizendo "concluído".

Mecanismo:
  - Fira em UserPromptSubmit; sai na hora se o prompt não começa com
    /common:session (o custo do scan só é pago nessa raríssima ocasião).
  - Resolve o primeiro token para o comando real, com os mesmos apelidos do
    session.md; um nome com ":" é usado literalmente.
  - Acha o arquivo do comando na fonte instalada (ou no repo), confere que o
    plugin dono bate com o prefixo pedido — `capture.md` existe em board-flow E
    em discovery, e `docs` mora no diretório `docs-topology/` — e lê o campo
    `interaction:` do frontmatter.
  - `interaction: conversational` → bloqueia dizendo para rodar direto.
  - Qualquer coisa inesperada (comando não encontrado, frontmatter ilegível,
    raiz desconhecida) → LIBERA. Este gate afirma um fato positivo sobre um
    arquivo; na dúvida ele não sabe, e não saber não é motivo para barrar.

Exit codes:
  0 — liberado
  2 — bloqueado (o stderr chega ao agente, que explica ao dono)
"""

import json
import os
import re
import sys
from pathlib import Path

# Os apelidos que o passo 1 do session.md mapeia para comandos reais.
APELIDOS = {
    "prove-drain": "board-flow:prove-drain",
    "drain": "board-flow:drain",
    "triage": "board-flow:triage",
    "decide": "board-flow:decide",
    "execute": "board-flow:execute",
    "autonomous": "common:autonomous-start",
    "docs": "docs:survey",
}

INVOCACAO_RE = re.compile(r"^\s*/common:session\s+(\S+)", re.IGNORECASE)

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
INTERACTION_RE = re.compile(
    r"^interaction\s*:\s*[\"']?([A-Za-z-]+)[\"']?\s*$", re.MULTILINE
)


def bases():
    """Diretórios onde procurar os plugins, no repo e no cache instalado.

    No repo,  CLAUDE_PLUGIN_ROOT = <repo>/common          → irmãos em <repo>/
    No cache, CLAUDE_PLUGIN_ROOT = <cache>/cepa/common/1.5.0 → irmãos dois
    níveis acima, cada um com o seu próprio diretório de versão.
    """
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return []
    p = Path(root)
    return [d for d in (p.parent, p.parent.parent) if d and d.is_dir()]


def nome_do_plugin(cmd_file: Path):
    """O nome declarado no manifest do plugin dono deste arquivo de comando.

    Vem do manifest e não do diretório de propósito: o plugin `docs` mora em
    `docs-topology/`, e casar pelo diretório erraria.
    """
    for pai in cmd_file.parents:
        mf = pai / ".claude-plugin" / "plugin.json"
        if mf.is_file():
            try:
                return json.loads(mf.read_text(encoding="utf-8")).get("name")
            except Exception:  # noqa: BLE001
                return None
    return None


def acha_comando(plugin: str, cmd: str):
    for base in bases():
        for padrao in (f"{plugin}*/commands/{cmd}.md",
                       f"{plugin}*/*/commands/{cmd}.md",
                       f"*/commands/{cmd}.md",
                       f"*/*/commands/{cmd}.md"):
            for cand in sorted(base.glob(padrao)):
                if nome_do_plugin(cand) == plugin:
                    return cand
    return None


def interaction(cmd_file: Path):
    try:
        texto = cmd_file.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None
    m = FRONTMATTER_RE.match(texto)
    if not m:
        return None
    achado = INTERACTION_RE.search(m.group(1))
    return achado.group(1).lower() if achado else None


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.exit(0)

    prompt = payload.get("prompt") or ""
    m = INVOCACAO_RE.match(prompt)
    if not m:
        sys.exit(0)          # o custo do scan só é pago aqui

    token = m.group(1).lstrip("/")
    alvo = token if ":" in token else APELIDOS.get(token)
    if not alvo or ":" not in alvo:
        sys.exit(0)          # rotina desconhecida é problema do session, não deste gate

    plugin, _, cmd = alvo.partition(":")
    cmd_file = acha_comando(plugin, cmd)
    if cmd_file is None:
        sys.exit(0)          # não achou o arquivo: não sabe, não barra

    if interaction(cmd_file) != "conversational":
        sys.exit(0)

    print(
        f"[session-routine-guard] BLOQUEADO: /{alvo} conversa com você, e "
        "/common:session foi feito para não conversar.\n"
        "  A regra que rege o /common:session é 'entre a largada e o relatório, "
        "você não pergunta nada': ele ativa a skill default-yes e, no passo 3, "
        f"antecipa numa rodada só tudo que /{alvo} perguntaria depois.\n"
        f"  /{alvo} não é antecipável: cada resposta sua decide quais são as "
        "próximas perguntas. Espremido numa rodada, o resto seria ADIVINHADO — "
        "e o resultado sai bem formatado, passa nos gates, e ninguém percebe "
        "que as respostas não vieram de você.\n"
        f"  Rode direto:  /{alvo} <seus argumentos>\n"
        "  Ele já cuida sozinho de parar e retomar; não precisa do session "
        "em volta.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
