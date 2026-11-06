#!/usr/bin/env python3
"""cepa-doctor flags TRACKED files that hooks write (fb-20261105-3), and agrees
with cepa-until that an untracked `queue.yaml.bak` is not dirt.

Run: python3 tests/test_doctor_tracked_runtime.py
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


def build(tmp, tracked_runtime=False, queue=False):
    root = Path(tmp)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    if tracked_runtime:
        (root / ".claude").mkdir()
        (root / ".claude" / "last-build.json").write_text("{}\n", encoding="utf-8")
    if queue:
        d = root / ".claude" / "queues" / "fila"
        d.mkdir(parents=True)
        (d / "queue.yaml").write_text(
            "schema_version: 2\nmode: single-track\nprogram: fila\nsource: t\n"
            "items:\n- id: a1\n  title: p\n  why: w\n  status: pending\n"
            "  blocked_by: []\n  human_pending: null\n  evidence: null\n",
            encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    return root


def doctor(root):
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"], cwd=str(root),
                       capture_output=True, text=True, timeout=120)
    return p.stdout + p.stderr


with tempfile.TemporaryDirectory() as tmp:
    out = doctor(build(tmp, tracked_runtime=True))
    check("runtime versionado → aviso", "⚠ [runtime]" in out or
          ("[runtime]" in out and "⚠" in out), out[-500:])
    check("...nomeia o arquivo", ".claude/last-build.json" in out, out[-500:])

with tempfile.TemporaryDirectory() as tmp:
    out = doctor(build(tmp))
    check("sem runtime versionado → ok", "[runtime]" in out
          and "nenhum arquivo de runtime" in out, out[-500:])

with tempfile.TemporaryDirectory() as tmp:
    root = build(tmp, queue=True)
    (root / ".claude/queues/fila/queue.yaml.bak").write_text("x\n", encoding="utf-8")
    out = doctor(root)
    check("queue.yaml.bak não conta: execucao ok", "[execucao]" in out
          and "⚠ [execucao]" not in out, out[-500:])

with tempfile.TemporaryDirectory() as tmp:
    # A project that tracks .claude/expertise/*.yaml on purpose: a hook writing
    # there is a change the wrap-up commits, not a file to untrack.
    root = Path(tmp)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    (root / ".claude" / "expertise").mkdir(parents=True)
    (root / ".claude" / "expertise" / "qa.yaml").write_text("a: 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    out = doctor(root)
    check("expertise versionado de propósito → sem aviso", "⚠ [runtime]" not in out
          and "nenhum arquivo de runtime" in out, out[-500:])

if FAILURES:
    print(f"\n{len(FAILURES)} FAILED: {FAILURES}")
    sys.exit(1)
print("\nall ok")
