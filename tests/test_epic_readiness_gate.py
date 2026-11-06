#!/usr/bin/env python3
"""Regression tests for the Epic sieve in the spec-readiness-gate, and for /common:epic (CS-5).

`/common:epic` interviews the owner in the "grill me" style and writes
`docs/epics/<name>.md`. It closes by script, not by criterion: the document may only
declare itself `Status: pronta` when each cycle of the ladder has a
demonstration script with an observable effect on screen and in backend, the list of
invariants is not empty and the "Decidido sem perguntar" section exists. Without the sieve, the Epic
closes out of tiredness just as the specification would, and `/common:plan --from-epic`
(CS-6) derives a queue from a cycle nobody knows how to demonstrate.

What these tests pin down:
  - an Epic in `rascunho` never blocks, not even all holey;
  - a complete `pronta` Epic passes (Write and Edit that only swaps the Status);
  - a `pronta` Epic blocks, naming the cycle or the section, when missing: script,
    screen effect, backend effect, cycle line, invariant, the
    "Decidido sem perguntar" section, or an open question remains;
  - who is an Epic: the path `docs/epics/*.md` or the title `# Epic:`;
  - a specification that is not an Epic keeps the old ruler: `Status: pronta`
    on it is not gated (only `pronta-para-construir`);
  - discovery mode may write `docs/epics/**`;
  - the command exists, is conversational (the session-routine-guard blocks it), is
    in the catalog, and the grill-me contract is written in it.

Run: python3 tests/test_epic_readiness_gate.py
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "spec-readiness-gate.py"
WRITE = REPO / "common" / "hooks" / "write-mode-gate.py"
CMD = REPO / "common" / "commands" / "epic.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def run(payload, env=None):
    p = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stderr


def write(content, file_path=None):
    ti = {"content": content}
    if file_path:
        ti["file_path"] = file_path
    return run({"tool_name": "Write", "tool_input": ti})


LADDER_PT = """## Escada de valor

| Ciclo | Roteiro de demonstração | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
| 1. Ler | O operador carrega o PDF do contrato e vê as 3 respostas. | a tela de upload mostra as 3 respostas com a cláusula citada | `GET /api/v1/contratos/{id}/respostas` devolve as 3 com o nonce do upload | upload → extrator → tela | próxima quinzena |
| 2. Regrar | O operador aprova uma regra e a próxima conta já sai glosada. | a conta aparece com a glosa e o motivo | a tabela `glosa` tem a linha com o id da regra | regra → motor → conta | depois do ciclo 1 |
"""

INVARIANTS_PT = """## Invariantes (nunca regridem)

- A conta já faturada nunca muda de valor.
"""

DECIDED_PT = """## Decidido sem perguntar (vete aqui)

- O PDF fica no bucket que já existe.
"""

QUESTIONS_PT = """## Perguntas em aberto

- [x] Quem aprova a regra? O auditor médico, na tela de regras.
"""


def epic(status="pronta", ladder=LADDER_PT, invariants=INVARIANTS_PT,
         decided=DECIDED_PT, questions=QUESTIONS_PT, title="# Epic: Contratos",
         outcome=""):
    return f"""{title}

**Status:** {status} · **Aberto em:** 2026-10-08

## Intenção

O operador deixa de ler contrato à mão.

