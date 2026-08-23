#!/usr/bin/env python3
"""Regression test for P4/CS-5 — rename counts as a write on both paths.

No third-party deps beyond PyYAML (build-hex's path-lock needs it to parse
build-hex.yaml, but the default-layout path used here never touches it) — run
with `python3 tests/test_write_lock_rename.py`. Exits non-zero on failure.

docs/spec/planejador-de-lotes-paralelos.md, CS-5:
  "Um slice travado para escrever em `api-rest/**` que renomeia um arquivo
  para `application/**` é barrado, porque renomear conta como escrita na
  origem E no destino."
  Teste vermelho: hoje um `git mv` de um caminho declarado para um caminho
  não declarado passa pela trava sem ser barrado.

This drives the full `bash-path-lock.py` PIPELINE end-to-end (subprocess, real
exit code) — not just the target-extraction helper, which
test_bash_path_lock_redir.py already covers. The scenario that mattered and
was NOT covered by the old destination-only check: renaming a file FROM a
path outside the agent's surface TO a path inside it. The destination alone
was always allowed, so the write silently passed — the agent had just deleted
a file it was never allowed to touch.

The hook ships in every topology; drive every copy.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = sorted(REPO.glob("*/hooks/bash-path-lock.py"))

FAILURES = []


def run(hook, agent_type, command, cwd):
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "agent_type": agent_type,
        "cwd": str(cwd),
    }
    p = subprocess.run(
        [sys.executable, str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stderr


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        print(f"FAIL  {label}  {detail}")
        FAILURES.append(label)


def main():
    if not HOOKS:
        print("FAIL: no */hooks/bash-path-lock.py found under", REPO)
        return 1

    # domain-dev's canonical allowlist (build-hex default layout) is
    # domain/src/main/** + application/src/main/**. infrastructure/ is
    # someone else's lane (adapter-dev).
    import tempfile

    for hook in HOOKS:
        topo = hook.parent.parent.name
        if topo != "build-hex":
            # Only build-hex ships role-keyed agents (domain-dev, api-dev...);
            # the other 4 topologies gate different agent names. Skip those —
            # the mechanism under test (source counted, not just destination
            # in _segment_targets) is byte-identical across all 5 copies,
            # guarded separately by test_lock_copies_drift.py.
            continue

        proj = Path(tempfile.mkdtemp())

        # rename FROM an allowed path TO a disallowed one — already caught by
        # the old destination-only check; must keep working.
        rc, err = run(hook, "build-hex:domain-dev",
                      "git mv domain/src/main/Foo.java infrastructure/src/main/Foo.java",
                      proj)
        check(f"[{topo}] domain-dev: rename INTO disallowed dest is blocked",
              rc == 2, f"exit={rc} stderr={err[:200]}")

        # rename FROM a disallowed path TO an allowed one — this is the gap
        # CS-5 exists to close: before the fix, only the (allowed) destination
        # was checked, so this passed silently.
        rc, err = run(hook, "build-hex:domain-dev",
                      "git mv infrastructure/src/main/Foo.java domain/src/main/Foo.java",
                      proj)
        check(f"[{topo}] domain-dev: rename FROM disallowed source is blocked",
              rc == 2, f"exit={rc} stderr={err[:200]}")
        check(f"[{topo}] the block names the origin path",
              "infrastructure/src/main/Foo.java" in err, err[:300])

        # rename fully inside the agent's own lane — must still pass.
        rc, err = run(hook, "build-hex:domain-dev",
                      "git mv domain/src/main/Old.java domain/src/main/New.java",
                      proj)
        check(f"[{topo}] domain-dev: rename inside own lane is allowed",
              rc == 0, f"exit={rc} stderr={err[:200]}")

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
