#!/usr/bin/env python3
"""decide-agrupa-perguntas-iguais: `cepa run decide` groups equal questions and asks
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
recording `answer`; one case runs the real `cepa-run decide --all` in a pty with the
real `cepa-queue answer` behind it.

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
# `CEPA_RUN_SCRIPT` points every case at another copy of the script (a mutated copy
# in a proof run); `common/bin/` next to it must come along (it imports its siblings).
if os.environ.get("CEPA_RUN_SCRIPT"):
    CEPA_UNTIL = Path(os.environ["CEPA_RUN_SCRIPT"]).resolve()
    dec.CEPA_UNTIL = al.CEPA_UNTIL = CEPA_UNTIL
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

    def __init__(self, inputs, exhausted=None):
        self.inputs, self.prompts, self.exhausted = list(inputs), [], exhausted

    def __call__(self, prompt):
        self.prompts.append(ANSI.sub("", prompt))
        if not self.inputs:
            raise (self.exhausted() if self.exhausted
                   else EOFError("the script ran out of inputs"))
        return self.inputs.pop(0)


class Recorder:
    """A recording `answer`; `fail` is the set of ids whose answer fails."""

    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def __call__(self, ident, text, keep=False, drop=False):
        self.calls.append({"id": ident, "text": text, "keep": keep, "drop": drop})
        if ident in self.fail:
            return 1, f"cepa-queue refused {ident}"
        return 0, f"{ident} recorded"


def run(deferred, inputs, repo=None, fail=(), analysis=None, **kw):
    m = dec.load_module(kw.pop("color", "nunca"))
    keys, rec, screen = Keys(inputs), Recorder(fail), []
    progress = kw.pop("progress", {})
    states = kw.pop("states", {})
    editor = kw.pop("editor", None)
    if editor:
        m.edit_in_editor = editor
    with tempfile.TemporaryDirectory() as tmp:
        repo = repo or Path(tmp)
        if callable(repo):
            repo = repo(Path(tmp))
        applied, later = m.decide(repo, "fila", "run1", states, deferred, analysis or {},
                                  question=keys, output=screen.append, answer=rec,
                                  progress=progress, **kw)
    return m, "\n".join(screen), applied, later, rec, keys, progress


def three_with_waivers(tmp):
    write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2"), waiver("fila", "x3")])
    return tmp


SCOPED = [owner_item("x1", "Aceito a dispensa do classificador? Recomendo sim: mesmo criterio"),
          owner_item("x2", "Aceito a dispensa do cepa-queue? Recomendo sim: mesmo criterio"),
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
          == ["sim: Aceito a dispensa do classificador", "sim: Aceito a dispensa do cepa-queue",
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
          "not recorded: x2 — title of x2: cepa-queue refused x2" in out
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


def _panel(root, inputs, fail=(), as_text=False, color="nunca", exhausted=None,
           real=False):
    """`ask_at_launch_all` in-process with a scripted keyboard and a recording
    `_apply_answer` (the real one needs a terminal; `real=True` runs it, see
    `real_plan`). `exhausted(m)` makes the exception the keyboard raises when the
    script runs out (default EOFError)."""
    m = dec.load_module(color)
    keys, calls = Keys(inputs, (lambda: exhausted(m)) if exhausted else None), []

    def fake_apply(repo, queue, ident, text, keep=False, drop=False):
        calls.append({"queue": queue, "id": ident, "text": text, "keep": keep})
        return (1, "refused") if f"{queue}/{ident}" in fail else (0, f"{queue}/{ident} ok")
    if not real:
        m._apply_answer = fake_apply
    m.read_line = lambda prompt, output=print, wait=None: keys(prompt)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), real_plan(m, real):
        m.ask_at_launch_all(root, wait=None, leftovers=True, as_text=as_text)
    return buf.getvalue(), calls, keys


@contextlib.contextmanager
def real_plan(m, on=True):
    """`cepa-queue answer` runs only with a terminal on stdin. The module under test gets
    a `subprocess` that hands every child a pty as stdin, so the REAL `_apply_answer`
    and the real `cepa-queue answer` run in-process."""
    if not on:
        yield
        return
    master, slave = os.openpty()
    real = subprocess

    class WithTty:
        def __getattr__(self, name):
            return getattr(real, name)

        def run(self, cmd, **kw):
            kw.setdefault("stdin", slave)
            return real.run(cmd, **kw)
    m.subprocess = WithTty()
    try:
        yield
    finally:
        m.subprocess = real
        os.close(master)
        os.close(slave)


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
          "cepa-run decide b" in out, out)


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
        env["CEPA_RUN_READER"] = "off"
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
              "cepa-run decide a" in tail and "cepa-run decide b" in tail, out)
        if label == "q":
            check("q: the queue of the group never opened is named too",
                  "cepa-run decide c" in tail, out)
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
          and "cepa-run decide a" in out and "cepa-run decide b" in out, out)


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


# ── proof review: what a member records, the keys, the wording, the terminal ──

def flat(text):
    """The screen wraps long lines: compare the words."""
    return " ".join(str(text).split())


def four_with_waivers(tmp):
    write_waivers(tmp, [waiver("fila", f"x{i}") for i in (1, 2, 3, 4)])
    return tmp


def _four_members():
    """x1 writes a question AND has an analysis `pergunta` (the question wins); x2 only
    the analysis one; x3 only a route; x4 nothing at all."""
    x1 = owner_item("x1", "Q1? Recomendo sim: ok")
    x2, x3, x4 = owner_item("x2", None), owner_item("x3", None), owner_item("x4", None)
    x4["human_pending"] = None
    analysis = {"itens": {"x1": {"pergunta": "P1?", "instrucao": "  faça   X  "},
                          "x2": {"pergunta": "P2?", "instrucao": "Y2"},
                          "x3": {},
                          "x4": {"instrucao": "Y4"}}}
    return [x1, x2, x3, x4], analysis


def test_group_answer_text_instruction_extra_and_base_fallbacks():
    items, analysis = _four_members()
    _, out, applied, later, rec, keys, _ = run(items, ["y", "e1"], repo=four_with_waivers,
                                              analysis=analysis)
    note = "(respondida em grupo de 4)"
    check("y with a one-line extra: base question, then Instrução, then the extra, then the "
          "group note; base falls back from question to analysis pergunta to the route to "
          "'unblock the item'",
          [c["text"] for c in rec.calls] == [
              f"sim: Q1? Recomendo sim: ok Instrução: faça X. e1 {note}",
              f"sim: P2? Instrução: Y2. e1 {note}",
              f"sim: route of x3. e1 {note}",
              f"sim: unblock the item Instrução: Y4. e1 {note}"], rec.calls)
    check("y is never kept", not any(c["keep"] for c in rec.calls), rec.calls)
    _, out, *_, rec, keys, _ = run(items, ["y", ""], repo=four_with_waivers,
                                   analysis=analysis)
    check("y with no extra: no '. ' piece, the instruction stays",
          [c["text"] for c in rec.calls] == [
              f"sim: Q1? Recomendo sim: ok Instrução: faça X {note}",
              f"sim: P2? Instrução: Y2 {note}", f"sim: route of x3 {note}",
              f"sim: unblock the item Instrução: Y4 {note}"], rec.calls)
    _, out, *_, rec, keys, _ = run(items, ["n", "e1"], repo=four_with_waivers,
                                   analysis=analysis)
    check("n: 'não', the same bases, NO Instrução (it is only for yes), always kept",
          [c["text"] for c in rec.calls] == [
              f"não: Q1? Recomendo sim: ok. e1 {note}", f"não: P2?. e1 {note}",
              f"não: route of x3. e1 {note}", f"não: unblock the item. e1 {note}"]
          and all(c["keep"] for c in rec.calls), rec.calls)


def test_a_answers_each_member_with_its_own_recommendation_and_the_rest_one_by_one():
    items, analysis = _four_members()
    analysis["itens"]["x2"]["recomendo"] = "não"
    analysis["itens"]["x3"]["recomendo"] = "sim"
    _, out, applied, later, rec, keys, prog = run(
        items, ["a", "", "n", ""], repo=four_with_waivers, analysis=analysis)
    note = "(respondida em grupo de 4)"
    byid = {c["id"]: c for c in rec.calls}
    check("x1 sim from its own question, x2 não from the analysis (kept, no Instrução), "
          "x3 sim from the analysis",
          byid["x1"]["text"] == f"sim: Q1? Recomendo sim: ok Instrução: faça X {note}"
          and byid["x2"]["text"] == f"não: P2? {note}" and byid["x2"]["keep"]
          and byid["x3"]["text"] == f"sim: route of x3 {note}" and not byid["x3"]["keep"],
          rec.calls)
    check("x4 carries none: asked on its own card afterwards, no group note",
          "[2/2] x4" in out and byid["x4"]["text"].startswith("não: unblock the item")
          and "grupo" not in byid["x4"]["text"], (out, rec.calls))
    check("the card counts the ones with a recommendation and says the rest follow",
          "3 of the 4 carry a recommendation (2 yes, 1 no); the 1 that carry none stay out "
          "of [a] and are asked one by one" in flat(out)
          and "a = answers each item with its own recommendation (2 yes, 1 no); the 1 with "
          "none are asked one by one" in flat(out), out)
    check("the summary line says how many were recorded and how many come next",
          "→ 3 of 4 answers recorded, 1 asked one by one next" in out, out)
    check("the analysis recommendation alone is enough to offer [a]",
          "[a] accept each one's recommendation" in keys.prompts[0]
          and "(recommended)" not in keys.prompts[0], keys.prompts[0])


def test_group_summary_line_all_recorded_and_the_card_words():
    _, out, *_ = run(SCOPED, ["y", ""], repo=three_with_waivers)
    check("everything recorded: the line has no 'not recorded' and no failure piece",
          "→ 3 of 3 answers recorded\n" in out + "\n" and "not recorded" not in out
          and "failed" not in out and "asked one by one next" not in out, out)
    check("the card has its Items label, the three one-by-one lines and the legend of o/Enter/q",
          "Items: 3 share this question:" in out
          and "o = asks the 3 one by one, as usual" in out
          and "Enter = leaves all 3 for later" in out
          and "q = stops the questions; the rest stays for later" in out
          and "y = yes to all 3: the item goes back to the queue with your answer; a "
          "proposed waiver is accepted" in flat(out)
          and "n = no to all 3: it stays as it is and I only record what you say" in flat(out),
          out)
    text_items = [owner_item("t1", "Fecho o card? Recomendo sim: x"),
                  owner_item("t2", "fecho   o CARD? recomendo sim: x")]
    _, out, *_ = run(text_items, ["q"])
    check("a text group shows the question itself and has no waiver piece in its legend",
          "Question: Fecho o card? Recomendo sim: x" in out
          and "a proposed waiver" not in out and "In common" not in out
          and "Items: 2 share this question:" in out, out)


def test_group_keys_are_case_blind_and_have_the_words_yes_no_nao():
    for key, want in (("Y", "sim"), ("yes", "sim"), ("  YES ", "sim"), ("N", "não"),
                      ("no", "não"), ("nao", "não"), ("não", "não"), ("NAO", "não")):
        _, out, applied, later, rec, keys, _ = run(SCOPED, [key, ""],
                                                   repo=three_with_waivers)
        check(f"{key!r} on the group card answers {want} to the three",
              len(rec.calls) == 3 and all(c["text"].startswith(want + ": ")
                                          for c in rec.calls)
              and all(c["keep"] == (want == "não") for c in rec.calls), (out, rec.calls))
    _, out, applied, later, rec, keys, _ = run(
        [owner_item("x1", "A?"), owner_item("x2", "B?")], ["a", "q"],
        repo=lambda t: (write_waivers(t, [waiver("fila", "x1"), waiver("fila", "x2")]) or t))
    check("`a` when nobody recommends is an error and the card asks again (then q)",
          '"a" is not one of the options' in out and len(keys.prompts) == 2
          and not rec.calls, (out, keys.prompts))


def test_group_v_opens_the_editor_for_the_one_line_extra():
    seen = []

    def editor(*a, **k):
        seen.append(a)
        return "texto do editor"
    _, out, applied, later, rec, keys, _ = run(SCOPED, ["y", "v"], repo=three_with_waivers,
                                              editor=editor)
    check("the editor opened once, as 'group of 3', on the common reason, titled with the "
          "count",
          len(seen) == 1 and seen[0][0] == "group of 3" and "nada a provar" in seen[0][1]
          and seen[0][2] == "3 items, one question", seen)
    check("what the editor returned is the extra of every member",
          all(". texto do editor (respondida em grupo de 3)" in c["text"]
              for c in rec.calls) and len(rec.calls) == 3, rec.calls)
    seen.clear()
    pair = [owner_item("t1", "Fecho   o card?"), owner_item("t2", "fecho o card?")]
    run(pair, ["n", "V"], editor=editor)
    check("on a text group the editor is shown the question text itself",
          len(seen) == 1 and seen[0][0] == "group of 2" and seen[0][1] == "Fecho   o card?"
          and seen[0][2] == "2 items, one question", seen)


def test_group_o_says_it_asks_them_one_by_one_and_all_no_recommendation_lines():
    _, out, *_ = run(SCOPED, ["o", "q"], repo=three_with_waivers)
    check("o prints its note and the panel announces the cards that follow",
          "asking the 3 one by one" in out
          and "3 more question(s) follow, one by one" in out, out)
    no = [owner_item(f"x{i}", f"Aceito {i}? Recomendo não: nao") for i in (1, 2, 3)]
    _, out, _a, _l, rec, keys, _p = run(no, ["a", ""], repo=three_with_waivers)
    check("all-no: the line says no, `a` is recommended, the legend counts 0 yes 3 no",
          "Recommend a: all 3 recommend no" in out
          and "(recommended)" in keys.prompts[0]
          and "a = answers each item with its own recommendation (0 yes, 3 no)" in out
          and "the 3 with none" not in out, out)
    check("a on all-no keeps every item with 'não'", len(rec.calls) == 3 and all(
        c["keep"] and c["text"].startswith("não: ") for c in rec.calls), rec.calls)
    _, out, *_ = run(SCOPED[:2] + [owner_item("x3", "C? Recomendo não: x")], ["q"],
                     repo=three_with_waivers)
    check("mixed: the recommendation is 'each item's own', `a` is the recommended key",
          "Recommend a: each item's own recommendation (2 yes, 1 no)" in out
          and "all 3 recommend" not in out, out)
    _, out, *_ = run([owner_item("x1", "A?"), owner_item("x2", "B?")], ["q"],
                     repo=lambda t: (write_waivers(
                         t, [waiver("fila", "x1"), waiver("fila", "x2")]) or t))
    check("no recommendation: the card says so and the legend has no `a` line",
          "none of them carries a recommendation, so there is no [a]" in flat(out)
          and "a = answers" not in out, out)


def test_analysis_recommendation_and_pergunta_reach_the_group():
    items = [owner_item(f"t{i}", None) for i in (1, 2, 3)]
    analysis = {"itens": {f"t{i}": {"pergunta": "Fecho o card?", "recomendo": "sim",
                                    "porque": "p"} for i in (1, 2, 3)}}
    _, out, applied, later, rec, keys, _ = run(items, ["a", ""], analysis=analysis)
    check("the analysis pergunta is the written question, so the three are one text group",
          "[1/1] 3 items, one question" in out and "Question: Fecho o card?" in out, out)
    check("the analysis recommendation makes `a` the recommended key",
          "Recommend a: all 3 recommend yes" in out and "(recommended)" in keys.prompts[0],
          out)
    check("each member records the analysis pergunta",
          [c["text"] for c in rec.calls] == ["sim: Fecho o card? (respondida em grupo de 3)"] * 3,
          rec.calls)
    out2 = []
    m = dec.load_module()
    m.pending_as_text("fila", "run1", {}, items, analysis, output=out2.append,
                      repo=Path(tempfile.gettempdir()))
    check("the text listing takes the analysis too",
          "- 3 items, same question (t1, t2, t3): Fecho o card?" in "\n".join(out2), out2)


def test_group_card_on_a_real_terminal_lists_members_and_numbers_the_head():
    long_title = " ".join(f"palavra{i}" for i in range(60))
    items = [owner_item("x1", "Aceito? Recomendo sim: ok", title=long_title)] + [
        dict(it) for it in SCOPED[1:]] + [owner_item("z9", "Libero o acesso?")]
    _, out, applied, later, rec, keys, _ = run(items, ["y", "", "n", ""],
                                              repo=three_with_waivers, color="sempre")
    plain = ANSI.sub("", out)
    lines = plain.splitlines()
    check("the opening rule counts items and questions",
          "── 4 items in 2 question(s) for you" in plain, plain)
    check("the head is a card top with i/n and the count",
          any(l.startswith("┌─ 1/2 · 3 items, one question") for l in lines), plain)
    check("every member is a bordered line, indented by 4, with its title",
          "│    x2 — title of x2" in lines and "│    x3 — title of x3" in lines
          and any(l.startswith("│    x1 — palavra0 palavra1") for l in lines), plain)
    check("a long member line wraps with a hanging indent of 6",
          any(l.startswith("│      palavra") for l in lines), plain)
    check("the card is closed: one end per card (group and single)",
          sum(l.startswith("└─") for l in lines) == 2, plain)
    check("the summary is a green tick line inside the card",
          "│  ✓ 3 of 3 answers recorded" in lines, plain)
    check("the second card is numbered 2/2", any(l.startswith("┌─ 2/2 · z9") for l in lines),
          plain)
    _, out, *_ = run(SCOPED, ["y", ""], repo=three_with_waivers, color="sempre",
                     fail={"x2"})
    lines = ANSI.sub("", out).splitlines()
    check("a failed member is a red cross line, and so is the summary",
          "│  ✗ not recorded: x2 — title of x2: cepa-queue refused x2" in lines
          and "│  ✗ not recorded: 2 of 3 answers recorded, 1 failed and stay for later"
          in lines, lines)
    check("on a terminal a good run is green and the colors are those of the screen",
          "\x1b[32m✓ 3 of 3 answers recorded" in
          run(SCOPED, ["y", ""], repo=three_with_waivers, color="sempre")[1]
          and "\x1b[31m✗" in out, out)


# ── proof review: decide numbering, landing, the listing, the grouping rules ─

def test_decide_numbers_the_cards_after_a_group_is_handed_back():
    def repo(tmp):
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2"),
                            waiver("fila", "y1", motivo="m2"), waiver("fila", "y2", motivo="m2"),
                            waiver("fila", "w1", motivo="m3"), waiver("fila", "w2", motivo="m3")])
        return tmp
    items = [owner_item(i, f"{i}? Recomendo sim: x") for i in ("x1", "x2", "y1", "y2", "w1", "w2")]
    items.insert(1, owner_item("z9", "Libero o acesso?"))
    inputs = ["o", "y", "", "y", "", "y", "", "y", "", "y", ""]
    _, out, applied, later, rec, keys, prog = run(items, inputs, repo=repo)
    check("the opening counts 7 items in 4 questions", "7 items in 4 question(s) for you" in out,
          out)
    heads = [l.strip() for l in out.splitlines() if l.strip().startswith("━━")]
    check("G1 is 1/4; once it is handed back the others are 1/5 and 2/5; the members and the "
          "single come after, 3/5 to 5/5, the handed-back ones first",
          heads == ["━━ [1/4] 2 items, one question", "━━ [1/5] 2 items, one question",
                    "━━ [2/5] 2 items, one question", "━━ [3/5] x1", "━━ [4/5] x2",
                    "━━ [5/5] z9"], heads)
    check("the handed-back members are announced once",
          out.count("2 more question(s) follow, one by one") == 1, out)
    check("answers: the two other groups first, then x1, x2, then z9",
          [c["id"] for c in rec.calls] == ["y1", "y2", "w1", "w2", "x1", "x2", "z9"], rec.calls)
    check("asked counts 7 items, once each; one card per group, the handed-back one included",
          prog.get("asked") == 7 and prog.get("answered") == 7
          and prog.get("questions") == 3, prog)


def test_decide_group_false_asks_every_item_one_by_one():
    _, out, applied, later, rec, keys, prog = run(SCOPED, ["q"], repo=three_with_waivers,
                                                  group=False)
    check("with group=False the panel is the old one: 3 cards, no group card",
          "3 question(s) for you" in out and "one question" not in out
          and "[1/3] x1" in out and "items in" not in out, out)


def test_decide_with_a_given_total_numbers_inside_it():
    _, out, *_ = run(SCOPED, ["q"], repo=three_with_waivers, first=3, of=9)
    check("of=9 and first=3: the opening says 9, the card is 3/9",
          "── 9 question(s) for you" in out and "[3/9] 3 items, one question" in out, out)


def test_the_landing_counts_in_the_opening_and_q_there_leaves_the_groups_for_later():
    action = {"acoes": [{"id": "aterrissar", "frase": "Land it", "destino": "main"}]}
    items = SCOPED + [owner_item("z9", "Outra?")]
    _, out, applied, later, rec, keys, prog = run(items, ["q"], repo=three_with_waivers,
                                                  states=action)
    check("the landing is one item and one question next to 3+1 owner items: 5 items in 3",
          "5 items in 3 question(s) for you" in out, out)
    check("q on the landing card: no group card, nothing asked, everything for later",
          len(keys.prompts) == 1 and "one question" not in out and not rec.calls
          and [l.split(":")[0] for l in later] == ["merge into `main`", "x1", "x2", "x3", "z9"],
          (later, keys.prompts))
    check("the group never reached the screen, so it is not counted as asked",
          prog.get("questions", 0) == 0, prog)
    landed = []
    _, out, applied, later, rec, keys, prog = run(
        SCOPED, ["y", "n", "ok"], repo=three_with_waivers, states=action,
        land=lambda: landed.append(1) or 0)
    check("y on the landing lands it and the group card follows",
          landed == [1] and "3 items, one question" in out and len(rec.calls) == 3
          and "2 items in 2 question(s)" not in out and "4 items in 2 question(s)" in out,
          out)


def test_pending_as_text_counts_the_landing_and_asks_the_listing_for_the_repo():
    action = {"acoes": [{"id": "aterrissar", "frase": "Land it", "destino": "main"}]}
    items = SCOPED + [owner_item("z9", "Outra?")]
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2"), waiver("fila", "x3")])
        with_action, without = [], []
        m.pending_as_text("fila", "run1", action, items, {}, output=with_action.append,
                          repo=Path(tmp))
        m.pending_as_text("fila", "run1", {}, items, {}, output=without.append,
                          repo=Path(tmp))
    check("with the landing: 5 items (landing + 4) in 3 questions (landing + group + z9)",
          "waiting on you: 5 items in 3 question(s)" in "\n".join(with_action),
          with_action)
    check("without it: 4 items in 2 questions",
          "waiting on you: 4 items in 2 question(s)" in "\n".join(without), without)


def _delivered_repo(tmp, ids=("a", "b", "c")):
    """A git repo whose queue `fila` holds delivered items (done, with a route left) and
    a proposed waiver each: what `cepa-run decide fila` lists."""
    queue = []
    for i in ids:
        it = base.item(i, status="done", human_pending=f"route of {i}")
        it["route_kind"] = "owner-task"
        it["owner_question"] = f"Aceito {i}?"
        queue.append(it)
    root, paths = al._repo(tmp, {"fila": queue})
    write_waivers(root, [waiver("fila", i) for i in ids])
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
                    "waivers"], cwd=root, check=True)
    return root, paths["fila"]


def test_close_with_owner_lists_a_group_as_one_entry_when_not_interactive():
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _delivered_repo(tmp)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = m.close_with_owner(root, "fila", None, {}, interactive=False)
    out = buf.getvalue()
    check("the closing path passes the repo, so the listing groups: 3 items in 1 question",
          rc == 0 and "waiting on you: 3 items in 1 question(s)" in out
          and "- 3 items, same question (a, b, c): proof waiver" in out
          and "- a (" not in out, out)


def test_ask_at_launch_asks_one_by_one_and_never_groups():
    m = dec.load_module()
    queue = []
    for i in ("a", "b"):
        it = base.item(i, status="blocked", human_pending=f"route of {i}")
        it["route_kind"] = "owner-task"
        it["owner_question"] = f"Aceito {i}?"
        queue.append(it)
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {"fila": queue})
        write_waivers(root, [waiver("fila", "a"), waiver("fila", "b")])
        data, _ = m.query_queue("fila", root)
        keys, buf = Keys(["q"]), io.StringIO()
        m.read_line = lambda prompt, output=print, wait=None: keys(prompt)
        with contextlib.redirect_stdout(buf):
            m.ask_at_launch(root, "fila", data)
    out = buf.getvalue()
    check("the launch panel counts items and shows the first item's own card, no group card",
          "── 2 question(s) for you" in out and "one question" not in out
          and "[1/2] a" in out, out)


# ── group_owner_items and its helpers, called directly ──────────────────────

def member(queue, ident, question=None, d=None, delivered=False, kind="owner-task"):
    ad = owner_item(ident, question, kind=kind)
    if delivered:
        ad["reason"] = "pos-entrega"
    return {"queue": queue, "ad": ad, "d": d or {}, "label": ident, "bare": ident}


def grouping(waivers, members, files=()):
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        write_waivers(tmp, waivers)
        for name, text in files:
            (Path(tmp) / ".claude" / "waivers").mkdir(parents=True, exist_ok=True)
            (Path(tmp) / ".claude" / "waivers" / name).write_text(text, encoding="utf-8")
        return m.group_owner_items(Path(tmp), members)


def ids(group_or_list):
    members = group_or_list["members"] if isinstance(group_or_list, dict) else group_or_list
    return [x["bare"] for x in members]


def test_grouping_an_item_is_in_one_group_and_groups_keep_the_order_of_their_first_member():
    members = [member("fila", "t1", "  Mesma?"), member("fila", "w1", "A?"),
               member("fila", "t2", "mesma?"), member("fila", "w2", "B?"),
               member("fila", "w3", "Mesma?"), member("fila", "lone", "Outra?")]
    groups, singles = grouping([waiver("fila", f"w{i}") for i in (1, 2, 3)], members)
    check("the waiver group takes w3 and the text group does not take it again",
          [(g["kind"], ids(g)) for g in groups] == [("text", ["t1", "t2"]),
                                                    ("waiver", ["w1", "w2", "w3"])],
          [(g["kind"], ids(g)) for g in groups])
    check("the group order follows the first member (text at 0 before waiver at 1), the "
          "members keep the queue order, the singles are what is left, in order",
          ids(singles) == ["lone"], ids(singles))
    check("a text group carries the first member's question as written, not collapsed",
          groups[0]["text"] == "  Mesma?" and groups[0]["delivered"] is False
          and groups[1]["motivo"] == MOTIVO and groups[1]["delivered"] is False, groups)
    members = [member("fila", "d1", "Igual?", delivered=True),
               member("fila", "d2", "igual?", delivered=True)]
    groups, singles = grouping([], members)
    check("a text group of delivered items is delivered, and has no motivo",
          len(groups) == 1 and groups[0]["delivered"] is True and "motivo" not in groups[0]
          and not singles, groups)
    members = [member("fila", "w1"), member("fila", "w2"), member("fila", "t1", "Q?"),
               member("fila", "t2", "Q?"), member("fila", "u1", "R?"), member("fila", "u2", "R?")]
    groups, _ = grouping([waiver("fila", "w1"), waiver("fila", "w2")], members)
    check("the first group is the one of the first member; three groups come out in order",
          [(g["kind"], ids(g)) for g in groups] == [
              ("waiver", ["w1", "w2"]), ("text", ["t1", "t2"]), ("text", ["u1", "u2"])], groups)


def test_grouping_waivers_by_motivo_queue_status_and_unreadable_files():
    members = [member("fila", i) for i in ("x1", "x2", "x3", "x4")]
    groups, singles = grouping([waiver("fila", "x1", "m1"), waiver("fila", "x2", "m1"),
                                waiver("fila", "x3", "m2"), waiver("fila", "x4", "m2")],
                               members)
    check("two different motivos are two groups, each with its own motivo",
          [(g["motivo"], ids(g)) for g in groups] == [("m1", ["x1", "x2"]),
                                                      ("m2", ["x3", "x4"])] and not singles,
          groups)
    for status in ("aceita", "recusada", None):
        w = [waiver("fila", "x1", status=status), waiver("fila", "x2", status=status)]
        if status is None:
            for x in w:
                del x["status"]
        groups, singles = grouping(w, members[:2])
        check(f"a waiver whose status is {status!r} is not a proposal: no group",
              not groups and len(singles) == 2, groups)
    groups, _ = grouping([waiver(None, "x1"), waiver(None, "x2")],
                         [member("a", "x1"), member("b", "x2")])
    check("a waiver without `fila` ties its item in any queue: one group across queues",
          [(g["kind"], [(x["queue"], x["bare"]) for x in g["members"]]) for g in groups]
          == [("waiver", [("a", "x1"), ("b", "x2")])], groups)
    groups, singles = grouping([waiver("a", "x1"), waiver("a", "x2")],
                               [member("a", "x1"), member("b", "x2")])
    check("a waiver that names another queue does not tie the item", not groups
          and len(singles) == 2, groups)
    groups, _ = grouping([waiver("fila", 7), waiver("fila", 8)],
                         [member("fila", "7"), member("fila", "8")])
    check("an item id the yaml reads as a number still matches", len(groups) == 1, groups)
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        write_waivers(tmp, [waiver("fila", "x1", "b"), waiver("fila", "x1", "a"),
                            waiver("fila", "x1", "a"), waiver("fila", "x9", "c")])
        found = m.proposed_waivers(Path(tmp))
        check("two motivos on one item are joined sorted and deduplicated; an item with none "
              "is None",
              m.waiver_motivo_of(found, "fila", "x1") == "a, b"
              and m.waiver_motivo_of(found, "fila", "nope") is None
              and m.waiver_motivo_of(found, "other", "x9") is None, found)
    members = [member("fila", "x1"), member("fila", "x2")]
    groups, _ = grouping([waiver("fila", "x1", "a"), waiver("fila", "x1", "b"),
                          waiver("fila", "x2", "a, b")], members)
    check("the joined motivos are the key: x1 (a + b) and x2 (a, b) are one group",
          len(groups) == 1 and groups[0]["motivo"] == "a, b", groups)


def test_proposed_waivers_skips_what_is_not_a_proposal_or_cannot_be_read():
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / ".claude" / "waivers"
        folder.mkdir(parents=True)
        for name, text in (("00-list.yaml", "- a\n- b\n"), ("01-scalar.yaml", "hello\n"),
                           ("02-broken.yaml", "a: [unclosed\n"),
                           ("03-noitem.yaml", "motivo: m\nstatus: proposta\n"),
                           ("04-nomotivo.yaml", "item: x1\nstatus: proposta\n"),
                           ("05-emptymotivo.yaml", "item: x1\nmotivo: ''\nstatus: proposta\n"),
                           ("06-nostatus.yaml", "item: x1\nmotivo: m\n"),
                           ("07-accepted.yaml", "item: x1\nmotivo: m\nstatus: aceita\n"),
                           ("08-ok.yaml", "item: x5\nmotivo: m\nstatus: proposta\n")):
            (folder / name).write_text(text, encoding="utf-8")
        (folder / "09-dir.yaml").mkdir()
        (folder / "10-ok.yaml").write_text("item: x6\nmotivo: m\nstatus: proposta\n",
                                           encoding="utf-8")
        found = m.proposed_waivers(Path(tmp))
    check("only the two real proposals are returned, whatever came before them",
          [w["item"] for w in found] == ["x5", "x6"], found)


def test_written_question_and_own_recommendation_read_the_question_then_the_analysis():
    m = dec.load_module()
    wq = m.written_question_of
    check("the item's question wins, then the analysis pergunta, then nothing",
          wq({"question": "Q"}, {"pergunta": "P"}) == "Q"
          and wq({"question": None}, {"pergunta": "P"}) == "P"
          and wq({"question": ""}, {"pergunta": "P"}) == "P"
          and wq({}, {}) is None and wq({}, None) is None and wq({"question": ""}, {}) is None,
          None)
    rec = m.own_recommendation
    check("'Recomendo sim' in any case, 'nao' and 'não', any amount of space",
          rec({"question": "Fecho? recomendo SIM"}, {}) == "y"
          and rec({"question": "Fecho? Recomendo nao"}, {}) == "n"
          and rec({"question": "Fecho? Recomendo   não"}, {}) == "n"
          and rec({"question": "Fecho? RECOMENDO\tsim: porque"}, {}) == "y", None)
    check("the word must stand alone on both sides",
          rec({"question": "Fecho? irRecomendo sim"}, {}) is None
          and rec({"question": "Fecho? Recomendo simples"}, {}) is None
          and rec({"question": "Fecho? Recomendo naoo"}, {}) is None, None)
    check("with none in the question, the analysis one; the question's own wins over it",
          rec({"question": "Fecho?"}, {"recomendo": "sim"}) == "y"
          and rec({"question": "Fecho?"}, {"recomendo": "não"}) == "n"
          and rec({"question": "Fecho?"}, {"recomendo": "nao"}) == "n"
          and rec({"question": "Fecho?"}, {}) is None and rec({}, {}) is None
          and rec({"question": "Fecho? Recomendo sim"}, {"recomendo": "não"}) == "y"
          and rec({}, {"pergunta": "Fecho? Recomendo não", "recomendo": "sim"}) == "n", None)


# ── proof review: the --all panel (hand back, cut, numbering, keep) ────────

def _each_alone(names, pairs):
    """One queue per name holding ONE item; `pairs` are the groups: (motivo, [names])."""
    queues = {n: [_q_item(f"{n}1", f"Aceito {n}? Recomendo sim: ok")] for n in names}
    waivers = [waiver(n, f"{n}1", motivo=motivo) for motivo, group in pairs for n in group]
    return queues, waivers


def test_all_panel_o_on_a_group_whose_members_are_the_only_items_of_their_queues():
    with tempfile.TemporaryDirectory() as tmp:
        queues, ws = _each_alone("ab", [(MOTIVO, "ab")])
        root, _ = _all_repo(tmp, queues, ws)
        out, calls, _ = _panel(root, ["o", "y", "", "n", ""])
    check("each member, whose queue holds nothing else, gets its own card after the group",
          [(c["queue"], c["id"]) for c in calls] == [("a", "a1"), ("b", "b1")], (calls, out))
    check("...answered one by one: no group note, y goes back, n keeps",
          [c["keep"] for c in calls] == [False, True]
          and all("grupo" not in c["text"] for c in calls), calls)
    check("the cards are numbered 1/2 and 2/2 and the handing back is announced",
          "[1/2] a1" in out and "[2/2] b1" in out
          and "2 more question(s) follow, one by one" in out
          and "queue `a` · 1 question(s)" in out and "queue `b` · 1 question(s)" in out, out)


def test_all_panel_o_with_two_members_in_the_same_queue_asks_them_one_by_one():
    with tempfile.TemporaryDirectory() as tmp:
        queues = {"c": [_q_item("c1", "Aceito C? Recomendo sim: ok"),
                        _q_item("c2", "Aceito D? Recomendo sim: ok")]}
        root, _ = _all_repo(tmp, queues, [waiver("c", "c1"), waiver("c", "c2")])
        out, calls, keys = _panel(root, ["o", "y", "", "n", ""])
    check("after `o` the two come as single cards, not as a second group card",
          out.count("one question") == 1 and "[1/2] c1" in out and "[2/2] c2" in out,
          out)
    check("each answered on its own, in order, without the group note",
          [(c["id"], c["keep"]) for c in calls] == [("c1", False), ("c2", True)]
          and all("grupo" not in c["text"] for c in calls), calls)
    check("the singles had the per-item menu", sum("[w] I write" in p for p in keys.prompts)
          == 2, keys.prompts)


def test_all_panel_n_to_all_keeps_every_item_and_y_does_not():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        out, calls, _ = _panel(root, ["n", "porque", "y", "", "y", ""])
    byk = {(c["queue"], c["id"]): c for c in calls}
    check("n to the group: both members recorded 'não: ...' with keep, with the follow-up",
          all(byk[k]["keep"] and byk[k]["text"].startswith("não: ")
              and ". porque (respondida em grupo de 2)" in byk[k]["text"]
              for k in (("a", "a1"), ("b", "b1"))), calls)
    check("y on the singles that follow is not kept",
          not byk[("a", "a2")]["keep"] and not byk[("b", "b2")]["keep"], calls)
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        out, calls, _ = _panel(root, ["y", "", "q"])
    check("y to the group: both members NOT kept",
          [(c["id"], c["keep"]) for c in calls] == [("a1", False), ("b1", False)], calls)


def _three_groups():
    """Six queues with one item each; G1 = a+b, G2 = c+d, G3 = e+f."""
    return _each_alone("abcdef", [("m1", "ab"), ("m2", "cd"), ("m3", "ef")])


def _all_back(names):
    return " · ".join(f"cepa-run decide {n}" for n in names)


def test_all_panel_quit_or_cut_on_the_first_of_three_groups_names_every_queue_once():
    cuts = (("q", ["q"], None, "questions stopped with q; the run goes on without."),
            ("EOF", [], None, "questions interrupted; the run goes on without."),
            ("NoAnswer", [], lambda m: m.NoAnswer("wait"),
             "nobody answered in 0 min; the run goes on without."),
            ("Ctrl-C", [], lambda m: KeyboardInterrupt(),
             "questions interrupted; the run goes on without."))
    for label, inputs, exhausted, says in cuts:
        with tempfile.TemporaryDirectory() as tmp:
            queues, ws = _three_groups()
            root, _ = _all_repo(tmp, queues, ws)
            out, calls, keys = _panel(root, inputs, exhausted=exhausted)
        check(f"{label} on the first card: nothing answered, only that card was shown",
              not calls and len(keys.prompts) == 1 and "[2/3]" not in out, (calls, out))
        check(f"{label}: the closing line says why and names the six queues, each once, "
              "in the order of the groups",
              f"{says} To answer later: {_all_back('abcdef')}" in out
              and out.count("cepa-run decide a") == 1, out)
        check(f"{label}: the card counters are 1/3 and no closing panel follows",
              "[1/3] 2 items, one question" in out and "Answered now" not in out, out)


def test_all_panel_cut_on_a_later_group_names_only_the_queues_still_holding_questions():
    for label, exhausted, says in (
            ("EOF", None, "questions interrupted;"),
            ("NoAnswer", lambda m: m.NoAnswer("wait"), "nobody answered in")):
        with tempfile.TemporaryDirectory() as tmp:
            queues, ws = _three_groups()
            root, _ = _all_repo(tmp, queues, ws)
            out, calls, _ = _panel(root, ["y", ""], exhausted=exhausted)
        check(f"{label} on G2: G1 was answered in its two queues",
              [(c["queue"], c["id"]) for c in calls] == [("a", "a1"), ("b", "b1")], calls)
        check(f"{label}: the line names the queues of G2 and G3 only, G2's included",
              f"{says}" in out and f"To answer later: {_all_back('cdef')}\n" in out + "\n"
              and "decide a" not in out and "decide b" not in out, out)
    with tempfile.TemporaryDirectory() as tmp:
        queues, ws = _three_groups()
        root, _ = _all_repo(tmp, queues, ws)
        out, calls, _ = _panel(root, ["y", "", "q"])
    check("q on G2: G1 answered, the queues of G2 and G3 named, once each",
          f"To answer later: {_all_back('cdef')}" in out, out)


def test_all_panel_numbers_the_cards_and_the_singles_after_a_group_is_handed_back():
    with tempfile.TemporaryDirectory() as tmp:
        queues, ws = _three_groups()
        root, _ = _all_repo(tmp, queues, ws)
        out, calls, _ = _panel(root, ["y", "", "y", "", "y", ""])
    heads = [l.strip() for l in out.splitlines() if "one question" in l]
    check("three groups, three cards numbered 1/3, 2/3, 3/3",
          heads == [f"━━ [{k}/3] 2 items, one question" for k in (1, 2, 3)]
          and "6 items in 3 question(s) for you" in out, heads)
    with tempfile.TemporaryDirectory() as tmp:
        queues, ws = _three_groups()
        root, _ = _all_repo(tmp, queues, ws)
        out, calls, _ = _panel(root, ["o", "y", "", "y", "", "y", "", "y", ""])
    heads = [l.strip() for l in out.splitlines() if l.strip().startswith("━━")]
    check("G1 handed back: it was 1/3, the other two are 1/4 and 2/4 and the two members "
          "come last, 3/4 and 4/4",
          heads == ["━━ [1/3] 2 items, one question", "━━ [1/4] 2 items, one question",
                    "━━ [2/4] 2 items, one question", "━━ [3/4] a1", "━━ [4/4] b1"], heads)
    check("the handed-back members answered as singles; the others as groups",
          [(c["id"], "grupo" in c["text"]) for c in calls] == [
              ("c1", True), ("d1", True), ("e1", True), ("f1", True),
              ("a1", False), ("b1", False)], calls)


# ── proof review: the REAL `_apply_answer` against the real `cepa-queue answer` ──

def _queue_of(path):
    return {str(i["id"]): i for i in yaml.safe_load(Path(path).read_text())["items"]}


def _commits(root):
    return int(al._git(root, "rev-list", "--count", "HEAD").strip())


def test_real_apply_answer_records_drops_flattens_multiline_and_refuses():
    m = dec.load_module()
    items = []
    for ident, status in (("a", "pending"), ("b", "pending"), ("c", "done"), ("d", "pending"),
                          ("e", "pending")):
        it = base.item(ident, status=status, human_pending=f"route of {ident}")
        it["route_kind"] = "owner-task"
        items.append(it)
    with tempfile.TemporaryDirectory() as tmp:
        root, path = al._repo(tmp, {"fila": items})
        path = path["fila"]
        with real_plan(m):
            before = _commits(root)
            ra = m._apply_answer(root, "fila", "a", "sim: pode seguir")
            rb = m._apply_answer(root, "fila", "b", "não: ainda não", keep=True)
            rc_ = m._apply_answer(root, "fila", "c", "sim: linha 1\nlinha 2")
            rd = m._apply_answer(root, "fila", "d", "descartado: não vale", drop=True)
            made = _commits(root) - before
            rz = m._apply_answer(root, "fila", "zz", "sim: nada")
            m._answer_commit = False
            re_ = m._apply_answer(root, "fila", "e", "sim: sem commit")
            after = _commits(root)
        q = _queue_of(path)
        check("y: rc 0, the route closes and the item stays pending with the answer kept",
              ra[0] == 0 and q["a"]["human_pending"] is None and q["a"]["status"] == "pending"
              and "sim: pode seguir" in q["a"]["evidence"], (ra, q["a"]))
        check("n with keep: rc 0, the route stays open, the answer is recorded",
              rb[0] == 0 and q["b"]["human_pending"] == "route of b"
              and "não: ainda não" in q["b"]["evidence"], (rb, q["b"]))
        check("a text with a line break keeps it (--multiline)",
              rc_[0] == 0 and "linha 1\nlinha 2" in q["c"]["evidence"], (rc_, q["c"]))
        check("drop: the item is dropped", rd[0] == 0 and q["d"]["status"] == "dropped",
              (rd, q["d"]))
        check("a refusal comes back as its nonzero rc and its message (stderr here)",
              rz[0] != 0 and "não tem item 'zz'" in rz[1], rz)
        check("the answer is committed by default, one commit per answered item",
              made == 4, made)
        check("with the commit turned off the queue is written but nothing is committed, "
              "and the 'fila gravada sem commit' notice (false by then) is not shown",
              re_[0] == 0 and after == before + 4 and q["e"]["human_pending"] is None
              and "sem commit" not in re_[1] and re_[1], (re_, before, after))
        m._answer_commit = True


def test_real_apply_answer_shows_the_no_commit_notice_cepa_plan_prints_when_unfiltered():
    """The notice is cepa-queue's own, so dropping the filter in `_apply_answer` shows it;
    here the filter is what keeps `decide`'s output true."""
    m = dec.load_module()
    it = base.item("e", status="pending", human_pending="route of e")
    it["route_kind"] = "owner-task"
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {"fila": [it]})
        master, slave = os.openpty()
        raw = subprocess.run([sys.executable, str(CEPA_UNTIL.parent / "cepa-queue"), "answer",
                              "fila", "e", "--answer", "sim: z", "--repo", str(root),
                              "--no-commit"], capture_output=True, text=True, stdin=slave)
        os.close(master)
        os.close(slave)
    check("cepa-queue itself prints the notice with --no-commit",
          "fila gravada sem commit" in raw.stdout + raw.stderr, raw)