{invariants}
{ladder}
{decided}
{questions}
{outcome}"""


def test_draft_status_never_blocks():
    holey = epic(status="rascunho", ladder="## Escada de valor\n", invariants="",
                  decided="", questions="## Perguntas em aberto\n- [ ] tudo\n")
    rc, err = write(holey)
    check("Epic rascunho todo furado passa", rc == 0, err)


def test_ready_complete_passes():
    rc, err = write(epic())
    check("Epic pronta completo passa", rc == 0, err)
    rc, err = write(epic(title="# Epic: x"), file_path="/tmp/x/docs/epics/x.md")
    check("Epic pronta completo passa com file_path em docs/epics", rc == 0, err)


def test_ready_without_screen_blocks():
    ladder = LADDER_PT.replace(
        "| a conta aparece com a glosa e o motivo |", "|  |")
    rc, err = write(epic(ladder=ladder))
    check("ciclo sem efeito em tela bloqueia", rc == 2, err)
    check("a mensagem nomeia o ciclo 2 e a tela",
          "2. Regrar" in err and "tela" in err.lower(), err)


def test_ready_without_backend_blocks():
    ladder = LADDER_PT.replace(
        "| `GET /api/v1/contratos/{id}/respostas` devolve as 3 com o nonce do upload |",
        "| a definir |")
    rc, err = write(epic(ladder=ladder))
    check("ciclo com backend placeholder bloqueia", rc == 2, err)
    check("a mensagem nomeia o ciclo 1 e o backend",
          "1. Ler" in err and "backend" in err.lower(), err)


def test_cell_that_says_nothing_blocks():
    for empty in ("—", "nenhum", "n/d"):
        ladder = LADDER_PT.replace(
            "| a conta aparece com a glosa e o motivo |", f"| {empty} |")
        rc, err = write(epic(ladder=ladder))
        check(f'célula de tela "{empty}" bloqueia', rc == 2, err)


def test_escaped_pipe_does_not_shift_column():
    # `\|` inside the script is not a divider: without this the screen becomes backend and
    # the backend becomes "what crosses", and the cycle passes with the wrong column.
    ladder = LADDER_PT.replace("O operador carrega o PDF",
                               "O operador escolhe PDF \\| DOCX, carrega o PDF")
    rc, err = write(epic(ladder=ladder))
    check("barra escapada na célula não quebra Epic completo", rc == 0, err)
    ladder = ladder.replace(
        "| `GET /api/v1/contratos/{id}/respostas` devolve as 3 com o nonce do upload |",
        "|  |")
    rc, err = write(epic(ladder=ladder))
    check("com barra escapada, backend vazio ainda é achado no ciclo 1",
          rc == 2 and "1. Ler" in err and "backend" in err.lower(), err)


def test_ready_without_script_blocks():
    ladder = LADDER_PT.replace(
        "| O operador carrega o PDF do contrato e vê as 3 respostas. |", "| - |")
    rc, err = write(epic(ladder=ladder))
    check("ciclo sem roteiro bloqueia", rc == 2, err)
    check("a mensagem nomeia o roteiro", "script" in err.lower(), err)


def test_ready_without_effect_columns_blocks():
    # The old format, written by hand: only the script column. Ready like this is the
    # script without observable effect, which is what the sieve exists to refuse.
    ladder = """## Escada de valor

| Ciclo | Roteiro de demonstração | O que atravessa | Quando |
|---|---|---|---|
| 1. Ler | O operador vê as 3 respostas. | upload → tela | já |
"""
    rc, err = write(epic(ladder=ladder))
    check("escada sem colunas de tela e backend bloqueia", rc == 2, err)
    check("a mensagem diz as colunas que faltam",
          "Effect on screen" in err and "Effect in backend" in err, err)


def test_ready_without_cycle_blocks():
    ladder = """## Escada de valor

