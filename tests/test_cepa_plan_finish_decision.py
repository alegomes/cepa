#!/usr/bin/env python3
"""CS-11 of docs/spec/perguntar-antes-do-run.md: a behavior choice the agent
already committed is recorded without opening a route, and the end-of-run
summary lists it with the commit.

Red test declared in the spec: `cepa-plan finish <fila> <id> done --decision
"lote pula credencial inativa" --commit <hash>` leaves `human_pending` null and
records the choice in `decisions`; the end-of-run summary lists it with the
commit; `cepa-until decide <fila>` does not ask about it. Before CS-11,
`--decision` was refused as an unknown argument.

One deliberate difference from the spec text, recorded in the item's
evidence: the commit flag is `--decision-commit <hash>` (default HEAD),
because `finish --commit` already exists and means "commit the queue file";
and the status is `--status done`, as it always was.

Run: python3 tests/test_cepa_plan_finish_decision.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cepa_until import (  # noqa: E402
    CEPA_UNTIL, build_repo, fake_claude, item, run_until)

CEPA_PLAN = CEPA_UNTIL.parent / "cepa-plan"
DECISION = "lote pula credencial inativa"
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def git(root, *args):
    return subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                           *args], cwd=root, capture_output=True, text=True,
                          check=True).stdout.strip()


def plan_cli(root, *args):
    env = dict(os.environ)
    env.pop("CLAUDE_AUTONOMOUS_RUN_ID", None)
    return subprocess.run([sys.executable, str(CEPA_PLAN), *args, "--repo", str(root)],
                          capture_output=True, text=True, cwd=root, env=env,
                          timeout=60)


def plan_file(root):
    return Path(root) / ".claude" / "programs" / "fila" / "plan.yaml"


def items_of(root):
    return {i["id"]: i for i in yaml.safe_load(plan_file(root).read_text())["items"]}


def commit_choice(root, name="skip.txt"):
    """Commits a file (the 'choice') AND the queue, so the tree is clean for `done`."""
    (Path(root) / name).write_text("skip inactive credentials\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", f"choice {name}")
    return git(root, "rev-parse", "HEAD")


def started(root, ident="a1"):
    p = plan_cli(root, "start", "fila", ident)
    assert p.returncode == 0, p.stderr
    git(root, "add", "-A")
    git(root, "commit", "-qm", "reserve")


# ── cepa-plan finish --decision ──────────────────────────────────────────────

def test_decision_is_recorded_without_opening_a_route():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        started(root)
        sha = commit_choice(root)
        p = plan_cli(root, "finish", "fila", "a1", "--status", "done",
                     "--evidence", "commit da escolha", "--decision", DECISION,
                     "--decision-commit", sha[:8])
        check("finish --decision sai 0", p.returncode == 0, p.stderr + p.stdout)
        it = items_of(root)["a1"]
        check("human_pending continua nulo", "human_pending" in it
              and it["human_pending"] is None, str(it))
        check("decisions grava a escolha com o commit completo",
              it.get("decisions") == [{"texto": DECISION, "commit": sha}],
              str(it.get("decisions")))
        check("o item fecha done", it["status"] == "done", str(it))
        check("a saída diz que não abriu rota",
              "sem rota para o dono" in p.stdout and DECISION in p.stdout, p.stdout)


def test_decision_commit_defaults_to_head_and_flag_repeats():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        started(root)
        sha = commit_choice(root)
        p = plan_cli(root, "finish", "fila", "a1", "--status", "done",
                     "--evidence", "duas escolhas", "--decision", DECISION,
                     "--decision", "  reenvio   espera 5 min ", "--decision", DECISION)
        it = items_of(root)["a1"]
        check("sem --decision-commit, o commit é o HEAD; texto achatado; repetida "
              "uma vez só", p.returncode == 0 and it.get("decisions") == [
                  {"texto": DECISION, "commit": sha},
                  {"texto": "reenvio espera 5 min", "commit": sha}],
              p.stderr + str(it.get("decisions")))


def test_decision_refusals_leave_the_item_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        started(root)
        git(root, "checkout", "-qb", "outra")
        other = commit_choice(root, "other.txt")
        git(root, "checkout", "-q", "-")
        commit_choice(root)
        before = items_of(root)["a1"]
        cases = [
            ("commit que não existe", ["--decision", DECISION, "--decision-commit",
                                       "deadbeefdeadbeef"], "não existe"),
            ("commit fora da branch atual", ["--decision", DECISION,
                                            "--decision-commit", other],
             "não está na branch"),
            ("texto vazio", ["--decision", "   "], "vazio"),
            ("--decision-commit sem --decision", ["--decision-commit", other],
             "sem `--decision`"),
        ]
        for label, extra, needle in cases:
            p = plan_cli(root, "finish", "fila", "a1", "--status", "done",
                         "--evidence", "x", *extra)
            check(f"recusa: {label}", p.returncode == 2 and needle in p.stderr,
                  f"rc={p.returncode} {p.stderr}")
        check("nenhuma recusa mexeu no item", items_of(root)["a1"] == before,
              str(items_of(root)["a1"]))


def test_old_queue_without_decisions_still_valid():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        started(root)
        commit_choice(root)
        p = plan_cli(root, "finish", "fila", "a1", "--status", "done",
                     "--evidence", "sem escolha")
        check("finish sem --decision não cria a chave",
              p.returncode == 0 and "decisions" not in items_of(root)["a1"],
              p.stderr + str(items_of(root)["a1"]))


# ── the run summary and `decide` ─────────────────────────────────────────────

AGENT = r"""
import subprocess
ident = primeiro_pendente()
if ident:
    cwd = os.getcwd()
    def g(*a):
        return subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t', *a],
                              cwd=cwd, capture_output=True, text=True).stdout.strip()
    plan = [sys.executable, os.environ['CEPA_PLAN_BIN']]
    subprocess.run(plan + ['start', 'fila', ident, '--repo', cwd], cwd=cwd,
                   capture_output=True)
    open(os.path.join(cwd, ident + '.txt'), 'w').write('choice\n')
    g('add', '-A'); g('commit', '-qm', 'choice ' + ident)
    sha = g('rev-parse', 'HEAD')
    extra = []
    if ident == 'a1':
        extra = ['--decision', os.environ['DECISAO'], '--decision-commit', sha]
    elif ident == 'a2':
        # A choice whose commit is NOT on the run branch (a dangling commit,
        # like the one a red build takes off): the summary must not list it.
        g('checkout', '-qb', 'lado-' + ident)
        open(os.path.join(cwd, 'lado.txt'), 'w').write('x\n')
        g('add', '-A'); g('commit', '-qm', 'side')
        side = g('rev-parse', 'HEAD')
        g('checkout', '-q', '-')
        p = carrega()
        for it in p['items']:
            if it['id'] == ident:
                it['decisions'] = [{'texto': 'escolha fora da branch', 'commit': side}]
        grava(p)
    r = subprocess.run(plan + ['finish', 'fila', ident, '--status', 'done',
                               '--evidence', 'feito', '--repo', cwd] + extra,
                       cwd=cwd, capture_output=True, text=True)
    open(os.environ['FAKE_CHAMADAS'] + '.finish', 'a').write(r.stdout + r.stderr)
