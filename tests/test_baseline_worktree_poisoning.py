#!/usr/bin/env python3
"""Regression tests for the poisoned-baseline fix (proof gate vs advance gate).

No third-party deps — run with `python3 tests/test_baseline_worktree_poisoning.py`.
Exits non-zero on first failure.

Guards the contract found on 2026-07-16 (wego session): a deliberate RED run
in a throwaway proof worktree (`cd /tmp/wt && ./mvnw verify`) must NOT touch
the main repo's .claude/last-build.json — otherwise gate-advance blocks the
next push on another directory's failure. Covers both hooks:

  capture-build-result.py
    - out-of-root `cd X &&` RED  → recorded in X/.claude, main untouched;
    - quoted paths and `;` separators too;
    - no-cd build                → main baseline written (unchanged behavior);
    - in-root `cd subdir &&`     → main baseline written (monorepo behavior).

  mark-build-stale.py
    - out-of-root source edit    → exit 0, main untouched (used to CRASH on
      Path.relative_to and, conceptually, to poison the baseline as STALE);
    - in-root source edit        → STALE written (unchanged behavior).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CAPTURE = REPO / "common" / "hooks" / "capture-build-result.py"
STALE = REPO / "common" / "hooks" / "mark-build-stale.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run_hook(script, payload):
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )


def bash_payload(cwd, command, output):
    return {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": output},
        "cwd": str(cwd),
    }


def read_state(root):
    p = Path(root) / ".claude" / "last-build.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


with tempfile.TemporaryDirectory() as tmp:
    main_repo = Path(tmp) / "main-repo"
    worktree = Path(tmp) / "proof-wt"
    for d in (main_repo, worktree):
        d.mkdir()

    # ── capture-build-result: out-of-root RED must not poison main ─────────
    r = run_hook(CAPTURE, bash_payload(
        main_repo, f"cd {worktree} && ./mvnw verify", "... BUILD FAILURE ..."))
    check("out-of-root RED: hook exits 0", r.returncode == 0, r.stderr)
    check("out-of-root RED: main baseline untouched", read_state(main_repo) is None)
    wt_state = read_state(worktree)
    check("out-of-root RED: recorded in the worktree",
          wt_state is not None and wt_state["status"] == "FAILURE", str(wt_state))
    check("out-of-root RED: stderr says main untouched",
          "main baseline untouched" in r.stderr, r.stderr[:200])

    # quoted path + `;` separator variant, green this time
    quoted = Path(tmp) / "wt with spaces"
    quoted.mkdir()
    r = run_hook(CAPTURE, bash_payload(
        main_repo, f'cd "{quoted}"; ./mvnw verify', "... BUILD SUCCESS ..."))
    check("quoted path + ';': main untouched", read_state(main_repo) is None)
    q_state = read_state(quoted)
    check("quoted path + ';': recorded in the worktree",
          q_state is not None and q_state["status"] == "SUCCESS", str(q_state))

    # ── unchanged behavior: no cd → main baseline written ──────────────────
    r = run_hook(CAPTURE, bash_payload(
        main_repo, "./mvnw verify", "... BUILD SUCCESS ..."))
    m_state = read_state(main_repo)
    check("no-cd build writes main baseline",
          m_state is not None and m_state["status"] == "SUCCESS", str(m_state))

    # ── unchanged behavior: in-root cd (monorepo) → main baseline written ──
    sub = main_repo / "backend"
    sub.mkdir()
    r = run_hook(CAPTURE, bash_payload(
        main_repo, "cd backend && ./mvnw verify", "... BUILD FAILURE ..."))
    m_state = read_state(main_repo)
    check("in-root `cd subdir` still writes main baseline",
          m_state is not None and m_state["status"] == "FAILURE", str(m_state))
    check("in-root `cd subdir` does not create sub-baseline",
          read_state(sub) is None)

    # ── mark-build-stale: out-of-root edit must not stale (nor crash) ──────
    # reset main to a known green baseline first
    (main_repo / ".claude" / "last-build.json").write_text(
        json.dumps({"status": "SUCCESS", "at": "2026-07-16T00:00:00+00:00"}))
    r = run_hook(STALE, {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(worktree / "src" / "main" / "X.java")},
        "cwd": str(main_repo),
    })
    check("out-of-root edit: exit 0 (used to crash)", r.returncode == 0,
          f"rc={r.returncode} stderr={r.stderr[:200]}")
    check("out-of-root edit: main baseline stays SUCCESS",
          read_state(main_repo)["status"] == "SUCCESS")

    # ── unchanged behavior: in-root edit marks STALE ───────────────────────
    r = run_hook(STALE, {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(main_repo / "src" / "main" / "X.java")},
        "cwd": str(main_repo),
    })
    m_state = read_state(main_repo)
    check("in-root edit marks STALE",
          r.returncode == 0 and m_state["status"] == "STALE", str(m_state))
    check("in-root edit records relative path",
          m_state["after_edit_to"] == "src/main/X.java", str(m_state))

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {FAILURES}")
    sys.exit(1)
print("all baseline-worktree-poisoning tests passed")
