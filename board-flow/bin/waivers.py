#!/usr/bin/env python3
"""Dispensas do humano: leitura, casamento e gravação de `.claude/waivers/`.

Por que existe: sem isto, a fila repete a mesma pergunta toda semana. "O dublê
da PlugSign engole o sinal, aceito a prova interna?" volta em todo card que
toca aquele adapter, e a resposta dada da última vez morre no chat que a
produziu.

Quem dispensa é SEMPRE o humano. O `proof-reviewer` continua sem poder dispensar
nada e o artefato da prova continua sem campo para isso — a dispensa mora aqui
fora, com autor, data e gatilho de revisita, e é auditável. Ver a seção "Verdict
routing" em build-hex/agents/proof-reviewer.md.

Um waiver casa por MOTIVO + ESCOPO, nunca por card: casar por card não
economizaria pergunta nenhuma (todo card é novo), e casar só por motivo
dispensaria o adapter inteiro do projeto por causa de uma resposta sobre uma
classe.

Em run autônomo (`claude -p` do `cepa-until`, ou /common:autonomous-start) NÃO
existe dono na frente do agente. Uma dispensa gravada ali é o agente dispensando
prova em nome do dono (fb-20261014-3: um run gravou `autor: alegomes` sozinho).
Por isso, nesse modo `gravar` vira `propor`: o arquivo nasce como PROPOSTA
(`status: proposta`, `autor: null`), `carregar` não a enxerga, e só o
`cepa-plan responde` do dono, num terminal, a converte em dispensa
(`converter`). Gêmeo inline da conversão: `common/bin/cepa-plan` (`cmd_responde`).
"""
from __future__ import annotations

import glob
import os
import re
from datetime import date

DIR = ".claude/waivers"

STATUS_SEM_EFEITO = ("proposta", "recusada")

CAMPOS = ("motivo", "escopo", "razao", "autor", "criado_em", "revisit_trigger")


def caminho(repo: str, motivo: str, escopo: str) -> str:
    return os.path.join(repo, DIR, f"{motivo}--{_slug(escopo)}.yaml")


