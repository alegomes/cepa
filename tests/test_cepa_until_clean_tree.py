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


# ── CS-5: git refuses the commit: the run warns with the reason and the command ─

def _git_spy(tmp):
    """A `git` first on PATH that logs each call's argv and runs the real git, so
    the test sees every flag the run handed to git (`--no-verify` included)."""
    import shutil
    real = shutil.which("git")
    spy_dir = Path(tmp) / "espiao-git"
    spy_dir.mkdir()
    log = Path(tmp) / "git-chamadas.txt"
    spy = spy_dir / "git"
    spy.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {log}\nexec {real} \"$@\"\n",
                   encoding="utf-8")
    spy.chmod(0o755)
    return spy_dir, log


def _cs5_run(tmp, hook_body):
    """One run with analysis on (so a `.review.md` exists) and, when `hook_body`
    is set, a pre-commit hook with that body. Returns (root, process, git log,
    HEAD before the run)."""
    import os
    root = _scenario(tmp)
    if hook_body is not None:
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_text(hook_body, encoding="utf-8")
        hook.chmod(0o755)
    binv = base.fake_claude(tmp, (
        "if any('until-review' in a for a in ARGS):\n"
        "    print('# revisão do run\\n\\nnada pendente')\n"
        "else:\n"
        "    marca(primeiro_pendente(), status='done')"))
    spy_dir, log = _git_spy(tmp)
    plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
    before = _git(root, "rev-parse", "HEAD").strip()
    p, _calls = base.run_until(root, binv, plan, ["--for", "2h", "--com-analise"],
                               extra_env={"PATH": f"{spy_dir}:{os.environ['PATH']}"})
    return root, p, log, before


def _cs5_checks(label, tmp, hook_body, reason):
    with tempfile.TemporaryDirectory() as tmp_ok:
        _r, p_ok, _l, _b = _cs5_run(tmp_ok, None)
    root, p, log, before = _cs5_run(tmp, hook_body)
    out = p.stdout + p.stderr
    check(f"CS-5 {label}: o código de saída é o mesmo do run sem o hook",
          p.returncode == p_ok.returncode, f"{p.returncode} != {p_ok.returncode}")
    check(f"CS-5 {label}: nenhum commit novo",
          _git(root, "rev-parse", "HEAD").strip() == before)
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    check(f"CS-5 {label}: o run chamou git commit pelo espião", "commit" in calls,
          calls[-400:])
    check(f"CS-5 {label}: nenhuma chamada a git traz --no-verify",
          "--no-verify" not in calls,
          [l for l in calls.splitlines() if "--no-verify" in l])
    reason_lines = [l for l in out.splitlines() if "git refused" in l]
    check(f"CS-5 {label}: a tela final traz a linha do motivo",
          any(reason in l for l in reason_lines), out[-800:])
    marker = "to commit by hand: "
    cmds = [l.split(marker, 1)[1].strip() for l in out.splitlines() if marker in l]
    check(f"CS-5 {label}: a tela final traz o comando para o dono",
          len(cmds) == 1 and "git" in cmds[0] and " commit " in cmds[0], out[-800:])
    reviews = sorted((root / ".claude" / "programs" / "fila" / "until")
                     .glob("*.review.md"))
    text = reviews[0].read_text(encoding="utf-8") if reviews else ""
    check(f"CS-5 {label}: o .review.md mantém a análise",
          "nada pendente" in text, text[:300])
    check(f"CS-5 {label}: o .review.md traz o motivo", reason in text, text[-600:])
    check(f"CS-5 {label}: o .review.md traz o mesmo comando",
          bool(cmds) and cmds[0] in text, text[-600:])
    check(f"CS-5 {label}: o comando não traz --no-verify",
          bool(cmds) and "--no-verify" not in cmds[0], cmds)
    if not cmds:
        return
    # The command is exact: once the owner deals with the hook, running it as
    # printed, from anywhere, leaves the clone clean with one commit of the run.
    (root / ".git" / "hooks" / "pre-commit").unlink()
    r = subprocess.run(["sh", "-c", cmds[0]], cwd=tmp, capture_output=True,
                       text=True)
    check(f"CS-5 {label}: o comando roda como impresso", r.returncode == 0,
          r.stdout + r.stderr)
    st = _git(root, "status", "--porcelain", "--untracked-files=all")
    check(f"CS-5 {label}: depois do comando, git status vazio", st == "", st)
    check(f"CS-5 {label}: ...com um commit só, sobre a base",
          _git(root, "rev-parse", "HEAD~1").strip() == before)
    files = sorted(_git(root, "show", "--name-only", "--format=", "HEAD").split())
    check(f"CS-5 {label}: ...que leva fila, registro e revisão",
          len(files) == 3 and any(f.endswith("plan.yaml") for f in files)
          and any(f.endswith(".jsonl") for f in files)
          and any(f.endswith(".review.md") for f in files), files)


def test_cs5_refusing_hook_with_a_message():
    with tempfile.TemporaryDirectory() as tmp:
        _cs5_checks("hook com mensagem", tmp,
                    "#!/bin/sh\necho 'lint: 3 erros em fila' >&2\nexit 1\n",
                    "lint: 3 erros em fila")


def test_cs5_silent_refusing_hook_still_warns():
    """A hook that exits 1 without printing: git says nothing, and before CS-5 the
    run said nothing either (`elif error` on an empty string)."""
    with tempfile.TemporaryDirectory() as tmp:
        _cs5_checks("hook mudo", tmp, "#!/bin/sh\nexit 1\n", "exited 1")


# ── CS-6: merge, rebase or detached HEAD at the end: no commit, a warning ────

