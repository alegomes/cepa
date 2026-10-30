#!/usr/bin/env python3
"""cepa-until — an item that advanced without closing, and the resumption in the next run.

Run 2026-09-27-1632 of wego-acessos-backend showed two defects in the same
item, WEGO-2283:

  - killed by the slack (exit 143) with 15 commits on the night branch, the
    `item_end` came out `progresso: false`. The circuit breaker and the attempt ceiling
    read that field: an item that advanced a lot was treated as stalled;
  - the next run created `until/<run>` from the clone's HEAD. `start`
    claimed 2283's orphan reservation, but its 15 commits stayed on
    `until/2026-09-27-1632` and did not enter the new branch: the item restarted
    from zero, and the workaround was merging the old branch by hand before the run.

The cases below pin the fix:
  - a commit on the night branch counts as progress, even without an outcome;
  - the night branch inherits the previous run's branch when it holds commits
    of an item that was left half done and has not been merged yet;
  - an already merged branch is not inherited;
  - an inheritance that conflicts refuses the launch, leaving neither worktree nor branch.
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

OLD = "2026-01-01-0000"
OLD_BRANCH = f"until/{OLD}"


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


def commit(root, msg):
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", msg], cwd=root, check=True)


def orphan(ident):
    """`in_progress` item whose reservation is from another machine and is past 24h:
    `cepa-plan queue` returns it as executable."""
    it = item(ident, status="in_progress")
    it["claimed_by"] = {"session_id": "morta", "pid": 1,
                        "hostname": "outra-maquina", "cwd": "/nao/existe",
                        "branch": OLD_BRANCH,
                        "started_at": "2026-01-01T00:00:00+00:00"}
    return it


def previous_run(root, file="parcial.txt", content="metade do a1\n",
                 commits=1):
    """What the dead run left: the night branch with a1's half-done work
    and the record saying a1 left with commits and no outcome."""
    base = git(root, "rev-parse", "HEAD")
    subprocess.run(["git", "branch", OLD_BRANCH], cwd=root, check=True)
    subprocess.run(["git", "checkout", "-q", OLD_BRANCH], cwd=root, check=True)
    (root / file).write_text(content)
    commit(root, "a1 pela metade")
    subprocess.run(["git", "checkout", "-q", "-"], cwd=root, check=True)
    d = root / ".claude" / "programs" / "fila" / "until"
    d.mkdir(parents=True, exist_ok=True)
    events = [
        {"evento": "run_start", "branch": OLD_BRANCH, "base": base,
         "arvore": "/nao/existe"},
        {"evento": "item_start", "id": "a1", "tentativa": 1},
        {"evento": "item_end", "id": "a1", "status": "in_progress",
         "exit_code": 143, "timeout": True, "commits": commits,
         "progresso": False},
        {"evento": "run_end", "motivo": "prazo"},
    ]
    (d / f"{OLD}.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in events))


# The resumption's fake `claude`: says whether it saw the previous run's work,
# commits and closes a1.
RESUMES = (
    "import subprocess\n"
    "viu = os.path.exists('parcial.txt')\n"
    "with open(os.environ['FAKE_CHAMADAS'] + '.viu', 'a') as f:\n"
    "    f.write(json.dumps({'viu_parcial': viu}) + '\\n')\n"
    "open('a1.txt', 'w').write('feito')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', 'a1 fechado'], check=True)\n"
    "marca('a1', status='done', evidence='ok')\n")


def saw(root):
    f = Path(root).parent / "chamadas.jsonl.viu"
    return [json.loads(l) for l in f.read_text().splitlines()] if f.exists() else []


def new_runs(ev):
    return [e for e in ev if e["evento"] == "run_start"
            and e.get("branch") != OLD_BRANCH]


# ── 1. a commit is progress ─────────────────────────────────────────────────

def test_item_that_committed_without_closing_counts_as_progress():
    """With `--attempts-per-item 1`, the attempt that committed and left without an
    outcome marked the item `blocked` through the ceiling. It advanced: the next turn closes it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = (
            "import subprocess\n"
            "n = len(open(os.environ['FAKE_CHAMADAS']).read().splitlines())\n"
            "open(f'passo{n}.txt', 'w').write('x')\n"
            "subprocess.run(['git', 'add', '-A'], check=True)\n"
            "subprocess.run(['git', '-c', 'user.email=t@t', '-c',"
            " 'user.name=t', 'commit', '-qm', f'passo {n}'], check=True)\n"
            "if n >= 2:\n"
            "    marca('a1', status='done', evidence='ok')\n")
        binv = fake_claude(tmp, body)
        p, calls = run_until(root, binv, plan_of(root),
                           ["--for", "2h", "--attempts-per-item", "1",
                            "--max-failures", "1"])
        ends = [e for e in ledger_of(root) if e["evento"] == "item_end"]
        check("a 1ª tentativa sai com commit e sem desfecho",
              ends and ends[0]["commits"] == 1
              and ends[0]["status"] == "pending", str(ends))
        check("...e o registro diz progresso",
              ends and ends[0]["progresso"] is True, str(ends))
        check("o teto de tentativas não tira o item da frente",
              status(root, "a1")["status"] == "done",
              str(status(root, "a1")) + p.stdout[-600:])
        check("o disjuntor não dispara",
              "· disjuntor" not in p.stdout and len(calls) == 2,
              p.stdout[-600:])
        check("a tela diz que andou sem fechar",
              "commit(s) sem fechar" in p.stdout, p.stdout[-600:])


