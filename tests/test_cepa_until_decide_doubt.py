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
from test_cepa_until_decide import ANSI, FAILURES, check, on_tty  # noqa: E402

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


def test_doubt_typed_through_v_does_not_show_the_new_prompt_yet():
    """`v` is CS-4, a later item: today `v` still goes straight to the
    "Send the item back" prompt."""
    failed_before = len(FAILURES)
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        editor = Path(tmp) / "fake-editor.sh"
        editor.write_text(f"#!/bin/sh\nprintf '%s' '{DOUBT}' > \"$1\"\n")
        editor.chmod(0o755)
        it = item("b1", status="pending", human_pending="falta escolher a variante")
        it["owner_question"] = QUESTION
        it["route_kind"] = "external-block"
        root = build_repo(tmp, [it])
        env = {k: v for k, v in os.environ.items() if k not in ("VISUAL", "EDITOR")}
        env.update(CEPA_FEEDBACK_DIR=fb, CEPA_RUN_READER="off", EDITOR=str(editor))
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), env=env, timeout=30, inputs=[
            ("[v] write in the editor", "v"),
            ("Send the item back to the queue", "n"),
        ])
        plain = ANSI.sub("", out)
        check("CS-1 pty v: decide exits 0", rc == 0, plain[-1500:])
        check("CS-1 pty v: the new prompt is not shown for v yet",
              ASK not in plain, plain[-1500:])
        assert len(FAILURES) == failed_before, FAILURES[failed_before:]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print(f"\n{len(FAILURES)} FAIL" if FAILURES else "\ntudo verde")
    sys.exit(1 if FAILURES else 0)
