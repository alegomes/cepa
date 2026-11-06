#!/usr/bin/env python3
"""Tests of `common/bin/cepa-until` — the time-window supervisor.

Run with `python3 tests/test_cepa_until.py` (it only needs PyYAML).

## What these tests prove, and what they do NOT prove

The supervisor has a single responsibility: deciding WHEN to fire one more
subprocess and when to stop. Everything that happens INSIDE the subprocess belongs to
`/common:drain-plan` and the topology, and no test here touches that.

So `claude` is replaced by a fake script on the PATH, which does what
drain-plan would do with the plan (mark `done`, open `human_pending`, do
nothing, jam). That makes it possible to measure exactly the four decisions of the supervisor:

  - the deadline is respected BEFORE starting an item, never in the middle of it;
  - the circuit breaker counts failures IN A ROW and progress resets the count;
  - `human_pending` is PROGRESS — the debt with the human cannot look like a failure,
    otherwise three deferred items kill the night at 10pm;
  - the truth of the outcome is the STATUS IN THE PLAN, not the exit code of the
    subprocess (a `claude` that exits 0 without touching the item is a failure).

What these tests do NOT prove: that a real 12h night holds up. That is
a calendar night, and only the first real run tells.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_UNTIL = REPO / "common" / "bin" / "cepa-until"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


# ── scenario ────────────────────────────────────────────────────────────────

def build_repo(tmp, item_list):
    """Git repo with a `queue` named `fila` and the requested items.

    The repo stays in `<tmp>/repo`, and NOT in the tmp root, because the fake `claude` and
    the call record live in the tmp: inside the repo they would dirty the tree and
    the launch guard would refuse the run — which was exactly the first failure mode
    of these tests.
    """
    root = Path(tmp) / "repo"
    root.mkdir(parents=True, exist_ok=True)
    d = root / ".claude" / "programs" / "fila"
    d.mkdir(parents=True)
    plan = {"schema_version": 2, "mode": "single-track", "program": "fila",
             "source": "teste", "items": item_list}
    (d / "plan.yaml").write_text(yaml.safe_dump(plan, allow_unicode=True),
                                 encoding="utf-8")
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    return root


def item(ident, status="pending", human_pending=None):
    return {"id": ident, "title": f"item {ident}", "why": "porque",
            "status": status, "blocked_by": [], "human_pending": human_pending,
            "evidence": None}


def fake_claude(tmp, body):
    """A fake `claude` on the PATH. `body` is python3 that receives PLAN and ARGS."""
    binv = Path(tmp) / "bin"
    binv.mkdir(exist_ok=True)
    script = binv / "claude"
    # Shebang with THIS suite's interpreter, not `env python3`: the system's python3
    # may not have PyYAML, and the adversarial test fixes the PATH on
    # purpose. With `env python3` the fake died on import and the measured case
    # became another. (2026-08-30.)
    script.write_text(
        f"#!{sys.executable}\n"
        "import os, sys, yaml, json, time\n"
        "PLANO = os.environ['FAKE_PLANO']\n"
        "ARGS = sys.argv[1:]\n"
        "def carrega():\n"
        "    return yaml.safe_load(open(PLANO, encoding='utf-8'))\n"
        "def grava(p):\n"
        "    open(PLANO, 'w', encoding='utf-8').write("
        "yaml.safe_dump(p, allow_unicode=True))\n"
        "def marca(ident, **campos):\n"
        "    p = carrega()\n"
        "    for it in p['items']:\n"
        "        if it['id'] == ident:\n"
        "            it.update(campos)\n"
        "    grava(p)\n"
        # Mirrors the deferral rule of `cepa-plan build_batch`: an item with an open
        # `human_pending` is NOT handed to the executor again. Without this the
        # fake marks the same item forever and the test measures itself.
        "def primeiro_pendente():\n"
        "    for it in carrega()['items']:\n"
        "        if it['status'] == 'pending' and not it.get('human_pending'):\n"
        "            return it['id']\n"
        "    return None\n"
        "with open(os.environ['FAKE_CHAMADAS'], 'a') as f:\n"
        "    f.write(json.dumps(ARGS) + '\\n')\n"
        + body + "\n",
        encoding="utf-8")
    script.chmod(0o755)
    return binv


def run_until(root, binv, plan, args, timeout=120, extra_env=None):
    """By default the run goes out `--sem-verify --sem-analise`: the test repos have no
    build, and the end analysis would be one more call to the fake `claude` in
    every test. Whoever tests the two passes `--verify`/`--com-analise`
    (`--com-analise` is only from this helper: it just does not add
    `--sem-analise`)."""
    env = dict(os.environ)
    env.update(extra_env or {})
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_PLANO"] = str(plan)
    env.setdefault("CEPA_WORKTREE_HOME", str(Path(root).parent / "worktrees"))
    calls = Path(root).parent / "chamadas.jsonl"
    env["FAKE_CHAMADAS"] = str(calls)
    args = list(args)
    if "--verify" not in args and "--no-verify" not in args:
        args.append("--no-verify")
    if "--com-analise" in args:
        args.remove("--com-analise")
    elif "--no-analysis" not in args:
        args.append("--no-analysis")
    p = subprocess.run([sys.executable, str(CEPA_UNTIL), "fila", "--repo", str(root)]
                       + args, capture_output=True, text=True, env=env,
                       timeout=timeout)
    lines = []
    if calls.exists():
        lines = [json.loads(l) for l in calls.read_text().splitlines() if l.strip()]
    return p, lines


def ledger_of(root):
    d = Path(root) / ".claude" / "programs" / "fila" / "until"
    events = []
    for f in sorted(d.glob("*.jsonl")):
        events += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return events


# ── 1. clock ────────────────────────────────────────────────────────────────

def test_duration_without_unit_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "12"])
        check("--for sem unidade é recusado", p.returncode == 2,
              f"saiu {p.returncode}")
        # The refusal has to name the FLAG and the VALUE refused. Only requiring "exited 2"
        # and "the text cites 12h/90m" lets through a version that accepts `--for 12`
        # and dies later in --min-reserve: same exit code, a message
        # sending you to check the wrong argument. (Perturbation, 2026-08-30.)
        check("...e a recusa nomeia --for e o valor recusado",
              "--for '12'" in p.stderr, p.stderr[:300])
        check("...e a recusa diz qual é o formato",
              "12h" in p.stderr and "90m" in p.stderr, p.stderr[:300])
        check("...e nada foi disparado", not calls, str(calls))


def test_refusal_names_the_right_flag_among_the_three_durations():
    """--for, --min-reserve and --slack go through the same parser. A refusal
    that always names `--for` sends you to check the wrong argument."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        for flag, value in (("--min-reserve", "25"), ("--slack", "30")):
            p, calls = run_until(root, binv, plan, ["--for", "2h", flag, value])
            check(f"{flag} inválida é recusada", p.returncode == 2,
                  f"saiu {p.returncode}")
            check(f"...e a recusa nomeia {flag}, não --for",
                  f"{flag} '{value}'" in p.stderr, p.stderr[:300])
            check("...e nada foi disparado", not calls, str(calls))


