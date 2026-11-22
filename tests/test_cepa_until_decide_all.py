#!/usr/bin/env python3
"""`cepa until decide --all` (spec `decisoes-de-todas-as-filas`).

CS-7: on a terminal, `cepa until decide --all` asks the owner questions of
every queue in ONE panel, a section per queue in the order of `cepa plan
ready`, numbered across the whole list; each answer is recorded in the queue
of its own item, and one commit at the end holds every queue file an answer
changed. Before it, the command exited 2 refusing the queue `'--all'`, and the
owner had to run `cepa until decide <fila>` once per queue, guessing which
queues held a question.

CS-8: `cepa until decide` with no argument does the same as `--all`.

CS-9: in that panel a route already answered "no" is not asked (one line per
queue counts them), and a queue with its own live run is left out with one line
naming the queue and its run.

CS-10: off a terminal, `cepa until decide --all` prints the pending questions of
every queue as text, asks nothing and commits nothing.

CS-11: with no open route in any queue, `cepa until decide --all` says "nada
espera você" in one line and exits 0 without committing; before, it printed
nothing at all, and the owner could not tell "nothing waits" from "it broke".

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
        check("...dizendo que não combinam e por quê",
              "--all do not go together" in p.stderr
              and "--all already asks every queue" in p.stderr, p.stderr)


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
                try:
                    os.write(fd, reply.encode()
                             + (b"" if reply in ("\x03",) else b"\n"))
                except OSError:  # the child already left: the checks say why
                    alive = False
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


def test_cs7_q_stops_the_panel_and_says_nothing_else_is_asked():
    """`q` at the first question ends the whole panel: the line says nothing else
    is asked, names `decide` for both queues and never speaks of a run."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a?")],
            "b": [_owner_item("b1", "liberar b", "Liberei b?")]})
        rc, out, _ = _pty_session(
            [sys.executable, str(CEPA_UNTIL), "decide", "--all", "--repo", str(root)],
            str(root), _decide_all_env(tmp, "600"),
            [("[w] I write the answer", "q", 0)])
        check("q: sai com 0", rc == 0, out[-1200:])
        check("...a linha diz que nada mais é perguntado",
              "questions stopped with q; nothing else is asked." in out, out[-1200:])
        check("...nomeia o decide das duas filas",
              "cepa-until decide a" in out and "cepa-until decide b" in out,
              out[-1200:])
        check("...sem falar de run", "the run goes on" not in out, out[-1200:])
        check("...e não pergunta a segunda", "Liberei b?" not in out, out[-1200:])


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