def _real_decide(deferred, inputs, queue_items, waivers=(), **kw):
    """`decide` on queue `fila` with the real `_apply_answer`; returns what the screen,
    the queue file and the waivers say after."""
    m = dec.load_module()
    keys, screen = Keys(inputs), []
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _all_repo(tmp, {"fila": queue_items}, list(waivers))
        with real_plan(m):
            applied, later = m.decide(root, "fila", None, {}, deferred, {}, question=keys,
                                      output=screen.append, progress={}, **kw)
        waiver_files = [yaml.safe_load(p.read_text()) for p in
                        sorted((root / ".claude" / "waivers").glob("*.yaml"))] \
            if (root / ".claude" / "waivers").exists() else []
        return ("\n".join(screen), applied, later, _queue_of(paths["fila"]), waiver_files,
                _commits(root))


def _delivered_queue_items(ids):
    out = []
    for i in ids:
        it = base.item(i, status="done", human_pending=f"route of {i}")
        it["route_kind"] = "owner-task"
        out.append(it)
    return out


def test_real_group_answer_on_delivered_items_y_n_and_a_refusal():
    ids = ("x1", "x2", "x3")
    deferred = [delivered_item(i, f"Aceito {i}? Recomendo sim: ok") for i in ids]
    ws = [waiver("fila", i) for i in ids]
    out, applied, later, q, waivers, _ = _real_decide(
        deferred, ["y", "tudo certo"], _delivered_queue_items(ids), ws)
    check("y to a delivered group: the three tasks close in the real queue, the work stays done",
          all(q[i]["human_pending"] is None and q[i]["status"] == "done" for i in ids)
          and [a.split(":")[0] for a in applied] == list(ids) and not later, (q, applied))
    check("each item's evidence holds its own question, the extra and the group note",
          all(f"sim: Aceito {i}? Recomendo sim: ok. tudo certo (respondida em grupo de 3)"
              in q[i]["evidence"] for i in ids), q)
    check("the proposed waivers were accepted by the yes (status gone)",
          len(waivers) == 3 and all("status" not in w for w in waivers), waivers)
    check("the card reports the three recorded", "→ 3 of 3 answers recorded" in out, out)
    out, applied, later, q, waivers, _ = _real_decide(
        deferred, ["n", ""], _delivered_queue_items(ids), ws)
    check("n to the group: every route stays open (kept), the answer is recorded as 'não'",
          all(q[i]["human_pending"] == f"route of {i}"
              and f"não: Aceito {i}? Recomendo sim: ok (respondida em grupo de 3)"
              in q[i]["evidence"] for i in ids), q)
    out, applied, later, q, waivers, _ = _real_decide(
        deferred, ["y", ""], _delivered_queue_items(("x1", "x3")), ws)
    check("a member cepa-queue refuses (it is not in the queue): its message is shown, it "
          "stays for later, the other two are recorded",
          "not recorded: x2 — title of x2: a fila fila não tem item 'x2'" in out
          and "2 of 3 answers recorded, 1 failed and stay for later" in out
          and [a.split(":")[0] for a in applied] == ["x1", "x3"]
          and [l.split(":")[0] for l in later] == ["x2"]
          and q["x1"]["human_pending"] is None and q["x3"]["human_pending"] is None,
          (out, applied, later))