def _cs6_run(tmp, make_state):
    """One run with analysis on. `make_state` is Python run by the fake `claude`
    when it is the end analysis (the run's last act before the commit), inside the
    main clone: the launch refuses a tree that is mid-merge, so the state has to
    appear during the run. It snapshots the index right after. Returns (root,
    process, HEAD before, `git ls-files -s` snapshot taken by the fake)."""
    root = _scenario(tmp)
    # A side branch that changes another file, for `git merge --no-commit`.
    _git(root, "checkout", "-qb", "lado")
    (root / "lado.txt").write_text("lado\n", encoding="utf-8")
    _git(root, "add", "lado.txt")
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit",
                    "-qm", "lado"], cwd=root, check=True)
    _git(root, "checkout", "-q", "-")
    snap = Path(tmp) / "indice-antes.txt"
    binv = base.fake_claude(tmp, (
        "def git(*a):\n"
        "    import subprocess\n"
        f"    return subprocess.run(['git', '-C', {str(root)!r}, *a],\n"
        "        capture_output=True, text=True, check=True).stdout\n"
        "if any('until-review' in a for a in ARGS):\n"
        "    print('# revisão do run\\n\\nnada pendente')\n"
        + "".join("    " + l + "\n" for l in make_state.splitlines())
        + f"    open({str(snap)!r}, 'w').write(git('ls-files', '-s'))\n"
        "else:\n"
        "    marca(primeiro_pendente(), status='done')"))
    plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
    before = _git(root, "rev-parse", "HEAD").strip()
    p, _calls = base.run_until(root, binv, plan, ["--for", "2h", "--com-analise"])
    return root, p, before, snap


_CS6_STATES = {
    "merge": ("git('-c', 'user.email=t@t', '-c', 'user.name=t', 'merge', "
              "'--no-commit', '--no-ff', 'lado')", "merge", ["MERGE_HEAD"]),
    "rebase": ("os.makedirs(os.path.join(git('rev-parse', '--absolute-git-dir')"
               ".strip(), 'rebase-merge'))", "rebase", ["rebase-merge"]),
    # `rebase-apply` is what `git am` and `git rebase --apply` leave behind.
    "rebase-apply": ("os.makedirs(os.path.join(git('rev-parse', "
                     "'--absolute-git-dir').strip(), 'rebase-apply'))",
                     "rebase", ["rebase-apply"]),
    "cherry-pick": ("open(os.path.join(git('rev-parse', '--absolute-git-dir')"
                    ".strip(), 'CHERRY_PICK_HEAD'), 'w').write("
                    "git('rev-parse', 'HEAD'))", "cherry-pick",
                    ["CHERRY_PICK_HEAD"]),
    "revert": ("open(os.path.join(git('rev-parse', '--absolute-git-dir')"
               ".strip(), 'REVERT_HEAD'), 'w').write(git('rev-parse', 'HEAD'))",
               "revert", ["REVERT_HEAD"]),
    "HEAD destacado": ("git('checkout', '-q', '--detach')", "detached HEAD", []),
}


def _cs6_checks(label, tmp, tmp_ok):
    code, word, markers = _CS6_STATES[label]
    root, p, before, snap = _cs6_run(tmp, code)
    root_ok, p_ok, _b, _s = _cs6_run(tmp_ok, "pass")
    out = p.stdout + p.stderr
    gitdir = Path(_git(root, "rev-parse", "--absolute-git-dir").strip())
    check(f"CS-6 {label}: o código de saída é o mesmo do run sem o estado",
          p.returncode == p_ok.returncode, f"{p.returncode} != {p_ok.returncode}")
    check(f"CS-6 {label}: nenhum commit novo",
          _git(root, "rev-parse", "HEAD").strip() == before)
    for m in markers:
        check(f"CS-6 {label}: {m} segue no lugar", (gitdir / m).exists())
    if label == "merge":
        check(f"CS-6 {label}: o git status ainda diz que está no merge",
              "merging" in _git(root, "status").lower(), _git(root, "status"))
    snapshot = snap.read_text(encoding="utf-8") if snap.exists() else None
    check(f"CS-6 {label}: o fake chegou a tirar o retrato do índice",
          snapshot is not None, out[-600:])
    check(f"CS-6 {label}: o índice é idêntico byte a byte ao de antes do commit",
          snapshot == _git(root, "ls-files", "-s"),
          (snapshot, _git(root, "ls-files", "-s")))
    staged = _git(root, "diff", "--cached", "--name-only")
    check(f"CS-6 {label}: nada do run foi para o índice",
          not any(x in staged for x in ("plan.yaml", ".jsonl", ".review.md")), staged)
    lines = [l for l in out.splitlines() if "commit:" in l or "cepa-until:" in l]
    check(f"CS-6 {label}: a tela final diz por que não commitou ({word})",
          any(word in l for l in lines), out[-800:])
    check(f"CS-6 {label}: a tela não diz que o git recusou",
          not any("git refused" in l for l in out.splitlines()), out[-800:])
    marker = "to commit by hand: "
    cmds = [l.split(marker, 1)[1].strip() for l in out.splitlines() if marker in l]
    check(f"CS-6 {label}: a tela traz o comando para o dono",
          len(cmds) == 1 and " commit " in cmds[0], out[-800:])
    reviews = sorted((root / ".claude" / "programs" / "fila" / "until")
                     .glob("*.review.md"))
    text = reviews[0].read_text(encoding="utf-8") if reviews else ""
    check(f"CS-6 {label}: o .review.md mantém a análise e traz o motivo",
          "nada pendente" in text and word in text, text[-600:])
    check(f"CS-6 {label}: o .review.md diz que o run não commitou, não que o git recusou",
          "The run did not commit its records" in text
          and "refused by git" not in text, text[-600:])
    check(f"CS-6 {label}: o .review.md diz o que fazer antes do comando",
          "conclude or abort" in text and bool(cmds) and cmds[0] in text,
          text[-600:])
    check(f"CS-6 {label}: a tela diz o que fazer antes do comando",
          any("Conclude or abort" in l for l in lines), out[-800:])


def _cs6(label):
    with tempfile.TemporaryDirectory() as tmp, \
            tempfile.TemporaryDirectory() as tmp_ok:
        _cs6_checks(label, tmp, tmp_ok)


def test_cs6_merge_in_progress_is_left_alone():
    _cs6("merge")


def test_cs6_rebase_in_progress_is_left_alone():
    _cs6("rebase")


def test_cs6_rebase_apply_in_progress_is_left_alone():
    _cs6("rebase-apply")


