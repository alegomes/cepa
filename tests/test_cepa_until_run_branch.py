#!/usr/bin/env python3
"""cepa-until — the night branch and the supervisor's full build.

The 2026-09-23 run on WEGO delivered 5 cards in 25 rounds: each subprocess
opened its own worktree from `origin/main`, nothing merged, and the following cards
jammed because the predecessor only existed on a loose branch. 2308
even closed `done` with the full build run before the last refactor.

The cases below pin the fix:
  - the supervisor creates `until/<run>` in a worktree and runs each subprocess in it;
  - the main clone does not leave the branch it was on;
  - the 2nd card sees the 1st's commit;
  - after each `done` the supervisor runs the full build; red takes the item's
    commits off the night branch (without losing them) and marks the item
    `blocked`;
  - `done` without a commit on the night branch is pointed out in the record;
  - a repo without a known build does not start without `--verify` or `--sem-verify`;
  - the summary separates delivered from stuck;
  - the end analysis calls `/common:until-review` and writes `<run>.review.md`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    FAILURES, check, fake_claude, item, ledger_of, build_repo, run_until)


# A fake `claude` that works like drain-plan with `--na-branch`: commits
# in the directory it woke up in. Records the content it saw of `a1.txt` so the
# test knows whether the 2nd card saw the 1st.
WORKS = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "viu = os.path.exists('a1.txt')\n"
    "open(ident + '.txt', 'w').write('feito')\n"
    "if ident in os.environ.get('FAKE_QUEBRA', '').split(','):\n"
    "    open('quebra.txt', 'w').write('x')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', ident], check=True)\n"
    "with open(os.environ['FAKE_CHAMADAS'] + '.cwd', 'a') as f:\n"
    "    f.write(json.dumps({'id': ident, 'cwd': os.getcwd(), 'viu_a1': viu})"
    " + '\\n')\n"
    "marca(ident, status='done', evidence='ok')\n")

# Fake full build: red when the item left `quebra.txt`.
VERIFY = "test ! -f quebra.txt"


def cwds(root):
    f = Path(root).parent / "chamadas.jsonl.cwd"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def plan_of(root):
    return root / ".claude" / "programs" / "fila" / "plan.yaml"


def status(root, ident):
    for it in yaml.safe_load(plan_of(root).read_text())["items"]:
        if it["id"] == ident:
            return it
    return None


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True).stdout.strip()


def test_subprocess_runs_on_the_night_branch_and_the_clone_stays_put():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        branch_before = git(root, "rev-parse", "--abbrev-ref", "HEAD")
        binv = fake_claude(tmp, WORKS)
        p, calls = run_until(root, binv, plan_of(root),
                           ["--for", "2h", "--verify", VERIFY])
        start = [e for e in ledger_of(root) if e["evento"] == "run_start"][0]
        branch = start.get("branch") or ""
        check("a largada cria uma branch until/<run>",
              branch.startswith("until/"), str(start))
        seen_ones = cwds(root)
        check("cada subprocesso acorda na worktree da noite",
              len(seen_ones) == 2 and all(Path(v["cwd"]).resolve()
                                       == Path(start["arvore"]).resolve()
                                       for v in seen_ones), str(seen_ones))
        check("...que fica fora do clone",
              not Path(start["arvore"]).resolve().is_relative_to(root.resolve()),
              start["arvore"])
        check("o pedido ao claude leva --na-branch",
              calls and all(f"--na-branch {branch}" in c[1] for c in calls),
              str(calls))
        check("o 2º card enxerga o commit do 1º",
              len(seen_ones) == 2 and seen_ones[1]["viu_a1"], str(seen_ones))
        check("o clone principal não sai da branch em que estava",
              git(root, "rev-parse", "--abbrev-ref", "HEAD") == branch_before)
        check("a branch da noite tem os 2 commits",
              git(root, "rev-list", "--count", f"{start['base']}..{branch}")
              == "2", p.stdout[-600:])
        check("o resumo diz como aterrissar",
              f"cepa-until aterrissar fila/{branch.split('/', 1)[1]}"
              in p.stdout, p.stdout[-600:])


def test_red_build_takes_the_item_off_the_branch_without_losing_the_commits():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_QUEBRA": "a2"})
        ev = ledger_of(root)
        start = [e for e in ev if e["evento"] == "run_start"][0]
        branch = start["branch"]
        check("o item com build vermelho vira blocked",
              status(root, "a2")["status"] == "blocked", str(status(root, "a2")))
        check("...e a evidência diz onde estão os commits",
              "vermelho-a2" in (status(root, "a2").get("evidence") or ""),
              str(status(root, "a2")))
        side_branch = f"{branch}-vermelho-a2"
        check("os commits do item ficam na branch lateral",
              git(root, "log", "-1", "--format=%s", side_branch) == "a2")
        night_log = git(root, "log", "--format=%s", branch).splitlines()
        check("a branch da noite não tem o commit vermelho",
              "a2" not in night_log and "a1" in night_log and "a3" in night_log,
              str(night_log))
        seen_ones = {v["id"]: v for v in cwds(root)}
        check("o card seguinte começa sem o código vermelho",
              "a3" in seen_ones, str(seen_ones))
        end = [e for e in ev if e["evento"] == "run_end"][0]
        # Revision 3: a2 goes back to `pending` on the 1st red return and only becomes
        # `blocked` on the 2nd, so it takes two reds for one stuck item.
        check("o registro conta entregues, travados e vermelhos",
              (end.get("entregues"), end.get("travados"),
               end.get("verify_vermelho")) == (2, 1, 2), str(end))
        check("o resumo separa entregues de travados",
              "2 delivered · 1 stuck" in p.stdout, p.stdout[-800:])


def test_done_without_commit_on_the_night_branch_is_pointed_out():
    """The 23/09 case seen from the inside: the card closes `done`, but the work
    went to another branch. The supervisor has no way to fetch it; it has a way to say so."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY])
        ev = ledger_of(root)
        check("o registro marca done_sem_commit",
              any(e["evento"] == "done_sem_commit" and e["id"] == "a1"
                  for e in ev), str(ev))
        check("...e o resumo aponta", "with no commit on the run branch" in p.stdout,
              p.stdout[-600:])
        check("sem nenhum commit, a branch da noite some",
              "removed `" in p.stdout
              and not git(root, "branch", "--list", "until/*"), p.stdout[-400:])


