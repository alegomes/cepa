#!/usr/bin/env python3
"""Regression tests para `cepa-doctor --fix` — o lote de correções mecânicas.

O `--fix` existe para matar o ciclo "acha um problema → propõe → confirma →
acha o próximo → propõe → confirma", que consumia mais atenção do dono do
harness que a própria tarefa da sessão. O risco de um comando que muta sem
perguntar é óbvio, então a fronteira é o que estes testes fixam:

  - aplica o que é MECÂNICO e REVERSÍVEL (arquivar handoff vencido — move,
    não apaga; limpar registro de worktree cujo diretório sumiu);
  - NUNCA aplica o que é uma decisão (descartar diretório órfão, editar
    board-flow.yaml, escolher entre reinstalar e voltar versão) — esses saem
    no bloco "Precisa de você";
  - sem --fix, não muta nada e apenas anuncia o que seria corrigido;
  - re-diagnostica depois de corrigir, para que o achado sumido some de fato.

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
    """Repo com um handoff vencido e uma worktree fantasma (dir removido)."""
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
    if worktree_home:
        env["CEPA_WORKTREE_HOME"] = str(worktree_home)
    p = subprocess.run([sys.executable, str(DOCTOR), *args],
                       capture_output=True, text=True, cwd=str(root), env=env)
    return p.returncode, p.stdout + p.stderr


def test_dry_run_nao_muta():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp))
        _rc, out = run_doctor(root)
        check("sem --fix acusa o handoff vencido",
              "velho.md" in out, out)
        check("sem --fix o handoff continua onde estava",
              (root / ".claude" / "handoffs" / "velho.md").exists())
        check("sem --fix anuncia que existe correção mecânica",
              "cepa-doctor --fix" in out, out)


def test_fix_aplica_o_mecanico():
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


def test_fix_nao_toca_no_que_e_decisao():
    """A fronteira: órfã, board-flow incompleto e baseline ausente ficam."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        root = make_repo(tmpp)
        (root / ".claude" / "no-build").unlink()          # baseline ausente
        (root / "board-flow.yaml").write_text("site: x\n", encoding="utf-8")
        wt_home = tmpp / "wts"
        (wt_home / f"{root.name}-orfa").mkdir(parents=True)  # dir órfão

        _rc, out = run_doctor(root, "--fix", worktree_home=wt_home)

        check("diretório órfão NÃO é removido por --fix",
              (wt_home / f"{root.name}-orfa").is_dir())
        check("board-flow.yaml não é editado",
              (root / "board-flow.yaml").read_text() == "site: x\n")
        check("os três aparecem no bloco 'Precisa de você'",
              "## Precisa de você" in out
              and "órfão" in out and "board-flow" in out and "baseline" in out, out)


def test_exit_code_preservado():
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(Path(tmp))
        rc, _out = run_doctor(root, "--fix")
        check("depois de corrigir tudo que era mecânico, exit 0", rc == 0)


def test_preflight_do_wrapper():
    """O preflight pendurado no `cepa`: barato, calado e nunca bloqueante."""
    wrapper = REPO / "common" / "bin" / "cepa"
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        root = make_repo(tmpp)

        # 1ª chamada (carimbo inexistente = velho): corrige e fala
        rc1, out1 = run_doctor(root, "--fix", "--brief", "--if-stale", "12")
        check("preflight corrige o mecânico e resume em poucas linhas",
              "arquivar handoff" in out1 and len(out1.strip().splitlines()) <= 4, out1)
        check("preflight não despeja o diagnóstico inteiro",
              "# cepa-doctor" not in out1, out1)

        # 2ª chamada dentro da janela: silêncio total
        _rc2, out2 = run_doctor(root, "--fix", "--brief", "--if-stale", "12")
        check("dentro da janela, o preflight é MUDO", out2.strip() == "", repr(out2))

        # o wrapper abre a sessão mesmo com o doctor quebrado
        fake = tmpp / "fakeclaude"
        fake.write_text("#!/bin/sh\necho SESSAO-ABRIU\n", encoding="utf-8")
        fake.chmod(0o755)
        bindir = tmpp / "broken" / "bin"
        bindir.mkdir(parents=True)
        (tmpp / "broken" / "hooks").mkdir()
        (bindir / "cepa-doctor").write_text("raise SystemExit('boom')\n", encoding="utf-8")
        (bindir / "cepa").write_text(wrapper.read_text(encoding="utf-8"), encoding="utf-8")
        env = dict(os.environ, CLAUDE_WT_CLAUDE_BIN=str(fake), CEPA_PREFLIGHT_TTL="0")
        p = subprocess.run(["sh", str(bindir / "cepa")], capture_output=True,
                           text=True, cwd=str(root), env=env)
        check("doctor quebrado NÃO impede a sessão de abrir",
              "SESSAO-ABRIU" in p.stdout, p.stdout + p.stderr)

        env_off = dict(os.environ, CLAUDE_WT_CLAUDE_BIN=str(fake), CEPA_PREFLIGHT="off")
        p = subprocess.run(["sh", str(wrapper)], capture_output=True, text=True,
                           cwd=str(root), env=env_off)
        check("CEPA_PREFLIGHT=off desliga o preflight",
              "SESSAO-ABRIU" in p.stdout and "cepa-doctor" not in p.stderr,
              p.stdout + p.stderr)


def main():
    test_dry_run_nao_muta()
    test_fix_aplica_o_mecanico()
    test_fix_nao_toca_no_que_e_decisao()
    test_exit_code_preservado()
    test_preflight_do_wrapper()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
