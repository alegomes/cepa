"""Regressão do classificador de motivos de NEEDS-HUMAN.

As fixtures em tests/fixtures/needs-human/ são os 33 artefatos reais que o
piloto de 03/08/2026 encontrou em wego-assinatura-backend e wego-tasy-gateway,
reduzidos aos campos que o classificador lê. A classificação esperada abaixo
foi conferida à mão, artefato por artefato.

Por que esta suíte existe: a primeira versão do classificador errou 7 dos 33
por ler só uma das duas grafias de nome de nível que existem no disco — entre
eles o WEGO-1698, que é o caso de referência da documentação.
"""
import os
import sys

import pytest

yaml = pytest.importorskip("yaml")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "board-flow", "bin"))
from classify_needs_human import (  # noqa: E402
    MOTIVOS,
    NAO_PERGUNTA,
    ORDEM_FILA,
    classify,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "needs-human")

# card -> motivo esperado
ESPERADO = {
    # A prova não chegou a rodar — ninguém decide nada aqui
    "WEGO-1558": "nao-rodou",
    "WEGO-1612": "nao-rodou",
    "WEGO-1663": "nao-rodou",
    "WEGO-1682": "nao-rodou",
    "WEGO-1683": "nao-rodou",   # Docker fora
    "WEGO-1698": "nao-rodou",   # PIT ausente no projeto inteiro
    "WEGO-1732": "nao-rodou",
    "WEGO-1763": "nao-rodou",
    "WEGO-1769": "nao-rodou",
    "WEGO-1770": "nao-rodou",
    "WEGO-1812": "nao-rodou",
    "WEGO-1949": "nao-rodou",
    "WEGO-1958": "nao-rodou",
    "WEGO-1675": "nao-rodou",
    "WEGO-1785": "nao-rodou",   # trava do harness bloqueou a escrita da prova
    # O teste não consegue enxergar essa mudança
    "WEGO-1529": "teste-cego",
    "WEGO-1538": "teste-cego",
    "WEGO-1540": "teste-cego",
    "WEGO-1546": "teste-cego",
    "WEGO-1611": "teste-cego",
    "WEGO-1710": "teste-cego",  # vermelho-no-base só por argumento analítico
    "WEGO-1778": "teste-cego",  # perturbação só coletiva (dois portões juntos)
    "WEGO-1783": "teste-cego",
    "WEGO-1510": "teste-cego",  # a superfície viva do PlugSign não é alcançável no automatizado
    "WEGO-1614": "teste-cego",  # reverter só o pedaço não compila no commit-base
    "WEGO-1619": "teste-cego",  # falta o @QuarkusTest que asserta o 400 na rejeição
    # Não havia o que provar aqui
    # Epic-mãe sem commit-base próprio. Classificado `nao-rodou` até 2026-08-04,
    # quando o primeiro run real do /board-flow:decide mostrou o custo: `nao-rodou`
    # é o único motivo que sai da frente do humano sem perguntar, e sua saída
    # prescrita é re-rodar a prova — que num Epic devolve o mesmo resultado para
    # sempre. O artefato já dizia em prosa "não fabrica um diff sintético agregando
    # as 8 Stories filhas"; faltava a regra olhar issue_type.
    "WEGO-1550": "nada-a-provar",
    "WEGO-1658": "nada-a-provar",   # card só de documentação
    "WEGO-1709": "nada-a-provar",   # ADR puro
    "WEGO-1962": "nada-a-provar",   # fuzzer HTTP não cabe em vazamento de log
    # Os testes rodam, mas seguram pouco
    "WEGO-1564": "guarda-fraca",    # PedidoAssinatura, 60% dos mutantes mortos
    # Apareceu comportamento que nenhum teste confere
    "WEGO-1819": "sem-cobertura",
    # Depende de alguém de fora
    "WEGO-1757": "fora-do-alcance",  # schedule no Bitbucket + quota da Tecnospeed
}


def _carrega(card):
    with open(os.path.join(FIXTURES, f"{card}.yaml")) as fh:
        return yaml.safe_load(fh)


@pytest.mark.parametrize("card,motivo", sorted(ESPERADO.items()))
def test_classifica_artefato_real(card, motivo):
    slug, evidencia = classify(_carrega(card))
    assert slug == motivo, f"{card}: esperado {motivo}, veio {slug} ({evidencia})"
    assert evidencia, f"{card}: motivo sem evidência para mostrar ao usuário"