def test_uncommitted_leftover_does_not_pass_to_the_next_item():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = ("ident = primeiro_pendente()\n"
                 "suja = os.path.exists('sobra.txt')\n"
                 "with open(os.environ['FAKE_CHAMADAS'] + '.cwd', 'a') as f:\n"
                 "    f.write(json.dumps({'id': ident, 'cwd': os.getcwd(),"
                 " 'viu_a1': suja}) + '\\n')\n"
                 "open('sobra.txt', 'w').write('x')\n"
                 "marca(ident, status='blocked', evidence='travou')\n")
        binv = fake_claude(tmp, body)
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        seen_ones = cwds(root)
        check("o 2º item não acorda com a sobra do 1º",
              len(seen_ones) == 2 and not seen_ones[1]["viu_a1"], str(seen_ones))
        ev = ledger_of(root)
        saved = [e for e in ev if e["evento"] == "sobra_guardada"]
        check("a sobra fica num stash registrado",
              len(saved) == 2 and all(e.get("stash") for e in saved),
              str(saved))
        for e in saved:
            subprocess.run(["git", "stash", "drop", e["stash"]], cwd=root,
                           capture_output=True)


def test_repo_without_known_build_does_not_start_without_saying_which():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WORKS)
        env = dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}")
        p = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "common"
                                 / "bin" / "cepa-until"),
             "fila", "--repo", str(root), "--for", "2h", "--no-analysis"],
            capture_output=True, text=True, timeout=60,
            env={**env, "FAKE_PLANO": str(plan_of(root)),
                 "FAKE_CHAMADAS": str(Path(tmp) / "chamadas.jsonl"),
                 "CEPA_WORKTREE_HOME": str(Path(tmp) / "worktrees")})
        check("sem mvnw/gradlew e sem flag, recusa", p.returncode == 2,
              f"saiu {p.returncode}: {p.stderr[-300:]}")
        check("...e diz as duas saídas",
              "--verify" in p.stderr and "--no-verify" in p.stderr, p.stderr)
        check("...e nomeia a suíte que teria bastado",
              "tests/run-all.sh" in p.stderr, p.stderr)
        check("...sem ter criado branch", not git(root, "branch", "--list",
                                                  "until/*"))


def test_mvnw_at_root_becomes_the_default_build():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        (root / "mvnw").write_text("#!/bin/sh\nexit 0\n")
        subprocess.run(["git", "add", "-A"], cwd=root)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "mvnw"], cwd=root)
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h", "--dry-run",
                                                  "--verify", "x"])
        # explicit --verify wins; without it, the banner shows mvnw.
        check("--verify explícito ganha do mvnw", "x after each done item" in
              p.stdout, p.stdout)
        env_args = ["--for", "2h", "--dry-run"]
        p = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "common"
                                 / "bin" / "cepa-until"),
             "fila", "--repo", str(root), *env_args],
            capture_output=True, text=True, timeout=60,
            env=dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}",
                     FAKE_PLANO="x", FAKE_CHAMADAS=str(Path(tmp) / "c.jsonl")))
        check("sem --verify, o banner mostra ./mvnw -B clean verify",
              "./mvnw -B clean verify" in p.stdout, p.stdout + p.stderr)


def _run_without_verify_flag(tmp, root, binv):
    """Without `--verify` nor `--sem-verify`: whoever chooses is `cepa-until`."""
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "common"
                             / "bin" / "cepa-until"),
         "fila", "--repo", str(root), "--for", "2h", "--no-analysis"],
        capture_output=True, text=True, timeout=120,
        env=dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}",
                 FAKE_PLANO=str(plan_of(root)),
                 FAKE_CHAMADAS=str(Path(tmp) / "chamadas.jsonl"),
                 CEPA_WORKTREE_HOME=str(Path(tmp) / "worktrees"),
                 # away from the real ledger of /common:metrics
                 CEPA_TELEMETRY_DIR=str(Path(tmp) / "telemetria")))


def _commits(root, msg):
    subprocess.run(["git", "add", "-A"], cwd=root)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", msg], cwd=root)


def test_no_build_with_suite_runs_the_suite():
    # cepa has `.claude/no-build` (no build for gate-advance) and
    # `tests/run-all.sh`. Run 2026-09-26-2203 read the first as "without
    # verify" and 18 items closed without the whole suite running.
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        suite_mark = Path(tmp) / "suite-rodou"
        (root / ".claude" / "no-build").write_text("# sem build\n")
        (root / "tests").mkdir(exist_ok=True)
        suite = root / "tests" / "run-all.sh"
        suite.write_text(f"#!/bin/sh\necho x >> {suite_mark}\nexit 0\n")
        suite.chmod(0o755)
        _commits(root, "no-build + suite")
        binv = fake_claude(tmp, WORKS)
        p = _run_without_verify_flag(tmp, root, binv)
        start = [e for e in ledger_of(root) if e["evento"] == "run_start"]
        check("com no-build e tests/run-all.sh, o run começa",
              p.returncode == 0 and start, f"saiu {p.returncode}: {p.stderr[-300:]}")
        check("...e o run_start grava a suíte como verify, não null",
              start and start[0].get("verify") == "tests/run-all.sh",
              str(start))
        check("...e a suíte rodou depois do item done", suite_mark.exists(),
              p.stdout[-400:])


