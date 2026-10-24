#!/usr/bin/env python3
"""The cepa queue has somewhere to be executed (item topologia-do-cepa, 2026-09-25).

No dependencies — run with `python3 tests/test_cepa_topology.py`.
Exits non-zero on failure.

`/common:drain-plan` executes each item the way `/common:autonomous-start`
dispatches: reads `.claude/topology` and calls `/<topology>:plan-build-validate`, or
`/<topology>:reproduce-fix-verify` when the item is a defect. cepa did not have the
file, and step 1 of autonomous-start aborted ("No topology configured").
No topology fit: build-solo, the only one without path-lock in apps/* or in
Maven layers, had no flow command.

What is locked:

  - **cepa declares a topology.** Without the file, the abort of step 1 comes back.
  - **The declared topology is a plugin of this repo.** A name that does not match an
    installed plugin also aborts ("doesn't match any installed plugin").
  - **It has the two flows that drain-plan dispatches.** Having only one makes the
    first defect item (or the first feature one) abort at step 2.
  - **The flows run the suite and commit on the branch.** Under `cepa-until` the item
    works on the night branch and the supervisor expects a commit, not a dirty tree.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ("plan-build-validate", "reproduce-fix-verify")

fails = []


def case(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f" — {detail}"))
    if not cond:
        fails.append(name)


marker = ROOT / ".claude" / "topology"
case("o cepa declara topologia em .claude/topology", marker.is_file(),
     "arquivo ausente: o autonomous-start aborta no passo 1")
topology = marker.read_text().strip() if marker.is_file() else ""

manifest = ROOT / topology / ".claude-plugin" / "plugin.json"
plugin_name = (json.loads(manifest.read_text()).get("name")
               if topology and manifest.is_file() else None)
case("a topologia é um plugin deste repo", plugin_name == topology,
     f"{topology!r} não tem {manifest.relative_to(ROOT) if topology else 'manifesto'}")

for flow in FLOWS:
    cmd = ROOT / topology / "commands" / f"{flow}.md"
    case(f"{topology} tem /{topology}:{flow}", bool(topology) and cmd.is_file(),
         f"{cmd.relative_to(ROOT)} ausente: o drain-plan aborta no passo 2")
    if cmd.is_file():
        text = cmd.read_text()
        case(f"/{topology}:{flow} roda a suíte em primeiro plano",
             "tests/run-all.sh" in text and "foreground" in text,
             "sem suíte colhida no mesmo turno, o item fecha sem prova")
        case(f"/{topology}:{flow} commita na branch atual, sem push",
             "Commit" in text and "No push" in text,
             "o supervisor do cepa-until espera commit na branch da noite")

sys.exit(1 if fails else 0)
