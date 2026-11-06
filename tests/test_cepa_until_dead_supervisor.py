#!/usr/bin/env python3
"""cepa-until — the supervisor that dies silently.

WEGO run 2026-09-28-2003 ended with the `.jsonl` record holding only `run_start`
and `item_start`. The card closed `done` on its own at 20:13, but there was no `verify`,
`item_end` nor `run_end`, and the queue was left with a `done` without the full build. There
was no kill in any session nor Mac sleep. The hypothesis that remained was the
SIGHUP of a closed terminal tab: `claude` runs with
`start_new_session=True`, outside the terminal's group, and survives; the supervisor
handled no signal and died in the middle of the item.

What these tests pin:

  1. SIGHUP (and the terminal vanishing with it) does not kill the supervisor: the in-flight item
     finishes, the full build runs and the record closes with `run_end`;
  2. SIGTERM and Ctrl+C write `run_interrompido` to the `.jsonl`, with the signal and the
     in-flight item, and leave the `<run>.estado.json` as `interrompido`;
  3. the `run_start` and the state carry the supervisor's pid and host;
  4. `cepa-until pendentes`, `cepa-doctor` and `/common:until-review`
     point to the `rodando` run whose supervisor died, with the full build that
     was missing.

Run: python3 tests/test_cepa_until_dead_supervisor.py
"""

import importlib.machinery
import importlib.util
import json
import os
import pty
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)
from test_cepa_until_run_branch import (  # noqa: E402
    WORKS, VERIFY, plan_of)

DOCTOR = CEPA_UNTIL.parent / "cepa-doctor"
UNTIL_REVIEW = CEPA_UNTIL.parent.parent / "commands" / "until-review.md"

# The fake `claude` waits for the file `<tmp>/segue` before working: that is the
# window in which the test sends the signal with the item in flight.
WAITS_AND_WORKS = (
    "segue = os.path.join(os.path.dirname(os.environ['FAKE_CHAMADAS']), 'segue')\n"
    "open(segue + '.pid', 'w').write(str(os.getpid()))\n"
    "fim = time.time() + 60\n"
    "while not os.path.exists(segue) and time.time() < fim:\n"
    "    time.sleep(0.1)\n"
    + WORKS)


def until_dir(root):
    return root / ".claude" / "programs" / "fila" / "until"


def state(root):
    return json.loads(sorted(until_dir(root).glob("*.estado.json"))[-1]
                      .read_text())


def waiting(cond, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.1)
    return False


def in_flight_item(root):
    try:
        return any(e["evento"] == "item_start" for e in ledger_of(root))
    except (OSError, ValueError):
        return False


def launches(root, binv, plan, args, **popen):
    """Starts `cepa-until` in the background (the `runs` of test_cepa_until
    waits for the end, and here the test needs to send the signal in the middle)."""
    env = dict(os.environ)
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(plan)
    env["FAKE_CHAMADAS"] = str(root.parent / "chamadas.jsonl")
    env["CEPA_WORKTREE_HOME"] = str(root.parent / "worktrees")
    return subprocess.Popen(
        [sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root)] + args
        + ["--no-analysis"], env=env, stdin=subprocess.DEVNULL, **popen)


# ── 1. SIGHUP ───────────────────────────────────────────────────────────────

