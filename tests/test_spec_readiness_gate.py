#!/usr/bin/env python3
"""Regression tests of the spec-readiness-gate.

`/common:spec` leads an interrogation until the specification becomes rich
enough to build. The failure mode this gate exists to prevent is not
the interrogation being short — it is it ENDING out of tiredness: the agent decides it
is good enough, writes `Status: pronta-para-construir`, and delivers criteria that are
sentences of intent ("the system must validate the registration"), without an
observable surface where anyone could prove it happened. That does not fail there; it fails
at construction, weeks later, when another person interprets the criterion
another way.

What these tests pin down:
  - `Status: rascunho` NEVER blocks, not even with the whole document full of holes (the
    interrogation must be able to write while it runs);
  - declared ready and complete, it passes;
  - a criterion without Surface, without Red test, or with a Surface outside the
    vocabulary, blocks — and the message names WHICH criterion;
  - ready with zero criteria blocks (the most silent case);
  - a leftover open question (`- [ ]`) blocks;
  - the format's template line passes, otherwise the document that
    defines the format could not be edited;
  - the gate reads Write, Edit and MultiEdit, and never blocks what it cannot see.

Run: python3 tests/test_spec_readiness_gate.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "spec-readiness-gate.py"

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


def write(content, tool="Write"):
    key = "content" if tool == "Write" else "new_string"
    return run({"tool_name": tool, "tool_input": {key: content}})


CRITERION_OK = """### CS-1: POST /api/v1/assinaturas sem responsável responde 422

**Superfície:** http
**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — hoje não existe.
"""

READY_OK = f"""# Especificação: assinatura de menor

**Status:** pronta-para-construir

## Critérios de sucesso

{CRITERION_OK}
"""


def test_draft_never_blocks():
    doc = """# Especificação: qualquer coisa

**Status:** rascunho

## Perguntas em aberto
- [ ] quem pode assinar por um menor?

## Critérios de sucesso

### CS-1: o sistema deve validar o cadastro
"""
    rc, _ = write(doc)
    check("rascunho furado não bloqueia", rc == 0, f"rc={rc}")


def test_ready_complete_passes():
    rc, err = write(READY_OK)
    check("pronta e completa passa", rc == 0, f"rc={rc} err={err[:200]}")


def test_missing_surface():
    doc = READY_OK.replace("**Superfície:** http\n", "")
    rc, err = write(doc)
    check("falta Superfície bloqueia", rc == 2, f"rc={rc}")
    check("mensagem nomeia o critério", "CS-1" in err, err[:200])


def test_missing_red_test():
    doc = "\n".join(l for l in READY_OK.splitlines()
                    if not l.startswith("**Teste vermelho:**"))
    rc, err = write(doc)
    check("falta Teste vermelho bloqueia", rc == 2, f"rc={rc}")
    check("mensagem cita Red test", "Red test" in err, err[:200])


def test_surface_outside_the_vocabulary():
    doc = READY_OK.replace("**Superfície:** http", "**Superfície:** banco de dados")
    rc, err = write(doc)
    check("Superfície inventada bloqueia", rc == 2, f"rc={rc}")
    check("mensagem mostra o valor recusado", "banco de dados" in err, err[:200])


def test_all_vocabulary_surfaces_pass():
    for surface in ("http", "cli", "ui", "event", "domain", "application"):
        doc = READY_OK.replace("**Superfície:** http", f"**Superfície:** {surface}")
        rc, err = write(doc)
        check(f"superfície {surface} passa", rc == 0, f"rc={rc} err={err[:120]}")


def test_ready_without_any_criterion():
    doc = """# Especificação: vazia

**Status:** pronta-para-construir

