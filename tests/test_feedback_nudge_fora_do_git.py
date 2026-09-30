#!/usr/bin/env python3
"""Regression tests: o marcador do hook feedback-nudge não é versionado.

## Por que este teste existe

O hook `common/hooks/feedback-nudge.py` grava em `.claude/feedback-nudge` o id
da sessão que já recebeu o aviso, para avisar uma vez só por sessão. É estado
de runtime desta máquina, reescrito a cada sessão — mas estava versionado, e
duas worktrees que o reescreveram deram conflito no merge 3f4fe2e (desvios.md,
2026-09-26).

O teste cobra as duas metades do conserto, na superfície em que o problema
aparece (o `git status` de quem vai commitar):

- neste repo, o arquivo não está no índice e o `.gitignore` o ignora;
- num repo com o `.gitignore` deste, o hook de verdade dispara, grava o
  marcador, e o `git status` continua limpo.

Run: python3 tests/test_feedback_nudge_fora_do_git.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "feedback-nudge.py"
MARCADOR = ".claude/feedback-nudge"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def git(raiz, *args):
    return subprocess.run(["git", "-C", str(raiz), *args],
                          capture_output=True, text=True)


def test_repo_nao_versiona_o_marcador():
    listado = git(REPO, "ls-files", "--", MARCADOR).stdout.strip()
    check("marcador fora do índice do repo", listado == "", listado)
    ignorado = git(REPO, "check-ignore", "-q", "--no-index", MARCADOR)
    check("o .gitignore do repo ignora o marcador", ignorado.returncode == 0,
          f"exit {ignorado.returncode}")


def test_hook_grava_e_status_fica_limpo():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        git(raiz, "init", "-q")
        git(raiz, "config", "user.email", "t@t")
        git(raiz, "config", "user.name", "t")
        (raiz / ".gitignore").write_text(
            (REPO / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8")
        git(raiz, "add", ".gitignore")
        git(raiz, "commit", "-qm", "base")

        payload = {"prompt": "esse hook é irritante, não gosto dele",
                   "session_id": "sessao-teste", "cwd": str(raiz)}
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                           capture_output=True, text=True, cwd=raiz)
        check("o hook disparou o aviso", "feedback-capture" in r.stdout,
              r.stdout[-300:] + r.stderr[-300:])
        arq = raiz / MARCADOR
        check("o hook gravou o marcador",
              arq.exists() and arq.read_text().strip() == "sessao-teste")
        status = git(raiz, "status", "--porcelain").stdout.strip()
        check("git status limpo depois do hook", status == "", status)


def main():
    print("feedback-nudge — marcador fora do git\n")
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"{nome}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