def test_cs8_bare_decide_on_a_terminal_is_the_all_panel():
    """CS-8: `cepa until decide` with no argument does what `--all` does. The
    CS-7 repo, on a terminal: one panel with sections `a` and `b` numbered 1
    and 2, each answer in its own queue file, one commit touching both. Before
    CS-8 the bare call exited 2 for the missing argument."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {
            "b": [_owner_item("b1", "liberar o acesso da fila b",
                              "Liberei o acesso da fila b?")],
            "a": [_owner_item("a1", "liberar o acesso da fila a",
                              "Liberei o acesso da fila a?")]})
        head_before = al._git(root, "rev-parse", "HEAD").strip()
        rc, out = _decide_all_on_tty(tmp, root, [
            ("[w] I write the answer", "y"), ("Anything to add", ""),
            ("[w] I write the answer", "y"), ("Anything to add", "")], args=())
        check("decide sem argumento no terminal sai com 0", rc == 0, out[-1500:])
        check("...não pede o argumento", "required" not in out, out[-800:])
        check("...um painel único com as duas perguntas",
              out.count("question(s) for you") == 1
              and "2 question(s) for you" in out, out[-2500:])
        sec_a, sec_b = out.find("queue `a`"), out.find("queue `b`")
        qa = out.find("Liberei o acesso da fila a?")
        qb = out.find("Liberei o acesso da fila b?")
        check("...seções a e b, cada pergunta na sua",
              0 <= sec_a < qa < sec_b < qb, out[-2500:])
        check("...numeradas 1 e 2 entre as filas",
              re.search(r"1/2\]? ·? ?a1", out) and re.search(r"2/2\]? ·? ?b1", out),
              out[-2500:])
        a1, b1 = _item_of(paths["a"], "a1"), _item_of(paths["b"], "b1")
        check("a1 e b1 ficam com human_pending: null nas suas filas",
              a1.get("human_pending") is None and b1.get("human_pending") is None,
              (a1, b1))
        files = al._git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("...e o último commit toca os dois queue.yaml",
              al._git(root, "rev-parse", "HEAD").strip() != head_before
              and ".claude/queues/a/queue.yaml" in files
              and ".claude/queues/b/queue.yaml" in files, str(files))
        subject = al._git(root, "log", "-1", "--format=%s").strip()
        check("...com a mesma mensagem do decide --all",
              subject == "until --all decide: owner answers recorded in 2 queue(s)",
              subject)


def test_cs8_bare_decide_off_a_terminal_is_the_same_as_all():
    """Off a terminal the bare call is still `--all`: same exit code, same
    output, and not the usage error it used to be. What `--all` itself prints
    there is CS-10's to settle; CS-8 only says the two are one command."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a fila a?")],
            "b": [_owner_item("b1", "liberar b", "Liberei a fila b?")]})
        outs = []
        for args in ((), ("--all",)):
            p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide", *args,
                                "--repo", str(root)], capture_output=True,
                               text=True, stdin=subprocess.DEVNULL, timeout=60)
            outs.append((p.returncode, p.stdout, p.stderr))
        (rc, out, err), bare_all = outs[0], outs[1]
        check("fora do terminal: decide sem argumento não é erro de uso",
              rc != 2 and "required" not in err, err)
        check("...e mostra a primeira pergunta do painel",
              "queue `a`" in out and "Liberei a fila a?" in out, out[-1500:])
        check("...igual ao decide --all (código, saída e erro)",
              outs[0] == bare_all, (outs[0][1][-600:], bare_all[1][-600:]))


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


def test_cs9_decide_all_skips_the_no_answers_and_the_queue_with_a_live_run():
    """CS-9, the spec's own script: `a1` already answered "no" on 2026-11-18,
    queue `c` with a live run of its own and `b1` with an open route. The panel
    asks only `b1`; one line counts the "no" of `a` and names `cepa-until decide
    a`; one line names queue `c` and its run, whose question is not asked."""
    with tempfile.TemporaryDirectory() as tmp:
        old = _owner_item("a1", "liberar a", "Liberei a?")
        old["evidence"] = "Resposta do dono em 2026-11-18: não: Liberei a?"
        root, paths = al._repo(tmp, {
            "a": [old],
            "b": [_owner_item("b1", "liberar b", "Liberei b?")],
            "c": [_owner_item("c1", "liberar c", "Liberei c?")]})
        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(120)", "cepa-until"])
        try:
            run = al._live_run_of_queue(root, "c", alive.pid)
            rc, out = _decide_all_on_tty(tmp, root, [
                ("[w] I write the answer", "y"), ("Anything to add", "")])
        finally:
            alive.kill()
            alive.wait()
        check("decide --all com negada e run vivo sai com 0", rc == 0, out[-1500:])
        check("...pergunta só b1",
              "1 question(s) for you" in out and "Liberei b?" in out
              and "Liberei a?" not in out.split("question(s) for you", 1)[-1]
              and "Liberei c?" not in out, out[-2500:])
        no_line = [l for l in out.splitlines() if "already answered" in l]
        check("...uma linha conta a negada de a, com a data e o comando",
              len(no_line) == 1 and "queue `a`" in no_line[0]
              and "18/11" in no_line[0] and "cepa-until decide a" in no_line[0],
              str(no_line) + out[-1500:])
        live_line = [l for l in out.splitlines() if "queue `c`" in l]
        check("...uma linha nomeia a fila c e o run dela",
              len(live_line) == 1 and f"c/{run}" in live_line[0]
              and "left out of this panel" in live_line[0]
              and f"pid {alive.pid}" in live_line[0],
              str(live_line) + out[-1500:])
        check("...e diz onde responder c depois que o run acabar",
              live_line and "cepa-until decide c" in live_line[0], str(live_line))
        c1 = _item_of(paths["c"], "c1")
        b1 = _item_of(paths["b"], "b1")
        check("c1 segue esperando, sem resposta gravada",
              c1.get("human_pending") and "Resposta do dono" not in
              str(c1.get("evidence") or ""), str(c1))
        check("b1 fecha com o sim", b1.get("human_pending") is None, str(b1))
        files = al._git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("...o commit toca só a fila b",
              files == [".claude/queues/b/queue.yaml"], str(files))


