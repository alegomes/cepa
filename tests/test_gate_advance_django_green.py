"""After a green `manage.py test`, the build gate releases `git commit`
(spec build-django-manage-py-test, CS-5).

The two hooks are run as subprocesses, in the order Claude Code runs them: `capture-build-result.py`
(PostToolUse of the test command) and then `gate-advance.py` (PreToolUse of `git commit`). The repo is a
Python project (`pyproject.toml`) whose `.claude/last-build.json` is STALE because a `.py` was edited.
Before CS-1 the green run left the state STALE and the commit stayed blocked with "build is STALE"."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _isolated_telemetry import isolate

isolate()

HOOKS = Path(__file__).resolve().parents[1] / "common" / "hooks"

GREEN = "Found 12 test(s).\nRan 12 tests in 0.312s\n\nOK"
RED = "Found 12 test(s).\nRan 12 tests in 0.312s\n\nFAILED (failures=1)"
COMMIT = "git commit -m x"


def _git(args, cwd):
    subprocess.run(["git"] + args, cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def stale_repo(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    _git(["init", "-q", "-b", "main"], proj)
    _git(["config", "user.email", "t@t"], proj)
    _git(["config", "user.name", "t"], proj)
    (proj / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    (proj / "manage.py").write_text("")
    (proj / "app.py").write_text("x = 1\n")
    _git(["add", "-A"], proj)
    _git(["commit", "-qm", "seed"], proj)
    (proj / "app.py").write_text("x = 2\n")
    (proj / ".claude").mkdir()
    (proj / ".claude" / "last-build.json").write_text(json.dumps({
        "status": "STALE", "since": "2026-11-15T10:00:00+00:00", "after_edit_to": str(proj / "app.py"),
    }))
    (tmp_path / "tmp").mkdir()
    return proj


def _hook(script, proj, payload):
    env = {**os.environ, "TMPDIR": str(proj.parent / "tmp")}
    return subprocess.run([sys.executable, str(HOOKS / script)], input=json.dumps(payload),
                          text=True, capture_output=True, cwd=proj, env=env)


def _capture(proj, command, stdout, extra=None):
    return _hook("capture-build-result.py", proj, {
        "cwd": str(proj), "session_id": "s-cs5", "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_response": {"stdout": stdout, "stderr": "", "interrupted": False, **(extra or {})}})


def _gate(proj, command=COMMIT):
    return _hook("gate-advance.py", proj, {
        "cwd": str(proj), "session_id": "s-cs5", "hook_event_name": "PreToolUse",
        "tool_name": "Bash", "tool_input": {"command": command}})


def test_stale_blocks_commit_before_any_test_run(stale_repo):
    r = _gate(stale_repo)
    assert r.returncode == 2
    assert "build is STALE" in r.stderr


@pytest.mark.parametrize("command", ["uv run python manage.py test", "python manage.py test"])
def test_green_manage_py_test_releases_git_commit(stale_repo, command):
    _capture(stale_repo, command, GREEN)
    r = _gate(stale_repo)
    assert r.returncode == 0, r.stderr
    assert "BLOCKED" not in r.stderr


def test_red_manage_py_test_keeps_git_commit_blocked(stale_repo):
    _capture(stale_repo, "python manage.py test", RED, extra={"exit_code": 1})
    r = _gate(stale_repo)
    assert r.returncode == 2
    assert "BLOCKED" in r.stderr


def test_command_that_is_not_a_test_run_keeps_git_commit_blocked(stale_repo):
    _capture(stale_repo, "python manage.py testserver", GREEN)
    r = _gate(stale_repo)
    assert r.returncode == 2
    assert "build is STALE" in r.stderr
