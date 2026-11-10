#!/usr/bin/env python3
"""Regression test: tests/run-all.sh puts a per-file ceiling on each test.

On 2026-11-05/06 a pty test with a wrong anchor held the suite for 3h and 10h
with no signal. Contract guarded here: a hanging file is killed (with its
children), counted as a [TIMEOUT] failure, and the suite goes on to the next file.

run-all.sh does `cd "$(dirname "$0")/.."`, so the test builds a temp tree
`tmp/tests/` with a copy of run-all.sh, the limiter and two fixture tests.

No third-party deps — run with `python3 tests/test_run_all_timeout.py`.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from _isolated_telemetry import isolate  # noqa: E402

isolate()

HERE = Path(__file__).resolve().parent
failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


HANG = '''import subprocess, sys, time
from pathlib import Path
# filho de longa duração, como os que um teste de pty abre
child = subprocess.Popen(["sleep", "300"])
Path(sys.argv[0]).with_name("child.pid").write_text(str(child.pid))
time.sleep(300)
'''
PASS = 'print("ok")\n'


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def test_sigterm_kills_child_group():
    with tempfile.TemporaryDirectory() as tmp:
        pidf = Path(tmp) / "child.pid"
        script = ("import subprocess,sys,time\n"
                  "c=subprocess.Popen(['sleep','300'])\n"
                  f"open({str(pidf)!r},'w').write(str(c.pid))\n"
                  "time.sleep(300)\n")
        p = subprocess.Popen([sys.executable, str(HERE / "_run_with_timeout.py"), "100",
                              sys.executable, "-c", script])
        for _ in range(50):
            if pidf.exists() and pidf.read_text():
                break
            time.sleep(0.1)
        pid = int(pidf.read_text()) if pidf.exists() and pidf.read_text() else None
        check("sigterm: child spawned", pid is not None)
        p.terminate()
        try:
            rc = p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()
            rc = None
        check("sigterm: wrapper exits 128+15", rc == 143, f"rc={rc}")
        if pid:
            time.sleep(0.3)
            orphan = alive(pid)
            if orphan:
                os.kill(pid, 9)
            check("sigterm: child group is gone", not orphan, f"pid={pid}")


PYHANG = '''import pytest, subprocess, sys, time
from pathlib import Path


def test_hang():
    child = subprocess.Popen(["sleep", "300"])
    Path(__file__).with_name("pychild.pid").write_text(str(child.pid))
    time.sleep(300)
'''
PYPASS = "import pytest\n\n\ndef test_ok():\n    assert True\n"


def test_pytest_family_timeout():
    # pytest ausente é erro, não skip: falha alto em vez de pular
    has = subprocess.run([sys.executable, "-m", "pytest", "--version"],
                         capture_output=True).returncode == 0
    check("pytest family: pytest is installed", has)
    if not has:
        return
    with tempfile.TemporaryDirectory() as tmp:
        tests = Path(tmp) / "tests"
        tests.mkdir()
        for f in ("run-all.sh", "_run_with_timeout.py"):
            shutil.copy(HERE / f, tests / f)
        (tests / "test_aaa_pyhang.py").write_text(PYHANG)
        (tests / "test_zzz_pypass.py").write_text(PYPASS)
        env = dict(os.environ, CEPA_TEST_TIMEOUT="2")
        env.pop("SKIP_PYTEST", None)
        t0 = time.time()
        try:
            r = subprocess.run(["bash", str(tests / "run-all.sh")], env=env,
                               capture_output=True, text=True, timeout=60)
            out, rc = r.stdout + r.stderr, r.returncode
        except subprocess.TimeoutExpired:
            out, rc = "", None
        took = time.time() - t0
        check("pytest family: run ends quickly", rc is not None and took < 30, f"took={took:.1f}s")
        check("pytest family: exit is non-zero", rc not in (0, None), f"rc={rc}")
        check("pytest family: hanging file listed [TIMEOUT 2s]",
              "- tests/test_aaa_pyhang.py  [TIMEOUT 2s]" in out, out)
        check("pytest family: passing file ran", "1 passed" in out, out)
        check("pytest family: passing file not a failure",
              "- tests/test_zzz_pypass.py" not in out, out)
        pidf = tests / "pychild.pid"
        check("pytest family: hang fixture spawned a child", pidf.exists())
        if pidf.exists():
            pid = int(pidf.read_text())
            time.sleep(0.3)
            orphan = alive(pid)
            if orphan:
                os.kill(pid, 9)
            check("pytest family: no orphan child survives", not orphan, f"pid={pid}")


def main():
    test_pytest_family_timeout()
    test_sigterm_kills_child_group()
    with tempfile.TemporaryDirectory() as tmp:
        tests = Path(tmp) / "tests"
        tests.mkdir()
        for f in ("run-all.sh", "_run_with_timeout.py"):
            shutil.copy(HERE / f, tests / f)
        (tests / "test_aaa_hang.py").write_text(HANG)
        (tests / "test_zzz_pass.py").write_text(PASS)
        env = dict(os.environ, CEPA_TEST_TIMEOUT="2", SKIP_PYTEST="1")
        t0 = time.time()
        try:
            r = subprocess.run(["bash", str(tests / "run-all.sh")], env=env,
                               capture_output=True, text=True, timeout=60)
            out, rc = r.stdout + r.stderr, r.returncode
        except subprocess.TimeoutExpired:
            out, rc = "", None
        took = time.time() - t0

        check("run ends quickly (not stuck)", rc is not None and took < 30, f"took={took:.1f}s")
        check("exit is non-zero", rc not in (0, None), f"rc={rc}")
        check("hanging file named as TIMEOUT",
              any("TIMEOUT" in l and "test_aaa_hang.py" in l for l in out.splitlines()), out)
        check("summary lists it as [TIMEOUT 2s]", "test_aaa_hang.py  [TIMEOUT 2s]" in out, out)
        check("passing file still ran", "ok    tests/test_zzz_pass.py" in out, out)
        check("passing file not listed as failure", "- tests/test_zzz_pass.py" not in out, out)
        pidf = tests / "child.pid"
        check("hang fixture spawned a child", pidf.exists())
        if pidf.exists():
            pid = int(pidf.read_text())
            time.sleep(0.3)
            orphan = alive(pid)
            if orphan:
                os.kill(pid, 9)
            check("no orphan child survives", not orphan, f"pid={pid}")

    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
