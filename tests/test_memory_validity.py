#!/usr/bin/env python3
"""Regression tests for the validity declared in memories.

A state memory ("not installed yet", "not run in a real repo") is
true on the day it was written and rots in silence. The MEMORY.md index is
loaded in every session, so an expired line enters the context looking exactly
like a fresh one. The `validade: AAAA-MM-DD` field in the frontmatter says until
when the fact can be repeated without rechecking; the sweep marks the index line
after that.

Contracts guarded here:
  - a memory with validity in the past → shows up as expired AND its line in the
    index gets the mark;
  - a memory WITHOUT the field → silence. Never an alarm invented from data
    that does not exist (a permanent lesson does not expire);
  - validity in the future → silence;
  - sweeping twice does not mark twice;
  - extended validity → the mark leaves;
  - an unreadable date → ignored, the sweep does not break;
  - the memory directory comes from the main clone's path, the way
    Claude Code names it;
  - the session notice names each expired memory.

Run with `python3 tests/test_memory_validity.py`.
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))
sys.path.insert(0, str(REPO / "tests"))

from _isolated_telemetry import isolate  # noqa: E402

isolate()

import _memval as V  # noqa: E402

TODAY = date(2026, 9, 20)
failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def mem(d, name, validity=None):
    extra = f"  validade: {validity}\n" if validity else ""
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: x\nmetadata:\n  type: project\n{extra}---\n\ncorpo\n",
        encoding="utf-8")


def scenario():
    d = Path(tempfile.mkdtemp(prefix="memval-"))
    mem(d, "velha", "2026-07-10")
    mem(d, "nova", "2026-12-01")
    mem(d, "licao")
    mem(d, "torta", "semana que vem")
    (d / "MEMORY.md").write_text(
        "- [velha](velha.md) — plugin NÃO instalado ainda\n"
        "- [nova](nova.md) — comparar custo em dezembro\n"
        "- [licao](licao.md) — gate se escreve sobre o efeito\n"
        "- [torta](torta.md) — data ilegível\n", encoding="utf-8")
    return d


def line(d, name):
    return next(l for l in (d / "MEMORY.md").read_text().splitlines() if f"({name}.md)" in l)


def test_expired_is_marked():
    d = scenario()
    expired = V.sweep(d, TODAY)
    check("só a vencida aparece", [v["file"] for v in expired] == ["velha.md"], expired)
    check("linha do índice ganha a marca", V.MARK_PREFIX in line(d, "velha"), line(d, "velha"))
    check("a marca diz desde quando", "2026-07-10" in line(d, "velha"), line(d, "velha"))
    check("o texto original da linha fica", "plugin NÃO instalado ainda" in line(d, "velha"))


def test_no_field_and_future_stay_silent():
    d = scenario()
    V.sweep(d, TODAY)
    for name in ("nova", "licao", "torta"):
        check(f"{name} sem marca", V.MARK_PREFIX not in line(d, name), line(d, name))


def test_idempotent():
    d = scenario()
    V.sweep(d, TODAY)
    before = (d / "MEMORY.md").read_text()
    V.sweep(d, TODAY)
    check("segunda varredura não muda nada", (d / "MEMORY.md").read_text() == before)
    check("uma marca só", line(d, "velha").count(V.MARK_PREFIX) == 1, line(d, "velha"))


def test_extended_validity_removes_the_mark():
    d = scenario()
    V.sweep(d, TODAY)
    mem(d, "velha", "2027-01-01")
    expired = V.sweep(d, TODAY)
    check("não conta mais como vencida", expired == [], expired)
    check("marca removida", V.MARK_PREFIX not in line(d, "velha"), line(d, "velha"))
    check("linha volta ao texto original",
          line(d, "velha") == "- [velha](velha.md) — plugin NÃO instalado ainda", line(d, "velha"))


def test_expires_the_next_day():
    d = scenario()
    mem(d, "velha", "2026-09-20")
    check("no próprio dia ainda vale", V.sweep(d, TODAY) == [])
    check("no dia seguinte venceu", len(V.sweep(d, date(2026, 9, 21))) == 1)


def test_directory_comes_from_the_main_clone():
    got = V.memory_dir("/Users/a/Insync/a@gmail.com/GoogleDrive/2026/coding/cepa", home="/H")
    want = Path("/H/.claude/projects/-Users-a-Insync-a-gmail-com-GoogleDrive-2026-coding-cepa/memory")
    check("slug igual ao do Claude Code", got == want, got)


def test_notice_names_the_expired():
    d = scenario()
    txt = V.notice(V.sweep(d, TODAY)) or ""
    check("aviso cita a memória", "velha" in txt and "2026-07-10" in txt, txt)
    check("sem vencidas, sem aviso", V.notice([]) is None)


def test_missing_directory_does_not_break():
    check("varredura em pasta inexistente devolve vazio",
          V.sweep(Path("/nao/existe/mesmo"), TODAY) == [])


def test_session_start_delivers_the_notice():
    """The wiring: the real SessionStart, as a subprocess, in a disposable git
    repo whose memory directory (in a fake HOME) has an expired one.
    """
    import json
    import os
    import subprocess
    home = Path(tempfile.mkdtemp(prefix="memval-home-"))
    repo = Path(tempfile.mkdtemp(prefix="memval-repo-")).resolve()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "x"], check=True)
    mdir = V.memory_dir(str(repo), home=str(home))
    mdir.mkdir(parents=True)
    mem(mdir, "velha", "2020-01-01")
    (mdir / "MEMORY.md").write_text("- [velha](velha.md) — estado antigo\n", encoding="utf-8")
    env = {**os.environ, "HOME": str(home)}
    r = subprocess.run(
        [sys.executable, str(REPO / "common" / "hooks" / "session-registry.py")],
        input=json.dumps({"hook_event_name": "SessionStart", "session_id": "s-teste",
                          "cwd": str(repo)}),
        capture_output=True, text=True, env=env, timeout=60)
    check("hook sai 0", r.returncode == 0, r.stderr[-300:])
    check("aviso de memória vencida chega na saída", "velha" in r.stdout and "vencida" in r.stdout,
          r.stdout[-400:] + r.stderr[-300:])
    check("índice foi marcado", V.MARK_PREFIX in (mdir / "MEMORY.md").read_text())


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print()
    if failures:
        print(f"{len(failures)} FALHA(S): {failures}")
        sys.exit(1)
    print("tudo ok")
