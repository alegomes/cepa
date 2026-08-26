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

    # --- `git mv` is a real write (only docs-topology handled it until
    #     2026-08-17; the drift detector in test_lock_copies_drift.py found
    #     the other four letting it through) ---
    ("git mv destination", "git mv docs/old.md docs/new.md",
     lambda t: "docs/new.md" in t,            "destination is the write target"),
    ("git mv out of lane", "git mv README.md ../outside/README.md",
     lambda t: "../outside/README.md" in t,   "escaping the lane is still a target"),
    ("git status is not a write", "git status --short",
     lambda t: t == [],                       "read-only git verbs write nothing"),
    ("git log is not a write", "git log --oneline -3",
     lambda t: t == [],                       "read-only git verbs write nothing"),
    ("git commit is not a file write", "git commit -m 'x'",
     lambda t: t == [],                       "commit writes via git, not the shell"),

    # --- P4 / CS-5: rename counts as a write on BOTH the origin and the
    #     destination — moving a file OUT of a slice's declared surface is a
    #     write to that origin path even when the destination is allowed ---
    ("git mv source", "git mv infrastructure/Foo.java domain/Foo.java",
     lambda t: "infrastructure/Foo.java" in t, "origin is a write target too"),
    ("git mv both paths", "git mv infrastructure/Foo.java domain/Foo.java",
     lambda t: set(t) == {"infrastructure/Foo.java", "domain/Foo.java"},
     "exactly origin + destination, nothing else"),
    ("plain mv source", "mv src/old.py src/new.py",
     lambda t: "src/old.py" in t and "src/new.py" in t,
     "plain `mv` deletes its source too — both paths are targets"),
    ("cp does not delete its source", "cp src/a.py src/b.py",
     lambda t: t == ["src/b.py"],
     "`cp` only reads its source — destination-only, unlike `mv`"),

    # --- a forma BSD do `sed -i`: o sufixo vazio é um OPERANDO ---
    #     `sed -i '' 's/a/b/' arquivo` (macOS) deixa o `''` na lista de
    #     não-flags, então o SCRIPT do sed passava a ser o 1º operando e o
    #     arquivo real vinha depois — `nonflags[1:]` registrava `s/a/b/` como
    #     arquivo escrito. Fail-closed, e por isso invisível: o alvo de mentira
    #     só bloqueia MAIS. Consertado em 26/08/2026 filtrando o token vazio,
    #     e sem este caso o conserto só era visto pelo detector de divergência
    #     — que compara as duas fontes ENTRE SI e ficaria verde se as duas
    #     regredissem juntas, que é exatamente o que uma restauração de branch
    #     antigo faria.
    ("sed -i BSD: script is not a file", "sed -i '' 's/a/b/' docs/x.md",
     lambda t: t == ["docs/x.md"],
     "só o arquivo — o script do sed não é alvo de escrita"),
    ("sed -i GNU: script is not a file", "sed -i 's/a/b/' docs/x.md",
     lambda t: t == ["docs/x.md"],
     "a forma GNU já estava certa; fica travada junto"),
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