def test_cs6_launch_collect_does_not_commit_mid_rebase():
    """The collect of a dead run's loose records at launch (CS-4) goes through the
    same guard: with a rebase in progress in the clone it commits nothing, leaves
    the index alone, and says so without blaming git."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        other = _other_queue(root)
        _dead_run_of(other, _dead_pid(), review=True)
        gitdir = Path(_git(root, "rev-parse", "--absolute-git-dir").strip())
        (gitdir / "rebase-merge").mkdir()
        before = _git(root, "rev-parse", "HEAD").strip()
        index = _git(root, "ls-files", "-s")
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, _calls = base.run_until(root, binv, plan, ["--for", "2h"])
        out = p.stdout + p.stderr
        check("CS-6 recolha: nenhum commit novo",
              _git(root, "rev-parse", "HEAD").strip() == before,
              _git(root, "log", "--oneline", f"{before}..HEAD"))
        check("CS-6 recolha: o índice é o de antes",
              _git(root, "ls-files", "-s") == index)
        check("CS-6 recolha: rebase-merge segue no lugar",
              (gitdir / "rebase-merge").exists())
        lines = [l for l in out.splitlines()
                 if "did not commit the loose records of dead runs (outra)" in l]
        check("CS-6 recolha: a largada diz por que não recolheu",
              len(lines) == 1 and "rebase" in lines[0]
              and "the index was not touched" in lines[0]
              and "Conclude or abort" in lines[0], out[-800:])
        check("CS-6 recolha: a largada não diz que o git recusou",
              "git refused" not in out, out[-800:])
        check("CS-6 recolha: a largada traz o comando para o dono",
              any("to commit by hand: " in l and "collect records of dead runs" in l
                  for l in out.splitlines()), out[-800:])


def test_cs6_cherry_pick_in_progress_is_left_alone():
    _cs6("cherry-pick")


def test_cs6_revert_in_progress_is_left_alone():
    _cs6("revert")


def test_cs6_detached_head_does_not_commit():
    _cs6("HEAD destacado")


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


# ── CS-7: decide, close-dead and land commit what they wrote ─────────────────

import json  # noqa: E402
import os  # noqa: E402

import yaml  # noqa: E402

import test_cepa_until_decide as dec  # noqa: E402
from test_cepa_until_run_branch import WORKS, VERIFY  # noqa: E402

CS7_BLOCKS = (
    "ident = primeiro_pendente()\n"
    "if ident == 'a1':\n"
    "    marca(ident, status='blocked', evidence='sem produção',\n"
    "          owner_question='Fecho o card?')\n"
    "elif ident:\n"
    "    marca(ident, status='done')\n")


def _git_ok(root, *args):
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
                   cwd=root, check=True, capture_output=True)


def _two_item_scenario(tmp):
    """`_scenario` with a second item, so the run ends with a1 blocked on a question
    and a2 done, and the run's own commit already made."""
    root = base.build_repo(tmp, [base.item("a1"), base.item("a2")])
    (root / ".gitignore").write_text(
        ".claude/programs/*/until/*.log\n"
        ".claude/programs/*/until/*.estado.json\n"
        ".claude/queues/*/until/*.log\n"
        ".claude/queues/*/until/*.estado.json\n", encoding="utf-8")
    _git_ok(root, "add", ".gitignore")
    _git_ok(root, "commit", "-qm", "gitignore")
    return root


def _blocked_run(tmp):
    """A finished, committed run that left a question for the owner."""
    root = _two_item_scenario(tmp)
    binv = base.fake_claude(tmp, CS7_BLOCKS)
    plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
    p, _calls = base.run_until(root, binv, plan, ["--for", "2h"])
    run_id = sorted((root / ".claude" / "programs" / "fila" / "until")
                    .glob("*.estado.json"))[-1].name.split(".")[0]
    return root, run_id, p


def _decide_cmd(root, target):
    return [sys.executable, str(base.CEPA_UNTIL), "decide", target,
            "--repo", str(root)]


def test_cs7_decide_commits_the_answer_it_wrote_to_the_queue():
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id, p = _blocked_run(tmp)
        check("CS-7 decide: o run termina e deixa a árvore limpa",
              p.returncode == 0 and _git(root, "status", "--porcelain") == "",
              p.stdout[-400:] + _git(root, "status", "--porcelain"))
        # What the owner has around: a staged file, a modified tracked file, an
        # untracked one. None of it is the run's.
        (root / "staged.txt").write_text("s\n")
        _git_ok(root, "add", "staged.txt")
        gi = root / ".gitignore"
        gi.write_text(gi.read_text() + "# dono\n")
        (root / "solto.txt").write_text("x\n")
        before = _git(root, "rev-parse", "HEAD").strip()
        rc, out = dec.on_tty(_decide_cmd(root, f"fila/{run_id}"), str(root), inputs=[
            ("[w] I write the answer", "n"), ("Anything to add", "")])
        check("CS-7 decide: a resposta foi aplicada na fila",
              "não: Fecho o card?" in (yaml.safe_load(
                  (root / ".claude/programs/fila/plan.yaml").read_text())
                  ["items"][0]["evidence"] or ""), out[-800:])
        check("CS-7 decide: sai 0", rc == 0, out[-400:])
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-7 decide: nenhum caminho da fila ou do registro fica sujo",
              ".claude/" not in st, st)
        check("CS-7 decide: um commit novo sobre a base",
              _git(root, "rev-parse", "HEAD~1").strip() == before
              and _git(root, "rev-parse", "HEAD").strip() != before)
        files = sorted(_git(root, "show", "--name-only", "--format=",
                            "HEAD").split())
        check("CS-7 decide: o commit leva a fila e nada do dono",
              files == [".claude/programs/fila/plan.yaml"], files)
        msg = _git(root, "log", "-1", "--format=%s").strip()
        check("CS-7 decide: a mensagem é `until <fila>/<run> decide: ...`",
              msg.startswith(f"until fila/{run_id} decide: "), msg)
        check("CS-7 decide: a tela diz do commit", "commit: " in out, out[-600:])
        check("CS-7 decide: o que era do dono fica como estava",
              "A  staged.txt" in st and " M .gitignore" in st
              and "?? solto.txt" in st, st)


def test_cs7_decide_on_a_whole_queue_commits_only_the_queue():
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id, _p = _blocked_run(tmp)
        before = _git(root, "rev-parse", "HEAD").strip()
        rc, out = dec.on_tty(_decide_cmd(root, "fila"), str(root), inputs=[
            ("[w] I write the answer", "n"), ("Anything to add", "")])
        check("CS-7 decide <fila>: sai 0", rc == 0, out[-400:])
        check("CS-7 decide <fila>: git status vazio",
              _git(root, "status", "--porcelain", "--untracked-files=all") == "",
              _git(root, "status", "--porcelain"))
        check("CS-7 decide <fila>: um commit novo",
              _git(root, "rev-parse", "HEAD~1").strip() == before)
        msg = _git(root, "log", "-1", "--format=%s").strip()
        check("CS-7 decide <fila>: a mensagem é `until <fila> decide: ...`",
              msg.startswith("until fila decide: "), msg)


