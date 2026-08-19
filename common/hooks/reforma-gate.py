#!/usr/bin/env python3
"""Gate do modo Reforma: bloqueia editar teste EXTERNO enquanto a reforma corre.

A condição de saída da Reforma tem três partes (docs/modos-de-trabalho.md):
o orçamento declarado exaurido, build verde, e nenhum teste externo editado.
As duas primeiras ninguém consegue medir sozinho — orçamento é texto livre e
build verde já tem o green-or-revert. A terceira é mecânica, e é a que importa:

    reforma reorganiza o código SEM mudar o comportamento observável.
    Se o teste que já passava precisou mudar, o comportamento mudou.
    Então não era reforma — era construção, e construção exige critério de
    aceite e teste vermelho ANTES (a fronteira que o modo existe para cobrar).

Bloqueia em vez de avisar de propósito: o aviso chega depois do vazamento, que
é exatamente o que os modos existem para impedir. A saída não é forçar o
bloqueio — é encerrar a reforma e abrir a construção com critério.

Teste INTERNO segue livre: renomear uma classe obriga a mexer no teste de
unidade dela, e isso é reforma legítima. A distinção mora nos padrões abaixo,
sobrescritíveis por repo em `.claude/external-tests` (um glob por linha).

Silencioso fora do modo reforma. Desliga com CEPA_MODO=off.
"""

import fnmatch
import json
import os
import re
import subprocess
import sys

# Testes que asseguram comportamento observável de fora. Um repo com outro
# arranjo sobrescreve a lista em .claude/external-tests.
DEFAULT_EXTERNOS = [
    "*IT.java", "*ITCase.java", "*IntegrationTest*", "*E2E*", "*e2e*",
    "*/e2e/*", "*/integration/*", "*/integration-tests/*",
    "*/cypress/*", "*/playwright/*",
    "*_e2e_test.*", "test_e2e_*", "*/acceptance/*", "*AcceptanceTest*",
]

# `>` e `>>` que não sejam `>&` nem `>=`; o `>=` já custou um falso bloqueio
# neste repo (bash-path-lock), então a exclusão fica explícita.
_REDIR = re.compile(r"""(?<![0-9&])>>?\s*(?![&=])("[^"]+"|'[^']+'|[^\s;&|<>()]+)""")
# Editores que gravam sem redirecionar — o caminho por onde um bloqueio de
# Write vaza se ninguém olhar o Bash.
_INPLACE = re.compile(
    r"\b(?:sed\s+(?:-[^\s]*\s+)*-i|perl\s+-[^\s]*i|tee|cp|mv|install)\b\s+(.+)"
)


def repo_root(cwd):
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else cwd
    except Exception:  # noqa: BLE001
        return cwd


def modo_ativo(root):
    path = os.path.join(root, ".claude", "session-mode")
    if not os.path.isfile(path):
        return None, None
    modo = orc = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                k, _, v = line.partition(":")
                v = v.strip().strip('"')
                if k.strip() == "modo":
                    modo = v or None
                elif k.strip() == "orcamento" and v not in ("null", ""):
                    orc = v
    except Exception:  # noqa: BLE001
        return None, None
    return modo, orc


def padroes(root):
    override = os.path.join(root, ".claude", "external-tests")
    if os.path.isfile(override):
        try:
            with open(override, encoding="utf-8") as fh:
                pats = [ln.strip() for ln in fh
                        if ln.strip() and not ln.lstrip().startswith("#")]
            if pats:
                return pats
        except Exception:  # noqa: BLE001
            pass
    return DEFAULT_EXTERNOS


def eh_teste_externo(path, pats):
    p = path.replace("\\", "/")
    # "/" na frente para que um padrão de diretório (*/cypress/*) também case
    # quando o diretório está na RAIZ do repo — sem isso, `cypress/x.cy.js`
    # escapa e `a/cypress/x.cy.js` não, o que é o pior tipo de gate: o que
    # pega alguns casos e dá a impressão de cobrir todos.
    formas = {p, "/" + p.lstrip("/"), os.path.basename(p)}
    return next((pat for pat in pats
                 if any(fnmatch.fnmatch(f, pat) for f in formas)), None)


def alvos(tool, inp):
    """Caminhos que esta chamada vai escrever."""
    if tool in ("Edit", "Write", "NotebookEdit"):
        t = inp.get("file_path") or inp.get("notebook_path")
        return [t] if t else []
    if tool == "MultiEdit":
        t = inp.get("file_path")
        return [t] if t else []
    if tool == "Bash":
        cmd = inp.get("command") or ""
        found = [m.group(1).strip("\"'") for m in _REDIR.finditer(cmd)]
        for m in _INPLACE.finditer(cmd):
            found += [tok.strip("\"'") for tok in m.group(1).split()
                      if not tok.startswith("-")]
        return found
    return []


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
        modo, orc = modo_ativo(root)
        if modo != "reforma":
            sys.exit(0)

        pats = padroes(root)
        for alvo in alvos(payload.get("tool_name", ""),
                          payload.get("tool_input", {}) or {}):
            pat = eh_teste_externo(alvo, pats)
            if not pat:
                continue
            print(
                f"[reforma-gate] BLOQUEADO: esta sessão está em modo reforma e "
                f"você ia editar um teste externo.\n"
                f"  Alvo: {alvo}   (casou com o padrão {pat!r})\n"
                + (f"  Orçamento da reforma: {orc}\n" if orc else "")
                + f"  Reforma reorganiza o código SEM mudar comportamento "
                f"observável. Se o teste que já passava precisa mudar, o "
                f"comportamento mudou — isso é construção, não reforma, e "
                f"construção exige critério de aceite e teste vermelho ANTES.\n"
                f"  O que fazer: registre isto pelo skill off-mode-capture e "
                f"siga a reforma; ou encerre a reforma e abra uma sessão de "
                f"construção com o critério escrito.\n"
                f"  Se este arquivo não é um teste externo, corrija a lista em "
                f".claude/external-tests (um glob por linha).",
                file=sys.stderr,
            )
            sys.exit(2)
    except Exception as e:  # noqa: BLE001
        print(f"[reforma-gate] {e}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