def test_real_all_panel_n_to_all_keeps_the_routes_open_in_every_queue():
    with tempfile.TemporaryDirectory() as tmp:
        queues, ws = _each_alone("ab", [(MOTIVO, "ab")])
        root, paths = _all_repo(tmp, queues, ws)
        out, _, _ = _panel(root, ["n", "porque", ], real=True)
        qa, qb = _queue_of(paths["a"]), _queue_of(paths["b"])
    check("n to all in the --all panel: both routes stay open and carry 'não' + the note",
          qa["a1"]["human_pending"] == "route of a1" and qb["b1"]["human_pending"] == "route of b1"
          and "não: Aceito a? Recomendo sim: ok. porque (respondida em grupo de 2)"
          in qa["a1"]["evidence"]
          and "(respondida em grupo de 2)" in qb["b1"]["evidence"], (qa, qb, out))


def test_group_card_closes_on_o_on_a_terminal_and_mixed_marks_a_recommended():
    _, out, *_ = run(SCOPED, ["o", "q"], repo=three_with_waivers, color="sempre")
    lines = ANSI.sub("", out).splitlines()
    check("`o` closes the group card (one end) before the single card opens",
          lines.index("└─") < next(i for i, l in enumerate(lines) if l.startswith("┌─ 1/3 · x1")),
          lines)
    mixed = [owner_item("x1", "A? Recomendo sim: ok"), owner_item("x2", "B? Recomendo não: x")]
    _, _, _, _, _, keys, _ = run(mixed, ["q"], repo=lambda t: (write_waivers(
        t, [waiver("fila", "x1"), waiver("fila", "x2")]) or t))
    check("mixed recommendations: `a` is the recommended key in the menu",
          "[a] accept each one's recommendation (recommended)" in keys.prompts[0],
          keys.prompts[0])