def test_cs7_decide_listing_without_a_terminal_commits_nothing():
    """Nothing was written: a queue the owner left dirty is not swept in."""
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id, _p = _blocked_run(tmp)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        plan.write_text(plan.read_text() + "# nota do dono\n")
        before = _git(root, "rev-parse", "HEAD").strip()
        r = subprocess.run(_decide_cmd(root, f"fila/{run_id}"), cwd=root,
                           capture_output=True, text=True, timeout=60)
        check("CS-7 decide sem terminal: lista e sai 0", r.returncode == 0,
              r.stdout + r.stderr)
        check("CS-7 decide sem terminal: nenhum commit",
              _git(root, "rev-parse", "HEAD").strip() == before)


def test_cs7_decide_mid_merge_does_not_commit_and_says_why():
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id, _p = _blocked_run(tmp)
        (root / ".git" / "MERGE_HEAD").write_text(
            _git(root, "rev-parse", "HEAD"))
        before = _git(root, "rev-parse", "HEAD").strip()
        rc, out = dec.on_tty(_decide_cmd(root, f"fila/{run_id}"), str(root), inputs=[
            ("[w] I write the answer", "n"), ("Anything to add", "")])
        check("CS-7 decide merge: o código de saída não muda (0)", rc == 0,
              out[-400:])
        check("CS-7 decide merge: nenhum commit",
              _git(root, "rev-parse", "HEAD").strip() == before)
        check("CS-7 decide merge: a fila segue com a resposta, sem commit",
              "plan.yaml" in _git(root, "status", "--porcelain"))
        check("CS-7 decide merge: a tela diz o motivo",
              "a merge is in progress" in out and "commit: not made" in out,
              out[-800:])
        check("CS-7 decide merge: ...e o comando exato, sem --no-verify",
              "to commit by hand: git -C" in out and " commit -m " in out
              and "--no-verify" not in out, out[-800:])
        check("CS-7 decide merge: o merge segue intacto",
              (root / ".git" / "MERGE_HEAD").exists())


def _night_that_died(tmp, queue_dirty=True):
    """A real run (a1 delivered, build green) rewound to where a dead supervisor
    leaves it: state `rodando`, the record without `run_end`, and the queue with
    the mark of the item in flight, all of it modified in the clone."""
    root = _scenario(tmp)
    binv = base.fake_claude(tmp, WORKS)
    plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
    base.run_until(root, binv, plan, ["--for", "2h", "--verify", VERIFY])
    d = root / ".claude" / "programs" / "fila" / "until"
    jsonl = sorted(d.glob("*.jsonl"))[-1]
    events = [json.loads(l) for l in jsonl.read_text().splitlines()]
    cut = next(i for i, e in enumerate(events) if e["evento"] == "item_start")
    events = events[:cut + 1]
    jsonl.write_text("".join(json.dumps(e) + "\n" for e in events))
    import socket
    spath = sorted(d.glob("*.estado.json"))[-1]
    st = json.loads(spath.read_text())
    st.update(estado="rodando", pid=_dead_pid(), host=socket.gethostname())
    for k in ("acoes", "fica_com_voce", "itens", "motivo_fim"):
        st.pop(k, None)
    spath.write_text(json.dumps(st))
    if queue_dirty:
        q = yaml.safe_load(plan.read_text())
        q["items"][0]["evidence"] = "marca do run que morreu"
        plan.write_text(yaml.safe_dump(q, allow_unicode=True))
    return root, events[0]["branch"].split("/", 1)[1]


def _close_dead(root, tmp, run_id, extra_env=None):
    env = dict(os.environ, CEPA_WORKTREE_HOME=str(root.parent / "worktrees"))
    env.update(extra_env or {})
    return subprocess.run([sys.executable, str(base.CEPA_UNTIL), "close-dead",
                           f"fila/{run_id}", "--repo", str(root), "--yes"],
                          capture_output=True, text=True, cwd=str(root), env=env,
                          timeout=120)


def test_cs7_close_dead_commits_the_record_and_the_queue():
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id = _night_that_died(tmp)
        (root / "solto.txt").write_text("x\n")
        before = _git(root, "rev-parse", "HEAD").strip()
        r = _close_dead(root, tmp, run_id)
        check("CS-7 close-dead: sai 0 com o build verde", r.returncode == 0,
              r.stdout + r.stderr)
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-7 close-dead: nenhum caminho da fila ou do registro sujo",
              ".claude/" not in st, st)
        check("CS-7 close-dead: um commit novo sobre a base",
              _git(root, "rev-parse", "HEAD~1").strip() == before)
        files = sorted(_git(root, "show", "--name-only", "--format=",
                            "HEAD").split())
        rel = ".claude/programs/fila/"
        check("CS-7 close-dead: o commit leva o .jsonl e a fila, e só eles",
              files == sorted([f"{rel}plan.yaml", f"{rel}until/{run_id}.jsonl"]),
              files)
        msg = _git(root, "log", "-1", "--format=%s").strip()
        check("CS-7 close-dead: a mensagem é `until <fila>/<run> close-dead: ...`",
              msg.startswith(f"until fila/{run_id} close-dead: "), msg)
        check("CS-7 close-dead: o arquivo do dono fica fora", "?? solto.txt" in st,
              st)
        ev = [json.loads(l) for l in _git(
            root, "show", f"HEAD:{rel}until/{run_id}.jsonl").splitlines()]
        check("CS-7 close-dead: o commit já traz o run_end",
              ev[-1]["evento"] == "run_end", ev[-1])


