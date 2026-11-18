#!/usr/bin/env python3
"""`cepa until --all` (spec `until-todas-as-filas`).

CS-1: `cepa until --all --for 8h --dry-run` lists the ready items of every
queue, grouped by queue and in the order of `cepa plan ready`, and exits 0
without executing anything. Before the flag existed the call exited 2: the
queue name was a required positional.

Against the real CLI (`cepa until`, through the launcher), in a temporary git
repo with two queues, `a` and `b`, one ready item each, and a fake `claude`
that records any call (none may happen).

CS-3: the order is queue by queue, and the ready items are re-read before each
item: an item that becomes ready during the run enters before the run moves on
to the next queue (and an earlier queue's item that becomes ready runs next).
Observed in the order of the `item_start` events of the run's record.

Run with `python3 tests/test_cepa_until_all.py`.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cepa_until as base  # noqa: E402

import yaml  # noqa: E402

check = base.check
FAILURES = base.FAILURES
REPO = Path(__file__).resolve().parent.parent
CEPA = REPO / "common" / "bin" / "cepa"
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"


def _queue(root, name, items):
    d = root / ".claude" / "queues" / name
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "queue": name,
            "source": "teste", "items": items}
    (d / "queue.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                  encoding="utf-8")
    return d / "queue.yaml"


def _repo(tmp, queues):
    root = Path(tmp) / "repo"
    root.mkdir()
    paths = {n: _queue(root, n, its) for n, its in queues.items()}
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    return root, paths


def _run(tmp, root, args, via_launcher=True, claude_body="pass"):
    binv = base.fake_claude(tmp, claude_body)
    env = dict(os.environ)
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(Path(tmp) / "nenhum.yaml")
    calls = Path(tmp) / "chamadas.jsonl"
    env["FAKE_CHAMADAS"] = str(calls)
    env["CEPA_UNTIL_LEITOR"] = "off"
    env["CEPA_WORKTREE_HOME"] = str(Path(tmp) / "worktrees")
    env["FAKE_CEPA_PLAN"] = str(REPO / "common" / "bin" / "cepa-plan")
    cmd = ([str(CEPA), "until"] if via_launcher
           else [sys.executable, str(CEPA_UNTIL)])
    p = subprocess.run(cmd + list(args) + ["--repo", str(root)],
                       capture_output=True, text=True, env=env, timeout=120,
                       stdin=subprocess.DEVNULL)
    return p, (calls.read_text().splitlines() if calls.exists() else [])


def _branches(root):
    return subprocess.run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/until/"],
        cwd=root, capture_output=True, text=True).stdout.split()


def test_dry_run_lists_every_queue_in_ready_order():
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"b": [base.item("b1")],
                                  "a": [base.item("a1")]})
        before = {n: p.read_text() for n, p in paths.items()}
        p, calls = _run(tmp, root, ["--all", "--for", "8h", "--dry-run"])
        out = p.stdout
        check("--all --dry-run sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-400:]}")
        check("...traz os dois ids", "a1" in out and "b1" in out, out[-800:])
        check("...a fila a antes da b (ordem do `cepa plan ready`)",
              "a1" in out and "b1" in out and out.index("a1") < out.index("b1"),
              out[-800:])
        check("...agrupa por fila: o nome de cada fila precede o seu item",
              "a" in out and out.rfind(" a ", 0, out.index("a1")) >= 0
              and out.rfind(" b ", 0, out.index("b1")) > out.index("a1"),
              out[-800:])
        check("...não chama o claude", not calls, str(calls))
        check("...não toca nenhuma fila",
              all(paths[n].read_text() == before[n] for n in paths))
        check("...não cria branch until/*", not _branches(root),
              str(_branches(root)))


def test_dry_run_order_is_the_order_of_plan_ready():
    """The same order `cepa plan ready --json` gives, item order inside a
    queue included, and a queue with nothing ready does not list an item."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {
            "zeta": [base.item("z1"), base.item("z2")],
            "alfa": [base.item("x1", status="done"), base.item("x2")],
            "meio": [base.item("m1", human_pending="validar à mão")],
        })
        ready = json.loads(subprocess.run(
            [sys.executable, str(REPO / "common" / "bin" / "cepa-plan"),
             "ready", "--repo", str(root), "--json"],
            capture_output=True, text=True, check=True).stdout)
        expected = [l["id"] for q in ready["filas"] for l in q["prontos"]]
        p, _ = _run(tmp, root, ["--all", "--for", "8h", "--dry-run"])
        out = p.stdout
        pos = [out.find(i) for i in expected]
        check("a ordem da saída é a do `cepa plan ready`",
              p.returncode == 0 and all(x >= 0 for x in pos) and pos == sorted(pos),
              f"esperado {expected}, posições {pos}\n{out[-800:]}")
        check("...item feito e item à espera do dono não aparecem como prontos",
              "x1 " not in out and "m1 —" not in out, out[-800:])
        check("...fila sem item pronto não ganha cabeçalho de fila",
              "queue meio" not in out and "queue alfa" in out, out[-800:])
        check("...e aparece no rodapé dos que não têm nada pronto",
              any(l.strip().startswith("nothing ready:") and "meio" in l
                  and "alfa" not in l and "zeta" not in l
                  for l in out.splitlines()), out[-800:])


def test_dry_run_with_nothing_ready_says_so_and_exits_0():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("a1", status="done")],
                              "b": [base.item("b1", human_pending="validar")]})
        p, calls = _run(tmp, root, ["--all", "--for", "8h", "--dry-run"])
        check("nenhum pronto: --all --dry-run sai com 0", p.returncode == 0,
              p.stderr[-400:])
        check("...e diz que nenhuma fila tem item pronto",
              "no queue has a ready item" in p.stdout, p.stdout[-600:])
        check("...sem chamar o claude", not calls)


def test_dependency_inside_the_run_is_named():
    """A ready item whose `blocked_by` is another ready item of the same run
    says what it waits for, as `cepa plan ready` does."""
    with tempfile.TemporaryDirectory() as tmp:
        c2 = dict(base.item("c2"), blocked_by=["c1"])
        root, _ = _repo(tmp, {"c": [base.item("c1"), c2]})
        p, _ = _run(tmp, root, ["--all", "--for", "8h", "--dry-run"])
        lines = p.stdout.splitlines()
        i = next((k for k, l in enumerate(lines) if "c2 —" in l), None)
        check("item que depende de outro pronto mostra a linha waits",
              i is not None and i + 1 < len(lines)
              and "waits: c1" in lines[i + 1], p.stdout[-600:])


def test_all_and_queue_name_together_are_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("a1")]})
        p, calls = _run(tmp, root, ["a", "--all", "--for", "8h", "--dry-run"])
        check("nome da fila + --all é recusado com 2", p.returncode == 2,
              f"rc={p.returncode}")
        check("...e a recusa nomeia o --all", "--all" in p.stderr, p.stderr[-400:])
        check("...sem chamar o claude", not calls)


def test_neither_queue_nor_all_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("a1")]})
        p, _ = _run(tmp, root, ["--for", "8h", "--dry-run"])
        check("sem fila e sem --all é recusado com 2", p.returncode == 2,
              f"rc={p.returncode}")
        check("...e a recusa sugere o --all", "--all" in p.stderr, p.stderr[-400:])


# A fake `claude` that works like `/common:drain-plan <queue> --max 1` on the run
# worktree: asks `cepa-plan` for the queue's first runnable item, reserves it,
# commits a file named after it and closes it `done`, all in ITS queue.
DONE_IN_ITS_QUEUE = (
    "import subprocess\n"
    "req = ARGS[1].split()\n"
    "queue = req[1]\n"
    "cp = [sys.executable, os.environ['FAKE_CEPA_PLAN']]\n"
    "repo = ['--repo', os.getcwd()]\n"
    "q = json.loads(subprocess.run(cp + ['queue', queue, '--max', '1', '--json']"
    " + repo, capture_output=True, text=True).stdout)\n"
    "ident = q['batch'][0]['id']\n"
    "subprocess.run(cp + ['start', queue, ident] + repo, check=True,"
    " capture_output=True)\n"
    "open(queue + '-' + ident + '.txt', 'w').write('feito')\n"
    "subprocess.run(['git', 'add', '-A'], check=True)\n"
    "subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                'commit', '-qm', queue + ':' + ident], check=True)\n"
    "subprocess.run(cp + ['finish', queue, ident, '--status', 'done',"
    " '--evidence', 'ok'] + repo, check=True)\n")


def _statuses(path):
    return {str(i["id"]): i["status"]
            for i in yaml.safe_load(path.read_text())["items"]}


