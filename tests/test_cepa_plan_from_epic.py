#!/usr/bin/env python3
"""CS-6 do ciclo 1 do Epic Cepa em espiral: a fila de um ciclo sai do Epic.

Rode com `python3 tests/test_cepa_plan_from_epic.py`. Superfície: a CLI
`common/bin/cepa-plan`, chamada como subprocesso — o que o `/common:plan
--from-epic` manda rodar.

O que estes testes cobram:

  - sobre o Epic real `docs/epics/cepa-em-espiral.md`, `write cepa-espiral-c2
    --from-epic ... --ciclo 2 --dry-run` imprime uma fila cujo `demonstra:` é
    o roteiro do ciclo 2 e que tem um item por frase de "O que atravessa", na
    ordem do texto, cada um com critério de aceite e superfície; e não grava;
  - no formato do /common:epic (com "Efeito em tela" e "Efeito em backend") a
    superfície sai dessas colunas, e frase com ponto dentro de crase não parte;
  - gravar de verdade leva o `demonstra:` ao disco, o `show` o imprime, e
    reescrever o ciclo não apaga o `status` que a execução gravou;
  - o que não dá para derivar é recusa com motivo: ciclo que não existe,
    Epic sem escada, ciclo sem peça, `--from-epic` sem `--ciclo` e vice-versa.
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
CMD = REPO / "common" / "commands" / "plan.md"

FAILURES = []

# O roteiro do ciclo 2, copiado do Epic à mão: se o parser trocar de coluna
# ou cortar a célula, o `demonstra:` deixa de bater com este texto.
ROTEIRO_C2 = (
    "Com a escada do Epic Contratos aprovada, o dono vai dormir e de manhã o "
    "ciclo 2 do Contratos está demonstrável: construção (drain), prova "
    "(`ui-proof-reviewer` com nonce) e aterrissagem em branch própria rodaram "
    "sozinhas, em worktrees filhas com o modo de cada estágio. Um needs-human "
    "em item com dependentes parou o ciclo em `aguardando-dono` e a pergunta "
    "está no terminal.")
PECAS_C2 = [
    "`cepa-until` como tronco + fork de filhos e merge train extraídos do "
    "Maestro como biblioteca",
    "`/maestro:run` deprecado",
]

EPIC_NOVO = """# Epic: Fixture

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


def repo_git(base, nome):
    d = Path(base) / nome
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def corpo_yaml(saida):
    """O documento YAML impresso pelo --dry-run (o cabeçalho é comentário)."""
    return yaml.safe_load(saida)


def plano_de(d, nome):
    return d / ".claude" / "programs" / nome / "plan.yaml"


def test_epic_real_ciclo_2(base):
    d = repo_git(base, "real")
    r = run(d, "write", "cepa-espiral-c2", "--from-epic", str(EPIC_REAL),
            "--ciclo", "2", "--dry-run", "--repo", ".")
    check("dry-run sobre o Epic real sai 0", r.returncode == 0, r.stderr)
    if r.returncode != 0:
        return
    plan = corpo_yaml(r.stdout)
    check("o cabeçalho tem `demonstra:` igual ao roteiro do ciclo 2",
          plan.get("demonstra") == ROTEIRO_C2, repr(plan.get("demonstra")))
    itens = plan.get("items") or []
    check("um item por frase de \"O que atravessa\", na ordem do texto",
          [i.get("title") for i in itens] == PECAS_C2,
          repr([i.get("title") for i in itens]))
    check("ids estáveis por posição: C2-1, C2-2",
          [i.get("id") for i in itens] == ["C2-1", "C2-2"],
          repr([i.get("id") for i in itens]))
    for i in itens:
        why = i.get("why") or ""
        check(f"{i.get('id')}: `why` traz o critério de aceite (o roteiro)",
              f"critério de aceite: o roteiro do ciclo — {ROTEIRO_C2}" in why,
              why)
        check(f"{i.get('id')}: `why` traz a superfície onde se observa",
              "superfície onde se observa:" in why, why)
        check(f"{i.get('id')}: `why` diz que a ordem foi herdada do texto",
              'herdado da ordem do texto da coluna "O que atravessa"; '
              "ninguém priorizou as peças entre si" in why, why)
        check(f"{i.get('id')}: nasce pending, sem dependência deduzida",
              i.get("status") == "pending" and i.get("blocked_by") == [], repr(i))
    check("sem as colunas de efeito, a superfície é \"não declarada\", e é dito",
          all("não declarada no Epic" in (i.get("why") or "") for i in itens)
          and "não declara \"Efeito em tela\"" in r.stderr, r.stderr)
    check("Epic em rascunho vira aviso, não recusa",
          "Status: rascunho" in r.stderr, r.stderr)
    check("a linha `source` diz de que Epic e de que ciclo veio",
          "ciclo 2" in str(plan.get("source")) and "cepa-em-espiral.md" in
          str(plan.get("source")), repr(plan.get("source")))
    check("--dry-run não grava nada",
          not plano_de(d, "cepa-espiral-c2").exists())


