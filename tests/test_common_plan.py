#!/usr/bin/env python3
"""Testes da etapa 1 de "um escritor, três fontes": /common:plan + cepa-plan.

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
    check("o `human_pending` aberto sobrevive a uma repriorização",
          por_id["B"]["human_pending"] == ITENS_OK[1]["human_pending"],
          "zerá-lo apagaria dívida que só o humano fecha")
    check("guardou cópia do arquivo anterior",
          (d / ".claude" / "programs" / "fila" / "plan.yaml.bak").is_file(),
          "os comentários escritos à mão não sobrevivem à reescrita")


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
    check("manda dizer quando a ordem foi HERDADA do texto da spec",
          "herdou" in f and "herdad" in f.lower(),
          "a preferência registrada no desenho: herdar e dizer que herdou")
    check("recusa gravar por cima de um plano de ondas",
          "Nunca grava por cima de um plano de ondas" in f)
    check("não fecha `human_pending` de ninguém",
          "Não fecha `human_pending` de ninguém" in f,
          "lista que se fecha sozinha é decoração")
    check("diz que `--from-jira` ainda não existe e para onde ir enquanto isso",
          "`--from-jira` ainda não existe" in f and "/board-flow:triage" in f,
          "sem isso o agente improvisa uma consulta ao Jira e a ordem sai da "
          "coluna, não da classificação")
    check("aponta o consumidor da fila", "/common:next" in f)
    check("declara que não executa nada", "Não executa" in f)

    # o catálogo é o único lugar onde um comando é encontrável por quem não o
    # escreveu — 8 comandos já sumiram dele sem nenhum teste piscar
    cat = flat((REPO / "docs" / "commands.md").read_text(encoding="utf-8"))
    check("está no catálogo docs/commands.md", "`/common:plan`" in cat)
    plugin = (REPO / "common" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    check("está na descrição do plugin common", "/plan" in plugin)


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_grava_fila_valida, test_recusa_sem_why,
                   test_recusa_human_pending_ausente, test_recusa_ciclo_e_fantasma,
                   test_recusa_id_repetido, test_colisao_com_ondas,
                   test_reescrita_preserva_execucao, test_item_sumido_nao_some_calado,
                   test_raiz_e_a_do_clone_principal, test_dry_run_nao_grava,
                   test_validate_recusa_plano_de_ondas, test_contrato_do_comando):
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
