#!/usr/bin/env python3
"""Regression tests: dirty tree with a queue waiting for unattended execution.

## Why this check exists

`cepa-until` (the unattended execution window) REFUSES to start with a dirty
tree — it is how it separates, in the morning, what the run did from what was
already there. The refusal is instant, so discovering the problem at 11pm costs
the whole window. The doctor charges for it beforehand, when the session opens.

## Why the warning is GATED on the queue, and not loose

A dirty tree is the NORMAL state of someone who is working. A warning on every
session opening is the noise the user learns to skip — the same reason the
doctor's summarized mode does not print "everything is ok". The warning only
appears when both things are true at the same time: a `single-track` queue
with a `pending` item exists, AND the tree is dirty.

The test that matters most here is precisely the SILENCE one: a dirty tree
without a pending queue must say nothing.

Run: python3 tests/test_doctor_dirty_tree.py
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
program: fila
source: teste
items:
- id: a1
  title: primeiro
  why: porque
  status: {status}
  blocked_by: []
  human_pending: null
  evidence: null
"""


def build(tmp, status="pending", mode="single-track", with_queue=True):
    root = Path(tmp)
    if with_queue:
        d = root / ".claude" / "programs" / "fila"
        d.mkdir(parents=True)
        (d / "plan.yaml").write_text(
            PLAN.format(status=status).replace("mode: single-track",
                                                f"mode: {mode}"),
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


def make_dirty(root):
    (root / "lixo.txt").write_text("trabalho não commitado\n", encoding="utf-8")


def test_dirty_with_pending_queue_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp)
        make_dirty(root)
        out = run_doctor(root)
        check("avisa quando há fila pendente E árvore suja",
              "[execucao]" in out and "⚠" in out, out[-600:])
        check("...e nomeia o comando que vai recusar",
              "cepa-until" in out, out[-600:])
        check("...e nomeia o escape", "--dirty-ok" in out, out[-600:])
        check("...e nomeia a fila", "`fila`" in out, out[-600:])


def test_dirty_without_pending_queue_is_SILENT():
    """The case that decides whether the check is useful or noise."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, status="done")
        make_dirty(root)
        out = run_doctor(root)
        check("fila sem item pendente + árvore suja → não diz nada",
              "[execucao]" not in out, out[-600:])

    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, with_queue=False)
        make_dirty(root)
        out = run_doctor(root)
        check("repo sem fila nenhuma + árvore suja → não diz nada",
              "[execucao]" not in out, out[-600:])


def test_waves_plan_does_not_count_as_queue():
    """`mode: waves` belongs to /maestro:run, which does not go through cepa-until."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, mode="waves")
        make_dirty(root)
        out = run_doctor(root)
        check("plano de ondas não dispara o aviso", "[execucao]" not in out,
              out[-600:])


def test_clean_with_pending_queue_confirms_it_can_start():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp)
        out = run_doctor(root)
        check("árvore limpa + fila pendente → confirma que larga",
              "[execucao]" in out and "✓" in out, out[-600:])
        check("...e não é um aviso", "⚠ [execucao]" not in out, out[-600:])


def test_cepa_until_record_does_not_count_as_dirt():
    """The record of previous runs lives in `.claude/programs/<queue>/until/`
    and `cepa-until` does not refuse because of it — so the doctor must not
    warn that it will refuse.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp)
        # the doctor writes `.claude/doctor-last-run` on the 1st pass; outside the count
        (root / ".gitignore").write_text(".claude/doctor-last-run\n",
                                         encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "ignore"], cwd=root, check=True)
        d = root / ".claude" / "programs" / "fila" / "until"
        d.mkdir(parents=True)
        (d / "2026-09-26-1809.jsonl").write_text("{}\n", encoding="utf-8")
        (d / "2026-09-26-1809.log").write_text("saida\n", encoding="utf-8")
        out = run_doctor(root)
        check("só o registro do run → confirma que larga",
              "[execucao]" in out and "⚠ [execucao]" not in out, out[-600:])
        make_dirty(root)
        out = run_doctor(root)
        check("registro + sujeira de verdade → ainda avisa",
              "⚠ [execucao]" in out and "1 arquivo(s)" in out,
              [l for l in out.splitlines() if "execucao" in l])


def main():
    print("cepa-doctor — árvore suja vs. fila pendente\n")
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
