#!/usr/bin/env python3
"""Regression tests para a validade declarada nas memórias.

Uma memória de estado ("não instalado ainda", "não rodado em repo real") é
verdadeira no dia em que foi escrita e apodrece calada. O índice MEMORY.md é
carregado em toda sessão, então uma linha vencida entra no contexto com a mesma
cara de uma linha fresca. O campo `validade: AAAA-MM-DD` no frontmatter diz até
quando o fato pode ser repetido sem reconferir; a varredura marca a linha do
índice depois disso.

Contratos guardados aqui:
  - memória com validade no passado → aparece como vencida E a linha dela no
    índice ganha a marca;
  - memória SEM o campo → silêncio. Nunca um alarme inventado a partir de dado
    que não existe (lição permanente não vence);
  - validade no futuro → silêncio;
  - varrer duas vezes não marca duas vezes;
  - validade estendida → a marca sai;
  - data ilegível → ignorada, a varredura não quebra;
  - o diretório de memória sai do caminho do clone principal, do jeito que o
    Claude Code o nomeia;
  - o aviso da sessão nomeia cada memória vencida.

Rode com `python3 tests/test_memoria_validade.py`.
"""

import sys
import tempfile
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "common" / "hooks"))
sys.path.insert(0, str(REPO / "tests"))

from _telemetria_isolada import isola  # noqa: E402

isola()

import _memval as V  # noqa: E402

HOJE = date(2026, 9, 20)
failures = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {detail}")
        failures.append(name)


def mem(d, nome, validade=None):
    extra = f"  validade: {validade}\n" if validade else ""
    (d / f"{nome}.md").write_text(
        f"---\nname: {nome}\ndescription: x\nmetadata:\n  type: project\n{extra}---\n\ncorpo\n",
        encoding="utf-8")


def cenario():
    d = Path(tempfile.mkdtemp(prefix="memval-"))
    mem(d, "velha", "2026-07-10")
    mem(d, "nova", "2026-12-01")
    mem(d, "licao")
    mem(d, "torta", "semana que vem")
    (d / "MEMORY.md").write_text(
        "- [velha](velha.md) — plugin NÃO instalado ainda\n"
        "- [nova](nova.md) — comparar custo em dezembro\n"
        "- [licao](licao.md) — gate se escreve sobre o efeito\n"
        "- [torta](torta.md) — data ilegível\n", encoding="utf-8")
    return d


def linha(d, nome):
    return next(l for l in (d / "MEMORY.md").read_text().splitlines() if f"({nome}.md)" in l)


def test_vencida_e_marcada():
    d = cenario()
    venc = V.sweep(d, HOJE)
    check("só a vencida aparece", [v["file"] for v in venc] == ["velha.md"], venc)
    check("linha do índice ganha a marca", V.MARK_PREFIX in linha(d, "velha"), linha(d, "velha"))
    check("a marca diz desde quando", "2026-07-10" in linha(d, "velha"), linha(d, "velha"))
    check("o texto original da linha fica", "plugin NÃO instalado ainda" in linha(d, "velha"))


def test_sem_campo_e_futuro_ficam_em_silencio():
    d = cenario()
    V.sweep(d, HOJE)
    for nome in ("nova", "licao", "torta"):
        check(f"{nome} sem marca", V.MARK_PREFIX not in linha(d, nome), linha(d, nome))


def test_idempotente():
    d = cenario()
    V.sweep(d, HOJE)
    antes = (d / "MEMORY.md").read_text()
    V.sweep(d, HOJE)
    check("segunda varredura não muda nada", (d / "MEMORY.md").read_text() == antes)
    check("uma marca só", linha(d, "velha").count(V.MARK_PREFIX) == 1, linha(d, "velha"))


def test_validade_estendida_tira_a_marca():
    d = cenario()
    V.sweep(d, HOJE)
    mem(d, "velha", "2027-01-01")
    venc = V.sweep(d, HOJE)
    check("não conta mais como vencida", venc == [], venc)
    check("marca removida", V.MARK_PREFIX not in linha(d, "velha"), linha(d, "velha"))
    check("linha volta ao texto original",
          linha(d, "velha") == "- [velha](velha.md) — plugin NÃO instalado ainda", linha(d, "velha"))


def test_vence_no_dia_seguinte():
    d = cenario()
    mem(d, "velha", "2026-09-20")
    check("no próprio dia ainda vale", V.sweep(d, HOJE) == [])
    check("no dia seguinte venceu", len(V.sweep(d, date(2026, 9, 21))) == 1)


def test_diretorio_sai_do_clone_principal():
    got = V.memory_dir("/Users/a/Insync/a@gmail.com/GoogleDrive/2026/coding/cepa", home="/H")
    want = Path("/H/.claude/projects/-Users-a-Insync-a-gmail-com-GoogleDrive-2026-coding-cepa/memory")
    check("slug igual ao do Claude Code", got == want, got)


def test_aviso_nomeia_as_vencidas():
    d = cenario()
    txt = V.notice(V.sweep(d, HOJE)) or ""
    check("aviso cita a memória", "velha" in txt and "2026-07-10" in txt, txt)
    check("sem vencidas, sem aviso", V.notice([]) is None)


def test_diretorio_ausente_nao_quebra():
    check("varredura em pasta inexistente devolve vazio",
          V.sweep(Path("/nao/existe/mesmo"), HOJE) == [])


def test_session_start_entrega_o_aviso():
    """A fiação: o SessionStart de verdade, como subprocesso, num repo git
    descartável cujo diretório de memória (em HOME falso) tem uma vencida."""
    import json
    import os
    import subprocess
    home = Path(tempfile.mkdtemp(prefix="memval-home-"))
    repo = Path(tempfile.mkdtemp(prefix="memval-repo-")).resolve()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-q", "--allow-empty", "--no-gpg-sign", "-m", "x"], check=True)
    mdir = V.memory_dir(str(repo), home=str(home))
    mdir.mkdir(parents=True)
    mem(mdir, "velha", "2020-01-01")
    (mdir / "MEMORY.md").write_text("- [velha](velha.md) — estado antigo\n", encoding="utf-8")
    env = {**os.environ, "HOME": str(home)}
    r = subprocess.run(
        [sys.executable, str(REPO / "common" / "hooks" / "session-registry.py")],
        input=json.dumps({"hook_event_name": "SessionStart", "session_id": "s-teste",
                          "cwd": str(repo)}),
        capture_output=True, text=True, env=env, timeout=60)
    check("hook sai 0", r.returncode == 0, r.stderr[-300:])
    check("aviso de memória vencida chega na saída", "velha" in r.stdout and "vencida" in r.stdout,
          r.stdout[-400:] + r.stderr[-300:])
    check("índice foi marcado", V.MARK_PREFIX in (mdir / "MEMORY.md").read_text())


if __name__ == "__main__":
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            print(f"\n{nome}")
            fn()
    print()
    if failures:
        print(f"{len(failures)} FALHA(S): {failures}")
        sys.exit(1)
    print("tudo ok")
