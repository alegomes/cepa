#!/usr/bin/env python3
"""The format of `.claude/session-intent` and the shared reader in `_modes.py`.

No external dependency — run with `python3 tests/test_session_intent.py`.
Exits with code != 0 if anything fails.

## Why it exists

The session intent (purpose, plan, step, history) is a file of its own
because `session-mode` is read line by line by six readers that do not understand
lists, and the `write_mode` of `cepa` rewrites it with `>`. The reader lives in
`common/hooks/_modes.py` (a single one, without pyyaml) and is tolerant: a hook that breaks on a
half-written file takes down the turn. The worktree rescue also needs to
ignore the file (`RESCUE_SKIP` in `_wtlib.py`), otherwise the intent of a session
that ended would be carried to the next tree.

The example YAML is the literal of `docs/estrategia-intencao-da-sessao.md`.
`EXAMPLE_OLD` is the same file with the keys in pt-BR (format prior to the
`interface-in-english` item): the reader still understands it and returns the new keys.
"""

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _modes as M  # noqa: E402
import _wtlib as L  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


EXAMPLE = '''purpose: "institucionalizar as quatro perguntas de aterrissagem"
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
EXAMPLE_OLD = '''proposito: "institucionalizar as quatro perguntas de aterrissagem"
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


def test_doc_example():
    d = M.parse_intent(EXAMPLE)
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
    check("PLAN_MAX é 6", M.PLAN_MAX == 6)


def test_old_keys_are_read_as_new():
    legacy, new = M.parse_intent(EXAMPLE_OLD), M.parse_intent(EXAMPLE)
    check("exemplo antigo (proposito/plano/passo/...) == exemplo novo", legacy == new, (legacy, new))
    check("antigo: passo vira `step` int", legacy["step"] == 3 and "passo" not in legacy, legacy)
    check("antigo: nenhuma chave pt-BR sobra",
          not {"proposito", "para_quando", "plano", "passo", "passo_desde", "aberto_em",
               "resumo", "historico"} & set(legacy), sorted(legacy))
    check("antigo: entradas do histórico com chaves novas",
          legacy["history"][0].keys() == {"at", "purpose", "change_reason"}, legacy["history"])
    check("só `proposito:` antigo ainda é intenção",
          M.parse_intent("proposito: x\nplano:\n  - a\npasso: 2\n")
          == {"purpose": "x", "plan": ["a"], "step": 2})
    # round trip: render writes the new keys, parse reads them back the same
    text = M.render_intent(legacy)
    check("render_intent grava só chaves novas",
          text.startswith('purpose: ') and "\nproposito" not in text and "\nplano" not in text
          and "\nstep: 3\n" in text and "\nhistory:\n" in text, text)
    check("render -> parse é identidade", M.parse_intent(text) == legacy)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / ".claude").mkdir()
        (Path(tmp) / M.INTENT_FILE).write_text(EXAMPLE_OLD)
        d = M.read_intent(tmp)
        check("read_intent de arquivo antigo devolve chaves novas", d == new, d)


def test_session_mode_old_and_new():
    new = M.parse_session_mode("mode: construction\nroutine: null\nbudget: null\nopened_at: 2026-10-19T13:46:36Z\n")
    legacy = M.parse_session_mode("modo: construcao\nrotina: null\norcamento: null\naberto_em: 2026-10-19T13:46:36Z\n")
    check("session-mode antigo (modo: construcao) == novo (mode: construction)", legacy == new, (legacy, new))
    check("session-mode: mode=construction", legacy["mode"] == "construction", legacy)
    check("session-mode: null vira None", legacy["routine"] is None and legacy["budget"] is None)
    check("session-mode: opened_at", legacy["opened_at"] == "2026-10-19T13:46:36Z", legacy)
    for old, nv in (("exploracao", "exploration"), ("descoberta", "discovery"), ("design", "design"),
                      ("construcao", "construction"), ("reforma", "refactor"),
                      ("reflexao", "reflection"), ("documentacao", "documentation")):
        check(f"session-mode: modo: {old} -> {nv}",
              M.parse_session_mode(f"modo: {old}\n")["mode"] == nv)
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


def test_missing_file_is_read_from_disk(tmp):
    check("ausente -> None", M.read_intent(tmp) is None)
    (Path(tmp) / ".claude").mkdir()
    (Path(tmp) / M.INTENT_FILE).write_text(EXAMPLE)
    d = M.read_intent(tmp)
    check("presente -> dict", isinstance(d, dict) and d["step"] == 3, d)


def test_tolerance():
    junk = ["", "\n\n", "   ", "isto nao e yaml", ":::", "plano:\n  - a\n  lixo sem hifen\n",
             "passo: tres\n", "historico:\n  - \n    em\n", "- solto\n", "\tindentado\n",
             'proposito: "aspas sem fechar\n', "plano:\n", "# so comentario\n",
             "historico:\n    em: sem item\n", "\x00\xff"]
    for t in junk:
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


def test_quotes_preserve_colons_and_hashes():
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


def test_rescue_does_not_drag_the_intent(tmp):
    w = Path(tmp) / "w"
    (w / ".claude").mkdir(parents=True)
    (w / ".claude" / "session-intent").write_text(EXAMPLE)
    (w / ".claude" / "outro-artefato.yaml").write_text("x: 1\n")
    doomed = L.doomed_artifacts(str(w))
    check("session-intent fora do resgate", ".claude/session-intent" not in doomed, doomed)
    check("controle: outro artefato continua sendo resgatado",
          ".claude/outro-artefato.yaml" in doomed, doomed)


def main():
    test_doc_example()
    test_old_keys_are_read_as_new()
    test_session_mode_old_and_new()
    test_tolerance()
    test_quotes_preserve_colons_and_hashes()
    with tempfile.TemporaryDirectory() as tmp:
        test_missing_file_is_read_from_disk(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        test_rescue_does_not_drag_the_intent(tmp)
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
        return 1
    print("\nok — session-intent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
