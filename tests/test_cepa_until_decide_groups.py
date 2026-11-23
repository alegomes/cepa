#!/usr/bin/env python3
"""decide-agrupa-perguntas-iguais: `cepa until decide` groups equal questions and asks
once per group.

Origin (run `all/2026-11-21-1244`, feedback fb-20261123-8): 26 delivered items in 4
queues each asked the same thing (accept the proof's coverage waiver because the repo
has no Python coverage tool); the question TEXTS differed (each named its scope), so
text equality alone would not have grouped them. Two items are equal when (a) both have
a proposed waiver (`status: proposta`, matched by `fila` + `item`) with the same
`motivo`, else (b) their question text is the same after collapsing whitespace and case
and the route kind is the same. A group is ONE card, asked before the one-by-one items,
across queues in the `--all` panel; each member records its own answer in its own queue.

In-process cases drive `decide` / `ask_at_launch_all` with a scripted keyboard and a
recording `answer`; one case runs the real `cepa-until decide --all` in a pty with the
real `cepa-plan answer` behind it.

Run with `python3 tests/test_cepa_until_decide_groups.py`, exit 1 on any failure.
"""
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until as base  # noqa: E402
import test_cepa_until_all as al  # noqa: E402
import test_cepa_until_decide as dec  # noqa: E402

check = dec.check
FAILURES = dec.FAILURES
CEPA_UNTIL = al.CEPA_UNTIL
ANSI = dec.ANSI

MOTIVO = "nada-a-provar"


def owner_item(ident, question, title=None, motivo=None, kind="owner-task"):
    return {"id": ident, "title": title or f"title of {ident}", "reason": "human_pending",
            "question": question, "human_pending": f"route of {ident}",
            "route_kind": kind, "evidence": ""}


def waiver(fila, ident, motivo=MOTIVO, status="proposta"):
    return {"motivo": motivo, "escopo": f"scope-{ident}.py", "razao": "r",
            "status": status, "autor": None, "fila": fila, "item": ident}


def write_waivers(root, waivers):
    folder = Path(root) / ".claude" / "waivers"
    folder.mkdir(parents=True, exist_ok=True)
    for i, w in enumerate(waivers):
        (folder / f"w{i}-{w['item']}.yaml").write_text(
            yaml.safe_dump(w, allow_unicode=True, sort_keys=False), encoding="utf-8")


class Keys:
    """A scripted keyboard: returns the next input, records the prompts."""

    def __init__(self, inputs):
        self.inputs, self.prompts = list(inputs), []

    def __call__(self, prompt):
        self.prompts.append(ANSI.sub("", prompt))
        if not self.inputs:
            raise EOFError("the script ran out of inputs")
        return self.inputs.pop(0)


class Recorder:
    """A recording `answer`; `fail` is the set of ids whose answer fails."""

    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def __call__(self, ident, text, keep=False, drop=False):
        self.calls.append({"id": ident, "text": text, "keep": keep, "drop": drop})
        if ident in self.fail:
            return 1, f"cepa-plan refused {ident}"
        return 0, f"{ident} recorded"


def run(deferred, inputs, repo=None, fail=(), analysis=None, **kw):
    m = dec.load_module()
    keys, rec, screen = Keys(inputs), Recorder(fail), []
    progress = kw.pop("progress", {})
    with tempfile.TemporaryDirectory() as tmp:
        repo = repo or Path(tmp)
        if callable(repo):
            repo = repo(Path(tmp))
        applied, later = m.decide(repo, "fila", "run1", {}, deferred, analysis or {},
                                  question=keys, output=screen.append, answer=rec,
                                  progress=progress, **kw)
    return m, "\n".join(screen), applied, later, rec, keys, progress


def three_with_waivers(tmp):
    write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2"), waiver("fila", "x3")])
    return tmp


SCOPED = [owner_item("x1", "Aceito a dispensa do classificador? Recomendo sim: mesmo criterio"),
          owner_item("x2", "Aceito a dispensa do cepa-plan? Recomendo sim: mesmo criterio"),
          owner_item("x3", "Aceito a dispensa do cepa-intent? Recomendo sim: mesmo criterio")]


