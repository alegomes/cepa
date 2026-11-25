#!/usr/bin/env python3
"""`cepa-run land --yes` when git refuses to take the run worktree or branch off
(CS-2 of pouso-ja-feito-sai-da-lista: the helper shared with `pending`).

Every case runs a real `cepa-until` night against a fake repo, then the landing.
The run's `verify` (kept in the state record, run in the clone during the landing)
is rewritten to do what the case needs after the merge and before the removal.

  - a tracked change in the run worktree appears during the build: the landing
    still saves the ignored files, git refuses the removal (never `--force`), the
    worktree and its change stay, and the output warns
  - the clone is left on an older branch during the build: `git branch -d`
    refuses (`land` never uses `-D`), the branch stays, and the output warns
  - the branch is already gone when the removal runs: no warning about it

Run with `python3 tests/test_cepa_until_land_refusals.py`.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import FAILURES, check, item, build_repo  # noqa: E402
from test_cepa_until_land import night, land, state  # noqa: E402
from test_cepa_until_run_branch import git  # noqa: E402


def set_verify(root, command):
    d = root / ".claude" / "programs" / "fila" / "until"
    path = sorted(d.glob("*.estado.json"))[-1]
    data = json.loads(path.read_text())
    data["verify"] = command
    path.write_text(json.dumps(data))


def rescued_notes(root):
    return list((root / ".claude" / "rescued").rglob("nova.md"))


def test_tracked_change_in_run_tree_keeps_worktree_and_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, branch, tree = night(root)
        with open(root / ".git" / "info" / "exclude", "a") as f:
            f.write(".claude/notas/\n.claude/rescued/\n")
        (Path(tree) / ".claude" / "notas").mkdir(parents=True, exist_ok=True)
        (Path(tree) / ".claude" / "notas" / "nova.md").write_text("só na árvore")
        set_verify(root, f"echo mudou >> '{tree}/a1.txt'")
        p = land(root, run_id, "--yes")
        out = p.stdout
        check("aterrissa com saída 0", p.returncode == 0, p.stderr + out)
        check("o estado vira aterrissado", state(root).get("estado") == "aterrissado")
        check("a worktree segue (git recusou, sem --force)", Path(tree).exists(), out)
        check("...com a mudança não commitada", "mudou" in (Path(tree) / "a1.txt").read_text())
        check("avisa que não removeu a worktree",
              f"warning: did not remove the worktree {tree}" in out, out)
        check("o branch segue, preso à worktree", bool(git(root, "branch", "--list", branch)))
        check("o arquivo ignorado foi guardado em .claude/rescued/",
              len(rescued_notes(root)) == 1, rescued_notes(root))


def test_branch_not_merged_into_head_is_kept_with_a_warning():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, branch, tree = night(root)
        # The build leaves the clone on an older branch: the run branch is in
        # `main` but not in HEAD, so `git branch -d` refuses and `-D` would not.
        set_verify(root, "git checkout -q -b velho HEAD~1")
        p = land(root, run_id, "--yes")
        out = p.stdout
        check("aterrissa com saída 0", p.returncode == 0, p.stderr + out)
        check("o branch da run segue (land usa -d, nunca -D)",
              bool(git(root, "branch", "--list", branch)), out)
        check("avisa que não apagou o branch",
              f"warning: did not delete `{branch}`" in out, out)
        check("a worktree saiu", not Path(tree).exists(), tree)


def test_branch_already_gone_gives_no_warning():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, branch, tree = night(root)
        set_verify(root, f"git update-ref -d refs/heads/{branch}")
        p = land(root, run_id, "--yes")
        out = p.stdout
        check("aterrissa com saída 0", p.returncode == 0, p.stderr + out)
        check("o branch não existe", not git(root, "branch", "--list", branch))
        check("nenhum aviso de branch não apagado", "did not delete" not in out, out)


def main():
    print("cepa-run land: recusas do git na remoção\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