def test_all_panel_cut_after_o_lists_the_handed_back_queues_in_order_and_asks_nothing():
    queues = {"a": [_q_item("a1", "Aceito A? Recomendo sim: ok")],
              "b": [_q_item("b1", "Aceito B? Recomendo sim: ok")],
              "c": [_q_item("c1", "Outra coisa?")],
              "d": [_q_item("d1", "Aceito D? Recomendo sim: ok")],
              "e": [_q_item("e1", "Aceito E? Recomendo sim: ok")]}
    ws = [waiver("a", "a1"), waiver("b", "b1"), waiver("d", "d1", motivo="m2"),
          waiver("e", "e1", motivo="m2")]
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, queues, ws)
        out, calls, keys = _panel(root, ["o"])
    check("`o` on G1 then the keyboard ends on G2: nothing answered, no 'more questions "
          "follow' (they are never asked)",
          not calls and "more question(s) follow" not in out and len(keys.prompts) == 2,
          (calls, out))
    check("the closing names G2's queues first, then the handed-back ones, then the queue "
          "that was never opened, each once",
          f"To answer later: {_all_back('deabc')}" in out, out)


def test_all_panel_two_members_of_one_queue_name_that_queue_once():
    with tempfile.TemporaryDirectory() as tmp:
        queues = {"c": [_q_item("c1", "Aceito C? Recomendo sim: ok"),
                        _q_item("c2", "Aceito D? Recomendo sim: ok")]}
        root, _ = _all_repo(tmp, queues, [waiver("c", "c1"), waiver("c", "c2")])
        out, calls, _ = _panel(root, ["q"])
    check("q on a group with two members in one queue: the queue is named once",
          "To answer later: cepa-run decide c\n" in out + "\n"
          and out.count("cepa-run decide c") == 1, out)