def test_waiver_group_with_different_texts_is_one_card_and_a_records_each_item():
    _, out, applied, later, rec, keys, prog = run(
        SCOPED + [owner_item("z9", "Libero o acesso?")],
        ["a", "", "n", ""], repo=three_with_waivers)
    check("one card for the three, one for the other: 4 items in 2 questions",
          "4 items in 2 question(s) for you" in out, out)
    check("the group card says 3 items, one question",
          "[1/2] 3 items, one question" in out, out)
    check("it names the waiver reason in words and says it is a proof waiver",
          "proof waiver" in out and "nada a provar" in out, out)
    check("the members are listed one per line",
          all(f"         {i} — title of {i}" in out for i in ("x1", "x2", "x3")), out)
    check("all three recommend yes and `a` is the recommended key",
          "Recommend a: all 3 recommend yes" in out and "[a] accept each one's "
          "recommendation (recommended)" in keys.prompts[0], (out, keys.prompts))
    check("the legend has one line per key",
          all(f"       {k} = " in out for k in ("y", "n", "a", "o", "Enter", "q")), out)
    check("the single item comes after, numbered 2/2",
          "[2/2] z9" in out and out.index("3 items, one question") < out.index("[2/2] z9"),
          out)
    grouped = [c for c in rec.calls if c["id"] in ("x1", "x2", "x3")]
    check("three answers, one per member, 'sim: <own question>' + the group note",
          len(grouped) == 3 and all(
              c["text"].startswith("sim: Aceito a dispensa do")
              and c["text"].endswith("(respondida em grupo de 3)")
              and not c["keep"] for c in grouped), rec.calls)
    check("each answer carries its OWN question",
          [c["text"].split("?")[0] for c in grouped]
          == ["sim: Aceito a dispensa do classificador", "sim: Aceito a dispensa do cepa-plan",
              "sim: Aceito a dispensa do cepa-intent"], rec.calls)
    check("no per-item 'anything to add': one follow-up for the group, one for z9",
          sum("Anything to add" in p for p in keys.prompts) == 2
          and any("all 3 answers" in p for p in keys.prompts), keys.prompts)
    check("applied/for_later keep one entry per item",
          [a.split(":")[0] for a in applied] == ["x1", "x2", "x3", "z9"] and later == [],
          (applied, later))
    check("counts: asked 4 items, answered 4, one group card", prog.get("asked") == 4
          and prog.get("answered") == 4 and prog.get("questions") == 1, prog)


def test_y_to_all_text_group_in_single_queue_decide():
    """No waiver: same WRITTEN text after collapsing whitespace and case (items with no
    written question are never grouped by text)."""
    items = [owner_item("t1", "Fecho   o card?"), owner_item("t2", "fecho o CARD?"),
             owner_item("t3", "Fecho o card dois?"), owner_item("t4", "fecho o  card dois?"),
             owner_item("t5", "Fecho o card?", kind="open-question")]
    _, out, applied, later, rec, keys, _ = run(items, ["y", "", "y", "", "y", ""])
    check("5 items in 3 questions: two groups and the odd one (same text, other kind)",
          "5 items in 3 question(s) for you" in out, out)
    check("the text group shows the question itself", "Question: Fecho   o card?" in out
          or "Question: Fecho o card?" in out, out)
    check("`y` to all: every member answered sim, not kept",
          [c["id"] for c in rec.calls] == ["t1", "t2", "t3", "t4", "t5"]
          and all(c["text"].startswith("sim: ") and not c["keep"] for c in rec.calls[:4]),
          rec.calls)
    check("t5 (other route kind) was NOT grouped: asked on its own after the groups",
          "[3/3] t5" in out, out)
    check("the group note says 2 for the two groups of 2",
          rec.calls[0]["text"].endswith("(respondida em grupo de 2)"), rec.calls[0])


