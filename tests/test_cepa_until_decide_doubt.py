#!/usr/bin/env python3
"""CS-1 of docs/spec/duvida-sobre-a-pergunta-do-decide.md: text typed in `w` that
looks like a doubt ("O que é a variante O?", the `not_an_answer` rule of
`cepa-queue`) makes the `cepa run decide` panel ask "Is this a doubt about the
question? [Y/n]" before anything is recorded, and `queue.yaml` stays byte for
byte the same. Before, the screen asked "Send the item back to the queue with
that answer? [y/N]" and then showed "not recorded".

Its own file so the proof gate can run it alone:
`python3 tests/test_cepa_until_decide_doubt.py`, exit 1 on any failure.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import CEPA_UNTIL, build_repo, item  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    ANSI, FAILURES, check, load_module, on_tty)
from pathlib import Path  # noqa: E402,F811

QUESTION = "A variante O já foi escolhida?"
DOUBT = "O que é a variante O?"
ASK = "Is this a doubt about the question? [Y/n]"


def test_doubt_typed_in_w_asks_if_it_is_a_doubt_before_recording():
    """Red test of CS-1, as a process in a pseudo-terminal."""
    failed_before = len(FAILURES)
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        it = item("b1", status="pending", human_pending="falta escolher a variante")
        it["owner_question"] = QUESTION
        it["route_kind"] = "external-block"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = qfile.read_bytes()
        env = dict(os.environ, CEPA_FEEDBACK_DIR=fb, CEPA_RUN_READER="off")
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        # Enter on the doubt question is yes (default Y); in the interim build it
        # records nothing and leaves the item for later.
        rc, out = on_tty(cmd, str(root), env=env, timeout=30, inputs=[
            ("[w] I write the answer", "w"),
            ("Your answer, in one line", DOUBT),
            (ASK, ""),
        ])
        plain = ANSI.sub("", out)
        check("CS-1 pty: decide exits 0", rc == 0, plain[-1500:])
        check("CS-1 pty: the panel asks if it is a doubt about the question",
              ASK in plain, plain[-1500:])
        check("CS-1 pty: the doubt is not offered as an answer to send back",
              "Send the item back to the queue with that answer?" not in plain, plain)
        check("CS-1 pty: nothing is refused as 'not recorded'",
              "not recorded" not in plain, plain)
        check("CS-1 pty: queue.yaml is byte-identical", qfile.read_bytes() == before,
              qfile.read_text())
        check("CS-1 pty: the item is left for later",
              "answered now 0" in plain and "for later 1" in plain, plain[-1500:])
        # `check` only records; without this, pytest reports green on a red case.
        assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def _fake_editor(tmp, text):
    editor = Path(tmp) / "fake-editor.sh"
    editor.write_text(f"#!/bin/sh\nprintf '%s' '{text}' > \"$1\"\n")
    editor.chmod(0o755)
    return editor


def _v_env(editor, fb, reader="off"):
    env = {k: v for k, v in os.environ.items() if k not in ("VISUAL", "EDITOR")}
    env.update(CEPA_FEEDBACK_DIR=fb, CEPA_RUN_READER=str(reader), EDITOR=str(editor))
    return env


def test_doubt_typed_through_v_asks_if_it_is_a_doubt_before_recording():
    """Red test of CS-4, as a process in a pseudo-terminal: a fake editor saves
    "não entendi a pergunta"; `v` shows the doubt prompt. Before, the screen
    showed "not recorded: resposta recusada" and the item went to later."""
    failed_before = len(FAILURES)
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        editor = _fake_editor(tmp, "não entendi a pergunta")
        it = item("b1", status="pending", human_pending="falta escolher a variante")
        it["owner_question"] = QUESTION
        it["route_kind"] = "external-block"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = qfile.read_bytes()
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), env=_v_env(editor, fb), timeout=30, inputs=[
            ("[v] write in the editor", "v"),
            (ASK, ""),
        ])
        plain = ANSI.sub("", out)
        check("CS-4 pty v: decide exits 0", rc == 0, plain[-1500:])
        check("CS-4 pty v: the panel asks if it is a doubt about the question",
              ASK in plain, plain[-1500:])
        check("CS-4 pty v: nothing is refused as 'not recorded'",
              "not recorded" not in plain and "resposta recusada" not in plain,
              plain[-1500:])
        check("CS-4 pty v: no send-back question for the doubt",
              "Send the item back to the queue with that answer?" not in plain,
              plain[-1500:])
        check("CS-4 pty v: queue.yaml is byte-identical (no reader, nothing recorded)",
              qfile.read_bytes() == before, qfile.read_text())
        assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_yes_at_the_doubt_prompt_after_v_rewrites_with_the_editor_text():
    """CS-4, yes: same as CS-2 but the doubt comes from the editor."""
    import yaml
    failed_before = len(FAILURES)
    typed = "não entendi a pergunta"
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        editor = _fake_editor(tmp, typed)
        it = item("b1", status="pending", human_pending="falta escolher a variante")
        it["owner_question"] = QUESTION
        it["route_kind"] = "external-block"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        reader, log = _doubt_reader(tmp)
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), env=_v_env(editor, fb, reader), timeout=90,
                         inputs=[
            ("[v] write in the editor", "v"),
            (ASK, ""),
            ("answer it again", None),
            ("[v] write in the editor", ""),
        ])
        plain = ANSI.sub("", out)
        check("CS-4 pty yes: decide exits 0", rc == 0, plain[-1500:])
        reqs = [r for r in _requests(log) if r.get("tarefa") == "reescrever-pergunta"]
        check("CS-4 pty yes: one rewrite request", len(reqs) == 1, reqs)
        if reqs:
            check("CS-4 pty yes: the request carries the editor text as the doubt",
                  reqs[0].get("duvida_do_dono") == typed, reqs[0])
        check("CS-4 pty yes: the new question shows in the same item block",
              NEW_Q in plain.split("badly written", 1)[-1]
              and plain.count("· b1") == 1, plain)
        now = {i["id"]: i for i in yaml.safe_load(qfile.read_text())["items"]}["b1"]
        check("CS-4 pty yes: new question recorded, no answer, no doubt text on the item",
              now.get("owner_question") == NEW_Q and now.get("status") == "pending"
              and typed not in qfile.read_text() and "answered now 0" in plain, now)
        lines = _ledger(fb)
        check("CS-4 pty yes: one feedback line with id, question and doubt",
              len(lines) == 1 and "b1" in lines[0].get("texto", "")
              and QUESTION in lines[0].get("texto", "")
              and typed in lines[0].get("texto", ""), lines)
        assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_v_doubt_with_yes_unit_reader_gets_the_doubt_and_nothing_is_answered():
    failed_before = len(FAILURES)
    m = load_module()
    m.edit_in_editor = lambda *a, **k: DOUBT
    marks, rewrites, answers, it = [], [], [], iter(["v", "", ""])
    m.decide(Path("/nao/existe"), "fila", None, {}, [_deferred()], {},
             question=lambda _p: next(it, ""), output=lambda *_: None,
             answer=lambda ident, text, **k: answers.append(text) or (0, "ok"),
             unclear=lambda ident, text, doubt="": marks.append((ident, text, doubt))
             or (0, "ok"),
             rewrite=lambda ad, text, doubt="": rewrites.append((text, doubt))
             or (NEW, None))
    check("CS-4 unit yes: the rewrite got the question and the editor text",
          rewrites == [(QUESTION, DOUBT)], rewrites)
    check("CS-4 unit yes: the feedback mark got the editor text",
          marks == [("b1", QUESTION, DOUBT)], marks)
    check("CS-4 unit yes: no answer recorded", answers == [], answers)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


SEND_BACK = "Send the item back to the queue with that answer? [y/N]"


def _w_session(typed, then):
    """`w` + `typed`, then the `then` inputs; returns (rc, plain output, queue
    file bytes before, after)."""
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        it = item("b1", status="pending", human_pending="falta escolher a variante")
        it["owner_question"] = QUESTION
        it["route_kind"] = "external-block"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = qfile.read_bytes()
        env = dict(os.environ, CEPA_FEEDBACK_DIR=fb, CEPA_RUN_READER="off")
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), env=env, timeout=30, inputs=[
            ("[w] I write the answer", "w"),
            ("Your answer, in one line", typed),
            *then,
        ])
        return rc, ANSI.sub("", out), before, qfile.read_bytes()


def test_n_at_the_doubt_prompt_goes_to_send_back_and_n_keeps_the_item():
    """`n` is not yes: the text is treated as an answer and the usual
    "Send the item back" question comes. `n` there too: as for any `w` answer, the
    text is recorded and the item stays where it was (CS-3 made it record; it
    recorded nothing in the interim build)."""
    import yaml
    failed_before = len(FAILURES)
    rc, plain, before, after = _w_session(DOUBT, [(ASK, "n"), (SEND_BACK, "n")])
    check("CS-1 pty n: decide exits 0", rc == 0, plain[-1500:])
    check("CS-1 pty n: the doubt prompt is shown", ASK in plain, plain[-1500:])
    check("CS-1 pty n: after `n` comes the send-back question",
          SEND_BACK in plain, plain[-1500:])
    now = {i["id"]: i for i in yaml.safe_load(after)["items"]}["b1"]
    check("CS-3 pty n+n: the text is recorded and the item is not sent back",
          DOUBT in str(now.get("evidence")) and now.get("status") == "pending"
          and "not recorded" not in plain, (now, plain[-800:]))
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_ordinary_text_in_w_does_not_show_the_doubt_prompt():
    failed_before = len(FAILURES)
    rc, plain, before, after = _w_session("variante B", [(SEND_BACK, "n")])
    check("CS-1 pty plain: decide exits 0", rc == 0, plain[-1500:])
    check("CS-1 pty plain: no doubt prompt", ASK not in plain, plain[-1500:])
    check("CS-1 pty plain: goes straight to send-back",
          SEND_BACK in plain, plain[-1500:])
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_punctuation_only_text_in_w_does_not_show_the_doubt_prompt():
    failed_before = len(FAILURES)
    rc, plain, before, after = _w_session("...", [(SEND_BACK, "n")])
    check("CS-1 pty punct: decide exits 0", rc == 0, plain[-1500:])
    check("CS-1 pty punct: no doubt prompt", ASK not in plain, plain[-1500:])
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_looks_like_doubt_survives_cepa_queue_exiting_with_2():
    """`cepa-queue` does sys.exit(2) without PyYAML: the panel must not die."""
    from importlib.machinery import SourceFileLoader
    from importlib.util import module_from_spec, spec_from_loader
    loader = SourceFileLoader("cepa_run_doubt", str(CEPA_UNTIL))
    mod = module_from_spec(spec_from_loader("cepa_run_doubt", loader))
    loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "cepa-queue"
        fake.write_text("import sys\nsys.exit(2)\n")
        old_plan = mod.CEPA_PLAN
        mod.CEPA_PLAN = fake
        mod._QUEUE_MODULE.clear()
        try:
            result = mod.looks_like_doubt("O que é?")
        finally:
            mod.CEPA_PLAN = old_plan
            mod._QUEUE_MODULE.clear()
    assert result is False, result


# ---- CS-2: yes at the doubt prompt rewrites the question with the doubt ----------

NEW_Q = "Você já escolheu qual versão do plano vai usar?"
NEW_YES = "O item volta para a fila e o próximo run usa a versão escolhida."
NEW_NO = "O item continua esperando a escolha."


def _doubt_reader(tmp):
    """Fake reader: logs every request it gets (as JSON, one per line) and answers
    a new closed question for the rewrite job."""
    script = Path(tmp) / "leitor.py"
    log = Path(tmp) / "leitor-pedidos.jsonl"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "it = json.load(sys.stdin)\n"
        f"open({str(log)!r}, 'a').write(json.dumps(it) + '\\n')\n"
        "if it.get('tarefa') == 'reescrever-pergunta':\n"
        f"    print(json.dumps({{'route_kind': 'owner-task', 'question': {NEW_Q!r},\n"
        f"        'if_yes': {NEW_YES!r}, 'if_no': {NEW_NO!r}, 'item_se_nao': 'nenhum'}}))\n"
        "else:\n"
        "    print(json.dumps({'tipo': None}))\n")
    script.chmod(0o755)
    return script, log


def _requests(log):
    import json
    if not Path(log).exists():
        return []
    return [json.loads(l) for l in Path(log).read_text().splitlines() if l.strip()]


def _ledger(d):
    import json
    out = []
    for f in sorted(Path(d).glob("feedback-*.jsonl")):
        out += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return out


def test_yes_at_the_doubt_prompt_rewrites_the_question_with_the_doubt():
    """Red test of CS-2, as a process in a pseudo-terminal."""
    import yaml
    failed_before = len(FAILURES)
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        it = item("b1", status="pending", human_pending="falta escolher a variante")
        it["owner_question"] = QUESTION
        it["route_kind"] = "external-block"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        reader, log = _doubt_reader(tmp)
        env = dict(os.environ, CEPA_FEEDBACK_DIR=fb, CEPA_RUN_READER=str(reader))
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), env=env, timeout=90, inputs=[
            ("[w] I write the answer", "w"),
            ("Your answer, in one line", DOUBT),
            (ASK, ""),
            ("answer it again", None),
            ("[w] I write the answer", ""),
        ])
        plain = ANSI.sub("", out)
        check("CS-2 pty: decide exits 0", rc == 0, plain[-1500:])
        reqs = [r for r in _requests(log) if r.get("tarefa") == "reescrever-pergunta"]
        check("CS-2 pty: the reader got one rewrite request", len(reqs) == 1, reqs)
        if reqs:
            check("CS-2 pty: the request carries the doubt",
                  reqs[0].get("duvida_do_dono") == DOUBT, reqs[0])
            check("CS-2 pty: the request carries the question shown",
                  reqs[0].get("pergunta_mal_escrita") == QUESTION, reqs[0])
        tail = plain.split("answer it again", 1)[-1]
        check("CS-2 pty: the new question shows after the rewrite", NEW_Q in plain.split(
            "badly written", 1)[-1], plain)
        check("CS-2 pty: same block, the item header shows once",
              plain.count("· b1") == 1, plain)
        check("CS-2 pty: the panel asks for the answer again",
              "[w] I write the answer" in tail, tail)
        check("CS-2 pty: no 'Send the item back' question for the doubt",
              "Send the item back to the queue with that answer?" not in plain, plain)
        now = {i["id"]: i for i in yaml.safe_load(qfile.read_text())["items"]}["b1"]
        check("CS-2 pty: queue.yaml has the new question and no doubt text",
              now.get("owner_question") == NEW_Q and DOUBT not in qfile.read_text(), now)
        check("CS-2 pty: the item is still without answer",
              now.get("status") == "pending" and "answered now 0" in plain
              and "for later 1" in plain, plain[-1500:])
        lines = _ledger(fb)
        check("CS-2 pty: one feedback line", len(lines) == 1, lines)
        if lines:
            txt = lines[0].get("texto", "")
            check("CS-2 pty: feedback has item id, question and doubt",
                  "b1" in txt and QUESTION in txt and DOUBT in txt, txt)
        assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def _deferred(**kw):
    d = {"id": "b1", "title": "t", "reason": "human_pending",
         "human_pending": "falta escolher a variante", "question": QUESTION,
         "evidence": "x", "route_kind": "external-block"}
    d.update(kw)
    return d


NEW = {"route_kind": "owner-task", "question": NEW_Q, "if_yes": NEW_YES,
       "if_no": NEW_NO}


def _inject(replies, deferred=None, rewrite=None):
    """`decide` with injected unclear/rewrite that record what they receive."""
    m = load_module()
    screen, marks, rewrites, answers = [], [], [], []
    it = iter(replies)

    def unclear(ident, text, doubt=""):
        marks.append((ident, text, doubt))
        return 0, "ok"

    def rw(ad, text, doubt=""):
        rewrites.append((text, doubt))
        return (NEW, None) if rewrite is None else rewrite

    _, later = m.decide(Path("/nao/existe"), "fila", None, {}, deferred or [_deferred()],
                        {}, question=lambda _p: next(it, ""), output=screen.append,
                        answer=lambda ident, text, **k: answers.append(text) or (0, "ok"),
                        unclear=unclear, rewrite=rw)
    return "\n".join(screen), later, marks, rewrites, answers


def test_doubt_goes_to_the_rewrite_and_to_the_feedback_mark():
    failed_before = len(FAILURES)
    text, later, marks, rewrites, answers = _inject(["w", DOUBT, "", ""])
    check("CS-2 unit: rewrite got the question and the doubt",
          rewrites == [(QUESTION, DOUBT)], rewrites)
    check("CS-2 unit: the feedback mark got the doubt",
          marks == [("b1", QUESTION, DOUBT)], marks)
    check("CS-2 unit: no answer recorded", answers == [], answers)
    check("CS-2 unit: the new question shows in the same panel",
          NEW_Q in text and text.count(QUESTION) >= 1, text)
    check("CS-2 unit: the item is left for later", len(later) == 1, later)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_answering_the_new_question_records_the_new_text_not_the_doubt():
    failed_before = len(FAILURES)
    _, later, _, rewrites, answers = _inject(["w", DOUBT, "", "y", ""])
    check("CS-2 unit: answered after the rewrite",
          len(answers) == 1 and NEW_Q in answers[0] and DOUBT not in answers[0], answers)
    check("CS-2 unit: nothing left for later", later == [], later)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_plain_question_mark_sends_no_doubt():
    failed_before = len(FAILURES)
    _, _, marks, rewrites, _ = _inject(["?", ""])
    check("CS-2 unit: `?` rewrite has no doubt", rewrites == [(QUESTION, "")], rewrites)
    check("CS-2 unit: `?` mark has no doubt", marks == [("b1", QUESTION, "")], marks)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_n_at_the_doubt_prompt_does_not_call_the_rewrite():
    failed_before = len(FAILURES)
    _, _, marks, rewrites, _ = _inject(["w", DOUBT, "n", "n"])
    check("CS-2 unit: `n` calls no rewrite and no mark", rewrites == [] and marks == [],
          (rewrites, marks))
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_doubt_after_a_rewrite_does_not_call_the_reader_again():
    """Today's limit stays: one rewrite per item, whatever key triggered it."""
    failed_before = len(FAILURES)
    text, later, marks, rewrites, answers = _inject(["?", "w", DOUBT, ""])
    check("CS-2 unit: the reader ran once", len(rewrites) == 1, rewrites)
    check("CS-2 unit: the doubt reached the feedback mark",
          marks == [("b1", QUESTION, ""), ("b1", NEW_Q, DOUBT)], marks)
    check("CS-2 unit: says it is not rewritten again", "not rewritten again" in text, text)
    check("CS-2 unit: no answer, item for later", answers == [] and len(later) == 1,
          (answers, later))
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_failed_rewrite_with_a_doubt_leaves_the_item_for_later():
    failed_before = len(FAILURES)
    text, later, marks, rewrites, answers = _inject(
        ["w", DOUBT, ""], rewrite=(None, "reader off"))
    check("CS-2 unit: doubt reached the mark", marks == [("b1", QUESTION, DOUBT)], marks)
    check("CS-2 unit: failure line", "question not rewritten" in text, text)
    check("CS-2 unit: no answer, item for later", answers == [] and len(later) == 1,
          (answers, later))
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_default_rewrite_puts_the_doubt_in_the_reader_payload():
    failed_before = len(FAILURES)
    m = load_module()
    reads, screen = [], []
    m.read_route = lambda repo, payload, deadline, prompt=None: (
        reads.append(payload) or (NEW, None))
    m.reword_route = lambda *a, **k: None
    replies = iter(["w", DOUBT, "", ""])
    m.decide(Path("/nao/existe"), "fila", None, {}, [_deferred()], {},
             question=lambda _p: next(replies, ""), output=screen.append,
             answer=lambda *a, **k: (0, "ok"),
             unclear=lambda ident, text, doubt="": (0, "ok"))
    check("CS-2 payload: one read with the doubt next to the bad question",
          len(reads) == 1 and reads[0].get("duvida_do_dono") == DOUBT
          and reads[0].get("pergunta_mal_escrita") == QUESTION, reads)
    reads.clear()
    replies = iter(["?", ""])
    m.decide(Path("/nao/existe"), "fila", None, {}, [_deferred()], {},
             question=lambda _p: next(replies, ""), output=screen.append,
             answer=lambda *a, **k: (0, "ok"),
             unclear=lambda ident, text, doubt="": (0, "ok"))
    check("CS-2 payload: `?` alone has no doubt field",
          len(reads) == 1 and "duvida_do_dono" not in reads[0], reads)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_item_without_open_route_sends_the_doubt_to_feedback_and_waits():
    """No open route (default rewrite): the reader is not called, the doubt is in the
    feedback line, nothing is answered, the item stays for later."""
    failed_before = len(FAILURES)
    m = load_module()
    reads, screen, marks = [], [], []
    m.read_route = lambda *a, **k: reads.append(a) or (NEW, None)
    replies = iter(["w", DOUBT, ""])
    _, later = m.decide(
        Path("/nao/existe"), "fila", None, {}, [_deferred(human_pending=None)], {},
        question=lambda _p: next(replies, ""), output=screen.append,
        answer=lambda *a, **k: marks.append("answered") or (0, "ok"),
        unclear=lambda ident, text, doubt="": marks.append(doubt) or (0, "ok"))
    check("CS-2 no route: the reader was not called", reads == [], reads)
    check("CS-2 no route: the doubt went to the feedback mark and nothing was answered",
          marks == [DOUBT], marks)
    check("CS-2 no route: the item stays for later", len(later) == 1, later)
    check("CS-2 no route: the screen says why", "no open route" in " ".join(" ".join(screen).split()),
          screen)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_default_feedback_line_carries_the_doubt():
    failed_before = len(FAILURES)
    with tempfile.TemporaryDirectory() as fb:
        m = load_module()
        os.environ["CEPA_FEEDBACK_DIR"] = fb
        try:
            replies = iter(["w", DOUBT, ""])
            m.decide(Path(fb), "fila", None, {}, [_deferred(human_pending=None)], {},
                     question=lambda _p: next(replies, ""), output=lambda *_: None,
                     answer=lambda *a, **k: (0, "ok"))
        finally:
            del os.environ["CEPA_FEEDBACK_DIR"]
        lines = _ledger(fb)
        check("CS-2 ledger: one line with item, question and doubt",
              len(lines) == 1 and all(x in lines[0].get("texto", "")
                                      for x in ("b1", QUESTION, DOUBT)), lines)
        check("CS-2 ledger: the label is followed by the doubt text",
              len(lines) == 1 and f"dúvida do dono: {DOUBT}" in lines[0].get("texto", ""),
              lines)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_default_feedback_line_for_plain_question_mark_has_no_doubt_label():
    failed_before = len(FAILURES)
    with tempfile.TemporaryDirectory() as fb:
        m = load_module()
        os.environ["CEPA_FEEDBACK_DIR"] = fb
        try:
            replies = iter(["?", ""])
            m.decide(Path(fb), "fila", None, {}, [_deferred(human_pending=None)], {},
                     question=lambda _p: next(replies, ""), output=lambda *_: None,
                     answer=lambda *a, **k: (0, "ok"))
        finally:
            del os.environ["CEPA_FEEDBACK_DIR"]
        lines = _ledger(fb)
        check("CS-2 ledger: plain `?` writes one line without the doubt label",
              len(lines) == 1 and "b1" in lines[0].get("texto", "")
              and "dúvida do dono" not in lines[0].get("texto", ""), lines)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def _calls(replies, editor_text=None):
    """`decide` with an injected `answer` that records every call with its keyword
    arguments (`keep`, `force`...): a list of (text, kwargs)."""
    m = load_module()
    calls, it = [], iter(replies)
    if editor_text is not None:
        m.edit_in_editor = lambda *a, **k: editor_text
    m.decide(Path("/nao/existe"), "fila", None, {}, [_deferred()], {},
             question=lambda _p: next(it, ""), output=lambda *_: None,
             answer=lambda ident, text, **k: calls.append((text, k)) or (0, "ok"),
             unclear=lambda *a, **k: (0, "ok"),
             rewrite=lambda *a, **k: (None, "no"))
    return calls


