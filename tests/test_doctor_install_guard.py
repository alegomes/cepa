#!/usr/bin/env python3
"""Regression tests: the suite must not swap the owner's live installation.

`cepa-doctor --fix` has one correction that leaves the project: `fix_install` runs
the cepa repo's `bin/install.sh` and reinstalls the MACHINE's plugins, no matter
which directory the doctor was called from. That is what you want in the
preflight of a real session.

On 2026-08-19 the opposite happened: the doctor's own suite, running `--fix` in
temporary repositories, saw the repo ahead of the cache and reinstalled the
owner's harness in the middle of a `python3 tests/...`. Nobody asked, nothing
warned, and the swap only showed up later, in the doctor's report. A test able to
swap the installed harness can cause exactly the class of failure the doctor
exists to find — and even erase its trail.

What these tests pin down:
  - CEPA_DOCTOR_INSTALL=off turns the reinstall off;
  - a doctor called from inside a temporary directory does not reinstall either
    (the net for the test not yet written that will forget the variable);
  - outside the temporary directory and without the variable, the reinstall remains
    allowed — the preflight cannot lose its function;
  - when blocked, it does NOT become "failed to fix": it leaves the batch and goes to
    the owner's decision block, with the command at hand.

Run: python3 tests/test_doctor_install_guard.py
"""

import importlib.machinery
import importlib.util
import os
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


def load_doctor():
    """Loads the cepa-doctor as a module — it is a script, without a .py extension."""
    spec = importlib.util.spec_from_loader(
        "cepa_doctor", importlib.machinery.SourceFileLoader("cepa_doctor", str(DOCTOR)))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_variable_turns_it_off():
    D = load_doctor()
    before = os.environ.get("CEPA_DOCTOR_INSTALL")
    os.environ["CEPA_DOCTOR_INSTALL"] = "off"
    try:
        check("CEPA_DOCTOR_INSTALL=off desliga a reinstalação",
              D.auto_install_allowed() is False)
        ok, msg = D.fix_install({"kind": "install", "repo": str(REPO)})
        check("e o fix_install recusa em vez de rodar o install.sh",
              ok is False and "instalação da máquina" in msg, msg)
    finally:
        os.environ.pop("CEPA_DOCTOR_INSTALL", None)
        if before is not None:
            os.environ["CEPA_DOCTOR_INSTALL"] = before


def test_temporary_directory_turns_it_off():
    D = load_doctor()
    origin = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            check("doctor rodando de um diretório temporário não reinstala",
                  D.auto_install_allowed() is False)
        finally:
            os.chdir(origin)


def test_tmp_also_counts_as_temporary():
    """On macOS Python's tempdir is /var/folders/...; whoever runs from /tmp
    would slip through if the list had only gettempdir().
    """
    D = load_doctor()
    origin = Path.cwd()
    target = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path("/tmp")
    if not target.is_dir():
        return
    os.chdir(target)
    try:
        check("/tmp também conta como temporário",
              D.auto_install_allowed() is False)
    finally:
        os.chdir(origin)


def test_real_use_remains_allowed():
    D = load_doctor()
    origin = Path.cwd()
    os.chdir(REPO)
    try:
        check("fora do temporário e sem a variável, a reinstalação segue permitida",
              D.auto_install_allowed() is True)
    finally:
        os.chdir(origin)


def test_blocked_becomes_owner_decision_not_failure():
    D = load_doctor()
    os.environ["CEPA_DOCTOR_INSTALL"] = "off"
    try:
        D.RESULTS.clear()
        D.warn("plugins", "common: repo está em 9.9.9 mas o cache instalado é 1.0.0",
               fix={"kind": "install", "repo": str(REPO)})
        pending = D.pending_fixes()
        check("a reinstalação bloqueada sai do lote automático",
              all(f["kind"] != "install" for f in pending), pending)
        check("mas o achado continua no relatório para o dono decidir",
              any("cache instalado" in r[2] for r in D.RESULTS))
    finally:
        os.environ.pop("CEPA_DOCTOR_INSTALL", None)
        D.RESULTS.clear()


