#!/usr/bin/env python3
"""`cepa` decides isolation by the real worktree, not by the branch name.

The loss this guards (2026-11-09): a session ran `git checkout -b session/x` in
the main tree. A later `cepa --mode construction -s pt2en` saw a `session/*`
branch, concluded it was already isolated and opened in the main tree, on the
other session's branch, ignoring `-s`. The registry recorded it as a session
worktree, and its SessionEnd autosave would commit the other session's files.

Run: python3 tests/test_cepa_slice_isolation.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

for _k in ("CEPA_PROMPT", "CEPA_PROMPT_MODO", "CEPA_LAUNCH_ID", "CLAUDE_WT_CLAIM",
           "CEPA_MODO", "CEPA_MODO_DEFAULT"):
    os.environ.pop(_k, None)

REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"
REGISTRY = REPO / "common" / "hooks" / "session-registry.py"
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _wtlib as L  # noqa: E402

STUB = """#!/bin/sh
printf '%s\\t%s\\n' "$(pwd -P)" "$(git rev-parse --abbrev-ref HEAD)" >> "$STUB_LOG"
"""
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
failures = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + ("" if cond else f" {detail}"))
    if not cond:
        failures.append(name)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, check=True,
                          capture_output=True, text=True).stdout.strip()


class World:
    """A repo whose MAIN tree sits on `session/other`."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name).resolve()
        self.repo = t / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", ".")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")
        git(self.repo, "checkout", "-q", "-b", "session/other")
        self.stub = t / "fakeclaude"
        self.stub.write_text(STUB)
        self.stub.chmod(0o755)
        self.log = t / "stub.log"
        self.home = t / "worktrees"
        self.telemetry = t / "telemetry"
        self.tmp_home = t / "home"
        return self

    def __exit__(self, *a):
        self.tmp.cleanup()

    def cepa(self, *args, cwd=None, extra_env=None):
        env = {**os.environ, "CLAUDE_WT_CLAUDE_BIN": str(self.stub), "CEPA_PREFLIGHT": "off",
               "CEPA_ENCADEAR": "off", "CEPA_WORKTREE_HOME": str(self.home),
               "CEPA_TELEMETRY_DIR": str(self.telemetry), "STUB_LOG": str(self.log),
               # the launcher and registry write ~/.claude/cepa-wt-index/: keep it out of the real home
               "HOME": str(self.tmp_home), **(extra_env or {})}
        return subprocess.run([str(CEPA), "--mode", "construction", *args],
                              cwd=cwd or self.repo, env=env, capture_output=True, text=True,
                              timeout=60, stdin=subprocess.DEVNULL)

    def calls(self):
        if not self.log.exists():
            return []
        return [x.split("\t") for x in self.log.read_text().splitlines()]

    def occupy_main(self):
        sdir = self.repo / ".claude" / "sessions"
        sdir.mkdir(parents=True, exist_ok=True)
        (sdir / "occupant.json").write_text(json.dumps({
            "session_id": "occupant", "pid": os.getpid(), "hostname": L.host(),
            "cwd": str(self.repo), "branch": "session/other",
            "started_at": L.now_iso(), "last_seen": L.now_iso()}))

    def linked(self, name):
        path = self.home / f"repo-{name}"
        git(self.repo, "worktree", "add", "-q", str(path), "-b", f"session/{name}")
        return path

    def hook(self, event, cwd, sid="s1"):
        return subprocess.run([sys.executable, str(REGISTRY)], cwd=cwd, text=True,
                              env={**GIT_ENV, "HOME": str(self.tmp_home)},
                              input=json.dumps({"session_id": sid, "cwd": str(cwd),
                                                "hook_event_name": event}),
                              capture_output=True, timeout=60)


def t_slice_from_main_tree_on_session_branch():
    with World() as w:
        r = w.cepa("-s", "pt2en")
        want = [str(w.home / "repo-pt2en"), "session/pt2en"]
        check("-s opens its worktree from a main tree on session/*",
              w.calls() == [want], f"{w.calls()} {r.stderr}")