| Ciclo | Roteiro de demonstração | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
"""
    rc, err = write(epic(ladder=ladder))
    check("escada com zero ciclos bloqueia", rc == 2, err)
    rc, err = write(epic(ladder=""))
    check("sem seção Escada de valor bloqueia", rc == 2, err)
    check("a mensagem nomeia a escada", "value ladder" in err.lower(), err)


def test_ready_without_invariant_blocks():
    rc, err = write(epic(invariants="## Invariantes (nunca regridem)\n\n"))
    check("Invariantes vazia bloqueia", rc == 2, err)
    check("a mensagem nomeia os invariantes", "invariante" in err.lower(), err)
    rc, err = write(epic(invariants="## Invariantes\n\n- <invariante>\n"))
    check("Invariantes só com placeholder bloqueia", rc == 2, err)
    rc, err = write(epic(invariants=""))
    check("sem seção Invariantes bloqueia", rc == 2, err)


def test_invariant_in_another_section_does_not_count():
    # A list item after the Invariants section (not in the Intent; in the next
    # section) must not make the empty list pass.
    inv = "## Invariantes (nunca regridem)\n\n## Outra coisa\n\n- item fora\n"
    rc, err = write(epic(invariants=inv))
    check("item de lista de outra seção não conta como invariante", rc == 2, err)


def test_ready_without_decided_blocks():
    rc, err = write(epic(decided=""))
    check("sem seção Decidido sem perguntar bloqueia", rc == 2, err)
    check("a mensagem nomeia a seção", "Decided without asking" in err, err)


def test_ready_with_open_question_blocks():
    rc, err = write(epic(questions="## Perguntas em aberto\n\n- [ ] Quem aprova a regra?\n"))
    check("pergunta em aberto bloqueia Epic pronta", rc == 2, err)
    check("a mensagem cita a pergunta", "Quem aprova a regra" in err, err)


def test_epic_by_path_without_title():
    doc = epic(title="# Contratos e regras", decided="")
    rc, err = write(doc)
    check("sem título Epic e sem caminho, 'pronta' não é gateado", rc == 0, err)
    rc, err = write(doc, file_path="/tmp/r/docs/epics/contratos.md")
    check("em docs/epics/, 'pronta' é gateado mesmo sem título Epic", rc == 2, err)


def test_edit_that_only_swaps_status_is_judged_whole():
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "docs" / "epics" / "contratos.md"
        target.parent.mkdir(parents=True)
        target.write_text(epic(status="rascunho", invariants=""))
        rc, err = run({"tool_name": "Edit", "tool_input": {
            "file_path": str(target),
            "old_string": "**Status:** rascunho",
            "new_string": "**Status:** pronta",
        }})
        check("Edit que só troca o Status olha o arquivo inteiro", rc == 2, err)
        target.write_text(epic(status="rascunho"))
        rc, err = run({"tool_name": "Edit", "tool_input": {
            "file_path": str(target),
            "old_string": "**Status:** rascunho",
            "new_string": "**Status:** pronta",
        }})
        check("Edit que só troca o Status de um Epic completo passa", rc == 0, err)


def test_non_epic_spec_keeps_ruler():
    spec = """# Especificação: x

**Status:** pronta

