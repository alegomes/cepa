#!/usr/bin/env python3
"""CS-3 of docs/spec/filas-fechadas-saem-da-vista.md: the spec a closed queue
came from goes with it, and what went along is announced.

Red test declared in the spec: `velha` has `source: docs/spec/velha.md`, and
that file has two lines in "Decided without asking" without a verdict. After
`cepa-queue archive`: `docs/spec/_archive/velha.md` exists, `docs/spec/velha.md`
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


# ── proof gaps of CS-3 (round 1): rollback, filters, odd sources, containment ──

def raw_queue(root, name, source_raw, days=8, statuses=("done",)):
    """Like old_queue, but the `source:` line is written as given (folded,
    quoted, `./`, a list...), so the queue.yaml is not re-dumped by PyYAML."""
    write_queue(root, name, list(statuses), with_until=True)
    f = queue_dir(root, name) / "queue.yaml"
    text = f.read_text(encoding="utf-8")
    assert "source: teste\n" in text, text
    f.write_text(text.replace("source: teste\n", source_raw, 1), encoding="utf-8")
    commit(root, name, days_ago(days), f"{NEW}/{name}")


def archive_by_hand(root, name):
    """The queue was archived in an earlier sweep."""
    d = archived(root, name)
    d.parent.mkdir(parents=True, exist_ok=True)
    queue_dir(root, name).rename(d)
    commit(root, f"arquivou {name}", days_ago(20), ".claude/queues")


def qtext(root, name, archived_queue=True):
    d = archived(root, name) if archived_queue else queue_dir(root, name)
    return (d / "queue.yaml").read_bytes()


def head_files(root):
    return git(root, "show", "--no-renames", "--name-only", "--format=", "HEAD").split()


FOLDED = "source: >-\n  docs/spec/comum.md\n"
PLAIN = "source: docs/spec/comum.md, parte 1\n"


def test_rollback_when_a_source_rewrite_fails():
    # two queues of one sweep cite the same spec; the plain one is rewritten
    # fine, the folded one cannot be: everything goes back as it was, and the
    # queues are archived and committed anyway. Both name orders, so the plain
    # one is rewritten before the folded one fails in one of them.
    for plain, folded in (("a-plain", "b-folded"), ("a-folded", "b-plain")):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_repo(tmp)
            commit_spec(root, "comum")
            raw_queue(root, plain, PLAIN)
            raw_queue(root, folded, FOLDED)
            before = {n: qtext(root, n, archived_queue=False) for n in (plain, folded)}
            p = cli(root, "archive")
            tag = f"[{plain}+{folded}] "
            check(tag + "exits 0", p.returncode == 0, p.stdout + p.stderr)
            check(tag + "spec is back at docs/spec", (root / SPEC_DIR / "comum.md").is_file()
                  and (root / SPEC_DIR / "comum.md").read_text() == TWO_PENDING)
            check(tag + "nothing at docs/spec/_archive/comum.md",
                  not archived_spec(root, "comum").exists())
            for n in (plain, folded):
                check(tag + f"{n} archived", (archived(root, n) / "queue.yaml").is_file(),
                      p.stdout)
                check(tag + f"{n} queue.yaml byte-identical", qtext(root, n) == before[n],
                      qtext(root, n).decode())
            check(tag + "output says the spec was not moved and names the folded queue",
                  "especificação não movida" in p.stdout
                  and f"o source de {folded} não é uma linha simples" in p.stdout, p.stdout)
            check(tag + "no 'movida' line", "especificação movida" not in p.stdout, p.stdout)
            files = head_files(root)
            check(tag + "commit holds both queues",
                  f".claude/queues/_archive/{plain}/queue.yaml" in files
                  and f".claude/queues/_archive/{folded}/queue.yaml" in files, str(files))
            check(tag + "commit holds no spec path", not any(f.startswith("docs/") for f in files),
                  str(files))
            check(tag + "tree clean", git(root, "status", "--porcelain").strip() == "")


def test_rollback_single_folded_queue_and_earlier_queue():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "comum")
        raw_queue(root, "dobrada", FOLDED)
        before = qtext(root, "dobrada", archived_queue=False)
        p = cli(root, "archive")
        check("single folded: exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("single folded: spec stays", (root / SPEC_DIR / "comum.md").is_file()
              and not archived_spec(root, "comum").exists())
        check("single folded: queue.yaml unchanged", qtext(root, "dobrada") == before)
        check("single folded: says so and names the queue",
              "especificação não movida" in p.stdout and "dobrada" in p.stdout, p.stdout)
        check("single folded: queue committed",
              ".claude/queues/_archive/dobrada/queue.yaml" in head_files(root))
        check("single folded: tree clean", git(root, "status", "--porcelain").strip() == "")
    # an earlier-archived queue that cannot be rewritten: the new queue, rewritten
    # first, goes back too
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "comum")
        raw_queue(root, "antes", FOLDED, days=40)
        archive_by_hand(root, "antes")
        raw_queue(root, "agora", PLAIN)
        before_antes = qtext(root, "antes")
        before_agora = qtext(root, "agora", archived_queue=False)
        p = cli(root, "archive")
        check("earlier folded: exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("earlier folded: spec stays", (root / SPEC_DIR / "comum.md").is_file()
              and not archived_spec(root, "comum").exists(), p.stdout)
        check("earlier folded: both queue.yaml unchanged",
              qtext(root, "antes") == before_antes and qtext(root, "agora") == before_agora)
        check("earlier folded: names the earlier queue",
              "o source de antes não é uma linha simples" in p.stdout, p.stdout)
        check("earlier folded: tree clean", git(root, "status", "--porcelain").strip() == "")


def test_unrelated_archived_queues_are_left_alone():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        commit_spec(root, "outra")
        (root / "docs" / "epics").mkdir(parents=True)
        (root / "docs" / "epics" / "x.md").write_text("# Epic\n")
        commit(root, "epic", days_ago(30), "docs/epics")
        old_queue(root, "arq-spec", "docs/spec/outra.md", days=40)
        old_queue(root, "arq-epic", "docs/epics/x.md, ciclo 1", days=40)
        archive_by_hand(root, "arq-spec")
        archive_by_hand(root, "arq-epic")
        broken = archived(root, "arq-quebrada")
        broken.mkdir(parents=True)
        (broken / "queue.yaml").write_text("source: [docs/spec/velha.md\nitems: {\n",
                                           encoding="utf-8")
        commit(root, "quebrada", days_ago(20), ".claude/queues")
        before = {n: qtext(root, n) for n in ("arq-spec", "arq-epic", "arq-quebrada")}
        old_queue(root, "velha", "docs/spec/velha.md")
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("the spec moves", archived_spec(root, "velha").is_file()
              and not (root / SPEC_DIR / "velha.md").exists(), p.stdout)
        check("its queue follows", str(source_of(root, "velha")).startswith(
            "docs/spec/_archive/velha.md"))
        for n in before:
            check(f"{n} untouched", qtext(root, n) == before[n])
        files = head_files(root)
        check("unrelated archived queues are not in the commit",
              not any(n in f for f in files for n in before), str(files))
        check("the other spec stays", (root / SPEC_DIR / "outra.md").is_file())
        check("tree clean", git(root, "status", "--porcelain").strip() == "")


def test_dot_slash_and_quoted_sources():
    cases = (("./docs/spec/a.md", "source: ./docs/spec/a.md\n", "docs/spec/_archive/a.md"),
             ("double quoted", 'source: "docs/spec/a.md"\n', "docs/spec/_archive/a.md"),
             ("single quoted with tail", "source: 'docs/spec/a.md, ciclo 2'\n",
              "docs/spec/_archive/a.md, ciclo 2"),
             ("./ and tail", "source: ./docs/spec/a.md ciclo 3\n",
              "docs/spec/_archive/a.md ciclo 3"))
    for label, raw, expected in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_repo(tmp)
            commit_spec(root, "a")
            raw_queue(root, "q", raw)
            p = cli(root, "archive")
            check(f"{label}: exits 0", p.returncode == 0, p.stdout + p.stderr)
            check(f"{label}: spec moved", archived_spec(root, "a").is_file()
                  and not (root / SPEC_DIR / "a.md").exists(), p.stdout)
            got = source_of(root, "q")
            check(f"{label}: source parses to the new path, tail kept", got == expected,
                  repr(got))
            check(f"{label}: tree clean", git(root, "status", "--porcelain").strip() == "")
    # a value that itself starts with a quote can never be rewritten: the spec
    # stays and the output says why (the quote in the first regex is what
    # makes the queue reach the rewrite and be reported)
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "a")
        raw_queue(root, "q", "source: '\"docs/spec/a.md\" ciclo'\n")
        p = cli(root, "archive")
        check("quote inside the value: spec stays", (root / SPEC_DIR / "a.md").is_file()
              and not archived_spec(root, "a").exists(), p.stdout)
        check("quote inside the value: says why",
              "especificação não movida" in p.stdout and "q" in p.stdout, p.stdout)


def test_spec_slug_guards():
    # (a) a list `source:` does not raise and does not stop the other spec
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "a")
        commit_spec(root, "b")
        raw_queue(root, "lista", "source:\n- docs/spec/a.md\n")
        old_queue(root, "ok", "docs/spec/b.md")
        p = cli(root, "archive")
        check("list: exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("list: both queues archived",
              (archived(root, "lista") / "queue.yaml").is_file()
              and (archived(root, "ok") / "queue.yaml").is_file(), p.stdout)
        check("list: its spec does not move", (root / SPEC_DIR / "a.md").is_file()
              and not archived_spec(root, "a").exists())
        check("list: the other queue's spec still moves", archived_spec(root, "b").is_file()
              and not (root / SPEC_DIR / "b.md").exists(), p.stdout + p.stderr)
        check("list: no containment warning", "aviso: as especificações" not in p.stderr,
              p.stderr)
        check("list: tree clean", git(root, "status", "--porcelain").strip() == "")
    # (b) a slug starting with `_` never moves
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "_x")
        old_queue(root, "q", "docs/spec/_x.md")
        p = cli(root, "archive")
        check("underscore: exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("underscore: spec stays", (root / SPEC_DIR / "_x.md").is_file()
              and not archived_spec(root, "_x").exists(), p.stdout)
        check("underscore: source untouched", source_of(root, "q") == "docs/spec/_x.md")
    # (c) the path must end there: `a.md.bak` is not `a.md`
    for src in ("docs/spec/a.md.bak", "docs/spec/a.mdx"):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_repo(tmp)
            commit_spec(root, "a")
            old_queue(root, "q", src)
            p = cli(root, "archive")
            check(f"{src}: exits 0", p.returncode == 0, p.stdout + p.stderr)
            check(f"{src}: a.md stays", (root / SPEC_DIR / "a.md").is_file()
                  and not archived_spec(root, "a").exists(), p.stdout)
            check(f"{src}: says nothing about a spec (a.md is not what it cites)",
                  "especificação" not in p.stdout, p.stdout)
            check(f"{src}: source untouched", source_of(root, "q") == src)
    # a slug that is a prefix of another: only the cited one moves
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "a")
        commit_spec(root, "ab")
        old_queue(root, "q", "docs/spec/ab.md")
        p = cli(root, "archive")
        check("prefix: ab moved", archived_spec(root, "ab").is_file(), p.stdout)
        check("prefix: a stays", (root / SPEC_DIR / "a.md").is_file()
              and not archived_spec(root, "a").exists())
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "a")
        commit_spec(root, "ab")
        old_queue(root, "fechada", "docs/spec/a.md")
        old_queue(root, "aberta", "docs/spec/ab.md", days=3, statuses=("done", "pending"))
        p = cli(root, "archive")
        check("prefix, open citer of ab: a moved", archived_spec(root, "a").is_file(), p.stdout)
        check("prefix, open citer of ab: ab stays", (root / SPEC_DIR / "ab.md").is_file()
              and not archived_spec(root, "ab").exists(), p.stdout)


def test_unreadable_open_queue_that_cites_the_spec_keeps_it():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "a")
        old_queue(root, "fechada", "docs/spec/a.md")
        d = queue_dir(root, "quebrada")
        d.mkdir(parents=True)
        (d / "queue.yaml").write_text("source: docs/spec/a.md (parte 2)\nitems: [\n",
                                      encoding="utf-8")
        commit(root, "quebrada", days_ago(3), f"{NEW}/quebrada")
        p = cli(root, "archive")
        check("exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("the closed queue moved", (archived(root, "fechada") / "queue.yaml").is_file())
        check("spec stays", (root / SPEC_DIR / "a.md").is_file()
              and not archived_spec(root, "a").exists(), p.stdout)
        check("output names the unreadable open queue",
              "a fila quebrada ainda a cita" in p.stdout, p.stdout)
        check("source untouched", source_of(root, "fechada") == "docs/spec/a.md")


def test_dry_run_judges_like_the_real_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "comum")
        old_queue(root, "um", "docs/spec/comum.md")
        old_queue(root, "dois", "docs/spec/comum.md (parte 2)")
        p = cli(root, "archive", "--dry-run")
        check("both eligible: exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("both eligible: dry-run says it would take the spec",
              "(dry-run) levaria a especificação docs/spec/comum.md" in p.stdout, p.stdout)
        check("both eligible: no 'não movida'", "especificação não movida" not in p.stdout,
              p.stdout)
        check("both eligible: nothing moved", (root / SPEC_DIR / "comum.md").is_file()
              and queue_dir(root, "um").is_dir() and queue_dir(root, "dois").is_dir())
        check("both eligible: tree clean", git(root, "status", "--porcelain").strip() == "")
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "comum")
        old_queue(root, "um", "docs/spec/comum.md")
        old_queue(root, "dois", "docs/spec/comum.md (parte 2)")
        old_queue(root, "terceira", "docs/spec/comum.md (parte 3)", days=3,
                  statuses=("done", "pending"))
        p = cli(root, "archive", "--dry-run")
        check("third still open: dry-run says the spec stays",
              "especificação não movida" in p.stdout and "a fila terceira ainda a cita"
              in p.stdout, p.stdout)
        check("third still open: no 'levaria'", "levaria a especificação" not in p.stdout,
              p.stdout)


def test_one_failing_spec_does_not_stop_the_sweep():
    # (a) the folded-source spec fails, in both orders, and the other still moves
    for failing, fine in (("a-bad", "b-good"), ("b-bad", "a-good")):
        with tempfile.TemporaryDirectory() as tmp:
            root = new_repo(tmp)
            commit_spec(root, "ruim")
            commit_spec(root, "boa")
            raw_queue(root, failing, "source: >-\n  docs/spec/ruim.md\n")
            old_queue(root, fine, "docs/spec/boa.md")
            p = cli(root, "archive")
            tag = f"[{failing}] "
            check(tag + "exits 0", p.returncode == 0, p.stdout + p.stderr)
            check(tag + "failing spec stays", (root / SPEC_DIR / "ruim.md").is_file()
                  and not archived_spec(root, "ruim").exists(), p.stdout)
            check(tag + "the other spec moved", archived_spec(root, "boa").is_file()
                  and not (root / SPEC_DIR / "boa.md").exists(), p.stdout)
            files = head_files(root)
            check(tag + "commit holds the good spec", "docs/spec/_archive/boa.md" in files,
                  str(files))
            check(tag + "tree clean", git(root, "status", "--porcelain").strip() == "")
    # (b) docs/spec/_archive is a regular file: the move fails, the queues are
    # still archived and committed
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        (root / SPEC_DIR / "_archive").write_text("sou um arquivo\n")
        commit(root, "arquivo no lugar da pasta", days_ago(30), f"{SPEC_DIR}/_archive")
        old_queue(root, "velha", "docs/spec/velha.md")
        p = cli(root, "archive")
        check("_archive is a file: exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("_archive is a file: spec stays, unchanged",
              (root / SPEC_DIR / "velha.md").read_text() == TWO_PENDING)
        check("_archive is a file: says the spec was not moved",
              "especificação não movida" in p.stdout and "FileExistsError" in p.stdout,
              p.stdout)
        check("_archive is a file: queue archived and committed",
              ".claude/queues/_archive/velha/queue.yaml" in head_files(root))
        check("_archive is a file: source untouched",
              source_of(root, "velha") == "docs/spec/velha.md")
        check("_archive is a file: tree clean", git(root, "status", "--porcelain").strip() == "")


def test_spec_step_raises_outside_the_per_spec_guard():
    # Reaching the `try/except` in cmd_archive needs an error that the per-spec
    # guard does not see: the first read of the archived queue.yaml, in the loop
    # that groups the queues by spec. A sitecustomize shim (apart from the repo
    # under test) makes Path.read_text raise for a queue.yaml under `_archive`.
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as shim:
        root = new_repo(tmp)
        commit_spec(root, "velha")
        old_queue(root, "velha", "docs/spec/velha.md")
        old_queue(root, "outra", "teste")
        (Path(shim) / "sitecustomize.py").write_text(
            "import pathlib\n"
            "_real = pathlib.Path.read_text\n"
            "def _read_text(self, *a, **k):\n"
            "    if '_archive' in self.parts and self.name == 'queue.yaml':\n"
            "        raise RuntimeError('leitura forcada a falhar')\n"
            "    return _real(self, *a, **k)\n"
            "pathlib.Path.read_text = _read_text\n", encoding="utf-8")
        env = dict(ENV, PYTHONPATH=shim + os.pathsep + ENV.get("PYTHONPATH", ""))
        p = subprocess.run([sys.executable, str(CEPA_PLAN), "archive", "--repo", str(root)],
                           capture_output=True, text=True, cwd=root, env=env, timeout=60)
        check("exits 0", p.returncode == 0, p.stdout + p.stderr)
        check("warns that the specs were not moved",
              "aviso: as especificações não foram movidas" in p.stderr
              and "RuntimeError" in p.stderr, p.stderr)
        check("both queues archived",
              (archived(root, "velha") / "queue.yaml").is_file()
              and (archived(root, "outra") / "queue.yaml").is_file(), p.stdout)
        check("spec stays", (root / SPEC_DIR / "velha.md").is_file()
              and not archived_spec(root, "velha").exists())
        files = head_files(root)
        check("the queues are committed", ".claude/queues/_archive/velha/queue.yaml" in files
              and ".claude/queues/_archive/outra/queue.yaml" in files, str(files))
        check("tree clean", git(root, "status", "--porcelain").strip() == "")



def main():
    for t in (test_declared_red_test, test_trailing_text_and_other_citations_untouched,
              test_wording_for_one_and_zero, test_other_open_queue_keeps_the_spec,
              test_all_citers_archived_in_one_sweep_or_before, test_dry_run_and_no_commit,
              test_commit_leaves_strangers_out, test_spec_missing, test_destination_taken,
              test_spec_with_uncommitted_changes, test_only_docs_spec_slug_paths_move,
              test_help_mentions_the_spec_move, test_count_fails_after_the_move,
              test_rollback_when_a_source_rewrite_fails,
              test_rollback_single_folded_queue_and_earlier_queue,
              test_unrelated_archived_queues_are_left_alone,
              test_dot_slash_and_quoted_sources, test_spec_slug_guards,
              test_unreadable_open_queue_that_cites_the_spec_keeps_it,
              test_dry_run_judges_like_the_real_run,
              test_one_failing_spec_does_not_stop_the_sweep,
              test_spec_step_raises_outside_the_per_spec_guard):
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
