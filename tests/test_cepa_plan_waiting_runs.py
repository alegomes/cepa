#!/usr/bin/env python3
"""`cepa plan waiting` shows, in a section of its own, the runs waiting on the
owner, each with the command that resolves it (spec
docs/spec/decisoes-de-todas-as-filas.md, CS-2).

The section reads the same source as `cepa until pending` (the spec forbids a
rule of its own for "a run waiting"), so the fixtures here are the run states
that make `pending` list a run, and every case checks both commands agree.

Against the real CLI, in a temporary git repo:

  - CS-2 red test: a run of queue `a` waiting to land, `waiting` prints a runs
    section with `a/<run>` and `cepa-until land a/<run>`, exit 0
  - `--json` carries the same run under `runs`
  - a run whose branch already landed in the destination is not listed
  - a run merged with a red build says so and offers `land ... --yes`
  - a run whose supervisor died offers `cepa-until close-dead a/<run>`
  - with no run waiting, the section is not printed

Run with `python3 tests/test_cepa_plan_waiting_runs.py`.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"
FAILURES = []
RUN = "2026-11-20-0100"


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def run(repo, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN), *args],
                          capture_output=True, text=True, cwd=str(repo))


def pending(repo):
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "pending", "--json",
                        "--repo", str(repo)],
                       capture_output=True, text=True, cwd=str(repo))
    return json.loads(p.stdout)


def git(root, *args):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                           *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout.strip()


def repo_with_night(tmp):
    """A repo on `main` with queue `a` and a night branch one commit ahead."""
    root = Path(tmp) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main", ".")
    (root / "f.txt").write_text("base\n")
    git(root, "add", "f.txt")
    git(root, "commit", "-qm", "base")
    d = root / ".claude" / "queues" / "a"
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": "a",
            "source": "teste",
            "items": [{"id": "a1", "title": "item a1", "why": "porque",
                       "status": "done", "blocked_by": [],
                       "human_pending": None, "evidence": "feito"}]}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")
    git(root, "checkout", "-qb", f"until/{RUN}")
    (root / "f.txt").write_text("night\n")
    git(root, "commit", "-qam", "night work")
    git(root, "checkout", "-q", "main")
    return root


def write_state(root, **state):
    d = root / ".claude" / "queues" / "a" / "until"
    d.mkdir(parents=True, exist_ok=True)
    base = {"fila": "a", "run": RUN, "branch": f"until/{RUN}"}
    base.update(state)
    (d / f"{RUN}.estado.json").write_text(json.dumps(base), encoding="utf-8")


def runs_section(out):
    lines = out.splitlines()
    for i, l in enumerate(lines):
        if l.startswith("runs que esperam você"):
            return lines[i:]
    return None


LAND = {"estado": "esperando-dono",
        "acoes": [{"id": "aterrissar", "destino": "main"}]}


def red_test():
    print("CS-2: run da fila `a` esperando aterrissar")
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with_night(tmp)
        write_state(root, **LAND)
        listed = pending(root)["runs"]
        check("o próprio `cepa until pending` lista o run (fixture válida)",
              [(r["fila"], r["run"]) for r in listed] == [("a", RUN)], listed)
        p = run(root, "waiting")
        check("sai com 0", p.returncode == 0, p.stderr)
        sec = runs_section(p.stdout)
        check("imprime uma seção de runs", sec is not None, p.stdout)
        sec = sec or []
        check("a seção diz quantos runs", sec[:1] == ["runs que esperam você · 1"],
              sec)
        check("a seção traz a/<run> com `cepa-until land a/<run>`",
              any(f"a/{RUN}" in l and f"cepa-until land a/{RUN}" in l
                  and "espera aterrissar em `main`" in l for l in sec[1:]),
              p.stdout)
        check("a seção vem depois das filas",
              p.stdout.find("esperam você ·") < p.stdout.find("runs que esperam"),
              p.stdout)
        j = run(root, "waiting", "--json")
        data = json.loads(j.stdout)
        check("--json traz o run em `runs`",
              [(r["alvo"], r["comando"]) for r in data.get("runs", [])]
              == [(f"a/{RUN}", f"cepa-until land a/{RUN}")], j.stdout)


def landed_red_and_dead():
    print("run já aterrissado, build vermelho, supervisor morto, nenhum run")
    with tempfile.TemporaryDirectory() as tmp:
        root = repo_with_night(tmp)
        p = run(root, "waiting")
        check("sem run esperando, a seção não aparece",
              p.returncode == 0 and runs_section(p.stdout) is None, p.stdout)
        j = json.loads(run(root, "waiting", "--json").stdout)
        check("sem run esperando, --json traz `runs` vazio", j.get("runs") == [], j)

        write_state(root, estado="interrompido", sinal="SIGTERM")
        p = run(root, "waiting")
        sec = runs_section(p.stdout) or []
        check("supervisor morto: listado com `cepa-until close-dead a/<run>`",
              any(f"a/{RUN}" in l and "o supervisor morreu" in l
                  and f"cepa-until close-dead a/{RUN}" in l for l in sec),
              p.stdout)

        git(root, "merge", "-q", "--no-ff", "-m", "land", f"until/{RUN}")
        write_state(root, aterrissagem={"parou": "build-vermelho"}, **LAND)
        check("build vermelho: o `pending` também lista (fixture válida)",
              [r["build_vermelho"] for r in pending(root)["runs"]] == [True])
        p = run(root, "waiting")
        sec = runs_section(p.stdout) or []
        check("build vermelho: diz isso e oferece `land ... --yes`",
              any(f"a/{RUN}" in l and "build vermelho" in l
                  and f"cepa-until land a/{RUN} --yes" in l for l in sec),
              p.stdout)

        write_state(root, **LAND)
        check("já aterrissado: o `pending` não lista", pending(root)["runs"] == [])
        p = run(root, "waiting")
        check("já aterrissado: a seção não aparece",
              runs_section(p.stdout) is None, p.stdout)


if __name__ == "__main__":
    red_test()
    landed_red_and_dead()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
