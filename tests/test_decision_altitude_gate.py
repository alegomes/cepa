#!/usr/bin/env python3
"""Regression tests do decision-altitude-gate.

O campo `**Altitude:**` de um bloco de decisão diz QUEM revisa (o dono no
debrief, o lead, ou ninguém até pedir `--all`) — não diz sobre o que a decisão
é. Em 2026-08-19, quatro runs autônomos escreveram 57 blocos e 51 deles traziam
palavra livre em português nesse campo ("contrato", "schema", "fronteira"),
35 valores distintos. O debrief filtra por esse campo: com 89% fora do
vocabulário, ele ofereceu três decisões ao dono — todas do primeiro card —
enquanto as de maior consequência ficaram invisíveis. Nada apareceu como erro.

O que estes testes fixam:
  - valor fora do vocabulário bloqueia, e a mensagem diz o que fazer;
  - os três valores válidos passam;
  - a linha-modelo da documentação passa (senão não dá para editar o documento
    que define o vocabulário);
  - bloco sem campo Altitude NÃO bloqueia (o debrief já assume tactical, e
    bloquear ausência viraria parede na edição de bloco legado);
  - o gate lê Write, Edit e MultiEdit, e nunca bloqueia o que não consegue ver.

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


def escrita(content, tool="Write"):
    campo = {"Write": "content", "Edit": "new_string"}.get(tool, "content")
    return {"tool_name": tool, "tool_input": {"file_path": "/tmp/RESULT.md", campo: content}}


BLOCO = "### Decision: cortar a cadeia de hash\n\n**Altitude:** {}\n\n**Chosen:** A\n"


def test_palavra_livre_bloqueia():
    rc, err = run(escrita(BLOCO.format("garantia")))
    check("palavra livre no campo Altitude bloqueia", rc == 2, err)
    check("a mensagem mostra o valor recusado", '"garantia"' in err, err)
    check("a mensagem lista os três valores válidos",
          all(v in err for v in ("strategic", "tactical", "implementation")), err)
    check("a mensagem diz onde o assunto deve ir",
          "título" in err and "### Decision:" in err, err)


def test_vocabulario_passa():
    for v in ("strategic", "tactical", "implementation"):
        rc, err = run(escrita(BLOCO.format(v)))
        check(f"'{v}' passa", rc == 0, err)
    rc, _ = run(escrita(BLOCO.format("**Tactical**")))
    check("valor com marcação e maiúscula passa", rc == 0)


def test_linha_modelo_da_documentacao_passa():
    rc, err = run(escrita("**Altitude:** strategic | tactical | implementation\n"))
    check("a enumeração que ensina o vocabulário passa", rc == 0, err)
    rc, err = run(escrita("**Altitude:** <strategic|tactical|implementation>\n"))
    check("o marcador de preencher passa", rc == 0, err)


def test_campo_ausente_nao_bloqueia():
    rc, err = run(escrita("### Decision: x\n\n**Chosen:** Option A\n"))
    check("bloco sem campo Altitude não bloqueia", rc == 0, err)


def test_edit_e_multiedit():
    rc, _ = run(escrita(BLOCO.format("fronteira"), tool="Edit"))
    check("Edit também é lido", rc == 2)
    rc, _ = run({"tool_name": "MultiEdit", "tool_input": {
        "file_path": "/tmp/RESULT.md",
        "edits": [{"new_string": "nada aqui"},
                  {"new_string": BLOCO.format("retenção")}]}})
    check("MultiEdit também é lido", rc == 2)


def test_nunca_bloqueia_o_que_nao_ve():
    rc, _ = run({"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.md"}})
    check("sem conteúdo visível, libera", rc == 0)
    rc, _ = run({"tool_name": "Bash", "tool_input": {"command": "echo Altitude: contrato"}})
    check("ferramenta fora do escopo, libera", rc == 0)
    p = subprocess.run([sys.executable, str(HOOK)], input="isto não é json",
                       capture_output=True, text=True)
    check("payload ilegível, libera", p.returncode == 0)


def test_nao_bloqueia_os_documentos_que_definem_o_campo():
    """Gate que impede consertar a própria definição ensina a desligar o gate.

    Os dois documentos citam o campo em prosa ("**Altitude field** classifies
    who reviews...") e trazem a linha-modelo com comentário ao lado. Ambos
    passaram a ser bloqueados na primeira versão do gate.
    """
    for rel in ("common/skills/autonomous-mode/SKILL.md", "common/commands/debrief.md"):
        conteudo = (REPO / rel).read_text(encoding="utf-8")
        rc, err = run(escrita(conteudo))
        check(f"{rel.split('/')[-1]} passa pelo gate", rc == 0, err[:300])

    rc, err = run(escrita("**Altitude field** classifies who reviews the decision\n"))
    check("prosa que fala do campo, sem dois pontos, não é valor",
          rc == 0, err)
    rc, err = run(escrita("**Altitude:** <strategic|tactical|implementation>   ← escolha uma\n"))
    check("linha-modelo com comentário ao lado passa", rc == 0, err)


def test_so_vale_dentro_do_bloco_de_decisao():
    """`Altitude` fora de bloco de decisão é OUTRO campo, com outro vocabulário.

    Em 2026-08-22 o completion-auditor tentou gravar
    `.claude/acceptance/WEGO-2085.yaml` com `altitude: http` — ali o campo diz em
    que superfície o critério é observável (http/cli/ui/event/domain/application),
    nada a ver com quem revisa a decisão. O gate barrou e o agente contornou
    renomeando o campo na marra, o que faz cada sessão inventar um nome e os
    artefatos de aceite deixarem de ser comparáveis.
    """
    rc, err = run(escrita("### Decision: mover o gate\n\n**Altitude:** operacional\n"))
    check("dentro do bloco, palavra fora do vocabulário bloqueia", rc == 2, err)

    yaml = ("key: WEGO-2085\ncriteria:\n  - id: AC1\n    altitude: http\n"
            "    surface: POST /acessos\n")
    rc, err = run({"tool_name": "Write", "tool_input": {
        "file_path": "/tmp/WEGO-2085.yaml", "content": yaml}})
    check("yaml de aceite sem bloco de decisão passa", rc == 0, err)

    misto = ("### Decision: cortar a cadeia\n\n**Altitude:** tactical\n\n"
             "### Critérios de aceite\n\ncriteria:\n  - altitude: http\n")
    rc, err = run(escrita(misto))
    check("altitude fora do bloco, no mesmo arquivo, passa", rc == 0, err)


def test_edit_sem_cabecalho_usa_o_arquivo_de_destino():
    """Um Edit pode trazer só a linha do campo; quem diz se é bloco é o arquivo.

    Sem isto, corrigir a altitude de um bloco existente por Edit escaparia do
    gate — que é exatamente o momento em que o autor está ali para consertar.
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
    test_palavra_livre_bloqueia()
    test_vocabulario_passa()
    test_linha_modelo_da_documentacao_passa()
    test_campo_ausente_nao_bloqueia()
    test_edit_e_multiedit()
    test_nunca_bloqueia_o_que_nao_ve()
    test_nao_bloqueia_os_documentos_que_definem_o_campo()
    test_so_vale_dentro_do_bloco_de_decisao()
    test_edit_sem_cabecalho_usa_o_arquivo_de_destino()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
