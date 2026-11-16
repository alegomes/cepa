#!/usr/bin/env python3
"""CS-1, CS-2 and CS-3: the installer registers the fixed folder, from a linked
worktree (CS-1) and from the main clone (CS-2).

`bin/install.sh` used to hand `claude plugin marketplace add` the folder it ran
from. From a cepa-until worktree that is a folder that later gets removed, and
the plugin registry then points at nothing. Now the installer copies the
marketplace + plugin folders to `~/.claude/cepa-live` and registers THAT.

Hermetic: temp HOME, a fake `claude` first on PATH that logs its argv, and a
throwaway git repo (never the real one) with a real linked worktree.

CS-2 is the same claim from the main clone, on a HOME that never saw an
install: the registry gets `~/.claude/cepa-live`, never the clone's path.

CS-3: `--clean` sets the current cepa-live aside as `cepa-live.prev` and
`--rollback` puts it back (the .prev is gone afterwards).

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

        calls = log.read_text() if log.exists() else ""
        adds = [l.split("marketplace add ", 1)[1].strip()
                for l in calls.splitlines() if "marketplace add " in l]
        live = home / ".claude" / "cepa-live"
        check("CS-2: marketplace add recebe ~/.claude/cepa-live",
              adds == [str(live)], f"adds={adds}")
        check("CS-2: o caminho do clone principal não aparece em nenhuma chamada do claude",
              bool(calls) and str(main) not in calls, calls[-400:])
        check("CS-2: cepa-live/.claude-plugin/marketplace.json igual ao do clone",
              (live / ".claude-plugin" / "marketplace.json").is_file()
              and (live / ".claude-plugin" / "marketplace.json").read_bytes()
              == (main / ".claude-plugin" / "marketplace.json").read_bytes())
        for p in mk["plugins"]:
            rel = os.path.normpath(p["source"])
            pj = live / rel / ".claude-plugin" / "plugin.json"
            check(f"CS-2: pasta do plugin {p['name']} em cepa-live/{rel}, com o plugin.json dele",
                  pj.is_file() and pj.read_bytes()
                  == (main / rel / ".claude-plugin" / "plugin.json").read_bytes(),
                  str(live / rel))
        listed = {os.path.normpath(p["source"]) for p in mk["plugins"]}
        found = {p.name for p in live.iterdir()} if live.is_dir() else set()
        check("CS-2: cepa-live tem só o marketplace e as pastas dos plugins listados",
              found == listed | {".claude-plugin"}, str(sorted(found)))


# Expected installer lines, compared WHOLE (== a line of stdout), never as substrings:
# a stray character after a path must turn a check red.
def cache_block(claude):
    cache = str(claude / "plugins" / "cache" / "cepa")
    return ["▶ --rollback: restoring the cache set aside by the last --clean",
            f"    from: {cache}.prev", f"      to: {cache}"]


def live_block(claude):
    return ["▶ --rollback: restoring the fixed folder set aside by the last --clean",
            f"    from: {claude / 'cepa-live.prev'}", f"      to: {claude / 'cepa-live'}"]


def kept_cache(claude):
    return str(claude / "plugins" / "cache" / "cepa") + ".rolledback"


def kept_live(claude):
    return str(claude / "cepa-live") + ".rolledback"


def restored_line(kept):
    return "✓ Restored. Replaced copy kept at: " + kept


def rollback_note(claude, cache, live):
    cp = str(claude / "plugins" / "cache" / "cepa")
    lp = str(claude / "cepa-live")
    if cache and live:
        return (f"restored the cache from {cp}.prev and the fixed folder from {lp}.prev; "
                f"replaced copies were kept at {cp}.rolledback and {lp}.rolledback")
    if cache:
        return f"restored the cache from {cp}.prev; the replaced copy was kept at {cp}.rolledback"
    return (f"restored only the fixed folder from {lp}.prev (the cache was not touched, "
            f"versions not recorded); the replaced copy was kept at {lp}.rolledback")


def test_clean_and_rollback():
    """CS-3: install A, --clean with B, --rollback -> A back, no cepa-live.prev."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        home = tmp / "home"
        home.mkdir()
        main = tmp / "main"
        build_repo(main)
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
        live = home / ".claude" / "cepa-live"
        prev = home / ".claude" / "cepa-live.prev"
        pj_main = main / "common" / ".claude-plugin" / "plugin.json"
        pj_live = live / "common" / ".claude-plugin" / "plugin.json"

        def run(*args):
            return subprocess.run(["sh", "bin/install.sh", *args, str(host)],
                                  capture_output=True, text=True, env=env, cwd=str(main))

        def version(path):
            return json.loads(path.read_text())["version"]

        def set_version(v):
            d = json.loads(pj_main.read_text())
            d["version"] = v
            pj_main.write_text(json.dumps(d))

        set_version("1.0.0-A")
        r = run()
        check("CS-3: instalar A sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
        check("CS-3: cepa-live diz A", pj_live.is_file() and version(pj_live) == "1.0.0-A")
        check("CS-3: instalar sem --clean não cria cepa-live.prev", not prev.exists())

        set_version("2.0.0-B")
        r = run("--clean")
        check("CS-3: --clean com B sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
        check("CS-3: cepa-live diz B", version(pj_live) == "2.0.0-B")
        check("CS-3: cepa-live.prev guarda A",
              (prev / "common" / ".claude-plugin" / "plugin.json").is_file()
              and version(prev / "common" / ".claude-plugin" / "plugin.json") == "1.0.0-A")
        out_lines = r.stdout.splitlines()
        check("CS-3: --clean diz que põe a pasta fixa de lado em cepa-live.prev",
              "▶ --clean: setting the current fixed folder aside at " + str(prev) in out_lines,
              r.stdout[-600:])
        check("CS-3: --clean fecha com linha 'Rollback point' com o caminho de cepa-live.prev",
              f"  Rollback point: {prev}  (restore with bin/install.sh --rollback)" in out_lines,
              r.stdout[-600:])

        r = run("--rollback")
        check("CS-3: --rollback sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
        check("CS-3: depois do --rollback cepa-live volta a dizer A",
              pj_live.is_file() and version(pj_live) == "1.0.0-A")
        check("CS-3: depois do --rollback cepa-live.prev não existe", not prev.exists())

        # a second --clean replaces the previous .prev with what was live (B)
        set_version("2.0.0-B")
        run("--clean")
        set_version("3.0.0-C")
        r = run("--clean")
        check("CS-3: segundo --clean sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
        check("CS-3: segundo --clean: .prev passa a guardar B (não A)",
              version(prev / "common" / ".claude-plugin" / "plugin.json") == "2.0.0-B")

        r = run("--rollback")
        check("CS-3: --rollback depois do segundo --clean sai 0", r.returncode == 0)
        check("CS-3: depois do --rollback cepa-live diz a versão anterior (B)",
              pj_live.is_file() and version(pj_live) == "2.0.0-B")
        check("CS-3: depois do --rollback cepa-live.prev não existe", not prev.exists())

        r = run("--rollback")
        check("CS-3: --rollback sem ponto de volta sai diferente de 0", r.returncode != 0)
        check("CS-3: --rollback sem ponto de volta não mexe em cepa-live",
              version(pj_live) == "2.0.0-B")


def test_rollback_fixed_folder_only_ignores_stale_cache():
    """CS-3: --rollback that only restores cepa-live must not report a stale cache.rolledback."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        home = tmp / "home"
        main = tmp / "main"
        build_repo(main)
        fakebin = tmp / "fakebin"
        fakebin.mkdir()
        (fakebin / "claude").write_text("#!/bin/sh\nexit 0\n")
        (fakebin / "claude").chmod(0o755)
        host = tmp / "host"
        host.mkdir()
        env = dict(os.environ, HOME=str(home), PATH=f"{fakebin}:{os.environ['PATH']}")
        claude = home / ".claude"
        # stale leftover from an older rollback: plugin STALEat 9.9.9-STALE
        stale = Path(str(claude / "plugins" / "cache" / "cepa") + ".rolledback")
        (stale / "stale-plugin" / "9.9.9-STALE").mkdir(parents=True)
        (claude / "cepa-live" / "common" / ".claude-plugin").mkdir(parents=True)
        (claude / "cepa-live.prev" / "common" / ".claude-plugin").mkdir(parents=True)
        r = subprocess.run(["sh", "bin/install.sh", "--rollback", str(host)],
                           capture_output=True, text=True, env=env, cwd=str(main))
        check("CS-3: --rollback só da pasta fixa sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        rec_file = claude / "ops" / "last-install.json"
        rec = json.loads(rec_file.read_text()) if rec_file.is_file() else {}
        check("CS-3: registro não traz versões do cache.rolledback velho",
              "9.9.9-STALE" not in json.dumps(rec) and rec.get("versions_before") == {}
              and rec.get("versions_target") == {},
              json.dumps(rec)[:400])
        outl = r.stdout.splitlines()
        check("CS-3: --rollback da pasta fixa mostra 'from: cepa-live.prev' e 'to: cepa-live'",
              all(l in outl for l in live_block(claude)), r.stdout[-600:])
        check("CS-3: registro diz 'only the fixed folder' e cita cepa-live.rolledback, não o do cache",
              rec.get("note") == rollback_note(claude, False, True)
              and str(stale) not in json.dumps(rec), json.dumps(rec)[:400])
        check("CS-3: linha 'Restored' cita só cepa-live.rolledback, não o .rolledback do cache",
              restored_line(kept_live(claude)) in outl, r.stdout[-400:])


def _scenario(tmp):
    tmp = Path(tmp).resolve()
    home = tmp / "home"
    home.mkdir()
    main = tmp / "main"
    build_repo(main)
    fakebin = tmp / "fakebin"
    fakebin.mkdir()
    (fakebin / "claude").write_text("#!/bin/sh\nexit 0\n")
    (fakebin / "claude").chmod(0o755)
    host = tmp / "host"
    host.mkdir()
    env = dict(os.environ, HOME=str(home), PATH=f"{fakebin}:{os.environ['PATH']}")

    def run(*args):
        return subprocess.run(["sh", "bin/install.sh", *args, str(host)],
                              capture_output=True, text=True, env=env, cwd=str(main))
    return home / ".claude", main, run


def test_clean_without_existing_live():
    """CS-3: --clean on a HOME with no cepa-live yet installs normally, no .prev."""
    with tempfile.TemporaryDirectory() as tmp:
        claude, main, run = _scenario(tmp)
        want = json.loads((main / "common" / ".claude-plugin" / "plugin.json").read_text())["version"]
        r = run("--clean")
        check("CS-3: --clean sem cepa-live prévio sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        pj = claude / "cepa-live" / "common" / ".claude-plugin" / "plugin.json"
        check("CS-3: --clean sem cepa-live prévio cria cepa-live com a versão instalada",
              pj.is_file() and json.loads(pj.read_text())["version"] == want)
        check("CS-3: --clean sem cepa-live prévio não cria cepa-live.prev",
              not (claude / "cepa-live.prev").exists())
        check("CS-3: --clean sem cepa-live prévio não anuncia 'Rollback point' de cepa-live.prev",
              not any("Rollback point" in l and "cepa-live.prev" in l for l in r.stdout.splitlines()),
              r.stdout[-600:])
        check("CS-3: --clean sem cepa-live prévio não diz que põe a pasta fixa de lado",
              "setting the current fixed folder aside" not in r.stdout, r.stdout[-600:])


def test_rollback_cache_only_leaves_fixed_folder():
    """CS-3: --rollback with only a cache.prev restores the cache and does not touch cepa-live."""
    with tempfile.TemporaryDirectory() as tmp:
        claude, main, run = _scenario(tmp)
        cache = claude / "plugins" / "cache" / "cepa"
        prev_cache = Path(str(cache) + ".prev")
        for d in (cache / "p" / "2.0.0", prev_cache / "p" / "1.0.0",
                  claude / "cepa-live" / "common" / ".claude-plugin"):
            d.mkdir(parents=True)
        (claude / "cepa-live" / "KEEP").write_text("x")
        r = run("--rollback")
        check("CS-3: --rollback só do cache sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        check("CS-3: --rollback só do cache restaura o cache (1.0.0) e guarda o antigo (2.0.0)",
              (cache / "p" / "1.0.0").is_dir() and not prev_cache.exists()
              and (Path(str(cache) + ".rolledback") / "p" / "2.0.0").is_dir())
        check("CS-3: --rollback só do cache não mexe em cepa-live",
              (claude / "cepa-live" / "KEEP").is_file()
              and not (claude / "cepa-live.rolledback").exists())
        outl = r.stdout.splitlines()
        check("CS-3: linha 'Restored' do rollback só do cache cita cache.rolledback e não cepa-live.rolledback",
              restored_line(kept_cache(claude)) in outl, r.stdout[-400:])
        check("CS-3: rollback só do cache anuncia a restauração do cache com origem e destino",
              all(l in outl for l in cache_block(claude)), r.stdout[-600:])
        check("CS-3: rollback só do cache não fala em restaurar a pasta fixa",
              "fixed folder" not in r.stdout, r.stdout[-600:])
        rec_file = claude / "ops" / "last-install.json"
        rec = json.loads(rec_file.read_text()) if rec_file.is_file() else {}
        note = json.dumps(rec)
        check("CS-3: registro do rollback só do cache descreve o cache e não a pasta fixa",
              rec.get("note") == rollback_note(claude, True, False), note[:500])
        check("CS-3: registro do rollback só do cache traz as versões (antes 2.0.0, alvo 1.0.0)",
              rec.get("versions_before") == {"p": "2.0.0"} and rec.get("versions_target") == {"p": "1.0.0"},
              note[:500])


def test_rollback_replaces_old_cache_rolledback_and_tolerates_missing_targets():
    """CS-3: an old cache.rolledback is replaced, not nested; a missing cache or cepa-live is no error."""
    with tempfile.TemporaryDirectory() as tmp:
        claude, main, run = _scenario(tmp)
        cache = claude / "plugins" / "cache" / "cepa"
        old = Path(str(cache) + ".rolledback")
        for d in (cache / "p" / "2.0.0", Path(str(cache) + ".prev") / "p" / "1.0.0",
                  old / "q" / "0.1.0"):
            d.mkdir(parents=True)
        r = run("--rollback")
        check("CS-3: --rollback com cache.rolledback antigo sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        check("CS-3: cache.rolledback guarda a cópia substituída (2.0.0) e não o antigo",
              (old / "p" / "2.0.0").is_dir() and not (old / "q").exists()
              and not (old / "cepa").exists())

    with tempfile.TemporaryDirectory() as tmp:
        claude, main, run = _scenario(tmp)
        cache = claude / "plugins" / "cache" / "cepa"
        (Path(str(cache) + ".prev") / "p" / "1.0.0").mkdir(parents=True)
        (claude / "cepa-live.prev" / "common").mkdir(parents=True)
        r = run("--rollback")
        check("CS-3: --rollback sem cache nem cepa-live atuais sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        check("CS-3: --rollback sem cache nem cepa-live atuais não escreve erro",
              r.stderr.strip() == "", r.stderr[-400:])
        check("CS-3: --rollback sem cache nem cepa-live atuais restaura os dois",
              (cache / "p" / "1.0.0").is_dir() and (claude / "cepa-live" / "common").is_dir())
        check("CS-3: --rollback sem cache nem cepa-live atuais não cria .rolledback vazio",
              not Path(str(cache) + ".rolledback").exists()
              and not (claude / "cepa-live.rolledback").exists())


def test_plain_install_keeps_rollback_point():
    """CS-3: an install without --clean never sets cepa-live aside nor touches cepa-live.prev."""
    with tempfile.TemporaryDirectory() as tmp:
        claude, main, run = _scenario(tmp)
        pj_main = main / "common" / ".claude-plugin" / "plugin.json"
        live, prev = claude / "cepa-live", claude / "cepa-live.prev"
        pj_live = live / "common" / ".claude-plugin" / "plugin.json"
        pj_prev = prev / "common" / ".claude-plugin" / "plugin.json"

        def set_version(v):
            d = json.loads(pj_main.read_text())
            d["version"] = v
            pj_main.write_text(json.dumps(d))

        set_version("1.0.0-A")
        run()
        set_version("2.0.0-B")
        r = run()
        check("CS-3: segunda instalação sem --clean sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        check("CS-3: duas instalações sem --clean não criam cepa-live.prev", not prev.exists())
        check("CS-3: duas instalações sem --clean não falam em pôr a pasta fixa de lado",
              "setting the current fixed folder aside" not in r.stdout, r.stdout[-600:])

        # now a real rollback point (A) and a plain install of C on top of it
        shutil.rmtree(live)
        set_version("1.0.0-A")
        run()
        set_version("2.0.0-B")
        run("--clean")
        check("CS-3: preparo: .prev guarda A", pj_prev.is_file()
              and json.loads(pj_prev.read_text())["version"] == "1.0.0-A")
        (prev / "MARKER").write_text("keep")
        set_version("3.0.0-C")
        r = run()
        check("CS-3: instalar C sem --clean sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        check("CS-3: instalar C sem --clean deixa cepa-live dizendo C",
              pj_live.is_file() and json.loads(pj_live.read_text())["version"] == "3.0.0-C")
        check("CS-3: instalar C sem --clean deixa cepa-live.prev guardando A, com o marcador",
              pj_prev.is_file() and json.loads(pj_prev.read_text())["version"] == "1.0.0-A"
              and (prev / "MARKER").is_file())
        check("CS-3: instalar C sem --clean não anuncia 'Rollback point'",
              "Rollback point" not in r.stdout, r.stdout[-600:])


def test_rollback_with_nothing_names_both_paths():
    """CS-3: --rollback with no rollback point says which two folders it looked for."""
    with tempfile.TemporaryDirectory() as tmp:
        claude, main, run = _scenario(tmp)
        r = run("--rollback")
        check("CS-3: --rollback sem ponto de volta sai 1", r.returncode == 1,
              r.stdout[-400:] + r.stderr[-400:])
        out = r.stdout
        outl = out.splitlines()
        cache_prev = str(claude / "plugins" / "cache" / "cepa") + ".prev"
        check("CS-3: mensagem 'Nothing to roll back' cita cepa-live.prev",
              f"  nor {claude / 'cepa-live.prev'} exists." in outl, out[-600:])
        check("CS-3: mensagem 'Nothing to roll back' cita também o cache.prev",
              f"✗ Nothing to roll back to: neither {cache_prev}" in outl, out[-600:])
        check("CS-3: mensagem 'Nothing to roll back' explica que --clean cria o ponto de volta do cache e da pasta fixa",
              "  A rollback point is created by --clean (it sets the old cache and the" in outl
              and "  old fixed folder aside instead of deleting them). If you have never run" in outl,
              out[-600:])
        check("CS-3: mensagem 'Nothing to roll back' diz o que fazer se nunca rodou --clean",
              "  --clean since this feature landed, there is no previous state to restore." in outl,
              out[-600:])


def test_rollback_replaces_old_rolledback():
    """CS-3: --rollback discards an older cepa-live.rolledback instead of nesting into it."""
    with tempfile.TemporaryDirectory() as tmp:
        claude, main, run = _scenario(tmp)
        for name, ver in (("cepa-live", "B"), ("cepa-live.prev", "A"), ("cepa-live.rolledback", "OLD")):
            d = claude / name / "common" / ".claude-plugin"
            d.mkdir(parents=True)
            (d / "plugin.json").write_text(json.dumps({"version": ver}))
        (claude / "cepa-live.rolledback" / "old-marker").write_text("x")
        r = run("--rollback")
        check("CS-3: --rollback com .rolledback antigo sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        rb = claude / "cepa-live.rolledback"
        pj = rb / "common" / ".claude-plugin" / "plugin.json"
        check("CS-3: cepa-live.rolledback guarda a cópia substituída (B)",
              pj.is_file() and json.loads(pj.read_text())["version"] == "B")
        check("CS-3: cepa-live.rolledback não tem cepa-live aninhado", not (rb / "cepa-live").exists())
        check("CS-3: marcador do .rolledback antigo sumiu", not (rb / "old-marker").exists())
        live, live_prev = claude / "cepa-live", claude / "cepa-live.prev"
        outl = r.stdout.splitlines()
        check("CS-3: rollback só da pasta fixa anuncia a restauração da pasta fixa com origem e destino",
              all(l in outl for l in live_block(claude)), r.stdout[-600:])
        check("CS-3: rollback só da pasta fixa não fala em restaurar o cache",
              "restoring the cache" not in r.stdout, r.stdout[-600:])


def test_rollback_names_both_replaced_copies():
    """CS-3: when cache and fixed folder are both restored, the report names both kept copies."""
    with tempfile.TemporaryDirectory() as tmp:
        claude, main, run = _scenario(tmp)
        cache = claude / "plugins" / "cache" / "cepa"
        prev_cache = Path(str(cache) + ".prev")
        for d in (cache / "p" / "2.0.0", prev_cache / "p" / "1.0.0",
                  claude / "cepa-live" / "common" / ".claude-plugin",
                  claude / "cepa-live.prev" / "common" / ".claude-plugin"):
            d.mkdir(parents=True)
        r = run("--rollback")
        check("CS-3: --rollback de cache e pasta fixa sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        outl = r.stdout.splitlines()
        check("CS-3: linha 'Restored' cita cache.rolledback e cepa-live.rolledback",
              restored_line(kept_cache(claude) + " and " + kept_live(claude)) in outl,
              r.stdout[-400:])
        check("CS-3: rollback de cache e pasta fixa anuncia o cache com origem e destino",
              all(l in outl for l in cache_block(claude)), r.stdout[-600:])
        check("CS-3: rollback de cache e pasta fixa anuncia a pasta fixa com origem e destino",
              all(l in outl for l in live_block(claude)), r.stdout[-600:])
        rec_file = claude / "ops" / "last-install.json"
        rec = json.loads(rec_file.read_text()) if rec_file.is_file() else {}
        note = json.dumps(rec)
        check("CS-3: registro cita cache.rolledback e cepa-live.rolledback, de onde vieram o cache e a pasta fixa",
              rec.get("note") == rollback_note(claude, True, True), note[:500])


def test_failed_copy_leaves_previous_live_whole():
    """CS-4: a copy that dies halfway leaves the previous cepa-live whole."""
    with tempfile.TemporaryDirectory() as tmp:
        claude, main, run = _scenario(tmp)
        r = run()
        check("CS-4: instalação da versão A sai 0", r.returncode == 0,
              r.stdout[-400:] + r.stderr[-400:])
        live = claude / "cepa-live"

        def snap():
            return {str(f.relative_to(live)): (f.read_bytes() if f.is_file() and not f.is_symlink() else None)
                    for f in live.rglob("*") if f.is_file() or f.is_symlink()}
        before = snap()
        check("CS-4: versão A tem arquivos em cepa-live", len(before) > 0)
        # version B of the repo, with one plugin folder the copy cannot read
        (main / "common" / "VERSION-B.txt").write_text("b")
        (main / "build-solo" / "agents").chmod(0)
        try:
            r = run()
        finally:
            (main / "build-solo" / "agents").chmod(0o755)
        check("CS-4: cópia que falha faz o instalador sair diferente de zero",
              r.returncode != 0, r.stdout[-400:] + r.stderr[-400:])
        check("CS-4: cepa-live ainda tem a versão A completa, byte a byte",
              live.is_dir() and snap() == before)
        check("CS-4: cepa-live não ganhou arquivo da versão B",
              not (live / "common" / "VERSION-B.txt").exists())
        rec_file = claude / "ops" / "last-install.json"
        rec = json.loads(rec_file.read_text()) if rec_file.is_file() else {}
        check("CS-4: last-install.json diz in_progress", rec.get("status") == "in_progress",
              json.dumps(rec)[:300])


def test_ops_record_says_where_copy_came_from():
    """CS-5: last-install.json carries repo_dir, main_clone and live_dir."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        claude, main, run = _scenario(tmp)
        home = claude.parent
        host = tmp / "host"
        live = str(claude / "cepa-live")
        rec_file = claude / "ops" / "last-install.json"
        env = dict(os.environ, HOME=str(home),
                   PATH=f"{tmp / 'fakebin'}:{os.environ['PATH']}")

        def install_from(root, *args):
            r = subprocess.run(["sh", str(root / "bin" / "install.sh"), *args, str(host)],
                               capture_output=True, text=True, env=env, cwd=str(tmp))
            rec = json.loads(rec_file.read_text()) if rec_file.is_file() else {}
            return r, rec

        # from a linked worktree
        wt = tmp / "wt"
        git(main, "worktree", "add", "-q", "-b", "until/x", str(wt))
        r, rec = install_from(wt)
        check("CS-5: install do worktree sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
        check("CS-5: worktree: status ok", rec.get("status") == "ok", str(rec))
        check("CS-5: worktree: repo_dir é o worktree", rec.get("repo_dir") == str(wt), str(rec))
        check("CS-5: worktree: main_clone é o clone principal",
              rec.get("main_clone") == str(main), str(rec))
        check("CS-5: worktree: live_dir é ~/.claude/cepa-live", rec.get("live_dir") == live, str(rec))

        # from the main clone
        r, rec = install_from(main)
        check("CS-5: install do clone principal sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
        check("CS-5: clone principal: repo_dir é o clone", rec.get("repo_dir") == str(main), str(rec))
        check("CS-5: clone principal: main_clone == repo_dir == clone",
              rec.get("main_clone") == rec.get("repo_dir") == str(main), str(rec))
        check("CS-5: clone principal: live_dir é ~/.claude/cepa-live", rec.get("live_dir") == live, str(rec))

        # from a folder that is not a git repo
        plain = tmp / "plain"
        shutil.copytree(main, plain, ignore=shutil.ignore_patterns(".git"), symlinks=True)
        r, rec = install_from(plain)
        check("CS-5: pasta sem git: install sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
        check("CS-5: pasta sem git: repo_dir é a pasta", rec.get("repo_dir") == str(plain), str(rec))
        check("CS-5: pasta sem git: main_clone == repo_dir",
              rec.get("main_clone") == str(plain), str(rec))
        check("CS-5: pasta sem git: live_dir é ~/.claude/cepa-live", rec.get("live_dir") == live, str(rec))

        # after --rollback
        r, _ = install_from(main, "--clean")
        check("CS-5: --clean sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
        r, rec = install_from(main, "--rollback")
        check("CS-5: --rollback sai 0", r.returncode == 0, r.stdout[-400:] + r.stderr[-400:])
        check("CS-5: rollback: status rolled_back", rec.get("status") == "rolled_back", str(rec))
        check("CS-5: rollback: main_clone no registro", rec.get("main_clone") == str(main), str(rec))
        check("CS-5: rollback: live_dir no registro", rec.get("live_dir") == live, str(rec))


if __name__ == "__main__":
    test_worktree_install()
    test_main_clone_install()
    test_clean_and_rollback()
    test_rollback_fixed_folder_only_ignores_stale_cache()
    test_clean_without_existing_live()
    test_rollback_replaces_old_rolledback()
    test_rollback_names_both_replaced_copies()
    test_rollback_cache_only_leaves_fixed_folder()
    test_rollback_replaces_old_cache_rolledback_and_tolerates_missing_targets()
    test_plain_install_keeps_rollback_point()
    test_rollback_with_nothing_names_both_paths()
    test_failed_copy_leaves_previous_live_whole()
    test_ops_record_says_where_copy_came_from()
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED")
        sys.exit(1)
    print("\nall ok")
