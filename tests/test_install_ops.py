#!/usr/bin/env python3
"""Regression tests for the operational-update route (A2).

Covers the two halves that make a harness update recoverable:
  - bin/install.sh --rollback: refuses with no rollback point, and restores
    the set-aside cache when there is one (HOME is sandboxed — these tests
    never touch the real plugin cache);
  - cepa-doctor's check_ops: an install that died halfway is reported as a
    FAILURE, not silence; a rollback is reported as a live-state warning; a
    clean install is ok, and says whether a way back exists.

Run: python3 tests/test_install_ops.py
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INSTALL = REPO / "bin" / "install.sh"
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def load_doctor():
    spec = importlib.util.spec_from_loader(
        "cepa_doctor",
        importlib.machinery.SourceFileLoader("cepa_doctor", str(DOCTOR)),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def iso(days_ago=0):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


# ── install.sh --rollback ───────────────────────────────────────────────────

def test_rollback():
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, HOME=home)
        cache = Path(home) / ".claude" / "plugins" / "cache" / "cepa"
        prev = Path(str(cache) + ".prev")

        # no rollback point → refuses, and says why
        r = subprocess.run(["bash", str(INSTALL), "--rollback"],
                           capture_output=True, text=True, env=env, cwd=home)
        check("--rollback sem ponto de restauração falha", r.returncode == 1, r.stdout)
        check("explica que só --clean cria o ponto",
              "--clean" in r.stdout, r.stdout)

        # with a rollback point → restores it, keeps the replaced one
        prev.mkdir(parents=True)
        (prev / "common").mkdir()
        (prev / "common" / "0.16.0").mkdir()
        cache.mkdir(parents=True)
        (cache / "common").mkdir()
        (cache / "common" / "0.18.0").mkdir()

        r = subprocess.run(["bash", str(INSTALL), "--rollback"],
                           capture_output=True, text=True, env=env, cwd=home)
        check("--rollback com ponto restaura (exit 0)", r.returncode == 0,
              r.stdout + r.stderr)
        check("cache live volta a ser o anterior",
              (cache / "common" / "0.16.0").is_dir()
              and not (cache / "common" / "0.18.0").is_dir(),
              sorted(p.name for p in (cache / "common").iterdir()))
        check("o cache substituído é preservado, não apagado",
              (Path(str(cache) + ".rolledback") / "common" / "0.18.0").is_dir(),
              "")
        check("avisa que a sessão precisa reiniciar",
              "Restart Claude Code" in r.stdout, r.stdout)

        rec = json.loads((Path(home) / ".claude" / "ops" / "last-install.json").read_text())
        check("registra status rolled_back", rec["status"] == "rolled_back", rec)
        check("registro diz de onde para onde",
              rec["versions_before"] == {"common": "0.18.0"}
              and rec["versions_target"] == {"common": "0.16.0"}, rec)


def _stub_claude(home):
    """A no-op `claude` on PATH so the full install path is runnable offline.

    Without this the --clean branch is untestable, and an earlier version of
    this suite proved only that --rollback CONSUMES a rollback point — never
    that --clean CREATES one. Deleting the preservation left every test green.
    """
    binx = Path(home) / "stubbin"
    binx.mkdir(parents=True, exist_ok=True)
    stub = binx / "claude"
    stub.write_text("#!/bin/sh\nexit 0\n")
    stub.chmod(0o755)
    return str(binx)


def test_clean_creates_rollback_point():
    with tempfile.TemporaryDirectory() as home:
        host = Path(home) / "host"
        host.mkdir()
        env = dict(os.environ, HOME=home,
                   PATH=_stub_claude(home) + os.pathsep + os.environ["PATH"])
        cache = Path(home) / ".claude" / "plugins" / "cache" / "cepa"
        prev = Path(str(cache) + ".prev")

        # a live cache exists; --clean must set it aside, not destroy it
        (cache / "common" / "0.17.0").mkdir(parents=True)
        r = subprocess.run(["bash", str(INSTALL), "--clean", str(host)],
                           capture_output=True, text=True, env=env, cwd=home)
        check("--clean roda até o fim", r.returncode == 0,
              (r.stdout + r.stderr)[-600:])
        check("--clean PRESERVA o cache anterior (ponto de rollback)",
              (prev / "common" / "0.17.0").is_dir(),
              f"prev={list(prev.rglob('*')) if prev.exists() else 'AUSENTE'}")
        check("--clean anuncia como desfazer", "--rollback" in r.stdout, r.stdout)

        rec = json.loads((Path(home) / ".claude" / "ops" / "last-install.json").read_text())
        check("registro fecha em ok", rec["status"] == "ok", rec)
        check("registro guarda o estado ANTERIOR",
              rec["versions_before"] == {"common": "0.17.0"}, rec)
        check("registro guarda o alvo (versões do repo)",
              rec["versions_target"].get("common") is not None
              and rec["versions_target"]["common"] != "0.17.0", rec)
        check("registro aponta o ponto de rollback",
              rec["previous_cache_dir"] == str(prev), rec)


def test_interrupted_install_leaves_in_progress():
    """An install killed mid-flight must leave a record the doctor can catch."""
    with tempfile.TemporaryDirectory() as home:
        host = Path(home) / "host"
        host.mkdir()
        # a `claude` stub that fails: install dies AFTER the in_progress record
        # is written and BEFORE the closing ok — the exact halfway state.
        binx = Path(home) / "stubbin"
        binx.mkdir(parents=True)
        stub = binx / "claude"
        stub.write_text("#!/bin/sh\n[ \"$1\" = plugin ] && [ \"$2\" = install ] && exit 3\nexit 0\n")
        stub.chmod(0o755)
        env = dict(os.environ, HOME=home,
                   PATH=str(binx) + os.pathsep + os.environ["PATH"])

        r = subprocess.run(["bash", str(INSTALL), str(host)],
                           capture_output=True, text=True, env=env, cwd=home)
        check("install interrompido falha", r.returncode != 0, r.stdout)

        rec_path = Path(home) / ".claude" / "ops" / "last-install.json"
        check("mesmo interrompido, deixou registro", rec_path.is_file(), "")
        rec = json.loads(rec_path.read_text())
        check("registro fica em in_progress (não em ok)",
              rec["status"] == "in_progress", rec)

        d = load_doctor()
        d.RESULTS.clear()
        d.check_ops(rec)
        check("doctor ACUSA o install interrompido",
              d.RESULTS and d.RESULTS[0][0] == "fail", d.RESULTS)


# ── cepa-doctor check_ops ───────────────────────────────────────────────────

def test_check_ops():
    d = load_doctor()

    def verdicts(rec):
        d.RESULTS.clear()
        d.check_ops(rec)
        # RESULTS carrega (level, area, msg, fix) desde o --fix do doctor;
        # este teste só olha nível e mensagem.
        return [(r[0], r[2]) for r in d.RESULTS]

    v = verdicts(None)
    check("sem registro → aviso (não silêncio)", v and v[0][0] == "warn", v)

    v = verdicts({"status": "in_progress", "started_at": iso(0.5)})
    check("install que não terminou → FALHA", v and v[0][0] == "fail", v)
    check("a falha oferece as duas saídas",
          "--rollback" in v[0][1] and "install.sh" in v[0][1], v)
    check("a falha diz há quanto tempo", "começou há" in v[0][1], v)

    v = verdicts({"status": "rolled_back", "started_at": iso(1),
                  "finished_at": iso(1)})
    check("rollback → aviso de estado live inesperado",
          v and v[0][0] == "warn" and "ANTERIOR" in v[0][1], v)

    with tempfile.TemporaryDirectory() as tmp:
        v = verdicts({"status": "ok", "started_at": iso(3), "finished_at": iso(3),
                      "previous_cache_dir": tmp})
        check("install ok com rollback disponível → ok",
              v and v[0][0] == "ok" and "rollback disponível" in v[0][1], v)
        check("ok informa a idade", "há 3d" in v[0][1], v)

    v = verdicts({"status": "ok", "started_at": iso(0), "finished_at": iso(0),
                  "previous_cache_dir": "/nao/existe"})
    check("install ok sem ponto de rollback → ok, mas diz que não há",
          v and v[0][0] == "ok" and "sem ponto de rollback" in v[0][1], v)


def main():
    test_rollback()
    test_clean_creates_rollback_point()
    test_interrupted_install_leaves_in_progress()
    test_check_ops()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
