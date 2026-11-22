#!/usr/bin/env python3
"""`cepa until decide --all` (spec `decisoes-de-todas-as-filas`).

CS-7: on a terminal, `cepa until decide --all` asks the owner questions of
every queue in ONE panel, a section per queue in the order of `cepa plan
ready`, numbered across the whole list; each answer is recorded in the queue
of its own item, and one commit at the end holds every queue file an answer
changed. Before it, the command exited 2 refusing the queue `'--all'`, and the
owner had to run `cepa until decide <fila>` once per queue, guessing which
queues held a question.

Against the real CLI (`cepa-until decide --all`) in a pseudo-terminal, in a
temporary git repo with two queues, `a` and `b`, each holding one item with an
open owner route.

Run with `python3 tests/test_cepa_until_decide_all.py`.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until as base  # noqa: E402
import test_cepa_until_all as al  # noqa: E402
import test_cepa_until_decide as dec  # noqa: E402

import yaml  # noqa: E402

check = base.check
FAILURES = base.FAILURES
CEPA_UNTIL = al.CEPA_UNTIL


def _owner_item(ident, route, question, status="pending"):
    it = base.item(ident, status=status, human_pending=route)
    it["route_kind"] = "owner-task"
    it["owner_question"] = question
    return it


def _decide_all_on_tty(tmp, root, inputs, args=("--all",)):
    env = al._tty_env(tmp)
    env["CEPA_UNTIL_LEITOR"] = "off"
    rc, out = dec.on_tty(
        [sys.executable, str(CEPA_UNTIL), "decide", *args, "--repo", str(root)],
        str(root), inputs=inputs, env=env, timeout=90)
    return rc, dec.ANSI.sub("", out)


def _item_of(path, ident):
    return {str(i["id"]): i for i in
            yaml.safe_load(path.read_text())["items"]}[ident]


def test_cs7_decide_all_asks_every_queue_in_one_panel_and_records_each_answer():
    """The spec's own script: `a1` in queue `a` and `b1` in queue `b`, each with
    an open route; `y` to both closes both routes, each in its own queue file,
    and the last commit touches the two files."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {
            "b": [_owner_item("b1", "liberar o acesso da fila b",
                              "Liberei o acesso da fila b?")],
            "a": [_owner_item("a1", "liberar o acesso da fila a",
                              "Liberei o acesso da fila a?")]})
        head_before = al._git(root, "rev-parse", "HEAD").strip()
        rc, out = _decide_all_on_tty(tmp, root, [
            ("[w] I write the answer", "y"), ("Anything to add", ""),
            ("[w] I write the answer", "y"), ("Anything to add", "")])
        check("decide --all no terminal sai com 0", rc == 0, out[-1500:])
        check("...não recusa a fila '--all'", "invalid queue" not in out,
              out[-800:])
        check("...um painel único com as duas perguntas",
              out.count("question(s) for you") == 1
              and "2 question(s) for you" in out, out[-2500:])
        sec_a, sec_b = out.find("queue `a`"), out.find("queue `b`")
        check("...seção da fila a antes da seção da fila b",
              0 <= sec_a < sec_b, out[-2500:])
        qa = out.find("Liberei o acesso da fila a?")
        qb = out.find("Liberei o acesso da fila b?")
        check("...cada pergunta dentro da seção da sua fila",
              sec_a < qa < sec_b < qb, out[-2500:])
        check("...numeradas 1 e 2 entre as filas",
              re.search(r"1/2\]? ·? ?a1", out) and re.search(r"2/2\]? ·? ?b1", out),
              out[-2500:])
        a1, b1 = _item_of(paths["a"], "a1"), _item_of(paths["b"], "b1")
        check("a1 fica com human_pending: null na fila a",
              a1.get("human_pending") is None
              and "sim: " in str(a1.get("evidence")), str(a1))
        check("b1 fica com human_pending: null na fila b",
              b1.get("human_pending") is None
              and "sim: " in str(b1.get("evidence")), str(b1))
        head = al._git(root, "rev-parse", "HEAD").strip()
        check("...e há um commit novo", head != head_before, head)
        files = al._git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("o último commit toca os dois queue.yaml",
              head != head_before
              and ".claude/queues/a/queue.yaml" in files
              and ".claude/queues/b/queue.yaml" in files, str(files))
        dirty = al._git(root, "status", "--short", "--",
                        ".claude/queues/a/queue.yaml", ".claude/queues/b/queue.yaml")
        check("...e as filas ficam sem mudança solta", dirty.strip() == "", dirty)


def test_cs7_decide_all_asks_the_leftover_task_of_a_delivered_item():
    """`cepa until decide <fila>` asks the task a `done` item left for the owner;
    the panel of every queue asks it too, or the owner would still need the
    per-queue command for the tasks `cepa plan waiting` lists as theirs."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {
            "a": [_owner_item("a1", "rotacionar o segredo",
                              "Rotacionei o segredo?", status="done")],
            "b": [_owner_item("b1", "liberar b", "Liberei b?")]})
        rc, out = _decide_all_on_tty(tmp, root, [
            ("[w] I write the answer", "y"), ("Anything to add", ""),
            ("[w] I write the answer", "n"), ("Anything to add", "")])
        check("decide --all com tarefa sobrando sai com 0", rc == 0, out[-1500:])
        check("...pergunta a tarefa do item concluído",
              "Rotacionei o segredo?" in out and "2 question(s) for you" in out,
              out[-2500:])
        a1, b1 = _item_of(paths["a"], "a1"), _item_of(paths["b"], "b1")
        check("...o sim fecha a tarefa do a1, que segue done",
              a1.get("human_pending") is None and a1["status"] == "done", str(a1))
        check("...o não deixa b1 esperando, com o não gravado",
              b1.get("human_pending") and "não" in str(b1.get("evidence")), str(b1))


def test_cs7_decide_all_commits_only_the_queues_an_answer_changed():
    """A queue file the owner left modified, and that no answer touched, is not
    swept into the commit of `decide --all` (as with `decide <fila>`)."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a?")],
            "c": [base.item("c1")]})
        paths["c"].write_text(paths["c"].read_text() + "# nota do dono\n")
        head_before = al._git(root, "rev-parse", "HEAD").strip()
        rc, out = _decide_all_on_tty(tmp, root, [
            ("[w] I write the answer", "y"), ("Anything to add", "")])
        files = al._git(root, "show", "--name-only", "--format=", "HEAD").split()
        head = al._git(root, "rev-parse", "HEAD").strip()
        check("o commit leva a fila a", rc == 0 and head != head_before
              and ".claude/queues/a/queue.yaml" in files, (files, out[-1200:]))
        check("...e não leva a fila c que o dono deixou modificada",
              head != head_before and ".claude/queues/c/queue.yaml" not in files, str(files))
        check("...que segue modificada", "# nota do dono" in paths["c"].read_text())


def test_cs7_queue_and_all_together_are_refused():
    """`decide a --all` is ambiguous: exit 2, saying the two do not go together."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {"a": [_owner_item("a1", "x", "X?")]})
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide", "a", "--all",
                            "--repo", str(root)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("decide <fila> --all sai com 2", p.returncode == 2,
              p.stdout + p.stderr)
        check("...dizendo que não combinam", "--all" in p.stderr, p.stderr)


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        return 1
    print(f"\n✓ {len(tests)} testes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
