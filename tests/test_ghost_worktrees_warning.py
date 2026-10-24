#!/usr/bin/env python3
"""Regression test: the "📋 Unmerged session worktrees" warning of SessionStart
listed branches that `git branch -a` does not know.

The defect (measured in wego-acesso-backend, 2026-08-24): the block listed three
`session/WEGO-paralelo-*` as unmerged, one of them "with uncommitted
changes", and none existed. The list already came from git on the spot — what
lied was the case where the branch ref vanishes (update-ref -d, a tool that
bypasses `git branch -D`) while `git worktree list` still registers the
worktree:
  - `rev-list main..<branch>` fails → ahead = -1, and the `ahead != 0` filter
    counted "unknown" as pending;
  - with the directory still on disk, `git status` on a branch without a ref shows
    every file as staged → "uncommitted changes".

Contracts guarded here, firing the real hook:
  - deleted branch + vanished directory → appears nowhere;
  - deleted branch + directory present → leaves the 📋 block and gets its own
    line saying the branch no longer exists, with the path;
  - live branch with a commit ahead → stays in the 📋 block ("1 commit").

Run with `python3 tests/test_ghost_worktrees_warning.py`.
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


def build(base: Path) -> Path:
    repo = base / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)

    # ghost: directory and ref vanished, only the worktree registration remained
    git("worktree", "add", "-q", "-b", "session/fantasma", str(base / "wt-fantasma"), cwd=repo)
    subprocess.run(["rm", "-rf", str(base / "wt-fantasma")], check=True)
    git("update-ref", "-d", "refs/heads/session/fantasma", cwd=repo)

    # orphan: ref vanished, directory with a file remains on disk
    orphan = base / "wt-orfa"
    git("worktree", "add", "-q", "-b", "session/orfa", str(orphan), cwd=repo)
    (orphan / "f").write_text("x\n")
    git("add", "f", cwd=orphan)
    git("commit", "-q", "-m", "f", cwd=orphan)
    git("update-ref", "-d", "refs/heads/session/orfa", cwd=repo)

    # real: live branch with a commit that main does not have
    real = base / "wt-real"
    git("worktree", "add", "-q", "-b", "session/real", str(real), cwd=repo)
    (real / "g").write_text("y\n")
    git("add", "g", cwd=real)
    git("commit", "-q", "-m", "g", cwd=real)
    return repo


def run_hook(repo: Path, home: Path) -> str:
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


def block(ctx: str, head: str) -> str:
    for part in ctx.split("\n\n"):
        if part.startswith(head):
            return part
    return ""


def main():
    with tempfile.TemporaryDirectory() as t:
        base = Path(t).resolve()
        (base / "home").mkdir()
        repo = build(base)

        rows = {c["branch"]: c for c in L.classify(str(repo))}
        check("classify: ref apagado é branch_gone",
              rows["session/fantasma"]["branch_gone"] and rows["session/orfa"]["branch_gone"],
              str(rows))
        check("classify: branch viva não é branch_gone",
              rows["session/real"]["branch_gone"] is False, str(rows["session/real"]))

        ctx = run_hook(repo, base / "home")
        unmerged = block(ctx, "📋 Unmerged session worktrees")
        orphans = block(ctx, "⚠ Worktrees whose branch no longer exists")

        check("fantasma não aparece em lugar nenhum", "session/fantasma" not in ctx, ctx)
        check("órfã não é listada como não mesclada", "session/orfa" not in unmerged, unmerged)
        check("órfã não vira 'uncommitted changes'",
              "uncommitted" not in unmerged, unmerged)
        check("órfã ganha linha própria com o caminho",
              str(base / "wt-orfa") in orphans and "session/orfa" in orphans, ctx)
        check("branch viva com commit continua no aviso",
              "session/real" in unmerged and "1 commit" in unmerged, ctx)

    print()
    if failures:
        print(f"{len(failures)} FAIL")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
