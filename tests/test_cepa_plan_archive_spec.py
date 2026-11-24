#!/usr/bin/env python3
"""CS-3 of docs/spec/filas-fechadas-saem-da-vista.md: the spec a closed queue
came from goes with it, and what went along is announced.

Red test declared in the spec: `velha` has `source: docs/spec/velha.md`, and
that file has two lines in "Decided without asking" without a verdict. After
`cepa-plan archive`: `docs/spec/_archive/velha.md` exists, `docs/spec/velha.md`
does not, the `source:` of `.claude/queues/_archive/velha/queue.yaml` starts
with `docs/spec/_archive/velha.md`, and the output contains
"2 decisões sem veredito foram junto em docs/spec/_archive/velha.md". A second
closed queue with `source: docs/epics/x.md, ciclo 1` is moved and
`docs/epics/x.md` stays.

Also covered: trailing text after the path is kept; only the queue's own
`source:` is rewritten; a spec is moved only when EVERY queue citing it is
archived (this sweep or before) and stays when another one is still open; the
singular/zero wording; --dry-run moves nothing; --no-commit stages the spec
move; the commit holds the spec's old and new paths; the spec file missing, the
destination taken and the spec with uncommitted changes all keep the spec and
the queue's `source:` as they were, and the queue still moves.

Run: python3 tests/test_cepa_plan_archive_spec.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_plan_archive import (CEPA_PLAN, ENV, FAILURES, NEW, archived, check, cli,  # noqa: E402
                                    commit, days_ago, git, new_repo, queue_dir,
                                    write_queue)

SPEC_DIR = "docs/spec"

TWO_PENDING = """# Spec

