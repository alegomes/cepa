#!/usr/bin/env python3
"""Regression tests: árvore suja com fila esperando execução desatendida.

## Por que este check existe

O `cepa-until` (a janela de execução desatendida) RECUSA largar com a árvore
suja — é como ele separa, de manhã, o que o run fez do que já estava ali. A
recusa é instantânea, então descobrir o problema às 23h custa a janela inteira.
O doctor cobra antes, na abertura da sessão.

## Por que o aviso é GATEADO na fila, e não solto

Árvore suja é o estado NORMAL de quem está trabalhando. Um aviso em toda
abertura de sessão é o ruído que o usuário aprende a pular — a mesma razão pela
qual o modo resumido do doctor não imprime "está tudo ok". O aviso só aparece
quando as duas coisas são verdade ao mesmo tempo: existe fila `single-track`
com item `pending`, E a árvore está suja.

O teste que mais importa aqui é justamente o do SILÊNCIO: árvore suja sem fila
pendente não pode dizer nada.

Run: python3 tests/test_doctor_arvore_suja.py
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
program: fila
source: teste
items:
- id: a1
  title: primeiro
  why: porque
  status: {status}
  blocked_by: []
  human_pending: null
  evidence: null
"""


def monta(tmp, status="pending", mode="single-track", com_fila=True):
    raiz = Path(tmp)
    if com_fila:
        d = raiz / ".claude" / "programs" / "fila"
        d.mkdir(parents=True)
        (d / "plan.yaml").write_text(
            PLANO.format(status=status).replace("mode: single-track",
                                                f"mode: {mode}"),
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


def suja(raiz):
    (raiz / "lixo.txt").write_text("trabalho não commitado\n", encoding="utf-8")


def test_suja_com_fila_pendente_avisa():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp)
        suja(raiz)
        out = roda(raiz)
        check("avisa quando há fila pendente E árvore suja",
              "[execucao]" in out and "⚠" in out, out[-600:])
        check("...e nomeia o comando que vai recusar",
              "cepa-until" in out, out[-600:])
        check("...e nomeia o escape", "--sujo-ok" in out, out[-600:])
        check("...e nomeia a fila", "`fila`" in out, out[-600:])


def test_suja_sem_fila_pendente_e_SILENCIOSA():
    """O caso que decide se o check é útil ou ruído."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, status="done")
        suja(raiz)
        out = roda(raiz)
        check("fila sem item pendente + árvore suja → não diz nada",
              "[execucao]" not in out, out[-600:])

    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, com_fila=False)
        suja(raiz)
        out = roda(raiz)
        check("repo sem fila nenhuma + árvore suja → não diz nada",
              "[execucao]" not in out, out[-600:])


def test_plano_de_ondas_nao_conta_como_fila():
    """`mode: waves` é do /maestro:run, que não passa pelo cepa-until."""
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp, mode="waves")
        suja(raiz)
        out = roda(raiz)
        check("plano de ondas não dispara o aviso", "[execucao]" not in out,
              out[-600:])


def test_limpa_com_fila_pendente_confirma_que_pode_largar():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = monta(tmp)
        out = roda(raiz)
        check("árvore limpa + fila pendente → confirma que larga",
              "[execucao]" in out and "✓" in out, out[-600:])
        check("...e não é um aviso", "⚠ [execucao]" not in out, out[-600:])


def main():
    print("cepa-doctor — árvore suja vs. fila pendente\n")
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
