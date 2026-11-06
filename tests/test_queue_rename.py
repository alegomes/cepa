#!/usr/bin/env python3
"""Tests of the single-track queue rename (owner's decision, 2026-10-20):

    .claude/programs/<n>/plan.yaml  (key `program:`, /common:plan)
 -> .claude/queues/<n>/queue.yaml   (key `queue:`,   /common:queue)

During the transition every consumer READS both layouts and `cepa-plan migrate`
moves the existing queues. Each test calls the real binary (subprocess)
in a temporary git repo, like the neighbors (`test_cepa_plan_write_commits.py`).

Run with `python3 tests/test_queue_rename.py` or with pytest (each test creates its
own temporary directory).

What these tests do NOT prove: that the compass panel (TypeScript) reads both
layouts — it has its own runner (`claude plugin test`); nor that the
`/common:queue` command converses right, which is prompt.
"""

import importlib.machinery
import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"
MAESTRO_PROGRAMS = REPO / "maestro" / "bin" / "maestro-programs"


def run(script, repo, *args):
    return subprocess.run([sys.executable, str(script)] + list(args),
                          capture_output=True, text=True, cwd=str(repo))


def plan(repo, *args):
    return run(CEPA_PLAN, repo, *args)


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo)] + list(args),
                          capture_output=True, text=True, check=True).stdout


def new_repo(base, name="r"):
    d = Path(base) / name
    d.mkdir(parents=True)
    git(d, "init", "-q")
    git(d, "config", "user.email", "t@t")
    git(d, "config", "user.name", "t")
    (d / "README").write_text("x\n")
    git(d, "add", "README")
    git(d, "commit", "-q", "-m", "init")
    return d


def item(ident, **kw):
    base = {"id": ident, "title": f"item {ident}", "why": f"porque {ident}",
            "status": "pending", "blocked_by": [], "human_pending": None}
    base.update(kw)
    return base


def write_items(d, items):
    p = Path(d) / "itens.json"
    p.write_text(json.dumps(items), encoding="utf-8")
    return p


LEGACY = """\
# comentario que a migracao nao pode perder
schema_version: 2
mode: single-track
program: {nome}
source: teste
items:
- id: A
  title: item A
  why: porque A
  status: pending
  blocked_by: []
  human_pending: null
"""


def legacy_queue(d, name="x", text=None, commit_all=True, bak=True):
    """A queue in the old layout, written by hand, with `until/` and `.bak` beside it."""
    folder = Path(d) / ".claude" / "programs" / name
    (folder / "until").mkdir(parents=True)
    (folder / "plan.yaml").write_text(text or LEGACY.format(nome=name),
                                     encoding="utf-8")
    (folder / "until" / "2026-10-20-0900.jsonl").write_text("{}\n")
    if bak:
        (folder / "plan.yaml.bak").write_text("# anterior\n")
    if commit_all:
        git(d, "add", "-f", ".claude")
        git(d, "commit", "-q", "-m", "fila legada")
    return folder


def with_repo(fn):
    def body():
        with tempfile.TemporaryDirectory() as base:
            fn(new_repo(base))
    body.__name__ = fn.__name__
    return body


# ── (a) a new queue is born in the new layout ────────────────────────────────

@with_repo
def test_new_queue_is_born_in_queues(d):
    r = plan(d, "write", "fila", "--items", str(write_items(d, [item("A")])),
             "--source", "t", "--quando", "2026-10-20", "--repo", ".")
    assert r.returncode == 0, r.stderr
    new = d / ".claude" / "queues" / "fila" / "queue.yaml"
    assert new.is_file(), r.stdout
    assert not (d / ".claude" / "programs" / "fila").exists()
    data = yaml.safe_load(new.read_text(encoding="utf-8"))
    assert data.get("queue") == "fila" and "program" not in data, data
    assert plan(d, "validate", str(new)).returncode == 0
    r = plan(d, "status", "fila", "--json", "--repo", ".")
    output = json.loads(r.stdout)
    assert output["queue"] == "fila" and output["program"] == "fila", output