def test_items_with_no_written_question_are_asked_one_by_one():
    """The default question is not a written one: two unrelated owner tasks with the
    same route kind and no question are NOT one group; the panel is what it is with
    `group=False`."""
    items = [owner_item("u1", None), owner_item("u2", None)]
    _, out, applied, later, rec, keys, _ = run(items, ["y", "", "y", ""])
    _, plain, *_ = run(items, ["y", "", "y", ""], group=False)
    check("no group card: 2 items in 2 questions, each its own card",
          "2 question(s) for you" in out and "one question" not in out
          and "[1/2] u1" in out and "[2/2] u2" in out, out)
    check("each answered on its own, no group note",
          [c["id"] for c in rec.calls] == ["u1", "u2"]
          and not any("respondida em grupo" in c["text"] for c in rec.calls), rec.calls)
    check("the panel is the same as without the grouping feature", out == plain,
          (out, plain))


def test_a_group_of_waiver_wins_over_text():
    """x1/x2 share a waiver motivo; x3 has the same TEXT as x1 but no waiver: x1 is in
    the waiver group only, so x3 stays alone (an item is in at most one group)."""
    def repo(tmp):
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2")])
        return tmp
    items = [owner_item("x1", "Mesma pergunta?"), owner_item("x2", "Outra?"),
             owner_item("x3", "Mesma pergunta?")]
    _, out, *_ = run(items, ["q"], repo=repo)
    check("2 items in the waiver group, x3 alone: 3 items in 2 questions",
          "3 items in 2 question(s)" in out and "[1/2] 2 items, one question" in out, out)


def test_waiver_needs_status_proposta_and_the_same_queue():
    def repo(tmp):
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2", status="recusada"),
                            waiver("other", "x3")])
        return tmp
    _, out, *_ = run(SCOPED, ["q"], repo=repo)
    check("a refused waiver and a waiver of another queue make no group",
          "one question" not in out and "3 question(s) for you" in out, out)


def test_n_to_all_keeps_every_item():
    _, out, applied, later, rec, _, _ = run(SCOPED, ["n", "porque sim"],
                                            repo=three_with_waivers)
    check("n: every member answered 'não: ...' with keep",
          len(rec.calls) == 3 and all(c["text"].startswith("não: ") and c["keep"]
                                      for c in rec.calls), rec.calls)
    check("the group follow-up line goes to every member, before the group note",
          all(". porque sim (respondida em grupo de 3)" in c["text"] for c in rec.calls),
          rec.calls)


def test_o_dissolves_the_group_into_the_per_item_flow():
    _, out, applied, later, rec, keys, _ = run(
        SCOPED, ["o", "y", "", "n", "", "y", ""], repo=three_with_waivers)
    check("the group card dissolved, so it does not count: the three are 1/3 to 3/3",
          all(f"[{n}/3] x{n}" in out for n in (1, 2, 3)) and "/4]" not in out, out)
    check("each recorded the per-item text, with NO group note",
          [c["id"] for c in rec.calls] == ["x1", "x2", "x3"]
          and all("grupo" not in c["text"] for c in rec.calls)
          and [c["keep"] for c in rec.calls] == [False, True, False], rec.calls)
    check("the menu of each single card has the usual [w] key",
          sum("[w] I write the answer" in p for p in keys.prompts) == 3, keys.prompts)


def test_enter_leaves_all_for_later_and_q_quits():
    _, out, applied, later, rec, _, _ = run(SCOPED + [owner_item("z9", "Outra?")],
                                            ["", "q"], repo=three_with_waivers)
    check("Enter: the three go to for_later, nothing answered for them",
          [l.split(":")[0] for l in later[:3]] == ["x1", "x2", "x3"] and not applied
          and [c["id"] for c in rec.calls] == [], (later, rec.calls))
    check("...and the panel went on to the next card (z9 asked, then q)",
          "z9" in out and [l.split(":")[0] for l in later] == ["x1", "x2", "x3", "z9"],
          later)
    _, out2, applied2, later2, rec2, _, prog = run(
        SCOPED + [owner_item("z9", "Outra?")], ["q"], repo=three_with_waivers)
    check("q on the group card: everything for later, the single is never shown",
          [l.split(":")[0] for l in later2] == ["x1", "x2", "x3", "z9"]
          and "[2/2] z9" not in out2 and not rec2.calls, (later2, out2))


