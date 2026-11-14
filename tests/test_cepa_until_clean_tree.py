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
