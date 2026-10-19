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


# Os comandos abaixo CASAM o regex no comando cru (há espaço antes do token, dentro
# das aspas) e NÃO casam na visão sem texto citado: sem a visão, viram build.
def test_grep_with_mvnw_verify_in_quoted_pattern_is_not_a_build():
    status, kind, _ = cbr.classify("grep -E 'no-build| mvnw verify' common/bin/cepa-until", ERR1, 1)
    assert (status, kind) == (None, None)


def test_echo_of_mvnw_is_not_a_build():
    status, kind, _ = cbr.classify('echo " ./mvnw verify"', ERR1, 1)
    assert (status, kind) == (None, None)


def test_heredoc_body_mentioning_swift_build_is_not_a_build():
    status, kind, _ = cbr.classify('python3 - <<\'PY\'\nprint(" swift build")\nPY', " swift build\n", None)
    assert (status, kind) == (None, None)


def test_echo_of_pytest_is_not_a_build():
    assert cbr.classify('echo " pytest x"', " 1 passed", None)[:2] == (None, None)


def test_echo_of_npm_test_is_not_a_build():
    assert cbr.classify('echo " npm test"', "Done in 1s", None)[:2] == (None, None)


def test_maven_words_without_a_real_invoker_are_not_a_build():
    # casa o regex Maven na visão (`mvnw verify` solto), mas `ls` não é Maven
    assert cbr.classify("ls ./mvnw verify", "BUILD SUCCESS", None)[:2] == (None, None)


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


def test_grep_with_quoted_mvnw_verify_leaves_no_state(tmp_path):
    st = _run_hook(tmp_path, "grep -E 'no-build| mvnw verify' cepa-until", None,
                   response="Error: Exit code 1\n")
    assert st is None


def test_echo_of_quoted_mvnw_verify_leaves_no_state(tmp_path):
    assert _run_hook(tmp_path, 'echo " ./mvnw verify"', None) is None


# ── 2026-10-16: marcadores Maven ancorados em início de linha + build_dir real ──

LAST_BUILD_CMD = (
    "./mvnw -o -pl infrastructure,bootstrap -am test -Dtest='LerLoteTest' "
    "-Dsurefire.failIfNoSpecifiedTests=false 2>&1 | grep -E \"Tests run:.*Fail|BUILD|ERROR\" "
    "| tail -15; cat .claude/last-build.json"
)
# O JSON do registro anterior vem em UMA linha, com \n literal dentro da string.
CAT_JSON_OUT = (
    "[INFO] Tests run: 74, Failures: 0, Errors: 0, Skipped: 0\n[INFO] BUILD SUCCESS\n"
    "{\n  \"status\": \"FAILURE\",\n"
    "  \"tail\": \"[ERROR] Tests run: 61, Failures: 1 <<< FAILURE!\\n[INFO] BUILD FAILURE\"\n}\n"
)


def test_cat_of_last_build_json_does_not_flip_green_to_failure():
    status, kind, _ = cbr.classify(LAST_BUILD_CMD, CAT_JSON_OUT, None)
    assert (status, kind) == ("SUCCESS", "maven")


def test_cat_of_last_build_json_end_to_end_stays_success(tmp_path):
    st = _run_hook(tmp_path, LAST_BUILD_CMD, None,
                   response={"stdout": CAT_JSON_OUT, "stderr": "", "interrupted": False})
    assert st and st["status"] == "SUCCESS"


def test_cat_of_a_log_with_build_failure_is_not_a_build():
    status, kind, _ = cbr.classify("cat build.log", "[INFO] BUILD FAILURE\n", None)
    assert (status, kind) == (None, None)


def test_cat_of_a_log_with_build_failure_leaves_no_state(tmp_path):
    # the hook, not classify(): a `cat` whose output is a real Maven failure line
    # must not write .claude/last-build.json (fb-20261016-3, 2026-10-16)
    st = _run_hook(tmp_path, "cat build.log", None,
                   response={"stdout": "[INFO] BUILD FAILURE\n", "stderr": "", "interrupted": False})
    assert st is None


def test_ansi_colored_build_success_is_success():
    out = "[\x1b[1;34mINFO\x1b[m] \x1b[1;32mBUILD SUCCESS\x1b[m\n"
    assert cbr.classify("./mvnw verify", out, None)[:2] == ("SUCCESS", "maven")


def test_grep_n_prefixed_build_success_is_success():
    assert cbr.classify("./mvnw verify 2>&1 | grep -n BUILD", "12:[INFO] BUILD SUCCESS\n",
                        None)[:2] == ("SUCCESS", "maven")


def test_real_build_failure_line_after_success_line_still_wins():
    out = "[INFO] BUILD SUCCESS\n[INFO] BUILD FAILURE\n"
    assert cbr.classify("./mvnw verify", out, None)[:2] == ("FAILURE", "maven")


def test_effective_build_dir_follows_cd_after_git_dash_c(tmp_path):
    wt = (tmp_path / "wt").resolve()
    wt.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    cmd = (f"git -C {wt} checkout -- f; cd {wt} && sed -i.bak 's/a/b/' f "
           f"&& ./mvnw -o -pl x test -Dtest=T")
    assert cbr.effective_build_dir(cmd, repo) == wt


def test_effective_build_dir_without_cd_is_cwd_and_in_root_cd_is_subdir(tmp_path):
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    assert cbr.effective_build_dir("./mvnw verify", repo) == repo
    assert cbr.effective_build_dir("cd backend && ./mvnw verify", repo) == (repo / "backend").resolve()


def test_perturbation_build_after_git_dash_c_does_not_touch_main_state(tmp_path):
    wt = (tmp_path / "wt").resolve()
    wt.mkdir()
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    cmd = (f"git -C {wt} checkout -- f; cd {wt} && sed -i.bak 's/a/b/' f "
           f"&& ./mvnw -o -pl x test -Dtest=T")
    payload = {"cwd": str(proj), "session_id": "s-pert", "tool_name": "Bash",
               "tool_input": {"command": cmd},
               "tool_response": {"stdout": "[INFO] BUILD FAILURE\n", "stderr": "",
                                 "interrupted": False}}
    subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), text=True,
                   capture_output=True, cwd=proj, env={**os.environ, "TMPDIR": str(tmp)})
    assert not (proj / ".claude" / "last-build.json").exists()
    st = json.loads((wt / ".claude" / "last-build.json").read_text())
    assert st["status"] == "FAILURE"
