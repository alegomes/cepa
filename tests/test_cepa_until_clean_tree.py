#!/usr/bin/env python3
"""Tests of the clean-tree rule of `cepa-until` (spec `until-arvore-limpa`).

Run with `python3 tests/test_cepa_until_clean_tree.py`.

The spec's red test says `--for 5m`; here it is `--for 2h`, because the
minimum reserve (45min) refuses to start an item in a 5-minute window.

CS-1: a run that ends normally leaves the main clone with nothing of its own
outside git. The queue marks, the `until/<run>.jsonl` record and the
`until/<run>.review.md` analysis go into ONE new commit on the clone's branch,
and that commit holds exactly those paths.

The helpers (fake `claude`, scenario repo, run launcher) are the ones of
`tests/test_cepa_until.py`, imported instead of copied.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until as base  # noqa: E402

check = base.check
FAILURES = base.FAILURES


def _scenario(tmp):
    """The scenario repo with the `.gitignore` lines the real repo has for the run's
    raw output and live state (`.log`, `.estado.json`): the spec keeps those ignored,
    so a test repo without them would measure files the real clone never shows."""
    root = base.build_repo(tmp, [base.item("a1")])
    (root / ".gitignore").write_text(
        ".claude/programs/*/until/*.log\n"
        ".claude/programs/*/until/*.estado.json\n"
        ".claude/queues/*/until/*.log\n"
        ".claude/queues/*/until/*.estado.json\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "gitignore"], cwd=root, check=True)
    return root


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True).stdout


def test_normal_end_commits_queue_record_and_review():
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        # The fake marks the item done and, when called as the end analysis
        # (`/common:until-review <ledger>`), prints a review like the real one.
        binv = base.fake_claude(tmp, (
            "if any('until-review' in a for a in ARGS):\n"
            "    print('# revisão do run\\n\\nnada pendente')\n"
            "else:\n"
            "    marca(primeiro_pendente(), status='done')"))
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = _git(root, "rev-parse", "HEAD").strip()
        p, _calls = base.run_until(root, binv, plan,
                                   ["--for", "2h", "--com-analise"])
        check("CS-1: o run termina", p.returncode == 0,
              f"saiu {p.returncode}: {p.stderr[-400:]}")
        records = sorted((root / ".claude" / "programs" / "fila" / "until")
                         .glob("*.jsonl"))
        check("CS-1: o run escreveu o registro e a revisão",
              len(records) == 1 and records[0].with_suffix(".review.md").exists(),
              str(records))
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-1: git status do clone vazio no fim do run", st == "", st)
        head = _git(root, "rev-parse", "HEAD").strip()
        check("CS-1: há um commit novo no topo", head != before)
        parent = _git(root, "rev-parse", "HEAD~1").strip()
        check("CS-1: ...um só, em cima da base", parent == before,
              f"HEAD~1={parent} base={before}")
        files = sorted(_git(root, "show", "--name-only", "--format=",
                            "HEAD").split())
        rel = ".claude/programs/fila/"
        run_id = records[0].stem if records else "?"
        expected = sorted([f"{rel}plan.yaml", f"{rel}until/{run_id}.jsonl",
                           f"{rel}until/{run_id}.review.md"])
        check("CS-1: o commit contém exatamente fila, registro e revisão",
              files == expected, f"{files} != {expected}")
        msg = _git(root, "log", "-1", "--format=%s")
        check("CS-1: a mensagem segue o formato decidido",
              msg.strip() == f"until fila/{run_id}: queue marks and run records",
              msg)


def test_normal_end_without_analysis_commits_what_exists():
    """No `.review.md` (analysis off): the commit takes the queue and the record,
    and does not fail over the missing file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, _calls = base.run_until(root, binv, plan, ["--for", "2h"])
        check("sem análise: o run termina", p.returncode == 0, p.stderr[-400:])
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("sem análise: git status vazio", st == "", st)
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("sem análise: commit com fila e registro, sem revisão",
              len(files) == 2 and any(f.endswith("plan.yaml") for f in files)
              and any(f.endswith(".jsonl") for f in files), str(files))


