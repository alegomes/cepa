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


def _run_hook(tmp_path, command, output, stderr="", extra=None):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "manage.py").write_text("")
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    payload = {"cwd": str(proj), "session_id": "s-django", "tool_name": "Bash",
               "tool_input": {"command": command},
               "tool_response": {"stdout": output, "stderr": stderr, "interrupted": False, **(extra or {})}}
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


@pytest.mark.parametrize("out", [
    "Ran 3 tests in 0.1s\nsome log line\nOK\n",   # text between Ran and OK
    "foo Ran 3 tests in 1s\n\nOK\n",              # Ran not at line start
    "Ran 3 tests\n\nOK\n",                        # no ' in <time>' clause
    "Ran 3 tests\nin 0.1s\n\nOK\n",               # Ran line split across lines
    "Ran 3\ntests in 0.1s\n\nOK\n",
    "Ran 3 tests in 0.1s\n\nOK (a (b))\n",        # nested parentheses
    "Ran 3 tests in 0.1s\n\nOK(skipped=1)\n",     # no space before the parenthesis
])
def test_malformed_unittest_summary_is_not_success(out):
    assert cbr.classify("python manage.py test", out, None)[:2] == (None, "unittest")


@pytest.mark.parametrize("out", [
    "Ran 3 tests in 0.1s\n\n\n\nOK\n",            # several blank lines tolerated
    "Ran 3 tests in 0.1s\nOK\n",                  # zero blank lines tolerated
])
def test_any_number_of_blank_lines_before_ok_is_success(out):
    assert cbr.classify("python manage.py test", out, None)[:2] == ("SUCCESS", "unittest")


@pytest.mark.parametrize("command", [
    "xmanage.py test",
    "python xmanage.py test",
    "python manage.pytest",
    "python manageXpy test",
])
def test_command_must_be_manage_py_test_exactly(command):
    assert cbr.classify(command, _GREEN_OUT, None)[:2] == (None, None)


@pytest.mark.parametrize("command", [
    "manage.py test",                              # at the very start of the command
    "python manage.py  test",                      # two spaces
])
def test_manage_py_test_start_of_command_and_extra_spaces(command):
    assert cbr.classify(command, _GREEN_OUT, None)[:2] == ("SUCCESS", "unittest")


# --- CS-2: a failing or erroring `manage.py test` records FAILURE (cli surface) ---

RED = "Found 12 test(s).\nRan 12 tests in 0.4s\n\nFAILED (failures=1, errors=2)"


@pytest.mark.parametrize("command", [
    "uv run python manage.py test",
    "python manage.py test",
    "docker compose exec web python manage.py test",
])
def test_failed_manage_py_test_writes_failure(tmp_path, command):
    st = _run_hook(tmp_path, command, RED)
    assert st and st["status"] == "FAILURE" and st["kind"] == "unittest"


@pytest.mark.parametrize("tail", [
    "FAILED (failures=1)",
    "FAILED (errors=2)",
    "FAILED (failures=1, skipped=2)",
])
def test_each_failed_summary_shape_writes_failure(tmp_path, tail):
    st = _run_hook(tmp_path, "python manage.py test", "Ran 5 tests in 0.1s\n\n" + tail + "\n")
    assert st and st["status"] == "FAILURE"


def test_failed_summary_only_in_stderr_writes_failure(tmp_path):
    # unittest writes its summary to stderr; with empty stdout the hook falls back to it
    st = _run_hook(tmp_path, "python manage.py test", "", stderr=RED)
    assert st and st["status"] == "FAILURE"


def test_failed_summary_in_stderr_with_chatty_stdout_writes_failure(tmp_path):
    # real Django: "Found N test(s)" / system-check lines go to stdout, the verdict to stderr
    st = _run_hook(tmp_path, "python manage.py test",
                   "Found 12 test(s).\nSystem check identified no issues (0 silenced).\n",
                   stderr="Ran 12 tests in 0.4s\n\nFAILED (failures=1)\n")
    assert st and st["status"] == "FAILURE"


