#!/usr/bin/env python3
"""Regression tests: cepa-doctor reporta (nunca corrige) a fila × BACKLOG.md.

## Por que este check existe

A "Fila única" (BACKLOG.md, Jira e plan.yaml convergem no plan.yaml) só se
mantém se algo cobra a divergência entre os três. `cepa-plan divergencia` faz
o cálculo (seções do BACKLOG.md sem `**Plano:**`, `**Plano:**` citando id que
não existe na fila); este check só chama esse comando e traduz o resultado em
✓/⚠, na abertura de sessão que já roda o doctor. Nunca corrige — fechar uma
seção ou inventar um `**Plano:**` é decisão do dono.

## Por que é gateado em ter BACKLOG.md E uma fila resolvível

Repo sem `BACKLOG.md` não tem o que comparar. Repo com MAIS DE UMA fila
`single-track` é ambíguo — o doctor não adivinha qual o dono quer ver, então
fica calado em vez de arriscar a fila errada.

Run: python3 tests/test_doctor_divergencia_plano.py
"""

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


PLANO = """schema_version: 2
mode: single-track
program: WEGO
source: teste
items:
- id: WEGO-1
  title: primeiro
  why: porque
  status: pending
  blocked_by: []
  human_pending: null
  evidence: null
"""


def monta(tmp, com_backlog=True, backlog_texto=None, com_fila=True,
          com_board_flow=False):
    raiz = Path(tmp)
    if com_fila:
        d = raiz / ".claude" / "programs" / "WEGO"
        d.mkdir(parents=True)
        (d / "plan.yaml").write_text(PLANO, encoding="utf-8")
    if com_backlog:
        (raiz / "BACKLOG.md").write_text(
            backlog_texto or "## Seção X\n\n**Plano:** WEGO-1\n",
            encoding="utf-8")
    if com_board_flow:
        (raiz / "board-flow.yaml").write_text(
            "site: x\nproject_key: WEGO\nstatus_map:\n  to_do: To Do\n",
            encoding="utf-8")
    (raiz / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=raiz, check=True)
    subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=raiz, check=True)
    return raiz


def roda(raiz):
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                       cwd=str(raiz), capture_output=True, text=True, timeout=120)
    return p.stdout + p.stderr


def test_sem_divergencia_confirma():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp)
        out = roda(raiz)
        check("fila × BACKLOG em dia confirma", "[plano]" in out and "✓" in out, out)


def test_secao_sem_plano_avisa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, backlog_texto="## Seção sem plano\n\nnada aqui.\n")
        out = roda(raiz)
        check("seção sem `**Plano:**` gera aviso",
              "[plano]" in out and "⚠" in out, out)
        check("...e nomeia a seção", "Seção sem plano" in out, out)


def test_plano_citando_id_fora_da_fila_avisa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, backlog_texto="## Seção Y\n\n**Plano:** WEGO-999\n")
        out = roda(raiz)
        check("`**Plano:**` com id inexistente gera aviso",
              "[plano]" in out and "⚠" in out, out)
        check("...e nomeia o id", "WEGO-999" in out, out)


def test_sem_backlog_e_silencioso():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, com_backlog=False)
        out = roda(raiz)
        check("sem BACKLOG.md: nada a comparar, silêncio",
              "[plano]" not in out, out)


def test_duas_filas_sem_board_flow_e_ambiguo_e_silencioso():
    """Sem `board-flow.yaml` e com MAIS de uma fila `single-track`, o doctor
    não pode escolher uma delas no chute — pegar "a primeira que achar" é
    exatamente a ambiguidade que `resolve_fila_unica` existe para recusar.
    """
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        for nome in ("WEGO", "OUTRA"):
            d = raiz / ".claude" / "programs" / nome
            d.mkdir(parents=True)
            (d / "plan.yaml").write_text(PLANO.replace("program: WEGO", f"program: {nome}"),
                                         encoding="utf-8")
        (raiz / "BACKLOG.md").write_text("## Seção sem plano\n\nnada aqui.\n",
                                         encoding="utf-8")
        (raiz / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", "."], cwd=raiz, check=True)
        subprocess.run(["git", "add", "-A"], cwd=raiz, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "base"], cwd=raiz, check=True)
        out = roda(raiz)
        check("duas filas ambíguas: nenhuma linha [plano] no relatório",
              "[plano]" not in out, out)


def test_resolve_via_project_key_do_board_flow():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, com_board_flow=True,
                     backlog_texto="## Seção Z\n\n**Plano:** WEGO-1\n")
        out = roda(raiz)
        check("resolve a fila pelo project_key do board-flow.yaml e confirma",
              "[plano]" in out and "✓" in out, out)


def main():
    print("cepa-doctor — divergência da fila única × BACKLOG.md\n")
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"{nome}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
