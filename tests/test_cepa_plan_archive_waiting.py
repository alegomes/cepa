#!/usr/bin/env python3
"""CS-2 of docs/spec/filas-fechadas-saem-da-vista.md: a closed queue with
something waiting on the owner is not archived, and the output says why.

Red test declared in the spec: four queues with every item `done` or `dropped`
and the last commit 8 days ago: `sobra` (a leftover point on a `done` item),
`rota` (an open human route), `run` (a run waiting to land) and `vazia`
(`items: []`). `cepa-plan archive` moves none and the output gives the reason
per queue. A fifth control queue `velha` (plainly closed) IS archived in the
same sweep, to prove the refusals are specific.

The run is the real thing: a night branch plus a state file that makes the real
`cepa-until pending --json` list it (the fixture approach of
tests/test_cepa_plan_waiting_runs.py). The "could not check the runs" case swaps
the sibling `cepa-until` of a copy of cepa-plan for a script that fails.

Run: python3 tests/test_cepa_plan_archive_waiting.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_plan_archive import (CEPA_PLAN, ENV, FAILURES, NEW, REPO,  # noqa: E402
                                    archived, check, commit, days_ago, git, item,
                                    queue_dir, write_queue)

RUN = "2026-11-20-0100"


def cli_at(plan_bin, root, *args):
    return subprocess.run([sys.executable, str(plan_bin), *args, "--repo", str(root)],
                          capture_output=True, text=True, cwd=root, env=ENV,
                          timeout=120)


def cli(root, *args):
    return cli_at(CEPA_PLAN, root, *args)


def new_repo(tmp):
    """Like the archive tests' repo, but on `main` (a run lands in `main`)."""
    root = Path(tmp) / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main", ".")
    (root / "f.txt").write_text("base\n")
    commit(root, "base", days_ago(30))
    return root


def edit_queue(root, name, fn):
    f = queue_dir(root, name) / "queue.yaml"
    plan = yaml.safe_load(f.read_text(encoding="utf-8"))
    fn(plan)
    f.write_text(yaml.safe_dump(plan, allow_unicode=True), encoding="utf-8")


def closed(root, name, days=8, mutate=None):
    """A closed queue (one `done` item), committed `days` ago; `mutate(item)`
    changes its item before the commit."""
    write_queue(root, name, ["done"])
    if mutate:
        edit_queue(root, name, lambda plan: mutate(plan["items"][0]))
    commit(root, name, days_ago(days), f"{NEW}/{name}")


def with_route(it, answer=None):
    it["human_pending"] = "Conferir a tela no celular"
    if answer:
        it["evidence"] = f"Resposta do dono em 2026-11-01: {answer}"


def with_point(it):
    it["pendencias"] = [{"texto": "validar o relatório em produção",
                         "resolvida_em": None}]


def with_run(root, name, days=8, fila=None):
    """A night branch one commit ahead of `main` and a state file that makes
    `cepa-until pending` list the run of queue `name` as waiting to land.
    `fila` is the queue name the run recorded, when it is not the folder's."""
    git(root, "checkout", "-qb", f"until/{RUN}")
    (root / "f.txt").write_text("night\n")
    commit(root, "night work", days_ago(days), "f.txt")
    git(root, "checkout", "-q", "main")
    d = queue_dir(root, name) / "until"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{RUN}.estado.json").write_text(json.dumps({
        "fila": fila or name, "run": RUN, "branch": f"until/{RUN}",
        "estado": "esperando-dono",
        "acoes": [{"id": "aterrissar", "destino": "main"}]}), encoding="utf-8")
    commit(root, "run state", days_ago(days), f"{NEW}/{name}")


def line_of(out, name):
    for l in out.splitlines():
        if l.startswith(f"não arquivada · {name}:"):
            return l
    return ""


