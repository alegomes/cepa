#!/usr/bin/env python3
"""Regression tests: the cepa-doctor's check_twg_version.

## Why this check exists

The `twg` CLI (Atlassian) installs a `launchd` scheduler
(`com.atlassian.twg.upkeep.plist`) that checks for updates by itself every 12
minutes — the version may change BETWEEN two cards of the same unattended batch, with no
signal at all. The doctor checks the installed one against the one declared in
`twg_version:` in the environment manifest (docs/env.yaml, or the legacy
.claude/env.yaml — see docs/env-manifest.md).

## Why the warning is GATED on the declaration, and not loose

Without a declared `twg_version:`, the doctor stays in total silence. It runs on
every session opening, and a warning about a tool nobody asked to
track is the noise people learn to skip.

Run: python3 tests/test_doctor_twg_version.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
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


def fake_twg_dir(tmp, version):
    """Directory with a fake `twg` (sh script) that echoes `version`."""
    d = Path(tmp) / "faketwg"
    d.mkdir()
    script = d / "twg"
    script.write_text(f"#!/bin/sh\necho 'twg version {version}'\n", encoding="utf-8")
    script.chmod(0o755)
    return d


def essential_paths(tmp):
    """Directory with only symlinks to git/python3/lsof — the minimum the
    doctor needs to run `--projeto` without `twg` on the PATH.
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


def test_without_declared_twg_version_is_silent():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, docs_env="ports: [8083]\n")
        fake = fake_twg_dir(tmp, "1.3.1")
        out = run_doctor(root, [fake, essential_paths(tmp)])
        check("sem twg_version declarado → nenhuma linha menciona twg",
              "twg" not in out.lower(), out)


def test_docs_env_yaml_same_version_is_ok():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, docs_env="twg_version: 1.3.1\n")
        fake = fake_twg_dir(tmp, "1.3.1")
        out = run_doctor(root, [fake, essential_paths(tmp)])
        check("versão igual → linha ok com a versão",
              "✓ [ambiente]" in out and "1.3.1" in out, out)


def test_docs_env_yaml_different_version_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, docs_env="twg_version: 1.3.1\n")
        fake = fake_twg_dir(tmp, "1.4.0")
        out = run_doctor(root, [fake, essential_paths(tmp)])
        check("versão diferente → aviso nomeando as duas",
              "⚠ [ambiente]" in out and "1.3.1" in out and "1.4.0" in out, out)
        check("...e nomeia o agendador responsável",
              "com.atlassian.twg.upkeep" in out, out)


def test_legacy_claude_env_yaml_also_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, legacy_env="twg_version: 1.3.1\n")
        fake = fake_twg_dir(tmp, "1.4.0")
        out = run_doctor(root, [fake, essential_paths(tmp)])
        check(".claude/env.yaml (legado) também dispara o check",
              "⚠ [ambiente]" in out and "1.3.1" in out and "1.4.0" in out, out)


def test_twg_missing_from_path_warns():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, docs_env="twg_version: 1.3.1\n")
        out = run_doctor(root, [essential_paths(tmp)])
        check("twg fora do PATH → aviso de ausente",
              "⚠ [ambiente]" in out and "1.3.1" in out
              and ("não está instalada" in out or "não está no PATH" in out), out)


def test_docs_env_yaml_wins_over_legacy():
    with tempfile.TemporaryDirectory() as tmp:
        root = build(tmp, docs_env="twg_version: 1.3.1\n",
                     legacy_env="twg_version: 9.9.9\n")
        fake = fake_twg_dir(tmp, "1.3.1")
        out = run_doctor(root, [fake, essential_paths(tmp)])
        check("docs/env.yaml ganha do legado (compara com 1.3.1, não 9.9.9)",
              "✓ [ambiente]" in out and "1.3.1" in out and "9.9.9" not in out, out)


def main():
    print("cepa-doctor — check_twg_version\n")
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
