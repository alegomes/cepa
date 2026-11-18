#!/usr/bin/env python3
"""CS-7 of docs/spec/perguntas-da-largada-legiveis.md: after `?` ("I don't understand
the question"), the reader rewrites the question right there, within 60 seconds, the
new question shows in the block of the SAME item and the panel asks for the answer
again; `queue.yaml` then carries the new question (through `cepa-plan reword-route
--replace`, the only door), with `human_pending`, `status` and `evidence` unchanged.

Its own file so the proof gate can run it alone:
`python3 tests/test_cepa_until_unclear_rewrite.py`, exit 1 on any failure.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import CEPA_UNTIL, build_repo, item  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    ANSI, FAILURES, CEPA_PLAN, check, load_module, on_tty)

OLD_Q = "A chave do cofre já existe?"
NEW_Q = "Você já criou a senha do cofre que o sistema usa?"
NEW_YES = "O item volta para a fila e o próximo run usa a senha nova."
NEW_NO = "O item continua esperando a senha."
ROUTE = "falta a chave do cofre"


def _reader(tmp):
    """A fake reader: for the unclear-question job it answers a new closed question
    and logs the payload's bad question; anything else gets no finding."""
    script = Path(tmp) / "leitor.py"
    log = Path(tmp) / "leitor-chamadas.txt"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "it = json.load(sys.stdin)\n"
        f"open({str(log)!r}, 'a').write(str(it.get('tarefa')) + ' | '\n"
        "    + str(it.get('pergunta_mal_escrita')) + '\\n')\n"
        "if it.get('tarefa') == 'reescrever-pergunta':\n"
        f"    print(json.dumps({{'route_kind': 'owner-task', 'question': {NEW_Q!r},\n"
        f"        'if_yes': {NEW_YES!r}, 'if_no': {NEW_NO!r}}}))\n"
        "else:\n"
        "    print(json.dumps({'tipo': None}))\n")
    script.chmod(0o755)
    return script, log


def _items(qfile):
    return {i["id"]: i for i in yaml.safe_load(qfile.read_text())["items"]}


def test_question_mark_rewrites_in_the_same_block_and_asks_again():
    """Red test of CS-7, as a process in a pseudo-terminal."""
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as fb:
        it = item("b1", status="pending", human_pending=ROUTE)
        it["owner_question"] = OLD_Q
        it["route_kind"] = "external-block"
        it["evidence"] = "evidência original"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = _items(qfile)["b1"]
        reader, log = _reader(tmp)
        env = dict(os.environ, CEPA_FEEDBACK_DIR=fb, CEPA_UNTIL_LEITOR=str(reader))
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", "fila", "--repo", str(root)]
        rc, out = on_tty(cmd, str(root), env=env,
                         inputs=[("[t] I write the answer", "?"),
                                 ("[t] I write the answer", "")], timeout=90)
        plain = ANSI.sub("", out)
        check("CS-7 pty: decide exits 0", rc == 0, plain[-1500:])
        check("CS-7 pty: the reader got the unclear-question job with the old question",
              log.exists() and f"reescrever-pergunta | {OLD_Q}" in log.read_text(),
              log.read_text() if log.exists() else "no call")
        after_mark = plain.split("badly written", 1)[-1]
        check("CS-7 pty: the new question shows after the `?`", NEW_Q in after_mark,
              plain)
        check("CS-7 pty: same block, the item header shows once",
              plain.count("· b1") == 1, plain)
        check("CS-7 pty: the panel asks for the answer again",
              "[t] I write the answer" in after_mark, after_mark)
        now = _items(qfile)["b1"]
        check("CS-7 pty: queue.yaml carries the new question",
              now.get("owner_question") == NEW_Q, now)
        check("CS-7 pty: queue.yaml carries the new kind and effects",
              now.get("route_kind") == "owner-task"
              and (now.get("owner_summary") or {}).get("se_sim") == NEW_YES
              and (now.get("owner_summary") or {}).get("se_nao") == NEW_NO, now)
        check("CS-7 pty: human_pending, status and evidence unchanged",
              all(now.get(k) == before.get(k)
                  for k in ("human_pending", "status", "evidence")), (before, now))
        check("CS-7 pty: left for later, nothing answered",
              "answered now 0" in plain and "for later 1" in plain, plain[-1500:])


