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


def test_the_whole_sentence_is_pinned():
    """Labels, order, separator and punctuation: the reader months later reads
    this sentence, not loose fragments (proof survivors S1-S4)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [routed("a1"), routed("a2")])
        answer(root, "a1", "sim: pode calibrar")
        answer(root, "a2", "não: deixa")
        options = (f"O que cada opção prometia: se sim, {IF_YES}; "
                   f"se não, {IF_NO}.")
        check("sim: a frase inteira",
              f"Pergunta respondida: {QUESTION} {options} "
              'O dono escolheu o "sim".' in evidence(root, "a1"),
              evidence(root, "a1"))
        check("não: a frase inteira",
              f"Pergunta respondida: {QUESTION} {options} "
              'O dono escolheu o "não".' in evidence(root, "a2"),
              evidence(root, "a2"))


def test_punctuation_is_not_doubled():
    """A question without `?` gets one `.`; one with `?` gets none; an effect
    that already ends in `.` is not doubled (proof survivors S5-S6)."""
    with tempfile.TemporaryDirectory() as tmp:
        plain = routed("a1")
        plain["owner_question"] = "Calibro X agora"
        plain["owner_summary"]["se_sim"] = "X é calibrado."
        plain["owner_summary"]["se_nao"] = "X fica."
        root = build_repo(tmp, [plain, routed("a2")])
        answer(root, "a1", "sim: calibra")
        answer(root, "a2", "sim: calibra")
        ev1, ev2 = evidence(root, "a1"), evidence(root, "a2")
        check("pergunta sem `?` ganha um ponto",
              "Pergunta respondida: Calibro X agora. O que" in ev1, ev1)
        check("efeito terminado em ponto não vira `..`",
              "se sim, X é calibrado; se não, X fica. O dono" in ev1, ev1)
        check("pergunta com `?` não ganha `?.`",
              f"{QUESTION} O que" in ev2 and "?." not in ev2, ev2)


def test_one_sided_summary_names_no_choice_it_did_not_keep():
    """A summary with only one side: the answer for the missing side does not
    claim the owner chose it (proof survivor S7)."""
    with tempfile.TemporaryDirectory() as tmp:
        only_no = routed("a1")
        del only_no["owner_summary"]["se_sim"]
        only_yes = routed("a2")
        del only_yes["owner_summary"]["se_nao"]
        root = build_repo(tmp, [only_no, only_yes])
        answer(root, "a1", "sim: pode")
        answer(root, "a2", "não: deixa")
        ev1, ev2 = evidence(root, "a1"), evidence(root, "a2")
        check("só se_não, resposta sim: guarda o não e não diz que escolheu o sim",
              f"O que cada opção prometia: se não, {IF_NO}." in ev1
              and "O dono escolheu" not in ev1, ev1)
        check("só se_sim, resposta não: guarda o sim e não diz que escolheu o não",
              f"O que cada opção prometia: se sim, {IF_YES}." in ev2
              and "O dono escolheu" not in ev2, ev2)


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
