#!/usr/bin/env python3
"""Tests of the iteration ceiling (P0-2 of the 2026-08-17 review).

No dependencies — run with `python3 tests/test_loop_budget.py`.
Exits non-zero on failure.

The rule this file protects has two halves, and both are costly if
broken:

  - **Repeating blocks.** The same failure for the 3rd time stops the delegation. Without it,
    a pathological card consumes the whole session cycling on the same red.
  - **Iterating does NOT block.** A different failure, progress, a green build — all
    of that goes on. A ceiling that bites legitimate iteration would be switched off on the
    first day, and then it protects nothing. Half of the cases below exist only
    to prove that it does not bite.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

# This test executes a hook that emits telemetry; without this the events would fall
# in ~/.claude/cepa-telemetry/ and enter the /common:metrics report
# as if they were real use. See tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()


REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "common" / "hooks" / "loop-budget.py"

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL {label}{' — ' + detail if detail else ''}")


def run(event, cwd, result_text="", agent="build-hex:domain-dev", env=None):
    payload = {
        "tool_name": "Task",
        "hook_event_name": event,
        "cwd": str(cwd),
        "agent_type": agent,
        "tool_input": {"subagent_type": agent, "prompt": "faça a coisa"},
        "tool_response": {"content": result_text},
    }
    return subprocess.run(
        [sys.executable, str(HOOK)], input=json.dumps(payload),
        capture_output=True, text=True, env=env,
    )


def fresh(tmp, name):
    d = Path(tmp) / name
    (d / ".claude").mkdir(parents=True, exist_ok=True)
    return d


RED_A = """
[ERROR] Tests run: 12, Failures: 1, Errors: 0, Skipped: 0
[ERROR] TenantResourceTest.shouldRejectUnknownTenant:88 expected 422 but was 500
BUILD FAILURE
"""
RED_A_OTHER_RUN = """
[ERROR] Tests run: 12, Failures: 1, Errors: 0, Skipped: 0
[ERROR] TenantResourceTest.shouldRejectUnknownTenant:88 expected 422 but was 500
BUILD FAILURE
Total time: 47.221 s
Finished at: 2026-08-17T23:55:04-03:00
"""
RED_B = """
[ERROR] Tests run: 9, Failures: 1, Errors: 0
[ERROR] SignatureAdapterTest.shouldRetryOnTimeout:41 expected 3 calls but was 1
BUILD FAILURE
"""
GREEN = "Tests run: 12, Failures: 0, Errors: 0\nBUILD SUCCESS"


# ── repeating blocks ─────────────────────────────────────────────────────────

def test_third_identical_failure_blocks(tmp):
    d = fresh(tmp, "repete")
    for i in (1, 2):
        run("PostToolUse", d, RED_A)
        r = run("PreToolUse", d)
        check(f"{i}ª repetição ainda passa (iteração legítima)", r.returncode == 0,
              f"exit {r.returncode}")
    run("PostToolUse", d, RED_A)
    r = run("PreToolUse", d)
    check("3ª aparição da mesma falha BLOQUEIA", r.returncode == 2, f"exit {r.returncode}")
    check("o bloqueio NOMEIA a falha que se repete",
          "TenantResourceTest" in r.stderr)
    check("o bloqueio diz o que fazer (diagnosticar / BLOCKED)",
          "DIAGNOSTIQUE" in r.stderr and "BLOCKED" in r.stderr)


def test_volatile_noise_does_not_disguise_the_same_failure(tmp):
    """Timestamp and duration change on every run — they cannot become a 'new failure'.

    Without the normalization, each lap would have its own signature and the ceiling would never
    fire: the detector would stay green forever while the loop runs.
    """
    d = fresh(tmp, "ruido")
    run("PostToolUse", d, RED_A)
    run("PostToolUse", d, RED_A_OTHER_RUN)
    run("PostToolUse", d, RED_A)
    r = run("PreToolUse", d)
    check("mesma falha com timestamp/duração diferentes conta como a mesma",
          r.returncode == 2, f"exit {r.returncode}")


def test_warning_before_the_block(tmp):
    d = fresh(tmp, "aviso")
    run("PostToolUse", d, RED_A)
    r = run("PostToolUse", d, RED_A)
    check("a 2ª aparição avisa que a próxima bloqueia",
          "BLOQUEADA" in r.stderr or "⚠" in r.stderr, r.stderr[:120])


# ── iterating does NOT block ─────────────────────────────────────────────────

def test_different_failures_do_not_block(tmp):
    d = fresh(tmp, "progresso")
    for text in (RED_A, RED_B, RED_A, RED_B):
        run("PostToolUse", d, text)
    r = run("PreToolUse", d)
    check("alternar entre falhas diferentes não bloqueia (2x cada)",
          r.returncode == 0, f"exit {r.returncode}")


def test_green_resets_the_counter(tmp):
    d = fresh(tmp, "verde")
    run("PostToolUse", d, RED_A)
    run("PostToolUse", d, RED_A)
    (d / ".claude" / "last-build.json").write_text(json.dumps({"status": "SUCCESS"}))
    run("PostToolUse", d, GREEN)
    (d / ".claude" / "last-build.json").write_text(json.dumps({"status": "STALE"}))
    run("PostToolUse", d, RED_A)
    r = run("PreToolUse", d)
    check("build verde zera o contador (a falha anterior é passado)",
          r.returncode == 0, f"exit {r.returncode}")


def test_success_does_not_count(tmp):
    d = fresh(tmp, "sucesso")
    for _ in range(5):
        run("PostToolUse", d, "APPROVED. Tests run: 40, Failures: 0, Errors: 0")
    r = run("PreToolUse", d)
    check("resultado sem falha nunca conta", r.returncode == 0, f"exit {r.returncode}")
    state = json.loads((d / ".claude" / "loop-state.json").read_text())
    check("nenhuma assinatura registrada num run limpo", state["signatures"] == {})


def test_signature_ages(tmp):
    """A resolved red cannot keep counting half an hour later."""
    d = fresh(tmp, "idade")
    run("PostToolUse", d, RED_A)
    run("PostToolUse", d, RED_A)
    for _ in range(7):  # AGE_OUT = 6 delegations without the signature appearing
        run("PostToolUse", d, "tudo certo por aqui")
    run("PostToolUse", d, RED_A)
    r = run("PreToolUse", d)
    check("assinatura ausente por 6+ delegações é esquecida",
          r.returncode == 0, f"exit {r.returncode}")


# ── never gets in the way ────────────────────────────────────────────────────

def test_other_tools_pass(tmp):
    d = fresh(tmp, "outras")
    payload = {"tool_name": "Bash", "hook_event_name": "PreToolUse", "cwd": str(d),
               "tool_input": {"command": "ls"}}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True)
    check("hook só age em Task", r.returncode == 0)


def test_unreadable_payload_releases(tmp):
    r = subprocess.run([sys.executable, str(HOOK)], input="{isto não é json",
                       capture_output=True, text=True)
    check("payload ilegível libera (fail-open)", r.returncode == 0)


def test_corrupted_state_releases(tmp):
    d = fresh(tmp, "corrompido")
    (d / ".claude" / "loop-state.json").write_text("{lixo")
    r = run("PreToolUse", d)
    check("estado corrompido libera em vez de travar a sessão", r.returncode == 0)


def test_explicitly_disableable(tmp):
    import os
    d = fresh(tmp, "off")
    for _ in range(4):
        run("PostToolUse", d, RED_A)
    env = dict(os.environ, CEPA_LOOP_BUDGET="off")
    r = run("PreToolUse", d, env=env)
    check("CEPA_LOOP_BUDGET=off desliga (decisão explícita, não acidente)",
          r.returncode == 0, f"exit {r.returncode}")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        test_third_identical_failure_blocks(tmp)
        test_volatile_noise_does_not_disguise_the_same_failure(tmp)
        test_warning_before_the_block(tmp)
        test_different_failures_do_not_block(tmp)
        test_green_resets_the_counter(tmp)
        test_success_does_not_count(tmp)
        test_signature_ages(tmp)
        test_other_tools_pass(tmp)
        test_unreadable_payload_releases(tmp)
        test_corrupted_state_releases(tmp)
        test_explicitly_disableable(tmp)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
