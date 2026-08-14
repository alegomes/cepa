#!/usr/bin/env python3
"""Classifica um veredito NEEDS-HUMAN em um dos sete motivos.

Entrada: o dicionário de um `.claude/proof/<KEY>.yaml`.
Saída:   (slug, evidência) — a evidência é a frase que fez a regra casar, para
         o comando mostrar sem o usuário abrir o arquivo.

Os motivos, o que cada um significa e quem decide cada um estão em
docs/needs-human-motivos.md. A lista é FECHADA: um caso que não casa com
nenhuma regra sai como `sem-motivo`, e `/board-flow:decide` para e avisa — ele
nunca inventa um oitavo motivo em tempo de execução, porque motivo inventado é
o que faz um waiver gravado casar depois com o card errado.

A suíte de regressão é tests/test_needs_human_motivos.py, montada sobre 33
artefatos reais de wego-assinatura-backend e wego-tasy-gateway.

Uso como script (leitura, não escreve nada):
    classify_needs_human.py <repo> [<repo> ...]
"""
from __future__ import annotations

import glob
import os
import re
import sys

MOTIVOS = {
    "nao-rodou": "A prova não chegou a rodar",
    "teste-cego": "O teste não consegue enxergar essa mudança",
    "sem-cobertura": "Apareceu comportamento que nenhum teste confere",
    "guarda-fraca": "Os testes rodam, mas seguram pouco",
    "nao-separavel": "Dois cards, uma mudança só",
    "nada-a-provar": "Não havia o que provar aqui",
    "fora-do-alcance": "Depende de alguém de fora",
    "sem-motivo": ">>> não cabe em nenhum motivo",
}

# Só este não vira pergunta para o humano: ninguém decide nada sobre um Docker
# que não subiu. O comando re-roda e, persistindo, abre UM card de infra.
NAO_PERGUNTA = {"nao-rodou"}

# A ordem da fila que o usuário lê: risco decrescente. `nao-rodou` fica fora
# porque não chega a ser pergunta.
ORDEM_FILA = [
    "sem-cobertura",
    "teste-cego",
    "guarda-fraca",
    "nao-separavel",
    "fora-do-alcance",
    "nada-a-provar",
]

# Os artefatos no disco usam duas grafias para os mesmos níveis (ver
# docs/needs-human-motivos.md). Ler só a documentada perde metade da base.
ALIAS = {
    "l2": ("l2_coverage", "l2_external_coverage"),
    "l3": ("l3_load_bearing", "l3_diff_mutation"),
    "l4": ("l4_adversarial_input",),
    "bug": ("bugfix_regression_red_at_base", "bugfix_regression_red_on_base"),
}


def _nivel(levels: dict, chave: str) -> dict:
    for nome in ALIAS[chave]:
        if nome in levels:
            valor = levels[nome]
            return valor if isinstance(valor, dict) else {"status": valor}
    return {}


def _texto(*valores) -> str:
    return " ".join(str(v) for v in valores if v).lower()


# Cada padrão abaixo saiu de um artefato real; o card citado é o exemplo vivo.
FORA_DO_ALCANCE = [
    (r"decis[ãa]o operacional", "decisão operacional fora da sessão"),        # WEGO-1757
    (r"n[ãa]o fa[çc]o merge|n[ãa]o edito o schedule|fora do meu poder", "ação que a sessão não pode executar"),
    (r"n[ãa]o confirmad[ao] com a |aguardando (o |a )?(fornecedor|terceiro)", "pendente de confirmação de terceiro"),
]

# Só o diff é assunto aqui: nenhuma linha de produção mudou.
DIFF_SEM_PRODUCAO = [
    (r"no production (code|line)|nenhuma linha de produ[çc][ãa]o", "diff sem código de produção"),   # WEGO-1709
    (r"pure adr|doc-only|somente documenta|apenas documenta", "diff só de documentação"),            # WEGO-1658
    (r"nothing to perturb|structurally inapplicable|estruturalmente inaplic", "não há o que perturbar"),
]