def test_formato_do_epic_command(base):
    d = repo_git(base, "novo")
    ep = d / "docs" / "epics" / "fixture.md"
    ep.parent.mkdir(parents=True)
    ep.write_text(EPIC_NOVO, encoding="utf-8")
    r = run(d, "from-epic", "docs/epics/fixture.md", "--ciclo", "1")
    check("from-epic sai 0 no formato do /common:epic", r.returncode == 0,
          r.stderr)
    if r.returncode != 0:
        return
    dados = json.loads(r.stdout)
    check("from-epic devolve o `demonstra` do ciclo pedido",
          dados.get("demonstra") == "O operador carrega o PDF e vê 3 respostas.",
          repr(dados.get("demonstra")))
    titulos = [i["title"] for i in dados.get("items") or []]
    check("frase terminada em ponto vira item; ponto dentro de crase e `\\|` "
          "não partem",
          titulos == ["O leitor de PDF extrai o texto",
                      "O classificador lê `docs/regras.md` e marca `art. 5` na cláusula a | b",
                      "A tela mostra as 3 respostas"], repr(titulos))
    sup = ("superfície onde se observa: tela: a lista de respostas na tela de "
           "upload; backend: registro `contrato_lido` no banco")
    check("a superfície sai de \"Efeito em tela\" e \"Efeito em backend\"",
          all(sup in i["why"] for i in dados["items"]),
          dados["items"][0]["why"])
    check("Epic pronto e com efeitos não gera aviso", r.stderr.strip() == "",
          r.stderr)
    r2 = run(d, "from-epic", "docs/epics/fixture.md", "--ciclo", "2")
    t2 = [i["title"] for i in json.loads(r2.stdout)["items"]] if r2.returncode == 0 else r2.stderr
    check("outro ciclo, outra fila: só as peças do ciclo 2",
          t2 == ["O comparador de versões 2.0"], repr(t2))


def test_grava_e_reescreve(base):
    d = repo_git(base, "grava")
    ep = d / "epic.md"
    ep.write_text(EPIC_NOVO, encoding="utf-8")
    r = run(d, "write", "fx-c1", "--from-epic", "epic.md", "--ciclo", "1",
            "--quando", "2026-10-08", "--repo", ".")
    check("write --from-epic grava", r.returncode == 0, r.stderr)
    alvo = plano_de(d, "fx-c1")
    if not alvo.exists():
        check("o plano existe depois do write", False)
        return
    plan = yaml.safe_load(alvo.read_text(encoding="utf-8"))
    check("o `demonstra:` gravado é o roteiro do ciclo",
          plan.get("demonstra") == "O operador carrega o PDF e vê 3 respostas.",
          repr(plan.get("demonstra")))
    v = run(d, "validate", str(alvo))
    check("a fila gravada passa no validate", v.returncode == 0, v.stderr)
    s = run(d, "show", "fx-c1", "--repo", ".")
    check("show imprime o roteiro como `demonstra`",
          "O operador carrega o PDF e vê 3 respostas." in s.stdout, s.stdout)
    st = run(d, "start", "fx-c1", "C1-1", "--repo", ".")
    check("o primeiro item é reservável", st.returncode == 0, st.stderr)
    r = run(d, "write", "fx-c1", "--from-epic", "epic.md", "--ciclo", "1",
            "--repo", ".")
    plan = yaml.safe_load(alvo.read_text(encoding="utf-8"))
    status = {i["id"]: i["status"] for i in plan["items"]}
    check("reescrever o ciclo preserva o status que a execução gravou",
          r.returncode == 0 and status.get("C1-1") == "in_progress",
          f"{r.stderr} {status}")


