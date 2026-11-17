#!/usr/bin/env python3
"""CS-11: the doctor compares the cache against the ORIGIN repo, not the registered folder.

With the registry at the fixed folder `~/.claude/cepa-live`, the folder is a copy
made by the installer, so comparing the cache with it always says "all installed".
The origin repo is `repo_dir` from `~/.claude/ops/last-install.json`; when that
folder is gone, `main_clone`. With neither, the doctor says which command to run
and offers no automatic fix (cepa-live has no `bin/install.sh`).

Observation from the CLI: temporary HOME; fake checkouts whose `bin/install.sh`
only writes its cwd to a marker. Nothing here touches the machine's real plugins.

Run: python3 tests/test_doctor_origin_repo.py
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


def short(detail):
    if not isinstance(detail, str):
        return detail
    keep = [l for l in detail.splitlines()
            if "[plugins]" in l or "reinstalar" in l or "install.sh" in l]
    return " | ".join(l.strip()[:220] for l in keep) or detail[:300]


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {short(detail)}")
        FAILURES.append(name)


def fake_checkout(path: Path, version: str, marker: Path = None):
    """A cepa checkout with plugin `common` at `version`. With `marker`, it has a
    bin/install.sh that only records its cwd."""
    pdir = path / "common" / ".claude-plugin"
    pdir.mkdir(parents=True)
    (pdir / "plugin.json").write_text(
        json.dumps({"name": "common", "version": version}), encoding="utf-8")
    if marker is not None:
        (path / "bin").mkdir()
        (path / "bin" / "install.sh").write_text(
            f"#!/bin/sh\npwd >> '{marker}'\n", encoding="utf-8")
        (path / "bin" / "install.sh").chmod(0o755)


def make_world(tmp: Path, live_v="3.6.0", cache_v="3.6.0", repo_dir_v="3.7.0",
               main_clone_v=None, record=True):
    """HOME with the registry at ~/.claude/cepa-live (plugin common at `live_v`),
    the cache at `cache_v`, `common` enabled. `repo_dir_v` / `main_clone_v`: version of
    that checkout, or None for a path that does not exist. `record=False`: no
    last-install.json at all."""
    home = tmp / "home"
    claude = home / ".claude"
    (claude / "plugins").mkdir(parents=True)
    (claude / "ops").mkdir(parents=True)
    marker = tmp / "install-cwd"
    live = claude / "cepa-live"
    fake_checkout(live, live_v)
    (claude / "plugins" / "cache" / "cepa" / "common" / cache_v).mkdir(parents=True)
    (claude / "plugins" / "known_marketplaces.json").write_text(
        json.dumps({"cepa": {"installLocation": str(live)}}), encoding="utf-8")
    (claude / "settings.json").write_text(
        json.dumps({"enabledPlugins": {"common@cepa": True}}), encoding="utf-8")
    repo_dir, main_clone = tmp / "repo-dir", tmp / "main-clone"
    if repo_dir_v:
        fake_checkout(repo_dir, repo_dir_v, marker)
    if main_clone_v:
        fake_checkout(main_clone, main_clone_v, marker)
    if record:
        (claude / "ops" / "last-install.json").write_text(
            json.dumps({"status": "ok", "repo_dir": str(repo_dir),
                        "main_clone": str(main_clone)}), encoding="utf-8")
    return home, repo_dir, main_clone, marker


def run_doctor(home, *args):
    env = dict(os.environ, HOME=str(home))
    env.pop("CEPA_DOCTOR_INSTALL", None)
    # cwd=REPO: outside the temporary-directory lock, so --fix may run the FAKE install.sh.
    p = subprocess.run([sys.executable, str(DOCTOR), *args], capture_output=True,
                       text=True, cwd=str(REPO), env=env)
    return p.stdout + p.stderr


def marker_cwds(marker):
    return [Path(l).resolve() for l in marker.read_text().split() if l] if marker.exists() else []


def test_repo_dir_ahead_of_cache():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home, repo_dir, _mc, marker = make_world(tmpp)
        out = run_doctor(home)
        check("avisa que o repo está em 3.7.0 e o cache em 3.6.0",
              "repo está em 3.7.0 mas o cache instalado é 3.6.0" in out, out)
        check("não diz 'common 3.6.0 instalado e habilitado'",
              "common 3.6.0 instalado e habilitado" not in out, out)
        check("oferece o conserto install", "reinstalar os plugins" in out, out)
        check("origem conhecida: sem aviso 'sem repo de origem'",
              "sem repo de origem" not in out, out)
        check("sem --fix nada foi instalado", not marker.exists())
        run_doctor(home, "--fix")
        check("--fix roda o install.sh do repo_dir",
              marker_cwds(marker) == [repo_dir.resolve()], str(marker_cwds(marker)))


def test_repo_dir_gone_falls_back_to_main_clone():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home, _rd, main_clone, marker = make_world(tmpp, repo_dir_v=None, main_clone_v="3.7.0")
        out = run_doctor(home)
        check("repo_dir sumiu: compara com o main_clone",
              "repo está em 3.7.0 mas o cache instalado é 3.6.0" in out, out)
        run_doctor(home, "--fix")
        check("--fix roda o install.sh do main_clone",
              marker_cwds(marker) == [main_clone.resolve()], str(marker_cwds(marker)))


def test_repo_dir_wins_over_main_clone():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home, repo_dir, _mc, marker = make_world(tmpp, repo_dir_v="3.7.0", main_clone_v="3.9.0")
        out = run_doctor(home)
        check("a mensagem mostra a versão do repo_dir",
              "repo está em 3.7.0 mas o cache instalado é 3.6.0" in out
              and "3.9.0" not in out, out)
        run_doctor(home, "--fix")
        check("--fix roda do repo_dir, não do main_clone",
              marker_cwds(marker) == [repo_dir.resolve()], str(marker_cwds(marker)))


def test_no_origin_known():
    for label, kw in {"sem last-install.json": {"record": False, "repo_dir_v": None},
                      "repo_dir e main_clone não existem": {"repo_dir_v": None}}.items():
        with tempfile.TemporaryDirectory() as tmp:
            tmpp = Path(tmp)
            home, _rd, _mc, marker = make_world(tmpp, **kw)
            out = run_doctor(home)
            warns = [l for l in out.splitlines() if "⚠" in l and "[plugins]" in l]
            check(f"[{label}] avisa que não há repo de origem e nomeia sh bin/install.sh",
                  any("repo de origem" in l and "sh bin/install.sh" in l for l in warns), out)
            check(f"[{label}] sem linha ok 'instalado e habilitado'",
                  "instalado e habilitado" not in out, out)
            check(f"[{label}] não oferece conserto install", "reinstalar os plugins" not in out, out)
            run_doctor(home, "--fix")
            check(f"[{label}] --fix não roda nada", not marker.exists())


def write_record(home, rec):
    (home / ".claude" / "ops" / "last-install.json").write_text(
        json.dumps(rec), encoding="utf-8")


def test_malformed_record_does_not_crash():
    bad = {"repo_dir numérico": {"repo_dir": 123},
           "repo_dir lista": {"repo_dir": ["a"]},
           "main_clone numérico, repo_dir null": {"main_clone": 5, "repo_dir": None}}
    for label, rec in bad.items():
        with tempfile.TemporaryDirectory() as tmp:
            home, _rd, _mc, _m = make_world(Path(tmp), record=False)
            write_record(home, rec)
            out = run_doctor(home)
            check(f"[{label}] sem Traceback", "Traceback" not in out, out)
            check(f"[{label}] avisa 'sem repo de origem'", "repo de origem" in out, out)


def test_numeric_repo_dir_falls_to_main_clone():
    with tempfile.TemporaryDirectory() as tmp:
        home, _rd, mc, _m = make_world(Path(tmp), repo_dir_v=None, main_clone_v="3.7.0",
                                       record=False)
        write_record(home, {"repo_dir": 7, "main_clone": str(mc)})
        out = run_doctor(home)
        check("repo_dir numérico: sem Traceback", "Traceback" not in out, out)
        check("repo_dir numérico: o drift vem do main_clone",
              "repo está em 3.7.0 mas o cache instalado é 3.6.0" in out, out)


def test_same_version_is_ok():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home, _rd, _mc, _m = make_world(tmpp, repo_dir_v="3.6.0")
        out = run_doctor(home)
        check("origem e cache na mesma versão: linha ok",
              "common 3.6.0 instalado e habilitado" in out, out)
        check("origem e cache na mesma versão: sem aviso de drift",
              "repo está em" not in out, out)


def test_empty_repo_dir_is_not_the_cwd():
    # Path("") is the cwd (REPO here, a real checkout with plugins): an accepted "" would
    # be scanned as the origin instead of warning.
    with tempfile.TemporaryDirectory() as tmp:
        home, _rd, _mc, marker = make_world(Path(tmp), record=False, repo_dir_v=None)
        write_record(home, {"repo_dir": ""})
        out = run_doctor(home)
        check("repo_dir vazio: avisa 'sem repo de origem'", "sem repo de origem" in out, out)
        check("repo_dir vazio: sem linha ok 'instalado e habilitado'",
              "instalado e habilitado" not in out, out)
        check("repo_dir vazio: sem Traceback", "Traceback" not in out, out)


def test_unusable_path_strings_do_not_crash():
    bad = {"repo_dir maior que PATH_MAX": "/" + "a" * 5000,
           "repo_dir com NUL embutido": "a\u0000b"}
    for label, val in bad.items():
        with tempfile.TemporaryDirectory() as tmp:
            home, _rd, _mc, _m = make_world(Path(tmp), record=False, repo_dir_v=None)
            write_record(home, {"repo_dir": val})
            out = run_doctor(home)
            check(f"[{label}] sem Traceback", "Traceback" not in out, out)
            check(f"[{label}] avisa 'sem repo de origem'", "sem repo de origem" in out, out)


def test_registry_at_outside_checkout_is_the_origin():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home, _rd, _mc, marker = make_world(tmpp, record=False, repo_dir_v=None)
        outside = tmpp / "outside"
        fake_checkout(outside, "3.7.0", marker)
        (home / ".claude" / "plugins" / "known_marketplaces.json").write_text(
            json.dumps({"cepa": {"installLocation": str(outside)}}), encoding="utf-8")
        out = run_doctor(home)
        check("registro fora do cepa-live: compara com a pasta registrada",
              "repo está em 3.7.0 mas o cache instalado é 3.6.0" in out, out)
        check("registro fora do cepa-live: não diz 'sem repo de origem'",
              "sem repo de origem" not in out, out)
        run_doctor(home, "--fix")
        check("--fix roda o install.sh da pasta registrada",
              marker_cwds(marker) and set(marker_cwds(marker)) == {outside.resolve()},
              str(marker_cwds(marker)))


def test_missing_cache_with_origin():
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home, repo_dir, _mc, marker = make_world(tmpp)
        (home / ".claude" / "plugins" / "cache" / "cepa" / "common" / "3.6.0").rmdir()
        out = run_doctor(home)
        check("cache vazio: falha 'nenhuma versão no cache'",
              "nenhuma versão no cache" in out, out)
        check("cache vazio: oferece o conserto install", "reinstalar os plugins" in out, out)
        check("cache vazio: sem install antes do --fix", not marker.exists())
        run_doctor(home, "--fix")
        check("cache vazio: --fix roda o install.sh do repo_dir",
              marker_cwds(marker) == [repo_dir.resolve()], str(marker_cwds(marker)))


def test_no_origin_offers_no_fix():
    # cache empty, no origin
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home, _rd, _mc, marker = make_world(tmpp, record=False, repo_dir_v=None)
        (home / ".claude" / "plugins" / "cache" / "cepa" / "common" / "3.6.0").rmdir()
        out = run_doctor(home)
        check("sem origem + cache vazio: imprime 'nenhuma versão no cache'",
              "nenhuma versão no cache" in out, out)
        check("sem origem + cache vazio: não oferece conserto", "reinstalar os plugins" not in out, out)
        run_doctor(home, "--fix")
        check("sem origem + cache vazio: --fix não roda nada", not marker.exists())
    # drift, no origin: cepa-live ahead of the cache, no record
    with tempfile.TemporaryDirectory() as tmp:
        tmpp = Path(tmp)
        home, _rd, _mc, marker = make_world(tmpp, live_v="3.7.0", record=False, repo_dir_v=None)
        out = run_doctor(home)
        check("sem origem + drift: imprime o aviso de drift",
              "repo está em 3.7.0 mas o cache instalado é 3.6.0" in out, out)
        check("sem origem + drift: não oferece conserto", "reinstalar os plugins" not in out, out)
        run_doctor(home, "--fix")
        check("sem origem + drift: --fix não roda nada", not marker.exists())


if __name__ == "__main__":
    test_repo_dir_ahead_of_cache()
    test_repo_dir_gone_falls_back_to_main_clone()
    test_repo_dir_wins_over_main_clone()
    test_no_origin_known()
    test_malformed_record_does_not_crash()
    test_numeric_repo_dir_falls_to_main_clone()
    test_same_version_is_ok()
    test_empty_repo_dir_is_not_the_cwd()
    test_unusable_path_strings_do_not_crash()
    test_registry_at_outside_checkout_is_the_origin()
    test_missing_cache_with_origin()
    test_no_origin_offers_no_fix()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s)")
        sys.exit(1)
    print("tudo ok")
