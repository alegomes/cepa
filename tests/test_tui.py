#!/usr/bin/env python3
"""Tests for the TUI look of the cepa-* commands (common/hooks/_tui.py).

What these cases hold:

  - outside a terminal the output is byte for byte what it used to be: it is
    what the commands' tests read, what an agent receives through Bash and what
    a `nohup` writes;
  - `NO_COLOR` and `CEPA_COR=nunca` turn the decoration off; `CEPA_COR=sempre` turns it on;
  - when on, the long line wraps with a hanging indent and no text is lost;
  - `--json` is never decorated, not even with the decoration forced;
  - the decorated `cepa-plan status` brings a header, a scoreboard and the
    calculation memory of the percentage, and keeps the ids of all items.

No third-party deps — run with `python3 tests/test_tui.py`.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / "common" / "bin"
sys.path.insert(0, str(ROOT / "common" / "hooks"))
import _tui  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run(args, color=None, cwd=None, columns="100"):
    env = {k: v for k, v in os.environ.items() if k not in ("CEPA_COR", "NO_COLOR")}
    env["COLUMNS"] = columns
    if color:
        env["CEPA_COR"] = color
    return subprocess.run([sys.executable, *args], capture_output=True, text=True,
                          env=env, cwd=cwd)


def queue(root):
    target = root / ".claude" / "programs" / "f" / "plan.yaml"
    target.parent.mkdir(parents=True)
    items = []
    for i, st in enumerate(["pending", "done", "blocked", "pending"], 1):
        items.append(
            f"  - id: item-{i}\n    title: \"{'palavra ' * 40}fim-{i}\"\n"
            f"    why: porque\n    status: {st}\n    blocked_by: []\n"
            f"    human_pending: null\n"
            + ("    evidence: travou no passo dois\n" if st == "blocked" else ""))
    target.write_text("program: f\nmode: single-track\nitems:\n" + "".join(items))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def test_disabled_outside_terminal():
    t = _tui.Screen(stream=open(os.devnull, "w"))
    assert not t.enabled
    line_text = "  18. id-x — " + "texto " * 50
    assert t.line(line_text) == line_text
    assert t.section("pendentes", 3) == "pendentes (3)"
    assert t.header("fila x") == "fila x"


def test_no_color_wins_and_always_enables():
    os.environ["NO_COLOR"] = "1"
    try:
        assert not _tui.Screen().enabled
    finally:
        del os.environ["NO_COLOR"]
    os.environ["CEPA_COR"] = "sempre"
    try:
        assert _tui.Screen(stream=open(os.devnull, "w")).enabled
    finally:
        del os.environ["CEPA_COR"]


def test_wrap_with_hanging_indent_keeps_text():
    os.environ["CEPA_COR"] = "sempre"
    os.environ["COLUMNS"] = "60"
    try:
        t = _tui.Screen()
        original = "  18. item-x — " + " ".join(f"p{i}" for i in range(60))
        output = ANSI.sub("", t.line(original)).split("\n")
    finally:
        del os.environ["CEPA_COR"]
    assert len(output) > 1
    assert all(len(l) <= 59 for l in output)
    assert all(l.startswith(" " * 6) and not l.startswith(" " * 7) for l in output[1:])
    assert " ".join(l.strip() for l in output) == original.strip()


def test_status_same_as_before_outside_terminal():
    with tempfile.TemporaryDirectory() as d:
        root = queue(Path(d))
        r = run([str(BIN / "cepa-plan"), "status", "f", "--repo", str(root)])
    assert r.returncode == 0, r.stderr
    assert "\x1b" not in r.stdout
    assert "\npendentes (2)\n" in r.stdout
    assert "    1. item-1 — palavra" in r.stdout


def test_status_decorated_in_terminal():
    with tempfile.TemporaryDirectory() as d:
        root = queue(Path(d))
        r = run([str(BIN / "cepa-plan"), "status", "f", "--repo", str(root)],
                 color="sempre")
    assert r.returncode == 0, r.stderr
    plan_out = ANSI.sub("", r.stdout)
    assert "\x1b[" in r.stdout
    assert "fila f" in plan_out.splitlines()[0]
    assert "25% fechados (1 concluídos + 0 descartados) ÷ 4" in plan_out
    for i in range(1, 5):
        assert f"item-{i}" in plan_out
    assert "↳ motivo: travou no passo dois" in plan_out
    assert all(len(l) <= 99 for l in plan_out.splitlines())


def test_json_never_decorated():
    with tempfile.TemporaryDirectory() as d:
        root = queue(Path(d))
        r = run([str(BIN / "cepa-plan"), "status", "f", "--repo", str(root),
                  "--json"], color="sempre")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["total"] == 4


def test_filter_decorates_command_without_own_screen():
    r = run([str(BIN / "cepa-autonomy"), "listar"], color="sempre")
    assert r.returncode == 0, r.stderr
    assert "\x1b[" in r.stdout
    plain = run([str(BIN / "cepa-autonomy"), "listar"])
    assert "\x1b" not in plain.stdout
    assert "executa e reporta" in ANSI.sub("", r.stdout)


if __name__ == "__main__":
    failures = 0
    for name, f in list(globals().items()):
        if name.startswith("test_") and callable(f):
            try:
                f()
                print(f"ok   {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failures else 0)
