#!/usr/bin/env python3
"""Testes do mod `rumo/` (painel de orientação do Claude Code).

Sem dependências — rode com `python3 tests/test_rumo_mod.py`.
Sai não-zero em falha.

O mod é TypeScript e roda dentro do Claude Code, então quem o testa é o próprio
`claude`: `claude plugin validate` lê o manifesto e o módulo como o engine lê, e
`claude plugin test` roda `rumo/hooks/*.test.tsx` contra o engine. Este arquivo
só amarra os dois à suíte do repo. Sem `claude` no PATH, pula com aviso: a
máquina de CI do repo não tem o Claude Code instalado.
"""

import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(RAIZ, "rumo")


def roda(*args):
    r = subprocess.run(["claude", "plugin", *args, MOD], capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def main():
    if shutil.which("claude") is None:
        print("PULADO: `claude` fora do PATH; o mod rumo/ não foi testado")
        return 0
    falhas = []
    rc, out = roda("validate")
    if rc != 0:
        falhas.append(f"claude plugin validate falhou:\n{out}")
    rc, out = roda("test")
    if rc != 0 or " 0 fail" not in out:
        falhas.append(f"claude plugin test falhou:\n{out}")
    for f in falhas:
        print("FALHA:", f)
    if not falhas:
        print("ok: rumo/ valida e passa nos testes do engine")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