def test_sighup_with_closed_terminal_does_not_kill_the_supervisor():
    """The closed tab sends SIGHUP and takes the terminal with it: after that, each
    `print` of the supervisor hits a terminal that no longer exists."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WAITS_AND_WORKS)
        master, slave = pty.openpty()
        proc = launches(root, binv, plan_of(root),
                     ["--for", "2h", "--verify", VERIFY],
                     stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        try:
            check("o item entrou em voo",
                  waiting(lambda: in_flight_item(root)), str(ledger_of(root)))
            os.kill(proc.pid, signal.SIGHUP)
            time.sleep(0.5)
            os.close(master)
            master = None
            (Path(tmp) / "segue").write_text("")
            try:
                code = proc.wait(timeout=90)
            except subprocess.TimeoutExpired:
                proc.kill()
                code = "não terminou"
        finally:
            if master is not None:
                os.close(master)
            (Path(tmp) / "segue").write_text("")
        ev = [e["evento"] for e in ledger_of(root)]
        check("o supervisor sobrevive ao SIGHUP e sai 0", code == 0,
              f"saiu {code}; eventos {ev}")
        check("...fecha o item (item_end)", "item_end" in ev, str(ev))
        check("...roda o build completo (verify)", "verify" in ev, str(ev))
        check("...e fecha o registro (run_end)",
              ev and ev[-1] == "run_end", str(ev))


# ── 2. SIGTERM and Ctrl+C ───────────────────────────────────────────────────

def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie that nobody has reaped yet counts as dead.
    ps = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                        capture_output=True, text=True).stdout.strip()
    return bool(ps) and not ps.startswith("Z")


def _interrupt(sig):
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WAITS_AND_WORKS)
        proc = launches(root, binv, plan_of(root),
                     ["--for", "2h", "--verify", VERIFY],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True)
        try:
            # Wait for the child's own pid mark, not for `item_start`: the
            # supervisor logs `item_start` BEFORE the Popen of `claude`, so a
            # signal in that gap finds no child and `pid_filho` is None (the
            # intermittent red of 2026-10-22). The fake writes segue.pid as its
            # first action, which happens only after Popen and `on_launch`.
            file = Path(tmp) / "segue.pid"
            check("o `claude` do item foi lançado e registrado",
                  waiting(lambda: file.exists() and file.read_text().strip()),
                  str(ledger_of(root)))
            pid_text = file.read_text().strip() if file.exists() else ""
            child = int(pid_text) if pid_text else None
            os.kill(proc.pid, sig)
            try:
                output, _ = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                output, _ = proc.communicate()
            time.sleep(0.5)
            live_child = child is not None and alive(child)
        finally:
            # Releases the fake `claude`, which runs in its own session and survives.
            (Path(tmp) / "segue").write_text("")
            time.sleep(1.5)
        return (proc.returncode, output, ledger_of(root), state(root),
                live_child)


def test_sigterm_writes_interrupted_run_with_the_in_flight_item():
    code, output, ev, state_dict, live_child = _interrupt(signal.SIGTERM)
    end = ev[-1] if ev else {}
    check("SIGTERM encerra o `claude` do item (sessão própria) antes de sair",
          not live_child and end.get("filho_encerrado") is True, str(end))
    check("SIGTERM fecha o registro com run_interrompido",
          end.get("evento") == "run_interrompido", str(ev[-2:]))
    check("...com o sinal e o item em voo",
          end.get("sinal") == "SIGTERM" and end.get("id") == "a1",
          str(end))
    check("...o estado vira `interrompido` com o item",
          state_dict.get("estado") == "interrompido"
          and (state_dict.get("item_em_voo") or {}).get("id") == "a1", str(state_dict))
    check("...e o processo sai com 143 (128 + SIGTERM)", code == 143,
          f"{code}: {output[-500:]}")


def test_ctrl_c_writes_interrupted_run_with_the_in_flight_item():
    code, output, ev, state_dict, live_child = _interrupt(signal.SIGINT)
    end = ev[-1] if ev else {}
    check("Ctrl+C encerra o `claude` do item antes de sair",
          not live_child and end.get("filho_encerrado") is True, str(end))
    check("Ctrl+C fecha o registro com run_interrompido (SIGINT, a1)",
          end.get("evento") == "run_interrompido"
          and end.get("sinal") == "SIGINT" and end.get("id") == "a1",
          str(ev[-2:]))
    check("...o estado vira `interrompido`",
          state_dict.get("estado") == "interrompido", str(state_dict))
    check("...e o processo sai com 130", code == 130,
          f"{code}: {output[-500:]}")


def test_sigterm_on_the_full_build_ends_the_build():
    """The full build also runs in its own session: SIGTERM in the middle of it
    must take it along, and the record says the phase was `verify`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WORKS)
        mark = Path(tmp) / "build.pid"
        build = f"echo $$ > {mark}; sleep 60"
        proc = launches(root, binv, plan_of(root), ["--for", "2h", "--verify", build],
                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            waiting(lambda: mark.exists() and mark.read_text().strip())
            os.kill(proc.pid, signal.SIGTERM)
            try:
                proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
            pid_build = int(mark.read_text())
            time.sleep(0.5)
            live_build = alive(pid_build)
        finally:
            if proc.poll() is None:
                proc.kill()
        end = ledger_of(root)[-1]
        check("SIGTERM no build registra a fase `verify`",
              end.get("evento") == "run_interrompido"
              and end.get("fase") == "verify" and end.get("id") == "a1",
              str(end))
        check("...e encerra o build", not live_build
              and end.get("filho_encerrado") is True, str(end))


# `terminate_group` must not call a dead group "alive/unknown": on macOS
# killpg(pgid, 0) gives EPERM while the group only holds exited, unreaped zombies.
def _load_until():
    loader = importlib.machinery.SourceFileLoader("cepa_until", str(CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_until", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _stat(pid):
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                          capture_output=True, text=True).stdout.strip()


def test_terminate_group_calls_an_all_zombie_group_dead():
    _until = _load_until()

    _p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                          start_new_session=True)
    try:
        os.killpg(_p.pid, signal.SIGTERM)
        _deadline = time.monotonic() + 5
        while not _stat(_p.pid).startswith("Z") and time.monotonic() < _deadline:
            time.sleep(0.02)
        check("terminate_group diz que o grupo acabou quando só restam zumbis (macOS devolve EPERM)",
              _until.terminate_group(_p.pid, 2) is True, _stat(_p.pid))
    finally:
        try:
            os.killpg(_p.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            os.waitpid(_p.pid, 0)
        except ChildProcessError:
            pass

    _p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                          start_new_session=True)
    try:
        _r = _until.terminate_group(_p.pid, 2)
        check("terminate_group num grupo vivo devolve True e o processo morre de fato",
              _r is True and not alive(_p.pid), str(_r))
    finally:
        try:
            os.killpg(_p.pid, signal.SIGKILL)
        except OSError:
            pass
        try:
            os.waitpid(_p.pid, os.WNOHANG)
        except ChildProcessError:
            pass


# ── 3. pid and host ─────────────────────────────────────────────────────────

def test_run_start_and_state_carry_pid_and_host():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WORKS)
        run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", VERIFY])
        start = [e for e in ledger_of(root) if e["evento"] == "run_start"][0]
        state_dict = state(root)
        check("run_start tem pid (int) e o host desta máquina",
              isinstance(start.get("pid"), int)
              and start.get("host") == socket.gethostname(), str(start))
        check("o estado tem o mesmo pid e host",
              state_dict.get("pid") == start.get("pid")
              and state_dict.get("host") == start.get("host"), str(state_dict))


