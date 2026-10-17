#!/usr/bin/env python3
"""_modos — a tabela dos modos de trabalho, em UM lugar só.

## Por que existe

O modo de uma sessão é um ESTADO que dura (`docs/modos-de-trabalho.md`), e cada
modo tem entrada, produto e condição de saída. Essa informação estava em três
lugares que não conversavam:

- `common/bin/cepa` — a lista de nomes válidos (`MODOS=`), para validar `--modo`;
- `common/hooks/session-mode.py` — só as condições de saída, para injetar no turno;
- `docs/modos-de-trabalho.md` — a prosa completa, que ninguém lê no meio da sessão.

Quem esquece o propósito de um modo no meio do trabalho não vai abrir um doc de
307 linhas. E três cópias da mesma tabela é o padrão que este repo já pagou caro
(memória `hooks-texto-citado-nao-e-shell`: 7 cópias do mesmo parser, conserto
aplicado em 5). Aqui a tabela é uma; o hook importa, o `cepa-modos` imprime, e
`tests/test_modos_fonte_unica.py` reprova se a lista do `cepa` divergir daqui.

Cada modo declara também `escrita`: a lista branca de DESTINOS que ele produz,
lida pelo `modo-escrita-gate.py`. `"tudo"` significa que o modo não tem lista —
não que ele é livre de cobrança: na construção quem cobra são o
completion-auditor e o proof-reviewer, e na reforma o `reforma-gate.py`.

`deploy` NÃO está aqui de propósito: é o 8º modo do documento, deixado fora da
rodada por decisão do dono (é o único que depende de infra externa). Quando
entrar, entra aqui primeiro.
"""

import os
import re

# ordem = a ordem do ciclo de trabalho, não alfabética
MODOS = {
    "exploracao": {
        "proposito": "entender uma dor que ainda não tem solução proposta, e sair com um caminho recomendado",
        "entrada": "uma dor em linguagem natural, SEM solução proposta — se você "
                   "já sabe a solução, não é exploração",
        "produz": "um documento de estratégia com 2+ caminhos considerados, um "
                  "recomendado, e a dor reformulada com o que se aprendeu",
        "saida": "um documento de estratégia com 2+ caminhos considerados, "
                 "passado pelo painel /common:advisors com as discordâncias nomeadas",
        "gate": "parcial — o painel existe, o veredito não; o modo-escrita-gate já barra escrita fora de docs/**",
        "escrita": ["docs/**", ".claude/**", "BACKLOG.md"],
    },
    "descoberta": {
        "proposito": "virar um comportamento desejado em critério de aceite cobrável, com evidência atrás",
        "entrada": "um comportamento desejado, vindo da exploração ou direto",
        "produz": "oportunidade enquadrada, evidência coletada, e os critérios de "
                  "aceite escritos NA ALTITUDE em que serão cobrados",
        "saida": "evidence-auditor Confirmed nas suposições de risco + os "
                 "critérios de aceite escritos na altitude + o teste vermelho de cada um",
        "gate": "em parte: o spec-readiness-gate barra especificação pronta sem superfície e teste vermelho declarados por critério, mas não roda o teste; o modo-escrita-gate barra escrita fora de docs/discovery, docs/spec e docs/epics",
        "escrita": ["docs/discovery/**", "docs/spec/**", "docs/epics/**", ".claude/**", "BACKLOG.md"],
    },
    "design": {
        "proposito": "desenhar como a coisa funciona e como ela se parece, antes de existir código",
        "entrada": "oportunidade validada",
        "produz": "fluxos, estados, spec visual reconciliada com o design system, "
                  "protótipo compartilhável",
        "saida": "design-critic devolvendo SHIP",
        "gate": "existe e funciona (topologia design); o modo-escrita-gate barra escrita fora de docs/design",
        "escrita": ["docs/design/**", ".claude/**", "BACKLOG.md"],
    },
    "construcao": {
        "proposito": "escrever o código que faz o teste vermelho do critério ficar verde",
        "entrada": "UM TESTE VERMELHO escrito a partir do critério de aceite, antes "
                   "do código, por quem não vai implementar",
        "produz": "código + testes",
        "saida": "completion-auditor COMPLETE e proof-reviewer PROVEN",
        "gate": "existe e funciona (os dois gates, nesta ordem)",
        "escrita": "tudo",
    },
    "reforma": {
        "proposito": "reorganizar código já entregue sem mudar nada que se veja de fora",
        "entrada": "ORÇAMENTO DECLARADO — a lista fechada do que será reformado e o "
                   "limite; sem orçamento a reforma nunca termina",
        "produz": "código reorganizado, comportamento externo idêntico",
        "saida": "o orçamento declarado exaurido, build verde, e NENHUM teste "
                 "externo editado (teste editado = mudou comportamento = não era reforma)",
        "gate": "reforma-gate.py bloqueia editar teste externo enquanto o modo dura",
        "escrita": "tudo",
    },
    "reflexao": {
        "proposito": "olhar o que já existe por uma lente escolhida e transformar cada achado em destino",
        "entrada": "um RECORTE e uma LENTE, ambos escolhidos de menu — reflexão sem "
                   "recorte vira leitura infinita do repo",
        "produz": "um relatório de achados classificados",
        "saida": "nenhum achado sem destino — cada um virou card ou foi "
                 "descartado com motivo escrito",
        "gate": "reflexao-gate.py barra relatório fechado com achado solto, e o modo-escrita-gate barra escrita fora de docs/** e .claude/reflexao",
        "escrita": [".claude/reflexao/**", "docs/**", "BACKLOG.md"],
    },
    "documentacao": {
        "proposito": "documentar código estável na árvore Diátaxis, com cada porquê citando sua fonte",
        "entrada": "código estável, não em construção ativa",
        "produz": "a árvore Diátaxis fundamentada",
        "saida": "consistency-reviewer PASS e sua assinatura em /docs:finalize",
        "gate": "existe e funciona (topologia docs); o modo-escrita-gate barra escrita fora de docs/**",
        "escrita": ["docs/**", ".claude/**", "BACKLOG.md"],
    },
}