# ── (b) a legacy queue is still read and marked in place ────────────────────

@with_repo
def test_legacy_queue_is_read_and_marked_in_place(d):
    folder = legacy_queue(d, commit_all=False)
    r = plan(d, "queue", "x", "--json", "--repo", ".")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["path"].endswith("programs/x/plan.yaml")
    assert plan(d, "start", "x", "A", "--repo", ".").returncode == 0
    r = plan(d, "finish", "x", "A", "--status", "done", "--evidence", "ok",
             "--repo", ".")
    assert r.returncode == 0, r.stderr
    data = yaml.safe_load((folder / "plan.yaml").read_text(encoding="utf-8"))
    assert data["items"][0]["status"] == "done"
    assert data.get("program") == "x", "a chave antiga segue até migrar"
    assert not (d / ".claude" / "queues").exists()
    # rewriting a legacy queue keeps its file and key
    r = plan(d, "write", "x", "--items", str(write_items(d, [item("A"), item("B")])),
             "--repo", ".")
    assert r.returncode == 0, r.stderr
    assert (folder / "plan.yaml.bak").is_file()
    assert yaml.safe_load((folder / "plan.yaml").read_text())["program"] == "x"
    assert not (d / ".claude" / "queues").exists()


# ── (c) same name in both layouts: the new one wins ─────────────────────────

@with_repo
def test_name_in_both_layouts_the_new_wins(d):
    legacy_queue(d, commit_all=False)
    new = d / ".claude" / "queues" / "x"
    new.mkdir(parents=True)
    (new / "queue.yaml").write_text(
        LEGACY.format(nome="x").replace("program:", "queue:").replace("item A", "item NOVO"),
        encoding="utf-8")
    r = plan(d, "status", "x", "--json", "--repo", ".")
    assert r.returncode == 0, r.stderr
    output = json.loads(r.stdout)
    assert output["path"].endswith("queues/x/queue.yaml"), output["path"]
    assert output["items"][0]["title"] == "item NOVO"


# ── (d) migrate ──────────────────────────────────────────────────────────────