def test_minimum_reserve_prevents_starting_an_item_that_does_not_fit():
    """The cut is BEFORE the item. A window smaller than the minimum reserve fires
    nothing — starting an item that does not fit is work thrown away."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan,
                           ["--for", "10m", "--min-reserve", "25m"])
        check("janela menor que a reserva não dispara item", not calls,
              f"disparou {len(calls)}x")
        check("...e o run termina por `prazo`",
              any(e.get("evento") == "run_end" and e.get("motivo") == "prazo"
                  for e in ledger_of(root)),
              json.dumps(ledger_of(root))[:300])
        check("...e o item continua pendente",
              yaml.safe_load(plan.read_text())["items"][0]["status"] == "pending")


def test_item_environment_turns_on_the_window_and_zeroes_the_wait_ceiling():
    """What the subprocess receives in the environment is contract, not detail.

    `CEPA_UNTIL_RUN` is what makes the window's hooks exist. And
    `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=0` is what keeps `claude -p` from killing
    itself at 10 minutes with background work pending — that is how
    WEGO-2224 died half done on 2026-09-03 and the 8h window closed with
    6h54 left over. Without this assertion, removing the line breaks no test.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        target = Path(tmp) / "ambiente.json"
        binv = fake_claude(
            tmp,
            "import os as _o, json as _j\n"
            f"open({str(target)!r}, 'w').write(_j.dumps(dict(_o.environ)))\n"
            "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        run_until(root, binv, plan, ["--for", "2h"])
        env = json.loads(target.read_text())
        check("o subprocesso nasce com CEPA_UNTIL_RUN",
              env.get("CEPA_UNTIL_RUN") == "1", repr(env.get("CEPA_UNTIL_RUN")))
        check("...e com o teto de espera por segundo plano zerado",
              env.get("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS") == "0",
              repr(env.get("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS")))


def test_wait_ceiling_chosen_by_the_operator_wins():
    """Whoever exported the value by hand knows what they want; the supervisor does not overwrite it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        target = Path(tmp) / "ambiente.json"
        binv = fake_claude(
            tmp,
            "import os as _o, json as _j\n"
            f"open({str(target)!r}, 'w').write(_j.dumps(dict(_o.environ)))\n"
            "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        run_until(root, binv, plan, ["--for", "2h"],
             extra_env={"CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS": "90000"})
        env = json.loads(target.read_text())
        check("valor posto pelo operador sobrevive",
              env.get("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS") == "90000",
              repr(env.get("CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS")))


# ── 2. progress and circuit breaker ─────────────────────────────────────────

def test_whole_queue_runs_until_empty():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("três itens, três subprocessos", len(calls) == 3,
              f"{len(calls)}: {calls}")
        check("um item por subprocesso (--max 1 no prompt)",
              all(any("--max 1" in a for a in c) for c in calls), str(calls))
        check("todos ficaram done",
              all(it["status"] == "done"
                  for it in yaml.safe_load(plan.read_text())["items"]))
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("o run termina por end-of-queue", end["motivo"] == "end-of-queue",
              str(end))
        check("...e conta 3 com progresso", end["com_progresso"] == 3, str(end))


def test_circuit_breaker_stops_after_n_failures_in_a_row():
    """`claude` exits 0 but does not touch the item: the supervisor cannot believe the
    exit code, otherwise it spins the whole night on the same item."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, "sys.exit(0)")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h", "--max-failures", "3"])
        check("para na 3ª falha seguida", len(calls) == 3,
              f"disparou {len(calls)}x")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("o run termina por `disjuntor`", end["motivo"] == "disjuntor", str(end))
        check("exit 0 sem mexer no item NÃO é progresso",
              end["com_progresso"] == 0 and end["sem_progresso"] == 3, str(end))


def test_progress_resets_the_circuit_breaker():
    """Two failures, a success, two failures: with the ceiling at 3, this must NOT
    stop the run — otherwise scattered bad luck ends a healthy night.

    `--attempts-per-item 6` turns off the OTHER ceiling, the one for attempts on the same
    item, which would otherwise take a1 off the front on the 2nd failure and the case would measure the
    wrong ceiling. They are two independent cuts: this one measures the circuit breaker, which counts
    failures in a row between ANY items.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = (
            "n = len(open(os.environ['FAKE_CHAMADAS']).read().splitlines())\n"
            "if n == 3:\n"
            "    marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan,
                           ["--for", "2h", "--max-failures", "3",
                            "--attempts-per-item", "6"])
        check("o sucesso do meio zerou a contagem", len(calls) == 6,
              f"disparou {len(calls)}x (esperado 2 falhas + 1 ok + 3 falhas)")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("e o fim é o disjuntor, na segunda sequência",
              end["motivo"] == "disjuntor" and end["com_progresso"] == 1, str(end))


def test_human_pending_is_progress_and_not_failure():
    """The route that only the human closes DEFERS the item (owner's decision, 2026-08-28).
    If the supervisor read it as a failure, three deferrals would kill the night."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(
            tmp, "marca(primeiro_pendente(), human_pending='valide o deploy à mão')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h", "--max-failures", "3"])
        check("três adiamentos NÃO disparam o disjuntor", len(calls) == 3,
              f"disparou {len(calls)}x")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("adiamento conta como progresso",
              end["com_progresso"] == 3 and end["sem_progresso"] == 0, str(end))
        check("o run termina por end-of-queue, não por disjuntor",
              end["motivo"] == "end-of-queue", str(end))
        check("a rota aberta aparece no relatório do fim",
              "valide o deploy à mão" in p.stdout, p.stdout[-400:])