def _slug(texto: str) -> str:
    """Nome de arquivo legível."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", (texto or "").strip())
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "sem-escopo"


def _chave(texto: str) -> str:
    """A chave de casamento, mais frouxa que o nome do arquivo de propósito:
    `PlugSignAdapter`, `PlugSign Adapter` e `plugsign-adapter` são o MESMO
    escopo. Se cada grafia virasse uma dispensa própria, a pergunta voltaria —
    que é o defeito que este arquivo existe para eliminar."""
    return re.sub(r"[^a-z0-9]+", "", (texto or "").lower())


def em_run_autonomo(env=None) -> bool:
    """True quando o processo é um run sem dono na frente: `CEPA_UNTIL_RUN`
    (posto pelo `cepa-until` em todo `claude -p`) ou `CLAUDE_AUTONOMOUS_RUN_ID`
    (posto pelo /common:autonomous-start)."""
    env = os.environ if env is None else env
    return bool(env.get("CEPA_UNTIL_RUN") or env.get("CLAUDE_AUTONOMOUS_RUN_ID"))


def carregar(repo: str) -> list[dict]:
    """Todo waiver do repo. Arquivo sem os campos obrigatórios é IGNORADO.

    Ignorar é o lado seguro: um waiver malformado que valesse dispensaria uma
    prova sem ninguém conseguir dizer quem dispensou nem até quando.
    """
    import yaml

    fora = []
    for path in sorted(glob.glob(os.path.join(repo, DIR, "*.yaml"))):
        with open(path) as fh:
            d = yaml.safe_load(fh)
        if not isinstance(d, dict):
            continue
        # Proposta e recusa nunca dispensam, mesmo se alguém preencher `autor`:
        # só a conversão pelo dono tira o `status`.
        if d.get("status") in STATUS_SEM_EFEITO:
            continue
        if any(not d.get(c) for c in CAMPOS):
            continue
        d["_path"] = path
        fora.append(d)
    return fora


def vencido(waiver: dict, hoje: date | None = None) -> bool:
    """Só vence por DATA. `revisit_trigger` em prosa ("quando o adapter mudar")
    não é verificável por código: ele é mostrado ao humano, nunca avaliado
    aqui — inventar uma avaliação seria dispensar por conta própria."""
    gatilho = str(waiver.get("revisit_trigger") or "")
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", gatilho)
    if not m:
        return False
    return (hoje or date.today()).isoformat() > m.group(0)


def casa(waiver: dict, motivo: str, escopo: str) -> bool:
    """Mesmo motivo E mesmo escopo, comparando por `_chave` — senão
    "PlugSignAdapter" e "plugsign adapter" viram duas dispensas da mesma coisa."""
    return (waiver.get("motivo") == motivo
            and _chave(str(waiver.get("escopo"))) == _chave(escopo))


def aplicavel(waivers: list[dict], motivo: str, escopo: str,
              hoje: date | None = None) -> dict | None:
    """O waiver que dispensa esta pergunta, ou None se ela precisa ser feita.

    Vencido não dispensa: volta a ser pergunta, e quem chama diz que venceu.
    """
    for w in waivers:
        if casa(w, motivo, escopo) and not vencido(w, hoje):
            return w
    return None


def _le(path: str):
    import yaml

    try:
        with open(path) as fh:
            d = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError):
        return None
    return d if isinstance(d, dict) else None


def _escreve(path: str, d: dict) -> None:
    import yaml

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        yaml.safe_dump(d, fh, allow_unicode=True, sort_keys=False)


def _dispensa_valida(d) -> bool:
    return (isinstance(d, dict) and d.get("status") not in STATUS_SEM_EFEITO
            and all(d.get(c) for c in CAMPOS))


def propor(repo: str, motivo: str, escopo: str, razao: str,
           revisit_trigger: str, proposto_por: str, hoje: date | None = None,
           fila: str | None = None, item: str | None = None,
           pergunta: str | None = None) -> str:
    """Grava uma PROPOSTA de dispensa: uma pergunta ao dono, não uma decisão.

    Mesmo caminho do waiver (`caminho`), mas `status: proposta` e `autor: null`
    explícito — o dono ainda não decidiu. `carregar` a ignora. Se nesse caminho
    já existe uma dispensa VÁLIDA ou uma proposta `recusada`, o dono já decidiu:
    devolve o caminho sem tocar no arquivo. A recusa vale até o dono apagar ou
    editar o arquivo — um run repropor o que o dono recusou é o mesmo padrão de
    fb-20261014-3. Só proposta pendente antiga é sobrescrita.
    """
    faltando = [n for n, v in (("razao", razao), ("proposto_por", proposto_por),
                               ("revisit_trigger", revisit_trigger),
                               ("escopo", escopo), ("motivo", motivo)) if not v]
    if faltando:
        raise ValueError(f"proposta sem {', '.join(faltando)} — não gravo")

    destino = caminho(repo, motivo, escopo)
    existente = _le(destino)
    if _dispensa_valida(existente) or (
            isinstance(existente, dict) and existente.get("status") == "recusada"):
        return destino

    por = proposto_por
    run_id = os.environ.get("CLAUDE_AUTONOMOUS_RUN_ID")
    if run_id and run_id not in por:
        por = f"{por} (run {run_id})"
    d = {
        "status": "proposta",
        "motivo": motivo,
        "escopo": escopo,
        "razao": razao,
        "revisit_trigger": revisit_trigger,
        "autor": None,
        "proposto_por": por,
        "proposto_em": (hoje or date.today()).isoformat(),
        "pergunta": " ".join((pergunta or
                              f"Aceito a dispensa de {escopo} ({motivo}) por: {razao}?"
                              ).split()),
    }
    if fila:
        d["fila"] = fila
    if item:
        d["item"] = str(item)
    _escreve(destino, d)
    return destino


def propostas(repo: str) -> list[dict]:
    """Toda proposta pendente (`status: proposta`), por caminho."""
    fora = []
    for path in sorted(glob.glob(os.path.join(repo, DIR, "*.yaml"))):
        d = _le(path)
        if d and d.get("status") == "proposta":
            d["_path"] = path
            fora.append(d)
    return fora


def converter(repo: str, motivo: str, escopo: str, autor: str,
              resposta: str | None = None, hoje: date | None = None) -> str:
    """O dono aceitou: a proposta vira dispensa. Ato do dono, nunca do agente."""
    if em_run_autonomo():
        raise PermissionError("converter proposta em dispensa é ato do dono; "
                              "em run autônomo não há dono — não converto")
    if not autor or not str(autor).strip():
        raise ValueError("dispensa sem autor — não converto")
    destino = caminho(repo, motivo, escopo)
    d = _le(destino)
    if d is None:
        raise FileNotFoundError(f"não há proposta em {destino}")
    if d.get("status") != "proposta":
        if _dispensa_valida(d):
            raise ValueError(f"{destino} já é uma dispensa — nada a converter")
        raise FileNotFoundError(f"não há proposta em {destino}")
    novo = {k: v for k, v in d.items() if k not in ("status", "autor")}
    novo["autor"] = autor
    novo["criado_em"] = (hoje or date.today()).isoformat()
    if resposta:
        novo["resposta_do_dono"] = resposta
    _escreve(destino, novo)
    return destino


def recusar(repo: str, motivo: str, escopo: str, resposta: str,
            hoje: date | None = None) -> str:
    """O dono recusou: a proposta fica registrada como `recusada`, sem efeito."""
    if em_run_autonomo():
        raise PermissionError("recusar proposta é ato do dono; em run autônomo "
                              "não há dono — não recuso")
    destino = caminho(repo, motivo, escopo)
    d = _le(destino)
    if d is None or d.get("status") != "proposta":
        raise FileNotFoundError(f"não há proposta em {destino}")
    d["status"] = "recusada"
    d["recusada_em"] = (hoje or date.today()).isoformat()
    d["resposta_do_dono"] = resposta
    _escreve(destino, d)
    return destino


def gravar(repo: str, motivo: str, escopo: str, razao: str, autor: str,
           revisit_trigger: str, hoje: date | None = None,
           fila: str | None = None, item: str | None = None) -> str:
    """Grava a decisão do humano. Todo campo é obrigatório — inclusive o
    gatilho de revisita: dispensa sem prazo nem condição é dispensa para sempre,
    e ninguém decidiu isso.

    Em run autônomo (`em_run_autonomo()`) NÃO grava dispensa: grava uma proposta
    (`propor`) e devolve o caminho dela. O agente de um `claude -p` não tem dono
    na frente; uma dispensa gravada ali é o agente dispensando prova em nome do
    dono (fb-20261014-3, `autor: alegomes` escrito sozinho). Não há parâmetro que
    force a dispensa real nesse modo — de propósito. `fila`/`item` amarram a
    proposta ao item da fila para o `cepa-plan responde` achá-la."""
    if em_run_autonomo():
        for n, v in (("razao", razao), ("autor", autor),
                     ("revisit_trigger", revisit_trigger),
                     ("escopo", escopo), ("motivo", motivo)):
            if not v:
                raise ValueError(f"waiver sem {n} — não gravo")
        return propor(repo, motivo, escopo, razao, revisit_trigger,
                      proposto_por=f"agente em run autônomo, em nome de {autor}",
                      hoje=hoje, fila=fila, item=item)

    import yaml

    faltando = [n for n, v in (("razao", razao), ("autor", autor),
                               ("revisit_trigger", revisit_trigger),
                               ("escopo", escopo), ("motivo", motivo)) if not v]
    if faltando:
        raise ValueError(f"waiver sem {', '.join(faltando)} — não gravo")

    destino = caminho(repo, motivo, escopo)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w") as fh:
        yaml.safe_dump({
            "motivo": motivo,
            "escopo": escopo,
            "razao": razao,
            "autor": autor,
            "criado_em": (hoje or date.today()).isoformat(),
            "revisit_trigger": revisit_trigger,
        }, fh, allow_unicode=True, sort_keys=False)
    return destino
