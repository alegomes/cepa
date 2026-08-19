#!/usr/bin/env python3
"""Regression tests: worktree de agente esquecida DENTRO do repositório.

A ferramenta de subagente do Claude Code cria worktree em
`.claude/worktrees/agent-<id>` — dentro da árvore, não em ~/cepa-worktrees/ como
as `session/*`. Ela deveria sumir sozinha quando nada muda, mas sobrevive se o
agente commitar, e aí duplica o código-fonte inteiro para qualquer ferramenta
que varra o projeto com `find`.

O caso que pagou por este check (2026-08-19, wego-acesso-backend): a sobra fez o
`bin/run-dev.sh doctor` contar cada migration duas vezes e acusar 14 versões
duplicadas inexistentes — o boot do backend ficou barrado, o portão de prova de
UI de outro repo caiu e a auditoria de aceite de dois cards também. O preflight
do cepa-doctor tinha rodado limpo no começo daquela sessão.

O que estes testes fixam:
  - a sobra limpa e já contida na base é ACHADA e removida por --fix;
  - a sobra com arquivo não rastreado NÃO é removida (havia um teste de medição
    do WEGO-2037 que só existia dentro da worktree do caso real);
  - a sobra com commit que a base não tem NÃO é removida;
  - worktree de sessão (fora do repo) continua tratada como antes.

Run: python3 tests/test_doctor_worktree_interna.py
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
    """A worktree como a ferramenta de agente a cria: dentro de .claude/."""
    path = root / ".claude" / "worktrees" / name
    if branch:
        git(["worktree", "add", "-q", str(path), "-b", branch], root)
    else:
        git(["worktree", "add", "-q", "--detach", str(path)], root)
    return path


def run_doctor(root: Path, *args):
    p = subprocess.run([sys.executable, str(DOCTOR), *args],
                       capture_output=True, text=True, cwd=str(root),
                       env=dict(os.environ, CEPA_WORKTREE_HOME=str(root / "no-such")))
    return p.returncode, p.stdout + p.stderr


def test_sobra_limpa_e_achada_e_removida():
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


def test_sobra_com_arquivo_nao_rastreado_sobrevive():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp))
        path = add_agent_worktree(root, branch="claude/agent-2")
        so_existe_aqui = path / "medicao-wego-2037.md"
        so_existe_aqui.write_text("dado que só existe aqui\n", encoding="utf-8")

        _rc, out = run_doctor(root, "--fix")
        check("worktree com arquivo não rastreado NÃO é removida", path.is_dir(), out)
        check("o arquivo que só existia ali sobrevive", so_existe_aqui.exists())
        check("o achado vai para o bloco de decisão do dono",
              "## Precisa de você" in out and "não rastreado" in out, out)


def test_sobra_com_commit_exclusivo_sobrevive():
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


def test_worktree_de_sessao_fora_do_repo_nao_muda():
    """O parse foi reescrito; a regra antiga das session/* tem que sobreviver."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        root = make_repo(tmpp)
        fora = tmpp / "proj-slice"
        git(["worktree", "add", "-q", str(fora), "-b", "session/slice"], root)

        _rc, out = run_doctor(root, "--fix")
        check("session/* fora do repo não é confundida com worktree de agente",
              "worktree de agente" not in out, out)
        check("e não é removida por --fix", fora.is_dir())


def main():
    test_sobra_limpa_e_achada_e_removida()
    test_sobra_com_arquivo_nao_rastreado_sobrevive()
    test_sobra_com_commit_exclusivo_sobrevive()
    test_worktree_de_sessao_fora_do_repo_nao_muda()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
