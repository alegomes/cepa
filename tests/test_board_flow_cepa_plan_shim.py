"""Regressão do atalho `board-flow/bin/cepa-plan`.

## Por que este arquivo existe

`common/bin/cepa-plan` é um caminho RELATIVO que só existe por acidente de
layout dentro do próprio repo `cepa`. `/board-flow:capture`, `/drain` e
`/triage` chamavam esse caminho direto — funcionava rodando de dentro do
`cepa`, mas em qualquer projeto hospedeiro (WEGO, por exemplo) o arquivo não
existe, o comando falha calado e o card nasce fora da fila sem nenhum aviso.
Este shim existe para resolver o `cepa-plan` real do `common` (no repo ou no
cache de plugins) e repassar tudo — argv e código de saída — sem que quem
chama perceba a diferença.

Os testes aqui usam layouts FALSOS em `tmp_path` com um `cepa-plan` fake (que
só imprime o argv recebido e sai com um código escolhido), para provar a
resolução de caminho sem depender do `cepa-plan` de verdade — mais um teste de
integração real no fim, que roda o shim de verdade contra o `common` de
verdade.
"""
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from _telemetria_isolada import isola

isola()

REPO = Path(__file__).resolve().parent.parent
SHIM_REAL = REPO / "board-flow" / "bin" / "cepa-plan"

FAKE_CEPA_PLAN = """#!/usr/bin/env python3
import sys
print("ARGV:" + repr(sys.argv[1:]))
sys.exit({exit_code})
"""