def test_declared_red_test():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        closed(root, "sobra", mutate=with_point)
        closed(root, "rota", mutate=with_route)
        closed(root, "run")
        with_run(root, "run")
        write_queue(root, "vazia", [])
        commit(root, "vazia", days_ago(8), f"{NEW}/vazia")
        closed(root, "velha")
        p = cli(root, "archive")
        print(p.stdout, end="")
        check("red: exit 0", p.returncode == 0, p.stdout + p.stderr)
        check("red: no traceback", "Traceback" not in p.stderr, p.stderr)
        for n in ("sobra", "rota", "run", "vazia"):
            check(f"red: {n} stays in place",
                  (queue_dir(root, n) / "queue.yaml").is_file()
                  and not archived(root, n).exists(), p.stdout)
        check("red: the control queue is archived in the same sweep",
              (archived(root, "velha") / "queue.yaml").is_file(), p.stdout)
        check("red: only velha in _archive",
              [q.name for q in archived(root, "").iterdir()] == ["velha"])
        sobra, rota = line_of(p.stdout, "sobra"), line_of(p.stdout, "rota")
        run, vazia = line_of(p.stdout, "run"), line_of(p.stdout, "vazia")
        check("red: sobra names the item and the leftover point",
              "sobra-0" in sobra and "ponto" in sobra and "pendente" in sobra, sobra)
        check("red: sobra is not told as a route", "tarefa sua" not in sobra, sobra)
        check("red: rota names the item and the open task",
              "rota-0" in rota and "tarefa sua" in rota, rota)
        check("red: rota is not told as a leftover point", "ponto" not in rota, rota)
        check("red: run names the run and repeats the command",
              RUN in run and f"cepa-until land run/{RUN}" in run, run)
        check("red: run has no age or dirty-folder reason (commit is 8 days old)",
              "último commit" not in run and "não commitadas" not in run, run)
        check("red: vazia says it has no item", "nenhum item" in vazia, vazia)
        check("red: velha moved, so no 'nada a arquivar'",
              "nada a arquivar" not in p.stdout, p.stdout)


def test_route_answered_no_still_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        closed(root, "nao", mutate=lambda it: with_route(it, "não"))
        p = cli(root, "archive")
        l = line_of(p.stdout, "nao")
        check("no-answer: exit 0", p.returncode == 0, p.stderr)
        check("no-answer: stays", (queue_dir(root, "nao") / "queue.yaml").is_file())
        check("no-answer: own wording, names the item",
              "nao-0" in l and "respondeu não" in l and "continua" in l, l)


def test_dropped_route_does_not_block():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "solta", ["done", "dropped"])
        edit_queue(root, "solta", lambda plan: with_route(plan["items"][1]))
        commit(root, "solta", days_ago(8), f"{NEW}/solta")
        p = cli(root, "archive")
        check("dropped route: archived", (archived(root, "solta") / "queue.yaml").is_file(),
              p.stdout)


def test_resolved_point_does_not_block():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)

        def resolved(it):
            it["pendencias"] = [{"texto": "x", "resolvida_em": "2026-11-02"}]
        closed(root, "resolvida", mutate=resolved)
        p = cli(root, "archive")
        check("resolved point: archived",
              (archived(root, "resolvida") / "queue.yaml").is_file(), p.stdout)


def test_blocked_only_queue_is_silent_and_stays():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "travada", ["done", "blocked"])
        commit(root, "travada", days_ago(8), f"{NEW}/travada")
        p = cli(root, "archive")
        check("blocked: exit 0", p.returncode == 0, p.stderr)
        check("blocked: stays", (queue_dir(root, "travada") / "queue.yaml").is_file()
              and not archived(root, "travada").exists())
        check("blocked: silent", "travada" not in p.stdout, p.stdout)


def test_dry_run_shows_refusals_and_moves_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        closed(root, "rota", mutate=with_route)
        write_queue(root, "vazia", [])
        commit(root, "vazia", days_ago(8), f"{NEW}/vazia")
        closed(root, "velha")
        p = cli(root, "archive", "--dry-run")
        check("dry-run: exit 0", p.returncode == 0, p.stderr)
        check("dry-run: refusal for the route", "rota-0" in line_of(p.stdout, "rota"), p.stdout)
        check("dry-run: refusal for the empty one", "nenhum item" in line_of(p.stdout, "vazia"),
              p.stdout)
        check("dry-run: velha would go", "(dry-run) arquivaria · velha" in p.stdout, p.stdout)
        check("dry-run: nothing moved", queue_dir(root, "velha").is_dir()
              and not archived(root, "velha").exists())


def test_all_reasons_are_listed():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        closed(root, "nova-rota", days=2, mutate=with_route)
        p = cli(root, "archive")
        l = line_of(p.stdout, "nova-rota")
        check("both: the age reason", "último commit em" in l and "faltam" in l, l)
        check("both: the route reason", "nova-rota-0" in l and "tarefa sua" in l, l)
        check("both: one line, joined by '; '", "; " in l and l.count("\n") == 0, l)
        check("both: nothing archived says so", "nada a arquivar" in p.stdout, p.stdout)


def test_two_items_and_two_reasons_in_one_queue():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "mista", ["done", "done", "done"])

        def both(plan):
            with_route(plan["items"][0])
            with_point(plan["items"][1])
            with_route(plan["items"][2])
        edit_queue(root, "mista", both)
        commit(root, "mista", days_ago(8), f"{NEW}/mista")
        p = cli(root, "archive")
        l = line_of(p.stdout, "mista")
        check("mixed: route reason names both route items",
              "mista-0" in l and "mista-2" in l, l)
        check("mixed: point reason names its item", "mista-1" in l, l)


