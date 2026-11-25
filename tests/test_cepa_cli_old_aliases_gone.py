#!/usr/bin/env python3
"""CS-4 of docs/spec/reforma-de-nomes-dos-comandos.md: the CLI aliases `cepa
intencao` and `cepa modos` are gone. Each is refused with exit 2 and a line that
names the new command, and the files `common/bin/cepa-intencao` and
`common/bin/cepa-modos` no longer exist. `cepa help` no longer has an "Old
subcommand names" line and does not list the two names.

Everything goes through the real `cepa` launcher as a subprocess.

Run with `python3 -m pytest tests/test_cepa_cli_old_aliases_gone.py -q` or
`python3 tests/test_cepa_cli_old_aliases_gone.py`.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin"
CEPA = BIN / "cepa"

OLD = {"intencao": "intent", "modos": "modes"}


def _run(argv, cwd):
    env = dict(os.environ)
    env["CEPA_PREFLIGHT"] = "off"
    env["NO_COLOR"] = "1"
    return subprocess.run([str(a) for a in argv], capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=120)


def _refused(argv, old, new):
    with tempfile.TemporaryDirectory() as base:
        subprocess.run(["git", "-C", base, "init", "-q"], check=True)
        r = _run(argv, base)
        assert r.returncode == 2, (argv, r.returncode, r.stdout, r.stderr)
        assert f"{old} is now {new}" in r.stderr, r.stderr
        assert f"cepa {new}" in r.stderr, r.stderr
        assert "did you mean" not in r.stderr, r.stderr
        assert r.stdout == "", r.stdout  # the new command did not run
        assert not (Path(base) / ".claude").exists()  # and wrote nothing


def test_intencao_is_refused_with_the_new_name():
    _refused([CEPA, "intencao", "estado"], "intencao", "intent")


def test_modos_is_refused_with_the_new_name():
    _refused([CEPA, "modos", "--purposes"], "modos", "modes")


def test_refusal_without_arguments_and_with_flags():
    _refused([CEPA, "intencao"], "intencao", "intent")
    _refused([CEPA, "modos", "--menu", "discovery"], "modos", "modes")


def test_refusal_through_help_and_upper_case():
    for old, new in OLD.items():
        _refused([CEPA, "help", old], old, new)
        _refused([CEPA, "--help", old], old, new)
        _refused([CEPA, old.upper(), "x"], old, new)
        _refused([CEPA, "help", old.upper()], old, new)


def test_the_new_names_still_work():
    with tempfile.TemporaryDirectory() as base:
        subprocess.run(["git", "-C", base, "init", "-q"], check=True)
        for new in OLD.values():
            r = _run([CEPA, new, "--help"], base)
            assert r.returncode == 0, (new, r.stdout, r.stderr)
            assert "is now" not in r.stderr, r.stderr


def test_the_alias_files_do_not_exist():
    for old in OLD:
        assert not (BIN / f"cepa-{old}").exists(), old


def _words(out):
    return [ln.split()[0] for ln in out.splitlines() if ln.startswith("  ") and ln.split()]


def test_help_has_no_old_names_line_and_does_not_list_them():
    with tempfile.TemporaryDirectory() as base:
        r = _run([CEPA, "help"], base)
        assert r.returncode == 0, r.stderr
        assert "Old subcommand names" not in r.stdout, r.stdout
        words = _words(r.stdout)
        assert "intent" in words and "modes" in words, r.stdout
        for old in OLD:
            assert old not in words, r.stdout
            assert f"= {OLD[old]}" not in r.stdout, r.stdout


def test_help_fallback_in_plain_sh_does_not_list_them():
    # A copy of common/bin with no ../hooks/_clihelp.py beside it, so `cepa help`
    # takes the plain-sh list (the path for a machine without python3).
    with tempfile.TemporaryDirectory() as base:
        bindir = Path(base) / "bin"
        shutil.copytree(BIN, bindir, ignore=shutil.ignore_patterns("__pycache__"))
        assert not (Path(base) / "hooks" / "_clihelp.py").exists()
        r = _run(["/bin/sh", bindir / "cepa", "help"], base)
        assert r.returncode == 0, (r.stdout, r.stderr)
        assert "subcommands:" in r.stdout, r.stdout
        assert "alias" not in r.stdout.lower(), r.stdout
        words = _words(r.stdout)
        assert "intent" in words and "modes" in words, r.stdout
        for old in OLD:
            assert old not in words, r.stdout


if __name__ == "__main__":
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", __file__]))