def test_all_panel_a_with_one_member_lacking_a_recommendation_keeps_the_numbering():
    queues = {"a": [_q_item("a1", "Aceito A? Recomendo sim: ok")],
              "b": [_q_item("b1", "Aceito B? Recomendo não: x")],
              "c": [_q_item("c1", "Aceito C?")],
              "d": [_q_item("d1", "Outra coisa?")]}
    ws = [waiver("a", "a1"), waiver("b", "b1"), waiver("c", "c1")]
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, queues, ws)
        out, calls, _ = _panel(root, ["a", "", "y", "", "n", ""])
    heads = [l.strip() for l in out.splitlines() if l.strip().startswith("━━")]
    check("the group is not dissolved (two members were answered): the card stays 1/2 and "
          "the two singles are 2/3 and 3/3, the handed-back member last",
          heads == ["━━ [1/2] 3 items, one question", "━━ [2/3] d1", "━━ [3/3] c1"], heads)
    byk = {(c["queue"], c["id"]): c for c in calls}
    check("a1 sim, b1 não (kept) from their own recommendation; d1 and c1 one by one",
          byk[("a", "a1")]["text"].startswith("sim: ") and not byk[("a", "a1")]["keep"]
          and byk[("b", "b1")]["text"].startswith("não: ") and byk[("b", "b1")]["keep"]
          and not byk[("d", "d1")]["keep"] and byk[("c", "c1")]["keep"]
          and "grupo" not in byk[("c", "c1")]["text"], calls)


