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
