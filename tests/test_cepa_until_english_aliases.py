#!/usr/bin/env python3
"""Aliases of the English interface (item `interface-in-english`, slice C).

The fixed names of `cepa-until`, `cepa-feedback`, `cepa-clock` and `cepa-tokens`
moved to English; the old names are still accepted. Each case runs the old name
and the new one and demands the same result.

Run with `python3 tests/test_cepa_until_english_aliases.py`.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# `cepa-feedback` and `cepa-until` emit telemetry, and each case runs them
# as a subprocess: without isolating, the suite writes to the ledger of whoever runs it
# (tests/test_isolated_telemetry.py sweeps whoever cites an emitting hook).
from _isolated_telemetry import isolate  # noqa: E402

isolate()

import test_cepa_until as tu  # noqa: E402
import test_cepa_feedback as tf  # noqa: E402
import test_cepa_tokens as tt  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BIN = REPO / "common" / "bin"
FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def mask(plain_text):
    """Removes hours, durations and temporary paths, which vary between rounds."""
    plain_text = re.sub(r"/[^\s`')]*tmp[^\s`')]*", "<tmp>", plain_text)
    return re.sub(r"\d", "#", plain_text)


def test_until_old_and_new_flags_give_the_same_plan():
    pairs = [("--sem-verify", "--no-verify"), ("--sem-analise", "--no-analysis"),
             ("--sujo-ok", "--dirty-ok"), ("--titulo-inteiro", "--full-title"),
             ("--com-permissoes", "--with-permissions"),
             ("--max-falhas", "--max-failures", "4"),
             ("--max-travados", "--max-blocked", "4"),
             ("--tentativas-por-item", "--attempts-per-item", "3"),
             ("--reserva-minima", "--min-reserve", "25m"),
             ("--folga", "--slack", "45m")]
    outputs = {}
    for side in (0, 1):
        with tempfile.TemporaryDirectory() as tmp:
            root = tu.build_repo(tmp, [tu.item("a1")])
            binv = tu.fake_claude(tmp, "pass")
            plan = root / ".claude" / "programs" / "fila" / "plan.yaml"
            args = ["--for", "2h", "--dry-run"]
            for pair in pairs:
                args += [pair[side]] + list(pair[2:])
            env = dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}",
                       FAKE_PLANO=str(plan), FAKE_CHAMADAS=str(Path(tmp) / "c.jsonl"),
                       CEPA_WORKTREE_HOME=str(Path(tmp) / "worktrees"))
            p = subprocess.run([sys.executable, str(tu.CEPA_UNTIL), "fila", "--repo",
                                str(root)] + args, capture_output=True, text=True,
                               env=env, timeout=120)
            outputs[side] = (p.returncode, mask(p.stdout), mask(p.stderr))
    check("until: flags antigas aceitas (rc=0)", outputs[0][0] == 0, outputs[0])
    check("until: flags novas aceitas (rc=0)", outputs[1][0] == 0, outputs[1])
    check("until: --dry-run com nomes antigos == com nomes novos",
          outputs[0] == outputs[1], f"{outputs[0]}\n{outputs[1]}")


def test_until_decidir_and_decide_dispatch_the_same():
    res = []
    for sub in ("decidir", "decide"):
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([sys.executable, str(tu.CEPA_UNTIL), sub,
                                "fila/inexistente", "--repo", tmp],
                               capture_output=True, text=True, timeout=60)
            res.append((p.returncode, mask(p.stdout), mask(p.stderr)))
    check("until: `decidir` chega no decide (alvo ruim recusado, rc != 0)",
          res[0][0] != 0 and "cepa-until decide:" in res[0][2], res[0])
    check("until: `decidir` == `decide`", res[0] == res[1], res)


def test_until_sim_and_yes_on_land_and_close_dead():
    for sub in ("aterrissar", "fecha-morto"):
        res = []
        for flag in ("--sim", "--yes"):
            with tempfile.TemporaryDirectory() as tmp:
                p = subprocess.run([sys.executable, str(tu.CEPA_UNTIL), sub,
                                    "fila/x", "--repo", tmp, flag],
                                   capture_output=True, text=True, timeout=60)
                res.append((p.returncode, mask(p.stdout), mask(p.stderr)))
        check(f"until {sub}: --sim == --yes", res[0] == res[1], res)
        check(f"until {sub}: --sim e --yes são entendidos pelo parser",
              "unrecognized" not in res[0][2] + res[1][2], res)


def test_feedback_triar_same_as_triage():
    ev = {}
    for sub, d, n, q, t, o in (("triar", "--destino", "--nota", "--plano", "--alvo", "--origem"),
                               ("triage", "--destination", "--note", "--queue", "--target", "--origin")):
        with tf.Box() as c:
            p = c.cli("add", "o gate X barrou", t, "write-mode-gate", o, "skill")
            check(f"feedback add {t} {o}: rc=0", p.returncode == 0, p.stderr)
            fid = c.lines()[0]["id"]
            p = c.cli(sub, fid, d, "BACKLOG.md § X", n, "uma nota")
            check(f"feedback {sub}: rc=0", p.returncode == 0, p.stderr)
            reg = c.lines()
            ev[sub] = (reg[0]["alvo"], reg[0]["origem"], reg[-1]["tipo"],
                       reg[-1]["destino"], reg[-1]["nota"])
            p = c.cli("list", "--status", "todos",
                      "--sem-cor" if sub == "triar" else "--no-color")
            check(f"feedback list {sub}: flag de cor aceita", p.returncode == 0, p.stderr)
    check("feedback: `triar` com flags antigas == `triage` com flags novas",
          ev["triar"] == ev["triage"], ev)


def test_tokens_and_clock_all_files():
    with tempfile.TemporaryDirectory() as tmp:
        sess = tt.build_session(Path(tmp), tmp)
        out = []
        for flag in ("--arquivo", "--file"):
            p = subprocess.run([sys.executable, str(BIN / "cepa-tokens"), flag,
                                str(sess), "--json"], capture_output=True, text=True)
            out.append((p.returncode, p.stdout))
        check("tokens: --arquivo == --file", out[0] == out[1] and out[0][0] == 0, out)
        home = Path(tmp) / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home))
        for given_name in ("cepa-tokens", "cepa-clock"):
            r = []
            for flag in ("--todas", "--all"):
                p = subprocess.run([sys.executable, str(BIN / given_name), flag, "--days", "1"],
                                   capture_output=True, text=True, env=env)
                r.append((p.returncode, p.stdout, p.stderr))
            check(f"{given_name}: --todas == --all", r[0] == r[1], r)
            check(f"{given_name}: --todas e --all são entendidos pelo parser",
                  "unrecognized" not in r[0][2] + r[1][2], r)


if __name__ == "__main__":
    print("aliases da interface em inglês (cepa-until/feedback/clock/tokens)\n")
    test_until_old_and_new_flags_give_the_same_plan()
    test_until_decidir_and_decide_dispatch_the_same()
    test_until_sim_and_yes_on_land_and_close_dead()
    test_feedback_triar_same_as_triage()
    test_tokens_and_clock_all_files()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
        sys.exit(1)
    print("\ntudo verde")