## Critérios de sucesso
"""
    rc, err = write(spec, file_path="/tmp/r/docs/spec/x.md")
    check("especificação com 'pronta' (não Epic) segue livre", rc == 0, err)
    spec2 = spec.replace("pronta", "pronta-para-construir")
    rc, err = write(spec2, file_path="/tmp/r/docs/spec/x.md")
    check("especificação pronta-para-construir sem critério segue bloqueada",
          rc == 2, err)


def test_format_template_passes():
    # The command itself teaches the format with the Status template line.
    doc = epic(status="rascunho | pronta", ladder="", invariants="", decided="")
    rc, err = write(doc)
    check("linha-modelo 'rascunho | pronta' não é gateada", rc == 0, err)


def test_discovery_writes_docs_epics():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d).resolve()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / ".claude").mkdir()
        (root / ".claude" / "session-mode").write_text("modo: descoberta\n")
        env = dict(os.environ)
        env.pop("CEPA_MODO", None)
        payload = {
            "tool_name": "Write",
            "cwd": str(root),
            "tool_input": {"file_path": str(root / "docs" / "epics" / "c.md"),
                           "content": "# Epic: c\n"},
        }
        p = subprocess.run([sys.executable, str(WRITE)], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, cwd=str(root))
        check("modo descoberta pode escrever docs/epics/<nome>.md",
              p.returncode == 0, p.stderr)
        payload["tool_input"]["file_path"] = str(root / "common" / "x.py")
        p = subprocess.run([sys.executable, str(WRITE)], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, cwd=str(root))
        check("controle: modo descoberta segue barrando código",
              p.returncode == 2, p.stderr)


def test_command_exists_and_is_grill_me():
    check("common/commands/epic.md existe", CMD.exists())
    if not CMD.exists():
        return
    text = CMD.read_text()
    fm = text.split("---", 2)[1] if text.startswith("---") else ""
    check("frontmatter declara interaction: conversational",
          re.search(r"^interaction:\s*conversational\s*$", fm, re.M) is not None)
    check("argumento é <nome>", re.search(r"^argument-hint:.*<name>", fm, re.M) is not None)
    check("escreve docs/epics/<nome>.md", "docs/epics/<name>.md" in text)
    check("uma pergunta por turno", "one question per turn" in text.lower())
    check("proíbe menu / AskUserQuestion",
          "AskUserQuestion" in text and "list of options" in text.lower())
    check("um único ? por turno, sem alternativas enumeradas na frase",
          "only `?` of the turn" in text and "menu written inline" in text)
    check("releitura que corta a segunda pergunta ligada por 'e'",
          "reread the question" in text and "cut the second one" in text)
    check("desafio único com as duas perguntas-modelo",
          "quem vê isso e onde?" in text and "o que quebra se faltar?" in text)
    check("grava no mesmo turno", "same turn" in text)
    check("proposta antes da pergunta, turno termina nela",
          "**before** the question" in text)
    # The 2026-10-08 transcript showed the challenge coming out as a report
    # (Pra você + numbered question), pulled by the global plain-report rule.
    check("turno de entrevista não usa plain-report",
          "not a work report" in text and "plain-report" in text)
    check("recusa pronta antes do crivo em voz alta",
          "refuse out loud" in text)
    check("carrega guided-interrogation", "guided-interrogation" in text)
    check("fecha pelo spec-readiness-gate", "spec-readiness-gate" in text)
    check("formato traz as colunas de efeito",
          "Effect on screen" in text and "Effect in backend" in text)


def test_command_in_catalog():
    cat = (REPO / "docs" / "commands.md").read_text()
    check("/common:epic tem linha na tabela do catálogo",
          re.search(r"^\|\s*`/common:epic`\s*\|", cat, re.M) is not None)


def test_session_blocks_epic():
    guard = REPO / "common" / "hooks" / "session-routine-guard.py"
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO / "common")
    env["HOME"] = tempfile.mkdtemp()  # without installed_plugins.json: reads the repo
    p = subprocess.run([sys.executable, str(guard)],
                       input=json.dumps({"prompt": "/common:session common:epic contratos"}),
                       capture_output=True, text=True, env=env)
    check("/common:session common:epic é barrado (rotina conversacional)",
          p.returncode == 2, p.stderr)


LINT = REPO / "common" / "hooks" / "report-style-lint.py"

# Long-enough interview speech (>= 80 words) for the lint to measure, without
# any plain-report block: it is exactly the turn that /common:epic produces.
SPEECH = ("Gravei sua resposta na Intenção do documento. Se o sistema disser que "
        "o procedimento tem cobertura com carência de noventa dias e estiver "
        "errado, ou não achar a cláusula, o que quebra para o operador? Minha "
        "proposta: a resposta sempre traz o trecho do contrato e a página de "
        "onde saiu, e quando o sistema não tem certeza ele diz que não "
        "encontrou em vez de chutar, porque assim o operador confere em "
        "segundos e só liga para o setor de contratos nos casos duvidosos que "
        "sobram depois disso. Corrija se não for isso, e diga o que quebraria "
        "para ele se faltar?")


def _lint_stop(target, speech=SPEECH, extra=None):
    d = Path(tempfile.mkdtemp(prefix="cs5-lint-"))
    rows = [
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "text", "text": "quase isso, a pergunta é sempre a mesma"}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": target}}]}},
    ]
    if extra:
        rows.append({"type": "assistant", "message": {"role": "assistant",
                                                      "content": [extra]}})
    rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": speech}]}})
    t = d / "t.jsonl"
    t.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    env = dict(os.environ, CEPA_REPORT_STYLE_DIR=str(d / "st"),
               CEPA_TELEMETRY_DIR=str(d / "tel"))
    p = subprocess.run([sys.executable, str(LINT)], input=json.dumps({
        "hook_event_name": "Stop", "session_id": "s", "transcript_path": str(t),
        "cwd": str(d)}), capture_output=True, text=True, env=env)
    return '"block"' in p.stdout


def test_lint_spares_interview_turn():
    # The 2026-10-08 transcript (docs/proof/CS-5-transcricao.md): the lint
    # ordered the challenge rewritten as a report, with a numbered question — a menu
    # in other clothes, and that is what grill me forbids.
    check("lint não bloqueia turno que só gravou docs/epics e termina em pergunta",
          not _lint_stop("/r/docs/epics/contratos.md"))
    # Item spec-isento-do-report-style-lint (2026-11-06, CS-5 follow-up): the
    # /common:spec round also writes its document every turn and ends asking,
    # so it is spared like the epic interview. The plural directory is not.
    check("turno do /common:spec (docs/spec) também é poupado",
          not _lint_stop("/r/docs/spec/x.md"))
    check("controle: docs/specs (plural) segue medido",
          _lint_stop("/r/docs/specs/x.md"))
    # The pair review of 61b71db: the closing report ends in the numbered
    # decision list, which has `?` in the last paragraph. It is a report.
    closing = (SPEECH.replace("?", ".") + "\n\n**Pra você:** 1 decisão.\n\n"
                  "### Detalhe técnico\nGravei o Status como pronta.\n\n"
                  "### Decisões e próximos passos\n"
                  "1. Rodo o plan do ciclo 1? Recomendo sim, a fila nasce dele.")
    check("controle: relatório de fechamento terminando em pergunta é medido",
          _lint_stop("/r/docs/epics/c.md", speech=closing))
    check("controle: mesma fala editando código é medida e bloqueada",
          _lint_stop("/r/common/hooks/x.py"))
    check("lint poupa a pergunta seguida da proposta no mesmo parágrafo",
          not _lint_stop("/r/docs/epics/c.md",
                         speech=SPEECH.rstrip("?") + ". Corrija."))
    check("controle: gravou docs/epics mas o último parágrafo não pergunta",
          _lint_stop("/r/docs/epics/c.md",
                     speech=SPEECH + "\n\nFechei o Epic e gravei o Status como pronta."))
    commit = {"type": "tool_use", "name": "Bash",
              "input": {"command": "git commit -m x"}}
    check("controle: turno de entrevista que também commitou é medido",
          _lint_stop("/r/docs/epics/c.md", extra=commit))
    other = {"type": "tool_use", "name": "Write",
             "input": {"file_path": "/r/docs/epics/sub/c.md"}}
    check("controle: escrita fora de docs/epics/<nome>.md é medida",
          _lint_stop("/r/docs/epics/c.md", extra=other))


# ── holes the proof-reviewer found in 65908ee (perturbations S1-S16) ────

def test_epic_ready_to_build_is_also_gated():
    # S1: without this, an Epic that uses the specification's word escapes the sieve.
    rc, err = write(epic(status="pronta-para-construir", invariants=""))
    check("Epic com pronta-para-construir incompleto bloqueia", rc == 2, err)


def test_checkbox_only_invariant_does_not_count():
    # S2: a `- [x]` item is an answered question, not an invariant.
    inv = "## Invariantes (nunca regridem)\n\n- [x] A conta nunca muda.\n"
    rc, err = write(epic(invariants=inv))
    check("Invariantes só com - [x] bloqueia", rc == 2, err)


def test_template_question_does_not_count_as_open():
    # S3: the template line `- [ ] <pergunta>` is not an open question.
    rc, err = write(epic(questions="## Perguntas em aberto\n\n- [ ] <pergunta>\n"))
    check("'- [ ] <pergunta>' (modelo) não bloqueia Epic completo", rc == 0, err)


def test_short_line_without_backend_column_blocks():
    # S4: a line that ends before the backend column does not fill it.
    ladder = """## Escada de valor

