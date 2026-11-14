#!/usr/bin/env python3
"""Tests of the clean-tree rule of `cepa-until` (spec `until-arvore-limpa`).

Run with `python3 tests/test_cepa_until_clean_tree.py`.

The spec's red test says `--for 5m`; here it is `--for 2h`, because the
minimum reserve (45min) refuses to start an item in a 5-minute window.

CS-1: a run that ends normally leaves the main clone with nothing of its own
outside git. The queue marks, the `until/<run>.jsonl` record and the
`until/<run>.review.md` analysis go into ONE new commit on the clone's branch,
and that commit holds exactly those paths.

The helpers (fake `claude`, scenario repo, run launcher) are the ones of
`tests/test_cepa_until.py`, imported instead of copied.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until as base  # noqa: E402

check = base.check
FAILURES = base.FAILURES


def _scenario(tmp):
    """The scenario repo with the `.gitignore` lines the real repo has for the run's
    raw output and live state (`.log`, `.estado.json`): the spec keeps those ignored,
    so a test repo without them would measure files the real clone never shows."""
    root = base.build_repo(tmp, [base.item("a1")])
    (root / ".gitignore").write_text(
        ".claude/programs/*/until/*.log\n"
        ".claude/programs/*/until/*.estado.json\n"
        ".claude/queues/*/until/*.log\n"
        ".claude/queues/*/until/*.estado.json\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "gitignore"], cwd=root, check=True)
    return root


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True).stdout


def test_normal_end_commits_queue_record_and_review():
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        # The fake marks the item done and, when called as the end analysis
        # (`/common:until-review <ledger>`), prints a review like the real one.
        binv = base.fake_claude(tmp, (
            "if any('until-review' in a for a in ARGS):\n"
            "    print('# revisão do run\\n\\nnada pendente')\n"
            "else:\n"
            "    marca(primeiro_pendente(), status='done')"))
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = _git(root, "rev-parse", "HEAD").strip()
        p, _calls = base.run_until(root, binv, plan,
                                   ["--for", "2h", "--com-analise"])
        check("CS-1: o run termina", p.returncode == 0,
              f"saiu {p.returncode}: {p.stderr[-400:]}")
        records = sorted((root / ".claude" / "programs" / "fila" / "until")
                         .glob("*.jsonl"))
        check("CS-1: o run escreveu o registro e a revisão",
              len(records) == 1 and records[0].with_suffix(".review.md").exists(),
              str(records))
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-1: git status do clone vazio no fim do run", st == "", st)
        head = _git(root, "rev-parse", "HEAD").strip()
        check("CS-1: há um commit novo no topo", head != before)
        parent = _git(root, "rev-parse", "HEAD~1").strip()
        check("CS-1: ...um só, em cima da base", parent == before,
              f"HEAD~1={parent} base={before}")
        files = sorted(_git(root, "show", "--name-only", "--format=",
                            "HEAD").split())
        rel = ".claude/programs/fila/"
        run_id = records[0].stem if records else "?"
        expected = sorted([f"{rel}plan.yaml", f"{rel}until/{run_id}.jsonl",
                           f"{rel}until/{run_id}.review.md"])
        check("CS-1: o commit contém exatamente fila, registro e revisão",
              files == expected, f"{files} != {expected}")
        msg = _git(root, "log", "-1", "--format=%s")
        check("CS-1: a mensagem segue o formato decidido",
              msg.strip() == f"until fila/{run_id}: queue marks and run records",
              msg)


def test_normal_end_without_analysis_commits_what_exists():
    """No `.review.md` (analysis off): the commit takes the queue and the record,
    and does not fail over the missing file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, _calls = base.run_until(root, binv, plan, ["--for", "2h"])
        check("sem análise: o run termina", p.returncode == 0, p.stderr[-400:])
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("sem análise: git status vazio", st == "", st)
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("sem análise: commit com fila e registro, sem revisão",
              len(files) == 2 and any(f.endswith("plan.yaml") for f in files)
              and any(f.endswith(".jsonl") for f in files), str(files))


def test_quota_end_also_commits_the_record():
    """The run that stops on the account's usage ceiling (`limite-de-uso`) skips
    the analysis and ends through its own return path: that path commits too.
    The proof of 2026-11-14 removed the commit on this path and every other
    test stayed green. `--com-analise` is what reaches the path: with analysis
    off, the run returns before the quota branch."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        binv = base.fake_claude(tmp, f"print({base.FAR_LIMIT!r})\nsys.exit(1)")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = _git(root, "rev-parse", "HEAD").strip()
        p, _calls = base.run_until(root, binv, plan,
                                   ["--for", "2h", "--com-analise"])
        end = [e for e in base.ledger_of(root) if e.get("evento") == "run_end"]
        check("cota: o run termina por limite-de-uso",
              end and end[0].get("motivo") == "limite-de-uso", str(end))
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("cota: git status do clone vazio", st == "", st)
        check("cota: um commit novo sobre a base",
              _git(root, "rev-parse", "HEAD~1").strip() == before)
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("cota: o commit leva o registro do run",
              any(f.endswith(".jsonl") for f in files), str(files))


def main():
    print("cepa-until — árvore limpa no fim do run\n")
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"{given_name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
