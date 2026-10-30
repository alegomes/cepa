#!/usr/bin/env python3
"""Regression tests: cepa-doctor reports (never fixes) the queue × BACKLOG.md divergence.

## Why this check exists

The "single queue" (BACKLOG.md, Jira and plan.yaml converge on plan.yaml) only
holds if something charges for the divergence among the three. `cepa-plan divergencia` does
the calculation (BACKLOG.md sections without `**Plano:**`, `**Plano:**` citing an id that
does not exist in the queue); this check only calls that command and translates the result into
✓/⚠, at the session opening that already runs the doctor. It never fixes — closing a
section or inventing a `**Plano:**` is the owner's decision.

## Why it is gated on having BACKLOG.md AND a resolvable queue

A repo without `BACKLOG.md` has nothing to compare. A repo with MORE THAN ONE
`single-track` queue is ambiguous — the doctor does not guess which one the owner wants to see, so
it stays quiet instead of risking the wrong queue.

Run: python3 tests/test_doctor_queue_divergence.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


PLAN = """schema_version: 2
mode: single-track
program: WEGO
source: teste
items:
- id: WEGO-1
  title: primeiro
  why: porque
  status: pending
  blocked_by: []
  human_pending: null
  evidence: null
"""


def build(tmp, with_backlog=True, backlog_text=None, with_queue=True,
          with_board_flow=False):
    root = Path(tmp)
    if with_queue:
        d = root / ".claude" / "programs" / "WEGO"
        d.mkdir(parents=True)
        (d / "plan.yaml").write_text(PLAN, encoding="utf-8")
    if with_backlog:
        (root / "BACKLOG.md").write_text(
            backlog_text or "## Seção X\n\n**Plano:** WEGO-1\n",
            encoding="utf-8")
    if with_board_flow:
        (root / "board-flow.yaml").write_text(
            "site: x\nproject_key: WEGO\nstatus_map:\n  to_do: To Do\n",
            encoding="utf-8")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    return root


def run_doctor(root):
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                       cwd=str(root), capture_output=True, text=True, timeout=120)
    return p.stdout + p.stderr


def test_without_divergence_confirms():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp)
        out = run_doctor(root)
        check("fila × BACKLOG em dia confirma", "[plano]" in out and "✓" in out, out)


def test_section_without_plan_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, backlog_text="## Seção sem plano\n\nnada aqui.\n")
        out = run_doctor(root)
        check("seção sem `**Plano:**` gera aviso",
              "[plano]" in out and "⚠" in out, out)
        check("...e nomeia a seção", "Seção sem plano" in out, out)


def test_plan_citing_id_outside_the_queue_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, backlog_text="## Seção Y\n\n**Plano:** WEGO-999\n")
        out = run_doctor(root)
        check("`**Plano:**` com id inexistente gera aviso",
              "[plano]" in out and "⚠" in out, out)
        check("...e nomeia o id", "WEGO-999" in out, out)


def test_without_backlog_is_silent():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, with_backlog=False)
        out = run_doctor(root)
        check("sem BACKLOG.md: nada a comparar, silêncio",
              "[plano]" not in out, out)


def test_two_queues_without_board_flow_is_ambiguous_and_silent():
    """Without `board-flow.yaml` and with MORE than one `single-track` queue, the doctor
    cannot pick one of them at random — taking "the first it finds" is
    exactly the ambiguity `resolve_fila_unica` exists to refuse.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("WEGO", "OUTRA"):
            d = root / ".claude" / "programs" / name
            d.mkdir(parents=True)
            (d / "plan.yaml").write_text(PLAN.replace("program: WEGO", f"program: {name}"),
                                         encoding="utf-8")
        (root / "BACKLOG.md").write_text("## Seção sem plano\n\nnada aqui.\n",
                                         encoding="utf-8")
        (root / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "base"], cwd=root, check=True)
        out = run_doctor(root)
        check("duas filas ambíguas: nenhuma linha [plano] no relatório",
              "[plano]" not in out, out)


def test_resolves_via_board_flow_project_key():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, with_board_flow=True,
                     backlog_text="## Seção Z\n\n**Plano:** WEGO-1\n")
        out = run_doctor(root)
        check("resolve a fila pelo project_key do board-flow.yaml e confirma",
              "[plano]" in out and "✓" in out, out)


def main():
    print("cepa-doctor — divergência da fila única × BACKLOG.md\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
