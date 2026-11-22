"""`flutter test` and a repo check script (`tool/check.sh`) must reach .claude/last-build.json
(fb-20261115-1, herdr-mobile, 2026-11-15). Without a pattern for either, no green run ever
cleared the STALE baseline and gate-advance stayed locked; the only way out was
`.claude/no-build`, which switches the whole gate off.

- `flutter test` (also `fvm flutter test`): CC omits the exit code on success, so the verdict is
  read from flutter's summary line: `All tests passed!` = SUCCESS, `Some tests failed.` = FAILURE.
- A check script is not a toolchain the hook can know by name, so the repo declares it in
  `.claude/check-scripts.json`: {"scripts": [{"command": "tool/check.sh", "ok_line": "OK"}]}.
  SUCCESS = the last non-empty output line is exactly `ok_line` (default `OK`); a nonzero exit
  code is FAILURE and wins over the last line; anything else stays unclassified (stale beats
  a wrong green)."""
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

# Real shape of `flutter test` output when stdout is not a terminal (CC's Bash tool).
FLUTTER_GREEN = (
    "00:00 +0: loading /proj/test/widget_test.dart\n"
    "00:01 +1: Counter increments smoke test\n"
    "00:02 +5: All tests passed!\n"
)
FLUTTER_RED = (
    "00:01 +1: Counter increments smoke test\n"
    "00:02 +4 -1: load flaky [E]\n"
    "  Expected: <1>\n    Actual: <0>\n"
    "00:02 +4 -1: Some tests failed.\n"
)
FLUTTER_COMPILE_ERROR = (
    "00:01 +0: loading /proj/test/widget_test.dart\n"
    "test/widget_test.dart:3:8: Error: Not found: 'package:app/missing.dart'\n"
    "00:01 +0 -1: Some tests failed.\n"
)

CHECK_GREEN = "analyze: No issues found!\nformat: 0 changed\ntests: All tests passed!\nOK\n"
CHECK_RED_TEXT = "analyze: 2 issues found\nFAIL\n"


def _project(tmp_path, manifest=None):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pubspec.yaml").write_text("name: app\n")
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    if manifest is not None:
        (proj / ".claude").mkdir()
        (proj / ".claude" / "check-scripts.json").write_text(
            manifest if isinstance(manifest, str) else json.dumps(manifest))
    return proj


def _run_hook(proj, tmp_path, command, output, extra=None):
    """A failed Bash call reaches the hook as a plain string "Error: Exit code N\\n<output>"
    (CC drops the dict form on non-zero exits); a green one as the stdout dict."""
    tmp = tmp_path / "tmp"
    tmp.mkdir(exist_ok=True)
    response = (output if output.startswith("Error: Exit code ") else
                {"stdout": output, "stderr": "", "interrupted": False, **(extra or {})})
    payload = {"cwd": str(proj), "session_id": "s-flutter", "tool_name": "Bash",
               "tool_input": {"command": command}, "tool_response": response}
    subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True,
                   capture_output=True, cwd=proj, env={**os.environ, "TMPDIR": str(tmp)})
    state = proj / ".claude" / "last-build.json"
    return json.loads(state.read_text()) if state.exists() else None


DECLARED = {"scripts": [{"command": "tool/check.sh", "ok_line": "OK"}]}


# ─── flutter test ─────────────────────────────────────────────────────

@pytest.mark.parametrize("command", [
    "flutter test",
    "fvm flutter test",
    "flutter test test/widget_test.dart",
    "cd app && flutter test --reporter expanded",
])
def test_flutter_green_without_exit_code_is_success(command):
    assert cbr.classify(command, FLUTTER_GREEN, None)[:2] == ("SUCCESS", "flutter")


def test_flutter_red_is_failure():
    assert cbr.classify("flutter test", FLUTTER_RED, None)[:2] == ("FAILURE", "flutter")


def test_flutter_compile_error_is_failure():
    assert cbr.classify("flutter test", FLUTTER_COMPILE_ERROR, None)[:2] == ("FAILURE", "flutter")


def test_flutter_red_wins_over_an_earlier_green_in_the_same_output():
    # two runs chained in one command: the red one must not be hidden by the green one
    out = FLUTTER_GREEN + FLUTTER_RED
    assert cbr.classify("flutter test a_test.dart; flutter test b_test.dart", out, None)[0] == "FAILURE"


