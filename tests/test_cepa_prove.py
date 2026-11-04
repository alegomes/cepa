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


def run_prove(root, binv, tmp, args, timeout=120, path=None):
    env = dict(os.environ)
    env["PATH"] = path if path is not None else f"{binv}:{env['PATH']}"
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
        kinds = [e["evento"] for e in ev]
        check("registro: run_start, rodada_start/rodada_end por rodada, run_end",
              kinds[0] == "run_start" and kinds.count("rodada_start") == 3
              and kinds.count("rodada_end") == 3 and kinds[-1] == "run_end", str(kinds))
        ends = [e for e in ev if e.get("evento") == "rodada_end"]
        check("...e cada rodada_end traz o veredito lido do artefato",
              ends[0]["cards"] == [{"key": "WEGO-1", "veredito": "PROVEN",
                                    "arquivo": "docs/proof/WEGO-1.yaml"}]
              and ends[1]["cards"][0]["veredito"] == "NEEDS-HUMAN" and ends[2]["cards"] == [],
              json.dumps(ends)[:600])
        starts = [e for e in ev if e.get("evento") == "rodada_start"]
        check("...e o rodada_start registra o --skip da vez",
              starts[0]["skip"] == [] and starts[2]["skip"] == ["WEGO-1", "WEGO-2"],
              json.dumps(starts)[:400])


def test_state_is_encerrado_without_needs_human():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [("proof", "WEGO-1", "proven"), ("proof", "WEGO-2", "unproven")])
        p, calls = run_prove(root, binv, tmp, ["--for", "2h"])
        state = json.loads(next((root / ".claude" / "prove").glob("*.estado.json")).read_text())
        check("sem NEEDS-HUMAN o estado final é `encerrado`", state["estado"] == "encerrado",
              state["estado"])
        check("...com os cards e o motivo", state["cards"] == {"WEGO-1": "PROVEN", "WEGO-2": "UNPROVEN"}
              and state["motivo"] == "review-vazia", json.dumps(state)[:300])
        check("...e o resumo na tela nomeia o UNPROVEN", "UNPROVEN     1  WEGO-2" in p.stdout,
              p.stdout[-400:])
        # A second run right after: the first run's record in .claude/prove/ is
        # not dirt, otherwise every run after the first would be refused.
        p2, calls2 = run_prove(root, binv, tmp, ["--for", "2h"])
        check("o registro do run anterior não é árvore suja para o próximo",
              p2.returncode == 0 and len(calls2) == len(calls) + 1, p2.stderr[-300:])


def test_rewritten_artifact_and_nonzero_exit_still_count():
    """The truth of a round is the artifact: a file that already existed and was
    rewritten counts, and a `claude` that exits non-zero after writing it too."""
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        old = root / "docs" / "proof" / "WEGO-1.yaml"
        old.write_text("schema_version: 2\ncard: WEGO-1\nverdict: unproven\n")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "prova antiga"], cwd=root, check=True)
        binv = fake_claude(tmp, [("proof", "WEGO-1", "proven")])
        script = Path(binv) / "claude"
        script.write_text(script.read_text().replace(
            "print(json.dumps(", "print(json.dumps(") + "sys.exit(3) if n == 0 else None\n")
        p, calls = run_prove(root, binv, tmp, ["--for", "2h"])
        ev = ledger_of(root)
        ends = [e for e in ev if e.get("evento") == "rodada_end"]
        check("artefato reescrito é lido com o veredito novo, mesmo com exit 3",
              ends and ends[0]["exit_code"] == 3
              and ends[0]["cards"] == [{"key": "WEGO-1", "veredito": "PROVEN",
                                        "arquivo": "docs/proof/WEGO-1.yaml"}],
              json.dumps(ends)[:400])
        check("...e vai para o --skip da rodada seguinte", len(calls) == 2
              and "--skip WEGO-1" in calls[1][1], str(calls))
        check("...e foi commitado", "proof: WEGO-1 PROVEN" in git_log(root), git_log(root)[:200])
        end = [e for e in ev if e.get("evento") == "run_end"]
        check("...sem contar como falha do disjuntor", end and end[0]["motivo"] == "review-vazia",
              json.dumps(end)[:300])


