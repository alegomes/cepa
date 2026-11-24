#!/usr/bin/env python3
"""CS-1 of docs/spec/filas-fechadas-saem-da-vista.md: `cepa-plan archive` moves
the closed queue that has been still for 7 days, and only that one.

Red test declared in the spec: in a fixture repo with the queue `velha` (every
item `done`, last commit 8 days ago, with `until/r1.jsonl`), `recente` (every
item `done`, last commit 6 days ago) and `aberta` (one `pending` item),
`cepa-plan archive` exits 0; afterwards
`.claude/queues/_archive/velha/queue.yaml` and
`.claude/queues/_archive/velha/until/r1.jsonl` exist, `.claude/queues/velha/`
does not, and `recente` and `aberta` stay in place. With `--dry-run` the output
names `velha` and nothing moves.

Also covered here: the 7-day boundary (exactly 7 days is archived), a
`done`+`dropped` mix, a name already taken in `_archive` (that queue stays, the
sweep goes on), a queue with no commit (no measurable age), waves plans and the
legacy `.claude/programs/` layout untouched, and the commit: by hand the
command commits only what it moved; `--no-commit` leaves the commit to the
caller.

Run: python3 tests/test_cepa_plan_archive.py
"""
import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"

FAILURES = []
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t", NO_COLOR="1")


def check(name, cond, detail=""):
    print(f"  ok  {name}" if cond else f"FAIL  {name}  {detail}")
    if not cond:
        FAILURES.append(name)


def git(root, *args, when=None):
    env = dict(ENV)
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                          text=True, env=env, check=True).stdout


def cli(root, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN), *args, "--repo", str(root)],
                          capture_output=True, text=True, cwd=root, env=ENV,
                          timeout=60)


def days_ago(n):
    """Noon, local time, n days before today (the date the command compares)."""
    d = datetime.combine(date.today() - timedelta(days=n), datetime.min.time())
    return d.replace(hour=12).strftime("%Y-%m-%dT%H:%M:%S")


def item(ident, status):
    return {"id": ident, "title": f"item {ident}", "why": "porque",
            "status": status, "blocked_by": [], "human_pending": None,
            "evidence": None}


def write_queue(root, name, statuses, with_until=False, mode="single-track",
                legacy=False):
    base = ".claude/programs" if legacy else ".claude/queues"
    d = Path(root) / base / name
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": mode,
            ("program" if legacy else "queue"): name, "source": "teste",
            "items": [item(f"{name}-{i}", s) for i, s in enumerate(statuses)]}
    (d / ("plan.yaml" if legacy else "queue.yaml")).write_text(
        yaml.safe_dump(plan, allow_unicode=True), encoding="utf-8")
    if with_until:
        (d / "until").mkdir()
        (d / "until" / "r1.jsonl").write_text('{"ev": "start"}\n', encoding="utf-8")
    return d


def commit(root, msg, when, *paths):
    git(root, "add", "-A", "--", *(paths or ["."]))
    git(root, "commit", "-qm", msg, when=when)


def new_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir()
    git(root, "init", "-q", ".")
    (root / "README").write_text("x\n")
    commit(root, "base", days_ago(30))
    return root


def archived(root, name):
    return Path(root) / ".claude" / "queues" / "_archive" / name


def queue_dir(root, name):
    return Path(root) / ".claude" / "queues" / name


def test_declared_red_test():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "velha", ["done", "done"], with_until=True)
        commit(root, "velha", days_ago(8), ".claude/queues/velha")
        write_queue(root, "recente", ["done"])
        commit(root, "recente", days_ago(6), ".claude/queues/recente")
        write_queue(root, "aberta", ["done", "pending"])
        commit(root, "aberta", days_ago(40), ".claude/queues/aberta")

        p = cli(root, "archive", "--dry-run")
        check("dry-run exits 0", p.returncode == 0, p.stderr)
        check("dry-run names velha", "velha" in p.stdout, p.stdout)
        check("dry-run does not name recente as archived",
              "arquivaria · recente" not in p.stdout, p.stdout)
        check("dry-run moves nothing", queue_dir(root, "velha").is_dir()
              and not archived(root, "velha").exists())

        p = cli(root, "archive")
        check("archive exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("velha/queue.yaml is in _archive",
              (archived(root, "velha") / "queue.yaml").is_file(), p.stdout)
        check("velha/until/r1.jsonl is in _archive",
              (archived(root, "velha") / "until" / "r1.jsonl").is_file())
        check("velha is gone from its place", not queue_dir(root, "velha").exists())
        check("recente stays", (queue_dir(root, "recente") / "queue.yaml").is_file())
        check("aberta stays", (queue_dir(root, "aberta") / "queue.yaml").is_file())
        check("nothing else in _archive",
              archived(root, "").is_dir()
              and [q.name for q in archived(root, "").iterdir()] == ["velha"])
        check("output names velha", "velha" in p.stdout, p.stdout)
        check("by hand: own commit, tree clean",
              git(root, "status", "--porcelain").strip() == "",
              git(root, "status", "--porcelain"))
        files = [f for f in git(root, "show", "--name-only", "--format=", "HEAD").split()]
        check("the commit holds only what moved",
              bool(files) and all(f.startswith(".claude/queues/") and "velha" in f
                                  for f in files), str(files))
        p = cli(root, "archive")
        check("second sweep: nothing to do, exit 0", p.returncode == 0, p.stderr)


