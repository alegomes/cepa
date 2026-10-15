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


@pytest.fixture(autouse=True)
def fora_de_run_autonomo(monkeypatch):
    """A suíte pode rodar dentro de uma janela do cepa-until (`CEPA_UNTIL_RUN`
    posto): os testes que esperam dispensa real precisam do ambiente limpo."""
    monkeypatch.delenv("CEPA_UNTIL_RUN", raising=False)
    monkeypatch.delenv("CLAUDE_AUTONOMOUS_RUN_ID", raising=False)


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


# ── run autônomo: dispensa é proposta, só o dono converte (fb-20261014-3) ────

VARS_DE_RUN = ["CEPA_UNTIL_RUN", "CLAUDE_AUTONOMOUS_RUN_ID"]


def _em_run(monkeypatch, var):
    monkeypatch.setenv(var, "1" if var == "CEPA_UNTIL_RUN" else "run-42")


def _fora_do_run(monkeypatch):
    for v in VARS_DE_RUN:
        monkeypatch.delenv(v, raising=False)


@pytest.mark.parametrize("var", VARS_DE_RUN)
def test_em_run_autonomo_gravar_vira_proposta(tmp_path, monkeypatch, var):
    repo = str(tmp_path)
    _em_run(monkeypatch, var)
    assert waivers.em_run_autonomo()
    path = _grava(repo, fila="fila", item="a1")
    d = yaml.safe_load(open(path))
    assert d["status"] == "proposta"
    assert "autor" in d and d["autor"] is None
    assert "alegomes" in d["proposto_por"]
    assert (d["fila"], d["item"]) == ("fila", "a1")
    assert d["pergunta"].startswith("Aceito a dispensa de PlugSignAdapter")
    assert waivers.carregar(repo) == []
    assert waivers.aplicavel(waivers.carregar(repo), "teste-cego", "PlugSignAdapter", HOJE) is None
    assert [p["_path"] for p in waivers.propostas(repo)] == [path]


def test_run_id_aparece_em_proposto_por(tmp_path, monkeypatch):
    _em_run(monkeypatch, "CLAUDE_AUTONOMOUS_RUN_ID")
    d = yaml.safe_load(open(_grava(str(tmp_path))))
    assert "run-42" in d["proposto_por"]


@pytest.mark.parametrize("var", VARS_DE_RUN)
def test_converter_e_recusar_sao_proibidos_no_run(tmp_path, monkeypatch, var):
    repo = str(tmp_path)
    _em_run(monkeypatch, var)
    _grava(repo)
    with pytest.raises(PermissionError):
        waivers.converter(repo, "teste-cego", "PlugSignAdapter", "alegomes")
    with pytest.raises(PermissionError):
        waivers.recusar(repo, "teste-cego", "PlugSignAdapter", "não")
    assert waivers.carregar(repo) == []


def test_dono_converte_a_proposta_em_dispensa_valida(tmp_path, monkeypatch):
    repo = str(tmp_path)
    _em_run(monkeypatch, "CEPA_UNTIL_RUN")
    _grava(repo, fila="fila", item="a1")
    _fora_do_run(monkeypatch)
    waivers.converter(repo, "teste-cego", "PlugSignAdapter", "alegomes",
                      resposta="sim: aceito", hoje=HOJE)
    w = waivers.aplicavel(waivers.carregar(repo), "teste-cego", "PlugSignAdapter", HOJE)
    assert w is not None
    assert w["autor"] == "alegomes" and "status" not in w
    assert w["criado_em"] == "2026-08-03"
    assert w["resposta_do_dono"] == "sim: aceito"
    assert "alegomes" in w["proposto_por"] and w["proposto_em"] == "2026-08-03"
    assert waivers.propostas(repo) == []


