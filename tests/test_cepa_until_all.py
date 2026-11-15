#!/usr/bin/env python3
"""`cepa until --all` (spec `until-todas-as-filas`).

CS-1: `cepa until --all --for 8h --dry-run` lists the ready items of every
queue, grouped by queue and in the order of `cepa plan ready`, and exits 0
without executing anything. Before the flag existed the call exited 2: the
queue name was a required positional.

Against the real CLI (`cepa until`, through the launcher), in a temporary git
repo with two queues, `a` and `b`, one ready item each, and a fake `claude`
that records any call (none may happen).

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


def test_single_queue_dry_run_unchanged():
    with tempfile.TemporaryDirectory() as tmp:
        root, _ = _repo(tmp, {"a": [base.item("a1")]})
        p, calls = _run(tmp, root, ["a", "--for", "2h", "--dry-run",
                                    "--no-verify"])
        check("`cepa until a --dry-run` segue saindo com 0", p.returncode == 0,
              p.stderr[-400:])
        check("...e nomeia o item", "a1" in p.stdout)


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