def _instala_shim(destino):
    """Copia o shim de verdade para `destino` (um `.../bin/cepa-plan`), executável."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(SHIM_REAL, destino)
    destino.chmod(destino.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _instala_fake_cepa_plan(destino, exit_code):
    """Escreve um `cepa-plan` fake em `destino` que só ecoa o argv e sai com `exit_code`."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(FAKE_CEPA_PLAN.format(exit_code=exit_code), encoding="utf-8")
    destino.chmod(destino.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run(shim, args, cwd, env=None):
    return subprocess.run(
        [sys.executable, str(shim), *args],
        cwd=str(cwd), capture_output=True, text=True, env=env,
    )


def test_layout_de_repo_resolve_e_repassa_argv_e_exit(tmp_path):
    repo = tmp_path / "repo"
    shim = repo / "board-flow" / "bin" / "cepa-plan"
    _instala_shim(shim)
    _instala_fake_cepa_plan(repo / "common" / "bin" / "cepa-plan", exit_code=42)

    outro_cwd = tmp_path / "em-qualquer-lugar"
    outro_cwd.mkdir()

    r = _run(shim, ["add", "WEGO", "WEGO-1", "--title", "x"], cwd=outro_cwd)

    assert r.returncode == 42, r.stderr
    assert "ARGV:['add', 'WEGO', 'WEGO-1', '--title', 'x']" in r.stdout


def test_layout_de_cache_pega_a_versao_mais_alta_do_common(tmp_path):
    mkt = tmp_path / "cache" / "cepa"
    shim = mkt / "board-flow" / "0.25.1" / "bin" / "cepa-plan"
    _instala_shim(shim)
    # 2.9.0 sairia "na frente" de 2.10.0 numa comparação lexical de string —
    # é exatamente o erro que a comparação numérica de tupla evita.
    _instala_fake_cepa_plan(mkt / "common" / "2.9.0" / "bin" / "cepa-plan", exit_code=9)
    _instala_fake_cepa_plan(mkt / "common" / "2.10.0" / "bin" / "cepa-plan", exit_code=10)

    r = _run(shim, ["ordena", "WEGO"], cwd=tmp_path)

    assert r.returncode == 10, r.stderr
    assert "ARGV:['ordena', 'WEGO']" in r.stdout


def test_fallback_pro_path_quando_nenhum_layout_existe(tmp_path):
    # Shim isolado, sem `common/` nem um irmão em posição de repo ou cache
    # (mesma profundidade de `<repo>/board-flow/bin/`, só que sem `common/`).
    shim = tmp_path / "solto" / "board-flow" / "bin" / "cepa-plan"
    _instala_shim(shim)

    bin_no_path = tmp_path / "fake-path-bin"
    _instala_fake_cepa_plan(bin_no_path / "cepa-plan", exit_code=7)

    env = dict(os.environ, PATH=f"{bin_no_path}:{os.environ.get('PATH', '')}")
    r = _run(shim, ["divergencia", "WEGO"], cwd=tmp_path, env=env)

    assert r.returncode == 7, r.stderr
    assert "ARGV:['divergencia', 'WEGO']" in r.stdout


def test_nenhum_candidato_sai_127_e_nomeia_os_caminhos_tentados(tmp_path):
    shim = tmp_path / "solto" / "board-flow" / "bin" / "cepa-plan"
    _instala_shim(shim)

    # PATH sem nenhum cepa-plan de verdade (nem o próprio shim, que não se
    # chama "cepa-plan" no PATH aqui — só existe soltinho em tmp_path).
    env = dict(os.environ, PATH="/usr/bin:/bin")
    r = _run(shim, ["add", "WEGO", "WEGO-1", "--title", "x"], cwd=tmp_path, env=env)

    assert r.returncode == 127
    assert "não encontrado" in r.stderr
    # shim = .../solto/board-flow/bin/cepa-plan; a raiz do "repo" é `solto/`.
    assert str(shim.parent.parent.parent / "common" / "bin" / "cepa-plan") in r.stderr
    assert "instale o plugin" in r.stderr.lower()


def test_cwd_sem_common_ainda_resolve_pelo_layout_de_repo(tmp_path):
    """O bug de verdade: um host como WEGO não tem `common/` na raiz. A
    resolução tem que depender de onde o SHIM está, não do cwd de quem chama."""
    repo = tmp_path / "wego-like-repo"
    shim = repo / "board-flow" / "bin" / "cepa-plan"
    _instala_shim(shim)
    _instala_fake_cepa_plan(repo / "common" / "bin" / "cepa-plan", exit_code=0)

    cwd_do_host = tmp_path / "wego-like-repo"  # sem common/ na raiz do projeto do usuário
    assert not (tmp_path / "outro-projeto-sem-common").exists()
    cwd_sem_common = tmp_path / "outro-projeto-sem-common"
    cwd_sem_common.mkdir()

    r = _run(shim, ["add", "WEGO", "WEGO-1", "--title", "x"], cwd=cwd_sem_common)

    assert r.returncode == 0, r.stderr
    assert "ARGV:['add', 'WEGO', 'WEGO-1', '--title', 'x']" in r.stdout


def test_nenhum_arquivo_do_board_flow_chama_o_caminho_relativo():
    """Contrato: nada em `board-flow/{commands,skills,agents}` invoca
    `python3 common/bin/cepa-plan` — o caminho que só existe dentro do repo
    `cepa`. capture/drain/triage têm que chamar o shim via `${CLAUDE_PLUGIN_ROOT}`."""
    alvo = "python3 common/bin/cepa-plan"
    ofensores = []
    for sub in ("commands", "skills", "agents"):
        d = REPO / "board-flow" / sub
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.is_file() and alvo in f.read_text(encoding="utf-8", errors="ignore"):
                ofensores.append(str(f))
    assert ofensores == [], f"ainda chamam o caminho relativo: {ofensores}"

    for nome in ("capture.md", "drain.md", "triage.md"):
        f = REPO / "board-flow" / "commands" / nome
        conteudo = f.read_text(encoding="utf-8")
        assert '${CLAUDE_PLUGIN_ROOT}/bin/cepa-plan' in conteudo, (
            f"{nome} não chama o shim via CLAUDE_PLUGIN_ROOT")


def test_integracao_real_chega_no_cepa_plan_de_verdade(tmp_path):
    """Sem fakes: roda o `board-flow/bin/cepa-plan` de dentro do próprio repo
    `cepa` (layout de repo de verdade) e confere que chegou no `cepa-plan`
    real do `common` — não um shim que só finge sucesso."""
    r = _run(SHIM_REAL, ["--help"], cwd=tmp_path)

    assert r.returncode == 0, r.stderr
    assert "cepa-plan" in r.stdout
    assert "single-track" in r.stdout or "single-track" in r.stdout.lower()