# O que `session-mode.py` injeta a cada turno — só a condição de saída.
SAIDA = {nome: d["saida"] for nome, d in MODOS.items()}


# ---------------------------------------------------------------------------
# A intenção da sessão: `.claude/session-intent`
# ---------------------------------------------------------------------------
#
# Formato e leitor ficam AQUI, num lugar só, pelo mesmo motivo da tabela acima.
# O `session-mode` é lido linha a linha por seis leitores (`grep`/`sed` e hooks)
# que não entendem lista, e o `write_modo` do `cepa` o reescreve inteiro com `>`:
# pôr o plano e o histórico lá dentro seria perdê-los na primeira troca de modo.
# Por isso a intenção é um arquivo próprio, e quem o lê (hook, `whereami`,
# statusline, `cepa-intencao`) importa `read_intent` em vez de copiar um parser.
#
# O formato, documentado em `docs/estrategia-intencao-da-sessao.md`:
#
#   proposito, para_quando, passo_desde, session_id, branch, aberto_em, resumo
#                 escalares (entre aspas "..." ou nus)
#   plano         lista de 1 a PLANO_MAX textos (`- item`)
#   passo         inteiro, 1-based: o passo EM ANDAMENTO, não o último concluído
#   historico     lista de mapas (`- em: ...` e chaves recuadas abaixo)
#
# Sem pyyaml: os hooks deste repo não dependem dele (ver `_wtlib.py`). O leitor é
# tolerante de propósito — um hook que quebra por causa de um arquivo meio escrito
# derruba o turno inteiro. Ele devolve o que conseguiu ler, mantém chaves
# desconhecidas e nunca levanta. NÃO impõe as regras do escritor (item de plano
# sem dois-pontos, por exemplo): isso é do `cepa-intencao`.

INTENT_FILE = ".claude/session-intent"

# Plano de 1 a 6 passos; mais que isso é programa (`plan.yaml`).
PLANO_MAX = 6

# Chaves cujo valor é uma lista de mapas; qualquer outra lista é de textos.
_INTENT_LISTAS_DE_MAPAS = ("historico",)

_KV = re.compile(r"^([A-Za-z_][\w-]*)\s*:(?:\s+(.*)|\s*)$")


