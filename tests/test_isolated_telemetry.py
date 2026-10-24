#!/usr/bin/env python3
"""The suite does not write to the telemetry ledger of whoever runs it.

The defect (2026-08-26): the hooks record events in ~/.claude/cepa-telemetry/ and
this suite executes the hooks. Only 3 of the 53 files defined CEPA_TELEMETRY_DIR,
so running the tests invented repos in the /common:metrics report —
`main-repo` with 206 green and 206 red, `r3`, `sem-git`, `pert2` — and the two
highest-volume lines of that report's "Suggested readings" were rehearsal,
not use. A metric that mixes rehearsal with use measures the rehearsal.

What is proven here, and why this way:

  - the proof runs the REAL tests that emit telemetry, each with HOME
    pointed at a disposable directory, and demands that this HOME stay
    untouched. A double that only called `isola()` would prove the function, not the
    suite — and the defect was the suite, not the function;
  - the same test, with CEPA_TELEMETRY_DIR already defined, must respect the
    requested destination: several tests check what they wrote in their own tmpdir, and
    an isolation that overwrote it would break them silently;
  - a static sweep catches the NEXT polluter: every tests/test_*.py that
    executes an emitter hook must isolate. Without it, the fix holds for today's 7
    and the 8th goes back to polluting quietly — which is exactly how the defect was born.

Expected red without the fix: removing the call to `isola()` from any of the
emitters makes the first case write to <HOME>/.claude/cepa-telemetry/.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"

# The tests that execute an emitter hook. Measured, not assumed: each of these,
# run with a disposable HOME BEFORE the 2026-08-26 fix, created
# <HOME>/.claude/cepa-telemetry/ (81 events in total).
EMITTERS = [
    "test_baseline_worktree_poisoning.py",
    "test_loop_budget.py",
    "test_maven_reactor_guard.py",
    "test_proof_double_substitution.py",
    "test_proof_status_enum.py",
    "test_session_anchor_root.py",
    "test_ui_proof_verdict_guard.py",
    "test_write_mode_gate.py",
]
GUINEA_PIG = TESTS / "test_proof_status_enum.py"

# The hooks and binaries that write to the ledger. A test that cites any of
# these and does not isolate is the next polluter.
EMITTER_HOOKS = [
    "capture-build-result", "gate-advance", "loop-budget", "maven-reactor-guard",
    "write-mode-gate", "proof-verdict-guard", "report-style-lint", "session-log",
    "session-registry", "ui-proof-verdict-guard",
]


def isolates_somehow(text: str) -> bool:
    """The test sends the telemetry away from the real ledger, in one of the two accepted
    ways: the shared call, or its own destination in the env.
    """
    return "isola()" in text or "CEPA_TELEMETRY_DIR" in text

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_test(guinea_pig, home, **env_extra):
    """Runs a suite test with a disposable HOME. Returns the CompletedProcess."""
    env = {k: v for k, v in os.environ.items() if k != "CEPA_TELEMETRY_DIR"}
    env["HOME"] = str(home)
    env.update(env_extra)
    return subprocess.run([sys.executable, str(guinea_pig)], capture_output=True,
                          text=True, env=env, cwd=str(REPO))


def home_ledger(home):
    return Path(home) / ".claude" / "cepa-telemetry"


for name in EMITTERS:
    check(f"{name} ainda existe (renomeado, este teste vira decoração)",
          (TESTS / name).is_file(), name)

# ── 1. no emitter touches the ledger of whoever runs ───────────────────────
destination = Path(tempfile.gettempdir()) / "cepa-telemetry-tests"
before = set(destination.glob("events-*.jsonl")) if destination.is_dir() else set()
size_before = {f: f.stat().st_size for f in before}

for name in EMITTERS:
    with tempfile.TemporaryDirectory(prefix="tele-home-") as home:
        r = run_test(TESTS / name, home)
        check(f"{name} continua passando com HOME descartável",
              r.returncode == 0, f"rc={r.returncode} {r.stderr[-300:]}")
        check(f"{name} NÃO cria ledger no HOME de quem roda",
              not home_ledger(home).exists(),
              f"criou {home_ledger(home)}: "
              f"{[p.name for p in home_ledger(home).glob('*')][:5]}")

after = set(destination.glob("events-*.jsonl")) if destination.is_dir() else set()
grew = bool(after - before) or any(
    f.stat().st_size > size_before.get(f, 0) for f in after)
check("…e os eventos foram para o ledger descartável, não sumiram",
      grew, f"destino={destination} arquivos={[p.name for p in after]}")

# ── 2. an explicitly requested destination is respected ────────────────────
with tempfile.TemporaryDirectory(prefix="tele-home-") as home, \
        tempfile.TemporaryDirectory(prefix="tele-dir-") as requested:
    r = run_test(GUINEA_PIG, home, CEPA_TELEMETRY_DIR=requested)
    check("teste que pede o próprio destino continua sendo obedecido",
          r.returncode == 0, f"rc={r.returncode} {r.stderr[-300:]}")
    check("…e escreve lá, não no descartável",
          any(Path(requested).glob("events-*.jsonl")),
          f"{[p.name for p in Path(requested).glob('*')]}")
    check("…e segue sem tocar o HOME",
          not home_ledger(home).exists(), str(home_ledger(home)))

# ── 3. the runner isolates on its own ──────────────────────────────────────
runner = (REPO / "tests" / "run-all.sh").read_text(encoding="utf-8")
check("run-all.sh exporta CEPA_TELEMETRY_DIR",
      "export CEPA_TELEMETRY_DIR=" in runner)
check("…sem atropelar um destino já escolhido por quem chamou",
      "${CEPA_TELEMETRY_DIR:-" in runner)

# ── 4. the pytest family also isolates ─────────────────────────────────────
conf = (REPO / "tests" / "conftest.py")
check("tests/conftest.py chama isola() (a família pytest não roda pelo caminho "
      "de script)", "isola()" in conf.read_text(encoding="utf-8"))

# ── 5. the next polluter does not pass silently ────────────────────────────
# Static sweep: whoever CITES an emitter hook must isolate. The rule is
# deliberately conservative — citing is not executing, and 5 of the files it
# covers today emit nothing. But the distance between citing and executing is one
# commit, and it was precisely that which left 7 tests polluting the ledger for a month.
# Isolating one that does not emit costs nothing; discovering the 8th polluter through the
# crooked metric cost this day of work.
missing = []
for f in sorted(TESTS.glob("test_*.py")):
    text = f.read_text(encoding="utf-8")
    if any(h in text for h in EMITTER_HOOKS) and not isolates_somehow(text):
        missing.append(f.name)
check("todo teste que executa hook emissor isola a telemetria",
      not missing, f"sem isolamento: {missing}")

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all telemetria-isolada tests passed")
