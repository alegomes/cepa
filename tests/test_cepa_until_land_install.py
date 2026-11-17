#!/usr/bin/env python3
"""cepa-until land installs the plugins from the clone after the green build.

Spec `registro-de-plugins-pasta-estavel`, CS-6. A run that reinstalls the plugins
leaves the fixed folder (`~/.claude/cepa-live`) with the content of the run
worktree, and the landing removes that worktree. Until now the owner had to
remember to run `bin/install.sh` in the main clone after landing. Now, in the cepa
repo only (`.claude-plugin/marketplace.json` named `cepa` plus `bin/install.sh`),
`cepa-until land <queue>/<run> --yes` runs the installer itself, with the clone as
directory, after the merge and the green build, and the run record gains
`instalado_no_pouso`.

Every case runs a real `cepa-until` against a fake repo whose `bin/install.sh`
only writes down where it was called from and what the clone held at that moment.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)
from test_cepa_until_run_branch import WORKS, plan_of  # noqa: E402
from test_cepa_until_land import commit, land, state  # noqa: E402


def calls_file(root):
    return root.parent / "install-calls.jsonl"


def order_file(root):
    return root.parent / "ordem.txt"


def verify_of(root):
    """The build of the run, which also writes down that it ran: the order file
    is what says the installer came after the build."""
    return f"test ! -f quebra.txt && echo build >> '{order_file(root)}'"


def as_cepa_repo(root):
    """The test repo becomes the cepa repo: a marketplace named `cepa` and a
    `bin/install.sh`. The installer is a fake that appends one line per call with
    its directory, its arguments and the subjects of the clone's history."""
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps({"name": "cepa", "plugins": []}))
    (root / "bin").mkdir()
    (root / "bin" / "install.sh").write_text(
        "#!/bin/sh\n"
        f"echo install >> '{order_file(root)}'\n"
        f"'{sys.executable}' - \"$@\" <<'EOF'\n"
        "import json, os, subprocess, sys\n"
        "log = subprocess.run(['git', 'log', '--format=%s'], capture_output=True,\n"
        "                     text=True).stdout.splitlines()\n"
        f"with open({str(calls_file(root))!r}, 'a') as f:\n"
        "    f.write(json.dumps({'cwd': os.path.realpath(os.getcwd()),\n"
        "                        'args': sys.argv[1:], 'log': log}) + '\\n')\n"
        "EOF\n"
        # FAKE_INSTALL_EXIT makes the installer fail after writing the call down.
        "exit ${FAKE_INSTALL_EXIT:-0}\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "repo do cepa"], cwd=root, check=True)
    return root


def calls(root):
    f = calls_file(root)
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def night(root):
    """A night with a1 delivered. Returns (run_id, branch, tree), with the order
    file emptied: what it holds afterwards belongs to the landing."""
    binv = fake_claude(root.parent, WORKS)
    run_until(root, binv, plan_of(root),
              ["--for", "2h", "--verify", verify_of(root)])
    start = [e for e in ledger_of(root) if e["evento"] == "run_start"][0]
    if order_file(root).exists():
        order_file(root).unlink()
    return start["branch"].split("/", 1)[1], start["branch"], start["arvore"]


def landing_events(root):
    return [e for e in ledger_of(root) if e["evento"] == "instalado_no_pouso"]


def test_cs6_land_installs_from_the_clone_after_merge_and_green_build():
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, _branch, tree = night(root)
        check("CS-6: a rodada em si não chamou o instalador", calls(root) == [],
              str(calls(root)))
        p = land(root, run_id, "--yes")
        check("CS-6: o pouso sai 0", p.returncode == 0, p.stdout + p.stderr)
        c = calls(root)
        check("CS-6: o instalador foi chamado uma vez", len(c) == 1, str(c))
        call = c[0] if c else {}
        check("CS-6: ...com o clone como diretório",
              call.get("cwd") == str(root.resolve()), str(call))
        check("CS-6: ...e não com a pasta da rodada",
              call.get("cwd") != str(Path(tree).resolve()), str(call))
        check("CS-6: ...sem --clean nem --rollback", call.get("args") == [],
              str(call))
        check("CS-6: ...depois do merge (o commit do item já estava no clone)",
              "a1" in (call.get("log") or []), str(call))
        order = (order_file(root).read_text().split()
                 if order_file(root).exists() else [])
        check("CS-6: ...e depois do build", order == ["build", "install"],
              str(order))
        ev = landing_events(root)
        check("CS-6: o registro da rodada ganha instalado_no_pouso",
              len(ev) == 1, str(ledger_of(root)[-4:]))
        e = ev[0] if ev else {}
        check("CS-6: ...que diz que deu certo e de onde instalou",
              e.get("ok") is True
              and Path(e.get("repo") or "/x").resolve() == root.resolve(), str(e))
        check("CS-6: a tela diz que instalou do clone",
              "bin/install.sh" in p.stdout, p.stdout)
        check("CS-6: o estado vira aterrissado",
              state(root).get("estado") == "aterrissado", str(state(root)))


def test_cs6_red_build_does_not_install():
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, _branch, _tree = night(root)
        commit(root, "quebra.txt", "x", "main andou")
        p = land(root, run_id, "--yes")
        check("CS-6: build vermelho no pouso sai 5", p.returncode == 5,
              p.stdout + p.stderr)
        check("CS-6: ...e o instalador não é chamado", calls(root) == [],
              str(calls(root)))
        check("CS-6: ...nem o registro ganha instalado_no_pouso",
              landing_events(root) == [], str(landing_events(root)))


def test_cs6_failed_install_does_not_change_the_landing():
    """Spec, "Decided without asking": the exit code of the landing does not
    change when the install fails, because the landing happened."""
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, branch, _tree = night(root)
        os.environ["FAKE_INSTALL_EXIT"] = "1"
        try:
            p = land(root, run_id, "--yes")
        finally:
            del os.environ["FAKE_INSTALL_EXIT"]
        check("CS-6: instalador que falha: o pouso ainda sai 0",
              p.returncode == 0, p.stdout + p.stderr)
        check("CS-6: ...o instalador foi chamado", len(calls(root)) == 1,
              str(calls(root)))
        ev = landing_events(root)
        e = ev[0] if ev else {}
        check("CS-6: ...o registro diz que a instalação não deu certo e por quê",
              len(ev) == 1 and e.get("ok") is False
              and "1" in str(e.get("motivo")), str(ev))
        check("CS-6: ...o estado vira aterrissado mesmo assim",
              state(root).get("estado") == "aterrissado", str(state(root)))
        check("CS-6: ...a branch da rodada foi removida",
              not subprocess.run(["git", "branch", "--list", branch], cwd=root,
                                 capture_output=True, text=True).stdout.strip())
        check("CS-6: ...e a tela diz que falhou e pede o install à mão no clone",
              "FAILED" in p.stdout and "sh bin/install.sh" in p.stdout
              and str(root.resolve()) in p.stdout, p.stdout)


def test_cs6_plan_only_and_already_landed_do_not_install():
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, _branch, _tree = night(root)
        p = land(root, run_id)
        check("CS-6: sem --yes sai 0", p.returncode == 0, p.stdout + p.stderr)
        check("CS-6: ...e não instala", calls(root) == [], str(calls(root)))
        check("CS-6: ...mas o plano avisa que vai instalar",
              "bin/install.sh" in p.stdout, p.stdout)
        land(root, run_id, "--yes")
        again = land(root, run_id, "--yes")
        check("CS-6: pousar de novo sai 0 dizendo que já pousou",
              again.returncode == 0 and "already landed" in again.stdout,
              again.stdout + again.stderr)
        check("CS-6: ...e não instala uma segunda vez", len(calls(root)) == 1,
              str(calls(root)))


def test_cs6_other_repo_lands_without_installing():
    """Out of scope by the spec: `land` in a repo that is not the cepa repo
    installs nothing, even when it has a `bin/install.sh` of its own."""
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        (root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"name": "outro", "plugins": []}))
        commit(root, ".claude-plugin/marketplace.json",
               json.dumps({"name": "outro", "plugins": []}), "não é o cepa")
        run_id, _branch, _tree = night(root)
        p = land(root, run_id, "--yes")
        check("CS-6: em outro repo o pouso sai 0", p.returncode == 0,
              p.stdout + p.stderr)
        check("CS-6: ...sem chamar o instalador", calls(root) == [],
              str(calls(root)))
        check("CS-6: ...sem instalado_no_pouso no registro",
              landing_events(root) == [], str(landing_events(root)))
        check("CS-6: ...e sem falar de instalação na tela",
              "bin/install.sh" not in p.stdout, p.stdout)


def main():
    print("cepa-until land: install from the clone after the green build\n")
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
