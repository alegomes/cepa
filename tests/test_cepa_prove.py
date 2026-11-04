#!/usr/bin/env python3
"""Tests of `common/bin/cepa-prove` — the Review-column window supervisor — and of
the `cepa <subcommand>` door in the launcher.

Run with `python3 tests/test_cepa_prove.py`.

As in test_cepa_until.py, `claude` is replaced by a fake on the PATH. The fake
does what one `/board-flow:prove-drain --max 1` round would leave behind: a
`docs/proof/<KEY>.yaml` with a verdict, or nothing, or the text "Nothing in
Review". That measures the supervisor's decisions and nothing else:

  - the truth of a round is the ARTIFACT on disk, not the exit code;
  - keys already handled travel in `--skip`, round after round;
  - a round without artifact counts for the circuit breaker; "Nothing in
    Review" ends the run cleanly;
  - artifacts are committed on the current branch after each round;
  - the deadline is respected BEFORE a round, never in the middle.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CEPA_PROVE = REPO / "common" / "bin" / "cepa-prove"
CEPA = REPO / "common" / "bin" / "cepa"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def build_repo(tmp):
    root = Path(tmp) / "repo"
    root.mkdir(parents=True)
    (root / "board-flow.yaml").write_text("defaults:\n  status_map:\n    in_review: Review\n")
    (root / "docs" / "proof").mkdir(parents=True)
    (root / "docs" / "proof" / ".keep").write_text("")
    subprocess.run(["git", "init", "-q", "."], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    return root


def fake_claude(tmp, rounds):
    """`rounds` is a list; round i does rounds[i]: ("proof", KEY, verdict),
    ("text", "..."), or ("nothing",). Past the list: ("text", "Nothing in Review")."""
    binv = Path(tmp) / "bin"
    binv.mkdir(exist_ok=True)
    (Path(tmp) / "rounds.json").write_text(json.dumps(rounds))
    script = binv / "claude"
    script.write_text(
        f"#!{sys.executable}\n"
        "import os, sys, json\n"
        "tmp = os.environ['FAKE_TMP']\n"
        "with open(os.path.join(tmp, 'chamadas.jsonl'), 'a') as f:\n"
        "    f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "n_path = os.path.join(tmp, 'n')\n"
        "n = int(open(n_path).read()) if os.path.exists(n_path) else 0\n"
        "open(n_path, 'w').write(str(n + 1))\n"
        "rounds = json.load(open(os.path.join(tmp, 'rounds.json')))\n"
        "r = rounds[n] if n < len(rounds) else ['text', 'Nothing in Review (scope: none).']\n"
        "text = ''\n"
        "if r[0] == 'proof':\n"
        "    p = os.path.join(os.getcwd(), 'docs', 'proof', r[1] + '.yaml')\n"
        "    open(p, 'w').write('schema_version: 2\\ncard: ' + r[1] + '\\nverdict: ' + r[2] + '\\n')\n"
        "    text = 'Proved from Review: ' + r[1] + ' ' + r[2]\n"
        "elif r[0] == 'text':\n"
        "    text = r[1]\n"
        "print(json.dumps({'type': 'result', 'result': text, 'session_id': 's' + str(n), 'total_cost_usd': 1.5}))\n",
        encoding="utf-8")
    script.chmod(0o755)
    return binv


def run_prove(root, binv, tmp, args, timeout=120):
    env = dict(os.environ)
    env["PATH"] = f"{binv}:{env['PATH']}"
    env["FAKE_TMP"] = str(tmp)
    env["CEPA_UNTIL_GRACA_SIGTERM"] = "2"
    p = subprocess.run([sys.executable, str(CEPA_PROVE), "--repo", str(root)] + list(args),
                       capture_output=True, text=True, env=env, timeout=timeout)
    calls_path = Path(tmp) / "chamadas.jsonl"
    calls = []
    if calls_path.exists():
        calls = [json.loads(l) for l in calls_path.read_text().splitlines() if l.strip()]
    return p, calls


def ledger_of(root):
    events = []
    for f in sorted((root / ".claude" / "prove").glob("*.jsonl")):
        events += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return events


def git_log(root):
    return subprocess.run(["git", "log", "--format=%s", "--name-only"], cwd=root,
                          capture_output=True, text=True).stdout


# ── 1. the happy run ────────────────────────────────────────────────────────

def test_rounds_skip_handled_keys_and_end_on_empty_review():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [("proof", "WEGO-1", "proven"),
                                 ("proof", "WEGO-2", "needs-human")])
        p, calls = run_prove(root, binv, tmp, ["--for", "2h"])
        check("o run termina 0", p.returncode == 0, p.stderr[-500:])
        check("três rodadas: duas com prova, a terceira acha a Review vazia",
              len(calls) == 3, f"{len(calls)}: {calls}")
        req = [c[1] for c in calls]
        check("1ª rodada sem --skip", "--skip" not in req[0], req[0])
        check("2ª rodada pula WEGO-1", "--skip WEGO-1" in req[1], req[1])
        check("3ª rodada pula WEGO-1,WEGO-2", "--skip WEGO-1,WEGO-2" in req[2], req[2])
        check("cada rodada é `--max 1` em modo não interativo",
              all(c[0] == "-p" and "--max 1" in c[1] and "--dangerously-skip-permissions" in c
                  for c in calls), str(calls))
        ev = ledger_of(root)
        end = [e for e in ev if e.get("evento") == "run_end"]
        check("run_end por `review-vazia`", end and end[0]["motivo"] == "review-vazia",
              json.dumps(end)[:300])
        check("...com os vereditos lidos do artefato",
              end and end[0]["cards"] == {"WEGO-1": "PROVEN", "WEGO-2": "NEEDS-HUMAN"},
              json.dumps(end)[:300])
        log = git_log(root)
        check("os artefatos foram commitados na branch atual, um commit por rodada",
              "proof: WEGO-1 PROVEN" in log and "proof: WEGO-2 NEEDS-HUMAN" in log, log)
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root,
                                capture_output=True, text=True).stdout
        outside = [l for l in status.splitlines() if ".claude/" not in l]
        check("...e a árvore termina limpa (fora do registro do run em .claude/prove/)",
              not outside, status)
        state = json.loads(next((root / ".claude" / "prove").glob("*.estado.json")).read_text())
        check("estado `esperando-dono` porque sobrou um NEEDS-HUMAN",
              state["estado"] == "esperando-dono", state["estado"])
        check("o resumo diz quem ficou pra você", "NEEDS-HUMAN" in p.stdout and "WEGO-2" in p.stdout,
              p.stdout[-600:])


def test_env_marks_the_round_as_unattended():
    """The round must see CEPA_UNTIL_RUN: it is what makes prove-drain skip its
    only confirmation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [])
        probe = Path(binv) / "claude"
        body = probe.read_text()
        probe.write_text(body.replace(
            "text = ''\n",
            "open(os.path.join(tmp, 'env'), 'w').write(os.environ.get('CEPA_UNTIL_RUN', ''))\n"
            "text = ''\n"))
        run_prove(root, binv, tmp, ["--for", "2h"])
        check("CEPA_UNTIL_RUN=1 no ambiente da rodada",
              (Path(tmp) / "env").read_text() == "1")


