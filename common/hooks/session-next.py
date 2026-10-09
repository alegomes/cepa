#!/usr/bin/env python3
"""Grava o próximo passo do encadeamento a partir do handoff (CS-4 do ciclo cepa-espiral-c1).

Quem chama é o passo L7 do `/common:wrap-up`. Lê a zona NOTE do handoff
(`<!-- HANDOFF:NOTE -->…<!-- /HANDOFF:NOTE -->`) e procura a linha

    **Próximo:** repo=<caminho> modo=<modo> comando=<comando e argumentos>

Achou: escreve `<raiz-principal>/.claude/sessions/<session_id>.next.json` com
`repo`, `modo`, `comando` e `brief`, onde o brief é o parágrafo da seção
`## Próximo passo` da mesma zona. É o arquivo que o launcher `cepa` lê quando
a sessão sai (`session-chain.py`, CS-3) para abrir a seguinte sem o dono digitar.

Sem a linha, não escreve nada e diz isso: handoff sem `Próximo:` continua
válido, a sessão só não encadeia. Linha presente mas inutilizável (repo que não
existe, modo desconhecido, brief vazio) também não escreve, e diz o motivo: um
arquivo que o launcher recusaria apagaria o próximo passo em silêncio.

Uso: session-next.py --handoff <arquivo> --session-id <id> [--root <raiz>]
Saída: exit 0 escreveu ou não havia linha; exit 2 a linha existe e não serve.
A primeira linha do stdout é o que vai no relatório do wrap-up.
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _modos  # noqa: E402
import _wtlib as L  # noqa: E402

NOTE_RE = re.compile(r"<!-- HANDOFF:NOTE -->(.*?)<!-- /HANDOFF:NOTE -->", re.S)
LINHA_RE = re.compile(r"^\s*\*\*Próximo:\*\*\s*(.*)$", re.M)
CHAVE_RE = re.compile(r"(?:^|\s)(repo|modo|comando)=")
SECAO_RE = re.compile(r"^##\s+Próximo passo\s*$", re.M)


def note_zone(texto: str) -> str:
    m = NOTE_RE.search(texto)
    return m.group(1) if m else ""


def parse_linha(resto: str) -> dict:
    """`repo=… modo=… comando=…` → dict. O comando leva o resto até a próxima
    chave, porque carrega argumentos com espaço (`/common:epic contratos`)."""
    achados = list(CHAVE_RE.finditer(resto))
    campos = {}
    for i, m in enumerate(achados):
        fim = achados[i + 1].start() if i + 1 < len(achados) else len(resto)
        campos[m.group(1)] = resto[m.end():fim].strip()
    return campos


def brief_da_secao(note: str) -> str:
    """O parágrafo de `## Próximo passo`, sem a linha `**Próximo:**`."""
    m = SECAO_RE.search(note)
    if not m:
        return ""
    corpo = note[m.end():]
    prox = re.search(r"^##\s", corpo, re.M)
    if prox:
        corpo = corpo[:prox.start()]
    corpo = LINHA_RE.sub("", corpo)
    return corpo.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handoff", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument("--root")
    a = ap.parse_args()

    try:
        texto = open(a.handoff, encoding="utf-8").read()
    except OSError as e:
        print(f"próximo passo não gravado: handoff ilegível ({e})")
        return 2
    note = note_zone(texto)
    m = LINHA_RE.search(note)
    if not m:
        print("próximo passo não gravado: o handoff não tem a linha `**Próximo:**` "
              "na zona NOTE, então a sessão seguinte não abre sozinha")
        return 0

    campos = parse_linha(m.group(1))
    repo, modo, comando = campos.get("repo", ""), campos.get("modo", ""), campos.get("comando", "")
    brief = brief_da_secao(note)
    faltas = [k for k, v in (("repo", repo), ("modo", modo), ("comando", comando)) if not v]
    if faltas:
        motivo = f"a linha `**Próximo:**` não traz {', '.join(faltas)}"
    elif not os.path.isdir(repo):
        motivo = f"repo {repo} não existe"
    elif modo not in _modos.MODOS:
        motivo = f"modo {modo} não é um dos modos ({' '.join(_modos.MODOS)})"
    elif modo == "reforma":
        motivo = "modo reforma exige --orcamento, que o encadeamento não passa"
    elif not brief:
        motivo = "a seção `## Próximo passo` está vazia ou não existe"
    else:
        motivo = ""
    if motivo:
        print(f"próximo passo não gravado: {motivo}")
        return 2

    root = a.root or L.main_root(os.getcwd())
    if not root:
        print("próximo passo não gravado: raiz do repositório não encontrada")
        return 2
    d = L.sessions_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    alvo = d / f"{a.session_id}.next.json"
    alvo.write_text(json.dumps({"repo": repo, "modo": modo, "comando": comando,
                                "brief": brief}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"próximo passo gravado em {alvo}: ao sair, o cepa abre {repo} "
          f"no modo {modo} ({comando})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