def test_cs7_close_dead_with_a_refusing_hook_warns_and_keeps_the_exit_code():
    with tempfile.TemporaryDirectory() as tmp:
        with tempfile.TemporaryDirectory() as tmp_ok:
            root_ok, run_ok = _night_that_died(tmp_ok)
            r_ok = _close_dead(root_ok, tmp_ok, run_ok)
        root, run_id = _night_that_died(tmp)
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'lint: 3 erros' >&2\nexit 1\n")
        hook.chmod(0o755)
        spy_dir, log = _git_spy(tmp)
        before = _git(root, "rev-parse", "HEAD").strip()
        r = _close_dead(root, tmp, run_id,
                        {"PATH": f"{spy_dir}:{os.environ['PATH']}"})
        out = r.stdout + r.stderr
        check("CS-7 close-dead hook: o código de saída é o do run sem hook",
              r.returncode == r_ok.returncode == 0,
              f"{r.returncode} vs {r_ok.returncode}")
        check("CS-7 close-dead hook: nenhum commit novo",
              _git(root, "rev-parse", "HEAD").strip() == before)
        check("CS-7 close-dead hook: o registro fica sem commit",
              ".jsonl" in _git(root, "status", "--porcelain"))
        calls = log.read_text() if log.exists() else ""
        check("CS-7 close-dead hook: tentou git commit, sem --no-verify",
              "commit" in calls and "--no-verify" not in calls, calls[-300:])
        check("CS-7 close-dead hook: a tela traz o motivo",
              "git refused the commit" in out and "lint: 3 erros" in out,
              out[-800:])
        cmds = [l.split("to commit by hand: ", 1)[1].strip()
                for l in out.splitlines() if "to commit by hand: " in l]
        check("CS-7 close-dead hook: ...e o comando exato",
              len(cmds) == 1 and " commit " in cmds[0]
              and "--no-verify" not in cmds[0], out[-800:])
        if cmds:
            hook.unlink()
            c = subprocess.run(["sh", "-c", cmds[0]], cwd=tmp,
                               capture_output=True, text=True)
            check("CS-7 close-dead hook: o comando roda como impresso e limpa",
                  c.returncode == 0 and ".claude/" not in _git(
                      root, "status", "--porcelain"), c.stdout + c.stderr)


def _land_ready(tmp, layout="programs"):
    """A finished, committed run (a1 delivered) whose queue the owner's clone holds
    modified, the state a refused or older commit leaves."""
    root = _scenario(tmp)
    if layout == "queues":
        (root / ".claude" / "queues").mkdir()
        _git_ok(root, "mv", ".claude/programs/fila", ".claude/queues/fila")
        _git_ok(root, "mv", ".claude/queues/fila/plan.yaml",
                ".claude/queues/fila/queue.yaml")
        _git_ok(root, "commit", "-qm", "new layout")
    binv = base.fake_claude(tmp, WORKS)
    qfile = root / ".claude" / layout / "fila" / (
        "queue.yaml" if layout == "queues" else "plan.yaml")
    p, _c = base.run_until(root, binv, qfile, ["--for", "2h", "--verify", VERIFY])
    d = qfile.parent / "until"
    run_id = sorted(d.glob("*.estado.json"))[-1].name.split(".")[0]
    q = yaml.safe_load(qfile.read_text())
    q["items"][0]["evidence"] = "marca que ficou na fila"
    qfile.write_text(yaml.safe_dump(q, allow_unicode=True))
    return root, run_id, qfile


def _land_yes(root, run_id):
    env = dict(os.environ, CEPA_WORKTREE_HOME=str(root.parent / "worktrees"))
    return subprocess.run([sys.executable, str(base.CEPA_UNTIL), "land",
                           f"fila/{run_id}", "--repo", str(root), "--yes"],
                          capture_output=True, text=True, cwd=str(root), env=env,
                          timeout=180)


def _cs7_land_checks(layout):
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id, qfile = _land_ready(tmp, layout)
        rel = str(qfile.relative_to(root))
        r = _land_yes(root, run_id)
        out = r.stdout + r.stderr
        check(f"CS-7 land ({layout}): aterrissa com saída 0", r.returncode == 0,
              out[-800:])
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check(f"CS-7 land ({layout}): nenhum caminho de .claude/ sujo", ".claude/" not in st,
              st)
        check(f"CS-7 land ({layout}): a velha linha 'commit whenever you want' sumiu",
              "commit whenever you want" not in out, out[-800:])
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check(f"CS-7 land ({layout}): o commit do topo leva a fila",
              files == [rel], files)
        msg = _git(root, "log", "-1", "--format=%s").strip()
        check(f"CS-7 land ({layout}): a mensagem é `until <fila>/<run> land: ...`",
              msg.startswith(f"until fila/{run_id} land: "), msg)
        check(f"CS-7 land ({layout}): o merge do run está embaixo do commit",
              len(_git(root, "rev-list", "--parents", "-1",
                       "HEAD~1").split()) == 3, _git(root, "log", "-3",
                                                     "--format=%s"))
        check(f"CS-7 land ({layout}): a tela diz do commit", "commit: " in out,
              out[-600:])


def test_cs7_land_commits_the_queue_marks_it_leaves_behind():
    _cs7_land_checks("programs")


def test_cs7_land_commits_in_the_new_queue_layout_too():
    _cs7_land_checks("queues")


def _proposed_waiver(root, queue="fila", item="a1"):
    """A waiver the agent proposed for `item` (`status: proposta`), committed, so the
    owner's "sim" in `decide` rewrites a tracked file."""
    sys.path.insert(0, str(Path(base.__file__).resolve().parent.parent
                           / "board-flow" / "bin"))
    import waivers
    before = os.environ.get("CEPA_UNTIL_RUN")
    os.environ["CEPA_UNTIL_RUN"] = "1"
    try:
        path = Path(waivers.write(str(root), "teste-cego", "PlugSignAdapter",
                                  "o fornecedor não é alcançável", "alegomes",
                                  "quando o adapter mudar", queue=queue, item=item))
    finally:
        if before is None:
            os.environ.pop("CEPA_UNTIL_RUN")
        else:
            os.environ["CEPA_UNTIL_RUN"] = before
    _git_ok(root, "add", "-f", "--", str(path))
    _git_ok(root, "commit", "-qm", "proposed waiver")
    return path