def test_new_question_answered_records_the_new_text():
    """After the rewrite, an `s` answers the NEW question: the answer text quotes it."""
    m = load_module()
    answers, screen, rewrites = [], [], []
    deferred = [{"id": "b1", "title": "t", "reason": "human_pending",
                 "human_pending": ROUTE, "question": OLD_Q, "evidence": "x",
                 "route_kind": "external-block"}]
    replies = iter(["?", "s", ""])
    new = {"route_kind": "owner-task", "question": NEW_Q, "if_yes": NEW_YES,
           "if_no": NEW_NO}
    m.decide(Path("/nao/existe"), "fila", None, {}, deferred, {},
             question=lambda _p: next(replies, ""), output=screen.append,
             answer=lambda ident, text, **k: answers.append(text) or (0, "ok"),
             unclear=lambda ident, text: (0, "ok"),
             rewrite=lambda ad, text: rewrites.append(text) or (new, None))
    check("CS-7 text: the rewrite got the question shown", rewrites == [OLD_Q],
          rewrites)
    check("CS-7 text: the answer quotes the new question",
          len(answers) == 1 and NEW_Q in answers[0] and OLD_Q not in answers[0],
          answers)


def test_second_question_mark_does_not_call_the_reader_again():
    """Spec, "Decided without asking": the second `?` on the same item does not run
    the reader again; the item stays for later (no loop holding the launch)."""
    m = load_module()
    screen, rewrites, marks = [], [], []
    deferred = [{"id": "b1", "title": "t", "reason": "human_pending",
                 "human_pending": ROUTE, "question": OLD_Q, "evidence": "x",
                 "route_kind": "external-block"}]
    replies = iter(["?", "?"])
    new = {"route_kind": "owner-task", "question": NEW_Q, "if_yes": NEW_YES,
           "if_no": NEW_NO}
    _, later = m.decide(Path("/nao/existe"), "fila", None, {}, deferred, {},
                        question=lambda _p: next(replies, ""), output=screen.append,
                        answer=lambda *a, **k: (0, "ok"),
                        unclear=lambda ident, text: marks.append(text) or (0, "ok"),
                        rewrite=lambda ad, text: rewrites.append(text) or (new, None))
    check("CS-7 text: the reader ran once", len(rewrites) == 1, rewrites)
    check("CS-7 text: both `?` recorded, the second on the new question",
          marks == [OLD_Q, NEW_Q], marks)
    check("CS-7 text: the item stays for later", len(later) == 1, later)


def _default_rewrite_run(read_result):
    """Runs `decide` with its OWN default rewrite (no `rewrite=` injected), with the
    module's `read_route` and `reword_route` swapped so nothing is spawned. Returns
    (read calls, reword calls, screen text, for_later)."""
    m = load_module()
    reads, rewords, screen = [], [], []

    def fake_read(repo, payload, deadline, prompt=None):
        reads.append({"left": deadline - m.time.monotonic(), "prompt": prompt,
                      "payload": payload})
        return read_result

    m.read_route = fake_read
    m.reword_route = lambda *a, **k: rewords.append((a, k)) or None
    deferred = [{"id": "b1", "title": "t", "reason": "human_pending",
                 "human_pending": ROUTE, "question": OLD_Q, "evidence": "x",
                 "route_kind": "external-block"}]
    replies = iter(["?", ""])
    _, later = m.decide(Path("/nao/existe"), "fila", None, {}, deferred, {},
                        question=lambda _p: next(replies, ""), output=screen.append,
                        answer=lambda *a, **k: (0, "ok"),
                        unclear=lambda ident, text: (0, "ok"))
    return m, reads, rewords, "\n".join(screen), later