# A outra metade do motivo 6: tudo foi provado, e UMA checagem não cabe nesse
# tipo de mudança. Só vale com o teste estrutural em `classify` — a frase
# sozinha aparece em prosa de artefato nenhum relacionada ("PIT não se aplica",
# "regression check not applicable" num card que não é bug) e roubaria metade
# da base para o motivo errado.
CHECAGEM_INAPLICAVEL = [
    (r"n[ãa]o se aplica|not applicable|n[ãa]o [ée] aplic[áa]vel|lacuna de expressividade do schema",
     "checagem que não cabe nesse tipo de mudança"),                                                 # WEGO-1962
]

NAO_RODOU = [
    # A polaridade é obrigatória. A versão anterior casava a palavra "docker"
    # solta e, num projeto Quarkus, TODO artefato de prova externa bem-feita cita
    # Testcontainers — inclusive dizendo "Docker OK". Como `nao-rodou` é o único
    # motivo que sai da fila sem passar pelo humano, a regra apagava justamente
    # as provas que rodaram direito. Achado em 14/08/2026 no prove-drain de
    # wego-acesso-backend: WEGO-1894 e WEGO-1897, ambos com Postgres real e
    # achado de segurança, foram classificados "Docker indisponível" por causa da
    # frase "Docker OK". As demais regras deste bloco sempre exigiram o marcador
    # de indisponibilidade ("jacoco ausente", "pit absent"); esta era a exceção.
    (r"(docker|dev services|testcontainers?)[^.\n]{0,60}"
     r"(indispon[íi]vel|unavailable|not (available|running|started|installed)|"
     r"n[ãa]o (subiu|iniciou|est[áa] (dispon[íi]vel|rodando)|dispon[íi]vel)|"
     r"fora do ar|ausente|down)"
     r"|(?:sem|no|without) (docker|dev services|testcontainers?)"
     r"|(?:cannot|could not|unable to|n[ãa]o (?:consegui|foi poss[íi]vel)) "
     r"(?:connect to |start |iniciar |subir |conectar (?:a|ao|no) )?"
     r"(?:the )?(docker|dev services|testcontainers?)",
     "Docker/Dev Services indisponível"),                                                            # WEGO-1683
    (r"jacoco (ausente|absent|n[ãa]o|missing)|no quarkus-jacoco|sem quarkus-jacoco|jacoco not (configured|wired)|no quarkus-jacoco wired",
     "ferramenta de cobertura ausente no projeto"),
    (r"pit is absent|pit ausente|pitest (absent|ausente|not configured)|no pit plugin",
     "PIT ausente no projeto"),                                                                      # WEGO-1698
    (r"path-lock|path_lock|bloqueio do harness|permiss[ãa]o negada pelo hook",
     "trava do próprio harness bloqueou a prova"),                                                   # WEGO-1785
    (r"base_commit (missing|ausente|n[ãa]o)", "commit-base ausente"),
    (r"build (falhou|failed|quebrado)|compilation (error|failure)", "build não subiu"),
]

NAO_SEPARAVEL = [
    (r"n[ãa]o (consegui|foi poss[íi]vel) separar|not separable|aggregate verdict",
     "evidência não atribuível a um card"),
]

# A cegueira NOMEADA vence tudo: quando o artefato diz qual desenho impede a
# prova, é isso que o humano vai decidir — mesmo que o mesmo artefato também
# reclame de ferramenta ausente (WEGO-1540 tem os dois, e o que importa é o
# dublê no-op, não o jacoco que faltou).
TESTE_CEGO_NOMEADO = [
    (r"no-op|noop|mock.*(engole|swallow)", "dublê engole o sinal"),                                      # WEGO-1540
    (r"n[ãa]o alcan[çc]|not reachable", "a superfície real não é alcançável pelo teste"),
    (r"only collective|apenas coletiv|s[óo] coletiv|double-gate|both .{0,30}layers|layered.defense|ambas as camadas",
     "só vai vermelho quando as duas camadas caem juntas"),                                              # WEGO-1778
]