def test_markerless_exit_1_writes_failure(tmp_path):
    # e.g. a settings ImportError before the runner prints any summary: no marker, only the exit code
    st = _run_hook(tmp_path, "python manage.py test",
                   "Traceback (most recent call last):\nImportError: No module named 'settings'\n",
                   extra={"exit_code": 1})
    assert st and st["status"] == "FAILURE" and st["kind"] == "unittest"


def test_green_verdict_only_in_stderr_writes_success(tmp_path):
    st = _run_hook(tmp_path, "python manage.py test",
                   "Found 12 test(s).\nSystem check identified no issues (0 silenced).\n",
                   stderr="Ran 12 tests in 0.3s\n\nOK\n")
    assert st and st["status"] == "SUCCESS" and st["kind"] == "unittest"


_WARN = "DeprecationWarning: error in foo\n"


@pytest.mark.parametrize("command", ["pytest && python manage.py test", "pytest"])
def test_stderr_not_appended_when_kind_is_not_unittest(tmp_path, command):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    with_err = _run_hook(tmp_path / "a", command, "3 passed in 0.1s\n", stderr=_WARN)
    without = _run_hook(tmp_path / "b", command, "3 passed in 0.1s\n")
    assert with_err and with_err["status"] != "FAILURE"
    assert with_err["status"] == without["status"] and with_err["kind"] == without["kind"]


def test_quoted_manage_py_test_gets_no_stderr(tmp_path):
    assert cbr.add_unittest_stderr('echo "manage.py test"', "out", {"stderr": "Ran 1 test\nOK"}) == "out"


@pytest.mark.parametrize("out, expected", [
    ("Ran 3 tests in 0.1s\n\nFAILED (failures=1)\n", "FAILURE"),
    ("Ran 3 tests in 0.1s\n\nOK\n", "SUCCESS"),
])
def test_verdict_in_stdout_survives_noisy_stderr(tmp_path, out, expected):
    # appending stderr must keep stdout: the verdict lives there, stderr is only a warning
    st = _run_hook(tmp_path, "python manage.py test", out, stderr="RuntimeWarning: x\n")
    assert st and st["status"] == expected and st["kind"] == "unittest"


def test_stderr_is_joined_on_its_own_line(tmp_path):
    # stdout ends without a newline: the warning must not be glued onto the OK line
    st = _run_hook(tmp_path, "python manage.py test", "Ran 3 tests in 0.1s\n\nOK",
                   stderr="RuntimeWarning: x\n")
    assert st and st["status"] == "SUCCESS" and st["kind"] == "unittest"


def test_non_string_stderr_does_not_crash_unittest(tmp_path):
    st = _run_hook(tmp_path, "python manage.py test",
                   "Ran 3 tests in 0.1s\n\nFAILED (failures=1)\n", stderr=["x"])
    assert st and st["status"] == "FAILURE" and st["kind"] == "unittest"


def test_non_string_stderr_does_not_crash_other_commands(tmp_path):
    st = _run_hook(tmp_path, "pytest", "something broke\n", stderr=["x"], extra={"exit_code": 1})
    assert st and st["status"] == "FAILURE" and st["kind"] == "pytest"


@pytest.mark.parametrize("command, out", [
    ("python manage.py test", "Ran 0 tests in 0.000s\n\nOK"),
    ("python manage.py test app.tests.NaoExiste", "Ran 0 tests in 0.000s\n\nNO TESTS RAN"),
    ("uv run python manage.py test app", "Found 0 test(s).\nRan 0 tests in 0.000s\n\nOK"),
])
def test_ran_zero_tests_records_empty(tmp_path, command, out):
    st = _run_hook(tmp_path, command, out)
    assert st and st["status"] == "EMPTY" and st["tests_run"] == 0


def test_ran_zero_tests_in_stderr_records_empty(tmp_path):
    st = _run_hook(tmp_path, "python manage.py test", "", stderr="Ran 0 tests in 0.000s\n\nNO TESTS RAN")
    assert st and st["status"] == "EMPTY"


