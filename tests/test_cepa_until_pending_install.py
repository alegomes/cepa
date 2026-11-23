#!/usr/bin/env python3
"""`cepa-until pending` reinstalls the plugins when it closes a landed run, with the
same rule and the same guards as `land` (spec docs/spec/pouso-ja-feito-sai-da-lista.md,
CS-6; owner's answer: "yes, like `land`, same rule and same guards").

Against the real CLI, in a temporary git repo with a remote and a fake HOME (never the
real `~/.claude`), whose `bin/install.sh` only writes down that it ran:

  - cepa repo (marketplace `cepa` + `bin/install.sh`), `a/r1` landed: `pending` closes
    it, runs the installer once from the clone, and the `.jsonl` of `a/r1` gains
    `instalado_no_pouso`
  - `last-install.json` pointing at the worktree of ANOTHER live run: the `.jsonl` gains
    `instalacao_adiada` and the installer does not run
  - a repo that is not the cepa repo: no event, no install
  - `--json` still parses as JSON when an install happened
  - a call that closes nothing, or only discards a run, does not install
  - two runs closed in one call: one install, both `.jsonl` carry the event

Run with `python3 tests/test_cepa_until_pending_install.py`.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until_pending_says_what_closed import (  # noqa: E402
    CEPA_UNTIL, FAILURES, check, git, make_repo, add_run, state_path)

RED = {"parou": "build-vermelho", "motivo": "exit 1"}


def as_cepa_repo(root, name="cepa"):
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": name, "plugins": []}))
    (root / "bin").mkdir()
    (root / "bin" / "install.sh").write_text(
        f"#!/bin/sh\npwd -P >> '{calls_file(root)}'\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "cepa repo")
    git(root, "push", "-q", "origin", "main")


def calls_file(root):
    return root.parent / "install-calls.txt"


def calls(root):
    f = calls_file(root)
    return f.read_text().splitlines() if f.exists() else []


def pending(root, home, *extra):
    env = dict(os.environ, HOME=str(home))
    return subprocess.run([sys.executable, str(CEPA_UNTIL), "pending",
                           "--repo", str(root), *extra],
                          capture_output=True, text=True, cwd=str(root), env=env)


def events(root, run, name=None):
    f = state_path(root, run).with_name(f"{run}.jsonl")
    out = ([json.loads(l) for l in f.read_text().splitlines() if l.strip()]
           if f.exists() else [])
    return [e for e in out if name is None or e.get("evento") == name]


def landed_repo(tmp, cepa=True, runs=("r1",)):
    root = make_repo(tmp)
    if cepa:
        as_cepa_repo(root)
    for r in runs:
        add_run(root, r, keep_branch=True, aterrissagem=RED)
    git(root, "push", "-q", "origin", "main")
    return root


def live_other_run(root, tree, pid):
    d = root / ".claude" / "queues" / "outra" / "until"
    d.mkdir(parents=True, exist_ok=True)
    Path(tree).mkdir(parents=True, exist_ok=True)
    (d / "o1.estado.json").write_text(json.dumps(
        {"run": "o1", "fila": "outra", "estado": "rodando", "branch": "until/o1",
         "registro": "o1.jsonl", "pid": pid, "host": socket.gethostname()}))
    (d / "o1.jsonl").write_text(json.dumps(
        {"evento": "run_start", "fila": "outra", "branch": "until/o1", "pid": pid,
         "arvore": str(tree)}) + "\n")


def last_install_in(home, repo_dir):
    ops = Path(home) / ".claude" / "ops"
    ops.mkdir(parents=True, exist_ok=True)
    (ops / "last-install.json").write_text(json.dumps(
        {"repo_dir": str(repo_dir), "main_clone": "/x", "live_dir": "/y"}))


def test_installs_when_it_closes():
    print("CS-6: fecha a/r1 no repo do cepa e instala do clone")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        p = pending(root, Path(tmp) / "home")
        check("sai 0", p.returncode == 0, p.stderr)
        check("a/r1 foi fechado", "closed: queue a" in p.stdout, p.stdout)
        ev = events(root, "r1", "instalado_no_pouso")
        check("o .jsonl de a/r1 ganha instalado_no_pouso",
              len(ev) == 1 and ev[0].get("ok") is True, str(ev))
        check("o instalador rodou uma vez, no clone",
              calls(root) == [str(root.resolve())], str(calls(root)))
        p2 = pending(root, Path(tmp) / "home")
        check("segunda chamada nao instala de novo", len(calls(root)) == 1
              and not events(root, "r1", "instalacao_adiada"), str(calls(root)))
        del p2


def test_live_other_run_defers():
    print("CS-6: last-install na worktree de outro run vivo adia")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        home = Path(tmp) / "home"
        other_tree = Path(tmp) / "wt" / "outra"
        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(120)", "cepa-until"])
        try:
            live_other_run(root, other_tree, alive.pid)
            last_install_in(home, other_tree)
            p = pending(root, home)
        finally:
            alive.kill()
            alive.wait()
        check("sai 0", p.returncode == 0, p.stderr)
        ev = events(root, "r1", "instalacao_adiada")
        check("o .jsonl ganha instalacao_adiada nomeando a outra rodada",
              len(ev) == 1 and "o1" in json.dumps(ev[0]), str(ev))
        check("sem instalado_no_pouso", not events(root, "r1", "instalado_no_pouso"))
        check("o instalador nao rodou", calls(root) == [], str(calls(root)))


def test_other_repo_does_not_install():
    print("CS-6: repo que nao e o do cepa nao instala")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, cepa=False)
        p = pending(root, Path(tmp) / "home")
        check("fecha e sai 0", p.returncode == 0 and "closed:" in p.stdout, p.stdout)
        check("nenhum evento de instalacao",
              not events(root, "r1", "instalado_no_pouso")
              and not events(root, "r1", "instalacao_adiada"))
        check("sem install.sh no repo, nada rodou", calls(root) == [])
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        as_cepa_repo(root, name="outro")
        add_run(root, "r1", keep_branch=True, aterrissagem=RED)
        git(root, "push", "-q", "origin", "main")
        p = pending(root, Path(tmp) / "home")
        check("marketplace com outro nome: fecha sem instalar",
              "closed:" in p.stdout and calls(root) == []
              and not events(root, "r1", "instalado_no_pouso"), p.stdout)


def test_json_stays_json():
    print("CS-6: --json continua JSON quando instalou")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp)
        p = pending(root, Path(tmp) / "home", "--json")
        try:
            j = json.loads(p.stdout)
        except ValueError:
            j = None
        check("stdout e JSON", j is not None, p.stdout)
        check("...com fechados e instalou",
              j is not None and len(j["fechados"]) == 1
              and len(calls(root)) == 1, p.stdout)


def test_nothing_closed_does_not_install():
    print("CS-6: chamada que nao fecha nada, ou so descarta, nao instala")
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        as_cepa_repo(root)
        add_run(root, "r2", keep_branch=True, aterrissagem=RED)   # local only
        p = pending(root, Path(tmp) / "home")
        check("nada fechado, nada instalado",
              "closed:" not in p.stdout and calls(root) == [], p.stdout)
    with tempfile.TemporaryDirectory() as tmp:
        root = make_repo(tmp)
        as_cepa_repo(root)
        add_run(root, "r4", keep_branch=False, merged=False)       # never landed
        p = pending(root, Path(tmp) / "home")
        check("so descartado: fecha, nao instala",
              "discarded" in p.stdout and calls(root) == []
              and not events(root, "r4", "instalado_no_pouso"), p.stdout)


def test_two_closed_install_once():
    print("CS-6: dois fechados na mesma chamada, uma instalacao")
    with tempfile.TemporaryDirectory() as tmp:
        root = landed_repo(tmp, runs=("r1", "r3"))
        pending(root, Path(tmp) / "home")
        check("o instalador rodou uma vez", len(calls(root)) == 1, str(calls(root)))
        check("os dois .jsonl trazem instalado_no_pouso",
              all(len(events(root, r, "instalado_no_pouso")) == 1
                  for r in ("r1", "r3")))


if __name__ == "__main__":
    test_installs_when_it_closes()
    test_live_other_run_defers()
    test_other_repo_does_not_install()
    test_json_stays_json()
    test_nothing_closed_does_not_install()
    test_two_closed_install_once()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        sys.exit(1)
    print("\n✓ tudo passou")