def test_cs9_a_live_run_is_named_even_when_nothing_else_is_asked():
    """The queue with a live run is the only one with a question: the panel
    opens no question, the line still names the queue and its run, and nothing
    is committed."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {
            "c": [_owner_item("c1", "liberar c", "Liberei c?")]})
        head_before = al._git(root, "rev-parse", "HEAD").strip()
        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(120)", "cepa-until"])
        try:
            run = al._live_run_of_queue(root, "c", alive.pid)
            rc, out = _decide_all_on_tty(tmp, root, [])
        finally:
            alive.kill()
            alive.wait()
        check("só fila com run vivo: sai com 0", rc == 0, out[-1500:])
        check("...nenhuma pergunta", "question(s) for you" not in out
              and "Liberei c?" not in out, out[-1500:])
        check("...a linha nomeia c e o run",
              any("queue `c`" in l and f"c/{run}" in l for l in out.splitlines()),
              out[-1500:])
        check("...e nada é commitado",
              al._git(root, "rev-parse", "HEAD").strip() == head_before, "")


def test_cs9_the_launch_panel_of_all_keeps_its_live_queue_silent():
    """The `--all` launch already warns the queue with a live run on stderr when
    it has ready items (CS-4 of until-todas-as-filas); its panel does not add a
    second line for it."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {
            "b": [_owner_item("b1", "liberar b", "Liberei b?")],
            "c": [_owner_item("c1", "liberar c", "Liberei c?")]})
        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(120)", "cepa-until"])
        try:
            run = al._live_run_of_queue(root, "c", alive.pid)
            rc, out, _ = al._launch_all_on_tty(tmp, root, [], wait="2")
        finally:
            alive.kill()
            alive.wait()
        launch = out.split("item 1", 1)[0]
        check("largada sai com 0", rc == 0, out[-1500:])
        check("largada: o painel não ganha a linha da fila com run vivo",
              "left out of this panel" not in out and f"c/{run}" not in launch,
              launch[-1500:])
        check("...e não pergunta c1", "Liberei c?" not in launch, launch[-1500:])