def test_blocked_item_does_not_jam_the_night_behind_it():
    """Owner's decision, 2026-08-30: `blocked` DEFERS instead of stopping the batch. It was
    the last way for a single item to jam a whole window — the supervisor
    fired once, `queue` stopped at `blocked-before` and the night ended
    at 23h05 with one item done."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        body = ("ident = primeiro_pendente()\n"
                 "if ident == 'a1':\n"
                 "    marca(ident, status='blocked', evidence='a API de fora caiu')\n"
                 "else:\n"
                 "    marca(ident, status='done')\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("o item travado NÃO encerra a janela", len(calls) == 3,
              f"disparou {len(calls)}x")
        after = {it["id"]: it["status"]
                  for it in yaml.safe_load(plan.read_text())["items"]}
        check("o travado fica `blocked` e não é re-executado",
              after["a1"] == "blocked", after)
        check("...e os seguintes fecharam",
              after["a2"] == "done" and after["a3"] == "done", after)
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("o run termina por end-of-queue, não por `blocked-before`",
              end["motivo"] == "end-of-queue", str(end))
        check("...e a razão do fim cita os adiados",
              "adiado" in (end.get("detalhe") or "").lower(), str(end))
        # Without these two, taking `blocked` out of the progress count went
        # unnoticed: the three items ran the same, but the stuck one began to
        # count as a FAILURE and, on a night with several `blocked` in a row, the
        # circuit breaker would end the window early with nobody knowing why.
        # (Found by the proof gate, 2026-08-30.)
        check("o item travado conta como PROGRESSO, não como falha",
              end["com_progresso"] == 3 and end["sem_progresso"] == 0, str(end))


def test_end_summary_says_why_each_item_got_stuck():
    """Item `until-build-longo-sem-trava`, part 3: in WEGO's 25/09 run the
    summary only said "Stuck (1)", and the command WEGO-2334 left for the
    owner to run was at the end of the `evidence`, which could only be read by opening the queue."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        long_ = ("o par de clean verify foi cortado com EXIT=124 " * 30
                 + "rode ~/.wego-acesso/proof-2334/rodar-par-head.sh")
        body = ("ident = primeiro_pendente()\n"
                 "if ident == 'a1':\n"
                 f"    marca(ident, status='blocked', evidence={long_!r})\n"
                 "else:\n"
                 "    marca(ident, status='blocked', evidence=None,\n"
                 "          human_pending='aprove o PR 12 na interface')\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, _ = run_until(root, binv, plan, ["--for", "2h"])
        # Since step 2 of until-fim-sem-dono (A4), each item has ONE line
        # in "Items", and not one per list it falls into.
        # The end finishes, since 30/09, with the questions to the owner ("waiting
        # for you"), which repeat the question or the route on purpose: there it is a
        # question, no longer one more list of the same problem. Rule A4 holds from the
        # list of items up to that block.
        summary = p.stdout[p.stdout.find("Items ("):]
        summary = summary.split("── waiting on you")[0]
        check("o resumo dos travados existe", "Items (2)" in summary,
              p.stdout[-800:])
        check("o comando no FIM de uma evidence longa chega ao resumo",
              "rodar-par-head.sh" in summary, summary[:900])
        check("...e a evidence longa é cortada, não despejada inteira",
              "[...]" in summary and summary.count("EXIT=124") < 30, summary[:900])
        check("travado sem evidence mostra a rota, uma vez só",
              summary.count("aprove o PR 12 na interface") == 1, summary[:900])


def test_n_blocked_in_a_row_end_the_run_as_stuck_queue():
    """The acceptance of item `cepa-until-blocked-como-progresso`: 1 `done` item without
    merge followed by 5 dependents that jam. On 2026-09-23 there were 20 rounds
    like that, each rediscovering the same cause; `blocked` is progress, so the
    circuit breaker never fired. The run has to stop at the 3rd `blocked` in a row, with
    its own reason — and without blaming the items."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a0", status="done")]
                          + [item(f"b{n}") for n in range(1, 6)])
        binv = fake_claude(
            tmp, "marca(primeiro_pendente(), status='blocked', "
                 "evidence='a0 esta done numa branch sem merge')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("para no 3º `blocked` seguido", len(calls) == 3,
              f"disparou {len(calls)}x")
        after = {it["id"]: it["status"]
                  for it in yaml.safe_load(plan.read_text())["items"]}
        check("os dois últimos nem foram tocados",
              after["b4"] == "pending" and after["b5"] == "pending", after)
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("o run termina por `fila-travada`, não por `disjuntor`",
              end["motivo"] == "fila-travada", str(end))
        check("...e o motivo nomeia os itens da sequência",
              all(i in (end.get("detalhe") or "") for i in ("b1", "b2", "b3")),
              str(end))
        check("os travados continuam PROGRESSO, não falha do item",
              end["com_progresso"] == 3 and end["sem_progresso"] == 0
              and end["travados"] == 3, str(end))


def test_outcome_that_is_not_blocked_resets_the_sequence():
    """Two `blocked`, one `done`, two `blocked`: with the ceiling at 3 the run does NOT
    stop — jamming scattered across the queue is item by item, not a stuck queue."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item(f"a{n}") for n in range(1, 6)])
        body = ("ident = primeiro_pendente()\n"
                 "marca(ident, status='done' if ident == 'a3' else 'blocked', "
                 "evidence='x')\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("os cinco rodaram", len(calls) == 5,
              f"disparou {len(calls)}x")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("o run termina pela fila, não por `fila-travada`",
              end["motivo"] == "end-of-queue", str(end))


def test_max_stuck_configurable_and_validated():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item(f"a{n}") for n in range(1, 4)])
        binv = fake_claude(
            tmp, "marca(primeiro_pendente(), status='blocked', evidence='x')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h", "--max-blocked", "0"])
        check("--max-blocked 0 é recusado antes de disparar",
              p.returncode == 2 and not calls, f"{p.returncode} {calls}")
        p, calls = run_until(root, binv, plan, ["--for", "2h", "--max-blocked", "2"])
        check("--max-blocked 2 para no 2º", len(calls) == 2,
              f"disparou {len(calls)}x")
        check("o banner mostra o teto escolhido",
              "2 consecutive `blocked` items (stuck queue)" in p.stdout,
              p.stdout[:600])
        launch = [e for e in ledger_of(root) if e.get("evento") == "run_start"]
        check("o run_start registra o teto, para a análise da manhã",
              launch and launch[-1].get("max_travados") == 2, str(launch))


# ── 3. launch guards ────────────────────────────────────────────────────────

def test_dirty_tree_refuses_the_run():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        (root / "lixo.txt").write_text("pendura", encoding="utf-8")
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("árvore suja recusa", p.returncode == 2, f"saiu {p.returncode}")
        check("...e nada foi disparado", not calls, str(calls))
        check("...e a recusa nomeia o escape --dirty-ok",
              "--dirty-ok" in p.stderr, p.stderr[:300])
        p2, calls2 = run_until(root, binv, plan, ["--for", "2h", "--dirty-ok"])
        check("--dirty-ok deixa passar", len(calls2) == 1,
              f"saiu {p2.returncode}, disparou {len(calls2)}x")