# ── 2. the circuit breaker ───────────────────────────────────────────────────

def test_rounds_without_artifact_trip_the_breaker():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [("text", "SKIPPED: reserved by other")] * 10)
        p, calls = run_prove(root, binv, tmp, ["--for", "2h"])
        check("três rodadas e para", len(calls) == 3, f"{len(calls)}")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"]
        check("run_end por `disjuntor`", end and end[0]["motivo"] == "disjuntor",
              json.dumps(end)[:300])


def test_progress_resets_the_breaker():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [("nothing",), ("nothing",),
                                 ("proof", "WEGO-7", "unproven"),
                                 ("nothing",), ("nothing",)])
        p, calls = run_prove(root, binv, tmp, ["--for", "2h"])
        # 2 misses, 1 hit (reset), 2 misses, then "Nothing in Review" from the fake.
        check("a prova zera a contagem do disjuntor: 6 rodadas, fim por review vazia",
              len(calls) == 6, f"{len(calls)}")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"]
        check("...run_end por `review-vazia`", end and end[0]["motivo"] == "review-vazia",
              json.dumps(end)[:300])


def test_max_caps_the_cards():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [("proof", f"WEGO-{i}", "proven") for i in range(9)])
        p, calls = run_prove(root, binv, tmp, ["--for", "2h", "--max", "2"])
        check("--max 2 para depois de dois vereditos", len(calls) == 2, f"{len(calls)}")
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"]
        check("...run_end por `teto`", end and end[0]["motivo"] == "teto", json.dumps(end)[:300])


# ── 3. the clock and the guards ──────────────────────────────────────────────

