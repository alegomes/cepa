#!/usr/bin/env python3
"""Regression tests for maestro/bin/maestro-programs.

Run with `python3 tests/test_maestro_programs.py` (no third-party deps beyond
the PyYAML the script itself needs). Exits non-zero on first failure.

What these tests hold is the reason the script exists: it answers "what can
be run here?" and that answer is only worth anything if it MATCHES the refusal of
/maestro:run. A lister that says RUNS about a single-track plan (or about a
plan without schema_version) is worse than no lister — it sends the user to a
refusal he could already have seen. Hence cases 2-5 are all refusals.

Case 6 holds the seam invariant: called from inside a linked
worktree, the script has to see the programs of the MAIN CLONE — the same
root /maestro:run uses. If they diverge, the listing shows a program that the
execution does not find (or hides what it would find).
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "maestro" / "bin" / "maestro-programs"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo)] + list(args),
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {args} failed: {r.stderr}")
    return r


def run(repo, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), str(repo)] + list(extra),
                          capture_output=True, text=True)


def as_json(repo):
    r = run(repo, "--json")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    return {p["nome"]: p for p in data["programas"]}, data["raiz"]


def write_program(repo, name, text):
    d = Path(repo) / ".claude" / "programs" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "plan.yaml").write_text(text)
    return d


PENDING_WAVES = """\
schema_version: 2
mode: parallel-waves
program: com-onda
waves:
  - id: 1
    slices: [S1, S2]
    status: pending
  - id: 2
    slices: [S3]
    status: pending
"""

ALL_DONE = """\
schema_version: 2
mode: parallel-waves
program: acabado
waves:
  - id: 1
    slices: [S1]
    status: done
"""

SINGLE_TRACK = """\
schema_version: 2
mode: single-track
program: fila
items:
  - id: ITEM-1
    title: primeiro
    status: done
  - id: ITEM-2
    title: segundo
    status: pending
"""

NO_SCHEMA = """\
program: legado-sem-versao
waves:
  - id: 1
    slices: [S1]
    status: pending
"""


def fixture_repo(base):
    repo = Path(base) / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "README.md").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "seed")
    return repo


def test_eligible_points_to_the_next_wave(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "com-onda", PENDING_WAVES)
    progs, _ = as_json(repo)
    p = progs["com-onda"]
    check("plano com onda pendente é elegível", p["elegivel"], p["motivo"])
    check("aponta a PRIMEIRA onda pendente",
          p["proxima_onda"] and p["proxima_onda"]["id"] == 1, p["proxima_onda"])
    output = run(repo).stdout
    check("saída humana traz a linha de comando pronta",
          "/maestro:run com-onda --wave 1" in output, output)


def test_waves_all_done_does_not_run(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "acabado", ALL_DONE)
    progs, _ = as_json(repo)
    p = progs["acabado"]
    check("programa acabado não é elegível", not p["elegivel"])
    check("motivo diz que as ondas acabaram", "done" in (p["motivo"] or ""), p["motivo"])


def test_single_track_refused_with_the_right_route(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "fila", SINGLE_TRACK)
    progs, _ = as_json(repo)
    p = progs["fila"]
    check("single-track não é elegível (igual ao /maestro:run)", not p["elegivel"])
    check("motivo nomeia /common:next", "/common:next" in (p["motivo"] or ""), p["motivo"])
    check("motivo nomeia o próximo item pendente",
          "ITEM-2" in (p["motivo"] or ""), p["motivo"])


def test_without_schema_version_refuses_like_run(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "legado", NO_SCHEMA)
    progs, _ = as_json(repo)
    p = progs["legado"]
    check("plano sem schema_version não é elegível", not p["elegivel"])
    check("motivo cita schema_version", "schema_version" in (p["motivo"] or ""), p["motivo"])


def test_directory_without_plan_shows_up_as_such(tmp):
    repo = fixture_repo(tmp)
    (Path(repo) / ".claude" / "programs" / "vazio").mkdir(parents=True)
    progs, _ = as_json(repo)
    p = progs["vazio"]
    check("diretório sem plan.yaml não é elegível", not p["elegivel"])
    check("motivo é 'sem plan.yaml'", p["motivo"] == "sem plan.yaml", p["motivo"])


def test_from_inside_the_worktree_reads_the_main_clone(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "com-onda", PENDING_WAVES)
    wt = Path(tmp) / "wt"
    git(repo, "worktree", "add", "-q", "-b", "session/x", str(wt))
    progs, root = as_json(wt)
    check("worktree ligada enxerga o programa do clone principal",
          "com-onda" in progs, list(progs))
    check("a raiz reportada é a do clone principal",
          Path(root).resolve() == repo.resolve(), root)


def test_outside_git_repo_exits_2(tmp):
    outside = Path(tmp) / "nao-repo"
    outside.mkdir()
    r = run(outside)
    check("diretório sem git sai com 2", r.returncode == 2, r.returncode)
    check("e diz por quê", "git" in r.stderr, r.stderr)


def test_check_name_refuses_board_queue(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "WEGO", SINGLE_TRACK)
    r = run(repo, "--check-name", "WEGO")
    check("nome ocupado por fila single-track sai com 3", r.returncode == 3, r.returncode)
    check("a mensagem diz que a fila é do board",
          "single-track" in r.stderr and "COLIS" in r.stderr, r.stderr)
    check("e nomeia quem escreveu aquilo",
          "/board-flow:triage" in r.stderr, r.stderr)


def test_check_name_releases_replanning_its_own_waves(tmp):
    repo = fixture_repo(tmp)
    write_program(repo, "com-onda", PENDING_WAVES)
    r = run(repo, "--check-name", "com-onda")
    check("reescrever plano de ondas é liberado", r.returncode == 0, r.stderr)
    check("mas avisa que o nome está ocupado",
          "ocupado" in r.stdout, r.stdout)


def test_check_name_releases_new_name(tmp):
    repo = fixture_repo(tmp)
    r = run(repo, "--check-name", "ainda-nao-existe")
    check("nome inédito é livre", r.returncode == 0, r.stderr)
    check("e diz que o caminho não existe", "livre" in r.stdout, r.stdout)


def test_program_plan_calls_the_check_before_writing(tmp):
    """Prompt contract: step 4 of /maestro:program-plan has to run the
    check BEFORE the write. Without this the script exists and nobody calls it.
    """
    cmd = (REPO / "maestro" / "commands" / "program-plan.md").read_text()
    check("o passo 4 chama --check-name", "--check-name" in cmd)
    check("e trata o exit 3 como parada", "Exit 3 = stop" in cmd)
    i_check = cmd.find("--check-name")
    i_write = cmd.find("write the plan to\n   `<main-root>/.claude/programs/")
    check("a checagem vem antes da escrita",
          i_check != -1 and i_write != -1 and i_check < i_write,
          f"check={i_check} write={i_write}")


def main():
    tests = [test_eligible_points_to_the_next_wave,
             test_waves_all_done_does_not_run,
             test_single_track_refused_with_the_right_route,
             test_without_schema_version_refuses_like_run,
             test_directory_without_plan_shows_up_as_such,
             test_from_inside_the_worktree_reads_the_main_clone,
             test_outside_git_repo_exits_2,
             test_check_name_refuses_board_queue,
             test_check_name_releases_replanning_its_own_waves,
             test_check_name_releases_new_name,
             test_program_plan_calls_the_check_before_writing]
    for t in tests:
        print(t.__name__)
        with tempfile.TemporaryDirectory() as d:
            t(d)
    if FAILURES:
        print(f"\n{len(FAILURES)} failing: {', '.join(FAILURES)}")
        return 1
    print("\nall green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