def test_previous_run_record_is_not_dirt():
    """`cepa-until` writes `.jsonl`/`.log`/`.review.md` in
    `.claude/programs/<queue>/until/`, inside the repo. Before the filter, the next
    run saw the folder as untracked and refused the launch because of
    what the previous run itself wrote (seen on 2026-09-26, queue `cepa`)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p1, _ = run_until(root, binv, plan, ["--for", "2h"])
        check("o primeiro run anda", p1.returncode == 0, p1.stderr[-300:])
        # the morning: the owner lands what the run did and the queue has a pending
        # item again; only the run's record is left behind, as in the real clone
        subprocess.run(["git", "checkout", "-q", "--", str(plan)], cwd=root,
                       check=True)
        st = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                            capture_output=True, text=True).stdout
        check("...e deixa o registro não rastreado na árvore",
              "?? .claude/programs/fila/until/" in st, st)
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        p2, calls2 = run_until(root, binv, plan, ["--for", "2h"])
        check("o run seguinte larga mesmo com o registro do anterior",
              "modified file(s)" not in p2.stderr and len(calls2) == 1,
              f"saiu {p2.returncode}, disparou {len(calls2)}x: "
              f"{p2.stderr[:300]}")

        # the filter is only for the record: real dirt beside it still refuses
        subprocess.run(["git", "checkout", "-q", "--", str(plan)], cwd=root,
                       check=True)
        (root / "lixo.txt").write_text("pendura", encoding="utf-8")
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        p3, calls3 = run_until(root, binv, plan, ["--for", "2h"])
        check("sujeira de verdade ao lado do registro ainda recusa",
              p3.returncode == 2 and not calls3, f"saiu {p3.returncode}")
        check("...e a lista mostra só a sujeira, não o registro",
              "lixo.txt" in p3.stderr and "until/" not in p3.stderr,
              p3.stderr[:400])


def test_bak_of_the_queue_rewrite_is_not_dirt():
    """`cepa-plan write` copies the previous queue to `plan.yaml.bak` before
    rewriting (it is where the hand-written comments stay). The file is born
    untracked, and before the filter every queue rewrite blocked the next
    run until someone deleted the `.bak` by hand (seen on 2026-09-29, queue
    `cepa`)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        item_list = Path(tmp) / "itens.json"
        item_list.write_text(json.dumps([
            {"id": "a1", "title": "item a1", "why": "porque",
             "human_pending": None},
            {"id": "a2", "title": "item a2", "why": "entrou depois",
             "human_pending": None}]),
            encoding="utf-8")
        w = subprocess.run([sys.executable, str(REPO / "common" / "bin" /
                                                "cepa-plan"),
                            "write", "fila", "--items", str(item_list),
                            "--repo", str(root)],
                           capture_output=True, text=True)
        check("a reescrita da fila grava", w.returncode == 0, w.stderr[:300])
        # the owner commits the new queue; the `.bak` does not enter the commit
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "fila reescrita", "--", str(plan)],
                       cwd=root, check=True)
        st = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                            capture_output=True, text=True).stdout
        check("...e deixa o .bak não rastreado na árvore",
              "?? .claude/programs/fila/plan.yaml.bak" in st, st)
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("o run larga mesmo com o .bak da reescrita",
              "modified file(s)" not in p.stderr and len(calls) >= 1,
              f"saiu {p.returncode}, disparou {len(calls)}x: "
              f"{p.stderr[:300]}")

        # the filter is only for the untracked `.bak`: a `.bak` that someone
        # committed and then changed is a real change
        (root / ".claude" / "programs" / "fila" / "plan.yaml.bak").unlink()
        subprocess.run(["git", "checkout", "-q", "--", str(plan)], cwd=root,
                       check=True)
        (root / "lixo.bak").write_text("pendura", encoding="utf-8")
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        p2, calls2 = run_until(root, binv, plan, ["--for", "2h"])
        check("um .bak fora da fila ainda é sujeira",
              p2.returncode == 2 and not calls2
              and "lixo.bak" in p2.stderr, f"saiu {p2.returncode}")

        (root / "lixo.bak").unlink()
        bak = root / ".claude" / "programs" / "fila" / "plan.yaml.bak"
        bak.write_text("commitado\n", encoding="utf-8")
        _commits(root, "alguém commitou o .bak")
        bak.write_text("mudou depois\n", encoding="utf-8")
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        p3, calls3 = run_until(root, binv, plan, ["--for", "2h"])
        check("um .bak da fila commitado e depois mudado ainda é sujeira",
              p3.returncode == 2 and not calls3
              and "plan.yaml.bak" in p3.stderr, f"saiu {p3.returncode}")


def _commits(root, msg):
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", msg], cwd=root, check=True)


