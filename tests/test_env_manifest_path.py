#!/usr/bin/env python3
"""Regressão do leitor do manifesto de ambiente (`common/hooks/_wtlib.py`).

Sem dependências — rode com `python3 tests/test_env_manifest_path.py`.
Sai não-zero em falha.

## O que este arquivo existe para segurar

O manifesto de ambiente declara o runtime do projeto: portas, como subir o app,
healthcheck, e a lista `seed:` de arquivos gitignored que uma worktree nova
precisa receber para funcionar (`.env`, credenciais locais). Quem lê é a
semeadura de worktree (`seed-worktree.py`, `/common:worktree-start`) e o gate de
tela, quando o `up:` dele diz `env.yaml`.

Ele morava em `.claude/env.yaml` até 22/08/2026 — e `.claude/` é gitignored nos
projetos que usam o harness, então o manifesto era invisível para o git e sumia
com a worktree descartável da sessão. Agora o lugar é `docs/env.yaml`, e o
antigo continua sendo lido.

**Aqui não há hook para travar o destino, e isso é uma diferença real** em
relação ao veredito de prova e ao manifesto de prova de UI: aqueles dois são
escritos por um agente, então um hook consegue barrar a escrita no lugar errado.
Este é declarado à mão pelo dono do projeto — não existe escrita para barrar. A
ordem de leitura testada abaixo é a ÚNICA mecânica que move a convenção, o que a
torna a única coisa que pode quebrá-la em silêncio: se a preferência inverter, o
projeto que moveu o arquivo passa a ser semeado pela declaração velha, e uma
worktree nasce sem os arquivos que o `seed:` novo listava.

## Perturbação (como saber que este teste prova algo)

Inverta a ordem de `ENV_MANIFEST_PATHS` e o caso "os dois → docs ganha" fica
vermelho.
"""

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("wtlib", REPO / "common" / "hooks" / "_wtlib.py")
wtlib = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wtlib)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def repo_com(**manifestos):
    """Cria um repo temporário com os manifestos pedidos: docs=..., claude=..."""
    root = tempfile.mkdtemp()
    for onde, conteudo in manifestos.items():
        d = os.path.join(root, "docs" if onde == "docs" else ".claude")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "env.yaml"), "w") as fh:
            fh.write(conteudo)
    return root


NOVO = "ports:\n  - 8083\nseed:\n  - .env\n  - novo.local\n"
ANTIGO = "ports:\n  - 9999\nseed:\n  - .env\n  - antigo.local\n"

# ── precedência ───────────────────────────────────────────────────────────
r = repo_com(docs=NOVO, claude=ANTIGO)
check("os dois no disco → docs/env.yaml ganha",
      wtlib.env_manifest_list(r, "seed") == [".env", "novo.local"],
      wtlib.env_manifest_list(r, "seed"))
check("…e o caminho devolvido é o de docs/",
      str(wtlib.env_manifest_path(r)).endswith("docs/env.yaml"),
      str(wtlib.env_manifest_path(r)))

r = repo_com(claude=ANTIGO)
check("só o antigo → segue sendo lido (repo que ainda não moveu)",
      wtlib.env_manifest_list(r, "seed") == [".env", "antigo.local"],
      wtlib.env_manifest_list(r, "seed"))

r = repo_com(docs=NOVO)
check("só o novo → lido", wtlib.env_manifest_list(r, "seed") == [".env", "novo.local"],
      wtlib.env_manifest_list(r, "seed"))

# ── ausência e lixo: fail-silent, como todo o caminho de semeadura ────────
r = tempfile.mkdtemp()
check("nenhum manifesto → lista vazia, sem exceção",
      wtlib.env_manifest_list(r, "seed") == [], wtlib.env_manifest_list(r, "seed"))
check("nenhum manifesto → caminho None", wtlib.env_manifest_path(r) is None)

r = repo_com(docs=":::: isto não é yaml ::::\n")
check("manifesto ilegível → lista vazia, nunca estoura",
      wtlib.env_manifest_list(r, "seed") == [], wtlib.env_manifest_list(r, "seed"))

r = repo_com(docs=NOVO)
check("chave ausente → lista vazia",
      wtlib.env_manifest_list(r, "inexistente") == [])

# ── as duas formas de lista que o parser tolerante aceita ─────────────────
r = repo_com(docs="seed: [.env, cred.local]\n")
check("lista inline → lida", wtlib.env_manifest_list(r, "seed") == [".env", "cred.local"],
      wtlib.env_manifest_list(r, "seed"))

r = repo_com(docs="ports:\n  - 8083\nseed:\n  - .env   # comentário\n")
check("comentário no fim da linha → removido",
      wtlib.env_manifest_list(r, "seed") == [".env"], wtlib.env_manifest_list(r, "seed"))

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all env-manifest path tests passed")
