#!/usr/bin/env python3
"""Regression tests for common/bin/cepa-dor (Maestro's Definition of Ready).

No third-party deps beyond PyYAML (already required by the script itself) —
run with `python3 tests/test_cepa_pain.py`. Exits non-zero on first failure.

Guards the intake-gate contracts from the v1 design (Component 4):
  - surface intersection on a `cartorios` (registry-file) file downs BOTH
    slices; intersection on any other file is a warning, not a veto (P3,
    docs/spec/planejador-de-lotes-paralelos.md CS-4); no `cartorios` field
    means no data, so nothing is vetoed on overlap — only warned;
  - enforcement zone is an unconditional veto;
  - open human_gate / missing acceptance_cmd in a no-build repo → NOT-READY;
  - D7 floor (<4 demands) blocks the program;
  - a clean plan comes out READY (exit 0 or 1-with-warnings, never 2);
  - unknown schema_version is refused (known: 1 and 2);
  - `mode` (conducting thread, schema shared with board-flow): a v1 plan
    without `mode` stays valid without migration, v2 requires the field, single-track in v1
    says to bump the version, single-track in v2 is refused pointing the way, and
    an unknown value does not pass in silence;
  - "BDD or substrate" (A3): a slice whose acceptance only names private
    implementation steps fails naming the gap; declaring `acceptance_form:
    substrate` (or writing the observable triple) passes.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAIN = REPO / "common" / "bin" / "cepa-dor"

FAILURES = []


def run_pain(plan_text, repo, extra=None):
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(plan_text)
        plan = f.name
    cmd = [sys.executable, str(PAIN), plan, "--repo", str(repo)] + (extra or [])
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
    for p in ["src/a.py", "src/b.py", "docs/x.md", "plug/hooks/h.py", "package-lock.json"]:
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


def with_registries(plan_text, files):
    """Inserts the optional `cartorios:` field at the top of an already formatted plan."""
    block = "cartorios:\n" + "".join(f'  - "{f}"\n' for f in files)
    return plan_text.replace("program: t\n", "program: t\n" + block, 1)

# Plan of 1 slice in the wave (S2..S4 exist only for the D7 floor) used to
# exercise the shape of the acceptance in isolation.
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

# Acceptance that only names private implementation steps — the case A3 catches.
ACC_PRIVATE = "refatorar o parser e extrair o helper de normalizacao"
ACC_BDD = ("Dado um card em Review sem razao, Quando o agente posta a "
           "devolucao, Entao o hook bloqueia nomeando o campo")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        repo = make_repo(tmp)

        # clean plan → READY, exit 0/1
        r = run_pain(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        # note: S2/S3 share docs/x.md but are in DIFFERENT waves? No — S2 in
        # wave, S3 not in wave 1 → disjointness only between slices OF the wave.
        check("plano limpo sai READY", r.returncode in (0, 1), r.stdout)
        check("disjunção só compara slices da MESMA onda",
              "intersecta a de S3" not in r.stdout, r.stdout)

        # without `cartorios` in the plan: intersection no longer vetoes — only warns
        # (P3: loosening of the intake, docs/spec/planejador-de-lotes-paralelos.md)
        r = run_pain(PLAN_4D.format(s1='"src/*.py"', s2='"src/b.py"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        check("sem cartorios declarado, interseção não veta",
              r.returncode != 2 or "NOT-READY" not in r.stdout, r.stdout)
        check("sem cartorios declarado, interseção é avisada",
              "cruzam fora de arquivo-cartório" in r.stdout, r.stdout)

        # intersection ON a declared registry file downs BOTH slices
        plan_cart = with_registries(
            PLAN_4D.format(s1='"src/*.py"', s2='"src/b.py"',
                           hg1="none", ac1='acceptance_cmd: "true",'),
            ["src/b.py"])
        r = run_pain(plan_cart, repo)
        check("interseção num arquivo-cartório derruba os DOIS slices",
              r.returncode == 2 and r.stdout.count("NOT-READY") == 2, r.stdout)
        check("a lacuna nomeia o arquivo-cartório",
              "arquivo-cartório" in r.stdout, r.stdout)

        # intersection declared as a registry BUT that does not match the slice does not veto
        plan_cart_miss = with_registries(
            PLAN_4D.format(s1='"src/*.py"', s2='"src/b.py"',
                           hg1="none", ac1='acceptance_cmd: "true",'),
            ["docs/x.md"])
        r = run_pain(plan_cart_miss, repo)
        check("cartório declarado que não intersecta os slices não veta",
              r.returncode != 2 or "NOT-READY" not in r.stdout, r.stdout)

        # registry file that no slice declares → wave warning, not veto
        plan_undeclared = with_registries(
            PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                           hg1="none", ac1='acceptance_cmd: "true",'),
            ["src/b.py"])  # S4 declares src/b.py only outside wave 1
        r = run_pain(plan_undeclared, repo)
        check("cartório fora de toda superfície da onda é avisado",
              "fora de toda superfície" in r.stdout, r.stdout)
        check("cartório fora de toda superfície não veta",
              r.returncode != 2 or "NOT-READY" not in r.stdout, r.stdout)

        # without `cartorios`, a file that matched the old HIGH_FRICTION
        # heuristic (removed by P3) raises no warning — locks against the
        # heuristic coming back by mistake or an equivalent bug
        r = run_pain(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        check("sem cartorios, arquivo da heurística antiga não gera aviso",
              "fora de toda superfície" not in r.stdout, r.stdout)

        # enforcement zone veto
        r = run_pain(PLAN_4D.format(s1='"plug/hooks/h.py"', s2='"docs/x.md"',
                                   hg1="none", ac1='acceptance_cmd: "true",'),
                    repo)
        check("zona de enforcement é veto", r.returncode == 2
              and "zona de enforcement" in r.stdout, r.stdout)

        # open human gate
        r = run_pain(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1='"open: naming"',
                                   ac1='acceptance_cmd: "true",'), repo)
        check("human_gate aberto → NOT-READY", r.returncode == 2
              and "decisão estratégica em aberto" in r.stdout, r.stdout)

        # missing acceptance_cmd in no-build repo
        r = run_pain(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                   hg1="none", ac1=""), repo)
        check("no-build sem acceptance_cmd → NOT-READY", r.returncode == 2
              and "acceptance_cmd" in r.stdout, r.stdout)

        # D7 floor
        plan_3d = PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                 hg1="none", ac1='acceptance_cmd: "true",')
        plan_3d = "\n".join(l for l in plan_3d.splitlines()
                            if not l.startswith("  S4"))
        r = run_pain(plan_3d, repo)
        check("piso D7 (<4 demandas) bloqueia", r.returncode == 2
              and "piso é 4" in r.stdout, r.stdout)

        # unknown schema_version (v1 and v2 are known; 3 is not)
        r = run_pain("schema_version: 3\nprogram: t\nwaves: []\nslices: {}\n",
                    repo)
        check("schema_version desconhecida é recusada", r.returncode == 2
              and "schema_version" in r.stdout, r.stdout)

        # ── `mode` (conducting thread): schema shared with board-flow ────────
        # v1 COMPATIBILITY — the assertion that holds up "a plan on disk
        # does not need to be migrated": PLAN_4D is v1 and without `mode`, like every plan
        # written before the field existed, and must pass exactly as before.
        wave_v1 = PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
                                 hg1="none", ac1='acceptance_cmd: "true",')
        r = run_pain(wave_v1, repo)
        check("v1 sem `mode` segue válido (legado = parallel-waves)",
              r.returncode in (0, 1), r.stdout)

        # v2 with the explicit wave mode: same plan, same verdict
        wave_v2 = wave_v1.replace("schema_version: 1",
                                  "schema_version: 2\nmode: parallel-waves", 1)
        check("o fixture v2 difere mesmo do v1", wave_v2 != wave_v1)
        r = run_pain(wave_v2, repo)
        check("v2 com mode: parallel-waves é aceito",
              r.returncode in (0, 1), r.stdout)

        # v2 requires the field — without it there is no way to know which document it is
        r = run_pain(wave_v1.replace("schema_version: 1", "schema_version: 2", 1),
                    repo)
        check("v2 sem `mode` é recusado", r.returncode == 2
              and "exige `mode` explícito" in r.stdout, r.stdout)

        # single-track did NOT exist in v1 — the refusal says to bump the version instead of
        # accepting a document that version never described
        r = run_pain("schema_version: 1\nmode: single-track\nprogram: t\n"
                    "items:\n  - id: X\n    why: y\n    status: pending\n", repo)
        check("single-track em plano v1 é recusado", r.returncode == 2
              and "não existe no schema v1" in r.stdout, r.stdout)
        check("a recusa do v1 manda subir para v2",
              "schema_version: 2" in r.stdout, r.stdout)

        # single-track in v2 is refused POINTING THE WAY — a raw error here
        # would return "no pending wave", which does not say what to do.
        r = run_pain("schema_version: 2\nmode: single-track\nprogram: t\n"
                    "items:\n  - id: X\n    why: y\n    status: pending\n", repo)
        # do NOT match only on "single-track": the generic message of unknown
        # mode also contains that word ("esperado 'parallel-waves'
        # ou 'single-track'"), and the assertion would pass for the wrong reason — that is
        # what the perturbation caught. Match on the specific guidance.
        check("plano single-track é recusado pelo cepa-dor",
              r.returncode == 2 and "um item por vez" in r.stdout, r.stdout)
        check("recusa do single-track aponta /common:next",
              "/common:next" in r.stdout, r.stdout)

        # an invalid value does not pass in silence as if it were a wave
        r = run_pain("schema_version: 2\nmode: talvez\nprogram: t\n"
                    "waves: []\nslices: {}\n", repo)
        check("mode desconhecido é recusado", r.returncode == 2
              and "mode desconhecido" in r.stdout, r.stdout)

        # ── A3: "BDD or substrate" ──────────────────────────────────────────
        # US without BDD and without a substrate declaration → NOT-READY, gap named
        r = run_pain(PLAN_FORM.format(acc=ACC_PRIVATE, form=""), repo)
        check("aceite só com passos privados → NOT-READY", r.returncode == 2
              and "NOT-READY" in r.stdout, r.stdout)
        check("a lacuna do aceite é NOMEADA (BDD ou substrato)",
              "Given/When/Then" in r.stdout and "substrate" in r.stdout,
              r.stdout)

        # substrate declared → passes (technical acceptance is legitimate for TS)
        r = run_pain(PLAN_FORM.format(acc=ACC_PRIVATE,
                                     form="    acceptance_form: substrate\n"),
                    repo)
        check("substrato declarado passa", r.returncode in (0, 1), r.stdout)

        # observable triple (pt-BR) without declaring the form → passes
        r = run_pain(PLAN_FORM.format(acc=ACC_BDD, form=""), repo)
        check("Given/When/Then observável passa sem declarar forma",
              r.returncode in (0, 1), r.stdout)

        # declared bdd but did not write the triple → NOT-READY
        r = run_pain(PLAN_FORM.format(acc=ACC_PRIVATE,
                                     form="    acceptance_form: bdd\n"), repo)
        check("acceptance_form: bdd sem tripla → NOT-READY",
              r.returncode == 2 and "acceptance_form: bdd" in r.stdout,
              r.stdout)

        # an invalid value is refused instead of silently ignored
        r = run_pain(PLAN_FORM.format(acc=ACC_BDD,
                                     form="    acceptance_form: talvez\n"), repo)
        check("acceptance_form inválido → NOT-READY", r.returncode == 2
              and "inválido" in r.stdout, r.stdout)

        # non-green baseline in a repo WITH a build
        repo2 = make_repo(tempfile.mkdtemp(dir=tmp), no_build=False)
        r = run_pain(PLAN_4D.format(s1='"src/a.py"', s2='"docs/x.md"',
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
