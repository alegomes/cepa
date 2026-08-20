#!/usr/bin/env python3
"""PreToolUse hook: bloqueia uma especificação que se declara pronta para
construir enquanto algum critério de sucesso não tem superfície e teste vermelho.

O `/common:spec` conduz um interrogatório: o agente pergunta, o dono responde, e
a especificação cresce. O risco não é o interrogatório ficar curto — é ele
TERMINAR por cansaço. O agente decide que já está bom, escreve `Status:
pronta-para-construir`, e o que sai é uma especificação plausível cujos
critérios são frases de intenção ("o sistema deve validar o cadastro") sem
nenhuma superfície observável onde alguém possa provar que aconteceu. Isso não
falha na especificação: falha três semanas depois, na construção, quando o
critério é interpretado por outra pessoa de outro jeito.

Por isso o encerramento é mecânico e não editorial. `Status: rascunho` nunca
bloqueia nada — o interrogatório precisa poder escrever livremente enquanto
corre. O que é gateado é exclusivamente a AFIRMAÇÃO de que acabou.

Mecanismo:
  - Fira em Write/Edit/MultiEdit; só olha conteúdo com um campo Status.
  - Status diferente de "pronta-para-construir" → libera, sem olhar mais nada.
  - Declarou pronta, então exige, em cada bloco `### CS-<n>`:
      · **Superfície:** com valor do vocabulário fechado (o mesmo da skill
        acceptance-completeness: http, cli, ui, event, domain, application);
      · **Teste vermelho:** com texto que não seja placeholder.
  - Exige pelo menos um critério: especificação pronta com zero critérios é o
    caso mais silencioso de todos.
  - Exige que nenhuma pergunta em aberto (`- [ ]`) tenha sobrado.
  - A linha-modelo do próprio formato (enumeração ou <placeholder>) passa, senão
    o gate impede editar o documento que define o formato.

Exit codes:
  0 — liberado
  2 — bloqueado (o stderr chega ao agente, que corrige sozinho)
"""

import json
import re
import sys

GATED_TOOLS = ("Write", "Edit", "MultiEdit")

SUPERFICIES = ("http", "cli", "ui", "event", "domain", "application")

PRONTA = "pronta-para-construir"

MARKER = r"(?:\*\*|__|#{1,6}\s*|h[1-6]\.\s*|[-*+]\s+)"

STATUS_RE = re.compile(
    rf"^{MARKER}?\s*Status\s*(?:\*\*|__)?\s*:\s*{MARKER}?\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

# Cabeçalho de critério: "### CS-1: texto". O id é o que aparece na mensagem de
# bloqueio, para o agente saber QUAL critério consertar.
CS_RE = re.compile(r"^#{2,6}\s*(CS-[0-9A-Za-z]+)\s*:?\s*(.*)$", re.MULTILINE)

CAMPO_RE = {
    "superficie": re.compile(
        rf"^{MARKER}?\s*Superf[íi]cie\s*(?:\*\*|__)?\s*:\s*{MARKER}?\s*(.+)$",
        re.MULTILINE | re.IGNORECASE,
    ),
    "teste": re.compile(
        rf"^{MARKER}?\s*Teste vermelho\s*(?:\*\*|__)?\s*:\s*{MARKER}?\s*(.+)$",
        re.MULTILINE | re.IGNORECASE,
    ),
}

# Pergunta em aberto no formato checklist markdown.
ABERTA_RE = re.compile(r"^\s*[-*+]\s*\[\s\]\s*(.+)$", re.MULTILINE)


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
    v = valor.strip()
    v = re.sub(r"^(\*\*|__|`)+|(\*\*|__|`)+$", "", v).strip()
    v = v.strip("*_`").strip()
    return v.rstrip(".;,").strip()


def e_linha_modelo(valor: str) -> bool:
    """A linha que ENSINA o formato, não um critério real."""
    v = limpa(valor).lower()
    if v.startswith("<"):
        return True
    v = v.strip("<>").strip()
    partes = [p.strip() for p in re.split(r"[|/]", v) if p.strip()]
    return len(partes) > 1 and all(p in SUPERFICIES for p in partes)


def e_vazio(valor: str) -> bool:
    """Texto que ocupa a linha sem dizer nada."""
    v = limpa(valor).lower()
    if not v or v.startswith("<"):
        return True
    return v in ("", "-", "n/a", "na", "tbd", "todo", "a definir", "?", "...")


def blocos_de_criterio(content: str):
    """Fatiar o documento em (id, corpo) por cabeçalho `### CS-<n>`."""
    marcas = list(CS_RE.finditer(content))
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(content)
        yield m.group(1), content[m.end():fim]


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[spec-readiness-gate] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if not any(t in payload.get("tool_name", "") for t in GATED_TOOLS):
        sys.exit(0)

    content = extract_content(payload.get("tool_input") or {})
    if content is None:
        sys.exit(0)          # sem ver o conteúdo, não se bloqueia nada

    status = [limpa(v).lower() for v in STATUS_RE.findall(content)]
    status = [s for s in status if not s.startswith("<")]
    # A linha-modelo "rascunho | pronta-para-construir" ensina o formato.
    status = [s for s in status if "|" not in s]
    if not any(s == PRONTA for s in status):
        sys.exit(0)          # rascunho corre livre; só a afirmação é gateada

    problemas = []

    criterios = list(blocos_de_criterio(content))
    if not criterios:
        problemas.append(
            "nenhum critério de sucesso (`### CS-1: ...`) — uma especificação "
            "pronta sem critério é a que mais engana"
        )

    for cid, corpo in criterios:
        sup = [v for v in CAMPO_RE["superficie"].findall(corpo)
               if not e_linha_modelo(v)]
        if not sup:
            problemas.append(f"{cid}: falta **Superfície:**")
        else:
            for v in sup:
                if limpa(v).lower() not in SUPERFICIES:
                    problemas.append(
                        f'{cid}: Superfície "{limpa(v)}" fora do vocabulário'
                    )

        teste = [v for v in CAMPO_RE["teste"].findall(corpo) if not e_vazio(v)]
        if not teste:
            problemas.append(
                f"{cid}: falta **Teste vermelho:** — a frase do teste que hoje "
                "falharia"
            )

    abertas = [limpa(q) for q in ABERTA_RE.findall(content) if not e_vazio(q)]
    for q in abertas[:5]:
        problemas.append(f'pergunta em aberto sem resposta: "{q}"')
    if len(abertas) > 5:
        problemas.append(f"... e mais {len(abertas) - 5} pergunta(s) em aberto")

    if not problemas:
        sys.exit(0)

    linhas = "\n".join(f"   · {p}" for p in problemas)
    print(
        "[spec-readiness-gate] BLOQUEADO: a especificação se declara "
        f"`Status: {PRONTA}` mas ainda não passa no crivo.\n"
        f"{linhas}\n"
        "  O que o crivo exige de CADA critério de sucesso:\n"
        "   · **Superfície:** a camada mais externa que o critério nomeia — "
        f"{', '.join(SUPERFICIES)}. Não é o assunto do critério, é onde ele é "
        "observável.\n"
        "   · **Teste vermelho:** a frase do teste que HOJE falharia naquela "
        "superfície e passará quando a coisa existir.\n"
        "  Enquanto faltar qualquer um, o Status correto é `rascunho` — e a "
        "resposta certa é continuar o interrogatório, não relaxar o campo.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
