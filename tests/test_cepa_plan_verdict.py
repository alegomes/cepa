#!/usr/bin/env python3
"""CS-6 of docs/spec/tres-portas-spec-epic.md (item 4 of O2'): `cepa-plan
verdict <arquivo> <n> mantida|vetada|refinada` writes, on decision `<n>` of the
"Decided without asking" section (numbered as `cepa-plan decisions` numbers
it), the marker with today's date, and on vetada or refinada warns when a
queue was already derived from the file.

Red test declared in the spec: in a test repo with a spec of three decisions
and a queue whose `source:` cites that spec with one `done` item,
`cepa-plan verdict <spec> 2 vetada --reason "fora do ciclo"` exits 0, line 2
ends in `· vetada em <hoje>: fora do ciclo`, lines 1 and 3 do not change,
`Status` does not change, the output contains "já virou código na fila" with
the queue name and "1 item done"; repeating the command on line 2 exits
nonzero; `vetada` without `--reason` exits nonzero.

Decided without asking (same spec): `refinada` requires `--text` and swaps
the text before the marker; a line that already has a marker is refused.

(The fixture spec is `draft`: the spec-readiness-gate hook reads any file
that declares itself ready, test fixtures included.)

Run: python3 tests/test_cepa_plan_verdict.py
"""

import datetime
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


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


TODAY = datetime.date.today().isoformat()

SPEC = """# Spec

**Status:** draft

## Decided without asking

- Primeira decisão fica como está.
- Segunda decisão vai ser vetada.
- Terceira decisão
  continua na linha de baixo.

## Riscos

- não é decisão
"""

QUEUE = """mode: single-track
queue: derivada
source: docs/spec/a.md (3 critérios; ordem do texto)
written_at: 2026-11-06
items:
  - id: A-1
    title: primeiro
    why: ordem do texto
    status: done
    evidence: commit abc
  - id: A-2
    title: segundo
    why: ordem do texto
    status: pending
"""

OTHER_QUEUE = """mode: single-track
queue: outra
source: docs/spec/zzz.md
written_at: 2026-11-06
items:
  - id: B-1
    title: um
    why: ordem
    status: done
    evidence: commit def
"""


def decisions(path):
    r = run("decisions", str(path), "--json")
    return json.loads(r.stdout)["files"][0]["decisions"]