def test_all_runs_items_of_two_queues_on_one_branch():
    """CS-2: one run, one `until/<run>` branch, one commit per queue's item,
    each item closed `done` in its own queue.yaml."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1")],
                                  "b": [base.item("b1")]})
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                    "--no-analysis"],
                        claude_body=DONE_IN_ITS_QUEUE)
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        check("a1 fica done na fila a", _statuses(paths["a"]) == {"a1": "done"},
              str(_statuses(paths["a"])))
        check("b1 fica done na fila b", _statuses(paths["b"]) == {"b1": "done"},
              str(_statuses(paths["b"])))
        check("um claude por item: dois subprocessos", len(calls) == 2,
              str(calls))
        branches = _branches(root)
        check("uma só branch until/<run>", len(branches) == 1, str(branches))
        if len(branches) == 1:
            subjects = subprocess.run(
                ["git", "log", "--format=%s", f"HEAD..{branches[0]}"],
                cwd=root, capture_output=True, text=True).stdout.split()
            check("...com os dois commits, um de cada fila",
                  "a:a1" in subjects and "b:b1" in subjects, str(subjects))


def test_same_id_in_two_queues_both_delivered():
    """The per-item bookkeeping is keyed by (queue, id): two queues with a `CS-1`
    each are two items, both `done`, both in the summary with their queue."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("CS-1")],
                                  "b": [base.item("CS-1")]})
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                    "--no-analysis"],
                        claude_body=DONE_IN_ITS_QUEUE)
        check("rc 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        check("a/CS-1 done", _statuses(paths["a"]) == {"CS-1": "done"})
        check("b/CS-1 done", _statuses(paths["b"]) == {"CS-1": "done"})
        check("dois subprocessos", len(calls) == 2, str(calls))
        check("o resumo lista 2 itens", "Items (2)" in p.stdout, p.stdout[-1500:])
        check("...cada um com a sua fila",
              "a/CS-1" in p.stdout and "b/CS-1" in p.stdout, p.stdout[-1500:])


NO_PROGRESS_ON_B_CS1 = DONE_IN_ITS_QUEUE.replace(
    "subprocess.run(cp + ['start'",
    "if queue == 'b' and ident == 'CS-1':\n    sys.exit(0)\n"
    "subprocess.run(cp + ['start'", 1)


def test_same_id_stuck_in_one_queue_does_not_inherit_the_other_ones_state():
    """a/CS-1 delivered, b/CS-1 makes no progress: b/CS-1 gets its own full
    attempts from 1, the run does not end `item-preso`, b/CS-2 still runs."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("CS-1")],
                                  "b": [base.item("CS-1"), base.item("CS-2")]})
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                    "--no-analysis"],
                        claude_body=NO_PROGRESS_ON_B_CS1)
        out = p.stdout
        check("a/CS-1 fica done", _statuses(paths["a"])["CS-1"] == "done",
              out[-1500:])
        check("b/CS-2 roda e fica done", _statuses(paths["b"])["CS-2"] == "done",
              f"{_statuses(paths['b'])} {out[-1500:]}")
        check("b/CS-1 nao fecha", _statuses(paths["b"])["CS-1"] != "done")
        check("a run nao termina em item-preso", "item-preso" not in out
              and "item-preso" not in p.stderr, out[-1500:])
        b_lines = [ln for ln in out.splitlines() if "b/CS-1" in ln and "left" in ln]
        check("b/CS-1 tem as 2 tentativas, a 1a sem 'attempt' e a 2a 'attempt 2/2'",
              len(b_lines) == 2 and "attempt" not in b_lines[0]
              and "attempt 2/2" in b_lines[1], str(b_lines))
        subjects = subprocess.run(
            ["git", "log", "--format=%s", "--all"], cwd=root,
            capture_output=True, text=True).stdout.split()
        check("o commit de a/CS-1 segue na branch", "a:CS-1" in subjects,
              str(subjects))


def test_done_without_commit_in_one_queue_does_not_taint_the_same_id_in_another():
    """a/CS-1 closes `done` with no commit, then b/CS-1 closes `done` WITH a
    commit: b/CS-1 is a normal delivery, not `done-sem-commit`."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("CS-1")],
                                  "b": [base.item("CS-1")]})
        body = DONE_IN_ITS_QUEUE.replace(
            "open(queue + '-'",
            "if queue == 'a':\n"
            "    subprocess.run(cp + ['finish', queue, ident, '--status',"
            " 'done', '--evidence', 'ok'] + repo, check=True)\n"
            "    sys.exit(0)\n"
            "open(queue + '-'", 1)
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                    "--no-analysis"], claude_body=body)
        out = p.stdout
        check("b/CS-1 fica done", _statuses(paths["b"]) == {"CS-1": "done"},
              out[-1500:])
        ev = [json.loads(ln) for ln in
              next((root / ".claude" / "queues" / "_all" / "until").glob(
                  "*.jsonl")).read_text().splitlines()]
        check("so um done_sem_commit no ledger (o de a)",
              len([e for e in ev if e["evento"] == "done_sem_commit"]) == 1,
              str(ev))
        sem = [ln for ln in out.splitlines()
               if "done-sem-commit" in ln or "no commit" in ln]
        check("b/CS-1 nao e done-sem-commit no resumo",
              not any("b/CS-1" in ln for ln in sem), str(sem) + out[-1500:])


BREAKS_BUILD = DONE_IN_ITS_QUEUE.replace(
    "open(queue + '-' + ident + '.txt', 'w').write('feito')\n",
    "open(queue + '-' + ident + '.txt', 'w').write('feito')\n"
    "open('quebra.txt', 'w').write('x')\n", 1)


def test_same_id_red_in_two_queues_keeps_two_side_branches_and_own_returns():
    """a/CS-1 and b/CS-1 both go red in the same run: each one's commits stay in
    their own side branch (queue in the name), and a/CS-1's red returns do not
    count against b/CS-1 (its first return is 1/N, not blocked at once)."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("CS-1")],
                                  "b": [base.item("CS-1")]})
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--verify",
                                    "test ! -f quebra.txt", "--no-analysis",
                                    "--max-failures", "10"],
                        claude_body=BREAKS_BUILD)
        out = p.stdout
        side = [b for b in _branches(root) if "vermelho" in b]
        check("lateral de a/CS-1 e de b/CS-1 sao branches distintas",
              any("-a-CS-1" in b for b in side)
              and any("-b-CS-1" in b for b in side), str(side))
        for q in ("a", "b"):
            subj = []
            for b in side:
                if f"-{q}-CS-1" in b:
                    subj += subprocess.run(
                        ["git", "log", "--format=%s", b], cwd=root,
                        capture_output=True, text=True).stdout.split()
            check(f"{q}/CS-1: o commit dele esta na lateral dele",
                  f"{q}:CS-1" in subj, f"{subj} {side}")
        ev = [json.loads(ln) for ln in
              next((root / ".claude" / "queues" / "_all" / "until").glob(
                  "*.jsonl")).read_text().splitlines()]
        voltas = [(e.get("fila"), e["volta"]) for e in ev
                  if e["evento"] == "volta_vermelha"]
        check("cada fila tem as voltas 1 e 2, nao 1,2,3,4",
              sorted(voltas) == [("a", 1), ("a", 2), ("b", 1), ("b", 2)],
              f"{voltas} {out[-1500:]}")


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True).stdout


def test_final_commit_holds_the_queue_file_of_every_touched_queue():
    """The run's final record commit (on the clone's branch, not the run branch)
    carries the `queue.yaml` of EVERY queue the run touched, not only the first."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1")],
                                  "b": [base.item("b1")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                "--no-analysis"],
                    claude_body=DONE_IN_ITS_QUEUE)
        check("rc 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        changed = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("o ultimo commit do clone leva a fila a",
              ".claude/queues/a/queue.yaml" in changed, str(changed))
        check("...e a fila b",
              ".claude/queues/b/queue.yaml" in changed, str(changed))
        dirty = _git(root, "status", "--porcelain", "--", ".claude/queues/a/queue.yaml",
                     ".claude/queues/b/queue.yaml")
        check("...e nenhum queue.yaml fica sujo", dirty.strip() == "", dirty)


def test_done_without_commit_is_reported_for_the_queue_that_did_it():
    """a/CS-1 closes `done` with no commit while b/CS-1 closes with one: the
    summary names a/CS-1 as done-without-commit, and the run counts it."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("CS-1")],
                                  "b": [base.item("CS-1")]})
        body = DONE_IN_ITS_QUEUE.replace(
            "open(queue + '-'",
            "if queue == 'a':\n"
            "    subprocess.run(cp + ['finish', queue, ident, '--status',"
            " 'done', '--evidence', 'ok'] + repo, check=True)\n"
            "    sys.exit(0)\n"
            "open(queue + '-'", 1)
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                "--no-analysis"], claude_body=body)
        out = p.stdout
        sem = [ln for ln in out.splitlines()
               if "a/CS-1" in ln and ("done-sem-commit" in ln or "no commit" in ln)]
        check("a/CS-1 aparece como done sem commit no resumo", len(sem) >= 1,
              out[-1800:])


# Fakes for the stuck (`travado`) and stopped (`parado`) paths. Per-(queue, id)
# attempt counter in a file next to the fake's own record, outside the worktree.
ATTEMPT_COUNTER = (
    "import subprocess\n"
    "req = ARGS[1].split()\n"
    "queue = req[1]\n"
    "cp = [sys.executable, os.environ['FAKE_CEPA_PLAN']]\n"
    "repo = ['--repo', os.getcwd()]\n"
    "q = json.loads(subprocess.run(cp + ['queue', queue, '--max', '1', '--json']"
    " + repo, capture_output=True, text=True).stdout)\n"
    "ident = q['batch'][0]['id']\n"
    "cnt = os.path.join(os.path.dirname(os.environ['FAKE_CHAMADAS']),"
    " 'n-' + queue + '-' + ident)\n"
    "n = int(open(cnt).read()) + 1 if os.path.exists(cnt) else 1\n"
    "open(cnt, 'w').write(str(n))\n"
    "def commit(tag):\n"
    "    open(queue + '-' + ident + '-' + tag + '.txt', 'w').write('x')\n"
    "    subprocess.run(['git', 'add', '-A'], check=True)\n"
    "    subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',\n"
    "                    'commit', '-qm', queue + ':' + ident + ':' + tag],"
    " check=True)\n")

BLOCKED_WITH_COMMIT = ATTEMPT_COUNTER + (
    "subprocess.run(cp + ['start', queue, ident] + repo, check=True,"
    " capture_output=True)\n"
    "commit('1')\n"
    "subprocess.run(cp + ['finish', queue, ident, '--status', 'blocked',"
    " '--evidence', 'preso', '--blocker', 'o sistema nao responde'] + repo,"
    " check=True)\n")

# Attempts 1 and 2 commit without closing; attempt 3 does nothing.
COMMITS_TWICE_THEN_NOTHING = ATTEMPT_COUNTER + (
    "if n == 1:\n"
    "    subprocess.run(cp + ['start', queue, ident] + repo, check=True,"
    " capture_output=True)\n"
    "if n <= 2:\n"
    "    commit(str(n))\n")


def _side_branches(root, suffix):
    return [b for b in _branches(root) if suffix in b]


def _subjects_of_branch(root, b):
    return _git(root, "log", "--format=%s", b).split()


def test_same_id_stuck_in_two_queues_keeps_two_side_branches():
    """a/CS-1 and b/CS-1 both close `blocked` with a commit: two distinct
    `travado` side branches, each holding its own item's commit."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("CS-1")],
                              "b": [base.item("CS-1")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                "--no-analysis", "--max-blocked", "10"],
                    claude_body=BLOCKED_WITH_COMMIT)
        side = _side_branches(root, "travado")
        check("duas laterais travado distintas", len(side) == 2,
              f"{side} {p.stdout[-1200:]}")
        for q in ("a", "b"):
            own = [b for b in side if f"-{q}-CS-1" in b]
            subj = _subjects_of_branch(root, own[0]) if len(own) == 1 else []
            check(f"{q}/CS-1: a lateral dele tem o commit dele",
                  len(own) == 1 and f"{q}:CS-1:1" in subj, f"{own} {subj}")
            other = "b" if q == "a" else "a"
            check(f"...e nao o commit de {other}/CS-1",
                  f"{other}:CS-1:1" not in subj, str(subj))