def test_cs7_decide_commits_the_waiver_the_answer_converted():
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id, _p = _blocked_run(tmp)
        waiver = _proposed_waiver(root)
        rel = str(waiver.relative_to(root))
        (root / "outro.txt").write_text("do dono\n")
        _git_ok(root, "add", "outro.txt")
        before = _git(root, "rev-parse", "HEAD").strip()
        rc, out = dec.on_tty(_decide_cmd(root, f"fila/{run_id}"), str(root), inputs=[
            ("[w] I write the answer", "s"), ("Anything to add", "")],
            env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                     GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
        check("CS-7 decide dispensa: a proposta virou dispensa",
              "status" not in yaml.safe_load(waiver.read_text()), waiver.read_text())
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-7 decide dispensa: so o arquivo do dono fica fora do commit",
              st.strip() == "A  outro.txt", st)
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("CS-7 decide dispensa: o commit leva a fila e a dispensa",
              rel in files and ".claude/programs/fila/plan.yaml" in files
              and "outro.txt" not in files
              and _git(root, "rev-parse", "HEAD~1").strip() == before, files)
        # CS-7 follow-up 3: `answer` runs with --no-commit under `decide`, and its
        # "queue written without a commit" line would contradict the commit line.
        check("CS-7 decide: a tela nao diz 'fila gravada sem commit'",
              "sem commit" not in out and "Falta commitar" not in out
              and "commita a fila" not in out, out[-900:])
        check("CS-7 decide dispensa: a tela diz do commit", "commit: " in out,
              out[-600:])


def test_cs7_decide_that_lands_commits_the_run_paths_already_dirty():
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id, qfile = _land_ready(tmp)
        rel = str(qfile.relative_to(root))
        before = _git(root, "rev-parse", "HEAD").strip()
        env = dict(os.environ, CEPA_WORKTREE_HOME=str(root.parent / "worktrees"))
        rc, out = dec.on_tty(_decide_cmd(root, f"fila/{run_id}"), str(root),
                             inputs=[("Land now?", "s")], env=env, timeout=180)
        check("CS-7 decide aterrissa: sai 0", rc == 0, out[-600:])
        check("CS-7 decide aterrissa: o run foi aterrissado",
              _git(root, "rev-list", "--count", f"{before}..HEAD").strip() != "0",
              out[-600:])
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-7 decide aterrissa: a fila ja suja antes sai commitada",
              ".claude/" not in st, st)
        check("CS-7 decide aterrissa: o commit do topo leva a fila",
              _git(root, "show", "--name-only", "--format=", "HEAD").split() == [rel],
              _git(root, "log", "-3", "--format=%s"))
        check("CS-7 decide aterrissa: a tela diz do commit", "commit: " in out,
              out[-600:])


def test_cs7_decide_killed_by_sigterm_or_sighup_after_an_answer_commits_it():
    import pty
    import select
    import signal
    import time
    for sig in (signal.SIGTERM, signal.SIGHUP):
        label = f"CS-7 decide {sig.name}"
        with tempfile.TemporaryDirectory() as tmp:
            root = _two_item_scenario(tmp)
            binv = base.fake_claude(tmp, (
                "ident = primeiro_pendente()\n"
                "if ident:\n"
                "    marca(ident, status='blocked', evidence='sem producao',\n"
                "          owner_question='Fecho o card ' + ident + '?')\n"))
            plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
            base.run_until(root, binv, plan, ["--for", "2h"])
            run_id = sorted((root / ".claude" / "programs" / "fila" / "until")
                            .glob("*.estado.json"))[-1].name.split(".")[0]
            before = _git(root, "rev-parse", "HEAD").strip()
            cmd = _decide_cmd(root, f"fila/{run_id}")
            env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
            pid, fd = pty.fork()
            if pid == 0:
                os.chdir(str(root))
                os.execve(cmd[0], cmd, env)
            seen, step, text, end = 0, 0, "", time.time() + 120
            status = None
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.5)
                if r:
                    try:
                        data = os.read(fd, 4096)
                    except OSError:
                        break
                    if not data:
                        break
                    text += data.decode(errors="replace")
                if step == 0 and "[w] I write the answer" in text:
                    text = text.replace("[w] I write the answer", "<q1>", 1)
                    os.write(fd, b"n\n")
                    step = 1
                elif step == 1 and "Anything to add" in text:
                    text = text.replace("Anything to add", "<add>", 1)
                    os.write(fd, b"\n")
                    step = 2
                elif step == 2 and "[w] I write the answer" in text:
                    os.kill(pid, sig)   # second question on screen: first is answered
                    step, sent_at = 3, time.time()
                    end = min(end, time.time() + 30)
                elif step == 3 and time.time() - sent_at > 2:
                    # The signal can land in the microseconds between the legend
                    # and the `select` of the prompt: Python then runs the handler
                    # only when the read returns, which nobody makes happen here
                    # (1 run in 8, 2026-11-15). Sent again while `decide` sits in
                    # that read, it interrupts it and the handler runs once.
                    os.kill(pid, sig)
                    sent_at = time.time()
            else:
                os.kill(pid, signal.SIGKILL)
            _, wst = os.waitpid(pid, 0)
            code = os.waitstatus_to_exitcode(wst)
            check(f"{label}: chegou a segunda pergunta e o sinal foi enviado",
                  step == 3, text[-500:])
            check(f"{label}: sai com 128 + sinal", code == 128 + sig, str(code))
            st = _git(root, "status", "--porcelain", "--untracked-files=all")
            check(f"{label}: a fila nao fica suja", ".claude/" not in st, st)
            check(f"{label}: um commit novo com a fila",
                  _git(root, "rev-parse", "HEAD~1").strip() == before
                  and ".claude/programs/fila/plan.yaml" in _git(
                      root, "show", "--name-only", "--format=", "HEAD").split(),
                  _git(root, "log", "-2", "--format=%s"))


def test_cs7_decide_that_lands_makes_exactly_one_records_commit():
    """`decide` that lands the run commits the records ONCE, at its end, with the
    `decide` message. The landing inside it must not commit on its own (a `land`
    commit before the `decide` one). The proof of 2026-11-15 made `decide` call the
    landing that commits and every other test stayed green: the final state is the
    same, there is one commit more."""
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id, _qfile = _land_ready(tmp)
        before = _git(root, "rev-parse", "HEAD").strip()
        env = dict(os.environ, CEPA_WORKTREE_HOME=str(root.parent / "worktrees"))
        rc, out = dec.on_tty(_decide_cmd(root, f"fila/{run_id}"), str(root),
                             inputs=[("Land now?", "s")], env=env, timeout=180)
        check("CS-7 decide 1 commit: sai 0", rc == 0, out[-600:])
        subjects = _git(root, "log", "--format=%s", f"{before}..HEAD").splitlines()
        mine = [x for x in subjects if x.startswith(f"until fila/{run_id} ")]
        check("CS-7 decide 1 commit: exatamente um commit de registro do run",
              len(mine) == 1, subjects)
        check("CS-7 decide 1 commit: ele é o do decide, não o do land",
              len(mine) == 1 and mine[0].startswith(f"until fila/{run_id} decide: "),
              subjects)
        check("CS-7 decide 1 commit: ele é o do topo",
              _git(root, "log", "-1", "--format=%s").strip() in mine, subjects)