# ── 4. the `rodando` run with a dead supervisor ─────────────────────────────

def dead_pid():
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def night_that_died(tmp, **swap):
    """A real night (a1 delivered), with the state and the record
    rewound to the point where the WEGO supervisor died: `rodando`,
    item in flight, without `item_end`, `verify` nor `run_end`."""
    root = build_repo(tmp, [item("a1")])
    binv = fake_claude(tmp, WORKS)
    run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", VERIFY])
    jsonl = sorted(until_dir(root).glob("*.jsonl"))[-1]
    events = [json.loads(l) for l in jsonl.read_text().splitlines()]
    cut_ = next(i for i, e in enumerate(events) if e["evento"] == "item_start")
    events = events[:cut_ + 1]
    if "prazo" in swap:
        events[0]["prazo"] = swap.pop("prazo")
    for k in ("pid", "host"):
        # A run prior to the pid in the state also does not have it in `run_start`.
        if k in swap and swap[k] is None:
            events[0].pop(k, None)
    jsonl.write_text("".join(json.dumps(e) + "\n" for e in events))
    file_path = sorted(until_dir(root).glob("*.estado.json"))[-1]
    state_dict = json.loads(file_path.read_text())
    state_dict.update(estado="rodando", pid=dead_pid(), host=socket.gethostname())
    for k in ("acoes", "fica_com_voce", "itens", "motivo_fim"):
        state_dict.pop(k, None)
    for k, v in swap.items():
        if v is None:
            state_dict.pop(k, None)
        else:
            state_dict[k] = v
    file_path.write_text(json.dumps(state_dict))
    return root, events[0]


def pending_ones(root):
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "pendentes",
                        "--repo", str(root), "--json"],
                       capture_output=True, text=True, timeout=60)
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"erro": p.stdout + p.stderr}


def test_pending_accuses_running_run_with_dead_pid():
    with tempfile.TemporaryDirectory() as tmp:
        root, start = night_that_died(tmp)
        dead_ones = pending_ones(root).get("mortos") or []
        check("pendentes --json lista o run em `mortos`",
              len(dead_ones) == 1 and dead_ones[0].get("item") == "a1", str(dead_ones))
        m = dead_ones[0] if dead_ones else {}
        check("...oferecendo o build completo que faltou, na worktree da noite",
              VERIFY in (m.get("comando") or "")
              and start["arvore"] in (m.get("comando") or ""), str(m))
        plain_text = subprocess.run([sys.executable, str(CEPA_UNTIL), "pendentes",
                                "--repo", str(root)], capture_output=True,
                               text=True, timeout=60).stdout
        check("...e o texto diz que o supervisor morreu", "morreu" in plain_text,
              plain_text)


