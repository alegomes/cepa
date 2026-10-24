#!/usr/bin/env python3
"""cepa-until — a git that does not respond is not a branch change.

The WEGO run of 25/09/2026 stopped at 00:25 with `branch-mudou` ("now we are on
`?`") and 5h40 of deadline left. Nobody changed branch: the `.git/worktrees/`
folder, which links the night worktree to the clone, vanished, and
`branch_atual` returned `"?"` for any git error.

The cases below pin the fix:
  - link erased with the worktree on disk: the supervisor redoes the link and the
    night goes on, with the next commit on the night branch;
  - link erased and repair impossible (the branch vanished from the clone): the run stops
    with `git-quebrado`, naming the git error, and not with `branch-mudou`.

Run with `python3 tests/test_cepa_until_broken_git.py`.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)


# Commits the item in the worktree it woke up in and, on `a1`, deletes the whole
# `<clone>/.git/worktrees` folder, as happened on 25/09. With
# FAKE_APAGA_BRANCH, it also deletes the night branch in the clone, which leaves the
# repair with nowhere to point.
ERASES_LINK = (
    "import subprocess, shutil\n"
    "ident = primeiro_pendente()\n"
    "if ident == 'a2':\n"
    "    open(os.environ['FAKE_CHAMADAS'] + '.status', 'w').write(\n"
    "        subprocess.run(['git', 'status', '--porcelain'],\n"
    "                       capture_output=True, text=True).stdout)\n"
    "open(ident + '.txt', 'w').write('feito')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', ident], check=True)\n"
    "marca(ident, status='done', evidence='ok')\n"
    "if ident == 'a1':\n"
    "    comum = subprocess.run(['git', 'rev-parse', '--path-format=absolute',\n"
    "                            '--git-common-dir'], capture_output=True,\n"
    "                           text=True, check=True).stdout.strip()\n"
    "    branch = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],\n"
    "                            capture_output=True, text=True,\n"
    "                            check=True).stdout.strip()\n"
    "    shutil.rmtree(os.path.join(comum, 'worktrees'))\n"
    "    if os.environ.get('FAKE_APAGA_BRANCH'):\n"
    "        subprocess.run(['git', '--git-dir', comum, 'branch', '-D', branch],\n"
    "                       check=True, capture_output=True)\n")


def plan_of(root):
    return root / ".claude" / "programs" / "fila" / "plan.yaml"


def status(root, ident):
    for it in yaml.safe_load(plan_of(root).read_text())["items"]:
        if it["id"] == ident:
            return it["status"]
    return None


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True).stdout.strip()


def test_link_erased_and_redone_and_the_night_goes_on():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, ERASES_LINK)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"])
        ev = ledger_of(root)
        end = [e for e in ev if e.get("evento") == "run_end"][0]
        check("o run não para por `branch-mudou` nem por `git-quebrado`",
              end["motivo"] not in ("branch-mudou", "git-quebrado"), str(end))
        check("o 2º item roda depois da ligação apagada", len(calls) == 2,
              f"disparou {len(calls)}x · {p.stdout[-600:]}")
        check("e fecha `done`", status(root, "a2") == "done")
        repairs = [e for e in ev if e.get("evento") == "git_reparo"]
        check("o registro diz que reparou e qual erro o git deu",
              len(repairs) == 1 and repairs[0]["reparou"]
              and "not a git repository" in repairs[0]["erro"], str(repairs))
        branch = [e for e in ev if e.get("evento") == "run_start"][0]["branch"]
        log = git(root, "log", "--format=%s", branch)
        check("o commit do 2º item está na branch da noite, em cima do 1º",
              log.splitlines()[:2] == ["a2", "a1"], log)
        check("o clone voltou a listar a worktree da noite",
              branch in git(root, "worktree", "list"),
              git(root, "worktree", "list"))
        # The index lived in the deleted folder. Without redoing it, the 2nd item would wake up
        # with every file as deleted in the index and loose in the tree.
        seen = Path(tmp) / "chamadas.jsonl.status"
        check("o 2º item acorda com a worktree limpa, índice refeito",
              seen.exists() and seen.read_text() == "",
              seen.read_text() if seen.exists() else "não gravou")


def test_impossible_repair_stops_as_broken_git_and_not_branch_changed():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, ERASES_LINK)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"],
                           extra_env={"FAKE_APAGA_BRANCH": "1"})
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("o motivo é `git-quebrado`", end["motivo"] == "git-quebrado",
              str(end))
        detail = end.get("detalhe") or ""
        check("o detalhe traz o erro do git e o que impediu o reparo",
              "not a git repository" in detail and "não existe mais" in detail,
              detail)
        check("o detalhe não acusa troca de branch",
              "`?`" not in detail and "trocou de branch no meio" not in detail,
              detail)
        check("o 2º item não é disparado", len(calls) == 1,
              f"disparou {len(calls)}x")
        check("e segue `pending`", status(root, "a2") == "pending")
        tree = [e for e in ledger_of(root)
                  if e.get("evento") == "run_start"][0]["arvore"]
        check("a worktree da noite continua no disco com o trabalho",
              (Path(tree) / "a1.txt").exists())


def _cepa_until():
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    from test_cepa_until import CEPA_UNTIL
    loader = SourceFileLoader("cepa_until", str(CEPA_UNTIL))
    mod = module_from_spec(spec_from_loader("cepa_until", loader))
    loader.exec_module(mod)
    return mod


def test_repair_does_not_write_outside_the_clone_worktrees_folder():
    """The worktree's `.git` says where the link lives. If it points outside
    `<clone>/.git/worktrees/`, the repair refuses instead of creating a folder wherever the
    file says."""
    cu = _cepa_until()
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        tree = Path(tmp) / "wt"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "until/x",
                        str(tree), "HEAD"], cwd=root, check=True)
        outside = Path(tmp) / "fora" / "wt"
        (tree / ".git").write_text(f"gitdir: {outside}\n")
        failure = cu.repair_link(root, tree, "until/x")
        check("recusa ligação fora de .git/worktrees",
              failure is not None and "fora de" in failure, str(failure))
        check("e não cria nada lá", not outside.parent.exists())


def main():
    print("cepa-until — git quebrado na worktree da noite\n")
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
