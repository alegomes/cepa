#!/usr/bin/env python3
"""CS-1 of docs/spec/filas-fechadas-saem-da-vista.md: `cepa-queue archive` moves
the closed queue that has been still for 7 days, and only that one.

Red test declared in the spec: in a fixture repo with the queue `velha` (every
item `done`, last commit 8 days ago, with `until/r1.jsonl`), `recente` (every
item `done`, last commit 6 days ago) and `aberta` (one `pending` item),
`cepa-queue archive` exits 0; afterwards
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
CEPA_PLAN = REPO / "common" / "bin" / "cepa-queue"

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


NEW = ".claude/queues"


def old_queue(root, name, days=10, statuses=("done",), with_until=False):
    """A closed queue whose last commit is `days` old, committed and clean."""
    write_queue(root, name, list(statuses), with_until=with_until)
    commit(root, name, days_ago(days), f"{NEW}/{name}")


def head_changes(root):
    """`git show --name-status HEAD` without rename detection, as a sorted list."""
    out = git(root, "show", "--no-renames", "--name-status", "--format=", "HEAD")
    return sorted(line for line in out.splitlines() if line.strip())


def test_corrupted_queues_do_not_abort_the_sweep():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "a-boa", with_until=True)
        old_queue(root, "m-binaria")
        (queue_dir(root, "m-binaria") / "queue.yaml").write_bytes(b"\xff\xfe\x00\x80\xc3\x28")
        commit(root, "binaria", days_ago(10), f"{NEW}/m-binaria")
        old_queue(root, "n-itens")
        (queue_dir(root, "n-itens") / "queue.yaml").write_text(
            "schema_version: 2\nmode: single-track\nqueue: n-itens\nitems: 5\n")
        commit(root, "itens", days_ago(10), f"{NEW}/n-itens")
        old_queue(root, "z-boa")
        p = cli(root, "archive")
        check("corrupted: exit 0", p.returncode == 0, p.stdout + p.stderr)
        check("corrupted: no traceback", "Traceback" not in p.stderr, p.stderr)
        check("corrupted: binary queue stays", (queue_dir(root, "m-binaria") / "queue.yaml").is_file())
        check("corrupted: items-not-a-list queue stays", (queue_dir(root, "n-itens") / "queue.yaml").is_file())
        check("corrupted: the reason is printed for the binary one",
              "m-binaria" in p.stderr and "ilegível" in p.stderr, p.stderr)
        check("corrupted: the warning names the exception class",
              "UnicodeDecodeError" in p.stderr or "TypeError" in p.stderr, p.stderr)
        check("corrupted: the reason is printed for the items one",
              "n-itens" in p.stderr and "ilegível" in p.stderr, p.stderr)
        check("corrupted: good queue before them archived",
              (archived(root, "a-boa") / "until" / "r1.jsonl").is_file(), p.stdout)
        check("corrupted: good queue after them archived",
              (archived(root, "z-boa") / "queue.yaml").is_file(), p.stdout)
        check("corrupted: the good moves are committed, tree has no stray state",
              git(root, "status", "--porcelain").strip() == "", git(root, "status", "--porcelain"))
        check("corrupted: the commit holds exactly the two good queues",
              head_changes(root) == sorted([
                  f"D\t{NEW}/a-boa/queue.yaml", f"D\t{NEW}/a-boa/until/r1.jsonl",
                  f"A\t{NEW}/_archive/a-boa/queue.yaml", f"A\t{NEW}/_archive/a-boa/until/r1.jsonl",
                  f"D\t{NEW}/z-boa/queue.yaml", f"A\t{NEW}/_archive/z-boa/queue.yaml"]),
              str(head_changes(root)))


def test_dirty_folder_is_not_archived():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "mexida")
        old_queue(root, "com-novo", with_until=True)
        old_queue(root, "limpa")
        (queue_dir(root, "mexida") / "queue.yaml").write_text(
            (queue_dir(root, "mexida") / "queue.yaml").read_text() + "# editado\n")
        (queue_dir(root, "com-novo") / "until" / "r2.jsonl").write_text("{}\n")
        p = cli(root, "archive")
        check("dirty: exit 0", p.returncode == 0, p.stderr)
        check("dirty: modified tracked file keeps the queue",
              queue_dir(root, "mexida").is_dir() and not archived(root, "mexida").exists())
        check("dirty: untracked file inside keeps the queue",
              (queue_dir(root, "com-novo") / "until" / "r2.jsonl").is_file()
              and not archived(root, "com-novo").exists())
        check("dirty: modified file, the output says why",
              "não arquivada · mexida: a pasta tem alterações não commitadas; commite antes de arquivar"
              in p.stdout, p.stdout)
        check("dirty: untracked file, the output says why",
              "não arquivada · com-novo: a pasta tem alterações não commitadas; commite antes de arquivar"
              in p.stdout, p.stdout)
        check("dirty: the clean one goes", (archived(root, "limpa") / "queue.yaml").is_file(), p.stdout)
        check("dirty: the dirty edit survives, untouched",
              "# editado" in (queue_dir(root, "mexida") / "queue.yaml").read_text())


def test_commit_failure_exits_3_and_keeps_stage():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "velha")
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho nope >&2\nexit 1\n")
        hook.chmod(0o755)
        p = cli(root, "archive")
        check("commit failure: exit 3", p.returncode == 3, f"{p.returncode} {p.stdout} {p.stderr}")
        check("commit failure: warning on stderr",
              "aviso: o commit falhou" in p.stderr and "o move ficou em stage" in p.stderr, p.stderr)
        check("commit failure: no success line", "commit feito" not in p.stdout, p.stdout)
        check("commit failure: the move stays staged",
              f"{NEW}/_archive/velha/queue.yaml" in git(root, "diff", "--cached", "--name-only"))
        check("commit failure: the folder did move", (archived(root, "velha") / "queue.yaml").is_file())


def test_unreadable_and_non_dict_plans_are_skipped():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "a-boa")
        old_queue(root, "b-quebrada")
        (queue_dir(root, "b-quebrada") / "queue.yaml").write_text("items: [unclosed\n  - : :\n")
        old_queue(root, "c-lista")
        (queue_dir(root, "c-lista") / "queue.yaml").write_text("- um\n- dois\n")
        old_queue(root, "d-escalar")
        (queue_dir(root, "d-escalar") / "queue.yaml").write_text("so texto\n")
        old_queue(root, "e-boa")
        commit(root, "bad", days_ago(10), NEW)
        p = cli(root, "archive")
        check("skips: exit 0", p.returncode == 0, p.stderr)
        check("skips: no traceback", "Traceback" not in p.stderr, p.stderr)
        check("skips: broken YAML is named on stderr",
              "aviso: fila b-quebrada ilegível, não arquivada" in p.stderr, p.stderr)
        check("skips: list plan is skipped without a warning", "c-lista" not in p.stderr, p.stderr)
        check("skips: scalar plan is skipped without a warning", "d-escalar" not in p.stderr, p.stderr)
        for n in ("b-quebrada", "c-lista", "d-escalar"):
            check(f"skips: {n} stays", (queue_dir(root, n) / "queue.yaml").is_file())
        check("skips: good ones around them go",
              (archived(root, "a-boa") / "queue.yaml").is_file()
              and (archived(root, "e-boa") / "queue.yaml").is_file(), p.stdout)


def test_move_failure_leaves_the_queue_intact():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "velha", with_until=True)
        (root / NEW / "_archive").write_text("sou um arquivo\n")
        before = git(root, "rev-parse", "HEAD")
        p = cli(root, "archive")
        check("move failure: exit 0", p.returncode == 0, p.stdout + p.stderr)
        check("move failure: no traceback", "Traceback" not in p.stderr, p.stderr)
        check("move failure: the output says so",
              "não arquivada · velha: o move falhou (" in p.stdout, p.stdout)
        check("move failure: queue intact",
              (queue_dir(root, "velha") / "until" / "r1.jsonl").is_file())
        check("move failure: no archived line",
              not any(l.startswith("arquivada ·") for l in p.stdout.splitlines()), p.stdout)
        check("move failure: nothing to archive, no commit",
              "nada a arquivar" in p.stdout and git(root, "rev-parse", "HEAD") == before, p.stdout)


def test_no_commit_ever_touched_the_folder():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        root.mkdir()
        git(root, "init", "-q", ".")  # no commit at all: git log fails
        write_queue(root, "nova", ["done"])
        p = cli(root, "archive")
        check("unborn repo: exit 0", p.returncode == 0, p.stdout + p.stderr)
        check("unborn repo: kept, with the reason",
              "não arquivada · nova: nenhum commit tocou a pasta da fila, então não há idade para medir"
              in p.stdout, p.stdout)
        check("unborn repo: stays", queue_dir(root, "nova").is_dir())


def test_days_remaining_number():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "seis", days=6)
        old_queue(root, "tres", days=3)
        p = cli(root, "archive")
        d6 = (date.today() - timedelta(days=6)).isoformat()
        d3 = (date.today() - timedelta(days=3)).isoformat()
        check("remaining: 6 days old, 1 day left",
              f"não arquivada · seis: último commit em {d6}, faltam 1 dia(s) para os 7 de parada"
              in p.stdout, p.stdout)
        check("remaining: 3 days old, 4 days left",
              f"não arquivada · tres: último commit em {d3}, faltam 4 dia(s) para os 7 de parada"
              in p.stdout, p.stdout)
        check("remaining: nothing moved, says so", "nada a arquivar" in p.stdout, p.stdout)


def test_commit_pathspec_and_messages():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "velha", with_until=True)
        old_queue(root, "aberta", statuses=("done", "pending"))
        old_queue(root, "outra", statuses=("done", "pending"))
        # a stranger staged INSIDE .claude/queues: another queue's edit
        outra = queue_dir(root, "outra") / "queue.yaml"
        outra.write_text(outra.read_text() + "# edit de outra sessao\n")
        git(root, "add", f"{NEW}/outra/queue.yaml")
        p = cli(root, "archive", "--dry-run")
        check("messages: dry-run line exact", "(dry-run) arquivaria · velha\n" in p.stdout, p.stdout)
        p = cli(root, "archive")
        check("messages: exit 0", p.returncode == 0, p.stderr)
        check("messages: moved line exact",
              f"arquivada · velha → {NEW}/_archive/velha\n" in p.stdout, p.stdout)
        check("messages: commit line exact", "commit feito com 1 fila(s)\n" in p.stdout, p.stdout)
        check("messages: the commit holds exactly the moved paths",
              head_changes(root) == sorted([
                  f"D\t{NEW}/velha/queue.yaml", f"D\t{NEW}/velha/until/r1.jsonl",
                  f"A\t{NEW}/_archive/velha/queue.yaml", f"A\t{NEW}/_archive/velha/until/r1.jsonl"]),
              str(head_changes(root)))
        check("messages: the commit message names the queue",
              git(root, "log", "-1", "--format=%s").strip() == "archive closed queues: velha")
        check("messages: the stranger inside queues is still staged, not committed",
              git(root, "diff", "--cached", "--name-only").split() == [f"{NEW}/outra/queue.yaml"])
        # nothing left to do
        git(root, "reset", "-q", "--hard")
        p = cli(root, "archive")
        check("messages: nothing to do line", p.stdout == "nada a arquivar\n", p.stdout)
        # --no-commit line
        old_queue(root, "outra2")
        p = cli(root, "archive", "--no-commit")
        check("messages: --no-commit line exact",
              "movido e em stage, sem commit (--no-commit): o commit é de quem chamou\n" in p.stdout,
              p.stdout)
        # collision: exact reason
        git(root, "reset", "-q", "--hard")
        old_queue(root, "dup")
        pre = archived(root, "dup")
        pre.mkdir(parents=True)
        (pre / "queue.yaml").write_text("# antes\n")
        commit(root, "pre", days_ago(10), f"{NEW}/_archive")
        p = cli(root, "archive")
        check("messages: collision reason exact",
              f"não arquivada · dup: já existe {NEW}/_archive/dup; a fila não foi movida\n" in p.stdout,
              p.stdout)


def test_help_lists_archive():
    p = subprocess.run([sys.executable, str(CEPA_PLAN), "--help"], capture_output=True,
                       text=True, env=ENV, timeout=60)
    lines = p.stdout.splitlines()
    check("help: exit 0", p.returncode == 0, p.stderr)
    check("help: archive is listed under a group, with its text",
          any(l.startswith("    archive ") and "closed queues" in l for l in lines), p.stdout)


def test_latest_commit_counts():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "dois-velhos", days=20)
        (queue_dir(root, "dois-velhos") / "nota.txt").write_text("b\n")
        commit(root, "segundo", days_ago(10), f"{NEW}/dois-velhos")
        old_queue(root, "mexida-ontem", days=20)
        (queue_dir(root, "mexida-ontem") / "nota.txt").write_text("b\n")
        commit(root, "segundo", days_ago(3), f"{NEW}/mexida-ontem")
        p = cli(root, "archive")
        check("two old commits: archived", (archived(root, "dois-velhos") / "queue.yaml").is_file(), p.stdout)
        check("old commit then a 3-day-old one: stays (latest counts)",
              (queue_dir(root, "mexida-ontem") / "queue.yaml").is_file(), p.stdout)


def test_dry_run_nothing_line():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "velha")
        p = cli(root, "archive", "--dry-run")
        check("dry-run with a candidate: no 'nada a arquivar'",
              "nada a arquivar" not in p.stdout, p.stdout)
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "recente", days=2)
        p = cli(root, "archive", "--dry-run")
        check("dry-run with nothing qualifying: 'nada a arquivar'",
              "nada a arquivar" in p.stdout, p.stdout)


def main():
    for t in (test_declared_red_test, test_boundary_and_mix,
              test_collision_in_archive, test_untouched_kinds, test_underscore_folder_is_not_a_queue,
              test_no_commit_flag, test_corrupted_queues_do_not_abort_the_sweep,
              test_dirty_folder_is_not_archived, test_commit_failure_exits_3_and_keeps_stage,
              test_unreadable_and_non_dict_plans_are_skipped,
              test_move_failure_leaves_the_queue_intact, test_no_commit_ever_touched_the_folder,
              test_days_remaining_number, test_commit_pathspec_and_messages,
              test_help_lists_archive, test_latest_commit_counts,
              test_dry_run_nothing_line):
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
