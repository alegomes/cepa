#!/usr/bin/env python3
"""Regression test: o aviso "📋 Unmerged session worktrees" do SessionStart
listava branches que `git branch -a` não conhece.

O defeito (medido em wego-acesso-backend, 2026-08-24): o bloco listou três
`session/WEGO-paralelo-*` como não mescladas, uma delas "com alterações não
commitadas", e nenhuma existia. A lista já vinha do git na hora — o que
mentia era o caso em que o ref da branch some (update-ref -d, ferramenta que
contorna o `git branch -D`) enquanto `git worktree list` ainda registra a
worktree:
  - `rev-list main..<branch>` falha → ahead = -1, e o filtro `ahead != 0`
    contava "desconhecido" como pendência;
  - com o diretório ainda no disco, `git status` numa branch sem ref mostra
    todo arquivo como staged → "uncommitted changes".

Contratos guardados aqui, disparando o hook de verdade:
  - branch apagada + diretório sumido → não aparece em lugar nenhum;
  - branch apagada + diretório presente → sai do bloco 📋 e ganha linha
    própria dizendo que a branch não existe mais, com o caminho;
  - branch viva com commit à frente → continua no bloco 📋 ("1 commit").

Rode com `python3 tests/test_aviso_worktrees_fantasma.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"
sys.path.insert(0, str(HOOKS))
import _wtlib as L  # noqa: E402

from _telemetria_isolada import isola

isola()

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True)


def montar(base: Path) -> Path:
    repo = base / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)

    # fantasma: diretório e ref sumiram, só o registro da worktree sobrou
    git("worktree", "add", "-q", "-b", "session/fantasma", str(base / "wt-fantasma"), cwd=repo)
    subprocess.run(["rm", "-rf", str(base / "wt-fantasma")], check=True)
    git("update-ref", "-d", "refs/heads/session/fantasma", cwd=repo)

    # órfã: ref sumiu, diretório com um arquivo continua no disco
    orfa = base / "wt-orfa"
    git("worktree", "add", "-q", "-b", "session/orfa", str(orfa), cwd=repo)
    (orfa / "f").write_text("x\n")
    git("add", "f", cwd=orfa)
    git("commit", "-q", "-m", "f", cwd=orfa)
    git("update-ref", "-d", "refs/heads/session/orfa", cwd=repo)

    # real: branch viva com um commit que a main não tem
    real = base / "wt-real"
    git("worktree", "add", "-q", "-b", "session/real", str(real), cwd=repo)
    (real / "g").write_text("y\n")
    git("add", "g", cwd=real)
    git("commit", "-q", "-m", "g", cwd=real)
    return repo


def rodar_hook(repo: Path, home: Path) -> str:
    env = dict(os.environ, HOME=str(home))
    env.pop("CLAUDE_WT_CLAIM", None)
    p = subprocess.run(
        [sys.executable, str(HOOKS / "session-registry.py")],
        input=json.dumps({"session_id": "teste-fantasma", "cwd": str(repo),
                          "hook_event_name": "SessionStart"}),
        capture_output=True, text=True, env=env, cwd=str(repo), timeout=60)
    if not p.stdout.strip():
        return ""
    return json.loads(p.stdout)["hookSpecificOutput"]["additionalContext"]


def bloco(ctx: str, cabeca: str) -> str:
    for parte in ctx.split("\n\n"):
        if parte.startswith(cabeca):
            return parte
    return ""


def main():
    with tempfile.TemporaryDirectory() as t:
        base = Path(t).resolve()
        (base / "home").mkdir()
        repo = montar(base)

        rows = {c["branch"]: c for c in L.classify(str(repo))}
        check("classify: ref apagado é branch_gone",
              rows["session/fantasma"]["branch_gone"] and rows["session/orfa"]["branch_gone"],
              str(rows))
        check("classify: branch viva não é branch_gone",
              rows["session/real"]["branch_gone"] is False, str(rows["session/real"]))

        ctx = rodar_hook(repo, base / "home")
        unmerged = bloco(ctx, "📋 Unmerged session worktrees")
        orfas = bloco(ctx, "⚠ Worktrees whose branch no longer exists")

        check("fantasma não aparece em lugar nenhum", "session/fantasma" not in ctx, ctx)
        check("órfã não é listada como não mesclada", "session/orfa" not in unmerged, unmerged)
        check("órfã não vira 'uncommitted changes'",
              "uncommitted" not in unmerged, unmerged)
        check("órfã ganha linha própria com o caminho",
              str(base / "wt-orfa") in orfas and "session/orfa" in orfas, ctx)
        check("branch viva com commit continua no aviso",
              "session/real" in unmerged and "1 commit" in unmerged, ctx)

    print()
    if failures:
        print(f"{len(failures)} FAIL")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