def t_occupied_main_tree_on_session_branch_isolates():
    with World() as w:
        w.occupy_main()
        r = w.cepa()
        c = w.calls()
        check("occupied main tree on session/* isolates the new session",
              len(c) == 1 and c[0][0] != str(w.repo) and c[0][1] not in ("session/other", ""),
              f"{c} {r.stderr}")


def t_free_main_tree_runs_in_place():
    with World() as w:
        w.cepa()
        check("free main tree on session/* runs in place",
              w.calls() == [[str(w.repo), "session/other"]], str(w.calls()))


def t_linked_worktree_without_slice_stays():
    with World() as w:
        wt = w.linked("mine")
        w.occupy_main()
        w.cepa(cwd=wt)
        check("linked session worktree without -s stays put",
              w.calls() == [[str(wt), "session/mine"]], str(w.calls()))


def t_slice_from_linked_worktree():
    with World() as w:
        wt = w.linked("mine")
        w.cepa("-s", "another", cwd=wt)
        want = [str(w.home / "repo-another"), "session/another"]
        check("-s from a linked worktree opens the named one",
              w.calls() == [want], str(w.calls()))


def t_slice_failure_aborts():
    with World() as w:
        # session/other is checked out in the main tree: `git worktree add` refuses.
        r = w.cepa("-s", "other")
        check("-s that cannot be honoured opens nothing", w.calls() == [], str(w.calls()))
        check("-s failure exits non-zero with cepa's own message",
              r.returncode != 0
              and "could not open the worktree session/other" in r.stderr,
              f"{r.returncode} {r.stderr}")


def t_picker_from_linked_worktree():
    with World() as w:
        wt = w.linked("mine")
        git(w.repo, "branch", "session/target")
        fake = w.home.parent / "fakebin"
        fake.mkdir()
        (fake / "fzf").write_text("#!/bin/sh\ngrep '^target'\n")
        (fake / "fzf").chmod(0o755)
        w.cepa("-s", cwd=wt, extra_env={"PATH": f"{fake}:{os.environ['PATH']}"})
        want = [str(w.home / "repo-target"), "session/target"]
        check("-s with no name from a linked worktree runs the picker",
              w.calls() == [want], str(w.calls()))


def t_is_linked_worktree_outside_repo():
    with tempfile.TemporaryDirectory() as d:
        check("is_linked_worktree is False outside any repository",
              L.is_linked_worktree(d) is False)


def t_registry_flag_follows_real_worktree():
    with World() as w:
        w.hook("SessionStart", w.repo, "main-s")
        # After the first SessionStart: that hook reaps empty worktrees.
        wt = w.linked("mine")
        w.hook("SessionStart", wt, "wt-s")
        sdir = w.repo / ".claude" / "sessions"
        main = json.loads((sdir / "main-s.json").read_text())
        linked = json.loads((sdir / "wt-s.json").read_text())
        check("registry: main tree on session/* is not a session worktree",
              main["is_session_worktree"] is False, str(main))
        check("registry: linked session/* worktree is a session worktree",
              linked["is_session_worktree"] is True, str(linked))


def t_autosave_only_in_linked_worktree():
    with World() as w:
        (w.repo / "others-work.txt").write_text("not mine")
        before = git(w.repo, "rev-parse", "HEAD")
        w.hook("SessionEnd", w.repo)
        check("autosave leaves the main tree's files uncommitted",
              git(w.repo, "rev-parse", "HEAD") == before
              and "others-work.txt" in git(w.repo, "status", "--porcelain"))
        wt = w.linked("mine")
        (wt / "mine.txt").write_text("wip")
        w.hook("SessionEnd", wt)
        check("autosave still commits in a linked session worktree",
              git(wt, "log", "-1", "--format=%s").startswith("WIP: session autosave"))


for fn in (t_slice_from_main_tree_on_session_branch,
           t_occupied_main_tree_on_session_branch_isolates,
           t_free_main_tree_runs_in_place,
           t_linked_worktree_without_slice_stays,
           t_slice_from_linked_worktree,
           t_slice_failure_aborts,
           t_picker_from_linked_worktree,
           t_is_linked_worktree_outside_repo,
           t_registry_flag_follows_real_worktree,
           t_autosave_only_in_linked_worktree):
    fn()

print(f"\n{len(failures)} failure(s)" if failures else "\nall ok")
sys.exit(1 if failures else 0)
