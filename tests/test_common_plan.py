#!/usr/bin/env python3
"""Testes das etapas 1 e 2 de "um escritor, três fontes": /common:plan + cepa-plan.

Rode com `python3 tests/test_common_plan.py` (só precisa do PyYAML que o próprio
script usa). Duas famílias, de propósito:

  - COMPORTAMENTO do `common/bin/cepa-plan`, que é quem grava. Cada recusa aqui
    existe porque a falha correspondente destrói o documento em silêncio: fila
    gravada por cima de um plano de ondas, `human_pending` zerado numa
    repriorização, ciclo de bloqueio que faz o /common:next dizer que a fila
    acabou quando ela travou.
  - CONTRATO DE PROSA do `common/commands/plan.md`. O comando é um prompt, então
    a única guarda possível é mecânica: a frase "não invente o `why`" é
    exatamente o tipo de instrução que some numa reescrita bem-intencionada.

O que estes testes NÃO provam: que o comando conduz bem o interrogatório. Isso
só um run real diz.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
CEPA_PLAN = REPO / "common" / "bin" / "cepa-plan"
CMD = REPO / "common" / "commands" / "plan.md"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(repo, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(repo))


def repo_git(base, nome):
    d = Path(base) / nome
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def escreve_itens(d, itens):
    p = d / "itens.json"
    p.write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
    return p


def plano_de(d, nome="fila"):
    return yaml.safe_load(
        (d / ".claude" / "programs" / nome / "plan.yaml").read_text(encoding="utf-8"))


ITENS_OK = [
    {"id": "A", "title": "primeiro", "why": "destrava o B", "human_pending": None},
    {"id": "B", "title": "segundo", "why": "depende do A", "blocked_by": ["A"],
     "human_pending": "rodar bin/install.sh --clean e reiniciar"},
]


# ── comportamento ────────────────────────────────────────────────────────────

def test_grava_fila_valida(base):
    d = repo_git(base, "grava")
    r = run(d, "write", "fila", "--items", str(escreve_itens(d, ITENS_OK)),
            "--source", "BACKLOG.md", "--quando", "2026-08-24", "--repo", ".")
    check("grava uma fila válida", r.returncode == 0, r.stderr)
    plan = plano_de(d)
    check("declara schema 2 e single-track",
          plan["schema_version"] == 2 and plan["mode"] == "single-track")
    check("a ORDEM da lista é o dado, preservada como veio",
          [i["id"] for i in plan["items"]] == ["A", "B"])
    check("guarda o `why` de cada posição",
          [i["why"] for i in plan["items"]] == ["destrava o B", "depende do A"])
    check("guarda a fonte das demandas", plan["source"] == "BACKLOG.md")
    check("o arquivo gravado passa na própria validação",
          run(d, "validate",
              str(d / ".claude" / "programs" / "fila" / "plan.yaml")).returncode == 0)


def test_recusa_sem_why(base):
    """`why` vazio é a lacuna que mata o documento: a fila guarda a ordem e
    perde o critério, que é a única coisa que o tracker já não guardava."""
    d = repo_git(base, "sem-why")
    itens = [{"id": "A", "title": "x", "why": "  ", "human_pending": None}]
    r = run(d, "write", "fila", "--items", str(escreve_itens(d, itens)), "--repo", ".")
    check("recusa item sem `why`", r.returncode == 2, r.stdout)
    check("a recusa NOMEIA o campo", "`why`" in r.stderr, r.stderr)
    check("nada foi gravado na recusa",
          not (d / ".claude" / "programs" / "fila").exists())


def test_recusa_human_pending_ausente(base):
    """Nulo explícito é resposta; a chave ausente é omissão, e a dívida com o
    humano volta a ser invisível — que é a razão do campo existir."""
    d = repo_git(base, "sem-hp")
    itens = [{"id": "A", "title": "x", "why": "porque sim"}]
    r = run(d, "write", "fila", "--items", str(escreve_itens(d, itens)), "--repo", ".")
    check("recusa item sem a chave `human_pending`", r.returncode == 2)
    check("a recusa explica que null explícito serve",
          "null" in r.stderr.lower() or "nulo" in r.stderr.lower(), r.stderr)


def test_recusa_ciclo_e_fantasma(base):
    d = repo_git(base, "ciclo")
    itens = [
        {"id": "X", "title": "x", "why": "por causa do Y", "blocked_by": ["Y"],
         "human_pending": None},
        {"id": "Y", "title": "y", "why": "por causa do X", "blocked_by": ["X"],
         "human_pending": None},
    ]
    r = run(d, "write", "fila", "--items", str(escreve_itens(d, itens)), "--repo", ".")
    check("recusa ciclo de bloqueio", r.returncode == 2)
    check("a recusa diz por que ciclo é pior que travamento visível",
          "ciclo" in r.stderr and "acabado" in r.stderr, r.stderr)

    itens = [{"id": "X", "title": "x", "why": "w", "blocked_by": ["FANTASMA"],
              "human_pending": None}]
    r = run(d, "write", "fila", "--items", str(escreve_itens(d, itens)), "--repo", ".")
    check("recusa `blocked_by` apontando para item inexistente", r.returncode == 2)
    check("nomeia o id fantasma", "FANTASMA" in r.stderr, r.stderr)


def test_recusa_id_repetido(base):
    d = repo_git(base, "repetido")
    itens = [{"id": "A", "title": "um", "why": "w", "human_pending": None},
             {"id": "A", "title": "outro", "why": "w", "human_pending": None}]
    r = run(d, "write", "fila", "--items", str(escreve_itens(d, itens)), "--repo", ".")
    check("recusa `id` repetido", r.returncode == 2, r.stdout)


def test_colisao_com_ondas(base):
    """O espelho do maestro-programs --check-name, pelo outro lado.

    Os dois planejadores gravam no MESMO diretório e o nome é escolha livre de
    quem chama; sem esta recusa, `/common:plan WEGO-paralelo` apaga as ondas —
    superfície, aceite e fork point de cada slice — sem uma palavra.
    """
    d = repo_git(base, "colisao")
    ondas = d / ".claude" / "programs" / "ondas"
    ondas.mkdir(parents=True)
    (ondas / "plan.yaml").write_text(
        "schema_version: 2\nmode: parallel-waves\nprogram: ondas\nwaves: []\n")

    r = run(d, "check-name", "ondas", "--repo", ".")
    check("check-name devolve 3 na colisão com ondas", r.returncode == 3, r.stdout)
    check("a colisão nomeia o dono do arquivo",
          "/maestro:program-plan" in r.stderr, r.stderr)

    r = run(d, "write", "ondas", "--items", str(escreve_itens(d, ITENS_OK)), "--repo", ".")
    check("write também recusa (a checagem não é só do comando)", r.returncode == 3)
    intacto = yaml.safe_load((ondas / "plan.yaml").read_text())
    check("o plano de ondas ficou intacto", intacto["mode"] == "parallel-waves")

    r = run(d, "check-name", "livre", "--repo", ".")
    check("nome livre devolve 0", r.returncode == 0, r.stderr)


def test_reescrita_preserva_execucao(base):
    """Repriorizar não pode apagar dívida que ninguém pagou.

    `status` e `human_pending` vêm da EXECUÇÃO; `title`, `why` e a posição vêm
    do PLANEJAMENTO. Uma reescrita que zerasse o `human_pending` faria a dívida
    sumir do único lugar que a mostrava — e só o humano fecha esse campo.
    """
    d = repo_git(base, "reescrita")
    run(d, "write", "fila", "--items", str(escreve_itens(d, ITENS_OK)), "--repo", ".")
    alvo = d / ".claude" / "programs" / "fila" / "plan.yaml"
    plan = yaml.safe_load(alvo.read_text())
    plan["items"][0]["status"] = "done"
    alvo.write_text(yaml.dump(plan, allow_unicode=True, sort_keys=False))

    # mesma fila, ordem invertida e `why` novo — o planejamento mudou de ideia
    novos = [
        {"id": "B", "title": "segundo", "why": "subiu: o A esbarrou em decisão",
         "human_pending": None},
        {"id": "A", "title": "primeiro", "why": "desceu", "human_pending": None},
    ]
    r = run(d, "write", "fila", "--items", str(escreve_itens(d, novos)), "--repo", ".")
    check("reescreve uma fila existente", r.returncode == 0, r.stderr)
    plan = plano_de(d)
    por_id = {i["id"]: i for i in plan["items"]}
    check("a nova ORDEM manda", [i["id"] for i in plan["items"]] == ["B", "A"])
    check("o novo `why` manda", por_id["B"]["why"].startswith("subiu"))
    check("o `status` da execução sobrevive", por_id["A"]["status"] == "done")
    check("e a lista nova NÃO consegue reivindicar progresso que o disco não tem",
          run(d, "write", "fila", "--repo", ".", "--items", str(escreve_itens(d, [
              {"id": "B", "title": "segundo", "why": "w", "status": "done",
               "human_pending": None},
              {"id": "A", "title": "primeiro", "why": "w", "human_pending": None},
          ]))).returncode == 0
          and {i["id"]: i["status"] for i in plano_de(d)["items"]}["B"] == "pending",
          "quem replaneja decide ordem, não progresso")
    check("o `human_pending` aberto sobrevive a uma repriorização",
          por_id["B"]["human_pending"] == ITENS_OK[1]["human_pending"],
          "zerá-lo apagaria dívida que só o humano fecha")
    check("guardou cópia do arquivo anterior",
          (d / ".claude" / "programs" / "fila" / "plan.yaml.bak").is_file(),
          "os comentários escritos à mão não sobrevivem à reescrita")


def test_planejamento_pode_aposentar_item(base):
    """`dropped` é a única palavra que o planejamento tem sobre o status.

    Achado no 1º uso real (2026-08-25): a regra "o status do disco sempre
    ganha" impedia aposentar um item que a própria entrega tornou obsoleto —
    ele voltava `pending` a cada repriorização, e a fila só crescia.
    """
    d = repo_git(base, "aposenta")
    run(d, "write", "fila", "--items", str(escreve_itens(d, ITENS_OK)), "--repo", ".")
    novos = [
        {"id": "A", "title": "primeiro", "why": "destrava o B", "human_pending": None},
        {"id": "B", "title": "segundo", "why": "obsoleto: o A entregou junto",
         "status": "dropped", "human_pending": None},
    ]
    r = run(d, "write", "fila", "--items", str(escreve_itens(d, novos)), "--repo", ".")
    check("a repriorização consegue aposentar um item", r.returncode == 0, r.stderr)
    por_id = {i["id"]: i for i in plano_de(d)["items"]}
    check("o item aposentado fica no documento com o porquê",
          por_id["B"]["status"] == "dropped" and "obsoleto" in por_id["B"]["why"],
          "sumir com ele apagaria a razão de ele ter saído")


def test_chave_extra_sobrevive(base):
    """Campo que o schema não prevê não some na repriorização.

    Achado ao usar o comando pela primeira vez de verdade: a evidência de um
    item `done` mora hoje em comentário, e comentário não sobrevive à
    reescrita. Um campo sobrevive — desde que o escritor não o descarte em
    silêncio, que é o que ele fazia.
    """
    d = repo_git(base, "extra")
    itens = [{"id": "A", "title": "x", "why": "w", "human_pending": None,
              "evidence": "suíte 49/49 verde em 2026-08-24"}]
    run(d, "write", "fila", "--items", str(escreve_itens(d, itens)), "--repo", ".")
    check("a chave extra chega ao arquivo",
          plano_de(d)["items"][0].get("evidence", "").startswith("suíte"))

    # repriorização que NÃO menciona a chave: ela vem do disco
    magros = [{"id": "A", "title": "x", "why": "outro motivo", "human_pending": None}]
    run(d, "write", "fila", "--items", str(escreve_itens(d, magros)), "--repo", ".")
    item = plano_de(d)["items"][0]
    check("e sobrevive a uma reescrita que não a menciona",
          item.get("evidence", "").startswith("suíte"), str(item))
    check("sem impedir que o `why` novo entre", item["why"] == "outro motivo")


def test_item_sumido_nao_some_calado(base):
    d = repo_git(base, "sumido")
    run(d, "write", "fila", "--items", str(escreve_itens(d, ITENS_OK)), "--repo", ".")
    menos = [{"id": "A", "title": "primeiro", "why": "agora sozinho",
              "human_pending": None}]
    p = escreve_itens(d, menos)
    r = run(d, "write", "fila", "--items", str(p), "--repo", ".")
    check("recusa por default quando um item do disco não é mencionado",
          r.returncode == 4, r.stdout)
    check("nomeia o item que sumiria", " B" in r.stderr or "B," in r.stderr or
          r.stderr.strip().find("B") != -1, r.stderr)
    check("ainda tem 2 itens no disco", len(plano_de(d)["items"]) == 2)

    r = run(d, "write", "fila", "--items", str(p), "--repo", ".", "--on-missing", "drop")
    check("com --on-missing drop, grava marcando dropped", r.returncode == 0, r.stderr)
    por_id = {i["id"]: i for i in plano_de(d)["items"]}
    check("o item some da fila viva mas continua no documento",
          por_id["B"]["status"] == "dropped")


def test_raiz_e_a_do_clone_principal(base):
    """Chamado de dentro de uma worktree ligada, grava no CLONE PRINCIPAL.

    É a camada 0 no lado da escrita: num repo cujo .gitignore cobre `.claude/`,
    um plano escrito dentro da worktree é invisível ao git e morre com ela — a
    perda verificada em 2026-08-18, que custou uma triagem inteira.
    """
    d = repo_git(base, "principal")
    (d / "seed.txt").write_text("x")
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "seed"], check=True)
    wt = Path(base) / "wt"
    subprocess.run(["git", "-C", str(d), "worktree", "add", "-q", str(wt), "-b", "lado"],
                   check=True, capture_output=True)

    r = run(wt, "write", "fila", "--items", str(escreve_itens(wt, ITENS_OK)), "--repo", ".")
    check("grava a partir da worktree", r.returncode == 0, r.stderr)
    check("o arquivo nasceu no clone principal",
          (d / ".claude" / "programs" / "fila" / "plan.yaml").is_file())
    check("e NÃO dentro da worktree",
          not (wt / ".claude" / "programs" / "fila" / "plan.yaml").exists(),
          "plano dentro da worktree morre com ela, sem aviso")


def test_dry_run_nao_grava(base):
    d = repo_git(base, "dry")
    r = run(d, "write", "fila", "--items", str(escreve_itens(d, ITENS_OK)),
            "--repo", ".", "--dry-run")
    check("--dry-run sai 0 e imprime o arquivo",
          r.returncode == 0 and "mode: single-track" in r.stdout)
    check("--dry-run não grava nada",
          not (d / ".claude" / "programs" / "fila").exists())


def test_validate_recusa_plano_de_ondas(base):
    d = repo_git(base, "validate-ondas")
    p = d / "ondas.yaml"
    p.write_text("schema_version: 2\nmode: parallel-waves\nprogram: o\nwaves: []\n")
    r = run(d, "validate", str(p))
    check("validate recusa um documento de ondas", r.returncode == 2)
    check("e diz de quem é esse documento",
          "/maestro:program-plan" in r.stderr, r.stderr)
    # continuar listando lacunas de fila num documento que não é fila manda
    # consertar a coisa errada: o dono leria "a fila não tem itens" sobre um
    # plano de ondas perfeitamente válido e iria mexer nele.
    check("para na primeira lacuna e não reclama de campo de fila",
          "1 lacuna" in r.stderr and "nenhum item" not in r.stderr, r.stderr)

    v1 = d / "v1.yaml"
    v1.write_text("program: legado\nwaves: []\n")
    r = run(d, "validate", str(v1))
    check("um plano v1 (sem `mode`) também é lido como ondas, não como fila vazia",
          r.returncode == 2 and "nenhum item" not in r.stderr, r.stderr)


SPEC_FIXTURE = """\
# Especificação: exportar relatório