| Ciclo | Roteiro de demonstração | Efeito em tela | Efeito em backend |
|---|---|---|---|
| 1. Ler | O operador vê as 3 respostas. | a tela mostra as 3 |
"""
    rc, err = write(epic(ladder=ladder))
    check("linha de ciclo curta (sem backend) bloqueia",
          rc == 2 and "backend" in err.lower(), err)


def test_many_open_questions_summarized():
    # S5: the message does not dump them all; it says how many remain.
    open_ones = "".join(f"- [ ] pergunta {i}?\n" for i in range(7))
    rc, err = write(epic(questions="## Perguntas em aberto\n\n" + open_ones))
    check("7 perguntas abertas: bloqueia e diz 'e mais 2'",
          rc == 2 and "e mais 2" in err, err)


def _gate_mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("srg", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cells_escaped_pipe_at_the_end():
    # S6: `\|` at the end of the line is content of the last cell, not the divider.
    cell = _gate_mod().cells("| a | b \\|")
    check("cells: '\\|' no fim fica na última célula",
          cell == ["a", "b \\|"], repr(cell))


def test_empty_epic_ignores_case():
    # S7: capitalized "Nenhum" is also a cell that says nothing.
    ladder = LADDER_PT.replace(
        "| a conta aparece com a glosa e o motivo |", "| Nenhum |")
    rc, err = write(epic(ladder=ladder))
    check("célula 'Nenhum' (maiúscula) bloqueia", rc == 2, err)


def test_status_with_bullet_separator():
    # S8: `**Status:** pronta • **Aberto em:**` is still ready.
    doc = epic(invariants="").replace("**Status:** pronta ·", "**Status:** pronta •")
    rc, err = write(doc)
    check("Status 'pronta •' incompleto bloqueia", rc == 2, err)


def _lint_rows(rows, speech=SPEECH):
    d = Path(tempfile.mkdtemp(prefix="cs5-lint-"))
    rows = list(rows) + [{"type": "assistant", "message": {
        "role": "assistant", "content": [{"type": "text", "text": speech}]}}]
    t = d / "t.jsonl"
    t.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    env = dict(os.environ, CEPA_REPORT_STYLE_DIR=str(d / "st"),
               CEPA_TELEMETRY_DIR=str(d / "tel"))
    p = subprocess.run([sys.executable, str(LINT)], input=json.dumps({
        "hook_event_name": "Stop", "session_id": "s", "transcript_path": str(t),
        "cwd": str(d)}), capture_output=True, text=True, env=env)
    return '"block"' in p.stdout


def _u(text="responde"):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "text", "text": text}]}}


def _tool(name, entry, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain, "message": {
        "role": "assistant", "content": [
            {"type": "tool_use", "name": name, "input": entry}]}}


def test_lint_exception_rules():
    epic_md = {"file_path": "/r/docs/epics/c.md"}
    # S9 + S11: subagent-only writing is not the interview recording.
    check("controle: só subagente gravou docs/epics, turno é medido",
          _lint_rows([_u(), _tool("Edit", epic_md, sidechain=True)]))
    # S10: what came before the last prompt does not count for this turn.
    check("escrita de código em turno ANTERIOR não tira a exceção",
          not _lint_rows([_u("antes"), _tool("Edit", {"file_path": "/r/x.py"}),
                          _u(), _tool("Edit", epic_md)]))
    # S12: the path must be really docs/epics, not a suffix of it.
    check("controle: mydocs/epics/ não é docs/epics/, turno é medido",
          _lint_rows([_u(), _tool("Edit", {"file_path": "/r/mydocs/epics/c.md"})]))
    # S13: MultiEdit and NotebookEdit outside docs/epics remove the exception.
    check("controle: MultiEdit em código junto, turno é medido",
          _lint_rows([_u(), _tool("Edit", epic_md),
                      _tool("MultiEdit", {"file_path": "/r/x.py", "edits": []})]))
    check("controle: NotebookEdit junto, turno é medido",
          _lint_rows([_u(), _tool("Edit", epic_md),
                      _tool("NotebookEdit", {"notebook_path": "/r/n.ipynb"})]))
    # S14: merge and push are also delivered work.
    for cmd in ("git merge x", "git push"):
        check(f"controle: '{cmd}' no turno, turno é medido",
              _lint_rows([_u(), _tool("Edit", epic_md),
                          _tool("Bash", {"command": cmd})]))
    # Each mark of the report, alone, already removes the exception.
    for mark in ("**Pra você:** nada.", "### Detalhe técnico\nx",
                  "### Decisões e próximos passos\n1. x?"):
        speech = mark + "\n\n" + SPEECH
        check(f"controle: marca de relatório sozinha ({mark[:14]!r}) é medida",
              _lint_rows([_u(), _tool("Edit", epic_md)], speech=speech))


def test_prose_of_intent_and_closing():
    text = CMD.read_text()
    # S15 and S16: the two prose rules that the transcript exercises.
    check("intenção em dois turnos", "**Intent**, in two turns" in text)
    check("grava pronta no mesmo turno em que a última lacuna fecha",
          "write `ready` in the same turn" in text)
    # S17: the line of e0c7d05, which took turn 1 to 10 of 10 in round 7.
    check("com a intenção no argumento, turno 1 pergunta só o que se faz hoje",
          "If the intent came in the argument" in text
          and "record it and ask only" in text
          and "what hurts along that path" in text)


def test_descriptive_texts():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_modes", REPO / "common" / "hooks" / "_modes.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    check("o gate da descoberta cita docs/epics",
          "docs/epics" in (mod.MODES.get("discovery") or mod.MODES["descoberta"])["gate"])
    cat = (REPO / "docs" / "commands.md").read_text()
    check("o cenário 'ideia vaga' do catálogo cita /common:epic",
          re.search(r"^- `/common:epic <nome>`", cat, re.M) is not None)


# ── English names (2026-10-23): the gate accepts both languages ──────────────
LADDER_EN = (LADDER_PT.replace("## Escada de valor", "## Value ladder")
             .replace("| Ciclo | Roteiro de demonstração | Efeito em tela | Efeito em backend | O que atravessa | Quando |",
                      "| Cycle | Script | Effect on screen | Effect in backend | What it crosses | When |"))
INVARIANTS_EN = INVARIANTS_PT.replace("## Invariantes (nunca regridem)",
                                        "## Invariants (never regress)")
DECIDED_EN = DECIDED_PT.replace("## Decidido sem perguntar (vete aqui)",
                                  "## Decided without asking (veto here)")


WHO = """## Who it is for