TESTE_CEGO = [
    (r"nenhum @quarkustest|no @quarkustest|sem teste externo|unobservable at (the )?http",
     "nenhum teste externo passa por esse caminho"),
    # base/revert que não compila é obstáculo da FORMA DO CÓDIGO, não do
    # ambiente: a máquina rodou, o vermelho-no-base é que não é produzível.
    (r"n[ãa]o compila|do(es)? not compile", "reverter só esse pedaço não compila no commit-base"),       # WEGO-1614, 1710, 1783
    (r"analytical proof|prova anal[íi]tica|argumento estrutural|structural argument|an[áa]lise est[áa]tica",
     "sobrou argumento analítico no lugar da prova"),                                                    # WEGO-1710
    (r"n[ãa]o (é |e )?por endpoint|prova o mecanismo uma vez|sem http|adapter diretamente",
     "prova só uma vez, não em cada endpoint"),                                                          # WEGO-1783
]


PASSOU = ("pass", "clean", "ran", "n/a", None)


def _travados(levels: dict) -> list[tuple[str, str]]:
    """Níveis que impedem PROVEN — o que sobrou sem evidência, por nome."""
    fora = []
    for chave, rotulo in (("l2", "L2"), ("l3", "L3"), ("l4", "L4"), ("bug", "regressão")):
        nivel = _nivel(levels, chave)
        if not nivel:
            continue
        status = nivel.get("status")
        pert = nivel.get("perturbation")
        if isinstance(pert, dict) and pert.get("status") not in PASSOU:
            fora.append((rotulo, pert.get("status")))
        elif status not in PASSOU:
            fora.append((rotulo, status))
    return fora


def _casa(regras, blob):
    for padrao, evidencia in regras:
        if re.search(padrao, blob):
            return evidencia
    return None