def test_same_id_stopped_in_two_queues_keeps_two_side_branches_with_all_attempts():
    """a/CS-1 and b/CS-1 each commit in attempts 1 and 2 without closing, and
    attempt 3 moves nothing: two distinct `parado` side branches, each holding
    the commits of BOTH of its item's attempts (the starting point of the item
    survives between attempts)."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("CS-1")],
                              "b": [base.item("CS-1")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                "--no-analysis", "--max-failures", "10",
                                "--attempts-per-item", "3"],
                    claude_body=COMMITS_TWICE_THEN_NOTHING)
        side = _side_branches(root, "parado")
        check("duas laterais parado distintas", len(side) == 2,
              f"{side} {p.stdout[-1500:]}")
        for q in ("a", "b"):
            own = [b for b in side if f"-{q}-CS-1" in b]
            subj = _subjects_of_branch(root, own[0]) if len(own) == 1 else []
            check(f"{q}/CS-1: a lateral dele tem os commits das duas tentativas",
                  len(own) == 1 and f"{q}:CS-1:1" in subj
                  and f"{q}:CS-1:2" in subj, f"{own} {subj}")
            other = "b" if q == "a" else "a"
            check(f"...e nada de {other}/CS-1",
                  not any(s.startswith(f"{other}:") for s in subj), str(subj))


def test_all_leaves_side_branches_of_earlier_runs_alone():
    """The cleanup of side branches reads the item ids of ONE queue; in `--all`
    it is skipped. A `vermelho` side branch of an earlier run, whose id is
    `done` in queue a, survives (single-queue it would be deleted), and the
    run still delivers its items."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("old1", status="done"),
                                        base.item("a1")],
                                  "b": [base.item("b1")]})
        old = "until/2026-01-01-0000-vermelho-old1"
        _git(root, "checkout", "-q", "-b", old)
        (root / "l1.txt").write_text("x")
        _git(root, "add", "-A")
        _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit",
             "-qm", "commit of l1")
        _git(root, "checkout", "-q", "-")
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                    "--no-analysis"],
                        claude_body=DONE_IN_ITS_QUEUE)
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        check("a lateral da rodada antiga continua la", old in _branches(root),
              f"{_branches(root)} {p.stdout[-800:]}")
        check("...e nenhum aviso de lateral apagada ou mantida",
              "side branch" not in p.stdout, p.stdout[-800:])
        check("os itens prontos foram entregues",
              _statuses(paths["a"]).get("a1") == "done"
              and _statuses(paths["b"]) == {"b1": "done"},
              f"{_statuses(paths['a'])} {_statuses(paths['b'])}")


def _item_starts(root):
    """The ids of the `item_start` events of the `--all` run's record, in the
    order they were written."""
    records = sorted((root / ".claude" / "queues" / "_all" / "until").glob("*.jsonl"))
    if len(records) != 1:
        return None
    events = [json.loads(l) for l in records[0].read_text().splitlines() if l.strip()]
    return [str(e["id"]) for e in events if e.get("evento") == "item_start"]


def test_item_that_becomes_ready_runs_before_the_next_queue():
    """CS-3: queue by queue, and the ready items are re-read before each item.
    `a2` waits for `a1`, so at launch only `a1` and `b1` are ready; `a2` becomes
    ready when `a1` closes and runs BEFORE the run moves on to queue `b`."""
    with tempfile.TemporaryDirectory() as tmp:
        a2 = base.item("a2")
        a2["blocked_by"] = ["a1"]
        root, paths = _repo(tmp, {"a": [base.item("a1"), a2],
                                  "b": [base.item("b1")]})
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                    "--no-analysis"],
                        claude_body=DONE_IN_ITS_QUEUE)
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        starts = _item_starts(root)
        check("os item_start do registro vêm na ordem a1, a2, b1",
              starts == ["a1", "a2", "b1"], f"{starts} out={p.stdout[-800:]}")
        check("os três itens ficam done",
              _statuses(paths["a"]) == {"a1": "done", "a2": "done"}
              and _statuses(paths["b"]) == {"b1": "done"},
              f"{_statuses(paths['a'])} {_statuses(paths['b'])}")
        check("um claude por item: três subprocessos", len(calls) == 3, str(calls))


# Same fake, but while it works on `b1` the owner's route on `a1` closes: the
# fake clears `human_pending` of `a1` in the clone's queue file, the way an
# answer given during the run would.
A1_ROUTE_CLOSES_DURING_B1 = DONE_IN_ITS_QUEUE.replace(
    "subprocess.run(cp + ['start'",
    "if queue == 'b' and ident == 'b1':\n"
    "    import yaml\n"
    "    common = subprocess.run(['git', 'rev-parse', '--path-format=absolute',"
    " '--git-common-dir'], capture_output=True, text=True).stdout.strip()\n"
    "    qa = os.path.join(os.path.dirname(common), '.claude', 'queues', 'a',"
    " 'queue.yaml')\n"
    "    plan = yaml.safe_load(open(qa, encoding='utf-8'))\n"
    "    plan['items'][0]['human_pending'] = None\n"
    "    open(qa, 'w', encoding='utf-8').write(yaml.safe_dump(plan,"
    " allow_unicode=True))\n"
    "subprocess.run(cp + ['start'", 1)


def test_item_that_becomes_ready_in_an_earlier_queue_runs_next():
    """CS-3, the spec's "decided without asking": the run always takes the first
    ready item in `ready` order, even when it shows up in a queue BEFORE the
    current one. `a1` starts with an open owner route (not ready), so the run
    starts on queue `b`; the route closes during `b1`, and `a1` runs before
    `b2`."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1", human_pending="validar à mão")],
                                  "b": [base.item("b1"), base.item("b2")]})
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                    "--no-analysis"],
                        claude_body=A1_ROUTE_CLOSES_DURING_B1)
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        starts = _item_starts(root)
        check("os item_start do registro vêm na ordem b1, a1, b2",
              starts == ["b1", "a1", "b2"], f"{starts} out={p.stdout[-800:]}")
        check("os três itens ficam done",
              _statuses(paths["a"]) == {"a1": "done"}
              and _statuses(paths["b"]) == {"b1": "done", "b2": "done"},
              f"{_statuses(paths['a'])} {_statuses(paths['b'])}")


def _live_run_of_queue(root, queue, pid, run="2026-11-15-0900"):
    """The state and the record of a single-queue run of `queue` that is up:
    `rodando`, a live pid, this host, as the real `cepa-until` leaves them."""
    import socket
    from datetime import datetime, timedelta
    d = root / ".claude" / "queues" / queue / "until"
    d.mkdir(parents=True, exist_ok=True)
    deadline = (datetime.now() + timedelta(hours=3)).isoformat()
    (d / f"{run}.estado.json").write_text(json.dumps(
        {"run": run, "fila": queue, "estado": "rodando", "branch": "until/x",
         "registro": f"{run}.jsonl", "pid": pid, "host": socket.gethostname(),
         "prazo": deadline}), encoding="utf-8")
    (d / f"{run}.jsonl").write_text(json.dumps(
        {"evento": "run_start", "fila": queue, "prazo": deadline, "pid": pid})
        + "\n", encoding="utf-8")
    return run


def test_queue_with_its_own_live_run_is_skipped_with_a_warning():
    """CS-4: queue `a` has a live single-queue run: the `--all` run warns naming
    `a` and its run, starts no item of `a`, and finishes `b1` as `done`."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1")],
                                  "b": [base.item("b1")]})
        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(120)", "cepa-until"])
        try:
            run = _live_run_of_queue(root, "a", alive.pid)
            p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                        "--no-analysis"],
                            claude_body=DONE_IN_ITS_QUEUE)
        finally:
            alive.kill()
            alive.wait()
        out = p.stdout + p.stderr
        warn = [l for l in out.splitlines() if "skipping queue" in l]
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        check("avisa que pula a fila a, com o run dela",
              any("`a`" in l for l in warn) and any(run in l for l in warn),
              f"{warn} {out[-800:]}")
        check("...avisa uma vez so", len(warn) == 1, str(warn))
        check("o aviso nomeia o pid do run vivo",
              any(f"pid {alive.pid}" in l for l in warn), str(warn))
        check("o aviso vai para o stderr, nao para o stdout",
              "skipping queue" in p.stderr and "skipping queue" not in p.stdout,
              f"err={p.stderr[-500:]} out={p.stdout[-500:]}")
        check("b1 fica done", _statuses(paths["b"]) == {"b1": "done"},
              str(_statuses(paths["b"])))
        check("a1 nao e tocado", _statuses(paths["a"]) == {"a1": "pending"},
              str(_statuses(paths["a"])))
        check("nenhum item_start de a", _item_starts(root) == ["b1"],
              str(_item_starts(root)))
        check("um so subprocesso, o de b1", len(calls) == 1, str(calls))


