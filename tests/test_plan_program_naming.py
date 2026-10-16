#!/usr/bin/env python3
"""Contract tests: a queue is found by its work slice, never by the project key.

The collision, verified on disk 2026-08-18 (wego-acesso-backend): the main clone
held `.claude/programs/WEGO/` (To Do, 48 items) and
`.claude/programs/WEGO-in-progress/` side by side. A key names a project, not a
slice, so a lookup "board-flow.yaml -> defaults.project_key -> <key>/plan.yaml"
silently picks `WEGO/` forever. `/common:next` must instead follow the same rule
as `cepa-plan`: one queue -> that one; several -> list and ask.

The guard is mechanical because prose saying "don't pick by key" erodes quietly.
Half A pins the prompt contracts (next.md, the doc); half B runs the real
`cepa-plan status` on temp repos and pins the three paths.

Run with `python3 tests/test_plan_program_naming.py`.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOC = REPO / "docs" / "execution-plan.md"
NEXT = REPO / "common" / "commands" / "next.md"
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"

FAILURES = []


def check(label, cond, extra=""):
    if cond:
        print(f"✓ {label}")
    else:
        print(f"✗ {label}" + (f" — {extra}" if extra else ""))
        FAILURES.append(label)


def read(p):
    return p.read_text(encoding="utf-8")


def flat(txt):
    return " ".join(txt.split())


def body(p):
    txt = read(p)
    if txt.startswith("---"):
        end = txt.find("\n---", 3)
        if end != -1:
            return txt[end + 4:]
    return txt


PLAN = """schema_version: 2
mode: single-track
program: {name}
source: "teste · {name}"
items:
  - id: {name}-1
    title: "item um de {name}"
    why: "primeiro"
    status: pending
    blocked_by: []
    human_pending: null
"""


def make_repo(tmp, names):
    subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "init", "-q", tmp],
                   check=True)
    (Path(tmp) / "board-flow.yaml").write_text(
        "defaults:\n  project_key: WEGO\n  status_map:\n    to_do: To Do\n",
        encoding="utf-8")
    for n in names:
        d = Path(tmp) / ".claude" / "programs" / n
        d.mkdir(parents=True)
        (d / "plan.yaml").write_text(PLAN.format(name=n), encoding="utf-8")


def run_status(names):
    with tempfile.TemporaryDirectory() as tmp:
        make_repo(tmp, names)
        return subprocess.run(
            [sys.executable, str(CEPA_PLAN), "status", "--repo", tmp, "--json"],
            capture_output=True, text=True, timeout=60)


def half_a():
    nxt = flat(body(NEXT))
    check("next: seção '### 1. Locate the plan'", "### 1. Locate the plan" in nxt)
    check("next: regra 'Exactly one' single-track", "Exactly one" in nxt
          and "mode: single-track" in nxt)
    check("next: regra negativa 'Never pick' + <project_key>",
          "Never pick" in nxt and "<project_key>" in nxt)
    check("next: chama a pasta de 'work slice'", "work slice" in nxt)
    check("next: cita o caso WEGO-in-progress", "WEGO-in-progress" in nxt)
    check("next: não resolve por <programs>/<project_key>/plan.yaml",
          "<programs>/<project_key>/plan.yaml" not in nxt.replace(
              "`<programs>/<project_key>/plan.yaml` automatically", ""),
          "só pode aparecer na regra negativa")
    check("next: não lê defaults.project_key", "defaults.project_key" not in nxt)
    check("next: liga a prosa à ferramenta (cepa-plan status)",
          "cepa-plan status" in nxt)

    doc = flat(read(DOC))
    check("doc: seção '### What the file is called'",
          "### What the file is called" in doc)
    check("doc: 'work slice'", "work slice" in doc)
    check("doc: cita WEGO-in-progress", "WEGO-in-progress" in doc)
    check("doc: 'never pick' + <project_key>",
          "never pick" in doc.lower() and "<project_key>" in doc)
    check("doc: decisão do dono 2026-09-25", "2026-09-25" in doc)


def half_b():
    r = run_status(["wego-todo-agosto"])
    check("cenário 1: fila única com outro nome resolve (exit 0)",
          r.returncode == 0, f"rc={r.returncode} err={r.stderr!r}")
    check("cenário 1: a saída nomeia wego-todo-agosto",
          "wego-todo-agosto" in r.stdout, r.stdout[:200])

    r = run_status(["WEGO", "WEGO-in-progress"])
    check("cenário 2: duas filas -> exit 2", r.returncode == 2,
          f"rc={r.returncode}")
    check("cenário 2: stderr 'há mais de uma fila'",
          "há mais de uma fila" in r.stderr, r.stderr)
    check("cenário 2: stderr nomeia AS DUAS",
          "WEGO-in-progress" in r.stderr
          and "WEGO," in r.stderr.replace("WEGO-in-progress", ""), r.stderr)
    resolved = False
    try:
        resolved = bool(json.loads(r.stdout).get("items"))
    except Exception:
        pass
    check("cenário 2: não escolheu WEGO em silêncio",
          not resolved and "WEGO-1" not in r.stdout, r.stdout[:200])

    r = run_status([])
    check("cenário 3: nenhuma fila -> exit 2", r.returncode == 2,
          f"rc={r.returncode}")
    check("cenário 3: stderr 'nenhuma fila'", "nenhuma fila" in r.stderr,
          r.stderr)


def main():
    half_a()
    half_b()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