def test_quota_end_also_commits_the_record():
    """The run that stops on the account's usage ceiling (`limite-de-uso`) skips
    the analysis and ends through its own return path: that path commits too.
    The proof of 2026-11-14 removed the commit on this path and every other
    test stayed green. `--com-analise` is what reaches the path: with analysis
    off, the run returns before the quota branch."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        binv = base.fake_claude(tmp, f"print({base.FAR_LIMIT!r})\nsys.exit(1)")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = _git(root, "rev-parse", "HEAD").strip()
        p, _calls = base.run_until(root, binv, plan,
                                   ["--for", "2h", "--com-analise"])
        end = [e for e in base.ledger_of(root) if e.get("evento") == "run_end"]
        check("cota: o run termina por limite-de-uso",
              end and end[0].get("motivo") == "limite-de-uso", str(end))
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("cota: git status do clone vazio", st == "", st)
        check("cota: um commit novo sobre a base",
              _git(root, "rev-parse", "HEAD~1").strip() == before)
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("cota: o commit leva o registro do run",
              any(f.endswith(".jsonl") for f in files), str(files))


def test_commit_leaves_the_owners_staged_file_out():
    """A file the owner had staged before the run stays out of the run's commit
    and stays staged after it. It is what `git commit --only` buys: a plain
    `git commit` takes the whole index along (the proof of 2026-11-14 removed
    `--only` and every other test stayed green)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        (root / "alheio.txt").write_text("do dono\n", encoding="utf-8")
        subprocess.run(["git", "add", "alheio.txt"], cwd=root, check=True)
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        # `--dirty-ok`: the launch refuses a dirty tree by default; the owner who
        # runs with their own change staged passes this flag.
        p, _calls = base.run_until(root, binv, plan, ["--for", "2h", "--dirty-ok"])
        check("staged: o run termina", p.returncode == 0, p.stderr[-400:])
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("staged: o commit do run não leva o arquivo do dono",
              "alheio.txt" not in files and any(f.endswith(".jsonl") for f in files),
              str(files))
        staged = _git(root, "diff", "--cached", "--name-only").split()
        check("staged: o arquivo do dono continua em stage", staged == ["alheio.txt"],
              str(staged))


def test_cs2_owners_modified_and_staged_files_stay_as_they_were():
    """CS-2: with a tracked `notas.txt` modified (not staged) and a new
    `rascunho.md` staged in the clone before the run, the run's commit holds
    neither, and `git status --porcelain` shows both exactly as before: same
    status codes, same contents on disk and in the index. A `git add -A` (or
    `commit -a`) would take `notas.txt`; a commit without `--only` would take
    `rascunho.md`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        (root / "notas.txt").write_text("versão commitada\n", encoding="utf-8")
        subprocess.run(["git", "add", "notas.txt"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "notas"], cwd=root, check=True)
        (root / "notas.txt").write_text("edição do dono, sem stage\n",
                                        encoding="utf-8")
        (root / "rascunho.md").write_text("# rascunho do dono\n", encoding="utf-8")
        subprocess.run(["git", "add", "rascunho.md"], cwd=root, check=True)
        owners = ["notas.txt", "rascunho.md"]
        st_before = _git(root, "status", "--porcelain", "--", *owners)
        index_before = _git(root, "ls-files", "-s", "--", *owners)
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = _git(root, "rev-parse", "HEAD").strip()
        p, _calls = base.run_until(root, binv, plan, ["--for", "2h", "--dirty-ok"])
        check("CS-2: o run termina", p.returncode == 0, p.stderr[-400:])
        check("CS-2: há um commit novo do run",
              _git(root, "rev-parse", "HEAD~1").strip() == before)
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("CS-2: o commit do run não leva nenhum dos dois arquivos do dono",
              not set(owners) & set(files)
              and any(f.endswith(".jsonl") for f in files), str(files))
        check("CS-2: git status mostra os dois como estavam",
              st_before == " M notas.txt\nA  rascunho.md\n"
              and _git(root, "status", "--porcelain", "--", *owners) == st_before,
              _git(root, "status", "--porcelain", "--", *owners))
        check("CS-2: o índice dos dois não mudou",
              _git(root, "ls-files", "-s", "--", *owners) == index_before)
        check("CS-2: o conteúdo em disco não mudou",
              (root / "notas.txt").read_text(encoding="utf-8")
              == "edição do dono, sem stage\n"
              and (root / "rascunho.md").read_text(encoding="utf-8")
              == "# rascunho do dono\n")


def test_failing_pre_commit_hook_is_respected():
    """The run never skips the repo's hooks: a pre-commit that refuses leaves the
    records without a commit and the run says git refused. The proof of 2026-11-14
    added `--no-verify` and every other test stayed green."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'recusado pelo hook' >&2\nexit 1\n",
                        encoding="utf-8")
        hook.chmod(0o755)
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = _git(root, "rev-parse", "HEAD").strip()
        p, _calls = base.run_until(root, binv, plan, ["--for", "2h"])
        check("hook: o run termina", p.returncode == 0, p.stderr[-400:])
        check("hook: nenhum commit novo",
              _git(root, "rev-parse", "HEAD").strip() == before)
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("hook: os registros ficam sem commit",
              "plan.yaml" in st and ".jsonl" in st, st)
        check("hook: o run avisa que o git recusou",
              "git refused the commit of the run records" in p.stdout + p.stderr,
              (p.stdout + p.stderr)[-600:])


