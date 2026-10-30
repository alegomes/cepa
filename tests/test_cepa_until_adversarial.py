#!/usr/bin/env python3
"""Adversarial input to `cepa-until` — the l4 level of the proof gate.

## Why this file exists separately

`test_cepa_until.py` proves the supervisor does the right thing when everything
is in place. This one proves what it does when it is NOT — and for an executor
that runs alone in the small hours that is the half that matters more, because there is
nobody to read a traceback at 3am.

The rule all the cases here share: **the supervisor may refuse, may
end, may count as a failure — but must never blow up.** A traceback kills
the whole window and leaves the record half done, which is exactly the opposite
of what it exists to do.

Two input surfaces:
  - the COMMAND LINE (absurd durations, invalid ceiling, conflicting flags);
  - the STATE ON DISK, which changes under it during the run (the corrupted or deleted
    `plan.yaml` midway, the `claude` that vanishes from PATH).

Run: python3 tests/test_cepa_until_adversarial.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    fake_claude, item, ledger_of, build_repo, run_until)

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def without_traceback(p, given_name):
    check(f"{given_name}: não estoura",
          "Traceback" not in (p.stderr or ""),
          (p.stderr or "").strip()[-300:])


# ── 1. command line ─────────────────────────────────────────────────────────

def test_absurd_durations_are_refused_without_blowing_up():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        for bad in ("0h", "0m", "-3h", "1e9h", "h", "12hh", ""):
            p, calls = run_until(root, binv, plan, ["--for", bad])
            without_traceback(p, f"--for {bad!r}")
            check(f"--for {bad!r} é recusado", p.returncode == 2,
                  f"saiu {p.returncode}")
            check(f"--for {bad!r} não dispara nada", not calls, str(calls))


def test_giant_window_does_not_break_the_arithmetic():
    """An absurd window has to either be accepted and become a valid date, or be
    refused — never become an `OverflowError` in the middle of the night."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        for big in ("99999h", "1000000m"):
            p, _ = run_until(root, binv, plan, ["--for", big, "--dry-run"])
            without_traceback(p, f"--for {big}")
            check(f"--for {big} termina com veredito",
                  p.returncode in (0, 2), f"saiu {p.returncode}")


def test_invalid_circuit_breaker_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        for bad in ("0", "-1"):
            p, calls = run_until(root, binv, plan,
                               ["--for", "2h", "--max-failures", bad])
            without_traceback(p, f"--max-failures {bad}")
            check(f"--max-failures {bad} é recusado", p.returncode == 2,
                  f"saiu {p.returncode}")
            check("...e nada foi disparado", not calls, str(calls))


