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
    route and the next plan item (loss 2);
  - /common:next answers on demand (loss 3), lives in common because a plan does
    not require a tracker, names ONE step, and never infers `done` from a commit;
  - the canonical doc is docs/execution-plan.md — the mechanism belongs to the
    plan, not to the tracker plugin — and docs/board-flow.md stayed a pointer.
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
    """Arquivo ausente devolve vazio em vez de estourar.

    Um arquivo sumido tem de derrubar as asserções QUE FALAM DELE, não abortar
    a suíte no meio — senão a primeira remoção esconde todas as regressões
    seguintes (foi o que a perturbação pegou, duas vezes)."""
    return p.read_text(encoding="utf-8") if p.exists() else ""


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
          "<programs>/<project_key>/plan.yaml" in triage
          and "mode: single-track" in triage)
    # `<programs>` resolve para o clone principal, nunca para a worktree — a
    # regra e o guard mecânico moram em tests/test_plan_anchor_root.py.
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

    # ── /common:next: a pergunta respondida sob demanda (loss 3) ────────
    nxt_path = REPO / "common" / "commands" / "next.md"
    check("/common:next existe (mora em common — plano não exige tracker)",
          nxt_path.exists())
    nxt = read(nxt_path)

    check("next lê o plano single-track",
          "plan.yaml" in nxt and "single-track" in nxt)
    check("next separa os DOIS tipos de próximo",
          "pending human action" in nxt.lower() or "ação humana" in nxt.lower())
    check("next trata o plano como hipótese, não contrato",
          "The plan is a hypothesis, not a contract" in nxt)
    check("next declara divergência em vez de absorvê-la",
          "Divergences are stated, never absorbed" in nxt)
    check("next nomeia UM passo, não um menu",
          "Exactly one recommendation" in nxt)
    check("next não inventa ordem sem plano",
          "Never invents an order" in nxt and "/board-flow:triage" in nxt)
    check("next é read-only sem --sync",
          "Read-only unless `--sync`" in nxt)
    check("next recusa plano de ondas (é do maestro)",
          "parallel-waves" in nxt and "/maestro:run" in nxt)
    # só o humano fecha a dívida — senão a lista vira decoração
    check("só o usuário fecha um human_pending",
          "only the user clears it" in nxt)
    check("o schema registra que fechar = null, e só o humano fecha",
          "Só o humano fecha" in schema_txt)

    # registrado onde o usuário encontra
    check("next está na tabela de comandos",
          "/common:next" in read(REPO / "docs" / "commands.md"))
    # o doc canônico é o do mecanismo (common), não o do plugin de tracker —
    # o board-flow.md guarda ponteiro + a metade que é dele, sem duplicar
    doc = read(REPO / "docs" / "execution-plan.md")
    check("existe doc canônico do mecanismo", bool(doc))
    check("o doc nomeia as 3 perdas", doc.count("three distinct losses") == 1)
    check("o doc registra que tracker é opcional",
          "A tracker is optional" in doc)
    check("o doc separa single-track de parallel-waves",
          "single-track" in doc and "parallel-waves" in doc)
    bf = read(REPO / "docs" / "board-flow.md")
    check("board-flow.md aponta para o doc canônico",
          "execution-plan.md" in bf)
    check("board-flow.md não reintroduziu uma cópia do schema do plano",
          "human_pending: null" not in bf,
          "o doc do plugin voltou a duplicar o schema — front-door rival")
    check("next está no índice do README",
          "docs/execution-plan.md" in read(REPO / "README.md"))
    check("next está registrado no manifest do common",
          "/next (answers" in read(REPO / "common" / ".claude-plugin" / "plugin.json"))
    check("board-flow não reivindica mais o next",
          "advance, next" not in read(REPO / "board-flow" / ".claude-plugin" / "plugin.json"))

    # o furo que o dono achou: um repo sem Jira (como o cepa) tem de conseguir usar
    # a frase "A tracker is optional" aparece 2x (Purpose e Constraints) — casar
    # a solta deixaria a asserção passar com uma das duas removida, que foi o que
    # a perturbação pegou. Cada uma é ancorada no seu contexto.
    check("next declara no Purpose que tracker é opcional",
          "**A tracker is optional.** The plan is a file" in nxt)
    check("a constraint reafirma tracker opcional, plano não",
          "A tracker is optional; a plan is not." in nxt)
    check("sem tracker, o status é declaradamente auto-declarado",
          "self-reported" in nxt)
    check("next não infere `done` de commit (escada de confiança)",
          "never that an item is *done*" in nxt)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {FAILURES}")
        return 1
    print("all green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
