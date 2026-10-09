#!/usr/bin/env python3
"""Regression tests do crivo de Epic no spec-readiness-gate, e do /common:epic (CS-5).

O `/common:epic` entrevista o dono no estilo "grill me" e escreve
`docs/epics/<nome>.md`. Ele fecha por roteiro, não por critério: o documento só
pode se declarar `Status: pronta` quando cada ciclo da escada tem um roteiro de
demonstração com efeito observável em tela e em backend, a lista de invariantes
não está vazia e a seção "Decidido sem perguntar" existe. Sem o crivo, o Epic
fecha por cansaço igual à especificação fecharia, e o `/common:plan --from-epic`
(CS-6) deriva uma fila de um ciclo que ninguém sabe como demonstrar.

O que estes testes fixam:
  - Epic em `rascunho` nunca bloqueia, nem todo furado;
  - Epic `pronta` completo passa (Write e Edit que só troca o Status);
  - Epic `pronta` bloqueia, nomeando o ciclo ou a seção, quando falta: roteiro,
    efeito em tela, efeito em backend, linha de ciclo, invariante, a seção
    "Decidido sem perguntar", ou sobra pergunta em aberto;
  - quem é Epic: o caminho `docs/epics/*.md` ou o título `# Epic:`;
  - especificação que não é Epic continua com a régua de antes: `Status: pronta`
    nela não é gateado (só `pronta-para-construir`);
  - o modo descoberta pode escrever `docs/epics/**`;
  - o comando existe, é conversacional (o session-routine-guard o barra), está
    no catálogo, e o contrato do grill-me está escrito nele.

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
ESCRITA = REPO / "common" / "hooks" / "modo-escrita-gate.py"
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


ESCADA_OK = """## Escada de valor

| Ciclo | Roteiro de demonstração | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
| 1. Ler | O operador carrega o PDF do contrato e vê as 3 respostas. | a tela de upload mostra as 3 respostas com a cláusula citada | `GET /api/v1/contratos/{id}/respostas` devolve as 3 com o nonce do upload | upload → extrator → tela | próxima quinzena |
| 2. Regrar | O operador aprova uma regra e a próxima conta já sai glosada. | a conta aparece com a glosa e o motivo | a tabela `glosa` tem a linha com o id da regra | regra → motor → conta | depois do ciclo 1 |
"""

INVARIANTES_OK = """## Invariantes (nunca regridem)

- A conta já faturada nunca muda de valor.
"""

DECIDIDO_OK = """## Decidido sem perguntar (vete aqui)

- O PDF fica no bucket que já existe.
"""

PERGUNTAS_OK = """## Perguntas em aberto

- [x] Quem aprova a regra? O auditor médico, na tela de regras.
"""


def epic(status="pronta", escada=ESCADA_OK, invariantes=INVARIANTES_OK,
         decidido=DECIDIDO_OK, perguntas=PERGUNTAS_OK, titulo="# Epic: Contratos"):
    return f"""{titulo}

**Status:** {status} · **Aberto em:** 2026-10-08

## Intenção

O operador deixa de ler contrato à mão.