def test_cs10_decide_all_off_a_terminal_lists_every_question_and_commits_nothing():
    """The spec's script: the CS-7 repo with a stdin that is not a TTY. Exit 0,
    the questions of `a1` and `b1` printed as text, no prompt, and `git log`
    gains no commit (the queue files stay as they were)."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {
            "b": [_owner_item("b1", "liberar o acesso da fila b",
                              "Liberei o acesso da fila b?")],
            "a": [_owner_item("a1", "liberar o acesso da fila a",
                              "Liberei o acesso da fila a?")]})
        head_before = al._git(root, "rev-parse", "HEAD").strip()
        queues_before = {q: p.read_text() for q, p in paths.items()}
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide", "--all",
                            "--repo", str(root)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        out = p.stdout
        check("fora do terminal: decide --all sai com 0", p.returncode == 0,
              out[-1500:] + p.stderr[-800:])
        check("...imprime a pergunta de a1",
              re.search(r"a1 \(.*\): Liberei o acesso da fila a\?", out), out)
        check("...e a pergunta de b1",
              re.search(r"b1 \(.*\): Liberei o acesso da fila b\?", out), out)
        check("...na ordem das filas, cada uma na sua seção",
              0 <= out.find("queue `a`") < out.find("a1 (")
              < out.find("queue `b`") < out.find("b1 ("), out)
        check("...conta as duas perguntas", "waiting on you: 2" in out, out)
        check("...não pergunta nada (sem o menu de resposta)",
              "[y] yes" not in out and "questions interrupted" not in out, out)
        check("...diz onde responder, num terminal",
              "in a terminal: cepa-until decide --all" in out, out)
        head = al._git(root, "rev-parse", "HEAD").strip()
        check("...e o git log não ganha commit", head == head_before, head)
        check("...e as filas ficam como estavam",
              {q: p.read_text() for q, p in paths.items()} == queues_before,
              "fila mudou")


def test_cs10_bare_decide_off_a_terminal_also_lists_as_text():
    """CS-8 says the bare call is `--all`; off a terminal it lists the same text."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a fila a?")]})
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide",
                            "--repo", str(root)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("decide sem argumento fora do terminal lista a1 como texto",
              p.returncode == 0 and "a1 (" in p.stdout
              and "Liberei a fila a?" in p.stdout and "[y] yes" not in p.stdout,
              p.stdout[-1200:])


def test_cs10_off_a_terminal_every_question_of_a_queue_is_listed():
    """A queue with two questions lists both, and the count says three in all:
    the text listing must not keep only the first question of each queue."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {
            "a": [_owner_item("a1", "liberar a1", "Liberei a1?"),
                  _owner_item("a2", "liberar a2", "Liberei a2?")],
            "b": [_owner_item("b1", "liberar b1", "Liberei b1?")]})
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide", "--all",
                            "--repo", str(root)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        out = p.stdout
        check("fora do terminal: as três perguntas aparecem",
              all(re.search(rf"{i} \(.*\): Liberei {i}\?", out)
                  for i in ("a1", "a2", "b1")), out)
        check("...a fila a diz 2 perguntas e o total diz 3",
              "queue `a` · 2 question(s)" in out and "waiting on you: 3" in out, out)


def test_cs10_stdin_not_a_tty_lists_even_when_stdout_is_a_terminal():
    """The criterion is about stdin: with stdout on a terminal and stdin not one,
    there is nobody to answer, so it lists as text, exits 0 and commits nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = al._repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a fila a?")],
            "b": [_owner_item("b1", "liberar b", "Liberei a fila b?")]})
        head_before = al._git(root, "rev-parse", "HEAD").strip()
        env = al._tty_env(tmp)
        env["CEPA_UNTIL_LEITOR"] = "off"
        master, slave = pty.openpty()
        proc = subprocess.Popen(
            [sys.executable, str(CEPA_UNTIL), "decide", "--all", "--repo",
             str(root)], cwd=str(root), env=env, stdin=subprocess.DEVNULL,
            stdout=slave, stderr=slave)
        os.close(slave)
        chunks, deadline = [], time.time() + 60
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.5)
            if ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                chunks.append(data)
            elif proc.poll() is not None:
                break
        try:
            rc = proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = proc.wait()
        os.close(master)
        out = dec.ANSI.sub("", b"".join(chunks).decode("utf-8", "replace"))
        check("stdin sem terminal, stdout em terminal: sai com 0", rc == 0, out[-1200:])
        check("...lista a1 e b1 como texto, sem o menu",
              "a1 (" in out and "b1 (" in out and "[y] yes" not in out
              and "questions interrupted" not in out, out[-1500:])
        check("...e não commita", al._git(root, "rev-parse", "HEAD").strip()
              == head_before, "commit novo")


