#!/usr/bin/env python3
"""Regression tests for common/bin/cepa-dor (Definition of Ready do Maestro).

No third-party deps beyond PyYAML (already required by the script itself) —
run with `python3 tests/test_cepa_dor.py`. Exits non-zero on first failure.

Guards the intake-gate contracts from the v1 design (Componente 4):
  - surface intersection downs BOTH slices (the v0 merge-conflict lesson);
  - enforcement zone is an unconditional veto;
  - open human_gate / missing acceptance_cmd in a no-build repo → NOT-READY;
  - D7 floor (<4 demandas) blocks the program;
  - a clean plan comes out READY (exit 0 or 1-with-warnings, never 2);
  - unknown schema_version is refused;
  - "BDD ou substrato" (A3): um slice cujo aceite só nomeia passos privados de
    implementação reprova nomeando a lacuna; declarar `acceptance_form:
    substrate` (ou escrever a tripla observável) passa.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOR = REPO / "common" / "bin" / "cepa-dor"

FAILURES = []


def run_dor(plan_text, repo, extra=None):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(plan_text)
        plan = f.name
    cmd = [sys.executable, str(DOR), plan, "--repo", str(repo)] + (extra or [])
    return subprocess.run(cmd, capture_output=True, text=True)


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def make_repo(tmp, no_build=True):
    """Tiny committed git repo the surfaces expand against."""
    repo = Path(tmp) / "r"
    repo.mkdir()
    for p in ["src/a.py", "src/b.py", "docs/x.md", "plug/hooks/h.py"]:
        (repo / p).parent.mkdir(parents=True, exist_ok=True)
        (repo / p).write_text("x")
    if no_build:
        (repo / ".claude").mkdir()
        (repo / ".claude" / "no-build").write_text("")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "seed"], cwd=repo, check=True)
    return repo


PLAN_4D = """\
schema_version: 1
program: t
waves:
  - id: 1
    slices: [S1, S2]
    status: pending
slices:
  S1: {{demanda: A, surface: [{s1}], human_gate: {hg1}, acceptance: ok, acceptance_form: substrate, {ac1} context: [x]}}
  S2: {{demanda: B, surface: [{s2}], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
  S3: {{demanda: C, surface: ["docs/x.md"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
  S4: {{demanda: D, surface: ["src/b.py"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
"""

# Plano de 1 slice na onda (S2..S4 existem só para o piso D7) usado para
# exercitar a forma do aceite isoladamente.
PLAN_FORM = """\
schema_version: 1
program: t
waves:
  - id: 1
    slices: [S1]
    status: pending
slices:
  S1:
    demanda: A
    surface: ["src/a.py"]
    human_gate: none
    acceptance: "{acc}"
    acceptance_cmd: "true"
    context: [x]
{form}\
  S2: {{demanda: B, surface: ["docs/x.md"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
  S3: {{demanda: C, surface: ["docs/x.md"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
  S4: {{demanda: D, surface: ["docs/x.md"], human_gate: none, acceptance: ok, acceptance_form: substrate, acceptance_cmd: "true", context: [x]}}
"""

# Aceite que só nomeia passos privados de implementação — o caso que o A3 pega.
ACC_PRIVADO = "refatorar o parser e extrair o helper de normalizacao"
ACC_BDD = ("Dado um card em Review sem razao, Quando o agente posta a "
           "devolucao, Entao o hook bloqueia nomeando o campo")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)

        # clean plan → READY, exit 0/1
        r = run_dor(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        # note: S2/S3 share docs/x.md but are in DIFFERENT waves? No — S2 in
        # wave, S3 not in wave 1 → disjunção só entre slices DA onda.
        check("plano limpo sai READY", r.returncode in (0, 1), r.stdout)
        check("disjunção só compara slices da MESMA onda",
              "intersecta a de S3" not in r.stdout, r.stdout)

        # intersection downs BOTH
        r = run_dor(PLAN_4D.format(s1='"src/*.py"', s2='"src/b.py"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        check("interseção derruba os DOIS slices", r.returncode == 2
              and r.stdout.count("NOT-READY") == 2, r.stdout)

        # enforcement zone veto
        r = run_dor(PLAN_4D.format(s1='"plug/hooks/h.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        check("zona de enforcement é veto", r.returncode == 2
              and "zona de enforcement" in r.stdout, r.stdout)

        # open human gate
        r = run_dor(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1='"open: naming"',
                                   ac1='acceptance_cmd: "true",'), repo)
        check("human_gate aberto → NOT-READY", r.returncode == 2
              and "decisão estratégica em aberto" in r.stdout, r.stdout)

        # missing acceptance_cmd in no-build repo
        r = run_dor(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1=""), repo)
        check("no-build sem acceptance_cmd → NOT-READY", r.returncode == 2
              and "acceptance_cmd" in r.stdout, r.stdout)

        # D7 floor
        plan_3d = PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                 hg1="none", ac1='acceptance_cmd: "true",')
        plan_3d = "\n".join(l for l in plan_3d.splitlines()
                            if not l.startswith("  S4"))
        r = run_dor(plan_3d, repo)
        check("piso D7 (<4 demandas) bloqueia", r.returncode == 2
              and "piso é 4" in r.stdout, r.stdout)

        # unknown schema_version
        r = run_dor("schema_version: 2\nprogram: t\nwaves: []\nslices: {}\n",
                    repo)
        check("schema_version desconhecida é recusada", r.returncode == 2
              and "schema_version" in r.stdout, r.stdout)

        # ── A3: "BDD ou substrato" ──────────────────────────────────────────
        # US sem BDD e sem declaração de substrato → NOT-READY, lacuna nomeada
        r = run_dor(PLAN_FORM.format(acc=ACC_PRIVADO, form=""), repo)
        check("aceite só com passos privados → NOT-READY", r.returncode == 2
              and "NOT-READY" in r.stdout, r.stdout)
        check("a lacuna do aceite é NOMEADA (BDD ou substrato)",
              "Given/When/Then" in r.stdout and "substrate" in r.stdout,
              r.stdout)

        # substrato declarado → passa (aceite técnico é legítimo p/ TS)
        r = run_dor(PLAN_FORM.format(acc=ACC_PRIVADO,
                                     form="    acceptance_form: substrate\n"),
                    repo)
        check("substrato declarado passa", r.returncode in (0, 1), r.stdout)

        # tripla observável (pt-BR) sem declarar forma → passa
        r = run_dor(PLAN_FORM.format(acc=ACC_BDD, form=""), repo)
        check("Given/When/Then observável passa sem declarar forma",
              r.returncode in (0, 1), r.stdout)

        # declarou bdd mas não escreveu a tripla → NOT-READY
        r = run_dor(PLAN_FORM.format(acc=ACC_PRIVADO,
                                     form="    acceptance_form: bdd\n"), repo)
        check("acceptance_form: bdd sem tripla → NOT-READY",
              r.returncode == 2 and "acceptance_form: bdd" in r.stdout,
              r.stdout)

        # valor inválido é recusado em vez de ignorado em silêncio
        r = run_dor(PLAN_FORM.format(acc=ACC_BDD,
                                     form="    acceptance_form: talvez\n"), repo)
        check("acceptance_form inválido → NOT-READY", r.returncode == 2
              and "inválido" in r.stdout, r.stdout)

        # baseline não-verde em repo COM build
        repo2 = make_repo(tempfile.mkdtemp(dir=tmp), no_build=False)
        r = run_dor(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo2)
        check("baseline ausente em repo com build → NOT-READY",
              r.returncode == 2 and "baseline" in r.stdout, r.stdout)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
