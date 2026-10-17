#!/usr/bin/env python3
"""O formato do `.claude/session-intent` e o leitor compartilhado em `_modos.py`.

Sem dependência externa — rode com `python3 tests/test_session_intent.py`.
Sai com código != 0 se algo falhar.

## Por que existe

A intenção da sessão (propósito, plano, passo, histórico) é um arquivo próprio
porque o `session-mode` é lido linha a linha por seis leitores que não entendem
lista, e o `write_modo` do `cepa` o reescreve com `>`. O leitor mora em
`common/hooks/_modos.py` (um só, sem pyyaml) e é tolerante: hook que quebra por
arquivo meio escrito derruba o turno. O resgate de worktree também precisa
ignorar o arquivo (`RESCUE_SKIP` em `_wtlib.py`), senão a intenção de uma sessão
que acabou seria carregada para a árvore seguinte.

O YAML de exemplo é o literal de `docs/estrategia-intencao-da-sessao.md`.
"""

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _modos as M  # noqa: E402
import _wtlib as L  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


EXEMPLO = '''proposito: "institucionalizar as quatro perguntas de aterrissagem"
para_quando: "doc de estratégia em docs/ passado pelo /common:advisors e decidido"
plano:
  - levantar o que o harness já cobre
  - escrever o doc com 2+ caminhos
  - rodar advisors e registrar as discordâncias
  - decidir
passo: 3                      # o passo EM ANDAMENTO (não o último concluído)
passo_desde: 2026-10-16T21:40:00Z
session_id: 209286bf
branch: main
aberto_em: 2026-10-16T18:30:00Z
resumo: "passo 3/4 · rodar advisors · institucionalizar as quatro perguntas"
historico:
  - em: 2026-10-16T18:30:00Z
    proposito: "criar um comando whereami"
    motivo_da_troca: "o dono reformulou: o objeto é a intenção, não o comando"
'''


def test_exemplo_do_doc():
    d = M.parse_intent(EXEMPLO)
    check("proposito", d["proposito"] == "institucionalizar as quatro perguntas de aterrissagem", d)
    check("para_quando com ':' e '/' no meio",
          d["para_quando"] == "doc de estratégia em docs/ passado pelo /common:advisors e decidido", d)
    check("plano: 4 itens", d["plano"] == [
        "levantar o que o harness já cobre",
        "escrever o doc com 2+ caminhos",
        "rodar advisors e registrar as discordâncias",
        "decidir"], d.get("plano"))
    check("passo é int 3, sem o comentário", d["passo"] == 3 and isinstance(d["passo"], int), d["passo"])
    check("passo_desde nu", d["passo_desde"] == "2026-10-16T21:40:00Z", d["passo_desde"])
    check("session_id/branch/aberto_em",
          (d["session_id"], d["branch"], d["aberto_em"]) == ("209286bf", "main", "2026-10-16T18:30:00Z"), d)
    check("resumo", d["resumo"] == "passo 3/4 · rodar advisors · institucionalizar as quatro perguntas", d["resumo"])
    check("historico: 1 entrada com 3 chaves",
          d["historico"] == [{
              "em": "2026-10-16T18:30:00Z",
              "proposito": "criar um comando whereami",
              "motivo_da_troca": "o dono reformulou: o objeto é a intenção, não o comando"}],
          d["historico"])
    check("PLANO_MAX é 6", M.PLANO_MAX == 6)


def test_arquivo_ausente_e_lido_do_disco(tmp):
    check("ausente -> None", M.read_intent(tmp) is None)
    (Path(tmp) / ".claude").mkdir()
    (Path(tmp) / M.INTENT_FILE).write_text(EXEMPLO)
    d = M.read_intent(tmp)
    check("presente -> dict", isinstance(d, dict) and d["passo"] == 3, d)


def test_tolerancia():
    lixos = ["", "\n\n", "   ", "isto nao e yaml", ":::", "plano:\n  - a\n  lixo sem hifen\n",
             "passo: tres\n", "historico:\n  - \n    em\n", "- solto\n", "\tindentado\n",
             'proposito: "aspas sem fechar\n', "plano:\n", "# so comentario\n",
             "historico:\n    em: sem item\n", "\x00\xff"]
    for t in lixos:
        try:
            r = M.parse_intent(t)
            check(f"nao levanta: {t[:25]!r}", isinstance(r, dict))
        except Exception as e:  # noqa: BLE001
            check(f"nao levanta: {t[:25]!r}", False, repr(e))
    check("parcial devolve o que leu",
          M.parse_intent("proposito: x\nplano:\n  - a\n  - b\nlixo")
          == {"proposito": "x", "plano": ["a", "b"]})
    check("passo nao numerico fica como veio", M.parse_intent("passo: tres\n")["passo"] == "tres")
    check("plano vazio vira lista vazia", M.parse_intent("plano:\n")["plano"] == [])
    check("bloco com comentario: plano",
          M.parse_intent("plano: # nota\n  - a\n  - b\n")["plano"] == ["a", "b"])
    check("bloco com comentario: historico",
          M.parse_intent("historico: # x\n  - em: t\n    motivo_da_troca: m\n")["historico"]
          == [{"em": "t", "motivo_da_troca": "m"}])
    check("chave desconhecida e mantida", M.parse_intent("futuro: 1\n")["futuro"] == "1")
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".claude").mkdir()
        (Path(tmp) / M.INTENT_FILE).write_bytes(b"proposito: \xff\xfe\n")
        check("bytes invalidos nao levantam", isinstance(M.read_intent(tmp), dict))


def test_aspas_preservam_dois_pontos_e_cerquilha():
    d = M.parse_intent('proposito: "corrigir a: parte # dois"   # nota\n'
                       'resumo: \'passo 1/2 # x\'\n'
                       'branch: feat/x # comentario\n'
                       'para_quando: "diz \\"oi\\" e vai"\n'
                       'url: http://x/a#frag\n')
    check("aspas duplas com ':' e '#'", d["proposito"] == "corrigir a: parte # dois", d["proposito"])
    check("aspas simples com '#'", d["resumo"] == "passo 1/2 # x", d["resumo"])
    check("nu: corta ' # comentario'", d["branch"] == "feat/x", d["branch"])
    check("aspa escapada", d["para_quando"] == 'diz "oi" e vai', d["para_quando"])
    check("'#' colado (sem espaco) nao e comentario", d["url"] == "http://x/a#frag", d["url"])


def test_resgate_nao_arrasta_a_intencao(tmp):
    w = Path(tmp) / "w"
    (w / ".claude").mkdir(parents=True)
    (w / ".claude" / "session-intent").write_text(EXEMPLO)
    (w / ".claude" / "outro-artefato.yaml").write_text("x: 1\n")
    doomed = L.doomed_artifacts(str(w))
    check("session-intent fora do resgate", ".claude/session-intent" not in doomed, doomed)
    check("controle: outro artefato continua sendo resgatado",
          ".claude/outro-artefato.yaml" in doomed, doomed)


def main():
    test_exemplo_do_doc()
    test_tolerancia()
    test_aspas_preservam_dois_pontos_e_cerquilha()
    with tempfile.TemporaryDirectory() as tmp:
        test_arquivo_ausente_e_lido_do_disco(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_resgate_nao_arrasta_a_intencao(tmp)
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
        return 1
    print("\nok — session-intent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