# ── proof round 2: the 18 gaps and the unreadable waiver file ───────────────

BAD_WAIVER_FILES = (("a-latin1.yaml", "item: x3\nmotivo: não-vale\nstatus: proposta\n"
                     .encode("latin-1")),
                    ("b-binary.yaml", b"\x00\xff\xfe\x80\x81\x00\x9c"))


def _put_bad_waivers(root):
    folder = Path(root) / ".claude" / "waivers"
    folder.mkdir(parents=True, exist_ok=True)
    for name, raw in BAD_WAIVER_FILES:
        (folder / name).write_bytes(raw)


def test_a_waiver_file_that_is_not_utf8_counts_as_no_proposal_and_the_panel_still_asks():
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2")])
        _put_bad_waivers(tmp)
        try:
            found = m.proposed_waivers(Path(tmp))
        except Exception as e:  # noqa: BLE001
            found = f"{type(e).__name__}: {e}"
    check("proposed_waivers skips a Latin-1 file and a binary one, keeps the valid two",
          isinstance(found, list) and [w["item"] for w in found] == ["x1", "x2"], found)

    def repo(tmp):
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2")])
        _put_bad_waivers(tmp)
        return tmp
    try:
        _, out, applied, later, rec, keys, _ = run(SCOPED, ["y", "", "y", ""], repo=repo)
    except Exception as e:  # noqa: BLE001
        check("decide with a bad waiver file does not crash", False, f"{type(e).__name__}: {e}")
        return
    check("decide: the valid proposals still group (x1, x2), the Latin-1 one ties nothing "
          "to x3, which is asked on its own",
          "[1/2] 2 items, one question" in out and "[2/2] x3" in out, out)
    check("decide: the three were answered, the group first",
          [c["id"] for c in rec.calls] == ["x1", "x2", "x3"]
          and "grupo" not in rec.calls[2]["text"], rec.calls)
    # the all-queues panel and the non-terminal listing read the same folder
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        _put_bad_waivers(root)
        try:
            out, calls, _ = _panel(root, ["y", "", "y", "", "y", ""])
        except Exception as e:  # noqa: BLE001
            check("the --all panel with a bad waiver file does not crash", False,
                  f"{type(e).__name__}: {e}")
            out, calls = "", []
    check("--all: the valid proposals group across queues and the panel asks every question",
          "4 items in 3 question(s) for you" in out and "2 items, one question" in out
          and len(calls) == 4, out)
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        _put_bad_waivers(root)
        try:
            out, _, _ = _panel(root, [], as_text=True)
        except Exception as e:  # noqa: BLE001
            check("the --all listing with a bad waiver file does not crash", False,
                  f"{type(e).__name__}: {e}")
            out = ""
    check("--all listing: one group entry, the singles listed",
          "waiting on you: 4 items in 3 question(s)" in out
          and "- 2 items, same question (a/a1, b/b1)" in out, out)
    listing = []
    with tempfile.TemporaryDirectory() as tmp:
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2")])
        _put_bad_waivers(tmp)
        try:
            m.pending_as_text("fila", "run1", {}, SCOPED, {}, output=listing.append,
                              repo=Path(tmp))
        except Exception as e:  # noqa: BLE001
            check("pending_as_text with a bad waiver file does not crash", False,
                  f"{type(e).__name__}: {e}")
    check("single-queue listing: 2 in a group, x3 alone",
          "3 items in 2 question(s)" in "\n".join(listing)
          and "(x1, x2)" in "\n".join(listing) and "- x3 (" in "\n".join(listing), listing)


def test_all_panel_o_asks_a_handed_back_member_once_and_the_new_queues_in_a_fixed_order():
    names = "zyxwvu"
    queues = {"k": [_q_item("k1", "Aceito k? Recomendo sim: ok"), _q_item("k2", "Outra K?")]}
    for n in names:
        queues[n] = [_q_item(f"{n}1", f"Aceito {n}? Recomendo sim: ok")]
    ws = [waiver(q, f"{q}1") for q in ["k", *names]]
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, queues, ws)
        out, calls, keys = _panel(root, ["o"] + ["y", ""] * 8)
    check("`o` on the group of 7 (k1 sits in a queue that also holds k2): 8 items, each "
          "asked exactly once, k's queue first (it already had a section), then the queues "
          "that only exist because of the handed-back members, in the order of the cards",
          [(c["queue"], c["id"]) for c in calls]
          == [("k", "k1"), ("k", "k2")] + [(n, f"{n}1") for n in "uvwxyz"], calls)
    check("the keyboard was read 1 + 8 x 2 times: no member is asked a second time",
          len(keys.prompts) == 17 and not keys.inputs, (len(keys.prompts), keys.inputs))
    check("each single card shows once: k1 once, and the heads run 1/8 to 8/8",
          out.count("] k1\n") == 1 and "[8/8] z1" in out and "[9/9]" not in out
          and out.count("queue `k` · 2 question(s)") == 1, out)


def test_all_panel_gives_its_wait_limit_to_the_group_card_through_the_real_reader():
    m = dec.load_module()
    waits = []

    def nobody_types(mod):
        def timed_input(prompt, wait):
            waits.append(wait)
            raise mod.NoAnswer("nobody typed")
        return timed_input

    def no_keyboard(prompt=""):
        raise EOFError("a read with no wait limit reached the keyboard")
    m.input = no_keyboard
    m._timed_input = nobody_types(m)
    m._apply_answer = lambda *a, **k: (0, "ok")
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.ask_at_launch_all(root, wait=120, leftovers=True)
    out = buf.getvalue()
    check("the real read_line gets the panel's wait (120 s) on the group card, once",
          waits == [120], waits)
    check("nobody answered the group card: the panel is cut with the wait in minutes and "
          "names the queues",
          "nobody answered in 2 min" in out and "To answer later: cepa-run decide a "
          "· cepa-run decide b" in out, out)
    waits.clear()
    m2 = dec.load_module()
    m2.input = no_keyboard
    m2._timed_input = nobody_types(m2)
    with tempfile.TemporaryDirectory() as tmp:
        repo = three_with_waivers(Path(tmp))
        try:
            m2.decide(repo, "fila", "run1", {}, SCOPED, {}, output=lambda *a: None,
                      answer=Recorder(), wait=45, progress={})
            cut = None
        except m2.NoAnswer as e:
            cut = e
    check("decide with no reader of its own: the group card reads with its wait (45 s)",
          waits == [45] and cut is not None, (waits, cut))


def test_decide_numbers_every_card_next_to_the_landing_question():
    action = {"acoes": [{"id": "aterrissar", "frase": "Land it", "destino": "main"}]}
    items = SCOPED + [owner_item("z9", "Outra?")]
    landed = []
    _, out, applied, later, rec, keys, _ = run(
        items, ["y", "y", "", "y", ""], repo=three_with_waivers, states=action,
        land=lambda: landed.append(1) or 0)
    heads = [l.strip() for l in out.splitlines() if l.strip().startswith("━━")]
    check("the landing is not numbered; the group card is 1/2 and the single 2/2",
          heads == ["━━ [1/2] 3 items, one question", "━━ [2/2] z9"] and landed == [1],
          heads)
    _, out, *_ = run(items, ["y", "o", "y", "", "y", "", "y", "", "y", ""],
                     repo=three_with_waivers, states=action, land=lambda: 0)
    heads = [l.strip() for l in out.splitlines() if l.strip().startswith("━━")]
    check("with the landing and a group handed back: the group was 1/2, the cards after it "
          "are numbered 1/4 to 4/4 (the landing is still out)",
          heads == ["━━ [1/2] 3 items, one question", "━━ [1/4] x1", "━━ [2/4] x2",
                    "━━ [3/4] x3", "━━ [4/4] z9"], heads)


