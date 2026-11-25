#!/usr/bin/env python3
"""`tests/run-all.sh` does not inherit the launching shell's terminal size.

Origin (2026-11-18): the landing of run until-todas-as-filas/2026-11-17-1431
went red in test_cepa_plan_answer_waiver and test_cepa_until_decide because the
shell that launched `cepa-run land` had COLUMNS exported. The screens that
`cepa-until` / `cepa-queue` render take their width from
`shutil.get_terminal_size()`, which reads COLUMNS first, so the wrap changed and
the assertions on the text failed.

Runs the runner with COLUMNS=60 LINES=20 in the env, filtered to the one file
that is known to break, and expects exit 0.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
failures = 0


def check(name, cond, detail=""):
    global failures
    if cond:
        print(f"ok   {name}")
    else:
        failures += 1
        print(f"FAIL {name}")
        if detail:
            print(detail)


env = dict(os.environ, COLUMNS="60", LINES="20")
r = subprocess.run(
    ["bash", str(ROOT / "tests" / "run-all.sh"), "test_cepa_plan_answer_waiver"],
    cwd=ROOT, env=env, capture_output=True, text=True,
)
out = r.stdout + r.stderr
check("o filtro seleciona exatamente 1 arquivo", "→ 1 arquivo(s)" in out, out)
check("run-all com COLUMNS=60 LINES=20 sai 0", r.returncode == 0, out)

sys.exit(1 if failures else 0)
