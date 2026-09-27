#!/usr/bin/env python3
"""Regression tests do spec-readiness-gate.

O `/common:spec` conduz um interrogatório até a especificação ficar rica o
bastante para construir. O modo de falha que este gate existe para impedir não é
o interrogatório ficar curto — é ele TERMINAR por cansaço: o agente decide que
já está bom, escreve `Status: pronta-para-construir`, e entrega critérios que são
frases de intenção ("o sistema deve validar o cadastro"), sem superfície
observável onde alguém possa provar que aconteceu. Isso não falha ali; falha na
construção, semanas depois, quando outra pessoa interpreta o critério de outro
jeito.

O que estes testes fixam:
  - `Status: rascunho` NUNCA bloqueia, nem com o documento todo furado (o
    interrogatório precisa poder escrever enquanto corre);
  - declarada pronta e completa, passa;
  - critério sem Superfície, sem Teste vermelho, ou com Superfície fora do
    vocabulário, bloqueia — e a mensagem nomeia QUAL critério;
  - pronta com zero critérios bloqueia (o caso mais silencioso);
  - pergunta em aberto (`- [ ]`) sobrando bloqueia;
  - a linha-modelo do formato passa, senão não dá para editar o documento que
    define o formato;
  - o gate lê Write, Edit e MultiEdit, e nunca bloqueia o que não consegue ver.

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


CRITERIO_OK = """### CS-1: POST /api/v1/assinaturas sem responsável responde 422

**Superfície:** http
**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — hoje não existe.
"""

PRONTA_OK = f"""# Especificação: assinatura de menor

**Status:** pronta-para-construir

## Critérios de sucesso

{CRITERIO_OK}
"""


def test_rascunho_nunca_bloqueia():
    doc = """# Especificação: qualquer coisa

**Status:** rascunho

## Perguntas em aberto
- [ ] quem pode assinar por um menor?

## Critérios de sucesso

### CS-1: o sistema deve validar o cadastro
"""
    rc, _ = write(doc)
    check("rascunho furado não bloqueia", rc == 0, f"rc={rc}")


def test_pronta_completa_passa():
    rc, err = write(PRONTA_OK)
    check("pronta e completa passa", rc == 0, f"rc={rc} err={err[:200]}")


def test_falta_superficie():
    doc = PRONTA_OK.replace("**Superfície:** http\n", "")
    rc, err = write(doc)
    check("falta Superfície bloqueia", rc == 2, f"rc={rc}")
    check("mensagem nomeia o critério", "CS-1" in err, err[:200])


def test_falta_teste_vermelho():
    doc = "\n".join(l for l in PRONTA_OK.splitlines()
                    if not l.startswith("**Teste vermelho:**"))
    rc, err = write(doc)
    check("falta Teste vermelho bloqueia", rc == 2, f"rc={rc}")
    check("mensagem cita Teste vermelho", "Teste vermelho" in err, err[:200])


def test_superficie_fora_do_vocabulario():
    doc = PRONTA_OK.replace("**Superfície:** http", "**Superfície:** banco de dados")
    rc, err = write(doc)
    check("Superfície inventada bloqueia", rc == 2, f"rc={rc}")
    check("mensagem mostra o valor recusado", "banco de dados" in err, err[:200])


def test_todas_as_superficies_do_vocabulario_passam():
    for sup in ("http", "cli", "ui", "event", "domain", "application"):
        doc = PRONTA_OK.replace("**Superfície:** http", f"**Superfície:** {sup}")
        rc, err = write(doc)
        check(f"superfície {sup} passa", rc == 0, f"rc={rc} err={err[:120]}")


def test_pronta_sem_criterio_nenhum():
    doc = """# Especificação: vazia

**Status:** pronta-para-construir

## Problema
Alguma prosa convincente e nenhum critério.
"""
    rc, err = write(doc)
    check("pronta sem critério bloqueia", rc == 2, f"rc={rc}")
    check("mensagem explica o vazio", "nenhum critério" in err, err[:200])


def test_pergunta_em_aberto_sobrando():
    doc = PRONTA_OK.replace(
        "## Critérios de sucesso",
        "## Perguntas em aberto\n- [ ] menor emancipado conta como menor?\n\n## Critérios de sucesso",
    )
    rc, err = write(doc)
    check("pergunta em aberto bloqueia", rc == 2, f"rc={rc}")
    check("mensagem cita a pergunta", "emancipado" in err, err[:300])


def test_pergunta_respondida_nao_bloqueia():
    doc = PRONTA_OK.replace(
        "## Critérios de sucesso",
        "## Perguntas em aberto\n- [x] menor emancipado conta como menor? Não.\n\n## Critérios de sucesso",
    )
    rc, err = write(doc)
    check("pergunta marcada como respondida passa", rc == 0, f"rc={rc} err={err[:200]}")


def test_linha_modelo_do_formato_passa():
    doc = """# Formato da especificação

**Status:** rascunho | pronta-para-construir

## Critérios de sucesso

### CS-<n>: <o critério em termos observáveis>

