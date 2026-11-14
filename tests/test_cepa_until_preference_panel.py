#!/usr/bin/env python3
"""CS-9 of docs/spec/perguntas-da-largada-legiveis.md: on a terminal of 80 columns, the
pre-read's choices appear inside the panel frame (`N/M · <id>` on top, the labels
"Choice" and "Agent's default", the key menu) and no line is wider than the terminal,
even when the reader returns a 200-character text.

Run with `python3 tests/test_cepa_until_preference_panel.py`, exit 1 on any failure.
"""
import fcntl
import os
import pty
import re
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until_decide as base  # noqa: E402
from test_cepa_until_decide import (  # noqa: E402
    check, item, build_repo, fake_claude, env_do_run, CEPA_UNTIL, FAILURES)

COLS = 80
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
LONG = ("Há duas formas de mostrar a data na tela de pedidos e o desenho não diz "
        "qual vale: o formato curto, com dia e mês, e o formato por extenso, com "
        "o nome do mês escrito e o ano completo, e cada tela já usa um deles. ")[:200]
assert len(LONG) == 200


def _long_reader(tmp):
    script = Path(tmp) / "leitor-longo.py"
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "it = json.load(sys.stdin)\n"
        "if it['id'] != 'x1':\n"
        "    print(json.dumps({'tipo': None}))\n"
        "else:\n"
        "    print(json.dumps({'tipo': 'preferencia', 'padrao': 'usar o formato curto',\n"
        f"        'texto': {LONG!r},\n"
        "        'pergunta': 'Posso usar o formato curto?'}))\n")
    script.chmod(0o755)
    return script


def _on_80_cols(cmd, cwd, env, answer_after, timeout=90):
    pid, fd = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, COLS, 0, 0))
        os.chdir(cwd)
        os.execve(cmd[0], cmd, env)
    out, answered, end = "", False, time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            out += data.decode(errors="replace")
        if not answered and answer_after in out:
            answered = True
            os.write(fd, b"\n")
    if time.time() >= end:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    os.waitpid(pid, 0)
    return out


def test_cs9_long_preference_fits_80_columns_inside_the_frame():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("x1"), item("y1")])
        env = env_do_run(tmp, root, fake_claude(tmp, "pass"))
        env["CEPA_UNTIL_LEITOR"] = str(_long_reader(tmp))
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "5"
        env.pop("COLUMNS", None)
        cmd = [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root),
               "--for", "2h", "--no-verify", "--no-analysis"]
        raw = _on_80_cols(cmd, str(root), env, "Your choice, in one line")
    out = ANSI.sub("", raw).replace("\r", "")
    lines = out.split("\n")
    start = next((i for i, l in enumerate(lines) if "choice(s) the pre-read found" in l), None)
    check("cs9: the block exists", start is not None, out[-1500:])
    if start is None:
        return
    stop = next((i for i, l in enumerate(lines) if "Your choice, in one line" in l), len(lines))
    block = lines[start:stop + 1]
    wide = [(len(l), l) for l in block if len(l) > COLS]
    check("cs9: no line of the block is wider than 80 columns", not wide, str(wide))
    check("cs9: the frame opens with `1/1 · x1`",
          any(re.match(r"┌─ 1/1 · x1 ", l) for l in block), "\n".join(block))
    text = "\n".join(block)
    check("cs9: the label Choice", re.search(r"│\s+Choice\s", text) is not None, text)
    check("cs9: the label Agent's default",
          re.search(r"│\s+Agent's default\s", text) is not None, text)
    check("cs9: the key menu", "[Enter] keep the agent's default (recommended)" in text, text)
    check("cs9: the whole text reached the screen",
          " ".join(LONG.split()[-3:]) in " ".join(re.sub(r"│", " ", text).split()), text)


def test_cs9_in_process_every_line_fits_for_each_exit():
    """Decorated screen, 80 columns: the answer, the wait, Ctrl-C all stay within it."""
    import contextlib, io
    m = base.load_module(color="sempre")
    m.shutil.get_terminal_size = lambda *a, **k: os.terminal_size((COLS, 24))
    for name, exc in (("answered", None), ("the wait", m.NoAnswer),
                      ("Ctrl-C", KeyboardInterrupt)):
        prefs = {"x1": {"texto": LONG, "pergunta": "P " * 90, "padrao": "D " * 90,
                        "escolha": "d", "fonte": "padrao"}}
        def question(prompt, exc=exc):
            if exc:
                raise exc()
            return ""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            m.ask_preferences(prefs, wait=600, question=question)
        lines = ANSI.sub("", buf.getvalue()).split("\n")
        wide = [(len(l), l) for l in lines if len(l) > COLS]
        check(f"cs9 in process ({name}): no line wider than 80", not wide, str(wide))
        check(f"cs9 in process ({name}): the frame line is there",
              any(l.startswith("┌─ 1/1 · x1 ") for l in lines), "\n".join(lines))


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
