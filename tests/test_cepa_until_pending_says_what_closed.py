#!/usr/bin/env python3
"""`cepa-until pending` says what it closed, one line per run, apart from the
waiting lines (spec docs/spec/pouso-ja-feito-sai-da-lista.md, CS-5).

Against the real CLI, in a temporary git repo with a remote, with the runs of
CS-1 (`a/r1` landed with red-build marks, `a/r2` merged only locally) and of CS-4
(`a/r3` branchless and landed, `a/r4` branchless and never landed):

  - the text output has a line STARTING with `closed:` for `a/r1`, `a/r3` (landed)
    and `a/r4` (discarded), each with queue and run
  - `a/r2` stays waiting: its line does not start with `closed:`, and the closed
    runs produce no waiting line
  - `--json` carries `fechados` with the three (fila, run, resultado); `runs` and
    `mortos` keep their shape
  - a second call prints no `closed:` line and its `fechados` is empty

Run with `python3 tests/test_cepa_until_pending_says_what_closed.py`.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"
FAILURES = []
OLD_STAMP = "2020-01-02T03:04:05"


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def git(root, *args):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                           *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout.strip()


def pending(root, *extra):
    return subprocess.run([sys.executable, str(CEPA_UNTIL), "pending",
                           "--repo", str(root), *extra],
                          capture_output=True, text=True, cwd=str(root))


def state_path(root, run):
    return root / ".claude" / "queues" / "a" / "until" / f"{run}.estado.json"


def make_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main", ".")
    (root / "f.txt").write_text("base\n")
    git(root, "add", "f.txt")
    git(root, "commit", "-qm", "base")
    bare = Path(tmp) / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-q", "-u", "origin", "main")
    return root


def add_run(root, run, keep_branch, merged=True, aterrissagem=None):
    """A run commit on `until/<run>`, merged into `main` (or not), the branch kept
    or deleted, and the `esperando-dono` record with the commit in `aterrissar`."""
    branch = f"until/{run}"
    git(root, "checkout", "-qb", branch)
    (root / f"{run}.txt").write_text("night\n")
    git(root, "add", f"{run}.txt")
    git(root, "commit", "-qm", f"work {run}")
    sha = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    if merged:
        git(root, "merge", "-q", "--no-ff", "-m", f"land {run}", branch)
    if not keep_branch:
        git(root, "branch", "-D", branch)
    d = root / ".claude" / "queues" / "a" / "until"
    d.mkdir(parents=True, exist_ok=True)
    state_path(root, run).write_text(json.dumps({
        "fila": "a", "run": run, "branch": branch,
        "estado": "esperando-dono", "atualizado": OLD_STAMP,
        "acoes": [{"id": "aterrissar", "destino": "main", "sha": sha}],
        "aterrissagem": aterrissagem,
    }), encoding="utf-8")


def fixture(tmp):
    root = make_repo(tmp)
    red = {"parou": "build-vermelho", "motivo": "exit 1"}
    add_run(root, "r1", keep_branch=True, aterrissagem=red)
    add_run(root, "r3", keep_branch=False)
    git(root, "push", "-q", "origin", "main")      # r1 and r3 reach origin/main
    add_run(root, "r2", keep_branch=True, aterrissagem=red)   # local only
    add_run(root, "r4", keep_branch=False, merged=False)      # never landed
    return root


def closed_lines(out):
    return [ln for ln in out.splitlines() if ln.startswith("closed:")]


def red_test():
    print("CS-5: `pending` diz o que fechou, uma linha por run")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        p = pending(root)
        check("`pending` sai 0", p.returncode == 0, p.stderr)
        lines = closed_lines(p.stdout)
        check("tres linhas `closed:`", len(lines) == 3, p.stdout)
        for run, outcome in (("r1", "landed"), ("r3", "landed"), ("r4", "discarded")):
            mine = [ln for ln in lines if f"run {run}" in ln]
            check(f"a/{run}: uma linha `closed:`", len(mine) == 1, p.stdout)
            ln = mine[0] if mine else ""
            check(f"a/{run}: linha traz fila `a`, run e `{outcome}`",
                  "queue a" in ln and f"run {run}" in ln
                  and ln.rstrip().endswith(outcome), ln)
        check("a/r2 segue esperando, sem `closed:`",
              not any("run r2" in ln for ln in lines)
              and any("run r2" in ln and not ln.startswith("closed:")
                      for ln in p.stdout.splitlines()), p.stdout)
        waiting = [ln for ln in p.stdout.splitlines() if not ln.startswith("closed:")]
        check("run fechado nao gera linha de espera",
              not any(f"run {r}" in ln for ln in waiting for r in ("r1", "r3", "r4")),
              p.stdout)
        second = pending(root)
        check("segunda chamada sem `closed:`", not closed_lines(second.stdout),
              second.stdout)
        check("segunda chamada ainda lista a/r2", "run r2" in second.stdout)


def json_test():
    print("--json traz `fechados`; `runs` e `mortos` mantem a forma")
    with tempfile.TemporaryDirectory() as tmp:
        root = fixture(tmp)
        j = json.loads(pending(root, "--json").stdout)
        check("chaves `runs`, `mortos` e `fechados`",
              {"runs", "mortos", "fechados"} <= set(j), list(j))
        got = {(e.get("fila"), e.get("run")): e.get("resultado")
               for e in j.get("fechados") or []}
        check("`fechados` tem os tres, com resultado",
              got == {("a", "r1"): "landed", ("a", "r3"): "landed",
                      ("a", "r4"): "discarded"}, j.get("fechados"))
        check("`runs` e so a/r2, com a forma de sempre",
              [r.get("run") for r in j["runs"]] == ["r2"]
              and {"fila", "run", "branch", "destino", "fica_com_voce",
                   "build_vermelho", "comando"} == set(j["runs"][0]), j["runs"])
        check("`mortos` vazio", j["mortos"] == [], j["mortos"])
        j2 = json.loads(pending(root, "--json").stdout)
        check("segunda chamada: `fechados` vazio", j2.get("fechados") == [], j2)
        check("segunda chamada: `runs` igual", j2["runs"] == j["runs"])


if __name__ == "__main__":
    red_test()
    json_test()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