def classify(d: dict) -> tuple[str, str]:
    """Retorna (slug, evidência) para um artefato de prova já lido."""
    levels = d.get("levels") or {}
    l3 = _nivel(levels, "l3")
    l2 = _nivel(levels, "l2")
    l4 = _nivel(levels, "l4")
    bug = _nivel(levels, "bug")
    # no schema 2 a perturbação é um sub-bloco; na grafia antiga o nível é raso
    pert = l3.get("perturbation") or {
        "status": l3.get("status"),
        "results": l3.get("results") or l3.get("note"),
    }
    scope = d.get("scope") or {}

    blob = _texto(
        d.get("routing_reason"),
        pert.get("results"), pert.get("note"),
        l2.get("run"), l2.get("note"),
        l3.get("pit"), l3.get("note"),
        l4.get("reason"), l4.get("note"), l4.get("findings"),
        bug.get("run"), bug.get("note"),
    )

    # ESTRUTURAL, e por isso vem antes de qualquer casador de prosa: se o L4
    # registrou achado, a prova rodou E encontrou defeito na superfície mudada.
    # Isso é decisão do humano por definição, e nenhuma frase pode reroteá-lo.
    #
    # Esta checagem existia, mas lá embaixo, depois dos casadores de texto — e o
    # blob inclui `l4.findings`, isto é, a PROSA DO PRÓPRIO ACHADO. Um achado que
    # descrevesse "jacoco ausente" ou "docker" era classificado pela sua própria
    # descrição e caía em `nao-rodou`, o único balde que dispensa o humano.
    # Achado em 14/08/2026 no prove-drain de wego-acesso-backend: WEGO-1894
    # (colisão de hash) e WEGO-1897 (NUL byte derrubando a API) sumiam da fila,
    # os dois achados mais graves do lote. O fato vence o texto.
    #
    # `findings` guarda prosa, não estado: WEGO-1819 está marcado `findings` e o
    # texto diz que o achado já foi fechado. Por isso a evidência devolvida é o
    # próprio texto — quem lê é o humano; o comando não afirma que está aberto.
    if l4.get("status") == "findings":
        return "sem-cobertura", str(l4.get("findings") or "")[:200]

    # A ordem é precedência, não gosto. "Depende de alguém de fora" e "diff sem
    # produção" vêm primeiro porque também citam ambiente na prosa e seriam
    # engolidos por "não rodou".
    ev = _casa(FORA_DO_ALCANCE, blob)
    if ev:
        return "fora-do-alcance", ev

    ev = _casa(TESTE_CEGO_NOMEADO, blob)
    if ev:
        return "teste-cego", ev

    ev = _casa(DIFF_SEM_PRODUCAO, blob)
    if ev:
        return "nada-a-provar", ev

    sem_base = scope.get("base_commit_resolved") is False or not d.get("base_commit")

    # Um Epic-mãe não tem diff próprio: o trabalho mora nas Stories filhas, cada
    # uma com seu base_commit e seu artefato. Sem esta guarda ele cai na regra de
    # commit-base ausente logo abaixo e sai como `nao-rodou` — o ÚNICO motivo que
    # dispensa o humano sem perguntar, e cuja saída prescrita é re-rodar a prova.
    # Re-rodar num Epic devolve o mesmo resultado para sempre e o card fica em
    # Review em silêncio. Achado no primeiro run real do comando (WEGO-1550,
    # 2026-08-04), cujo artefato já dizia em prosa "um Epic-mãe, por definição,
    # não produz esse diff" — o campo issue_type é o que faltava a regra olhar.
    if sem_base and str(d.get("issue_type") or "").strip().lower() == "epic":
        return "nada-a-provar", "Epic agrega Stories filhas e não tem diff próprio"

    if sem_base:
        return "nao-rodou", "commit-base não resolvido"
    ev = _casa(NAO_RODOU, blob)
    if ev:
        return "nao-rodou", ev

    ev = _casa(NAO_SEPARAVEL, blob)
    if ev:
        return "nao-separavel", ev

    ev = _casa(TESTE_CEGO, blob)
    if ev:
        return "teste-cego", ev
    if pert.get("status") == "skipped":
        return "teste-cego", "perturbação externa não pôde rodar"

    # A segunda metade do motivo 6, e ela é ESTRUTURAL: tudo passou menos uma
    # checagem, e essa checagem não cabe no tipo da mudança. Sem esta condição
    # a frase "não se aplica" (que aparece solta em meio artefato) levava cards
    # de ferramenta ausente para o motivo errado.
    travados = _travados(levels)
    if len(travados) == 1 and _casa(CHECAGEM_INAPLICAVEL, blob):
        return "nada-a-provar", f"{travados[0][0]} não cabe nesse tipo de mudança"

    # (A checagem de `l4.status == "findings"` que ficava aqui subiu para antes
    # dos casadores de prosa — ver o comentário lá em cima. Daqui ela nunca era
    # alcançada quando o texto do próprio achado casava outra regra.)

    for r in ((l3.get("pit") or {}).get("results") or []):
        m = re.search(r"\((\d+)%\)", str(r))
        if m and int(m.group(1)) < 70:
            return "guarda-fraca", str(r)[:200]

    for nome, nivel in (("L2", l2), ("perturbação", pert), ("L4", l4), ("regressão", bug)):
        if nivel.get("status") in ("assumed", "skipped"):
            return "sem-motivo", f"{nome} = {nivel.get('status')}, sem causa reconhecida"
    return "sem-motivo", "needs-human sem nível bloqueado identificável"


def _main(repos):
    import yaml

    buckets: dict[str, list] = {}
    total = 0
    for repo in repos:
        for path in sorted(glob.glob(os.path.join(repo, ".claude/proof/*.yaml"))):
            with open(path) as fh:
                d = yaml.safe_load(fh)
            if not isinstance(d, dict):
                continue
            if str(d.get("verdict", "")).strip().split()[:1] != ["needs-human"]:
                continue
            total += 1
            slug, ev = classify(d)
            card = d.get("card") or os.path.basename(path)
            buckets.setdefault(slug, []).append((card, os.path.basename(repo), ev))

    print(f"NEEDS-HUMAN nos artefatos: {total}\n")
    for slug in ORDEM_FILA + ["nao-rodou", "sem-motivo"]:
        itens = buckets.get(slug) or []
        if not itens:
            continue
        print(f"[{len(itens)}] {MOTIVOS[slug]}  ({slug})")
        for card, repo, ev in itens:
            print(f"    {card:12} {repo:26} {ev}")
        print()
    nao_pergunta = sum(len(buckets.get(s) or []) for s in NAO_PERGUNTA)
    print(f"{total} artefatos − {nao_pergunta} que não são decisão sua = {total - nao_pergunta}")
    print("⚠ isto conta ARTEFATOS, não a fila: a fila são os cards que estão em Review agora.")


if __name__ == "__main__":
    _main(sys.argv[1:])