def test_a_non_text_motivo_does_not_crash_and_does_not_group_unrelated_items():
    members = [member("fila", i) for i in ("x1", "x2", "x3", "x4", "x5", "x6")]
    odd = [waiver("fila", "x1", 7), waiver("fila", "x2", 7),
           waiver("fila", "x3", ["a", "b"]), waiver("fila", "x4", {"k": "v"}),
           waiver("fila", "x5", ["a", "b"]), waiver("fila", "x6", "outro")]
    try:
        groups, singles = grouping(odd, members)
    except Exception as e:  # noqa: BLE001
        check("a motivo that is a number, a list or a dict does not crash", False,
              f"{type(e).__name__}: {e}")
        return
    check("two items with the motivo 7 group; a list motivo groups only with an equal one; "
          "a dict motivo and a text one stay alone",
          [(g["motivo"], ids(g)) for g in groups]
          == [("7", ["x1", "x2"]), ("['a', 'b']", ["x3", "x5"])]
          and ids(singles) == ["x4", "x6"], (groups, singles))
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        write_waivers(tmp, [waiver("fila", "x1", 7), waiver("fila", "x2", 7),
                            waiver("fila", "x3", ["a", "b"])])
        found = m.proposed_waivers(Path(tmp))
        check("the motivo of an item is its text, never the raw value",
              m.waiver_motivo_of(found, "fila", "x1") == "7"
              and m.waiver_motivo_of(found, "fila", "x3") == "['a', 'b']", found)

    def repo(tmp):
        write_waivers(tmp, [waiver("fila", "x1", 7), waiver("fila", "x2", 7),
                            waiver("fila", "x3", ["a", "b"])])
        return tmp
    _, out, *_ = run(SCOPED, ["", "q"], repo=repo)
    check("the panel shows the group of the number motivo and the list one alone",
          "[1/2] 2 items, one question" in out and 'reason "7"' in out
          and "[2/2] x3" in out, out)


def test_a_group_of_legacy_named_reasons_names_them_when_left_for_later():
    items = [owner_item(i, f"Aceito {i}?") for i in ("x1", "x2", "x3")]
    for it in items:
        it["reason"] = "bloqueado-antes"
    stuck = "the agent marked the item as stuck"
    _, out, applied, later, rec, _, _ = run(items, ["", ], repo=three_with_waivers)
    check("Enter on a group whose reason is the old spelling: one 'why' per member",
          later == [f"{i}: {stuck}" for i in ("x1", "x2", "x3")] and not rec.calls, later)
    _, out, applied, later, rec, _, _ = run(items + [owner_item("z9", "Outra?")], ["q"],
                                            repo=three_with_waivers)
    check("q on that card: the same, and the single after it is left too",
          later[:3] == [f"{i}: {stuck}" for i in ("x1", "x2", "x3")] and len(later) == 4,
          later)
    _, out, applied, later, rec, _, _ = run(items, ["y", ""], repo=three_with_waivers,
                                            fail={"x2"})
    check("a member whose answer fails is left for later with the same wording",
          later == [f"x2: {stuck}"], later)


def test_the_group_extra_is_trimmed_and_the_recorded_message_has_no_trailing_newline():
    _, _, _, _, rec_none, _, _ = run(SCOPED, ["y", ""], repo=three_with_waivers)
    _, _, _, _, rec_blank, _, _ = run(SCOPED, ["y", "   \t "], repo=three_with_waivers)
    check("an extra of only spaces records no extra: the same texts as no extra",
          [c["text"] for c in rec_blank.calls] == [c["text"] for c in rec_none.calls]
          and rec_blank.calls, rec_blank.calls)
    _, _, _, _, rec_pad, _, _ = run(SCOPED, ["y", "  texto  "], repo=three_with_waivers)
    check("an extra with spaces around it is recorded trimmed",
          all(c["text"].endswith(". texto (respondida em grupo de 3)") for c in rec_pad.calls),
          rec_pad.calls)
    seen = []

    def editor(*a, **k):
        seen.append(a)
        return "do editor"
    _, _, _, _, rec_v, _, _ = run(SCOPED, ["y", " v "], repo=three_with_waivers, editor=editor)
    check("' v ' (spaces around) opens the editor, and its text is the extra",
          len(seen) == 1 and all(". do editor (respondida" in c["text"] for c in rec_v.calls),
          (seen, rec_v.calls))
    m = dec.load_module()
    it = base.item("a", status="pending", human_pending="route of a")
    it["route_kind"] = "owner-task"
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {"fila": [it]})
        with real_plan(m):
            ok = m._apply_answer(root, "fila", "a", "sim: pode seguir")
            bad = m._apply_answer(root, "fila", "zz", "sim: nada")
    check("the message of a recorded answer and of a refusal come without their trailing "
          "newline",
          ok[0] == 0 and ok[1] and ok[1] == ok[1].strip()
          and bad[0] != 0 and bad[1] and bad[1] == bad[1].strip(), (ok, bad))


def test_a_member_title_with_whitespace_lists_on_one_line():
    items = [owner_item("x1", "A?", title="  primeira   linha\n  segunda\tlinha  "),
             owner_item("x2", "B?", title="x2   com   espaços"), owner_item("x3", "C?")]
    _, out, *_ = run(items, ["q"], repo=three_with_waivers)
    check("a title's line breaks and runs of spaces collapse to one space, and the member "
          "is one line",
          "         x1 — primeira linha segunda linha\n" in out + "\n"
          and "         x2 — x2 com espaços\n" in out + "\n", out)
    m = dec.load_module()
    check("member_line trims a title that is only whitespace and shows the bare id",
          m.member_line({"queue": "q", "bare": "i", "ad": {"title": " \n "}}, True) == "q/i"
          and m.member_line({"queue": "q", "bare": "i", "ad": {"title": " a \n b "}}, False)
          == "i — a b", None)


def test_the_menu_of_the_group_card_names_every_key():
    _, _, _, _, _, keys, _ = run(SCOPED, ["q"], repo=three_with_waivers)
    check("the menu with the recommendation: every chip, in order, with the recommended mark",
          keys.prompts[0] == "       [y] yes to all 3 · [n] no to all 3 · [a] accept each "
          "one's recommendation (recommended) · [o] ask them one by one · [Enter] later · "
          "[q] quit: ", keys.prompts[0])
    _, _, _, _, _, keys, _ = run([owner_item("x1", "A?"), owner_item("x2", "A?")], ["q"])
    check("the menu with no recommendation anywhere has no [a] chip",
          keys.prompts[0] == "       [y] yes to all 2 · [n] no to all 2 · [o] ask them "
          "one by one · [Enter] later · [q] quit: ", keys.prompts[0])
    _, _, _, _, _, keys, _ = run(
        [owner_item("x1", "A? Recomendo sim: ok"), owner_item("x2", "B?")], ["q"],
        repo=lambda t: (write_waivers(t, [waiver("fila", "x1"), waiver("fila", "x2")]) or t))
    check("a partial recommendation: [a] is offered but not marked recommended",
          keys.prompts[0] == "       [y] yes to all 2 · [n] no to all 2 · [a] accept each "
          "one's recommendation · [o] ask them one by one · [Enter] later · [q] quit: ",
          keys.prompts[0])


def _card_block(out):
    """The lines of the first card of a terminal screen, from its top to its closing."""
    lines = ANSI.sub("", out).splitlines()
    top = next(i for i, l in enumerate(lines) if l.startswith("┌─ 1/"))
    end = next(i for i in range(top, len(lines)) if lines[i].startswith("└─"))
    return lines[top:end + 1]


def test_group_card_on_a_terminal_has_its_borders_and_closes_on_enter_and_on_q():
    expected = [
        "│",
        "│  In common       proof waiver: each of these items' proof asks you to accept the "
        "waiver for the",
        "│                  reason \"nada a provar\"",
        "│  Items           3 share this question:",
        "│    x1 — title of x1", "│    x2 — title of x2", "│    x3 — title of x3",
        "│",
        "│  ✦ Recommend a: all 3 recommend yes",
        "│",
        "│  y = yes to all 3: the item goes back to the queue with your answer; a proposed "
        "waiver is accepted",
        "│  n = no to all 3: it stays as it is and I only record what you say",
        "│  a = answers each item with its own recommendation (3 yes, 0 no)",
        "│  o = asks the 3 one by one, as usual",
        "│  Enter = leaves all 3 for later",
        "│  q = stops the questions; the rest stays for later",
        "│",
        "│  [y] yes to all 3 · [n] no to all 3 · [a] accept each one's recommendation "
        "(recommended)",
        "│  [o] ask them one by one · [Enter] later · [q] quit",
        "└─"]
    for key in ("", "q"):
        _, out, *_ = run(SCOPED + [owner_item("z9", "Outra?")], [key, "q"],
                         repo=three_with_waivers, color="sempre")
        block = _card_block(out)
        check(f"{key!r} on the group card: the card is bordered line by line, its head is "
              "followed by an empty border line, the legend by another, and it is closed",
              block[0].startswith("┌─ 1/2 · 3 items, one question") and block[1:] == expected,
              block)
        lines = ANSI.sub("", out).splitlines()
        tops = [i for i, l in enumerate(lines) if l.startswith("┌─")]
        ends = [i for i, l in enumerate(lines) if l.startswith("└─")]
        check(f"{key!r}: every card opened is closed before the next one opens",
              len(tops) == len(ends) and all(t < e for t, e in zip(tops, ends))
              and (len(tops) < 2 or ends[0] < tops[1]), lines)