def test_hostile_queue_name_does_not_become_a_command():
    """The queue name goes into the subprocess prompt. It is passed as a
    LIST ELEMENT, never through a shell, so a metacharacter is text — but that
    needs to stay true, and it is the kind of thing a refactor to
    `shell=True` would silently break."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        canary = Path(tmp) / "executou.txt"
        hostile = f"fila; touch {canary}"
        env = dict(os.environ)
        env["PATH"] = f"{binv}:{env['PATH']}"
        env["FAKE_PLANO"] = str(plan)
        env["FAKE_CHAMADAS"] = str(Path(tmp) / "chamadas.jsonl")
        p = subprocess.run(
            [sys.executable,
             str(Path(__file__).resolve().parent.parent / "common" / "bin" / "cepa-until"),
             hostile, "--repo", str(root), "--for", "2h"],
            capture_output=True, text=True, env=env, timeout=120)
        without_traceback(p, "nome de fila hostil")
        check("nome de fila hostil não executa nada",
              not canary.exists(), "o `touch` embutido no nome rodou")
        check("...e o comando recusa a fila inexistente", p.returncode == 2,
              f"saiu {p.returncode}")


# ── 2. the disk changes under it ────────────────────────────────────────────

def test_corrupted_plan_mid_run_ends_without_blowing_up():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        body = ("marca(primeiro_pendente(), status='done')\n"
                 "open(PLANO, 'w').write('isto: [nao: e: yaml valido\\n')\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        without_traceback(p, "plano corrompido")
        check("dispara uma vez e encerra", len(calls) == 1,
              f"disparou {len(calls)}x")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("o run encerra por `fila-ilegivel`",
              end["motivo"] == "fila-ilegivel", str(end))
        check("...e o registro fecha mesmo assim",
              end.get("itens") is not None, str(end))


def test_deleted_plan_mid_run_ends_without_blowing_up():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = ("marca(primeiro_pendente(), status='done')\n"
                 "os.unlink(PLANO)\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        without_traceback(p, "plano apagado")
        check("dispara uma vez e encerra", len(calls) == 1,
              f"disparou {len(calls)}x")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("o run encerra por `fila-ilegivel`",
              end["motivo"] == "fila-ilegivel", str(end))


def test_claude_corrupted_midway_is_counted_failure_not_traceback():
    """`claude` passes the launch test and becomes garbage afterwards. Blowing up here
    would kill the supervisor and the window together, with the record half done."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = ("marca(primeiro_pendente(), status='done')\n"
                 "alvo = os.path.join(os.environ['FAKE_BIN'], 'claude')\n"
                 "os.unlink(alvo)\n"
                 "os.mkdir(alvo)\n")   # directory in place of the binary: OSError on spawn
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        # FIXED PATH, and this is the point: with the inherited PATH, deleting the fake made
        # execvp keep searching and find the REAL `claude` — the test
        # ran the real agent for 87s before I noticed. A test that invokes
        # the real binary measures nothing and still spends the session of whoever runs it.
        p, calls = run_until(root, binv, plan, ["--for", "2h", "--max-failures", "2"],
                           extra_env={"FAKE_BIN": str(binv),
                                      "PATH": "/usr/bin:/bin"})
        without_traceback(p, "claude corrompido")
        ends = [e for e in ledger_of(root) if e.get("evento") == "item_end"]
        check("o item que nem lançou é registrado sem progresso",
              any(f["progresso"] is False for f in ends), str(ends))
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("e o run encerra pelo disjuntor, com registro completo",
              end["motivo"] == "disjuntor", str(end))
        check("...e o relatório nomeia que nem deu para lançar",
              "lançar" in p.stdout, p.stdout[-500:])


def test_exhausted_item_that_cannot_be_blocked_ends_without_loop():
    """The per-item attempt ceiling depends on WRITING `blocked` into the plan —
    it is what makes `queue` stop re-offering the item. If that write fails
    (full disk, permission, plan of another owner), the supervisor cannot
    go on: the next `queue` would return the same item and the window would become a
    loop. It ends with its own reason, and without a traceback.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        d = Path(root) / ".claude" / "programs" / "fila"
        # The fake locks the WRITE in the queue directory (`finish` writes a
        # .tmp beside it and renames), keeping the READ standing — which is the shape
        # of the failure: the supervisor keeps seeing the queue and keeps being unable
        # to take the item off the front.
        binv = fake_claude(tmp, f"os.chmod({str(d)!r}, 0o555)")
        plan = d / "plan.yaml"
        try:
            p, calls = run_until(root, binv, plan, ["--for", "2h"])
        finally:
            os.chmod(d, 0o755)
        without_traceback(p, "escrita do `blocked` recusada")
        check("o run não vira laço no mesmo item", len(calls) <= 3,
              f"disparou {len(calls)}x")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("...encerra por `item-preso`", end["motivo"] == "item-preso",
              str(end))
        check("...e o motivo nomeia o item e o que falhou",
              "a1" in (end.get("detalhe") or "")
              and "tentativas" in (end.get("detalhe") or ""), str(end))
        ev = [e for e in ledger_of(root) if e.get("evento") == "esgotado"]
        check("...o registro guarda que o bloqueio NÃO pegou",
              ev and ev[-1].get("bloqueado") is False, str(ev))


def main():
    print("cepa-until — entrada adversária (nível l4)\n")
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"{given_name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
