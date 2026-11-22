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
import pty
import re
import select
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until as base  # noqa: E402
import test_cepa_until_all as al  # noqa: E402
import test_cepa_until_decide as dec  # noqa: E402
import test_cepa_until_clean_tree as ct  # noqa: E402

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
        subject = al._git(root, "log", "-1", "--format=%s").strip()
        check("...com a mensagem do decide --all",
              subject == "until --all decide: owner answers recorded in 2 queue(s)",
              subject)


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


def _pty_session(cmd, cwd, env, steps, timeout=90):
    """Like `on_tty`, but each step is (excerpt, reply, pause): after the excerpt
    shows, wait `pause` seconds and record the screen at that instant, then send
    the reply. Returns (rc, plain output, screens seen right before each reply)."""
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execve(cmd[0], cmd, env)
    out, steps, seen, end = "", list(steps), [], time.time() + timeout

    def pump(limit):
        nonlocal out
        stop = time.time() + limit
        while time.time() < stop:
            r, _, _ = select.select([fd], [], [], 0.2)
            if not r:
                continue
            try:
                data = os.read(fd, 4096)
            except OSError:
                return False
            if not data:
                return False
            out += data.decode(errors="replace")
        return True

    alive = True
    while alive and time.time() < end:
        alive = pump(0.3)
        if steps and steps[0][0] in out:
            trigger, reply, pause = steps.pop(0)
            out = out.replace(trigger, f"<{trigger}>", 1)
            if pause:
                alive = pump(pause)
            seen.append(dec.ANSI.sub("", out))
            if reply is not None:
                os.write(fd, reply.encode() + (b"" if reply in ("\x03",) else b"\n"))
        elif not steps:
            alive = pump(1)
            break
    if time.time() >= end:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    while pump(0.5):
        if time.time() >= end:
            break
    _, st = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(st), dec.ANSI.sub("", out), seen


def _decide_all_env(tmp, wait="1"):
    env = al._tty_env(tmp)
    env["CEPA_UNTIL_LEITOR"] = "off"
    env["CEPA_UNTIL_ESPERA_RESPOSTA"] = wait
    return env


def test_cs7_decide_all_waits_for_the_owner_with_no_time_limit():
    """The spec decided it (Decided without asking): whoever calls `decide --all`
    is at the terminal on purpose, so the panel has no wait limit. With the
    launch's wait at 1 s, a question left 4 s unanswered is still asked, and the
    late "y" is recorded."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {"a": [_owner_item("a1", "liberar a",
                                                       "Liberei a?")]})
        rc, out, seen = _pty_session(
            [sys.executable, str(CEPA_UNTIL), "decide", "--all", "--repo", str(root)],
            str(root), _decide_all_env(tmp, "1"),
            [("[w] I write the answer", "y", 4), ("Anything to add", "", 0)])
        check("sem limite: 4 s depois a pergunta segue esperando",
              seen and "nobody answered" not in seen[0], (seen or [""])[0][-800:])
        a1 = _item_of(paths["a"], "a1")
        check("...e o sim tardio é gravado",
              rc == 0 and a1.get("human_pending") is None, (rc, a1, out[-800:]))


def test_cs7_ctrl_c_keeps_what_was_answered_and_says_where_to_answer_the_rest():
    """Ctrl-C at the second question: the first answer stays recorded and
    committed, and the line says nothing else is asked and names the queue still
    holding a question. No run exists here, so it never says "the run goes on"."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a?")],
            "b": [_owner_item("b1", "liberar b", "Liberei b?")]})
        rc, out, _ = _pty_session(
            [sys.executable, str(CEPA_UNTIL), "decide", "--all", "--repo", str(root)],
            str(root), _decide_all_env(tmp, "600"),
            [("[w] I write the answer", "y", 0), ("Anything to add", "", 0),
             ("[w] I write the answer", "\x03", 0)])
        check("Ctrl-C: sai com 0", rc == 0, out[-1200:])
        check("...a linha diz que nada mais é perguntado",
              "questions interrupted; nothing else is asked." in out, out[-1200:])
        check("...nomeia o decide da fila que sobrou",
              "To answer later: cepa-until decide b" in out, out[-1200:])
        check("...sem falar de run", "the run goes on" not in out, out[-1200:])
        check("...sem repetir 'to answer later'",
              out.lower().count("to answer later") == 1, out[-1200:])
        a1, b1 = _item_of(paths["a"], "a1"), _item_of(paths["b"], "b1")
        files = al._git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("...a1 respondido fica gravado e commitado",
              a1.get("human_pending") is None
              and ".claude/queues/a/queue.yaml" in files
              and ".claude/queues/b/queue.yaml" not in files, (a1, files))
        check("...b1 segue esperando", b1.get("human_pending") == "liberar b", str(b1))


def test_cs7_decide_all_commits_the_waiver_the_answer_converted():
    """A "yes" to a proposed waiver turns it into a waiver (`cepa plan answer`);
    the one commit of `decide --all` carries that file with the queue, as the
    commit of `decide <fila>` does."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {"a": [_owner_item(
            "a1", "Aceitar ou recusar a dispensa de teste-cego",
            "Aceito a dispensa de teste-cego?")]})
        waiver = ct._proposed_waiver(root, queue="a", item="a1")
        rel = str(waiver.relative_to(root))
        rc, out = _decide_all_on_tty(tmp, root, [
            ("[w] I write the answer", "y"), ("Anything to add", "")])
        check("dispensa: a proposta virou dispensa",
              "status" not in yaml.safe_load(waiver.read_text()), waiver.read_text())
        files = al._git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("dispensa: o commit leva a fila e a dispensa",
              rc == 0 and rel in files and ".claude/queues/a/queue.yaml" in files,
              (files, out[-800:]))
        st = al._git(root, "status", "--porcelain", "--untracked-files=all")
        check("dispensa: nada fica solto", st.strip() == "", st)


def test_cs7_decide_without_queue_nor_all_is_still_a_usage_error():
    """Until CS-8 makes the bare `decide` mean `--all`, a call with neither a
    queue nor `--all` is a usage error: exit 2, naming both ways."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {"a": [_owner_item("a1", "x", "X?")]})
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide",
                            "--repo", str(root)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("decide sem nada sai com 2", p.returncode == 2, p.stdout + p.stderr)
        check("...pedindo a fila ou --all",
              "QUEUE[/RUN]" in p.stderr and "--all" in p.stderr, p.stderr)


def test_cs7_launch_panel_of_all_still_leaves_out_the_leftover_tasks():
    """The launch panel of `cepa until --all` shares the function: a task left on a
    delivered item holds no run back, so it is still not asked there (only
    `decide --all` asks it), and a cut panel still says the run goes on."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {
            "a": [_owner_item("a1", "rotacionar o segredo",
                              "Rotacionei o segredo?", status="done")],
            "b": [_owner_item("b1", "liberar b", "Liberei b?")]})
        rc, out, _ = al._launch_all_on_tty(tmp, root, [], wait="2")
        check("largada: uma pergunta só, a do b1",
              "1 question(s) for you" in out and "Liberei b?" in out
              and "Rotacionei o segredo?" not in out, out[-1500:])
        check("...e o corte diz que o run segue",
              "nobody answered in" in out and "the run goes on without." in out,
              out[-1500:])


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
