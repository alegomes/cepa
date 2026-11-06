#!/usr/bin/env python3
"""Regression test: a `.claude/sessions/<id>.prune-on-exit` marker outlived the
worktree and branch it pointed to (feedback fb-20261105-2: a marker from
2026-10-29 stayed on disk after the session died before SessionEnd).

The marker is only consumed at SessionEnd of the SAME session_id, so nothing
else ever removed it. Contract guarded here, firing the real SessionStart hook:
  - session_worktree directory gone        → marker deleted, stderr names it;
  - worktree present but branch ref gone   → marker deleted, stderr names it;
  - worktree and branch both alive         → marker kept (SessionEnd consumes it);
  - unreadable (non-JSON) marker           → kept (we do not guess);
  - branch alive, worktree directory gone  → deleted by the worktree clause alone.

Run with `python3 tests/test_prune_marker_orphan.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
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


def marker(sdir: Path, sid: str, branch: str, wt: Path):
    (sdir / f"{sid}.prune-on-exit").write_text(json.dumps({
        "base_worktree": str(sdir.parent.parent), "base_branch": "main",
        "branch": branch, "session_worktree": str(wt), "discard": False}))


def build(base: Path):
    repo = base / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main", cwd=repo)
    git("commit", "-q", "--allow-empty", "-m", "init", cwd=repo)
    sdir = repo / ".claude" / "sessions"
    sdir.mkdir(parents=True)

    # (a) worktree directory never existed on disk
    marker(sdir, "aaaaaaaa-gone", "session/a", base / "wt-nao-existe")

    # (b) directory exists, branch ref deleted
    wtb = base / "wt-b"
    git("worktree", "add", "-q", "-b", "session/b", str(wtb), cwd=repo)
    (wtb / "f").write_text("x\n")
    git("add", "f", cwd=wtb)
    git("commit", "-q", "-m", "f", cwd=wtb)
    git("update-ref", "-d", "refs/heads/session/b", cwd=repo)
    marker(sdir, "bbbbbbbb-nobranch", "session/b", wtb)

    # (c) live: worktree + branch with a commit ahead (so auto_clean keeps it)
    wtc = base / "wt-c"
    git("worktree", "add", "-q", "-b", "session/x", str(wtc), cwd=repo)
    (wtc / "g").write_text("y\n")
    git("add", "g", cwd=wtc)
    git("commit", "-q", "-m", "g", cwd=wtc)
    marker(sdir, "cccccccc-live", "session/x", wtc)

    # (d) unreadable marker
    (sdir / "dddddddd-junk.prune-on-exit").write_text("not json {{{")

    # (e) branch alive (with a commit ahead, so nothing else reaps it) but the
    # worktree directory is gone: ONLY the "worktree gone" clause can fire here.
    wte = base / "wt-e"
    git("worktree", "add", "-q", "-b", "session/keep", str(wte), cwd=repo)
    (wte / "h").write_text("z\n")
    git("add", "h", cwd=wte)
    git("commit", "-q", "-m", "h", cwd=wte)
    git("worktree", "remove", "--force", str(wte), cwd=repo)
    marker(sdir, "eeeeeeee-dirgone", "session/keep", wte)
    return repo, sdir


def run_hook(repo: Path, home: Path):
    env = dict(os.environ, HOME=str(home))
    env.pop("CLAUDE_WT_CLAIM", None)
    return subprocess.run(
        [sys.executable, str(HOOKS / "session-registry.py")],
        input=json.dumps({"session_id": "teste-marca", "cwd": str(repo),
                          "hook_event_name": "SessionStart"}),
        capture_output=True, text=True, env=env, cwd=str(repo), timeout=60)


def main():
    with tempfile.TemporaryDirectory() as t:
        base = Path(t).resolve()
        (base / "home").mkdir()
        repo, sdir = build(base)
        p = run_hook(repo, base / "home")
        err = p.stderr

        check("hook exit 0", p.returncode == 0, str(p.returncode))
        check("(a) worktree sumido: marca apagada",
              not (sdir / "aaaaaaaa-gone.prune-on-exit").exists())
        check("(a) stderr nomeia a marca apagada",
              "removed orphan prune-on-exit marker" in err and "session/a" in err, err)
        check("(b) branch sumida: marca apagada",
              not (sdir / "bbbbbbbb-nobranch.prune-on-exit").exists())
        check("(b) stderr nomeia a marca apagada", "session/b" in err, err)
        check("(c) worktree e branch vivas: marca mantida",
              (sdir / "cccccccc-live.prune-on-exit").exists(), err)
        check("(d) marca ilegível: mantida",
              (sdir / "dddddddd-junk.prune-on-exit").exists(), err)
        check("(e) branch viva, pasta sumida: marca apagada",
              not (sdir / "eeeeeeee-dirgone.prune-on-exit").exists(), err)
        check("(e) stderr diz 'worktree gone' para session/keep",
              "session/keep (worktree gone)" in err, err)

    print()
    if failures:
        print(f"{len(failures)} FAIL")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    main()
