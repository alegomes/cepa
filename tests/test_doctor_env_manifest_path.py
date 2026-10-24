#!/usr/bin/env python3
"""Regression tests: the cepa-doctor's check_env_manifest reads docs/env.yaml.

## Why this check exists

The environment manifest changed address on 2026-08-22: `docs/env.yaml`
wins, with fallback to the legacy `.claude/env.yaml` (see
docs/env-manifest.md). `check_env_manifest` hardcoded `.claude/env.yaml` and
never saw `docs/env.yaml` — a silent regression, because the check is
fail-silent by design (absent file → no warning). This test proves
that the port declared in `docs/env.yaml` is checked.

Run: python3 tests/test_doctor_env_manifest_path.py
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def build(tmp, docs_env=None, legacy_env=None):
    """Minimal git repo, with optional docs/env.yaml and/or .claude/env.yaml."""
    root = Path(tmp) / "repo"
    root.mkdir()
    (root / "README.md").write_text("base\n", encoding="utf-8")
    if docs_env is not None:
        d = root / "docs"
        d.mkdir(parents=True, exist_ok=True)
        (d / "env.yaml").write_text(docs_env, encoding="utf-8")
    if legacy_env is not None:
        d = root / ".claude"
        d.mkdir(parents=True, exist_ok=True)
        (d / "env.yaml").write_text(legacy_env, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    return root


def essential_paths(tmp):
    """Directory with only symlinks to git/python3/lsof — the minimum the
    doctor needs to run `--projeto`.
    """
    d = Path(tmp) / "minpath"
    d.mkdir()
    for name in ("git", "python3", "lsof"):
        real = shutil.which(name)
        if real:
            (d / name).symlink_to(real)
    return d


def run_doctor(root, path_dirs):
    env = dict(os.environ)
    env["PATH"] = ":".join(str(p) for p in path_dirs)
    p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"], cwd=str(root),
                       capture_output=True, text=True, timeout=120, env=env)
    return p.stdout + p.stderr


class PortListener:
    """Opens a TCP socket on 127.0.0.1:0 (free port chosen by the OS) and
    keeps listening in a thread — enough for the doctor's `lsof` to
    find a LISTEN. The owning process is this very Python interpreter,
    whose cwd (the directory this test was invoked from) is NOT inside
    the temporary repo built by `build()` — a condition this
    test depends on to trigger the "process from ANOTHER directory" branch.
    """

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(1)
        self._stop = False
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        time.sleep(0.2)  # gives lsof time to see the LISTEN

    def _loop(self):
        self.sock.settimeout(0.5)
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                return

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass
        self._t.join(timeout=2)


def lsof_available():
    return shutil.which("lsof") is not None


def test_docs_env_yaml_busy_port_warns():
    if not lsof_available():
        print("  skip  lsof ausente no PATH — pulando (sem como o doctor achar o holder)")
        return
    listener = PortListener()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = build(tmp, docs_env=f"ports: [{listener.port}]\n")
            out = run_doctor(root, [essential_paths(tmp)])
            check("docs/env.yaml declara porta ocupada → warn nomeando a porta",
                  f"porta {listener.port} ocupada" in out, out)
    finally:
        listener.close()


def test_legacy_claude_env_yaml_busy_port_also_warns():
    if not lsof_available():
        print("  skip  lsof ausente no PATH — pulando (sem como o doctor achar o holder)")
        return
    listener = PortListener()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = build(tmp, legacy_env=f"ports: [{listener.port}]\n")
            out = run_doctor(root, [essential_paths(tmp)])
            check(".claude/env.yaml (legado, sem docs/env.yaml) também dispara o aviso",
                  f"porta {listener.port} ocupada" in out, out)
    finally:
        listener.close()


def test_docs_env_yaml_wins_over_legacy_on_port():
    if not lsof_available():
        print("  skip  lsof ausente no PATH — pulando (sem como o doctor achar o holder)")
        return
    listener = PortListener()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            # free port guaranteed: opens and closes right away, only to reserve
            # a number whose chance of colliding with the listener is negligible
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", 0))
            free_legacy_port = s.getsockname()[1]
            s.close()

            root = build(tmp, docs_env=f"ports: [{listener.port}]\n",
                         legacy_env=f"ports: [{free_legacy_port}]\n")
            out = run_doctor(root, [essential_paths(tmp)])
            check("docs/env.yaml ganha: avisa da porta do docs/env.yaml",
                  f"porta {listener.port} ocupada" in out, out)
            check("...e NÃO menciona a porta do legado (docs/env.yaml venceu)",
                  str(free_legacy_port) not in out, out)
    finally:
        listener.close()


def main():
    print("cepa-doctor — check_env_manifest usa docs/env.yaml\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