def test_a_with_a_member_without_recommendation_asks_it_one_by_one():
    items = [owner_item("x1", "Aceito A? Recomendo sim: ok"),
             owner_item("x2", "Aceito B? Recomendo não: nao vale"),
             owner_item("x3", "Aceito C?")]
    _, out, applied, later, rec, keys, _ = run(
        items, ["a", "", "n", ""], repo=three_with_waivers)
    check("the card says how many carry none before the owner chooses",
          "2 of the 3 carry a recommendation (1 yes, 1 no); the 1 that carry none" in out,
          out)
    check("`a` is not marked recommended when a member has none",
          "[a] accept each one's recommendation" in keys.prompts[0]
          and "(recommended)" not in keys.prompts[0], keys.prompts[0])
    byid = {c["id"]: c for c in rec.calls}
    check("x1 got sim, x2 got não (kept) from their own recommendation",
          byid["x1"]["text"].startswith("sim: ") and not byid["x1"]["keep"]
          and byid["x2"]["text"].startswith("não: ") and byid["x2"]["keep"], rec.calls)
    check("x3 was asked one by one afterwards (own card, own text, no group note)",
          "[2/2] x3" in out and byid["x3"]["text"].startswith("não: Aceito C?")
          and "grupo" not in byid["x3"]["text"], (out, rec.calls))


def test_a_is_hidden_when_nobody_recommends_and_mixed_says_so():
    _, out, _a, _l, _r, keys, _p = run([owner_item("x1", "A?"), owner_item("x2", "A?")],
                                       ["q"])
    check("no recommendation anywhere: no [a] key, and the card says why",
          "[a] accept" not in "".join(keys.prompts) and "a = " not in out
          and "none of them carries a recommendation" in out, out)
    mixed = [owner_item("x1", "A? Recomendo sim: ok"), owner_item("x2", "B? Recomendo não: x")]
    _, out2, *_ = run(mixed, ["q"], repo=lambda t: (write_waivers(
        t, [waiver("fila", "x1"), waiver("fila", "x2")]) or t))
    check("mixed recommendations: `a` recommended, counts shown",
          "Recommend a: each item's own recommendation (1 yes, 1 no)" in out2, out2)


def test_a_failing_answer_goes_to_for_later_and_the_others_stay_applied():
    _, out, applied, later, rec, _, prog = run(
        SCOPED, ["y", ""], repo=three_with_waivers, fail={"x2"})
    check("two applied, one for later, one entry per item",
          [a.split(":")[0] for a in applied] == ["x1", "x3"]
          and [l.split(":")[0] for l in later] == ["x2"], (applied, later))
    check("the card reports the failed member and its reason",
          "not recorded: x2 — title of x2: cepa-plan refused x2" in out
          and "2 of 3 answers recorded, 1 failed and stay for later" in out, out)
    check("answered counts the two", prog.get("answered") == 2, prog)


def test_invalid_key_on_the_group_card_errors_and_asks_again():
    _, out, applied, later, rec, keys, _ = run(SCOPED, ["w", "zzz", "s", "y", ""],
                                               repo=three_with_waivers)
    check("an invalid key gets the usual error", '"w" is not one of the options' in out
          and '"zzz" is not one of the options' in out, out)
    check("old keys keep their own line", "s is now y (yes)" in out, out)
    check("it asked again and then answered", len(rec.calls) == 3, rec.calls)


def test_ungrouped_items_are_byte_for_byte_what_they_were():
    items = [owner_item("a1", "Pergunta um? Recomendo sim: x"),
             owner_item("a2", "Pergunta dois?")]
    _, with_groups, ap1, l1, rec1, _, _ = run(items, ["y", "", "n", ""])
    _, without, ap2, l2, rec2, _, _ = run(items, ["y", "", "n", ""], group=False)
    check("no group when the questions differ: same screen as with grouping off",
          with_groups == without and "one question" not in with_groups
          and "2 question(s) for you" in with_groups and "items in" not in with_groups,
          with_groups)
    check("...same answers", rec1.calls == rec2.calls and ap1 == ap2 and l1 == l2)


def test_one_equal_pair_is_not_a_group_of_one():
    _, out, *_ = run([owner_item("a1", "Igual?")], ["q"])
    check("a lone item is never a group", "one question" not in out, out)