def test_suite_without_no_build_becomes_the_verify():
    # Repo without mvnw/gradlew and without `.claude/no-build`, only with the suite: it is the
    # full build, instead of the refusal "I don't know this repo's build".
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        suite_mark = Path(tmp) / "suite-rodou"
        (root / "tests").mkdir(exist_ok=True)
        suite = root / "tests" / "run-all.sh"
        suite.write_text(f"#!/bin/sh\necho x >> {suite_mark}\nexit 0\n")
        suite.chmod(0o755)
        _commits(root, "suite")
        binv = fake_claude(tmp, WORKS)
        p = _run_without_verify_flag(tmp, root, binv)
        start = [e for e in ledger_of(root) if e["evento"] == "run_start"]
        check("só com tests/run-all.sh, o run começa com a suíte como verify",
              p.returncode == 0 and start
              and start[0].get("verify") == "tests/run-all.sh",
              f"saiu {p.returncode}: {start} {p.stderr[-300:]}")
        check("...e a suíte rodou", suite_mark.exists(), p.stdout[-400:])


def test_no_build_without_suite_still_waives():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        (root / ".claude" / "no-build").write_text("# sem build\n")
        _commits(root, "no-build")
        binv = fake_claude(tmp, WORKS)
        p = _run_without_verify_flag(tmp, root, binv)
        start = [e for e in ledger_of(root) if e["evento"] == "run_start"]
        check("só com no-build, o run começa sem verify",
              p.returncode == 0 and start and start[0].get("verify") is None,
              f"saiu {p.returncode}: {start} {p.stderr[-300:]}")


def test_end_analysis_writes_the_review_beside_the_record():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = ("if ARGS and ARGS[1].startswith('/common:until-review'):\n"
                 "    print('RELATORIO DA NOITE')\n"
                 "    sys.exit(0)\n"
                 "marca(primeiro_pendente(), status='blocked', evidence='x')\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root),
                           ["--for", "2h", "--com-analise"])
        requests = [c[1] for c in calls]
        check("a última chamada é o /common:until-review do registro",
              requests and requests[-1].startswith("/common:until-review ")
              and requests[-1].endswith(".jsonl"), str(requests))
        revs = list((root / ".claude" / "programs" / "fila" / "until")
                    .glob("*.review.md"))
        check("o review.md fica ao lado do registro",
              len(revs) == 1 and "RELATORIO DA NOITE" in revs[0].read_text(),
              str(revs))
        ev = ledger_of(root)
        check("o registro diz que a análise foi feita",
              any(e["evento"] == "analise" and e["feita"] for e in ev), str(ev))


def test_run_stopped_by_quota_does_not_run_the_analysis():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = ("if ARGS and ARGS[1].startswith('/common:until-review'):\n"
                 "    sys.exit(0)\n"
                 "print(json.dumps({'type': 'result', 'result': "
                 "\"You've hit your session limit\"}))\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root),
                           ["--for", "2h", "--com-analise"])
        end = [e for e in ledger_of(root) if e["evento"] == "run_end"][0]
        check("o run parou pela cota", end["motivo"] == "limite-de-uso", str(end))
        check("...e a análise não foi chamada",
              not any(c[1].startswith("/common:until-review") for c in calls),
              str(calls))
        check("...mas o resumo diz como rodá-la depois",
              "/common:until-review" in p.stdout, p.stdout[-400:])


# ── all attempts go to the side branch (Revision 3, step 1; C4) ─────────────

# A fake `claude` that needs more than one attempt. Each call commits
# `<id>-t<n>`. The items in FAKE_DUAS only close on the 2nd; those in FAKE_QUEBRA leave
# the build red on the 2nd; those in FAKE_ADIA go to the end of the queue after the 1st
# (so another item closes in the middle); those in FAKE_PARA do nothing from the 2nd
# on (an attempt without progress); those in FAKE_TRAVA commit and, on the attempt
# in which they would close, close `blocked` instead of `done`.
TRIES = (
    "import subprocess\n"
    "ident = primeiro_pendente()\n"
    "lista = lambda k: os.environ.get(k, '').split(',')\n"
    "cont = os.environ['FAKE_CHAMADAS'] + '.n.' + ident\n"
    "n = int(open(cont).read()) + 1 if os.path.exists(cont) else 1\n"
    "open(cont, 'w').write(str(n))\n"
    "if n >= 2 and ident in lista('FAKE_PARA'):\n"
    "    sys.exit(0)\n"
    "open(f'{ident}-t{n}.txt', 'w').write('x')\n"
    "if n >= 2 and ident in lista('FAKE_QUEBRA'):\n"
    "    open('quebra.txt', 'w').write('x')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', f'{ident}-t{n}'], check=True)\n"
    "if ident not in lista('FAKE_DUAS') or n >= 2:\n"
    "    if ident in lista('FAKE_TRAVA'):\n"
    "        marca(ident, status='blocked', evidence='condicao de fora')\n"
    "    else:\n"
    "        marca(ident, status='done', evidence='ok')\n"
    "elif ident in lista('FAKE_ADIA'):\n"
    "    p = carrega()\n"
    "    p['items'].sort(key=lambda it: it['id'] == ident)\n"
    "    grava(p)\n")


