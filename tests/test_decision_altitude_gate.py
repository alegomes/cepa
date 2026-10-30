#!/usr/bin/env python3
"""Regression tests for the decision-altitude-gate.

The `**Altitude:**` field of a decision block says WHO reviews (the owner in the
debrief, the lead, or nobody until `--all` is asked) — it does not say what the
decision is about. On 2026-08-19, four autonomous runs wrote 57 blocks and 51 of
them carried a free Portuguese word in that field ("contrato", "schema",
"fronteira"), 35 distinct values. The debrief filters on that field: with 89%
outside the vocabulary, it offered the owner three decisions — all from the
first card — while the ones with the greatest consequence stayed invisible.
Nothing showed up as an error.

What these tests pin down:
  - a value outside the vocabulary blocks, and the message says what to do;
  - the three valid values pass;
  - the documentation's template line passes (otherwise the document that
    defines the vocabulary could not be edited);
  - a block without an Altitude field does NOT block (the debrief already
    assumes tactical, and blocking absence would become a wall when editing a
    legacy block);
  - the gate reads Write, Edit and MultiEdit, and never blocks what it cannot see.

Run: python3 tests/test_decision_altitude_gate.py
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "decision-altitude-gate.py"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def run(payload):
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True)
    return p.returncode, p.stderr


def write_payload(content, tool="Write"):
    field = {"Write": "content", "Edit": "new_string"}.get(tool, "content")
    return {"tool_name": tool, "tool_input": {"file_path": "/tmp/RESULT.md", field: content}}


BLOCK = "### Decision: cortar a cadeia de hash\n\n**Altitude:** {}\n\n**Chosen:** A\n"


def test_free_word_blocks():
    rc, err = run(write_payload(BLOCK.format("garantia")))
    check("palavra livre no campo Altitude bloqueia", rc == 2, err)
    check("a mensagem mostra o valor recusado", '"garantia"' in err, err)
    check("a mensagem lista os três valores válidos",
          all(v in err for v in ("strategic", "tactical", "implementation")), err)
    check("a mensagem diz onde o assunto deve ir",
          "título" in err and "### Decision:" in err, err)


def test_vocabulary_passes():
    for v in ("strategic", "tactical", "implementation"):
        rc, err = run(write_payload(BLOCK.format(v)))
        check(f"'{v}' passa", rc == 0, err)
    rc, _ = run(write_payload(BLOCK.format("**Tactical**")))
    check("valor com marcação e maiúscula passa", rc == 0)


def test_documentation_template_line_passes():
    rc, err = run(write_payload("**Altitude:** strategic | tactical | implementation\n"))
    check("a enumeração que ensina o vocabulário passa", rc == 0, err)
    rc, err = run(write_payload("**Altitude:** <strategic|tactical|implementation>\n"))
    check("o marcador de preencher passa", rc == 0, err)


def test_missing_field_does_not_block():
    rc, err = run(write_payload("### Decision: x\n\n**Chosen:** Option A\n"))
    check("bloco sem campo Altitude não bloqueia", rc == 0, err)


def test_edit_and_multiedit():
    rc, _ = run(write_payload(BLOCK.format("fronteira"), tool="Edit"))
    check("Edit também é lido", rc == 2)
    rc, _ = run({"tool_name": "MultiEdit", "tool_input": {
        "file_path": "/tmp/RESULT.md",
        "edits": [{"new_string": "nada aqui"},
                  {"new_string": BLOCK.format("retenção")}]}})
    check("MultiEdit também é lido", rc == 2)


def test_never_blocks_what_it_cannot_see():
    rc, _ = run({"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.md"}})
    check("sem conteúdo visível, libera", rc == 0)
    rc, _ = run({"tool_name": "Bash", "tool_input": {"command": "echo Altitude: contrato"}})
    check("ferramenta fora do escopo, libera", rc == 0)
    p = subprocess.run([sys.executable, str(HOOK)], input="isto não é json",
                       capture_output=True, text=True)
    check("payload ilegível, libera", p.returncode == 0)


def test_does_not_block_the_documents_that_define_the_field():
    """A gate that stops you from fixing its own definition teaches people to turn the gate off.

    The two documents cite the field in prose ("**Altitude field** classifies
    who reviews...") and carry the template line with a comment beside it. Both
    were blocked in the first version of the gate.
    """
    for rel_path in ("common/skills/autonomous-mode/SKILL.md", "common/commands/debrief.md"):
        content = (REPO / rel_path).read_text(encoding="utf-8")
        rc, err = run(write_payload(content))
        check(f"{rel_path.split('/')[-1]} passa pelo gate", rc == 0, err[:300])

    rc, err = run(write_payload("**Altitude field** classifies who reviews the decision\n"))
    check("prosa que fala do campo, sem dois pontos, não é valor",
          rc == 0, err)
    rc, err = run(write_payload("**Altitude:** <strategic|tactical|implementation>   ← escolha uma\n"))
    check("linha-modelo com comentário ao lado passa", rc == 0, err)


def test_only_applies_inside_the_decision_block():
    """`Altitude` outside a decision block is ANOTHER field, with another vocabulary.

    On 2026-08-22 the completion-auditor tried to write
    `.claude/acceptance/WEGO-2085.yaml` with `altitude: http` — there the field says
    on which surface the criterion is observable (http/cli/ui/event/domain/application),
    nothing to do with who reviews the decision. The gate blocked it and the agent
    worked around it by renaming the field by force, which makes each session invent
    a name and the acceptance artifacts stop being comparable.
    """
    rc, err = run(write_payload("### Decision: mover o gate\n\n**Altitude:** operacional\n"))
    check("dentro do bloco, palavra fora do vocabulário bloqueia", rc == 2, err)

    yaml = ("key: WEGO-2085\ncriteria:\n  - id: AC1\n    altitude: http\n"
            "    surface: POST /acessos\n")
    rc, err = run({"tool_name": "Write", "tool_input": {
        "file_path": "/tmp/WEGO-2085.yaml", "content": yaml}})
    check("yaml de aceite sem bloco de decisão passa", rc == 0, err)

    mixed = ("### Decision: cortar a cadeia\n\n**Altitude:** tactical\n\n"
             "### Critérios de aceite\n\ncriteria:\n  - altitude: http\n")
    rc, err = run(write_payload(mixed))
    check("altitude fora do bloco, no mesmo arquivo, passa", rc == 0, err)


def test_edit_without_header_uses_the_target_file():
    """An Edit may carry only the field line; the file says whether it is a block.

    Without this, fixing the altitude of an existing block through Edit would escape
    the gate — which is exactly the moment when the author is there to fix it.
    """
    import tempfile, os
    d = tempfile.mkdtemp()
    md = os.path.join(d, "RESULT.md")
    Path(md).write_text("### Decision: x\n\n**Altitude:** tactical\n", encoding="utf-8")
    rc, _ = run({"tool_name": "Edit", "tool_input": {
        "file_path": md, "new_string": "**Altitude:** contrato"}})
    check("fragmento sem cabeçalho, em arquivo com bloco, bloqueia", rc == 2)

    ya = os.path.join(d, "WEGO-2085.yaml")
    Path(ya).write_text("key: WEGO-2085\ncriteria:\n  - altitude: cli\n", encoding="utf-8")
    rc, err = run({"tool_name": "Edit", "tool_input": {
        "file_path": ya, "new_string": "    altitude: http"}})
    check("fragmento sem cabeçalho, em arquivo sem bloco, passa", rc == 0, err)

    rc, err = run({"tool_name": "Edit", "tool_input": {
        "file_path": os.path.join(d, "nao-existe.yaml"), "new_string": "altitude: http"}})
    check("arquivo inexistente não vira bloco de decisão", rc == 0, err)


def main():
    test_free_word_blocks()
    test_vocabulary_passes()
    test_documentation_template_line_passes()
    test_missing_field_does_not_block()
    test_edit_and_multiedit()
    test_never_blocks_what_it_cannot_see()
    test_does_not_block_the_documents_that_define_the_field()
    test_only_applies_inside_the_decision_block()
    test_edit_without_header_uses_the_target_file()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