def test_cs7_close_dead_leaves_the_review_in_the_commit():
    """A run's `.review.md` that is on disk when `close-dead` commits goes in the
    commit with the `.jsonl` and the queue: no path of the run is left behind."""
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id = _night_that_died(tmp)
        rel = ".claude/programs/fila/"
        review = root / rel / "until" / f"{run_id}.review.md"
        review.write_text("# revisão do run\n\nnada pendente\n", encoding="utf-8")
        before = _git(root, "rev-parse", "HEAD").strip()
        r = _close_dead(root, tmp, run_id)
        check("CS-7 close-dead review: sai 0", r.returncode == 0,
              r.stdout + r.stderr)
        files = sorted(_git(root, "show", "--name-only", "--format=",
                            "HEAD").split())
        check("CS-7 close-dead review: o commit leva o .review.md junto",
              files == sorted([f"{rel}plan.yaml", f"{rel}until/{run_id}.jsonl",
                               f"{rel}until/{run_id}.review.md"])
              and _git(root, "rev-parse", "HEAD~1").strip() == before, files)
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-7 close-dead review: o .review.md não fica solto",
              "review.md" not in st and ".claude/" not in st, st)


def test_cs7_close_dead_with_a_red_build_exits_1_and_commits_the_record():
    """Red build: the exit code stays 1 and the state does not change, but the
    `.jsonl` now holds a `verify` event and the queue marks are still the dead
    run's: both are committed (help text and docstring say so)."""
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id = _night_that_died(tmp)
        rel = ".claude/programs/fila/"
        state = root / rel / "until" / f"{run_id}.estado.json"
        st = json.loads(state.read_text())
        st["verify"] = "false"
        state.write_text(json.dumps(st))
        before = _git(root, "rev-parse", "HEAD").strip()
        r = _close_dead(root, tmp, run_id)
        out = r.stdout + r.stderr
        check("CS-7 close-dead red: sai 1, como antes", r.returncode == 1, out[-800:])
        check("CS-7 close-dead red: a tela diz que o build ficou vermelho",
              "red (" in out, out[-800:])
        status = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-7 close-dead red: nada do run fica sujo", ".claude/" not in status,
              status)
        check("CS-7 close-dead red: um commit novo sobre a base",
              _git(root, "rev-parse", "HEAD~1").strip() == before)
        files = sorted(_git(root, "show", "--name-only", "--format=",
                            "HEAD").split())
        check("CS-7 close-dead red: o commit leva o .jsonl e a fila",
              files == sorted([f"{rel}plan.yaml", f"{rel}until/{run_id}.jsonl"]),
              files)
        ev = [json.loads(l) for l in _git(
            root, "show", f"HEAD:{rel}until/{run_id}.jsonl").splitlines()]
        check("CS-7 close-dead red: o registro commitado traz o evento verify vermelho",
              ev[-1]["evento"] == "verify" and ev[-1]["verde"] is False, ev[-1])
        check("CS-7 close-dead red: o estado não mudou (segue rodando)",
              json.loads(state.read_text()).get("estado") == "rodando")


def test_cs7_close_dead_signals_during_the_commit_do_not_cut_it():
    """The owner presses Ctrl+C (and a SIGTERM comes too) while `close-dead`'s
    `git commit` runs (a slow pre-commit hook holds it, and the test signals once
    the hook has started). Without ignoring SIGTERM/SIGINT around the commit the
    process dies (or git is killed halfway and `.git/index.lock` can stay), and
    the records stay loose. The proof of 2026-11-15 removed the ignore of the
    subcommands' commit and every other test stayed green."""
    import signal
    import time
    with tempfile.TemporaryDirectory() as tmp:
        root, run_id = _night_that_died(tmp)
        started = Path(tmp) / "hook.started"
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_text(f"#!/bin/sh\ntouch '{started}'\nsleep 3\nexit 0\n",
                        encoding="utf-8")
        hook.chmod(0o755)
        before = _git(root, "rev-parse", "HEAD").strip()
        env = dict(os.environ, CEPA_WORKTREE_HOME=str(root.parent / "worktrees"))
        proc = subprocess.Popen(
            [sys.executable, str(base.CEPA_UNTIL), "close-dead",
             f"fila/{run_id}", "--repo", str(root), "--yes"], env=env,
            cwd=str(root), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True)
        try:
            end = time.time() + 60
            while not started.exists() and time.time() < end and proc.poll() is None:
                time.sleep(0.05)
            check("CS-7 close-dead sinal: o commit começou (hook rodando)",
                  started.exists())
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                proc.send_signal(signal.SIGINT)
            try:
                output, _ = proc.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                output, _ = proc.communicate()
        finally:
            if proc.poll() is None:
                proc.kill()
        check("CS-7 close-dead sinal: o processo sai 0, como sem sinal",
              proc.returncode == 0, f"{proc.returncode}: {output[-600:]}")
        check("CS-7 close-dead sinal: o commit terminou mesmo assim",
              _git(root, "rev-parse", "HEAD~1").strip() == before,
              _git(root, "log", "--oneline", "-3"))
        check("CS-7 close-dead sinal: a tela diz do commit", "commit: " in output,
              output[-600:])
        check("CS-7 close-dead sinal: não sobrou .git/index.lock",
              not (root / ".git" / "index.lock").exists())
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-7 close-dead sinal: nada do run solto", ".claude/" not in st, st)