def test_red_build_takes_the_commits_of_all_attempts():
    """WEGO-2320 took two attempts: the side branch kept the 2nd's 2 commits
    and the 9 of the 1st stayed on the night branch, never passing
    through the supervisor's build."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a0"), item("a1"), item("a2")])
        binv = fake_claude(tmp, TRIES)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_QUEBRA": "a1"})
        branch = [e for e in ledger_of(root)
                  if e["evento"] == "run_start"][0]["branch"]
        side_branch = git(root, "log", "--format=%s",
                      f"{branch}-vermelho-a1").splitlines()
        check("a lateral tem os commits das duas tentativas",
              "a1-t1" in side_branch and "a1-t2" in side_branch, str(side_branch))
        night = git(root, "log", "--format=%s", branch).splitlines()
        check("a branch da noite não tem nenhum commit do item vermelho",
              "a1-t1" not in night and "a1-t2" not in night, str(night))
        check("...e guarda os itens verdes de antes e de depois",
              "a0-t1" in night and "a2-t1" in night, str(night))


def test_other_done_amid_attempts_stops_instead_of_resetting():
    """The reset to the start of the 1st attempt would erase the item that closed green in the
    middle. C4 says to stop and warn."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, TRIES)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_QUEBRA": "a1",
                               "FAKE_ADIA": "a1"})
        ev = ledger_of(root)
        branch = [e for e in ev if e["evento"] == "run_start"][0]["branch"]
        night = git(root, "log", "--format=%s", branch).splitlines()
        check("o item verde do meio continua na branch da noite",
              "a2-t1" in night, str(night))
        end = [e for e in ev if e["evento"] == "run_end"][0]
        check("o run para no vermelho", end["motivo"] == "verify-vermelho",
              str(end))
        check("...e o aviso nomeia o item do meio",
              "a2" in (end.get("detalhe") or ""), str(end))


def test_exhausted_item_takes_the_attempt_commits_to_the_side_branch():
    """The 1st attempt committed without closing and the 2nd did not advance: the ceiling marks
    `blocked`, and the 1st's commits stayed on the night branch without a build."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, TRIES)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_DUAS": "a1", "FAKE_PARA": "a1"})
        branch = [e for e in ledger_of(root)
                  if e["evento"] == "run_start"][0]["branch"]
        check("o item vira blocked", status(root, "a1")["status"] == "blocked",
              str(status(root, "a1")))
        night = git(root, "log", "--format=%s", branch).splitlines()
        check("a branch da noite não tem o commit do item parado",
              "a1-t1" not in night and "a2-t1" in night, str(night))
        side_branches = git(root, "branch", "--list", f"{branch}-*-a1").split()
        check("o commit fica numa lateral",
              side_branches and "a1-t1" in git(root, "log", "--format=%s",
                                          side_branches[-1]), str(side_branches))
        check("...que a evidência nomeia",
              side_branches and side_branches[-1] in (status(root, "a1").get("evidence")
                                            or ""), str(status(root, "a1")))



def test_item_the_agent_blocks_after_committing_leaves_the_night_branch():
    """The supervisor only runs the build after `done`: an item the agent
    closes `blocked` after committing left the commits on the
    night branch, without a build, under the next card."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, TRIES)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_TRAVA": "a1,a2"})
        ev = ledger_of(root)
        branch = [e for e in ev if e["evento"] == "run_start"][0]["branch"]
        night = git(root, "log", "--format=%s", branch).splitlines()
        check("a branch da noite não tem os commits dos itens travados",
              "a1-t1" not in night and "a2-t1" not in night, str(night))
        check("...e guarda o item entregue depois deles",
              "a3-t1" in night, str(night))
        for ident in ("a1", "a2"):
            it = status(root, ident)
            side_branches = git(root, "branch", "--list", f"{branch}-*-{ident}").split()
            check(f"{ident} continua `blocked`", it["status"] == "blocked",
                  str(it))
            check(f"o commit do {ident} fica numa lateral",
                  side_branches and f"{ident}-t1" in git(root, "log", "--format=%s",
                                                    side_branches[-1]), str(side_branches))
            ev_item = it.get("evidence") or ""
            check(f"...que a evidência do {ident} nomeia, sem perder o motivo "
                  "do agente", side_branches and side_branches[-1] in ev_item
                  and "condicao de fora" in ev_item, ev_item)
        separated = [e["id"] for e in ev if e["evento"] == "travado_separado"]
        check("o registro diz o que foi separado", separated == ["a1", "a2"],
              str(separated))


def test_stuck_item_with_other_done_amid_stops_instead_of_resetting():
    """Taking the stuck item's commits off would take the branch back to the start of the 1st
    attempt and erase the item that closed green in the middle. The run stops."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, TRIES)
        run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", VERIFY],
             extra_env={"FAKE_DUAS": "a1", "FAKE_ADIA": "a1",
                        "FAKE_TRAVA": "a1"})
        ev = ledger_of(root)
        branch = [e for e in ev if e["evento"] == "run_start"][0]["branch"]
        night = git(root, "log", "--format=%s", branch).splitlines()
        end = [e for e in ev if e["evento"] == "run_end"][0]
        check("o run para com item-preso", end["motivo"] == "item-preso",
              str(end))
        check("...e o aviso nomeia o item do meio",
              "a2" in (end.get("detalhe") or ""), str(end))
        check("nada foi apagado da branch da noite",
              all(c in night for c in ("a1-t1", "a2-t1", "a1-t2")), str(night))


def test_stuck_item_without_commit_leaves_the_branch_alone():
    """Without a commit of the item, there is nothing to separate: neither side branch nor reset."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = ("import subprocess\n"
                 "ident = primeiro_pendente()\n"
                 "if ident == 'a1':\n"
                 "    marca(ident, status='blocked', evidence='condicao de fora')\n"
                 "    sys.exit(0)\n"
                 "open(ident + '.txt', 'w').write('feito')\n"
                 "subprocess.run(['git', 'add', '-A'], check=True)\n"
                 "subprocess.run(['git', '-c', 'user.email=t@t', '-c',\n"
                 "                'user.name=t', 'commit', '-qm', ident],\n"
                 "               check=True)\n"
                 "marca(ident, status='done', evidence='ok')\n")
        binv = fake_claude(tmp, body)
        run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", VERIFY])
        ev = ledger_of(root)
        branch = [e for e in ev if e["evento"] == "run_start"][0]["branch"]
        check("nenhum travado_separado no registro",
              not [e for e in ev if e["evento"] == "travado_separado"], str(ev))
        check("nenhuma lateral travado",
              not git(root, "branch", "--list", f"{branch}-travado-*"),
              git(root, "branch", "--list", "until/*"))
        check("a evidência do a1 fica como o agente escreveu",
              status(root, "a1").get("evidence") == "condicao de fora",
              str(status(root, "a1")))
        check("...e o a2 entra na branch da noite",
              "a2" in git(root, "log", "--format=%s", branch).splitlines(),
              git(root, "log", "--format=%s", branch))

