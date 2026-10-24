#!/usr/bin/env python3
"""Regression tests for `cepa-doctor --fix` — the batch of mechanical corrections.

`--fix` exists to kill the cycle "finds a problem → proposes → confirms →
finds the next → proposes → confirms", which consumed more of the harness
owner's attention than the session's own task. The risk of a command that
mutates without asking is obvious, so the boundary is what these tests pin down:

  - it applies what is MECHANICAL and REVERSIBLE (archiving an expired handoff —
    moves, does not delete; cleaning the registry of a worktree whose directory
    vanished);
  - it NEVER applies what is a decision (discarding an orphan directory, editing
    board-flow.yaml, choosing between reinstalling and rolling back a version) —
    those come out in the "Needs you" block;
  - without --fix, it mutates nothing and only announces what would be fixed;
  - it re-diagnoses after fixing, so that the finding that vanished really vanishes.

Run: python3 tests/test_doctor_fix.py
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
    """Repo with an expired handoff and a ghost worktree (removed dir)."""
    root = tmp / "proj"
    root.mkdir()
    git(["init", "-q", "."], root)
    git(["commit", "-q", "--allow-empty", "-m", "init"], root)
    (root / ".claude" / "handoffs").mkdir(parents=True)
    (root / ".claude" / "no-build").touch()
    (root / ".claude" / "handoffs" / "velho.md").write_text(
        "updated_at: 2020-01-01T00:00:00Z\n\nfatos vencidos\n", encoding="utf-8")
    ghost = tmp / "ghost"
    git(["worktree", "add", "-q", str(ghost), "-b", "session/ghost"], root)
    subprocess.run(["rm", "-rf", str(ghost)], check=True)
    return root


def run_doctor(root: Path, *args, worktree_home=None):
    env = dict(os.environ)
    # No suite reinstalls the machine's plugins — see
    # tests/test_doctor_install_guard.py.
    env["CEPA_DOCTOR_INSTALL"] = "off"
    if worktree_home:
        env["CEPA_WORKTREE_HOME"] = str(worktree_home)
    # --projeto: the suite's verdict cannot depend on the installation of the machine
    # of whoever runs it (that is what the silent reinstall "solved").
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto", *args],
                       capture_output=True, text=True, cwd=str(root), env=env)
    return p.returncode, p.stdout + p.stderr


def test_dry_run_does_not_mutate():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp))
        _rc, out = run_doctor(root)
        check("sem --fix acusa o handoff vencido",
              "velho.md" in out, out)
        check("sem --fix o handoff continua onde estava",
              (root / ".claude" / "handoffs" / "velho.md").exists())
        check("sem --fix anuncia que existe correção mecânica",
              "cepa-doctor --fix" in out, out)


def test_fix_applies_the_mechanical():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp))
        _rc, out = run_doctor(root, "--fix")

        arch = root / ".claude" / "handoffs" / "archive" / "velho.md"
        check("handoff vencido é ARQUIVADO, não apagado", arch.exists(), out)
        check("o original sai do diretório vivo",
              not (root / ".claude" / "handoffs" / "velho.md").exists())
        check("registro de worktree fantasma é limpo",
              "prunable" not in git(["worktree", "list", "--porcelain"], root).stdout)
        check("relatório lista o que foi corrigido",
              "## Corrigido automaticamente" in out and "arquivar handoff" in out, out)
        check("o achado corrigido SOME do diagnóstico (re-rodou)",
              "sem handoffs vencidos" in out, out)


def test_fix_does_not_touch_what_is_a_decision():
    """The boundary: orphan, incomplete board-flow and missing baseline stay."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        root = make_repo(tmpp)
        (root / ".claude" / "no-build").unlink()          # baseline missing
        (root / "board-flow.yaml").write_text("site: x\n", encoding="utf-8")
        wt_home = tmpp / "wts"
        (wt_home / f"{root.name}-orfa").mkdir(parents=True)  # orphan dir

        _rc, out = run_doctor(root, "--fix", worktree_home=wt_home)

        check("diretório órfão NÃO é removido por --fix",
              (wt_home / f"{root.name}-orfa").is_dir())
        check("board-flow.yaml não é editado",
              (root / "board-flow.yaml").read_text() == "site: x\n")
        check("os três aparecem no bloco 'Precisa de você'",
              "## Precisa de você" in out
              and "órfão" in out and "board-flow" in out and "baseline" in out, out)


def test_exit_code_preserved():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp))
        rc, _out = run_doctor(root, "--fix")
        check("depois de corrigir tudo que era mecânico, exit 0", rc == 0)


def test_wrapper_preflight():
    """The preflight hanging off `cepa`: cheap, quiet and never blocking."""
    wrapper = REPO / "common" / "bin" / "cepa"
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        root = make_repo(tmpp)

        # 1st call (nonexistent stamp = old): fixes and speaks
        rc1, out1 = run_doctor(root, "--fix", "--brief", "--if-stale", "12")
        check("preflight corrige o mecânico e resume em poucas linhas",
              "arquivar handoff" in out1 and len(out1.strip().splitlines()) <= 4, out1)
        check("preflight não despeja o diagnóstico inteiro",
              "# cepa-doctor" not in out1, out1)

        # 2nd call within the window: total silence
        _rc2, out2 = run_doctor(root, "--fix", "--brief", "--if-stale", "12")
        check("dentro da janela, o preflight é MUDO", out2.strip() == "", repr(out2))

        # the wrapper opens the session even with the doctor broken
        fake = tmpp / "fakeclaude"
        fake.write_text("#!/bin/sh\necho SESSAO-ABRIU\n", encoding="utf-8")
        fake.chmod(0o755)
        bindir = tmpp / "broken" / "bin"
        bindir.mkdir(parents=True)
        (tmpp / "broken" / "hooks").mkdir()
        (bindir / "cepa-doctor").write_text("raise SystemExit('boom')\n", encoding="utf-8")
        (bindir / "cepa").write_text(wrapper.read_text(encoding="utf-8"), encoding="utf-8")
        # --modo: since common 1.0.0 no session starts without a declared mode, and
        # without a tty cepa has no way to ask.
        env = dict(os.environ, CLAUDE_WT_CLAUDE_BIN=str(fake), CEPA_PREFLIGHT_TTL="0")
        p = subprocess.run(["sh", str(bindir / "cepa"), "--modo", "construcao"],
                           capture_output=True, text=True, cwd=str(root), env=env)
        check("doctor quebrado NÃO impede a sessão de abrir",
              "SESSAO-ABRIU" in p.stdout, p.stdout + p.stderr)

        env_off = dict(os.environ, CLAUDE_WT_CLAUDE_BIN=str(fake), CEPA_PREFLIGHT="off")
        p = subprocess.run(["sh", str(wrapper), "--modo", "construcao"],
                           capture_output=True, text=True, cwd=str(root), env=env_off)
        check("CEPA_PREFLIGHT=off desliga o preflight",
              "SESSAO-ABRIU" in p.stdout and "cepa-doctor" not in p.stderr,
              p.stdout + p.stderr)


def main():
    test_dry_run_does_not_mutate()
    test_fix_applies_the_mechanical()
    test_fix_does_not_touch_what_is_a_decision()
    test_exit_code_preserved()
    test_wrapper_preflight()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