@with_repo
def test_migrate_moves_renames_rewrites_commits_and_is_idempotent(d):
    legacy_queue(d)
    before = git(d, "rev-list", "--count", "HEAD").strip()
    r = plan(d, "migrate", "--all", "--dry-run", "--repo", ".")
    assert r.returncode == 0 and "x" in r.stdout, r.stdout + r.stderr
    assert (d / ".claude" / "programs" / "x" / "plan.yaml").is_file(), \
        "--dry-run não move nada"

    r = plan(d, "migrate", "--all", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    new = d / ".claude" / "queues" / "x"
    assert not (d / ".claude" / "programs" / "x").exists()
    assert (new / "queue.yaml").is_file() and not (new / "plan.yaml").exists()
    assert (new / "queue.yaml.bak").is_file()
    assert (new / "until" / "2026-10-20-0900.jsonl").is_file()
    text = (new / "queue.yaml").read_text(encoding="utf-8")
    assert text.startswith("# comentario que a migracao nao pode perder\n"), text
    assert "\nqueue: x\n" in text and "program:" not in text, text
    assert git(d, "rev-list", "--count", "HEAD").strip() == str(int(before) + 1), \
        "um commit só"
    assert git(d, "status", "--porcelain").strip() == "", git(d, "status", "--porcelain")

    r = plan(d, "migrate", "--all", "--repo", ".")
    assert r.returncode == 0 and "nada a migrar" in r.stdout, r.stdout + r.stderr
    assert git(d, "rev-list", "--count", "HEAD").strip() == str(int(before) + 1)
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr


# ── (e) migrate skips waves and refuses an existing destination ─────────────

@with_repo
def test_migrate_skips_waves_and_refuses_existing_destination(d):
    waves = d / ".claude" / "programs" / "ondas"
    waves.mkdir(parents=True)
    (waves / "plan.yaml").write_text(yaml.dump(
        {"schema_version": 2, "mode": "parallel-waves", "program": "ondas",
         "waves": []}), encoding="utf-8")
    r = plan(d, "migrate", "--all", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (waves / "plan.yaml").is_file() and not (d / ".claude" / "queues").exists()
    r = plan(d, "migrate", "ondas", "--repo", ".")
    assert r.returncode != 0 and (waves / "plan.yaml").is_file()

    folder = legacy_queue(d, commit_all=False)
    (d / ".claude" / "queues" / "x").mkdir(parents=True)
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode != 0 and "já existe" in r.stderr, r.stderr
    assert (folder / "plan.yaml").is_file(), "nada foi movido"
    assert "program: x" in (folder / "plan.yaml").read_text()


# ── (f) migrate refuses a live reservation ───────────────────────────────────

@with_repo
def test_migrate_refuses_live_reservation(d):
    owner = {"session_id": "S-VIVA", "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "started_at": datetime.now(timezone.utc).isoformat()}
    text = LEGACY.format(nome="x").replace(
        "  status: pending\n",
        "  status: in_progress\n  claimed_by: " + json.dumps(owner) + "\n")
    folder = legacy_queue(d, text=text)
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode != 0 and "VIVA" in r.stderr, r.stdout + r.stderr
    assert (folder / "plan.yaml").is_file()
    assert not (d / ".claude" / "queues").exists()

    # orphan reservation (dead pid) does not hold the migration
    dead = dict(owner, pid=2 ** 22 + 12345, session_id="S-MORTA")
    (folder / "plan.yaml").write_text(text.replace(json.dumps(owner), json.dumps(dead)),
                                     encoding="utf-8")
    git(d, "commit", "-q", "-am", "reserva órfã")
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (d / ".claude" / "queues" / "x" / "queue.yaml").is_file()


# ── (f2) migrate refuses a live cepa-until run, even between items ──────────

def _running_state(folder, pid):
    (folder / "until" / "2026-10-20-2055.estado.json").write_text(json.dumps(
        {"estado": "rodando", "pid": pid, "host": socket.gethostname(),
         "run": "2026-10-20-2055"}), encoding="utf-8")


@with_repo
def test_migrate_refuses_live_cepa_until_run(d):
    folder = legacy_queue(d)
    fake = subprocess.Popen(["bash", "-c", "exec -a cepa-until sleep 60"])
    try:
        _running_state(folder, fake.pid)
        r = plan(d, "migrate", "x", "--repo", ".")
        assert r.returncode != 0 and "cepa-until" in r.stderr, r.stdout + r.stderr
        assert (folder / "plan.yaml").is_file()
        assert not (d / ".claude" / "queues").exists()
    finally:
        fake.kill()
        fake.wait()
    _running_state(folder, fake.pid)  # now dead
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (d / ".claude" / "queues" / "x" / "queue.yaml").is_file()


# ── (f3) migrate refuses a queue with an uncommitted change ─────────────────

@with_repo
def test_migrate_refuses_uncommitted_queue(d):
    folder = legacy_queue(d)
    with open(folder / "plan.yaml", "a", encoding="utf-8") as f:
        f.write("# status mexido e não commitado\n")
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode != 0 and "não commitadas" in r.stderr, r.stdout + r.stderr
    assert (folder / "plan.yaml").is_file()
    assert not (d / ".claude" / "queues").exists()


# ── (f4) a queue without `program:` at the top gets `queue:` on migration ───

@with_repo
def test_migrate_queue_without_key_gets_queue(d):
    legacy_queue(d, text=LEGACY.format(nome="x").replace("program: x\n", ""))
    r = plan(d, "migrate", "x", "--repo", ".")
    assert r.returncode == 0, r.stdout + r.stderr
    text = (d / ".claude" / "queues" / "x" / "queue.yaml").read_text()
    assert text.startswith("# comentario que a migracao nao pode perder\n"), text
    assert yaml.safe_load(text)["queue"] == "x", text


# ── (g) cepa-until: dirt ignores the record in both layouts ─────────────────

def load_until():
    loader = importlib.machinery.SourceFileLoader("cepa_until_qr", str(CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_until_qr", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_cepa_until_dirt_filters_accept_both_layouts():
    cu = load_until()
    for base, filename in ((".claude/programs", "plan.yaml"), (".claude/queues", "queue.yaml")):
        assert cu.RUN_RECORD.match(f"?? {base}/f/until/2026-10-20-0900.jsonl"), base
        assert cu.QUEUE_BAK.match(f"?? {base}/f/{filename}.bak"), base
        m = cu.PLAN_MODIFIED.match(f" M {base}/f/{filename}")
        assert m and m.group(1) == f"{base}/f/{filename}", base
        assert (m.group(2) or m.group(3)) == "f", base
    assert not cu.QUEUE_BAK.match("?? .claude/queues/f/plan.yaml.bak")
    assert not cu.RUN_RECORD.match("?? .claude/outro/f/until/x")


@with_repo
def test_cepa_until_dirty_tree_ignores_record_and_bak_of_both_layouts(d):
    cu = load_until()
    # with something tracked in .claude/ git lists each untracked file
    for base in ("programs", "queues"):
        (d / ".claude" / base / "f" / "until").mkdir(parents=True)
        (d / ".claude" / base / "f" / "keep").write_text("x\n")
    git(d, "add", "-f", ".claude")
    git(d, "commit", "-q", "-m", "keep")
    for base, filename in (("programs", "plan.yaml"), ("queues", "queue.yaml")):
        folder = d / ".claude" / base / "f"
        (folder / "until" / "2026-10-20-0900.jsonl").write_text("{}\n")
        (folder / (filename + ".bak")).write_text("x\n")
    assert cu.dirty_tree(d) == [], cu.dirty_tree(d)
    (d / "sujeira.txt").write_text("x\n")
    assert [l for l in cu.dirty_tree(d)] == ["?? sujeira.txt"]


@with_repo
def test_cepa_until_resolves_ledger_and_queue_through_the_resolver(d):
    cu = load_until()
    assert cu.qp.queue_dir(d, "f") == d / ".claude" / "queues" / "f"
    legacy_queue(d, name="f", commit_all=False)
    assert cu.qp.queue_dir(d, "f") == d / ".claude" / "programs" / "f"
    (d / ".claude" / "queues" / "f").mkdir(parents=True)
    (d / ".claude" / "queues" / "f" / "queue.yaml").write_text("queue: f\n")
    assert cu.qp.queue_dir(d, "f") == d / ".claude" / "queues" / "f"
    assert cu.qp.queue_name_of({"queue": "a", "program": "b"}) == "a"
    assert cu.qp.queue_name_of({"program": "b"}) == "b"
    assert cu.qp.queue_name_of({}, "z") == "z"


# ── (h) maestro-programs --check-name sees the new layout ───────────────────

@with_repo
def test_maestro_programs_check_name_refuses_new_queue_name(d):
    folder = d / ".claude" / "queues" / "minha"
    folder.mkdir(parents=True)
    (folder / "queue.yaml").write_text(
        LEGACY.format(nome="minha").replace("program:", "queue:"), encoding="utf-8")
    r = run(MAESTRO_PROGRAMS, d, str(d), "--check-name", "minha")
    assert r.returncode == 3, r.stdout + r.stderr
    assert "minha" in r.stderr
    r = run(MAESTRO_PROGRAMS, d, str(d), "--check-name", "livre")
    assert r.returncode == 0, r.stderr
    r = run(MAESTRO_PROGRAMS, d, str(d), "--json")
    names = [p["nome"] for p in json.loads(r.stdout)["programas"]]
    assert "minha" in names, names


@with_repo
def test_cepa_plan_check_name_sees_legacy_wave(d):
    waves = d / ".claude" / "programs" / "ondas"
    waves.mkdir(parents=True)
    (waves / "plan.yaml").write_text(yaml.dump(
        {"schema_version": 2, "mode": "parallel-waves", "program": "ondas",
         "waves": []}), encoding="utf-8")
    assert plan(d, "check-name", "ondas", "--repo", ".").returncode == 3
    r = plan(d, "write", "ondas", "--items", str(write_items(d, [item("A")])),
             "--repo", ".")
    assert r.returncode == 3, "plano de ondas no caminho antigo segue recusado"
    assert not (d / ".claude" / "queues").exists()


# ── (i) the command ──────────────────────────────────────────────────────────

def test_queue_command_exists_and_plan_is_alias():
    q = REPO / "common" / "commands" / "queue.md"
    p = REPO / "common" / "commands" / "plan.md"
    assert q.is_file() and p.is_file()
    qt, pt = q.read_text(encoding="utf-8"), p.read_text(encoding="utf-8")
    assert qt.splitlines()[0] == "---" and "# /common:queue" in qt
    assert "/common:plan" not in qt.split("## Purpose")[1], \
        "o corpo do /common:queue não pode mandar o leitor de volta ao nome velho"
    assert "/common:queue" in pt and "renamed" in pt.lower()
    assert len(pt.splitlines()) < 30, "o alias é curto; os passos moram no queue.md"
    cat = (REPO / "docs" / "commands.md").read_text(encoding="utf-8")
    assert "| `/common:queue` |" in cat and "| `/common:plan` |" in cat


def test_doctor_warns_name_in_both_layouts_and_suggests_migrating():
    with tempfile.TemporaryDirectory() as base:
        d = new_repo(base)
        legacy_queue(d, commit_all=False)
        loader = importlib.machinery.SourceFileLoader(
            "cepa_doctor_qr", str(REPO / "common" / "bin" / "cepa-doctor"))
        spec = importlib.util.spec_from_loader("cepa_doctor_qr", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        mod.RESULTS.clear()
        mod.check_queue_layout(d)
        assert any("migrate --all" in m for _, _, m, _ in mod.RESULTS), mod.RESULTS
        new = d / ".claude" / "queues" / "x"
        new.mkdir(parents=True)
        (new / "queue.yaml").write_text("queue: x\nmode: single-track\n")
        mod.RESULTS.clear()
        mod.check_queue_layout(d)
        assert any(k == "warn" and "dois layouts" in m for k, _, m, _ in mod.RESULTS), \
            mod.RESULTS



# ── (j) proof gaps: consumers of the NEW layout ─────────────────────────────
# Each test below exists because a perturbation of docs/proof/
# rename-to-queue.yaml survived with the suite green (id in brackets).

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shutil  # noqa: E402

DOCTOR = REPO / "common" / "bin" / "cepa-doctor"
DIGEST = REPO / "common" / "bin" / "cepa-until-digest"


def to_new_layout(root, name="fila"):
    """Converts the queue `name` of a repo built by `build_repo` (which writes
    in the old layout) to `.claude/queues/<name>/queue.yaml` with `queue:`, and
    commits.
    """
    old = Path(root) / ".claude" / "programs" / name
    new = Path(root) / ".claude" / "queues" / name
    new.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old), str(new))
    (new / "plan.yaml").rename(new / "queue.yaml")
    data = yaml.safe_load((new / "queue.yaml").read_text(encoding="utf-8"))
    data["queue"] = data.pop("program")
    (new / "queue.yaml").write_text(yaml.safe_dump(data, allow_unicode=True),
                                     encoding="utf-8")
    shutil.rmtree(Path(root) / ".claude" / "programs", ignore_errors=True)
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
        "fila no layout novo")


# [R4] queue_files: name in both layouts, the new one wins (directly and through the CLI)

def test_queue_files_name_in_both_layouts_returns_the_new_path():
    qp = load_until().qp
    with tempfile.TemporaryDirectory() as base:
        d = new_repo(base)
        legacy_queue(d, name="x", commit_all=False)
        legacy_queue(d, name="so-velha", commit_all=False)
        new = d / ".claude" / "queues" / "x"
        new.mkdir(parents=True)
        (new / "queue.yaml").write_text("queue: x\n")
        findings = dict(qp.queue_files(d))
        assert findings["x"] == new / "queue.yaml", findings
        assert findings["so-velha"].name == "plan.yaml", findings
        assert [n for n, _ in qp.queue_files(d)] == ["so-velha", "x"]


@with_repo
def test_cepa_plan_status_without_name_picks_the_new_queue_when_the_name_is_in_both(d):
    legacy_queue(d, name="x", commit_all=False)
    new = d / ".claude" / "queues" / "x"
    new.mkdir(parents=True)
    (new / "queue.yaml").write_text(
        LEGACY.format(nome="x").replace("program:", "queue:").replace("item A", "item NOVO"),
        encoding="utf-8")
    # no name: the list of candidates comes from queue_files; it is what chooses the file
    r = plan(d, "status", "--json", "--repo", ".")
    assert r.returncode == 0, r.stderr
    output = json.loads(r.stdout)
    assert output["path"].endswith("queues/x/queue.yaml"), output["path"]
    assert output["items"][0]["title"] == "item NOVO"


# [W3] overwriting a queue of the new layout: the backup is queue.yaml.bak

@with_repo
def test_cepa_plan_overwriting_new_queue_makes_backup_queue_yaml_bak(d):
    items = write_items(d, [item("A")])
    r = plan(d, "write", "fila", "--items", str(items), "--repo", ".")
    assert r.returncode == 0, r.stderr
    folder = d / ".claude" / "queues" / "fila"
    assert (folder / "queue.yaml").is_file()
    assert not (folder / "queue.yaml.bak").exists()
    before = (folder / "queue.yaml").read_text(encoding="utf-8")
    items = write_items(d, [item("A"), item("B")])
    r = plan(d, "write", "fila", "--items", str(items), "--repo", ".")
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in folder.iterdir() if p.is_file()) == \
        ["queue.yaml", "queue.yaml.bak"], list(folder.iterdir())
    assert (folder / "queue.yaml.bak").read_text(encoding="utf-8") == before


# [U4 U5 U6 G1] cepa-until with a queue in the new layout, end to end

def test_cepa_until_dry_run_new_queue_header_and_ledger_dir():
    """[G1] the header shows the name coming from `queue:`; [U6] the record
    folder is born in queues/<n>/until, and not in programs/.
    """
    from test_cepa_until import build_repo, item as it
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [it("a1")])
        to_new_layout(root)
        r = subprocess.run([sys.executable, str(CEPA_UNTIL), "fila", "--repo",
                            str(root), "--for", "1h", "--dry-run", "--sem-verify",
                            "--sem-analise"], capture_output=True, text=True,
                           cwd=str(root), timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        first_line = r.stdout.splitlines()[0]
        assert "queue fila" in first_line.replace("\x1b[36m", "").replace("\x1b[0m", ""), \
            first_line
        assert (root / ".claude" / "queues" / "fila" / "until").is_dir()
        assert not (root / ".claude" / "programs").exists()


def test_cepa_until_header_shows_queue_name_with_only_queue():
    """[G1] `cepa-plan queue` today returns `program` AND `queue`; if one day it only
    returns `queue:`, the header must keep showing the name. Calls the real
    `main()`, with the queue query returning only `queue`.
    """
    import contextlib
    import io
    from test_cepa_until import build_repo, item as it
    cu = load_until()
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [it("a1")])
        to_new_layout(root)
        real = cu.query_queue

        def only_queue(name, repo):
            data, error = real(name, repo)
            data.pop("program", None)
            data["queue"] = "NOME-GRAVADO"
            return data, error
        cu.query_queue = only_queue
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = cu.main(["fila", "--repo", str(root), "--for", "1h", "--dry-run",
                          "--sem-verify", "--sem-analise"])
        assert rc == 0, output.getvalue()
        assert "NOME-GRAVADO" in output.getvalue().splitlines()[0], output.getvalue()[:300]
        assert (root / ".claude" / "queues" / "fila" / "until").is_dir()


def test_cepa_until_run_landing_pending_and_doctor_see_new_queue():
    """[U6] ledger and log in queues/<n>/until; [U5] the live run there is found by
    `pendentes` and by the doctor ([D5]: repo with only .claude/queues); [U4] the queue
    dirty in the clone, in the new layout, does not prevent `aterrissar`.
    """
    from test_cepa_until import fake_claude, item as it, build_repo, run_until
    from test_cepa_until_run_branch import WORKS, VERIFY
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [it("a1")])
        to_new_layout(root)
        binv = fake_claude(Path(tmp), WORKS)
        plan_file = root / ".claude" / "queues" / "fila" / "queue.yaml"
        run_until(root, binv, plan_file, ["--for", "2h", "--verify", VERIFY])
        until = root / ".claude" / "queues" / "fila" / "until"
        assert list(until.glob("*.jsonl")) and list(until.glob("*.log")), list(until.glob("*"))
        assert not (root / ".claude" / "programs").exists()
        run_id = sorted(until.glob("*.jsonl"))[-1].stem
        assert "status: done" in plan_file.read_text(), "a fila do clone foi marcada (suja)"
        assert git(root, "status", "--porcelain").count("queues/fila/queue.yaml") == 1

        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "pendentes",
                            "--repo", str(root)], capture_output=True, text=True,
                           cwd=str(root), timeout=60)
        assert f"cepa-until aterrissar fila/{run_id}" in p.stdout, p.stdout + p.stderr

        d = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(root), capture_output=True, text=True,
                           timeout=120, env=dict(os.environ, CEPA_DOCTOR_INSTALL="off"))
        out = d.stdout + d.stderr
        assert "[until]" in out and f"cepa-until aterrissar fila/{run_id}" in out, out[-1500:]

        (root / ".claude" / "doctor-last-run").unlink(missing_ok=True)  # doctor trace
        env = dict(os.environ, CEPA_WORKTREE_HOME=str(Path(tmp) / "worktrees"))
        a = subprocess.run([sys.executable, str(CEPA_UNTIL), "aterrissar",
                            f"fila/{run_id}", "--repo", str(root), "--sim"],
                           capture_output=True, text=True, cwd=str(root), env=env,
                           timeout=120)
        assert a.returncode == 0, a.stdout + a.stderr
        assert "mudança sem commit" not in a.stderr