# ── red resolves without the owner (Revision 3, steps 4a, 4b, 4d, 4e) ───────

# A fake `claude` that, on each call, notes the `evidence` the item had when
# it was picked: it is the note the agent would see in `cepa-plan start`.
WORKS_AND_READS = WORKS.replace(
    "ident = primeiro_pendente()\n",
    "ident = primeiro_pendente()\n"
    "_ev = [it.get('evidence') for it in carrega()['items'] if it['id'] == ident][0]\n"
    "with open(os.environ['FAKE_CHAMADAS'] + '.recado', 'a') as f:\n"
    "    f.write(json.dumps({'id': ident, 'evidence': _ev}) + '\\n')\n", 1)

ALWAYS_RED = "false"


def notes(root):
    f = Path(root).parent / "chamadas.jsonl.recado"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def telemetry(dirt):
    ev = []
    for f in Path(dirt).glob("*.jsonl"):
        ev += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return ev


def test_4a_second_green_build_closes_done_and_records_the_instability():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WORKS)
        cont = Path(tmp) / "n-verify"
        # red on the 1st call, green from the 2nd on
        verify = (f"n=$(cat {cont} 2>/dev/null || echo 0); "
                  f"echo $((n+1)) > {cont}; [ $n -ge 1 ]")
        tele = Path(tmp) / "tele"
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", verify],
                    extra_env={"CEPA_TELEMETRY_DIR": str(tele)})
        check("o item fecha done", status(root, "a1")["status"] == "done",
              str(status(root, "a1")) + p.stdout[-600:])
        ev = ledger_of(root)
        check("o registro grava verify_repetido_verde",
              any(e["evento"] == "verify_repetido_verde" and e["id"] == "a1"
                  for e in ev), str(ev))
        t = [e for e in telemetry(tele) if e.get("event") == "build_instavel"]
        check("a telemetria grava build_instavel com card e run",
              len(t) == 1 and t[0].get("card") == "a1" and t[0].get("run"),
              str(telemetry(tele)))
        branch = [e for e in ev if e["evento"] == "run_start"][0]["branch"]
        check("o commit fica na branch da noite",
              "a1" in git(root, "log", "--format=%s", branch).splitlines())


def test_4b_red_return_gives_the_item_back_to_pending_with_a_note():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WORKS_AND_READS)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", ALWAYS_RED,
                     "--max-failures", "5"])
        ev = ledger_of(root)
        branch = [e for e in ev if e["evento"] == "run_start"][0]["branch"]
        seen_ones = notes(root)
        check("o item volta a ser executado depois da 1ª volta",
              len(seen_ones) >= 2, str(seen_ones) + p.stdout[-800:])
        note = (seen_ones[1]["evidence"] or "") if len(seen_ones) >= 2 else ""
        check("...como pending, com a lateral no recado",
              f"{branch}-vermelho-a1" in note, note)
        check("...o motivo e o número da volta",
              "exited 1" in note and "return 1 of" in note, note)
        check("...e que desligar teste não conserta",
              "disabling" in note.lower(), note)
        check("o registro grava volta_vermelha",
              any(e["evento"] == "volta_vermelha" and e["id"] == "a1"
                  for e in ev), str(ev))
        check("o 2º build rodou antes da volta",
              len([e for e in ev if e["evento"] == "verify"
                   and e["id"] == "a1"]) >= 2, str(ev))


def test_4d_second_red_return_becomes_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", ALWAYS_RED])
        check("o run termina com o item blocked",
              status(root, "a1")["status"] == "blocked",
              str(status(root, "a1")) + p.stdout[-600:])
        returns = [e for e in ledger_of(root)
                  if e["evento"] == "volta_vermelha" and e["id"] == "a1"]
        check("...e exatamente duas voltas vermelhas", len(returns) == 2,
              str(returns))
        branch = [e for e in ledger_of(root)
                  if e["evento"] == "run_start"][0]["branch"]
        check("a 2ª volta não sobrescreve a lateral da 1ª",
              git(root, "branch", "--list", f"{branch}-vermelho-a1")
              and git(root, "branch", "--list", f"{branch}-vermelho-a1-v2"),
              git(root, "branch", "--list", "until/*"))


