#!/usr/bin/env python3
"""Regression tests: cepa-doctor counts the decisions without a verdict (CS-5 of
docs/spec/tres-portas-spec-epic.md, item 5 of O2').

## Why this check exists

The "Decided without asking" section of a spec or Epic is the list of choices
the agent made on its own, waiting for the owner's veto. The closing count
(item 6) only sees the file being closed; once closed, nothing reminded anyone
that those decisions were still waiting. The doctor runs at the start of the
session, so it is where the repo total shows up, as a warning (exit 1, in the
`--brief` summary and in "Precisa de você").

## Why draft files are left out

A spec in `draft` (or an Epic in `rascunho`) is still in interview: its
decisions are counted when it closes, by the readiness gate. Counting them here
would charge the owner for a veto on a text that is still changing.

The fixtures carry the status as a `{status}` placeholder filled in at write
time: a literal ready status line in this file would make the
spec-readiness-gate hook read the test itself as a spec claiming to be ready.

Run: python3 tests/test_doctor_decisions.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


SPEC = """# Spec: {title}

**Status:** {status}

## Decided without asking

{items}
"""

EPIC = """# Epic: {title}

**Status:** {status} · **Aberto em:** 2026-11-06

## Decidido sem perguntar

{items}
"""

READY_SPEC = SPEC.format(
    title="pronta", status="ready-to-build",
    items="- A cor do botão é azul. · mantida em 2026-11-06\n"
          "- O limite é de 10 itens por página.")

DRAFT_SPEC = SPEC.format(
    title="rascunho", status="draft",
    items="- primeira decisão em entrevista\n"
          "- segunda decisão em entrevista\n"
          "- terceira decisão em entrevista")

DRAFT_EPIC = EPIC.format(
    title="em entrevista", status="rascunho",
    items="- uma decisão do Epic ainda em entrevista")

READY_EPIC = EPIC.format(
    title="fechado", status="ready",
    items="- o Epic fechado tem uma decisão sem veredito")


def build(tmp, files):
    root = Path(tmp)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    # Without a baseline the doctor would warn about the build and the exit
    # code would be 1 for a reason that is not this check.
    (root / ".claude").mkdir(exist_ok=True)
    (root / ".claude" / "no-build").write_text("", encoding="utf-8")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    return root


def run_doctor(root, *extra):
    p = subprocess.run([sys.executable, str(DOCTOR), "--project", *extra],
                       cwd=str(root), capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr


def test_ready_spec_with_pending_decision_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, {
            "docs/spec/pronta.md": READY_SPEC,
            "docs/spec/rascunho.md": DRAFT_SPEC,
            "docs/epics/em-entrevista.md": DRAFT_EPIC,
        })
        code, out = run_doctor(root)
        check("spec pronta com 1 decisão sem veredito: sai com 1",
              code == 1, f"exit={code}\n{out}")
        check("...mostra '⚠ [decisoes] 1 decisão sem veredito'",
              "⚠ [decisoes] 1 decisão sem veredito" in out, out)
        check("...com o caminho da spec pronta",
              "docs/spec/pronta.md" in out, out)
        check("...e o comando que abre o veto",
              "/common:spec --continuar pronta" in out, out)
        check("...não cita a spec em draft",
              "rascunho.md" not in out, out)
        check("...não cita o Epic em rascunho",
              "em-entrevista" not in out, out)
        need = out.split("## Precisa de você", 1)
        check("...repete a linha em 'Precisa de você'",
              len(need) == 2 and "[decisoes]" in need[1]
              and "docs/spec/pronta.md" in need[1], out)
        code_b, out_b = run_doctor(root, "--brief")
        check("--brief conta o aviso",
              "1 aviso(s)" in out_b and "decisoes" in out_b,
              f"exit={code_b}\n{out_b}")


def test_ready_epic_points_at_the_epic_command():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, {
            "docs/spec/pronta.md": READY_SPEC,
            "docs/epics/fechado.md": READY_EPIC,
        })
        _code, out = run_doctor(root)
        check("spec + Epic fechados: o total soma os dois (2)",
              "⚠ [decisoes] 2 decisões sem veredito" in out, out)
        check("...o Epic sai com /common:epic <nome>",
              "/common:epic fechado" in out and "docs/epics/fechado.md" in out,
              out)
        first_block = out.split("## Precisa de você", 1)[0].splitlines()
        check("...um arquivo por linha",
              sum("docs/spec/pronta.md" in ln for ln in first_block) == 1
              and sum("docs/epics/fechado.md" in ln for ln in first_block) == 1
              and not any("pronta.md" in ln and "fechado.md" in ln
                          for ln in first_block),
              out)


def test_zero_pending_shows_ok_with_zero():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, {
            "docs/spec/pronta.md": READY_SPEC.replace(
                "por página.", "por página. · vetada em 2026-11-06"),
            "docs/spec/rascunho.md": DRAFT_SPEC,
        })
        code, out = run_doctor(root)
        check("zero pendência: ✓ [decisoes] com o zero",
              "✓ [decisoes] 0 decisões sem veredito" in out, out)
        check("...e não vira aviso (sai com 0)", code == 0, f"exit={code}\n{out}")


def test_without_spec_or_epic_dirs_is_silent():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, {})
        _code, out = run_doctor(root)
        check("sem docs/spec nem docs/epics: a área não aparece",
              "[decisoes]" not in out, out)


def test_no_automatic_fix():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, {"docs/spec/pronta.md": READY_SPEC})
        _code, out = run_doctor(root)
        check("sem conserto automático no --fix",
              "correção mecânica" not in out, out)


if __name__ == "__main__":
    test_ready_spec_with_pending_decision_warns()
    test_ready_epic_points_at_the_epic_command()
    test_zero_pending_shows_ok_with_zero()
    test_without_spec_or_epic_dirs_is_silent()
    test_no_automatic_fix()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\ntodos ok")