def test_pending_does_not_accuse_run_with_live_supervisor():
    with tempfile.TemporaryDirectory() as tmp:
        alive = subprocess.Popen([sys.executable, "-c",
                                 "import time; time.sleep(60)", "cepa-until"])
        try:
            root, _ = night_that_died(tmp, pid=alive.pid)
            check("supervisor vivo não entra em `mortos`",
                  not pending_ones(root).get("mortos"), str(pending_ones(root)))
        finally:
            alive.kill()


def test_pending_does_not_accuse_pid_from_another_machine():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = night_that_died(tmp, host="outra-maquina.local")
        check("pid de outro host não é conferido aqui",
              not pending_ones(root).get("mortos"), str(pending_ones(root)))


def test_old_run_without_pid_past_the_deadline_is_accused():
    """WEGO's own run (2026-09-28-2003) predates the pid in the state:
    without a pid, what says it died is the deadline having passed long ago."""
    with tempfile.TemporaryDirectory() as tmp:
        old = (datetime.now() - timedelta(hours=6)).isoformat()
        root, _ = night_that_died(tmp, pid=None, host=None, prazo=old)
        dead_ones = pending_ones(root).get("mortos") or []
        check("run sem pid, 6h depois do prazo, entra em `mortos`",
              len(dead_ones) == 1, str(dead_ones))


def test_run_without_pid_within_the_deadline_is_not_accused():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = night_that_died(tmp, pid=None, host=None)
        check("run sem pid ainda dentro do prazo não entra em `mortos`",
              not pending_ones(root).get("mortos"), str(pending_ones(root)))


def test_doctor_points_to_the_run_with_dead_supervisor():
    with tempfile.TemporaryDirectory() as tmp:
        root, start = night_that_died(tmp)
        p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(root), capture_output=True, text=True,
                           timeout=120, env=dict(os.environ,
                                                 CEPA_DOCTOR_INSTALL="off"))
        out = p.stdout + p.stderr
        lines = [l for l in out.splitlines() if "[until]" in l]
        check("o doctor avisa em [until] que o supervisor morreu",
              any("morreu" in l for l in lines), out[-1500:])
        check("...com o build completo que faltou",
              any(VERIFY in l for l in lines), "\n".join(lines))


def closes(root, run_id, *extra):
    env = dict(os.environ, CEPA_WORKTREE_HOME=str(root.parent / "worktrees"))
    return subprocess.run([sys.executable, str(CEPA_UNTIL), "fecha-morto",
                           f"fila/{run_id}", "--repo", str(root), *extra],
                          capture_output=True, text=True, cwd=str(root),
                          env=env, timeout=120)


def run_of(start):
    return start["branch"].split("/", 1)[1]


def test_pending_and_doctor_say_to_run_close_dead():
    with tempfile.TemporaryDirectory() as tmp:
        root, start = night_that_died(tmp)
        m = (pending_ones(root).get("mortos") or [{}])[0]
        check("pendentes traz o comando do fecha-morto",
              m.get("fechar") == f"cepa-until fecha-morto fila/{run_of(start)}",
              str(m))
        p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(root), capture_output=True, text=True,
                           timeout=120, env=dict(os.environ,
                                                 CEPA_DOCTOR_INSTALL="off"))
        check("...e o doctor também",
              f"cepa-until fecha-morto fila/{run_of(start)}" in p.stdout,
              p.stdout[-1500:])


def test_close_dead_without_yes_only_shows_the_plan():
    with tempfile.TemporaryDirectory() as tmp:
        root, start = night_that_died(tmp)
        p = closes(root, run_of(start))
        check("sem --yes sai 0 e diz como confirmar",
              p.returncode == 0 and "--yes" in p.stdout, p.stdout + p.stderr)
        check("...e não mexe no estado", state(root)["estado"] == "rodando",
              str(state(root)))
        n = sum(1 for e in ledger_of(root) if e["evento"] == "verify")
        check("...nem roda o build", n == 0, str(ledger_of(root)))


