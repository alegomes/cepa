#!/usr/bin/env python3
"""CS-2 of docs/spec/reforma-de-nomes-dos-comandos.md: `cepa run` does what
`cepa until` did, `cepa run digest` what `cepa until-digest` did, and the two old
names are refused with the new one.

Each test goes through the real CLI (the `cepa` launcher and `cepa-run`) as a
subprocess in a temporary git repo that has a recorded queue. Nothing on disk is
renamed: the run folder stays `.claude/queues/<queue>/until/` and the run branch
stays `until/<run>`.

Run with `python3 -m pytest tests/test_cepa_run_rename_cli.py -q` or
`python3 tests/test_cepa_run_rename_cli.py`.
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
CEPA_RUN = REPO / "common" / "bin" / "cepa-run"
CEPA_QUEUE = REPO / "common" / "bin" / "cepa-queue"
SHIM_UNTIL = REPO / "common" / "bin" / "cepa-until"
SHIM_DIGEST = REPO / "common" / "bin" / "cepa-until-digest"
QUEUE_RUN_CMD = REPO / "common" / "commands" / "queue-run.md"

MARK = "item-marcador-da-fila"


def _env(extra_path=None):
    env = dict(os.environ)
    env["CEPA_PREFLIGHT"] = "off"
    env["NO_COLOR"] = "1"
    if extra_path:
        env["PATH"] = f"{extra_path}{os.pathsep}{env.get('PATH', '')}"
    return env


def _run(argv, cwd, extra_path=None):
    return subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                          cwd=str(cwd), env=_env(extra_path), timeout=120)


def _stub_claude(base):
    """A `claude` on the PATH that must never be reached by a dry run."""
    bindir = Path(base) / "stubbin"
    bindir.mkdir()
    stub = bindir / "claude"
    stub.write_text('#!/bin/sh\necho "claude was called" >&2\nexit 1\n', encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return bindir


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
    r = _run([sys.executable, CEPA_QUEUE, "write", "fila", "--items", p,
              "--source", "teste", "--quando", "2026-11-24", "--repo", "."], d)
    assert r.returncode == 0, r.stderr
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "-m", "queue"], check=True)
    return d


def _record(base):
    """A finished run record (`<run>.jsonl`) with its `.log`, in the new queue layout."""
    until = Path(base) / ".claude" / "queues" / "fila" / "until"
    until.mkdir(parents=True)
    ev = [{"evento": "run_start", "fila": "fila", "branch": "until/r",
           "base": "deadbeef00", "verify": "./mvnw -B clean verify"},
          {"evento": "item_start", "id": "A1", "title": "um"},
          {"evento": "item_end", "id": "A1", "status": "done", "segundos": 10,
           "exit_code": 0, "commits": 3, "tentativa": 1},
          {"evento": "run_end", "motivo": "end-of-queue", "detalhe": "acabou",
           "itens": 1, "entregues": 1, "travados": 0}]
    ledger = until / "r.jsonl"
    ledger.write_text("\n".join(json.dumps(e) for e in ev) + "\n", encoding="utf-8")
    result = {"type": "result", "subtype": "success", "result": "RELATORIO-DO-A1",
              "total_cost_usd": 0.5}
    (until / "r.log").write_text(
        "\n===== t · claude -p /common:queue-run fila --max 1\n"
        + json.dumps({"type": "system", "subtype": "init"}) + "\n"
        + json.dumps(result) + "\n", encoding="utf-8")
    return ledger


def test_run_dry_run_cites_queue_run_and_exits_0():
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        stubs = _stub_claude(base)
        r = _run([CEPA, "run", "fila", "--for", "1h", "--dry-run", "--no-verify"], d, stubs)
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        assert "/common:queue-run fila --max 1" in r.stdout, r.stdout
        assert "/common:drain-plan" not in r.stdout, r.stdout
        assert MARK in r.stdout, r.stdout
        assert "claude was called" not in r.stderr, r.stderr
        # nothing on disk was renamed: the run lives in until/<run>
        assert "until/" in r.stdout, r.stdout


def test_run_dry_run_without_no_verify_cites_queue_run():
    """The literal command of the criterion: no `--no-verify`, a committed
    executable tests/run-all.sh, and the stub `claude` is never reached."""
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        runall = d / "tests" / "run-all.sh"
        runall.parent.mkdir()
        runall.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        runall.chmod(runall.stat().st_mode | stat.S_IXUSR)
        subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-q", "-m", "run-all"], check=True)
        stubs = _stub_claude(base)
        r = _run([CEPA, "run", "fila", "--for", "1h", "--dry-run"], d, stubs)
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        assert "/common:queue-run fila --max 1" in r.stdout, r.stdout
        assert "claude was called" not in r.stderr + r.stdout, (r.stdout, r.stderr)


def test_run_all_dry_run_item_line_cites_queue_run():
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        stubs = _stub_claude(base)
        r = _run([CEPA, "run", "--all", "--for", "1h", "--dry-run"], d, stubs)
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        item = [ln for ln in r.stdout.splitlines() if ln.lstrip().startswith("item   :")]
        assert item, r.stdout
        assert "/common:queue-run <queue> --max 1" in item[0], item[0]
        assert "/common:drain-plan" not in r.stdout, r.stdout


def test_run_help_names_the_new_command_and_digest():
    with tempfile.TemporaryDirectory() as base:
        r = _run([CEPA, "run", "--help"], base)
        assert r.returncode == 0, r.stderr
        assert "cepa run" in r.stdout and "digest" in r.stdout, r.stdout
        assert "cepa until" not in r.stdout and "cepa-until" not in r.stdout, r.stdout
        assert "/common:queue-run" in r.stdout, r.stdout
        # `cepa help run` is the same help
        h = _run([CEPA, "help", "run"], base)
        assert h.returncode == 0 and h.stdout == r.stdout, (h.stdout, h.stderr)


def test_run_digest_prints_the_summary_of_the_old_command():
    with tempfile.TemporaryDirectory() as base:
        ledger = _record(base)
        new = _run([CEPA, "run", "digest", ledger], base)
        assert new.returncode == 0, (new.stdout, new.stderr)
        assert "RELATORIO-DO-A1" in new.stdout, new.stdout
        assert "A1" in new.stdout, new.stdout
        # the same bytes through `cepa-run digest`, the shim and the code file
        for argv in ([sys.executable, CEPA_RUN, "digest", ledger],
                     [sys.executable, SHIM_DIGEST, ledger],
                     [sys.executable, REPO / "common" / "bin" / "_run_digest.py", ledger]):
            other = _run(argv, base)
            assert other.returncode == 0 and other.stdout == new.stdout, (argv, other.stderr)


def test_run_digest_help_and_missing_record():
    with tempfile.TemporaryDirectory() as base:
        h = _run([CEPA, "run", "digest", "--help"], base)
        assert h.returncode == 0, h.stderr
        assert "cepa run digest" in h.stdout and "cepa until" not in h.stdout, h.stdout
        m = _run([CEPA, "run", "digest", Path(base) / "nao-existe.jsonl"], base)
        assert m.returncode == 2 and "does not exist" in m.stderr, (m.returncode, m.stderr)


def test_until_is_refused_with_the_new_name():
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        stubs = _stub_claude(base)
        for argv in ([CEPA, "until", "fila", "--for", "1h", "--dry-run", "--no-verify"],
                     [CEPA, "help", "until"]):
            r = _run(argv, d, stubs)
            assert r.returncode == 2, (argv, r.returncode, r.stdout, r.stderr)
            assert "until is now run" in r.stderr, (argv, r.stderr)
            assert len(r.stderr.strip().splitlines()) == 1, r.stderr
            assert r.stdout == "" and MARK not in r.stderr, (argv, r.stdout)
            assert not (d / ".claude" / "queues" / "fila" / "until").exists(), argv


def test_until_digest_is_refused_with_the_new_name():
    with tempfile.TemporaryDirectory() as base:
        for argv in ([CEPA, "until-digest", "x"], [CEPA, "help", "until-digest"]):
            r = _run(argv, base)
            assert r.returncode == 2, (argv, r.returncode, r.stdout, r.stderr)
            assert "until-digest is now run digest" in r.stderr, (argv, r.stderr)
            assert len(r.stderr.strip().splitlines()) == 1, r.stderr
            assert r.stdout == "", (argv, r.stdout)


def test_old_names_are_refused_whatever_their_case():
    # macOS is case-insensitive: `cepa-UNTIL` would find the shim, so the refusal
    # must not depend on the case of the word.
    with tempfile.TemporaryDirectory() as base:
        for argv, phrase in (([CEPA, "UNTIL", "fila", "--for", "1h"], "until is now run"),
                             ([CEPA, "Until", "x"], "until is now run"),
                             ([CEPA, "help", "UNTIL"], "until is now run"),
                             ([CEPA, "UNTIL-DIGEST", "x"], "until-digest is now run digest"),
                             ([CEPA, "Until-Digest", "x"], "until-digest is now run digest"),
                             ([CEPA, "help", "Until-Digest"], "until-digest is now run digest")):
            r = _run(argv, base)
            assert r.returncode == 2, (argv, r.returncode, r.stdout, r.stderr)
            assert phrase in r.stderr, (argv, r.stderr)


def _launch_with_stub(base, *args):
    d = Path(base)
    stub = d / "claude-stub"
    trace = d / "claude-args"
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "' + str(trace) + '"\n',
                    encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    env = _env()
    env.update({"CEPA_WT_CLAUDE_BIN": str(stub), "CEPA_MODE": "off",
                "CEPA_CHAIN": "off", "CEPA_MENU": "off"})
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    r = subprocess.run([str(CEPA), *args], capture_output=True, text=True,
                       cwd=str(d), env=env, timeout=120)
    return r, trace


def test_quoted_prompt_starting_with_until_is_not_refused():
    with tempfile.TemporaryDirectory() as base:
        r, trace = _launch_with_stub(base, "until tomorrow do X")
        assert "is now run" not in r.stderr, r.stderr
        assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
        assert trace.exists() and "until tomorrow do X" in trace.read_text(), (r.stdout, r.stderr)


def test_help_lists_run_and_neither_old_name():
    with tempfile.TemporaryDirectory() as base:
        r = _run([CEPA, "help"], base)
        assert r.returncode == 0, r.stderr
        words = [ln.split()[0] for ln in r.stdout.splitlines() if ln.startswith("  ") and ln.split()]
        assert "run" in words, r.stdout
        for old in ("until", "until-digest", "run-digest", "digest", "plan"):
            assert old not in words, (old, r.stdout)


def test_help_fallback_in_plain_sh_lists_run_and_neither_old_name():
    # A copy of common/bin with no ../hooks/_clihelp.py beside it, so `cepa help`
    # takes the plain-sh list (the path for a machine without python3).
    with tempfile.TemporaryDirectory() as base:
        bindir = Path(base) / "bin"
        shutil.copytree(REPO / "common" / "bin", bindir,
                        ignore=shutil.ignore_patterns("__pycache__"))
        assert not (Path(base) / "hooks" / "_clihelp.py").exists()
        assert (bindir / "cepa-until").exists() and (bindir / "cepa-until-digest").exists()
        r = _run(["/bin/sh", bindir / "cepa", "help"], base)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert "subcommands:" in r.stdout, r.stdout
        words = [ln.split()[0] for ln in r.stdout.splitlines()
                 if ln.startswith("  ") and ln.split()]
        assert "run" in words, r.stdout
        for old in ("until", "until-digest", "run-digest", "digest", "plan"):
            assert old not in words, (old, r.stdout)


def test_transition_shims_are_not_commands():
    with tempfile.TemporaryDirectory() as base:
        d = _repo_with_queue(base)
        stubs = _stub_claude(base)
        # reachable by path: the supervisor in flight still calls these
        r = _run([sys.executable, SHIM_UNTIL, "fila", "--for", "1h", "--dry-run", "--no-verify"], d, stubs)
        assert r.returncode == 0 and "/common:queue-run fila --max 1" in r.stdout, (r.stdout, r.stderr)
        assert "TRANSITION SHIM" in SHIM_UNTIL.read_text(encoding="utf-8")
        assert "TRANSITION SHIM" in SHIM_DIGEST.read_text(encoding="utf-8")
        # and the typo logic never offers them: `untill` is not "did you mean until"
        stub = Path(base) / "claude-stub"
        trace = Path(base) / "claude-args"
        stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "' + str(trace) + '"\n',
                        encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        env = _env()
        env.update({"CEPA_WT_CLAUDE_BIN": str(stub), "CEPA_MODE": "off",
                    "CEPA_CHAIN": "off", "CEPA_MENU": "off"})
        for word in ("untill", "until-digst"):
            r = subprocess.run([str(CEPA), word], capture_output=True, text=True,
                               cwd=str(d), env=env, timeout=120)
            assert "did you mean `cepa until" not in r.stderr, (word, r.stderr)
            assert r.returncode == 0, (word, r.returncode, r.stdout, r.stderr)
            assert trace.exists() and word in trace.read_text(), (word, r.stdout, r.stderr)
            trace.unlink()


def test_a_live_supervisor_is_recognised_under_both_names():
    # a run started as `cepa-until` is still alive after the rename
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("cepa_run_mod", str(CEPA_RUN))
    spec = importlib.util.spec_from_loader("cepa_run_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    for name in ("cepa-run", "cepa-until"):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", name])
        try:
            assert mod.supervisor_alive(p.pid), name
        finally:
            p.kill()
            p.wait()
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", "outra-coisa"])
    try:
        assert not mod.supervisor_alive(other.pid)
    finally:
        other.kill()
        other.wait()


def test_the_new_command_file_is_the_real_runner():
    # CS-3: the transitional forwarder is gone; queue-run.md is the runner itself.
    text = QUEUE_RUN_CMD.read_text(encoding="utf-8")
    assert text.startswith("---\n") and "/common:queue-run" in text
    assert "/common:drain-plan" not in text
    assert not (REPO / "common" / "commands" / "drain-plan.md").exists()


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