**Superfície:** <http|cli|ui|event|domain|application>
**Teste vermelho:** <a frase do teste que hoje falharia>
"""
    rc, err = write(doc)
    check("documento que ensina o formato passa", rc == 0, f"rc={rc} err={err[:200]}")


def test_edit_e_multiedit():
    doc = PRONTA_OK.replace("**Superfície:** http\n", "")
    rc, _ = write(doc, tool="Edit")
    check("Edit é lido", rc == 2, f"rc={rc}")

    rc, _ = run({"tool_name": "MultiEdit",
                 "tool_input": {"edits": [{"new_string": doc}]}})
    check("MultiEdit é lido", rc == 2, f"rc={rc}")


def com_arquivo_temporario(conteudo):
    """Escreve `conteudo` num arquivo temporário e devolve o Path; quem chama
    apaga depois."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False,
                                     encoding="utf-8")
    f.write(conteudo)
    f.close()
    return Path(f.name)


def test_edit_com_file_path_le_o_arquivo_resultante():
    # (a) Status rascunho -> pronta, critério já completo no arquivo: hoje
    # bloqueava (falso bloqueio, o fragmento só tem o Status). Deve liberar.
    doc_rascunho = PRONTA_OK.replace("**Status:** pronta-para-construir",
                                     "**Status:** rascunho")
    caminho = com_arquivo_temporario(doc_rascunho)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(caminho),
                "old_string": "**Status:** rascunho",
                "new_string": "**Status:** pronta-para-construir",
            },
        })
        check("Edit que só muda o Status vê o critério completo e libera",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        caminho.unlink(missing_ok=True)

    # (b) já pronta no arquivo, Edit adiciona pergunta em aberto no fragmento
    # (que não tem Status): hoje passava (falso passe). Deve bloquear.
    caminho = com_arquivo_temporario(PRONTA_OK)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(caminho),
                "old_string": "## Critérios de sucesso",
                "new_string": "## Perguntas em aberto\n- [ ] pergunta nova\n\n## Critérios de sucesso",
            },
        })
        check("Edit que reabre pergunta numa spec pronta bloqueia",
              rc == 2, f"rc={rc}")
        check("mensagem cita a pergunta reaberta", "pergunta nova" in err, err[:300])
    finally:
        caminho.unlink(missing_ok=True)

    # (c) já pronta no arquivo, Edit remove o Teste vermelho no fragmento (que
    # não tem Status nem CS): hoje passava. Deve bloquear.
    caminho = com_arquivo_temporario(PRONTA_OK)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(caminho),
                "old_string": "**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — hoje não existe.\n",
                "new_string": "",
            },
        })
        check("Edit que remove Teste vermelho numa spec pronta bloqueia",
              rc == 2, f"rc={rc}")
        check("mensagem cita Teste vermelho", "Teste vermelho" in err, err[:300])
    finally:
        caminho.unlink(missing_ok=True)


