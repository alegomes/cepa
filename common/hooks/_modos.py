#!/usr/bin/env python3
"""_modos — a tabela dos modos de trabalho, em UM lugar só.

## Por que existe

O modo de uma sessão é um ESTADO que dura (`docs/modos-de-trabalho.md`), e cada
modo tem entrada, produto e condição de saída. Essa informação estava em três
lugares que não conversavam:

- `common/bin/cepa` — a lista de nomes válidos (`MODOS=`), para validar `--mode`;
- `common/hooks/session-mode.py` — só as condições de saída, para injetar no turno;
- `docs/modos-de-trabalho.md` — a prosa completa, que ninguém lê no meio da sessão.

Quem esquece o propósito de um modo no meio do trabalho não vai abrir um doc de
307 linhas. E três cópias da mesma tabela é o padrão que este repo já pagou caro
(memória `hooks-texto-citado-nao-e-shell`: 7 cópias do mesmo parser, conserto
aplicado em 5). Aqui a tabela é uma; o hook importa, o `cepa-modes` imprime, e
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
    "exploration": {
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
    "discovery": {
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
    "construction": {
        "proposito": "escrever o código que faz o teste vermelho do critério ficar verde",
        "entrada": "UM TESTE VERMELHO escrito a partir do critério de aceite, antes "
                   "do código, por quem não vai implementar",
        "produz": "código + testes",
        "saida": "completion-auditor COMPLETE e proof-reviewer PROVEN",
        "gate": "existe e funciona (os dois gates, nesta ordem)",
        "escrita": "tudo",
    },
    "refactor": {
        "proposito": "reorganizar código já entregue sem mudar nada que se veja de fora",
        "entrada": "ORÇAMENTO DECLARADO — a lista fechada do que será reformado e o "
                   "limite; sem orçamento a reforma nunca termina",
        "produz": "código reorganizado, comportamento externo idêntico",
        "saida": "o orçamento declarado exaurido, build verde, e NENHUM teste "
                 "externo editado (teste editado = mudou comportamento = não era reforma)",
        "gate": "reforma-gate.py bloqueia editar teste externo enquanto o modo dura",
        "escrita": "tudo",
    },
    "reflection": {
        "proposito": "olhar o que já existe por uma lente escolhida e transformar cada achado em destino",
        "entrada": "um RECORTE e uma LENTE, ambos escolhidos de menu — reflexão sem "
                   "recorte vira leitura infinita do repo",
        "produz": "um relatório de achados classificados",
        "saida": "nenhum achado sem destino — cada um virou card ou foi "
                 "descartado com motivo escrito",
        "gate": "reflexao-gate.py barra relatório fechado com achado solto, e o modo-escrita-gate barra escrita fora de docs/** e .claude/reflexao",
        "escrita": [".claude/reflexao/**", "docs/**", "BACKLOG.md"],
    },
    "documentation": {
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

# Os nomes antigos (pt-BR) dos modos, aceitos na leitura durante a transição
# (item `interface-in-english`): um `.claude/session-mode` gravado por um `cepa`
# antigo continua valendo. Quem ESCREVE grava só o nome novo.
MODO_ANTIGO_PARA_NOVO = {
    "exploracao": "exploration",
    "descoberta": "discovery",
    "design": "design",
    "construcao": "construction",
    "reforma": "refactor",
    "reflexao": "reflection",
    "documentacao": "documentation",
}

# As chaves antigas de `.claude/session-mode` -> as novas.
_SESSION_MODE_CHAVES = {"modo": "mode", "rotina": "routine",
                        "orcamento": "budget", "aberto_em": "opened_at"}


def normalize_mode(valor):
    """Nome de modo (antigo ou novo) -> o nome novo; desconhecido volta como veio."""
    v = str(valor or "").strip()
    return MODO_ANTIGO_PARA_NOVO.get(v, v)


def parse_session_mode(text):
    """Texto do `.claude/session-mode` -> dict com as chaves NOVAS (mode,
    routine, budget, opened_at), lendo também as antigas. `null`/vazio -> None.
    O valor de `mode` já vem normalizado para o nome novo. Nunca levanta."""
    data = {}
    try:
        for line in (text or "").splitlines():
            if ":" not in line:
                continue
            k, _, v = line.partition(":")
            k = k.strip()
            v = v.strip().strip('"')
            val = None if v in ("null", "") else v
            if k in _SESSION_MODE_CHAVES:  # chave antiga: só vale se a nova não veio
                data.setdefault(_SESSION_MODE_CHAVES[k], val)
            else:
                data[k] = val
    except Exception:  # noqa: BLE001
        pass
    if data.get("mode"):
        data["mode"] = normalize_mode(data["mode"])
    return data


def read_session_mode(root):
    """`<root>/.claude/session-mode` -> dict (chaves novas), ou None se o
    arquivo não existe/é ilegível ou não declara modo."""
    try:
        with open(os.path.join(str(root), ".claude", "session-mode"),
                  encoding="utf-8", errors="replace") as f:
            data = parse_session_mode(f.read())
    except OSError:
        return None
    return data if data.get("mode") else None


# ---------------------------------------------------------------------------
# A intenção da sessão: `.claude/session-intent`
# ---------------------------------------------------------------------------
#
# Formato e leitor ficam AQUI, num lugar só, pelo mesmo motivo da tabela acima.
# O `session-mode` é lido linha a linha por seis leitores (`grep`/`sed` e hooks)
# que não entendem lista, e o `write_modo` do `cepa` o reescreve inteiro com `>`:
# pôr o plano e o histórico lá dentro seria perdê-los na primeira troca de modo.
# Por isso a intenção é um arquivo próprio, e quem o lê (hook, `whereami`,
# statusline, `cepa-intent`) importa `read_intent` em vez de copiar um parser.
#
# O formato, documentado em `docs/estrategia-intencao-da-sessao.md`:
#
#   purpose, by_when, step_since, session_id, branch, opened_at, summary
#                 escalares (entre aspas "..." ou nus)
#   plan          lista de 1 a PLANO_MAX textos (`- item`)
#   step          inteiro, 1-based: o passo EM ANDAMENTO, não o último concluído
#   history       lista de mapas (`- at: ...` e chaves recuadas abaixo)
#
# As chaves antigas (proposito, para_quando, plano, passo, passo_desde,
# aberto_em, resumo, historico e, no histórico, em/proposito/plano_anterior/
# motivo_da_troca) continuam LIDAS e voltam já com o nome novo; o escritor
# grava só as novas.
#
# Sem pyyaml: os hooks deste repo não dependem dele (ver `_wtlib.py`). O leitor é
# tolerante de propósito — um hook que quebra por causa de um arquivo meio escrito
# derruba o turno inteiro. Ele devolve o que conseguiu ler, mantém chaves
# desconhecidas e nunca levanta. NÃO impõe as regras do escritor (item de plano
# sem dois-pontos, por exemplo): isso é do `cepa-intent`.

INTENT_FILE = ".claude/session-intent"

# Plano de 1 a 6 passos; mais que isso é programa (`plan.yaml`).
PLANO_MAX = 6

# Chaves cujo valor é uma lista de mapas; qualquer outra lista é de textos.
_INTENT_LISTAS_DE_MAPAS = ("history",)

# Chaves antigas -> novas, no topo do arquivo e dentro das entradas do histórico.
_INTENT_CHAVES_ANTIGAS = {
    "proposito": "purpose", "para_quando": "by_when", "plano": "plan",
    "passo": "step", "passo_desde": "step_since", "aberto_em": "opened_at",
    "resumo": "summary", "historico": "history",
}
_HISTORY_CHAVES_ANTIGAS = {
    "em": "at", "proposito": "purpose", "plano_anterior": "previous_plan",
    "motivo_da_troca": "change_reason",
    "acao": "action", "motivo": "reason", "de": "from", "para": "to",
}

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
                chave = _INTENT_CHAVES_ANTIGAS.get(chave, chave)
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
                        ultimo_mapa[_HISTORY_CHAVES_ANTIGAS.get(m.group(1), m.group(1))] = _intent_valor(m.group(2))
                else:
                    dados[chave].append(_intent_valor(item))
            elif mapas and ultimo_mapa is not None:
                m = _KV.match(corpo)
                if m:
                    ultimo_mapa[_HISTORY_CHAVES_ANTIGAS.get(m.group(1), m.group(1))] = _intent_valor(m.group(2))
        if "step" in dados:
            try:
                dados["step"] = int(str(dados["step"]).strip())
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
# por um `cepa-intent` antigo.
_INTENT_ORDEM = ("purpose", "by_when", "plan", "step", "step_since",
                 "session_id", "branch", "opened_at", "summary", "history")


def _intent_aspas(valor):
    """Escalar -> `"..."` com \\ e \" escapados; quebra de linha vira espaço."""
    s = " ".join(str(valor).split("\n")).replace("\r", " ")
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_intent(dados):
    """dict -> texto do `session-intent`; `parse_intent` o lê de volta igual.

    Mora ao lado do parser para o par ficar testado junto: o escritor
    (`cepa-intent`) é o único que chama, mas o formato é um só. Escalares
    saem sempre entre aspas (o `step` sai nu, é inteiro e o parser o converte).
    """
    chaves = [k for k in _INTENT_ORDEM if k in dados]
    chaves += [k for k in dados if k not in _INTENT_ORDEM]
    out = []
    for k in chaves:
        v = dados[k]
        if k == "step":
            out.append(f"{k}: {int(v)}")
        elif k == "history":
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


