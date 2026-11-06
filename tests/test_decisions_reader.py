#!/usr/bin/env python3
"""CS-2 of docs/spec/tres-portas-spec-epic.md (item 6 of O2', base of item 3):
the reader of the "Decided without asking" section lives in a shared module,
`common/hooks/_decisions.py`, which the spec-readiness-gate hook imports and
`cepa-plan decisions` (item 3) will reuse. It reads the new section name and
the old one ("Decidido sem perguntar") and returns the lines with and without
a verdict (`· mantida em`, `· vetada em`, `· refinada em`).

Red test declared in the spec: importing the module and reading the four real
documents of today (two specs, one Epic and a fixture with the old name and one
line) returns 3, 2, 2 and 1 lines without verdict, in the same words as the
file.

Run: python3 tests/test_decisions_reader.py
"""

import importlib.util
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"
MODULE = HOOKS / "_decisions.py"
GATE = HOOKS / "spec-readiness-gate.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def words(text):
    return re.sub(r"\s+", " ", text).strip()


def section_words(path):
    """Every word of the decisions section of the file, whitespace collapsed."""
    text = Path(path).read_text(encoding="utf-8")
    m = re.search(r"^## (?:Decided without asking|Decidido sem perguntar).*?$"
                  r"(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return words(m.group(1)) if m else ""


REAL = (
    ("docs/spec/cepa-espiral-c1.md", 3),
    ("docs/spec/planejador-de-lotes-paralelos.md", 2),
    ("docs/epics/cepa-em-espiral.md", 2),
)

FIXTURE = """# Spec: fixture

**Status:** draft

## Decidido sem perguntar

- O nome antigo da seção ainda vale. Vete aqui se discordar.

## Perguntas em aberto
- [ ] nada
"""


def test_module_exists():
    check("o módulo common/hooks/_decisions.py existe", MODULE.is_file(),
          f"{MODULE}")


def test_real_documents(D):
    for rel, expected in REAL:
        r = D.read_file(REPO / rel)
        check(f"{rel} tem a seção", r is not None, f"r={r!r}")
        if r is None:
            continue
        check(f"{rel}: {expected} linhas sem veredito",
              len(r.pending) == expected,
              f"got {len(r.pending)}: {[d.text[:60] for d in r.pending]}")
        check(f"{rel}: nenhuma linha com veredito hoje", r.decided == [],
              f"decided={[d.text[:60] for d in r.decided]}")
        body = section_words(REPO / rel)
        for d in r.pending:
            check(f"{rel}: linha {d.line} nas mesmas palavras do arquivo",
                  d.text and words(d.text) in body, f"text={d.text[:80]!r}")


def test_real_texts_are_whole(D):
    # The planejador items span three lines: the reader returns the whole item,
    # not only its first line (a verdict appended at the end of the item lives
    # on its last line).
    r = D.read_file(REPO / "docs/spec/planejador-de-lotes-paralelos.md")
    texts = [d.text for d in r.pending] if r else []
    check("item de várias linhas volta inteiro (até o 'Vete aqui')",
          any(t.startswith("**CS-5 entra nesta especificação**")
              and t.endswith("vire uma demanda separada no BACKLOG.md.")
              for t in texts), f"texts={texts!r}")
    r = D.read_file(REPO / "docs/spec/cepa-espiral-c1.md")
    check("primeira linha de cepa-espiral-c1 nas palavras do arquivo",
          r is not None and r.pending[0].text.startswith(
              "`/common:epic` reusa a skill `guided-interrogation`"),
          f"r={r!r}")


def test_old_name_fixture(D):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "fixture.md"
        p.write_text(FIXTURE, encoding="utf-8")
        r = D.read_file(p)
    check("fixture com `## Decidido sem perguntar`: 1 linha sem veredito",
          r is not None and len(r.pending) == 1, f"r={r!r}")
    check("...nas mesmas palavras do arquivo",
          r is not None and r.pending
          and r.pending[0].text == "O nome antigo da seção ainda vale. "
          "Vete aqui se discordar.", f"r={r!r}")


def test_verdicts_split(D):
    text = """# Spec: x

## Decided without asking

- A decisão sem veredito.
- A mantida. · mantida em 2026-11-06
- A vetada, com motivo. · vetada em 2026-11-06: o dono prefere outra
- Uma de duas linhas
  que termina refinada. · refinada em 2026-11-07
- <decisão que você tomou sozinho>
- n/a
- [ ] pergunta não é decisão

## Next
- fora da seção
"""
    r = D.read(text)
    check("separa sem veredito (1) e com veredito (3)",
          r is not None and len(r.pending) == 1 and len(r.decided) == 3,
          f"r={r!r}")
    if r is None:
        return
    check("o veredito vem nomeado",
          [d.verdict for d in r.decided] == ["mantida", "vetada", "refinada"],
          f"{[d.verdict for d in r.decided]}")
    check("sem veredito tem verdict None", r.pending[0].verdict is None)
    check("veredito na última linha de item de várias linhas é visto",
          r.decided[2].text.endswith("refinada em 2026-11-07"),
          f"{r.decided[2].text!r}")
    check("número da linha é o do arquivo (1-based)",
          [d.line for d in r.pending] == [5]
          and [d.line for d in r.decided] == [6, 7, 8],
          f"{[(d.line, d.text[:20]) for d in r.pending + r.decided]}")
    check("linha de modelo, n/a, checkbox e item fora da seção ficam fora",
          all("modelo" not in d.text and d.text != "n/a"
              and "pergunta" not in d.text and "fora" not in d.text
              for d in r.pending + r.decided))


def test_without_section(D):
    check("sem a seção devolve None", D.read("# Spec\n\n## Outra\n- a\n") is None)
    check("seção vazia devolve listas vazias",
          (lambda r: r is not None and r.pending == [] and r.decided == [])(
              D.read("## Decided without asking\n\n## Next\n")))


def test_hook_imports_module(D):
    src = GATE.read_text(encoding="utf-8")
    check("o hook importa o módulo compartilhado",
          re.search(r"^\s*import _decisions\b|^\s*from _decisions import",
                    src, re.MULTILINE) is not None)
    check("o hook não guarda uma cópia própria do marcador de veredito",
          "VERDICT_RE = re.compile" not in src)
    gate = load(GATE, "spec_readiness_gate_cs2")
    for rel, expected in REAL:
        content = (REPO / rel).read_text(encoding="utf-8")
        line = gate.decision_count_line(content)
        noun = "decisão" if expected == 1 else "decisões"
        check(f"hook conta {expected} em {rel} pelo módulo",
              f"{expected} {noun} sem veredito" in line, line)


def main():
    test_module_exists()
    if not MODULE.is_file():
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    sys.path.insert(0, str(HOOKS))
    D = load(MODULE, "_decisions")
    test_real_documents(D)
    test_real_texts_are_whole(D)
    test_old_name_fixture(D)
    test_verdicts_split(D)
    test_without_section(D)
    test_hook_imports_module(D)
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\nall green")


if __name__ == "__main__":
    main()
