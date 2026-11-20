#!/usr/bin/env python3
"""The Cepa commands run in a repo whose `python3` has no PyYAML
(docs/spec/cepa-roda-sem-pyyaml-instalado.md).

"A python3 without PyYAML" is simulated, on any machine and in CI, by a
`python3` shim at the front of PATH that execs the real interpreter with `-S`
(no site-packages). The command under test is run DIRECTLY through its
shebang (`#!/usr/bin/env python3`), the way a user's shell runs it, never via
`sys.executable`.

This file does not import yaml: fixtures are written as YAML text, so it runs
in the same environment it simulates. Later success criteria add their cases
here, reusing `make_shim`, `make_repo` and `run_direct`.

Cases:
  CS-1  `cepa-plan ready` lists the ready item, exit 0, no "PyYAML" on stderr

Run with `python3 tests/test_cepa_runs_without_pyyaml.py`.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
FAILURES = []


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def make_shim(tmp):
    """Dir with an executable `python3` that runs the real one with -S."""
    d = Path(tmp) / "shim"
    d.mkdir()
    shim = d / "python3"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -S "$@"\n',
                    encoding="utf-8")
    shim.chmod(0o755)
    return d


def make_repo(tmp, queue="q", item_id="X-1"):
    """Temp git repo with one single-track queue holding one pending item."""
    root = Path(tmp) / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    d = root / ".claude" / "queues" / queue
    d.mkdir(parents=True)
    (d / "queue.yaml").write_text(
        "schema_version: 2\n"
        "mode: single-track\n"
        f"queue: {queue}\n"
        "source: teste\n"
        "items:\n"
        f"- id: {item_id}\n"
        f"  title: item {item_id}\n"
        "  why: porque\n"
        "  status: pending\n"
        "  blocked_by: []\n"
        "  human_pending: null\n"
        "  evidence: null\n",
        encoding="utf-8")
    return root


def run_direct(script, args, cwd, shim_dir, extra_env=None):
    """Run `script` through its shebang with the shim first on PATH."""
    env = dict(os.environ)
    env["PATH"] = f"{shim_dir}{os.pathsep}{env.get('PATH', '')}"
    env.pop("PYTHONPATH", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run([str(script)] + list(args), capture_output=True,
                          text=True, cwd=str(cwd), env=env)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        shim = make_shim(tmp)
        probe = subprocess.run(
            [str(shim / "python3"), "-c", "import yaml"],
            capture_output=True, text=True,
            env={**os.environ, "PATH": f"{shim}{os.pathsep}{os.environ['PATH']}"})
        check("shim: this python3 really has no PyYAML",
              probe.returncode != 0, probe.stdout + probe.stderr)

        root = make_repo(tmp)

        # CS-1
        r = run_direct(CEPA_PLAN, ["ready"], root, shim)
        check("CS-1 cepa-plan ready exit 0 without PyYAML",
              r.returncode == 0, f"exit {r.returncode}: {r.stderr.strip()}")
        check("CS-1 cepa-plan ready lists the ready item",
              "X-1" in r.stdout, r.stdout)
        check("CS-1 no 'PyYAML' on stderr", "PyYAML" not in r.stderr, r.stderr)

    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ cepa runs without PyYAML")
    return 0


if __name__ == "__main__":
    sys.exit(main())