def iso_utc(stamp):
    """`2026-10-16T21:40:00Z` (ou com offset) -> datetime UTC; None se não der."""
    from datetime import datetime, timezone
    try:
        d = datetime.fromisoformat(str(stamp).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def mesma_sessao(gravada, atual):
    """A intenção é desta sessão? O arquivo pode guardar o id cortado (8
    caracteres); prefixo basta. Sem como comparar, não acusa outra sessão.

    Regra única: o hook `session-mode.py` e o `cepa-intent estado` (que o
    /common:whereami roda) perguntam a mesma coisa e não podem divergir."""
    g, a = str(gravada or "").strip(), str(atual or "").strip()
    if not g or not a:
        return True
    return g.startswith(a) or a.startswith(g)


def pergunta_outra_sessao(intent, prop):
    """As duas frases da decisão D1 (intenção gravada por OUTRA sessão): a data
    e a pergunta "continuo ou abro nova?". `prop` já vem cortado por quem chama
    (o hook paga pedágio por turno; o whereami mostra por extenso)."""
    quando = iso_utc(intent.get("opened_at", ""))
    data = quando.strftime("%Y-%m-%d %H:%M UTC") if quando else "data desconhecida"
    return [
        f"[intenção] Intenção de {data}, gravada em outra sessão: \"{prop}\". "
        "Não a trate como a desta sessão.",
        "Pergunte ao dono: continuo ou abro nova? Continuar = `cepa-intent "
        "continue`; abrir nova = `cepa-intent write ... --reason \"...\"`.",
    ]
