#!/usr/bin/env python3
"""Testes da etapa 4 de "um escritor, três fontes": /maestro:program-plan --from-plan.

Rode com `python3 tests/test_program_plan_from_plan.py` (só precisa do PyYAML).
Duas famílias, como em test_common_plan.py e test_common_drain_plan.py:

  - COMPORTAMENTO do `common/bin/cepa-plan promote` — quem da fila pode virar
    slice de onda, quem NÃO pode e por quê, e o piso de onda que o `blocked_by`
    impõe. Cada recusa aqui existe porque a falha correspondente custa uma onda
    inteira: forkar em cima de item reservado duplica trabalho, forkar duas
    demandas dependentes na mesma onda faz a de baixo nascer sem o que consome,
    e promover uma fila de 2 itens paga fork, porteiro e merge train para o que
    uma sessão em série resolve.
  - CONTRATO DE PROSA do `maestro/commands/program-plan.md`. O comando é
    `interaction: conversational` — um agente segue a prosa, não há função a
    chamar — então a única guarda possível sobre a instrução é mecânica. Cada
    `check()` embute o `[from-plan:id]` do bloco que cobre, para o
    `common/bin/cepa-promptcov` cruzar os dois conjuntos (docs/promptcov.md).

O que estes testes NÃO provam: que um agente agrupou bem as ondas numa sessão
real. Isso é conversa, e só um run diz.
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
CMD = REPO / "maestro" / "commands" / "program-plan.md"

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


def item(ident, **kw):
    base = {"id": ident, "title": f"item {ident}", "why": f"porque {ident}",
            "status": "pending", "blocked_by": [], "human_pending": None}
    base.update(kw)
    return base


def escreve_fila(d, itens, nome="fila"):
    """Grava a fila pelo próprio escritor, para o teste não fabricar YAML."""
    p = d / "itens.json"
    p.write_text(json.dumps(itens, ensure_ascii=False), encoding="utf-8")
    r = run(d, "write", nome, "--items", str(p), "--source", "teste",
            "--quando", "2026-08-25", "--repo", ".")
    assert r.returncode == 0, r.stderr
    return d / ".claude" / "programs" / nome / "plan.yaml"


def promote(d, nome="fila", *extra):
    r = run(d, "promote", nome, "--json", "--repo", ".", *extra)
    saida = None
    if r.stdout.strip():
        try:
            saida = json.loads(r.stdout)
        except json.JSONDecodeError:
            saida = None
    return r, saida


def quatro(**kw):
    """Uma fila que passa o piso D7, para o piso não mascarar o caso testado."""
    return [item("A", **kw), item("B"), item("C"), item("D")]


def ids(demandas):
    return [d["id"] for d in demandas]


def fora_de(saida, ident):
    for f in saida["excluded"]:
        if f["id"] == ident:
            return f
    return None


def testes_de_comportamento(base):
    # ── quem vira demanda ────────────────────────────────────────────────────
    d = repo_git(base, "status")
    escreve_fila(d, [item("A"), item("B", status="done"),
                     item("C", status="in_progress"), item("D", status="blocked"),
                     item("E", status="dropped"), item("F"), item("G"), item("H")])
    r, s = promote(d)
    check("promote: só `pending` vira demanda", r.returncode == 0 and
          ids(s["demands"]) == ["A", "F", "G", "H"], r.stderr + str(r.stdout[:200]))
    check("promote: `in_progress` fica de fora por estar reservado",
          "reservado" in (fora_de(s, "C") or {}).get("motivo", ""))
    check("promote: `blocked` fica de fora nomeando o run anterior",
          "run anterior" in (fora_de(s, "D") or {}).get("motivo", ""))
    check("promote: `done` e `dropped` ficam de fora com motivo",
          (fora_de(s, "B") or {}).get("motivo") and (fora_de(s, "E") or {}).get("motivo"))

    # ── a ordem da fila é o dado; promote não reordena ───────────────────────
    d = repo_git(base, "ordem")
    escreve_fila(d, [item("Z"), item("Y"), item("X"), item("W")])
    r, s = promote(d)
    check("promote: preserva a ordem da fila", ids(s["demands"]) == ["Z", "Y", "X", "W"])

    # ── onda_minima: o piso que o blocked_by impõe ───────────────────────────
    d = repo_git(base, "ondas")
    escreve_fila(d, [item("A"), item("B", blocked_by=["A"]),
                     item("C", blocked_by=["B"]), item("D")])
    r, s = promote(d)
    piso = {x["id"]: x["onda_minima"] for x in s["demands"]}
    check("promote: item sem dependência tem onda_minima 1",
          piso["A"] == 1 and piso["D"] == 1, str(piso))
    check("promote: item que depende de outro da promoção sobe de onda",
          piso["B"] == 2, str(piso))
    check("promote: dependência encadeada empilha as ondas",
          piso["C"] == 3, str(piso))
    check("promote: depends_on só lista bloqueador que está na promoção",
          [x for x in s["demands"] if x["id"] == "B"][0]["depends_on"] == ["A"])
    check("promote: `ondas_minimas` resume quantas ondas a dependência exige",
          s["ondas_minimas"] == 3, str(s.get("ondas_minimas")))

    # blocked_by apontando para item POSTERIOR na fila (a ordem é de execução,
    # não topológica) — uma passada só resolveria errado.
    d = repo_git(base, "pra-frente")
    escreve_fila(d, [item("A", blocked_by=["B"]), item("B"), item("C"), item("D")])
    r, s = promote(d)
    piso = {x["id"]: x["onda_minima"] for x in s["demands"]}
    check("promote: dependência que aponta para frente na fila também sobe a onda",
          piso["A"] == 2 and piso["B"] == 1, str(piso))

    # ── bloqueador que não é candidato ───────────────────────────────────────
    d = repo_git(base, "bloq-done")
    escreve_fila(d, [item("A", status="done"), item("B", blocked_by=["A"]),
                     item("C"), item("D"), item("E")])
    r, s = promote(d)
    piso = {x["id"]: x["onda_minima"] for x in s["demands"]}
    check("promote: bloqueador `done` não segura ninguém",
          "B" in piso and piso["B"] == 1, str(piso))

    d = repo_git(base, "bloq-dropped")
    escreve_fila(d, [item("A", status="dropped"), item("B", blocked_by=["A"]),
                     item("C"), item("D"), item("E")])
    r, s = promote(d)
    check("promote: bloqueador `dropped` sai do campo mas vira AVISO",
          "B" in ids(s["demands"]) and any("dropped" in a for a in s["warnings"]),
          str(s["warnings"]))
    check("promote: o aviso de bloqueador `dropped` não repete a cada passada",
          len(s["warnings"]) == len(set(s["warnings"])), str(s["warnings"]))

    d = repo_git(base, "bloq-aberto")
    escreve_fila(d, [item("A", status="in_progress"), item("B", blocked_by=["A"]),
                     item("C", blocked_by=["B"]), item("D"), item("E"), item("F")])
    r, s = promote(d)
    check("promote: item cujo bloqueador segue aberto e fora da promoção sai junto",
          "B" not in ids(s["demands"]) and "depende de A" in
          (fora_de(s, "B") or {}).get("motivo", ""), str(fora_de(s, "B")))
    check("promote: a exclusão cascateia para quem dependia do excluído",
          "C" not in ids(s["demands"]) and "depende de B" in
          (fora_de(s, "C") or {}).get("motivo", ""), str(fora_de(s, "C")))
    check("promote: o resto da fila sobrevive à cascata",
          ids(s["demands"]) == ["D", "E", "F"], str(ids(s["demands"])))

    # ── human_pending aberto vira gate aberto, não silêncio ──────────────────
    d = repo_git(base, "gate")
    escreve_fila(d, quatro(human_pending="abrir /admin e conferir\na recusa"))
    r, s = promote(d)
    gate = [x for x in s["demands"] if x["id"] == "A"][0]["human_gate"]
    check("promote: `human_pending` aberto vira human_gate `open:`",
          gate.startswith("open: ") and "/admin" in gate, gate)
    check("promote: o gate aberto cabe em uma linha (o plano é YAML)",
          "\n" not in gate, repr(gate))
    check("promote: item sem rota humana sai com human_gate `none`",
          [x for x in s["demands"] if x["id"] == "B"][0]["human_gate"] == "none")

    # ── piso D7 ──────────────────────────────────────────────────────────────
    d = repo_git(base, "piso")
    escreve_fila(d, [item("A"), item("B"), item("C")])
    r, s = promote(d)
    check("promote: 3 demandas não atingem o piso D7 (exit 4)", r.returncode == 4,
          f"exit={r.returncode}")
    check("promote: o piso recomenda o /common:drain-plan, que roda a mesma fila",
          "drain-plan" in r.stderr, r.stderr)
    check("promote: mesmo abaixo do piso, o JSON sai (o comando precisa reportar)",
          s is not None and s["floor"] == {"minimo": 4, "demandas": 3,
                                           "atingido": False}, str(s and s.get("floor")))
    d = repo_git(base, "piso-ok")
    escreve_fila(d, quatro())
    r, s = promote(d)
    check("promote: 4 demandas atingem o piso (exit 0)", r.returncode == 0,
          f"exit={r.returncode} {r.stderr}")

    # fila só com item fechado: zero demandas, e o motivo é dito
    d = repo_git(base, "vazia")
    escreve_fila(d, [item("A", status="done"), item("B", status="done")])
    r, s = promote(d)
    check("promote: fila sem nenhum `pending` para de vez, dizendo isso",
          r.returncode == 4 and "nenhum item `pending`" in r.stderr, r.stderr)

    # ── recusas ──────────────────────────────────────────────────────────────
    d = repo_git(base, "ondas-plan")
    alvo = d / ".claude" / "programs" / "w" / "plan.yaml"
    alvo.parent.mkdir(parents=True)
    alvo.write_text(yaml.dump({"schema_version": 2, "mode": "parallel-waves",
                               "program": "w", "waves": [], "slices": {}}),
                    encoding="utf-8")
    r, _ = promote(d, "w")
    check("promote: recusa um plano de ondas (exit 3) — ondas não viram ondas",
          r.returncode == 3 and "ondas não se promovem" in r.stderr, r.stderr)

    r, _ = promote(d, "nao-existe")
    check("promote: fila inexistente sai 2 apontando quem escreve (/common:plan)",
          r.returncode == 2 and "/common:plan" in r.stderr, r.stderr)

    d = repo_git(base, "invalida")
    alvo = d / ".claude" / "programs" / "f" / "plan.yaml"
    alvo.parent.mkdir(parents=True)
    alvo.write_text(yaml.dump({
        "schema_version": 2, "mode": "single-track", "program": "f",
        "items": [{"id": "A", "title": "t", "why": "", "status": "pending",
                   "blocked_by": [], "human_pending": None}]}), encoding="utf-8")
    r, _ = promote(d, "f")
    check("promote: recusa promover fila inválida (`why` vazio) — exit 2",
          r.returncode == 2 and "why" in r.stderr, r.stderr)

    # ── rastreio e leitura pura ──────────────────────────────────────────────
    d = repo_git(base, "fonte")
    plano = escreve_fila(d, quatro(status="done"))
    antes = plano.read_bytes()
    r, s = promote(d, "fila", "--quando", "2026-08-25")
    check("promote: `source` diz de qual fila, de qual caminho e quantos itens",
          "single-track 'fila'" in s["source"] and str(plano) in s["source"]
          and "3 de 4" in s["source"] and "2026-08-25" in s["source"], s["source"])
    check("promote: `source` carrega a fonte da própria fila (o fio até a origem)",
          "teste" in s["source"], s["source"])
    check("[from-plan:queue-untouched] promote não escreve na fila",
          plano.read_bytes() == antes)


def testes_de_prosa():
    if not CMD.is_file():
        check("program-plan.md existe", False, str(CMD))
        return
    texto = CMD.read_text(encoding="utf-8")
    linhas = texto.splitlines()

    check("--from-plan está no argument-hint", "--from-plan" in linhas[2])
    check("--from-plan está na descrição do comando", "--from-plan" in linhas[1])
    check("[from-plan:source] a fonte é a fila, lida pelo cepa-plan promote",
          "cepa-plan promote" in texto)
    check("[from-plan:source] o piso D7 é o exit 4, e a saída é o /common:drain-plan",
          "exit 4 = pare" in texto and "/common:drain-plan" in texto)
    check("[from-plan:source] mostra ao usuário o que ficou de fora",
          "excluded[]" in texto)
    check("[from-plan:carry-why] o `why` da fila é copiado, nunca reescrito",
          "COPIADO, nunca reescrito" in texto)
    check("[from-plan:human-gate] rota humana aberta é decidida agora ou fica fora da onda",
          "human_gate" in texto and "fica fora da onda" in texto)
    check("[from-plan:deps-to-waves] onda_minima é piso, não sugestão",
          "onda_minima" in texto and "PISO, não sugestão" in texto)
    check("[from-plan:deps-to-waves] onda N forka depois da N-1",
          'fork_after: "wave-<N-1>"' in texto)
    check("[from-plan:other-name] o plano de ondas precisa de nome próprio, escolhido pelo usuário",
          "nome PRÓPRIO" in texto and "não invente um sufixo" in texto)
    check("[from-plan:traceable-source] o `source` do plano vem do promote",
          "nasce órfão" in texto)
    check("[from-plan:queue-untouched] promover não mexe na fila, e o dobro de executores é dito",
          "continuam `pending`" in texto and "constrói duas vezes" in texto)


def main():
    with tempfile.TemporaryDirectory() as base:
        testes_de_comportamento(base)
    testes_de_prosa()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): " + ", ".join(FAILURES))
        return 1
    print("✓ todos os casos passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
