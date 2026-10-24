#!/usr/bin/env python3
"""Regression of the `--sweep` mode of /maestro:program-plan (P1, CS-1).

No third-party deps — run with `python3 tests/test_program_plan_sweep.py`.
Exits non-zero on the first failure.

`program-plan.md` is a conversational command (the step-by-step is followed by a
Claude agent, not executed by an interpreter) — there is no Python function to
call. What THIS test guards is the cheapest and most real regression: that the
instructions of the sweep mode remain in the file, naming the 5 pieces that CS-1
demands (docs/spec/planejador-de-lotes-paralelos.md):
  1. sweeps the WHOLE source, not only `--demandas`;
  2. stops at the next 2-3 waves (does not try to partition the whole backlog);
  3. a demand with an undeterminable surface enters alone in its own wave;
  4. suggests the slice ceiling instead of fixing 3;
  5. writes `cartorios:` in the plan from `common/bin/cepa-hotspots`.

The PROOF that the mechanism works (not only that the prose exists) is the real run
recorded in `.claude/programs/lotes-2026-08-23/plan.yaml` + the verdict of
`cepa-dor --wave 1` over it, documented in this change's commit — this
file does not repeat that proof, it only stops the prose from regressing silently.

Each `check()` below has the `id` of the `**[sweep:id]**` block it covers
embedded in the name (`[sweep:id] ...`). It is this embedding that
`common/bin/cepa-promptcov` reads to cross against the command's blocks and
point out a piece without coverage — see docs/promptcov.md.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CMD = REPO / "maestro" / "commands" / "program-plan.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def main():
    if not CMD.is_file():
        print(f"FAIL: {CMD} não existe")
        return 1

    text = CMD.read_text(encoding="utf-8")

    check("--sweep está no argument-hint", "--sweep" in text.splitlines()[2])
    check("[sweep:full-source] varre a fonte inteira (não só --demandas)",
          "Read the ENTIRE source" in text)
    check("[sweep:full-source] para nas próximas 2-3 ondas",
          "**2-3 waves**" in text)
    check("[sweep:full-source] nomeia a zona de enforcement como não-candidata a fork autônomo",
          "is not a candidate for autonomous fork" in text)
    check("[sweep:solo-wave] demanda indeterminável entra sozinha na própria onda",
          "**alone into its own wave**" in text)
    check("[sweep:wave-cap] sugere o teto de slices em vez de fixar 3",
          "not fixed at 3" in text and "**suggest** the ceiling" in text.lower())
    check("[sweep:cartorios] invoca cepa-hotspots para popular cartorios",
          "cepa-hotspots" in text and "cartorios:" in text)
    check("[sweep:cartorios] aponta o campo cartorios como opcional e no topo do plano",
          "the new and\n   optional field" in text or "the new and optional field" in text)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
