#!/usr/bin/env python3
"""Testes estruturais da suíte de tarefas douradas (P1-4, revisão 2026-08-17).

Sem dependências — rode com `python3 tests/test_eval_suite.py`.

Estes casos são **baratos**: leem os manifestos e o executor, sem criar worktree
nem gastar modelo. Eles NÃO substituem `python3 tests/eval/run-eval.py
--validate`, que é a prova de que cada tarefa exige trabalho real — essa custa
cerca de um minuto e roda sob demanda, não a cada suíte.

O que está travado aqui:

  - todo manifesto declara os campos sem os quais a medição não existe;
  - `base_commit` e `fix_commit` são commits reais E diferentes (iguais = a
    tarefa nasce verde, que é a autoilusão que a suíte inteira existe para
    evitar);
  - o teste de aceitação existe no `fix_commit` e NÃO existe no `base_commit`
    — se existisse nos dois, o agente poderia estar sendo medido contra um
    teste que já estava lá;
  - o enunciado não entrega a solução;
  - a suíte tem dificuldade variada — só-difícil e só-fácil medem igualmente
    pouco.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVAL = REPO / "tests" / "eval"
sys.path.insert(0, str(EVAL))

FAILURES = []


def check(label, cond, detail=""):
    if cond:
        print(f"  ok  {label}")
    else:
        FAILURES.append(f"{label}{' — ' + detail if detail else ''}")
        print(f"  FAIL {label}{' — ' + detail if detail else ''}")


def load_runner():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader("run_eval", str(EVAL / "run-eval.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def git(*args):
    return subprocess.run(["git", *args], cwd=str(REPO), capture_output=True, text=True)


def test_parser_le_bloco_multilinha():
    """O enunciado é um bloco `|`; lido errado, a tarefa mede outra coisa."""
    m = load_runner()
    d = m.parse_task_yaml(
        'id: x\ntitulo: "com espaço"\nprompt: |\n  linha um\n  linha dois\n'
        'dificuldade: alta\n'
    )
    check("parser lê escalar", d.get("id") == "x")
    check("parser tira aspas do escalar", d.get("titulo") == "com espaço")
    check("parser lê bloco multilinha inteiro",
          d.get("prompt") == "linha um\nlinha dois", repr(d.get("prompt")))
    check("parser volta a ler escalar depois do bloco", d.get("dificuldade") == "alta")


def test_manifestos_completos():
    m = load_runner()
    tasks = m.load_tasks()
    check("há tarefas declaradas", len(tasks) >= 3, f"{len(tasks)}")
    for t in tasks:
        tid = t["id"]
        for field in ("titulo", "fix_commit", "base_commit", "acceptance_test",
                      "acceptance_cmd", "prompt", "dificuldade"):
            check(f"{tid}: campo {field}", bool(t.get(field)))


def test_commits_reais_e_distintos():
    m = load_runner()
    for t in m.load_tasks():
        tid = t["id"]
        for field in ("base_commit", "fix_commit"):
            r = git("cat-file", "-t", t[field])
            check(f"{tid}: {field} é um commit real",
                  r.returncode == 0 and r.stdout.strip() == "commit", r.stderr.strip()[:80])
        base = git("rev-parse", t["base_commit"]).stdout.strip()
        fix = git("rev-parse", t["fix_commit"]).stdout.strip()
        check(f"{tid}: base ≠ fix (senão a tarefa nasce verde)", base != fix)
        # o conserto tem de descender da base, senão o teste não se aplica
        r = git("merge-base", "--is-ancestor", t["base_commit"], t["fix_commit"])
        check(f"{tid}: base é ancestral do conserto", r.returncode == 0)


def test_aceitacao_so_existe_depois_do_conserto():
    """Se o teste já estivesse na base, ele não mediria o trabalho do agente."""
    m = load_runner()
    for t in m.load_tasks():
        tid, path = t["id"], t["acceptance_test"]
        r_fix = git("cat-file", "-e", f"{t['fix_commit']}:{path}")
        check(f"{tid}: aceitação existe no fix_commit", r_fix.returncode == 0, path)
        r_base = git("cat-file", "-e", f"{t['base_commit']}:{path}")
        check(f"{tid}: aceitação NÃO existe no base_commit", r_base.returncode != 0,
              f"{path} já estava lá — o agente seria medido contra um teste preexistente")


def test_enunciado_nao_entrega_a_solucao():
    """O ENUNCIADO descreve o problema; quem nomeia arquivo é o contrato.

    A separação nasceu da primeira corrida de verdade, que deu 0/3. A causa não
    era dificuldade: os testes de aceitação exigem o caminho e o nome exatos do
    arquivo do conserto original, e os enunciados — de propósito — não diziam
    nada disso. A suíte estava medindo a capacidade de ADIVINHAR o desenho
    original, não a de resolver o problema, e nenhum agente passaria.

    Então o manifesto tem dois campos com papéis opostos, e este caso guarda os
    dois lados: o `prompt` segue proibido de nomear os arquivos do conserto
    (senão vira transcrição), e o `contrato` é obrigado a nomeá-los (senão vira
    adivinhação).
    """
    m = load_runner()
    for t in m.load_tasks():
        tid = t["id"]
        r = git("show", "--name-only", "--diff-filter=A", "--format=", t["fix_commit"])
        created = [f for f in r.stdout.split() if f.endswith(".py")
                   and not f.startswith("tests/")]
        leaked = [f for f in created if Path(f).name in t["prompt"]]
        check(f"{tid}: o enunciado não nomeia os arquivos criados pelo conserto",
              not leaked, f"vazou: {leaked}")
        check(f"{tid}: o enunciado descreve o problema (tem tamanho de enunciado)",
              len(t["prompt"]) > 400, f"{len(t['prompt'])} chars")
        # o contrato tem de nomear o arquivo que a aceitação vai procurar
        alvo = Path(t["acceptance_test"]).name
        check(f"{tid}: o contrato nomeia o teste que julga o trabalho",
              alvo in t["contrato"], f"{alvo} ausente do contrato")
        check(f"{tid}: o contrato entra no que o agente recebe",
              "COMO O SEU TRABALHO SERÁ CONFERIDO" in m.build_prompt(t))


def test_dificuldade_variada():
    m = load_runner()
    niveis = {t.get("dificuldade") for t in m.load_tasks()}
    check("a suíte tem dificuldade variada (não só fácil, não só difícil)",
          len(niveis) >= 2, f"níveis: {sorted(niveis)}")


def test_validate_e_obrigatorio_no_readme():
    """A trava contra tarefa vazia precisa estar documentada, não só existir."""
    readme = (EVAL / "README.md").read_text(encoding="utf-8")
    check("README explica o --validate", "--validate" in readme)
    check("README declara o estado real da suíte (rodou? tem A/B?)",
          re.search(r"não re-rodada|nunca rodada", readme, re.I) is not None)
    check("README registra o achado da 1ª corrida (0/3 mediu a própria suíte)",
          "0/3" in readme and "contrato" in readme.lower())


def main():
    test_parser_le_bloco_multilinha()
    test_manifestos_completos()
    test_commits_reais_e_distintos()
    test_aceitacao_so_existe_depois_do_conserto()
    test_enunciado_nao_entrega_a_solucao()
    test_dificuldade_variada()
    test_validate_e_obrigatorio_no_readme()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} falha(s):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("all green")
    print("\nLembrete: isto é o barato. A prova de que cada tarefa exige trabalho "
          "real é `python3 tests/eval/run-eval.py --validate`.")


if __name__ == "__main__":
    main()
