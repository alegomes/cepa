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
"""
from __future__ import annotations

import glob
import os
import re
from datetime import date

DIR = ".claude/waivers"

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


def gravar(repo: str, motivo: str, escopo: str, razao: str, autor: str,
           revisit_trigger: str, hoje: date | None = None) -> str:
    """Grava a decisão do humano. Todo campo é obrigatório — inclusive o
    gatilho de revisita: dispensa sem prazo nem condição é dispensa para sempre,
    e ninguém decidiu isso."""
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
