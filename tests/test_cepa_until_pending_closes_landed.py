#!/usr/bin/env python3
"""`cepa-until pending` closes the run whose merge already reached the upstream
of the destination branch (spec docs/spec/pouso-ja-feito-sai-da-lista.md, CS-1).

Against the real CLI, in a temporary git repo with a remote:

  - CS-1 red test: run `a/r1` is `esperando-dono` with `aterrissagem.parou:
    build-vermelho` and its branch is inside `origin/main`; run `a/r2` is the
    same, but the merge is only in the local `main`. The `verify` of both
    writes a marker file. After `pending`: no waiting line for `a/r1`, its
    record says `aterrissado`, the marker is absent (no build ran), and the
    line "merged in `main` with a red build" is still there for `a/r2`.
  - the closed run leaves no `parou`/`motivo` behind and keeps the merge sha
  - a second `pending` changes nothing
  - a branch that got a commit after the merge stays listed (the tip counts,
    not the commit recorded in the action)
  - `--json` does not list the closed run either
  - in a repo whose destination has no upstream, the local branch counts
  - the closed record carries `destino`, `fechado_por: pending` and an
    `atualizado` equal to `quando` (fresh, not the fixture's old stamp)
  - CS-3: runs with `aterrissagem: null` or `parou: conflito` whose branch is
    in `origin/main` are closed and lose the branch; one only in local `main` is not
  - `pending` never fetches: a stale `origin/main` keeps the run listed

Run with `python3 tests/test_cepa_until_pending_closes_landed.py`.
"""
import json
import subprocess
import sys
import tempfile
from datetime import datetime
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
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "pending",
                           "--repo", str(root), *extra],
                          capture_output=True, text=True, cwd=str(root))
    # The `closed:` lines (CS-5) say what this call closed; these checks are
    # about the waiting lines, so they are dropped here.
    p.stdout = "".join(ln for ln in p.stdout.splitlines(True)
                       if not ln.startswith("closed:"))
    return p


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


def add_run(root, run, marker):
    """A run branch one commit ahead, merged into `main` (not pushed), and the
    state record of a run that stopped on a red build after that merge."""
    branch = f"until/{run}"
    git(root, "checkout", "-qb", branch)
    (root / f"{run}.txt").write_text("night\n")
    git(root, "add", f"{run}.txt")
    git(root, "commit", "-qm", f"work {run}")
    sha = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    git(root, "merge", "-q", "--no-ff", "-m", f"land {run}", branch)
    d = root / ".claude" / "queues" / "a" / "until"
    d.mkdir(parents=True, exist_ok=True)
    state_path(root, run).write_text(json.dumps({
        "fila": "a", "run": run, "branch": branch,
        "estado": "esperando-dono", "atualizado": OLD_STAMP,
        "verify": f"touch {marker}",
        "acoes": [{"id": "aterrissar", "destino": "main", "sha": sha}],
        "aterrissagem": {"parou": "build-vermelho", "motivo": "exit 1",
                         "merge": git(root, "rev-parse", "HEAD")},
    }), encoding="utf-8")
    return branch, sha