def test_boundary_and_mix():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "sete", ["done", "dropped"])
        commit(root, "sete", days_ago(7), ".claude/queues/sete")
        write_queue(root, "seis", ["done", "dropped"])
        commit(root, "seis", days_ago(6), ".claude/queues/seis")
        write_queue(root, "so-dropped", ["dropped"])
        commit(root, "so-dropped", days_ago(20), ".claude/queues/so-dropped")
        p = cli(root, "archive")
        check("boundary exits 0", p.returncode == 0, p.stderr)
        check("exactly 7 days is archived (done+dropped mix)",
              (archived(root, "sete") / "queue.yaml").is_file(), p.stdout)
        check("6 days stays", queue_dir(root, "seis").is_dir())
        check("a queue with no `done` is not closed, stays",
              queue_dir(root, "so-dropped").is_dir())


def test_collision_in_archive():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "a", ["done"])
        write_queue(root, "b", ["done"])
        commit(root, "ab", days_ago(10), ".claude/queues")
        pre = archived(root, "a")
        pre.mkdir(parents=True)
        (pre / "queue.yaml").write_text("# ja arquivada antes\n")
        commit(root, "pre", days_ago(10), ".claude/queues/_archive")
        p = cli(root, "archive")
        check("collision: exit 0, sweep goes on", p.returncode == 0, p.stderr)
        check("collision: the queue is not moved", queue_dir(root, "a").is_dir())
        check("collision: the archived copy is untouched",
              (pre / "queue.yaml").read_text() == "# ja arquivada antes\n")
        check("collision: the output says so",
              "não arquivada · a:" in p.stdout and "já existe" in p.stdout, p.stdout)
        check("collision: the others move",
              (archived(root, "b") / "queue.yaml").is_file(), p.stdout)


def test_untouched_kinds():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "ondas", ["done"], mode="parallel-waves")
        write_queue(root, "legada", ["done"], legacy=True)
        commit(root, "old things", days_ago(30))
        (root / ".claude" / "queues" / "_all").mkdir(parents=True, exist_ok=True)
        (root / ".claude" / "queues" / "_all" / "r.jsonl").write_text("{}\n")
        write_queue(root, "nova", ["done"])  # never committed
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stderr)
        check("waves plan untouched", queue_dir(root, "ondas").is_dir())
        check("legacy layout untouched",
              (root / ".claude" / "programs" / "legada" / "plan.yaml").is_file())
        check("_all untouched", (root / ".claude/queues/_all/r.jsonl").is_file())
        check("no commit touching the queue: not archived",
              queue_dir(root, "nova").is_dir())
        check("no commit touching the queue: the output says so",
              "nova" in p.stdout and "commit" in p.stdout, p.stdout)


def test_underscore_folder_is_not_a_queue():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "_x", ["done"])
        commit(root, "x", days_ago(8), ".claude/queues")
        p = cli(root, "archive")
        check("_x: exits 0", p.returncode == 0, p.stderr)
        check("_x: stays in place", queue_dir(root, "_x").is_dir(), p.stdout)
        check("_x: not archived", not archived(root, "_x").exists(), p.stdout)


def test_no_commit_flag():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "velha", ["done"], with_until=True)
        commit(root, "velha", days_ago(9), ".claude/queues/velha")
        (root / "alheio.txt").write_text("not mine\n")
        before = git(root, "rev-parse", "HEAD")
        p = cli(root, "archive", "--no-commit")
        check("--no-commit exits 0", p.returncode == 0, p.stderr)
        check("--no-commit moves the folder",
              (archived(root, "velha") / "until" / "r1.jsonl").is_file())
        check("--no-commit makes no commit", git(root, "rev-parse", "HEAD") == before)
        check("--no-commit stages the move for the caller",
              "_archive/velha" in git(root, "diff", "--cached", "--name-only"))
        # by hand with a stranger's file around: the commit must not take it
        git(root, "reset", "-q", "--hard")
        git(root, "clean", "-fdq")
        (root / "alheio.txt").write_text("not mine\n")
        git(root, "add", "alheio.txt")
        p = cli(root, "archive")
        check("own commit exits 0", p.returncode == 0, p.stderr)
        shown = git(root, "show", "--name-only", "--format=", "HEAD")
        check("own commit leaves a staged stranger out", "alheio.txt" not in shown, shown)
        check("own commit holds the move", "_archive/velha" in shown, shown)


def main():
    for t in (test_declared_red_test, test_boundary_and_mix,
              test_collision_in_archive, test_untouched_kinds, test_underscore_folder_is_not_a_queue,
              test_no_commit_flag):
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