def test_recusas(base):
    d = repo_git(base, "recusa")
    r = run(d, "write", "x", "--from-epic", str(EPIC_REAL), "--ciclo", "9",
            "--dry-run", "--repo", ".")
    check("ciclo que não existe é recusa (exit 2) e lista os ciclos",
          r.returncode == 2 and "não tem o ciclo 9" in r.stderr
          and "2. Conduzir" in r.stderr, r.stderr)
    r = run(d, "write", "x", "--from-epic", str(EPIC_REAL), "--dry-run",
            "--repo", ".")
    check("--from-epic sem --ciclo é recusa",
          r.returncode != 0 and "--ciclo" in r.stderr, r.stderr)
    r = run(d, "write", "x", "--items", "-", "--ciclo", "2", "--dry-run",
            "--repo", ".")
    check("--ciclo sem --from-epic é recusa",
          r.returncode != 0 and "--from-epic" in r.stderr, r.stderr)
    sem = d / "sem.md"
    sem.write_text("# Epic: sem escada\n\n## Intenção\n\nnada\n", encoding="utf-8")
    r = run(d, "from-epic", str(sem), "--ciclo", "1")
    check("Epic sem `## Escada de valor` é recusa",
          r.returncode == 2 and "Escada de valor" in r.stderr, r.stderr)
    vazio = d / "vazio.md"
    vazio.write_text(EPIC_NOVO.replace("O comparador de versões 2.0.", "—"),
                     encoding="utf-8")
    r = run(d, "from-epic", str(vazio), "--ciclo", "2")
    check("ciclo com \"O que atravessa\" vazio é recusa",
          r.returncode == 2 and "O que atravessa" in r.stderr, r.stderr)
    sem_roteiro = d / "semroteiro.md"
    sem_roteiro.write_text(EPIC_NOVO.replace(
        "O operador vê a diferença entre duas versões.", "—"), encoding="utf-8")
    r = run(d, "from-epic", str(sem_roteiro), "--ciclo", "2")
    check("ciclo sem roteiro é recusa",
          r.returncode == 2 and "roteiro" in r.stderr, r.stderr)
    check("nada foi gravado nas recusas", not (d / ".claude").exists())


def test_avisos_e_recusas_de_epic_malformado(base):
    d = repo_git(base, "malformado")

    aberta = d / "aberta.md"
    aberta.write_text(EPIC_NOVO.replace("- [x] alguma? não",
                                        "- [ ] quem aprova?"), encoding="utf-8")
    r = run(d, "from-epic", str(aberta), "--ciclo", "1")
    check("pergunta `- [ ]` em Epic pronto vira aviso, e a fila sai",
          r.returncode == 0 and "1 pergunta(s) ainda em aberto" in r.stderr,
          r.stderr)

    for coluna, cabecalho in (("O que atravessa", "O que atravessa"),
                              ("Roteiro de demonstração", "Roteiro de demonstração (o que o dono vê)")):
        sem = d / f"sem-{coluna[:7].replace(' ', '')}.md"
        sem.write_text(EPIC_NOVO.replace(f"| {cabecalho} |", "| Outra |"),
                       encoding="utf-8")
        r = run(d, "from-epic", str(sem), "--ciclo", "1")
        check(f"escada sem a coluna \"{coluna}\" é recusa que a nomeia",
              r.returncode == 2 and "não tem a(s) coluna(s)" in r.stderr
              and coluna in r.stderr, r.stderr)

    sem_tabela = d / "semtabela.md"
    sem_tabela.write_text("# Epic: x\n\n## Escada de valor\n\nainda não escrita\n"
                          "\n## Invariantes\n\n- y\n", encoding="utf-8")
    r = run(d, "from-epic", str(sem_tabela), "--ciclo", "1")
    check("escada sem tabela é recusa",
          r.returncode == 2 and "não tem tabela" in r.stderr, r.stderr)

    r = run(d, "from-epic", str(aberta))
    check("o subcomando from-epic sem --ciclo é recusa",
          r.returncode != 0 and "--ciclo" in r.stderr, r.stderr)

    # A coluna "O que atravessa" por último, sem o `|` de fechamento: o `\|`
    # no fim da linha é barra escapada da célula, não o divisor.
    ultima = d / "ultima.md"
    ultima.write_text("# Epic: x\n\n## Escada de valor\n\n"
                      "| Ciclo | Roteiro | O que atravessa\n|---|---|---\n"
                      "| 1. Um | o dono vê. | A peça a \\|\n", encoding="utf-8")
    r = run(d, "from-epic", str(ultima), "--ciclo", "1")
    t = [i["title"] for i in json.loads(r.stdout)["items"]] if r.returncode == 0 else r.stderr
    check("`\\|` no fim da última célula é texto, não divisor",
          t == ["A peça a |"], repr(t))


def test_contrato_de_prosa():
    f = CMD.read_text(encoding="utf-8")
    check("plan.md manda a leitura do Epic passar pelo `from-epic`",
          "cepa-plan from-epic" in f)
    check("plan.md declara --from-epic e --ciclo no argument-hint",
          "--from-epic docs/epics/<nome>.md --ciclo N" in f.split("\n---", 1)[0])


def main():
    with tempfile.TemporaryDirectory() as base:
        test_epic_real_ciclo_2(base)
        test_formato_do_epic_command(base)
        test_grava_e_reescreve(base)
        test_recusas(base)
        test_avisos_e_recusas_de_epic_malformado(base)
    test_contrato_de_prosa()
    if FAILURES:
        print(f"\n{len(FAILURES)} falha(s)")
        return 1
    print("\ntudo ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
