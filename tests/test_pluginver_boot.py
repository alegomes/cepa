#!/usr/bin/env python3
"""Tests of the repo↔cache warning at session boot (P0-4 of the 2026-08-17 review).

No dependencies — run with `python3 tests/test_pluginver_boot.py`.
Exits non-zero on failure.

What is being locked, and why each case exists:

  - **Divergence warns.** It is the project's failure no. 1 (fix committed, not
    installed, everyone operating as if it were in force). If this case starts
    to go green with the warning absent, the alarm has vanished.
  - **Silence when up to date.** A warning that shows up every session becomes noise and
    trains the eye to skip the day it matters. Silence is a requirement, not
    chance.
  - **An empty cache counts as divergence.** "Nothing installed" is the extreme version
    of "what runs is not the repo".
  - **The message names the cost, not just the fact.** Saying "0.28.0 → 0.27.1" to
    someone who does not know the versioning scheme informs nothing; the warning has to
    say what is NOT in force.
  - **Never breaks the boot.** A comparator that takes down SessionStart would be
    switched off, and then it protects no one. A nonexistent directory, corrupted JSON
    and denied permission must come out as silence, not as an exception.
"""

import importlib.machinery
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

# This test cites a telemetry emitter hook. Today it does not get to execute it,
# but citing and executing are one step apart, and that distance is what
# left 7 tests polluting the real ledger for a month. See
# tests/_isolated_telemetry.py.
from _isolated_telemetry import isolate

isolate()


REPO = Path(__file__).resolve().parent.parent
MOD = REPO / "common" / "hooks" / "_pluginver.py"

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL {label}{' — ' + detail if detail else ''}")


def load(home: Path):
    """Loads _pluginver with HOME pointing to a fake world.

    CLAUDE_DIR is resolved at import (module-level), so each scenario needs
    a fresh import — hence the manual loader instead of a plain import.
    """
    os.environ["HOME"] = str(home)
    Path.home.cache_clear() if hasattr(Path.home, "cache_clear") else None
    loader = importlib.machinery.SourceFileLoader(f"_pv_{home.name}", str(MOD))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def make_world(tmp: Path, repo_versions: dict, cache_versions: dict, install=None):
    """Builds a ~/.claude + a clone of the repo with the requested versions."""
    home = tmp
    claude = home / ".claude"
    repo = home / "src" / "cepa"
    for name, ver in repo_versions.items():
        d = repo / name / ".claude-plugin"
        d.mkdir(parents=True, exist_ok=True)
        (d / "plugin.json").write_text(json.dumps({"name": name, "version": ver}))
    for name, vers in cache_versions.items():
        for v in vers:
            (claude / "plugins" / "cache" / "cepa" / name / v).mkdir(parents=True, exist_ok=True)
    (claude / "plugins").mkdir(parents=True, exist_ok=True)
    (claude / "plugins" / "known_marketplaces.json").write_text(
        json.dumps({"cepa": {"installLocation": str(repo)}})
    )
    if install is not None:
        (claude / "ops").mkdir(parents=True, exist_ok=True)
        (claude / "ops" / "last-install.json").write_text(json.dumps(install))
    return home


# ── cases ────────────────────────────────────────────────────────────────────

def test_drift_warns(tmp):
    home = make_world(
        Path(tmp) / "a",
        repo_versions={"common": "0.28.0", "board-flow": "0.12.0"},
        cache_versions={"common": ["0.27.1"], "board-flow": ["0.12.0"]},
    )
    m = load(home)
    n = m.boot_notice()
    check("divergência produz aviso", n is not None)
    if n:
        check("o aviso nomeia o plugin defasado", "common" in n)
        check("o aviso mostra as duas versões", "0.28.0" in n and "0.27.1" in n)
        check("o aviso NÃO acusa quem está em dia", "board-flow" not in n)
        check("o aviso diz o que não está valendo (custo, não só o fato)",
              "fora do ar" in n or "não está valendo" in n.lower())
        check("o aviso nomeia a saída", "install.sh" in n)


def test_up_to_date_stays_silent(tmp):
    home = make_world(
        Path(tmp) / "b",
        repo_versions={"common": "0.27.1"},
        cache_versions={"common": ["0.27.0", "0.27.1"]},
    )
    m = load(home)
    check("repo == cache → silêncio", m.boot_notice() is None)


