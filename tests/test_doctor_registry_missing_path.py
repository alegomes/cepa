#!/usr/bin/env python3
"""CS-9: the doctor fails when the plugin registry points to a folder that is gone.

`~/.claude/plugins/known_marketplaces.json` says where `cepa` lives
(`installLocation`). When that folder was deleted (a worktree removed after the
run that installed from it), the old doctor said "marketplace 'cepa' não
encontrado em known_marketplaces.json": false (it is registered) and with no way
out. The right finding names the path that vanished and, when
`~/.claude/ops/last-install.json` knows the `main_clone`, offers the `install`
fix with that clone as the repo.

How the offered fix is observed from the CLI: the doctor runs as a subprocess
with a temporary HOME and a FAKE `main_clone` whose `bin/install.sh` only writes
its own working directory to a marker. `--fix` from the real repo (outside the
temporary-directory lock) runs it; the marker proves WHICH repo the fix pointed
at. Nothing here can touch the machine's real plugins: HOME is temporary and the
only install.sh that can run is the fake one.

Run: python3 tests/test_doctor_registry_missing_path.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

FAILURES = []
OLD_MSG = "não encontrado em known_marketplaces.json"


def short(detail):
    """Failure detail without the unrelated findings of a whole doctor report."""
    if not isinstance(detail, str):
        return detail
    keep = [l for l in detail.splitlines()
            if "[plugins]" in l or "reinstalar" in l or "install.sh" in l]
    return " | ".join(l.strip()[:200] for l in keep) or detail[:300]


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {short(detail)}")
        FAILURES.append(name)


def make_world(tmp: Path, registry, last_install):
    """Temporary HOME + fake main_clone. `registry` / `last_install` are callables
    receiving (tmp, clone) and returning the JSON object to write (or None for no file)."""
    home = tmp / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "ops").mkdir(parents=True)
    clone = tmp / "clone"
    (clone / "bin").mkdir(parents=True)
    marker = tmp / "install-cwd"
    (clone / "bin" / "install.sh").write_text(
        f"#!/bin/sh\npwd > '{marker}'\n", encoding="utf-8")
    (clone / "bin" / "install.sh").chmod(0o755)
    reg = registry(tmp, clone)
    if reg is not None:
        (home / ".claude" / "plugins" / "known_marketplaces.json").write_text(
            json.dumps(reg), encoding="utf-8")
    rec = last_install(tmp, clone)
    if rec is not None:
        (home / ".claude" / "ops" / "last-install.json").write_text(
            json.dumps(rec), encoding="utf-8")
    return home, clone, marker


def run_doctor(home, *args, install_off=False):
    env = dict(os.environ, HOME=str(home))
    env.pop("CEPA_DOCTOR_INSTALL", None)
    if install_off:
        env["CEPA_DOCTOR_INSTALL"] = "off"
    # cwd=REPO: outside the temporary-directory lock, so --fix may run the FAKE install.sh.
    p = subprocess.run([sys.executable, str(DOCTOR), *args], capture_output=True,
                       text=True, cwd=str(REPO), env=env)
    return p.stdout + p.stderr


def plugins_fail_lines(out):
    return [l for l in out.splitlines() if "✗" in l and "[plugins]" in l]


def test_missing_path_with_main_clone():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        gone = tmpp / "worktree-que-sumiu"
        home, clone, marker = make_world(
            tmpp,
            lambda t, c: {"cepa": {"installLocation": str(gone)}},
            lambda t, c: {"status": "ok", "main_clone": str(c)})
        out = run_doctor(home)
        lines = plugins_fail_lines(out)
        check("falha de plugins nomeia o caminho inexistente",
              any(str(gone) in l for l in lines), out)
        check("não imprime mais 'não encontrado em known_marketplaces.json'",
              OLD_MSG not in out, out)
        check("oferece o conserto install (anunciado como correção mecânica)",
              "reinstalar os plugins" in out, out)
        check("sem --fix nada foi instalado", not marker.exists())

        out = run_doctor(home, "--fix")
        check("--fix roda o install.sh do main_clone",
              marker.exists() and Path(marker.read_text().strip()).resolve() == clone.resolve(),
              f"{marker.read_text() if marker.exists() else 'install.sh não rodou'}\n{out}")

        marker.unlink(missing_ok=True)
        out = run_doctor(home, "--fix", install_off=True)
        check("com CEPA_DOCTOR_INSTALL=off o install.sh não roda, e a falha segue no relatório",
              not marker.exists() and any(str(gone) in l for l in plugins_fail_lines(out)), out)


def test_missing_path_without_usable_main_clone():
    cases = {
        "sem last-install.json": lambda t, c: None,
        "last-install sem main_clone": lambda t, c: {"status": "ok"},
        "main_clone aponta para pasta que não existe":
            lambda t, c: {"status": "ok", "main_clone": str(t / "clone-sumiu")},
    }
    for label, rec in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            gone = tmpp / "worktree-que-sumiu"
            home, _clone, marker = make_world(
                tmpp, lambda t, c: {"cepa": {"installLocation": str(gone)}}, rec)
            out = run_doctor(home, "--fix")
            lines = plugins_fail_lines(out)
            check(f"[{label}] ainda falha nomeando o caminho",
                  any(str(gone) in l for l in lines), out)
            check(f"[{label}] pede bin/install.sh à mão no clone do cepa",
                  any("bin/install.sh" in l for l in lines), out)
            check(f"[{label}] não oferece conserto que não consegue fazer",
                  not marker.exists() and "reinstalar os plugins" not in out, out)
            check(f"[{label}] não diz que o marketplace não está registrado",
                  OLD_MSG not in out, out)


def test_genuinely_absent_keeps_old_message():
    cases = {
        "cepa ausente do registro": lambda t, c: {"outro": {"installLocation": str(t)}},
        "registro sem installLocation": lambda t, c: {"cepa": {}},
        "arquivo do registro não existe": lambda t, c: None,
    }
    for label, reg in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            home, _clone, marker = make_world(
                tmpp, reg, lambda t, c: {"status": "ok", "main_clone": str(c)})
            out = run_doctor(home, "--fix")
            check(f"[{label}] mantém a mensagem de não encontrado",
                  any(OLD_MSG in l for l in plugins_fail_lines(out)), out)
            check(f"[{label}] não oferece conserto", not marker.exists(), out)


def test_unreadable_registry_keeps_old_message():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home, _clone, _marker = make_world(
            tmpp, lambda t, c: None, lambda t, c: {"status": "ok", "main_clone": str(c)})
        (home / ".claude" / "plugins" / "known_marketplaces.json").write_text("{nao é json")
        out = run_doctor(home)
        check("[registro ilegível] mantém a mensagem de não encontrado",
              any(OLD_MSG in l for l in plugins_fail_lines(out)), out)


if __name__ == "__main__":
    test_missing_path_with_main_clone()
    test_missing_path_without_usable_main_clone()
    test_genuinely_absent_keeps_old_message()
    test_unreadable_registry_keeps_old_message()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("tudo ok")