# ── CS-3: Ctrl+C and SIGTERM also end with the commit ───────────────────────

# The fake `claude` for CS-3: a1 is worked and closed like in a normal run; a2
# writes its pid mark and waits for `<tmp>/segue`, the window in which the test
# sends the signal with the second item in flight. As the end analysis
# (`/common:until-review`), it writes the same mark and waits too, so a signal
# can land after the run's final state.
_WAITS_ON_A2 = (
    "segue = os.path.join(os.path.dirname(os.environ['FAKE_CHAMADAS']), 'segue')\n"
    "def espera(rotulo):\n"
    "    open(segue + '.' + rotulo, 'w').write(str(os.getpid()))\n"
    "    fim = time.time() + 60\n"
    "    while not os.path.exists(segue) and time.time() < fim:\n"
    "        time.sleep(0.1)\n"
    "if any('until-review' in a for a in ARGS):\n"
    "    espera('analise')\n"
    "    print('# revisão do run')\n"
    "else:\n"
    "    ident = primeiro_pendente()\n"
    "    if ident == 'a2':\n"
    "        espera('a2')\n"
    "    marca(ident, status='done', evidence='ok')\n")


def _launch(root, binv, plan, args):
    """`cepa-until` in the background, so the test can signal it mid-run. Same
    environment as `base.run_until`."""
    import os
    env = dict(os.environ)
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(plan)
    env.setdefault("CEPA_UNTIL_LEITOR", "off")
    env["FAKE_CHAMADAS"] = str(root.parent / "chamadas.jsonl")
    env["CEPA_WORKTREE_HOME"] = str(root.parent / "worktrees")
    return subprocess.Popen(
        [sys.executable, str(base.CEPA_UNTIL), "fila", "--repo", str(root),
         "--no-verify", *args], env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def _signal_when(proc, mark, sig, tmp):
    """Waits for the fake's `mark`, sends `sig` to the supervisor, collects it, and
    releases the fake (it runs in its own session and survives the supervisor)."""
    import os
    import time
    try:
        end = time.time() + 60
        while not mark.exists() and time.time() < end and proc.poll() is None:
            time.sleep(0.1)
        reached = mark.exists()
        if reached:
            os.kill(proc.pid, sig)
        try:
            output, _ = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate()
        return reached, output
    finally:
        (Path(tmp) / "segue").write_text("")
        time.sleep(1.0)


def _interrupted_run_is_committed(label, root, before):
    """What the spec's red test demands once the process has exited: no path of
    the queue's folder left in `git status`, and the `.jsonl` with
    `run_interrompido` inside the newest commit."""
    rel = ".claude/programs/fila/"
    st = _git(root, "status", "--porcelain", "--untracked-files=all")
    loose = [line for line in st.splitlines() if rel in line]
    check(f"{label}: nenhum caminho da fila solto no git status", not loose, st)
    check(f"{label}: um commit novo sobre a base",
          _git(root, "rev-parse", "HEAD~1").strip() == before,
          _git(root, "log", "--oneline", "-3"))
    files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
    jsonl = [f for f in files if f.endswith(".jsonl")]
    check(f"{label}: o último commit leva a fila e o registro",
          f"{rel}plan.yaml" in files and len(jsonl) == 1, str(files))
    committed = _git(root, "show", f"HEAD:{jsonl[0]}") if jsonl else ""
    check(f"{label}: o registro commitado traz run_interrompido",
          '"run_interrompido"' in committed, committed[-400:])
    return jsonl[0] if jsonl else None


def test_cs3_signal_mid_second_item_commits_the_records():
    import signal
    for sig, code in ((signal.SIGINT, 130), (signal.SIGTERM, 143)):
        label = f"CS-3 {sig.name}"
        with tempfile.TemporaryDirectory() as tmp:
            root = base.build_repo(tmp, [base.item("a1"), base.item("a2")])
            (root / ".gitignore").write_text(
                ".claude/programs/*/until/*.log\n"
                ".claude/programs/*/until/*.estado.json\n", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                            "commit", "-qm", "gitignore"], cwd=root, check=True)
            binv = base.fake_claude(tmp, _WAITS_ON_A2)
            plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
            before = _git(root, "rev-parse", "HEAD").strip()
            proc = _launch(root, binv, plan, ["--for", "2h", "--no-analysis"])
            reached, output = _signal_when(proc, Path(tmp) / "segue.a2", sig, tmp)
            check(f"{label}: o segundo item entrou em voo", reached, output[-600:])
            check(f"{label}: o processo sai com {code}", proc.returncode == code,
                  f"{proc.returncode}: {output[-600:]}")
            jsonl = _interrupted_run_is_committed(label, root, before)
            if jsonl:
                committed = _git(root, "show", f"HEAD:{jsonl}")
                check(f"{label}: o registro commitado diz que a2 estava em voo",
                      '"id": "a2"' in committed.split('"run_interrompido"')[-1],
                      committed[-400:])
            msg = _git(root, "log", "-1", "--format=%s").strip()
            check(f"{label}: a mensagem segue o formato decidido",
                  msg.startswith("until fila/")
                  and msg.endswith(": queue marks and run records"), msg)
            check(f"{label}: a tela diz que commitou",
                  "commit:" in output and "not pushed" in output, output[-600:])