def test_text_listing_prints_a_group_as_one_entry():
    m = dec.load_module()
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2"), waiver("fila", "x3")])
        m.pending_as_text("fila", "run1", {}, SCOPED + [owner_item("z9", "Outra?")], {},
                          output=out.append, repo=Path(tmp))
    text = "\n".join(out)
    check("the header counts items and questions",
          "waiting on you: 4 items in 2 question(s)" in text, text)
    check("one entry names the count and the member ids",
          "- 3 items, same question (x1, x2, x3): proof waiver, reason \"nada a provar\""
          in text, text)
    check("the three repeated lines are gone", "- x1 (" not in text and "- z9 (" in text, text)
    plain = []
    m.pending_as_text("fila", "run1", {}, SCOPED, {}, output=plain.append)
    check("without a repo the old text is untouched (no waiver lookup, no group)",
          "waiting on you: 3" in "\n".join(plain) and "- x1 (" in "\n".join(plain),
          "\n".join(plain))


# ── the all-queues panel ────────────────────────────────────────────────────

def _q_item(ident, question):
    it = base.item(ident, human_pending=f"route of {ident}")
    it["route_kind"] = "owner-task"
    it["owner_question"] = question
    return it


def _all_repo(tmp, queues, waivers):
    root, paths = al._repo(tmp, queues)
    if not waivers:
        return root, paths
    write_waivers(root, waivers)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
                    "waivers"], cwd=root, check=True)
    return root, paths


def _panel(root, inputs, fail=(), as_text=False):
    """`ask_at_launch_all` in-process with a scripted keyboard and a recording
    `_apply_answer` (the real one needs a terminal)."""
    m = dec.load_module()
    keys, calls = Keys(inputs), []

    def fake_apply(repo, queue, ident, text, keep=False, drop=False):
        calls.append({"queue": queue, "id": ident, "text": text, "keep": keep})
        return (1, "refused") if f"{queue}/{ident}" in fail else (0, f"{queue}/{ident} ok")
    m._apply_answer = fake_apply
    m.read_line = lambda prompt, output=print, wait=None: keys(prompt)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        m.ask_at_launch_all(root, wait=None, leftovers=True, as_text=as_text)
    return buf.getvalue(), calls, keys


TWO_QUEUES = lambda: {  # noqa: E731
    "a": [_q_item("a1", "Aceito a dispensa de A? Recomendo sim: ok"),
          _q_item("a2", "Outra coisa de A?")],
    "b": [_q_item("b1", "Aceito a dispensa de B? Recomendo sim: ok"),
          _q_item("b2", "Outra coisa de B?")]}
TWO_WAIVERS = [waiver("a", "a1"), waiver("b", "b1")]


def test_all_panel_waiver_group_spans_queues_and_is_asked_once():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        out, calls, keys = _panel(root, ["a", "", "y", "", "n", ""])
    check("the opening counts 4 items in 3 questions", "4 items in 3 question(s) for you"
          in out, out)
    check("ONE card for the group, with the queue prefix on its members",
          out.count("2 items, one question") == 1 and "a/a1 — item a1" in out
          and "b/b1 — item b1" in out, out)
    check("the group comes before the per-queue sections",
          out.index("2 items, one question") < out.index("queue `a`"), out)
    check("the singles are numbered after it: 2/3 and 3/3",
          "[2/3] a2" in out and "[3/3] b2" in out, out)
    byk = {(c["queue"], c["id"]): c for c in calls}
    check("each member recorded in ITS queue with its own text and the group note",
          byk[("a", "a1")]["text"].startswith("sim: Aceito a dispensa de A?")
          and byk[("b", "b1")]["text"].startswith("sim: Aceito a dispensa de B?")
          and all(byk[k]["text"].endswith("(respondida em grupo de 2)")
                  for k in (("a", "a1"), ("b", "b1"))), calls)
    check("the singles answered through the normal path (y keeps going back, n keeps)",
          not byk[("a", "a2")]["keep"] and byk[("b", "b2")]["keep"], calls)
    check("the closing keeps one ✓ per item, with the queue prefix",
          "Answered now: 4 · for later: 0" in out and "✓ a/a1: a/a1 ok" in out
          and "✓ b/b1: b/b1 ok" in out, out)


