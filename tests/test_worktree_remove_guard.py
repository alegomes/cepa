#!/usr/bin/env python3
"""Regression tests for common/hooks/worktree-remove-guard.py.

No third-party deps — run with `python3 tests/test_worktree_remove_guard.py`
(or under pytest: `test_worktree_remove_guard` roda o mesmo cenário).

Guards the contracts of the guard:
  - `git worktree remove` / `git branch -D|-d` com sessão VIVA de outra janela
    no worktree ou no branch é BLOQUEADO (exit 2), inclusive encadeado
    (incidente de 2026-08-17);
  - sessão morta nunca bloqueia;
  - a sessão que chama é excluída pelo session_id, NUNCA pelo cwd
    (episódio fb-20261013-1): outra sessão no mesmo cwd continua bloqueando;
  - caminho relativo e nome do slice (basename) casam o worktree;
  - texto (`echo`), `worktree list`, `branch -a`, outras tools, comando vazio,
    payload ilegível e fora de repo falham ABERTO.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from _telemetria_isolada import isola

isola()

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "worktree-remove-guard.py"

FAILURES = []


def git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def run_hook(command, cwd, session_id=None, tool_name="Bash", raw=None):
    if raw is None:
        p = {"tool_name": tool_name, "tool_input": {"command": command}, "cwd": str(cwd)}
        if session_id:
            p["session_id"] = session_id
        raw = json.dumps(p)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=raw, capture_output=True, text=True
    )


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def blocked(res):
    return res.returncode == 2


def dead_pid():
    """PID de um processo que já terminou e foi colhido: garantidamente morto."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    try:
        os.kill(proc.pid, 0)
    except ProcessLookupError:
        return proc.pid
    raise RuntimeError(f"pid {proc.pid} ainda responde; teste inconclusivo")


