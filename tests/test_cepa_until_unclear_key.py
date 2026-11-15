#!/usr/bin/env python3
"""CS-6 of docs/spec/perguntas-da-largada-legiveis.md: the `?` key ("I don't
understand the question") records the question as badly written, in the global
feedback ledger (`cepa-feedback add`, target `cepa-until`), with the item id and
the question text, and records NO answer on the item. Before, the panel answered
that `?` is not one of the options.

Its own file so the proof gate can run it alone:
`python3 tests/test_cepa_until_unclear_key.py`, exit 1 on any failure.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import CEPA_UNTIL, build_repo, item  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    ANSI, FAILURES, check, load_module, on_tty)

QUESTION = "A chave do cofre já existe?"


def _ledger_lines(d):
    lines = []
    for f in sorted(Path(d).glob("feedback-*.jsonl")):
        lines += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return lines


def test_question_mark_on_terminal_records_feedback_and_leaves_item():
    """Red test of CS-6, as a process in a pseudo-terminal: pressing `?` on a panel
    question leaves the item byte for byte in `queue.yaml` and appends one line to
    the feedback ledger with target `cepa-until`, the item id and the question."""
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        it = item("b1", status="pending", human_pending="falta a chave do cofre")
        it["owner_question"] = QUESTION
        it["route_kind"] = "external-block"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = qfile.read_bytes()
        # CS-7 rewrites the question after `?`; this case is about the record
        # alone, so the reader is off (and a real `claude` never runs in a test).
        env = dict(os.environ, CEPA_FEEDBACK_DIR=fb, CEPA_UNTIL_LEITOR="off")
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), env=env,
                         inputs=[("[t] I write the answer", "?")], timeout=60)
        plain = ANSI.sub("", out)
        check("CS-6 pty: decide exits 0", rc == 0, plain[-1500:])
        check("CS-6 pty: `?` is not refused as 'not one of the options'",
              "is not one of the options" not in plain, plain)
        check("CS-6 pty: the menu offers `[?]`", "[?]" in plain, plain)
        check("CS-6 pty: the legend says what `?` does",
              any(l.strip("│ ").startswith("? = ") for l in plain.splitlines()), plain)
        check("CS-6 pty: the queue file is unchanged", qfile.read_bytes() == before,
              qfile.read_text())
        lines = _ledger_lines(fb)
        check("CS-6 pty: exactly one feedback line", len(lines) == 1, lines)
        if lines:
            ev = lines[0]
            check("CS-6 pty: target cepa-until", ev.get("alvo") == "cepa-until", ev)
            check("CS-6 pty: text carries the item id", "b1" in ev.get("texto", ""), ev)
            check("CS-6 pty: text carries the question",
                  QUESTION in ev.get("texto", ""), ev)
        check("CS-6 pty: the item stays for later, nothing answered",
              "answered now 0" in plain and "for later 1" in plain, plain[-1500:])


def test_question_mark_records_the_default_question_when_none_was_written():
    """A route with no written question shows a fixed question (CS-3/CS-5); `?`
    records THAT text, the one the owner saw."""
    m = load_module()
    calls, answers_given, screen = [], [], []
    deferred = [{"id": "x1", "title": "t", "reason": "human_pending",
                 "human_pending": "valide o login", "question": None, "evidence": ""}]
    replies = iter(["?"])
    m.decide(Path("/nao/existe"), "fila", None, {}, deferred, {},
             question=lambda _p: next(replies, ""), output=screen.append,
             answer=lambda *a, **k: answers_given.append(a) or (0, "ok"),
             unclear=lambda ident, text: calls.append((ident, text)) or (0, "ok"),
             rewrite=lambda ad, text: (None, "off"))
    text = "\n".join(screen)
    check("CS-6 text: no answer recorded", answers_given == [], answers_given)
    check("CS-6 text: one unclear record for x1", len(calls) == 1
          and calls[0][0] == "x1", calls)
    check("CS-6 text: the recorded text is the question shown",
          bool(calls) and calls[0][1].strip() in text, (calls, text))


def test_unclear_record_failure_is_said_not_swallowed():
    """If the feedback ledger refuses, the panel says the record failed; the item
    still gets no answer."""
    m = load_module()
    screen, answers_given = [], []
    deferred = [{"id": "b1", "title": "t", "reason": "human_pending",
                 "human_pending": "x", "question": QUESTION, "evidence": ""}]
    replies = iter(["?"])
    m.decide(Path("/nao/existe"), "fila", None, {}, deferred, {},
             question=lambda _p: next(replies, ""), output=screen.append,
             answer=lambda *a, **k: answers_given.append(a) or (0, "ok"),
             unclear=lambda ident, text: (2, "disco cheio"),
             rewrite=lambda ad, text: (None, "off"))
    text = "\n".join(screen)
    check("CS-6 text: failure is shown", "not recorded" in text
          and "disco cheio" in text, text)
    check("CS-6 text: still no answer", answers_given == [], answers_given)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print(f"\n{len(FAILURES)} FAIL" if FAILURES else "\ntudo verde")
    sys.exit(1 if FAILURES else 0)
