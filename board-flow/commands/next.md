---
description: Responde "e agora, o que eu faço?" a qualquer momento — lê o plano de execução single-track (.claude/programs/<project_key>/plan.yaml), reconcilia contra o estado vivo do board e nomeia UM próximo passo com o porquê. Distingue os dois tipos de próximo que se confundem em silêncio: ação humana pendente (validar à mão, aprovar PR, rotacionar segredo) e próximo card. Read-only por default; --sync grava a reconciliação no plano.
argument-hint: [--plan NOME] [--offline] [--sync]
---

# /board-flow:next

## Purpose

Answer the literal question — *what do I do next?* — at any moment, not only
when a card happens to close.

`/board-flow:triage` writes the order down and `execute`/`fix`/`prove` point
forward when a card ends. Neither helps in the middle of a long session, which
is where the thread actually dissolves: three rounds of proof gate, four cards
opened, two scope decisions, and the original objective is buried under the
trail of how you got here. `/common:recap` reconstructs what **was done**;
nothing reconstructs what is **left to do**.

Two different questions hide inside "what next", and they compete in silence:

- **What is pending on ME** — validate a fix by hand, approve a PR, rotate a
  secret, cut a release. Nobody else can do it, and it accumulates invisibly.
- **What is the next card** — the next unblocked item of the plan.

This command separates them, then names **one** recommended step.

## Variables

- `--plan NOME` — plan to read. Default: `.claude/programs/<project_key>/plan.yaml`,
  with `project_key` from `board-flow.yaml`.
- `--offline` — skip the Jira round-trip; answer from the plan file alone. Use
  when you want an instant answer or have no board access. Say in the report
  that the answer was not reconciled against the board.
- `--sync` — write the reconciliation back into the plan (step 4). Without it
  the command is 100% read-only and only *reports* the divergences.

## Workflow

### 1. Locate the plan

Read `board-flow.yaml` at project root for `defaults.project_key` (else legacy
`.claude/board-flow.lifecycle.yaml`). Resolve the plan path.

**No plan file.** Don't guess an order from the board's default sort — an order
nobody chose is worse than an admitted absence, because it reads as a decision.
Report: no execution plan for this board, the queue exists in Jira but its order
and rationale don't; run `/board-flow:triage` to create one. Then, as a
courtesy, list the `to_do` cards **as an unordered set**, labelled as such.

**No `board-flow.yaml`.** Say the repo isn't wired to a board and stop — this
command reads a board's plan; it isn't a generic to-do list.

### 2. Read the plan

Parse it (schema `common/plan-schema.yaml`). Refuse `mode: parallel-waves`:
that's a maestro program — point at `/maestro:run`, don't try to linearise it.

Collect, in plan order:

- **open human debt** — every item (any status, including `done`) whose
  `human_pending` is a real route rather than the explicit null;
- **the candidate** — the first `pending` item whose `blocked_by` contains no
  unfinished item;
- **blocked items ahead of the candidate** — each with what blocks it, so a
  stalled top-of-queue is visible instead of silently skipped.

### 3. Reconcile against the board (skip if `--offline`)

**The plan is a hypothesis, not a contract.** It records what was true when
triage ran; the board is what is true now. Delegate to `atlassian-expert`:

> Command: next
>
> Fetch the current status of these Jira issues: `<keys in the plan>`. Also list
> the keys currently in `<defaults.status_map.to_do>` for project
> `<project_key>`. Reply as a compact key → status table, verbatim, no
> interpretation.

Compare, and name every divergence — each means something happened outside this
plan, and silently absorbing it is how the plan starts lying:

| Plan says | Board says | Reading |
|---|---|---|
| `pending` | done | someone finished it elsewhere → mark `done`, and **ask what its human validation route was** — that debt is otherwise lost |
| `pending` | in progress | a live session may be on it → warn before you start it too |
| `done` | in progress / to do | it bounced back (UNPROVEN, reopened) → it is `pending` again, and probably the real next step |
| item present | card gone / Won't Do | → `dropped`, with the reason |
| — | in `to_do`, absent from plan | the plan is stale or was truncated by `--max` → **name these cards**; never fold them in silently as if they'd been prioritised |

Divergences change the answer, so reconcile **before** choosing the candidate,
not after.

### 4. Sync (only with `--sync`)

Write the reconciled statuses back to the plan. Merge, never overwrite: keep
`why` and `human_pending` on every item, keep `dropped` items with their reason.
Cards found on the board but absent from the plan are **not** appended — they
were never given a position or a rationale, and inventing one here would forge
exactly the decision this whole mechanism exists to preserve. Say they're
missing and that `/board-flow:triage` is what places them.

**Closing human debt.** A `human_pending` is cleared by setting it to `null`,
and **only the user clears it** — they are the only one who knows whether they
actually ran the route. Ask, one item at a time, naming the route verbatim
("did you open /admin/devolucoes and confirm the refusal?"). Never infer it from
a green test, a card status, or the passage of time: a list that closes itself
is decoration, and the debt goes back to being invisible — which is the exact
failure this field exists to prevent.

Without `--sync`, report the divergences and offer it.

### 5. Answer

Name **one** recommended next step, and say why it and not the other.

Default precedence, to be overridden with a stated reason:

1. **An item the board says bounced back** — work already paid for that is
   sliding backwards outranks work not yet started.
2. **Human debt that blocks the queue** — a route that must pass before the next
   card is meaningful (e.g. the next card builds on the one awaiting validation).
3. **The candidate card.**
4. **Non-blocking human debt** — real, but it can ride along; list it, don't lead
   with it.

If everything is `done` and no human debt is open, say the plan is finished and
point at `/board-flow:triage` for the next round. Do not manufacture a next step
from an empty plan.

## Report

Plain language first, protocol second — apply `conversational-response`'s
"translate jargon at the human boundary". Short; this command is read in the
middle of a session, when attention is already spent.

```
Próximo passo: WEGO-1240 — "Agregar rota de validação humana"
  porque: depende do hook estabilizado em 1958, que fechou ontem

Pendente com você (2):
  • WEGO-1958 — abrir /admin/devolucoes e confirmar que o comentário sem razão
    é recusado. Falha se salvar.
  • WEGO-1235 — nada a validar à mão (substrato interno)

Fila depois dele: WEGO-1237 (maior, por último)
Bloqueado: nenhum
⚠ 2 cards em To Do fora do plano: WEGO-1962, WEGO-1963 — sem posição nem
  porquê. /board-flow:triage é quem os coloca.
```

Rules for the report:

- **Exactly one recommendation**, with its `why` from the plan — never a menu of
  equally-weighted options. A list of possibilities is the very state the user is
  stuck in when they run this.
- **Human debt is listed even when empty** — "nothing to validate by hand" is an
  answer; silence is the ambiguity that started all this.
- **Divergences are stated, never absorbed.** If the plan and the board disagree,
  the report says so before it says what to do.
- Under `--offline`, say the answer wasn't reconciled against the board.

## Constraints

- **Read-only unless `--sync`.** No Jira write ever — this command reports, it
  doesn't transition. `atlassian-expert` is used read-only.
- **Never invents an order.** Absent a plan, or for cards outside it, the honest
  answer is "these have no position yet" plus `/board-flow:triage`.
- **Doesn't execute anything.** It names the next step; `/board-flow:execute`,
  `/fix` and `/drain` do the work.
- **Refuses a parallel-waves plan** — that's `/maestro:run`'s document.
