#!/usr/bin/env python3
"""CS-1 and CS-2: the installer registers the fixed folder, from a linked
worktree (CS-1) and from the main clone (CS-2).

`bin/install.sh` used to hand `claude plugin marketplace add` the folder it ran
from. From a cepa-until worktree that is a folder that later gets removed, and
the plugin registry then points at nothing. Now the installer copies the
marketplace + plugin folders to `~/.claude/cepa-live` and registers THAT.

Hermetic: temp HOME, a fake `claude` first on PATH that logs its argv, and a
throwaway git repo (never the real one) with a real linked worktree.

CS-2 is the same claim from the main clone, on a HOME that never saw an
install: the registry gets `~/.claude/cepa-live`, never the clone's path.

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
        # whole tree, every plugin: same relative files (minus __pycache__), same bytes
        def tree(root):
            return {str(f.relative_to(root)): f for f in root.rglob("*")
                    if (f.is_file() or f.is_symlink())
                    and "__pycache__" not in f.relative_to(root).parts}
        for p in mk["plugins"]:
            rel = os.path.normpath(p["source"])
            a, b = tree(wt / rel), tree(live / rel)
            diff = sorted(set(a) ^ set(b))
            diff += sorted(k for k in set(a) & set(b)
                           if a[k].is_symlink() != b[k].is_symlink()
                           or (not a[k].is_symlink() and a[k].read_bytes() != b[k].read_bytes()))
            check(f"árvore inteira de {rel} idêntica à do worktree",
                  not diff and bool(a), f"{len(diff)} diferem, primeiros: {diff[:5]}")
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
        stale = home / ".claude" / "cepa-live.new"
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
        junk = sorted(str(p.relative_to(live)) for p in live.rglob("lixo"))
        check("o lixo do staging velho não está em cepa-live (não aninhou)",
              junk == [], str(junk))
        check("staging velho cepa-live.new não existe mais",
              not stale.exists(), str(stale))


def test_main_clone_install():
    """CS-2: same arrangement, installer run from the main clone, fresh HOME."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        home = tmp / "home"
        home.mkdir()
        main = tmp / "main"
        mk = build_repo(main)

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
        r = subprocess.run(["sh", "bin/install.sh", str(host)],
                           capture_output=True, text=True, env=env, cwd=str(main))
        check("CS-2: install.sh do clone principal sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])

        adds = [l.split("marketplace add ", 1)[1].strip()
                for l in log.read_text().splitlines() if "marketplace add " in l]
        live = home / ".claude" / "cepa-live"
        check("CS-2: marketplace add recebe ~/.claude/cepa-live",
              adds == [str(live)], f"adds={adds}")
        check("CS-2: o caminho do clone principal não aparece em nenhuma chamada do claude",
              str(main) not in log.read_text(), log.read_text()[-400:])
        check("CS-2: cepa-live/.claude-plugin/marketplace.json igual ao do clone",
              (live / ".claude-plugin" / "marketplace.json").is_file()
              and (live / ".claude-plugin" / "marketplace.json").read_bytes()
              == (main / ".claude-plugin" / "marketplace.json").read_bytes())
        for p in mk["plugins"]:
            rel = os.path.normpath(p["source"])
            check(f"CS-2: pasta do plugin {p['name']} em cepa-live/{rel}",
                  (live / rel / ".claude-plugin" / "plugin.json").is_file(),
                  str(live / rel))
        listed = {os.path.normpath(p["source"]) for p in mk["plugins"]}
        check("CS-2: cepa-live tem só o marketplace e as pastas dos plugins listados",
              {p.name for p in live.iterdir()} == listed | {".claude-plugin"},
              str(sorted(p.name for p in live.iterdir())))


if __name__ == "__main__":
    test_worktree_install()
    test_main_clone_install()
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        sys.exit(1)
    print("\nall ok")