def test_multiedit_com_file_path_aplica_em_sequencia():
    # A segunda edição só bate DEPOIS que a primeira foi aplicada (o old_string
    # da segunda não existe no arquivo original). O veredito só pode estar
    # certo se o gate aplicar as duas em sequência sobre o mesmo texto.
    doc = PRONTA_OK.replace("**Status:** pronta-para-construir",
                            "**Status:** RASCUNHO_TEMPORARIO")
    caminho = com_arquivo_temporario(doc)
    try:
        rc, err = run({
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(caminho),
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
        caminho.unlink(missing_ok=True)


DUAS_SUPERFICIES_OK = """# Especificação: duas superfícies
**Status:** pronta-para-construir
## Critérios de sucesso
### CS-1: POST /api/v1/assinaturas sem responsável responde 422
**Superfície:** http
**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — hoje não existe.
### CS-2: GET /api/v1/assinaturas retorna lista
**Superfície:** http
**Teste vermelho:** AssinaturaResourceIT#get_lista_retorna200 — hoje não existe.
"""


def test_multiedit_replace_all_troca_TODAS_as_ocorrencias():
    # old_string ("**Superfície:** http") aparece nos DOIS blocos, e o
    # veredito só fica certo se replace_all trocar as duas. Se a
    # implementação "esquecesse" o replace_all e caísse na checagem de
    # unicidade (que existe para o Edit sem replace_all), old_string bateria
    # 2x sem replace_all pedido, e o código teria que liberar (rc 0) em vez
    # de aplicar a troca. Aqui a troca É esperada, então o rc correto é 2
    # (as duas Superfícies viram inválidas) -- bem diferente do rc 0 que a
    # implementação quebrada devolveria.
    caminho = com_arquivo_temporario(DUAS_SUPERFICIES_OK)
    try:
        rc, err = run({
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(caminho),
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
        caminho.unlink(missing_ok=True)


DUAS_CS_UMA_INVALIDA = """# Especificação: duas superfícies
**Status:** pronta-para-construir
## Critérios de sucesso
### CS-1: POST /api/v1/assinaturas sem responsável responde 422
**Superfície:** http
**Teste vermelho:** AssinaturaResourceIT#post_menorSemResponsavel_retorna422 — hoje não existe.
### CS-2: GET /api/v1/assinaturas retorna lista
**Superfície:** banco de dados
**Teste vermelho:** AssinaturaResourceIT#get_lista_retorna200 — hoje não existe.
"""


def test_multiedit_acumula_sobre_o_resultado_da_edicao_anterior():
    # edit1 conserta a Superfície inválida do CS-2. edit2 mexe numa região que
    # edit1 NÃO tocou (o Teste vermelho do CS-1) -- o old_string de edit2
    # existe tanto no arquivo ORIGINAL quanto no resultado de edit1 (porque
    # edit1 não passou perto dali). Uma implementação que aplicasse cada
    # edição sobre o texto ORIGINAL (em vez de acumular sobre o resultado da
    # edição anterior) casaria os dois old_string igualmente -- só que o
    # resultado final dela DESCARTARIA o conserto de edit1: CS-2 continuaria
    # com "banco de dados" e o rc ficaria 2, contra o rc 0 da implementação
    # correta (que preserva os dois consertos).
    caminho = com_arquivo_temporario(DUAS_CS_UMA_INVALIDA)
    try:
        rc, err = run({
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(caminho),
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
        caminho.unlink(missing_ok=True)


def test_multiedit_replace_all():
    doc = PRONTA_OK.replace("**Status:** pronta-para-construir",
                            "**Status:** rascunho")
    caminho = com_arquivo_temporario(doc)
    try:
        rc, err = run({
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(caminho),
                "edits": [
                    {"old_string": "rascunho", "new_string": "pronta-para-construir",
                     "replace_all": True},
                ],
            },
        })
        check("replace_all é respeitado e a spec completa libera",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        caminho.unlink(missing_ok=True)


def test_edit_com_file_path_inexistente_libera():
    rc, err = run({
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/tmp/nao-existe-spec-readiness-gate-teste.md",
            "old_string": "**Status:** rascunho",
            "new_string": "**Status:** pronta-para-construir",
        },
    })
    check("file_path inexistente libera", rc == 0, f"rc={rc} err={err[:200]}")


def test_edit_com_old_string_duplicado_sem_replace_all_libera():
    # old_string bate duas vezes e replace_all não foi pedido: a ferramenta
    # Edit real exige unicidade e falha sozinha, então o gate libera em vez de
    # trocar "a primeira" ocorrência por conta própria.
    doc = PRONTA_OK.replace(
        "**Superfície:** http",
        "**Superfície:** http\n**Superfície:** http",
    )
    caminho = com_arquivo_temporario(doc)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(caminho),
                "old_string": "**Superfície:** http",
                "new_string": "**Superfície:** banco de dados",
            },
        })
        check("old_string duplicado sem replace_all libera",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        caminho.unlink(missing_ok=True)


def test_edit_com_old_string_que_nao_bate_libera():
    caminho = com_arquivo_temporario(PRONTA_OK)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(caminho),
                "old_string": "isto não existe no arquivo",
                "new_string": "qualquer coisa",
            },
        })
        check("old_string que não bate libera", rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        caminho.unlink(missing_ok=True)


def test_edit_com_old_string_que_nao_bate_em_spec_invalida_libera():
    # A spec no disco JÁ é inválida (pronta sem Superfície no CS-1) --
    # o teste anterior usa uma spec VÁLIDA como base, e por isso não pegaria
    # uma implementação que, ao não achar old_string, devolvesse o texto
    # ORIGINAL sem sinalizar erro (em vez de liberar): com uma base válida os
    # dois caminhos dão rc 0 igual. Aqui a base é inválida, então só uma
    # implementação que realmente libera (em vez de julgar o texto original
    # sem edição nenhuma aplicada) devolve rc 0; uma que "aplicasse mesmo
    # assim" o texto inalterado devolveria rc 2 (a spec inválida seria julgada).
    doc = PRONTA_OK.replace("**Superfície:** http\n", "")
    caminho = com_arquivo_temporario(doc)
    try:
        rc, err = run({
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(caminho),
                "old_string": "isto não existe no arquivo",
                "new_string": "qualquer coisa",
            },
        })
        check("old_string que não bate numa spec inválida libera",
              rc == 0, f"rc={rc} err={err[:200]}")
    finally:
        caminho.unlink(missing_ok=True)



def test_nunca_bloqueia_o_que_nao_ve():
    rc, _ = run({"tool_name": "Bash", "tool_input": {"command": "echo pronta-para-construir"}})
    check("ferramenta fora do escopo passa", rc == 0, f"rc={rc}")

    rc, _ = run({"tool_name": "Write", "tool_input": {}})
    check("Write sem conteúdo visível passa", rc == 0, f"rc={rc}")

    p = subprocess.run([sys.executable, str(HOOK)], input="{ not json",
                       capture_output=True, text=True)
    check("payload ilegível libera", p.returncode == 0, f"rc={p.returncode}")

    rc, _ = write("# Um markdown qualquer sem campo Status nenhum.")
    check("documento sem Status passa", rc == 0, f"rc={rc}")


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