@pytest.mark.parametrize("command", [
    'echo " flutter test"',
    "flutter analyze",
    "flutter build apk",
    "grep -rn 'flutter test' docs",
])
def test_not_flutter_test_is_not_this_kind(command):
    assert cbr.classify(command, FLUTTER_GREEN, None)[1] != "flutter"


def test_flutter_green_reaches_last_build_json(tmp_path):
    proj = _project(tmp_path)
    state = _run_hook(proj, tmp_path, "flutter test", FLUTTER_GREEN)
    assert state is not None and state["status"] == "SUCCESS" and state["kind"] == "flutter"


def test_flutter_red_reaches_last_build_json(tmp_path):
    proj = _project(tmp_path)
    state = _run_hook(proj, tmp_path, "flutter test", FLUTTER_RED)
    assert state is not None and state["status"] == "FAILURE"


def test_flutter_green_clears_a_previous_red(tmp_path):
    proj = _project(tmp_path)
    assert _run_hook(proj, tmp_path, "flutter test", FLUTTER_RED)["status"] == "FAILURE"
    assert _run_hook(proj, tmp_path, "flutter test", FLUTTER_GREEN)["status"] == "SUCCESS"


# ─── declared check script ────────────────────────────────────────────

@pytest.mark.parametrize("command", [
    "tool/check.sh",
    "./tool/check.sh",
    "bash tool/check.sh",
    "sh ./tool/check.sh",
    "cd app && tool/check.sh",
    "tool/check.sh --fast",
])
def test_declared_check_script_ending_in_ok_is_success(tmp_path, command):
    proj = _project(tmp_path, DECLARED)
    assert cbr.classify(command, CHECK_GREEN, None, root=proj)[:2] == ("SUCCESS", "check-script")


def test_declared_check_script_with_nonzero_exit_is_failure(tmp_path):
    proj = _project(tmp_path, DECLARED)
    assert cbr.classify("tool/check.sh", "Error: Exit code 1\n" + CHECK_RED_TEXT, 1,
                        root=proj)[:2] == ("FAILURE", "check-script")


def test_nonzero_exit_wins_over_a_last_line_ok(tmp_path):
    proj = _project(tmp_path, DECLARED)
    assert cbr.classify("tool/check.sh", CHECK_GREEN, 2, root=proj)[0] == "FAILURE"


def test_declared_check_script_without_ok_and_without_exit_code_is_unclassified(tmp_path):
    # stale beats a wrong green: no OK last line, no exit code to read
    proj = _project(tmp_path, DECLARED)
    assert cbr.classify("tool/check.sh", "analyze: fine\nOK, now running tests\n", None,
                        root=proj)[:2] == (None, "check-script")


def test_ok_only_in_the_middle_is_not_success(tmp_path):
    proj = _project(tmp_path, DECLARED)
    assert cbr.classify("tool/check.sh", "OK\nformat: 3 files changed\n", None,
                        root=proj)[0] is None


def test_custom_ok_line_is_respected(tmp_path):
    proj = _project(tmp_path, {"scripts": [{"command": "scripts/verify", "ok_line": "ALL GREEN"}]})
    assert cbr.classify("scripts/verify", "lint ok\nALL GREEN\n", None, root=proj)[0] == "SUCCESS"
    assert cbr.classify("scripts/verify", "lint ok\nOK\n", None, root=proj)[0] is None


def test_ok_line_defaults_to_ok(tmp_path):
    proj = _project(tmp_path, {"scripts": [{"command": "tool/check.sh"}]})
    assert cbr.classify("tool/check.sh", CHECK_GREEN, None, root=proj)[0] == "SUCCESS"


def test_undeclared_check_script_is_not_a_build(tmp_path):
    proj = _project(tmp_path)
    assert cbr.classify("tool/check.sh", CHECK_GREEN, None, root=proj)[:2] == (None, None)


@pytest.mark.parametrize("command", [
    "cat tool/check.sh",
    "vim tool/check.sh",
    'echo "tool/check.sh"',
    "tool/check.shx",
    "other/tool/check.sh",
])
def test_mentioning_the_script_is_not_running_it(tmp_path, command):
    proj = _project(tmp_path, DECLARED)
    assert cbr.classify(command, CHECK_GREEN, None, root=proj)[1] != "check-script"


@pytest.mark.parametrize("manifest", ["{not json", json.dumps({"scripts": "tool/check.sh"}),
                                      json.dumps([1, 2]), json.dumps({"scripts": [{"ok_line": "OK"}]})])