def test_ran_zero_tests_does_not_hide_a_red_block(tmp_path):
    out = "Ran 0 tests in 0.0s\n\nOK\nRan 2 tests in 0.1s\n\nFAILED (failures=1)"
    st = _run_hook(tmp_path, "python manage.py test", out)
    assert st and st["status"] == "FAILURE"


def test_ran_zero_tests_does_not_hide_a_green_block(tmp_path):
    out = "Ran 0 tests in 0.0s\n\nOK\nRan 2 tests in 0.1s\n\nOK"
    st = _run_hook(tmp_path, "python manage.py test", out)
    assert st and st["status"] == "SUCCESS"


def test_ran_zero_in_a_log_line_is_not_empty(tmp_path):
    assert _run_hook(tmp_path, "python manage.py test", "log: Ran 0 tests in 0.1s earlier") is None


@pytest.mark.parametrize("command, out", [
    ("python manage.py test", "Ran 0 tests in 0.000s\n\nOK"),
    ("python manage.py test app.tests.NaoExiste", "Ran 0 tests in 0.000s\n\nOK"),
    ("python manage.py test app.tests.NaoExiste", "Ran 0 tests in 0.000s\n\nNO TESTS RAN"),
])
def test_ran_zero_tests_with_explicit_exit_0_records_empty(tmp_path, command, out):
    st = _run_hook(tmp_path, command, out, extra={"exit_code": 0})
    assert st and st["status"] == "EMPTY" and st["tests_run"] == 0


def test_ran_zero_tests_with_exit_0_does_not_hide_a_green_block(tmp_path):
    out = "Ran 0 tests in 0.0s\n\nOK\nRan 2 tests in 0.1s\n\nOK"
    st = _run_hook(tmp_path, "python manage.py test", out, extra={"exit_code": 0})
    assert st and st["status"] == "SUCCESS"


def test_ran_zero_tests_with_nonzero_exit_stays_failure(tmp_path):
    st = _run_hook(tmp_path, "python manage.py test", "Ran 0 tests in 0.000s\n\nNO TESTS RAN",
                   extra={"exit_code": 1})
    assert st and st["status"] == "FAILURE"


def test_classify_exit_0_ran_zero_then_refine_is_empty():
    cmd, out = "python manage.py test", "Ran 0 tests in 0.000s\n\nOK"
    status, kind, _ = cbr.classify(cmd, out, 0)
    assert cbr.refine_empty(cmd, kind, status, out)[0] == "EMPTY"


@pytest.mark.parametrize("out", [
    "    Ran 0 tests in 0.000s\n\nOK",
    "Found 0 test(s).\n  Ran 0 tests in 0.000s\n\nOK",
    "\tRan 0 tests in 0.000s\n\nOK",
    "Ran 0 test in 0.000s\n\nOK",
])
def test_indented_or_singular_ran_zero_with_exit_0_records_empty(tmp_path, out):
    st = _run_hook(tmp_path, "python manage.py test", out, extra={"exit_code": 0})
    assert st and st["status"] == "EMPTY" and st["tests_run"] == 0


def test_ran_nonzero_without_verdict_and_exit_0_is_not_empty(tmp_path):
    st = _run_hook(tmp_path, "python manage.py test", "Ran 3 tests in 0.1s", extra={"exit_code": 0})
    assert st and st["status"] == "SUCCESS" and "tests_run" not in st


def test_ran_zero_line_from_a_non_unittest_command_stays_success(tmp_path):
    st = _run_hook(tmp_path, "pytest", "Ran 0 tests in 0.000s\n1 passed in 0.1s", extra={"exit_code": 0})
    assert st and st["status"] == "SUCCESS" and st["kind"] == "pytest"


def test_empty_reason_carries_the_test_label_hint(tmp_path):
    st = _run_hook(tmp_path, "python manage.py test app.NaoExiste", "Ran 0 tests in 0.000s\n\nNO TESTS RAN")
    assert st and st["status"] == "EMPTY"
    assert st["reason"] and cbr.UNITTEST_EMPTY_FIX_HINT in st["reason"]