def test_all_panel_y_and_for_later_and_failure():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        out, calls, _ = _panel(root, ["y", "", "", ""], fail={"b/b1"})
    check("y: both tried; the one that failed is reported and goes for later",
          [(c["queue"], c["id"]) for c in calls] == [("a", "a1"), ("b", "b1")]
          and "not recorded: b/b1 — item b1: refused" in out
          and "for later: 3" in out, out)
    check("the back-command names the queues that still hold questions",
          "cepa-until decide b" in out, out)


def test_all_panel_o_and_enter_and_q():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        out, calls, _ = _panel(root, ["o", "y", "", "n", "", "y", "", "q"])
    check("o: the two come one by one inside their queue sections",
          "[1/4] a1" in out and "queue `a` · 2 question(s)" in out
          and "queue `b` · 2 question(s)" in out and "/5]" not in out, out)
    check("...answered without the group note", [c["id"] for c in calls] == ["a1", "a2", "b1"]
          and all("grupo" not in c["text"] for c in calls), calls)
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        out, calls, _ = _panel(root, ["", "q"])
    check("Enter on the group, q on the next: nothing answered",
          not calls and "stopped with q" in out, out)


def test_all_panel_listing_without_terminal_prints_one_entry():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        out, calls, _ = _panel(root, [], as_text=True)
    check("header, one group entry with the queue-prefixed ids, then the sections",
          "waiting on you: 4 items in 3 question(s)" in out
          and "- 2 items, same question (a/a1, b/b1): proof waiver" in out
          and "queue `a` · 1 question(s)" in out and "- a2 (" in out
          and "- a1 (" not in out and not calls, out)


def test_all_panel_without_groups_is_the_old_panel():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, {"a": [_q_item("a1", "Um?")], "b": [_q_item("b1", "Dois?")]},
                            [])
        out, calls, _ = _panel(root, ["y", "", "y", ""])
    check("2 question(s), no 'items in', numbered 1/2 and 2/2, no group card",
          "── 2 question(s) for you" in out and "items in" not in out
          and "[1/2] a1" in out and "[2/2] b1" in out and "one question" not in out, out)


# ── the real command, in a pty ──────────────────────────────────────────────

def test_real_decide_all_in_a_pty_records_each_member_in_its_queue_and_converts_waivers():
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        env = al._tty_env(tmp)
        env["CEPA_UNTIL_LEITOR"] = "off"
        rc, out = dec.on_tty(
            [sys.executable, str(CEPA_UNTIL), "decide", "--all", "--repo", str(root)],
            str(root), env=env, timeout=90,
            inputs=[("(recommended)", "a"), ("Anything to add to all 2", ""),
                    ("[w] I write the answer", "n"), ("Anything to add, in one", ""),
                    ("[w] I write the answer", "n"), ("Anything to add, in one", "")])
        out = ANSI.sub("", out)
        check("rc 0", rc == 0, out[-1500:])
        qa = {str(i["id"]): i for i in yaml.safe_load(paths["a"].read_text())["items"]}
        qb = {str(i["id"]): i for i in yaml.safe_load(paths["b"].read_text())["items"]}
        check("a1 and b1 each closed their route in their own queue, with the group note",
              qa["a1"]["human_pending"] is None and qb["b1"]["human_pending"] is None
              and "(respondida em grupo de 2)" in str(qa["a1"]["evidence"])
              and "(respondida em grupo de 2)" in str(qb["b1"]["evidence"]),
              (qa["a1"], qb["b1"], out[-1500:]))
        check("the single items were kept ('não') as always",
              "não: Outra coisa de A?" in str(qa["a2"]["evidence"])
              and "(respondida em grupo" not in str(qa["a2"]["evidence"]), qa["a2"])
        waivers = [yaml.safe_load(p.read_text()) for p in
                   sorted((root / ".claude" / "waivers").glob("*.yaml"))]
        check("both proposed waivers were converted by the answers (status gone, autor set)",
              all("status" not in w and w.get("autor") for w in waivers), waivers)
        files = al._git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("one commit holds both queues and both waivers",
              ".claude/queues/a/queue.yaml" in files and ".claude/queues/b/queue.yaml" in files
              and sum(f.startswith(".claude/waivers/") for f in files) == 2, files)
        check("the closing counts 4 items answered", "answered now 4" in out
              or "Answered now: 4" in out, out[-1200:])