{invariantes}
{escada}
{decidido}
{perguntas}"""


def test_rascunho_nunca_bloqueia():
    furado = epic(status="rascunho", escada="## Escada de valor\n", invariantes="",
                  decidido="", perguntas="## Perguntas em aberto\n- [ ] tudo\n")
    rc, err = write(furado)
    check("Epic rascunho todo furado passa", rc == 0, err)


def test_pronta_completo_passa():
    rc, err = write(epic())
    check("Epic pronta completo passa", rc == 0, err)
    rc, err = write(epic(titulo="# Epic: x"), file_path="/tmp/x/docs/epics/x.md")
    check("Epic pronta completo passa com file_path em docs/epics", rc == 0, err)


def test_pronta_sem_tela_bloqueia():
    escada = ESCADA_OK.replace(
        "| a conta aparece com a glosa e o motivo |", "|  |")
    rc, err = write(epic(escada=escada))
    check("ciclo sem efeito em tela bloqueia", rc == 2, err)
    check("a mensagem nomeia o ciclo 2 e a tela",
          "2. Regrar" in err and "tela" in err.lower(), err)


def test_pronta_sem_backend_bloqueia():
    escada = ESCADA_OK.replace(
        "| `GET /api/v1/contratos/{id}/respostas` devolve as 3 com o nonce do upload |",
        "| a definir |")
    rc, err = write(epic(escada=escada))
    check("ciclo com backend placeholder bloqueia", rc == 2, err)
    check("a mensagem nomeia o ciclo 1 e o backend",
          "1. Ler" in err and "backend" in err.lower(), err)


def test_pronta_sem_roteiro_bloqueia():
    escada = ESCADA_OK.replace(
        "| O operador carrega o PDF do contrato e vê as 3 respostas. |", "| - |")
    rc, err = write(epic(escada=escada))
    check("ciclo sem roteiro bloqueia", rc == 2, err)
    check("a mensagem nomeia o roteiro", "roteiro" in err.lower(), err)


def test_pronta_sem_colunas_de_efeito_bloqueia():
    # O formato antigo, escrito à mão: só a coluna de roteiro. Pronta assim é o
    # roteiro sem efeito observável, que é o que o crivo existe para recusar.
    escada = """## Escada de valor

| Ciclo | Roteiro de demonstração | O que atravessa | Quando |
|---|---|---|---|
| 1. Ler | O operador vê as 3 respostas. | upload → tela | já |
"""
    rc, err = write(epic(escada=escada))
    check("escada sem colunas de tela e backend bloqueia", rc == 2, err)
    check("a mensagem diz as colunas que faltam",
          "Efeito em tela" in err and "Efeito em backend" in err, err)


def test_pronta_sem_ciclo_bloqueia():
    escada = """## Escada de valor