def test_close_dead_green_leaves_the_run_ready_to_land():
    with tempfile.TemporaryDirectory() as tmp:
        root, start = night_that_died(tmp)
        run_id = run_of(start)
        p = closes(root, run_id, "--yes")
        check("fecha-morto --yes sai 0 com o build verde", p.returncode == 0,
              p.stdout + p.stderr)
        ev = ledger_of(root)
        check("...grava o build no registro, marcado como fechamento",
              any(e["evento"] == "verify" and e.get("fechamento")
                  and e.get("verde") for e in ev), str(ev[-3:]))
        check("...e fecha o registro com run_end",
              ev[-1]["evento"] == "run_end"
              and ev[-1].get("motivo") == "supervisor-morto", str(ev[-1]))
        state_dict = state(root)
        check("...o estado vira esperando-dono com a ação aterrissar",
              state_dict.get("estado") == "esperando-dono"
              and any(x.get("id") == "aterrissar" for x in state_dict.get("acoes") or []),
              str(state_dict))
        env = dict(os.environ, CEPA_WORKTREE_HOME=str(root.parent / "worktrees"))
        a = subprocess.run([sys.executable, str(CEPA_UNTIL), "aterrissar",
                            f"fila/{run_id}", "--repo", str(root), "--yes"],
                           capture_output=True, text=True, cwd=str(root),
                           env=env, timeout=120)
        check("...e o aterrissar aceita o run", a.returncode == 0,
              a.stdout + a.stderr)
        check("...o doctor para de apontar o run",
              not pending_ones(root).get("mortos"), str(pending_ones(root)))


def test_close_dead_red_does_not_change_the_state():
    with tempfile.TemporaryDirectory() as tmp:
        root, start = night_that_died(tmp)
        tree = Path(start["arvore"])
        (tree / "quebra.txt").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "quebra"], cwd=tree, check=True)
        p = closes(root, run_of(start), "--yes")
        check("build vermelho sai com erro", p.returncode != 0,
              p.stdout + p.stderr)
        check("...o registro guarda o vermelho",
              any(e["evento"] == "verify" and e.get("fechamento")
                  and e.get("verde") is False for e in ledger_of(root)),
              str(ledger_of(root)[-2:]))
        check("...e o estado continua `rodando` (o doctor segue apontando)",
              state(root)["estado"] == "rodando"
              and pending_ones(root).get("mortos"), str(state(root)))


def test_close_dead_refuses_live_supervisor():
    with tempfile.TemporaryDirectory() as tmp:
        alive_ = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(60)", "cepa-until"])
        try:
            root, start = night_that_died(tmp, pid=alive_.pid)
            p = closes(root, run_of(start), "--yes")
            check("fecha-morto recusa run com o supervisor vivo",
                  p.returncode != 0 and str(alive_.pid) in p.stderr,
                  p.stdout + p.stderr)
            check("...sem rodar o build",
                  not any(e["evento"] == "verify" and e.get("fechamento")
                          for e in ledger_of(root)))
        finally:
            alive_.kill()


def test_close_dead_accepts_interrupted_run():
    with tempfile.TemporaryDirectory() as tmp:
        root, start = night_that_died(tmp, estado="interrompido")
        check("run interrompido também aparece em `mortos`",
              len(pending_ones(root).get("mortos") or []) == 1,
              str(pending_ones(root)))
        p = closes(root, run_of(start), "--yes")
        check("...e o fecha-morto o fecha",
              p.returncode == 0
              and state(root)["estado"] == "esperando-dono",
              p.stdout + p.stderr)


def test_help_lists_the_subcommands():
    """The subcommands are dispatched before the argparse of the main mode: without
    `commands=` in the top parser, `--help` does not say they exist."""
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "--help"],
                       capture_output=True, text=True, timeout=30)
    listed = p.stdout.split("subcommands:", 1)[-1].split("arguments:", 1)[0]
    for sub in ("aterrissar", "pendentes", "fecha-morto", "decide"):
        check(f"--help cita o subcomando {sub}",
              p.returncode == 0 and f"\n  {sub} " in listed, p.stdout[-800:])
        for word in ("--help", "help"):
            q = subprocess.run([sys.executable, str(CEPA_UNTIL), sub, word],
                               capture_output=True, text=True, timeout=30)
            check(f"...e `{sub} {word}` mostra o uso dele",
                  q.returncode == 0 and f"usage: cepa until {sub}" in q.stdout,
                  q.stdout + q.stderr)
    q = subprocess.run([sys.executable, str(CEPA_UNTIL), "help"],
                       capture_output=True, text=True, timeout=30)
    check("`cepa-until help` é o mesmo texto de --help, exit 0",
          q.returncode == 0 and q.stdout == p.stdout, q.stdout + q.stderr)


def test_until_review_checks_the_dead_supervisor():
    plain_text = UNTIL_REVIEW.read_text(encoding="utf-8")
    check("o /common:until-review manda conferir `mortos` no pendentes",
          "cepa-until pendentes" in plain_text and "mortos" in plain_text
          and "interrompido" in plain_text and "fecha-morto" in plain_text)


def main():
    print("cepa-until — supervisor morto\n")
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
