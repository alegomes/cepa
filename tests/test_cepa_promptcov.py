#!/usr/bin/env python3
"""Regressão de `common/bin/cepa-promptcov` — cobertura de checkpoints de prosa.

No third-party deps — run with `python3 tests/test_cepa_promptcov.py`. Exits
non-zero on the first failure.

Guardas:
  - checkpoint `**[tag:id]**` no comando, sem `tag:id` correspondente no
    teste → aparece como sem cobertura, exit 1;
  - todo checkpoint coberto → exit 0;
  - `--tag` filtra para uma família só (um comando pode ter mais de uma);
  - sem nenhum checkpoint do tag pedido → nunca declara cobertura 100% por
    vacuidade — devolve "nada para medir", exit 2 (mesmo espírito de CS-3 do
    cepa-hotspots: histórico insuficiente vira aviso explícito, não heurística
    disfarçada);
  - arquivo inexistente → exit 2;
  - run REAL sobre maestro/commands/program-plan.md × tests/test_program_plan_sweep.py
    (o par que motivou a ferramenta) sai com cobertura total — se isso quebrar,
    é regressão real no P1, não só neste script.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin" / "cepa-promptcov"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(cmd_path, test_path, extra=None):
    return subprocess.run(
        [sys.executable, str(BIN), str(cmd_path), str(test_path)] + (extra or []),
        capture_output=True, text=True)


CMD_TEXT = """\
# comando fixture

1. **Passo 1.** Comportamento normal.

   **[sweep:alpha]** Peça alpha do modo sweep.

2. **Passo 2.**

   **[sweep:beta]** Peça beta do modo sweep.

   **[outro:gamma]** Peça de outra família de anotação.
"""

TEST_FULL = """\
def main():
    check("[sweep:alpha] cobre alpha", True)
    check("[sweep:beta] cobre beta", True)
    check("[outro:gamma] cobre gamma", True)
"""

TEST_MISSING_BETA = """\
def main():
    check("[sweep:alpha] cobre alpha", True)
    check("[outro:gamma] cobre gamma", True)
"""

TEST_EMPTY = """\
def main():
    pass
"""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        cmd = Path(tmp) / "comando.md"
        cmd.write_text(CMD_TEXT)

        # ── caso feliz: cobertura total ──────────────────────────────────
        t_full = Path(tmp) / "test_full.py"
        t_full.write_text(TEST_FULL)
        r = run(cmd, t_full)
        check("cobertura total sai exit 0", r.returncode == 0, r.stdout)
        check("lista os 3 checkpoints (2 sweep + 1 outro, sem filtro)",
              "sweep:alpha" in r.stdout and "sweep:beta" in r.stdout
              and "outro:gamma" in r.stdout, r.stdout)
        check("relata 3/3 coberto(s)", "3/3 checkpoint(s) coberto(s)" in r.stdout,
              r.stdout)

        # ── checkpoint sem cobertura é detectado ─────────────────────────
        t_missing = Path(tmp) / "test_missing.py"
        t_missing.write_text(TEST_MISSING_BETA)
        r = run(cmd, t_missing)
        check("checkpoint sem cobertura sai exit 1", r.returncode == 1, r.stdout)
        check("nomeia exatamente o checkpoint sem cobertura (beta)",
              "sem cobertura: sweep:beta" in r.stdout, r.stdout)
        check("checkpoint coberto não aparece como sem cobertura",
              "sweep:alpha" not in r.stdout.split("sem cobertura:")[-1], r.stdout)

        # ── --tag filtra para uma família só ─────────────────────────────
        r = run(cmd, t_missing, ["--tag", "sweep"])
        check("--tag=sweep não mede a família 'outro'",
              "outro:gamma" not in r.stdout, r.stdout)
        check("--tag=sweep ainda acusa beta sem cobertura",
              r.returncode == 1 and "sweep:beta" in r.stdout, r.stdout)

        r = run(cmd, t_missing, ["--tag", "outro"])
        check("--tag=outro mede só gamma, que está coberto -> exit 0",
              r.returncode == 0, r.stdout)

        # ── sem checkpoint nenhum do tag pedido: nunca 100% por vacuidade ─
        r = run(cmd, t_missing, ["--tag", "inexistente"])
        check("tag sem nenhum checkpoint -> exit 2 (recusa, não 100% falso)",
              r.returncode == 2, r.stdout)
        check("a recusa nomeia que não há dado para medir",
              "nenhum checkpoint" in r.stdout, r.stdout)

        # ── comando sem NENHUM checkpoint (nem outro tag) ────────────────
        cmd_sem = Path(tmp) / "comando_sem.md"
        cmd_sem.write_text("# comando sem anotação nenhuma\n")
        r = run(cmd_sem, t_full)
        check("comando sem checkpoint algum -> exit 2", r.returncode == 2, r.stdout)

        # ── teste vazio: todo checkpoint aparece sem cobertura ───────────
        t_empty = Path(tmp) / "test_empty.py"
        t_empty.write_text(TEST_EMPTY)
        r = run(cmd, t_empty)
        check("teste sem nenhuma cobertura -> exit 1, todos sem cobertura",
              r.returncode == 1 and r.stdout.count("✗") == 3, r.stdout)

        # ── arquivo inexistente ───────────────────────────────────────────
        r = run(Path(tmp) / "nao-existe.md", t_full)
        check("comando inexistente -> exit 2", r.returncode == 2, r.stderr)
        r = run(cmd, Path(tmp) / "nao-existe.py")
        check("teste inexistente -> exit 2", r.returncode == 2, r.stderr)

        # ── --json ────────────────────────────────────────────────────────
        r = run(cmd, t_missing, ["--json"])
        check("--json produz JSON parseável", r.returncode in (0, 1), r.stdout)
        import json
        data = json.loads(r.stdout)
        check("--json nomeia uncovered corretamente",
              data.get("uncovered") == ["sweep:beta"], data)

    # ── run real sobre os pares de verdade ───────────────────────────────
    # O mesmo comando carrega DUAS famílias de anotação (`sweep`, do modo de
    # varrimento, e `from-plan`, da promoção fila → ondas), cada uma com o seu
    # teste de regressão. Sem o `--tag` o cruzamento mede um teste contra os
    # checkpoints do outro e acusa falta que não existe — que é exatamente o
    # que o filtro existe para evitar.
    real_cmd = REPO / "maestro" / "commands" / "program-plan.md"
    for familia, arquivo in (("sweep", "test_program_plan_sweep.py"),
                             ("from-plan", "test_program_plan_from_plan.py")):
        r = run(real_cmd, REPO / "tests" / arquivo, ["--tag", familia])
        check(f"run real: program-plan.md × {arquivo} cobre tudo de `{familia}`",
              r.returncode == 0, r.stdout)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