def test_committed_file_that_vanished_outside_the_run_does_not_suggest_dirty_ok():
    """On 14/09 Insync deleted `docs/tasks/wego-2229-.../` (9 committed
    files) from the main clone an hour and a half after the run stopped. The
    refusal blamed the run and suggested `--dirty-ok`, which would make the next item run
    over the missing folder. Deletion of a committed file that the last run
    did not touch is another thing, and the way out is `git restore`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        folder = root / "docs" / "tasks" / "wego-2229-remoção"
        folder.mkdir(parents=True)
        for n in ("00-SEAMS.md", "01-PLAN.md"):
            (folder / n).write_text(n, encoding="utf-8")
        _commits(root, "docs")
        binv = fake_claude(
            tmp, "marca(primeiro_pendente(), status='done')\nsys.exit(0)")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p1, _ = run_until(root, binv, plan, ["--for", "2h", "--max-failures", "1"])
        subprocess.run(["git", "checkout", "-q", "--", str(plan)], cwd=root,
                       check=True)
        for f in folder.iterdir():
            f.unlink()
        folder.rmdir()
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("deleção fantasma ainda recusa a largada",
              p.returncode == 2 and not calls, f"saiu {p.returncode}")
        check("...dizendo que o arquivo sumiu fora do run",
              "vanished from disk" in p.stderr and "outside the run" in p.stderr,
              p.stderr[:600])
        # The whole line: the folder that vanished, and not the files one by one (which
        # also start with the folder name).
        check("...e mandando restaurar a pasta com git restore",
              "    git restore -- docs/tasks/wego-2229-remoção\n" in p.stderr,
              p.stderr[:600])
        check("...sem sugerir --dirty-ok", "--dirty-ok" not in p.stderr,
              p.stderr[:600])

        # Ghost and real dirt together: the dirt goes to the "there is more"
        # list, and the files of the accented folder do not show up again there
        # (`git status` writes their name escaped).
        (root / "lixo.txt").write_text("pendura", encoding="utf-8")
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        more = p.stderr.split("And there are", 1)
        check("fantasma com sujeira ao lado recusa",
              p.returncode == 2 and not calls, f"saiu {p.returncode}")
        check("...e a sujeira de verdade é a única de 'há mais'",
              len(more) == 2 and more[1].startswith(" 1 more modified file(s)")
              and "lixo.txt" in more[1] and "wego-2229" not in more[1],
              p.stderr[:800])


def test_change_in_file_the_last_item_touched_keeps_todays_refusal():
    """The counterpoint: a file the previous run touched and which is different on
    disk is a change that gets confused with the run's. The message stays the one
    from before, with the `--dirty-ok` escape. It includes deletion: if the last item
    committed the file, its vanishing is not a ghost. The accented name is on
    purpose: git escapes `relatório.txt` in `status` and in `diff`, and the
    first version compared the escapes and called the file a ghost."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        (root / "tocado.txt").write_text("v0", encoding="utf-8")
        (root / "relatório.txt").write_text("v0", encoding="utf-8")
        (root / "intocado.txt").write_text("v0", encoding="utf-8")
        _commits(root, "base2")
        binv = fake_claude(
            tmp,
            "import subprocess\n"
            "open('tocado.txt','w').write('v1')\n"
            "open('relatório.txt','w').write('v1')\n"
            "subprocess.run(['git','-c','user.email=t@t','-c','user.name=t',"
            "'commit','-qam','item'])\n"
            "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p1, _ = run_until(root, binv, plan, ["--for", "2h", "--max-failures", "1"])
        launch = [e for e in ledger_of(root) if e.get("evento") == "run_start"]
        check("o run anterior deixou branch e base no registro",
              launch and launch[-1].get("base") and launch[-1].get("branch"),
              str(launch))
        subprocess.run(["git", "checkout", "-q", "--", str(plan)], cwd=root,
                       check=True)
        (root / "tocado.txt").write_text("mexido", encoding="utf-8")
        (root / "relatório.txt").unlink()
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("mudança em arquivo tocado recusa",
              p.returncode == 2 and not calls, f"saiu {p.returncode}")
        check("...com a mensagem de hoje, que nomeia --dirty-ok",
              "modified file(s)" in p.stderr and "--dirty-ok" in p.stderr,
              p.stderr[:600])
        check("...e não chama a deleção de arquivo tocado de fantasma",
              "vanished from disk" not in p.stderr, p.stderr[:600])

        # With a real ghost beside it, the deletion of the touched file does not
        # vanish: it goes to the "there is more" list, by the raw name.
        (root / "intocado.txt").unlink()
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        more = p.stderr.split("And there are", 1)
        check("fantasma ao lado de arquivo tocado vira a recusa nova",
              "1 committed file(s) vanished" in p.stderr
              and "git restore -- intocado.txt\n" in p.stderr, p.stderr[:800])
        check("...e a deleção do arquivo tocado segue listada em 'há mais'",
              len(more) == 2 and more[1].startswith(" 2 more modified file(s)")
              and " D relatório.txt" in more[1] and "tocado.txt" in more[1],
              p.stderr[:800])


def test_missing_queue_refuses_before_firing():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        env = dict(os.environ)
        env["PATH"] = f"{binv}:{env['PATH']}"
        env["FAKE_PLANO"] = str(plan)
        env["FAKE_CHAMADAS"] = str(root.parent / "chamadas.jsonl")
        p = subprocess.run([sys.executable, str(CEPA_UNTIL), "nao-existe",
                            "--repo", str(root), "--for", "2h"],
                           capture_output=True, text=True, env=env, timeout=60)
        check("fila inexistente recusa", p.returncode == 2, f"saiu {p.returncode}")
        check("...e a recusa nomeia a fila",
              "nao-existe" in p.stderr, p.stderr[:300])


# ── 4. the contract with the subprocess ─────────────────────────────────────

def test_permissions_granted_by_default_and_can_be_turned_off():
    """Owner's decision: without `--dangerously-skip-permissions` the subprocess jams
    at the first request and the night dies in silence. It stays on by default and
    can be turned off, never the other way around."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("por default o subprocesso nasce sem pedir permissão",
              calls and "--dangerously-skip-permissions" in calls[0],
              str(calls))
        check("...e o banner diz isso em voz alta",
              "--dangerously-skip-permissions ON" in p.stdout,
              p.stdout[:600])

        root2 = build_repo(tempfile.mkdtemp(), [item("a1")])
        plan2 = root2 / ".claude" / "programs" / "fila" / "plan.yaml"
        p2, calls2 = run_until(root2, binv, plan2, ["--for", "2h", "--with-permissions"])
        check("--with-permissions tira a flag",
              calls2 and "--dangerously-skip-permissions" not in calls2[-1],
              str(calls2))


def test_until_computes_the_next_time():
    """`--until 07:00` is one of the two documented ways to give the window, and
    had not a single test — all the coverage went through `--for`."""
    from datetime import datetime, timedelta
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"

        target = datetime.now() + timedelta(hours=3)
        p, _ = run_until(root, binv, plan,
                    ["--until", target.strftime("%H:%M"), "--dry-run"])
        check("--until aceita HH:MM", p.returncode == 0, p.stderr[:300])
        check("...e o prazo é o horário pedido, no dia certo",
              target.strftime("%d/%m %H:%M") in p.stdout, p.stdout[:800])

        # A time already past today = tomorrow. Without this, `--until 07:00` typed
        # at 11pm would give a NEGATIVE window and the run would die at the launch.
        past = datetime.now() - timedelta(hours=2)
        tomorrow = past + timedelta(days=1)
        p2, _ = run_until(root, binv, plan,
                     ["--until", past.strftime("%H:%M"), "--dry-run"])
        check("horário já passado hoje vira o de amanhã",
              tomorrow.strftime("%d/%m %H:%M") in p2.stdout, p2.stdout[:800])


def test_until_malformed_is_refused_naming_the_flag():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        for bad in ("7h", "25:00", "abc"):
            p, calls = run_until(root, binv, plan, ["--until", bad])
            check(f"--until {bad!r} é recusado", p.returncode == 2,
                  f"saiu {p.returncode}")
            check(f"...e a recusa nomeia --until e o valor",
                  f"--until {bad!r}" in p.stderr, p.stderr[:300])
            check("...e nada foi disparado", not calls, str(calls))


def test_slack_and_reserve_have_the_declared_defaults():
    """The two numbers that decide the cut at the ends of the window. They stay pinned
    because they are the difference between an item killed half done and an item that
    finished: the minimum reserve decides what does NOT start, the slack decides how much
    an item already running may go past the deadline. Slack at 60min is the owner's decision
    (2026-08-30), revising the initial 30min."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, _ = run_until(root, binv, plan, ["--for", "12h", "--dry-run"])
        check("a folga default é 60min",
              "kills an item that runs 1h00 past the deadline" in p.stdout, p.stdout[:800])
        check("a reserva mínima default é 45min",
              "no item starts with less than 45min left" in p.stdout, p.stdout[:800])


def test_dry_run_executes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h", "--dry-run"])
        check("--dry-run não dispara", not calls, str(calls))
        check("...e nomeia o 1º item que rodaria", "a1" in p.stdout, p.stdout[:600])
        check("...e a fila fica intacta",
              all(it["status"] == "pending"
                  for it in yaml.safe_load(plan.read_text())["items"]))


def test_item_that_exceeds_the_slack_is_killed_with_the_whole_group():
    """The slack (60min by default) only exists because something makes it count: the
    kill of the process GROUP. The group, and not only `claude`, because what
    holds the tree is the build it fired — killing the parent would leave the child
    orphaned running all night. Nothing exercised that path.

    Window in seconds (the parser accepts a fraction of a minute), otherwise the test
    would take an hour. (Found by the proof gate, 2026-08-30.)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        mark = Path(tmp) / "filho-sobreviveu.txt"
        body = (
            'import subprocess, time\n'
            'filho = [sys.executable, \'-c\', \'import sys,time; time.sleep(25); open(sys.argv[1], "w").write("vivo")\', os.environ[\'FAKE_FILHO\']]\n'
            'subprocess.Popen(filho)\n'
            'time.sleep(120)\n')
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan,
                           ["--for", "0.2m", "--min-reserve", "0.05m",
                            "--slack", "0.05m"],
                           timeout=180, extra_env={"FAKE_FILHO": str(mark)})
        check("o item foi disparado", len(calls) == 1, str(calls))
        ends = [e for e in ledger_of(root) if e.get("evento") == "item_end"]
        check("o item que estourou a folga é registrado como timeout",
              ends and ends[0]["timeout"] is True, str(ends))
        check("...e timeout NÃO é progresso",
              ends and ends[0]["progresso"] is False, str(ends))
        check("...e o item continua pendente na fila",
              yaml.safe_load(plan.read_text())["items"][0]["status"] == "pending")
        # ATTENTION to the clock: the child would only write at ~25s, and the whole run
        # ends at ~15s. Checking the marker right away would give "does not exist" even
        # with the wrong kill — it was the hole a perturbation (killing only the parent,
        # `proc.terminate()`) went through GREEN. So we wait until the hour
        # when the orphan would have written has passed, and only then charge the silence.
        limit = time.monotonic() + 20
        while time.monotonic() < limit and not mark.exists():
            time.sleep(0.5)
        check("o processo-filho morreu junto (kill do grupo, não só do pai)",
              not mark.exists(),
              "o filho sobreviveu ao kill — killpg não pegou o grupo")
        check("o run termina reconhecendo o prazo",
              [e for e in ledger_of(root)
               if e.get("evento") == "run_end"][0]["motivo"] == "prazo",
              str(ledger_of(root)[-1]))


def test_process_that_ignores_sigterm_is_killed_by_sigkill():
    """SIGTERM is a REQUEST, and a build with a trap can refuse it. Without the
    escalation to SIGKILL, the supervisor would think it killed and the process would keep
    running all night. Only a process that IGNORES SIGTERM exercises that
    path — without it the escalation could vanish with no test accusing it.
    (Found by perturbing the perturbation, 2026-08-30.)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        mark = Path(tmp) / "filho-sobreviveu.txt"
        body = (
            'import signal, subprocess, time\n'
            'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
            'filho = [sys.executable, \'-c\', \'import sys,signal,time; \'\n'
            '         \'signal.signal(signal.SIGTERM, signal.SIG_IGN); \'\n'
            '         \'time.sleep(25); open(sys.argv[1], "w").write("vivo")\',\n'
            '         os.environ[\'FAKE_FILHO\']]\n'
            'subprocess.Popen(filho)\n'
            'time.sleep(120)\n')
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan,
                           ["--for", "0.2m", "--min-reserve", "0.05m",
                            "--slack", "0.05m"],
                           timeout=200,
                           extra_env={"FAKE_FILHO": str(mark),
                                      "CEPA_UNTIL_GRACA_SIGTERM": "2"})
        ends = [e for e in ledger_of(root) if e.get("evento") == "item_end"]
        check("o item que ignora SIGTERM ainda é registrado como timeout",
              ends and ends[0]["timeout"] is True, str(ends))
        limit = time.monotonic() + 22
        while time.monotonic() < limit and not mark.exists():
            time.sleep(0.5)
        check("quem ignora o SIGTERM morre no SIGKILL", not mark.exists(),
              "o processo sobreviveu à escalada — o SIGKILL não chegou")