def _blocked_when(cond):
    """A fake `claude` that commits and closes the item `blocked` when `cond`
    (a Python expression over `queue` and `ident`) holds, `done` otherwise."""
    return ATTEMPT_COUNTER + (
        "subprocess.run(cp + ['start', queue, ident] + repo, check=True,"
        " capture_output=True)\n"
        "commit('1')\n"
        f"st = 'blocked' if ({cond}) else 'done'\n"
        "extra = ['--blocker', 'o sistema nao responde'] if st == 'blocked'"
        " else []\n"
        "subprocess.run(cp + ['finish', queue, ident, '--status', st,"
        " '--evidence', 'x'] + extra + repo, check=True)\n")


BLOCKED_IN_A = _blocked_when("queue == 'a'")


def _run_events(root):
    records = sorted((root / ".claude" / "queues" / "_all" / "until").glob("*.jsonl"))
    out = []
    for r in records:
        out += [json.loads(l) for l in r.read_text().splitlines() if l.strip()]
    return out


def test_queue_blocked_max_times_leaves_the_run_and_the_others_carry_on():
    """CS-5: `a` has three items that close `blocked`, `b` has one that closes
    `done`; with `--max-blocked 3` queue `a` leaves the run (a line says so) and
    `b1` still finishes `done`."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1"), base.item("a2"),
                                        base.item("a3")],
                                  "b": [base.item("b1")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--max-blocked", "3",
                                "--no-verify", "--no-analysis"],
                    claude_body=BLOCKED_IN_A)
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        left = [l for l in p.stdout.splitlines()
                if "`a`" in l and "left the run" in l]
        check("uma linha diz que a fila a saiu do run", len(left) == 1,
              p.stdout[-1500:])
        check("...e nomeia os itens travados",
              len(left) == 1 and all(i in left[0] for i in ("a1", "a2", "a3")),
              str(left))
        check("b1 fica done", _statuses(paths["b"]) == {"b1": "done"},
              str(_statuses(paths["b"])))
        check("a1..a3 ficam blocked",
              _statuses(paths["a"]) == {"a1": "blocked", "a2": "blocked",
                                        "a3": "blocked"},
              str(_statuses(paths["a"])))
        check("o run nao termina por fila-travada",
              "fila-travada" not in p.stdout, p.stdout[-1500:])


def test_queue_that_left_the_run_starts_no_more_items():
    """CS-5: `a` has four ready items and `--max-blocked 3`: a4 stays `pending`
    and has no `item_start`; without the exclusion it would be the next item."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item(f"a{i}") for i in range(1, 5)],
                                  "b": [base.item("b1")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--max-blocked", "3",
                                "--no-verify", "--no-analysis"],
                    claude_body=BLOCKED_IN_A)
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        check("a4 fica pending", _statuses(paths["a"]).get("a4") == "pending",
              str(_statuses(paths["a"])))
        check("nenhum item_start de a4", "a4" not in _item_starts(root),
              str(_item_starts(root)))
        check("b1 fica done", _statuses(paths["b"]) == {"b1": "done"},
              str(_statuses(paths["b"])))


def test_blocked_streak_is_counted_per_queue():
    """CS-5: two `blocked` in `a` and one in `b` are three in the run but two
    and one per queue: no queue leaves and the run does not end `fila-travada`."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1"), base.item("a2")],
                                  "b": [base.item("blk1"), base.item("b2")]})
        body = _blocked_when("queue == 'a' or ident.startswith('blk')")
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--max-blocked", "3",
                                "--no-verify", "--no-analysis"], claude_body=body)
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        check("nenhuma fila sai do run", "left the run" not in p.stdout,
              p.stdout[-1500:])
        check("o run nao termina por fila-travada",
              "fila-travada" not in p.stdout, p.stdout[-1500:])
        check("b2 fica done", _statuses(paths["b"]).get("b2") == "done",
              str(_statuses(paths["b"])))
        check("a1 e a2 ficam blocked",
              _statuses(paths["a"]) == {"a1": "blocked", "a2": "blocked"},
              str(_statuses(paths["a"])))
        ends = [e for e in _run_events(root) if e.get("evento") == "run_end"]
        check("o run_end tem filas_fora vazio quando nenhuma fila saiu",
              len(ends) == 1 and ends[0].get("filas_fora") == [], str(ends))


def test_run_record_carries_the_queue_that_left():
    """CS-5: the run record has a `fila_saiu_do_run` event naming queue `a`, its
    blocked items and the limit."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("a1"), base.item("a2")],
                              "b": [base.item("b1")]})
        _run(tmp, root, ["--all", "--for", "1h", "--max-blocked", "2",
                         "--no-verify", "--no-analysis"],
             claude_body=BLOCKED_IN_A)
        ev = [e for e in _run_events(root) if e.get("evento") == "fila_saiu_do_run"]
        check("um evento fila_saiu_do_run", len(ev) == 1, str(ev))
        if len(ev) == 1:
            check("...com a fila, os itens e o limite",
                  ev[0].get("fila") == "a" and ev[0].get("itens") == ["a1", "a2"]
                  and ev[0].get("max_travados") == 2, str(ev[0]))
        ends = [e for e in _run_events(root) if e.get("evento") == "run_end"]
        check("o run_end lista a fila que saiu em filas_fora",
              len(ends) == 1 and ends[0].get("filas_fora") == ["a"], str(ends))


def test_a_done_item_resets_the_blocked_streak_of_its_queue():
    """CS-5: in `a`, blocked, done, blocked, blocked with `--max-blocked 3`: the
    `done` in the middle resets the streak (the streak ends at 2), so `a` does not leave, all four items start and the run does not end
    `fila-travada`. Without the reset the streak would hit 3 at a4."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item(f"a{i}") for i in range(1, 5)],
                                  "b": [base.item("b1")]})
        body = _blocked_when("queue == 'a' and ident != 'a2'")
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--max-blocked", "3",
                                "--no-verify", "--no-analysis"], claude_body=body)
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        check("nenhuma fila sai do run", "left the run" not in p.stdout,
              p.stdout[-1500:])
        check("nenhum evento fila_saiu_do_run",
              not [e for e in _run_events(root)
                   if e.get("evento") == "fila_saiu_do_run"])
        check("os quatro itens de a comecam",
              all(i in _item_starts(root) for i in ("a1", "a2", "a3", "a4")),
              str(_item_starts(root)))
        check("a: blocked, done, blocked, blocked",
              _statuses(paths["a"]) == {"a1": "blocked", "a2": "done",
                                        "a3": "blocked", "a4": "blocked"},
              str(_statuses(paths["a"])))
        check("o run nao termina por fila-travada",
              "fila-travada" not in p.stdout, p.stdout[-1500:])


# Like DONE_IN_ITS_QUEUE, but the commit of queue `a`'s items breaks the build
# (the verify is `test ! -f quebra.txt`); queue `b`'s items stay green.
BREAKS_BUILD_IN_A = DONE_IN_ITS_QUEUE.replace(
    "open(queue + '-' + ident + '.txt', 'w').write('feito')\n",
    "open(queue + '-' + ident + '.txt', 'w').write('feito')\n"
    "if queue == 'a':\n"
    "    open('quebra.txt', 'w').write('x')\n", 1)


def test_red_returns_ending_blocked_count_toward_the_queue_leaving_the_run():
    """CS-5: the items of `a` close `done`, the run's build goes red and, after
    the returns run out, each is marked `blocked` (the `back_now` path). With
    `--max-blocked 2` queue `a` leaves the run after a2, a3 never starts, `b1`
    ends `done` and the run does not end `fila-travada`."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1"), base.item("a2"),
                                        base.item("a3")],
                                  "b": [base.item("b1")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--max-blocked", "2",
                                "--max-failures", "50", "--verify",
                                "test ! -f quebra.txt", "--no-analysis"],
                    claude_body=BREAKS_BUILD_IN_A)
        check("--all sai com 0", p.returncode == 0,
              f"rc={p.returncode} err={p.stderr[-500:]} out={p.stdout[-800:]}")
        left = [l for l in p.stdout.splitlines()
                if "`a`" in l and "left the run" in l]
        check("uma linha diz que a fila a saiu do run", len(left) == 1,
              p.stdout[-1500:])
        check("o evento fila_saiu_do_run existe",
              len([e for e in _run_events(root)
                   if e.get("evento") == "fila_saiu_do_run"
                   and e.get("fila") == "a"]) == 1, str(_run_events(root)[-6:]))
        check("a3 nunca comeca", "a3" not in _item_starts(root),
              str(_item_starts(root)))
        check("a1 e a2 ficam blocked, a3 pending",
              _statuses(paths["a"]) == {"a1": "blocked", "a2": "blocked",
                                        "a3": "pending"},
              str(_statuses(paths["a"])))
        check("b1 fica done", _statuses(paths["b"]) == {"b1": "done"},
              f"{_statuses(paths['b'])} {p.stdout[-1500:]}")
        check("o run nao termina por fila-travada",
              "fila-travada" not in p.stdout, p.stdout[-1500:])


