"""`manage.py test` (Django) green must reach .claude/last-build.json (spec build-django-manage-py-test, CS-1).
CC omits the exit code on success, so the green is read from the unittest summary: `Ran N tests in ...`
followed by a line that is `OK` alone (or `OK (...)`). A bare `OK` substring is not a marker (any app log has it)."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from _isolated_telemetry import isolate

isolate()

HOOK = Path(__file__).resolve().parents[1] / "common" / "hooks" / "capture-build-result.py"
spec = importlib.util.spec_from_file_location("capture_build_result", HOOK)
cbr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cbr)

GREEN = "Found 12 test(s).\nRan 12 tests in 0.312s\n\nOK"


def _run_hook(tmp_path, command, output):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "manage.py").write_text("")
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    payload = {"cwd": str(proj), "session_id": "s-django", "tool_name": "Bash",
               "tool_input": {"command": command},
               "tool_response": {"stdout": output, "stderr": "", "interrupted": False}}
    subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True,
                   capture_output=True, cwd=proj, env={**os.environ, "TMPDIR": str(tmp)})
    state = proj / ".claude" / "last-build.json"
    return json.loads(state.read_text()) if state.exists() else None


@pytest.mark.parametrize("command", [
    "uv run python manage.py test",
    "python manage.py test",
    "docker compose exec web python manage.py test",
])
def test_green_manage_py_test_writes_success(tmp_path, command):
    st = _run_hook(tmp_path, command, GREEN)
    assert st and st["status"] == "SUCCESS"


def test_singular_ran_1_test_is_success():
    assert cbr.classify("python manage.py test", "Ran 1 test in 0.001s\n\nOK\n", None)[:2] == ("SUCCESS", "unittest")


def test_ok_with_skipped_is_success():
    out = "Ran 5 tests in 0.1s\n\nOK (skipped=2)\n"
    assert cbr.classify("python manage.py test", out, None)[:2] == ("SUCCESS", "unittest")


@pytest.mark.parametrize("tail", ["OK (expected failures=1)", "OK (skipped=1, expected failures=1)"])
def test_ok_with_expected_failures_is_success(tail):
    out = "Ran 5 tests in 0.1s\n\n" + tail + "\n"
    assert cbr.classify("python manage.py test", out, None)[:2] == ("SUCCESS", "unittest")


@pytest.mark.parametrize("exit_code", [None, 1])
def test_green_block_does_not_hide_red_block(exit_code):
    out = "Ran 3 tests in 0.1s\n\nOK\nRan 2 tests in 0.1s\n\nFAILED (failures=1)\n"
    cmd = "python manage.py test a; python manage.py test b"
    assert cbr.classify(cmd, out, exit_code)[:2] == ("FAILURE", "unittest")


def test_crlf_output_is_success():
    out = "Ran 3 tests in 0.1s\r\n\r\nOK\r\n"
    assert cbr.classify("python manage.py test", out, None)[:2] == ("SUCCESS", "unittest")


def test_ran_zero_tests_is_not_success():
    assert cbr.classify("python manage.py test", "Ran 0 tests in 0.000s\n\nOK\n", None)[:2] == (None, "unittest")


def test_ok_only_inside_a_log_line_is_not_success():
    assert cbr.classify("python manage.py test", "GET /health 200 OK\n", None)[:2] == (None, "unittest")


def test_testserver_is_not_matched():
    assert cbr.classify("python manage.py testserver", GREEN, None)[:2] == (None, None)


def test_quoted_echo_is_not_matched():
    assert cbr.classify('echo "manage.py test"', GREEN, None)[:2] == (None, None)


_RAN = "Ran 3 tests in 0.1s\n\n"
_GREEN_OUT = _RAN + "OK\n"


@pytest.mark.parametrize("command", [
    "python ./manage.py test",
    "python3 src/manage.py test app.tests",
    "./manage.py test",
])
def test_manage_py_behind_a_path_is_matched(command):
    assert cbr.classify(command, _GREEN_OUT, None)[:2] == ("SUCCESS", "unittest")


@pytest.mark.parametrize("tail", ["not OK\n", "OKAY\n", "OK then something\n", "OK (skipped=1\nmore)\n"])
def test_ok_line_must_be_exactly_the_runner_verdict(tail):
    assert cbr.classify("python manage.py test", _RAN + tail, None)[:2] == (None, "unittest")


@pytest.mark.parametrize("noise", ["log: x FAILED (retrying)\n", "FAILED to connect to cache, retrying\n"])
def test_failed_not_at_verdict_line_does_not_hide_green(noise):
    assert cbr.classify("python manage.py test", noise + _GREEN_OUT, None)[:2] == ("SUCCESS", "unittest")
