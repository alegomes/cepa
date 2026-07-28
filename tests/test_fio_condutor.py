#!/usr/bin/env python3
"""Contract tests for the "fio condutor" pieces (BACKLOG, 2026-07-28).

No third-party deps beyond PyYAML — run with `python3 tests/test_fio_condutor.py`.

The pain: after hours of execution with detours, the owner could not answer
"what do I do next?". Three distinct losses presented as one feeling:
  1. the execution order did not survive the session that produced it;
  2. the end of a card pointed nowhere ("validate by hand" vs "pull the next");
  3. a long session dissolved the thread.

These are prompt contracts, so the guard has to be mechanical — prose that says
"the command should also write the plan" is exactly what erodes silently.

Guards:
  - the plan schema is CANONICAL in common/ and documents both modes, and
    maestro/plan-template.yaml stayed a pointer (no rival front-door);
  - the single-track mode still carries the three fields that encode the losses
    (`why`, `human_pending`, ordered `items`);
  - /board-flow:triage persists the ordered plan (loss 1);
  - execute/fix/prove close by pointing forward, surfacing the Human validation
    route and the next plan item (loss 2).
"""

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("✗ precisa de PyYAML (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

REPO = Path(__file__).resolve().parent.parent
SCHEMA = REPO / "common" / "plan-schema.yaml"
POINTER = REPO / "maestro" / "plan-template.yaml"

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ok  {name}")
    else:
        print(f"FAIL  {name}  {detail}")
        FAILURES.append(name)


def read(p):
    return p.read_text(encoding="utf-8")


def main():
    # ── schema canônico ─────────────────────────────────────────────────────
    schema_txt = read(SCHEMA)
    check("common/plan-schema.yaml existe", SCHEMA.exists())
    check("schema documenta os dois modos",
          "single-track" in schema_txt and "parallel-waves" in schema_txt)

    # O bloco single-track é YAML vivo (o parallel-waves fica comentado como
    # exemplo), então tem de parsear e trazer os campos que carregam a dor.
    plan = yaml.safe_load(schema_txt)
    check("schema canônico está em v2 (mode explícito)",
          plan.get("schema_version") == 2, repr(plan.get("schema_version")))
    check("v1 segue documentada como legado lido sem migração",
          "1 — legado" in schema_txt and "sem migração" in schema_txt)
    check("modo do exemplo vivo é single-track",
          plan.get("mode") == "single-track", repr(plan.get("mode")))

    items = plan.get("items") or []
    check("single-track traz items ordenados", len(items) >= 2, f"{len(items)} item(s)")
    for field, perda in (("why", "loss 1: a ordem sem critério"),
                         ("human_pending", "loss 2: o que sobrou pro humano"),
                         ("status", "estado por item"),
                         ("blocked_by", "o topo da fila pode estar bloqueado")):
        check(f"item declara `{field}` ({perda})",
              all(field in it for it in items),
              f"faltando em {[it.get('id') for it in items if field not in it]}")

    # ── sem front-door rival ────────────────────────────────────────────────
    pointer_txt = read(POINTER)
    check("maestro/plan-template.yaml aponta para o canônico",
          "common/plan-schema.yaml" in pointer_txt)
    check("o ponteiro não reintroduziu uma cópia do schema",
          "slices:" not in pointer_txt and "items:" not in pointer_txt,
          "o template voltou a duplicar o schema — front-door rival")

    # ── produtor: triage persiste ordem + porquê (loss 1) ───────────────────
    triage = read(REPO / "board-flow" / "commands" / "triage.md")
    check("triage persiste o plano single-track",
          ".claude/programs/<project_key>/plan.yaml" in triage
          and "mode: single-track" in triage)
    check("triage propõe a fila To Do em ORDEM",
          "in execution order" in triage)
    check("triage exige o `why` por item",
          "why" in triage and "re-priorisation from scratch" in triage)
    check("triage funde em vez de sobrescrever (não apaga human_pending)",
          "Merge, never overwrite" in triage)

    # ── fechamento que aponta adiante (loss 2) ──────────────────────────────
    for cmd in ("execute", "fix", "prove"):
        txt = read(REPO / "board-flow" / "commands" / f"{cmd}.md")
        check(f"{cmd}: fecha com \"And now?\"", '"And now?"' in txt)
        check(f"{cmd}: entrega a Human validation route ao humano",
              "Human validation route" in txt and "Left for you" in txt)
        check(f"{cmd}: aponta o próximo item do plano",
              "Next in the plan" in txt
              and "plan.yaml" in txt)
        check(f"{cmd}: sem plano, não inventa ordem",
              "/board-flow:triage" in txt)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