def test_cs3_second_signal_during_the_commit_does_not_cut_it():
    """The owner presses Ctrl+C twice. The second signal arrives while the run's
    `git commit` is still running (here a slow pre-commit hook holds it). Without
    ignoring SIGTERM/SIGINT around the commit, the handler raises SystemExit inside
    `subprocess.run`, git is killed halfway, nothing is committed and
    `.git/index.lock` may stay behind. The proof of 2026-11-14 swapped the ignore
    for the live handler and every other test stayed green."""
    import os
    import signal
    import time
    with tempfile.TemporaryDirectory() as tmp:
        root = base.build_repo(tmp, [base.item("a1"), base.item("a2")])
        started = Path(tmp) / "hook.started"
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_text(f"#!/bin/sh\ntouch '{started}'\nsleep 3\nexit 0\n",
                        encoding="utf-8")
        hook.chmod(0o755)
        binv = base.fake_claude(tmp, _WAITS_ON_A2)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = _git(root, "rev-parse", "HEAD").strip()
        proc = _launch(root, binv, plan, ["--for", "2h", "--no-analysis"])
        try:
            mark = Path(tmp) / "segue.a2"
            end = time.time() + 60
            while not mark.exists() and time.time() < end and proc.poll() is None:
                time.sleep(0.1)
            check("2º sinal: o segundo item entrou em voo", mark.exists())
            os.kill(proc.pid, signal.SIGTERM)
            end = time.time() + 30
            while not started.exists() and time.time() < end and proc.poll() is None:
                time.sleep(0.05)
            check("2º sinal: o commit do run começou (hook rodando)", started.exists())
            os.kill(proc.pid, signal.SIGINT)
            try:
                output, _ = proc.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                output, _ = proc.communicate()
        finally:
            (Path(tmp) / "segue").write_text("")
            time.sleep(1.0)
        check("2º sinal: o processo sai com 143 (o 1º sinal)",
              proc.returncode == 143, f"{proc.returncode}: {output[-600:]}")
        check("2º sinal: o commit do run terminou mesmo assim",
              _git(root, "rev-parse", "HEAD~1").strip() == before,
              _git(root, "log", "--oneline", "-3"))
        check("2º sinal: não sobrou .git/index.lock",
              not (root / ".git" / "index.lock").exists())
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        loose = [line for line in st.splitlines() if ".claude/programs/fila/" in line
                 and not line.endswith(".log") and not line.endswith(".estado.json")]
        check("2º sinal: nenhum registro do run solto", not loose, st)