def test_queue_warning_reaches_the_record_and_the_screen():
    """An orphan reservation (dead run that dropped the reserved item) is returned by
    `queue` as a WARNING. In the morning, that warning is the only clue that a previous
    session died in the middle — it vanishes silently if nobody passes it on."""
    import socket
    from datetime import datetime, timezone
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    owner = {"session_id": "sessao-morta", "pid": dead.pid,
            "hostname": socket.gethostname(), "cwd": "/tmp",
            "started_at": datetime.now(timezone.utc).isoformat()}
    with tempfile.TemporaryDirectory() as tmp:
        it = item("a1")
        it.update(status="in_progress", claimed_by=owner)
        root = build_repo(tmp, [it])
        binv = fake_claude(tmp, "marca(primeiro_pendente() or 'a1', status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("a reserva órfã volta a ser executável", len(calls) == 1,
              f"disparou {len(calls)}x")
        warnings = [e for e in ledger_of(root) if e.get("evento") == "aviso"]
        check("o aviso da fila é gravado no registro", warnings, str(ledger_of(root)))
        check("...e diz que a reserva era órfã",
              any("órfã" in (a.get("texto") or "") for a in warnings), str(warnings))
        check("...e aparece na tela também",
              "órfã" in p.stdout, p.stdout[:900])


def test_branch_different_from_the_launch_ends_the_run():
    """Owner's decision: a commit per item on a single branch. Since 2026-09-24 the
    watched branch is the night one (`until/<run>`), in the worktree where the
    subprocess wakes up — switching branches THERE would scatter the night.
    (Found by the acceptance gate, 2026-08-30.)"""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        body = ("ident = primeiro_pendente()\n"
                 "marca(ident, status='done')\n"
                 "if ident == 'a1':\n"
                 "    import subprocess\n"
                 "    subprocess.run(['git', 'checkout', '-q', '-b', 'outra'])\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("o run para quando a branch muda", len(calls) == 1,
              f"disparou {len(calls)}x")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("e o motivo é `branch-mudou`", end["motivo"] == "branch-mudou",
              str(end))
        check("...e o detalhe nomeia as duas branches",
              "outra" in (end.get("detalhe") or "")
              and "until/" in (end.get("detalhe") or ""), str(end))
        check("os itens seguintes NÃO foram executados",
              yaml.safe_load(plan.read_text())["items"][1]["status"] == "pending")


# ── 3. account usage ceiling ────────────────────────────────────────────────

REAL_LIMIT = "You've hit your session limit \u00b7 resets 8:40pm (America/Sao_Paulo)"


def _hour_12(dt):
    h = dt.hour % 12 or 12
    return f"{h}:{dt.minute:02d}{'am' if dt.hour < 12 else 'pm'}"


# The same text with the reset 5h ahead: outside any 2h window, at
# any hour of the day. With a fixed time the case depended on the clock — the
# supervisor now WAITS for a reset that fits in the window.
FAR_RESET = _hour_12(datetime.now() + timedelta(hours=5))
FAR_LIMIT = f"You've hit your session limit \u00b7 resets {FAR_RESET}"


