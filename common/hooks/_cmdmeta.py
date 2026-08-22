#!/usr/bin/env python3
"""Resolve o ARQUIVO de um comando de plugin e lê o frontmatter dele.

Dois hooks precisam da mesma resposta para a mesma pergunta — "qual arquivo .md
é este comando, e o que diz o campo `interaction:` dele?":

  - session-routine-guard.py  recusa /common:session sobre um comando
    `conversational`;
  - default-yes-inject.py     injeta a política default-yes quando o comando é
    `routine`.

Duplicar a resolução seria pior do que parece. Ela tem uma armadilha que já
mordeu uma vez (junho/2026, no session-routine-guard): o cache do Claude Code
guarda as versões lado a lado — cache/cepa/common/1.4.0, 1.5.0, 1.6.0 — e uma
varredura em ordem alfabética lê a versão VELHA, anterior ao campo, e responde
com confiança a coisa errada. Duas cópias da resolução são duas chances de a
correção existir só em uma.

Ordem de busca, do mais autoritativo para o menos:

  1. installed_plugins.json do CC — é quem sabe qual cópia está viva;
  2. o proprio CLAUDE_PLUGIN_ROOT, quando o plugin pedido é o dono do hook;
  3. varredura, da MAIOR versão para a menor (nunca alfabética).

O plugin dono casa pelo NOME declarado no manifest, não pelo diretório:
`capture.md` existe em board-flow E em discovery, e o plugin `docs` mora no
diretório `docs-topology/`.

Todas as funções falham devolvendo None. Quem chama decide o que fazer com o
"não sei" — e nos dois hooks de hoje "não sei" significa não interferir.
"""

import json
import os
import re
from pathlib import Path

FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
INTERACTION_RE = re.compile(
    r"^interaction\s*:\s*[\"']?([A-Za-z-]+)[\"']?\s*$", re.MULTILINE
)

# O vocabulário fechado do campo. Qualquer outro valor é tratado como
# desconhecido — e desconhecido nunca ativa política nenhuma.
ROUTINE = "routine"
CONVERSATIONAL = "conversational"
VALORES = (ROUTINE, CONVERSATIONAL)


def bases():
    """Diretórios onde procurar os plugins, no repo e no cache instalado.

    No repo,  CLAUDE_PLUGIN_ROOT = <repo>/common               → irmãos em <repo>/
    No cache, CLAUDE_PLUGIN_ROOT = <cache>/cepa/common/2.2.0   → irmãos dois
    níveis acima, cada um com o seu próprio diretório de versão.
    """
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return []
    p = Path(root)
    return [d for d in (p.parent, p.parent.parent) if d and d.is_dir()]


def nome_do_plugin(cmd_file: Path):
    """O nome declarado no manifest do plugin dono deste arquivo de comando."""
    for pai in cmd_file.parents:
        mf = pai / ".claude-plugin" / "plugin.json"
        if mf.is_file():
            try:
                return json.loads(mf.read_text(encoding="utf-8")).get("name")
            except Exception:  # noqa: BLE001
                return None
    return None


def raiz_instalada(plugin: str):
    """A cópia que o CC diz estar viva, segundo o installed_plugins.json.

    O nome do marketplace não é assumido: casa-se `<plugin>@` seja qual for o
    sufixo.
    """
    reg = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    try:
        d = json.loads(reg.read_text(encoding="utf-8")).get("plugins", {})
    except Exception:  # noqa: BLE001
        return None
    for chave, entradas in d.items():
        if not chave.startswith(f"{plugin}@") or not entradas:
            continue
        caminho = entradas[0].get("installPath")
        if caminho and (Path(caminho) / "commands").is_dir():
            return Path(caminho)
    return None


def versao_do(cand: Path):
    """Chave de ordenação: a maior versão primeiro, o resto depois."""
    for pai in cand.parents:
        partes = pai.name.split(".")
        if len(partes) == 3 and all(x.isdigit() for x in partes):
            return tuple(int(x) for x in partes)
    return (0, 0, 0)


def acha_comando(plugin: str, cmd: str):
    """O arquivo .md de `<plugin>:<cmd>`, ou None se não der para saber."""
    # 1. A cópia que o CC declara viva.
    raiz = raiz_instalada(plugin)
    if raiz:
        f = raiz / "commands" / f"{cmd}.md"
        if f.is_file() and nome_do_plugin(f) == plugin:
            return f

    # 2. A raiz de onde o hook está rodando, quando o alvo é este plugin.
    aqui = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if aqui:
        f = Path(aqui) / "commands" / f"{cmd}.md"
        if f.is_file() and nome_do_plugin(f) == plugin:
            return f

    # 3. Varredura, da maior versão para a menor — nunca em ordem alfabética.
    for base in bases():
        for padrao in (f"{plugin}*/commands/{cmd}.md",
                       f"{plugin}*/*/commands/{cmd}.md",
                       f"*/commands/{cmd}.md",
                       f"*/*/commands/{cmd}.md"):
            achados = [c for c in base.glob(padrao) if nome_do_plugin(c) == plugin]
            if achados:
                return max(achados, key=versao_do)
    return None


def interaction(cmd_file: Path):
    """O valor do campo `interaction:` do frontmatter, em minúsculas.

    None quando o arquivo não abre, não tem frontmatter, ou não declara o campo.
    """
    try:
        texto = cmd_file.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return None
    m = FRONTMATTER_RE.match(texto)
    if not m:
        return None
    achado = INTERACTION_RE.search(m.group(1))
    return achado.group(1).lower() if achado else None
