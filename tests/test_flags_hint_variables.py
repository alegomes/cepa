#!/usr/bin/env python3
"""Every flag of a command is in both places: `argument-hint:` and `## Variables`.

No third-party dependency — run with `python3 tests/test_flags_hint_variables.py`.
Exits non-zero on the first sweep with a failure.

The pain: each command describes the parameters twice. The `argument-hint:` of the
frontmatter is what autocomplete shows; the `## Variables` section is what the
agent reads. In the 2026-09-16 survey three diverged — `--offline` of
/common:drain-plan only in Variables (autocomplete did not show it),
`--no-jira` of /common:autonomous-start and `--force-feature-flow` of
/board-flow:execute only in the hint (the agent had no definition). The
/common:session --help already reported it by reading both places, but the source
remained wrong, and nothing prevented the next one.

A command without a `## Variables` section is left out: there is nothing to compare. The
known exception goes into EXCEPTIONS with the reason written — never as a silent omission.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

FLAG = re.compile(r"--[a-z][a-z0-9-]*")

# (relative file, flag) → why the divergence is accepted today.
EXCEPTIONS = {
    ("common/commands/session.md", "--max"):
        "no hint é exemplo de argumento de OUTRA rotina "
        "(`/common:session prove-drain --max 5`), não flag do session",
    ("common/commands/queue.md", "--source"):
        "divergência real, fora do escopo do item parametros-de-comando-pela-metade "
        "(que nomeou três comandos); só em Variables",
    ("common/commands/worktree-label.md", "--branch"):
        "divergência real, fora do escopo do item parametros-de-comando-pela-metade "
        "(que nomeou três comandos); só em Variables",
}

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def flags(text):
    """(flags of the argument-hint, flags of ## Variables or None if there is no section)."""
    m = re.search(r"^argument-hint:(.*)$", text, re.M)
    hint = set(FLAG.findall(m.group(1))) if m else set()
    v = re.search(r"^## Variables\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    var = set(FLAG.findall(v.group(1))) if v else None
    return hint, var


def divergences(rel, text):
    """List of (rel, flag, side-that-has-it) that is not in both places."""
    hint, var = flags(text)
    if var is None:
        return []
    out = [(rel, f, "só no argument-hint") for f in sorted(hint - var)]
    out += [(rel, f, "só em Variables") for f in sorted(var - hint)]
    return [d for d in out if (d[0], d[1]) not in EXCEPTIONS]


def main():
    files = sorted(REPO.glob("*/commands/*.md"))
    check("a varredura acha comandos", len(files) > 20, f"achou {len(files)}")

    found = []
    for file in files:
        rel = str(file.relative_to(REPO))
        found += divergences(rel, file.read_text())
    check("toda flag está no argument-hint e em ## Variables", not found,
          "; ".join(f"{r} {f} ({side})" for r, f, side in found))

    for rel in ("common/commands/drain-plan.md",
                "common/commands/autonomous-start.md",
                "board-flow/commands/execute.md"):
        hint, var = flags((REPO / rel).read_text())
        check(f"{rel} tem Variables e flags nos dois lados",
              var is not None and hint and hint == var, f"hint={hint} var={var}")

    phantoms = []
    for (rel, flag), _ in EXCEPTIONS.items():
        p = REPO / rel
        if not p.exists():
            phantoms.append(f"{rel} (sumiu)")
            continue
        hint, var = flags(p.read_text())
        if var is None or (flag in hint) == (flag in var):
            phantoms.append(f"{rel} {flag} (não diverge mais)")
    check("toda exceção em EXCECOES ainda diverge", not phantoms,
          "tire de EXCECOES: " + ", ".join(phantoms))

    # The test must be able to turn red.
    base = ("---\nargument-hint: <x> [--a] [--b N]\n---\n\n## Variables\n\n"
            "- `--a` — um.\n- `--b N` — dois.\n\n## Instructions\n\n`--c` na prosa.\n")
    check("os dois lados iguais não acusam nada", divergences("x.md", base) == [])
    check("flag só no hint é acusada",
          divergences("x.md", base.replace("- `--b N` — dois.\n", ""))
          == [("x.md", "--b", "só no argument-hint")])
    check("flag só em Variables é acusada",
          divergences("x.md", base.replace(" [--b N]", ""))
          == [("x.md", "--b", "só em Variables")])
    check("flag na prosa fora de Variables não conta como definida",
          divergences("x.md", base.replace("[--b N]", "[--b N] [--c]")
                       ) == [("x.md", "--c", "só no argument-hint")])
    check("Variables como última seção também é lida",
          divergences("x.md", "argument-hint: [--a]\n## Variables\n- `--a` x\n") == [])
    check("comando sem Variables fica fora",
          divergences("x.md", "argument-hint: [--a]\n## Instructions\n") == [])

    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print(f"\ntudo ok ({len(files)} comandos varridos)")


if __name__ == "__main__":
    main()