def test_until_with_permissions_and_cwd():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [])
        script = Path(binv) / "claude"
        script.write_text(script.read_text().replace(
            "text = ''\n",
            "open(os.path.join(tmp, 'cwd'), 'w').write(os.getcwd())\n"
            "text = ''\n"))
        from datetime import datetime, timedelta
        later = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
        p, calls = run_prove(root, binv, tmp, ["--until", later, "--with-permissions"])
        check("--until HH:MM abre a janela e dispara", p.returncode == 0 and len(calls) == 1,
              p.stderr[-300:] + str(calls))
        check("--with-permissions tira o --dangerously-skip-permissions",
              calls and "--dangerously-skip-permissions" not in calls[0], str(calls))
        check("a rodada roda com o clone como diretório de trabalho",
              Path((Path(tmp) / "cwd").read_text()).resolve() == root.resolve(),
              (Path(tmp) / "cwd").read_text())


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
        p, calls3 = run_prove(root, binv, tmp, ["--for", "2h", "--dirty-ok"])
        check("--dirty-ok contorna a recusa", p.returncode == 0 and len(calls3) == len(calls) + 1,
              p.stderr[-300:])


def test_without_claude_on_path_refuses():
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [("proof", "WEGO-1", "proven")])
        empty = Path(tmp) / "empty-bin"
        empty.mkdir()
        p, calls = run_prove(root, binv, tmp, ["--for", "2h"],
                             path=f"{empty}:/usr/bin:/bin")
        check("sem `claude` no PATH sai 2 e nomeia o claude",
              p.returncode == 2 and "`claude`" in p.stderr, p.stderr[-300:])
        check("...sem disparar nada", not calls, str(calls))


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
    # `help` lists only EXECUTABLE siblings: a copy of the launcher in a temp
    # dir (SCRIPT_DIR follows the script's location) next to one executable and
    # one non-executable `cepa-*`.
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "bin"
        d.mkdir()
        launcher = d / "cepa"
        launcher.write_bytes(CEPA.read_bytes())
        launcher.chmod(0o755)
        (d / "cepa-bar").write_text('#!/bin/sh\n# cepa-bar — listed sibling\n')
        (d / "cepa-bar").chmod(0o755)
        (d / "cepa-foo").write_text('#!/bin/sh\n# cepa-foo — NOT executable\n')
        (d / "cepa-foo").chmod(0o644)
        p = subprocess.run([str(launcher), "help"], capture_output=True, text=True, timeout=60)
        check("`cepa help` lista só os cepa-* executáveis",
              p.returncode == 0 and "bar" in p.stdout and "foo" not in p.stdout,
              (p.stdout + p.stderr)[-300:])
    # Real arguments after the subcommand reach the script WITHOUT the
    # subcommand word (the `shift`): with it, argparse would choke on "prove".
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        binv = fake_claude(tmp, [])
        env = dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}")
        p = subprocess.run([str(CEPA), "prove", "--repo", str(root), "--for", "1h",
                            "--dry-run", "--scope", "labels = via-porta"],
                           capture_output=True, text=True, env=env, timeout=60)
        check("`cepa prove <args>` entrega os args ao cepa-prove sem a palavra `prove`",
              p.returncode == 0 and "labels = via-porta" in p.stdout
              and "dry-run" in p.stdout, (p.stdout + p.stderr)[-400:])