def test_cs3_signal_during_the_end_analysis_commits_the_records():
    """After the final state is recorded, a signal only ends the run (it no
    longer writes `run_interrompido`), but the records the run wrote still have
    to land in the commit: otherwise the Ctrl+C on a slow analysis leaves the
    queue and the `.jsonl` loose again."""
    import signal
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        binv = base.fake_claude(tmp, _WAITS_ON_A2)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        before = _git(root, "rev-parse", "HEAD").strip()
        proc = _launch(root, binv, plan, ["--for", "2h"])
        reached, output = _signal_when(proc, Path(tmp) / "segue.analise",
                                       signal.SIGINT, tmp)
        check("CS-3 análise: a análise final começou", reached, output[-600:])
        check("CS-3 análise: o processo sai com 130", proc.returncode == 130,
              f"{proc.returncode}: {output[-600:]}")
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        loose = [line for line in st.splitlines() if ".claude/programs/fila/" in line]
        check("CS-3 análise: nenhum caminho da fila solto", not loose, st)
        check("CS-3 análise: um commit novo sobre a base",
              _git(root, "rev-parse", "HEAD~1").strip() == before,
              _git(root, "log", "--oneline", "-3"))
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("CS-3 análise: o commit leva a fila (a1 done) e o registro",
              any(f.endswith("plan.yaml") for f in files)
              and any(f.endswith(".jsonl") for f in files), str(files))


