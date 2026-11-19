#!/usr/bin/env python3
"""The final report is a set of panels and the merge shows up once — CS-6 of
docs/spec/fim-do-until-sem-espera.md.

Run with `python3 tests/test_cepa_until_final_report.py`.
"""

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, build_repo, run_until)
from test_cepa_until_run_branch import WORKS, VERIFY, plan_of  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")
LONG_REASON = ("the keycloak realm refuses the token " * 11)[:400]


def stuck_run(tmp, extra_env=None, args=()):
    """a1 delivers a commit, a2 ends `blocked` with a 400-character reason."""
    root = build_repo(tmp, [item("a1"), item("a2")])
    body = WORKS.replace(
        "marca(ident, status='done', evidence='ok')\n",
        "if ident == 'a2':\n"
        f"    marca(ident, status='blocked', evidence={LONG_REASON!r})\n"
        "else:\n"
        "    marca(ident, status='done', evidence='ok')\n")
    binv = fake_claude(tmp, body)
    env = {"COLUMNS": "100"}
    env.update(extra_env or {})
    p, _ = run_until(root, binv, plan_of(root),
                     ["--for", "2h", "--verify", VERIFY, "--no-analysis", *args],
                     extra_env=env)
    return root, p, ANSI.sub("", p.stdout + p.stderr)


def test_the_end_of_a_run_with_a_long_reason_fits_the_terminal_and_names_the_merge_once():
    with tempfile.TemporaryDirectory() as tmp:
        _, p, out = stuck_run(tmp)
        check("a run termina", p.returncode == 0, out[-1500:])
        check("o motivo de 400 caracteres existe no ambiente do teste",
              len(LONG_REASON) == 400)
        # The end of the run: from the header panel on (the launch card and the
        # per-item step lines above it are not part of the report).
        end = out[out.find("ended at"):]
        check("o relatório do fim começa no cabeçalho", "ended at" in out)
        wide = [l for l in end.splitlines() if len(l) > 100]
        check("nenhuma linha do fim passa de 100 colunas", not wide,
              "\n".join(wide[:5]))
        check("merge into aparece exatamente uma vez",
              out.count("merge into") == 1, f"{out.count('merge into')}x\n" + out[-2500:])
        for gone in ("Actions:", "Left with you", "waiting on you"):
            check(f"a tela não traz {gone!r}", gone not in out, out[-2500:])


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    sys.exit(1 if FAILURES else 0)