def test_runs_are_checked_at_most_once_and_only_for_closed_queues():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        closed(root, "a-run")
        with_run(root, "a-run")
        closed(root, "b-velha")
        closed(root, "c-velha")
        log = Path(tmp) / "calls.log"
        plugin = Path(tmp) / "plugin"
        (plugin / "bin").mkdir(parents=True)
        for d in ("hooks", "_vendor"):
            (plugin / d).symlink_to(REPO / "common" / d)
        (plugin / "bin" / "cepa-plan").write_text(CEPA_PLAN.read_text())
        real_until = REPO / "common" / "bin" / "cepa-until"
        (plugin / "bin" / "cepa-until").write_text(
            "import subprocess, sys\n"
            f"open({str(log)!r}, 'a').write('call\\n')\n"
            f"sys.exit(subprocess.call([sys.executable, {str(real_until)!r}, *sys.argv[1:]]))\n")
        p = cli_at(plugin / "bin" / "cepa-plan", root, "archive")
        calls = log.read_text().count("call") if log.exists() else 0
        check("once: exit 0", p.returncode == 0, p.stderr)
        check("once: cepa-until pending called exactly once for 3 closed queues",
              calls == 1, str(calls))
        check("once: the run still blocks its queue", "a-run" in line_of(p.stdout, "a-run")
              and RUN in line_of(p.stdout, "a-run"), p.stdout)
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "aberta", ["done", "pending"])
        write_queue(root, "vazia", [])
        commit(root, "q", days_ago(8), NEW)
        plugin = Path(tmp) / "plugin"
        (plugin / "bin").mkdir(parents=True)
        for d in ("hooks", "_vendor"):
            (plugin / d).symlink_to(REPO / "common" / d)
        (plugin / "bin" / "cepa-plan").write_text(CEPA_PLAN.read_text())
        (plugin / "bin" / "cepa-until").write_text(
            "open(%r, 'w').write('x')\n" % str(Path(tmp) / "called"))
        cli_at(plugin / "bin" / "cepa-plan", root, "archive")
        check("lazy: no closed queue, cepa-until never called",
              not (Path(tmp) / "called").exists())


def test_runs_check_failure_fails_closed():
    cases = [("exit 1", "import sys\nsys.stderr.write('boom')\nsys.exit(1)\n"),
             ("not JSON", "print('não é json')\n"),
             ("not an object", "print('[]')\n")]
    for label, body in cases:
        with tempfile.TemporaryDirectory() as tmp:
            root = new_repo(tmp)
            closed(root, "velha")
            plugin = Path(tmp) / "plugin"
            (plugin / "bin").mkdir(parents=True)
            for d in ("hooks", "_vendor"):
                (plugin / d).symlink_to(REPO / "common" / d)
            (plugin / "bin" / "cepa-plan").write_text(CEPA_PLAN.read_text())
            (plugin / "bin" / "cepa-until").write_text(body)
            p = cli_at(plugin / "bin" / "cepa-plan", root, "archive")
            l = line_of(p.stdout, "velha")
            check(f"fail-closed ({label}): exit 0", p.returncode == 0, p.stderr)
            check(f"fail-closed ({label}): not archived",
                  (queue_dir(root, "velha") / "queue.yaml").is_file()
                  and not archived(root, "velha").exists())
            check(f"fail-closed ({label}): says the runs could not be checked",
                  "não deu para conferir" in l and "run" in l, p.stdout)


def fake_until(tmp, body):
    """A copy of the plugin whose `cepa-until` is `body`: the only way to make
    `cepa-until pending` answer something a real repo cannot be put into."""
    plugin = Path(tmp) / "plugin"
    (plugin / "bin").mkdir(parents=True)
    for d in ("hooks", "_vendor"):
        (plugin / d).symlink_to(REPO / "common" / d)
    (plugin / "bin" / "cepa-plan").write_text(CEPA_PLAN.read_text())
    (plugin / "bin" / "cepa-until").write_text(body)
    return plugin / "bin" / "cepa-plan"


def test_dropped_point_does_not_block():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "solta", ["done", "dropped"])
        edit_queue(root, "solta", lambda plan: with_point(plan["items"][1]))
        commit(root, "solta", days_ago(8), f"{NEW}/solta")
        p = cli(root, "archive")
        check("dropped point: archived",
              (archived(root, "solta") / "queue.yaml").is_file(), p.stdout)