def test_end_to_end_install_sh_does_not_run():
    """The proof that matters: `bin/install.sh` is not EXECUTED.

    Builds a fake HOME whose marketplace points to a fake repo, whose
    install.sh only writes a marker. If the doctor runs the reinstall, the
    marker appears — that is how the owner's installation was swapped.
    """
    import json
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        fake_home = tmpp / "home"
        (fake_home / ".claude" / "plugins").mkdir(parents=True)
        fake_repo = tmpp / "cepa-falso"
        (fake_repo / "bin").mkdir(parents=True)
        marker = tmpp / "INSTALL-RODOU"
        (fake_repo / "bin" / "install.sh").write_text(
            f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
        (fake_repo / "bin" / "install.sh").chmod(0o755)
        for plug in ("common",):
            d = fake_repo / plug / ".claude-plugin"
            d.mkdir(parents=True)
            (d / "plugin.json").write_text(
                json.dumps({"name": plug, "version": "9.9.9"}), encoding="utf-8")
        (fake_home / ".claude" / "plugins" / "known_marketplaces.json").write_text(
            json.dumps({"cepa": {"installLocation": str(fake_repo)}}), encoding="utf-8")

        proj = tmpp / "proj"
        proj.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=proj)
        (proj / ".claude").mkdir()
        (proj / ".claude" / "no-build").touch()

        env = dict(os.environ, HOME=str(fake_home))
        env.pop("CEPA_DOCTOR_INSTALL", None)
        subprocess.run([sys.executable, str(DOCTOR), "--fix"], capture_output=True,
                       text=True, cwd=str(proj), env=env)
        check("o install.sh NÃO roda quando o doctor é chamado de um temporário",
              not marker.exists())


def test_fix_that_does_not_resolve_runs_only_once():
    """The batch tries each correction ONCE, even if the finding survives.

    `--fix` re-diagnoses between passes (one correction changes what the
    others see). Without memory of what was already tried, a correction that does not
    resolve its own finding was applied again on every pass: three
    runs of install.sh and the same line repeated three times in the report.
    """
    import json
    import subprocess
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        fake_home = tmpp / "home"
        (fake_home / ".claude" / "plugins").mkdir(parents=True)
        fake_repo = tmpp / "cepa-falso"
        (fake_repo / "bin").mkdir(parents=True)
        counter = tmpp / "execucoes"
        (fake_repo / "bin" / "install.sh").write_text(
            f"#!/bin/sh\necho x >> '{counter}'\n", encoding="utf-8")
        (fake_repo / "bin" / "install.sh").chmod(0o755)
        d = fake_repo / "common" / ".claude-plugin"
        d.mkdir(parents=True)
        (d / "plugin.json").write_text(
            json.dumps({"name": "common", "version": "9.9.9"}), encoding="utf-8")
        (fake_home / ".claude" / "plugins" / "known_marketplaces.json").write_text(
            json.dumps({"cepa": {"installLocation": str(fake_repo)}}), encoding="utf-8")

        proj = tmpp / "proj"
        proj.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=proj)
        (proj / ".claude").mkdir()
        (proj / ".claude" / "no-build").touch()

        # HOME=temporary but cwd=real repo: the temporary lock does not apply
        # here, otherwise the install would not even be attempted and the test would measure nothing.
        env = dict(os.environ, HOME=str(fake_home))
        env.pop("CEPA_DOCTOR_INSTALL", None)
        out = subprocess.run([sys.executable, str(DOCTOR), "--fix"], capture_output=True,
                             text=True, cwd=str(REPO), env=env)
        n = len(counter.read_text().splitlines()) if counter.exists() else 0
        check("a reinstalação que não resolve o achado roda UMA vez, não três",
              n == 1, f"{n} execuções\n{out.stdout[-800:]}")
        check("e o relatório não repete a mesma linha",
              out.stdout.count("plugins reinstalados a partir do repo") <= 1, out.stdout[-800:])


def main():
    test_variable_turns_it_off()
    test_temporary_directory_turns_it_off()
    test_tmp_also_counts_as_temporary()
    test_real_use_remains_allowed()
    test_blocked_becomes_owner_decision_not_failure()
    test_end_to_end_install_sh_does_not_run()
    test_fix_that_does_not_resolve_runs_only_once()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