def test_single_queue_red_returns_ending_blocked_end_the_run_fila_travada():
    """CS-5: the same red-return path in a single-queue run keeps the old
    behavior: the run ends `fila-travada` and no queue "leaves the run"."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1"), base.item("a2"),
                                        base.item("a3")]})
        p, _ = _run(tmp, root, ["a", "--for", "1h", "--max-blocked", "2",
                                "--max-failures", "50", "--verify",
                                "test ! -f quebra.txt", "--no-analysis"],
                    claude_body=BREAKS_BUILD_IN_A)
        check("o run termina por fila-travada", "fila-travada" in p.stdout,
              f"rc={p.returncode} {p.stdout[-1500:]}")
        check("nenhuma linha de saida de fila", "left the run" not in p.stdout,
              p.stdout[-1500:])
        check("a3 nunca comeca", _statuses(paths["a"]).get("a3") == "pending",
              str(_statuses(paths["a"])))


def test_single_queue_dry_run_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("a1")]})
        p, calls = _run(tmp, root, ["a", "--for", "2h", "--dry-run",
                                    "--no-verify"])
        check("`cepa until a --dry-run` segue saindo com 0", p.returncode == 0,
              p.stderr[-400:])
        check("...e nomeia o item", "a1" in p.stdout)


def _target_command(tmp, root, sub, target, *extra):
    env = dict(os.environ)
    env["CEPA_WORKTREE_HOME"] = str(Path(tmp) / "worktrees")
    return subprocess.run(
        [sys.executable, str(CEPA_UNTIL), sub, target, *extra,
         "--repo", str(root)],
        capture_output=True, text=True, env=env, timeout=120,
        stdin=subprocess.DEVNULL)


def test_target_all_run_reads_the_state_of_the_all_folder():
    """The end-of-run report names a `--all` run `all/<run>`, and its state lives
    in `.claude/queues/_all/until/`. On 2026-11-17 `cepa-until land
    all/2026-11-16-1426 --yes`, copied from that report, exited 2 with "could
    not read the run state at .claude/queues/all/until/...": `land` looked for a
    folder named after the label. The three commands that take `<queue>/<run>`
    have to find the state of the run the report named."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _paths = _repo(tmp, {"a": [base.item("a1")],
                                   "b": [base.item("b1")]})
        p, _calls = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                     "--no-analysis"],
                         claude_body=DONE_IN_ITS_QUEUE)
        check("--all sai com 0", p.returncode == 0, p.stderr[-500:])
        states = sorted((root / ".claude" / "queues" / "_all" / "until").glob(
            "*.estado.json"))
        check("o estado do run fica em _all/until", len(states) == 1, str(states))
        if len(states) != 1:
            return
        run_id = states[0].name.replace(".estado.json", "")
        target = f"all/{run_id}"
        check("o relatório do run manda rodar `land all/<run>`",
              f"cepa-until land {target}" in p.stdout, p.stdout[-1500:])
        for sub in ("land", "decide", "close-dead"):
            r = _target_command(tmp, root, sub, target)
            check(f"`{sub} {target}` lê o estado do run",
                  "could not read the run state" not in r.stderr,
                  f"rc={r.returncode} err={r.stderr[-400:]}")
        r = _target_command(tmp, root, "land", target)
        check("`land all/<run>` sem --yes mostra o plano e sai 0",
              r.returncode == 0 and "nothing was done" in r.stdout,
              f"rc={r.returncode} out={r.stdout[-600:]} err={r.stderr[-400:]}")


# A fake `claude` that leaves the items of queue `a` untouched (no reservation,
# no commit, exit 0: an attempt with no progress) and delivers the others.
NO_PROGRESS_IN_A = ("if ARGS[1].split()[1] == 'a':\n    sys.exit(0)\n"
                    + DONE_IN_ITS_QUEUE)


def test_max_failures_still_ends_the_whole_all_run():
    """Q8, the other half: the per-queue limit is `--max-blocked` only. Items of
    `a` that do not move trip the circuit breaker (`--max-failures`), which ends
    the WHOLE `--all` run: queue `a` does not "leave", and `b1` never starts."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1"), base.item("a2"),
                                        base.item("a3")],
                                  "b": [base.item("b1")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--max-failures", "2",
                                "--max-blocked", "1", "--no-verify",
                                "--no-analysis"], claude_body=NO_PROGRESS_IN_A)
        events = _run_events(root)
        ends = [e for e in events if e.get("evento") == "run_end"]
        check("o run inteiro termina por `disjuntor`",
              len(ends) == 1 and ends[0].get("motivo") == "disjuntor",
              f"{ends} out={p.stdout[-1200:]} err={p.stderr[-500:]}")
        check("...nenhuma fila sai do run: sem linha e sem evento",
              "left the run" not in p.stdout
              and not [e for e in events if e.get("evento") == "fila_saiu_do_run"]
              and len(ends) == 1 and ends[0].get("filas_fora") == [],
              f"{ends} {p.stdout[-1200:]}")
        check("...b1 segue pending: o run nao passou para a fila b",
              _statuses(paths["b"]) == {"b1": "pending"},
              str(_statuses(paths["b"])))
        check("...nenhum item_start de b",
              "b1" not in (_item_starts(root) or []), str(_item_starts(root)))



# ── CS-6: the record lives in `_all/until/` and `pending`, `decide`, `land` and
# `close-dead` take the target `all/<run>` ──────────────────────────────────

def _all_run_id(root):
    states = sorted((root / ".claude" / "queues" / "_all" / "until").glob(
        "*.estado.json"))
    return states[-1].name.replace(".estado.json", "") if states else None


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True,
                          text=True).stdout


def _stuck(ident, question):
    """An item a previous run left `blocked`, with the closed question for the
    owner."""
    it = base.item(ident, status="blocked")
    it["owner_question"] = question
    it["evidence"] = "travou no ambiente"
    return it


def test_cs6_record_in_all_folder_pending_lists_it_and_land_yes_lands():
    """The spec's own script: after a `--all` run the record is
    `.claude/queues/_all/until/<run>.jsonl`, `cepa until pending` lists
    `all/<run>` and `cepa until land all/<run> --yes` lands the branch."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _paths = _repo(tmp, {"a": [base.item("a1")],
                                   "b": [base.item("b1")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                "--no-analysis"], claude_body=DONE_IN_ITS_QUEUE)
        run_id = _all_run_id(root)
        check("o run grava o estado em _all/until", run_id is not None,
              p.stderr[-500:])
        if run_id is None:
            return
        folder = root / ".claude" / "queues" / "_all" / "until"
        check("o registro e _all/until/<run>.jsonl",
              (folder / f"{run_id}.jsonl").is_file(), str(sorted(folder.iterdir())))
        check("...e nenhuma pasta `all` e criada",
              not (root / ".claude" / "queues" / "all").exists())
        target = f"all/{run_id}"
        r = subprocess.run([str(CEPA), "until", "pending", "--repo", str(root)],
                           capture_output=True, text=True, timeout=60)
        check("`cepa until pending` lista all/<run> com o comando do land",
              r.returncode == 0 and f"cepa-until land {target}" in r.stdout
              and f"queue all · run {run_id}" in r.stdout,
              f"rc={r.returncode} out={r.stdout} err={r.stderr[-300:]}")
        r = _target_command(tmp, root, "land", target, "--yes")
        check("`land all/<run> --yes` sai com 0", r.returncode == 0,
              f"rc={r.returncode} out={r.stdout[-600:]} err={r.stderr[-400:]}")
        subjects = _git(root, "log", "--format=%s", "main").splitlines()
        check("...os commits das duas filas estao na main",
              "a:a1" in subjects and "b:b1" in subjects, str(subjects))
        check("...a branch do run foi removida", _branches(root) == [],
              str(_branches(root)))
        r = subprocess.run([str(CEPA), "until", "pending", "--repo", str(root)],
                           capture_output=True, text=True, timeout=60)
        check("...e o run sai do `pending`", target not in r.stdout, r.stdout)