def test_account_usage_limit_stops_the_run_without_blaming_the_item():
    """The verbatim message from the 2026-08-30 run.

    It came with exit 1 and the item stalled, which is EXACTLY the signature of "the
    item did not move" — and that is why two attempts of 92s and 4s entered the
    circuit breaker as if WEGO-1941 were systematically bad. The ceiling is the
    account's: repeating does not lift it, and the morning report cannot accuse the card.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2"), item("a3")])
        binv = fake_claude(tmp, f"print({FAR_LIMIT!r})\nsys.exit(1)")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("bateu o teto com reset fora da janela e parou na primeira tentativa", len(calls) == 1,
              f"disparou {len(calls)}x")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("...com motivo próprio, não `disjuntor`",
              end["motivo"] == "limite-de-uso", str(end))
        check("...e o item NÃO entra na conta de falhas",
              end["sem_progresso"] == 0 and end["limite_de_uso"] == 1, str(end))
        ev = [e for e in ledger_of(root) if e.get("evento") == "limite_de_uso"]
        check("...o registro guarda o horário do reset",
              ev and ev[0].get("reset") == FAR_RESET, str(ev))
        check("...o relatório diz em voz alta que não é falha do item",
              "not the item's fault" in p.stdout, p.stdout[-500:])
        check("...e o item continua pendente, sem culpa gravada",
              yaml.safe_load(plan.read_text())["items"][0]["status"] == "pending")


def test_usage_ceiling_only_stops_when_the_item_did_not_advance():
    """An item that CLOSED does not become a stop, whatever happens in the output.
    Without this order, a report that mentions the phrase would kill a live window.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(
            tmp, f"marca(primeiro_pendente(), status='done')\nprint({REAL_LIMIT!r})")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("os dois itens rodaram", len(calls) == 2, f"{len(calls)}x")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("...e o run terminou pela fila, não pelo teto de uso",
              end["motivo"] == "end-of-queue" and end["limite_de_uso"] == 0, str(end))


def test_limit_mid_long_output_does_not_stop_the_run():
    """The recognizer looks at the END of this attempt's output. A phrase quoted in the
    middle of a long report is agent prose, not the account hitting the ceiling —
    and treating it as a ceiling would kill the night over a quotation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = (f"print({REAL_LIMIT!r})\n"
                 "print('relatorio: ' + 'x' * 4000)\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h", "--max-failures", "3"])
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("a citação no meio não vira teto de uso",
              end["limite_de_uso"] == 0, str(end))
        check("...e o item conta como falha normal", end["sem_progresso"] >= 1,
              str(end))


# ── 4. per-item attempt ceiling ─────────────────────────────────────────────

def test_attempt_ceiling_takes_the_item_off_the_front_and_the_queue_moves():
    """The WEGO-1941 case: an item that does not move was re-offered by
    `queue` forever and ate 3 of the run's 5 attempts, with 15 pending
    behind it. On the second attempt it becomes `blocked` and the queue goes on."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        body = ("alvo = primeiro_pendente()\n"
                 "if alvo and alvo != 'a1':\n"
                 "    marca(alvo, status='done')\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        # Counting only the TOTAL of firings would let the version without a ceiling pass: it
        # also fires 3 times, all three on a1, and dies in the circuit breaker. What
        # tells the two apart is PER ITEM.
        by_item = {}
        for e in ledger_of(root):
            if e.get("evento") == "item_start":
                by_item[e["id"]] = by_item.get(e["id"], 0) + 1
        check("o item preso gastou 2 tentativas, não mais",
              by_item.get("a1") == 2, str(by_item))
        check("...e o item de trás foi alcançado", by_item.get("a2") == 1,
              str(by_item))
        after = {it["id"]: it for it in yaml.safe_load(plan.read_text())["items"]}
        check("...o item preso ficou `blocked`",
              after["a1"]["status"] == "blocked", str(after["a1"]))
        check("...com a evidência dizendo que foi o supervisor, não um veredito",
              "consecutive `cepa-until` attempts" in (after["a1"]["evidence"] or ""),
              str(after["a1"].get("evidence"))[:200])
        check("...a reserva órfã foi limpa junto",
              not after["a1"].get("claimed_by"), str(after["a1"]))
        check("...e a FILA ANDOU: o item de trás fechou",
              after["a2"]["status"] == "done", str(after["a2"]))
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"][0]
        check("...o run acaba pela fila, não pelo disjuntor",
              end["motivo"] == "end-of-queue" and end["esgotados"] == 1, str(end))
        check("...e o relatório cobra o item que ficou blocked",
              "taken off the front of the queue" in p.stdout and "a1" in p.stdout,
              p.stdout[-600:])