# ── review findings (asked count, handed-back items, delivered, numbering) ──

def delivered_item(ident, question, kind="owner-task"):
    it = owner_item(ident, question, kind=kind)
    it["reason"] = "pos-entrega"
    return it


def test_asked_counts_each_item_once_when_the_group_is_handed_back():
    _, out, applied, later, rec, _, prog = run(
        SCOPED, ["o", "y", "", "y", "", "y", ""], repo=three_with_waivers)
    check("o on a group of 3, each then answered: asked is 3, not 6",
          prog.get("asked") == 3 and prog.get("answered") == 3, prog)
    items = [owner_item("x1", "Aceito A? Recomendo sim: ok"),
             owner_item("x2", "Aceito B? Recomendo não: nao vale"),
             owner_item("x3", "Aceito C?")]
    _, out, applied, later, rec, _, prog = run(
        items, ["a", "", "n", ""], repo=three_with_waivers)
    check("a with one member lacking a recommendation: asked is 3", prog.get("asked") == 3
          and prog.get("answered") == 3, prog)
    _, out, applied, later, rec, _, prog = run(
        SCOPED, ["o", "q"], repo=three_with_waivers)
    check("handed back and then quit before they are asked: still 3, never 0 or 6",
          prog.get("asked") == 3, prog)


def test_single_queue_handed_back_items_end_in_for_later_when_the_owner_quits():
    def second(tmp):
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2"),
                            waiver("fila", "y1", motivo="outro"),
                            waiver("fila", "y2", motivo="outro")])
        return tmp
    items = [owner_item("x1", "A? Recomendo sim: x"), owner_item("x2", "B? Recomendo sim: x"),
             owner_item("y1", "C? Recomendo sim: x"), owner_item("y2", "D? Recomendo sim: x")]
    _, out, applied, later, rec, _, _ = run(items, ["o", "q"], repo=second)
    check("o on G1 then q on G2: x1 and x2 are for later, as are y1 and y2, nothing answered",
          sorted(l.split(":")[0] for l in later) == ["x1", "x2", "y1", "y2"]
          and not rec.calls, (later, out))


def _all_two_groups():
    """G1 = a1 + b1 (queues a, b); G2 = c1 + c2 (queue c only)."""
    queues = {"a": [_q_item("a1", "Aceito A? Recomendo sim: ok")],
              "b": [_q_item("b1", "Aceito B? Recomendo sim: ok")],
              "c": [_q_item("c1", "Aceito C? Recomendo sim: ok"),
                    _q_item("c2", "Aceito D? Recomendo sim: ok")]}
    return queues, [waiver("a", "a1"), waiver("b", "b1"),
                    waiver("c", "c1", motivo="outro"), waiver("c", "c2", motivo="outro")]


def test_all_panel_handed_back_items_are_named_when_the_owner_quits_or_is_cut():
    for label, inputs in (("q", ["o", "q"]), ("EOF", ["o"])):
        with tempfile.TemporaryDirectory() as tmp:
            queues, ws = _all_two_groups()
            root, _ = _all_repo(tmp, queues, ws)
            out, calls, _ = _panel(root, inputs)
        tail = out[out.rindex("To answer later"):] if "To answer later" in out else out
        check(f"{label}: nothing answered", not calls, calls)
        check(f"{label}: both queues of the handed-back items are in the closing line",
              "cepa-until decide a" in tail and "cepa-until decide b" in tail, out)
        if label == "q":
            check("q: the queue of the group never opened is named too",
                  "cepa-until decide c" in tail, out)
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        queues, ws = _all_two_groups()
        root, _ = _all_repo(tmp, queues, ws)
        keys, buf = Keys(["o"]), io.StringIO()

        def raise_no_answer(prompt, output=print, wait=None):
            if keys.inputs:
                return keys(prompt)
            raise m.NoAnswer("wait")
        m.read_line = raise_no_answer
        m._apply_answer = lambda *a, **k: (0, "ok")
        with contextlib.redirect_stdout(buf):
            m.ask_at_launch_all(root, wait=60, leftovers=True)
    out = buf.getvalue()
    check("NoAnswer after o: both queues named", "nobody answered" in out
          and "cepa-until decide a" in out and "cepa-until decide b" in out, out)


