#!/usr/bin/env python3
"""CS-8 of docs/spec/perguntas-da-largada-legiveis.md: when the rewrite after `?`
fails (the reader does not answer within 60 seconds, errors out, or is off), or on
the second `?` of the same item, the screen says in one line that the question was
not rewritten and that the item stays for later, the panel moves on to the next item
and the closing lists the item under "for later".

Its own file so the proof gate can run it alone:
`python3 tests/test_cepa_until_unclear_fallback.py`, exit 1 on any failure.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import CEPA_UNTIL, build_repo, item  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    ANSI, FAILURES, check, load_module, on_tty)

OLD_Q = "A chave do cofre já existe?"
NEXT_Q = "O certificado do banco já chegou?"
NEW_Q = "Você já criou a senha do cofre que o sistema usa?"
NOT_REWRITTEN = "not rewritten"


def _hung_reader(tmp):
    """A fake reader that never answers the unclear-question job (sleeps past the
    60 s ceiling) and gives no finding for anything else."""
    script = Path(tmp) / "leitor.py"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys, time\n"
        "it = json.load(sys.stdin)\n"
        "if it.get('tarefa') == 'reescrever-pergunta':\n"
        "    time.sleep(300)\n"
        "print(json.dumps({'tipo': None}))\n")
    script.chmod(0o755)
    return script


def test_hung_reader_leaves_the_item_for_later_and_the_panel_goes_on():
    """Red test of CS-8, as a process in a pseudo-terminal: two items, the reader
    hangs on the first one's rewrite; within the ceiling the screen says the question
    was not rewritten and the item stays for later, the second item shows, and the
    closing lists the first under "for later"."""
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        b1 = item("b1", status="pending", human_pending="falta a chave do cofre")
        b1["owner_question"] = OLD_Q
        b1["route_kind"] = "external-block"
        b2 = item("b2", status="pending", human_pending="falta o certificado")
        b2["owner_question"] = NEXT_Q
        b2["route_kind"] = "external-block"
        root = build_repo(tmp, [b1, b2])
        env = dict(os.environ, CEPA_FEEDBACK_DIR=fb,
                   CEPA_RUN_READER=str(_hung_reader(tmp)))
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        start = time.monotonic()
        rc, out = on_tty(cmd, str(root), env=env,
                         inputs=[("[w] I write the answer", "?"),
                                 ("What did you not understand?", ""),
                                 ("[w] I write the answer", "")], timeout=120)
        took = time.monotonic() - start
        plain = ANSI.sub("", out)
        check("CS-8 pty: decide exits 0", rc == 0, plain[-1500:])
        check("CS-8 pty: the rewrite is cut at the 60 s ceiling",
              55 <= took <= 90, took)
        after_mark = plain.split("badly written", 1)[-1]
        line = next((l for l in after_mark.splitlines() if NOT_REWRITTEN in l), "")
        check("CS-8 pty: a line says the question was not rewritten",
              bool(line), after_mark)
        check("CS-8 pty: the same line says the item stays for later",
              "for later" in line, line)
        check("CS-8 pty: the panel goes on to the next item",
              NEXT_Q in after_mark.split(NOT_REWRITTEN, 1)[-1], after_mark)
        closing = plain.rsplit("closing", 1)[-1]
        check("CS-8 pty: the closing counts both for later",
              "answered now 0" in closing and "for later 2" in closing, closing)
        check("CS-8 pty: the closing lists b1 under for later",
              "○ b1, b2" in closing, closing)


def _run(replies, rewrite):
    m = load_module()
    screen, rewrites, marks = [], [], []
    deferred = [{"id": "b1", "title": "t", "reason": "human_pending",
                 "human_pending": "falta a chave do cofre", "question": OLD_Q,
                 "evidence": "x", "route_kind": "external-block"},
                {"id": "b2", "title": "t2", "reason": "human_pending",
                 "human_pending": "falta o certificado", "question": NEXT_Q,
                 "evidence": "y", "route_kind": "external-block"}]
    it = iter(replies)
    _, later = m.decide(Path("/nao/existe"), "fila", None, {}, deferred, {},
                        question=lambda _p: next(it, ""), output=screen.append,
                        answer=lambda *a, **k: (0, "ok"),
                        unclear=lambda ident, text: marks.append(text) or (0, "ok"),
                        rewrite=lambda ad, text: rewrites.append(text) or rewrite)
    return "\n".join(screen), later, rewrites, marks


def test_a_failed_rewrite_says_so_and_moves_on():
    """Any failure of the rewrite (ceiling, reader error, reader off) gives the line,
    leaves the item for later and the next item still asks."""
    text, later, rewrites, _ = _run(["?", "", ""], (None, "not read within the ceiling"))
    check("CS-8 fail: the reader ran once", len(rewrites) == 1, rewrites)
    head, _, tail = text.partition(NOT_REWRITTEN)
    check("CS-8 fail: the not-rewritten line shows", bool(tail), text)
    check("CS-8 fail: it shows before the next item", NEXT_Q in tail, text)
    check("CS-8 fail: no 'rewritten and recorded' line",
          "question rewritten" not in text, text)
    check("CS-8 fail: b1 for later, b2 for later (Enter)",
          [x.split(":")[0] for x in later] == ["b1", "b2"], later)


def test_second_question_mark_says_so_and_moves_on():
    """The second `?` on the same item does not call the reader again; the screen
    says the question will not be rewritten again and the item stays for later."""
    new = {"route_kind": "owner-task", "question": NEW_Q, "if_yes": "volta",
           "if_no": "espera"}
    # the second `?` asks the optional line (CS-6) and gets an empty Enter; the
    # last Enter is the next item's menu
    text, later, rewrites, marks = _run(["?", "", "?", "", ""], (new, None))
    check("CS-8 second: the reader ran once", len(rewrites) == 1, rewrites)
    check("CS-8 second: both `?` recorded", marks == [OLD_Q, NEW_Q], marks)
    tail = text.split("question rewritten", 1)[-1]
    line = next((l for l in tail.splitlines() if NOT_REWRITTEN in l), "")
    check("CS-8 second: a line says it is not rewritten again",
          bool(line) and "for later" in line, tail)
    check("CS-8 second: the next item still asks",
          NEXT_Q in tail.split(NOT_REWRITTEN, 1)[-1], tail)
    check("CS-8 second: b1 for later", later and later[0].startswith("b1"), later)


def test_a_hostile_failure_reason_reaches_the_screen_as_one_safe_line():
    """The reason may be raw output of `cepa-queue reword-route`: terminal control
    sequences (clear screen, window title, NUL) never reach the screen raw, and a
    long reason is cut to one bounded line (proof L4 of CS-8)."""
    hostile = ("recusado\x1b[2J\x1b]0;pwned\x07\x00\r\nlinha nova " + "A" * 5000)
    text, later, _, _ = _run(["?", "", ""], (None, hostile))
    line = next((l for l in text.splitlines() if NOT_REWRITTEN in l), "")
    check("CS-8 hostile: the line shows", bool(line), text)
    check("CS-8 hostile: no control character on the screen",
          not any(ch in text for ch in "\x1b\x07\x00\r"), repr(text[:400]))
    flat = "".join(text.split())  # the panel wraps; joined, the A run is whole
    check("CS-8 hostile: the reason shows, cut to a bounded length",
          "recusado" in flat and "A" * 150 in flat and "A" * 300 not in flat,
          flat[:400])
    check("CS-8 hostile: the panel goes on",
          NEXT_Q in text.split(NOT_REWRITTEN, 1)[-1]
          and [x.split(":")[0] for x in later] == ["b1", "b2"], later)


def test_the_closing_names_each_item_left_for_later():
    """The closing lists the items left for later by name, not only their count."""
    text, later, _, _ = _run(["?", "", ""], (None, "reader exited 1"))
    closing = text.rsplit("Answered now", 1)[-1]
    check("CS-8 closing: both items named on the for-later line",
          "○ b1, b2" in closing, closing)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print(f"\n{len(FAILURES)} FAIL" if FAILURES else "\ntudo verde")
    sys.exit(1 if FAILURES else 0)
