#!/usr/bin/env python3
"""A proposed waiver is not proof: the guard blocks `proven` next to it.

Origin (BACKLOG.md § "Waiver recorded in the owner's name during an
autonomous run", fb-20261014-3): in an autonomous run the waiver becomes a PROPOSAL
(board-flow/bin/waivers.py `propor`), and a proposal is a question to the owner.
The artifact that carries it (`waiver_proposto: <path>`) stays NEEDS-HUMAN.

  - `proven` + `waiver_proposto` (or dispensa_proposta/waiver/dispensa) -> BLOCKS;
  - `needs-human` / `unproven` + the same key -> PASSES;
  - `proven` without the key -> PASSES (previous behavior);
  - the fallback without PyYAML sees the top-level key.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from _telemetria_isolada import isola

isola()

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "build-hex" / "hooks" / "proof-verdict-guard.py"
ARTIFACT = str(Path(tempfile.gettempdir()) / "proj" / "docs" / "proof" / "WEGO-2000.yaml")
FAILURES = []

CLEAN = """\
scope:
  changed_classes:
    - class: "com.wego.AssinaturaUseCase"
      module: application
      external_observable: true
      substituted_by_double: none
levels:
  l3_load_bearing:
    pit:
      status: ran
    perturbation:
      status: pass
  l2_coverage:
    status: pass
  l4_adversarial_input:
    status: clean
"""


def artifact_text(verdict="proven", extra=""):
    return f"schema_version: 2\ncard: WEGO-2000\nverdict: {verdict}\n{extra}{CLEAN}"


def run(content):
    payload = json.dumps({"tool_name": "Write",
                          "tool_input": {"file_path": ARTIFACT, "content": content},
                          "cwd": str(Path(tempfile.gettempdir()))})
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True)


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


WAIVER = "waiver_proposto: .claude/waivers/teste-cego--plugsignadapter.yaml\n"

r = run(artifact_text("proven", WAIVER))
check("proven + waiver_proposto -> BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")
check("...e a mensagem diz waiver_proposto e needs-human",
      "waiver_proposto" in r.stderr and "needs-human" in r.stderr, r.stderr[:300])

for key in ("dispensa_proposta", "waiver", "dispensa"):
    r = run(artifact_text("proven", f"{key}: .claude/waivers/x.yaml\n"))
    check(f"proven + {key} -> BLOQUEIA", r.returncode == 2, f"rc={r.returncode}")

for v in ("needs-human", "unproven"):
    r = run(artifact_text(v, WAIVER))
    check(f"{v} + waiver_proposto -> PASSA", r.returncode == 0, r.stderr[:300])

r = run(artifact_text("proven"))
check("proven sem a chave -> PASSA (inalterado)", r.returncode == 0, r.stderr[:300])

r = run(artifact_text("proven", "waiver_proposto: null\n"))
check("proven + waiver_proposto nulo -> PASSA (nada proposto)", r.returncode == 0,
      r.stderr[:300])

# Fallback without PyYAML: the lines function sees the top-level key.
spec = importlib.util.spec_from_file_location("guard", HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
v = guard.parse_with_lines(artifact_text("proven", WAIVER))
check("parse_with_lines marca a dispensa (6o elemento)", len(v) == 6 and v[5] is True, v)
v = guard.parse_with_lines(artifact_text("proven"))
check("parse_with_lines sem a chave -> False", v[5] is False, v)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all proof waiver_proposto tests passed")