## Decided without asking
- Primeira decisão sem veredito.
- Segunda decisão sem veredito.
- Terceira já resolvida. · mantida em 2026-11-20
"""
ONE_PENDING = "## Decided without asking\n- Só esta, sem veredito.\n"
NONE_PENDING = "## Decided without asking\n- Resolvida. · vetada em 2026-11-20\n"


def spec_file(root, slug, text=TWO_PENDING):
    p = Path(root) / SPEC_DIR / f"{slug}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def archived_spec(root, slug):
    return Path(root) / SPEC_DIR / "_archive" / f"{slug}.md"


def set_source(root, name, source):
    f = queue_dir(root, name) / "queue.yaml"
    plan = yaml.safe_load(f.read_text(encoding="utf-8"))
    plan["source"] = source
    f.write_text(yaml.safe_dump(plan, allow_unicode=True), encoding="utf-8")


def source_of(root, name, archived_queue=True):
    d = archived(root, name) if archived_queue else queue_dir(root, name)
    return yaml.safe_load((d / "queue.yaml").read_text(encoding="utf-8"))["source"]


def old_queue(root, name, source, days=8, statuses=("done",)):
    write_queue(root, name, list(statuses), with_until=True)
    set_source(root, name, source)
    commit(root, name, days_ago(days), f"{NEW}/{name}")


def commit_spec(root, slug, text=TWO_PENDING, days=30):
    spec_file(root, slug, text)
    commit(root, f"spec {slug}", days_ago(days), f"{SPEC_DIR}/{slug}.md")


def test_declared_red_test():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        old_queue(root, "velha", "docs/spec/velha.md")
        (root / "docs" / "epics").mkdir(parents=True)
        (root / "docs" / "epics" / "x.md").write_text("# Epic\n")
        commit(root, "epic", days_ago(30), "docs/epics")
        old_queue(root, "outra", "docs/epics/x.md, ciclo 1")

        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("spec is in _archive", archived_spec(root, "velha").is_file(), p.stdout)
        check("spec is gone from docs/spec",
              not (root / SPEC_DIR / "velha.md").exists())
        check("spec content intact",
              archived_spec(root, "velha").read_text() == TWO_PENDING)
        check("source of the archived queue starts at the new path",
              str(source_of(root, "velha")).startswith("docs/spec/_archive/velha.md"),
              str(source_of(root, "velha")))
        check("output announces the 2 decisions and the file",
              "2 decisões sem veredito foram junto em docs/spec/_archive/velha.md"
              in p.stdout, p.stdout)
        check("the epic-sourced queue moved",
              (archived(root, "outra") / "queue.yaml").is_file(), p.stdout)
        check("the epic stays in place", (root / "docs/epics/x.md").is_file())
        check("the epic-sourced queue keeps its source",
              source_of(root, "outra") == "docs/epics/x.md, ciclo 1")
        check("tree clean (own commit)", git(root, "status", "--porcelain").strip() == "")
        files = git(root, "show", "--no-renames", "--name-only", "--format=",
                    "HEAD").split()
        check("commit holds the spec's old path", "docs/spec/velha.md" in files, str(files))
        check("commit holds the spec's new path",
              "docs/spec/_archive/velha.md" in files, str(files))
        check("commit holds only moved things",
              all(f.startswith((".claude/queues/", "docs/spec/")) for f in files),
              str(files))


def test_trailing_text_and_other_citations_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        write_queue(root, "velha", ["done"], with_until=True)
        set_source(root, "velha", "docs/spec/velha.md, 3 critérios")
        f = queue_dir(root, "velha") / "queue.yaml"
        plan = yaml.safe_load(f.read_text())
        plan["items"][0]["evidence"] = "veja docs/spec/velha.md"
        f.write_text(yaml.safe_dump(plan, allow_unicode=True))
        commit(root, "velha", days_ago(8), f"{NEW}/velha")
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stderr)
        check("trailing text is kept after the new path",
              source_of(root, "velha") == "docs/spec/_archive/velha.md, 3 critérios",
              str(source_of(root, "velha")))
        plan = yaml.safe_load((archived(root, "velha") / "queue.yaml").read_text())
        check("evidence citing the old path is not touched",
              plan["items"][0]["evidence"] == "veja docs/spec/velha.md")


def test_wording_for_one_and_zero():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "um", ONE_PENDING)
        commit_spec(root, "zero", NONE_PENDING)
        commit_spec(root, "sem-secao", "# so isso\n")
        old_queue(root, "um", "docs/spec/um.md")
        old_queue(root, "zero", "docs/spec/zero.md")
        old_queue(root, "sem-secao", "docs/spec/sem-secao.md")
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stderr)
        check("one: singular",
              "1 decisão sem veredito foi junto em docs/spec/_archive/um.md"
              in p.stdout, p.stdout)
        check("zero: says none went along",
              "nenhuma decisão sem veredito foi junto em docs/spec/_archive/zero.md"
              in p.stdout, p.stdout)
        check("no section: same as zero",
              "nenhuma decisão sem veredito foi junto em "
              "docs/spec/_archive/sem-secao.md" in p.stdout, p.stdout)


def test_other_open_queue_keeps_the_spec():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "comum")
        old_queue(root, "velha", "docs/spec/comum.md")
        old_queue(root, "aberta", "docs/spec/comum.md (parte 2)", days=3,
                  statuses=("done", "pending"))
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stderr)
        check("the closed queue moved",
              (archived(root, "velha") / "queue.yaml").is_file(), p.stdout)
        check("the spec stays", (root / SPEC_DIR / "comum.md").is_file())
        check("nothing in spec _archive", not archived_spec(root, "comum").exists())
        check("source stays as is",
              source_of(root, "velha") == "docs/spec/comum.md",
              str(source_of(root, "velha")))
        check("the output says why the spec stayed",
              "aberta" in p.stdout and "docs/spec/comum.md" in p.stdout
              and "junto" not in p.stdout.replace("ficou", ""), p.stdout)
        check("no 'went along' line", "foi junto" not in p.stdout, p.stdout)
        # a closed queue that is not yet 7 days old also keeps the spec
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "comum")
        old_queue(root, "velha", "docs/spec/comum.md")
        old_queue(root, "recente", "docs/spec/comum.md", days=2)
        p = cli(root, "archive")
        check("recent closed sibling: spec stays", (root / SPEC_DIR / "comum.md").is_file())
        check("recent closed sibling: old queue moved",
              (archived(root, "velha") / "queue.yaml").is_file())


def test_all_citers_archived_in_one_sweep_or_before():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "comum")
        old_queue(root, "a", "docs/spec/comum.md")
        old_queue(root, "b", "docs/spec/comum.md; ver tb. x")
        p = cli(root, "archive")
        check("both in the same sweep: spec moved", archived_spec(root, "comum").is_file(),
              p.stdout)
        check("a rewritten", source_of(root, "a") == "docs/spec/_archive/comum.md")
        check("b rewritten, tail kept",
              source_of(root, "b") == "docs/spec/_archive/comum.md; ver tb. x",
              str(source_of(root, "b")))
        check("announced once",
              p.stdout.count("junto em docs/spec/_archive/comum.md") == 1, p.stdout)
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "comum")
        old_queue(root, "antes", "docs/spec/comum.md", days=40)
        # the sibling was archived earlier (its source points at the old path
        # because the spec stayed back then)
        d = archived(root, "antes")
        d.parent.mkdir(parents=True, exist_ok=True)
        (queue_dir(root, "antes")).rename(d)
        commit(root, "arquivou antes", days_ago(20), ".claude/queues")
        old_queue(root, "agora", "docs/spec/comum.md")
        p = cli(root, "archive")
        check("sibling already in _archive: spec moves",
              archived_spec(root, "comum").is_file(), p.stdout)
        check("sibling archived earlier: its source follows the spec",
              str(source_of(root, "antes")).startswith("docs/spec/_archive/comum.md"),
              str(source_of(root, "antes")))
        files = git(root, "show", "--no-renames", "--name-only", "--format=",
                    "HEAD").split()
        check("commit holds the earlier queue's queue.yaml",
              ".claude/queues/_archive/antes/queue.yaml" in files, str(files))
        check("tree clean after the sweep", git(root, "status", "--porcelain").strip() == "")
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "comum")
        old_queue(root, "antes", "docs/spec/comum.md; ver tb. x", days=40)
        d = archived(root, "antes")
        d.parent.mkdir(parents=True, exist_ok=True)
        (queue_dir(root, "antes")).rename(d)
        commit(root, "arquivou antes", days_ago(20), ".claude/queues")
        old_queue(root, "agora", "docs/spec/comum.md")
        p = cli(root, "archive", "--no-commit")
        staged = git(root, "diff", "--cached", "--name-only", "--no-renames").split()
        check("--no-commit stages the earlier queue's queue.yaml",
              ".claude/queues/_archive/antes/queue.yaml" in staged, str(staged))
        check("--no-commit: earlier queue keeps its tail",
              source_of(root, "antes") == "docs/spec/_archive/comum.md; ver tb. x",
              str(source_of(root, "antes")))


def test_dry_run_and_no_commit():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        old_queue(root, "velha", "docs/spec/velha.md")
        p = cli(root, "archive", "--dry-run")
        check("dry-run exits 0", p.returncode == 0, p.stderr)
        check("dry-run moves no spec", (root / SPEC_DIR / "velha.md").is_file()
              and not archived_spec(root, "velha").exists())
        check("dry-run leaves the queue and its source",
              source_of(root, "velha", archived_queue=False) == "docs/spec/velha.md")
        check("dry-run mentions the spec", "docs/spec/velha.md" in p.stdout, p.stdout)
        check("dry-run tree clean", git(root, "status", "--porcelain").strip() == "")
        before = git(root, "rev-parse", "HEAD")
        p = cli(root, "archive", "--no-commit")
        check("--no-commit exits 0", p.returncode == 0, p.stderr)
        check("--no-commit: no commit", git(root, "rev-parse", "HEAD") == before)
        staged = git(root, "diff", "--cached", "--name-only", "--no-renames").split()
        check("--no-commit stages the spec's new path",
              "docs/spec/_archive/velha.md" in staged, str(staged))
        check("--no-commit stages the spec's old path",
              "docs/spec/velha.md" in staged, str(staged))
        check("--no-commit: the announcement is there",
              "2 decisões sem veredito foram junto em docs/spec/_archive/velha.md"
              in p.stdout, p.stdout)


def test_commit_leaves_strangers_out():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        commit_spec(root, "alheia")
        old_queue(root, "velha", "docs/spec/velha.md")
        (root / SPEC_DIR / "alheia.md").write_text("# outra, mexida\n")
        git(root, "add", f"{SPEC_DIR}/alheia.md")
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stderr)
        shown = git(root, "show", "--no-renames", "--name-only", "--format=", "HEAD")
        check("a stranger's staged spec stays out of the commit",
              "alheia.md" not in shown, shown)


def test_spec_missing():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "velha", "docs/spec/velha.md")
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("queue still moves", (archived(root, "velha") / "queue.yaml").is_file())
        check("source stays", source_of(root, "velha") == "docs/spec/velha.md")
        check("nothing created in spec _archive",
              not archived_spec(root, "velha").exists())
        check("output says the spec does not exist",
              "docs/spec/velha.md" in p.stdout and "não existe" in p.stdout, p.stdout)
        check("tree clean", git(root, "status", "--porcelain").strip() == "")


def test_destination_taken():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        pre = archived_spec(root, "velha")
        pre.parent.mkdir(parents=True)
        pre.write_text("# ja arquivada antes\n")
        commit(root, "pre", days_ago(30), f"{SPEC_DIR}/_archive")
        old_queue(root, "velha", "docs/spec/velha.md")
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("queue still moves", (archived(root, "velha") / "queue.yaml").is_file())
        check("neither file is lost or overwritten",
              pre.read_text() == "# ja arquivada antes\n"
              and (root / SPEC_DIR / "velha.md").read_text() == TWO_PENDING)
        check("source stays", source_of(root, "velha") == "docs/spec/velha.md")
        check("output says the destination is taken",
              "já existe" in p.stdout and "docs/spec/_archive/velha.md" in p.stdout,
              p.stdout)


def test_spec_with_uncommitted_changes():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        old_queue(root, "velha", "docs/spec/velha.md")
        edited = TWO_PENDING + "\n- minha edição ainda não commitada\n"
        (root / SPEC_DIR / "velha.md").write_text(edited)
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("queue still moves", (archived(root, "velha") / "queue.yaml").is_file())
        check("spec stays with the edit",
              (root / SPEC_DIR / "velha.md").read_text() == edited)
        check("nothing in spec _archive", not archived_spec(root, "velha").exists())
        check("source stays", source_of(root, "velha") == "docs/spec/velha.md")
        check("output says it has uncommitted changes",
              "não commitadas" in p.stdout, p.stdout)
        check("the edit is still uncommitted, not swept into the commit",
              "docs/spec/velha.md" not in git(root, "show", "--name-only",
                                              "--format=", "HEAD"))
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        old_queue(root, "velha", "docs/spec/velha.md")
        spec_file(root, "velha")  # never committed
        p = cli(root, "archive")
        check("untracked spec: stays", (root / SPEC_DIR / "velha.md").is_file()
              and not archived_spec(root, "velha").exists(), p.stdout)


def test_only_docs_spec_slug_paths_move():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        (root / "BACKLOG.md").write_text("# b\n")
        (root / SPEC_DIR / "_archive").mkdir(parents=True)
        commit(root, "backlog", days_ago(30), "BACKLOG.md")
        old_queue(root, "um", "BACKLOG.md")
        old_queue(root, "dois", "docs/spec/sub/x.md")
        old_queue(root, "tres", "teste")
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stderr)
        check("all three queues moved",
              all((archived(root, n) / "queue.yaml").is_file()
                  for n in ("um", "dois", "tres")), p.stdout)
        check("BACKLOG stays", (root / "BACKLOG.md").is_file())
        check("sources untouched",
              source_of(root, "um") == "BACKLOG.md" and source_of(root, "tres") == "teste")
        check("no spec line", "foi junto" not in p.stdout, p.stdout)


def test_help_mentions_the_spec_move():
    p = cli(Path(tempfile.gettempdir()), "archive", "--help")
    check("help mentions docs/spec/_archive", "docs/spec/_archive" in p.stdout, p.stdout)


def test_count_fails_after_the_move():
    # The decisions reader reads with errors="replace" and answers None on
    # OSError, so no spec content makes it raise. The failure is forced from
    # outside: a `sitecustomize` on PYTHONPATH (kept apart from the repo under
    # test) loads the hooks' `_decisions` first and makes `read_file` raise for
    # paths under `_archive`, i.e. only the count made after the move.
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as shim:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        old_queue(root, "velha", "docs/spec/velha.md")
        (Path(shim) / "sitecustomize.py").write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(CEPA_PLAN.parent.parent / 'hooks')!r})\n"
            "import _decisions\n"
            "_real = _decisions.read_file\n"
            "def _read_file(path):\n"
            "    if '_archive' in str(path):\n"
            "        raise RuntimeError('leitura forcada a falhar')\n"
            "    return _real(path)\n"
            "_decisions.read_file = _read_file\n", encoding="utf-8")
        env = dict(ENV, PYTHONPATH=shim + os.pathsep + ENV.get("PYTHONPATH", ""))
        p = subprocess.run([sys.executable, str(CEPA_PLAN), "archive", "--repo", str(root)],
                           capture_output=True, text=True, cwd=root, env=env, timeout=60)
        check("exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("output says the spec moved", "especificação movida" in p.stdout, p.stdout)
        check("output says the count could not be made",
              "não puderam ser contadas" in p.stdout, p.stdout)
        check("output does not say the spec stayed",
              "especificação não movida" not in p.stdout, p.stdout)
        check("spec is in _archive", archived_spec(root, "velha").is_file(), p.stdout)
        check("spec is gone from the old path", not (root / SPEC_DIR / "velha.md").exists())
        check("source of the archived queue starts at the new path",
              str(source_of(root, "velha")).startswith("docs/spec/_archive/velha.md"),
              str(source_of(root, "velha")))
        files = git(root, "show", "--no-renames", "--name-only", "--format=",
                    "HEAD").split()
        check("commit holds the spec's old path", "docs/spec/velha.md" in files, str(files))
        check("commit holds the spec's new path",
              "docs/spec/_archive/velha.md" in files, str(files))
        check("tree clean (own commit)", git(root, "status", "--porcelain").strip() == "")


def main():
    for t in (test_declared_red_test, test_trailing_text_and_other_citations_untouched,
              test_wording_for_one_and_zero, test_other_open_queue_keeps_the_spec,
              test_all_citers_archived_in_one_sweep_or_before, test_dry_run_and_no_commit,
              test_commit_leaves_strangers_out, test_spec_missing, test_destination_taken,
              test_spec_with_uncommitted_changes, test_only_docs_spec_slug_paths_move,
              test_help_mentions_the_spec_move, test_count_fails_after_the_move):
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