def _intent_valor(bruto):
    """Um escalar do arquivo: "entre aspas" (com \\" e \\\\) ou nu sem `# nota`."""
    s = (bruto or "").strip()
    if s[:1] in ('"', "'"):
        q, out, i = s[0], [], 1
        while i < len(s):
            c = s[i]
            if c == "\\" and q == '"' and i + 1 < len(s):
                out.append(s[i + 1])
                i += 2
                continue
            if c == q:
                return "".join(out)
            out.append(c)
            i += 1
        return "".join(out)  # aspas sem fechar: devolve o que havia
    m = re.search(r"\s#", s)
    return (s[:m.start()] if m else s).strip()


def parse_intent(text):
    """Texto do `session-intent` -> dict. Tolerante: nunca levanta."""
    dados, chave, ultimo_mapa = {}, None, None
    try:
        for linha in (text or "").splitlines():
            if not linha.strip() or linha.lstrip().startswith("#"):
                continue
            if not linha[0].isspace():
                ultimo_mapa = None
                m = _KV.match(linha.rstrip())
                if not m:
                    chave = None
                    continue
                chave, resto = m.group(1), m.group(2)
                if resto is None or resto.lstrip().startswith("#"):
                    dados[chave] = []  # abre um bloco; sem itens vira lista vazia
                else:
                    dados[chave] = _intent_valor(resto)
                continue
            if chave is None or not isinstance(dados.get(chave), list):
                continue
            corpo = linha.strip()
            mapas = chave in _INTENT_LISTAS_DE_MAPAS
            if corpo.startswith("-"):
                item = corpo[1:].strip()
                if mapas:
                    ultimo_mapa = {}
                    dados[chave].append(ultimo_mapa)
                    m = _KV.match(item)
                    if m:
                        ultimo_mapa[m.group(1)] = _intent_valor(m.group(2))
                else:
                    dados[chave].append(_intent_valor(item))
            elif mapas and ultimo_mapa is not None:
                m = _KV.match(corpo)
                if m:
                    ultimo_mapa[m.group(1)] = _intent_valor(m.group(2))
        if "passo" in dados:
            try:
                dados["passo"] = int(str(dados["passo"]).strip())
            except (ValueError, TypeError):
                pass  # fica como veio; quem lê decide
    except Exception:
        pass  # devolve o que já tinha lido
    return dados


def read_intent(root):
    """`<root>/.claude/session-intent` -> dict, ou None se o arquivo não existe."""
    try:
        with open(os.path.join(str(root), INTENT_FILE), encoding="utf-8",
                  errors="replace") as f:
            return parse_intent(f.read())
    except OSError:
        return None


# Ordem em que o escritor emite as chaves conhecidas; as desconhecidas (que o
# leitor preserva) vão depois, para uma versão futura do formato não ser apagada
# por um `cepa-intencao` antigo.
_INTENT_ORDEM = ("proposito", "para_quando", "plano", "passo", "passo_desde",
                 "session_id", "branch", "aberto_em", "resumo", "historico")


def _intent_aspas(valor):
    """Escalar -> `"..."` com \\ e \" escapados; quebra de linha vira espaço."""
    s = " ".join(str(valor).split("\n")).replace("\r", " ")
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_intent(dados):
    """dict -> texto do `session-intent`; `parse_intent` o lê de volta igual.

    Mora ao lado do parser para o par ficar testado junto: o escritor
    (`cepa-intencao`) é o único que chama, mas o formato é um só. Escalares
    saem sempre entre aspas (o `passo` sai nu, é inteiro e o parser o converte).
    """
    chaves = [k for k in _INTENT_ORDEM if k in dados]
    chaves += [k for k in dados if k not in _INTENT_ORDEM]
    out = []
    for k in chaves:
        v = dados[k]
        if k == "passo":
            out.append(f"{k}: {int(v)}")
        elif k == "historico":
            out.append(f"{k}:")
            for mapa in v or []:
                pares = list(mapa.items())
                for i, (mk, mv) in enumerate(pares):
                    out.append(("  - " if i == 0 else "    ") + f"{mk}: {_intent_aspas(mv)}")
        elif isinstance(v, list):
            out.append(f"{k}:")
            out += [f"  - {_intent_aspas(i)}" for i in v]
        else:
            out.append(f"{k}: {_intent_aspas(v)}")
    return "\n".join(out) + "\n"