def test_cs6_decide_all_run_lists_what_every_queue_holds_for_the_owner():
    """`decide all/<run>` outside a terminal lists the landing and the questions
    of EVERY queue, each item named `queue/id`. Before, it asked `cepa-plan`
    for a queue called `all` and printed "could not list the deferred items"."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _paths = _repo(tmp, {
            "a": [_stuck("x1", "Fecho o card da fila a?")],
            "b": [base.item("b1"), _stuck("x1", "Fecho o card da fila b?")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                "--no-analysis"], claude_body=DONE_IN_ITS_QUEUE)
        run_id = _all_run_id(root)
        check("o run termina e grava o estado", p.returncode == 0
              and run_id is not None, p.stderr[-500:])
        if run_id is None:
            return
        check("o fim do run --all lista o que espera o dono, por fila",
              "waiting on you: 3" in p.stdout
              and "a/x1" in p.stdout and "Fecho o card da fila a?" in p.stdout
              and "b/x1" in p.stdout and "Fecho o card da fila b?" in p.stdout,
              p.stdout[-1500:])
        r = _target_command(tmp, root, "decide", f"all/{run_id}")
        out = r.stdout + r.stderr
        check("`decide all/<run>` sai com 0", r.returncode == 0, out[-600:])
        check("...sem procurar uma fila chamada `all`",
              "could not list the deferred items" not in out, out[-600:])
        check("...conta a aterrissagem e as duas perguntas",
              "waiting on you: 3" in out, out[-800:])
        check("...nomeia o item da fila a com a pergunta dele",
              "a/x1" in out and "Fecho o card da fila a?" in out, out[-800:])
        check("...e o da fila b, mesmo id, com a dele",
              "b/x1" in out and "Fecho o card da fila b?" in out, out[-800:])
        check("...e manda voltar com o alvo all/<run>",
              f"cepa-until decide all/{run_id}" in out, out[-800:])


def test_cs6_decide_all_run_on_a_terminal_answers_each_item_in_its_queue():
    """On a terminal, a "no" to `a/x1` and a "yes" to `b/x1` are recorded each in
    its own queue (same id, two queues), and `decide` commits both queue files
    under the name of the `all/<run>` run."""
    import test_cepa_until_decide as dec
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {
            "a": [_stuck("x1", "Fecho o card da fila a?")],
            "b": [base.item("b1"), _stuck("x1", "Fecho o card da fila b?")]})
        _run(tmp, root, ["--all", "--for", "1h", "--no-verify", "--no-analysis"],
             claude_body=DONE_IN_ITS_QUEUE)
        run_id = _all_run_id(root)
        check("o run grava o estado", run_id is not None)
        if run_id is None:
            return
        env = dict(os.environ)
        for k in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_BIN_PATH", "HC_TERMINAL_ID"):
            env.pop(k, None)
        env["CEPA_WORKTREE_HOME"] = str(Path(tmp) / "worktrees")
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", f"all/{run_id}",
               "--repo", str(root)]
        rc, out = dec.on_tty(cmd, str(root), env=env, timeout=90, inputs=[
            ("Land now?", "n"),
            ("[t] I write the answer", "n"), ("Anything to add", ""),
            ("[t] I write the answer", "s"), ("Anything to add", "")])
        check("decide all/<run> no terminal sai com 0", rc == 0, out[-1200:])
        check("...os itens aparecem como fila/id",
              "a/x1" in out and "b/x1" in out, out[-1500:])
        items_a = {str(i["id"]): i for i in
                   yaml.safe_load(paths["a"].read_text())["items"]}
        items_b = {str(i["id"]): i for i in
                   yaml.safe_load(paths["b"].read_text())["items"]}
        check("o `não` fica no x1 da fila a, que segue blocked",
              items_a["x1"]["status"] == "blocked"
              and "não: Fecho o card da fila a?" in str(items_a["x1"]["evidence"]),
              str(items_a["x1"]))
        check("o `sim` devolve o x1 da fila b para a fila",
              items_b["x1"]["status"] == "pending"
              and "sim: Fecho o card da fila b?" in str(items_b["x1"]["evidence"]),
              str(items_b["x1"]))
        subject = _git(root, "log", "-1", "--format=%s").strip()
        check("o commit leva o nome do run all/<run>",
              subject.startswith(f"until all/{run_id} decide:"), subject)
        files = _git(root, "show", "--name-only", "--format=", "HEAD").split()
        check("...com o queue.yaml das duas filas",
              ".claude/queues/a/queue.yaml" in files
              and ".claude/queues/b/queue.yaml" in files, str(files))
        dirty = _git(root, "status", "--short", "--", ".claude/queues/a/queue.yaml",
                     ".claude/queues/b/queue.yaml")
        check("...e as filas ficam sem mudanca solta", dirty.strip() == "", dirty)


def test_cs6_land_all_run_keeps_the_queue_files_the_clone_has_modified():
    """`land all/<run> --yes` knows the queue files of EVERY queue of the run are
    the run's own marks: with `a` and `b` both modified (uncommitted) in the
    clone, it lands anyway and the modifications are still there afterwards."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1")], "b": [base.item("b1")]})
        _run(tmp, root, ["--all", "--for", "1h", "--no-verify", "--no-analysis"],
             claude_body=DONE_IN_ITS_QUEUE)
        run_id = _all_run_id(root)
        check("o run grava o estado", run_id is not None)
        if run_id is None:
            return
        mark = "# alteracao local nao commitada\n"
        for q in ("a", "b"):
            f = root / ".claude" / "queues" / q / "queue.yaml"
            f.write_text(f.read_text() + mark)
        r = _target_command(tmp, root, "land", f"all/{run_id}", "--yes")
        check("`land all/<run> --yes` com as duas filas modificadas sai com 0",
              r.returncode == 0,
              f"rc={r.returncode} out={r.stdout[-600:]} err={r.stderr[-400:]}")
        subjects = _git(root, "log", "--format=%s", "main").splitlines()
        check("...aterrissa os commits das duas filas",
              "a:a1" in subjects and "b:b1" in subjects, str(subjects))
        for q in ("a", "b"):
            f = root / ".claude" / "queues" / q / "queue.yaml"
            check(f"...e a modificacao da fila {q} continua no clone",
                  f.read_text().endswith(mark), f.read_text()[-200:])


def _tty_env(tmp):
    env = dict(os.environ)
    for k in ("HERDR_ENV", "HERDR_PANE_ID", "HERDR_BIN_PATH", "HC_TERMINAL_ID"):
        env.pop(k, None)
    env["CEPA_WORKTREE_HOME"] = str(Path(tmp) / "worktrees")
    return env


def test_cs6_all_run_on_a_terminal_only_lists_at_the_end_and_never_asks():
    """A `--all` run with a terminal and an item waiting on the owner: the end
    LISTS the question and points to `decide all/<run>`; it does not open the
    panel (which would answer into queues the run did not commit). Bounded: a
    prompt that waits is killed by `on_tty` at its timeout and counts as a
    failure, the answer wait is 20 s."""
    import time
    import test_cepa_until_decide as dec
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {
            "a": [_stuck("x1", "Fecho o card da fila a?")],
            "b": [base.item("b1")]})
        binv = base.fake_claude(tmp, DONE_IN_ITS_QUEUE)
        env = _tty_env(tmp)
        env["PATH"] = f"{binv}:{env['PATH']}"
        env["FAKE_PLANO"] = str(Path(tmp) / "nenhum.yaml")
        env["FAKE_CHAMADAS"] = str(Path(tmp) / "chamadas.jsonl")
        env["CEPA_UNTIL_LEITOR"] = "off"
        env["FAKE_CEPA_PLAN"] = str(REPO / "common" / "bin" / "cepa-plan")
        env["CEPA_UNTIL_ESPERA_RESPOSTA"] = "20"
        t0 = time.time()
        rc, out = dec.on_tty(
            [sys.executable, str(CEPA_UNTIL), "--all", "--for", "1h",
             "--no-verify", "--no-analysis", "--no-pre-read",
             "--no-resume-on-answer", "--repo", str(root)], str(root),
            inputs=[], env=env, timeout=45)
        took = time.time() - t0
        plain = dec.ANSI.sub("", out)
        check("--all no terminal sai com 0 sem esperar resposta",
              rc == 0 and "on_tty: no answer" not in plain, plain[-1500:])
        check("...termina logo, sem esperar o dono (<15 s de espera)",
              took < 40, f"{took:.0f}s")
        check("...lista a pergunta da fila a",
              "Fecho o card da fila a?" in plain, plain[-1500:])
        run_id = _all_run_id(root)
        check("...e manda voltar com `decide all/<run>`",
              run_id is not None and f"cepa-until decide all/{run_id}" in plain,
              plain[-1500:])
        check("...sem abrir o painel de perguntas",
              "[t] I write the answer" not in plain
              and "Land now?" not in plain and "nobody answered" not in plain,
              plain[-1500:])
        check("...e o item segue como estava",
              _statuses(paths["a"]) == {"x1": "blocked"}
              and "travou no ambiente" in paths["a"].read_text(),
              paths["a"].read_text())


def test_cs6_decide_all_run_reword_lands_in_the_queue_of_the_item():
    """On a terminal, `?` on the question of `b/x1` (same id as `a/x1`) has the
    reader reword it and the new question is recorded in queue `b`'s item, not
    in a queue called `all` and not in `a`."""
    import test_cepa_until_decide as dec
    new_q = "Você já fechou o card da fila b no Jira?"
    with tempfile.TemporaryDirectory() as tmp:
        def routed(ident, question):
            it = _stuck(ident, question)
            it["human_pending"] = "fechar o card"
            it["route_kind"] = "external-block"
            return it
        root, paths = _repo(tmp, {"a": [routed("x1", "Fecho o card da fila a?")],
                                  "b": [base.item("b1"),
                                        routed("x1", "Fecho o card da fila b?")]})
        _run(tmp, root, ["--all", "--for", "1h", "--no-verify", "--no-analysis"],
             claude_body=DONE_IN_ITS_QUEUE)
        run_id = _all_run_id(root)
        check("o run grava o estado", run_id is not None)
        if run_id is None:
            return
        reader = Path(tmp) / "leitor.py"
        reader.write_text(
            f"#!{sys.executable}\n"
            "import json, sys\n"
            "it = json.load(sys.stdin)\n"
            "if it.get('tarefa') == 'reescrever-pergunta':\n"
            f"    print(json.dumps({{'route_kind': 'owner-task', 'question': {new_q!r},\n"
            "        'if_yes': 'O item volta para a fila.',\n"
            "        'if_no': 'O item continua esperando.'}))\n"
            "else:\n"
            "    print(json.dumps({'tipo': None}))\n")
        reader.chmod(0o755)
        env = _tty_env(tmp)
        env["CEPA_UNTIL_LEITOR"] = str(reader)
        env["CEPA_FEEDBACK_DIR"] = str(Path(tmp) / "feedback")
        before_a = paths["a"].read_text()
        cmd = [sys.executable, str(CEPA_UNTIL), "decide", f"all/{run_id}",
               "--repo", str(root)]
        rc, out = dec.on_tty(cmd, str(root), env=env, timeout=90, inputs=[
            ("Land now?", "n"),
            ("[t] I write the answer", ""),
            ("[t] I write the answer", "?"),
            ("[t] I write the answer", "")])
        plain = dec.ANSI.sub("", out)
        check("decide all/<run> com `?` sai com 0", rc == 0, plain[-1500:])
        items_b = {str(i["id"]): i for i in
                   yaml.safe_load(paths["b"].read_text())["items"]}
        check("a pergunta reescrita fica no x1 da fila b",
              items_b["x1"].get("owner_question") == new_q,
              str(items_b["x1"]) + plain[-1200:])
        check("...e a fila a nao mudou",
              paths["a"].read_text() == before_a, paths["a"].read_text())
        check("...nenhuma fila `all` foi criada",
              not (root / ".claude" / "queues" / "all").exists())


