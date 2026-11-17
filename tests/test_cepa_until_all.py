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
