#!/usr/bin/env python3
"""Tests for the zero-token hook replay (tests/replay/).

No third-party deps - run with `python3 tests/test_hook_replay.py`.
Exits non-zero on failure.

  (a) every call of the corpus decides, in the working tree, what its label
      `expect` says (a decision changed without the label changing fails here);
  (b) the comparison works: in a scratch repo, one deliberately weakened rule
      moves the numbers of that hook between versions and of no other hook;
  (c) hygiene: the corpus is hand-written and neutral (R3): no personal paths,
      every call has a valid `expect`.
"""

import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from _isolated_telemetry import isolate

isolate()

REPO = Path(__file__).resolve().parent.parent
REPLAY = REPO / "tests" / "replay"
RUN = REPLAY / "run.py"
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def replay(*args):
    r = subprocess.run([sys.executable, str(RUN), "--json", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None, r.stderr
    return json.loads(r.stdout), r.stderr


def scenario_files():
    return sorted(REPLAY.glob("*/*.json"))


def test_labels_hold_in_worktree():
    sys.path.insert(0, str(REPLAY))
    import run  # noqa: E402
    ids = sorted(p.name for p in REPLAY.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
    bad = []
    n = 0
    with tempfile.TemporaryDirectory() as tel:
        for sc in run.load_scenarios(ids):
            for r in run.run_scenario(sc, str(REPO), tel):
                n += 1
                if r["decision"] != r["call_def"]["expect"]:
                    bad.append(f"{r['scenario']} :: {r['call']} "
                               f"(expect {r['call_def']['expect']}, got {r['decision']})")
    check(f"all {n} corpus calls match their label", not bad and n > 0, "; ".join(bad))
    check("covers the three hooks", set(ids) >= {"bash-path-lock", "maven-reactor-guard", "gate-advance"})


def test_comparison_shows_a_changed_rule():
    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td) / "scratch"
        for d in ("common/hooks", "build-hex/hooks"):
            shutil.copytree(REPO / d, scratch / d, ignore=shutil.ignore_patterns("__pycache__"))

        def g(*a):
            subprocess.run(["git", "-C", str(scratch), *a], capture_output=True, check=True)
        g("init", "-q", "-b", "main")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        g("config", "commit.gpgsign", "false")
        g("add", "-A")
        g("commit", "-qm", "base")
        hook = scratch / "common/hooks/maven-reactor-guard.py"
        text = hook.read_text(encoding="utf-8")
        marker = "def main():\n"
        check("marker for weakening found", marker in text)
        # Weaken the covered rule: the guard never blocks.
        hook.write_text(text.replace(marker, marker + "    sys.exit(0)\n", 1), encoding="utf-8")
        g("commit", "-qam", "weaken maven-reactor-guard")

        rep, err = replay("--repo", str(scratch), "--ref", "HEAD~1")
        check("replay against a scratch repo runs", rep is not None, err)
        if rep is None:
            return
        h = rep["hooks"]
        new, old = h["maven-reactor-guard"]["worktree"], h["maven-reactor-guard"]["HEAD~1"]
        check("weakened hook denies less", new["denials"] < old["denials"], f"{new} vs {old}")
        check("weakened hook has more mismatches", new["mismatches"] > old["mismatches"], f"{new} vs {old}")
        check("weakened hook has holes the old one lacked", new["holes"] > old["holes"], f"{new} vs {old}")
        for other in ("bash-path-lock", "gate-advance"):
            a, b = h[other]["worktree"], h[other]["HEAD~1"]
            keys = ("calls", "denials", "redundant_denials", "holes", "mismatches", "deny_tokens_est")
            check(f"{other} numbers identical across versions",
                  all(a[k] == b[k] for k in keys), f"{a} vs {b}")
        diff_hooks = {d["hook"] for d in rep["diffs"]}
        check("decision diffs name only the changed hook", diff_hooks == {"maven-reactor-guard"}, str(diff_hooks))

        # A ref where a hook file does not exist is reported, not a crash.
        g("rm", "-q", "-r", "build-hex/hooks")
        g("commit", "-qm", "drop build-hex hooks")
        rep, err = replay("--repo", str(scratch), "--ref", "HEAD~1", "--hook", "bash-path-lock")
        check("missing hook dir in worktree is reported, not a crash", rep is not None, err)
        if rep is not None:
            check("missing hook counted", rep["hooks"]["bash-path-lock"]["worktree"]["missing"] > 0)


def test_corpus_hygiene():
    files = scenario_files()
    check("corpus is not empty", len(files) >= 8, str(len(files)))
    for f in files:
        raw = f.read_text(encoding="utf-8")
        rel = f.relative_to(REPLAY)
        check(f"{rel}: no personal paths", "/Users/" not in raw and ".claude/projects" not in raw)
        # R3: a pasted recorded payload carries session ids and transcript paths.
        check(f"{rel}: no recorded-session fields",
              not re.search(r'"(session_id|transcript_path)"', raw)
              and not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", raw, re.I))
        check(f"{rel}: no client names", not re.search(r"wego|kodez", raw, re.I))
        sc = json.loads(raw)
        check(f"{rel}: hook file exists", (REPO / sc["hook"]).is_file(), sc.get("hook", "?"))
        check(f"{rel}: every call has a valid expect",
              bool(sc["calls"]) and all(c.get("expect") in ("deny", "allow") for c in sc["calls"]))
    by_hook = {}
    for f in files:
        sc = json.loads(f.read_text(encoding="utf-8"))
        calls = by_hook.setdefault(f.parent.name, [])
        calls.extend(sc["calls"])
    for hid, calls in by_hook.items():
        check(f"{hid}: has deny and allow", {c["expect"] for c in calls} == {"deny", "allow"})
        check(f"{hid}: has a redundant call", any(c.get("redundant") for c in calls))
        check(f"{hid}: has a must_deny call", any(c.get("must_deny") for c in calls))
        check(f"{hid}: redundant/must_deny only on deny labels",
              all(c["expect"] == "deny" for c in calls if c.get("redundant") or c.get("must_deny")))


if __name__ == "__main__":
    test_labels_hold_in_worktree()
    test_comparison_shows_a_changed_rule()
    test_corpus_hygiene()
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        sys.exit(1)
    print("\nok")