def _dead_pid():
    """A pid that no longer exists: a child that already exited and was reaped."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _other_queue(root, layout="queues"):
    """Commits a second queue `outra` (new layout by default) with two items and
    returns its queue file."""
    import yaml
    fname = "queue.yaml" if layout == "queues" else "plan.yaml"
    path = root / ".claude" / layout / "outra" / fname
    path.parent.mkdir(parents=True)
    key = "queue" if layout == "queues" else "program"
    path.write_text(yaml.safe_dump(
        {"schema_version": 2, "mode": "single-track", key: "outra",
         "source": "teste", "items": [base.item("o1"), base.item("o2")]},
        allow_unicode=True), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "outra"], cwd=root, check=True)
    return path


def _dead_run_of(queue_file, pid, run="2026-11-13-2200", ended=False, host=None,
                 review=False):
    """What a run of `outra` killed without warning leaves in the clone: its
    `.jsonl` with `run_start` (pid, host) and `item_start`, the state `rodando`
    (ignored by git) and the queue marks of the item in flight, all uncommitted."""
    import json
    import socket
    import yaml
    d = queue_file.parent / "until"
    d.mkdir(exist_ok=True)
    host = host or socket.gethostname()
    events = [{"evento": "run_start", "fila": "outra", "pid": pid, "host": host,
               "branch": "until/x", "prazo": "2026-11-14T06:00:00"},
              {"evento": "item_start", "id": "o1"}]
    if ended:
        events.append({"evento": "run_end", "motivo": "fim-da-fila"})
    (d / f"{run}.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    (d / f"{run}.estado.json").write_text(json.dumps(
        {"run": run, "fila": "outra", "estado": "rodando", "pid": pid,
         "host": host, "branch": "until/x", "registro": f"{run}.jsonl"}),
        encoding="utf-8")
    q = yaml.safe_load(queue_file.read_text(encoding="utf-8"))
    q["items"][0].update(status="in_progress", claimed_by={"pid": pid})
    queue_file.write_text(yaml.safe_dump(q, allow_unicode=True), encoding="utf-8")
    rel = str(queue_file.parent.relative_to(queue_file.parents[3]))
    paths = [f"{rel}/{queue_file.name}", f"{rel}/until/{run}.jsonl"]
    if review:
        # The analysis a run writes at its end; a crash right after it leaves
        # it loose beside the record.
        (d / f"{run}.review.md").write_text("# revisão\n", encoding="utf-8")
        paths.append(f"{rel}/until/{run}.review.md")
    return paths


def test_cs4_launch_collects_the_loose_records_of_a_dead_run_of_another_queue():
    """CS-4: with a `.jsonl` and a modified `queue.yaml` of queue `outra` whose
    supervisor died (pid that no longer exists), `cepa-until fila` does not refuse
    over a dirty tree: it makes a collect commit with exactly the paths of
    `outra` BEFORE the first item (the run branch starts on top of it), and the
    run's own commit comes after."""
    import json
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        other = _other_queue(root)
        expected = sorted(_dead_run_of(other, _dead_pid(), review=True))
        before = _git(root, "rev-parse", "HEAD").strip()
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = base.run_until(root, binv, plan, ["--for", "2h"])
        check("CS-4: a largada não recusa por árvore suja",
              p.returncode == 0 and "modified file(s)" not in p.stderr,
              f"saiu {p.returncode}: {p.stderr[-400:]}")
        check("CS-4: o item da fila rodou", len(calls) == 1, str(calls))
        subjects = _git(root, "log", "--format=%H %s", f"{before}..HEAD").splitlines()
        collect = [s.split(" ", 1)[0] for s in subjects
                   if s.split(" ", 1)[1] == "until: collect records of dead runs (outra)"]
        check("CS-4: há um commit de recolha com a mensagem decidida",
              len(collect) == 1, "\n".join(subjects))
        sha = collect[0] if collect else "HEAD"
        files = sorted(_git(root, "show", "--name-only", "--format=", sha).split())
        check("CS-4: o commit de recolha leva exatamente os caminhos de outra",
              files == expected, f"{files} != {expected}")
        check("CS-4: a recolha é o primeiro commit sobre a base",
              _git(root, "rev-parse", f"{sha}~1").strip() == before)
        start = [e for e in base.ledger_of(root) if e.get("evento") == "run_start"]
        run_base = (start[0].get("base") if start else None) or "?"
        check("CS-4: a recolha veio antes do primeiro item (o run larga sobre ela)",
              subprocess.run(["git", "merge-base", "--is-ancestor", sha, run_base],
                             cwd=root).returncode == 0, run_base)
        check("CS-4: o run_start registra a recolha",
              start and (start[0].get("recolha") or {}).get("commit") == sha,
              json.dumps(start)[:400])
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-4: nada de outra fica solto depois",
              ".claude/queues/outra/" not in st.replace(".estado.json", ""), st)