def test_item_without_commit_and_without_outcome_remains_without_progress():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        p, _ = run_until(root, binv, plan_of(root),
                    ["--for", "2h", "--attempts-per-item", "1",
                     "--max-failures", "1"])
        ends = [e for e in ledger_of(root) if e["evento"] == "item_end"]
        check("sem commit, o registro segue dizendo sem progresso",
              ends and ends[0]["progresso"] is False
              and ends[0]["commits"] == 0, str(ends))
        check("...e o disjuntor dispara", "· disjuntor" in p.stdout,
              p.stdout[-400:])


# ── 2. the resumption inherits the previous run's branch ────────────────────

def test_resuming_the_orphan_reservation_inherits_the_previous_run_commits():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [orphan("a1")])
        previous_run(root)
        binv = fake_claude(tmp, RESUMES)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h"])
        seen_ones = saw(root)
        check("o item retomado acorda com o trabalho do run anterior",
              seen_ones and seen_ones[0]["viu_parcial"], str(seen_ones) + p.stdout[-800:]
              + p.stderr[-400:])
        start = new_runs(ledger_of(root))
        inherited = (start[0].get("herdou") or []) if start else []
        check("a largada registra de qual branch herdou",
              [(h.get("branch"), h.get("itens"), h.get("commits"))
               for h in inherited] == [(OLD_BRANCH, ["a1"], 1)], str(start))
        check("...e a tela avisa", OLD_BRANCH in p.stdout
              and "herd" in p.stdout, p.stdout[:1500])
        branch = start[0]["branch"] if start else "?"
        log = git(root, "log", "--format=%s", branch).splitlines()
        check("a branch nova tem o commit antigo e o novo",
              "a1 pela metade" in log and "a1 fechado" in log, str(log))
        check("o clone principal não recebeu nada",
              "a1 pela metade" not in git(root, "log", "--format=%s"))


def test_already_merged_branch_is_not_inherited():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [orphan("a1")])
        previous_run(root)
        subprocess.run(["git", "merge", "-q", "--ff-only", OLD_BRANCH],
                       cwd=root, check=True)
        binv = fake_claude(tmp, RESUMES)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h"])
        start = new_runs(ledger_of(root))
        check("nada a herdar: a largada não registra herança",
              start and not start[0].get("herdou"), str(start))
        check("...e o item vê o trabalho (veio pela main)",
              saw(root) and saw(root)[0]["viu_parcial"], str(saw(root)))


def test_previous_run_without_item_commit_is_not_inherited():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [orphan("a1")])
        previous_run(root, commits=0)
        binv = fake_claude(tmp, RESUMES)
        p, _ = run_until(root, binv, plan_of(root), ["--for", "2h"])
        start = new_runs(ledger_of(root))
        check("item que saiu sem commit não puxa a branch antiga",
              start and not start[0].get("herdou"), str(start))


def test_conflicting_inheritance_refuses_the_launch_leaving_no_trace():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [orphan("a1")])
        previous_run(root)
        (root / "parcial.txt").write_text("outra coisa na main\n")
        commit(root, "main mexeu no mesmo arquivo")
        binv = fake_claude(tmp, RESUMES)
        p, calls = run_until(root, binv, plan_of(root), ["--for", "2h"])
        check("a largada é recusada", p.returncode == 2,
              f"rc={p.returncode} {p.stdout[-400:]} {p.stderr[-400:]}")
        check("...nomeando a branch e o que fazer",
              OLD_BRANCH in p.stderr and "git merge" in p.stderr,
              p.stderr[-600:])
        check("nenhum item roda", not calls, str(calls))
        check("não sobra branch da noite nova",
              git(root, "branch", "--list", "until/*").split()
              == [OLD_BRANCH], git(root, "branch", "--list", "until/*"))
        match = Path(tmp) / "worktrees"
        check("...nem worktree", not match.exists() or not any(match.iterdir()),
              str(list(match.iterdir())) if match.exists() else "")
        check("a reserva órfã continua onde estava",
              status(root, "a1")["status"] == "in_progress")


def main():
    print("cepa-until — retomada\n")
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
