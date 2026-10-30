#!/usr/bin/env python3
"""Tests of the `compass/` mod (Claude Code orientation panel).

No dependencies — run with `python3 tests/test_compass_mod.py`.
Exits non-zero on failure.

The mod is TypeScript and runs inside Claude Code, so whoever tests it is `claude`
itself: `claude plugin validate` reads the manifest and the module as the engine reads them, and
`claude plugin test` runs `compass/hooks/*.test.tsx` against the engine. This file
only ties the two to the repo's suite. Without `claude` on the PATH, it skips with a warning: the
repo's CI machine does not have Claude Code installed.
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "compass")


def run_claude(*args):
    r = subprocess.run(["claude", "plugin", *args, MOD], capture_output=True, text=True, timeout=300)
    return r.returncode, r.stdout + r.stderr


def main():
    if shutil.which("claude") is None:
        print("PULADO: `claude` fora do PATH; o mod compass/ não foi testado")
        return 0
    fails = []
    rc, out = run_claude("validate")
    if rc != 0:
        fails.append(f"claude plugin validate falhou:\n{out}")
    rc, out = run_claude("test")
    if rc != 0 or " 0 fail" not in out:
        fails.append(f"claude plugin test falhou:\n{out}")
    for f in fails:
        print("FALHA:", f)
    if not fails:
        print("ok: compass/ valida e passa nos testes do engine")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
