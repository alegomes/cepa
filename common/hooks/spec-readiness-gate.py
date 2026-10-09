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
  - Em Edit/MultiEdit com `file_path`, não julga o fragmento (`new_string`)
    isolado: lê o arquivo do disco, aplica cada `old_string` → `new_string` na
    ordem (respeitando `replace_all`; sem ele, exige que `old_string` seja
    único no texto e troca essa única ocorrência — o mesmo que a ferramenta
    Edit faz de verdade) e julga o ARQUIVO RESULTANTE inteiro, Status incluso.
    Sem isso, um Edit que só troca `Status:` engana o gate (não vê os
    critérios, que estão fora do fragmento) e um Edit que fura um critério ou
    reabre uma pergunta engana o gate do lado oposto (o fragmento não tem
    Status, então nada dispara). Se o arquivo não existe, não lê, algum
    `old_string` não bate, ou bate mais de uma vez sem `replace_all`, libera (a
    própria ferramenta vai falhar por conta própria). Sem `file_path`, mantém
    o comportamento antigo: julga só os fragmentos (`new_string`).
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

Crivo de Epic (`/common:epic`, CS-5 do ciclo 1 do Epic Cepa em espiral):
  - Um Epic fecha por roteiro, não por critério. É Epic o documento em
    `docs/epics/*.md` ou o que abre com `# Epic:`; nele, `Status: pronta` (ou
    `pronta-para-construir`) é a afirmação gateada, e o crivo é outro:
      · a tabela de `## Escada de valor` tem pelo menos um ciclo, e as colunas
        "Roteiro", "Efeito em tela" e "Efeito em backend";
      · cada linha de ciclo preenche as três, sem placeholder: o roteiro é o
        que o dono vê, e tela e backend são onde alguém observa que aconteceu;
      · `## Invariantes` tem pelo menos um item de lista que não é placeholder;
      · a seção `## Decidido sem perguntar` existe;
      · nenhuma pergunta em aberto (`- [ ]`) sobrou.
  - Documento que não é Epic segue com a régua de antes: `Status: pronta` nele
    não é gateado, só `pronta-para-construir`.

Exit codes:
  0 — liberado
  2 — bloqueado (o stderr chega ao agente, que corrige sozinho)
