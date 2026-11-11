#!/usr/bin/env python3
"""Regression tests for the session worktree that vanished under a parked
conversation (feedback fb-20261110-4, session 56e8cebe / session/mkt-mode).

Three parts, all guarded here by firing the real hooks:
  1. last_seen is bumped on EVERY prompt (session-heartbeat.py, UserPromptSubmit),
     and a dead pid is refreshed so entry_is_live is true again. A session that
     prompted recently is NOT removed by auto_clean at the next SessionStart;
     one that did not, is (control).
  2. A resumed conversation whose worktree was removed is told, once, what
     disappeared (path, branch) and where the rescue went.
  3. The removal telemetry carries branch, path and by_session: both
     `worktree_auto_clean` (auto_clean) and `worktree_remove_allow`
     (worktree-remove-guard.py).

Run with `python3 tests/test_session_heartbeat.py`.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "common" / "hooks"
sys.path.insert(0, str(HOOKS))

from _isolated_telemetry import isolate

isolate()

failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   cwd=cwd, check=True, capture_output=True)


def dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def iso(delta=timedelta(0)):
    return (datetime.now(timezone.utc) - delta).isoformat(timespec="seconds")


def make_repo(base: Path):
    repo = base / "main"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    # Real projects gitignore .claude/; otherwise the artifact would make the
    # worktree "dirty" and auto_clean would (rightly) leave it alone.
    (repo / ".git" / "info" / "exclude").write_text(".claude/\n")
    return repo


def add_session_wt(repo: Path, base: Path, name: str, sid: str, age_h: int = 72):
    """A clean, zero-commit session worktree whose owner looks dead (pid gone,
    last_seen `age_h` hours ago) — exactly what auto_clean removes."""
    wt = base / f"wt-{name}"
    git("worktree", "add", "-q", "-b", f"session/{name}", str(wt), cwd=repo)
    (wt / ".claude").mkdir()
    (wt / ".claude" / "plan.md").write_text("plano\n")
    sdir = repo / ".claude" / "sessions"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / f"{sid}.json").write_text(json.dumps({
        "session_id": sid, "pid": dead_pid(), "hostname": socket.gethostname(),
        "cwd": str(wt), "worktree_path": str(wt), "branch": f"session/{name}",
        "is_session_worktree": True, "base_branch": "main",
        "started_at": iso(timedelta(hours=age_h)),
        "last_seen": iso(timedelta(hours=age_h))}))
    return wt, sdir


def env_for(tel: Path, home: Path):
    env = dict(os.environ, HOME=str(home), CEPA_TELEMETRY_DIR=str(tel))
    env.pop("CLAUDE_WT_CLAIM", None)
    env.pop("CLAUDE_PROJECT_DIR", None)
    return env


def run(hook, payload, cwd, env):
    return subprocess.run([sys.executable, str(HOOKS / hook)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=str(cwd), timeout=60)


def prompt(sid, cwd, env):
    return run("session-heartbeat.py",
               {"session_id": sid, "cwd": str(cwd), "prompt": "oi",
                "hook_event_name": "UserPromptSubmit"}, cwd, env)


def start(sid, repo, env):
    return run("session-registry.py",
               {"session_id": sid, "cwd": str(repo), "hook_event_name": "SessionStart"},
               repo, env)


def events(tel: Path, name: str):
    out = []
    for f in tel.glob("events-*.jsonl"):
        for line in f.read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("event") == name:
                out.append(e)
    return out


def additional(res):
    try:
        return json.loads(res.stdout)["hookSpecificOutput"]["additionalContext"]
    except (ValueError, KeyError):
        return ""


def check_wiring():
    data = json.loads((REPO / "common" / ".claude-plugin" / "plugin.json").read_text())
    cmds = [h.get("command", "") for e in data["hooks"].get("UserPromptSubmit", [])
            for h in e.get("hooks", [])]
    check("plugin.json registers session-heartbeat on UserPromptSubmit",
          any("hooks/session-heartbeat.py" in c for c in cmds))


def main():
    check_wiring()
    with tempfile.TemporaryDirectory() as t:
        base = Path(t).resolve()
        (base / "home").mkdir()
        tel = base / "tel"
        env = env_for(tel, base / "home")
        os.environ["HOME"] = str(base / "home")   # _wtlib.index_* use Path.home()
        repo = make_repo(base)

        # ── 1. a prompt bumps last_seen and revives the pid ─────────────────
        wt_a, sdir = add_session_wt(repo, base, "alive", "aaaaaaaa-prompted")
        wt_b, _ = add_session_wt(repo, base, "idle", "bbbbbbbb-silent")
        before = json.loads((sdir / "aaaaaaaa-prompted.json").read_text())
        r = prompt("aaaaaaaa-prompted", wt_a, env)
        after = json.loads((sdir / "aaaaaaaa-prompted.json").read_text())
        check("heartbeat exits 0 and prints nothing when the worktree exists",
              r.returncode == 0 and r.stdout.strip() == "", r.stdout + r.stderr)
        check("prompt bumps last_seen", after["last_seen"] > before["last_seen"])
        check("dead pid is refreshed to a live one", after["pid"] != before["pid"]
              and subprocess.run(["kill", "-0", str(after["pid"])]).returncode == 0)
        import _wtlib as L
        check("entry is live again after the prompt", L.entry_is_live(after))
        live_pid = os.getpid()
        after["pid"] = live_pid
        (sdir / "aaaaaaaa-prompted.json").write_text(json.dumps(after))
        prompt("aaaaaaaa-prompted", wt_a, env)
        check("a live pid is left alone",
              json.loads((sdir / "aaaaaaaa-prompted.json").read_text())["pid"] == live_pid)
        check("no entry -> no entry created",
              prompt("zzzzzzzz-unknown", repo, env).returncode == 0
              and not (sdir / "zzzzzzzz-unknown.json").exists())
        check("garbage payload exits 0",
              subprocess.run([sys.executable, str(HOOKS / "session-heartbeat.py")],
                             input="{nao", capture_output=True, text=True).returncode == 0)

        # ── auto_clean at the next SessionStart: prompted kept, silent removed
        r = start("cccccccc-newcomer", repo, env)
        check("SessionStart exits 0", r.returncode == 0, r.stderr)
        check("worktree of the session that prompted recently is KEPT", wt_a.is_dir())
        check("control: worktree of the silent dead session is removed", not wt_b.exists())

        # ── 3a. auto_clean telemetry ────────────────────────────────────────
        ev = events(tel, "worktree_auto_clean")
        mine = [e for e in ev if e.get("branch") == "session/idle"]
        check("worktree_auto_clean carries branch, path, by_session",
              len(mine) == 1 and mine[0].get("path") == str(wt_b)
              and mine[0].get("by_session") == "cccccccc-newcomer", str(ev))
        check("no auto_clean event for the kept worktree",
              not [e for e in ev if e.get("branch") == "session/alive"])

        # ── 2. resumed conversation of the removed worktree ─────────────────
        check("rescue copied the artifact",
              (repo / ".claude" / "rescued" / "session-idle" / "plan.md").is_file())
        tomb = L.read_tombstone(str(repo), "bbbbbbbb-silent")
        check("tombstone records branch, path and who removed",
              bool(tomb) and tomb.get("branch") == "session/idle"
              and tomb.get("worktree_path") == str(wt_b)
              and tomb.get("removed_by_session") == "cccccccc-newcomer", str(tomb))
        check("tombstone is not mistaken for a live session",
              all(e.get("session_id") != "bbbbbbbb-silent" for _, e in L.read_entries(str(repo))))
        r = prompt("bbbbbbbb-silent", repo, env)   # resumed from the main root
        msg = additional(r)
        check("first resumed prompt warns with path, branch, rescue dir and remover",
              str(wt_b) in msg and "session/idle" in msg
              and str(repo / ".claude" / "rescued" / "session-idle") in msg
              and "cccccccc" in msg, msg or r.stderr)
        check("the warning is in pt-BR", "não existe mais" in msg)
        r2 = prompt("bbbbbbbb-silent", repo, env)
        check("second prompt does NOT repeat the warning", additional(r2) == "" and r2.returncode == 0)
        # REAL resume layout: the worktree is a SIBLING of the main clone and
        # both cwd and CLAUDE_PROJECT_DIR are the deleted path. Walking up
        # cannot reach the clone; the home-dir index (written at SessionStart
        # and with the tombstone) has to.
        sdir_t = sdir / "bbbbbbbb-silent.gone"
        t2 = json.loads(sdir_t.read_text())
        t2.pop("warned_at")
        sdir_t.write_text(json.dumps(t2))
        outside = base / "elsewhere"
        outside.mkdir()
        r3 = run("session-heartbeat.py",
                 {"session_id": "bbbbbbbb-silent", "cwd": str(wt_b), "prompt": "x"},
                 outside, dict(env, CLAUDE_PROJECT_DIR=str(wt_b)))
        check("cwd and CLAUDE_PROJECT_DIR both the deleted sibling worktree: still warns",
              "session/idle" in additional(r3), r3.stdout + r3.stderr)
        check("index maps the deleted worktree to the main root",
              L.index_lookup(str(wt_b)) == str(repo) or
              os.path.realpath(L.index_lookup(str(wt_b))) == os.path.realpath(str(repo)))
        # a subdirectory of the deleted worktree resolves through its ancestor
        check("index resolves a subdirectory of the deleted worktree",
              L.index_lookup(str(wt_b / "src" / "x")) != "")
        # SessionStart in a linked worktree registers it in the index
        wt_s = base / "wt-start"
        git("worktree", "add", "-q", "-b", "session/start", str(wt_s), cwd=repo)
        start("ffffffff-linked", wt_s, env)
        check("SessionStart in a linked worktree registers it in the index",
              L.index_lookup(str(wt_s)) != "")

        # entry-only fallback: entry survives (live pid), cwd was deleted
        wt_c, _ = add_session_wt(repo, base, "orphan", "dddddddd-entry")
        e = json.loads((sdir / "dddddddd-entry.json").read_text())
        e["pid"] = os.getpid()
        e["last_seen"] = iso()
        (sdir / "dddddddd-entry.json").write_text(json.dumps(e))
        git("worktree", "remove", "--force", str(wt_c), cwd=repo)
        r = prompt("dddddddd-entry", repo, env)
        check("entry whose cwd vanished also warns", "session/orphan" in additional(r),
              r.stdout + r.stderr)
        check("...and only once", additional(prompt("dddddddd-entry", repo, env)) == "")

        # ── 3b. worktree-remove-guard telemetry ─────────────────────────────
        wt_d = base / "wt-guard"
        git("worktree", "add", "-q", "-b", "session/guard", str(wt_d), cwd=repo)
        r = run("worktree-remove-guard.py",
                {"tool_name": "Bash", "session_id": "eeeeeeee-remover", "cwd": str(repo),
                 "tool_input": {"command": f"git worktree remove {wt_d}"}}, repo, env)
        ev = [e for e in events(tel, "worktree_remove_allow") if e.get("branch") == "session/guard"]
        check("worktree_remove_allow carries branch, path, by_session",
              r.returncode == 0 and len(ev) == 1 and ev[0].get("path") == str(wt_d)
              and ev[0].get("by_session") == "eeeeeeee-remover", str(ev))
        r = run("worktree-remove-guard.py",
                {"tool_name": "Bash", "session_id": "eeeeeeee-remover", "cwd": str(repo),
                 "tool_input": {"command": "git branch -D session/guard"}}, repo, env)
        ev = [e for e in events(tel, "worktree_remove_allow")
              if e.get("branch") == "session/guard" and e.get("path") == ""]
        check("git branch -D records the branch with an empty path and the session",
              len(ev) == 1 and ev[0].get("by_session") == "eeeeeeee-remover", str(ev))

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S): {', '.join(failures)}")
        return 1
    print("all green")
    return 0


def test_session_heartbeat():
    failures.clear()
    assert main() == 0, failures


if __name__ == "__main__":
    sys.exit(main())
