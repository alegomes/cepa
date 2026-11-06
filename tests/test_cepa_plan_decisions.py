#!/usr/bin/env python3
"""CS-4 of docs/spec/tres-portas-spec-epic.md (item 3 of O2'): `cepa-plan
decisions` lists, per file, the decisions of the "Decided without asking"
section split into with and without verdict, reusing the shared reader
`common/hooks/_decisions.py`. With no argument it scans docs/spec/*.md and
docs/epics/*.md of --repo.

Red test declared in the spec: in a throwaway repo with one spec (two
decisions, one `· vetada em 2026-11-06: fora do ciclo`) and one Epic (one
decision, no marker), the command exits 0 and prints both paths with
"1 sem veredito" and the pending text; `<spec> --json` returns both lines with
the verdict filled only on the vetada one; a missing file exits nonzero.

Run: python3 tests/test_cepa_plan_decisions.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def run(*args, cwd=None):
    return subprocess.run([sys.executable, str(CEPA_PLAN), *args],
                          capture_output=True, text=True, cwd=cwd, timeout=60)


SPEC = """# Spec

## Decided without asking

- Item um sem marcador
- Item dois fica fora · vetada em 2026-11-06: fora do ciclo

## Outra seção

- nao e decisao
"""

EPIC = """# Epic

## Decided without asking

- Decisão do Epic sem marcador
"""

NOSECTION = "# Spec sem a seção\n\n## Goal\n\n- algo\n"


with tempfile.TemporaryDirectory() as tmp:
    repo = Path(tmp)
    (repo / "docs" / "spec").mkdir(parents=True)
    (repo / "docs" / "epics").mkdir(parents=True)
    spec = repo / "docs" / "spec" / "a.md"
    epic = repo / "docs" / "epics" / "b.md"
    spec.write_text(SPEC, encoding="utf-8")
    epic.write_text(EPIC, encoding="utf-8")

    r = run("decisions", "--repo", str(repo))
    out = r.stdout
    check("scan exits 0", r.returncode == 0, r.stderr)
    check("scan prints the spec path", "docs/spec/a.md" in out, out)
    check("scan prints the epic path", "docs/epics/b.md" in out, out)
    check("each file says '1 sem veredito'", out.count("1 sem veredito") == 2, out)
    check("pending text of the spec", "Item um sem marcador" in out, out)
    check("pending text of the epic", "Decisão do Epic sem marcador" in out, out)
    check("decided line is not listed as pending", "Item dois fica fora" not in out, out)
    check("pending shows its ordinal", "#1 " in out, out)
    check("human output in pt-BR", "1 com veredito" in out, out)

    r = run("decisions", str(spec), "--json")
    check("json exits 0", r.returncode == 0, r.stderr)
    try:
        data = json.loads(r.stdout)
    except ValueError:
        data = None
    check("json parses", data is not None, r.stdout)
    if data is not None:
        files = data.get("files") if isinstance(data, dict) else None
        entry = files[0] if files else {}
        decs = entry.get("decisions", [])
        check("json has both lines", len(decs) == 2, str(data))
        if len(decs) == 2:
            check("json verdict only on the vetada one",
                  decs[0]["verdict"] is None and decs[1]["verdict"] == "vetada",
                  str(decs))
            check("json ordinal and line",
                  [d["ordinal"] for d in decs] == [1, 2]
                  and [d["line"] for d in decs] == [5, 6], str(decs))
            check("json text in the file's words",
                  decs[0]["text"] == "Item um sem marcador", str(decs))

    # An explicit file reads only that file.
    r = run("decisions", str(spec))
    check("explicit file does not scan the others",
          "b.md" not in r.stdout and r.returncode == 0, r.stdout)

    # Ordinal is the position among ALL decisions of the file, not among the
    # pending ones: with the vetada one first, the pending one is #2.
    flipped = repo / "docs" / "spec" / "d.md"
    flipped.write_text(
        "# Spec\n\n## Decided without asking\n\n"
        "- Primeiro já vetado · vetada em 2026-11-06: fora do ciclo\n"
        "- Segundo ainda pendente\n", encoding="utf-8")
    r = run("decisions", str(flipped))
    check("flipped: pending shows #2", "#2 " in r.stdout and "Segundo ainda pendente" in r.stdout, r.stdout)
    check("flipped: pending does not show #1", "#1 " not in r.stdout, r.stdout)
    r = run("decisions", str(flipped), "--json")
    try:
        fdecs = json.loads(r.stdout)["files"][0]["decisions"]
    except (ValueError, KeyError, IndexError, TypeError):
        fdecs = []
    check("flipped: json ordinal 2 on the pending one",
          len(fdecs) == 2 and fdecs[0]["verdict"] == "vetada"
          and fdecs[1]["verdict"] is None and fdecs[1]["ordinal"] == 2, str(fdecs))

    # Distinct counts (1 pending, 2 decided): "com veredito" must be total - pending.
    mixed = repo / "docs" / "spec" / "e.md"
    mixed.write_text(
        "# Spec\n\n## Decided without asking\n\n"
        "- Uma mantida · mantida em 2026-11-06\n"
        "- Uma pendente\n"
        "- Uma vetada · vetada em 2026-11-06: x\n", encoding="utf-8")
    r = run("decisions", str(mixed))
    check("counts line: 3 decisões, 1 sem veredito, 2 com veredito",
          "3 decisões, 1 sem veredito, 2 com veredito" in r.stdout, r.stdout)

    # --help lists `decisions` in the "reading" group.
    h = run("--help").stdout
    reading = h.split("  reading:", 1)[-1].split("\n  one item's cycle:", 1)[0]
    check("--help lists decisions under reading",
          "  reading:" in h and "decisions" in reading, h)

    # File without the section: says so, does not crash.
    bare = repo / "docs" / "spec" / "c.md"
    bare.write_text(NOSECTION, encoding="utf-8")
    r = run("decisions", str(bare))
    check("no section exits 0", r.returncode == 0, r.stderr)
    check("no section is said in pt-BR", "sem a seção" in r.stdout, r.stdout)
    check("no traceback", "Traceback" not in r.stderr, r.stderr)
    r = run("decisions", str(bare), "--json")
    check("no section in json is null",
          r.returncode == 0 and json.loads(r.stdout)["files"][0]["decisions"] is None,
          r.stdout)

    # Missing file.
    r = run("decisions", "inexistente.md", cwd=str(repo))
    check("missing file exits nonzero", r.returncode != 0, str(r.returncode))
    check("missing file names it", "inexistente.md" in r.stderr, r.stderr)

    # Empty repo scan.
    with tempfile.TemporaryDirectory() as empty:
        r = run("decisions", "--repo", empty)
        check("empty repo exits 0 and says so",
              r.returncode == 0 and "Nenhuma" in r.stdout, r.stdout + r.stderr)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("all ok")