def test_the_rewrite_waits_at_most_60_seconds():
    """Spec, "Decided without asking": the rewrite ceiling is 60 s. The default
    rewrite hands the reader a deadline 60 s ahead, with the unclear-question prompt
    and the question the owner did not understand in the payload."""
    new = {"route_kind": "owner-task", "question": NEW_Q, "if_yes": NEW_YES,
           "if_no": NEW_NO}
    m, reads, rewords, text, _ = _default_rewrite_run((new, None))
    check("CS-7 ceiling: the reader ran once", len(reads) == 1, reads)
    if reads:
        check("CS-7 ceiling: the deadline is 60 s ahead",
              58 <= reads[0]["left"] <= 60, reads[0]["left"])
        check("CS-7 ceiling: the unclear-question prompt",
              reads[0]["prompt"] is m.UNCLEAR_READER_PROMPT, reads[0]["prompt"])
        check("CS-7 ceiling: payload carries the job and the old question",
              reads[0]["payload"].get("tarefa") == "reescrever-pergunta"
              and reads[0]["payload"].get("pergunta_mal_escrita") == OLD_Q,
              reads[0]["payload"])
    check("CS-7 ceiling: the screen names the 60 s", "up to 60 s" in text, text)
    check("CS-7 ceiling: recorded with --replace", len(rewords) == 1
          and rewords[0][1].get("replace") is True, rewords)


def test_a_rewrite_with_the_same_question_is_not_a_rewrite():
    """A reader that hands back the question the owner did not understand changes
    nothing: no record in the queue, no "rewritten" line, the item stays for later."""
    same = {"route_kind": "external-block", "question": "  " + OLD_Q,
            "if_yes": NEW_YES, "if_no": NEW_NO}
    _, reads, rewords, text, later = _default_rewrite_run((same, None))
    check("CS-7 same: the reader ran", len(reads) == 1, reads)
    check("CS-7 same: nothing recorded in the queue", rewords == [], rewords)
    check("CS-7 same: no 'rewritten' line", "question rewritten" not in text, text)
    check("CS-7 same: the item stays for later", len(later) == 1, later)


def test_reword_route_replace_overwrites_question_and_keeps_the_route():
    """`cepa-plan reword-route --replace` overwrites kind, question and effects (the
    owner said the old ones were unclear); without it, nothing already there changes."""
    with tempfile.TemporaryDirectory() as tmp:
        it = item("b1", status="pending", human_pending=ROUTE)
        it["owner_question"] = OLD_Q
        it["route_kind"] = "external-block"
        it["evidence"] = "e"
        root = build_repo(tmp, [it])
        qfile = root / ".claude" / "programs" / "fila" / "plan.yaml"
        base = [sys.executable, str(CEPA_PLAN), "reword-route", "fila", "b1",
                "--route-kind", "owner-task", "--question", NEW_Q,
                "--if-yes", NEW_YES, "--if-no", NEW_NO, "--if-no-item", "nenhum",
                "--repo", str(root)]
        p = subprocess.run(base, capture_output=True, text=True)
        check("reword-route without --replace: exit 0", p.returncode == 0, p.stderr)
        check("reword-route without --replace: question kept",
              _items(qfile)["b1"].get("owner_question") == OLD_Q, _items(qfile))
        p = subprocess.run(base + ["--replace"], capture_output=True, text=True)
        now = _items(qfile)["b1"]
        check("reword-route --replace: exit 0", p.returncode == 0, p.stderr)
        check("reword-route --replace: new question and kind",
              now.get("owner_question") == NEW_Q
              and now.get("route_kind") == "owner-task", now)
        check("reword-route --replace: new effects",
              now["owner_summary"].get("se_sim") == NEW_YES
              and now["owner_summary"].get("se_nao") == NEW_NO, now)
        check("reword-route --replace: route, status and evidence kept",
              now.get("human_pending") == ROUTE and now.get("status") == "pending"
              and now.get("evidence") == "e", now)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print(f"\n{len(FAILURES)} FAIL" if FAILURES else "\ntudo verde")
    sys.exit(1 if FAILURES else 0)
