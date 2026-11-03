#!/usr/bin/env python3
"""A session does not end its turn owing a validation-lead verdict
(fb-20261103-1).

Against the real CLI and the real hook, in a build-hex repo:

  - `finish --status done` without `docs/validation/<id>.yaml` is refused AND
    leaves a marker under the session's folder;
  - the Stop hook blocks that session, naming the item and the way out;
  - another session is not blocked; `stop_hook_active` is not blocked;
  - with the verdict on disk the block says to close with `done`;
  - `done` with the verdict clears the marker and the hook lets the turn end;
  - `pending` without the verdict leaves a marker; `blocked` clears it;
  - no session id in the environment: nothing written, nothing blocked.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import item, build_repo  # noqa: E402
from test_cepa_until_decide import CEPA_PLAN  # noqa: E402

HOOK = Path(__file__).resolve().parent.parent / "common" / "hooks" / "validation-owed-gate.py"
FAILURES = []


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def env_for(home, sid="S1"):
    e = dict(os.environ, HOME=str(home), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
             GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for k in ("CEPA_UNTIL_RUN", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "CEPA_MODO"):
        e.pop(k, None)
    if sid:
        e["CLAUDE_CODE_SESSION_ID"] = sid
    return e


def plan(root, env, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN), *args, "--repo", str(root)],
                          capture_output=True, text=True, env=env)


def stop(home, sid, active=False):
    p = subprocess.run([sys.executable, str(HOOK)], capture_output=True, text=True,
                       env=env_for(home, None),
                       input=json.dumps({"session_id": sid, "stop_hook_active": active}))
    out = p.stdout.strip()
    return json.loads(out) if out else None


def markers(home):
    return sorted(p.name for p in (home / ".claude" / "cepa-validation-owed").glob("*/*.json"))


def setup(tmp):
    root = build_repo(tmp, [item("a1"), item("a2")])
    (root / ".claude" / "topology").write_text("build-hex\n")
    home = Path(tmp) / "home"
    home.mkdir()
    return root, home


def write_verdict(root, ident):
    d = root / "docs" / "validation"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ident}.yaml").write_text(f"key: {ident}\nverdict: READY-TO-SHIP\n")


def test_done_refused_marks_and_stop_blocks_until_closed():
    with tempfile.TemporaryDirectory() as tmp:
        root, home = setup(tmp)
        env = env_for(home)
        p = plan(root, env, "finish", "fila", "a1", "--status", "done", "--evidence", "construído")
        check("done sem veredito é recusado", p.returncode == 2, p.stdout + p.stderr)
        check("...e deixa marcador", markers(home) == ["fila__a1.json"], markers(home))
        r = stop(home, "S1")
        check("Stop da mesma sessão bloqueia", r and r.get("decision") == "block", r)
        check("...nomeando o item e o validation-lead",
              r and "a1" in r["reason"] and "validation-lead" in r["reason"], r)
        check("outra sessão não é bloqueada", stop(home, "S2") is None)
        check("stop_hook_active não bloqueia de novo", stop(home, "S1", active=True) is None)
        write_verdict(root, "a1")
        r = stop(home, "S1")
        check("com veredito no disco, manda fechar com done",
              r and "--status done" in r["reason"] and "já está" in r["reason"], r)
        p = plan(root, env, "finish", "fila", "a1", "--status", "done", "--evidence", "validado")
        check("done com veredito sai 0", p.returncode == 0, p.stderr)
        check("...limpa o marcador", markers(home) == [], markers(home))
        check("...e o Stop libera", stop(home, "S1") is None)


def test_pending_marks_and_blocked_clears():
    with tempfile.TemporaryDirectory() as tmp:
        root, home = setup(tmp)
        env = env_for(home)
        p = plan(root, env, "finish", "fila", "a2", "--status", "pending", "--evidence", "voltou")
        check("pending sai 0", p.returncode == 0, p.stderr)
        check("...avisa que o fim do turno cobra", "fim do turno" in p.stdout, p.stdout)
        check("...e deixa marcador", markers(home) == ["fila__a2.json"], markers(home))
        p = plan(root, env, "finish", "fila", "a2", "--status", "blocked", "--evidence",
                 "sem acesso", "--impede", "falta um acesso de fora")
        check("blocked sai 0", p.returncode == 0, p.stderr)
        check("...e limpa o marcador", markers(home) == [], markers(home))


def test_without_session_id_nothing_is_written():
    with tempfile.TemporaryDirectory() as tmp:
        root, home = setup(tmp)
        p = plan(root, env_for(home, None), "finish", "fila", "a1", "--status", "done",
                 "--evidence", "x")
        check("recusa continua", p.returncode == 2)
        check("...sem marcador", markers(home) == [], markers(home))


def test_topology_without_validation_writes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root, home = setup(tmp)
        (root / ".claude" / "topology").write_text("build-solo\n")
        p = plan(root, env_for(home), "finish", "fila", "a1", "--status", "pending",
                 "--evidence", "x")
        check("build-solo pending sai 0", p.returncode == 0, p.stderr)
        check("...sem marcador", markers(home) == [], markers(home))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"\n{name}")
            fn()
    print("\nall green" if not FAILURES else f"\n{len(FAILURES)} FAIL")
    sys.exit(1 if FAILURES else 0)