def test_all_panel_handed_back_items_count_once_in_asked():
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        keys = Keys(["o", "y", "", "y", "", "y", "", "y", ""])
        m.read_line = lambda prompt, output=print, wait=None: keys(prompt)
        m._apply_answer = lambda *a, **k: (0, "ok")
        seen = {}
        real = m.Panel.close_panel
        m.Panel.close_panel = lambda self, *a, **k: seen.setdefault("n", True)
        orig_decide = m.decide

        def spy(*a, **k):
            seen["progress"] = k["progress"]
            return orig_decide(*a, **k)
        m.decide = spy
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                m.ask_at_launch_all(root, wait=None, leftovers=True)
        finally:
            m.Panel.close_panel = real
    check("4 items, group dissolved: asked is 4", seen["progress"].get("asked") == 4,
          seen["progress"])


def test_delivered_and_blocked_items_with_the_same_waiver_are_not_one_group():
    items = [delivered_item("x1", "Aceito A?"), owner_item("x2", "Aceito B?"),
             delivered_item("x3", "Aceito C?")]
    _, out, *_ = run(items, ["", "q"], repo=three_with_waivers)
    check("x1 and x3 (delivered) group; x2 (blocked) is alone: 3 items in 2 questions",
          "3 items in 2 question(s)" in out and "2 items, one question" in out
          and "x2" in out and "[2/2] x2" in out, out)
    same = [delivered_item("t1", "Mesma?"), owner_item("t2", "Mesma?")]
    _, out, *_ = run(same, ["q"])
    check("the same written question, one delivered one blocked: no group",
          "one question" not in out and "2 question(s) for you" in out, out)


def test_group_legend_says_what_y_does_for_its_kind():
    delivered = [delivered_item(f"x{i}", f"Aceito {i}?") for i in (1, 2, 3)]
    _, out, *_ = run(delivered, ["q"], repo=three_with_waivers)
    check("a delivered group: the task closes and the work stays; not 'back to the queue'",
          "y = yes to all 3: the task closes; the delivered work stays as it is" in out
          and "goes back to the queue" not in out
          and "n = no to all 3: the task stays open" in out, out)
    _, out, *_ = run(SCOPED, ["q"], repo=three_with_waivers)
    check("a blocked group: the item goes back to the queue",
          "y = yes to all 3: the item goes back to the queue with your answer" in out
          and "the delivered work" not in out, out)


def test_created_items_reads_the_lines_a_group_answer_produces():
    m = dec.load_module()
    line = "item novo criado pela resposta: n1 — novo titulo (no fim da fila, `pending`)"

    def answer(ident, text, keep=False, drop=False):
        return 0, f"{ident} recorded\n  {line}" if ident == "x2" else (0, "ok")[1]
    with tempfile.TemporaryDirectory() as tmp:
        repo = three_with_waivers(Path(tmp))
        applied, _ = m.decide(repo, "fila", "run1", {}, SCOPED, {},
                              question=Keys(["y", ""]), output=lambda *a: None,
                              answer=answer, progress={})
    check("single queue: the group member's created item is found",
          m.created_items(applied) == ["n1 — novo titulo"], (applied, m.created_items(applied)))
    with tempfile.TemporaryDirectory() as tmp:
        queues, ws = _all_two_groups()
        root, _ = _all_repo(tmp, queues, ws)
        keys = Keys(["y", "", ""])
        m.read_line = lambda prompt, output=print, wait=None: keys(prompt)
        got = []
        m._apply_answer = lambda repo, q, i, t, keep=False, drop=False: (
            0, f"{q}/{i} ok\n  {line}" if (q, i) == ("b", "b1") else "ok")
        m.commit_after_decide = lambda *a, **k: None
        real = m.Panel.close_panel
        m.Panel.close_panel = lambda self, nothing, applied, *a, **k: got.extend(applied)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                m.ask_at_launch_all(root, wait=None, leftovers=True)
        finally:
            m.Panel.close_panel = real
    check("all queues: the id carries its queue", m.created_items(got) == ["b/n1 — novo titulo"],
          (got, m.created_items(got)))


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
