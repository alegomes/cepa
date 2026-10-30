#!/usr/bin/env python3
"""Tests of stages 1 and 2 of "one writer, three sources": /common:plan + cepa-plan.

Run with `python3 tests/test_common_plan.py` (it only needs the PyYAML that the
script itself uses). Two families, on purpose:

  - BEHAVIOR of `common/bin/cepa-plan`, which is the one that writes. Each refusal here
    exists because the corresponding failure destroys the document in silence: a queue
    written over a wave plan, `human_pending` zeroed in a
    reprioritization, a blocking cycle that makes /common:next say the queue
    ended when it jammed.
  - PROSE CONTRACT of `common/commands/queue.md`. The command is a prompt, so
    the only possible guard is mechanical: the sentence "do not invent the `why`" is
    exactly the kind of instruction that vanishes in a well-intentioned rewrite.

What these tests do NOT prove: that the command conducts the interrogation well. Only
a real run tells.
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
CMD = REPO / "common" / "commands" / "queue.md"

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


def git_repo(base, given_name):
    d = Path(base) / given_name
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def write_items(d, items):
    p = d / "itens.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    return p


def plan_of(d, given_name="fila"):
    return yaml.safe_load(
        (d / ".claude" / "queues" / given_name / "queue.yaml").read_text(encoding="utf-8"))


ITEMS_OK = [
    {"id": "A", "title": "primeiro", "why": "destrava o B", "human_pending": None},
    {"id": "B", "title": "segundo", "why": "depende do A", "blocked_by": ["A"],
     "human_pending": "rodar bin/install.sh --clean e reiniciar"},
]


# ── behavior ─────────────────────────────────────────────────────────────────

def test_writes_valid_queue(base):
    d = git_repo(base, "grava")
    r = run(d, "write", "fila", "--items", str(write_items(d, ITEMS_OK)),
            "--source", "BACKLOG.md", "--quando", "2026-08-24", "--repo", ".")
    check("grava uma fila válida", r.returncode == 0, r.stderr)
    plan = plan_of(d)
    check("declara schema 2 e single-track",
          plan["schema_version"] == 2 and plan["mode"] == "single-track")
    check("a ORDEM da lista é o dado, preservada como veio",
          [i["id"] for i in plan["items"]] == ["A", "B"])
    check("guarda o `why` de cada posição",
          [i["why"] for i in plan["items"]] == ["destrava o B", "depende do A"])
    check("guarda a fonte das demandas", plan["source"] == "BACKLOG.md")
    check("o arquivo gravado passa na própria validação",
          run(d, "validate",
              str(d / ".claude" / "queues" / "fila" / "queue.yaml")).returncode == 0)


def test_refuses_without_why(base):
    """An empty `why` is the gap that kills the document: the queue keeps the order and
    loses the criterion, which is the only thing the tracker did not already keep."""
    d = git_repo(base, "sem-why")
    items = [{"id": "A", "title": "x", "why": "  ", "human_pending": None}]
    r = run(d, "write", "fila", "--items", str(write_items(d, items)), "--repo", ".")
    check("recusa item sem `why`", r.returncode == 2, r.stdout)
    check("a recusa NOMEIA o campo", "`why`" in r.stderr, r.stderr)
    check("nada foi gravado na recusa",
          not (d / ".claude" / "queues" / "fila").exists())


def test_refuses_missing_human_pending(base):
    """An explicit null is an answer; an absent key is an omission, and the debt with the
    human becomes invisible again — which is the reason the field exists."""
    d = git_repo(base, "sem-hp")
    items = [{"id": "A", "title": "x", "why": "porque sim"}]
    r = run(d, "write", "fila", "--items", str(write_items(d, items)), "--repo", ".")
    check("recusa item sem a chave `human_pending`", r.returncode == 2)
    check("a recusa explica que null explícito serve",
          "null" in r.stderr.lower() or "nulo" in r.stderr.lower(), r.stderr)


def test_refuses_cycle_and_ghost(base):
    d = git_repo(base, "ciclo")
    items = [
        {"id": "X", "title": "x", "why": "por causa do Y", "blocked_by": ["Y"],
         "human_pending": None},
        {"id": "Y", "title": "y", "why": "por causa do X", "blocked_by": ["X"],
         "human_pending": None},
    ]
    r = run(d, "write", "fila", "--items", str(write_items(d, items)), "--repo", ".")
    check("recusa ciclo de bloqueio", r.returncode == 2)
    check("a recusa diz por que ciclo é pior que travamento visível",
          "ciclo" in r.stderr and "acabado" in r.stderr, r.stderr)

    items = [{"id": "X", "title": "x", "why": "w", "blocked_by": ["FANTASMA"],
              "human_pending": None}]
    r = run(d, "write", "fila", "--items", str(write_items(d, items)), "--repo", ".")
    check("recusa `blocked_by` apontando para item inexistente", r.returncode == 2)
    check("nomeia o id fantasma", "FANTASMA" in r.stderr, r.stderr)


def test_refuses_repeated_id(base):
    d = git_repo(base, "repetido")
    items = [{"id": "A", "title": "um", "why": "w", "human_pending": None},
             {"id": "A", "title": "outro", "why": "w", "human_pending": None}]
    r = run(d, "write", "fila", "--items", str(write_items(d, items)), "--repo", ".")
    check("recusa `id` repetido", r.returncode == 2, r.stdout)


def test_collision_with_waves(base):
    """The mirror of maestro-programs --check-name, from the other side.

    The two planners write to the SAME directory and the name is a free choice of
    whoever calls; without this refusal, `/common:plan WEGO-paralelo` erases the waves —
    surface, acceptance and fork point of each slice — without a word.
    """
    d = git_repo(base, "colisao")
    waves = d / ".claude" / "programs" / "ondas"
    waves.mkdir(parents=True)
    (waves / "plan.yaml").write_text(
        "schema_version: 2\nmode: parallel-waves\nprogram: ondas\nwaves: []\n")

    r = run(d, "check-name", "ondas", "--repo", ".")
    check("check-name devolve 3 na colisão com ondas", r.returncode == 3, r.stdout)
    check("a colisão nomeia o dono do arquivo",
          "/maestro:program-plan" in r.stderr, r.stderr)

    r = run(d, "write", "ondas", "--items", str(write_items(d, ITEMS_OK)), "--repo", ".")
    check("write também recusa (a checagem não é só do comando)", r.returncode == 3)
    intact = yaml.safe_load((waves / "plan.yaml").read_text())
    check("o plano de ondas ficou intacto", intact["mode"] == "parallel-waves")

    r = run(d, "check-name", "livre", "--repo", ".")
    check("nome livre devolve 0", r.returncode == 0, r.stderr)


def test_rewrite_preserves_execution(base):
    """Reprioritizing cannot erase debt that nobody paid.

    `status` and `human_pending` come from EXECUTION; `title`, `why` and the position come
    from PLANNING. A rewrite that zeroed `human_pending` would make the debt
    vanish from the only place that showed it — and only the human closes that field.
    """
    d = git_repo(base, "reescrita")
    run(d, "write", "fila", "--items", str(write_items(d, ITEMS_OK)), "--repo", ".")
    target = d / ".claude" / "queues" / "fila" / "queue.yaml"
    plan = yaml.safe_load(target.read_text())
    plan["items"][0]["status"] = "done"
    target.write_text(yaml.dump(plan, allow_unicode=True, sort_keys=False))

    # same queue, inverted order and new `why` — the planning changed its mind
    new_ones = [
        {"id": "B", "title": "segundo", "why": "subiu: o A esbarrou em decisão",
         "human_pending": None},
        {"id": "A", "title": "primeiro", "why": "desceu", "human_pending": None},
    ]
    r = run(d, "write", "fila", "--items", str(write_items(d, new_ones)), "--repo", ".")
    check("reescreve uma fila existente", r.returncode == 0, r.stderr)
    plan = plan_of(d)
    by_id = {i["id"]: i for i in plan["items"]}
    check("a nova ORDEM manda", [i["id"] for i in plan["items"]] == ["B", "A"])
    check("o novo `why` manda", by_id["B"]["why"].startswith("subiu"))
    check("o `status` da execução sobrevive", by_id["A"]["status"] == "done")
    check("e a lista nova NÃO consegue reivindicar progresso que o disco não tem",
          run(d, "write", "fila", "--repo", ".", "--items", str(write_items(d, [
              {"id": "B", "title": "segundo", "why": "w", "status": "done",
               "human_pending": None},
              {"id": "A", "title": "primeiro", "why": "w", "human_pending": None},
          ]))).returncode == 0
          and {i["id"]: i["status"] for i in plan_of(d)["items"]}["B"] == "pending",
          "quem replaneja decide ordem, não progresso")
    check("o `human_pending` aberto sobrevive a uma repriorização",
          by_id["B"]["human_pending"] == ITEMS_OK[1]["human_pending"],
          "zerá-lo apagaria dívida que só o humano fecha")
    check("guardou cópia do arquivo anterior",
          (d / ".claude" / "queues" / "fila" / "queue.yaml.bak").is_file(),
          "os comentários escritos à mão não sobrevivem à reescrita")


def test_planning_can_retire_an_item(base):
    """`dropped` is the only word planning has about status.

    Found on the 1st real use (2026-08-25): the rule "the disk status always
    wins" prevented retiring an item the delivery itself made obsolete —
    it came back `pending` at each reprioritization, and the queue only grew.
    """
    d = git_repo(base, "aposenta")
    run(d, "write", "fila", "--items", str(write_items(d, ITEMS_OK)), "--repo", ".")
    new_ones = [
        {"id": "A", "title": "primeiro", "why": "destrava o B", "human_pending": None},
        {"id": "B", "title": "segundo", "why": "obsoleto: o A entregou junto",
         "status": "dropped", "human_pending": None},
    ]
    r = run(d, "write", "fila", "--items", str(write_items(d, new_ones)), "--repo", ".")
    check("a repriorização consegue aposentar um item", r.returncode == 0, r.stderr)
    by_id = {i["id"]: i for i in plan_of(d)["items"]}
    check("o item aposentado fica no documento com o porquê",
          by_id["B"]["status"] == "dropped" and "obsoleto" in by_id["B"]["why"],
          "sumir com ele apagaria a razão de ele ter saído")


def test_extra_key_survives(base):
    """A field the schema does not foresee does not vanish in a reprioritization.

    Found when using the command for the first time for real: the evidence of a
    `done` item lives today in a comment, and a comment does not survive the
    rewrite. A field does — as long as the writer does not discard it
    in silence, which is what it did.
    """
    d = git_repo(base, "extra")
    items = [{"id": "A", "title": "x", "why": "w", "human_pending": None,
              "evidence": "suíte 49/49 verde em 2026-08-24"}]
    run(d, "write", "fila", "--items", str(write_items(d, items)), "--repo", ".")
    check("a chave extra chega ao arquivo",
          plan_of(d)["items"][0].get("evidence", "").startswith("suíte"))

    # reprioritization that does NOT mention the key: it comes from the disk
    lean = [{"id": "A", "title": "x", "why": "outro motivo", "human_pending": None}]
    run(d, "write", "fila", "--items", str(write_items(d, lean)), "--repo", ".")
    item = plan_of(d)["items"][0]
    check("e sobrevive a uma reescrita que não a menciona",
          item.get("evidence", "").startswith("suíte"), str(item))
    check("sem impedir que o `why` novo entre", item["why"] == "outro motivo")


def test_vanished_item_does_not_vanish_silently(base):
    d = git_repo(base, "sumido")
    run(d, "write", "fila", "--items", str(write_items(d, ITEMS_OK)), "--repo", ".")
    less = [{"id": "A", "title": "primeiro", "why": "agora sozinho",
              "human_pending": None}]
    p = write_items(d, less)
    r = run(d, "write", "fila", "--items", str(p), "--repo", ".")
    check("recusa por default quando um item do disco não é mencionado",
          r.returncode == 4, r.stdout)
    check("nomeia o item que sumiria", " B" in r.stderr or "B," in r.stderr or
          r.stderr.strip().find("B") != -1, r.stderr)
    check("ainda tem 2 itens no disco", len(plan_of(d)["items"]) == 2)

    r = run(d, "write", "fila", "--items", str(p), "--repo", ".", "--on-missing", "drop")
    check("com --on-missing drop, grava marcando dropped", r.returncode == 0, r.stderr)
    by_id = {i["id"]: i for i in plan_of(d)["items"]}
    check("o item some da fila viva mas continua no documento",
          by_id["B"]["status"] == "dropped")


def test_from_spec_and_from_epic_still_refuse_vanished_item(base):
    """Only `--from-triage` stopped refusing: spec and epic still exit 4.

    The disk item that the new list does not mention carries a position and `why` that
    someone decided; outside triage there is no approved order that justifies
    making it vanish.
    """
    epic = """# Epic: Fixture