def test_newer_cache_stays_silent(tmp):
    """A cache ahead of the repo is not this alarm's problem.

    It really happens: another clone installed a newer version. That deserves
    the doctor, not an alarm at boot — the warning exists for "I edited and did not
    install", and firing here would only teach people to ignore it.
    """
    home = make_world(
        Path(tmp) / "c",
        repo_versions={"common": "0.27.0"},
        cache_versions={"common": ["0.28.0"]},
    )
    m = load(home)
    check("cache à frente do repo → silêncio", m.boot_notice() is None)


def test_empty_cache_warns(tmp):
    home = make_world(
        Path(tmp) / "d",
        repo_versions={"common": "0.27.1"},
        cache_versions={},
    )
    m = load(home)
    n = m.boot_notice()
    check("plugin sem nada no cache avisa", n is not None)
    if n:
        check("diz que não há nada instalado", "nada instalado" in n)


def test_install_age_enters(tmp):
    home = make_world(
        Path(tmp) / "e",
        repo_versions={"common": "0.28.0"},
        cache_versions={"common": ["0.27.1"]},
        install={"status": "ok", "finished_at": "2026-08-01T10:00:00+00:00"},
    )
    m = load(home)
    n = m.boot_notice() or ""
    check("a idade do último install aparece", "último install há" in n)


def test_never_breaks_the_boot(tmp):
    # 1. ~/.claude nonexistent
    home = Path(tmp) / "f"
    home.mkdir(parents=True, exist_ok=True)
    m = load(home)
    try:
        check("sem ~/.claude → None, sem exceção", m.boot_notice() is None)
    except Exception as e:  # noqa: BLE001
        check("sem ~/.claude → None, sem exceção", False, repr(e))

    # 2. corrupted known_marketplaces.json
    home2 = Path(tmp) / "g"
    (home2 / ".claude" / "plugins").mkdir(parents=True, exist_ok=True)
    (home2 / ".claude" / "plugins" / "known_marketplaces.json").write_text("{isto não é json")
    m2 = load(home2)
    try:
        check("marketplaces corrompido → None, sem exceção", m2.boot_notice() is None)
    except Exception as e:  # noqa: BLE001
        check("marketplaces corrompido → None, sem exceção", False, repr(e))

    # 3. unreadable plugin.json in the repo — the plugin vanishes from the scan, the others go on
    home3 = make_world(
        Path(tmp) / "h",
        repo_versions={"common": "0.28.0"},
        cache_versions={"common": ["0.27.1"], "design": ["0.1.0"]},
    )
    bad = home3 / "src" / "cepa" / "design" / ".claude-plugin"
    bad.mkdir(parents=True, exist_ok=True)
    (bad / "plugin.json").write_text("{quebrado")
    m3 = load(home3)
    try:
        n = m3.boot_notice()
        check("plugin.json quebrado não derruba o resto", n is not None and "common" in n)
    except Exception as e:  # noqa: BLE001
        check("plugin.json quebrado não derruba o resto", False, repr(e))


def test_hook_imports_the_module():
    """The session-registry must really call this — it is not enough to exist.

    Equivalent perturbation: deleting the call in session-registry.py turns this
    case red. It is what separates "module written" from "alarm on".
    """
    src = (REPO / "common" / "hooks" / "session-registry.py").read_text(encoding="utf-8")
    check("session-registry importa _pluginver", "import _pluginver" in src)
    check("session-registry chama boot_notice", "boot_notice()" in src)
    # The warning must be the FIRST of the list: a version drift contaminates the
    # reading of all the other warnings of the session.
    i_drift = src.find("boot_notice()")
    i_overlap = src.find("other live session")
    check("o aviso de versão vem antes do de overlap",
          i_drift != -1 and i_overlap != -1 and i_drift < i_overlap)


def main():
    real_home = os.environ.get("HOME")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            test_drift_warns(tmp)
            test_up_to_date_stays_silent(tmp)
            test_newer_cache_stays_silent(tmp)
            test_empty_cache_warns(tmp)
            test_install_age_enters(tmp)
            test_never_breaks_the_boot(tmp)
        finally:
            if real_home:
                os.environ["HOME"] = real_home
    test_hook_imports_the_module()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