def _no_route_repo(tmp):
    """Two queues and no open route: `a` only has a delivered item, `b` a pending
    item that waits for nobody."""
    return al._repo(tmp, {"a": [base.item("a1", status="done")],
                          "b": [base.item("b1")]})


def test_cs11_nothing_waiting_off_a_terminal_is_one_line_and_exit_0():
    """The spec's script, off a terminal: exit 0, stdout is the one line "nada
    espera você", and `git log` gains no commit."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _no_route_repo(tmp)
        head_before = al._git(root, "rev-parse", "HEAD").strip()
        queues_before = {q: p.read_text() for q, p in paths.items()}
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide", "--all",
                            "--repo", str(root)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("sem rota aberta, fora do terminal: sai com 0", p.returncode == 0,
              p.stdout[-800:] + p.stderr[-800:])
        check("...e a saída é a linha 'nada espera você', só ela",
              p.stdout.strip().splitlines() == ["nada espera você"], repr(p.stdout))
        check("...sem erro", p.stderr.strip() == "", p.stderr[-800:])
        check("...e o git log não ganha commit",
              al._git(root, "rev-parse", "HEAD").strip() == head_before, "")
        check("...e as filas ficam como estavam",
              {q: p.read_text() for q, p in paths.items()} == queues_before,
              "fila mudou")


def test_cs11_nothing_waiting_on_a_terminal_is_the_same_line():
    """On a terminal the owner came to answer: the same one line, no panel, exit
    0, no commit."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _no_route_repo(tmp)
        head_before = al._git(root, "rev-parse", "HEAD").strip()
        rc, out = _decide_all_on_tty(tmp, root, [])
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        check("sem rota aberta, no terminal: sai com 0", rc == 0, out[-800:])
        check("...uma linha só, 'nada espera você'",
              lines == ["nada espera você"], repr(out[-800:]))
        check("...e não commita",
              al._git(root, "rev-parse", "HEAD").strip() == head_before, "")


def test_cs11_bare_decide_with_nothing_waiting_says_the_same():
    """CS-8 makes the bare call `--all`: it says the same line."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _no_route_repo(tmp)
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide",
                            "--repo", str(root)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("decide sem argumento, nada esperando: a mesma linha e 0",
              p.returncode == 0
              and p.stdout.strip().splitlines() == ["nada espera você"],
              repr(p.stdout) + p.stderr[-400:])


def test_cs11_a_route_answered_no_or_a_live_run_is_not_nothing():
    """A route already answered "no" still sits with the owner (CS-9 counts it),
    and so does the question of a queue with its own live run: neither prints
    "nada espera você"."""
    with tempfile.TemporaryDirectory() as tmp:
        no = _owner_item("a1", "liberar a", "Liberei a?")
        no["evidence"] = "Resposta do dono em 2026-11-19: não: Liberei a?"
        root, _ = al._repo(tmp, {"a": [no]})
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide", "--all",
                            "--repo", str(root)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("só rota negada: não diz 'nada espera você'",
              "nada espera você" not in p.stdout
              and "already answered" in p.stdout, p.stdout[-800:])
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {
            "c": [_owner_item("c1", "liberar c", "Liberei c?")]})
        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(120)", "cepa-until"])
        try:
            al._live_run_of_queue(root, "c", alive.pid)
            p = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide",
                                "--all", "--repo", str(root)],
                               capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=60)
        finally:
            alive.kill()
            alive.wait()
        check("só fila com run vivo: não diz 'nada espera você'",
              "nada espera você" not in p.stdout
              and "left out of this panel" in p.stdout, p.stdout[-800:])


def test_cs11_the_launch_panel_with_nothing_waiting_stays_silent():
    """The `--all` launch panel prints nothing when nothing waits: the line is
    only for the owner who called `decide`."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = al._repo(tmp, {"b": [base.item("b1")]})
        rc, out, _ = al._launch_all_on_tty(tmp, root, [], wait="2")
        check("largada sem nada esperando: não diz 'nada espera você'",
              "nada espera você" not in out, out[-1200:])


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