def test_n_at_the_doubt_prompt_then_y_records_the_text_with_force():
    """CS-3, unit: the owner's `n` is what authorizes the record, so `force` goes
    to the answer, and the text is the typed one."""
    failed_before = len(FAILURES)
    calls = _calls(["w", DOUBT, "n", "y"])
    check("CS-3 unit: one answer, with the typed text and force",
          len(calls) == 1 and calls[0][0] == DOUBT and calls[0][1].get("force") is True,
          calls)
    check("CS-3 unit: `y` sends the item back (no keep)",
          calls and not calls[0][1].get("keep"), calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_n_at_the_doubt_prompt_then_n_keeps_the_item_with_force():
    """`n` at "Send the item back" is today's keep-the-item answer; the text was
    already cleared by the owner, so force goes along."""
    failed_before = len(FAILURES)
    calls = _calls(["w", DOUBT, "n", "n"])
    check("CS-3 unit n+n: recorded with keep and force",
          len(calls) == 1 and calls[0][0] == DOUBT
          and calls[0][1].get("keep") is True and calls[0][1].get("force") is True,
          calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_ordinary_text_is_answered_without_force():
    failed_before = len(FAILURES)
    calls = _calls(["w", "variante B", "y"])
    check("CS-3 unit: ordinary text, no force",
          len(calls) == 1 and calls[0][0] == "variante B"
          and not calls[0][1].get("force"), calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_punctuation_only_text_is_answered_without_force():
    """Never went through the doubt prompt: the refusal stays (CS-8)."""
    failed_before = len(FAILURES)
    calls = _calls(["w", "...", "y"])
    check("CS-3 unit: punctuation-only text, no force",
          len(calls) == 1 and calls[0][0] == "..." and not calls[0][1].get("force"),
          calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_v_text_is_answered_without_force():
    """CS-4: ORDINARY `v` text never meets the doubt prompt, so no force (before
    CS-4 this case used the doubt text DOUBT, which now meets the prompt)."""
    failed_before = len(FAILURES)
    calls = _calls(["v", "y"], editor_text="variante B")
    check("CS-3 unit: `v` text, no force",
          len(calls) == 1 and calls[0][0] == "variante B" and not calls[0][1].get("force"),
          calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_v_doubt_text_then_n_then_y_records_the_text_with_force():
    failed_before = len(FAILURES)
    calls = _calls(["v", "n", "y"], editor_text=DOUBT)
    check("CS-4 unit v n+y: one answer, the editor text, with force, sent back",
          len(calls) == 1 and calls[0][0] == DOUBT and calls[0][1].get("force") is True
          and not calls[0][1].get("keep"), calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_v_doubt_text_then_n_then_n_keeps_the_item_with_force():
    failed_before = len(FAILURES)
    calls = _calls(["v", "n", "n"], editor_text=DOUBT)
    check("CS-4 unit v n+n: recorded with keep and force",
          len(calls) == 1 and calls[0][0] == DOUBT
          and calls[0][1].get("keep") is True and calls[0][1].get("force") is True,
          calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_v_ordinary_text_does_not_show_the_doubt_prompt_and_has_no_force():
    failed_before = len(FAILURES)
    for reply, keep in (("y", False), ("n", True)):
        shown = []
        m = load_module()
        m.edit_in_editor = lambda *a, **k: "variante B"
        calls, it = [], iter(["v", reply])
        m.decide(Path("/nao/existe"), "fila", None, {}, [_deferred()], {},
                 question=lambda p: shown.append(p) or next(it, ""),
                 output=lambda *_: None,
                 answer=lambda ident, text, **k: calls.append((text, k)) or (0, "ok"))
        check(f"CS-4 unit v ordinary {reply}: no doubt prompt",
              not any("doubt about the question" in str(p) for p in shown), shown)
        check(f"CS-4 unit v ordinary {reply}: answered, no force",
              len(calls) == 1 and calls[0][0] == "variante B"
              and "force" not in calls[0][1]
              and bool(calls[0][1].get("keep")) == keep, calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_v_empty_editor_asks_nothing_and_records_nothing():
    failed_before = len(FAILURES)
    shown = []
    m = load_module()
    m.edit_in_editor = lambda *a, **k: ""
    calls, it, screen = [], iter(["v", ""]), []
    m.decide(Path("/nao/existe"), "fila", None, {}, [_deferred()], {},
             question=lambda p: shown.append(p) or next(it, ""),
             output=screen.append,
             answer=lambda ident, text, **k: calls.append((text, k)) or (0, "ok"))
    check("CS-4 unit v empty: no doubt prompt, no send-back, nothing recorded",
          calls == [] and not any("doubt about the question" in str(p)
                                  or "Send the item back" in str(p) for p in shown),
          (calls, shown))
    check("CS-4 unit v empty: the same menu comes back with the editor message",
          "nothing written in the editor" in "\n".join(screen)
          and len(shown) == 2, (shown, screen))
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_ordinary_text_kept_with_n_is_answered_with_keep_and_without_force():
    failed_before = len(FAILURES)
    calls = _calls(["w", "variante B", "n"])
    check("CS-3 unit: ordinary text + n, keep and no force",
          len(calls) == 1 and calls[0][0] == "variante B"
          and calls[0][1].get("keep") is True and "force" not in calls[0][1], calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_punctuation_only_text_kept_with_n_is_answered_with_keep_and_without_force():
    failed_before = len(FAILURES)
    calls = _calls(["w", "...", "n"])
    check("CS-3 unit: punctuation-only text + n, keep and no force",
          len(calls) == 1 and calls[0][0] == "..."
          and calls[0][1].get("keep") is True and "force" not in calls[0][1], calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_v_text_kept_with_n_is_answered_with_keep_and_without_force():
    """CS-4: with ORDINARY `v` text (the doubt text now meets the prompt)."""
    failed_before = len(FAILURES)
    calls = _calls(["v", "n"], editor_text="variante B")
    check("CS-3 unit: `v` text + n, keep and no force",
          len(calls) == 1 and calls[0][0] == "variante B"
          and calls[0][1].get("keep") is True and "force" not in calls[0][1], calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_force_does_not_leak_to_the_next_item():
    failed_before = len(FAILURES)
    m = load_module()
    calls, it = [], iter(["w", DOUBT, "n", "y", "w", "variante B", "y"])
    m.decide(Path("/nao/existe"), "fila", None, {},
             [_deferred(), _deferred(id="b2", question="Outra pergunta?")], {},
             question=lambda _p: next(it, ""), output=lambda *_: None,
             answer=lambda ident, text, **k: calls.append((text, k)) or (0, "ok"))
    check("CS-3 unit: force only on the first item",
          len(calls) == 2 and calls[0][1].get("force") is True
          and not calls[1][1].get("force"), calls)
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_n_at_the_doubt_prompt_then_y_records_the_answer_in_the_panel():
    """Red test of CS-3, as a process in a pseudo-terminal."""
    import yaml
    failed_before = len(FAILURES)
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        it = item("b1", status="pending", human_pending="falta escolher a variante")
        it["owner_question"] = QUESTION
        it["route_kind"] = "external-block"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        env = dict(os.environ, CEPA_FEEDBACK_DIR=fb, CEPA_RUN_READER="off")
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), env=env, timeout=30, inputs=[
            ("[w] I write the answer", "w"),
            ("Your answer, in one line", DOUBT),
            (ASK, "n"),
            (SEND_BACK, "y"),
        ])
        plain = ANSI.sub("", out)
        now = {i["id"]: i for i in yaml.safe_load(qfile.read_text())["items"]}["b1"]
        check("CS-3 pty: decide exits 0", rc == 0, plain[-1500:])
        check("CS-3 pty: the typed text is in the evidence as the owner's answer",
              f"Resposta do dono em" in str(now.get("evidence"))
              and DOUBT in str(now.get("evidence")), now)
        check("CS-3 pty: the screen shows the recorded confirmation",
              "not recorded" not in plain and "answered now 1" in plain, plain[-1500:])
        check("CS-3 pty: no question between `n` and the send-back one",
              plain.count("[Y/n]") == 1, plain[-1500:])
        assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_v_doubt_then_n_then_y_records_the_editor_text_through_the_real_answer():
    """CS-4, "no" outcome, as a process in a pseudo-terminal and with the real
    `cepa-queue answer`: the editor text is recorded as the owner's answer."""
    import yaml
    failed_before = len(FAILURES)
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        editor = _fake_editor(tmp, "não entendi a pergunta")
        it = item("b1", status="pending", human_pending="falta escolher a variante")
        it["owner_question"] = QUESTION
        it["route_kind"] = "external-block"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), env=_v_env(editor, fb), timeout=30, inputs=[
            ("[v] write in the editor", "v"),
            (ASK, "n"),
            (SEND_BACK, "y"),
        ])
        plain = ANSI.sub("", out)
        now = {i["id"]: i for i in yaml.safe_load(qfile.read_text())["items"]}["b1"]
        check("CS-4 pty v n y: decide exits 0", rc == 0, plain[-1500:])
        check("CS-4 pty v n y: the editor text is in the evidence as the owner's answer",
              "Resposta do dono em" in str(now.get("evidence"))
              and "não entendi a pergunta" in str(now.get("evidence")), now)
        check("CS-4 pty v n y: the screen shows the recorded confirmation",
              "answered now 1" in plain, plain[-1500:])
        check("CS-4 pty v n y: nothing is refused as 'not recorded'",
              "not recorded" not in plain, plain[-1500:])
        assert len(FAILURES) == failed_before, FAILURES[failed_before:]


def test_punctuation_only_text_is_still_refused_by_the_panel():
    failed_before = len(FAILURES)
    rc, plain, before, after = _w_session("...", [(SEND_BACK, "y")])
    check("CS-3 pty punct: refused as before", "not recorded" in plain
          and "resposta recusada" in plain, plain[-1500:])
    check("CS-3 pty punct: queue.yaml is byte-identical", after == before, "")
    assert len(FAILURES) == failed_before, FAILURES[failed_before:]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print(f"\n{len(FAILURES)} FAIL" if FAILURES else "\ntudo verde")
    sys.exit(1 if FAILURES else 0)