def test_cs4_collects_from_the_legacy_layout_and_leaves_the_owners_change_out():
    """The same collect for a queue in the old layout (`.claude/programs/<q>/
    plan.yaml`), and only the run's paths: a file the owner left modified beside
    it stays out of the collect commit (the launch then runs with `--dirty-ok`,
    the owner's own escape)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        other = _other_queue(root, layout="programs")
        expected = sorted(_dead_run_of(other, _dead_pid(), review=True))
        (root / "notas.txt").write_text("do dono\n", encoding="utf-8")
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = base.run_until(root, binv, plan, ["--for", "2h", "--dirty-ok"])
        check("CS-4 legado: o run larga", len(calls) == 1, p.stderr[-400:])
        sha = _git(root, "log", "--format=%H", "--grep",
                   "^until: collect records of dead runs (outra)$").strip()
        files = sorted(_git(root, "show", "--name-only", "--format=", sha).split()) \
            if sha else []
        check("CS-4 legado: recolha com exatamente o plan.yaml, o registro e a revisão",
              files == expected, f"{files} != {expected}")
        check("CS-4 legado: o arquivo do dono segue solto e fora dos commits",
              "?? notas.txt" in _git(root, "status", "--porcelain"))


def test_cs4_what_is_not_a_dead_run_is_not_collected():
    """The counterpoints. (1) A modified queue with no loose run record is the
    owner's change, not a dead run's: the launch refuses as before and commits
    nothing. (2) A run of `outra` with a live supervisor is left alone (the
    existing live-run tests pin that the live run's marks are not dirt).
    (3) A record from ANOTHER machine with no `run_end` may be a live run there:
    not collected, so the launch refuses over its queue marks."""
    import yaml
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        other = _other_queue(root)
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        q = yaml.safe_load(other.read_text(encoding="utf-8"))
        q["items"][1]["title"] = "editado pelo dono"
        other.write_text(yaml.safe_dump(q, allow_unicode=True), encoding="utf-8")
        before = _git(root, "rev-parse", "HEAD").strip()
        p, calls = base.run_until(root, binv, plan, ["--for", "2h"])
        check("sem registro solto: a fila editada pelo dono ainda recusa",
              p.returncode == 2 and not calls and "outra/queue.yaml" in p.stderr,
              f"saiu {p.returncode}: {p.stderr[-400:]}")
        check("...e nenhum commit foi feito",
              _git(root, "rev-parse", "HEAD").strip() == before)
        subprocess.run(["git", "checkout", "-q", "--", str(other)], cwd=root,
                       check=True)

        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(60)", "cepa-until"])
        try:
            _dead_run_of(other, alive.pid)
            (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
            p, calls = base.run_until(root, binv, plan, ["--for", "2h"])
            check("supervisor vivo: o registro dele não é recolhido",
                  "collect records of dead runs" not in _git(
                      root, "log", "--format=%s"), _git(root, "log", "--oneline"))
        finally:
            alive.kill()
            alive.wait()
        for f in (other.parent / "until").iterdir():
            f.unlink()
        subprocess.run(["git", "checkout", "-q", "--", str(other)], cwd=root,
                       check=True)

        _dead_run_of(other, _dead_pid(), host="outra-maquina.local")
        base.requeue(root, plan)
        before = _git(root, "rev-parse", "HEAD").strip()
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        p, calls = base.run_until(root, binv, plan, ["--for", "2h"])
        check("registro de outra máquina sem run_end não é recolhido",
              p.returncode == 2 and not calls
              and _git(root, "rev-parse", "HEAD").strip() == before,
              f"saiu {p.returncode}: {p.stderr[-400:]}")


def test_cs4_a_record_deleted_from_disk_is_not_collected_as_a_deletion():
    """An older run's record that was committed and then vanished from disk (a
    sync tool, a hand `rm`) is not a dead run's loose record: the collect commit
    takes the dead run's paths and does not turn the vanishing into a deletion
    in history. The file stays committed at HEAD."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        other = _other_queue(root)
        old = other.parent / "until" / "2026-11-01-0000.jsonl"
        old.parent.mkdir()
        old.write_text('{"evento": "run_start"}\n', encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "registro antigo"], cwd=root, check=True)
        old.unlink()
        expected = sorted(_dead_run_of(other, _dead_pid()))
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = base.run_until(root, binv, plan, ["--for", "2h"])
        sha = _git(root, "log", "--format=%H", "--grep",
                   "^until: collect records of dead runs (outra)$").strip()
        files = sorted(_git(root, "show", "--name-only", "--format=", sha).split()) \
            if sha else []
        check("apagado: a recolha leva só os caminhos do run morto",
              files == expected, f"{files} != {expected}: {p.stderr[-300:]}")
        check("apagado: o registro antigo segue no HEAD",
              _git(root, "ls-files", "--", str(old.relative_to(root))).strip()
              == str(old.relative_to(root)))


def test_cs4_dry_run_says_what_it_would_collect_and_commits_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        other = _other_queue(root)
        _dead_run_of(other, _dead_pid())
        before = _git(root, "rev-parse", "HEAD").strip()
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = base.run_until(root, binv, plan, ["--for", "2h", "--dry-run"])
        check("CS-4 dry-run: sai 0 sem recusar", p.returncode == 0
              and "modified file(s)" not in p.stderr, p.stderr[-400:])
        check("CS-4 dry-run: diz o que recolheria",
              "would collect 2 loose record(s) of dead runs (outra)" in p.stdout,
              p.stdout[-600:])
        check("CS-4 dry-run: nenhum commit",
              _git(root, "rev-parse", "HEAD").strip() == before and not calls)


def main():
    print("cepa-until — árvore limpa no fim do run\n")
    for given_name, fn in sorted(globals().items()):
        if given_name.startswith("test_") and callable(fn):
            print(f"{given_name}:")
            fn()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        return 1
    print("✓ tudo verde")
    return 0


if __name__ == "__main__":
    sys.exit(main())