def red_test():
    print("CS-1: build vermelho com merge no upstream sai da lista")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        marker1, marker2 = Path(tmp) / "m1", Path(tmp) / "m2"
        add_run(root, "r1", marker1)
        git(root, "push", "-q", "origin", "main")          # r1 reaches origin/main
        add_run(root, "r2", marker2)                       # r2 stays local
        p = pending(root)
        check("`pending` sai 0", p.returncode == 0, p.stderr)
        check("nenhuma linha de espera para a/r1", "run r1" not in p.stdout,
              p.stdout)
        check("o registro de a/r1 vira `aterrissado`",
              read_state(root, "r1")["estado"] == "aterrissado",
              read_state(root, "r1"))
        check("nenhum build rodou (marcador ausente)",
              not marker1.exists() and not marker2.exists())
        check("a/r2 segue com a linha `merged in `main` with a red build`",
              "run r2" in p.stdout
              and "merged in `main` with a red build" in p.stdout, p.stdout)
        check("a/r2 segue `esperando-dono`",
              read_state(root, "r2")["estado"] == "esperando-dono")

        info = read_state(root, "r1")["aterrissagem"]
        check("o run fechado não guarda `parou` nem `motivo`",
              "parou" not in info and "motivo" not in info, info)
        check("...e guarda o merge e a hora do fechamento",
              info.get("merge") and info.get("quando"), info)

        check("...com `destino` = `main`", info.get("destino") == "main", info)
        check("...e `fechado_por` = `pending`",
              info.get("fechado_por") == "pending", info)
        top = read_state(root, "r1").get("atualizado")
        check("`atualizado` iguala `aterrissagem.quando`",
              top == info.get("quando"), (top, info))
        check("...difere do valor antigo da fixture", top != OLD_STAMP, top)
        try:
            age = abs((datetime.now() - datetime.fromisoformat(top)).total_seconds())
        except (TypeError, ValueError):
            age = None
        check("...e e um ISO recente", age is not None and age < 300, top)

        p2 = pending(root)
        check("segunda chamada: a/r2 ainda listada, a/r1 não",
              "run r2" in p2.stdout and "run r1" not in p2.stdout, p2.stdout)
        j = json.loads(pending(root, "--json").stdout)
        check("--json lista só a/r2",
              [(r["fila"], r["run"]) for r in j["runs"]] == [("a", "r2")], j)


def tip_after_merge():
    print("commit no branch depois do merge mantém o run na lista")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        marker = Path(tmp) / "m"
        branch, _ = add_run(root, "r1", marker)
        git(root, "push", "-q", "origin", "main")
        git(root, "checkout", "-q", branch)
        (root / "late.txt").write_text("late\n")
        git(root, "add", "late.txt")
        git(root, "commit", "-qm", "late work")
        git(root, "checkout", "-q", "main")
        p = pending(root)
        check("o run segue listado e `esperando-dono`",
              "run r1" in p.stdout
              and read_state(root, "r1")["estado"] == "esperando-dono",
              p.stdout)
        check("sem build", not marker.exists())


def no_upstream():
    print("repo sem upstream: vale o branch local")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp, remote=False)
        marker = Path(tmp) / "m"
        add_run(root, "r1", marker)
        p = pending(root)
        check("fechado pelo branch local",
              "run r1" not in p.stdout
              and read_state(root, "r1")["estado"] == "aterrissado", p.stdout)
        check("sem build", not marker.exists())


def not_through_land():
    print("CS-3: run que nunca passou por `land` ate o fim, com branch no upstream, fecha")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        marker = Path(tmp) / "m"
        b1, _ = add_run(root, "r1", marker)
        b2, _ = add_run(root, "r2", marker)
        git(root, "push", "-q", "origin", "main")   # both merges in origin/main
        git(root, "reset", "-q", "--hard", "HEAD~2")  # local main behind upstream
        st = read_state(root, "r1")
        st["aterrissagem"] = None
        state_path(root, "r1").write_text(json.dumps(st), encoding="utf-8")
        st = read_state(root, "r2")
        st["aterrissagem"] = {"parou": "conflito", "motivo": "f.txt"}
        state_path(root, "r2").write_text(json.dumps(st), encoding="utf-8")
        b3, _ = add_run(root, "r3", marker)   # merged only in local main
        st = read_state(root, "r3")
        st["aterrissagem"] = None
        state_path(root, "r3").write_text(json.dumps(st), encoding="utf-8")
        p = pending(root)
        check("`pending` sai 0", p.returncode == 0, p.stderr)
        for run, branch in (("r1", b1), ("r2", b2)):
            check(f"a/{run} vira `aterrissado`",
                  read_state(root, run)["estado"] == "aterrissado",
                  read_state(root, run))
            check(f"a/{run} perde o branch",
                  not git(root, "branch", "--list", branch))
            check(f"a/{run} some da lista", f"run {run}" not in p.stdout,
                  p.stdout)
        info = read_state(root, "r2")["aterrissagem"]
        check("o `conflito` nao fica no registro fechado",
              "parou" not in info and "motivo" not in info, info)
        check("cerca: a/r3 (so no main local, sem `parou`) segue como estava",
              read_state(root, "r3")["estado"] == "esperando-dono"
              and git(root, "branch", "--list", b3), read_state(root, "r3"))
        check("cerca: a/r3 nao aparece na lista (nao espera por `land`)",
              "run r3" not in p.stdout, p.stdout)
        check("sem build", not marker.exists())