# [U7 U8] cepa-until-digest with the record in queues/<n>/until

def _build_new_run(tmp):
    from test_cepa_until_digest import build_run
    ledger = build_run(tmp)
    old = Path(tmp) / ".claude" / "programs" / "F"
    new = Path(tmp) / ".claude" / "queues" / "F"
    new.parent.mkdir(parents=True)
    shutil.move(str(old), str(new))
    (new / "plan.yaml").rename(new / "queue.yaml")
    return new / "until" / ledger.name, new / "queue.yaml"


def test_digest_reads_neighbor_file_queue_yaml_outside_git_repo():
    """[U8] without git, the queue is the file beside the record: queue.yaml."""
    with tempfile.TemporaryDirectory() as tmp:
        ledger, filename = _build_new_run(tmp)
        p = subprocess.run([sys.executable, str(DIGEST), str(ledger)],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        assert "depende do A1 que não está na main" in p.stdout, p.stdout[-900:]
        assert "queue.yaml" in p.stdout, p.stdout[-900:]


def test_digest_reads_the_main_clone_queue_in_new_layout():
    """[U7] with the record in a worktree, the real queue is the one of the main
    clone in queues/<n>/queue.yaml (the worktree's copy is stale).
    """
    from test_cepa_until_digest import build_run
    with tempfile.TemporaryDirectory() as tmp:
        main_clone = Path(tmp) / "principal"
        main_clone.mkdir()
        git(main_clone, "init", "-q")
        git(main_clone, "-c", "user.email=t@t", "-c", "user.name=t", "commit",
            "-q", "--allow-empty", "-m", "raiz")
        wt = Path(tmp) / "wt"
        git(main_clone, "worktree", "add", "-q", "--detach", str(wt))
        ledger, copied = _build_new_run(wt)
        queue = main_clone / ".claude" / "queues" / "F"
        queue.mkdir(parents=True)
        (queue / "queue.yaml").write_text(yaml.safe_dump({"items": [
            {"id": "A1", "status": "done", "blocked_by": [], "evidence": "ok"},
            {"id": "A2", "status": "done", "blocked_by": [],
             "evidence": "FECHADO NO CLONE PRINCIPAL"}]}), encoding="utf-8")
        p = subprocess.run([sys.executable, str(DIGEST), str(ledger)],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        assert "FECHADO NO CLONE PRINCIPAL" in p.stdout, p.stdout[-900:]
        assert "depende do A1 que não está na main" not in p.stdout
        assert str(queue / "queue.yaml") in p.stdout or \
            str((queue / "queue.yaml").resolve()) in p.stdout, p.stdout[-900:]


# [D4] the doctor CALLS check_queue_layout (through the CLI)

def test_doctor_cli_warns_name_in_both_layouts():
    with tempfile.TemporaryDirectory() as base:
        d = new_repo(base)
        legacy_queue(d, name="x", commit_all=False)
        new = d / ".claude" / "queues" / "x"
        new.mkdir(parents=True)
        (new / "queue.yaml").write_text("queue: x\nmode: single-track\n")
        r = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(d), capture_output=True, text=True, timeout=120,
                           env=dict(os.environ, CEPA_DOCTOR_INSTALL="off"))
        out = r.stdout + r.stderr
        assert "dois layouts" in out, out[-1500:]


# [MP] maestro-programs lists the queues of the new layout

@with_repo
def test_maestro_programs_lists_new_queues_with_waves_and_dedupes(d):
    waves = d / ".claude" / "programs" / "ondas"
    waves.mkdir(parents=True)
    (waves / "plan.yaml").write_text(yaml.dump(
        {"schema_version": 2, "mode": "parallel-waves", "program": "ondas",
         "waves": [{"id": 1, "status": "pending", "slices": []}]}), encoding="utf-8")
    legacy_queue(d, name="dupla", commit_all=False)           # in both layouts
    legacy_queue(d, name="so-velha", commit_all=False)
    for name in ("dupla", "so-nova"):
        folder = d / ".claude" / "queues" / name
        folder.mkdir(parents=True)
        (folder / "queue.yaml").write_text(
            LEGACY.format(nome=name).replace("program:", "queue:"), encoding="utf-8")
    (d / ".claude" / "queues" / "sem-arquivo").mkdir()      # folder without queue.yaml
    r = run(MAESTRO_PROGRAMS, d, str(d), "--json")
    assert r.returncode == 0, r.stderr
    listing = json.loads(r.stdout)["programas"]
    assert len(listing) == len({p["nome"] for p in listing}), \
        f"nome nos dois layouts aparece uma vez só: {[p['nome'] for p in listing]}"
    progs = {p["nome"]: p for p in listing}
    assert sorted(progs) == ["dupla", "ondas", "so-nova", "so-velha"], sorted(progs)
    for name in ("dupla", "so-nova"):
        assert progs[name]["dir"].endswith(f".claude/queues/{name}"), progs[name]
        assert progs[name]["mode"] == "single-track" and not progs[name]["elegivel"]
        assert ".claude/queues" in progs[name]["motivo"]
    assert progs["so-velha"]["dir"].endswith(".claude/programs/so-velha")
    assert progs["ondas"]["elegivel"] is True


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except Exception as e:  # noqa: BLE001
                print(f"FAIL  {name}  {e!r}")
                failures.append(name)
    sys.exit(1 if failures else 0)