def test_window_smaller_than_reserve_fires_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [("proof", "WEGO-1", "proven")])
        p, calls = run_prove(root, binv, tmp, ["--for", "10m", "--min-reserve", "25m"])
        check("janela menor que a reserva não dispara rodada", not calls, str(calls))
        end = [e for e in ledger_of(root) if e.get("evento") == "run_end"]
        check("...run_end por `prazo`", end and end[0]["motivo"] == "prazo", json.dumps(end)[:300])


def test_dirty_tree_outside_proofs_is_refused_but_proofs_are_not():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [])
        (root / "docs" / "proof" / "OLD-1.yaml").write_text("card: OLD-1\nverdict: proven\n")
        p, calls = run_prove(root, binv, tmp, ["--for", "2h"])
        check("artefato de prova solto NÃO é árvore suja", p.returncode == 0, p.stderr[-300:])
        (root / "x.txt").write_text("sujo")
        p, calls2 = run_prove(root, binv, tmp, ["--for", "2h"])
        check("arquivo solto fora de docs/proof/ recusa o run", p.returncode == 2
              and "docs/proof" in p.stderr, p.stderr[-300:])
        check("...sem disparar nada", len(calls2) == len(calls), str(calls2))


def test_without_board_flow_yaml_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        (root / "board-flow.yaml").unlink()
        subprocess.run(["git", "commit", "-qam", "sem quadro"], cwd=root, check=True)
        binv = fake_claude(tmp, [])
        p, calls = run_prove(root, binv, tmp, ["--for", "2h"])
        check("sem board-flow.yaml sai 2 e nomeia o arquivo",
              p.returncode == 2 and "board-flow.yaml" in p.stderr, p.stderr[-300:])


def test_dry_run_executes_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [("proof", "WEGO-1", "proven")])
        p, calls = run_prove(root, binv, tmp, ["--for", "2h", "--dry-run", "--scope", "labels = x"])
        check("--dry-run sai 0 sem disparar", p.returncode == 0 and not calls, p.stderr[-300:])
        check("...e o plano mostra o escopo", "labels = x" in p.stdout, p.stdout[-400:])
        check("...e não cria registro", not (root / ".claude" / "prove").exists())


def test_scope_flags_reach_the_round():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [])
        p, calls = run_prove(root, binv, tmp, ["--for", "2h", "--no-scope"])
        check("--no-scope chega na rodada", calls and "--no-scope" in calls[0][1], str(calls))
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [])
        p, calls = run_prove(root, binv, tmp, ["--for", "2h", "--scope", "labels = squad-a"])
        check("--scope chega na rodada, entre aspas",
              calls and '--scope "labels = squad-a"' in calls[0][1], str(calls))


def test_no_commit_leaves_the_artifacts():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [("proof", "WEGO-1", "proven")])
        p, calls = run_prove(root, binv, tmp, ["--for", "2h", "--no-commit"])
        log = git_log(root)
        check("--no-commit não commita", "proof:" not in log, log)
        check("...e o artefato fica no disco", (root / "docs" / "proof" / "WEGO-1.yaml").exists())


# ── 4. the door: `cepa <subcommand>` ─────────────────────────────────────────

def test_cepa_dispatches_to_sibling_scripts():
    p = subprocess.run([str(CEPA), "prove", "--help"], capture_output=True, text=True, timeout=60)
    check("`cepa prove --help` roda o cepa-prove", p.returncode == 0 and "prove-drain" in p.stdout,
          (p.stdout + p.stderr)[-300:])
    p = subprocess.run([str(CEPA), "until", "--help"], capture_output=True, text=True, timeout=60)
    check("`cepa until --help` roda o cepa-until", p.returncode == 0 and "fila" in p.stdout,
          (p.stdout + p.stderr)[-300:])
    p = subprocess.run([str(CEPA), "help"], capture_output=True, text=True, timeout=60)
    check("`cepa help` lista os subcomandos", p.returncode == 0
          and "until" in p.stdout and "prove" in p.stdout and "doctor" in p.stdout,
          (p.stdout + p.stderr)[-500:])
    check("...com a primeira linha de cada docstring",
          "Review" in p.stdout and "TIME WINDOW" in p.stdout, p.stdout[-800:])


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        print(f"\n{t.__name__}")
        try:
            t()
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__} levantou {type(e).__name__}: {e}")
            FAILURES.append(t.__name__)
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): {', '.join(FAILURES)}")
        sys.exit(1)
    print(f"✓ {len(tests)} teste(s) ok")
