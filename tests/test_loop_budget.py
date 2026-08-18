#!/usr/bin/env python3
"""Testes do teto de iteração (P0-2 da revisão 2026-08-17).

Sem dependências — rode com `python3 tests/test_loop_budget.py`.
Sai não-zero em falha.

A regra que este arquivo protege tem duas metades, e as duas custam caro se
quebrarem:

  - **Repetir bloqueia.** A mesma falha pela 3ª vez para a delegação. Sem isso,
    um card patológico consome a sessão inteira ciclando no mesmo vermelho.
  - **Iterar NÃO bloqueia.** Falha diferente, progresso, build verde — tudo
    isso segue. Um teto que morde a iteração legítima seria desligado no
    primeiro dia, e aí não protege nada. Metade dos casos abaixo existe só
    para provar que ele não morde.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

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
RED_A_OUTRO_RUN = """
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
VERDE = "Tests run: 12, Failures: 0, Errors: 0\nBUILD SUCCESS"


# ── repetir bloqueia ─────────────────────────────────────────────────────────

def test_terceira_falha_igual_bloqueia(tmp):
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


def test_ruido_volatil_nao_disfarca_a_mesma_falha(tmp):
    """Timestamp e duração mudam a cada run — não podem virar 'falha nova'.

    Sem a normalização, cada volta teria assinatura própria e o teto nunca
    dispararia: o detector ficaria verde para sempre enquanto o loop roda.
    """
    d = fresh(tmp, "ruido")
    run("PostToolUse", d, RED_A)
    run("PostToolUse", d, RED_A_OUTRO_RUN)
    run("PostToolUse", d, RED_A)
    r = run("PreToolUse", d)
    check("mesma falha com timestamp/duração diferentes conta como a mesma",
          r.returncode == 2, f"exit {r.returncode}")


def test_aviso_antes_do_bloqueio(tmp):
    d = fresh(tmp, "aviso")
    run("PostToolUse", d, RED_A)
    r = run("PostToolUse", d, RED_A)
    check("a 2ª aparição avisa que a próxima bloqueia",
          "BLOQUEADA" in r.stderr or "⚠" in r.stderr, r.stderr[:120])


# ── iterar NÃO bloqueia ──────────────────────────────────────────────────────

def test_falhas_diferentes_nao_bloqueiam(tmp):
    d = fresh(tmp, "progresso")
    for text in (RED_A, RED_B, RED_A, RED_B):
        run("PostToolUse", d, text)
    r = run("PreToolUse", d)
    check("alternar entre falhas diferentes não bloqueia (2x cada)",
          r.returncode == 0, f"exit {r.returncode}")


def test_verde_zera_o_contador(tmp):
    d = fresh(tmp, "verde")
    run("PostToolUse", d, RED_A)
    run("PostToolUse", d, RED_A)
    (d / ".claude" / "last-build.json").write_text(json.dumps({"status": "SUCCESS"}))
    run("PostToolUse", d, VERDE)
    (d / ".claude" / "last-build.json").write_text(json.dumps({"status": "STALE"}))
    run("PostToolUse", d, RED_A)
    r = run("PreToolUse", d)
    check("build verde zera o contador (a falha anterior é passado)",
          r.returncode == 0, f"exit {r.returncode}")


def test_sucesso_nao_conta(tmp):
    d = fresh(tmp, "sucesso")
    for _ in range(5):
        run("PostToolUse", d, "APPROVED. Tests run: 40, Failures: 0, Errors: 0")
    r = run("PreToolUse", d)
    check("resultado sem falha nunca conta", r.returncode == 0, f"exit {r.returncode}")
    state = json.loads((d / ".claude" / "loop-state.json").read_text())
    check("nenhuma assinatura registrada num run limpo", state["signatures"] == {})


def test_assinatura_envelhece(tmp):
    """Vermelho resolvido não pode seguir contando meia hora depois."""
    d = fresh(tmp, "idade")
    run("PostToolUse", d, RED_A)
    run("PostToolUse", d, RED_A)
    for _ in range(7):  # AGE_OUT = 6 delegações sem a assinatura aparecer
        run("PostToolUse", d, "tudo certo por aqui")
    run("PostToolUse", d, RED_A)
    r = run("PreToolUse", d)
    check("assinatura ausente por 6+ delegações é esquecida",
          r.returncode == 0, f"exit {r.returncode}")


# ── nunca atrapalha ──────────────────────────────────────────────────────────

def test_outras_tools_passam(tmp):
    d = fresh(tmp, "outras")
    payload = {"tool_name": "Bash", "hook_event_name": "PreToolUse", "cwd": str(d),
               "tool_input": {"command": "ls"}}
    r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                       capture_output=True, text=True)
    check("hook só age em Task", r.returncode == 0)


def test_payload_ilegivel_libera(tmp):
    r = subprocess.run([sys.executable, str(HOOK)], input="{isto não é json",
                       capture_output=True, text=True)
    check("payload ilegível libera (fail-open)", r.returncode == 0)


def test_estado_corrompido_libera(tmp):
    d = fresh(tmp, "corrompido")
    (d / ".claude" / "loop-state.json").write_text("{lixo")
    r = run("PreToolUse", d)
    check("estado corrompido libera em vez de travar a sessão", r.returncode == 0)


def test_desligavel_explicitamente(tmp):
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
        test_terceira_falha_igual_bloqueia(tmp)
        test_ruido_volatil_nao_disfarca_a_mesma_falha(tmp)
        test_aviso_antes_do_bloqueio(tmp)
        test_falhas_diferentes_nao_bloqueiam(tmp)
        test_verde_zera_o_contador(tmp)
        test_sucesso_nao_conta(tmp)
        test_assinatura_envelhece(tmp)
        test_outras_tools_passam(tmp)
        test_payload_ilegivel_libera(tmp)
        test_estado_corrompido_libera(tmp)
        test_desligavel_explicitamente(tmp)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
