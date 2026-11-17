#!/usr/bin/env python3
"""CS-10: the doctor warns when the plugin registry points outside ~/.claude/cepa-live.

`~/.claude/plugins/known_marketplaces.json` says where `cepa` lives
(`installLocation`). The fixed folder is `~/.claude/cepa-live`. When the registry
points somewhere else that still EXISTS (typically a worktree), nothing is broken
today, but the registry dies the day that folder is removed (CS-9). So the doctor
warns (not fails), names the registered path, and offers the `install` fix. The
fix runs from `main_clone` when it is an existing directory; otherwise from the
registered folder itself (a cepa checkout with its own `bin/install.sh`).

Observation of the fix from the CLI: temporary HOME, a FAKE `main_clone` and a
FAKE registered folder whose `bin/install.sh` only write their cwd to a marker.
Nothing here can touch the machine's real plugins.

Also pinned: two install fixes with different repos in one report run the install
once, not twice.

Run: python3 tests/test_doctor_registry_outside_live.py
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCTOR = REPO / "common" / "bin" / "cepa-doctor"

FAILURES = []


def short(detail):
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


def fake_checkout(path: Path, marker: Path):
    (path / "bin").mkdir(parents=True)
    (path / "bin" / "install.sh").write_text(
        f"#!/bin/sh\npwd >> '{marker}'\n", encoding="utf-8")
    (path / "bin" / "install.sh").chmod(0o755)


def make_world(tmp: Path, registered: Path, main_clone="ok"):
    """Temporary HOME with the registry pointing at `registered`. `main_clone`:
    "ok" (existing fake clone), "gone" (path that does not exist) or None (no record)."""
    home = tmp / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    (home / ".claude" / "ops").mkdir(parents=True)
    marker = tmp / "install-cwd"
    clone = tmp / "clone"
    fake_checkout(clone, marker)
    if not registered.exists():
        fake_checkout(registered, marker)
    (home / ".claude" / "plugins" / "known_marketplaces.json").write_text(
        json.dumps({"cepa": {"installLocation": str(registered)}}), encoding="utf-8")
    if main_clone is not None:
        mc = clone if main_clone == "ok" else tmp / "clone-sumiu"
        (home / ".claude" / "ops" / "last-install.json").write_text(
            json.dumps({"status": "ok", "main_clone": str(mc)}), encoding="utf-8")
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


def plugins_lines(out, mark):
    return [l for l in out.splitlines() if mark in l and "[plugins]" in l
            and "cepa-live" in l]


def marker_cwds(marker):
    return [Path(l).resolve() for l in marker.read_text().split() if l] if marker.exists() else []


def test_outside_with_main_clone():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        wt = tmpp / "worktree-existente"
        home, clone, marker = make_world(tmpp, wt)
        out = run_doctor(home)
        warns = plugins_lines(out, "⚠")
        check("aviso de plugins nomeia o caminho registrado e cepa-live",
              any(str(wt) in l for l in warns), out)
        check("o aviso diz que o registro está fora de ~/.claude/cepa-live",
              any("fora de ~/.claude/cepa-live" in l for l in warns), out)
        check("o aviso diz que reinstalar reaponta o registro para ~/.claude/cepa-live",
              any("reaponta o registro para ~/.claude/cepa-live" in l for l in warns), out)
        check("é aviso (⚠), não falha (✗)", bool(warns) and not plugins_lines(out, "✗"), out)
        check("o aviso diz de qual clone a reinstalação sai",
              any(str(clone) in l for l in warns), out)
        check("oferece o conserto install", "reinstalar os plugins" in out, out)
        check("sem --fix nada foi instalado", not marker.exists())

        run_doctor(home, "--fix")
        cwds = marker_cwds(marker)
        check("--fix roda o install.sh do main_clone, uma vez só",
              cwds == [clone.resolve()], str(cwds))

        marker.unlink(missing_ok=True)
        out = run_doctor(home, "--fix", install_off=True)
        check("com CEPA_DOCTOR_INSTALL=off o install.sh não roda e o aviso fica",
              not marker.exists() and any(str(wt) in l for l in plugins_lines(out, "⚠")), out)


def test_outside_without_usable_main_clone():
    for label, mc in {"sem last-install.json": None,
                      "main_clone aponta para pasta que não existe": "gone"}.items():
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            wt = tmpp / "worktree-existente"
            home, _clone, marker = make_world(tmpp, wt, main_clone=mc)
            out = run_doctor(home)
            check(f"[{label}] avisa e oferece o install a partir da pasta registrada",
                  any(str(wt) in l for l in plugins_lines(out, "⚠"))
                  and "reinstalar os plugins" in out, out)
            check(f"[{label}] o aviso diz que a reinstalação sai da própria pasta registrada",
                  any(f"a própria pasta registrada {wt}" in l for l in plugins_lines(out, "⚠")), out)
            run_doctor(home, "--fix")
            check(f"[{label}] --fix roda o install.sh da pasta registrada",
                  marker_cwds(marker) == [wt.resolve()], str(marker_cwds(marker)))


def test_registry_at_fixed_folder_is_quiet():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home = tmpp / "home"
        live = home / ".claude" / "cepa-live"
        h, _clone, marker = make_world(tmpp, live)
        out = run_doctor(h)
        check("registro na pasta fixa: nenhum aviso de fora do cepa-live",
              not plugins_lines(out, "⚠") and not plugins_lines(out, "✗"), out)
        check("registro na pasta fixa: nada instalado", not marker.exists())


def test_registry_at_fixed_folder_via_symlink_is_quiet():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home = tmpp / "home"
        real = tmpp / "real-live"
        marker = tmpp / "install-cwd"
        fake_checkout(real, marker)
        (home / ".claude").mkdir(parents=True)
        (home / ".claude" / "cepa-live").symlink_to(real)
        # registry written with the resolved path, the fixed folder being a symlink
        h, _c, _m = make_world(tmpp, real)
        out = run_doctor(h)
        check("symlink para a pasta fixa não gera aviso falso",
              not plugins_lines(out, "⚠"), out)


def test_two_installs_collapse_into_one():
    spec = importlib.util.spec_from_loader(
        "cepa_doctor", importlib.machinery.SourceFileLoader("cepa_doctor", str(DOCTOR)))
    D = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(D)
    saved = os.environ.pop("CEPA_DOCTOR_INSTALL", None)
    try:
        D.RESULTS.clear()
        D.warn("plugins", "fora do cepa-live", fix={"kind": "install", "repo": "/a"})
        D.warn("plugins", "deriva", fix={"kind": "install", "repo": "/b"})
        fixes = D.pending_fixes()
        check("dois consertos install com repos diferentes viram um só",
              len([f for f in fixes if f["kind"] == "install"]) == 1, str(fixes))
        check("vale o primeiro (o do aviso de fora do cepa-live)",
              bool(fixes) and fixes[0]["repo"] == "/a", str(fixes))
        D.RESULTS.clear()
        D.warn("x", "a", fix={"kind": "archive_handoff", "path": "/p1"})
        D.warn("x", "b", fix={"kind": "archive_handoff", "path": "/p2"})
        check("consertos de outros tipos não são colapsados", len(D.pending_fixes()) == 2)
    finally:
        if saved is not None:
            os.environ["CEPA_DOCTOR_INSTALL"] = saved


def test_warning_recorded_before_drift_findings():
    """Order pin: check_plugins records the outside-cepa-live warning BEFORE the
    drift findings, so the install that survives the collapse runs from main_clone."""
    spec = importlib.util.spec_from_loader(
        "cepa_doctor", importlib.machinery.SourceFileLoader("cepa_doctor", str(DOCTOR)))
    D = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(D)
    saved = os.environ.pop("CEPA_DOCTOR_INSTALL", None)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            wt = tmpp / "worktree-existente"
            home, clone, _marker = make_world(tmpp, wt)
            D.CLAUDE_DIR = home / ".claude"

            class StubPV:
                @staticmethod
                def scan(repo, enabled):
                    return [{"name": "p", "repo_version": "2", "cache_version": "1",
                             "enabled": True, "missing": False, "drift": True}]

            D.PV = StubPV
            D.RESULTS.clear()
            rec = json.loads((home / ".claude" / "ops" / "last-install.json").read_text())
            D.check_plugins({"enabledPlugins": {}}, rec)
            installs = [f for f in D.pending_fixes() if f["kind"] == "install"]
            check("aviso de fora do cepa-live vem antes do drift: um só install",
                  len(installs) == 1, str(installs))
            check("o install que sobrevive sai do main_clone, não da pasta registrada",
                  bool(installs) and installs[0]["repo"] == str(clone), str(installs))
            warns = [r[2] for r in D.RESULTS if r[0] == "warn" and r[1] == "plugins"]
            check("os dois achados ficam registrados: o aviso de fora do cepa-live",
                  any(str(wt) in m and "fora de ~/.claude/cepa-live" in m for m in warns),
                  " | ".join(warns))
            check("os dois achados ficam registrados: o drift do plugin stubado",
                  any("repo está em 2 mas o cache instalado é 1" in m for m in warns),
                  " | ".join(warns))
    finally:
        D.RESULTS.clear()
        if saved is not None:
            os.environ["CEPA_DOCTOR_INSTALL"] = saved


if __name__ == "__main__":
    test_outside_with_main_clone()
    test_outside_without_usable_main_clone()
    test_registry_at_fixed_folder_is_quiet()
    test_registry_at_fixed_folder_via_symlink_is_quiet()
    test_two_installs_collapse_into_one()
    test_warning_recorded_before_drift_findings()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("tudo ok")
