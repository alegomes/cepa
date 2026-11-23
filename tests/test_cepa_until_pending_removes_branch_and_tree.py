#!/usr/bin/env python3
"""`cepa-until pending` removes the branch and the worktree of the run it closes
and saves the worktree's git-ignored files (spec docs/spec/pouso-ja-feito-sai-da-lista.md, CS-2).

Against the real CLI, in a temporary git repo with a remote:

  - CS-2 red test: run `a/r1` of CS-1 (red build, branch inside `origin/main`)
    has a worktree holding a git-ignored file. After `pending`:
    `git branch --list until/r1` is empty, the worktree folder is gone and the
    ignored file is under `.claude/rescued/`.
  - a run with no worktree (branch only) is closed and loses its branch
  - `a/r2` (merge only in local `main`) keeps branch and worktree
  - a branch with a commit after the merge keeps branch and worktree
  - a worktree that cannot be removed (tracked change not committed) keeps the
    record `esperando-dono`, the branch and the worktree, and loses nothing

Run with `python3 tests/test_cepa_until_pending_removes_branch_and_tree.py`.
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until_pending_closes_landed import (  # noqa: E402
    FAILURES, add_run, check, git, make_repo, pending, read_state, state_path)


def add_tree(root, tmp, run, ignored=".claude/notes/idea.md"):
    """A worktree of `until/<run>` holding a file that git ignores."""
    tree = Path(tmp) / f"wt-{run}"
    git(root, "worktree", "add", "-q", str(tree), f"until/{run}")
    # `info/exclude` is shared by every worktree and commits nothing.
    exclude = root / ".git" / "info" / "exclude"
    exclude.write_text(".claude/notes/\n.claude/rescued/\n.claude/queues/\n")
    f = tree / ignored
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("ignored work\n")
    st = read_state(root, run)
    st["acoes"][0]["arvore"] = str(tree)
    state_path(root, run).write_text(json.dumps(st), encoding="utf-8")
    return tree


def branches(root, run):
    return git(root, "branch", "--list", f"until/{run}")


def rescued(root):
    return [p for p in (root / ".claude" / "rescued").rglob("idea.md")]


def red_test():
    print("CS-2: fechar remove branch e worktree e guarda o ignorado")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_run(root, "r1", Path(tmp) / "m1")
        tree = add_tree(root, tmp, "r1")
        git(root, "push", "-q", "origin", "main")
        add_run(root, "r2", Path(tmp) / "m2")
        tree2 = add_tree(root, tmp, "r2")
        p = pending(root)
        check("`pending` sai 0", p.returncode == 0, p.stderr)
        check("a/r1 fechado", read_state(root, "r1")["estado"] == "aterrissado")
        check("`git branch --list until/r1` vazio", branches(root, "r1") == "",
              branches(root, "r1"))
        check("a pasta da worktree sumiu", not tree.exists())
        check("o arquivo ignorado esta sob .claude/rescued/", len(rescued(root)) == 1,
              rescued(root))
        check("...com o mesmo conteudo",
              all(f.read_text() == "ignored work\n" for f in rescued(root)))
        check("a/r2 mantem branch e worktree",
              branches(root, "r2") != "" and tree2.exists())
        check("`git worktree list` nao cita a worktree de a/r1",
              str(tree.name) not in git(root, "worktree", "list"))


def branch_only():
    print("run sem worktree: fecha e perde o branch")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_run(root, "r1", Path(tmp) / "m")
        git(root, "push", "-q", "origin", "main")
        p = pending(root)
        check("fechado", read_state(root, "r1")["estado"] == "aterrissado", p.stdout)
        check("branch removido", branches(root, "r1") == "", branches(root, "r1"))


def branch_only_other_head():
    print("repo em outro branch: o branch do run sai mesmo assim")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_run(root, "r1", Path(tmp) / "m")
        git(root, "push", "-q", "origin", "main")
        git(root, "checkout", "-qb", "other", "HEAD~1")
        p = pending(root)
        check("fechado", read_state(root, "r1")["estado"] == "aterrissado", p.stdout)
        check("branch removido", branches(root, "r1") == "", branches(root, "r1"))


def tip_after_merge():
    print("commit depois do merge: mantem branch e worktree")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_run(root, "r1", Path(tmp) / "m")
        tree = add_tree(root, tmp, "r1")
        git(root, "push", "-q", "origin", "main")
        (tree / "late.txt").write_text("late\n")
        git(tree, "add", "late.txt")
        git(tree, "commit", "-qm", "late")
        pending(root)
        check("esperando-dono", read_state(root, "r1")["estado"] == "esperando-dono")
        check("branch e worktree ficam", branches(root, "r1") != "" and tree.exists())
        check("nada resgatado", not rescued(root))


def dirty_tree():
    print("worktree com mudanca rastreada sem commit: nada e destruido")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_run(root, "r1", Path(tmp) / "m")
        tree = add_tree(root, tmp, "r1")
        git(root, "push", "-q", "origin", "main")
        (tree / "r1.txt").write_text("edited, not committed\n")
        pending(root)
        check("registro segue esperando-dono",
              read_state(root, "r1")["estado"] == "esperando-dono")
        check("branch e worktree ficam", branches(root, "r1") != "" and tree.exists())
        check("a mudanca segue la",
              (tree / "r1.txt").read_text() == "edited, not committed\n")


def dirty_no_rescue():
    print("worktree suja: duas chamadas de pending nao copiam nada para rescued")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_run(root, "r1", Path(tmp) / "m")
        tree = add_tree(root, tmp, "r1")
        git(root, "push", "-q", "origin", "main")
        (tree / "r1.txt").write_text("edited, not committed\n")
        pending(root)
        pending(root)
        check("`.claude/rescued/` sem nenhuma copia",
              not list((root / ".claude" / "rescued").rglob("*.md")),
              list((root / ".claude" / "rescued").rglob("*")))
        check("registro segue esperando-dono",
              read_state(root, "r1")["estado"] == "esperando-dono")


def arvore_of_other_branch():
    print("arvore aponta para worktree de outro branch: nao e tocada")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_run(root, "r1", Path(tmp) / "m")
        git(root, "push", "-q", "origin", "main")
        other = Path(tmp) / "wt-other"
        git(root, "worktree", "add", "-q", "-b", "other-b", str(other), "main")
        st = read_state(root, "r1")
        st["acoes"][0]["arvore"] = str(other)
        state_path(root, "r1").write_text(json.dumps(st), encoding="utf-8")
        pending(root)
        check("worktree alheia segue", other.exists())
        check("branch alheio segue", git(root, "branch", "--list", "other-b") != "")
        check("branch do run saiu", branches(root, "r1") == "", branches(root, "r1"))
        check("registro aterrissado", read_state(root, "r1")["estado"] == "aterrissado")


def tree_deleted_by_hand():
    print("pasta da worktree apagada na mao mas registrada no git")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_run(root, "r1", Path(tmp) / "m")
        tree = add_tree(root, tmp, "r1")
        git(root, "push", "-q", "origin", "main")
        shutil.rmtree(tree)
        pending(root)
        check("branch removido", branches(root, "r1") == "", branches(root, "r1"))
        check("registro aterrissado", read_state(root, "r1")["estado"] == "aterrissado")


if __name__ == "__main__":
    red_test()
    branch_only()
    branch_only_other_head()
    tip_after_merge()
    dirty_tree()
    dirty_no_rescue()
    arvore_of_other_branch()
    tree_deleted_by_hand()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