def test_converter_sem_proposta_ou_sobre_dispensa_real(tmp_path):
    repo = str(tmp_path)
    with pytest.raises(FileNotFoundError):
        waivers.converter(repo, "teste-cego", "PlugSignAdapter", "alegomes")
    _grava(repo)  # fora do run: dispensa real
    with pytest.raises(ValueError):
        waivers.converter(repo, "teste-cego", "PlugSignAdapter", "alegomes")
    with pytest.raises(ValueError):
        waivers.converter(repo, "teste-cego", "PlugSignAdapter", "")


def test_recusar_deixa_a_proposta_sem_efeito(tmp_path, monkeypatch):
    repo = str(tmp_path)
    _em_run(monkeypatch, "CEPA_UNTIL_RUN")
    path = _grava(repo)
    _fora_do_run(monkeypatch)
    waivers.recusar(repo, "teste-cego", "PlugSignAdapter", "não: prova de verdade", hoje=HOJE)
    d = yaml.safe_load(open(path))
    assert d["status"] == "recusada" and d["recusada_em"] == "2026-08-03"
    assert d["resposta_do_dono"] == "não: prova de verdade"
    assert waivers.carregar(repo) == [] and waivers.propostas(repo) == []


def test_status_proposta_nunca_dispensa_nem_com_autor_preenchido(tmp_path):
    d = tmp_path / ".claude" / "waivers"
    d.mkdir(parents=True)
    (d / "teste-cego--x.yaml").write_text(
        "status: proposta\nmotivo: teste-cego\nescopo: X\nrazao: r\nautor: alguem\n"
        "criado_em: 2026-08-03\nrevisit_trigger: t\n", encoding="utf-8")
    assert waivers.carregar(str(tmp_path)) == []


@pytest.mark.parametrize("var", VARS_DE_RUN)
def test_propor_nao_sobrescreve_dispensa_valida(tmp_path, monkeypatch, var):
    repo = str(tmp_path)
    path = _grava(repo)  # dispensa real do dono, fora do run
    antes = open(path).read()
    _em_run(monkeypatch, var)
    de_novo = _grava(repo, razao="outra razão qualquer")
    assert de_novo == path
    assert open(path).read() == antes
    assert waivers.aplicavel(waivers.carregar(repo), "teste-cego", "PlugSignAdapter", HOJE)


def test_propor_sobrescreve_proposta_antiga_e_exige_campos(tmp_path):
    repo = str(tmp_path)
    kw = dict(motivo="teste-cego", escopo="X", razao="r1", revisit_trigger="t",
              proposto_por="agente", hoje=HOJE)
    path = waivers.propor(repo, **kw)
    waivers.propor(repo, **dict(kw, razao="r2"))
    assert yaml.safe_load(open(path))["razao"] == "r2"
    for faltando in ("razao", "revisit_trigger", "proposto_por"):
        with pytest.raises(ValueError):
            waivers.propor(repo, **dict(kw, **{faltando: ""}))


def test_propor_nao_reabre_o_que_o_dono_recusou(tmp_path, monkeypatch):
    repo = str(tmp_path)
    _em_run(monkeypatch, "CEPA_UNTIL_RUN")
    path = _grava(repo)
    _fora_do_run(monkeypatch)
    waivers.recusar(repo, "teste-cego", "PlugSignAdapter", "não: prova de verdade", hoje=HOJE)
    _em_run(monkeypatch, "CEPA_UNTIL_RUN")
    assert _grava(repo, razao="outra tentativa") == path
    d = yaml.safe_load(open(path))
    assert d["status"] == "recusada"
    assert d["resposta_do_dono"] == "não: prova de verdade"


def test_yaml_corrompido_e_ignorado_sem_derrubar_as_outras_dispensas(tmp_path):
    repo = str(tmp_path)
    _grava(repo)
    (tmp_path / ".claude" / "waivers" / "quebrado.yaml").write_text(
        "motivo: [unclosed", encoding="utf-8")
    assert [w["motivo"] for w in waivers.carregar(repo)] == ["teste-cego"]
    assert waivers.propostas(repo) == []
