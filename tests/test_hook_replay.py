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
        # The intact version's columns equal what the labels predict, so a
        # column that is dropped or miscounted shows here, not only as a delta.
        labels = [c for f in sorted((REPLAY / "maven-reactor-guard").glob("*.json"))
                  for c in json.loads(f.read_text(encoding="utf-8"))["calls"]]
        check("intact hook: denials equal deny labels",
              old["denials"] == sum(c["expect"] == "deny" for c in labels), str(old))
        check("intact hook: redundant column equals redundant labels",
              old["redundant_denials"] == sum(bool(c.get("redundant")) for c in labels) > 0, str(old))
        check("weakened hook loses its redundant denials",
              new["redundant_denials"] < old["redundant_denials"], f"{new} vs {old}")
        check("intact hook: denial tokens are counted", old["deny_tokens_est"] > 0, str(old))
        check("weakened hook: denial tokens drop", new["deny_tokens_est"] < old["deny_tokens_est"],
              f"{new} vs {old}")
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


PROBE = r"""import json, os, sys
sys.stdin.read()
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen-env.json")
json.dump(dict(os.environ), open(out, "w"))
sys.exit(int(os.environ.get("PROBE_EXIT", "0")))
"""


def test_runner_mechanics():
    """What the corpus cannot show: env scrub, telemetry isolation, error exits."""
    sys.path.insert(0, str(REPLAY))
    import run  # noqa: E402
    call = {"name": "c", "payload": {"tool_name": "Bash", "tool_input": {"command": "true"}},
            "expect": "allow"}
    hostile = {name: "hostile" for name in run.SCRUBBED_ENV}
    hostile.update({"GIT_DIR": "/nonexistent", "GIT_WORK_TREE": "/nonexistent",
                    "CEPA_TELEMETRY_DIR": "/real-ledger-must-not-be-used"})
    saved = dict(os.environ)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "hooks").mkdir()
        (root / "hooks" / "probe.py").write_text(PROBE, encoding="utf-8")
        tel = str(root / "tel")
        try:
            os.environ.update(hostile)
            sc = {"_file": "probe.json", "hook": "hooks/probe.py", "calls": [call]}
            res = run.run_scenario(sc, str(root), tel)
        finally:
            os.environ.clear()
            os.environ.update(saved)
        check("probe hook allowed", res[0]["decision"] == "allow", str(res[0]["decision"]))
        seen = json.loads((root / "hooks" / "seen-env.json").read_text(encoding="utf-8"))
        leaked = [k for k in run.SCRUBBED_ENV if k in seen]
        check("every hook-altering env var is scrubbed", not leaked, str(leaked))
        check("GIT_* is scrubbed", not [k for k in seen if k.startswith("GIT_")],
              str([k for k in seen if k.startswith("GIT_")]))
        check("telemetry goes to the replay's own dir", seen.get("CEPA_TELEMETRY_DIR") == tel,
              str(seen.get("CEPA_TELEMETRY_DIR")))

        sc1 = {"_file": "probe.json", "hook": "hooks/probe.py", "env": {"PROBE_EXIT": "1"},
               "calls": [call]}
        r1 = run.run_scenario(sc1, str(root), tel)[0]
        check("a hook that exits 1 is an error, not a denial", r1["decision"] == "error1", r1["decision"])

        locked = root / "hooks" / "locked.py"
        locked.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
        locked.chmod(0)
        try:
            sc2 = {"_file": "probe.json", "hook": "hooks/locked.py", "calls": [dict(call, expect="deny")]}
            r2 = run.run_scenario(sc2, str(root), tel)[0]
        finally:
            locked.chmod(0o644)
        check("python's own exit 2 (can't open file) is an error, not a denial",
              r2["decision"] == "error2", r2["decision"])
        summ = run.summarize([r1, r2])
        check("errors are counted, not denials", summ["errors"] == 2 and summ["denials"] == 0, str(summ))


if __name__ == "__main__":
    test_labels_hold_in_worktree()
    test_comparison_shows_a_changed_rule()
    test_corpus_hygiene()
    test_runner_mechanics()
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        sys.exit(1)
    print("\nok")