O operador de faturamento do hospital, que hoje lê o contrato à mão.
"""
METRIC = """## Outcome metric

**Baseline:** 40 min por conta · **Target:** 10 min por conta · **Source:** `GET /api/v1/metricas/tempo-por-conta`
"""
OUT = """## Out of scope

- Contratos em papel sem digitalização — o extrator só lê PDF.
"""
OUTCOME_EN = WHO + "\n" + METRIC + "\n" + OUT
IMPACT = """## Impact

**Measured value:** 14 min por conta · **Measured on:** 2026-12-01, pela mesma rota da Source
"""


def epic_en(status="ready", ladder=LADDER_EN, invariants=INVARIANTS_EN,
            decided=DECIDED_EN, outcome=OUTCOME_EN, **kw):
    return epic(status=status, ladder=ladder, invariants=invariants,
                decided=decided, outcome=outcome, **kw)


def test_complete_english_passes_and_complete_old_passes():
    rc, err = write(epic_en())
    check("Epic `Status: ready` + `## Value ladder` completo passa", rc == 0, err)
    rc, err = write(epic(status="pronta"))
    check("Epic `Status: pronta` + `## Escada de valor` completo passa", rc == 0, err)
    rc, err = write(epic_en(status="ready-to-build"))
    check("Epic `ready-to-build` completo passa", rc == 0, err)


def test_holey_english_blocks_and_message_gives_the_new_names():
    rc, err = write(epic_en(ladder=LADDER_EN.replace(
        "| a conta aparece com a glosa e o motivo |", "|  |")))
    check("ready: ciclo sem Effect on screen bloqueia", rc == 2, err)
    check("...nomeando a coluna nova", "Effect on screen" in err, err)
    rc, err = write(epic_en(invariants=""))
    check("ready sem `## Invariants` bloqueia, nomeando a seção nova",
          rc == 2 and "## Invariants" in err, err)
    rc, err = write(epic_en(decided=""))
    check("ready sem `## Decided without asking` bloqueia, nomeando a seção nova",
          rc == 2 and "## Decided without asking" in err, err)
    rc, err = write(epic_en(ladder=""))
    check("ready sem `## Value ladder` bloqueia, nomeando a seção nova",
          rc == 2 and "## Value ladder" in err, err)
    rc, err = write(epic_en(questions="## Perguntas em aberto\n- [ ] quem?\n"))
    check("ready com pergunta aberta bloqueia, e diz `draft`",
          rc == 2 and "`draft`" in err, err)


def test_draft_never_blocks():
    rc, err = write(epic_en(status="draft", ladder="## Value ladder\n",
                            invariants="", decided=""))
    check("Epic `Status: draft` todo furado passa", rc == 0, err)


# ── Outcome screen (2026-11-02): who, out of scope, metric; closed needs impact ─
def test_ready_requires_who_out_of_scope_and_metric():
    rc, err = write(epic_en(outcome=""))
    check("ready sem as três seções de resultado bloqueia", rc == 2, err)
    check("...nomeando as três",
          all(n in err for n in ("## Who it is for", "## Out of scope",
                                 "## Outcome metric")), err)
    rc, err = write(epic_en(outcome=METRIC + OUT))
    check("ready sem Who it is for bloqueia só por ela",
          rc == 2 and "falta a seção `## Who it is for`" in err
          and "## Out of scope` —" not in err and "Out of scope:" not in err, err)
    rc, err = write(epic_en(outcome="## Who it is for\n\n<quem>\n\n" + METRIC + OUT))
    check("Who it is for só com placeholder bloqueia",
          rc == 2 and "Who it is for: a seção está vazia" in err, err)
    rc, err = write(epic_en(outcome=WHO + "\n## Out of scope\n\n- <item>\n" + METRIC))
    check("Out of scope só com placeholder bloqueia",
          rc == 2 and "Out of scope: a lista está vazia" in err, err)


def test_metric_fields_on_one_line_are_each_checked():
    for field in ("Baseline", "Target", "Source"):
        metric = re.sub(rf"\*\*{field}:\*\* [^·\n]*", f"**{field}:** a definir ", METRIC)
        rc, err = write(epic_en(outcome=WHO + metric + OUT))
        check(f"métrica sem {field} bloqueia, nomeando o campo",
              rc == 2 and f"Outcome metric: falta **{field}:**" in err, err)


def test_old_pronta_keeps_old_screen():
    rc, err = write(epic(status="pronta"))
    check("Epic `pronta` sem seções de resultado segue passando", rc == 0, err)


def test_closed_requires_impact():
    rc, err = write(epic_en(status="closed"))
    check("closed sem Impact bloqueia", rc == 2 and "## Impact" in err, err)
    check("...e diz `Status: closed` na mensagem", "`Status: closed`" in err, err)
    rc, err = write(epic_en(status="closed", outcome=OUTCOME_EN + IMPACT))
    check("closed com Impact completo passa", rc == 0, err)
    no_date = IMPACT.replace("2026-12-01, pela mesma rota da Source", "<data>")
    rc, err = write(epic_en(status="closed", outcome=OUTCOME_EN + no_date))
    check("closed sem Measured on bloqueia",
          rc == 2 and "Impact: falta **Measured on:**" in err, err)
    no_value = IMPACT.replace("14 min por conta", "<valor>")
    rc, err = write(epic_en(status="closed", outcome=OUTCOME_EN + no_value))
    check("closed sem Measured value bloqueia",
          rc == 2 and "Impact: falta **Measured value:**" in err, err)
    rc, err = write(epic_en(status="closed", outcome=IMPACT, ladder=""))
    check("closed também passa pelo crivo de ready",
          rc == 2 and "## Value ladder" in err and "Who it is for" in err, err)


def test_template_status_line_with_closed_passes():
    rc, err = write(epic_en(status="draft | ready | closed", outcome=""))
    check("linha-modelo 'draft | ready | closed' não é gateada", rc == 0, err)


def test_command_teaches_outcome_and_impact():
    text = CMD.read_text()
    for h in ("## Who it is for", "## Outcome metric", "## Out of scope",
              "## Impact", "**Baseline:**", "**Target:**", "**Source:**",
              "**Measured value:**", "**Measured on:**"):
        check(f"/common:epic ensina {h}", h in text)
    check("/common:epic aceita closed", "draft | ready | closed" in text)


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\nOK")


if __name__ == "__main__":
    main()