def test_attempt_that_advances_does_not_spend_the_item_ceiling():
    """The 2nd attempt has a measured value: WEGO-2206 failed stuck on a background
    build and CLOSED on the repeat. The ceiling cannot punish whoever advanced."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        body = ("n = len(open(os.environ['FAKE_CHAMADAS']).read().splitlines())\n"
                 "if n == 2:\n"
                 "    marca(primeiro_pendente(), status='done')\n")
        binv = fake_claude(tmp, body)
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        check("a repetição aconteceu e fechou o item", len(calls) == 2,
              f"disparou {len(calls)}x")
        check("...e o item está done, não blocked",
              yaml.safe_load(plan.read_text())["items"][0]["status"] == "done")


def test_invalid_attempts_per_item_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "pass")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan,
                           ["--for", "2h", "--attempts-per-item", "0"])
        check("--attempts-per-item 0 é recusado", p.returncode == 2,
              f"saiu {p.returncode}")
        check("...e nada foi disparado", not calls, str(calls))


def test_record_writes_one_event_per_item():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1"), item("a2")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        p, calls = run_until(root, binv, plan, ["--for", "2h"])
        ev = ledger_of(root)
        check("o registro abre com run_start",
              ev and ev[0]["evento"] == "run_start", str(ev[:1]))
        ends = [e for e in ev if e.get("evento") == "item_end"]
        check("um item_end por item", len(ends) == 2, str(ends))
        check("cada item_end carrega status, exit e segundos",
              all({"status", "exit_code", "segundos", "progresso"} <= set(f)
                  for f in ends), str(ends))
        check("o registro fecha com run_end",
              ev[-1]["evento"] == "run_end", str(ev[-1:]))


def _fake_supervisor(root, queue, pid, state="rodando", item_list=()):
    """Writes the estado.json and the .jsonl of a run of the queue `fila`, as the real
    `cepa-until` leaves them."""
    d = Path(root) / ".claude" / "programs" / queue / "until"
    d.mkdir(parents=True, exist_ok=True)
    deadline = (datetime.now() + timedelta(hours=3)).isoformat()
    run = "2026-10-15-1853"
    state_dict = {"run": run, "fila": queue, "estado": state, "branch": "until/x",
           "registro": f"{run}.jsonl", "pid": pid,
           "host": socket.gethostname(), "prazo": deadline}
    (d / f"{run}.estado.json").write_text(json.dumps(state_dict), encoding="utf-8")
    evs = [{"evento": "run_start", "fila": queue, "prazo": deadline, "pid": pid}]
    evs += [{"evento": "item_start", "id": i} for i in item_list]
    (d / f"{run}.jsonl").write_text(
        "\n".join(json.dumps(e) for e in evs) + "\n", encoding="utf-8")


def _cepa_until_process():
    return subprocess.Popen([sys.executable, "-c",
                             "import time; time.sleep(60)", "cepa-until"])


def test_live_run_of_the_same_queue_refuses_the_launch():
    """fb-20261015-4: launching `cepa-until` with a run of the same queue still standing
    refused as "dirty tree" and suggested `--dirty-ok`. Two supervisors on the
    same queue is the failure: refuses before the dirt guard, with no escape."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        alive = _cepa_until_process()
        try:
            _fake_supervisor(root, "fila", alive.pid)
            for extra in ([], ["--dirty-ok"]):
                p, calls = run_until(root, binv, plan, ["--for", "2h"] + extra)
                check(f"run vivo recusa a largada {extra}",
                      p.returncode == 2 and not calls,
                      f"saiu {p.returncode}: {p.stderr[:300]}")
                check("...a mensagem diz que já há um run, com o pid",
                      "a run of this queue is already in progress" in p.stderr
                      and f"pid {alive.pid}" in p.stderr, p.stderr[:300])
                check("...e não oferece --dirty-ok",
                      "--dirty-ok" not in p.stderr, p.stderr[:300])
            # dead pid: the same estado.json stops blocking
            alive.kill()
            alive.wait()
            p, calls = run_until(root, binv, plan, ["--for", "2h"])
            check("pid morto não barra: o run larga",
                  len(calls) == 1, f"saiu {p.returncode}: {p.stderr[:300]}")
        finally:
            alive.kill()
            alive.wait()
        # a state that is not `rodando` does not block either
        (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
        subprocess.run(["git", "checkout", "-q", "--", str(plan)], cwd=root,
                       check=True)
        alive = _cepa_until_process()
        try:
            _fake_supervisor(root, "fila", alive.pid, state="esperando-dono")
            p, calls = run_until(root, binv, plan, ["--for", "2h"])
            check("estado esperando-dono não barra",
                  len(calls) == 1, f"saiu {p.returncode}: {p.stderr[:300]}")
        finally:
            alive.kill()
            alive.wait()


def test_plan_of_another_queue_dirtied_by_the_live_run_is_not_dirt():
    """The `plan.yaml` of ANOTHER queue, which a live run of it writes via
    `cepa-plan start/finish`, is not dirt; any other difference is."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        other = root / ".claude" / "programs" / "outra" / "plan.yaml"
        other.parent.mkdir(parents=True)
        base = {"schema_version": 2, "mode": "single-track",
                "program": "outra", "source": "teste",
                "items": [item("o1"), item("o2")]}
        other.write_text(yaml.safe_dump(base, allow_unicode=True),
                         encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", "outra"], cwd=root, check=True)
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"

        def changes(target, fields_o1=None, fields_o2=None):
            p = yaml.safe_load(yaml.safe_dump(base))
            p["items"][0].update(fields_o1 or {})
            p["items"][1].update(fields_o2 or {})
            target.write_text(yaml.safe_dump(p, allow_unicode=True),
                            encoding="utf-8")

        of_run = {"status": "in_progress", "claimed_by": {"run": "x"},
                  "evidence": "feito"}

        def tries(live_pid, **changed):
            subprocess.run(["git", "checkout", "-q", "--", str(plan),
                            str(other)], cwd=root, check=True)
            (Path(tmp) / "chamadas.jsonl").unlink(missing_ok=True)
            _fake_supervisor(root, "outra", live_pid, item_list=["o1"])
            changes(other, **changed)
            return run_until(root, binv, plan, ["--for", "2h"])

        alive = _cepa_until_process()
        try:
            p, calls = tries(alive.pid, fields_o1=of_run)
            check("plan de outra fila escrito pelo run vivo não é sujeira",
                  "modified file(s)" not in p.stderr and len(calls) == 1,
                  f"saiu {p.returncode}: {p.stderr[:300]}")
            p, calls = tries(alive.pid, fields_o1=dict(of_run, title="x"))
            check("...mudar também o title do item ainda é sujeira",
                  p.returncode == 2 and not calls
                  and "modified file(s)" in p.stderr, p.stderr[:300])
            p, calls = tries(alive.pid, fields_o2=of_run)
            check("...mudar item que o run não iniciou ainda é sujeira",
                  p.returncode == 2 and not calls
                  and "modified file(s)" in p.stderr, p.stderr[:300])
            check("...e a lista nomeia o plano sujo",
                  "outra/plan.yaml" in p.stderr, p.stderr[:300])
        finally:
            alive.kill()
            alive.wait()
        p, calls = tries(alive.pid, fields_o1=of_run)
        check("...com o supervisor morto o mesmo diff é sujeira",
              p.returncode == 2 and not calls
              and "modified file(s)" in p.stderr, p.stderr[:300])


def test_live_run_refuses_before_the_dirt_guard():
    """The live run's refusal comes BEFORE the dirt guard: with a run of the
    queue standing and real dirt in the tree, the message is the live run's, without
    `--dirty-ok` and without the count of modified files."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        binv = fake_claude(tmp, "marca(primeiro_pendente(), status='done')")
        plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
        (root / "lixo.txt").write_text("sujeira real\n", encoding="utf-8")
        alive = _cepa_until_process()
        try:
            _fake_supervisor(root, "fila", alive.pid)
            p, calls = run_until(root, binv, plan, ["--for", "2h"])
            check("run vivo + árvore suja: recusa com saída 2, sem disparar",
                  p.returncode == 2 and not calls,
                  f"saiu {p.returncode}: {p.stderr[:300]}")
            check("...a mensagem é a do run vivo",
                  "a run of this queue is already in progress" in p.stderr, p.stderr[:300])
            check("...e não a da árvore suja",
                  "--dirty-ok" not in p.stderr
                  and "modified file(s)" not in p.stderr, p.stderr[:300])
        finally:
            alive.kill()
            alive.wait()


def test_dirty_tree_stays_strict_for_the_other_callers():
    """The live-run filter only applies with `live_run_ok=True`; the default
    (used by the other callers of `dirty_tree`) keeps listing the
    other queue's `plan.yaml`."""
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("cepa_until_mod",
                                                  str(CEPA_UNTIL))
    spec = importlib.util.spec_from_loader("cepa_until_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp, [item("a1")])
        other = root / ".claude" / "programs" / "outra" / "plan.yaml"
        other.parent.mkdir(parents=True)
        base = {"schema_version": 2, "mode": "single-track",
                "program": "outra", "source": "teste",
                "items": [item("o1"), item("o2")]}
        other.write_text(yaml.safe_dump(base, allow_unicode=True),
                         encoding="utf-8")
        _commits(root, "outra")
        alive = _cepa_until_process()
        try:
            _fake_supervisor(root, "outra", alive.pid, item_list=["o1"])
            new = yaml.safe_load(yaml.safe_dump(base))
            new["items"][0].update({"status": "in_progress",
                                     "claimed_by": {"run": "x"},
                                     "evidence": "feito"})
            other.write_text(yaml.safe_dump(new, allow_unicode=True),
                             encoding="utf-8")
            strict = mod.dirty_tree(root)
            check("default segue estrito: lista o plan de outra fila",
                  any(l.startswith(" M ")
                      and l.endswith(".claude/programs/outra/plan.yaml")
                      for l in strict or []), f"{strict}")
            loose = mod.dirty_tree(root, live_run_ok=True)
            check("live_run_ok=True filtra o mesmo diff",
                  loose == [], f"{loose}")
        finally:
            alive.kill()
            alive.wait()


def main():
    print("cepa-until — supervisor de janela de tempo\n")
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
