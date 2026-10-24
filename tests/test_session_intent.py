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
`EXEMPLO_ANTIGO` é o mesmo arquivo com as chaves em pt-BR (formato anterior ao
item `interface-in-english`): o leitor ainda o entende e devolve as chaves novas.
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


EXEMPLO = '''purpose: "institucionalizar as quatro perguntas de aterrissagem"
by_when: "doc de estratégia em docs/ passado pelo /common:advisors e decidido"
plan:
  - levantar o que o harness já cobre
  - escrever o doc com 2+ caminhos
  - rodar advisors e registrar as discordâncias
  - decidir
step: 3                      # o passo EM ANDAMENTO (não o último concluído)
step_since: 2026-10-16T21:40:00Z
session_id: 209286bf
branch: main
opened_at: 2026-10-16T18:30:00Z
summary: "passo 3/4 · rodar advisors · institucionalizar as quatro perguntas"
history:
  - at: 2026-10-16T18:30:00Z
    purpose: "criar um comando whereami"
    change_reason: "o dono reformulou: o objeto é a intenção, não o comando"
'''
EXEMPLO_ANTIGO = '''proposito: "institucionalizar as quatro perguntas de aterrissagem"
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
    check("purpose", d["purpose"] == "institucionalizar as quatro perguntas de aterrissagem", d)
    check("by_when com ':' e '/' no meio",
          d["by_when"] == "doc de estratégia em docs/ passado pelo /common:advisors e decidido", d)
    check("plan: 4 itens", d["plan"] == [
        "levantar o que o harness já cobre",
        "escrever o doc com 2+ caminhos",
        "rodar advisors e registrar as discordâncias",
        "decidir"], d.get("plan"))
    check("step é int 3, sem o comentário", d["step"] == 3 and isinstance(d["step"], int), d["step"])
    check("step_since nu", d["step_since"] == "2026-10-16T21:40:00Z", d["step_since"])
    check("session_id/branch/opened_at",
          (d["session_id"], d["branch"], d["opened_at"]) == ("209286bf", "main", "2026-10-16T18:30:00Z"), d)
    check("summary", d["summary"] == "passo 3/4 · rodar advisors · institucionalizar as quatro perguntas", d["summary"])
    check("history: 1 entrada com 3 chaves",
          d["history"] == [{
              "at": "2026-10-16T18:30:00Z",
              "purpose": "criar um comando whereami",
              "change_reason": "o dono reformulou: o objeto é a intenção, não o comando"}],
          d["history"])
    check("PLANO_MAX é 6", M.PLANO_MAX == 6)


def test_chaves_antigas_sao_lidas_como_novas():
    antigo, novo = M.parse_intent(EXEMPLO_ANTIGO), M.parse_intent(EXEMPLO)
    check("exemplo antigo (proposito/plano/passo/...) == exemplo novo", antigo == novo, (antigo, novo))
    check("antigo: passo vira `step` int", antigo["step"] == 3 and "passo" not in antigo, antigo)
    check("antigo: nenhuma chave pt-BR sobra",
          not {"proposito", "para_quando", "plano", "passo", "passo_desde", "aberto_em",
               "resumo", "historico"} & set(antigo), sorted(antigo))
    check("antigo: entradas do histórico com chaves novas",
          antigo["history"][0].keys() == {"at", "purpose", "change_reason"}, antigo["history"])
    check("só `proposito:` antigo ainda é intenção",
          M.parse_intent("proposito: x\nplano:\n  - a\npasso: 2\n")
          == {"purpose": "x", "plan": ["a"], "step": 2})
    # ida e volta: render escreve as chaves novas, parse as lê iguais
    texto = M.render_intent(antigo)
    check("render_intent grava só chaves novas",
          texto.startswith('purpose: ') and "\nproposito" not in texto and "\nplano" not in texto
          and "\nstep: 3\n" in texto and "\nhistory:\n" in texto, texto)
    check("render -> parse é identidade", M.parse_intent(texto) == antigo)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".claude").mkdir()
        (Path(tmp) / M.INTENT_FILE).write_text(EXEMPLO_ANTIGO)
        d = M.read_intent(tmp)
        check("read_intent de arquivo antigo devolve chaves novas", d == novo, d)


def test_session_mode_antigo_e_novo():
    novo = M.parse_session_mode("mode: construction\nroutine: null\nbudget: null\nopened_at: 2026-10-19T13:46:36Z\n")
    antigo = M.parse_session_mode("modo: construcao\nrotina: null\norcamento: null\naberto_em: 2026-10-19T13:46:36Z\n")
    check("session-mode antigo (modo: construcao) == novo (mode: construction)", antigo == novo, (antigo, novo))
    check("session-mode: mode=construction", antigo["mode"] == "construction", antigo)
    check("session-mode: null vira None", antigo["routine"] is None and antigo["budget"] is None)
    check("session-mode: opened_at", antigo["opened_at"] == "2026-10-19T13:46:36Z", antigo)
    for velho, nv in (("exploracao", "exploration"), ("descoberta", "discovery"), ("design", "design"),
                      ("construcao", "construction"), ("reforma", "refactor"),
                      ("reflexao", "reflection"), ("documentacao", "documentation")):
        check(f"session-mode: modo: {velho} -> {nv}",
              M.parse_session_mode(f"modo: {velho}\n")["mode"] == nv)
        check(f"session-mode: mode: {nv} fica {nv}", M.parse_session_mode(f"mode: {nv}\n")["mode"] == nv)
    check("session-mode: orcamento entre aspas", M.parse_session_mode(
        'modo: reforma\norcamento: "só o filas.ts"\n')["budget"] == "só o filas.ts")
    check("chave nova vence a antiga quando as duas aparecem",
          M.parse_session_mode("modo: reforma\nmode: design\n")["mode"] == "design")
    with tempfile.TemporaryDirectory() as tmp:
        check("read_session_mode: ausente -> None", M.read_session_mode(tmp) is None)
        (Path(tmp) / ".claude").mkdir()
        (Path(tmp) / ".claude" / "session-mode").write_text("modo: construcao\nrotina: null\n")
        check("read_session_mode lê arquivo antigo", M.read_session_mode(tmp)["mode"] == "construction")
        (Path(tmp) / ".claude" / "session-mode").write_text("modo: null\n")
        check("read_session_mode: modo null -> None", M.read_session_mode(tmp) is None)


def test_arquivo_ausente_e_lido_do_disco(tmp):
    check("ausente -> None", M.read_intent(tmp) is None)
    (Path(tmp) / ".claude").mkdir()
    (Path(tmp) / M.INTENT_FILE).write_text(EXEMPLO)
    d = M.read_intent(tmp)
    check("presente -> dict", isinstance(d, dict) and d["step"] == 3, d)


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
          M.parse_intent("purpose: x\nplan:\n  - a\n  - b\nlixo")
          == {"purpose": "x", "plan": ["a", "b"]})
    check("parcial no formato antigo também",
          M.parse_intent("proposito: x\nplano:\n  - a\n  - b\nlixo")
          == {"purpose": "x", "plan": ["a", "b"]})
    check("passo nao numerico fica como veio", M.parse_intent("passo: tres\n")["step"] == "tres")
    check("plano vazio vira lista vazia", M.parse_intent("plano:\n")["plan"] == [])
    check("bloco com comentario: plano",
          M.parse_intent("plano: # nota\n  - a\n  - b\n")["plan"] == ["a", "b"])
    check("bloco com comentario: history",
          M.parse_intent("history: # x\n  - at: t\n    change_reason: m\n")["history"]
          == [{"at": "t", "change_reason": "m"}])
    check("bloco com comentario: historico (antigo)",
          M.parse_intent("historico: # x\n  - em: t\n    motivo_da_troca: m\n")["history"]
          == [{"at": "t", "change_reason": "m"}])
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
    check("aspas duplas com ':' e '#'", d["purpose"] == "corrigir a: parte # dois", d["purpose"])
    check("aspas simples com '#'", d["summary"] == "passo 1/2 # x", d["summary"])
    check("nu: corta ' # comentario'", d["branch"] == "feat/x", d["branch"])
    check("aspa escapada", d["by_when"] == 'diz "oi" e vai', d["by_when"])
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
    test_chaves_antigas_sao_lidas_como_novas()
    test_session_mode_antigo_e_novo()
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