def _all_night_that_died(tmp):
    """A real `--all` run (a1 and b1 delivered) with the state and the record
    rewound to where a supervisor dies: `rodando`, dead pid, the record cut at
    the `item_start` of `b1` (no `item_end`, no `run_end`)."""
    import socket
    import test_cepa_until_dead_supervisor as dead
    root, paths = _repo(tmp, {"a": [base.item("a1")], "b": [base.item("b1")]})
    _run(tmp, root, ["--all", "--for", "1h", "--no-verify", "--no-analysis"],
         claude_body=DONE_IN_ITS_QUEUE)
    folder = root / ".claude" / "queues" / "_all" / "until"
    jsonl = sorted(folder.glob("*.jsonl"))[-1]
    events = [json.loads(l) for l in jsonl.read_text().splitlines() if l.strip()]
    cut = next(i for i, e in enumerate(events)
               if e["evento"] == "item_start" and str(e["id"]) == "b1")
    jsonl.write_text("".join(json.dumps(e) + "\n" for e in events[:cut + 1]))
    state_file = sorted(folder.glob("*.estado.json"))[-1]
    state = json.loads(state_file.read_text())
    state.update(estado="rodando", pid=dead.dead_pid(), host=socket.gethostname())
    for k in ("acoes", "fica_com_voce", "itens", "motivo_fim"):
        state.pop(k, None)
    state_file.write_text(json.dumps(state))
    return root, paths, state_file.name.replace(".estado.json", ""), events[cut]


def test_cs6_close_dead_all_run_closes_it_and_leaves_it_ready_to_land():
    """A `--all` run whose supervisor died: `pending` points at
    `close-dead all/<run>` and reads the in-flight item in ITS queue (not in a
    queue called `all`), `close-dead all/<run> --yes` closes the record in
    `_all/until/`, commits it, and `land all/<run> --yes` then lands."""
    with tempfile.TemporaryDirectory() as tmp:
        root, _paths, run_id, start = _all_night_that_died(tmp)
        target = f"all/{run_id}"
        check("o item_start de um run --all leva a fila do item",
              start.get("fila") == "b", str(start))
        r = subprocess.run([sys.executable, str(CEPA_UNTIL), "pending", "--json",
                            "--repo", str(root)], capture_output=True, text=True,
                           timeout=60)
        dead_ones = (json.loads(r.stdout) if r.returncode == 0 else {}).get(
            "mortos") or []
        check("pending acusa o run morto com o comando close-dead all/<run>",
              len(dead_ones) == 1
              and dead_ones[0].get("fechar") == f"cepa-until close-dead {target}",
              r.stdout + r.stderr)
        m = dead_ones[0] if dead_ones else {}
        check("...o item em voo e b/b1, lido na fila b: `done`",
              m.get("item") == "b/b1" and m.get("status") == "done", str(m))
        r = _target_command(tmp, root, "close-dead", target)
        check("sem --yes mostra o plano e nao muda nada",
              r.returncode == 0 and f"close-dead {target} --yes" in r.stdout,
              r.stdout + r.stderr)
        r = _target_command(tmp, root, "close-dead", target, "--yes")
        check("`close-dead all/<run> --yes` sai com 0", r.returncode == 0,
              r.stdout + r.stderr)
        events = _run_events(root)
        check("...fecha o registro de _all/until com run_end",
              events and events[-1].get("evento") == "run_end"
              and events[-1].get("motivo") == "supervisor-morto", str(events[-2:]))
        state = json.loads((root / ".claude" / "queues" / "_all" / "until"
                            / f"{run_id}.estado.json").read_text())
        check("...o estado vira esperando-dono com `land all/<run>`",
              state.get("estado") == "esperando-dono"
              and any(f"cepa-until land {target}" in str(x.get("comando"))
                      for x in state.get("acoes") or []), str(state))
        record = f".claude/queues/_all/until/{run_id}.jsonl"
        check("...e o registro fechado entra num commit do run all/<run>",
              _git(root, "status", "--short", "--", record).strip() == ""
              and _git(root, "log", "-1", "--format=%s", "--", record).strip()
              .startswith(f"until {target} close-dead:"),
              _git(root, "status", "--short") + _git(root, "log", "-3",
                                                      "--format=%s"))
        r = _target_command(tmp, root, "land", target, "--yes")
        subjects = _git(root, "log", "--format=%s", "main").splitlines()
        check("...e `land all/<run> --yes` aterrissa o run fechado",
              r.returncode == 0 and "a:a1" in subjects and "b:b1" in subjects,
              f"rc={r.returncode} {r.stdout[-500:]} {r.stderr[-300:]} {subjects}")


def _launch_all_on_tty(tmp, root, inputs, wait="20", extra=()):
    """`cepa-until --all` on a pseudo-terminal, with the launch panel on (no
    `--no-pre-read`, the reader off). Returns (rc, plain output, run events)."""
    import test_cepa_until_decide as dec
    binv = base.fake_claude(tmp, DONE_IN_ITS_QUEUE)
    env = _tty_env(tmp)
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(Path(tmp) / "nenhum.yaml")
    env["FAKE_CHAMADAS"] = str(Path(tmp) / "chamadas.jsonl")
    env["CEPA_UNTIL_LEITOR"] = "off"
    env["FAKE_CEPA_PLAN"] = str(REPO / "common" / "bin" / "cepa-plan")
    env["CEPA_UNTIL_ESPERA_RESPOSTA"] = wait
    rc, out = dec.on_tty(
        [sys.executable, str(CEPA_UNTIL), "--all", "--for", "1h", "--no-verify",
         "--no-analysis", "--no-resume-on-answer", *extra, "--repo", str(root)],
        str(root), inputs=inputs, env=env, timeout=90)
    return rc, dec.ANSI.sub("", out), _run_events(root)


def _owner_item(ident, route, question):
    it = base.item(ident, human_pending=route)
    it["route_kind"] = "owner-task"
    it["owner_question"] = question
    return it


def test_cs7_launch_panel_is_one_panel_grouped_by_queue_and_yes_runs_the_item():
    """The spec's own script: queue `a` and queue `b` each hold one item with an
    open owner route; `cepa until --all --for 1h` on a terminal shows ONE panel
    with a section per queue, and "yes" to the item of `a` makes it run in this
    run (`item_start` with `fila: a`), while the "no" to `b` keeps it waiting."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {
            "a": [_owner_item("a1", "liberar o acesso da fila a",
                              "Liberei o acesso da fila a?")],
            "b": [_owner_item("b1", "liberar o acesso da fila b",
                              "Liberei o acesso da fila b?")]})
        rc, out, events = _launch_all_on_tty(tmp, root, [
            ("[t] I write the answer", "s"), ("Anything to add", ""),
            ("[t] I write the answer", "n"), ("Anything to add", "")])
        check("--all com painel no terminal sai com 0", rc == 0, out[-1500:])
        check("...um painel único com as duas perguntas",
              out.count("question(s) for you") == 1
              and "2 question(s) for you" in out, out[-2500:])
        sec_a, sec_b = out.find("queue `a`"), out.find("queue `b`")
        check("...com uma seção da fila a antes da seção da fila b",
              0 <= sec_a < sec_b, out[-2500:])
        qa, qb = out.find("Liberei o acesso da fila a?"), \
            out.find("Liberei o acesso da fila b?")
        check("...cada pergunta dentro da seção da sua fila",
              sec_a < qa < sec_b < qb, out[-2500:])
        starts = [(e.get("fila"), e.get("id")) for e in events
                  if e.get("evento") == "item_start"]
        check("o `sim` faz a1 rodar neste run", ("a", "a1") in starts,
              str(events)[-1500:] + out[-800:])
        check("...e o `não` deixa b1 de fora", ("b", "b1") not in starts,
              str(starts))
        check("a1 termina done na fila a", _statuses(paths["a"]) == {"a1": "done"},
              paths["a"].read_text())
        b1 = yaml.safe_load(paths["b"].read_text())["items"][0]
        check("b1 segue esperando o dono com o `não` gravado na fila b",
              b1.get("human_pending") and "não" in str(b1.get("evidence")),
              str(b1))


def test_cs7_launch_panel_without_answer_carries_on_and_says_where_to_answer():
    """Nobody at the terminal: the panel does not hang; one line says so and
    names `cepa-until decide` for the queues, and nothing runs."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a?")],
            "b": [_owner_item("b1", "liberar b", "Liberei b?")]})
        rc, out, events = _launch_all_on_tty(tmp, root, [], wait="2")
        check("sem resposta o --all sai com 0", rc == 0, out[-1500:])
        check("...diz que ninguém respondeu", "nobody answered" in out, out[-1500:])
        check("...e aponta o decide da fila", "cepa-until decide a" in out,
              out[-1500:])
        check("...sem item_start", not any(e.get("evento") == "item_start"
                                           for e in events), str(events))


