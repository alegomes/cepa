"""Regression of the `board-flow/bin/cepa-plan` shortcut.

## Why this file exists

`common/bin/cepa-plan` is a RELATIVE path that only exists by accident of
layout inside the `cepa` repo itself. `/board-flow:capture`, `/drain` and
`/triage` called that path directly — it worked running from inside
`cepa`, but in any host project (WEGO, for example) the file does not
exist, the command fails silently and the card is born outside the queue with no warning.
This shim exists to resolve the real `cepa-plan` of `common` (in the repo or in the
plugin cache) and pass everything on — argv and exit code — without the
caller noticing the difference.

The tests here use FAKE layouts in `tmp_path` with a fake `cepa-plan` (which
only prints the argv received and exits with a chosen code), to prove the
path resolution without depending on the real `cepa-plan` — plus one real
integration test at the end, which runs the real shim against the real
`common`.
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from _isolated_telemetry import isolate

isolate()

REPO = Path(__file__).resolve().parent.parent
SHIM_REAL = REPO / "board-flow" / "bin" / "cepa-plan"

FAKE_CEPA_PLAN = """#!/usr/bin/env python3
import sys
print("ARGV:" + repr(sys.argv[1:]))
sys.exit({exit_code})
"""


def _install_shim(destination):
    """Copies the real shim to `destination` (a `.../bin/cepa-plan`), executable."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(SHIM_REAL, destination)
    destination.chmod(destination.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _install_fake_cepa_plan(destination, exit_code):
    """Writes a fake `cepa-plan` at `destination` that only echoes the argv and exits with `exit_code`."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(FAKE_CEPA_PLAN.format(exit_code=exit_code), encoding="utf-8")
    destination.chmod(destination.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run(shim, args, cwd, env=None, timeout=None):
    return subprocess.run(
        [sys.executable, str(shim), *args],
        cwd=str(cwd), capture_output=True, text=True, env=env, timeout=timeout,
    )


def test_repo_layout_resolves_and_passes_on_argv_and_exit(tmp_path):
    repo = tmp_path / "repo"
    shim = repo / "board-flow" / "bin" / "cepa-plan"
    _install_shim(shim)
    _install_fake_cepa_plan(repo / "common" / "bin" / "cepa-plan", exit_code=42)

    other_cwd = tmp_path / "em-qualquer-lugar"
    other_cwd.mkdir()

    r = _run(shim, ["add", "WEGO", "WEGO-1", "--title", "x"], cwd=other_cwd)

    assert r.returncode == 42, r.stderr
    assert "ARGV:['add', 'WEGO', 'WEGO-1', '--title', 'x']" in r.stdout


def test_cache_layout_picks_the_highest_common_version(tmp_path):
    mkt = tmp_path / "cache" / "cepa"
    shim = mkt / "board-flow" / "0.25.1" / "bin" / "cepa-plan"
    _install_shim(shim)
    # 2.9.0 would come out "ahead" of 2.10.0 in a lexical string comparison —
    # which is exactly the error the numeric tuple comparison avoids.
    _install_fake_cepa_plan(mkt / "common" / "2.9.0" / "bin" / "cepa-plan", exit_code=9)
    _install_fake_cepa_plan(mkt / "common" / "2.10.0" / "bin" / "cepa-plan", exit_code=10)

    r = _run(shim, ["ordena", "WEGO"], cwd=tmp_path)

    assert r.returncode == 10, r.stderr
    assert "ARGV:['ordena', 'WEGO']" in r.stdout


def test_fallback_to_path_when_no_layout_exists(tmp_path):
    # Isolated shim, with no `common/` nor a sibling in repo or cache position
    # (same depth as `<repo>/board-flow/bin/`, only without `common/`).
    shim = tmp_path / "solto" / "board-flow" / "bin" / "cepa-plan"
    _install_shim(shim)

    bin_no_path = tmp_path / "fake-path-bin"
    _install_fake_cepa_plan(bin_no_path / "cepa-plan", exit_code=7)

    env = dict(os.environ, PATH=f"{bin_no_path}:{os.environ.get('PATH', '')}")
    r = _run(shim, ["divergencia", "WEGO"], cwd=tmp_path, env=env)

    assert r.returncode == 7, r.stderr
    assert "ARGV:['divergencia', 'WEGO']" in r.stdout


def test_no_candidate_exits_127_and_names_the_paths_tried(tmp_path):
    shim = tmp_path / "solto" / "board-flow" / "bin" / "cepa-plan"
    _install_shim(shim)

    # PATH with no real cepa-plan at all (not even the shim itself, which is not
    # called "cepa-plan" on the PATH here — it only exists loose in tmp_path).
    env = dict(os.environ, PATH="/usr/bin:/bin")
    r = _run(shim, ["add", "WEGO", "WEGO-1", "--title", "x"], cwd=tmp_path, env=env)

    assert r.returncode == 127
    assert "não encontrado" in r.stderr
    # shim = .../loose/board-flow/bin/cepa-plan; the "repo" root is `loose/`.
    assert str(shim.parent.parent.parent / "common" / "bin" / "cepa-plan") in r.stderr
    assert "instale o plugin" in r.stderr.lower()


def test_itself_on_path_does_not_re_execute_itself(tmp_path):
    """If `_candidato_path` did not skip this very file, `shutil.which("cepa-plan")`
    would find it itself (installed on the PATH under the name `cepa-plan`, with no `common/`
    around it, neither repo layout nor cache layout) and `os.execv` would call itself again
    and again, hanging until the timeout instead of exiting 127 with the error message."""
    bin_no_path = tmp_path / "so-o-shim-no-path"
    shim_como_cepa_plan = bin_no_path / "cepa-plan"
    _install_shim(shim_como_cepa_plan)

    env = dict(os.environ, PATH=f"{bin_no_path}:/usr/bin:/bin")

    r = _run(shim_como_cepa_plan, [], cwd=tmp_path, env=env, timeout=10)

    assert r.returncode == 127
    assert "não encontrado" in r.stderr


def test_cwd_without_common_still_resolves_by_repo_layout(tmp_path):
    """The real bug: a host like WEGO has no `common/` at the root. The
    resolution has to depend on where the SHIM is, not on the caller's cwd."""
    repo = tmp_path / "wego-like-repo"
    shim = repo / "board-flow" / "bin" / "cepa-plan"
    _install_shim(shim)
    _install_fake_cepa_plan(repo / "common" / "bin" / "cepa-plan", exit_code=0)

    host_cwd = tmp_path / "wego-like-repo"  # no common/ at the root of the user's project
    assert not (tmp_path / "outro-projeto-sem-common").exists()
    cwd_without_common = tmp_path / "outro-projeto-sem-common"
    cwd_without_common.mkdir()

    r = _run(shim, ["add", "WEGO", "WEGO-1", "--title", "x"], cwd=cwd_without_common)

    assert r.returncode == 0, r.stderr
    assert "ARGV:['add', 'WEGO', 'WEGO-1', '--title', 'x']" in r.stdout


def test_no_board_flow_file_calls_the_relative_path():
    """Contract: nothing in `board-flow/{commands,skills,agents}` invokes
    `python3 common/bin/cepa-plan` — the path that only exists inside the `cepa`
    repo. capture/drain/triage have to call the shim via `${CLAUDE_PLUGIN_ROOT}`."""
    target = "python3 common/bin/cepa-plan"
    offenders = []
    for sub in ("commands", "skills", "agents"):
        d = REPO / "board-flow" / sub
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file() and target in f.read_text(encoding="utf-8", errors="ignore"):
                offenders.append(str(f))
    assert offenders == [], f"ainda chamam o caminho relativo: {offenders}"

    for name in ("capture.md", "drain.md", "triage.md"):
        f = REPO / "board-flow" / "commands" / name
        content = f.read_text(encoding="utf-8")
        assert '${CLAUDE_PLUGIN_ROOT}/bin/cepa-plan' in content, (
            f"{name} não chama o shim via CLAUDE_PLUGIN_ROOT")


def test_real_integration_reaches_the_real_cepa_plan(tmp_path):
    """No fakes: runs `board-flow/bin/cepa-plan` from inside the `cepa` repo
    itself (real repo layout) and checks that it reached the real `cepa-plan`
    of `common` — not a shim that only pretends success."""
    r = _run(SHIM_REAL, ["--help"], cwd=tmp_path)

    assert r.returncode == 0, r.stderr
    assert "cepa-plan" in r.stdout
    assert "single-track" in r.stdout or "single-track" in r.stdout.lower()
