#!/usr/bin/env python3
"""CS-6 of cycle 1 of the Cepa in a spiral Epic: a cycle's queue comes out of the Epic.

Run with `python3 tests/test_cepa_plan_from_epic.py`. Surface: the CLI
`common/bin/cepa-plan`, called as a subprocess — what `/common:plan
--from-epic` tells to run.

What these tests charge:

  - on the real Epic `docs/epics/cepa-em-espiral.md`, `write cepa-espiral-c2
    --from-epic ... --ciclo 2 --dry-run` prints a queue whose `demonstrates:` is
    the walkthrough of cycle 2 and which has one item per sentence of "O que atravessa", in
    the order of the text, each with acceptance criterion and surface; and does not write;
  - in the /common:epic format (with "Efeito em tela" and "Efeito em backend") the
    surface comes from those columns, and a sentence with a period inside a backtick does not split;
  - really writing takes the `demonstrates:` to disk, `show` prints it, and
    rewriting the cycle does not erase the `status` that the execution recorded;
  - what cannot be derived is a refusal with a reason: a cycle that does not exist,
    an Epic without a ladder, a cycle without a piece, `--from-epic` without `--ciclo` and vice versa.
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
EPIC_REAL = REPO / "docs" / "epics" / "cepa-em-espiral.md"
CMD = REPO / "common" / "commands" / "queue.md"

FAILURES = []

# The walkthrough of cycle 2, copied from the Epic by hand: if the parser swaps column
# or cuts the cell, the `demonstrates:` stops matching this text.
WALKTHROUGH_C2 = (
    "Com a escada do Epic Contratos aprovada, o dono vai dormir e de manhã o "
    "ciclo 2 do Contratos está demonstrável: construção (drain), prova "
    "(`ui-proof-reviewer` com nonce) e aterrissagem em branch própria rodaram "
    "sozinhas, em worktrees filhas com o modo de cada estágio. Um needs-human "
    "em item com dependentes parou o ciclo em `aguardando-dono` e a pergunta "
    "está no terminal.")
PIECES_C2 = [
    "`cepa-until` como tronco + fork de filhos e merge train extraídos do "
    "Maestro como biblioteca",
    "`/maestro:run` deprecado",
]

EPIC_NEW = """# Epic: Fixture

**Status:** pronta · **Aberto em:** 2026-10-08 · **Origem:** teste

## Intenção

Um Epic no formato do /common:epic.

## Invariantes (nunca regridem)

- nada regride

## Escada de valor

| Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
| 1. Ler | O operador carrega o PDF e vê 3 respostas. | a lista de respostas na tela de upload | registro `contrato_lido` no banco | O leitor de PDF extrai o texto. O classificador lê `docs/regras.md` e marca `art. 5` na cláusula a \\| b. A tela mostra as 3 respostas. | já |
| 2. Comparar | O operador vê a diferença entre duas versões. | o diff lado a lado | evento `versao_comparada` | O comparador de versões 2.0. | depois |

## Decidido sem perguntar (vete aqui)

- nada

## Perguntas em aberto