# ── proof review round 3: assertions the mutants of the grouping code slipped past ──

# `yaml.safe_load` raises a plain ValueError (not a YAMLError, not a UnicodeDecodeError)
# for these two literals.
DATE_WAIVER_FILES = (
    ("a-bad-date.yaml", b"item: x3\nmotivo: m\nstatus: proposta\ncriado_em: 2026-13-45\n"),
    ("b-bad-timestamp.yaml",
     b"item: x3\nmotivo: m\nstatus: proposta\ncriado_em: !!timestamp 2026-02-30\n"),
    ("z-bad-date.yaml", b"item: x3\nmotivo: m\nstatus: proposta\ncriado_em: 2026-13-45\n"),
    ("zz-bad-timestamp.yaml",
     b"item: x3\nmotivo: m\nstatus: proposta\ncriado_em: !!timestamp 2026-02-30\n"))


def _put_date_waivers(root):
    folder = Path(root) / ".claude" / "waivers"
    folder.mkdir(parents=True, exist_ok=True)
    for name, raw in DATE_WAIVER_FILES:
        (folder / name).write_bytes(raw)


def test_a_waiver_file_with_an_impossible_date_counts_as_no_proposal_and_the_panel_asks():
    # the yaml loader raises a plain ValueError here: the catch must be wider than
    # UnicodeDecodeError; the bad files sort both before and after the valid ones
    for name, raw in DATE_WAIVER_FILES:
        try:
            yaml.safe_load(raw.decode())
            raised = None
        except Exception as e:  # noqa: BLE001
            raised = e
        check(f"{name} makes the yaml loader raise a plain ValueError",
              type(raised) is ValueError, raised)
    m = dec.load_module()
    with tempfile.TemporaryDirectory() as tmp:
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2")])
        _put_date_waivers(tmp)
        try:
            found = m.proposed_waivers(Path(tmp))
        except Exception as e:  # noqa: BLE001
            found = f"{type(e).__name__}: {e}"
    check("proposed_waivers skips the impossible dates, keeps the valid two",
          isinstance(found, list) and [w["item"] for w in found] == ["x1", "x2"], found)

    def repo(tmp):
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2")])
        _put_date_waivers(tmp)
        return tmp
    try:
        _, out, applied, later, rec, keys, _ = run(SCOPED, ["y", "", "y", ""], repo=repo)
    except Exception as e:  # noqa: BLE001
        check("decide with an impossible-date waiver does not crash", False,
              f"{type(e).__name__}: {e}")
    else:
        check("decide: x1 and x2 still group, x3 is asked on its own, all three answered",
              "[1/2] 2 items, one question" in out and "[2/2] x3" in out
              and [c["id"] for c in rec.calls] == ["x1", "x2", "x3"], out)
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        _put_date_waivers(root)
        try:
            out, calls, _ = _panel(root, ["y", "", "y", "", "y", ""])
        except Exception as e:  # noqa: BLE001
            check("the --all panel with an impossible-date waiver does not crash", False,
                  f"{type(e).__name__}: {e}")
        else:
            check("--all: the valid proposals group across queues and the panel asks all",
                  "4 items in 3 question(s) for you" in out
                  and "2 items, one question" in out and len(calls) == 4, out)
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        _put_date_waivers(root)
        try:
            out, _, _ = _panel(root, [], as_text=True)
        except Exception as e:  # noqa: BLE001
            check("the --all listing with an impossible-date waiver does not crash", False,
                  f"{type(e).__name__}: {e}")
        else:
            check("--all listing: the group is one entry",
                  "── waiting on you: 4 items in 3 question(s)" in out.splitlines()
                  and "- 2 items, same question (a/a1, b/b1)" in out, out)
    listing = []
    with tempfile.TemporaryDirectory() as tmp:
        write_waivers(tmp, [waiver("fila", "x1"), waiver("fila", "x2")])
        _put_date_waivers(tmp)
        try:
            m.pending_as_text("fila", "run1", {}, SCOPED, {}, output=listing.append,
                              repo=Path(tmp))
        except Exception as e:  # noqa: BLE001
            check("pending_as_text with an impossible-date waiver does not crash", False,
                  f"{type(e).__name__}: {e}")
        else:
            text = "\n".join(listing)
            check("single-queue listing: 2 in a group, x3 alone",
                  "3 items in 2 question(s)" in text and "(x1, x2)" in text
                  and "- x3 (" in text, listing)


def test_all_panel_listing_header_is_the_whole_line_with_and_without_groups():
    three = {"a": [_q_item("a1", "Primeira?")], "b": [_q_item("b1", "Segunda?")],
             "c": [_q_item("c1", "Terceira?")]}
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, three, [])
        out, calls, _ = _panel(root, [], as_text=True)
    lines = out.splitlines()
    check("no group: the header line is exactly 'waiting on you: 3'",
          "── waiting on you: 3" in lines and not any("items in" in l for l in lines)
          and not calls, lines)
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _all_repo(tmp, TWO_QUEUES(), TWO_WAIVERS)
        out, _, _ = _panel(root, [], as_text=True)
    check("with a group: the header line is exactly '4 items in 3 question(s)'",
          "── waiting on you: 4 items in 3 question(s)" in out.splitlines(), out)


def test_the_plain_group_head_has_a_blank_line_before_it_and_the_exact_lines_around():
    _, out, *_ = run(SCOPED + [owner_item("z9", "Outra?")], ["q"], repo=three_with_waivers)
    lines = out.split("\n")
    i = next((k for k, l in enumerate(lines) if "one question" in l), None)
    check("the head is `   ━━ [1/2] 3 items, one question`, after the opening rule and ONE "
          "blank line, followed by the first line of the body",
          i is not None and lines[i] == "   ━━ [1/2] 3 items, one question"
          and lines[i - 1] == "" and lines[i - 2].startswith("── 4 items in 2 question(s)")
          and lines[i + 1].startswith("       In common: proof waiver"), lines[:8])


def test_the_group_head_on_a_terminal_has_the_colour_of_a_single_head():
    m, out, *_ = run(SCOPED + [owner_item("z9", "Outra?")], ["", "q"], repo=three_with_waivers,
                     color="sempre")
    cyan = m.SCREEN.COLORS["ciano"]
    lines = out.split("\n")
    group = [l for l in lines if ANSI.sub("", l).startswith("┌─ 1/2 · 3 items, one question")]
    single = [l for l in lines if ANSI.sub("", l).startswith("┌─ 2/2 · z9")]
    check("one group head and one single head are on the screen",
          len(group) == 1 and len(single) == 1, lines)
    if len(group) == 1 and len(single) == 1:
        check("the single head starts with the cyan escape of the screen",
              single[0].startswith(cyan + "┌─ "), repr(single[0]))
        check("the group head starts with that same escape, and its rule is cyan too",
              group[0].startswith(cyan + "┌─ ") and group[0].endswith(
                  cyan + "─" * (len(ANSI.sub("", group[0])) - len(
                      ANSI.sub("", group[0]).rstrip("─"))) + m.SCREEN.RESET),
              repr(group[0]))


def test_blocked_before_and_human_pending_with_the_same_question_are_one_card():
    for reason in ("blocked-before", "bloqueado-antes"):
        stuck = owner_item("x1", "Mesma pergunta?")
        stuck["reason"] = reason
        _, out, applied, later, rec, keys, _ = run(
            [stuck, owner_item("x2", "Mesma pergunta?")], ["y", ""])
        check(f"{reason} + human_pending with the same question: one card of 2",
              "[1/1] 2 items, one question" in out
              and [c["id"] for c in rec.calls] == ["x1", "x2"], out)
        gone = delivered_item("x3", "Mesma pergunta?")
        _, out, *_ = run([stuck, gone, owner_item("x2", "Mesma pergunta?")], ["", "q"])
        check(f"a pos-entrega item does not join the {reason} + human_pending card",
              "[1/2] 2 items, one question" in out and "[2/2] x3" in out, out)
        _, out, *_ = run([stuck, gone], ["q"])
        check(f"{reason} and pos-entrega with the same question are not a group",
              "one question" not in out and "2 question(s) for you" in out, out)


PLAN_WRAPPER = '''\
import subprocess, sys
p = subprocess.run([sys.executable, {real!r}] + sys.argv[1:], capture_output=True, text=True)
notice = "  fila gravada sem commit"
head, found, tail = p.stdout.partition(notice)
if {mode!r} == "before":      # a blank line between the answer line and the notice
    sys.stdout.write(head + "\\n" + found + tail)
else:                         # the notice first, then a blank line, then the answer line
    sys.stdout.write(found + tail.rstrip("\\n") + "\\n\\n" + head)
sys.stderr.write(p.stderr)
sys.exit(p.returncode)
'''


def test_apply_answer_with_the_notice_filtered_has_no_blank_line_and_no_edge_whitespace():
    """A blank line before the filtered notice must not be left behind as a trailing
    newline (nor one after it as a leading one when the notice comes first). The real
    `cepa-queue answer` runs behind a wrapper that only inserts that blank line."""
    m = dec.load_module()
    real_script = CEPA_UNTIL.parent / "cepa-queue"
    for where in ("before", "after"):
        it = base.item("e", status="pending", human_pending="route of e")
        it["route_kind"] = "owner-task"
        with tempfile.TemporaryDirectory() as tmp:
            root, _ = al._repo(tmp, {"fila": [it]})
            wrapper = Path(tmp) / "cepa-queue"
            wrapper.write_text(PLAN_WRAPPER.format(real=str(real_script), mode=where),
                               encoding="utf-8")
            m.CEPA_PLAN = wrapper
            m._answer_commit = False
            try:
                with real_plan(m):
                    rc, msg = m._apply_answer(root, "fila", "e", "sim: ok")
            finally:
                m._answer_commit = True
                m.CEPA_PLAN = real_script
        check(f"blank line next to the notice ({where}): rc 0, the notice is gone, the "
              "message is its own strip() and no blank line is left where the notice was",
              rc == 0 and "sem commit" not in msg and bool(msg) and msg == msg.strip()
              and "\n\n" not in msg, (rc, msg))


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