def write_entry(main, sid, cwd, branch, pid=None):
    d = Path(main) / ".claude" / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    entry = {
        "session_id": sid,
        "pid": os.getpid() if pid is None else pid,
        "hostname": socket.gethostname(),
        "cwd": str(cwd),
        "branch": branch,
        "last_seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (d / f"{sid}.json").write_text(json.dumps(entry), encoding="utf-8")


def clear_entries(main):
    for f in (Path(main) / ".claude" / "sessions").glob("*.json"):
        f.unlink()


def main():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td).resolve()
        mainrepo = td / "main"
        mainrepo.mkdir()
        git(["init", "-q", "-b", "main"], mainrepo)
        git(["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
             "--allow-empty", "-m", "init"], mainrepo)
        wt = td / "wt-prove"
        git(["worktree", "add", "-q", str(wt), "-b", "session/prove"], mainrepo)
        outside = td / "outside"
        outside.mkdir()

        OWNER = "aaaaaaaa-owner-0001"
        CALLER = "bbbbbbbb-caller-0002"

        # ── sessão viva de OUTRA janela dentro do worktree ──────────────────
        write_entry(mainrepo, OWNER, wt, "session/prove")
        r = run_hook(f"git worktree remove {wt}", mainrepo, session_id=CALLER)
        check("worktree remove com dono vivo bloqueia", blocked(r), r.stderr)
        check("mensagem cita o caminho", str(wt) in r.stderr, r.stderr)
        check("mensagem cita worktree-discard", "worktree-discard" in r.stderr, r.stderr)
        check("mensagem cita worktree-merge e o dono",
              "worktree-merge" in r.stderr and OWNER[:8] in r.stderr, r.stderr)

        r = run_hook(f"git worktree remove {wt} && git branch -D session/prove",
                     mainrepo, session_id=CALLER)
        check("forma do incidente (remove && branch -D) bloqueia", blocked(r), r.stderr)
        check("encadeado com --force também",
              blocked(run_hook(f"git worktree remove --force {wt}", mainrepo, CALLER)))
        check("só o SEGUNDO segmento ofende (git status && branch -D) bloqueia",
              blocked(run_hook("git status && git branch -D session/prove", mainrepo, CALLER)))
        check("git -C <repo> worktree remove bloqueia",
              blocked(run_hook(f"git -C {mainrepo} worktree remove {wt}", outside, CALLER)))

        check("branch -D com dono vivo no branch bloqueia",
              blocked(run_hook("git branch -D session/prove", mainrepo, CALLER)))
        check("branch -d com dono vivo no branch bloqueia",
              blocked(run_hook("git branch -d session/prove", mainrepo, CALLER)))
        check("branch --delete --force bloqueia",
              blocked(run_hook("git branch --delete --force session/prove", mainrepo, CALLER)))
        check("branch -fd (cluster) bloqueia",
              blocked(run_hook("git branch -fd session/prove", mainrepo, CALLER)))

        # ── caminho relativo / nome do slice ────────────────────────────────
        check("cd <main> && worktree remove <nome do slice> bloqueia",
              blocked(run_hook(f"cd {mainrepo} && git worktree remove wt-prove", outside, CALLER)))
        check("caminho relativo ../wt-prove bloqueia",
              blocked(run_hook("git worktree remove ../wt-prove", mainrepo, CALLER)))

        # ── a sessão que chama não se bloqueia — por session_id, não por cwd ─
        clear_entries(mainrepo)
        write_entry(mainrepo, CALLER, wt, "session/prove")
        check("a própria sessão (mesmo session_id, cwd diferente do payload) libera",
              not blocked(run_hook(f"git worktree remove {wt}", mainrepo, session_id=CALLER)))
        check("a própria sessão no branch libera",
              not blocked(run_hook("git branch -D session/prove", mainrepo, session_id=CALLER)))

        # fb-20261013-1: outra sessão viva NO MESMO cwd do chamador continua visível
        write_entry(mainrepo, OWNER, wt, "session/prove")
        r = run_hook(f"git worktree remove {wt}", wt, session_id=CALLER)
        check("outra sessão com o MESMO cwd do chamador ainda bloqueia (fb-20261013-1)",
              blocked(r), r.stderr)
        check("sem session_id no payload nada é excluído",
              blocked(run_hook(f"git worktree remove {wt}", mainrepo)))

        # ── sessão morta não bloqueia ───────────────────────────────────────
        clear_entries(mainrepo)
        write_entry(mainrepo, OWNER, wt, "session/prove", pid=dead_pid())
        check("worktree remove com dono morto libera",
              not blocked(run_hook(f"git worktree remove {wt}", mainrepo, CALLER)))
        check("branch -D com dono morto libera",
              not blocked(run_hook("git branch -D session/prove", mainrepo, CALLER)))
        check("branch -d com dono morto libera",
              not blocked(run_hook("git branch -d session/prove", mainrepo, CALLER)))

        # ── texto e comandos que não removem nada ───────────────────────────
        clear_entries(mainrepo)
        write_entry(mainrepo, OWNER, wt, "session/prove")
        check("echo com o comando dentro NÃO bloqueia",
              not blocked(run_hook('echo "git worktree remove x"', mainrepo, CALLER)))
        check("grep pelo padrão NÃO bloqueia",
              not blocked(run_hook("grep -n 'git branch -D' README.md", mainrepo, CALLER)))
        check("git worktree list libera",
              not blocked(run_hook("git worktree list", mainrepo, CALLER)))
        check("git branch -a libera",
              not blocked(run_hook("git branch -a", mainrepo, CALLER)))
        check("git branch -D de branch sem dono libera",
              not blocked(run_hook("git branch -D session/outro", mainrepo, CALLER)))

        # ── fail-open ───────────────────────────────────────────────────────
        cmd = f"git worktree remove {wt}"
        check("outra tool não é gated",
              not blocked(run_hook(cmd, mainrepo, CALLER, tool_name="Read")))
        check("comando vazio libera", not blocked(run_hook("", mainrepo, CALLER)))
        check("payload ilegível falha aberto", not blocked(run_hook(None, mainrepo, raw="{nao é json")))
        check("payload vazio falha aberto", not blocked(run_hook(None, mainrepo, raw="")))
        check("fora de qualquer repo git libera",
              not blocked(run_hook(cmd, outside, CALLER)))
        check("aspas que não fecham falham aberto",
              not blocked(run_hook(f"git worktree remove '{wt}", mainrepo, CALLER)))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("all green")
    return 0


def test_worktree_remove_guard():
    FAILURES.clear()
    assert main() == 0, FAILURES


if __name__ == "__main__":
    sys.exit(main())
