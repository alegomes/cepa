#!/usr/bin/env python3
"""CS-1: installing from inside a linked worktree registers the fixed folder.

`bin/install.sh` used to hand `claude plugin marketplace add` the folder it ran
from. From a cepa-until worktree that is a folder that later gets removed, and
the plugin registry then points at nothing. Now the installer copies the
marketplace + plugin folders to `~/.claude/cepa-live` and registers THAT.

Hermetic: temp HOME, a fake `claude` first on PATH that logs its argv, and a
throwaway git repo (never the real one) with a real linked worktree.

Run: python3 tests/test_install_live_dir.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}   {detail}")
        FAILURES.append(name)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                            GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))


def build_repo(dest):
    """Throwaway repo with what install.sh needs: bin/, marketplace, plugins."""
    dest.mkdir()
    mk = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    folders = ["bin", ".claude-plugin"] + [p["source"][2:] for p in mk["plugins"]]
    ign = shutil.ignore_patterns("__pycache__", "node_modules", ".git")
    for f in folders:
        shutil.copytree(REPO / f, dest / f, ignore=ign, symlinks=True)
    # a committed __pycache__ the copy must leave behind
    pyc = dest / "common" / "bin" / "__pycache__"
    pyc.mkdir(parents=True, exist_ok=True)
    (pyc / "x.pyc").write_bytes(b"junk")
    git(dest, "init", "-q", "-b", "main")
    git(dest, "add", "-A", "-f")
    git(dest, "commit", "-q", "-m", "init")
    return mk


def test_worktree_install():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        home = tmp / "home"
        home.mkdir()
        main = tmp / "main"
        mk = build_repo(main)
        wt = tmp / "wt"
        git(main, "worktree", "add", "-q", "-b", "until/x", str(wt))
        # uncommitted file in the worktree: must be copied as on disk
        (wt / "common" / "UNCOMMITTED.txt").write_text("hi")

        fakebin = tmp / "fakebin"
        fakebin.mkdir()
        log = tmp / "claude.log"
        (fakebin / "claude").write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$FAKE_CLAUDE_LOG"\nexit 0\n')
        (fakebin / "claude").chmod(0o755)
        host = tmp / "host"
        host.mkdir()

        env = dict(os.environ, HOME=str(home), FAKE_CLAUDE_LOG=str(log),
                   PATH=f"{fakebin}:{os.environ['PATH']}")
        r = subprocess.run(["sh", str(wt / "bin" / "install.sh"), str(host)],
                           capture_output=True, text=True, env=env, cwd=str(tmp))
        check("install.sh sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])

        adds = [l.split("marketplace add ", 1)[1].strip()
                for l in log.read_text().splitlines() if "marketplace add " in l]
        live = home / ".claude" / "cepa-live"
        check("marketplace add recebe ~/.claude/cepa-live",
              adds == [str(live)], f"adds={adds}")
        check("nenhum marketplace add recebe o caminho do worktree",
              str(wt) not in adds and str(main) not in adds, f"adds={adds}")

        check("cepa-live/.claude-plugin/marketplace.json existe",
              (live / ".claude-plugin" / "marketplace.json").is_file())
        for p in mk["plugins"]:
            src = live / p["source"][2:]
            check(f"plugin {p['name']} presente em {p['source']}", src.is_dir(), str(src))
        check("plugin docs (nome != pasta) está em docs-topology",
              (live / "docs-topology").is_dir() and not (live / "docs").exists())

        pj_live = live / "common" / ".claude-plugin" / "plugin.json"
        check("plugin.json de common é igual ao do worktree",
              pj_live.is_file() and pj_live.read_bytes()
              == (wt / "common" / ".claude-plugin" / "plugin.json").read_bytes())
        check("arquivo não commitado do worktree foi copiado",
              (live / "common" / "UNCOMMITTED.txt").is_file())
        check("sem __pycache__ em cepa-live",
              not any(live.rglob("__pycache__")))
        check("sem pasta de staging ao lado de cepa-live",
              sorted(p.name for p in live.parent.glob("cepa-live*")) == ["cepa-live"],
              str(sorted(p.name for p in live.parent.glob("cepa-live*"))))

        git(main, "worktree", "remove", "--force", str(wt))
        check("o worktree foi removido", not wt.exists())
        check("depois de remover o worktree, plugin.json continua em cepa-live",
              pj_live.is_file())

        # second run: stale staging from a dead run must not break the install
        stale = home / ".claude" / f"cepa-live.new.99999"
        stale.mkdir()
        (stale / "lixo").write_text("x")
        (main / "common" / "MARKER.txt").write_text("novo")
        r2 = subprocess.run(["sh", str(main / "bin" / "install.sh"), str(host)],
                            capture_output=True, text=True, env=env, cwd=str(tmp))
        check("reinstalar com staging velho sai 0", r2.returncode == 0,
              r2.stdout[-400:] + r2.stderr[-400:])
        check("cepa-live continua inteiro após a reinstalação",
              pj_live.is_file())
        check("marcador do clone principal está em cepa-live",
              (live / "common" / "MARKER.txt").is_file())
        check("arquivo só do worktree sumiu de cepa-live (substituiu, não mesclou)",
              not (live / "common" / "UNCOMMITTED.txt").exists())
        nested = sorted(str(p.relative_to(live)) for p in live.rglob("cepa-live.new.*"))
        check("nenhum cepa-live.new.* dentro de cepa-live (não aninhou)",
              nested == [], str(nested))
        check("staging velho .new.99999 foi removido pelo instalador",
              not stale.exists(), str(stale))
        left = sorted(p.name for p in live.parent.iterdir()
                      if p.name.startswith("cepa-live.new."))
        check("sem nenhum staging .new.* após reinstalar", left == [], str(left))


if __name__ == "__main__":
    test_worktree_install()
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        sys.exit(1)
    print("\nall ok")
