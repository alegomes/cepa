#!/usr/bin/env python3
"""Regression tests: agent worktree forgotten INSIDE the repository.

Claude Code's subagent tool creates a worktree at
`.claude/worktrees/agent-<id>` — inside the tree, not in ~/cepa-worktrees/ like
the `session/*` ones. It should vanish by itself when nothing changes, but it survives if
the agent commits, and then it duplicates the entire source code for any tool
that sweeps the project with `find`.

The case that paid for this check (2026-08-19, wego-acesso-backend): the leftover made
`bin/run-dev.sh doctor` count each migration twice and report 14 nonexistent
duplicate versions — the backend boot was blocked, another repo's UI proof gate
fell and the acceptance audit of two cards too. The cepa-doctor preflight
had run clean at the start of that session.

What these tests pin down:
  - the clean leftover, already contained in the base, is FOUND and removed by --fix;
  - the leftover with an untracked file is NOT removed (there was a measurement test
    from WEGO-2037 that only existed inside the real case's worktree);
  - the leftover with a commit the base does not have is NOT removed;
  - a session worktree (outside the repo) remains treated as before.

Run: python3 tests/test_doctor_internal_worktree.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def git(args, cwd):
    return subprocess.run(["git"] + args, capture_output=True, text=True, cwd=str(cwd))


def make_repo(tmp: Path):
    root = tmp / "proj"
    root.mkdir()
    git(["init", "-q", "-b", "main", "."], root)
    git(["config", "user.email", "t@t"], root)
    git(["config", "user.name", "t"], root)
    (root / ".claude").mkdir()
    (root / ".claude" / "no-build").touch()
    (root / "src.txt").write_text("fonte\n", encoding="utf-8")
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", "init"], root)
    return root


def add_agent_worktree(root: Path, name="agent-a3494bc82de7f33a6", branch=None):
    """The worktree as the agent tool creates it: inside .claude/."""
    path = root / ".claude" / "worktrees" / name
    if branch:
        git(["worktree", "add", "-q", str(path), "-b", branch], root)
    else:
        git(["worktree", "add", "-q", "--detach", str(path)], root)
    return path


def run_doctor(root: Path, *args):
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto", *args],
                       capture_output=True, text=True, cwd=str(root),
                       env=dict(os.environ, CEPA_WORKTREE_HOME=str(root / "no-such"),
                                CEPA_DOCTOR_INSTALL="off"))
    return p.returncode, p.stdout + p.stderr


def test_clean_leftover_is_found_and_removed():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp))
        path = add_agent_worktree(root, branch="claude/agent-1")

        _rc, out = run_doctor(root)
        check("sem --fix, a sobra aparece no diagnóstico",
              "worktree de agente" in out and "agent-a3494bc82de7f33a6" in out, out)
        check("sem --fix, a sobra continua no disco", path.is_dir())

        _rc, out = run_doctor(root, "--fix")
        check("--fix remove a worktree", not path.exists(), out)
        check("--fix apaga a branch da worktree",
              "claude/agent-1" not in git(["branch", "--list"], root).stdout)
        check("o registro do git some junto",
              "agent-a3494bc82de7f33a6" not in git(["worktree", "list"], root).stdout)
        check("o relatório diz o que foi removido",
              "## Corrigido automaticamente" in out and "worktree de agente" in out, out)


def test_leftover_with_untracked_file_survives():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp))
        path = add_agent_worktree(root, branch="claude/agent-2")
        only_exists_here = path / "medicao-wego-2037.md"
        only_exists_here.write_text("dado que só existe aqui\n", encoding="utf-8")

        _rc, out = run_doctor(root, "--fix")
        check("worktree com arquivo não rastreado NÃO é removida", path.is_dir(), out)
        check("o arquivo que só existia ali sobrevive", only_exists_here.exists())
        check("o achado vai para o bloco de decisão do dono",
              "## Precisa de você" in out and "não rastreado" in out, out)


def test_leftover_with_exclusive_commit_survives():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp))
        path = add_agent_worktree(root, branch="claude/agent-3")
        (path / "novo.txt").write_text("trabalho do agente\n", encoding="utf-8")
        git(["add", "-A"], path)
        git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "trabalho"], path)

        _rc, out = run_doctor(root, "--fix")
        check("worktree com commit que main não tem NÃO é removida", path.is_dir(), out)
        check("o diagnóstico nomeia o motivo",
              "commit que main não tem" in out, out)
        check("a branch do agente continua existindo",
              "claude/agent-3" in git(["branch", "--list"], root).stdout)


def test_session_worktree_outside_repo_is_unchanged():
    """The parse was rewritten; the old rule for session/* must survive."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        root = make_repo(tmpp)
        outside = tmpp / "proj-slice"
        git(["worktree", "add", "-q", str(outside), "-b", "session/slice"], root)

        _rc, out = run_doctor(root, "--fix")
        check("session/* fora do repo não é confundida com worktree de agente",
              "worktree de agente" not in out, out)
        check("e não é removida por --fix", outside.is_dir())


def main():
    test_clean_leftover_is_found_and_removed()
    test_leftover_with_untracked_file_survives()
    test_leftover_with_exclusive_commit_survives()
    test_session_worktree_outside_repo_is_unchanged()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