- [x] alguma? não
"""


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def run(cwd, *args):
    return subprocess.run([sys.executable, str(CEPA_PLAN)] + list(args),
                          capture_output=True, text=True, cwd=str(cwd),
                          stdin=subprocess.DEVNULL)


def git_repo(base, given_name):
    d = Path(base) / given_name
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def yaml_body(output):
    """The YAML document printed by --dry-run (the header is a comment)."""
    return yaml.safe_load(output)


def plan_of(d, given_name):
    return d / ".claude" / "queues" / given_name / "queue.yaml"


def test_real_epic_cycle_2(base):
    d = git_repo(base, "real")
    r = run(d, "write", "cepa-espiral-c2", "--from-epic", str(EPIC_REAL),
            "--ciclo", "2", "--dry-run", "--repo", ".")
    check("dry-run sobre o Epic real sai 0", r.returncode == 0, r.stderr)
    if r.returncode != 0:
        return
    plan = yaml_body(r.stdout)
    check("o cabeçalho tem `demonstrates:` igual ao roteiro do ciclo 2",
          plan.get("demonstrates") == WALKTHROUGH_C2, repr(plan.get("demonstrates")))
    items = plan.get("items") or []
    check("um item por frase de \"O que atravessa\", na ordem do texto",
          [i.get("title") for i in items] == PIECES_C2,
          repr([i.get("title") for i in items]))
    check("ids estáveis por posição: C2-1, C2-2",
          [i.get("id") for i in items] == ["C2-1", "C2-2"],
          repr([i.get("id") for i in items]))
    for i in items:
        why = i.get("why") or ""
        check(f"{i.get('id')}: `why` traz o critério de aceite (o roteiro)",
              f"critério de aceite: o roteiro do ciclo — {WALKTHROUGH_C2}" in why,
              why)
        check(f"{i.get('id')}: `why` traz a superfície onde se observa",
              "superfície onde se observa:" in why, why)
        check(f"{i.get('id')}: `why` diz que a ordem foi herdada do texto",
              'herdado da ordem do texto da coluna "What it crosses"; '
              "ninguém priorizou as peças entre si" in why, why)
        check(f"{i.get('id')}: nasce pending, sem dependência deduzida",
              i.get("status") == "pending" and i.get("blocked_by") == [], repr(i))
    check("sem as colunas de efeito, a superfície é \"não declarada\", e é dito",
          all("não declarada no Epic" in (i.get("why") or "") for i in items)
          and "não declara \"Effect on screen\"" in r.stderr, r.stderr)
    check("Epic em rascunho vira aviso, não recusa",
          "Status: rascunho" in r.stderr, r.stderr)
    check("a linha `source` diz de que Epic e de que ciclo veio",
          "ciclo 2" in str(plan.get("source")) and "cepa-em-espiral.md" in
          str(plan.get("source")), repr(plan.get("source")))
    check("--dry-run não grava nada",
          not plan_of(d, "cepa-espiral-c2").exists())


def test_epic_command_format(base):
    d = git_repo(base, "novo")
    ep = d / "docs" / "epics" / "fixture.md"
    ep.parent.mkdir(parents=True)
    ep.write_text(EPIC_NEW, encoding="utf-8")
    r = run(d, "from-epic", "docs/epics/fixture.md", "--ciclo", "1")
    check("from-epic sai 0 no formato do /common:epic", r.returncode == 0,
          r.stderr)
    if r.returncode != 0:
        return
    data = json.loads(r.stdout)
    check("from-epic devolve o `demonstrates` do ciclo pedido",
          data.get("demonstrates") == "O operador carrega o PDF e vê 3 respostas.",
          repr(data.get("demonstrates")))
    titles = [i["title"] for i in data.get("items") or []]
    check("frase terminada em ponto vira item; ponto dentro de crase e `\\|` "
          "não partem",
          titles == ["O leitor de PDF extrai o texto",
                      "O classificador lê `docs/regras.md` e marca `art. 5` na cláusula a | b",
                      "A tela mostra as 3 respostas"], repr(titles))
    sup = ("superfície onde se observa: tela: a lista de respostas na tela de "
           "upload; backend: registro `contrato_lido` no banco")
    check("a superfície sai de \"Efeito em tela\" e \"Efeito em backend\"",
          all(sup in i["why"] for i in data["items"]),
          data["items"][0]["why"])
    check("Epic pronto e com efeitos não gera aviso", r.stderr.strip() == "",
          r.stderr)
    r2 = run(d, "from-epic", "docs/epics/fixture.md", "--ciclo", "2")
    t2 = [i["title"] for i in json.loads(r2.stdout)["items"]] if r2.returncode == 0 else r2.stderr
    check("outro ciclo, outra fila: só as peças do ciclo 2",
          t2 == ["O comparador de versões 2.0"], repr(t2))


EPIC_EN = (EPIC_NEW
           .replace("**Status:** pronta", "**Status:** ready")
           .replace("## Invariantes (nunca regridem)", "## Invariants (never regress)")
           .replace("## Escada de valor", "## Value ladder")
           .replace("| Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela "
                    "| Efeito em backend | O que atravessa | Quando |",
                    "| Cycle | Script (what the owner sees) | Effect on screen "
                    "| Effect in backend | What it crosses | When |")
           .replace("## Decidido sem perguntar (vete aqui)",
                    "## Decided without asking (veto here)"))


def test_new_and_old_epic_names(base):
    """The Epic with the names in Portuguese (`pronta`, `Escada de valor`, ...) and the one
    with the new ones (`ready`, `Value ladder`, ...) feed `--from-epic --cycle`
    the same way; `--cycle` and `--ciclo` are the same flag."""
    d = git_repo(base, "dois-idiomas")
    (d / "antigo.md").write_text(EPIC_NEW, encoding="utf-8")
    (d / "novo.md").write_text(EPIC_EN, encoding="utf-8")
    check("o fixture novo não tem mais nenhum nome antigo",
          not any(w in EPIC_EN for w in ("Escada de valor", "Roteiro",
                                         "Efeito em", "O que atravessa",
                                         "Status:** pronta")), EPIC_EN)
    outputs = {}
    for fname, flag in (("antigo.md", "--ciclo"), ("antigo.md", "--cycle"),
                      ("novo.md", "--cycle"), ("novo.md", "--ciclo")):
        r = run(d, "from-epic", fname, flag, "1")
        check(f"{fname} {flag} 1: sai 0 e sem aviso", r.returncode == 0
              and r.stderr.strip() == "", r.stderr)
        outputs[(fname, flag)] = r.stdout
    check("os quatro caminhos entregam o mesmo ciclo (mesmos itens)",
          len({json.dumps([(i["id"], i["title"]) for i in json.loads(v)["items"]])
               for v in outputs.values()}) == 1,
          repr(list(outputs.values())))
    check("...e o mesmo `demonstrates`",
          len({json.loads(v)["demonstrates"] for v in outputs.values()}) == 1)
    w = run(d, "write", "fx-en", "--from-epic", "novo.md", "--cycle", "1",
            "--when", "2026-10-23", "--repo", ".")
    check("write --from-epic novo.md --cycle 1 --when grava", w.returncode == 0,
          w.stderr)
    w2 = run(d, "write", "fx-pt", "--from-epic", "antigo.md", "--ciclo", "1",
             "--quando", "2026-10-23", "--repo", ".")
    check("write --from-epic antigo.md --ciclo 1 --quando grava", w2.returncode == 0,
          w2.stderr)
    if w.returncode == 0 and w2.returncode == 0:
        a = yaml.safe_load(plan_of(d, "fx-en").read_text(encoding="utf-8"))
        b = yaml.safe_load(plan_of(d, "fx-pt").read_text(encoding="utf-8"))
        check("as duas filas gravadas têm os mesmos itens e `demonstrates`",
              [i["title"] for i in a["items"]] == [i["title"] for i in b["items"]]
              and a["demonstrates"] == b["demonstrates"])
    draft = d / "rascunho.md"
    draft.write_text(EPIC_EN.replace("**Status:** ready", "**Status:** draft"),
                        encoding="utf-8")
    r = run(d, "from-epic", str(draft), "--cycle", "1")
    check("Status: draft vira aviso que nomeia `ready`",
          r.returncode == 0 and "Status: draft" in r.stderr
          and "só `ready`" in r.stderr, r.stderr)


def test_writes_and_rewrites(base):
    d = git_repo(base, "grava")
    ep = d / "epic.md"
    ep.write_text(EPIC_NEW, encoding="utf-8")
    r = run(d, "write", "fx-c1", "--from-epic", "epic.md", "--ciclo", "1",
            "--quando", "2026-10-08", "--repo", ".")
    check("write --from-epic grava", r.returncode == 0, r.stderr)
    target = plan_of(d, "fx-c1")
    if not target.exists():
        check("o plano existe depois do write", False)
        return
    plan = yaml.safe_load(target.read_text(encoding="utf-8"))
    check("o `demonstrates:` gravado é o roteiro do ciclo",
          plan.get("demonstrates") == "O operador carrega o PDF e vê 3 respostas.",
          repr(plan.get("demonstrates")))
    v = run(d, "validate", str(target))
    check("a fila gravada passa no validate", v.returncode == 0, v.stderr)
    s = run(d, "show", "fx-c1", "--repo", ".")
    check("show imprime o roteiro como `demonstrates`",
          "O operador carrega o PDF e vê 3 respostas." in s.stdout, s.stdout)
    st = run(d, "start", "fx-c1", "C1-1", "--repo", ".")
    check("o primeiro item é reservável", st.returncode == 0, st.stderr)
    r = run(d, "write", "fx-c1", "--from-epic", "epic.md", "--ciclo", "1",
            "--repo", ".")
    plan = yaml.safe_load(target.read_text(encoding="utf-8"))
    status = {i["id"]: i["status"] for i in plan["items"]}
    check("reescrever o ciclo preserva o status que a execução gravou",
          r.returncode == 0 and status.get("C1-1") == "in_progress",
          f"{r.stderr} {status}")


def test_from_epic_over_queue_with_old_key(base):
    d = git_repo(base, "antiga")
    (d / "epic.md").write_text(EPIC_NEW, encoding="utf-8")
    r = run(d, "write", "fx-old", "--from-epic", "epic.md", "--ciclo", "1",
            "--quando", "2026-10-08", "--repo", ".")
    target = plan_of(d, "fx-old")
    check("grava a fila de partida", r.returncode == 0 and target.exists(), r.stderr)
    if not target.exists():
        return
    plan = yaml.safe_load(target.read_text(encoding="utf-8"))
    walkthrough = plan.pop("demonstrates")
    plan["demonstra"] = walkthrough  # as the previous version wrote it
    target.write_text(yaml.dump(plan, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    s = run(d, "show", "fx-old", "--repo", ".")
    check("show imprime o roteiro de uma fila com a chave antiga `demonstra:`",
          walkthrough in s.stdout, s.stdout + s.stderr)
    st = run(d, "start", "fx-old", "C1-1", "--repo", ".")
    check("o item da fila antiga é reservável", st.returncode == 0, st.stderr)
    r = run(d, "write", "fx-old", "--from-epic", "epic.md", "--ciclo", "1",
            "--repo", ".")
    new = yaml.safe_load(target.read_text(encoding="utf-8"))
    status = {i["id"]: i["status"] for i in new["items"]}
    check("reescrever sobre a chave antiga funciona e preserva o status",
          r.returncode == 0 and status.get("C1-1") == "in_progress",
          f"{r.stderr} {status}")
    check("e grava só `demonstrates:`, com o roteiro do Epic",
          new.get("demonstrates") == walkthrough and "demonstra" not in new,
          str(list(new)))


def test_refusals(base):
    d = git_repo(base, "recusa")
    r = run(d, "write", "x", "--from-epic", str(EPIC_REAL), "--ciclo", "9",
            "--dry-run", "--repo", ".")
    check("ciclo que não existe é recusa (exit 2) e lista os ciclos",
          r.returncode == 2 and "não tem o ciclo 9" in r.stderr
          and "2. Conduzir" in r.stderr, r.stderr)
    r = run(d, "write", "x", "--from-epic", str(EPIC_REAL), "--dry-run",
            "--repo", ".")
    check("--from-epic sem --ciclo é recusa",
          r.returncode != 0 and "--cycle" in r.stderr, r.stderr)
    r = run(d, "write", "x", "--items", "-", "--ciclo", "2", "--dry-run",
            "--repo", ".")
    check("--ciclo sem --from-epic é recusa",
          r.returncode != 0 and "--from-epic" in r.stderr, r.stderr)
    without_ = d / "sem.md"
    without_.write_text("# Epic: sem escada\n\n## Intenção\n\nnada\n", encoding="utf-8")
    r = run(d, "from-epic", str(without_), "--ciclo", "1")
    check("Epic sem `## Escada de valor` é recusa",
          r.returncode == 2 and "Value ladder" in r.stderr, r.stderr)
    empty = d / "vazio.md"
    empty.write_text(EPIC_NEW.replace("O comparador de versões 2.0.", "—"),
                     encoding="utf-8")
    r = run(d, "from-epic", str(empty), "--ciclo", "2")
    check("ciclo com \"O que atravessa\" vazio é recusa",
          r.returncode == 2 and "What it crosses" in r.stderr, r.stderr)
    without_walkthrough = d / "semroteiro.md"
    without_walkthrough.write_text(EPIC_NEW.replace(
        "O operador vê a diferença entre duas versões.", "—"), encoding="utf-8")
    r = run(d, "from-epic", str(without_walkthrough), "--ciclo", "2")
    check("ciclo sem roteiro é recusa",
          r.returncode == 2 and "roteiro" in r.stderr, r.stderr)
    check("nada foi gravado nas recusas", not (d / ".claude").exists())


def test_warnings_and_refusals_of_malformed_epic(base):
    d = git_repo(base, "malformado")

    open_ = d / "aberta.md"
    open_.write_text(EPIC_NEW.replace("- [x] alguma? não",
                                        "- [ ] quem aprova?"), encoding="utf-8")
    r = run(d, "from-epic", str(open_), "--ciclo", "1")
    check("pergunta `- [ ]` em Epic pronto vira aviso, e a fila sai",
          r.returncode == 0 and "1 pergunta(s) ainda em aberto" in r.stderr,
          r.stderr)

    for column, header in (("What it crosses", "O que atravessa"),
                              ("Script", "Roteiro de demonstração (o que o dono vê)")):
        without_ = d / f"sem-{column[:7].replace(' ', '')}.md"
        without_.write_text(EPIC_NEW.replace(f"| {header} |", "| Outra |"),
                       encoding="utf-8")
        r = run(d, "from-epic", str(without_), "--ciclo", "1")
        check(f"escada sem a coluna \"{column}\" é recusa que a nomeia",
              r.returncode == 2 and "não tem a(s) coluna(s)" in r.stderr
              and column in r.stderr, r.stderr)

    without_table = d / "semtabela.md"
    without_table.write_text("# Epic: x\n\n## Escada de valor\n\nainda não escrita\n"
                          "\n## Invariantes\n\n- y\n", encoding="utf-8")
    r = run(d, "from-epic", str(without_table), "--ciclo", "1")
    check("escada sem tabela é recusa",
          r.returncode == 2 and "não tem tabela" in r.stderr, r.stderr)

    r = run(d, "from-epic", str(open_))
    check("o subcomando from-epic sem --ciclo é recusa",
          r.returncode != 0 and "--cycle" in r.stderr, r.stderr)

    # The "O que atravessa" column last, without the closing `|`: the `\|`
    # at the end of the line is an escaped bar of the cell, not the divider.
    last = d / "ultima.md"
    last.write_text("# Epic: x\n\n## Escada de valor\n\n"
                      "| Ciclo | Roteiro | O que atravessa\n|---|---|---\n"
                      "| 1. Um | o dono vê. | A peça a \\|\n", encoding="utf-8")
    r = run(d, "from-epic", str(last), "--ciclo", "1")
    t = [i["title"] for i in json.loads(r.stdout)["items"]] if r.returncode == 0 else r.stderr
    check("`\\|` no fim da última célula é texto, não divisor",
          t == ["A peça a |"], repr(t))


def test_prose_contract():
    f = CMD.read_text(encoding="utf-8")
    check("plan.md manda a leitura do Epic passar pelo `from-epic`",
          "cepa-plan from-epic" in f)
    check("plan.md declara --from-epic e --cycle no argument-hint",
          "--from-epic docs/epics/<name>.md --cycle N" in f.split("\n---", 1)[0])


def main():
    with tempfile.TemporaryDirectory() as base:
        test_real_epic_cycle_2(base)
        test_epic_command_format(base)
        test_new_and_old_epic_names(base)
        test_writes_and_rewrites(base)
        test_from_epic_over_queue_with_old_key(base)
        test_refusals(base)
        test_warnings_and_refusals_of_malformed_epic(base)
    test_prose_contract()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\ntudo ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
