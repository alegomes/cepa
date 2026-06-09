#!/usr/bin/env python3
"""Regression tests for the bash-path-lock redirect parser.

No third-party deps — run with `python3 tests/test_bash_path_lock_redir.py`.
Exits non-zero on the first failure.

Guards the `>=` false-match: the `>` in the `>=` comparison operator was read
as a redirection, capturing junk like `=/`, `=`, `='` as in-project "write
targets" → exit 2 → any Bash command containing `>=` got falsely blocked. That
silently skipped proof-reviewer perturbations (`sed -i 's/>=/>/'`), which can
let the proof gate emit false-PROVEN. See memory bash-pathlock-ge-falsematch.

The hook is byte-identical across all topologies, so we load and assert every
copy — a fix that misses one topology is still a bug.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = sorted(REPO.glob("*/hooks/bash-path-lock.py"))


def load(path):
    spec = importlib.util.spec_from_file_location(
        f"bpl_{path.parent.parent.name}", str(path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# (label, command, predicate(targets) -> bool, expectation text)
CASES = [
    # --- the >= regression: no junk `=`-shaped target may appear ---
    ("grep for >=",        "grep -n '>=' src/main/java/Foo.java",
     lambda t: t == [],                       "no write target at all"),
    ("arithmetic compare", "[[ $a >= $b ]] && ./mvnw test",
     lambda t: t == [],                       "no write target at all"),
    ("perturb: weaken >=", "sed -i 's/>=/>/' src/main/java/Foo.java",
     lambda t: not any("=" in x for x in t),  "no `=`-junk target (real file target is fine)"),

    # --- legit redirects must still be detected (no over-correction) ---
    ("redirect >",         'echo "x" > out.txt',
     lambda t: "out.txt" in t,                "out.txt detected"),
    ("append >>",          "cat a >> log.txt",
     lambda t: "log.txt" in t,                "log.txt detected"),
    ("stderr 2> excluded", "./mvnw test 2> err.log",
     lambda t: "err.log" not in t,            "2>/stderr is out of scope"),
]


def main():
    if not HOOKS:
        print("FAIL: no */hooks/bash-path-lock.py found under", REPO)
        return 1

    failures = 0
    for hook in HOOKS:
        topo = hook.parent.parent.name
        mod = load(hook)
        for label, cmd, ok, expect in CASES:
            targets, _ = mod.extract_write_targets(cmd)
            if ok(targets):
                print(f"PASS [{topo:11}] {label:20} -> {targets}")
            else:
                failures += 1
                print(f"FAIL [{topo:11}] {label:20} -> {targets}  (expected: {expect})")

    print()
    if failures:
        print(f"{failures} failure(s) across {len(HOOKS)} hook copies")
        return 1
    print(f"All checks passed across {len(HOOKS)} hook copies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
