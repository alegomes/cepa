#!/usr/bin/env python3
"""Injeta o modo de trabalho ativo no contexto, a cada turno.

O modo é declarado no `cepa --modo <x>` e gravado em .claude/session-mode. Ele é
um ESTADO que dura a sessão inteira — diferente da rotina, que é uma tarefa que
acaba. Desenho completo: docs/modos-de-trabalho.md.

Por que UserPromptSubmit e não SessionStart: a fronteira precisa estar presente
no turno em que o desvio aparece. Injetado só na abertura, o modo some do
contexto útil justamente nas sessões longas, que são onde o vazamento entre
atividades acontece.

Saída enxuta de propósito (cabe em poucas linhas): ela paga pedágio em todo
turno. Diz o modo, a condição de saída dele e a regra do desvio — nada mais.

Junto do modo vai a INTENÇÃO da sessão (`.claude/session-intent`, escrita só
pelo `cepa-intencao`; desenho em docs/estrategia-intencao-da-sessao.md), com
teto de duas linhas, num de três estados:

  - sem intenção gravada (e sessão aberta pelo `cepa`, isto é, com modo): os
    três primeiros prompts da sessão e o pedido de propor e gravar. Os prompts
    são a intenção na voz do dono antes de qualquer desvio (caminho C4);
  - intenção gravada por OUTRA sessão: a data e a pergunta "continuo ou abro
    nova?", em vez de exibi-la como atual (decisão D1);
  - intenção desta sessão: propósito, passo N/M com há quantos turnos o cursor
    está parado, e o próximo passo. A idade é o que denuncia o cursor que o
    agente esqueceu de avançar (decisão D2); o plano inteiro fica no whereami.

Rodada do `cepa-until` (`CEPA_UNTIL_RUN`) não recebe intenção nenhuma: ali a
intenção é o item do plan.yaml, e um arquivo herdado de outra sessão viraria
uma pergunta que ninguém está lá para responder.

Nunca bloqueia nada. Sem modo e sem intenção, é silencioso.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

# Condição de saída de cada modo — o que precisa ser verdade para ele fechar.
# Sem isso o modo é rótulo, não fronteira. A tabela mora em `_modos.py` (fonte
# única, compartilhada com o `cepa-modos`); aqui só se lê.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _modos import SAIDA
except Exception:  # noqa: BLE001 — o hook roda todo turno; nunca pode quebrar
    SAIDA = {}
try:
    from _modos import read_intent
except Exception:  # noqa: BLE001
    read_intent = None

# A marca que o `cepa-until` exporta em cada rodada (mesma do session-registry).
ENV_JANELA = "CEPA_UNTIL_RUN"

# Quantos prompts do log entram no estado vazio, e o corte de cada um: são
# pista da intenção, não transcrição, e pagam pedágio todo turno.
PRIMEIROS = 3
CORTE_PROMPT = 120
# O mesmo pedágio vale para o propósito e o nome do passo: o escritor não
# limita o tamanho deles, e o hook repete os dois em todo turno.
CORTE_PROPOSITO = 160
CORTE_PASSO = 80


def repo_root(cwd):
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], cwd=cwd,
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() if out.returncode == 0 else cwd
    except Exception:  # noqa: BLE001
        return cwd


def read_mode(root):
    """Lê o .claude/session-mode. Formato raso o bastante para não exigir PyYAML
    (o hook roda em todo turno; importar yaml aqui seria pedágio à toa)."""
    path = os.path.join(root, ".claude", "session-mode")
    if not os.path.isfile(path):
        return None
    data = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if ":" not in line:
                    continue
                k, _, v = line.partition(":")
                v = v.strip().strip('"')
                data[k.strip()] = None if v in ("null", "") else v
    except Exception:  # noqa: BLE001
        return None
    return data if data.get("modo") else None


def _iso(stamp):
    """`2026-10-16T21:40:00Z` (ou com offset) -> datetime UTC; None se não der."""
    try:
        d = datetime.fromisoformat(str(stamp).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def log_prompts(root):
    """`.claude/session-log.md` -> [(datetime UTC, prompt em uma linha)].

    O formato é o do `session-log.py`: `## AAAA-MM-DD` agrupa o dia e
    `### HH:MM:SS UTC` abre cada prompt."""
    path = os.path.join(root, ".claude", "session-log.md")
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            texto = fh.read()
    except OSError:
        return []
    out, dia, quando, corpo = [], None, None, []

    def fecha():
        t = " ".join(" ".join(corpo).split())
        if quando is not None and t:
            out.append((quando, t))

    for linha in texto.splitlines():
        m = re.match(r"^## (\d{4}-\d{2}-\d{2})\s*$", linha)
        if m:
            fecha()
            dia, quando, corpo = m.group(1), None, []
            continue
        m = re.match(r"^### (\d{2}:\d{2}:\d{2}) UTC\s*$", linha)
        if m:
            fecha()
            quando, corpo = _iso(f"{dia}T{m.group(1)}Z") if dia else None, []
            continue
        # o `# Session log` do topo cai aqui antes do 1º `###` e é descartado
        # pelo `fecha()`; dentro de um prompt, `# título` é texto do dono
        corpo.append(linha)
    fecha()
    return out


def inicio_da_sessao(root, session_id):
    """Quando ESTA sessão começou, pelo registro de sessões (clone principal).

    O log de prompts é por worktree e atravessa sessões; sem o início, "os
    primeiros prompts" seriam os de uma sessão de semanas atrás."""
    if not session_id:
        return None
    try:
        import _wtlib as L
        entrada = L.find_entry(L.main_root(root), session_id) or {}
    except Exception:  # noqa: BLE001
        return None
    return _iso(entrada.get("started_at", ""))