def test_broken_manifest_is_ignored_without_crashing(tmp_path, manifest):
    proj = _project(tmp_path, manifest)
    assert cbr.classify("tool/check.sh", CHECK_GREEN, None, root=proj)[:2] == (None, None)


def test_declared_check_script_green_reaches_last_build_json(tmp_path):
    proj = _project(tmp_path, DECLARED)
    state = _run_hook(proj, tmp_path, "tool/check.sh", CHECK_GREEN)
    assert state is not None and state["status"] == "SUCCESS" and state["kind"] == "check-script"


def test_declared_check_script_red_reaches_last_build_json(tmp_path):
    proj = _project(tmp_path, DECLARED)
    state = _run_hook(proj, tmp_path, "tool/check.sh", "Error: Exit code 1\n" + CHECK_RED_TEXT)
    assert state is not None and state["status"] == "FAILURE"


def test_check_script_in_a_subdirectory_records_in_the_session_tree(tmp_path):
    # `cd app && tool/check.sh` with the manifest at the session root: recorded in the session tree
    proj = _project(tmp_path, DECLARED)
    (proj / "app").mkdir()
    state = _run_hook(proj, tmp_path, "cd app && tool/check.sh", CHECK_GREEN)
    assert state is not None and state["status"] == "SUCCESS"


def test_background_check_script_is_harvested_with_the_manifest(tmp_path):
    # a declared check script that went to the background: the harvest (on the next Bash)
    # re-classifies it with the session root's manifest, so its green is recorded when it ends
    proj = _project(tmp_path, DECLARED)
    tmp = tmp_path / "tmp"
    tasks = tmp / "claude-501" / "proj-slug" / "s-bg" / "tasks"
    tasks.mkdir(parents=True)
    output = tasks / "bg1.output"
    output.write_text("")
    env = {**os.environ, "TMPDIR": str(tmp)}

    def bash(command, response):
        payload = {"cwd": str(proj), "session_id": "s-bg", "tool_name": "Bash",
                   "tool_input": {"command": command}, "tool_response": response}
        subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True,
                       capture_output=True, cwd=proj, env=env)

    bash("tool/check.sh", {"stdout": "", "stderr": "", "interrupted": False,
                           "backgroundTaskId": "bg1"})
    assert list(tasks.glob("bg1*")) != [output], "the background check script was not registered"
    output.write_text(CHECK_GREEN + "\n[exited with code 0]\n")  # the trailer CC appends
    bash("ls", {"stdout": "pubspec.yaml", "stderr": "", "interrupted": False})
    state = json.loads((proj / ".claude" / "last-build.json").read_text())
    assert state["status"] == "SUCCESS" and state["kind"] == "check-script"


def test_check_script_run_outside_the_session_tree_records_there(tmp_path):
    # `cd ../wt && tool/check.sh` (a proof worktree): the result describes wt, so it lands in
    # wt/.claude/last-build.json and the session baseline stays untouched (same rule as Maven)
    proj = _project(tmp_path, DECLARED)
    wt = tmp_path / "wt"
    wt.mkdir()
    assert _run_hook(proj, tmp_path, "cd ../wt && tool/check.sh", CHECK_GREEN) is None
    state = json.loads((wt / ".claude" / "last-build.json").read_text())
    assert state["status"] == "SUCCESS" and state["kind"] == "check-script"


def test_effective_build_dir_follows_cd_to_a_declared_check_script(tmp_path):
    proj = _project(tmp_path, DECLARED)
    wt = tmp_path / "wt"
    wt.mkdir()
    assert cbr.effective_build_dir("cd ../wt && tool/check.sh", proj.resolve()) == wt.resolve()
    # quoted mention is not running it: no build segment, falls back to the session root
    assert cbr.effective_build_dir('cd ../wt && echo "tool/check.sh"', proj.resolve()) == proj.resolve()
    assert cbr.effective_build_dir('cd ../wt && echo "x; tool/check.sh x"', proj.resolve()) == proj.resolve()


def test_check_script_declared_with_dot_slash_matches_both_spellings(tmp_path):
    proj = _project(tmp_path, {"scripts": [{"command": "./tool/check.sh"}]})
    for command in ("tool/check.sh", "./tool/check.sh"):
        assert cbr.classify(command, CHECK_GREEN, None, root=proj)[:2] == ("SUCCESS", "check-script")


def test_negative_exit_code_is_failure(tmp_path):
    proj = _project(tmp_path, DECLARED)
    assert cbr.classify("tool/check.sh", CHECK_GREEN, -9, root=proj)[0] == "FAILURE"
