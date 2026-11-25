#!/usr/bin/env python3
"""CS-1 of docs/spec/reforma-de-nomes-dos-comandos.md: `cepa queue` does what
`cepa plan` did, and `cepa plan` is refused with the new name.

Each test goes through the real CLI (the `cepa` launcher, `cepa-queue`, and the
board-flow shortcut) in a temporary git repo that has a recorded queue.

Run with `python3 -m pytest tests/test_cepa_queue_rename_cli.py -q` or
`python3 tests/test_cepa_queue_rename_cli.py`.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"
CEPA_QUEUE = REPO / "common" / "bin" / "cepa-queue"
BOARD_QUEUE = REPO / "board-flow" / "bin" / "cepa-queue"
SHIM_PLAN = REPO / "common" / "bin" / "cepa-plan"

MARK = "item-marcador-da-fila"


def _env():
    env = dict(os.environ)
    env["CEPA_PREFLIGHT"] = "off"
    env["NO_COLOR"] = "1"
    return env


def _run(argv, cwd):
    return subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                          cwd=str(cwd), env=_env(), timeout=120)


def _repo_with_queue(base):
    d = Path(base) / "repo"
    d.mkdir()
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "-m", "0"], check=True)
    items = [{"id": MARK, "title": "item " + MARK, "why": "porque sim",
              "status": "pending", "blocked_by": [], "human_pending": None}]
    p = d / "itens.json"
    p.write_text(json.dumps(items), encoding="utf-8")
    r = _run([sys.executable, CEPA_QUEUE if CEPA_QUEUE.exists() else REPO / "common" / "bin" / "cepa-plan",
              "write", "fila", "--items", p, "--source", "teste", "--quando", "2026-11-24",
              "--repo", "."], d)
    assert r.returncode == 0, r.stderr
    return d


def test_queue_status_through_launcher_and_script():
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        for argv in ([CEPA, "queue", "status", "fila", "--repo", "."],
                     [CEPA_QUEUE, "status", "fila", "--repo", "."]):
            r = _run(argv, d)
            assert r.returncode == 0, (argv, r.stdout, r.stderr)
            assert MARK in r.stdout, (argv, r.stdout)


def test_plan_is_refused_with_the_new_name():
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        for argv in ([CEPA, "plan", "status", "fila", "--repo", "."],
                     [CEPA, "help", "plan"]):
            r = _run(argv, d)
            assert r.returncode == 2, (argv, r.returncode, r.stdout, r.stderr)
            assert "plan is now queue" in r.stderr, (argv, r.stderr)
            assert len(r.stderr.strip().splitlines()) == 1, r.stderr
            assert MARK not in r.stdout and MARK not in r.stderr, argv


def test_plan_is_refused_whatever_its_case():
    # macOS is case-insensitive: `cepa-PLAN` would find the shim, so the refusal
    # must not depend on the case of the word.
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        for argv in ([CEPA, "PLAN", "status", "fila", "--repo", "."],
                     [CEPA, "Plan", "status", "fila", "--repo", "."],
                     [CEPA, "help", "PLAN"],
                     [CEPA, "help", "Plan"]):
            r = _run(argv, d)
            assert r.returncode == 2, (argv, r.returncode, r.stdout, r.stderr)
            assert "plan is now queue" in r.stderr, (argv, r.stderr)
            assert MARK not in r.stdout and MARK not in r.stderr, argv


def test_quoted_prompt_starting_with_plan_is_not_refused():
    with tempfile.TemporaryDirectory() as base:
        d = Path(base)
        stub = d / "claude-stub"
        trace = d / "claude-args"
        stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "' + str(trace) + '"\n',
                        encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        env = _env()
        env.update({"CLAUDE_WT_CLAUDE_BIN": str(stub), "CEPA_MODO": "off",
                    "CEPA_ENCADEAR": "off", "CEPA_MENU": "off"})
        subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
        r = subprocess.run([str(CEPA), "Plan the release"], capture_output=True,
                           text=True, cwd=str(d), env=env, timeout=120)
        assert "plan is now queue" not in r.stderr, r.stderr
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        assert trace.exists() and "Plan the release" in trace.read_text(), (r.stdout, r.stderr)


def test_help_lists_queue_and_not_plan():
    with tempfile.TemporaryDirectory() as base:
        d = Path(base)
        r = _run([CEPA, "help"], d)
        assert r.returncode == 0, r.stderr
        words = [ln.split()[0] for ln in r.stdout.splitlines() if ln.startswith("  ") and ln.split()]
        assert "queue" in words, r.stdout
        assert "plan" not in words, r.stdout


def test_help_fallback_in_plain_sh_lists_queue_and_not_plan():
    # A copy of common/bin with no ../hooks/_clihelp.py beside it, so `cepa help`
    # takes the plain-sh list (the path for a machine without python3).
    with tempfile.TemporaryDirectory() as base:
        bindir = Path(base) / "bin"
        shutil.copytree(REPO / "common" / "bin", bindir,
                        ignore=shutil.ignore_patterns("__pycache__"))
        assert not (Path(base) / "hooks" / "_clihelp.py").exists()
        assert (bindir / "cepa-plan").exists() and (bindir / "cepa-queue").exists()
        r = _run(["/bin/sh", bindir / "cepa", "help"], base)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert "subcommands:" in r.stdout, r.stdout
        words = [ln.split()[0] for ln in r.stdout.splitlines()
                 if ln.startswith("  ") and ln.split()]
        assert "queue" in words, r.stdout
        assert "plan" not in words, r.stdout


def test_transition_shim_is_not_a_command():
    # exists only for runs in flight; it hands over to cepa-queue
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        r = _run([sys.executable, SHIM_PLAN, "status", "fila", "--repo", "."], d)
        assert r.returncode == 0 and MARK in r.stdout, (r.stdout, r.stderr)
        # and the typo logic never offers it: a near-miss of `plan` is not refused
        # with "did you mean", it falls through to the launch (a stub `claude`
        # records that it was reached)
        stub = Path(base) / "claude-stub"
        trace = Path(base) / "claude-args"
        stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "' + str(trace) + '"\n',
                        encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        env = _env()
        env.update({"CLAUDE_WT_CLAUDE_BIN": str(stub), "CEPA_MODO": "off",
                    "CEPA_ENCADEAR": "off", "CEPA_MENU": "off"})
        r = subprocess.run([str(CEPA), "plam"], capture_output=True, text=True,
                           cwd=str(d), env=env, timeout=120)
        assert "did you mean" not in r.stderr, r.stderr
        assert "cepa plan" not in r.stderr, r.stderr
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        assert trace.exists() and "plam" in trace.read_text(), (r.stdout, r.stderr)


def test_board_flow_shortcut_reaches_the_same_script():
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        r = _run([sys.executable, BOARD_QUEUE, "status", "fila", "--repo", "."], d)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert MARK in r.stdout, r.stdout


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