with tempfile.TemporaryDirectory() as tmp:
    repo = Path(tmp).resolve()
    git(repo, "init", "-q")
    (repo / "docs" / "spec").mkdir(parents=True)
    spec = repo / "docs" / "spec" / "a.md"
    spec.write_text(SPEC, encoding="utf-8")
    qdir = repo / ".claude" / "queues" / "derivada"
    qdir.mkdir(parents=True)
    (qdir / "queue.yaml").write_text(QUEUE, encoding="utf-8")
    odir = repo / ".claude" / "queues" / "outra"
    odir.mkdir(parents=True)
    (odir / "queue.yaml").write_text(OTHER_QUEUE, encoding="utf-8")

    before = spec.read_text(encoding="utf-8").splitlines()

    # vetada without --reason: refused, file untouched.
    r = run("verdict", str(spec), "2", "vetada", "--repo", str(repo))
    check("vetada without --reason exits nonzero", r.returncode != 0, r.stdout)
    check("vetada without --reason names --reason", "--reason" in r.stderr, r.stderr)
    check("vetada without --reason leaves the file",
          spec.read_text(encoding="utf-8").splitlines() == before)

    # The red test of the spec.
    r = run("verdict", str(spec), "2", "vetada", "--reason", "fora do ciclo",
            "--repo", str(repo))
    out = r.stdout
    check("vetada exits 0", r.returncode == 0, r.stderr)
    after = spec.read_text(encoding="utf-8").splitlines()
    check("line 2 ends with the marker",
          len(after) > 7 and after[7]
          == f"- Segunda decisão vai ser vetada. · vetada em {TODAY}: fora do ciclo",
          after[7] if len(after) > 7 else after)
    check("line 1 unchanged", after[6] == before[6], after[6])
    check("line 3 unchanged", after[8:10] == before[8:10], after[8:10])
    check("Status unchanged", after[2] == "**Status:** draft", after[2])
    check("nothing else changed",
          [l for i, l in enumerate(after) if i != 7]
          == [l for i, l in enumerate(before) if i != 7])
    check("warns 'já virou código na fila'", "já virou código na fila" in out, out)
    check("warning names the queue", "derivada" in out, out)
    check("warning counts '1 item done'", "1 item done" in out, out)
    check("queue that does not cite the file is not named", "outra" not in out, out)
    decs = decisions(spec)
    check("the reader sees the verdict on #2 only",
          [d["verdict"] for d in decs] == [None, "vetada", None], str(decs))

    # Repeat on the same line: refused, file untouched.
    snap = spec.read_text(encoding="utf-8")
    r = run("verdict", str(spec), "2", "vetada", "--reason", "outra vez",
            "--repo", str(repo))
    check("repeating on line 2 exits nonzero", r.returncode != 0, r.stdout)
    check("repeat says it already has a verdict", "vetada" in r.stderr, r.stderr)
    check("repeat leaves the file", spec.read_text(encoding="utf-8") == snap)
    r = run("verdict", str(spec), "2", "mantida", "--repo", str(repo))
    check("another verdict on a marked line also refused", r.returncode != 0, r.stdout)

    # mantida on a multi-line decision: marker at the end of the item, no warning.
    r = run("verdict", str(spec), "3", "mantida", "--repo", str(repo))
    check("mantida exits 0", r.returncode == 0, r.stderr)
    after = spec.read_text(encoding="utf-8").splitlines()
    check("multi-line item: marker on its last line",
          after[8] == "- Terceira decisão"
          and after[9] == f"  continua na linha de baixo. · mantida em {TODAY}",
          after[8:10])
    check("mantida does not warn about the queue",
          "já virou código" not in r.stdout, r.stdout)

    # refinada requires --text.
    snap = spec.read_text(encoding="utf-8")
    r = run("verdict", str(spec), "1", "refinada", "--repo", str(repo))
    check("refinada without --text exits nonzero", r.returncode != 0, r.stdout)
    check("refinada without --text names --text", "--text" in r.stderr, r.stderr)
    check("refinada without --text leaves the file",
          spec.read_text(encoding="utf-8") == snap)

    # refinada swaps the text, then the marker; warns.
    r = run("verdict", str(spec), "1", "refinada", "--text",
            "Primeira decisão, agora mais estreita.", "--repo", str(repo))
    check("refinada exits 0", r.returncode == 0, r.stderr)
    after = spec.read_text(encoding="utf-8").splitlines()
    check("refinada swaps text and adds marker",
          after[6] == f"- Primeira decisão, agora mais estreita. · refinada em {TODAY}",
          after[6])
    check("refinada warns about the queue",
          "já virou código na fila" in r.stdout and "derivada" in r.stdout, r.stdout)
    decs = decisions(spec)
    check("reader after all three",
          [d["verdict"] for d in decs] == ["refinada", "vetada", "mantida"], str(decs))

    # Out of range ordinal, unknown verdict, missing file, no section.
    r = run("verdict", str(spec), "9", "mantida", "--repo", str(repo))
    check("ordinal out of range exits nonzero", r.returncode != 0, r.stdout)
    check("ordinal out of range says how many", "a seção tem 3" in r.stderr, r.stderr)
    check("ordinal out of range is a clean refusal", "Traceback" not in r.stderr, r.stderr)
    r = run("verdict", str(spec), "0", "mantida", "--repo", str(repo))
    check("ordinal 0 exits nonzero", r.returncode != 0, r.stdout)
    r = run("verdict", str(spec), "1", "aprovada", "--repo", str(repo))
    check("unknown verdict exits nonzero", r.returncode != 0, r.stdout)
    r = run("verdict", str(repo / "nada.md"), "1", "mantida", "--repo", str(repo))
    check("missing file exits nonzero", r.returncode != 0, r.stdout)
    bare = repo / "docs" / "spec" / "b.md"
    bare.write_text("# Spec\n\n## Goal\n\n- algo\n", encoding="utf-8")
    r = run("verdict", str(bare), "1", "mantida", "--repo", str(repo))
    check("file without the section exits nonzero", r.returncode != 0, r.stdout)
    check("file without the section says so", "sem a seção" in r.stderr, r.stderr)
    check("no traceback anywhere", "Traceback" not in r.stderr, r.stderr)

    # Relative path, run from inside the repo: same match against `source:`.
    spec2 = repo / "docs" / "spec" / "c.md"
    spec2.write_text(SPEC, encoding="utf-8")
    (qdir / "queue.yaml").write_text(
        QUEUE.replace("docs/spec/a.md", "docs/spec/c.md"), encoding="utf-8")
    r = run("verdict", "docs/spec/c.md", "2", "vetada", "--reason", "x",
            cwd=str(repo))
    check("relative path from inside the repo exits 0", r.returncode == 0, r.stderr)
    check("relative path still finds the queue",
          "já virou código na fila" in r.stdout and "derivada" in r.stdout, r.stdout)

    # A path that only shares a prefix or suffix (docs/spec/xc.md, or
    # docs/spec/d.md.bak) does not count as citing the file.
    (qdir / "queue.yaml").write_text(
        QUEUE.replace("docs/spec/a.md", "docs/spec/xd.md"), encoding="utf-8")
    spec3 = repo / "docs" / "spec" / "d.md"
    spec3.write_text(SPEC, encoding="utf-8")
    (odir / "queue.yaml").write_text(
        OTHER_QUEUE.replace("docs/spec/zzz.md", "docs/spec/d.md.bak"), encoding="utf-8")
    r = run("verdict", str(spec3), "2", "vetada", "--reason", "x", "--repo", str(repo))
    check("prefix-only source is not a citation",
          r.returncode == 0 and "já virou código" not in r.stdout, r.stdout)

    # refinada --text carrying a verdict marker: refused, file untouched.
    spec4 = repo / "docs" / "spec" / "e.md"
    spec4.write_text(SPEC, encoding="utf-8")
    snap = spec4.read_text(encoding="utf-8")
    r = run("verdict", str(spec4), "1", "refinada", "--text",
            "x · vetada em 2026-01-01", "--repo", str(repo))
    check("refinada --text with a marker exits nonzero", r.returncode != 0, r.stdout)
    check("refinada --text with a marker leaves the file",
          spec4.read_text(encoding="utf-8") == snap)

    # Warning wording: plural, zero done, and a waves plan citing the file is
    # not a queue.
    (qdir / "queue.yaml").write_text(
        QUEUE.replace("docs/spec/a.md", "docs/spec/e.md")
             .replace("    status: pending\n", "    status: done\n    evidence: commit x\n"),
        encoding="utf-8")
    (odir / "queue.yaml").write_text(
        OTHER_QUEUE.replace("docs/spec/zzz.md", "./docs/spec/e.md")
                   .replace("status: done\n    evidence: commit def\n", "status: pending\n"),
        encoding="utf-8")
    wdir = repo / ".claude" / "queues" / "ondas"
    wdir.mkdir(parents=True)
    (wdir / "queue.yaml").write_text(
        "mode: parallel-waves\nqueue: ondas\nsource: docs/spec/e.md\nwaves: []\n",
        encoding="utf-8")
    r = run("verdict", str(spec4), "2", "vetada", "--reason", "x", "--repo", str(repo))
    out = r.stdout
    check("plural: '2 itens done'", "fila derivada: 2 itens done de 2" in out, out)
    check("zero done is not 'já virou código'",
          "já virou código na fila outra" not in out
          and "a fila outra foi derivada deste arquivo (0 itens done de 1)" in out, out)
    check("./ prefix in source counts as citing", "outra" in out, out)
    check("a waves plan is not a derived queue", "ondas" not in out, out)

    # CRLF file stays CRLF byte for byte; refinada on the last line without a
    # trailing newline does not add one.
    crlf = repo / "docs" / "spec" / "f.md"
    crlf.write_bytes(SPEC.replace("\n", "\r\n").encode("utf-8"))
    raw_before = crlf.read_bytes()
    r = run("verdict", str(crlf), "1", "mantida", "--repo", str(repo))
    raw_after = crlf.read_bytes()
    check("CRLF: exits 0", r.returncode == 0, r.stderr)
    check("CRLF: every line still ends in CRLF",
          raw_after.count(b"\r\n") == raw_before.count(b"\r\n")
          and raw_after.replace(b"\r\n", b"").count(b"\n") == 0, repr(raw_after[:200]))
    check("CRLF: only decision 1 changed",
          [l for l in raw_after.split(b"\r\n") if l not in raw_before.split(b"\r\n")]
          == [f"- Primeira decisão fica como está. · mantida em {TODAY}".encode("utf-8")],
          repr(raw_after))
    tail = repo / "docs" / "spec" / "g.md"
    tail.write_text("# Spec\n\n## Decided without asking\n\n- Única decisão", encoding="utf-8")
    r = run("verdict", str(tail), "1", "refinada", "--text", "Única, refeita", "--repo", str(repo))
    check("no trailing newline: refinada keeps it absent",
          r.returncode == 0 and tail.read_bytes().endswith(
              f"- Única, refeita · refinada em {TODAY}".encode("utf-8")),
          repr(tail.read_bytes()))

    # `../docs/spec/h.md` is another file, not a citation; trailing spaces
    # before the marker and repeated spaces in --reason / --text collapse.
    spec5 = repo / "docs" / "spec" / "h.md"
    spec5.write_text("# Spec\n\n## Decided without asking\n\n"
                     "- Com espaço no fim   \n- Segunda\n- Terceira\n", encoding="utf-8")
    (qdir / "queue.yaml").write_text(
        QUEUE.replace("docs/spec/a.md", "../docs/spec/h.md"), encoding="utf-8")
    (odir / "queue.yaml").write_text(OTHER_QUEUE, encoding="utf-8")
    r = run("verdict", str(spec5), "1", "vetada", "--reason", "fora   do\n ciclo",
            "--repo", str(repo))
    lines = spec5.read_text(encoding="utf-8").splitlines()
    check("../ in source is not a citation",
          r.returncode == 0 and "já virou código" not in r.stdout, r.stdout)
    check("trailing spaces dropped and --reason collapsed",
          lines[4] == f"- Com espaço no fim · vetada em {TODAY}: fora do ciclo", lines[4])
    r = run("verdict", str(spec5), "2", "refinada", "--text", "  Segunda   bem\n  nova  ",
            "--repo", str(repo))
    lines = spec5.read_text(encoding="utf-8").splitlines()
    check("--text collapsed to one line",
          r.returncode == 0 and lines[5] == f"- Segunda bem nova · refinada em {TODAY}", lines[5])

    # --help lists verdict under writing.
    h = run("--help").stdout
    writing = h.split("  writing:", 1)[-1].split("\n  reading:", 1)[0]
    check("--help lists verdict under writing",
          "  writing:" in h and "verdict" in writing, h)

print()
if FAILURES:
    print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("all ok")