def test_todas_as_fixtures_estao_cobertas():
    no_disco = {f[:-5] for f in os.listdir(FIXTURES) if f.endswith(".yaml")}
    assert no_disco == set(ESPERADO), (
        "fixture sem classificação esperada (ou vice-versa): "
        f"{no_disco ^ set(ESPERADO)}"
    )


def test_nenhum_artefato_real_cai_em_sem_motivo():
    """A lista é fechada, mas precisa cobrir o que existe de verdade.

    Um `sem-motivo` aqui significa que a lista de sete ficou incompleta — é
    sinal de motivo novo a discutir com o dono, nunca de regra a afrouxar.
    """
    orfaos = [c for c in ESPERADO if classify(_carrega(c))[0] == "sem-motivo"]
    assert not orfaos, f"artefatos sem motivo: {orfaos}"


def test_epic_so_sai_do_nao_rodou_quando_nao_tem_commit_base():
    """A guarda de Epic é estreita de propósito.

    Ela existe para o Epic-mãe que nunca terá diff próprio (WEGO-1550). Um Epic
    COM commit-base resolvido tem diff e continua sujeito a todas as regras
    seguintes — varrer todo Epic para `nada-a-provar` esconderia prova real.
    O WEGO-1732 é esse caso: Epic, base_commit resolvido, e o artefato aponta
    mutantes sobreviventes de verdade.
    """
    mil732 = _carrega("WEGO-1732")
    assert mil732["issue_type"] == "Epic"
    assert mil732["base_commit"], "fixture perdeu o commit-base que faz o caso"
    assert classify(mil732)[0] != "nada-a-provar"

    # e o mesmo Epic, se perdesse o commit-base, cairia na guarda
    sem_base = dict(mil732, base_commit=None, scope={"base_commit_resolved": False})
    assert classify(sem_base)[0] == "nada-a-provar"


def test_so_nao_rodou_deixa_de_virar_pergunta():
    assert NAO_PERGUNTA == {"nao-rodou"}


def test_ordem_da_fila_cobre_todo_motivo_que_vira_pergunta():
    perguntaveis = set(MOTIVOS) - NAO_PERGUNTA - {"sem-motivo"}
    assert set(ORDEM_FILA) == perguntaveis
    assert ORDEM_FILA[0] == "sem-cobertura", "a fila abre pelo de maior risco"


def test_aceita_as_duas_grafias_de_nivel():
    """Grafia antiga e schema 2 têm que dar o mesmo motivo.

    Ler só a documentada foi o erro que classificou 7 dos 33 errado.
    """
    antigo = {
        "card": "X-1", "verdict": "needs-human", "base_commit": "abc1234",
        "routing_reason": "L4 encontrou algo",
        "levels": {"l4_adversarial_input": {"status": "findings",
                                            "findings": ["header aceito sem validação"]}},
    }
    novo = dict(antigo)
    novo["levels"] = {"l4_adversarial_input": dict(antigo["levels"]["l4_adversarial_input"])}
    assert classify(antigo)[0] == classify(novo)[0] == "sem-cobertura"

    perturbado_antigo = {
        "card": "X-2", "verdict": "needs-human", "base_commit": "abc1234",
        "routing_reason": "sem prova externa",
        "levels": {"l3_diff_mutation": {"status": "skipped", "note": "sem detalhe"}},
    }
    perturbado_novo = {
        "card": "X-2", "verdict": "needs-human", "base_commit": "abc1234",
        "routing_reason": "sem prova externa",
        "levels": {"l3_load_bearing": {"perturbation": {"status": "skipped",
                                                        "results": ["sem detalhe"]}}},
    }
    assert classify(perturbado_antigo)[0] == classify(perturbado_novo)[0] == "teste-cego"


def test_caso_desconhecido_nao_inventa_motivo():
    desconhecido = {
        "card": "X-3", "verdict": "needs-human", "base_commit": "abc1234",
        "routing_reason": "algo que nunca vimos antes",
        "levels": {"l2_coverage": {"status": "assumed"}},
    }
    slug, _ = classify(desconhecido)
    assert slug == "sem-motivo"