def test_4d_returns_count_across_runs():
    """The ceiling counts in the queue's `.jsonl` files, and not only in the current window."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, WORKS)
        d = root / ".claude" / "programs" / "fila" / "until"
        d.mkdir(parents=True)
        (d / "2026-01-01-0000.jsonl").write_text(json.dumps(
            {"evento": "volta_vermelha", "id": "a1", "volta": 1}) + "\n")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "run anterior"], cwd=root, check=True)
        run_until(root, binv, plan_of(root),
             ["--for", "2h", "--verify", ALWAYS_RED])
        check("com uma volta de um run anterior, a 1ª deste já vira blocked",
              status(root, "a1")["status"] == "blocked"
              and len(notes(root)) == 0 and len(cwds(root)) == 1,
              str(status(root, "a1")) + str(cwds(root)))


def test_4e_each_return_counts_toward_the_circuit_breaker():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, WORKS)
        run_until(root, binv, plan_of(root),
             ["--for", "2h", "--verify", ALWAYS_RED, "--max-failures", "2"])
        end = [e for e in ledger_of(root) if e["evento"] == "run_end"][0]
        check("o run para pelo disjuntor", end["motivo"] == "disjuntor", str(end))
        check("...sem nenhum item done",
              not any(status(root, i)["status"] == "done"
                      for i in ("a1", "a2", "a3")), str(end))


# ── the side branch only goes away with a copy (Revision 3, step 4f) ────────

def old_side_branch(root, given_name, file):
    """A side branch from a previous run with a commit that main does not have."""
    git(root, "checkout", "-q", "-b", given_name)
    (root / file).write_text("x")
    git(root, "add", "-A")
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
        f"commit de {file}")
    git(root, "checkout", "-q", "-")


def test_4f_side_branch_of_closed_item_becomes_patch_before_vanishing():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1", status="dropped"), item("a2"),
                                item("a3", status="blocked")])
        old_side_branch(root, "until/2026-01-01-0000-vermelho-a1", "l1.txt")
        old_side_branch(root, "until/2026-01-01-0000-vermelho-a1-v2", "l1b.txt")
        old_side_branch(root, "until/2026-01-01-0000-parado-a3", "l3.txt")
        old_side_branch(root, "until/2026-01-01-0000-travado-a1", "l1c.txt")
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        d = root / ".claude" / "programs" / "fila" / "until"
        patches = sorted(d.glob("*.laterais/*.patch"))
        names = [p.name for p in patches]
        check("as três laterais do item dropped viram patch",
              len(patches) == 3 and all(n.endswith(("-a1.patch", "-a1-v2.patch"))
                                        for n in names), str(names))
        check("...inclusive a do item que o agente travou com commits",
              any("travado-a1" in n for n in names), str(names))
        check("...com o commit dentro",
              any("commit de l1.txt" in p.read_text() for p in patches),
              str(names))
        check("...e só então somem",
              not git(root, "branch", "--list", "until/*-a1*"),
              git(root, "branch", "--list", "until/*"))
        check("a lateral de item ainda aberto (blocked) fica",
              git(root, "branch", "--list", "until/2026-01-01-0000-parado-a3"),
              git(root, "branch", "--list", "until/*"))
        check("o registro grava a lateral apagada com o patch",
              any(e["evento"] == "lateral_apagada" and e.get("patch")
                  for e in ledger_of(root)), str(ledger_of(root)))


def test_4f_without_patch_the_side_branch_stays():
    import shutil
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1", status="done"), item("a2")])
        old_side_branch(root, "until/2026-01-01-0000-vermelho-a1", "l1.txt")
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        fake_one = binv / "git"
        fake_one.write_text(
            "#!/bin/sh\n"
            "for a in \"$@\"; do [ \"$a\" = format-patch ] && exit 1; done\n"
            f"exec {shutil.which('git')} \"$@\"\n")
        fake_one.chmod(0o755)
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        check("com o format-patch falhando, a branch continua",
              git(root, "branch", "--list", "until/2026-01-01-0000-vermelho-a1"),
              git(root, "branch", "--list", "until/*"))
        check("...e o registro diz por quê",
              any(e["evento"] == "lateral_mantida" for e in ledger_of(root)),
              str(ledger_of(root)))


# ── run state and list of actions (step 2; C6, C7 and A4) ───────────────────

def state_of(root):
    d = root / ".claude" / "programs" / "fila" / "until"
    files = sorted(d.glob("*.estado.json"))
    return json.loads(files[-1].read_text()) if files else None


# The fake `claude` notes the run state it sees: during the item, and in the end
# analysis (the `/common:until-review` call).
LOOKS_AT_STATE = (
    "import glob\n"
    "def _estado():\n"
    "    d = os.path.join(os.path.dirname(PLANO), 'until')\n"
    "    a = sorted(glob.glob(os.path.join(d, '*.estado.json')))\n"
    "    return json.load(open(a[-1])) if a else None\n"
    "with open(os.environ['FAKE_CHAMADAS'] + '.estado', 'a') as f:\n"
    "    f.write(json.dumps({'args0': ARGS[1][:30] if len(ARGS) > 1 else '',\n"
    "                        'estado': _estado()}) + '\\n')\n"
    "if ARGS and ARGS[1].startswith('/common:until-review'):\n"
    "    print(json.dumps({'type': 'result', 'result': 'analise'}))\n"
    "    sys.exit(0)\n")


def seen_state(root):
    f = Path(root).parent / "chamadas.jsonl.estado"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def test_2_run_state_running_then_waiting_owner_before_the_analysis():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = LOOKS_AT_STATE + WORKS.replace(
            "marca(ident, status='done', evidence='ok')\n",
            "if ident == 'a2':\n"
            "    marca(ident, status='blocked', evidence='travou no Keycloak')\n"
            "else:\n"
            "    marca(ident, status='done', evidence='ok')\n")
        binv = fake_claude(tmp, body)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY, "--com-analise"])
        seen_ones = seen_state(root)
        during = [v for v in seen_ones if not v["args0"].startswith("/common:until")]
        check("durante o item, o estado é rodando",
              during and all((v["estado"] or {}).get("estado") == "rodando"
                              for v in during), str(during)[:400])
        analysis = [v for v in seen_ones if v["args0"].startswith("/common:until")]
        state_dict = (analysis[0]["estado"] or {}) if analysis else {}
        check("a análise já encontra o estado final gravado",
              state_dict.get("estado") == "esperando-dono", str(analysis)[:400])
        actions = state_dict.get("acoes") or []
        branch = [e for e in ledger_of(root)
                  if e["evento"] == "run_start"][0]["branch"]
        check("a única ação é aterrissar, com a branch da noite",
              [a.get("id") for a in actions] == ["aterrissar"]
              and f"fila/{branch.split('/', 1)[1]}"
              in (actions[0].get("comando") or ""), str(actions))
        check("...com a frase leiga do efeito",
              actions and actions[0].get("frase"), str(actions))
        item_list = state_dict.get("itens") or []
        check("uma linha por item",
              [i.get("id") for i in item_list] == ["a1", "a2"], str(item_list))
        stays = state_dict.get("fica_com_voce") or []
        check("o travado vai para 'fica com você' com o motivo",
              any(f.get("id") == "a2" and "Keycloak" in (f.get("texto") or "")
                  for f in stays), str(stays))
        check("o terminal imprime a ação numerada",
              "1. aterrissar" in p.stdout, p.stdout[-900:])
        check("...e o bloco 'Left with you'",
              "Left with you" in p.stdout, p.stdout[-900:])
        check("o resumo não sugere o /common:worktree-merge",
              "worktree-merge" not in p.stdout, p.stdout[-900:])


def test_2_each_item_appears_once_in_the_summary():
    """A4: WEGO-2320 appeared in "Stuck", "Red build" and "No
    progress", and was read as three problems."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, WORKS)
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY],
                    extra_env={"FAKE_QUEBRA": "a2"})
        end = p.stdout[p.stdout.find("── ended at"):]
        for ident in ("a1", "a2", "a3"):
            check(f"{ident} aparece uma vez na lista de itens do fim",
                  end.count(f"- {ident}:") == 1, end)
        check("a linha do a2 diz volta vermelha e a lateral",
              "vermelho-a2" in end and "red return" in end, end)


