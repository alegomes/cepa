"""pytest precisa de marcadores de texto: o CC omite o exit code no sucesso, e sem
marcador um pytest verde nunca limpava o STALE do gate-advance (pastinha-pipeline, 2026-10-10)."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "capture_build_result", Path(__file__).resolve().parents[1] / "common" / "hooks" / "capture-build-result.py")
cbr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cbr)


def test_pytest_green_without_exit_code_is_success():
    status, kind, _ = cbr.classify("pytest", "collected 10 items\n\n== 10 passed in 0.01s ==\n", None)
    assert (status, kind) == ("SUCCESS", "pytest")


def test_pytest_module_form_is_recognized():
    status, _, _ = cbr.classify("python3 -m pytest -q", "10 passed in 0.01s", None)
    assert status == "SUCCESS"


def test_pytest_mixed_result_is_failure():
    status, _, _ = cbr.classify("pytest", "== 1 failed, 9 passed in 0.02s ==", None)
    assert status == "FAILURE"


def test_pytest_collection_errors_is_failure():
    status, _, _ = cbr.classify("pytest -q", "!!! Interrupted: 3 errors during collection !!!\n3 errors in 0.07s", None)
    assert status == "FAILURE"
