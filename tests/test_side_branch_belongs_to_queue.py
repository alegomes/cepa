#!/usr/bin/env python3
"""A `cepa-until` side branch belongs to the queue whose run made it, not to
every queue that has an item with the same id (fb-20261120-2, fb-20261120-3).

Queues reuse ids (`CS-1`, `CS-6`). On 2026-11-20 the run `2026-11-20-1609` of
the queue `pyyaml` deleted at its start three side branches of OTHER queues,
because `clean_side_branches` only asked "is CS-6 done in pyyaml?". And
`cepa-plan status` of a queue just born listed the red branches of two other
queues as "código fora do main". The run in the branch name is the link: each
run writes `.claude/queues/<queue>/until/<run>.jsonl`.

  1. `_queuepath.side_branch_item`: own run -> id; another queue's run -> None;
     a `--all` run (ledger in `_all`) -> id only when the name carries the
     queue; two queues with a run in the same minute -> the ledger has to
     name the branch; a branch that is not a side branch -> None.
  2. `clean_side_branches` of queue A deletes A's side branch of a `done` item
     and keeps B's side branch whose id is also `done` in A.
  3. `cepa-plan status` of queue A does not list B's side branch with the same
     id as A's code outside main, and still lists A's own.

Against the real code, in a temporary git repo. Run with
`python3 tests/test_side_branch_belongs_to_queue.py`.
"""
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _queuepath as qp  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def ledger(root, queue, run, text=""):
    d = root / ".claude" / "queues" / queue / "until"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{run}.jsonl").write_text(text, encoding="utf-8")


def write_queue(root, queue, items):
    d = root / ".claude" / "queues" / queue
    d.mkdir(parents=True, exist_ok=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": queue,
            "source": "teste", "items": items}
    path = d / "queue.yaml"
    path.write_text(yaml.safe_dump(plan, allow_unicode=True), encoding="utf-8")
    return path


def new_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main", ".")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    (root / ".gitignore").write_text(".claude/\n", encoding="utf-8")
    git(root, "add", ".gitignore")
    git(root, "commit", "-q", "-m", "base")
    return root


def side_branch(root, branch, name):
    git(root, "checkout", "-q", "-b", branch, "main")
    (root / name).write_text(name, encoding="utf-8")
    git(root, "add", name)
    git(root, "commit", "-q", "-m", name)
    git(root, "checkout", "-q", "main")


def branches(root):
    return git(root, "for-each-ref", "--format=%(refname:short)",
               "refs/heads/until/").splitlines()


def item_rule():
    print("side_branch_item: the run in the name says the queue")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ledger(root, "pyyaml", "2026-11-20-1609")
        ledger(root, "campo-de-resposta", "2026-11-14-0953")
        ledger(root, "_all", "2026-11-16-1426")
        b_other = "until/2026-11-14-0953-vermelho-CS-6"
        check("another queue's run is not this queue's",
              qp.side_branch_item(root, "pyyaml", b_other) is None)
        check("the queue whose run made it gets the id",
              qp.side_branch_item(root, "campo-de-resposta", b_other) == "CS-6")
        check("-v<n> of a 2nd red return is the same item",
              qp.side_branch_item(root, "pyyaml",
                                  "until/2026-11-20-1609-vermelho-CS-6-v2") == "CS-6")
        check("parado and travado count too",
              qp.side_branch_item(root, "pyyaml", "until/2026-11-20-1609-parado-CS-1")
              == "CS-1"
              and qp.side_branch_item(root, "pyyaml",
                                      "until/2026-11-20-1609-travado-CS-1") == "CS-1")
        b_all = "until/2026-11-16-1426-vermelho-registro-de-plugins-CS-10"
        check("a --all run's branch belongs to the queue in its name",
              qp.side_branch_item(root, "registro-de-plugins", b_all) == "CS-10")
        check("a --all run's branch is not another queue's",
              qp.side_branch_item(root, "pyyaml", b_all) is None)
        check("a run with no ledger anywhere belongs to no queue",
              qp.side_branch_item(root, "pyyaml",
                                  "until/2026-01-01-0000-vermelho-CS-6") is None)
        check("a branch that is not a side branch is None",
              qp.side_branch_item(root, "pyyaml", "until/2026-11-20-1609") is None
              and qp.side_branch_item(root, "pyyaml", "feat/CS-6") is None)
        # Two queues started a run in the same minute: the ledger decides.
        b = "until/2026-11-21-0900-vermelho-CS-2"
        ledger(root, "pyyaml", "2026-11-21-0900",
               json.dumps({"evento": "volta_vermelha", "lateral": b}) + "\n")
        ledger(root, "campo-de-resposta", "2026-11-21-0900", "")
        check("same-minute runs: the queue whose ledger names the branch",
              qp.side_branch_item(root, "pyyaml", b) == "CS-2")
        check("same-minute runs: the other queue does not get it",
              qp.side_branch_item(root, "campo-de-resposta", b) is None)