def test_cs7_launch_panel_skips_a_queue_with_its_own_live_run():
    """A queue with its own live run is out of the `--all` run (CS-4), so its
    questions are not asked in this panel either: that run already asked them."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a?")],
            "b": [_owner_item("b1", "liberar b", "Liberei b?")]})
        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(120)", "cepa-until"])
        try:
            _live_run_of_queue(root, "a", alive.pid)
            rc, out, events = _launch_all_on_tty(tmp, root, [
                ("[t] I write the answer", "s"), ("Anything to add", "")])
        finally:
            alive.kill()
            alive.wait()
        check("sai com 0", rc == 0, out[-1500:])
        # The end of the run lists what still waits (CS-6); only the launch,
        # up to the first item, is the panel.
        launch = out.split("item 1", 1)[0]
        check("...o painel não pergunta pela fila com run vivo",
              "Liberei a?" not in launch and "1 question(s) for you" in launch,
              launch[-2000:])
        starts = [(e.get("fila"), e.get("id")) for e in events
                  if e.get("evento") == "item_start"]
        check("...e o `sim` em b1 faz b1 rodar", ("b", "b1") in starts,
              str(starts) + out[-800:])


def test_cs7_no_pre_read_keeps_the_all_launch_without_panel():
    """`--no-pre-read` skips the launch panel in `--all` too (CS-9 of the spec
    relies on it): nothing is asked and nothing runs."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [_owner_item("a1", "liberar a", "Liberei a?")]})
        rc, out, events = _launch_all_on_tty(tmp, root, [], wait="2",
                                             extra=("--no-pre-read",))
        check("sai com 0", rc == 0, out[-1500:])
        check("...sem painel", "question(s) for you" not in out
              and "nobody answered" not in out, out[-1500:])


def test_cs7_q_ends_the_whole_panel_not_only_the_section_of_its_queue():
    """`q` in the section of `a` ends the panel: the question of `b` is not
    asked, one line says how to answer later, and nothing runs."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a?")],
            "b": [_owner_item("b1", "liberar b", "Liberei b?")]})
        rc, out, events = _launch_all_on_tty(tmp, root, [
            ("[t] I write the answer", "q")], wait="5")
        launch = out.split("── ended", 1)[0]
        check("sai com 0", rc == 0, out[-1500:])
        check("...a pergunta de a foi feita", "Liberei a?" in launch, launch[-1500:])
        check("...o `q` não abre a seção de b",
              "queue `b`" not in launch and "Liberei b?" not in launch,
              launch[-2000:])
        check("...diz onde responder depois, nas duas filas",
              "cepa-until decide a" in launch and "cepa-until decide b" in launch,
              launch[-1500:])
        check("...e nada roda", not any(e.get("evento") == "item_start"
                                        for e in events), str(events))


def test_cs7_a_route_already_answered_no_is_summarized_and_not_asked():
    """A route the owner already answered "no" is not asked again in the
    `--all` panel: one line per queue counts it and names `decide <queue>`,
    and the panel asks only the other queue's question."""
    with tempfile.TemporaryDirectory() as tmp:
        old = _owner_item("a1", "liberar a", "Liberei a?")
        old["evidence"] = "Resposta do dono em 2026-11-10: não: Liberei a?"
        root, paths = _repo(tmp, {
            "a": [old],
            "b": [_owner_item("b1", "liberar b", "Liberei b?")]})
        rc, out, events = _launch_all_on_tty(tmp, root, [
            ("[t] I write the answer", "n"), ("Anything to add", "")], wait="5")
        launch = out.split("── ended", 1)[0]
        check("sai com 0", rc == 0, out[-1500:])
        check("...uma linha resume a rota de a já respondida não",
              "queue `a`: 1 route(s) you already answered" in launch
              and "10/11" in launch and "cepa-until decide a" in launch,
              launch[-2000:])
        check("...a pergunta de a não é feita de novo",
              "Liberei a?" not in launch.split("question(s) for you", 1)[-1],
              launch[-2000:])
        check("...o painel pergunta só a de b",
              "1 question(s) for you" in launch and "Liberei b?" in launch,
              launch[-2000:])


def test_cs7_without_a_terminal_the_all_launch_opens_no_panel():
    """No terminal: the `--all` launch asks nothing (the panel is for a person
    at the terminal); the item that waits for the owner stays as it was."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {
            "a": [_owner_item("a1", "liberar a", "Liberei a?")],
            "b": [base.item("b1")]})
        p, _ = _run(tmp, root, ["--all", "--for", "1h", "--no-verify",
                                "--no-analysis"], claude_body=DONE_IN_ITS_QUEUE)
        launch = p.stdout.split("── ended", 1)[0]
        check("sem terminal sai com 0", p.returncode == 0, p.stderr[-800:])
        check("...sem painel na largada",
              "question(s) for you" not in launch and "Liberei a?" not in launch
              and "nobody answered" not in p.stdout, launch[-1500:])
        check("...b1 roda e a1 segue esperando",
              _statuses(paths["b"]) == {"b1": "done"}
              and _statuses(paths["a"]) == {"a1": "pending"},
              f"{_statuses(paths['a'])} {_statuses(paths['b'])}")


def _live_all_run(root, pid, run="2026-11-17-0900"):
    """The state and the record of a `--all` run that is up, where the real
    `cepa-until` leaves them: `_all/until/`, `fila: all`, a live pid, this host."""
    import socket
    from datetime import datetime, timedelta
    d = root / ".claude" / "queues" / "_all" / "until"
    d.mkdir(parents=True, exist_ok=True)
    deadline = (datetime.now() + timedelta(hours=3)).isoformat()
    (d / f"{run}.estado.json").write_text(json.dumps(
        {"run": run, "fila": "all", "estado": "rodando", "branch": "until/x",
         "registro": f"{run}.jsonl", "pid": pid, "host": socket.gethostname(),
         "prazo": deadline}), encoding="utf-8")
    (d / f"{run}.jsonl").write_text(json.dumps(
        {"evento": "run_start", "fila": "all", "prazo": deadline, "pid": pid})
        + "\n", encoding="utf-8")
    return run


def test_cs8_live_all_run_refuses_a_second_all_and_a_single_queue_run():
    """CS-8: with a `--all` run alive, `cepa until --all --for 1h` and
    `cepa until a --for 1h` exit 2 naming `all/<run>`, and run nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1")],
                                  "b": [base.item("b1")]})
        alive = subprocess.Popen([sys.executable, "-c",
                                  "import time; time.sleep(120)", "cepa-until"])
        try:
            run = _live_all_run(root, alive.pid)
            second_all, calls_all = _run(
                tmp, root, ["--all", "--for", "1h", "--no-verify",
                            "--no-analysis"], claude_body=DONE_IN_ITS_QUEUE)
            single, calls_single = _run(
                tmp, root, ["a", "--for", "1h", "--no-verify", "--no-analysis"],
                claude_body=DONE_IN_ITS_QUEUE)
        finally:
            alive.kill()
            alive.wait()
        for label, p in (("--all", second_all), ("a", single)):
            check(f"{label}: sai com 2", p.returncode == 2,
                  f"rc={p.returncode} out={(p.stdout + p.stderr)[-800:]}")
            check(f"{label}: cita all/<run> no stderr",
                  f"all/{run}" in p.stderr, p.stderr[-800:])
            check(f"{label}: cita o pid do run vivo",
                  f"pid {alive.pid}" in p.stderr, p.stderr[-800:])
        check("nenhum subprocesso roda", calls_all == [] and calls_single == [],
              f"{calls_all} {calls_single}")
        check("nada muda nas filas",
              _statuses(paths["a"]) == {"a1": "pending"}
              and _statuses(paths["b"]) == {"b1": "pending"},
              f"{_statuses(paths['a'])} {_statuses(paths['b'])}")


def test_cs8_dead_all_run_does_not_refuse_a_single_queue_run():
    """CS-8, the other side: an `_all` state `rodando` whose pid died does not
    hold the repo; `cepa until a` runs `a1`."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {"a": [base.item("a1")]})
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        _live_all_run(root, dead.pid)
        p, calls = _run(tmp, root, ["a", "--for", "1h", "--no-verify",
                                    "--no-analysis"],
                        claude_body=DONE_IN_ITS_QUEUE)
        check("a roda com 0", p.returncode == 0,
              f"rc={p.returncode} out={(p.stdout + p.stderr)[-800:]}")
        check("a1 fica done", _statuses(paths["a"]) == {"a1": "done"},
              str(_statuses(paths["a"])))


def test_cs9_nothing_ready_in_any_queue_exits_0_says_so_and_creates_no_branch():
    """CS-9: every queue closed or waiting for the owner, the panel refused
    (`--no-pre-read`): `cepa until --all --for 1h` exits 0, says no queue has a
    ready item, runs nothing and leaves no new `until/*` branch."""
    with tempfile.TemporaryDirectory() as tmp:
        root, paths = _repo(tmp, {
            "a": [base.item("a1", status="done")],
            "b": [base.item("b1", human_pending="validar à mão")]})
        before = {n: p.read_text() for n, p in paths.items()}
        head_before = _git(root, "rev-parse", "HEAD")
        p, calls = _run(tmp, root, ["--all", "--for", "1h", "--no-pre-read",
                                    "--no-verify", "--no-analysis"],
                        claude_body=DONE_IN_ITS_QUEUE)
        out = p.stdout + p.stderr
        check("CS-9: --all sem pronto sai com 0", p.returncode == 0,
              f"rc={p.returncode} out={out[-800:]}")
        check("...diz que nenhuma fila tem item pronto",
              "no queue has a ready item" in out, out[-800:])
        check("...não chama o claude", not calls, str(calls))
        check("...não cria branch until/*", not _branches(root),
              str(_branches(root)))
        check("...não toca nenhuma fila",
              all(paths[n].read_text() == before[n] for n in paths))
        # A run that opened its branch and closed it empty at the end would
        # pass the checks above: what tells the two apart is that the run
        # never started at all.
        check("...diz que o run nem começa (antes de abrir branch)",
              "nothing to do: no item runs, so the run does not start" in out,
              out[-800:])
        check("...o HEAD do clone não muda", _git(root, "rev-parse", "HEAD")
              == head_before)
        all_dir = root / ".claude" / "queues" / "_all" / "until"
        check("...nenhum registro de run em _all/until",
              not all_dir.exists() or not any(all_dir.iterdir()),
              str(list(all_dir.iterdir()) if all_dir.exists() else []))


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n✗ {len(FAILURES)} falha(s)")
        return 1
    print(f"\n✓ {len(tests)} testes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
