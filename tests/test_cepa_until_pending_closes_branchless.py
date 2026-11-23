#!/usr/bin/env python3
"""`cepa-until pending` closes the `esperando-dono` record whose branch is gone, by
the commit recorded in its `aterrissar` action (spec
docs/spec/pouso-ja-feito-sai-da-lista.md, CS-4).

Against the real CLI, in a temporary git repo with a remote:

  - CS-4 red test: runs `a/r3` and `a/r4` are `esperando-dono` and their branch was
    deleted. The commit recorded in the `aterrissar` action of `a/r3` is in
    `origin/main`, the one of `a/r4` is not. After `pending`: `a/r3` is
    `aterrissado` and `a/r4` is `descartado`.
  - neither closed record is listed, and a second `pending` changes nothing
  - a commit merged only in the local `main` (not yet pushed) stays `esperando-dono`, untouched
  - no upstream (no remote): the local `main` decides
  - a record without a recorded commit, with a commit object that is not in the
    repo, or with a destination branch that does not exist is left as it is
  - a run whose branch still exists keeps the CS-1..CS-3 path (tip, not the
    recorded commit)

Run with `python3 tests/test_cepa_until_pending_closes_branchless.py`.
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


def read_state(root, run):
    return json.loads(state_path(root, run).read_text(encoding="utf-8"))


def make_repo(tmp, remote=True):
    root = Path(tmp) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main", ".")
    (root / "f.txt").write_text("base\n")
    git(root, "add", "f.txt")
    git(root, "commit", "-qm", "base")
    if remote:
        bare = Path(tmp) / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        git(root, "remote", "add", "origin", str(bare))
        git(root, "push", "-q", "-u", "origin", "main")
    return root


def add_branchless(root, run, merged, destino="main", action_extra=None):
    """A run commit (merged into `main` or not), its branch deleted, and the
    record of a run left `esperando-dono` with that commit in `aterrissar`."""
    branch = f"until/{run}"
    git(root, "checkout", "-qb", branch)
    (root / f"{run}.txt").write_text("night\n")
    git(root, "add", f"{run}.txt")
    git(root, "commit", "-qm", f"work {run}")
    sha = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    if merged:
        git(root, "merge", "-q", "--no-ff", "-m", f"land {run}", branch)
    git(root, "branch", "-D", branch)
    action = {"id": "aterrissar", "destino": destino, "sha": sha}
    action.update(action_extra or {})
    d = root / ".claude" / "queues" / "a" / "until"
    d.mkdir(parents=True, exist_ok=True)
    state_path(root, run).write_text(json.dumps({
        "fila": "a", "run": run, "branch": branch,
        "estado": "esperando-dono", "atualizado": OLD_STAMP,
        "acoes": [action], "aterrissagem": None,
    }), encoding="utf-8")
    return sha


def red_test():
    print("CS-4: registro sem branch fecha pelo commit gravado")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_branchless(root, "r3", merged=True)
        git(root, "push", "-q", "origin", "main")     # r3's commit reaches origin/main
        add_branchless(root, "r4", merged=False)      # r4's commit is nowhere
        p = pending(root)
        check("`pending` sai 0", p.returncode == 0, p.stderr)
        check("a/r3 vira `aterrissado`",
              read_state(root, "r3")["estado"] == "aterrissado", read_state(root, "r3"))
        check("a/r4 vira `descartado`",
              read_state(root, "r4")["estado"] == "descartado", read_state(root, "r4"))
        check("nenhum dos dois na lista",
              "run r3" not in p.stdout and "run r4" not in p.stdout, p.stdout)
        info = read_state(root, "r3")["aterrissagem"] or {}
        check("a/r3 guarda destino, `fechado_por` e hora",
              info.get("destino") == "main" and info.get("fechado_por") == "pending"
              and info.get("quando"), info)
        check("`atualizado` e novo nos dois",
              read_state(root, "r3")["atualizado"] != OLD_STAMP
              and read_state(root, "r4")["atualizado"] != OLD_STAMP)
        before = (read_state(root, "r3"), read_state(root, "r4"))
        pending(root)
        check("segunda chamada nao muda nada",
              before == (read_state(root, "r3"), read_state(root, "r4")))
        j = json.loads(pending(root, "--json").stdout)
        check("--json nao lista nenhum", j["runs"] == [], j)


def merged_only_local():
    print("commit so no main local (sem push): segue esperando-dono, intacto")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_branchless(root, "r4", merged=True)       # not pushed
        before = state_path(root, "r4").read_bytes()
        pending(root)
        check("a/r4 segue `esperando-dono`",
              read_state(root, "r4")["estado"] == "esperando-dono", read_state(root, "r4"))
        check("a/r4 intacto em disco", state_path(root, "r4").read_bytes() == before)


def no_upstream():
    print("repo sem upstream: vale o main local")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp, remote=False)
        add_branchless(root, "r3", merged=True)
        add_branchless(root, "r4", merged=False)
        pending(root)
        check("a/r3 `aterrissado`", read_state(root, "r3")["estado"] == "aterrissado")
        check("a/r4 `descartado`", read_state(root, "r4")["estado"] == "descartado")


def undecidable():
    print("sem commit gravado, commit sumido ou destino inexistente: fica como esta")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        add_branchless(root, "r5", merged=False)
        st = read_state(root, "r5")
        del st["acoes"][0]["sha"]
        state_path(root, "r5").write_text(json.dumps(st), encoding="utf-8")
        add_branchless(root, "r6", merged=False)
        st = read_state(root, "r6")
        st["acoes"][0]["sha"] = "1" * 40            # object not in the repo
        state_path(root, "r6").write_text(json.dumps(st), encoding="utf-8")
        add_branchless(root, "r7", merged=False, destino="nao-existe")
        add_branchless(root, "r8", merged=False)
        st = read_state(root, "r8")
        st["acoes"] = []                            # no `aterrissar` action
        state_path(root, "r8").write_text(json.dumps(st), encoding="utf-8")
        p = pending(root)
        check("`pending` sai 0", p.returncode == 0, p.stderr)
        for run in ("r5", "r6", "r7", "r8"):
            check(f"a/{run} segue `esperando-dono`",
                  read_state(root, run)["estado"] == "esperando-dono",
                  read_state(root, run))


def branch_exists_unchanged():
    print("com o branch vivo vale a ponta do branch, nao o commit gravado")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        sha = add_branchless(root, "r1", merged=True)
        git(root, "push", "-q", "origin", "main")
        git(root, "branch", "until/r1", sha)
        git(root, "checkout", "-q", "until/r1")
        (root / "late.txt").write_text("late\n")
        git(root, "add", "late.txt")
        git(root, "commit", "-qm", "late")
        git(root, "checkout", "-q", "main")
        p = pending(root)
        check("a/r1 segue `esperando-dono` e listado",
              read_state(root, "r1")["estado"] == "esperando-dono"
              and "run r1" in p.stdout, p.stdout)


if __name__ == "__main__":
    red_test()
    merged_only_local()
    no_upstream()
    undecidable()
    branch_exists_unchanged()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
