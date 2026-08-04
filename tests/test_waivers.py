"""Regressão das dispensas do humano (board-flow/bin/waivers.py).

O que estes testes protegem: que a mesma pergunta não volte (é a razão de o
arquivo existir), e que uma dispensa nunca valha sem autor, razão e gatilho de
revisita — dispensa anônima e sem prazo é exatamente o que o proof gate existe
para impedir, só que gravada em disco.
"""
import os
import sys
from datetime import date

import pytest

yaml = pytest.importorskip("yaml")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "board-flow", "bin"))
import waivers  # noqa: E402

HOJE = date(2026, 8, 3)


def _grava(repo, **kw):
    base = dict(motivo="teste-cego", escopo="PlugSignAdapter",
                razao="aceito a prova interna: o fornecedor não é alcançável no automatizado",
                autor="alegomes", revisit_trigger="quando o adapter mudar")
    base.update(kw)
    return waivers.gravar(repo, hoje=HOJE, **base)


def test_dispensa_gravada_impede_a_mesma_pergunta(tmp_path):
    repo = str(tmp_path)
    _grava(repo)
    carregados = waivers.carregar(repo)
    assert len(carregados) == 1
    assert waivers.aplicavel(carregados, "teste-cego", "PlugSignAdapter", HOJE)


def test_escopo_diferente_ainda_pergunta(tmp_path):
    repo = str(tmp_path)
    _grava(repo)
    carregados = waivers.carregar(repo)
    assert waivers.aplicavel(carregados, "teste-cego", "TasyGatewayAdapter", HOJE) is None


def test_motivo_diferente_no_mesmo_escopo_ainda_pergunta(tmp_path):
    repo = str(tmp_path)
    _grava(repo)
    carregados = waivers.carregar(repo)
    assert waivers.aplicavel(carregados, "guarda-fraca", "PlugSignAdapter", HOJE) is None


def test_escopo_casa_por_slug_e_nao_por_grafia(tmp_path):
    repo = str(tmp_path)
    _grava(repo)
    carregados = waivers.carregar(repo)
    assert waivers.aplicavel(carregados, "teste-cego", "plugsign adapter", HOJE)


def test_gatilho_com_data_vencida_volta_a_perguntar(tmp_path):
    repo = str(tmp_path)
    _grava(repo, revisit_trigger="revisar em 2026-07-01")
    carregados = waivers.carregar(repo)
    assert waivers.aplicavel(carregados, "teste-cego", "PlugSignAdapter", HOJE) is None
    assert waivers.vencido(carregados[0], HOJE)


def test_gatilho_com_data_futura_ainda_dispensa(tmp_path):
    repo = str(tmp_path)
    _grava(repo, revisit_trigger="revisar em 2026-12-31")
    carregados = waivers.carregar(repo)
    assert waivers.aplicavel(carregados, "teste-cego", "PlugSignAdapter", HOJE)


def test_gatilho_em_prosa_nao_e_avaliado_por_codigo(tmp_path):
    """Prosa é mostrada ao humano, nunca interpretada aqui.

    Um código que decidisse sozinho que "quando o adapter mudar" já aconteceu
    estaria dispensando por conta própria — que é o que o gate proíbe.
    """
    repo = str(tmp_path)
    _grava(repo, revisit_trigger="quando o adapter mudar")
    assert not waivers.vencido(waivers.carregar(repo)[0], HOJE)


@pytest.mark.parametrize("faltando", ["razao", "autor", "revisit_trigger"])
def test_nao_grava_dispensa_sem_campo_obrigatorio(tmp_path, faltando):
    with pytest.raises(ValueError):
        _grava(str(tmp_path), **{faltando: ""})


def test_arquivo_malformado_e_ignorado_em_vez_de_dispensar(tmp_path):
    """O lado seguro é ignorar: um waiver sem autor nem prazo que valesse
    dispensaria uma prova sem ninguém conseguir dizer quem dispensou."""
    d = tmp_path / ".claude" / "waivers"
    d.mkdir(parents=True)
    (d / "teste-cego--plugsignadapter.yaml").write_text(
        "motivo: teste-cego\nescopo: PlugSignAdapter\n", encoding="utf-8")
    carregados = waivers.carregar(str(tmp_path))
    assert carregados == []


def test_o_que_foi_gravado_e_legivel_por_humano(tmp_path):
    path = _grava(str(tmp_path))
    d = yaml.safe_load(open(path))
    assert d["autor"] == "alegomes"
    assert d["criado_em"] == "2026-08-03"
    assert "prova interna" in d["razao"]