**Status:** pronta-para-construir
**Aberta em:** 2026-08-24            **Fechada em:** 2026-08-24

## Problema
Ninguém consegue exportar.

## Critérios de sucesso

### CS-1: o endpoint devolve o arquivo
**Superfície:** http
**Teste vermelho:** hoje `GET /relatorios/1/export` devolve 404 porque a rota
não existe; passará quando devolver 200 com o CSV no corpo.

### CS-2: a exportação registra quem pediu
**Superfície:** domain
**Teste vermelho:** hoje nada grava o solicitante.

## Perguntas em aberto

## Decidido sem perguntar
- nada
"""

SPEC_RASCUNHO = SPEC_FIXTURE.replace("**Status:** pronta-para-construir",
                                     "**Status:** rascunho").replace(
    "## Perguntas em aberto\n", "## Perguntas em aberto\n- [ ] qual formato?\n")


def test_from_spec_le_os_criterios(base):
    """A conversão spec -> itens é CÓDIGO, não promessa de prompt.

    O auditor de completude pegou isto em 2026-08-24: enquanto `--from-spec`
    existia só como parágrafo de instrução no plan.md, o único teste possível
    era grepar a prosa — ou seja, provar que o comando PROMETE herdar a ordem,
    nunca que uma execução produz a fila prometida.
    """
    d = repo_git(base, "spec")
    sp = d / "spec.md"
    sp.write_text(SPEC_FIXTURE, encoding="utf-8")

    r = run(d, "from-spec", str(sp))
    check("lê a spec e devolve itens", r.returncode == 0, r.stderr)
    itens = json.loads(r.stdout)
    check("um item por critério de sucesso", len(itens) == 2, str(itens))
    check("a ORDEM é a do texto", [i["id"] for i in itens] == ["CS-1", "CS-2"])
    check("o título é o do critério",
          itens[0]["title"] == "o endpoint devolve o arquivo", itens[0]["title"])
    check("o `why` DIZ que a ordem foi herdada",
          all("ninguém priorizou os critérios entre si" in i["why"] for i in itens),
          "sem isso a fila apresenta como decisão uma ordem que ninguém tomou")
    check("o `why` carrega a superfície declarada na spec",
          "http" in itens[0]["why"] and "domain" in itens[1]["why"])
    check("o `why` carrega o teste vermelho INTEIRO, não a primeira linha",
          "passará quando devolver 200 com o CSV no corpo" in itens[0]["why"],
          "campo cortado no meio da oração parece texto completo")
    check("nasce sem rota humana a cobrar",
          all(i["human_pending"] is None for i in itens))

    r = run(d, "write", "daspec", "--from-spec", str(sp), "--repo", ".")
    check("write --from-spec grava a fila", r.returncode == 0, r.stderr)
    plan = plano_de(d, "daspec")
    check("a fila gravada tem um item por critério, na ordem do texto",
          [i["id"] for i in plan["items"]] == ["CS-1", "CS-2"])
    check("a fonte registrada aponta o arquivo da spec",
          "spec.md" in plan["source"], plan["source"])


def test_from_spec_le_depois_do_cs_como_blocked_by(base):
    """A spec do WEGO dizia "Depois do CS-1" no CS-2 e a fila nasceu com
    `blocked_by` vazio: a regra dependia do agente acrescentar à mão."""
    d = repo_git(base, "spec-dep")
    sp = d / "spec.md"
    sp.write_text(SPEC_FIXTURE
                  .replace("### CS-2:", "### CS-2:", 1)
                  + "\n### CS-3: o terceiro\n\nDepois do CS-1 e CS-2, a "
                  "listagem traz o total.\n\n**Superfície:** http\n\n"
                  "**Teste vermelho:** falha hoje.\n"
                  "\n### CS-4: o quarto\n\nApós o CS-9, nada.\n\n"
                  "**Superfície:** http\n\n**Teste vermelho:** falha hoje.\n",
                  encoding="utf-8")
    r = run(d, "from-spec", str(sp))
    check("lê a spec com dependência declarada", r.returncode == 0, r.stderr)
    itens = {i["id"]: i for i in json.loads(r.stdout)}
    check("\"Depois do CS-1 e CS-2\" vira blocked_by [CS-1, CS-2]",
          itens.get("CS-3", {}).get("blocked_by") == ["CS-1", "CS-2"],
          str(itens.get("CS-3")))
    check("critério sem a frase nasce sem dependência",
          itens["CS-1"]["blocked_by"] == [] and itens["CS-2"]["blocked_by"] == [])
    check("dependência de critério que não existe fica fora e é avisada",
          itens["CS-4"]["blocked_by"] == [] and "CS-9" in r.stderr, r.stderr)


def test_from_spec_avisa_rascunho_e_recusa_vazia(base):
    d = repo_git(base, "spec-ruim")
    sp = d / "rascunho.md"
    sp.write_text(SPEC_RASCUNHO, encoding="utf-8")
    r = run(d, "from-spec", str(sp))
    check("aceita a spec em rascunho mas AVISA", r.returncode == 0, r.stderr)
    check("o aviso nomeia o status e a pergunta em aberto",
          "rascunho" in r.stderr and "aberto" in r.stderr, r.stderr)

    vazia = d / "vazia.md"
    vazia.write_text("# Especificação: nada\n\n**Status:** rascunho\n", encoding="utf-8")
    r = run(d, "from-spec", str(vazia))
    check("recusa uma spec sem nenhum critério de sucesso", r.returncode == 2)
    check("e diz o que faltou", "CS-" in r.stderr, r.stderr)


# ── contrato de prosa do comando ─────────────────────────────────────────────

def flat(txt):
    return " ".join(txt.split())


def test_contrato_do_comando(_base):
    txt = CMD.read_text(encoding="utf-8")
    f = flat(txt)
    fm = txt.split("---")[1] if txt.startswith("---") else ""

    check("o comando existe", CMD.is_file())
    check("declara `interaction: conversational`",
          "interaction: conversational" in fm,
          "em `routine` o hook default-yes-inject injeta a política que manda "
          "decidir sozinho — e a ordem e o `why` são do dono, não do agente")
    check("manda a gravação passar pelo cepa-plan",
          "common/bin/cepa-plan" in f or "bin/cepa-plan" in f)
    check("proíbe escrever o YAML à mão",
          "Nunca escreve o YAML à mão" in f,
          "por fora do script nenhuma das recusas acontece")
    check("proíbe inventar ordem e `why`",
          "Nunca inventa ordem nem `why`" in f)
    check("manda a leitura da spec passar pelo `from-spec` (não pelos seus olhos)",
          "cepa-plan from-spec" in f,
          "leitura no olho não deixa evidência: só provaria que o comando promete")
    check("manda dizer quando a ordem foi HERDADA do texto da spec",
          "herdou" in f and "herdad" in f.lower(),
          "a preferência registrada no desenho: herdar e dizer que herdou")
    check("recusa gravar por cima de um plano de ondas",
          "Nunca grava por cima de um plano de ondas" in f)
    check("não fecha `human_pending` de ninguém",
          "Não fecha `human_pending` de ninguém" in f,
          "lista que se fecha sozinha é decoração")
    # Etapa 2: a flag existe. A guarda que importa deixou de ser "diga que não
    # existe" e passou a ser "não consulte o Jira por conta própria" — o risco é
    # o mesmo dos dois lados, uma fila cuja ordem saiu do rank do quadro.
    check("manda a leitura do repasse passar pelo `from-triage`",
          "cepa-plan from-triage" in f,
          "leitura no olho não deixa evidência: só provaria que o comando promete")
    check("proíbe montar a fila de uma consulta crua ao Jira",
          "Nunca consulta o Jira direto" in f and "/board-flow:triage" in f,
          "a ordem de uma fila vinda de board sai da CLASSIFICAÇÃO, não da "
          "coluna — o rank do quadro é justamente a ordem que este documento "
          "existe para substituir")
    check("diz o que fazer quando falta board-flow ou board-flow.yaml",
          "board-flow.yaml" in f and "não improvise" in f,
          "sem saída nomeada o agente inventa uma consulta ao Jira")
    check("diz que só card `ready` vira item da fila",
          "só card `ready` vira item `pending`" in f,
          "In Review pertence à fila de prova, não à de construção")
    check("aponta o consumidor da fila", "/common:next" in f)
    check("declara que não executa nada", "Não executa" in f)

    # o catálogo é o único lugar onde um comando é encontrável por quem não o
    # escreveu — 8 comandos já sumiram dele sem nenhum teste piscar
    cat = flat((REPO / "docs" / "commands.md").read_text(encoding="utf-8"))
    check("está no catálogo docs/commands.md", "`/common:plan`" in cat)
    plugin = (REPO / "common" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    check("está na descrição do plugin common", "/plan" in plugin)


# ── repasse de uma triagem (etapa 2) ─────────────────────────────────────────

REPASSE_OK = {
    "project_key": "WEGO",
    "source_column": "Backlog",
    "triaged_on": "2026-08-25",
    "remaining_in_column": 12,
    "cards": [
        {"key": "WEGO-1235", "title": "hook estabilizado", "bucket": "ready",
         "why": "destrava 1240 e 1237, que tocam o mesmo hook"},
        {"key": "WEGO-1240", "title": "rota de validação humana", "bucket": "ready",
         "why": "depende do hook do 1235", "blocked_by": ["WEGO-1235"]},
        {"key": "WEGO-1234", "title": "cliente PlugSign", "bucket": "implemented"},
        {"key": "WEGO-1236", "title": "dedup", "bucket": "obsolete",
         "reason": "dedup de WEGO-1240"},
        {"key": "WEGO-1238", "title": "vago", "bucket": "needs-refinement"},
    ],
}


def repasse(d, dados, nome="repasse.json"):
    p = Path(d) / nome
    p.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return p


def test_from_triage_so_ready_vira_item(base):
    """A conversão triagem -> itens é CÓDIGO, pela mesma razão da etapa 1.

    As regras exercitadas aqui viviam na prosa do `board-flow/commands/triage.md`
    — "only → To Do cards become pending items", "Won't Do vira dropped, não
    deleção", "sob --max, diga que a fila é um pedaço". Enquanto morarem só lá, o
    único teste possível é grepar a instrução, que prova que o comando PROMETE
    aplicá-las e nunca que uma execução as aplicou.
    """
    d = repo_git(base, "triagem")
    r = run(d, "from-triage", str(repasse(d, REPASSE_OK)))
    check("lê o repasse e devolve itens", r.returncode == 0, r.stderr)
    itens = json.loads(r.stdout)

    ids = [i["id"] for i in itens]
    check("card `implemented` NÃO vira item da fila", "WEGO-1234" not in ids,
          "In Review pertence à fila de prova; misturar manda construir o "
          "que já está construído")
    check("card `needs-refinement` NÃO vira item da fila", "WEGO-1238" not in ids)
    check("e o aviso NOMEIA quem ficou de fora e para onde vai",
          "WEGO-1234" in r.stderr and "prove-drain" in r.stderr, r.stderr)

    check("a ORDEM é a que a triagem classificou",
          ids == ["WEGO-1235", "WEGO-1240", "WEGO-1236"], str(ids))
    check("card READY vira `pending`",
          [i["status"] for i in itens[:2]] == ["pending", "pending"])
    check("o `why` é o da triagem, não um inventado",
          itens[0]["why"] == "destrava 1240 e 1237, que tocam o mesmo hook")
    check("a dependência entre cards sobrevive",
          itens[1]["blocked_by"] == ["WEGO-1235"])

    obsoleto = itens[2]
    check("card OBSOLETE fica na fila como `dropped`, não some",
          obsoleto["status"] == "dropped",
          "apagar faz a próxima varredura propor a mesma demanda de novo")
    check("e carrega o motivo do descarte",
          "dedup de WEGO-1240" in obsoleto["why"]
          and obsoleto.get("evidence") == "dedup de WEGO-1240")

    check("nasce sem rota humana a cobrar",
          all(i["human_pending"] is None for i in itens))


def test_from_triage_recusa_o_que_a_prosa_so_pedia(base):
    d = repo_git(base, "triagem-ruim")

    sem_why = {"cards": [{"key": "W-1", "title": "t", "bucket": "ready"}]}
    r = run(d, "from-triage", str(repasse(d, sem_why, "a.json")))
    check("recusa card READY sem `why`", r.returncode == 2)
    check("e diz que a ordem sem critério é o que o Jira já guarda",
          "W-1" in r.stderr and "inventar" in r.stderr, r.stderr)

    sem_motivo = {"cards": [{"key": "W-1", "title": "t", "bucket": "ready", "why": "x"},
                            {"key": "W-2", "title": "t", "bucket": "obsolete"}]}
    r = run(d, "from-triage", str(repasse(d, sem_motivo, "b.json")))
    check("recusa card OBSOLETE sem motivo", r.returncode == 2)
    check("e nomeia o card", "W-2" in r.stderr, r.stderr)

    na_grelha = {"cards": [{"key": "W-1", "title": "t", "bucket": "ready", "why": "x"},
                           {"key": "W-2", "title": "t", "bucket": "needs-decision"}]}
    r = run(d, "from-triage", str(repasse(d, na_grelha, "c.json")))
    check("recusa card ainda parado em `needs-decision`", r.returncode == 2,
          "a grelha do passo 6 não terminou, e a fila se leria como decidida")
    check("e manda de volta para a grelha",
          "W-2" in r.stderr and "grelha" in r.stderr, r.stderr)

    balde_novo = {"cards": [{"key": "W-1", "title": "t", "bucket": "talvez", "why": "x"}]}
    r = run(d, "from-triage", str(repasse(d, balde_novo, "d.json")))
    check("recusa balde que a triagem não usa", r.returncode == 2,
          "balde desconhecido ignorado em silêncio some com o card")
    check("e lista os válidos", "ready" in r.stderr and "obsolete" in r.stderr)

    vazio = {"cards": [{"key": "W-1", "title": "t", "bucket": "implemented"}]}
    r = run(d, "from-triage", str(repasse(d, vazio, "e.json")))
    check("recusa uma triagem que não deixou nada a enfileirar",
          r.returncode == 2, r.stderr)


def test_from_triage_dependencia_para_fora_da_fila(base):
    """Depender de um card que foi para In Review não é id fantasma.

    Recusar obrigaria o agente a apagar a informação à mão; deixar faria a
    validação geral recusar a fila inteira por id inexistente. Sai do campo e é
    DITO — sair calado é como uma dependência vira surpresa na execução.
    """
    d = repo_git(base, "dep-fora")
    dados = {"cards": [
        {"key": "W-1", "title": "t", "bucket": "ready", "why": "x",
         "blocked_by": ["W-2"]},
        {"key": "W-2", "title": "t", "bucket": "implemented"},
    ]}
    r = run(d, "from-triage", str(repasse(d, dados)))
    check("não recusa a fila por causa dela", r.returncode == 0, r.stderr)
    check("a dependência sai do `blocked_by`",
          json.loads(r.stdout)[0]["blocked_by"] == [])
    check("e o aviso nomeia os dois cards",
          "W-1" in r.stderr and "W-2" in r.stderr, r.stderr)

    fantasma = {"cards": [{"key": "W-1", "title": "t", "bucket": "ready", "why": "x",
                           "blocked_by": ["W-9"]}]}
    r = run(d, "from-triage", str(repasse(d, fantasma, "f.json")))
    check("mas id que a triagem nunca viu segue sendo recusa",
          r.returncode == 2 and "W-9" in r.stderr, r.stderr)


def test_write_from_triage_grava_e_diz_que_e_parcial(base):
    d = repo_git(base, "grava-triagem")
    rp = repasse(d, REPASSE_OK)
    r = run(d, "write", "WEGO", "--from-triage", str(rp), "--repo", ".",
            "--quando", "2026-08-25")
    check("write --from-triage grava a fila", r.returncode == 0, r.stderr)

    plan = plano_de(d, "WEGO")
    check("a fila gravada tem os itens na ordem da triagem",
          [i["id"] for i in plan["items"]] == ["WEGO-1235", "WEGO-1240", "WEGO-1236"])
    check("a fonte registra projeto, coluna e data",
          all(x in plan["source"] for x in ("WEGO", "Backlog", "2026-08-25")),
          plan["source"])
    check("a fonte DIZ que a fila é um pedaço do quadro",
          "PARCIAL" in plan["source"] and "12" in plan["source"],
          "uma fila de 15 cards de 27 se lê, meses depois, como o quadro inteiro")
    check("o cabeçalho lido a olho também carrega a parcialidade",
          "PARCIAL" in (d / ".claude" / "programs" / "WEGO" / "plan.yaml"
                        ).read_text(encoding="utf-8"))

    # e a re-triagem não pode apagar o que a execução escreveu
    p = d / ".claude" / "programs" / "WEGO" / "plan.yaml"
    plan["items"][0]["status"] = "done"
    plan["items"][0]["human_pending"] = "abrir /admin/devolucoes e conferir"
    p.write_text(yaml.dump(plan, allow_unicode=True, sort_keys=False),
                 encoding="utf-8")
    r = run(d, "write", "WEGO", "--from-triage", str(rp), "--repo", ".")
    check("re-triagem grava de novo", r.returncode == 0, r.stderr)
    de_novo = plano_de(d, "WEGO")["items"][0]
    check("o `done` do disco sobrevive à re-triagem", de_novo["status"] == "done")
    check("e a dívida humana ABERTA sobrevive junto",
          de_novo["human_pending"] == "abrir /admin/devolucoes e conferir",
          "só o humano fecha essa pendência; uma re-triagem que a zerasse "
          "apagaria dívida que ninguém pagou")


def test_contrato_do_triage(_base):
    """O `/board-flow:triage` deixou de ser o segundo escritor da fila.

    Dois escritores da mesma regra divergem, e o que é feito de prosa diverge
    sem nenhum teste ficar vermelho — que é a razão inteira da etapa 2.
    """
    tri = REPO / "board-flow" / "commands" / "triage.md"
    f = flat(tri.read_text(encoding="utf-8"))

    check("o comando existe", tri.is_file())
    check("declara que NÃO escreve mais o plan.yaml",
          "no longer writes `plan.yaml`" in f,
          "enquanto ele escrever também, as regras vivem em dois lugares")
    check("manda a gravação passar pelo cepa-plan --from-triage",
          "cepa-plan write --from-triage" in f or "--from-triage" in f)
    check("nomeia o repasse e onde ele mora",
          "triagem-<YYYY-MM-DD>.json" in f)
    check("entrega a ordem ao /common:plan", "/common:plan" in f)
    check("manda a raiz ser a do clone principal",
          "git rev-parse --git-common-dir" in f,
          "gravar contra a árvore corrente é a perda de 2026-08-18")
    check("diz que `needs-decision` não é balde válido no repasse",
          "`needs-decision` is not a valid bucket" in f,
          "sem isso a grelha inacabada vira fila que se lê como decidida")
    check("manda reportar o `remaining_in_column`",
          "remaining_in_column" in f,
          "é o que impede uma fila truncada de se ler como o quadro inteiro")
    check("proíbe escrever o YAML à mão aqui",
          "do not work around it by writing the YAML by hand" in f
          or "Triage never writes `plan.yaml`" in f)


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_grava_fila_valida, test_recusa_sem_why,
                   test_recusa_human_pending_ausente, test_recusa_ciclo_e_fantasma,
                   test_recusa_id_repetido, test_colisao_com_ondas,
                   test_reescrita_preserva_execucao, test_planejamento_pode_aposentar_item,
                   test_chave_extra_sobrevive,
                   test_item_sumido_nao_some_calado,
                   test_raiz_e_a_do_clone_principal, test_dry_run_nao_grava,
                   test_validate_recusa_plano_de_ondas, test_from_spec_le_os_criterios,
                   test_from_spec_avisa_rascunho_e_recusa_vazia,
                   test_from_spec_le_depois_do_cs_como_blocked_by,
                   test_from_triage_so_ready_vira_item,
                   test_from_triage_recusa_o_que_a_prosa_so_pedia,
                   test_from_triage_dependencia_para_fora_da_fila,
                   test_write_from_triage_grava_e_diz_que_e_parcial,
                   test_contrato_do_comando, test_contrato_do_triage):
            print(f"\n{fn.__name__}")
            fn(base)
    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