def load_until():
    loader = importlib.machinery.SourceFileLoader("cepa_until_under_test", str(CEPA_UNTIL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def clean_checks():
    print("clean_side_branches: only the run's own queue's branches go")
    until = load_until()
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        plan = write_queue(root, "pyyaml", [
            {"id": "CS-6", "title": "x", "why": "y", "status": "done"},
            {"id": "CS-1", "title": "x", "why": "y", "status": "done"}])
        write_queue(root, "campo-de-resposta", [
            {"id": "CS-6", "title": "x", "why": "y", "status": "pending"}])
        ledger(root, "pyyaml", "2026-11-19-1000")
        ledger(root, "campo-de-resposta", "2026-11-14-0953")
        own = "until/2026-11-19-1000-vermelho-CS-6"
        other = "until/2026-11-14-0953-vermelho-CS-6"
        unknown = "until/2026-11-18-1731-vermelho-CS-1"   # no ledger here
        for i, b in enumerate((own, other, unknown)):
            side_branch(root, b, f"f{i}.txt")
        dest = root / ".claude" / "queues" / "pyyaml" / "until" / "run.laterais"
        result = until.clean_side_branches(root, "pyyaml", plan, dest, "main")
        left = branches(root)
        check("the queue's own side branch of a done item is deleted",
              own not in left, left)
        check("its patch is saved in the queue's folder",
              (dest / (own[len("until/"):] + ".patch")).is_file())
        check("another queue's side branch with a done id here survives",
              other in left, left)
        check("a side branch of a run with no ledger in this queue survives",
              unknown in left, left)
        check("only the own branch is reported", [r[0] for r in result] == [own],
              result)


def status_checks():
    print("cepa-plan status: another queue's side branch is not this item's code")
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "until-arvore-limpa", [
            {"id": "CS-1", "title": "x", "why": "y", "status": "pending"},
            {"id": "CS-3", "title": "x", "why": "y", "status": "pending"}])
        ledger(root, "perguntar-antes-do-run", "2026-11-10-1650")
        ledger(root, "until-arvore-limpa", "2026-11-21-1000")
        side_branch(root, "until/2026-11-10-1650-vermelho-CS-1", "a.txt")
        side_branch(root, "until/2026-11-21-1000-vermelho-CS-3", "b.txt")
        env = {"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
               "HOME": str(root), "NO_COLOR": "1"}
        p = subprocess.run([sys.executable, str(CEPA_PLAN), "status",
                            "until-arvore-limpa", "--json", "--repo", str(root)],
                           capture_output=True, text=True, cwd=str(root), env=env)
        check("status runs", p.returncode == 0, p.stderr)
        try:
            data = json.loads(p.stdout)
        except ValueError:
            check("status prints JSON", False, p.stdout[:300])
            return
        items = {i["id"]: i for i in data.get("items") or []}
        cs1 = (items.get("CS-1") or {}).get("codigo")
        cs3 = (items.get("CS-3") or {}).get("codigo")
        check("CS-1 does not take the other queue's red branch",
              not cs1 or not any("CS-1" in f for f in cs1.get("fora") or []), cs1)
        check("CS-3 still lists its own run's red branch",
              bool(cs3) and any("vermelho-CS-3" in f for f in cs3["fora"]), cs3)


def main():
    item_rule()
    clean_checks()
    status_checks()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\ntudo ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