## Problema
Alguma prosa convincente e nenhum critério.
"""
    rc, err = write(doc)
    check("pronta sem critério bloqueia", rc == 2, f"rc={rc}")
    check("mensagem explica o vazio", "nenhum critério" in err, err[:200])


def test_leftover_open_question():
    doc = READY_OK.replace(
        "## Critérios de sucesso",
        "## Perguntas em aberto\n- [ ] menor emancipado conta como menor?\n\n## Critérios de sucesso",
    )
    rc, err = write(doc)
    check("pergunta em aberto bloqueia", rc == 2, f"rc={rc}")
    check("mensagem cita a pergunta", "emancipado" in err, err[:300])


def test_answered_question_does_not_block():
    doc = READY_OK.replace(
        "## Critérios de sucesso",
        "## Perguntas em aberto\n- [x] menor emancipado conta como menor? Não.\n\n## Critérios de sucesso",
    )
    rc, err = write(doc)
    check("pergunta marcada como respondida passa", rc == 0, f"rc={rc} err={err[:200]}")


def test_format_template_line_passes():
    doc = """# Formato da especificação

**Status:** rascunho | pronta-para-construir

## Critérios de sucesso

### CS-<n>: <o critério em termos observáveis>

**Superfície:** <http|cli|ui|event|domain|application>
**Teste vermelho:** <a frase do teste que hoje falharia>
"""
    rc, err = write(doc)
    check("documento que ensina o formato passa", rc == 0, f"rc={rc} err={err[:200]}")


def test_edit_and_multiedit():
    doc = READY_OK.replace("**Superfície:** http\n", "")
    rc, _ = write(doc, tool="Edit")
    check("Edit é lido", rc == 2, f"rc={rc}")

    rc, _ = run({"tool_name": "MultiEdit",
                 "tool_input": {"edits": [{"new_string": doc}]}})
    check("MultiEdit é lido", rc == 2, f"rc={rc}")


def with_temp_file(content):
    """Writes `content` to a temporary file and returns the Path; the caller
    deletes it afterwards.
    """
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                     encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


def test_edit_with_file_path_reads_the_resulting_file():
    # (a) Status rascunho -> pronta, criterion already complete in the file: it used
    # to block (false block, the fragment only has the Status). Must release.
    doc_draft = READY_OK.replace("**Status:** pronta-para-construir",
                                     "**Status:** rascunho")
    path_ = with_temp_file(doc_draft)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(path_),
                "old_string": "**Status:** rascunho",
                "new_string": "**Status:** pronta-para-construir",
            },
        })
        check("Edit que só muda o Status vê o critério completo e libera",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        path_.unlink(missing_ok=True)

    # (b) already pronta in the file, Edit adds an open question in the fragment
    # (which has no Status): it used to pass (false pass). Must block.
    path_ = with_temp_file(READY_OK)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(path_),
                "old_string": "## Critérios de sucesso",
                "new_string": "## Perguntas em aberto\n- [ ] pergunta nova\n\n## Critérios de sucesso",
            },
        })
        check("Edit que reabre pergunta numa spec pronta bloqueia",
              rc == 2, f"rc={rc}")
        check("mensagem cita a pergunta reaberta", "pergunta nova" in err, err[:300])
    finally:
        path_.unlink(missing_ok=True)

    # (c) already pronta in the file, Edit removes the Red test in the fragment (which
    # has neither Status nor CS): it used to pass. Must block.
    path_ = with_temp_file(READY_OK)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(path_),
                "old_string": "**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — hoje não existe.\n",
                "new_string": "",
            },
        })
        check("Edit que remove Teste vermelho numa spec pronta bloqueia",
              rc == 2, f"rc={rc}")
        check("mensagem cita Red test", "Red test" in err, err[:300])
    finally:
        path_.unlink(missing_ok=True)


def test_multiedit_with_file_path_applies_in_sequence():
    # The second edit only matches AFTER the first was applied (the old_string
    # of the second does not exist in the original file). The verdict can only be
    # right if the gate applies both in sequence over the same text.
    doc = READY_OK.replace("**Status:** pronta-para-construir",
                            "**Status:** RASCUNHO_TEMPORARIO")
    path_ = with_temp_file(doc)
    try:
        rc, err = run({
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(path_),
                "edits": [
                    {"old_string": "**Status:** RASCUNHO_TEMPORARIO",
                     "new_string": "**Status:** rascunho"},
                    {"old_string": "**Status:** rascunho",
                     "new_string": "**Status:** pronta-para-construir"},
                ],
            },
        })
        check("MultiEdit aplica as edições em sequência e libera (completa)",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        path_.unlink(missing_ok=True)


TWO_SURFACES_OK = """# Especificação: duas superfícies
**Status:** pronta-para-construir
## Critérios de sucesso
### CS-1: POST /api/v1/assinaturas sem responsável responde 422
**Superfície:** http
**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — hoje não existe.
### CS-2: GET /api/v1/assinaturas retorna lista
**Superfície:** http
**Teste vermelho:** AssinaturaResourceIT#get_lista_retorna200 — hoje não existe.
"""


def test_multiedit_replace_all_swaps_ALL_occurrences():
    # old_string ("**Superfície:** http") appears in BOTH blocks, and the
    # verdict is only right if replace_all swaps both. If the
    # implementation "forgot" replace_all and fell into the uniqueness check
    # (which exists for Edit without replace_all), old_string would match
    # 2x without replace_all requested, and the code would have to release (rc 0) instead
    # of applying the swap. Here the swap IS expected, so the correct rc is 2
    # (both Surfaces become invalid) -- quite different from the rc 0 that the broken
    # implementation would return.
    path_ = with_temp_file(TWO_SURFACES_OK)
    try:
        rc, err = run({
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(path_),
                "edits": [
                    {"old_string": "**Superfície:** http",
                     "new_string": "**Superfície:** banco de dados",
                     "replace_all": True},
                ],
            },
        })
        check("replace_all troca as duas ocorrências e as duas ficam inválidas",
              rc == 2, f"rc={rc} err={err[:200]}")
        check("mensagem cita os dois critérios", "CS-1" in err and "CS-2" in err,
              err[:400])
    finally:
        path_.unlink(missing_ok=True)


TWO_CS_ONE_INVALID = """# Especificação: duas superfícies
**Status:** pronta-para-construir
## Critérios de sucesso
### CS-1: POST /api/v1/assinaturas sem responsável responde 422
**Superfície:** http
**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — hoje não existe.
### CS-2: GET /api/v1/assinaturas retorna lista
**Superfície:** banco de dados
**Teste vermelho:** AssinaturaResourceIT#get_lista_retorna200 — hoje não existe.
"""


def test_multiedit_accumulates_over_the_result_of_the_previous_edit():
    # edit1 fixes the invalid Surface of CS-2. edit2 touches a region that
    # edit1 did NOT touch (the Red test of CS-1) -- edit2's old_string
    # exists both in the ORIGINAL file and in the result of edit1 (because
    # edit1 did not go near there). An implementation that applied each
    # edit over the ORIGINAL text (instead of accumulating over the result of the
    # previous edit) would match both old_strings equally -- only that its
    # final result would DISCARD edit1's fix: CS-2 would remain
    # with "banco de dados" and the rc would be 2, against the rc 0 of the correct
    # implementation (which preserves both fixes).
    path_ = with_temp_file(TWO_CS_ONE_INVALID)
    try:
        rc, err = run({
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(path_),
                "edits": [
                    {"old_string": "**Superfície:** banco de dados",
                     "new_string": "**Superfície:** http"},
                    {"old_string": "**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — hoje não existe.",
                     "new_string": "**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — falha hoje porque o endpoint não existe."},
                ],
            },
        })
        check("os dois consertos se acumulam e a spec completa libera",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        path_.unlink(missing_ok=True)


def test_multiedit_replace_all():
    doc = READY_OK.replace("**Status:** pronta-para-construir",
                            "**Status:** rascunho")
    path_ = with_temp_file(doc)
    try:
        rc, err = run({
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(path_),
                "edits": [
                    {"old_string": "rascunho", "new_string": "pronta-para-construir",
                     "replace_all": True},
                ],
            },
        })
        check("replace_all é respeitado e a spec completa libera",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        path_.unlink(missing_ok=True)


def test_edit_with_nonexistent_file_path_releases():
    rc, err = run({
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/tmp/nao-existe-spec-readiness-gate-teste.md",
            "old_string": "**Status:** rascunho",
            "new_string": "**Status:** pronta-para-construir",
        },
    })
    check("file_path inexistente libera", rc == 0, f"rc={rc} err={err[:200]}")


def test_edit_with_duplicate_old_string_without_replace_all_releases():
    # old_string matches twice and replace_all was not requested: the real Edit
    # tool requires uniqueness and fails by itself, so the gate releases instead of
    # swapping "the first" occurrence on its own.
    doc = READY_OK.replace(
        "**Superfície:** http",
        "**Superfície:** http\n**Superfície:** http",
    )
    path_ = with_temp_file(doc)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(path_),
                "old_string": "**Superfície:** http",
                "new_string": "**Superfície:** banco de dados",
            },
        })
        check("old_string duplicado sem replace_all libera",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        path_.unlink(missing_ok=True)


def test_edit_with_old_string_that_does_not_match_releases():
    path_ = with_temp_file(READY_OK)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(path_),
                "old_string": "isto não existe no arquivo",
                "new_string": "qualquer coisa",
            },
        })
        check("old_string que não bate libera", rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        path_.unlink(missing_ok=True)


def test_edit_with_old_string_that_does_not_match_on_invalid_spec_releases():
    # The spec on disk is ALREADY invalid (pronta without Surface in CS-1) --
    # the previous test uses a VALID spec as base, and so it would not catch
    # an implementation that, on not finding old_string, returned the ORIGINAL text
    # without signaling an error (instead of releasing): with a valid base the two
    # paths give the same rc 0. Here the base is invalid, so only an
    # implementation that really releases (instead of judging the original text
    # with no edit applied) returns rc 0; one that "applied anyway" the unchanged
    # text would return rc 2 (the invalid spec would be judged).
    doc = READY_OK.replace("**Superfície:** http\n", "")
    path_ = with_temp_file(doc)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(path_),
                "old_string": "isto não existe no arquivo",
                "new_string": "qualquer coisa",
            },
        })
        check("old_string que não bate numa spec inválida libera",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        path_.unlink(missing_ok=True)



def test_never_blocks_what_it_cannot_see():
    rc, _ = run({"tool_name": "Bash", "tool_input": {"command": "echo pronta-para-construir"}})
    check("ferramenta fora do escopo passa", rc == 0, f"rc={rc}")

    rc, _ = run({"tool_name": "Write", "tool_input": {}})
    check("Write sem conteúdo visível passa", rc == 0, f"rc={rc}")

    p = subprocess.run([sys.executable, str(HOOK)], input="{ not json",
                       capture_output=True, text=True)
    check("payload ilegível libera", p.returncode == 0, f"rc={p.returncode}")

    rc, _ = write("# Um markdown qualquer sem campo Status nenhum.")
    check("documento sem Status passa", rc == 0, f"rc={rc}")


READY_EN = (READY_OK.replace("pronta-para-construir", "ready-to-build")
             .replace("**Superfície:**", "**Surface:**")
             .replace("**Teste vermelho:**", "**Red test:**"))


def test_english_and_old_names_are_valid():
    rc, err = write(READY_EN)
    check("ready-to-build + Surface + Red test completo passa", rc == 0, err[:200])
    rc, err = write(READY_EN.replace("**Surface:** http\n", ""))
    check("ready-to-build sem Surface bloqueia, nomeando o campo novo",
          rc == 2 and "**Surface:**" in err, err[:300])
    rc, err = write("\n".join(l for l in READY_EN.splitlines()
                              if not l.startswith("**Red test:**")))
    check("ready-to-build sem Red test bloqueia, nomeando o campo novo",
          rc == 2 and "**Red test:**" in err and "`draft`" in err, err[:300])
    rc, err = write(READY_EN.replace("**Surface:** http", "**Surface:** banana"))
    check("Surface fora do vocabulário bloqueia", rc == 2 and "Surface" in err, err[:300])
    rc, err = write(READY_EN.replace("ready-to-build", "draft")
                    .replace("**Red test:**", "**x:**"))
    check("Status: draft furado não bloqueia", rc == 0, err[:200])
    rc, err = write(READY_OK)
    check("o formato antigo (pronta-para-construir) segue passando", rc == 0, err[:200])
    rc, err = write(READY_OK.replace("**Superfície:** http\n", ""))
    check("...e segue bloqueando", rc == 2, err[:200])


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
