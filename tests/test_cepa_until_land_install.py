#!/usr/bin/env python3
"""cepa-run land installs the plugins from the clone after the green build.

Spec `registro-de-plugins-pasta-estavel`, CS-6. A run that reinstalls the plugins
leaves the fixed folder (`~/.claude/cepa-live`) with the content of the run
worktree, and the landing removes that worktree. Until now the owner had to
remember to run `bin/install.sh` in the main clone after landing. Now, in the cepa
repo only (`.claude-plugin/marketplace.json` named `cepa` plus `bin/install.sh`),
`cepa-run land <queue>/<run> --yes` runs the installer itself, with the clone as
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


# What the fake installer prints on `--rollback`, and nowhere else.
ROLLBACK_MARK = "fake-rollback-ran-here"


def run_file(root, run_id, ext):
    """The `.jsonl` or `.log` of THIS run, and no other file of the folder."""
    return root / ".claude" / "programs" / "fila" / "until" / f"{run_id}.{ext}"


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
        # FAKE_INSTALL_EXIT makes the installer fail after writing the call down;
        # with `--rollback` among the arguments FAKE_ROLLBACK_EXIT (default 0) rules.
        # The rollback says a line of its own (it must reach the run's `.log`) and
        # may take FAKE_ROLLBACK_SLEEP seconds (the event records how long it took).
        "case \" $* \" in *\" --rollback \"*)\n"
        f"  echo '{ROLLBACK_MARK}'\n"
        "  sleep ${FAKE_ROLLBACK_SLEEP:-0}\n"
        "  exit ${FAKE_ROLLBACK_EXIT:-0};;\n"
        "esac\n"
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
        check("CS-6: ...o instalador foi chamado (a primeira chamada é a instalação)",
              len(calls(root)) >= 1 and calls(root)[0].get("args") == [],
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


def other_run(root, tree, pid, queue="outra", run="2026-11-16-0900",
              estado="rodando", host=None, with_arvore=True,
              base=".claude/queues"):
    """The state and the record of ANOTHER run of the repo, in another queue, as the
    real `cepa-until` leaves them: `arvore` in `run_start`, a pid, this host.
    `host` is another machine name, `with_arvore=False` leaves the worktree path
    out of the record, `base` picks the layout (`.claude/programs` is the legacy)."""
    import socket
    d = root / base / queue / "until"
    d.mkdir(parents=True, exist_ok=True)
    Path(tree).mkdir(parents=True, exist_ok=True)
    (d / f"{run}.estado.json").write_text(json.dumps(
        {"run": run, "fila": queue, "estado": estado, "branch": f"until/{run}",
         "registro": f"{run}.jsonl", "pid": pid,
         "host": host or socket.gethostname()}), encoding="utf-8")
    start = {"evento": "run_start", "fila": queue, "branch": f"until/{run}",
             "pid": pid}
    if with_arvore:
        start["arvore"] = str(tree)
    (d / f"{run}.jsonl").write_text(json.dumps(start) + "\n", encoding="utf-8")
    return run


def last_install_in(home, repo_dir):
    """`~/.claude/ops/last-install.json` of a fake HOME, as `bin/install.sh` writes it."""
    ops = Path(home) / ".claude" / "ops"
    ops.mkdir(parents=True, exist_ok=True)
    (ops / "last-install.json").write_text(json.dumps(
        {"repo_dir": str(repo_dir), "main_clone": "/x", "live_dir": "/y"}))


def land_with_home(root, run_id, home):
    """The landing with HOME pointing at a fake one: never the real `~/.claude`."""
    old = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        return land(root, run_id, "--yes")
    finally:
        if old is None:
            del os.environ["HOME"]
        else:
            os.environ["HOME"] = old


def alive_supervisor():
    return subprocess.Popen([sys.executable, "-c",
                             "import time; time.sleep(120)", "cepa-until"])


def deferred_events(root):
    return [e for e in ledger_of(root) if e["evento"] == "instalacao_adiada"]


def test_cs7_live_run_on_the_installed_worktree_defers_the_install():
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, _branch, _tree = night(root)
        home = Path(tmp) / "home"
        other_tree = Path(tmp) / "worktrees" / "outra-rodada"
        alive = alive_supervisor()
        try:
            other = other_run(root, other_tree, alive.pid)
            last_install_in(home, other_tree)
            p = land_with_home(root, run_id, home)
        finally:
            alive.kill()
            alive.wait()
        check("CS-7: o pouso sai 0", p.returncode == 0, p.stdout + p.stderr)
        check("CS-7: ...o instalador não é chamado", calls(root) == [],
              str(calls(root)))
        ev = deferred_events(root)
        e = ev[0] if ev else {}
        check("CS-7: ...o registro ganha instalacao_adiada nomeando a outra rodada",
              len(ev) == 1 and other in json.dumps(e)
              and str(other_tree) in json.dumps(e) and e.get("quando"), str(ev))
        check("CS-7: ...e não ganha instalado_no_pouso",
              landing_events(root) == [], str(landing_events(root)))
        out = p.stdout
        check("CS-7: ...a tela tem 'Fica com você' com o install, o clone e a outra rodada",
              "Fica com você" in out and "bin/install.sh" in out
              and str(root.resolve()) in out and other in out, out)
        check("CS-7: ...o estado vira aterrissado",
              state(root).get("estado") == "aterrissado", str(state(root)))
        check("CS-7: ...e a pasta da rodada foi removida",
              not Path(_tree).exists(), _tree)


def test_cs7_dead_or_not_running_other_run_installs_as_in_cs6():
    for how in ("pid morto", "estado encerrado"):
        with tempfile.TemporaryDirectory() as tmp:
            root = as_cepa_repo(build_repo(tmp, [item("a1")]))
            run_id, _branch, _tree = night(root)
            home = Path(tmp) / "home"
            other_tree = Path(tmp) / "worktrees" / "outra-rodada"
            gone = subprocess.Popen([sys.executable, "-c", "pass", "cepa-until"])
            gone.wait()
            alive = alive_supervisor()
            try:
                if how == "pid morto":
                    other_run(root, other_tree, gone.pid)
                else:
                    other_run(root, other_tree, alive.pid,
                              estado="esperando-dono")
                last_install_in(home, other_tree)
                p = land_with_home(root, run_id, home)
            finally:
                alive.kill()
                alive.wait()
            check(f"CS-7 ({how}): o pouso sai 0 e instala", p.returncode == 0
                  and len(calls(root)) == 1, p.stdout + p.stderr)
            check(f"CS-7 ({how}): ...com instalado_no_pouso e sem instalacao_adiada",
                  len(landing_events(root)) == 1 and deferred_events(root) == [],
                  str(ledger_of(root)[-3:]))


def test_cs7_no_record_or_clone_as_repo_dir_installs_as_in_cs6():
    for how in ("sem last-install.json", "repo_dir é o clone",
                "last-install.json ilegível"):
        with tempfile.TemporaryDirectory() as tmp:
            root = as_cepa_repo(build_repo(tmp, [item("a1")]))
            run_id, _branch, _tree = night(root)
            home = Path(tmp) / "home"
            home.mkdir()
            other_tree = Path(tmp) / "worktrees" / "outra-rodada"
            alive = alive_supervisor()
            try:
                other_run(root, other_tree, alive.pid)
                if how == "repo_dir é o clone":
                    last_install_in(home, root)
                elif how == "last-install.json ilegível":
                    ops = home / ".claude" / "ops"
                    ops.mkdir(parents=True)
                    (ops / "last-install.json").write_text("{não é json")
                p = land_with_home(root, run_id, home)
            finally:
                alive.kill()
                alive.wait()
            check(f"CS-7 ({how}): o pouso sai 0 e instala", p.returncode == 0
                  and len(calls(root)) == 1, p.stdout + p.stderr)
            check(f"CS-7 ({how}): ...sem instalacao_adiada",
                  deferred_events(root) == [], str(deferred_events(root)))


def test_cs7_the_installed_path_is_compared_resolved_not_as_written():
    # last-install.json names the other run's worktree through a symlink.
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, _branch, _tree = night(root)
        home = Path(tmp) / "home"
        other_tree = Path(tmp) / "worktrees" / "outra-rodada"
        link = Path(tmp) / "atalho"
        alive = alive_supervisor()
        try:
            other_run(root, other_tree, alive.pid)
            link.symlink_to(other_tree)
            last_install_in(home, link)
            p = land_with_home(root, run_id, home)
        finally:
            alive.kill()
            alive.wait()
        check("CS-7 (symlink): o pouso sai 0 e adia", p.returncode == 0
              and len(deferred_events(root)) == 1, p.stdout + p.stderr)
        check("CS-7 (symlink): ...o instalador não é chamado", calls(root) == [],
              str(calls(root)))


def test_cs7_a_live_run_that_does_not_count_lets_the_land_install():
    # Each case: the other run is up in some way but is not a holder of the plugins.
    for how in ("sem arvore", "outro host", "sem pid"):
        with tempfile.TemporaryDirectory() as tmp:
            root = as_cepa_repo(build_repo(tmp, [item("a1")]))
            run_id, _branch, _tree = night(root)
            home = Path(tmp) / "home"
            other_tree = Path(tmp) / "worktrees" / "outra-rodada"
            alive = alive_supervisor()
            try:
                if how == "sem arvore":
                    other_run(root, other_tree, alive.pid, with_arvore=False)
                elif how == "outro host":
                    other_run(root, other_tree, alive.pid,
                              host="outra-maquina.example")
                else:
                    other_run(root, other_tree, None)
                last_install_in(home, other_tree)
                p = land_with_home(root, run_id, home)
            finally:
                alive.kill()
                alive.wait()
            check(f"CS-7 ({how}): o pouso sai 0 e instala", p.returncode == 0
                  and len(calls(root)) == 1, p.stdout + p.stderr)
            check(f"CS-7 ({how}): ...com instalado_no_pouso e sem instalacao_adiada",
                  len(landing_events(root)) == 1 and deferred_events(root) == [],
                  str(ledger_of(root)[-3:]))


def test_cs7_the_live_run_is_found_in_any_queue_and_layout():
    for how, queue, base in (("outra fila", "outra", ".claude/queues"),
                             ("fila _all", "_all", ".claude/queues"),
                             ("layout legado", "outra", ".claude/programs")):
        with tempfile.TemporaryDirectory() as tmp:
            root = as_cepa_repo(build_repo(tmp, [item("a1")]))
            run_id, _branch, _tree = night(root)
            home = Path(tmp) / "home"
            other_tree = Path(tmp) / "worktrees" / "outra-rodada"
            alive = alive_supervisor()
            try:
                other_run(root, other_tree, alive.pid, queue=queue, base=base)
                last_install_in(home, other_tree)
                p = land_with_home(root, run_id, home)
            finally:
                alive.kill()
                alive.wait()
            check(f"CS-7 ({how}): o pouso sai 0 e adia", p.returncode == 0
                  and len(deferred_events(root)) == 1 and calls(root) == [],
                  p.stdout + p.stderr)


def undone_events(root):
    return [e for e in ledger_of(root) if e["evento"] == "reinstalacao_desfeita"]


def land_with_env(root, run_id, **env):
    for k, v in env.items():
        os.environ[k] = v
    try:
        return land(root, run_id, "--yes")
    finally:
        for k in env:
            del os.environ[k]


def test_cs8_failed_install_is_rolled_back_and_the_landing_stands():
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, branch, tree = night(root)
        p = land_with_env(root, run_id, FAKE_INSTALL_EXIT="1",
                          FAKE_ROLLBACK_SLEEP="1.3")
        out = p.stdout
        check("CS-8: instalação que falha: o pouso sai 0", p.returncode == 0,
              out + p.stderr)
        log = subprocess.run(["git", "log", "--format=%s"], cwd=root,
                             capture_output=True, text=True).stdout.splitlines()
        check("CS-8: ...o merge está no clone", "a1" in log, str(log))
        c = calls(root)
        check("CS-8: ...o instalador foi chamado duas vezes, instalação e depois --rollback",
              len(c) == 2 and c[0].get("args") == []
              and c[1].get("args") == ["--rollback"], str(c))
        check("CS-8: ...as duas com o clone como diretório",
              all(x.get("cwd") == str(root.resolve()) for x in c), str(c))
        ev = undone_events(root)
        e = ev[0] if ev else {}
        check("CS-8: ...o registro ganha reinstalacao_desfeita com ok verdadeiro",
              len(ev) == 1 and e.get("ok") is True
              and Path(e.get("repo") or "/x").resolve() == root.resolve()
              and "1" in str(e.get("motivo")) and e.get("quando")
              and "segundos" in e, str(ev))
        check("CS-8: ...com o tempo que o rollback levou (1,3 s dá 1 ou mais)",
              isinstance(e.get("segundos"), int) and e.get("segundos") >= 1,
              str(e))
        own = run_file(root, run_id, "jsonl")
        in_own = [json.loads(l) for l in own.read_text().splitlines()
                  if l.strip()] if own.exists() else []
        check("CS-8: ...gravado no .jsonl desta rodada, não em outro arquivo",
              [x["evento"] for x in in_own].count("reinstalacao_desfeita") == 1,
              str([x["evento"] for x in in_own]))
        runlog = run_file(root, run_id, "log")
        check("CS-8: ...e a saída do rollback está no .log desta rodada",
              runlog.exists() and ROLLBACK_MARK in runlog.read_text(),
              str(runlog))
        names = [x["evento"] for x in ledger_of(root)]
        inst = landing_events(root)
        check("CS-8: ...depois do instalado_no_pouso com ok falso",
              len(inst) == 1 and inst[0].get("ok") is False
              and "instalado_no_pouso" in names and "reinstalacao_desfeita" in names
              and names.index("instalado_no_pouso")
              < names.index("reinstalacao_desfeita"), str(names))
        check("CS-8: ...a tela tem 'Fica com você' com o install e o clone",
              "Fica com você" in out and "sh bin/install.sh" in out
              and str(root.resolve()) in out, out)
        check("CS-8: ...e diz que os plugins anteriores foram restaurados",
              "restored" in out, out)
        check("CS-8: ...e onde está a saída (.log)", f"{run_id}.log" in out, out)
        check("CS-8: ...o estado vira aterrissado",
              state(root).get("estado") == "aterrissado", str(state(root)))
        check("CS-8: ...a branch da rodada foi removida",
              not subprocess.run(["git", "branch", "--list", branch], cwd=root,
                                 capture_output=True, text=True).stdout.strip())
        check("CS-8: ...e a pasta da rodada também", not Path(tree).exists(), tree)


def test_cs8_rollback_that_also_fails_still_lands():
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, _branch, _tree = night(root)
        p = land_with_env(root, run_id, FAKE_INSTALL_EXIT="1",
                          FAKE_ROLLBACK_EXIT="3")
        out = p.stdout
        check("CS-8 (rollback falha): o pouso sai 0", p.returncode == 0,
              out + p.stderr)
        c = calls(root)
        check("CS-8 (rollback falha): ...instalação e --rollback foram chamados",
              len(c) == 2 and c[1].get("args") == ["--rollback"], str(c))
        ev = undone_events(root)
        check("CS-8 (rollback falha): ...o registro tem reinstalacao_desfeita com ok falso",
              len(ev) == 1 and ev[0].get("ok") is False, str(ev))
        check("CS-8 (rollback falha): ...com o motivo do rollback (saiu 3), "
              "não o da instalação (saiu 1)",
              bool(ev) and str(ev[0].get("motivo")) == "exited 3", str(ev))
        check("CS-8 (rollback falha): ...a tela diz que o rollback também falhou, "
              "que pode estar pela metade e aponta o doctor",
              "Fica com você" in out and "rollback" in out.lower()
              and "half" in out and "/common:doctor" in out
              and "restored" not in out, out)
        check("CS-8 (rollback falha): ...o estado vira aterrissado",
              state(root).get("estado") == "aterrissado", str(state(root)))


def test_cs8_green_install_makes_no_rollback():
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, _branch, _tree = night(root)
        p = land(root, run_id, "--yes")
        check("CS-8 (verde): o pouso sai 0 com uma só chamada, sem --rollback",
              p.returncode == 0 and len(calls(root)) == 1
              and calls(root)[0].get("args") == [], p.stdout + str(calls(root)))
        check("CS-8 (verde): ...sem reinstalacao_desfeita",
              undone_events(root) == [], str(undone_events(root)))


def test_cs8_no_rollback_without_an_install_that_failed():
    # Red build, plan-only landing and another repo: the installer never runs, so
    # there is nothing to roll back, even with the env that would make it fail.
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, _branch, _tree = night(root)
        commit(root, "quebra.txt", "x", "main andou")
        p = land_with_env(root, run_id, FAKE_INSTALL_EXIT="1")
        check("CS-8 (build vermelho): sai 5, sem chamada e sem reinstalacao_desfeita",
              p.returncode == 5 and calls(root) == [] and undone_events(root) == [],
              p.stdout + str(calls(root)))
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        run_id, _branch, _tree = night(root)
        os.environ["FAKE_INSTALL_EXIT"] = "1"
        try:
            p = land(root, run_id)
        finally:
            del os.environ["FAKE_INSTALL_EXIT"]
        check("CS-8 (só plano): sai 0, sem chamada e sem reinstalacao_desfeita",
              p.returncode == 0 and calls(root) == [] and undone_events(root) == [],
              p.stdout + str(calls(root)))
    with tempfile.TemporaryDirectory() as tmp:
        root = as_cepa_repo(build_repo(tmp, [item("a1")]))
        (root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps({"name": "outro", "plugins": []}))
        commit(root, ".claude-plugin/marketplace.json",
               json.dumps({"name": "outro", "plugins": []}), "não é o cepa")
        run_id, _branch, _tree = night(root)
        p = land_with_env(root, run_id, FAKE_INSTALL_EXIT="1")
        check("CS-8 (outro repo): sai 0, sem chamada e sem reinstalacao_desfeita",
              p.returncode == 0 and calls(root) == [] and undone_events(root) == [],
              p.stdout + str(calls(root)))


def main():
    print("cepa-run land: install from the clone after the green build\n")
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
