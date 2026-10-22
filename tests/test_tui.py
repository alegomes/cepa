#!/usr/bin/env python3
"""Testes da aparência de TUI dos comandos cepa-* (common/hooks/_tui.py).

O que estes casos seguram:

  - fora do terminal a saída é byte a byte a de antes: é o que os testes dos
    comandos leem, o que um agente recebe pelo Bash e o que um `nohup` grava;
  - `NO_COLOR` e `CEPA_COR=nunca` desligam a decoração; `CEPA_COR=sempre` liga;
  - ligada, a linha longa quebra com recuo pendurado e o texto não se perde;
  - `--json` nunca é decorado, nem com a decoração forçada;
  - o `cepa-plan status` decorado traz cabeçalho, placar e a memória de cálculo
    do percentual, e mantém os ids de todos os itens.

Sem deps de terceiros — rode com `python3 tests/test_tui.py`.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BIN = RAIZ / "common" / "bin"
sys.path.insert(0, str(RAIZ / "common" / "hooks"))
import _tui  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def roda(args, cor=None, cwd=None, colunas="100"):
    env = {k: v for k, v in os.environ.items() if k not in ("CEPA_COR", "NO_COLOR")}
    env["COLUMNS"] = colunas
    if cor:
        env["CEPA_COR"] = cor
    return subprocess.run([sys.executable, *args], capture_output=True, text=True,
                          env=env, cwd=cwd)


def fila(raiz):
    alvo = raiz / ".claude" / "programs" / "f" / "plan.yaml"
    alvo.parent.mkdir(parents=True)
    itens = []
    for i, st in enumerate(["pending", "done", "blocked", "pending"], 1):
        itens.append(
            f"  - id: item-{i}\n    title: \"{'palavra ' * 40}fim-{i}\"\n"
            f"    why: porque\n    status: {st}\n    blocked_by: []\n"
            f"    human_pending: null\n"
            + ("    evidence: travou no passo dois\n" if st == "blocked" else ""))
    alvo.write_text("program: f\nmode: single-track\nitems:\n" + "".join(itens))
    subprocess.run(["git", "init", "-q", str(raiz)], check=True)
    return raiz


def test_desligada_fora_do_terminal():
    t = _tui.Tela(fluxo=open(os.devnull, "w"))
    assert not t.ligada
    linha = "  18. id-x — " + "texto " * 50
    assert t.linha(linha) == linha
    assert t.secao("pendentes", 3) == "pendentes (3)"
    assert t.cabecalho("fila x") == "fila x"


def test_no_color_vence_e_sempre_liga():
    os.environ["NO_COLOR"] = "1"
    try:
        assert not _tui.Tela().ligada
    finally:
        del os.environ["NO_COLOR"]
    os.environ["CEPA_COR"] = "sempre"
    try:
        assert _tui.Tela(fluxo=open(os.devnull, "w")).ligada
    finally:
        del os.environ["CEPA_COR"]


def test_quebra_com_recuo_pendurado_sem_perder_texto():
    os.environ["CEPA_COR"] = "sempre"
    os.environ["COLUMNS"] = "60"
    try:
        t = _tui.Tela()
        original = "  18. item-x — " + " ".join(f"p{i}" for i in range(60))
        saida = ANSI.sub("", t.linha(original)).split("\n")
    finally:
        del os.environ["CEPA_COR"]
    assert len(saida) > 1
    assert all(len(l) <= 59 for l in saida)
    assert all(l.startswith(" " * 6) and not l.startswith(" " * 7) for l in saida[1:])
    assert " ".join(l.strip() for l in saida) == original.strip()


def test_status_igual_ao_de_antes_fora_do_terminal():
    with tempfile.TemporaryDirectory() as d:
        raiz = fila(Path(d))
        r = roda([str(BIN / "cepa-plan"), "status", "f", "--repo", str(raiz)])
    assert r.returncode == 0, r.stderr
    assert "\x1b" not in r.stdout
    assert "\npendentes (2)\n" in r.stdout
    assert "    1. item-1 — palavra" in r.stdout


def test_status_decorado_no_terminal():
    with tempfile.TemporaryDirectory() as d:
        raiz = fila(Path(d))
        r = roda([str(BIN / "cepa-plan"), "status", "f", "--repo", str(raiz)],
                 cor="sempre")
    assert r.returncode == 0, r.stderr
    plano = ANSI.sub("", r.stdout)
    assert "\x1b[" in r.stdout
    assert "fila f" in plano.splitlines()[0]
    assert "25% fechados (1 concluídos + 0 descartados) ÷ 4" in plano
    for i in range(1, 5):
        assert f"item-{i}" in plano
    assert "↳ motivo: travou no passo dois" in plano
    assert all(len(l) <= 99 for l in plano.splitlines())


def test_json_nunca_decorado():
    with tempfile.TemporaryDirectory() as d:
        raiz = fila(Path(d))
        r = roda([str(BIN / "cepa-plan"), "status", "f", "--repo", str(raiz),
                  "--json"], cor="sempre")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["total"] == 4


def test_filtro_decora_comando_sem_tela_propria():
    r = roda([str(BIN / "cepa-autonomy"), "listar"], cor="sempre")
    assert r.returncode == 0, r.stderr
    assert "\x1b[" in r.stdout
    simples = roda([str(BIN / "cepa-autonomy"), "listar"])
    assert "\x1b" not in simples.stdout
    assert "executa e reporta" in ANSI.sub("", r.stdout)


if __name__ == "__main__":
    falhas = 0
    for nome, f in list(globals().items()):
        if nome.startswith("test_") and callable(f):
            try:
                f()
                print(f"ok   {nome}")
            except AssertionError as e:
                falhas += 1
                print(f"FAIL {nome}: {e}")
    sys.exit(1 if falhas else 0)