def test_2_run_without_commit_ends_closed_without_action():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='dropped',"
                                " evidence='não precisa mais')")
        run_until(root, binv, plan_of(root), ["--for", "2h"])
        state_dict = state_of(root) or {}
        check("sem commit e sem pendência, o estado é encerrado",
              state_dict.get("estado") == "encerrado" and not state_dict.get("acoes"),
              str(state_dict))


# ── step 1 between runs: the previous run's attempt arrives through inheritance ─

# On the 1st call, the FAKE_METADE items commit and are left with an open
# human route: run A ends with them half done, without the loop repeating them.
HALF = TRIES.replace(
    "if ident not in lista('FAKE_DUAS') or n >= 2:\n",
    "if n == 1 and ident in lista('FAKE_METADE'):\n"
    "    marca(ident, human_pending='pela metade')\n"
    "elif ident not in lista('FAKE_DUAS') or n >= 2:\n", 1)


def run_ids(root):
    return [e["branch"] for e in ledger_of(root) if e["evento"] == "run_start"]


def frees(root, *idents):
    """The owner closes the human route between the two runs and commits the queue (the
    launch refuses the modified queue outside what the previous run touched)."""
    p = yaml.safe_load(plan_of(root).read_text())
    for it in p["items"]:
        if it["id"] in idents:
            it["human_pending"] = None
    plan_of(root).write_text(yaml.safe_dump(p, allow_unicode=True))
    git(root, "add", str(plan_of(root)))
    git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
        "dono: fecha a rota")


def test_1_attempt_of_the_previous_run_also_goes_to_the_side_branch():
    """Finding of the completion-auditor (2026-09-28): the reset went back to the start
    of the 1st attempt of THIS run, which is after the inheritance merge, and the commits
    of the previous run stayed on the night branch without passing through the build.

    a2 enters the queue only in run B and closes green after a1: it is what keeps
    run B's night branch alive for the test to look inside it."""
    import time
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2", status="dropped")])
        binv = fake_claude(tmp, HALF)
        env = {"FAKE_METADE": "a1", "FAKE_QUEBRA": "a1"}
        run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", VERIFY],
             extra_env=env)
        frees(root, "a1")
        p_ = yaml.safe_load(plan_of(root).read_text())
        for it in p_["items"]:
            if it["id"] == "a2":
                it["status"] = "pending"
        plan_of(root).write_text(yaml.safe_dump(p_, allow_unicode=True))
        git(root, "add", str(plan_of(root)))
        git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm",
            "dono: a2 entra na fila")
        time.sleep(61)  # the run id is per minute
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--verify", VERIFY], extra_env=env)
        runs = run_ids(root)
        check("o run B herdou a branch do run A",
              len(runs) == 2 and "inherits" in p.stdout, p.stdout[:900])
        check("...e o a2 fechou verde nele",
              status(root, "a2")["status"] == "done", str(status(root, "a2")))
        night_b = git(root, "log", "--format=%s", runs[-1]).splitlines()
        check("a branch da noite do run B não tem o commit do run A",
              "a2-t1" in night_b and "a1-t1" not in night_b, str(night_b))
        side_branch = git(root, "log", "--format=%s",
                      f"{runs[-1]}-vermelho-a1").splitlines()
        check("...que está na lateral da 1ª volta",
              "a1-t1" in side_branch and "a1-t2" in side_branch, str(side_branch))