def test_cepa_still_launches_a_session_for_flags_and_non_scripts():
    """A flag or a word that is not a sibling script is a session launch: the
    arguments reach the real `claude` untouched and no `cepa-*` runs."""
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "claude"
        fake.write_text(f"#!{sys.executable}\nimport sys, json\n"
                        f"open({str(Path(tmp) / 'argv')!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
        fake.chmod(0o755)
        env = dict(os.environ, CLAUDE_WT_CLAUDE_BIN=str(fake), CEPA_PREFLIGHT="off")
        env.pop("CEPA_PROMPT", None)   # the machine's default prompt would pad the argv
        for args in (["--version"], ["FOO-1"], ["plan the migration"]):
            # cwd outside any git repo: the launcher then "just is claude".
            p = subprocess.run([str(CEPA), *args], capture_output=True, text=True,
                               env=env, cwd=tmp, timeout=60)
            check(f"`cepa {' '.join(args)}` abre sessão, não despacha", p.returncode == 0,
                  (p.stdout + p.stderr)[-300:])
        got = [json.loads(l) for l in (Path(tmp) / "argv").read_text().splitlines()]
        # The launcher prepends its own flags (permission mode); the user's
        # arguments come last and untouched.
        check("...e o claude recebeu os argumentos intactos",
              [g[-1] for g in got] == ["--version", "FOO-1", "plan the migration"],
              str([g[-1:] for g in got]))


def test_cepa_help_flags_and_typos():
    """Discovery of the subcommands (2026-11-04): `--help`/`-h` print the same
    list as `cepa help` plus the launcher's flags; deprecated aliases carry a
    clean label; a lone word within two typos of a sibling is refused with the
    nearest name instead of opening a session whose first message is the typo."""
    ref = subprocess.run([str(CEPA), "help"], capture_output=True, text=True, timeout=60).stdout
    for flag in ("--help", "-h"):
        p = subprocess.run([str(CEPA), flag], capture_output=True, text=True, timeout=60)
        check(f"`cepa {flag}` lista os subcomandos como `cepa help`",
              p.returncode == 0 and p.stdout == ref and "until" in p.stdout, (p.stdout + p.stderr)[-300:])
    check("...e a seção de flags do launcher", "flags do launcher:" in ref and "--slice" in ref
          and "--mode" in ref and "--prompt" in ref, ref[-600:])
    check("...e os aliases com rótulo limpo", "(alias antigo de intent)" in ref
          and "(alias antigo de modes)" in ref and "Deprecated" not in ref, ref)
    # `autono` is 3 edits from `autonomy`: only the prefix fast path finds it.
    for typo, near in (("untl", "until"), ("prov", "prove"), ("docto", "doctor"), ("autono", "autonomy")):
        p = subprocess.run([str(CEPA), typo], capture_output=True, text=True, timeout=60)
        check(f"`cepa {typo}` recusa e sugere `cepa {near}`",
              p.returncode == 2 and "Você quis dizer" in p.stderr
              and f"cepa {near}" in p.stderr and "cepa help" in p.stderr,
              (p.stdout + p.stderr)[-300:])
    # Short words and words far from any sibling are prompts, not typos: they
    # reach claude (cwd outside a repo, fake claude records argv).
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "claude"
        fake.write_text(f"#!{sys.executable}\nimport sys, json\n"
                        f"open({str(Path(tmp) / 'argv')!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n")
        fake.chmod(0o755)
        env = dict(os.environ, CLAUDE_WT_CLAUDE_BIN=str(fake), CEPA_PREFLIGHT="off")
        env.pop("CEPA_PROMPT", None)
        # `untl foo` is two words: a prompt, never a typo, even with `untl` in it.
        for args in (["go"], ["xyzzyqq"], ["untl", "foo"]):
            p = subprocess.run([str(CEPA), *args], capture_output=True, text=True, env=env, cwd=tmp, timeout=60)
            check(f"`cepa {' '.join(args)}` abre sessão, não é tratado como erro de digitação",
                  p.returncode == 0, (p.stdout + p.stderr)[-300:])
        got = [json.loads(l)[-2:] for l in (Path(tmp) / "argv").read_text().splitlines()]
        check("...e o claude recebeu as palavras",
              [g[-1] for g in got[:2]] == ["go", "xyzzyqq"] and got[2] == ["untl", "foo"], str(got))


def test_mode_menu_points_to_cepa_help():
    """The interactive mode menu (needs a tty) carries the footer that names
    `cepa help`, so whoever never thought of asking for help still sees it."""
    import pty, select
    with tempfile.TemporaryDirectory() as tmp:
        root = build_repo(tmp)
        env = dict(os.environ, CEPA_PREFLIGHT="off", CEPA_MODO="")
        env.pop("CEPA_MODO_DEFAULT", None)
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(root)
            os.execve(str(CEPA), [str(CEPA)], env)
        out = b""
        try:
            while b"modo? [" not in out:
                r, _, _ = select.select([fd], [], [], 30)
                if not r:
                    break
                try:
                    chunk = os.read(fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
            os.write(fd, b"\n")   # empty Enter gives up: no session opens
            try:
                while True:
                    r, _, _ = select.select([fd], [], [], 5)
                    if not r:
                        break
                    chunk = os.read(fd, 4096)
                    if not chunk:
                        break
                    out += chunk
            except OSError:
                pass
        finally:
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        text = out.decode("utf-8", "replace")
        check("o menu de modo mostra o rodapé `cepa help`",
              "Em qual modo" in text and "subcomandos do cepa: cepa help" in text, text[-600:])


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