**Status:** pronta · **Aberto em:** 2026-10-08 · **Origem:** teste

## Intenção

Um Epic.

## Invariantes (nunca regridem)

- nada regride

## Escada de valor

| Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
| 1. Ler | O operador carrega o PDF e vê 3 respostas. | a lista | registro `contrato_lido` | O leitor de PDF extrai o texto. | já |

## Decidido sem perguntar (vete aqui)

- nada

## Perguntas em aberto

- [x] alguma? não
"""
    for given_name, source_args, plain_text in (
            ("spec", ("--from-spec", "spec.md"), SPEC_FIXTURE),
            ("epic", ("--from-epic", "epic.md", "--ciclo", "1"), epic)):
        d = git_repo(base, f"sumido-{given_name}")
        (d / source_args[1]).write_text(plain_text, encoding="utf-8")
        queue = [{"id": "VELHO", "title": "já na fila", "why": "decidido antes",
                 "human_pending": None}]
        r = run(d, "write", "fila", "--items", str(write_items(d, queue)),
                "--repo", ".")
        check(f"{given_name}: grava a fila de partida", r.returncode == 0, r.stderr)
        fname = d / ".claude" / "queues" / "fila" / "queue.yaml"
        before = fname.read_text(encoding="utf-8")
        r = run(d, "write", "fila", *source_args, "--repo", ".")
        check(f"{given_name}: sem --on-missing, item do disco não mencionado é exit 4",
              r.returncode == 4 and "VELHO" in r.stderr,
              f"{r.returncode} {r.stderr}")
        check(f"{given_name}: o arquivo do disco fica intacto",
              fname.read_text(encoding="utf-8") == before)


def test_root_is_the_main_clone_one(base):
    """Called from inside a linked worktree, it writes to the MAIN CLONE.

    It is layer 0 on the write side: in a repo whose .gitignore covers `.claude/`,
    a plan written inside the worktree is invisible to git and dies with it — the
    loss verified on 2026-08-18, which cost an entire triage.
    """
    d = git_repo(base, "principal")
    (d / "seed.txt").write_text("x")
    subprocess.run(["git", "-C", str(d), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(d), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "seed"], check=True)
    wt = Path(base) / "wt"
    subprocess.run(["git", "-C", str(d), "worktree", "add", "-q", str(wt), "-b", "lado"],
                   check=True, capture_output=True)

    r = run(wt, "write", "fila", "--items", str(write_items(wt, ITEMS_OK)), "--repo", ".")
    check("grava a partir da worktree", r.returncode == 0, r.stderr)
    check("o arquivo nasceu no clone principal",
          (d / ".claude" / "queues" / "fila" / "queue.yaml").is_file())
    check("e NÃO dentro da worktree",
          not (wt / ".claude" / "queues" / "fila" / "queue.yaml").exists(),
          "plano dentro da worktree morre com ela, sem aviso")


def test_dry_run_does_not_write(base):
    d = git_repo(base, "dry")
    r = run(d, "write", "fila", "--items", str(write_items(d, ITEMS_OK)),
            "--repo", ".", "--dry-run")
    check("--dry-run sai 0 e imprime o arquivo",
          r.returncode == 0 and "mode: single-track" in r.stdout)
    check("--dry-run não grava nada",
          not (d / ".claude" / "queues" / "fila").exists())


def test_validate_refuses_wave_plan(base):
    d = git_repo(base, "validate-ondas")
    p = d / "ondas.yaml"
    p.write_text("schema_version: 2\nmode: parallel-waves\nprogram: o\nwaves: []\n")
    r = run(d, "validate", str(p))
    check("validate recusa um documento de ondas", r.returncode == 2)
    check("e diz de quem é esse documento",
          "/maestro:program-plan" in r.stderr, r.stderr)
    # continuing to list queue gaps in a document that is not a queue sends
    # fixing the wrong thing: the owner would read "the queue has no items" about a
    # perfectly valid wave plan and would go tamper with it.
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

SPEC_DRAFT = SPEC_FIXTURE.replace("**Status:** pronta-para-construir",
                                     "**Status:** rascunho").replace(
    "## Perguntas em aberto\n", "## Perguntas em aberto\n- [ ] qual formato?\n")


def test_from_spec_reads_the_criteria(base):
    """The spec -> items conversion is CODE, not a prompt promise.

    The completeness auditor caught this on 2026-08-24: while `--from-spec`
    existed only as a paragraph of instruction in plan.md, the only possible test
    was grepping the prose — that is, proving the command PROMISES to inherit the order,
    never that an execution produces the promised queue.
    """
    d = git_repo(base, "spec")
    sp = d / "spec.md"
    sp.write_text(SPEC_FIXTURE, encoding="utf-8")

    r = run(d, "from-spec", str(sp))
    check("lê a spec e devolve itens", r.returncode == 0, r.stderr)
    items = json.loads(r.stdout)
    check("um item por critério de sucesso", len(items) == 2, str(items))
    check("a ORDEM é a do texto", [i["id"] for i in items] == ["CS-1", "CS-2"])
    check("o título é o do critério",
          items[0]["title"] == "o endpoint devolve o arquivo", items[0]["title"])
    check("o `why` DIZ que a ordem foi herdada",
          all("ninguém priorizou os critérios entre si" in i["why"] for i in items),
          "sem isso a fila apresenta como decisão uma ordem que ninguém tomou")
    check("o `why` carrega a superfície declarada na spec",
          "http" in items[0]["why"] and "domain" in items[1]["why"])
    check("o `why` carrega o teste vermelho INTEIRO, não a primeira linha",
          "passará quando devolver 200 com o CSV no corpo" in items[0]["why"],
          "campo cortado no meio da oração parece texto completo")
    check("nasce sem rota humana a cobrar",
          all(i["human_pending"] is None for i in items))

    r = run(d, "write", "daspec", "--from-spec", str(sp), "--repo", ".")
    check("write --from-spec grava a fila", r.returncode == 0, r.stderr)
    plan = plan_of(d, "daspec")
    check("a fila gravada tem um item por critério, na ordem do texto",
          [i["id"] for i in plan["items"]] == ["CS-1", "CS-2"])
    check("a fonte registrada aponta o arquivo da spec",
          "spec.md" in plan["source"], plan["source"])


def test_from_spec_reads_after_the_cs_as_blocked_by(base):
    """WEGO's spec said "Depois do CS-1" in CS-2 and the queue was born with
    `blocked_by` empty: the rule depended on the agent adding it by hand."""
    d = git_repo(base, "spec-dep")
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
    items = {i["id"]: i for i in json.loads(r.stdout)}
    check("\"Depois do CS-1 e CS-2\" vira blocked_by [CS-1, CS-2]",
          items.get("CS-3", {}).get("blocked_by") == ["CS-1", "CS-2"],
          str(items.get("CS-3")))
    check("critério sem a frase nasce sem dependência",
          items["CS-1"]["blocked_by"] == [] and items["CS-2"]["blocked_by"] == [])
    check("dependência de critério que não existe fica fora e é avisada",
          items["CS-4"]["blocked_by"] == [] and "CS-9" in r.stderr, r.stderr)


def test_from_spec_warns_draft_and_refuses_empty(base):
    d = git_repo(base, "spec-ruim")
    sp = d / "rascunho.md"
    sp.write_text(SPEC_DRAFT, encoding="utf-8")
    r = run(d, "from-spec", str(sp))
    check("aceita a spec em rascunho mas AVISA", r.returncode == 0, r.stderr)
    check("o aviso nomeia o status e a pergunta em aberto",
          "rascunho" in r.stderr and "aberto" in r.stderr, r.stderr)

    blank = d / "vazia.md"
    blank.write_text("# Especificação: nada\n\n**Status:** rascunho\n", encoding="utf-8")
    r = run(d, "from-spec", str(blank))
    check("recusa uma spec sem nenhum critério de sucesso", r.returncode == 2)
    check("e diz o que faltou", "CS-" in r.stderr, r.stderr)


def test_from_spec_reads_the_new_and_the_old_names(base):
    """`ready-to-build`/`Surface`/`Red test` and `pronta-para-construir`/
    `Superfície`/`Teste vermelho` produce the same queue, without a warning."""
    d = git_repo(base, "spec-idiomas")
    new = (SPEC_FIXTURE.replace("pronta-para-construir", "ready-to-build")
            .replace("**Superfície:**", "**Surface:**")
            .replace("**Teste vermelho:**", "**Red test:**"))
    (d / "antiga.md").write_text(SPEC_FIXTURE, encoding="utf-8")
    (d / "nova.md").write_text(new, encoding="utf-8")
    a = run(d, "from-spec", str(d / "antiga.md"))
    n = run(d, "from-spec", str(d / "nova.md"))
    check("from-spec lê a spec nos dois idiomas sem aviso",
          a.returncode == 0 == n.returncode and a.stderr.strip() == ""
          and n.stderr.strip() == "", (a.stderr, n.stderr))
    ia, inn = json.loads(a.stdout), json.loads(n.stdout)
    check("...e os itens são os mesmos (id, título, why)",
          [(i["id"], i["title"], i["why"]) for i in ia]
          == [(i["id"], i["title"], i["why"]) for i in inn] and len(ia) == 2,
          (ia, inn))
    check("...com a superfície e o teste vermelho no why",
          "superfície onde se observa: http" in inn[0]["why"]
          and "teste vermelho declarado:" in inn[0]["why"], inn[0]["why"])
    r = run(d, "from-spec", str(d / "nova.md"))
    draft = new.replace("ready-to-build", "draft")
    (d / "draft.md").write_text(draft, encoding="utf-8")
    r = run(d, "from-spec", str(d / "draft.md"))
    check("Status: draft vira aviso que nomeia `ready-to-build`",
          r.returncode == 0 and "Status: draft" in r.stderr
          and "`ready-to-build`" in r.stderr, r.stderr)


# ── prose contract of the command ────────────────────────────────────────────

def flat(txt):
    return " ".join(txt.split())


def test_command_contract(_base):
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
          "Never writes the YAML by hand" in f,
          "por fora do script nenhuma das recusas acontece")
    check("proíbe inventar ordem e `why`",
          "Never invents order or `why`" in f)
    check("manda a leitura da spec passar pelo `from-spec` (não pelos seus olhos)",
          "cepa-plan from-spec" in f,
          "leitura no olho não deixa evidência: só provaria que o comando promete")
    check("manda dizer quando a ordem foi HERDADA do texto da spec",
          "say that it inherited it" in f and "what was inherited" in f,
          "a preferência registrada no desenho: herdar e dizer que herdou")
    check("recusa gravar por cima de um plano de ondas",
          "Never writes over a wave plan" in f)
    check("não fecha `human_pending` de ninguém",
          "Never closes anyone's `human_pending`" in f,
          "lista que se fecha sozinha é decoração")
    # Stage 2: the flag exists. The guard that matters stopped being "say it does not
    # exist" and became "do not consult Jira on your own" — the risk is
    # the same on both sides, a queue whose order came out of the board's rank.
    check("manda a leitura do repasse passar pelo `from-triage`",
          "cepa-plan from-triage" in f,
          "leitura no olho não deixa evidência: só provaria que o comando promete")
    check("proíbe montar a fila de uma consulta crua ao Jira",
          "Never queries Jira directly" in f and "/board-flow:triage" in f,
          "a ordem de uma fila vinda de board sai da CLASSIFICAÇÃO, não da "
          "coluna — o rank do quadro é justamente a ordem que este documento "
          "existe para substituir")
    check("diz o que fazer quando falta board-flow ou board-flow.yaml",
          "board-flow.yaml" in f and "do not improvise a Jira query" in f,
          "sem saída nomeada o agente inventa uma consulta ao Jira")
    check("diz que só card `ready` vira item da fila",
          "only a `ready` card becomes a `pending` item" in f,
          "In Review pertence à fila de prova, não à de construção")
    check("aponta o consumidor da fila", "/common:next" in f)
    check("declara que não executa nada", "Does not execute anything" in f)

    # the catalog is the only place where a command is findable by whoever did not
    # write it — 8 commands already vanished from it with no test flickering
    cat = flat((REPO / "docs" / "commands.md").read_text(encoding="utf-8"))
    check("está no catálogo docs/commands.md", "`/common:queue`" in cat)
    plugin = (REPO / "common" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    check("está na descrição do plugin common", "/plan" in plugin)


# ── passing on a triage (stage 2) ────────────────────────────────────────────

PASS_ON_OK = {
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


def pass_on(d, data, given_name="repasse.json"):
    p = Path(d) / given_name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_from_triage_only_ready_becomes_item(base):
    """The triage -> items conversion is CODE, for the same reason as stage 1.

    The rules exercised here lived in the prose of `board-flow/commands/triage.md`
    — "only → To Do cards become pending items", "Won't Do becomes dropped, not
    deletion", "under --max, say that the queue is a piece". As long as they live only there, the
    only possible test is grepping the instruction, which proves the command PROMISES
    to apply them and never that an execution applied them.
    """
    d = git_repo(base, "triagem")
    r = run(d, "from-triage", str(pass_on(d, PASS_ON_OK)))
    check("lê o repasse e devolve itens", r.returncode == 0, r.stderr)
    items = json.loads(r.stdout)

    ids = [i["id"] for i in items]
    check("card `implemented` NÃO vira item da fila", "WEGO-1234" not in ids,
          "In Review pertence à fila de prova; misturar manda construir o "
          "que já está construído")
    check("card `needs-refinement` NÃO vira item da fila", "WEGO-1238" not in ids)
    check("e o aviso NOMEIA quem ficou de fora e para onde vai",
          "WEGO-1234" in r.stderr and "prove-drain" in r.stderr, r.stderr)

    check("a ORDEM é a que a triagem classificou",
          ids == ["WEGO-1235", "WEGO-1240", "WEGO-1236"], str(ids))
    check("card READY vira `pending`",
          [i["status"] for i in items[:2]] == ["pending", "pending"])
    check("o `why` é o da triagem, não um inventado",
          items[0]["why"] == "destrava 1240 e 1237, que tocam o mesmo hook")
    check("a dependência entre cards sobrevive",
          items[1]["blocked_by"] == ["WEGO-1235"])

    obsolete = items[2]
    check("card OBSOLETE fica na fila como `dropped`, não some",
          obsolete["status"] == "dropped",
          "apagar faz a próxima varredura propor a mesma demanda de novo")
    check("e carrega o motivo do descarte",
          "dedup de WEGO-1240" in obsolete["why"]
          and obsolete.get("evidence") == "dedup de WEGO-1240")

    check("nasce sem rota humana a cobrar",
          all(i["human_pending"] is None for i in items))


def test_from_triage_refuses_what_the_prose_only_asked(base):
    d = git_repo(base, "triagem-ruim")

    without_why = {"cards": [{"key": "W-1", "title": "t", "bucket": "ready"}]}
    r = run(d, "from-triage", str(pass_on(d, without_why, "a.json")))
    check("recusa card READY sem `why`", r.returncode == 2)
    check("e diz que a ordem sem critério é o que o Jira já guarda",
          "W-1" in r.stderr and "inventar" in r.stderr, r.stderr)

    without_reason = {"cards": [{"key": "W-1", "title": "t", "bucket": "ready", "why": "x"},
                            {"key": "W-2", "title": "t", "bucket": "obsolete"}]}
    r = run(d, "from-triage", str(pass_on(d, without_reason, "b.json")))
    check("recusa card OBSOLETE sem motivo", r.returncode == 2)
    check("e nomeia o card", "W-2" in r.stderr, r.stderr)

    on_the_grid = {"cards": [{"key": "W-1", "title": "t", "bucket": "ready", "why": "x"},
                           {"key": "W-2", "title": "t", "bucket": "needs-decision"}]}
    r = run(d, "from-triage", str(pass_on(d, on_the_grid, "c.json")))
    check("recusa card ainda parado em `needs-decision`", r.returncode == 2,
          "a grelha do passo 6 não terminou, e a fila se leria como decidida")
    check("e manda de volta para a grelha",
          "W-2" in r.stderr and "grelha" in r.stderr, r.stderr)

    new_bucket = {"cards": [{"key": "W-1", "title": "t", "bucket": "talvez", "why": "x"}]}
    r = run(d, "from-triage", str(pass_on(d, new_bucket, "d.json")))
    check("recusa balde que a triagem não usa", r.returncode == 2,
          "balde desconhecido ignorado em silêncio some com o card")
    check("e lista os válidos", "ready" in r.stderr and "obsolete" in r.stderr)

    nothing = {"cards": [{"key": "W-1", "title": "t", "bucket": "implemented"}]}
    r = run(d, "from-triage", str(pass_on(d, nothing, "e.json")))
    check("recusa uma triagem que não deixou nada a enfileirar",
          r.returncode == 2, r.stderr)


def test_from_triage_dependency_outside_the_queue(base):
    """Depending on a card that went to In Review is not a ghost id.

    Refusing would force the agent to erase the information by hand; leaving it would make the
    general validation refuse the whole queue for a nonexistent id. It leaves the field and is
    SAID — leaving silently is how a dependency becomes a surprise at execution.
    """
    d = git_repo(base, "dep-fora")
    data = {"cards": [
        {"key": "W-1", "title": "t", "bucket": "ready", "why": "x",
         "blocked_by": ["W-2"]},
        {"key": "W-2", "title": "t", "bucket": "implemented"},
    ]}
    r = run(d, "from-triage", str(pass_on(d, data)))
    check("não recusa a fila por causa dela", r.returncode == 0, r.stderr)
    check("a dependência sai do `blocked_by`",
          json.loads(r.stdout)[0]["blocked_by"] == [])
    check("e o aviso nomeia os dois cards",
          "W-1" in r.stderr and "W-2" in r.stderr, r.stderr)

    ghost = {"cards": [{"key": "W-1", "title": "t", "bucket": "ready", "why": "x",
                           "blocked_by": ["W-9"]}]}
    r = run(d, "from-triage", str(pass_on(d, ghost, "f.json")))
    check("mas id que a triagem nunca viu segue sendo recusa",
          r.returncode == 2 and "W-9" in r.stderr, r.stderr)


def test_write_from_triage_writes_and_says_it_is_partial(base):
    d = git_repo(base, "grava-triagem")
    rp = pass_on(d, PASS_ON_OK)
    r = run(d, "write", "WEGO", "--from-triage", str(rp), "--repo", ".",
            "--quando", "2026-08-25")
    check("write --from-triage grava a fila", r.returncode == 0, r.stderr)

    plan = plan_of(d, "WEGO")
    check("a fila gravada tem os itens na ordem da triagem",
          [i["id"] for i in plan["items"]] == ["WEGO-1235", "WEGO-1240", "WEGO-1236"])
    check("a fonte registra projeto, coluna e data",
          all(x in plan["source"] for x in ("WEGO", "Backlog", "2026-08-25")),
          plan["source"])
    check("a fonte DIZ que a fila é um pedaço do quadro",
          "PARCIAL" in plan["source"] and "12" in plan["source"],
          "uma fila de 15 cards de 27 se lê, meses depois, como o quadro inteiro")
    check("o cabeçalho lido a olho também carrega a parcialidade",
          "PARCIAL" in (d / ".claude" / "queues" / "WEGO" / "queue.yaml"
                        ).read_text(encoding="utf-8"))

    # and the re-triage cannot erase what the execution wrote
    p = d / ".claude" / "queues" / "WEGO" / "queue.yaml"
    plan["items"][0]["status"] = "done"
    plan["items"][0]["human_pending"] = "abrir /admin/devolucoes e conferir"
    p.write_text(yaml.dump(plan, allow_unicode=True, sort_keys=False),
                 encoding="utf-8")
    r = run(d, "write", "WEGO", "--from-triage", str(rp), "--repo", ".")
    check("re-triagem grava de novo", r.returncode == 0, r.stderr)
    again = plan_of(d, "WEGO")["items"][0]
    check("o `done` do disco sobrevive à re-triagem", again["status"] == "done")
    check("e a dívida humana ABERTA sobrevive junto",
          again["human_pending"] == "abrir /admin/devolucoes e conferir",
          "só o humano fecha essa pendência; uma re-triagem que a zerasse "
          "apagaria dívida que ninguém pagou")


def test_partial_triage_preserves_queue_order(base):
    """A partial triage appends AFTER the pending ones, without touching their order.

    Found on a real board (2026-09-25, validar-fio-condutor-em-board-real):
    with --on-missing keep, 3 new cards entered in front of the 5 pending ones that
    the owner prioritized, and the 5 went to the end "without a chosen position". A
    triage of 5 cards reordered a queue of 25.
    """
    d = git_repo(base, "triagem-parcial")
    queue = [{"id": f"W-{n}", "title": f"priorizado {n}",
             "why": f"posição {n} decidida pelo dono", "human_pending": None}
            for n in (1437, 1500, 1600, 1700, 1800)]
    queue.insert(2, {"id": "W-900", "title": "já feito", "why": "x",
                    "status": "done", "human_pending": None})
    r = run(d, "write", "WEGO", "--items", str(write_items(d, queue)),
            "--repo", ".")
    check("grava a fila priorizada", r.returncode == 0, r.stderr)

    partial = {"project_key": "WEGO", "source_column": "To Do",
               "triaged_on": "2026-09-25", "remaining_in_column": 156,
               "cards": [
                   {"key": "W-1438", "title": "novo a", "bucket": "ready",
                    "why": "triagem: a"},
                   {"key": "W-1600", "title": "priorizado 1600, relido",
                    "bucket": "ready", "why": "triagem: relido"},
                   {"key": "W-1439", "title": "novo b", "bucket": "ready",
                    "why": "triagem: b"},
                   {"key": "W-1440", "title": "novo c", "bucket": "ready",
                    "why": "triagem: c", "blocked_by": ["W-1438"]},
               ]}
    rp = pass_on(d, partial, "parcial.json")
    fname = d / ".claude" / "queues" / "WEGO" / "queue.yaml"
    original = fname.read_text(encoding="utf-8")
    r = run(d, "write", "WEGO", "--from-triage", str(rp), "--repo", ".")
    check("sem --on-missing, a triagem parcial grava (fb-20261002-1)",
          r.returncode == 0, r.stderr)
    its = plan_of(d, "WEGO")["items"]
    check("a ordem da triagem vale para os abertos que ela cita; os que ela "
          "não citou ficam depois, na ordem antiga",
          [i["id"] for i in its] == ["W-900", "W-1438", "W-1600", "W-1439",
                                     "W-1440", "W-1437", "W-1500", "W-1700",
                                     "W-1800"], str([i["id"] for i in its]))
    check("o aviso nomeia os abertos empurrados para depois",
          all(x in r.stderr and x in r.stdout
              for x in ("W-1437", "W-1500", "W-1700", "W-1800")),
          r.stderr + r.stdout)
    check("item relido segue `pending`",
          {i["id"]: i for i in its}["W-1600"]["status"] == "pending")
    fname.write_text(original, encoding="utf-8")  # the keep branch starts from the original queue

    r = run(d, "write", "WEGO", "--from-triage", str(rp), "--repo", ".",
            "--on-missing", "keep")
    check("com --on-missing keep, grava", r.returncode == 0, r.stderr)
    ids = [i["id"] for i in plan_of(d, "WEGO")["items"]]
    check("a fila do disco fica na ordem dela e os novos entram DEPOIS",
          ids == ["W-1437", "W-1500", "W-900", "W-1600", "W-1700", "W-1800",
                  "W-1438", "W-1439", "W-1440"], str(ids))
    check("o relatório nomeia os cards acrescentados",
          "triagem parcial" in r.stdout and "W-1438" in r.stdout
          and "W-1600" not in r.stdout.split("triagem parcial")[1], r.stdout)
    items = {i["id"]: i for i in plan_of(d, "WEGO")["items"]}
    check("item já na fila que a triagem releu continua `pending` no lugar dele",
          items["W-1600"]["status"] == "pending")
    check("o `done` do meio da fila sobrevive", items["W-900"]["status"] == "done")
    check("a dependência entre cards novos sobrevive",
          items["W-1440"]["blocked_by"] == ["W-1438"])

    # a triage that covers the whole queue still rules the order
    d2 = git_repo(base, "triagem-inteira")
    rp2 = pass_on(d2, PASS_ON_OK)
    run(d2, "write", "WEGO", "--from-triage", str(rp2), "--repo", ".")
    inverted = dict(PASS_ON_OK, cards=[PASS_ON_OK["cards"][3],
                                        {**PASS_ON_OK["cards"][1], "blocked_by": []},
                                        PASS_ON_OK["cards"][0]])
    r = run(d2, "write", "WEGO", "--from-triage",
            str(pass_on(d2, inverted, "inv.json")), "--repo", ".",
            "--on-missing", "keep")
    check("triagem sem item sumido ainda reordena a fila",
          [i["id"] for i in plan_of(d2, "WEGO")["items"]]
          == ["WEGO-1236", "WEGO-1240", "WEGO-1235"], r.stderr)


def test_from_triage_preserves_absent_done_and_applies_the_order(base):
    """Triage records the approved order without asking for --on-missing for the `done` ones.

    Found on a real board (fb-20261002-1, 2026-10-02): the owner approved an order
    with new cards in front of items already in the queue, but `write --from-triage`
    refused (exit 4) because of 236 `done` outside the list; `keep` kept the disk
    order and `drop` would mark the `done` as dropped. The approved order was lost.
    """
    def builds(given_name):
        d = git_repo(base, given_name)
        queue = [{"id": f"D-{n}", "title": f"feito {n}", "why": "x",
                 "status": "done", "human_pending": None} for n in (1, 2, 3)]
        queue += [{"id": f"O-{n}", "title": f"aberto {n}", "why": f"posição {n}",
                  "human_pending": None} for n in (1, 2, 3, 4)]
        queue.insert(3, {"id": "X-1", "title": "abandonado", "why": "x",
                        "status": "dropped", "human_pending": None})
        # O-3 the triage cites: what is execution on disk has to survive
        o3 = next(i for i in queue if i["id"] == "O-3")
        o3["status"] = "in_progress"
        o3["human_pending"] = "conferir no admin"
        r = run(d, "write", "WEGO", "--items", str(write_items(d, queue)),
                "--repo", ".")
        check("grava a fila de partida", r.returncode == 0, r.stderr)
        # `write --items` refuses an item without `why`; the old queue without it (written
        # by hand or by an old version) can only be assembled directly in the YAML.
        fname = d / ".claude" / "queues" / "WEGO" / "queue.yaml"
        plan_data = yaml.safe_load(fname.read_text(encoding="utf-8"))
        for i in plan_data["items"]:
            if i["id"] in ("O-2", "D-2"):
                del i["why"]
        fname.write_text(yaml.dump(plan_data, allow_unicode=True, sort_keys=False),
                       encoding="utf-8")
        tri = {"project_key": "WEGO", "source_column": "To Do",
               "triaged_on": "2026-10-02", "remaining_in_column": 9,
               "cards": [
                   {"key": "N-1", "title": "novo", "bucket": "ready",
                    "why": "triagem: novo"},
                   {"key": "O-3", "title": "aberto 3", "bucket": "ready",
                    "why": "triagem: 3"},
                   {"key": "O-1", "title": "aberto 1", "bucket": "ready",
                    "why": "triagem: 1"},
               ]}
        return d, pass_on(d, tri, "tri.json")

    d, rp = builds("ft-padrao")
    r = run(d, "write", "WEGO", "--from-triage", str(rp), "--repo", ".")
    check("sem --on-missing, não recusa por causa dos done", r.returncode == 0,
          r.stderr)
    its = plan_of(d, "WEGO")["items"]
    check("done preservados, depois novo, os 2 na ordem da triagem, e os "
          "abertos não citados na ordem antiga",
          [i["id"] for i in its] == ["D-1", "D-2", "D-3", "X-1", "N-1", "O-3",
                                     "O-1", "O-2", "O-4"],
          str([i["id"] for i in its]))
    st = {i["id"]: i["status"] for i in its}
    check("os 3 done continuam done",
          all(st[k] == "done" for k in ("D-1", "D-2", "D-3")), str(st))
    check("o dropped ausente fica no bloco fechado e continua dropped",
          st["X-1"] == "dropped", str(st))
    by = {i["id"]: i for i in its}
    default = "sem `why` registrado na fila anterior"
    check("aberto e done ausentes, sem `why` no disco, recebem o `why` padrão",
          by["O-2"]["why"] == default and by["D-2"]["why"] == default,
          f"{by['O-2'].get('why')!r} / {by['D-2'].get('why')!r}")
    check("o aviso nomeia os abertos empurrados para depois",
          "O-2" in r.stderr and "O-4" in r.stderr and "O-2" in r.stdout, r.stderr)
    o3 = {i["id"]: i for i in its}["O-3"]
    check("item citado pela triagem mantém o `status` do disco",
          o3["status"] == "in_progress", str(o3))
    check("e a dívida humana aberta do disco",
          o3["human_pending"] == "conferir no admin", str(o3))

    d, rp = builds("ft-drop")
    r = run(d, "write", "WEGO", "--from-triage", str(rp), "--repo", ".",
            "--on-missing", "drop")
    check("--on-missing drop grava", r.returncode == 0, r.stderr)
    st = {i["id"]: i["status"] for i in plan_of(d, "WEGO")["items"]}
    check("drop marca só os 2 abertos não citados",
          st["O-2"] == "dropped" and st["O-4"] == "dropped"
          and st["O-1"] == "pending" and st["O-3"] == "in_progress", str(st))
    check("e deixa os 3 done como done",
          all(st[k] == "done" for k in ("D-1", "D-2", "D-3")), str(st))


def test_triage_contract(_base):
    """`/board-flow:triage` stopped being the queue's second writer.

    Two writers of the same rule diverge, and what is made of prose diverges
    with no test going red — which is the whole reason for stage 2.
    """
    tri = REPO / "board-flow" / "commands" / "triage.md"
    f = flat(tri.read_text(encoding="utf-8"))

    check("o comando existe", tri.is_file())
    check("declara que NÃO escreve mais o plan.yaml",
          "no longer writes `queue.yaml`" in f,
          "enquanto ele escrever também, as regras vivem em dois lugares")
    check("manda a gravação passar pelo cepa-plan --from-triage",
          "cepa-plan write --from-triage" in f or "--from-triage" in f)
    check("nomeia o repasse e onde ele mora",
          "triagem-<YYYY-MM-DD>.json" in f)
    check("entrega a ordem ao /common:queue", "/common:queue" in f)
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
          or "Triage never writes `queue.yaml`" in f)


def main():
    with tempfile.TemporaryDirectory() as base:
        for fn in (test_writes_valid_queue, test_refuses_without_why,
                   test_refuses_missing_human_pending, test_refuses_cycle_and_ghost,
                   test_refuses_repeated_id, test_collision_with_waves,
                   test_rewrite_preserves_execution, test_planning_can_retire_an_item,
                   test_extra_key_survives,
                   test_vanished_item_does_not_vanish_silently,
                   test_root_is_the_main_clone_one, test_dry_run_does_not_write,
                   test_validate_refuses_wave_plan, test_from_spec_reads_the_criteria,
                   test_from_spec_warns_draft_and_refuses_empty,
                   test_from_spec_reads_the_new_and_the_old_names,
                   test_from_spec_reads_after_the_cs_as_blocked_by,
                   test_from_triage_only_ready_becomes_item,
                   test_from_triage_refuses_what_the_prose_only_asked,
                   test_from_triage_dependency_outside_the_queue,
                   test_write_from_triage_writes_and_says_it_is_partial,
                   test_partial_triage_preserves_queue_order,
                   test_from_triage_preserves_absent_done_and_applies_the_order,
                   test_from_spec_and_from_epic_still_refuse_vanished_item,
                   test_command_contract, test_triage_contract):
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
