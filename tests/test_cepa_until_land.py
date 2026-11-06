#!/usr/bin/env python3
"""cepa-until aterrissar — step 3 of until-fim-sem-dono.

The run does not touch `main` (owner's decision 3, 26/09): at the end it records the action
`aterrissar` in `<run>.estado.json`, and whoever triggers it is the owner. The command is a
thin layer over the guards that already exist (C3 of
`docs/estrategia-fim-do-cepa-until.md`): single owner through `worktree-guard.py`,
stop at conflict, never push with a red build, record the return
point, refuse if the state changed since the proposal, and resume from where it stopped.

All the cases run a real `cepa-until` against a fake repo, and then
`cepa-until aterrissar` against what it left.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)
from test_cepa_until_run_branch import (  # noqa: E402
    WORKS, VERIFY, git, plan_of)


def state(root):
    d = root / ".claude" / "programs" / "fila" / "until"
    return json.loads(sorted(d.glob("*.estado.json"))[-1].read_text())


def night(root):
    """Runs a night with a1 delivered and returns (run_id, branch, tree)."""
    tmp = root.parent
    binv = fake_claude(tmp, WORKS)
    run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", VERIFY])
    start = [e for e in ledger_of(root) if e["evento"] == "run_start"][0]
    return start["branch"].split("/", 1)[1], start["branch"], start["arvore"]


def land(root, run_id, *extra):
    env = dict(os.environ)
    env.setdefault("CEPA_WORKTREE_HOME", str(root.parent / "worktrees"))
    return subprocess.run(
        [sys.executable, str(CEPA_UNTIL), "aterrissar", f"fila/{run_id}",
         "--repo", str(root), *extra],
        capture_output=True, text=True, cwd=str(root), env=env, timeout=120)


def commit(root, file, content, msg):
    (root / file).write_text(content)
    # Only the file: the queue the run marked in the clone stays uncommitted, as it
    # really does after a run.
    git(root, "add", file)
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", msg)


def with_origin(root):
    remote = root.parent / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(root, "remote", "add", "origin", str(remote))
    git(root, "push", "-q", "-u", "origin", "HEAD")
    return remote


def test_without_yes_only_shows_the_plan():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, branch, _ = night(root)
        before = git(root, "rev-parse", "HEAD")
        p = land(root, run_id)
        check("sem --yes sai 0", p.returncode == 0, p.stderr + p.stdout)
        check("...mostra o efeito e como confirmar",
              "--yes" in p.stdout and branch in p.stdout, p.stdout)
        check("...e não mexe na main", git(root, "rev-parse", "HEAD") == before)


def test_land_builds_pushes_and_cleans():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        remote = with_origin(root)
        run_id, branch, tree = night(root)
        before = git(root, "rev-parse", "HEAD")
        p = land(root, run_id, "--yes")
        check("aterrissa com saída 0", p.returncode == 0, p.stderr + p.stdout)
        log = git(root, "log", "--format=%s", "HEAD").splitlines()
        check("o commit do item está na main", "a1" in log, str(log))
        check("...por um merge (--no-ff)",
              len(git(root, "rev-list", "--parents", "-1", "HEAD").split()) == 3)
        check("o push levou a main ao origin",
              git(root, "rev-parse", "HEAD")
              == subprocess.run(["git", "--git-dir", str(remote), "rev-parse",
                                 "HEAD"], capture_output=True,
                                text=True).stdout.strip())
        check("a branch da noite some",
              not git(root, "branch", "--list", branch))
        check("...e a worktree dela também", not Path(tree).exists(), tree)
        state_dict = state(root)
        check("o estado vira aterrissado com o ponto de retorno",
              state_dict.get("estado") == "aterrissado"
              and (state_dict.get("aterrissagem") or {}).get("retorno") == before,
              str(state_dict))


def test_red_build_after_the_merge_goes_back_to_return_without_push():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        remote = with_origin(root)
        run_id, branch, _ = night(root)
        # main moved after the run, and the sum of the two goes red.
        commit(root, "quebra.txt", "x", "main andou")
        git(root, "push", "-q")
        return_ = git(root, "rev-parse", "HEAD")
        p = land(root, run_id, "--yes")
        check("sai com erro", p.returncode != 0, p.stdout)
        check("a main volta ao ponto de retorno",
              git(root, "rev-parse", "HEAD") == return_)
        check("...o origin não recebe nada",
              subprocess.run(["git", "--git-dir", str(remote), "rev-parse",
                              "HEAD"], capture_output=True,
                             text=True).stdout.strip() == return_)
        check("a branch da noite continua", git(root, "branch", "--list", branch))
        check("o estado continua esperando-dono",
              state(root).get("estado") == "esperando-dono", str(state(root)))
        check("a saída diz que o build ficou vermelho",
              "red build" in p.stdout.lower(), p.stdout)
        check("...e o desfazer preserva a fila que o run marcou no clone",
              "status: done" in plan_of(root).read_text(),
              plan_of(root).read_text()[:300])


def test_conflict_stops_and_running_again_resumes():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, branch, tree = night(root)
        commit(root, "a1.txt", "outro conteudo", "main mexeu no a1.txt")
        p = land(root, run_id, "--yes")
        check("o conflito para com erro", p.returncode != 0, p.stdout)
        check("...e nomeia o arquivo", "a1.txt" in p.stdout, p.stdout)
        check("...deixando o conflito para o dono",
              "a1.txt" in git(root, "diff", "--name-only", "--diff-filter=U"))
        # The owner resolves and concludes the merge.
        (root / "a1.txt").write_text("resolvido")
        git(root, "add", "a1.txt")
        git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
            "resolve")
        p = land(root, run_id, "--yes")
        check("rodar de novo retoma do build e termina",
              p.returncode == 0 and state(root).get("estado") == "aterrissado",
              p.stdout + p.stderr)
        check("...sem fazer outro merge",
              git(root, "log", "-1", "--format=%s") == "resolve",
              git(root, "log", "-3", "--format=%s"))
        check("...e limpa a branch da noite",
              not git(root, "branch", "--list", branch))


def test_live_owner_on_the_night_branch_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, branch, tree = night(root)
        d = root / ".claude" / "sessions"
        d.mkdir(parents=True, exist_ok=True)
        current_time = datetime.now(timezone.utc).isoformat(timespec="seconds")
        (d / "viva.json").write_text(json.dumps({
            "session_id": "viva", "pid": os.getpid(),
            "hostname": socket.gethostname(), "cwd": tree,
            "branch": branch, "started_at": current_time, "last_seen": current_time}))
        before = git(root, "rev-parse", "HEAD")
        p = land(root, run_id, "--yes")
        check("recusa com sessão viva na branch da noite",
              p.returncode != 0 and git(root, "rev-parse", "HEAD") == before,
              p.stdout + p.stderr)
        check("...e diz quem está nela", tree in p.stdout + p.stderr,
              p.stdout + p.stderr)


def test_night_branch_that_changed_after_the_proposal_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, branch, tree = night(root)
        commit(Path(tree), "tarde.txt", "x", "commit depois do fim do run")
        before = git(root, "rev-parse", "HEAD")
        p = land(root, run_id, "--yes")
        check("recusa quando a branch da noite andou depois da proposta",
              p.returncode != 0 and git(root, "rev-parse", "HEAD") == before,
              p.stdout + p.stderr)
        check("...e diz o que mudou", "changed since" in p.stdout + p.stderr,
              p.stdout + p.stderr)


def test_clone_with_uncommitted_change_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, _, _ = night(root)
        (root / "rascunho.txt").write_text("x")
        before = git(root, "rev-parse", "HEAD")
        p = land(root, run_id, "--yes")
        check("recusa com o clone sujo",
              p.returncode != 0 and git(root, "rev-parse", "HEAD") == before,
              p.stdout + p.stderr)


def test_the_run_summary_points_to_the_command():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", VERIFY])
        run_id = [e for e in ledger_of(root)
                  if e["evento"] == "run_start"][0]["branch"].split("/", 1)[1]
        cmd = f"cepa-until aterrissar fila/{run_id}"
        check("o terminal mostra o comando", cmd in p.stdout, p.stdout[-800:])
        action = (state(root).get("acoes") or [{}])[0]
        check("...e o estado também", cmd in (action.get("comando") or ""), str(action))


# ── step 5: pendentes, doctor and next read the run state ──────────────────

DOCTOR = CEPA_UNTIL.parent / "cepa-doctor"
NEXT = CEPA_UNTIL.parents[1] / "commands" / "next.md"


def pending_ones(root):
    return subprocess.run([sys.executable, str(CEPA_UNTIL), "pendentes",
                           "--repo", str(root)], capture_output=True, text=True,
                          cwd=str(root), timeout=60)


def test_5_pending_lists_the_waiting_run_and_vanishes_after_landing():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, _, _ = night(root)
        p = pending_ones(root)
        check("pendentes lista o run com o comando",
              p.returncode == 0
              and f"cepa-until aterrissar fila/{run_id}" in p.stdout,
              p.stdout + p.stderr)
        land(root, run_id, "--yes")
        check("...e some depois de aterrissado",
              run_id not in pending_ones(root).stdout, pending_ones(root).stdout)


def test_5_hand_made_merge_also_takes_the_run_off_the_list():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, branch, _ = night(root)
        git(root, "-c", "user.email=t@t", "-c", "user.name=t", "merge",
            "-q", "--no-ff", "--no-edit", branch)
        check("branch já mesclada no clone não é pendência",
              run_id not in pending_ones(root).stdout, pending_ones(root).stdout)


def test_5_doctor_warns_of_the_run_waiting_for_the_owner():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        run_id, _, _ = night(root)
        p = subprocess.run([sys.executable, str(DOCTOR), "--projeto"],
                           cwd=str(root), capture_output=True, text=True,
                           timeout=120, env=dict(os.environ,
                                                 CEPA_DOCTOR_INSTALL="off"))
        out = p.stdout + p.stderr
        check("o doctor avisa na área [until] com o comando",
              "[until]" in out
              and f"cepa-until aterrissar fila/{run_id}" in out, out[-1500:])


def test_5_next_reads_the_waiting_runs():
    plain_text = NEXT.read_text(encoding="utf-8")
    check("o /common:next manda rodar o cepa-until pendentes",
          "cepa-until pendentes" in plain_text)


def test_5_short_header_without_absolute_path_and_with_cost():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = WORKS + (
            "print(json.dumps({'type': 'result', 'result': 'ok',"
            " 'total_cost_usd': 1.25}))\n")
        binv = fake_claude(tmp, body)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY])
        header = p.stdout.split("\n\n")[0].splitlines()
        check("o cabeçalho tem no máximo 7 linhas", len(header) <= 7,
              "\n".join(header))
        check("nenhum caminho absoluto do repo na saída",
              str(root) not in p.stdout
              and str(root.resolve()) not in p.stdout, p.stdout)
        check("o resumo traz o custo com a conta",
              "US$ 2,50" in p.stdout and "1,25 + 1,25" in p.stdout,
              p.stdout[-900:])
        check("...e o estado também",
              state(root).get("custo_usd") == 2.5, str(state(root)))


def test_5_cost_counts_once_per_session_not_per_result_block():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        # One process that prints the same `result` 3 times (the session is the
        # same, the cost is cumulative); the other item is another session.
        body = WORKS + (
            "sid, custo = ('s-x', 28.47) if ident == 'a1' else ('s-y', 21.78)\n"
            "for _ in range(3 if sid == 's-x' else 1):\n"
            "    print(json.dumps({'type': 'result', 'result': 'ok',"
            " 'session_id': sid, 'total_cost_usd': custo}))\n")
        binv = fake_claude(tmp, body)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY])
        check("o custo soma uma vez por sessão, sem os blocos repetidos",
              "US$ 50,25" in p.stdout and "28,47 + 21,78" in p.stdout
              and "2 round(s)" in p.stdout, p.stdout[-900:])
        check("...e o estado também",
              state(root).get("custo_usd") == 50.25, str(state(root)))


def main():
    print("cepa-until aterrissar\n")
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