"""

import json
import re
import sys
from pathlib import Path

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

# Epic: o status que ele afirma ao fechar. `pronta-para-construir` também vale,
# senão um Epic que use a palavra da especificação escapa do crivo dele.
EPIC_PRONTA = ("pronta", PRONTA)

EPIC_TITULO_RE = re.compile(r"^#\s+Epic\s*:", re.MULTILINE | re.IGNORECASE)
EPIC_CAMINHO_RE = re.compile(r"(^|/)docs/epics/[^/]+\.md$")

SECAO_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)

# Colunas da escada que o crivo exige, achadas pelo cabeçalho da tabela.
COLUNAS_EPIC = (
    ("roteiro", "Roteiro", "o que o dono vê funcionando no fim do ciclo"),
    ("efeito em tela", "Efeito em tela", "onde, na tela, alguém vê que aconteceu"),
    ("efeito em backend", "Efeito em backend",
     "o registro, endpoint ou evento que prova que aconteceu de verdade"),
)

ITEM_RE = re.compile(r"^\s*[-*+]\s+(?!\[[ xX]\])(.+)$", re.MULTILINE)


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


def aplica_edicao(texto: str, edit: dict):
    """Aplica um `old_string` → `new_string` sobre `texto`, como a ferramenta
    Edit faria de verdade. Retorna None se `old_string` não bate, ou se bate
    mais de uma vez sem `replace_all` — a ferramenta real exige que
    `old_string` seja único nesse caso e falha sozinha; quem chama aqui
    decide liberar."""
    old = edit.get("old_string")
    new = edit.get("new_string")
    if not isinstance(old, str) or not isinstance(new, str) or old == "":
        return None
    if old not in texto:
        return None
    if edit.get("replace_all"):
        return texto.replace(old, new)
    if texto.count(old) > 1:
        return None
    return texto.replace(old, new, 1)


def resultado_apos_edicoes(tool_name: str, tool_input: dict):
    """Para Edit/MultiEdit com `file_path`: lê o arquivo do disco e aplica cada
    edição na ordem, retornando o conteúdo resultante inteiro. Retorna None
    quando não dá para calcular com segurança (sem `file_path`, arquivo
    ilegível, formato inesperado, ou algum `old_string` que não bate) — nesses
    casos quem chama libera, porque a ferramenta real vai falhar por conta
    própria."""
    file_path = tool_input.get("file_path")
    if not isinstance(file_path, str) or not file_path:
        return None

    if tool_name == "MultiEdit":
        edits = tool_input.get("edits")
    else:
        edits = [tool_input]
    if not isinstance(edits, list) or not edits:
        return None

    try:
        texto = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    for edit in edits:
        if not isinstance(edit, dict):
            return None
        texto = aplica_edicao(texto, edit)
        if texto is None:
            return None
    return texto


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


def e_epic(content: str, file_path) -> bool:
    if isinstance(file_path, str) and EPIC_CAMINHO_RE.search(
            file_path.replace("\\", "/")):
        return True
    return EPIC_TITULO_RE.search(content) is not None


def secoes(content: str):
    """{título da seção ## em minúsculas: corpo até a próxima ##}."""
    marcas = list(SECAO_RE.finditer(content))
    out = {}
    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(content)
        out.setdefault(m.group(1).strip().lower(), content[m.end():fim])
    return out


def secao(content: str, prefixo: str):
    """O corpo da primeira seção `## <prefixo>...`, ou None se não existe."""
    for titulo, corpo in secoes(content).items():
        if titulo.startswith(prefixo):
            return corpo
    return None


def celulas(linha: str):
    s = linha.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def problemas_do_epic(content: str):
    problemas = []

    escada = secao(content, "escada de valor")
    if escada is None:
        problemas.append(
            "falta a seção `## Escada de valor` — um Epic pronto sem ciclo "
            "não tem o que demonstrar"
        )
    else:
        linhas = [l for l in escada.splitlines() if l.strip().startswith("|")]
        cab = [c.lower() for c in celulas(linhas[0])] if linhas else []
        idx = {}
        for chave, nome, _ in COLUNAS_EPIC:
            pos = [i for i, c in enumerate(cab) if c.startswith(chave)]
            if pos:
                idx[chave] = pos[0]
            else:
                problemas.append(
                    f'Escada de valor: falta a coluna "{nome}"'
                )
        ciclos = [l for l in linhas[1:]
                  if not re.fullmatch(r"[\s|:\-]*", l)]
        if not ciclos:
            problemas.append(
                "Escada de valor: nenhum ciclo — a tabela precisa de pelo menos "
                "uma linha"
            )
        if len(idx) == len(COLUNAS_EPIC):
            for l in ciclos:
                cel = celulas(l)
                nome_ciclo = limpa(cel[0]) if cel and cel[0] else "(sem nome)"
                for chave, nome, _ in COLUNAS_EPIC:
                    i = idx[chave]
                    valor = cel[i] if i < len(cel) else ""
                    if e_vazio(valor):
                        problemas.append(
                            f'ciclo "{nome_ciclo}": falta "{nome}"'
                        )

    invariantes = secao(content, "invariantes")
    if invariantes is None:
        problemas.append("falta a seção `## Invariantes`")
    else:
        itens = [v for v in ITEM_RE.findall(invariantes) if not e_vazio(v)]
        if not itens:
            problemas.append(
                "Invariantes: a lista está vazia — diga o que nunca pode "
                "regredir enquanto os ciclos andam"
            )

    if secao(content, "decidido sem perguntar") is None:
        problemas.append(
            "falta a seção `## Decidido sem perguntar` — é onde o dono veta o "
            "que você decidiu sozinho"
        )

    abertas = [limpa(q) for q in ABERTA_RE.findall(content) if not e_vazio(q)]
    for q in abertas[:5]:
        problemas.append(f'pergunta em aberto sem resposta: "{q}"')
    if len(abertas) > 5:
        problemas.append(f"... e mais {len(abertas) - 5} pergunta(s) em aberto")

    return problemas


def bloqueia_epic(problemas):
    linhas = "\n".join(f"   · {p}" for p in problemas)
    colunas = "\n".join(f'   · "{nome}": {o_que}' for _, nome, o_que in COLUNAS_EPIC)
    print(
        "[spec-readiness-gate] BLOQUEADO: o Epic se declara `Status: pronta` "
        "mas ainda não passa no crivo.\n"
        f"{linhas}\n"
        "  O que o crivo exige de CADA ciclo da escada:\n"
        f"{colunas}\n"
        "  E do documento: pelo menos um invariante, a seção \"Decidido sem "
        "perguntar\" e nenhuma pergunta em aberto.\n"
        "  Enquanto faltar qualquer um, o Status correto é `rascunho` — e a "
        "resposta certa é voltar a perguntar ao dono, não relaxar o campo.",
        file=sys.stderr,
    )
    sys.exit(2)


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print("[spec-readiness-gate] payload ilegível; liberando", file=sys.stderr)
        sys.exit(0)

    if not any(t in payload.get("tool_name", "") for t in GATED_TOOLS):
        sys.exit(0)

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")

    if tool_name in ("Edit", "MultiEdit") and isinstance(file_path, str) and file_path:
        # Com file_path, o fragmento (new_string) não basta — precisa do
        # ARQUIVO INTEIRO depois da edição, Status incluso (ver docstring).
        content = resultado_apos_edicoes(tool_name, tool_input)
        if content is None:
            sys.exit(0)      # arquivo ilegível ou old_string não bate: libera
    else:
        content = extract_content(tool_input)
        if content is None:
            sys.exit(0)          # sem ver o conteúdo, não se bloqueia nada

    status = [limpa(v).lower() for v in STATUS_RE.findall(content)]
    status = [s for s in status if not s.startswith("<")]
    # A linha-modelo "rascunho | pronta-para-construir" ensina o formato.
    status = [s for s in status if "|" not in s]

    if e_epic(content, file_path):
        # O Status do Epic costuma dividir a linha com outros campos
        # (`**Status:** pronta · **Aberto em:** ...`): vale a primeira palavra.
        primeiras = [re.split(r"\s*[·•]\s*|\s+\*\*|\s+__", s)[0].strip()
                     for s in status]
        if not any(s in EPIC_PRONTA for s in primeiras):
            sys.exit(0)      # rascunho corre livre
        problemas = problemas_do_epic(content)
        if problemas:
            bloqueia_epic(problemas)
        sys.exit(0)

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
