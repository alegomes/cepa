#!/usr/bin/env python3
"""CS-2 of docs/spec/perguntas-da-largada-legiveis.md: a route recorded with a kind
(`route_kind`, written by `cepa-plan finish --route-kind`, CS-1) shows up in the
panel with the label of its kind beside the route text, and with the question the
agent wrote. Before, the label was always "Task", whatever the route was.

Labels (spec, "Decided without asking"): owner-task -> "Task for you",
external-block -> "Blocked outside", open-question -> "Open question". A route with
no kind keeps the old label.

Its own file so the proof gate can run it alone:
`python3 tests/test_cepa_until_route_kind_label.py`, exit 1 on any failure.
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import CEPA_UNTIL, build_repo, item  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    ANSI, FAILURES, check, load_module, on_tty)


def _routed(ident, status, kind, route, question):
    it = item(ident, status=status, human_pending=route)
    it["owner_question"] = question
    if kind is not None:
        it["route_kind"] = kind
    return it


def test_decide_on_terminal_labels_each_route_by_its_kind():
    """Red test of CS-2, as a process in a pseudo-terminal: `cepa-until decide fila`
    over an `external-block` item shows "Blocked outside" beside the route text and
    the recorded question. The other two kinds, and a delivered (`done`) item, get
    their own label and their own question too."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [
            _routed("b1", "pending", "external-block", "falta a chave do cofre",
                    "A chave do cofre já existe?"),
            _routed("q1", "pending", "open-question", "de onde vem o número",
                    "O número vem da guia?"),
            _routed("o1", "done", "owner-task", "criar o papel no portal",
                    "Já criei o papel no portal?"),
            _routed("x1", "pending", None, "valide o login real", None),
        ])
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), inputs=[
            ("[w] I write the answer", ""), ("[w] I write the answer", ""),
            ("[w] I write the answer", ""), ("[w] I write the answer", "")])
        plain = ANSI.sub("", out)
        lines = plain.splitlines()

        def beside(label, text):
            return any(label in l and text in l for l in lines)
        check("CS-2 pty: decide exits 0", rc == 0, plain[-1500:])
        check("CS-2 pty: external-block shows 'Blocked outside' beside the route",
              beside("Blocked outside", "falta a chave do cofre"), plain)
        check("CS-2 pty: ...and the question the agent recorded",
              "A chave do cofre já existe?" in plain, plain)
        check("CS-2 pty: open-question shows 'Open question' beside the route",
              beside("Open question", "de onde vem o número"), plain)
        check("CS-2 pty: ...and its question", "O número vem da guia?" in plain, plain)
        check("CS-2 pty: a delivered owner-task shows 'Task for you' and its question",
              beside("Task for you", "criar o papel no portal")
              and "Já criei o papel no portal?" in plain, plain)
        check("CS-2 pty: no typed route is labelled with the bare 'Task' column",
              not any(re.match(r"Task {2,}", l.lstrip("│ ")) and
                      any(t in l for t in ("falta a chave", "de onde vem",
                                           "criar o papel"))
                      for l in lines), plain)
        check("CS-2 pty: a route with no kind gets 'Left for you' (CS-5)",
              beside("Left for you", "valide o login real")
              and not beside("Task", "valide o login real")
              and not beside("Blocked outside", "valide o login real"), plain)


def test_decide_without_terminal_names_the_kind_too():
    """Outside a terminal the panel prints `label: text`; the label is the kind's."""
    m = load_module()
    screen = []
    deferred = [
        {"id": "b1", "title": "t", "reason": "human_pending",
         "human_pending": "falta a chave do cofre", "route_kind": "external-block",
         "question": "A chave do cofre já existe?", "evidence": ""},
        {"id": "x1", "title": "t", "reason": "human_pending",
         "human_pending": "valide o login", "question": None, "evidence": ""},
    ]
    answers = iter(["", ""])
    m.decide(Path("/nao/existe"), "fila", None, {}, deferred, {},
             question=lambda _p: next(answers, ""), output=screen.append,
             answer=lambda i, t, keep=False, drop=False: (0, "ok"))
    text = "\n".join(screen)
    check("CS-2 text: 'Blocked outside: <route>'",
          "Blocked outside: falta a chave do cofre" in text, text)
    check("CS-2 text: route with no kind gets 'Left for you: <route>' (CS-5)",
          "Left for you: valide o login" in text, text)


def test_queue_hands_route_kind_to_the_panel():
    """The deferred item `cepa-plan queue` returns carries `route_kind`: without it
    the panel has no kind to show."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [_routed("b1", "pending", "external-block",
                                        "falta a chave", "A chave existe?")])
        plan = CEPA_UNTIL.parent / "cepa-plan"
        import json
        p = subprocess.run([sys.executable, str(plan), "queue", "fila", "--repo",
                            str(root), "--json"], capture_output=True, text=True)
        deferred = json.loads(p.stdout).get("deferred") or []
        check("CS-2 queue: the deferred item carries route_kind",
              any(d.get("route_kind") == "external-block" for d in deferred),
              p.stdout + p.stderr)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print(f"\n{len(FAILURES)} FAIL" if FAILURES else "\ntudo verde")
    sys.exit(1 if FAILURES else 0)
