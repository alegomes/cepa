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
  - unknown schema_version is refused.
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
  S1: {{demanda: A, surface: [{s1}], human_gate: {hg1}, acceptance: ok, {ac1} context: [x]}}
  S2: {{demanda: B, surface: [{s2}], human_gate: none, acceptance: ok, acceptance_cmd: "true", context: [x]}}
  S3: {{demanda: C, surface: ["docs/x.md"], human_gate: none, acceptance: ok, acceptance_cmd: "true", context: [x]}}
  S4: {{demanda: D, surface: ["src/b.py"], human_gate: none, acceptance: ok, acceptance_cmd: "true", context: [x]}}
"""


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
