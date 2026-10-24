#!/usr/bin/env python3
"""Regression: `twg ... --transition-id "<STATUS NAME>"` in the Jira gates.

The `twg` CLI accepts the status NAME in place of the transition id. `_jiramut`
only lowercased the name, so "In Review" reached the gates as
`in review`, which is no logical key at all. The `acceptance-gate` read that as a
lateral move and RELEASED a card with an incomplete audit toward Review
(reproduced on 2026-09-19). The `merge-truth-gate` had the same hole for
any closing status name that was not literally "done"
(e.g.: "Concluído").

Contract:
  - the status name becomes a logical key through the `status_map` of board-flow.yaml
    (technical name → key), or through the normalized form (space/hyphen → `_`);
  - a name that does not resolve to a known key = target NOT resolved, and the
    acceptance-gate blocks by default (bad config never opens a gate).

Run with `python3 tests/test_gate_status_by_name.py`.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ACCEPT = REPO / "common" / "hooks" / "acceptance-gate.py"
MERGE = REPO / "common" / "hooks" / "merge-truth-gate.py"
KEY = "PROJ-1"
FAILURES = []

BOARD_FLOW = """\
defaults:
  project_key: PROJ
  status_map:
    to_do: "A Fazer"
    in_progress: "Em Andamento"
    in_review: "Em Revisão"
    done: "Concluído"
    wont_do: "Descartados"
"""


def check(name, cond, detail=""):
    print(("  ok  " if cond else "FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAILURES.append(name)


def project(board_flow=None):
    d = Path(tempfile.mkdtemp(prefix="gate-nome-"))
    subprocess.run(["git", "init", "-q", str(d)], check=True)
    acc = d / ".claude" / "acceptance"
    acc.mkdir(parents=True)
    (acc / f"{KEY}.yaml").write_text(f"key: {KEY}\nstatus: incomplete\n", encoding="utf-8")
    if board_flow:
        (d / "board-flow.yaml").write_text(board_flow, encoding="utf-8")
    return d


def run_hook(hook, cwd, name):
    cmd = f'twg jira workitem transition --id {KEY} --transition-id "{name}"'
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd)})
    return subprocess.run([sys.executable, str(hook)], input=payload,
                          capture_output=True, text=True).returncode


# ── without board-flow.yaml: only the normalized form resolves ──────────────
without_map = project()
for name in ("In Review", "in review", "In-Review", "in_review", "Done", "DONE"):
    check(f"sem mapa, auditoria incompleta, '{name}' → BARRA",
          run_hook(ACCEPT, without_map, name) == 2)
for name in ("In Progress", "To Do"):
    check(f"sem mapa, '{name}' (devolução) → PASSA", run_hook(ACCEPT, without_map, name) == 0)
check("sem mapa, nome desconhecido 'Homologação' → BARRA (alvo não resolvido)",
      run_hook(ACCEPT, without_map, "Homologação") == 2)

# ── with a status_map in Portuguese: the technical name resolves through the table ──
with_map = project(BOARD_FLOW)
for name in ("Em Revisão", "em revisão", "Concluído"):
    check(f"com mapa, '{name}' → BARRA", run_hook(ACCEPT, with_map, name) == 2)
for name in ("Em Andamento", "A Fazer", "Descartados"):
    check(f"com mapa, '{name}' (devolução) → PASSA", run_hook(ACCEPT, with_map, name) == 0)

# ── merge-truth-gate: closing by technical name counts as closing ───────────
# Without an integration branch the gate has nothing to check and exits 0 anyway;
# what is verified here is that the NAME arrives resolved as `done`, through the
# function the two gates share.
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _jiramut as J  # noqa: E402

check("resolve 'Concluído' → done pelo status_map",
      J.logical_status("Concluído", with_map) == "done")
check("resolve 'In Review' → in_review sem mapa",
      J.logical_status("In Review", without_map) == "in_review")
check("nome desconhecido → None", J.logical_status("Homologação", without_map) is None)
check("None → None", J.logical_status(None, without_map) is None)

print()
if FAILURES:
    print(f"{len(FAILURES)} falha(s)")
    sys.exit(1)
print("tudo verde")
