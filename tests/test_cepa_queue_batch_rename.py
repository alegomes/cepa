#!/usr/bin/env python3
"""CS-8 of docs/spec/reforma-de-nomes-dos-comandos.md: the help of `cepa queue`
opens with the owner's subcommands, and `queue` becomes `batch`.

Each test goes through the real CLI (the `cepa` launcher and `cepa-queue`) in a
temporary git repo that has a recorded queue.

Run with `python3 -m pytest tests/test_cepa_queue_batch_rename.py -q`.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"
CEPA_QUEUE = REPO / "common" / "bin" / "cepa-queue"
CEPA_RUN = REPO / "common" / "bin" / "cepa-run"

MARK = "item-marcador-do-lote"
FOR_YOU = ["status", "show", "ready", "waiting", "epics", "answer", "add"]


def _env():
    env = dict(os.environ)
    env["CEPA_PREFLIGHT"] = "off"
    env["NO_COLOR"] = "1"
    return env


def _run(argv, cwd):
    return subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                          cwd=str(cwd), env=_env(), timeout=120)


def _repo_with_queue(base, n=4):
    d = Path(base) / "repo"
    d.mkdir()
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "0"], check=True)
    items = [{"id": f"{MARK}-{i}", "title": f"item {MARK}-{i}", "why": "porque sim",
              "status": "pending", "blocked_by": [], "human_pending": None}
             for i in range(1, n + 1)]
    p = d / "itens.json"
    p.write_text(json.dumps(items), encoding="utf-8")
    r = _run([sys.executable, CEPA_QUEUE, "write", "fila", "--items", p,
              "--source", "teste", "--when", "2026-11-25", "--repo", "."], d)
    assert r.returncode == 0, r.stderr
    return d


def _subcommand_blocks(help_text):
    """{block title: [subcommand names]} of the `subcommands:` section."""
    blocks, cur, inside = {}, None, False
    for ln in help_text.splitlines():
        if ln.startswith("subcommands"):
            inside = True
            continue
        if not inside:
            continue
        if ln and not ln.startswith(" "):
            break
        if ln.startswith("  ") and not ln.startswith("   ") and ln.rstrip().endswith(":"):
            cur = ln.strip()[:-1]
            blocks[cur] = []
        elif ln.startswith("    ") and not ln.startswith("     ") and cur:
            blocks[cur].append(ln.split()[0])
    return blocks


def test_help_opens_with_the_owner_block_then_the_commands_block():
    with tempfile.TemporaryDirectory() as base:
        for argv in ([CEPA, "queue", "--help"], [sys.executable, CEPA_QUEUE, "--help"]):
            r = _run(argv, base)
            assert r.returncode == 0, (argv, r.stderr)
            blocks = _subcommand_blocks(r.stdout)
            assert list(blocks) == ["for you", "used by the commands"], blocks
            assert blocks["for you"] == FOR_YOU, blocks
            rest = blocks["used by the commands"]
            assert "batch" in rest and "start" in rest and "finish" in rest, rest
            assert not set(rest) & set(FOR_YOU), rest
            assert "queue" not in rest, rest
            # nothing falls outside the two blocks
            out = r.stdout.split("subcommands", 1)[1].split("\noptions", 1)[0]
            listed = [ln.split()[0] for ln in out.splitlines()
                      if ln.startswith("  ") and not ln.startswith("   ")]
            assert listed == ["for", "used"], listed


def test_every_subcommand_is_in_one_of_the_two_blocks():
    with tempfile.TemporaryDirectory() as base:
        r = _run([sys.executable, CEPA_QUEUE, "--help"], base)
        blocks = _subcommand_blocks(r.stdout)
        shown = blocks["for you"] + blocks["used by the commands"]
        assert len(shown) == len(set(shown)), shown
        for name in shown:
            h = _run([sys.executable, CEPA_QUEUE, name, "--help"], base)
            assert h.returncode == 0, (name, h.stderr)


def test_batch_prints_what_queue_printed():
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        new = _run([CEPA, "queue", "batch", "fila", "--max", "3", "--repo", "."], d)
        old = _run([sys.executable, CEPA_QUEUE, "queue", "fila", "--max", "3",
                    "--repo", "."], d)
        assert new.returncode == 0 and old.returncode == 0, (new.stderr, old.stderr)
        assert new.stdout == old.stdout, (new.stdout, old.stdout)
        assert f"{MARK}-3" in new.stdout, new.stdout
        jn = _run([CEPA, "queue", "batch", "fila", "--max", "3", "--json", "--repo", "."], d)
        assert jn.returncode == 0, jn.stderr
        data = json.loads(jn.stdout)
        assert [x["id"] for x in data["batch"]] == [f"{MARK}-{i}" for i in (1, 2, 3)], data
        assert data["stop"]["reason"] == "cap" and data["stop"]["item"] == f"{MARK}-4", data


def test_typed_queue_queue_is_refused_with_the_new_name():
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        for argv in ([CEPA, "queue", "queue", "fila", "--repo", "."],
                     [CEPA, "Queue", "QUEUE", "fila", "--max", "3", "--repo", "."]):
            r = _run(argv, d)
            assert r.returncode == 2, (argv, r.returncode, r.stdout, r.stderr)
            assert "queue is now batch" in r.stderr, (argv, r.stderr)
            assert len(r.stderr.strip().splitlines()) == 1, r.stderr
            assert MARK not in r.stdout and MARK not in r.stderr, argv


def test_script_path_keeps_queue_for_runs_in_flight_with_a_note():
    # A slash command loaded before the rename still says
    # `python3 common/bin/cepa-queue queue ...`: it answers, and says the new name.
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        r = _run([sys.executable, CEPA_QUEUE, "queue", "fila", "--max", "1", "--json",
                  "--repo", "."], d)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["batch"][0]["id"] == f"{MARK}-1", r.stdout
        assert "queue is now batch" in r.stderr, r.stderr
        b = _run([sys.executable, CEPA_QUEUE, "batch", "fila", "--max", "1", "--json",
                  "--repo", "."], d)
        assert b.returncode == 0 and "is now" not in b.stderr, b.stderr


def test_supervisor_reads_the_queue_through_batch():
    # `cepa run` asks the queue for its next item with `batch`, not the old name:
    # a copy of common/bin whose cepa-queue records the subcommand it was given.
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        root = Path(base) / "copy" / "common"
        shutil.copytree(REPO / "common" / "bin", root / "bin",
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(REPO / "common" / "hooks", root / "hooks",
                        ignore=shutil.ignore_patterns("__pycache__"))
        real = root / "bin" / "cepa-queue.real"
        (root / "bin" / "cepa-queue").rename(real)
        log = Path(base) / "subcommands"
        (root / "bin" / "cepa-queue").write_text(
            "import os, sys\n"
            f"open({str(log)!r}, 'a').write(sys.argv[1] + '\\n')\n"
            f"os.execv(sys.executable, [sys.executable, {str(real)!r}, *sys.argv[1:]])\n",
            encoding="utf-8")
        r = _run([sys.executable, root / "bin" / "cepa-run", "fila", "--for", "1h",
                  "--dry-run", "--dirty-ok", "--no-verify", "--no-analysis"], d)
        assert r.returncode == 0, (r.stdout, r.stderr)
        used = log.read_text(encoding="utf-8").split()
        assert "batch" in used and "queue" not in used, used
        assert "queue is now batch" not in r.stderr, r.stderr


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
