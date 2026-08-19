#!/usr/bin/env python3
"""PreToolUse hook: bloqueia bloco de Decisão cujo campo Altitude não é um dos
três valores do vocabulário.

O `**Altitude:**` de um bloco `### Decision:` não descreve a decisão — ele diz
QUEM revisa: `strategic` vai para o dono no `/common:debrief`, `tactical` fica
com o lead, `implementation` só aparece com `--all`. É o único mecanismo que o
debrief tem para separar o que merece a atenção do dono do que é detalhe.

O que aconteceu em 2026-08-19: quatro runs autônomos produziram 57 blocos de
decisão bem formatados, e 51 deles traziam no campo de altitude uma palavra
livre em português — "contrato", "schema", "fronteira", "retenção", "semântica"
—, 35 valores distintos. O agente respondeu "de que assunto é esta decisão",
que é outra pergunta. Com 89% dos blocos fora do vocabulário, o filtro do
debrief não filtra: o dono revisaria três decisões, todas do primeiro card,
enquanto as de maior consequência ficavam invisíveis por estarem marcadas com
palavra que o filtro não reconhece.

Nada disso aparece como erro. O bloco está lindo, o run termina, o debrief roda
e diz "3 decisões estratégicas". Por isso o gate é mecânico e bloqueia na
escrita, quando o autor ainda está ali para corrigir.

Mecanismo:
  - Fira em Write/Edit/MultiEdit; só olha conteúdo que tenha um campo Altitude.
  - Valor aceito: strategic | tactical | implementation (só isso).
  - A linha-modelo da própria documentação ("strategic | tactical |
    implementation", ou um <placeholder>) passa — senão o gate impediria editar
    o documento que define o vocabulário.
  - Campo ausente NÃO é bloqueado: o debrief já trata ausência como `tactical`,
    e bloquear ausência transformaria a edição de bloco legado em parede.

Exit codes:
  0 — liberado
  2 — bloqueado (o stderr chega ao agente, que corrige sozinho)
"""

import json
import re
import sys

GATED_TOOLS = ("Write", "Edit", "MultiEdit")

VOCABULARIO = ("strategic", "tactical", "implementation")

MARKER = r"(?:\*\*|__|#{1,6}\s*|h[1-6]\.\s*|[-*+]\s+)"

# Campo Altitude e o resto da linha. pt-BR aceito no rótulo porque o harness
# manda escrever prosa em pt-BR; o VALOR continua sendo o vocabulário inglês,
# que é o que o debrief casa.
# Os dois pontos são OBRIGATÓRIOS: sem eles a regra casava a prosa que FALA do
# campo ("**Altitude field** classifies who reviews...") e bloqueava a edição do
# documento que define o vocabulário — gate que impede de consertar a própria
# definição é como se aprende a desligar o gate.
ALTITUDE_RE = re.compile(
    rf"^{MARKER}?\s*(?:Altitude|Altitude do bloco)\s*(?:\*\*|__)?\s*:\s*{MARKER}?\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)


def extract_content(tool_input: dict):
    v = tool_input.get("content")
    if isinstance(v, str):
        return v
    v = tool_input.get("new_string")
    if isinstance(v, str):
        return v
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        parts = [e.get("new_string", "") for e in edits if isinstance(e, dict)]
        if parts:
            return "\n".join(p for p in parts if isinstance(p, str))
    return None


def limpa(valor: str) -> str:
    """Tira marcação e pontuação de borda, preservando o texto do valor."""
    v = valor.strip()
    v = re.sub(r"^(\*\*|__|`)+|(\*\*|__|`)+$", "", v).strip()
    v = v.strip("*_`").strip()
    return v.rstrip(".;,").strip()


def e_linha_modelo(valor: str) -> bool:
    """A linha que ENSINA o vocabulário, não uma decisão real.

    Duas formas: a enumeração inteira ("strategic | tactical | implementation")
    e o marcador de preencher ("<strategic|tactical|implementation>").
    """
    v = limpa(valor).lower()
    # O marcador de preencher pode vir seguido de comentário na mesma linha
    # ("<strategic|tactical|implementation>   ← escolha uma"), e continua sendo
    # linha-modelo.
    if v.startswith("<"):
        return True
    v = v.strip("<>").strip()
    partes = [p.strip() for p in re.split(r"[|/]", v) if p.strip()]
    return len(partes) > 1 and all(p in VOCABULARIO for p in partes)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[decision-altitude-gate] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if not any(t in payload.get("tool_name", "") for t in GATED_TOOLS):
        sys.exit(0)

    content = extract_content(payload.get("tool_input") or {})
    if content is None:
        sys.exit(0)          # sem ver o conteúdo, não se bloqueia nada

    fora = []
    for valor in ALTITUDE_RE.findall(content):
        if e_linha_modelo(valor):
            continue
        v = limpa(valor).lower()
        if v not in VOCABULARIO:
            fora.append(limpa(valor))

    if not fora:
        sys.exit(0)

    lista = ", ".join(f'"{v}"' for v in dict.fromkeys(fora))
    print(
        "[decision-altitude-gate] BLOQUEADO: campo Altitude fora do vocabulário: "
        f"{lista}.\n"
        "  Altitude tem exatamente três valores — strategic, tactical, "
        "implementation — e diz QUEM revisa a decisão, não sobre o que ela é:\n"
        "   · strategic     — o dono revisa no debrief (escopo, contrato, "
        "nome público, semântica de spec, adiamento)\n"
        "   · tactical      — o lead revisa (decomposição, costura entre "
        "tarefas, estratégia de merge)\n"
        "   · implementation— fica registrado, o debrief só mostra com --all\n"
        "  O assunto da decisão vai no título (`### Decision: <assunto>`), "
        "nunca aqui.\n"
        "  Na dúvida entre strategic e tactical, use tactical.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
