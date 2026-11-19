#!/usr/bin/env python3
"""CS-6 of docs/spec/resposta-do-decide-vira-trabalho.md: the answer keeps in the
evidence what each option promised.

Origin (2026-11-18, kairos-etapa-1 queue of wego-digitacao-backend): `answer`
removes the owner section (`owner_question`, `owner_summary`) when it closes the
route, and the "se sim"/"se não" text went with it. Months later the evidence
said "Resposta do dono: sim" and nobody could tell what that "sim" had agreed to.

Against the real CLI, in a real git repo, in a PTY (`answer` only runs on a TTY):
  - red test: `answer --answer "sim: ..."` on a `done` item leaves in the
    evidence the question and the text of `se_sim`, marked as the chosen one;
  - the "se não" text is kept too (the title says "each option"), and a "não"
    answer marks that one as chosen;
  - a `blocked` item answered "sim" (it goes back to `pending`) keeps them too;
  - an answer that is neither "sim" nor "não" (`--force`) keeps both options and
    marks none as chosen;
  - `--keep` keeps the owner section in place, so the evidence gets no copy;
  - a route with no `owner_summary` keeps only the question.
"""
import os
import sys
import tempfile

from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import item, build_repo  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN, on_tty, items_of  # noqa: E402

FAILURES = []

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
for v in ("CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"):
    ENV.pop(v, None)

QUESTION = "Ponho na fila um item para calibrar X?"
IF_YES = "um item novo calibra X na próxima rodada"
IF_NO = "X fica com o valor de hoje"


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def routed(ident, status="done", summary=True):
    it = item(ident, status=status, human_pending="decidir se calibra X")
    it["route_kind"] = "open-question"
    it["owner_question"] = QUESTION
    if summary:
        it["owner_summary"] = {"se_sim": IF_YES, "se_nao": IF_NO,
                               "item_se_sim": "nenhum", "item_se_nao": "nenhum"}
    return it


def answer(root, ident, text, *extra):
    return on_tty([sys.executable, str(CEPA_PLAN), "answer", "fila", ident,
                   "--answer", text, "--repo", str(root), "--no-commit"]
                  + list(extra), str(root), env=ENV)


def evidence(root, ident):
    return " ".join(str(items_of(root)[ident].get("evidence") or "").split())


def test_red_test_yes_keeps_the_promise_of_yes():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1")])
        rc, out = answer(root, "a1", "sim: pode calibrar")
        check("answer sai 0", rc == 0, out)
        a1 = items_of(root)["a1"]
        check("a seção do dono sai do item, como antes",
              "owner_summary" not in a1 and "owner_question" not in a1, a1)
        ev = evidence(root, "a1")
        check("a evidência contém o texto do se_sim", IF_YES in ev, ev)
        check("...e a pergunta respondida", QUESTION in ev, ev)
        check("...e o se_não, porque cada opção prometia algo", IF_NO in ev, ev)
        check("...marcando o \"sim\" como o escolhido",
              'O dono escolheu o "sim"' in ev, ev)
        check("a resposta continua gravada", "sim: pode calibrar" in ev, ev)


def test_no_marks_the_promise_of_no():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1")])
        rc, out = answer(root, "a1", "não: deixa como está")
        check("não: sai 0", rc == 0, out)
        ev = evidence(root, "a1")
        check("não: guarda as duas promessas", IF_YES in ev and IF_NO in ev, ev)
        check("não: marca o \"não\" como o escolhido",
              'O dono escolheu o "não"' in ev, ev)
        check("não: não marca o \"sim\"", 'O dono escolheu o "sim"' not in ev, ev)


def test_nao_without_accent_counts_as_no():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1")])
        rc, out = answer(root, "a1", "nao: deixa como esta")
        ev = evidence(root, "a1")
        check("nao sem acento: marca o \"não\"",
              rc == 0 and 'O dono escolheu o "não"' in ev, out + ev)


def test_blocked_yes_keeps_the_promise():
    with tempfile.TemporaryDirectory() as tmp:
        it = routed("a1", status="blocked")
        it["human_pending"] = None
        root = build_repo(tmp, [it])
        rc, out = answer(root, "a1", "sim: destrava")
        a1 = items_of(root)["a1"]
        ev = evidence(root, "a1")
        check("blocked: volta para pending", rc == 0 and a1["status"] == "pending",
              out)
        check("blocked: a evidência guarda o se_sim e a pergunta",
              IF_YES in ev and QUESTION in ev, ev)


def test_free_answer_keeps_both_and_marks_none():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1")])
        rc, out = answer(root, "a1", "calibra só o X de produção", "--force")
        ev = evidence(root, "a1")
        check("resposta livre: sai 0", rc == 0, out)
        check("resposta livre: guarda as duas promessas",
              IF_YES in ev and IF_NO in ev, ev)
        check("resposta livre: não marca escolha", "O dono escolheu" not in ev, ev)


def test_keep_leaves_the_owner_section_and_copies_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1")])
        rc, out = answer(root, "a1", "não: pergunta de novo amanhã", "--keep")
        a1 = items_of(root)["a1"]
        ev = evidence(root, "a1")
        check("keep: sai 0 e a seção do dono fica",
              rc == 0 and a1.get("owner_summary", {}).get("se_sim") == IF_YES, a1)
        check("keep: nada é copiado para a evidência", IF_YES not in ev, ev)


def test_route_without_summary_keeps_the_question():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1", summary=False)])
        rc, out = answer(root, "a1", "sim: feito")
        ev = evidence(root, "a1")
        check("sem owner_summary: sai 0 e guarda a pergunta",
              rc == 0 and QUESTION in ev, out + ev)
        check("sem owner_summary: não inventa promessa",
              "prometia" not in ev, ev)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAIL")
        sys.exit(1)
    print("all ok")