| Ciclo | Roteiro de demonstração | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
"""
    rc, err = write(epic(escada=escada))
    check("escada com zero ciclos bloqueia", rc == 2, err)
    rc, err = write(epic(escada=""))
    check("sem seção Escada de valor bloqueia", rc == 2, err)
    check("a mensagem nomeia a escada", "escada" in err.lower(), err)


def test_pronta_sem_invariante_bloqueia():
    rc, err = write(epic(invariantes="## Invariantes (nunca regridem)\n\n"))
    check("Invariantes vazia bloqueia", rc == 2, err)
    check("a mensagem nomeia os invariantes", "invariante" in err.lower(), err)
    rc, err = write(epic(invariantes="## Invariantes\n\n- <invariante>\n"))
    check("Invariantes só com placeholder bloqueia", rc == 2, err)
    rc, err = write(epic(invariantes=""))
    check("sem seção Invariantes bloqueia", rc == 2, err)


def test_invariante_em_outra_secao_nao_conta():
    # Um item de lista depois da seção Invariantes (na Intenção não; na seção
    # seguinte) não pode fazer a lista vazia passar.
    inv = "## Invariantes (nunca regridem)\n\n## Outra coisa\n\n- item fora\n"
    rc, err = write(epic(invariantes=inv))
    check("item de lista de outra seção não conta como invariante", rc == 2, err)


def test_pronta_sem_decidido_bloqueia():
    rc, err = write(epic(decidido=""))
    check("sem seção Decidido sem perguntar bloqueia", rc == 2, err)
    check("a mensagem nomeia a seção", "Decidido sem perguntar" in err, err)


def test_pronta_com_pergunta_aberta_bloqueia():
    rc, err = write(epic(perguntas="## Perguntas em aberto\n\n- [ ] Quem aprova a regra?\n"))
    check("pergunta em aberto bloqueia Epic pronta", rc == 2, err)
    check("a mensagem cita a pergunta", "Quem aprova a regra" in err, err)


def test_epic_por_caminho_sem_titulo():
    doc = epic(titulo="# Contratos e regras", decidido="")
    rc, err = write(doc)
    check("sem título Epic e sem caminho, 'pronta' não é gateado", rc == 0, err)
    rc, err = write(doc, file_path="/tmp/r/docs/epics/contratos.md")
    check("em docs/epics/, 'pronta' é gateado mesmo sem título Epic", rc == 2, err)


def test_edit_que_so_troca_status_e_julgado_inteiro():
    with tempfile.TemporaryDirectory() as d:
        alvo = Path(d) / "docs" / "epics" / "contratos.md"
        alvo.parent.mkdir(parents=True)
        alvo.write_text(epic(status="rascunho", invariantes=""))
        rc, err = run({"tool_name": "Edit", "tool_input": {
            "file_path": str(alvo),
            "old_string": "**Status:** rascunho",
            "new_string": "**Status:** pronta",
        }})
        check("Edit que só troca o Status olha o arquivo inteiro", rc == 2, err)
        alvo.write_text(epic(status="rascunho"))
        rc, err = run({"tool_name": "Edit", "tool_input": {
            "file_path": str(alvo),
            "old_string": "**Status:** rascunho",
            "new_string": "**Status:** pronta",
        }})
        check("Edit que só troca o Status de um Epic completo passa", rc == 0, err)


def test_spec_nao_epic_mantem_regua():
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


def test_modelo_do_formato_passa():
    # O próprio comando ensina o formato com a linha-modelo do Status.
    doc = epic(status="rascunho | pronta", escada="", invariantes="", decidido="")
    rc, err = write(doc)
    check("linha-modelo 'rascunho | pronta' não é gateada", rc == 0, err)


def test_descoberta_escreve_docs_epics():
    with tempfile.TemporaryDirectory() as d:
        raiz = Path(d).resolve()
        subprocess.run(["git", "init", "-q", str(raiz)], check=True)
        (raiz / ".claude").mkdir()
        (raiz / ".claude" / "session-mode").write_text("modo: descoberta\n")
        env = dict(os.environ)
        env.pop("CEPA_MODO", None)
        payload = {
            "tool_name": "Write",
            "cwd": str(raiz),
            "tool_input": {"file_path": str(raiz / "docs" / "epics" / "c.md"),
                           "content": "# Epic: c\n"},
        }
        p = subprocess.run([sys.executable, str(ESCRITA)], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, cwd=str(raiz))
        check("modo descoberta pode escrever docs/epics/<nome>.md",
              p.returncode == 0, p.stderr)
        payload["tool_input"]["file_path"] = str(raiz / "common" / "x.py")
        p = subprocess.run([sys.executable, str(ESCRITA)], input=json.dumps(payload),
                           capture_output=True, text=True, env=env, cwd=str(raiz))
        check("controle: modo descoberta segue barrando código",
              p.returncode == 2, p.stderr)


def test_comando_existe_e_e_grill_me():
    check("common/commands/epic.md existe", CMD.exists())
    if not CMD.exists():
        return
    texto = CMD.read_text()
    fm = texto.split("---", 2)[1] if texto.startswith("---") else ""
    check("frontmatter declara interaction: conversational",
          re.search(r"^interaction:\s*conversational\s*$", fm, re.M) is not None)
    check("argumento é <nome>", re.search(r"^argument-hint:.*<nome>", fm, re.M) is not None)
    check("escreve docs/epics/<nome>.md", "docs/epics/<nome>.md" in texto)
    check("uma pergunta por turno", "uma pergunta por turno" in texto.lower())
    check("proíbe menu / AskUserQuestion",
          "AskUserQuestion" in texto and "lista de opções" in texto.lower())
    check("um único ? por turno, sem alternativas enumeradas na frase",
          "único `?` do turno" in texto and "menu escrito em linha" in texto)
    check("desafio único com as duas perguntas-modelo",
          "quem vê isso e onde?" in texto and "o que quebra se faltar?" in texto)
    check("grava no mesmo turno", "mesmo turno" in texto)
    check("proposta antes da pergunta, turno termina nela",
          "**antes** da pergunta" in texto)
    # A transcrição de 2026-10-08 mostrou o desafio saindo como relatório
    # (Pra você + pergunta numerada), puxado pela regra global de plain-report.
    check("turno de entrevista não usa plain-report",
          "não relatório de trabalho" in texto and "plain-report" in texto)
    check("carrega guided-interrogation", "guided-interrogation" in texto)
    check("fecha pelo spec-readiness-gate", "spec-readiness-gate" in texto)
    check("formato traz as colunas de efeito",
          "Efeito em tela" in texto and "Efeito em backend" in texto)


def test_comando_no_catalogo():
    cat = (REPO / "docs" / "commands.md").read_text()
    check("/common:epic tem linha na tabela do catálogo",
          re.search(r"^\|\s*`/common:epic`\s*\|", cat, re.M) is not None)


def test_session_barra_epic():
    guard = REPO / "common" / "hooks" / "session-routine-guard.py"
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(REPO / "common")
    env["HOME"] = tempfile.mkdtemp()  # sem installed_plugins.json: lê o repo
    p = subprocess.run([sys.executable, str(guard)],
                       input=json.dumps({"prompt": "/common:session common:epic contratos"}),
                       capture_output=True, text=True, env=env)
    check("/common:session common:epic é barrado (rotina conversacional)",
          p.returncode == 2, p.stderr)


LINT = REPO / "common" / "hooks" / "report-style-lint.py"

# Fala de entrevista longa o bastante (≥ 80 palavras) para o lint medir, sem
# nenhum bloco do plain-report: é exatamente o turno que o /common:epic produz.
FALA = ("Gravei sua resposta na Intenção do documento. Se o sistema disser que "
        "o procedimento tem cobertura com carência de noventa dias e estiver "
        "errado, ou não achar a cláusula, o que quebra para o operador? Minha "
        "proposta: a resposta sempre traz o trecho do contrato e a página de "
        "onde saiu, e quando o sistema não tem certeza ele diz que não "
        "encontrou em vez de chutar, porque assim o operador confere em "
        "segundos e só liga para o setor de contratos nos casos duvidosos que "
        "sobram depois disso. Corrija se não for isso, e diga o que quebraria "
        "para ele se faltar?")


def _lint_stop(alvo, fala=FALA, extra=None):
    d = Path(tempfile.mkdtemp(prefix="cs5-lint-"))
    rows = [
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "text", "text": "quase isso, a pergunta é sempre a mesma"}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": alvo}}]}},
    ]
    if extra:
        rows.append({"type": "assistant", "message": {"role": "assistant",
                                                      "content": [extra]}})
    rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": fala}]}})
    t = d / "t.jsonl"
    t.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    env = dict(os.environ, CEPA_REPORT_STYLE_DIR=str(d / "st"),
               CEPA_TELEMETRY_DIR=str(d / "tel"))
    p = subprocess.run([sys.executable, str(LINT)], input=json.dumps({
        "hook_event_name": "Stop", "session_id": "s", "transcript_path": str(t),
        "cwd": str(d)}), capture_output=True, text=True, env=env)
    return '"block"' in p.stdout


def test_lint_poupa_turno_de_entrevista():
    # A transcrição de 2026-10-08 (docs/proof/CS-5-transcricao.md): o lint
    # mandou reescrever o desafio como relatório, com pergunta numerada — menu
    # com outra roupa, e é o que o grill me proíbe.
    check("lint não bloqueia turno que só gravou docs/epics e termina em pergunta",
          not _lint_stop("/r/docs/epics/contratos.md"))
    check("lint não bloqueia o mesmo turno do /common:spec (docs/spec)",
          not _lint_stop("/r/docs/spec/x.md"))
    check("controle: mesma fala editando código é medida e bloqueada",
          _lint_stop("/r/common/hooks/x.py"))
    check("lint poupa a pergunta seguida da proposta no mesmo parágrafo",
          not _lint_stop("/r/docs/epics/c.md",
                         fala=FALA.rstrip("?") + ". Corrija."))
    check("controle: gravou docs/epics mas o último parágrafo não pergunta",
          _lint_stop("/r/docs/epics/c.md",
                     fala=FALA + "\n\nFechei o Epic e gravei o Status como pronta."))
    commit = {"type": "tool_use", "name": "Bash",
              "input": {"command": "git commit -m x"}}
    check("controle: turno de entrevista que também commitou é medido",
          _lint_stop("/r/docs/epics/c.md", extra=commit))
    outro = {"type": "tool_use", "name": "Write",
             "input": {"file_path": "/r/docs/epics/sub/c.md"}}
    check("controle: escrita fora de docs/epics/<nome>.md é medida",
          _lint_stop("/r/docs/epics/c.md", extra=outro))


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