"""


def test_run_summary_lists_the_decision_with_its_commit_and_decide_skips_it():
    with tempfile.TemporaryDirectory() as tmp:
        old = dict(item("a0", status="done"),
                   decisions=[{"texto": "escolha de um run antigo",
                               "commit": "0" * 40}])
        root = build_repo(tmp, [old, item("a1"), item("a2"), item("a3")])
        # a3 runs in this run but carries a choice recorded before it, on a
        # commit that IS on the run branch: only the "recorded in this run"
        # filter keeps it out of the summary.
        seeded = yaml.safe_load(plan_file(root).read_text())
        for it in seeded["items"]:
            if it["id"] == "a3":
                it["decisions"] = [{"texto": "escolha antiga em item relançado",
                                    "commit": git(root, "rev-parse", "HEAD")}]
        plan_file(root).write_text(yaml.safe_dump(seeded, allow_unicode=True))
        git(root, "add", "-A")
        git(root, "commit", "-qm", "seed a3 decision")
        binv = fake_claude(tmp, AGENT)
        p, calls = run_until(root, binv, plan_file(root), ["--for", "2h"],
                             extra_env={"CEPA_PLAN_BIN": str(CEPA_PLAN),
                                        "DECISAO": DECISION})
        finish_log = Path(tmp, "chamadas.jsonl.finish")
        finish_out = finish_log.read_text() if finish_log.exists() else ""
        its = items_of(root)
        check("o agente falso fechou os três itens pelo cepa-plan real",
              all(its[i]["status"] == "done" for i in ("a1", "a2", "a3")),
              finish_out + p.stdout[-800:])
        dec = (its["a1"].get("decisions") or [{}])[0]
        check("a1 tem a decisão e nenhuma rota",
              dec.get("texto") == DECISION and its["a1"]["human_pending"] is None,
              str(its["a1"]))
        out = p.stdout
        check("o resumo do fim lista a decisão com o commit",
              "Decided for you (1)" in out
              and f"a1: {DECISION} · commit {dec.get('commit', '?')[:10]}" in out,
              out[-1500:])
        check("o resumo não lista a escolha cujo commit saiu da branch",
              "escolha fora da branch" not in out, out[-1500:])
        check("o resumo não lista a decisão de um run anterior",
              "escolha de um run antigo" not in out, out[-1500:])
        check("o resumo não lista a decisão antiga de um item que rodou neste run",
              its["a3"].get("decisions") and "escolha antiga em item relançado"
              not in out, out[-1500:])
        waiting = out.split("waiting on you", 1)[-1] if "waiting on you" in out else ""
        check("a decisão não vira rota no resumo",
              "- a1" not in waiting and DECISION not in waiting
              and "a1: `done`, waiting on you" not in out, out[-1500:])
        d = subprocess.run([sys.executable, str(CEPA_UNTIL), "decide", "fila",
                            "--repo", str(root)], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=60)
        check("cepa-until decide <fila> não pergunta sobre a decisão",
              d.returncode == 0 and DECISION not in d.stdout
              and "- a1" not in d.stdout, d.stdout + d.stderr)


def main():
    print("cepa-plan finish --decision (CS-11)\n")
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