def test_entry_that_is_not_an_item_is_ignored():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "mista", ["done"])
        edit_queue(root, "mista", lambda plan: plan["items"].append("solto"))
        commit(root, "mista", days_ago(8), f"{NEW}/mista")
        p = cli(root, "archive")
        check("non-item entry: no warning", "ilegível" not in p.stderr, p.stderr)
        check("non-item entry: archived",
              (archived(root, "mista") / "queue.yaml").is_file(), p.stdout)


def test_run_recorded_under_the_header_name_blocks():
    """The folder is `pasta`, the header says `queue: titulo`, and the run
    recorded `titulo`: the run still belongs to this queue."""
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        write_queue(root, "pasta", ["done"])
        edit_queue(root, "pasta", lambda plan: plan.update(queue="titulo"))
        commit(root, "pasta", days_ago(8), f"{NEW}/pasta")
        with_run(root, "pasta", fila="titulo")
        p = cli(root, "archive")
        l = line_of(p.stdout, "pasta")
        check("header name: stays", (queue_dir(root, "pasta") / "queue.yaml").is_file()
              and not archived(root, "pasta").exists(), p.stdout)
        check("header name: names the run", RUN in l, p.stdout)


def test_each_route_wording_is_its_own():
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        closed(root, "aberta", mutate=with_route)
        write_queue(root, "duas", ["done", "done"])
        edit_queue(root, "duas", lambda plan: [with_route(it, "não")
                                               for it in plan["items"]])
        commit(root, "duas", days_ago(8), f"{NEW}/duas")
        p = cli(root, "archive")
        a, d = line_of(p.stdout, "aberta"), line_of(p.stdout, "duas")
        check("open route: says it is open, not that it was answered",
              "tarefa sua em aberto em aberta-0" in a and "respondeu não" not in a, a)
        check("answered no: counts the two and names them",
              "2 tarefa(s) que você respondeu não" in d
              and "duas-0, duas-1" in d, d)
        check("answered no: not also listed as an open task",
              "tarefa sua em aberto" not in d, d)


def test_run_without_a_command_does_not_print_none():
    body = ("import json\nprint(json.dumps({'runs': [], 'fechados': [], "
            "'mortos': [{'fila': 'velha', 'run': 'r9'}]}))\n")
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        closed(root, "velha")
        p = cli_at(fake_until(tmp, body), root, "archive")
        l = line_of(p.stdout, "velha")
        check("no command: stays and names the run", "r9" in l, p.stdout)
        check("no command: points at `cepa until pending`, never None",
              "None" not in l and "cepa until pending" in l, l)


def test_what_the_run_check_writes_counts_for_the_same_sweep():
    """`cepa-until pending` may close a landed run and write its record inside
    the queue folder. The sweep reads the runs BEFORE it measures the folder,
    so a queue changed by that read is not moved in the same sweep."""
    body = ("import json, sys\nfrom pathlib import Path\n"
            "root = Path(sys.argv[sys.argv.index('--repo') + 1])\n"
            "d = root / '.claude' / 'queues' / 'velha' / 'until'\n"
            "d.mkdir(exist_ok=True)\n(d / 'r9.jsonl').write_text('{}\\n')\n"
            "print(json.dumps({'runs': [], 'mortos': [], 'fechados': []}))\n")
    with tempfile.TemporaryDirectory() as tmp:
        root = new_repo(tmp)
        closed(root, "velha")
        p = cli_at(fake_until(tmp, body), root, "archive")
        l = line_of(p.stdout, "velha")
        check("run check wrote in the folder: stays",
              (queue_dir(root, "velha") / "queue.yaml").is_file()
              and not archived(root, "velha").exists(), p.stdout)
        check("run check wrote in the folder: says it is uncommitted",
              "não commitadas" in l, p.stdout)


def main():
    for t in (test_declared_red_test, test_route_answered_no_still_blocks,
              test_dropped_route_does_not_block, test_resolved_point_does_not_block,
              test_blocked_only_queue_is_silent_and_stays,
              test_dry_run_shows_refusals_and_moves_nothing,
              test_all_reasons_are_listed, test_two_items_and_two_reasons_in_one_queue,
              test_runs_are_checked_at_most_once_and_only_for_closed_queues,
              test_runs_check_failure_fails_closed,
              test_dropped_point_does_not_block,
              test_entry_that_is_not_an_item_is_ignored,
              test_run_recorded_under_the_header_name_blocks,
              test_each_route_wording_is_its_own,
              test_run_without_a_command_does_not_print_none,
              test_what_the_run_check_writes_counts_for_the_same_sweep):
        print(t.__name__)
        t()
    if FAILURES:
        print(f"\n{len(FAILURES)} failed: {FAILURES}")
        return 1
    print("\nall ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