def primeiros_prompts(root, session_id, prompt_atual):
    """Os PRIMEIROS prompts desta sessão, cortados. Sem o início registrado,
    cai para os prompts de hoje (UTC). O prompt do turno entra se o log ainda
    não o tem: os hooks do mesmo evento não têm ordem garantida."""
    prompts = log_prompts(root)
    inicio = inicio_da_sessao(root, session_id)
    if inicio is not None:
        prompts = [t for q, t in prompts if q >= inicio]
    else:
        hoje = datetime.now(timezone.utc).date()
        prompts = [t for q, t in prompts if q.date() == hoje]
    atual = " ".join(str(prompt_atual or "").split())
    if atual and (not prompts or prompts[-1] != atual):
        prompts.append(atual)
    return [corta(t, CORTE_PROMPT) for t in prompts[:PRIMEIROS]]


def corta(texto, n):
    t = " ".join(str(texto or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def turnos_desde(root, stamp):
    """Prompts do log a partir de `stamp`: há quantos turnos o cursor parou."""
    desde = _iso(stamp)
    if desde is None:
        return None
    return sum(1 for q, _ in log_prompts(root) if q >= desde)


def mesma_sessao(gravada, atual):
    """O arquivo pode guardar o id cortado (8 caracteres); prefixo basta."""
    g, a = str(gravada or "").strip(), str(atual or "").strip()
    if not g or not a:
        return True  # sem como comparar, não acusa outra sessão
    return g.startswith(a) or a.startswith(g)


def linhas_intencao(root, payload, tem_modo):
    """As até duas linhas de intenção deste turno, ou [] (silêncio)."""
    if read_intent is None:
        return []
    intent = read_intent(root)
    plano = (intent or {}).get("plano")
    if not intent or not intent.get("proposito") or not isinstance(plano, list) or not plano:
        if not tem_modo:
            return []
        prompts = primeiros_prompts(root, payload.get("session_id"),
                                    payload.get("prompt"))
        lista = " | ".join(f'"{t}"' for t in prompts) or "nenhum ainda"
        return [
            "[intenção] Esta sessão ainda não tem intenção gravada. "
            f"Primeiros prompts: {lista}.",
            "Se este prompt tem conteúdo, proponha em três linhas (propósito, para "
            "quando, plano numerado), grave com `cepa-intencao gravar --proposito "
            '"..." --para-quando "..." --plano "passo 1" "passo 2"`, e feche com: a '
            "qualquer momento `/common:whereami` mostra onde estamos. Se o prompt é "
            "trivial ou um comando de abertura, não proponha ainda.",
        ]

    prop = corta(intent["proposito"], CORTE_PROPOSITO)
    if not mesma_sessao(intent.get("session_id"), payload.get("session_id")):
        quando = _iso(intent.get("aberto_em", ""))
        data = quando.strftime("%Y-%m-%d %H:%M UTC") if quando else "data desconhecida"
        return [
            f"[intenção] Intenção de {data}, gravada em outra sessão: \"{prop}\". "
            "Não a trate como a desta sessão.",
            "Pergunte ao dono: continuo ou abro nova? Continuar = `cepa-intencao "
            "continuar`; abrir nova = `cepa-intencao gravar ... --motivo \"...\"`.",
        ]

    m = len(plano)
    passo = intent.get("passo")
    if not isinstance(passo, int) or not 1 <= passo <= m + 1:
        passo = 1
    if passo > m:
        para = corta(intent.get("para_quando"), CORTE_PROPOSITO)
        return [f"[intenção] {prop}. Plano cumprido ({m}/{m})"
                + (f"; ponto de parada: {para}" if para else "")
                + ". Próximo: hora de /common:wrap-up."]
    k = turnos_desde(root, intent.get("passo_desde"))
    idade = f" (há {k} turno{'s' if k != 1 else ''})" if k is not None else ""
    nome = corta(plano[passo - 1], CORTE_PASSO)
    prox = (corta(plano[passo], CORTE_PASSO) if passo < m
            else "plano cumprido: hora de /common:wrap-up")
    return [
        f"[intenção] {prop}. Passo {passo}/{m}: {nome}{idade}. Próximo: {prox}.",
        f"Ao concluir o passo, rode `cepa-intencao --passo {passo + 1}`.",
    ]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        sys.exit(0)

    try:
        if os.environ.get("CEPA_MODO", "on") == "off":
            sys.exit(0)

        cwd = payload.get("cwd") or os.getcwd()
        root = repo_root(cwd)
        mode = read_mode(root)

        blocos = []
        if mode:
            nome = mode["modo"]
            linhas = [f"[modo] Esta sessão opera em **{nome}**."]
            if mode.get("orcamento"):
                linhas.append(f"Orçamento declarado: {mode['orcamento']}.")
            if nome in SAIDA:
                linhas.append(f"Fecha quando: {SAIDA[nome]}.")
            linhas.append(
                "Ação fora deste modo NÃO vira pergunta e NÃO vira trabalho agora: "
                "registre pelo skill `off-mode-capture` e siga. As capturas entram "
                "no relatório final."
            )
            blocos.append(" ".join(linhas))

        if not os.environ.get(ENV_JANELA):
            try:
                blocos += linhas_intencao(root, payload, bool(mode))
            except Exception as e:  # noqa: BLE001 — intenção nunca derruba o modo
                print(f"[session-mode] intenção: {e}", file=sys.stderr)

        if not blocos:
            sys.exit(0)
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(blocos),
        }}))
    except Exception as e:  # noqa: BLE001
        print(f"[session-mode] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
