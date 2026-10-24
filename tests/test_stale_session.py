#!/usr/bin/env python3
"""Regression tests for the version snapshot that the session carries at boot.

The harness already knew how to say "you edited the repo and did not reinstall" (_pluginver.scan
compares REPO with CACHE). It did not know how to say the opposite, which is more treacherous:
you reinstalled WITH the session open — the cache becomes new, the session keeps
executing the hooks it read at opening, and nothing on screen distinguishes the two.

The snapshot (`plugin_versions` in the registry entry) is what makes the question
answerable: comparing what the session loaded with what the cache has NOW.

Contracts guarded here:
  - a session whose snapshot matches the cache → nothing to say;
  - a session whose snapshot fell behind → shows up, with the two versions;
  - a session WITHOUT a snapshot (opened before this check existed) → silence, never an
    alarm invented from data that does not exist;
  - a plugin that vanished from the cache does not become an alert — it leaves the comparison;
  - session-registry.py records the snapshot at SessionStart.

Run with `python3 tests/test_stale_session.py`.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))
import _pluginver as V  # noqa: E402

# This test cites a telemetry emitter hook. Today it does not get to execute it,
# but citing and executing are one step apart, and that distance is what
# left 7 tests polluting the real ledger for a month. See
# tests/_telemetria_isolada.py.
from _telemetria_isolada import isola

isola()


failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def with_cache(mapping):
    """Swaps the real cache for a fixed one, so the test does not depend on the machine."""
    original = V.loaded_now
    V.loaded_now = lambda: mapping
    return original


def test_up_to_date():
    orig = with_cache({"common": "1.0.0", "board-flow": "0.15.0"})
    try:
        r = V.session_stale({"plugin_versions": {"common": "1.0.0",
                                                 "board-flow": "0.15.0"}})
        check("em dia: nada a dizer", r == [], str(r))
    finally:
        V.loaded_now = orig


def test_fell_behind():
    orig = with_cache({"common": "1.0.0", "board-flow": "0.15.0"})
    try:
        r = V.session_stale({"plugin_versions": {"common": "0.30.0",
                                                 "board-flow": "0.15.0"}})
        check("atrasada: aparece", len(r) == 1, str(r))
        check("atrasada: diz as duas versões",
              r == [("common", "0.30.0", "1.0.0")], str(r))
    finally:
        V.loaded_now = orig


def test_without_snapshot_is_silence():
    orig = with_cache({"common": "1.0.0"})
    try:
        check("sem chave: silêncio", V.session_stale({}) == [])
        check("foto vazia: silêncio", V.session_stale({"plugin_versions": {}}) == [])
        check("entrada None: silêncio", V.session_stale(None) == [])
    finally:
        V.loaded_now = orig


def test_plugin_missing_from_cache():
    orig = with_cache({"common": "1.0.0"})
    try:
        r = V.session_stale({"plugin_versions": {"common": "1.0.0",
                                                 "extinto": "0.1.0"}})
        check("plugin fora do cache não vira alerta", r == [], str(r))
    finally:
        V.loaded_now = orig


def test_registry_records_the_snapshot():
    src = (REPO / "common" / "hooks" / "session-registry.py").read_text()
    check("session-registry grava plugin_versions",
          'entry.setdefault("plugin_versions", V.loaded_now())' in src)


def test_loaded_now_does_not_raise():
    """The module's contract: nothing here breaks the caller. A comparator that
    takes down the session boot would be switched off, and then it protects no one.
    """
    try:
        r = V.loaded_now()
        check("loaded_now devolve um mapa", isinstance(r, dict), str(type(r)))
    except Exception as e:  # noqa: BLE001
        check("loaded_now devolve um mapa", False, repr(e))


def main():
    print("test_stale_session")
    for fn in (test_up_to_date, test_fell_behind, test_without_snapshot_is_silence,
               test_plugin_missing_from_cache, test_registry_records_the_snapshot,
               test_loaded_now_does_not_raise):
        fn()
    if failures:
        print(f"\n{len(failures)} falha(s): {', '.join(failures)}")
        return 1
    print("\ntudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
