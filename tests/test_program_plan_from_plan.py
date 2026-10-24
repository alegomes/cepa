#!/usr/bin/env python3
"""Tests of stage 4 of "one writer, three sources": /maestro:program-plan --from-plan.

Run with `python3 tests/test_program_plan_from_plan.py` (only needs PyYAML).
Two families, as in test_common_plan.py and test_common_drain_plan.py:

  - BEHAVIOR of `common/bin/cepa-plan promote` — which queue items can become a
    wave slice, which CANNOT and why, and the wave floor that `blocked_by`
    imposes. Each refusal here exists because the corresponding failure costs an entire
    wave: forking on top of a reserved item duplicates work, forking two
    dependent demands in the same wave makes the lower one be born without what it consumes,
    and promoting a 2-item queue pays fork, gatekeeper and merge train for what
    a serial session solves.
  - PROSE CONTRACT of `maestro/commands/program-plan.md`. The command is
    `interaction: conversational` — an agent follows the prose, there is no function to
    call — so the only possible guard over the instruction is mechanical. Each
    `check()` embeds the `[from-plan:id]` of the block it covers, for
    `common/bin/cepa-promptcov` to cross the two sets (docs/promptcov.md).

What these tests do NOT prove: that an agent grouped the waves well in a real
session. That is conversation, and only a run tells.
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


def repo_git(base, name):
    d = Path(base) / name
    d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    return d


def item(ident, **kw):
    base = {"id": ident, "title": f"item {ident}", "why": f"porque {ident}",
            "status": "pending", "blocked_by": [], "human_pending": None}
    base.update(kw)
    return base


def write_queue(d, items, name="fila"):
    """Writes the queue through the writer itself, so the test does not fabricate YAML."""
    p = d / "itens.json"
    p.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    r = run(d, "write", name, "--items", str(p), "--source", "teste",
            "--quando", "2026-08-25", "--repo", ".")
    assert r.returncode == 0, r.stderr
    return d / ".claude" / "queues" / name / "queue.yaml"


def promote(d, name="fila", *extra):
    r = run(d, "promote", name, "--json", "--repo", ".", *extra)
    output = None
    if r.stdout.strip():
        try:
            output = json.loads(r.stdout)
        except json.JSONDecodeError:
            output = None
    return r, output


def four(**kw):
    """A queue that passes the D7 floor, so the floor does not mask the tested case."""
    return [item("A", **kw), item("B"), item("C"), item("D")]


def ids(demands):
    return [d["id"] for d in demands]


def outside_of(output, ident):
    for f in output["excluded"]:
        if f["id"] == ident:
            return f
    return None


def behavior_tests(base):
    # ── who becomes a demand ─────────────────────────────────────────────────
    d = repo_git(base, "status")
    write_queue(d, [item("A"), item("B", status="done"),
                     item("C", status="in_progress"), item("D", status="blocked"),
                     item("E", status="dropped"), item("F"), item("G"), item("H")])
    r, s = promote(d)
    check("promote: só `pending` vira demanda", r.returncode == 0 and
          ids(s["demands"]) == ["A", "F", "G", "H"], r.stderr + str(r.stdout[:200]))
    check("promote: `in_progress` fica de fora por estar reservado",
          "reservado" in (outside_of(s, "C") or {}).get("motivo", ""))
    check("promote: `blocked` fica de fora nomeando o run anterior",
          "run anterior" in (outside_of(s, "D") or {}).get("motivo", ""))
    check("promote: `done` e `dropped` ficam de fora com motivo",
          (outside_of(s, "B") or {}).get("motivo") and (outside_of(s, "E") or {}).get("motivo"))

    # ── the queue order is the data; promote does not reorder ────────────────
    d = repo_git(base, "ordem")
    write_queue(d, [item("Z"), item("Y"), item("X"), item("W")])
    r, s = promote(d)
    check("promote: preserva a ordem da fila", ids(s["demands"]) == ["Z", "Y", "X", "W"])

    # ── onda_minima: the floor that blocked_by imposes ───────────────────────
    d = repo_git(base, "ondas")
    write_queue(d, [item("A"), item("B", blocked_by=["A"]),
                     item("C", blocked_by=["B"]), item("D")])
    r, s = promote(d)
    floor = {x["id"]: x["onda_minima"] for x in s["demands"]}
    check("promote: item sem dependência tem onda_minima 1",
          floor["A"] == 1 and floor["D"] == 1, str(floor))
    check("promote: item que depende de outro da promoção sobe de onda",
          floor["B"] == 2, str(floor))
    check("promote: dependência encadeada empilha as ondas",
          floor["C"] == 3, str(floor))
    check("promote: depends_on só lista bloqueador que está na promoção",
          [x for x in s["demands"] if x["id"] == "B"][0]["depends_on"] == ["A"])
    check("promote: `ondas_minimas` resume quantas ondas a dependência exige",
          s["ondas_minimas"] == 3, str(s.get("ondas_minimas")))

    # blocked_by pointing to a LATER item in the queue (the order is of execution,
    # not topological) — a single pass would resolve wrongly.
    d = repo_git(base, "pra-frente")
    write_queue(d, [item("A", blocked_by=["B"]), item("B"), item("C"), item("D")])
    r, s = promote(d)
    floor = {x["id"]: x["onda_minima"] for x in s["demands"]}
    check("promote: dependência que aponta para frente na fila também sobe a onda",
          floor["A"] == 2 and floor["B"] == 1, str(floor))

    # INVERTED queue: the file order is the opposite of the dependency order
    # (D depends on C, C on B, B on A, and A is the last item). Without a fixed point, a
    # single pass would resolve the floors wrongly — in the two cases above the file
    # order coincides, by chance, with the order in which the dependency must be
    # resolved, so they do not distinguish one implementation from the other. Finding of the
    # proof-reviewer on 2026-08-25.
    d = repo_git(base, "invertida")
    write_queue(d, [item("D", blocked_by=["C"]), item("C", blocked_by=["B"]),
                     item("B", blocked_by=["A"]), item("A")])
    r, s = promote(d)
    floor = {x["id"]: x["onda_minima"] for x in s["demands"]}
    check("promote: fila com a ordem inversa da dependência empilha as ondas igual",
          floor == {"A": 1, "B": 2, "C": 3, "D": 4}, str(floor))

    # ── blocker that is not a candidate ──────────────────────────────────────
    d = repo_git(base, "bloq-done")
    write_queue(d, [item("A", status="done"), item("B", blocked_by=["A"]),
                     item("C"), item("D"), item("E")])
    r, s = promote(d)
    floor = {x["id"]: x["onda_minima"] for x in s["demands"]}
    check("promote: bloqueador `done` não segura ninguém",
          "B" in floor and floor["B"] == 1, str(floor))

    d = repo_git(base, "bloq-dropped")
    write_queue(d, [item("A", status="dropped"), item("B", blocked_by=["A"]),
                     item("C"), item("D"), item("E")])
    r, s = promote(d)
    check("promote: bloqueador `dropped` sai do campo mas vira AVISO",
          "B" in ids(s["demands"]) and any("dropped" in a for a in s["warnings"]),
          str(s["warnings"]))
    check("promote: o aviso de bloqueador `dropped` não repete a cada passada",
          len(s["warnings"]) == len(set(s["warnings"])), str(s["warnings"]))

    d = repo_git(base, "bloq-aberto")
    write_queue(d, [item("A", status="in_progress"), item("B", blocked_by=["A"]),
                     item("C", blocked_by=["B"]), item("D"), item("E"), item("F")])
    r, s = promote(d)
    check("promote: item cujo bloqueador segue aberto e fora da promoção sai junto",
          "B" not in ids(s["demands"]) and "depende de A" in
          (outside_of(s, "B") or {}).get("motivo", ""), str(outside_of(s, "B")))
    check("promote: a exclusão cascateia para quem dependia do excluído",
          "C" not in ids(s["demands"]) and "depende de B" in
          (outside_of(s, "C") or {}).get("motivo", ""), str(outside_of(s, "C")))
    check("promote: o resto da fila sobrevive à cascata",
          ids(s["demands"]) == ["D", "E", "F"], str(ids(s["demands"])))

    # ── open human_pending becomes an open gate, not silence ─────────────────
    d = repo_git(base, "gate")
    write_queue(d, four(human_pending="abrir /admin e conferir\na recusa"))
    r, s = promote(d)
    gate = [x for x in s["demands"] if x["id"] == "A"][0]["human_gate"]
    check("promote: `human_pending` aberto vira human_gate `open:`",
          gate.startswith("open: ") and "/admin" in gate, gate)
    check("promote: o gate aberto cabe em uma linha (o plano é YAML)",
          "\n" not in gate, repr(gate))
    check("promote: item sem rota humana sai com human_gate `none`",
          [x for x in s["demands"] if x["id"] == "B"][0]["human_gate"] == "none")

    # ── D7 floor ─────────────────────────────────────────────────────────────
    d = repo_git(base, "piso")
    write_queue(d, [item("A"), item("B"), item("C")])
    r, s = promote(d)
    check("promote: 3 demandas não atingem o piso D7 (exit 4)", r.returncode == 4,
          f"exit={r.returncode}")
    check("promote: o piso recomenda o /common:drain-plan, que roda a mesma fila",
          "drain-plan" in r.stderr, r.stderr)
    check("promote: mesmo abaixo do piso, o JSON sai (o comando precisa reportar)",
          s is not None and s["floor"] == {"minimo": 4, "demandas": 3,
                                           "atingido": False}, str(s and s.get("floor")))
    d = repo_git(base, "piso-ok")
    write_queue(d, four())
    r, s = promote(d)
    check("promote: 4 demandas atingem o piso (exit 0)", r.returncode == 0,
          f"exit={r.returncode} {r.stderr}")

    # queue with only a closed item: zero demands, and the reason is stated
    d = repo_git(base, "vazia")
    write_queue(d, [item("A", status="done"), item("B", status="done")])
    r, s = promote(d)
    check("promote: fila sem nenhum `pending` para de vez, dizendo isso",
          r.returncode == 4 and "nenhum item `pending`" in r.stderr, r.stderr)

    # ── refusals ─────────────────────────────────────────────────────────────
    d = repo_git(base, "ondas-plan")
    target = d / ".claude" / "programs" / "w" / "plan.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(yaml.dump({"schema_version": 2, "mode": "parallel-waves",
                               "program": "w", "waves": [], "slices": {}}),
                    encoding="utf-8")
    r, _ = promote(d, "w")
    check("promote: recusa um plano de ondas (exit 3) — ondas não viram ondas",
          r.returncode == 3 and "ondas não se promovem" in r.stderr, r.stderr)

    r, _ = promote(d, "nao-existe")
    check("promote: fila inexistente sai 2 apontando quem escreve (/common:queue)",
          r.returncode == 2 and "/common:queue" in r.stderr, r.stderr)

    d = repo_git(base, "invalida")
    target = d / ".claude" / "programs" / "f" / "plan.yaml"
    target.parent.mkdir(parents=True)
    target.write_text(yaml.dump({
        "schema_version": 2, "mode": "single-track", "program": "f",
        "items": [{"id": "A", "title": "t", "why": "", "status": "pending",
                   "blocked_by": [], "human_pending": None}]}), encoding="utf-8")
    r, _ = promote(d, "f")
    check("promote: recusa promover fila inválida (`why` vazio) — exit 2",
          r.returncode == 2 and "why" in r.stderr, r.stderr)

    # ── tracing and pure reading ─────────────────────────────────────────────
    d = repo_git(base, "fonte")
    plan = write_queue(d, four(status="done"))
    before = plan.read_bytes()
    r, s = promote(d, "fila", "--quando", "2026-08-25")
    check("promote: `source` diz de qual fila, de qual caminho e quantos itens",
          "single-track 'fila'" in s["source"] and str(plan) in s["source"]
          and "3 de 4" in s["source"] and "2026-08-25" in s["source"], s["source"])
    check("promote: `source` carrega a fonte da própria fila (o fio até a origem)",
          "teste" in s["source"], s["source"])
    check("[from-plan:queue-untouched] promote não escreve na fila",
          plan.read_bytes() == before)


def prose_tests():
    if not CMD.is_file():
        check("program-plan.md existe", False, str(CMD))
        return
    text = CMD.read_text(encoding="utf-8")
    lines = text.splitlines()

    check("--from-plan está no argument-hint", "--from-plan" in lines[2])
    check("--from-plan está na descrição do comando", "--from-plan" in lines[1])
    check("[from-plan:source] a fonte é a fila, lida pelo cepa-plan promote",
          "cepa-plan promote" in text)
    check("[from-plan:source] o piso D7 é o exit 4, e a saída é o /common:drain-plan",
          "**exit 4 = stop**" in text and "/common:drain-plan" in text)
    check("[from-plan:source] mostra ao usuário o que ficou de fora",
          "excluded[]" in text)
    check("[from-plan:carry-why] o `why` da fila é copiado, nunca reescrito",
          "COPIED, never rewritten" in text)
    check("[from-plan:human-gate] rota humana aberta é decidida agora ou fica fora da onda",
          "human_gate" in text and "the slice stays out of the wave" in text)
    check("[from-plan:deps-to-waves] onda_minima é piso, não sugestão",
          "onda_minima" in text and "a FLOOR, not a suggestion" in text)
    check("[from-plan:deps-to-waves] onda N forka depois da N-1",
          'fork_after: "wave-<N-1>"' in text)
    check("[from-plan:other-name] o plano de ondas precisa de nome próprio, escolhido pelo usuário",
          "OF ITS OWN" in text and "do not invent a suffix on your own" in text)
    check("[from-plan:traceable-source] o `source` do plano vem do promote",
          "is born orphaned" in text)
    check("[from-plan:queue-untouched] promover não mexe na fila, e o dobro de executores é dito",
          "the items remain `pending`" in text and "builds it twice" in text)


def main():
    with tempfile.TemporaryDirectory() as base:
        behavior_tests(base)
    prose_tests()
    print()
    if FAILURES:
        print(f"✗ {len(FAILURES)} falha(s): " + ", ".join(FAILURES))
        return 1
    print("✓ todos os casos passaram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
