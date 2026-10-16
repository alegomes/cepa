"""capture-build-result classifica pelo comando SEM texto citado e exige um Maven de
verdade (fb-20261008-1, 2026-10-08): `grep -E 'no-build|verify' x` virava FAILURE
maven e barrava o commit; `./mvnw -q verify > log` nunca virava SUCCESS."""
import json
import os
import subprocess
import sys
import importlib.util
from pathlib import Path

# Pedido explícito de isolamento: tests/test_telemetria_isolada.py exige que todo
# teste que cite um hook emissor isole a telemetria por conta própria.
from _telemetria_isolada import isola

isola()

HOOK = Path(__file__).resolve().parents[1] / "common" / "hooks" / "capture-build-result.py"
spec = importlib.util.spec_from_file_location("capture_build_result", HOOK)
cbr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cbr)

ERR1 = "Error: Exit code 1\n"


def test_grep_with_verify_in_quoted_pattern_is_not_a_build():
    status, kind, _ = cbr.classify("grep -E 'no-build|verify' cepa-until", ERR1, 1)
    assert (status, kind) == (None, None)


def test_echo_of_mvnw_is_not_a_build():
    status, kind, _ = cbr.classify('echo "./mvnw verify"', ERR1, 1)
    assert (status, kind) == (None, None)


def test_heredoc_body_mentioning_swift_build_is_not_a_build():
    status, kind, _ = cbr.classify('python3 - <<\'PY\'\nprint("swift build")\nPY', "swift build\n", None)
    assert (status, kind) == (None, None)


def test_real_maven_with_success_marker_still_works():
    status, kind, _ = cbr.classify("./mvnw -pl domain -am verify", "[INFO] BUILD SUCCESS", None)
    assert (status, kind) == ("SUCCESS", "maven")


def test_error_string_exit_code_is_parsed():
    assert cbr.extract_exit_code("Error: Exit code 3\nboom") == 3
    assert cbr.extract_exit_code("plain output") is None
    assert cbr.extract_exit_code({"stdout": "", "interrupted": False}) is None


def test_quiet_maven_without_output_and_without_exit_code_is_success():
    status, kind, _ = cbr.classify("timeout 580 ./mvnw -q clean verify", "", None, interrupted=False)
    assert (status, kind) == ("SUCCESS", "maven")


def test_quiet_maven_interrupted_is_not_classified():
    status, _, _ = cbr.classify("timeout 580 ./mvnw -q clean verify", "", None, interrupted=True)
    assert status is None


def test_quiet_maven_failure_is_failure():
    status, kind, _ = cbr.classify("./mvnw -q clean verify",
                                   "Error: Exit code 1\n[ERROR] ... BUILD FAILURE", 1)
    assert (status, kind) == ("FAILURE", "maven")


def test_non_quiet_maven_with_empty_output_stays_unclassified():
    status, kind, _ = cbr.classify("./mvnw clean verify", "", None)
    assert (status, kind) == (None, "maven")


def test_profile_or_property_containing_q_is_not_quiet():
    for cmd in ("./mvnw -Pquality verify", "./mvnw -Pqa verify", "./mvnw -Dquick verify"):
        status, kind, _ = cbr.classify(cmd, "", None)
        assert (status, kind) == (None, "maven"), cmd


def _run_hook(tmp_path, command, log_text, response=None):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pom.xml").write_text("<project/>")
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    if log_text is not None:
        (proj / "build.log").write_text(log_text)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    payload = {"cwd": str(proj), "session_id": "s-classify", "tool_name": "Bash",
               "tool_input": {"command": command},
               "tool_response": response if response is not None else
               {"stdout": "", "stderr": "", "interrupted": False}}
    subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True,
                   capture_output=True, cwd=proj, env={**os.environ, "TMPDIR": str(tmp)})
    state = proj / ".claude" / "last-build.json"
    return json.loads(state.read_text()) if state.exists() else None


def test_redirected_log_with_build_success_is_success(tmp_path):
    st = _run_hook(tmp_path, "./mvnw clean verify > build.log", "[INFO] BUILD SUCCESS\n")
    assert st and (st["status"], st["kind"]) == ("SUCCESS", "maven")


def test_redirected_log_with_build_failure_is_failure(tmp_path):
    st = _run_hook(tmp_path, "./mvnw clean verify > build.log", "[ERROR] BUILD FAILURE\n")
    assert st and (st["status"], st["kind"]) == ("FAILURE", "maven")


def test_quiet_redirected_empty_log_is_success(tmp_path):
    st = _run_hook(tmp_path, "./mvnw -q clean verify > build.log", "")
    assert st and (st["status"], st["kind"]) == ("SUCCESS", "maven")


def test_error_string_response_for_quiet_maven_is_failure(tmp_path):
    st = _run_hook(tmp_path, "./mvnw -q clean verify", None,
                   response="Error: Exit code 1\n[ERROR] ...\nBUILD FAILURE")
    assert st and (st["status"], st["kind"]) == ("FAILURE", "maven")