def test_cs7_decide_second_signal_while_ending_does_not_cut_the_commit():
    """The first SIGTERM ends the questions; a second one arrives while `decide` is
    still inside the `finally` that commits (here: reading a waiver file that is a
    FIFO, held open by the test until the signal has been sent: the reader being
    blocked on it is the observable event that `decide` is in that window). The
    second signal must not cut the commit. The proof of 2026-11-15 left the live
    handler there and every other test stayed green."""
    import pty
    import select
    import signal
    import threading
    import time
    with tempfile.TemporaryDirectory() as tmp:
        root = _two_item_scenario(tmp)
        binv = base.fake_claude(tmp, (
            "ident = primeiro_pendente()\n"
            "if ident:\n"
            "    marca(ident, status='blocked', evidence='sem producao',\n"
            "          owner_question='Fecho o card ' + ident + '?')\n"))
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        base.run_until(root, binv, plan, ["--for", "2h"])
        run_id = sorted((root / ".claude" / "programs" / "fila" / "until")
                        .glob("*.estado.json"))[-1].name.split(".")[0]
        fifo = root / ".claude" / "waivers" / "gate.yaml"
        fifo.parent.mkdir(parents=True, exist_ok=True)
        os.mkfifo(fifo)
        before = _git(root, "rev-parse", "HEAD").strip()
        cmd = _decide_cmd(root, f"fila/{run_id}")
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                   GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(str(root))
            os.execve(cmd[0], cmd, env)
        gate, stop, second = threading.Event(), threading.Event(), threading.Event()

        def feeder():
            # Every reader of the FIFO gets an empty file. The one that opens it
            # after the gate (the first signal already sent) is `decide` ending.
            while not stop.is_set():
                wfd = os.open(fifo, os.O_WRONLY)
                try:
                    if gate.is_set() and not stop.is_set() and not second.is_set():
                        os.kill(pid, signal.SIGTERM)
                        second.set()
                        time.sleep(0.5)
                finally:
                    os.close(wfd)

        thread = threading.Thread(target=feeder, daemon=True)
        thread.start()
        step, text, end, status = 0, "", time.time() + 120, None
        try:
            while time.time() < end:
                r, _, _ = select.select([fd], [], [], 0.5)
                if r:
                    try:
                        data = os.read(fd, 4096)
                    except OSError:
                        break
                    if not data:
                        break
                    text += data.decode(errors="replace")
                if step == 0 and "[w] I write the answer" in text:
                    text = text.replace("[w] I write the answer", "<q1>", 1)
                    os.write(fd, b"n\n")
                    step = 1
                elif step == 1 and "Anything to add" in text:
                    text = text.replace("Anything to add", "<add>", 1)
                    os.write(fd, b"\n")
                    step = 2
                elif step == 2 and "[w] I write the answer" in text:
                    gate.set()
                    os.kill(pid, signal.SIGTERM)
                    step, sent_at = 3, time.time()
                    end = min(end, time.time() + 30)
                elif (step == 3 and not second.is_set()
                      and time.time() - sent_at > 2):
                    # Same lost-signal window as in the test above: the FIRST
                    # signal is sent again while `decide` has not started to end
                    # (it has not opened the FIFO). It is not the second signal
                    # of this test, which only the feeder sends.
                    os.kill(pid, signal.SIGTERM)
                    sent_at = time.time()
            else:
                os.kill(pid, signal.SIGKILL)
            _, wst = os.waitpid(pid, 0)
            code = os.waitstatus_to_exitcode(wst)
        finally:
            stop.set()
            try:
                os.close(os.open(fifo, os.O_RDONLY | os.O_NONBLOCK))
            except OSError:
                pass
            thread.join(timeout=10)
        check("CS-7 decide 2o sinal: o primeiro sinal foi enviado", step == 3,
              text[-500:])
        check("CS-7 decide 2o sinal: o decide estava no fim quando o 2o chegou",
              second.is_set(), text[-500:])
        check("CS-7 decide 2o sinal: sai com 143 (o 1o sinal)", code == 143,
              str(code))
        check("CS-7 decide 2o sinal: o commit terminou mesmo assim",
              _git(root, "rev-parse", "HEAD~1").strip() == before
              and ".claude/programs/fila/plan.yaml" in _git(
                  root, "show", "--name-only", "--format=", "HEAD").split(),
              _git(root, "log", "-2", "--format=%s"))
        check("CS-7 decide 2o sinal: não sobrou .git/index.lock",
              not (root / ".git" / "index.lock").exists())
        st = _git(root, "status", "--porcelain", "--untracked-files=all")
        check("CS-7 decide 2o sinal: a fila não fica suja", ".claude/programs" not in st,
              st)


# ── CS-8: the run does not push ─────────────────────────────────────────────

def test_cs8_run_does_not_push():
    """CS-8: with a bare remote that the clone's branch tracks (so a plain
    `git push` would succeed), the run ends with its new commit in the clone and
    every ref of the remote exactly as before the launch, the run's own
    `until/<run>` branch included. Only `land`, fired by the owner, publishes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _scenario(tmp)
        remote = Path(tmp) / "remoto.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root,
                       check=True)
        subprocess.run(["git", "push", "-q", "-u", "origin", branch], cwd=root,
                       check=True, capture_output=True)
        refs_before = _git(remote, "for-each-ref", "--format=%(refname) %(objectname)")
        remote_head_before = _git(remote, "rev-parse", branch).strip()
        before = _git(root, "rev-parse", "HEAD").strip()
        binv = base.fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, _calls = base.run_until(root, binv, plan, ["--for", "2h"])
        check("CS-8: o run termina", p.returncode == 0,
              f"saiu {p.returncode}: {p.stderr[-400:]}")
        head = _git(root, "rev-parse", "HEAD").strip()
        check("CS-8: o clone tem o commit novo do run",
              head != before and _git(root, "rev-parse", "HEAD~1").strip() == before,
              _git(root, "log", "-2", "--format=%h %s"))
        check("CS-8: o HEAD do remoto é o mesmo de antes da largada",
              _git(remote, "rev-parse", branch).strip() == remote_head_before,
              _git(remote, "log", "-2", "--format=%h %s", branch))
        refs_after = _git(remote, "for-each-ref", "--format=%(refname) %(objectname)")
        check("CS-8: nenhuma ref do remoto mudou (nem a branch do run)",
              refs_after == refs_before, f"{refs_before!r} -> {refs_after!r}")
        ahead = _git(root, "rev-list", "--count", f"origin/{branch}..HEAD").strip()
        check("CS-8: o clone fica à frente do remoto pelo commit do run",
              ahead == "1", ahead)


def main():
    print("cepa-until — árvore limpa no fim do run\n")
    # Names on the command line run only those tests (the proof perturbs one
    # behavior and re-runs the test that covers it, without the whole file).
    wanted = set(sys.argv[1:])
    for given_name, fn in sorted(globals().items()):
        if (given_name.startswith("test_") and callable(fn)
                and (not wanted or given_name in wanted)):
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