def test_1_inheritance_with_another_open_item_stops_instead_of_resetting():
    import time
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, HALF)
        run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", VERIFY],
             extra_env={"FAKE_METADE": "a1,a2"})
        frees(root, "a1")
        time.sleep(61)
        run_until(root, binv, plan_of(root), ["--for", "2h", "--verify", VERIFY],
             extra_env={"FAKE_METADE": "a1,a2", "FAKE_QUEBRA": "a1"})
        ev = ledger_of(root)
        end = [e for e in ev if e["evento"] == "run_end"][-1]
        check("o run B para no vermelho", end["motivo"] == "verify-vermelho",
              str(end))
        check("...e o aviso nomeia o outro item herdado",
              "a2" in (end.get("detalhe") or ""), str(end))
        night_b = git(root, "log", "--format=%s", run_ids(root)[-1]).splitlines()
        check("o trabalho do a2 continua na branch da noite",
              "a2-t1" in night_b, str(night_b))


def main():
    print("cepa-until — branch da noite\n")
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


def _banner_with(tmp, files):
    """Repo with `files` committed; returns the --dry-run process without
    `--verify`, to see the build `cepa-until` chose on its own."""
    root = build_repo(tmp, [item("a1")])
    for name, content in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        if name.endswith(".sh"):
            target.chmod(0o755)
    _commits(root, "repo files")
    binv = fake_claude(tmp, WORKS)
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "common"
                             / "bin" / "cepa-until"),
         "fila", "--repo", str(root), "--for", "2h", "--dry-run"],
        capture_output=True, text=True, timeout=60,
        env=dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}",
                 FAKE_PLANO="x", FAKE_CHAMADAS=str(Path(tmp) / "c.jsonl"),
                 CEPA_WORKTREE_HOME=str(Path(tmp) / "worktrees"),
                 CEPA_TELEMETRY_DIR=str(Path(tmp) / "telemetria")))


def _pj(scripts):
    return json.dumps({"name": "x", "scripts": scripts})


def test_package_json_with_build_and_test_becomes_the_default_build():
    # wego-digitacao-demo (Next.js) on 2026-10-24: without mvnw, cepa-until
    # refused and the owner had to pass `--verify 'npm run build'` by hand.
    with tempfile.TemporaryDirectory() as tmp:
        p = _banner_with(tmp, {
            "package.json": _pj({"build": "next build",
                                 "test": "playwright test"}),
            "package-lock.json": "{}"})
        check("package.json + package-lock: install, build and test",
              p.returncode == 0
              and "npm ci && npm run build && npm test" in p.stdout,
              f"exited {p.returncode}: {p.stdout[-400:]} {p.stderr[-300:]}")


def test_package_json_with_build_only_does_not_invent_a_test():
    with tempfile.TemporaryDirectory() as tmp:
        p = _banner_with(tmp, {
            "package.json": _pj({"build": "tsc"}),
            "package-lock.json": "{}"})
        check("build only: npm ci && npm run build, no npm test",
              p.returncode == 0 and "npm ci && npm run build" in p.stdout
              and "npm test" not in p.stdout,
              f"exited {p.returncode}: {p.stdout[-400:]} {p.stderr[-300:]}")


def test_npm_init_test_does_not_count_as_a_suite():
    with tempfile.TemporaryDirectory() as tmp:
        p = _banner_with(tmp, {
            "package.json": _pj({
                "build": "tsc",
                "test": 'echo "Error: no test specified" && exit 1'}),
            "package-lock.json": "{}"})
        check("the npm init test stays out",
              p.returncode == 0 and "npm ci && npm run build" in p.stdout
              and "npm test" not in p.stdout,
              f"exited {p.returncode}: {p.stdout[-400:]} {p.stderr[-300:]}")


def test_pnpm_and_yarn_lock_pick_the_package_manager():
    with tempfile.TemporaryDirectory() as tmp:
        p = _banner_with(tmp, {
            "package.json": _pj({"build": "vite build", "test": "vitest run"}),
            "pnpm-lock.yaml": "lockfileVersion: 9\n"})
        check("pnpm-lock.yaml: pnpm with frozen lockfile",
              "pnpm install --frozen-lockfile && pnpm run build && pnpm test"
              in p.stdout, f"{p.stdout[-400:]} {p.stderr[-300:]}")
    with tempfile.TemporaryDirectory() as tmp:
        p = _banner_with(tmp, {
            "package.json": _pj({"build": "vite build"}),
            "yarn.lock": "# yarn\n"})
        check("yarn.lock: yarn with frozen lockfile",
              "yarn install --frozen-lockfile && yarn run build" in p.stdout,
              f"{p.stdout[-400:]} {p.stderr[-300:]}")


def test_package_json_without_build_nor_test_still_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        p = _banner_with(tmp, {"package.json": _pj({"dev": "next dev"})})
        check("package.json without build nor test: refuses as before",
              p.returncode == 2 and "package.json" in p.stderr,
              f"exited {p.returncode}: {p.stderr[-300:]}")


def test_repo_suite_beats_package_json():
    # Whoever wrote tests/run-all.sh said which suite it is: it rules.
    with tempfile.TemporaryDirectory() as tmp:
        p = _banner_with(tmp, {
            "package.json": _pj({"build": "next build"}),
            "tests/run-all.sh": "#!/bin/sh\nexit 0\n"})
        check("tests/run-all.sh beats package.json",
              p.returncode == 0 and "tests/run-all.sh" in p.stdout
              and "npm run build" not in p.stdout,
              f"exited {p.returncode}: {p.stdout[-400:]} {p.stderr[-300:]}")


if __name__ == "__main__":
    sys.exit(main())
