#!/usr/bin/env python3
"""Aliases da interface em inglês (item `interface-in-english`, fatia C).

Os nomes fixos de `cepa-until`, `cepa-feedback`, `cepa-clock` e `cepa-tokens`
foram para o inglês; os nomes antigos continuam aceitos. Cada caso roda o nome
antigo e o novo e exige o mesmo resultado.

Rode com `python3 tests/test_cepa_until_aliases_ingles.py`.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# `cepa-feedback` e `cepa-until` emitem telemetria, e cada caso os executa
# como subprocesso: sem isolar, a suíte escreve no ledger de quem a roda
# (tests/test_telemetria_isolada.py varre quem cita hook emissor).
from _telemetria_isolada import isola  # noqa: E402

isola()

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


def mascara(texto):
    """Tira horas, durações e caminhos temporários, que variam entre rodadas."""
    texto = re.sub(r"/[^\s`')]*tmp[^\s`')]*", "<tmp>", texto)
    return re.sub(r"\d", "#", texto)


def test_until_flags_antigas_e_novas_dao_o_mesmo_plano():
    pares = [("--sem-verify", "--no-verify"), ("--sem-analise", "--no-analysis"),
             ("--sujo-ok", "--dirty-ok"), ("--titulo-inteiro", "--full-title"),
             ("--com-permissoes", "--with-permissions"),
             ("--max-falhas", "--max-failures", "4"),
             ("--max-travados", "--max-blocked", "4"),
             ("--tentativas-por-item", "--attempts-per-item", "3"),
             ("--reserva-minima", "--min-reserve", "25m"),
             ("--folga", "--slack", "45m")]
    saidas = {}
    for lado in (0, 1):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = tu.monta_repo(tmp, [tu.item("a1")])
            binv = tu.fake_claude(tmp, "pass")
            plano = raiz / ".claude" / "programs" / "fila" / "plan.yaml"
            args = ["--for", "2h", "--dry-run"]
            for par in pares:
                args += [par[lado]] + list(par[2:])
            env = dict(os.environ, PATH=f"{binv}:{os.environ['PATH']}",
                       FAKE_PLANO=str(plano), FAKE_CHAMADAS=str(Path(tmp) / "c.jsonl"),
                       CEPA_WORKTREE_HOME=str(Path(tmp) / "worktrees"))
            p = subprocess.run([sys.executable, str(tu.CEPA_UNTIL), "fila", "--repo",
                                str(raiz)] + args, capture_output=True, text=True,
                               env=env, timeout=120)
            saidas[lado] = (p.returncode, mascara(p.stdout), mascara(p.stderr))
    check("until: flags antigas aceitas (rc=0)", saidas[0][0] == 0, saidas[0])
    check("until: flags novas aceitas (rc=0)", saidas[1][0] == 0, saidas[1])
    check("until: --dry-run com nomes antigos == com nomes novos",
          saidas[0] == saidas[1], f"{saidas[0]}\n{saidas[1]}")


def test_until_decidir_e_decide_despacham_igual():
    res = []
    for sub in ("decidir", "decide"):
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([sys.executable, str(tu.CEPA_UNTIL), sub,
                                "fila/inexistente", "--repo", tmp],
                               capture_output=True, text=True, timeout=60)
            res.append((p.returncode, mascara(p.stdout), mascara(p.stderr)))
    check("until: `decidir` chega no decide (alvo ruim recusado, rc != 0)",
          res[0][0] != 0 and "cepa-until decide:" in res[0][2], res[0])
    check("until: `decidir` == `decide`", res[0] == res[1], res)


def test_until_sim_e_yes_no_aterrissar_e_fecha_morto():
    for sub in ("aterrissar", "fecha-morto"):
        res = []
        for flag in ("--sim", "--yes"):
            with tempfile.TemporaryDirectory() as tmp:
                p = subprocess.run([sys.executable, str(tu.CEPA_UNTIL), sub,
                                    "fila/x", "--repo", tmp, flag],
                                   capture_output=True, text=True, timeout=60)
                res.append((p.returncode, mascara(p.stdout), mascara(p.stderr)))
        check(f"until {sub}: --sim == --yes", res[0] == res[1], res)
        check(f"until {sub}: --sim e --yes são entendidos pelo parser",
              "unrecognized" not in res[0][2] + res[1][2], res)


def test_feedback_triar_igual_a_triage():
    ev = {}
    for sub, d, n, q, t, o in (("triar", "--destino", "--nota", "--plano", "--alvo", "--origem"),
                               ("triage", "--destination", "--note", "--queue", "--target", "--origin")):
        with tf.Caixa() as c:
            p = c.cli("add", "o gate X barrou", t, "modo-escrita-gate", o, "skill")
            check(f"feedback add {t} {o}: rc=0", p.returncode == 0, p.stderr)
            fid = c.linhas()[0]["id"]
            p = c.cli(sub, fid, d, "BACKLOG.md § X", n, "uma nota")
            check(f"feedback {sub}: rc=0", p.returncode == 0, p.stderr)
            reg = c.linhas()
            ev[sub] = (reg[0]["alvo"], reg[0]["origem"], reg[-1]["tipo"],
                       reg[-1]["destino"], reg[-1]["nota"])
            p = c.cli("list", "--status", "todos",
                      "--sem-cor" if sub == "triar" else "--no-color")
            check(f"feedback list {sub}: flag de cor aceita", p.returncode == 0, p.stderr)
    check("feedback: `triar` com flags antigas == `triage` com flags novas",
          ev["triar"] == ev["triage"], ev)


def test_tokens_e_clock_todas_arquivo():
    with tempfile.TemporaryDirectory() as tmp:
        sess = tt.monta_sessao(Path(tmp), tmp)
        out = []
        for flag in ("--arquivo", "--file"):
            p = subprocess.run([sys.executable, str(BIN / "cepa-tokens"), flag,
                                str(sess), "--json"], capture_output=True, text=True)
            out.append((p.returncode, p.stdout))
        check("tokens: --arquivo == --file", out[0] == out[1] and out[0][0] == 0, out)
        home = Path(tmp) / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home))
        for nome in ("cepa-tokens", "cepa-clock"):
            r = []
            for flag in ("--todas", "--all"):
                p = subprocess.run([sys.executable, str(BIN / nome), flag, "--days", "1"],
                                   capture_output=True, text=True, env=env)
                r.append((p.returncode, p.stdout, p.stderr))
            check(f"{nome}: --todas == --all", r[0] == r[1], r)
            check(f"{nome}: --todas e --all são entendidos pelo parser",
                  "unrecognized" not in r[0][2] + r[1][2], r)


if __name__ == "__main__":
    print("aliases da interface em inglês (cepa-until/feedback/clock/tokens)\n")
    test_until_flags_antigas_e_novas_dao_o_mesmo_plano()
    test_until_decidir_e_decide_despacham_igual()
    test_until_sim_e_yes_no_aterrissar_e_fecha_morto()
    test_feedback_triar_igual_a_triage()
    test_tokens_e_clock_todas_arquivo()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s): {FAILURES}")
        sys.exit(1)
    print("\ntudo verde")