def merged_local_and_upstream():
    print("CS-3: merge no main local E no origin/main, sem `parou` de build, fecha")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        marker = Path(tmp) / "m"
        b1, _ = add_run(root, "r1", marker)
        b2, _ = add_run(root, "r2", marker)
        git(root, "push", "-q", "origin", "main")   # local main == origin/main
        st = read_state(root, "r1")
        st["aterrissagem"] = None
        state_path(root, "r1").write_text(json.dumps(st), encoding="utf-8")
        st = read_state(root, "r2")
        st["aterrissagem"] = {"parou": "conflito", "motivo": "f.txt"}
        state_path(root, "r2").write_text(json.dumps(st), encoding="utf-8")
        p = pending(root)
        check("`pending` sai 0", p.returncode == 0, p.stderr)
        for run, branch in (("r1", b1), ("r2", b2)):
            check(f"a/{run} vira `aterrissado`",
                  read_state(root, run)["estado"] == "aterrissado",
                  read_state(root, run))
            check(f"a/{run} perde o branch",
                  not git(root, "branch", "--list", branch))
            check(f"a/{run} some da lista", f"run {run}" not in p.stdout,
                  p.stdout)


def unmerged_run_stays():
    print("run que nao esta mergeado em lugar nenhum segue esperando e listado")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        marker = Path(tmp) / "m"
        branch = "until/r1"
        git(root, "checkout", "-qb", branch)
        (root / "r1.txt").write_text("night\n")
        git(root, "add", "r1.txt")
        git(root, "commit", "-qm", "work r1")
        sha = git(root, "rev-parse", "HEAD")
        git(root, "checkout", "-q", "main")
        d = root / ".claude" / "queues" / "a" / "until"
        d.mkdir(parents=True, exist_ok=True)
        state_path(root, "r1").write_text(json.dumps({
            "fila": "a", "run": "r1", "branch": branch,
            "estado": "esperando-dono", "atualizado": OLD_STAMP,
            "verify": f"touch {marker}",
            "acoes": [{"id": "aterrissar", "destino": "main", "sha": sha}],
            "aterrissagem": None,
        }), encoding="utf-8")
        p = pending(root)
        check("`pending` sai 0", p.returncode == 0, p.stderr)
        check("a/r1 segue `esperando-dono`",
              read_state(root, "r1")["estado"] == "esperando-dono",
              read_state(root, "r1"))
        check("a/r1 mantem o branch", git(root, "branch", "--list", branch))
        check("a/r1 aparece na lista com a linha `waits to land`",
              "run r1" in p.stdout and "waits to land" in p.stdout, p.stdout)
        check("sem build", not marker.exists())


def no_fetch():
    print("`pending` nao faz fetch: origin/main velho mantem o run listado")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        marker = Path(tmp) / "m"
        branch, _ = add_run(root, "r1", marker)
        git(root, "push", "-q", "origin", branch)
        second = Path(tmp) / "second"
        subprocess.run(["git", "clone", "-q", str(Path(tmp) / "origin.git"),
                        str(second)], check=True, capture_output=True)
        git(second, "merge", "-q", "--no-ff", "-m", "remote merge",
            f"origin/{branch}")
        git(second, "push", "-q", "origin", "main")
        before = git(root, "rev-parse", "refs/remotes/origin/main")
        p = pending(root)
        after = git(root, "rev-parse", "refs/remotes/origin/main")
        check("o run segue listado", "run r1" in p.stdout, p.stdout)
        check("...e `esperando-dono`",
              read_state(root, "r1")["estado"] == "esperando-dono")
        check("`refs/remotes/origin/main` intacto", before == after,
              (before, after))
        check("sem build", not marker.exists())


if __name__ == "__main__":
    not_through_land()
    merged_local_and_upstream()
    unmerged_run_stays()
    no_fetch()
    red_test()
    tip_after_merge()
    no_upstream()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
