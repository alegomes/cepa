---
description: Responde "e agora, o que eu faço?" a qualquer momento — lê o plano de execução single-track (.claude/programs/<nome>/plan.yaml) e nomeia UM próximo passo com o porquê registrado na priorização. Distingue os dois tipos de próximo que se confundem em silêncio: ação humana pendente (validar à mão, aprovar PR, rotacionar segredo) e próximo item. Não exige Jira — com board-flow.yaml presente, reconcilia contra o board vivo; sem, responde do plano e diz que o status é auto-declarado. Read-only por default; --sync grava a reconciliação.
argument-hint: [--plan NOME] [--offline] [--sync]
interaction: routine
---

# /common:next

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
- **What is the next item** — the next unblocked item of the plan.

This command separates them, then names **one** recommended step.

**A tracker is optional.** The plan is a file, not a board projection: an item's
`id` is a card key *or* an anchor in whatever source the work comes from
(`"P9 do BACKLOG"`, an ADR, an issue number). Where a tracker exists and
`board-flow` is installed, this command reconciles against it; where it doesn't
— a repo whose demands live in `BACKLOG.md`, like this one — it answers from the
plan and says plainly that the statuses are self-reported.

## Variables

- `--plan NOME` — plan to read, i.e. `<programs>/NOME/plan.yaml` (`<programs>`
  defined in step 1 — always the main clone's, never the current worktree's).
- `--offline` — skip the tracker round-trip even when one is configured. Use for
  an instant answer or with no network. Say in the report that the answer wasn't
  reconciled.
- `--sync` — write the reconciliation back into the plan (step 4). Without it
  the command is 100% read-only and only *reports* the divergences.

## Workflow

### 1. Locate the plan

**`<programs>` = `<main-root>/.claude/programs`**, where `<main-root>` is the
parent of `git rev-parse --git-common-dir` with the trailing `/.git` removed —
inside a linked worktree that is the MAIN clone, not this tree; anywhere else it
equals `git rev-parse --show-toplevel`. Never resolve the plan against the
current directory: the plan is repo state, and a session worktree's own
`.claude/` starts empty in any repo whose `.gitignore` covers `.claude/`
(rationale in `docs/execution-plan.md`, "Where the file lives").

In order, first hit wins:

1. `--plan NOME` → `<programs>/NOME/plan.yaml`.
2. `board-flow.yaml` at project root (else legacy
   `.claude/board-flow.lifecycle.yaml`) → `defaults.project_key` →
   `<programs>/<project_key>/plan.yaml`, if it exists.
3. Exactly one `<programs>/*/plan.yaml` with `mode: single-track` → that one.
4. More than one → list them and ask which; don't pick for the user.

**Before declaring absence, look where a lost plan actually is.** A session
running in a worktree that reads only its own `.claude/` will report a plan dead
that is sitting in the main clone — that happened on 2026-08-18 and cost a
triage. Two cheap checks, in this order:

1. `ls <main-root>/.claude/programs/*/plan.yaml` — the anchoring above already
   points here, so this is a check that the resolution actually ran against
   `<main-root>` and not against the current tree.
2. `ls <main-root>/.claude/rescued/*/programs/*/plan.yaml` — artifacts the
   rescue net carried out of a removed worktree (`_wtlib.rescue_artifacts`; the
   🛟 SessionStart notice announces the folder). A hit here means a plan was
   written inside a worktree that no longer exists.

If a rescued plan turns up, **never copy it over the live one and never treat it
as the newer truth.** Read the `source:` line and the header of both, count
`items` in each, and put both counts in front of the user: a rescued file is
often a partial run (on 2026-08-18 the rescued copy held 14 items and the live
one 47, and overwriting would have been the real loss). Merging is the user's
call, and `/common:next` doesn't do it silently.

**No plan file anywhere, including those two places.** Don't manufacture an
order — an order nobody chose is worse than an admitted absence, because it reads as a decision. Say there is no
execution plan, then name the cheapest way to get one **for this repo**:

- tracker wired (`board-flow.yaml` present) → `/board-flow:triage`, which grooms
  the column and writes the plan from the cards it just classified;
- no tracker → the plan is a short file and this session can write it: offer to
  build it from the repo's own source of demands (`BACKLOG.md` or whatever the
  user names), asking for the order and the `why` per item. Write nothing until
  the user confirms the order.

Then, as a courtesy, list whatever candidates you can see (the `to_do` cards, or
the source's open items) **as an unordered set**, labelled as such.

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

### 3. Reconcile against the tracker (only if one is wired; skip if `--offline`)

**The plan is a hypothesis, not a contract.** It records what was true when it
was written; the tracker is what is true now.

**No tracker wired** (no `board-flow.yaml`, or `board-flow` not installed): skip
this step and **say so in the report** — the statuses are self-reported by the
plan, nobody verified them. That is a weaker answer than a reconciled one, and
the user is entitled to know which of the two they got. Do not substitute a
guess: git history proves a commit exists, never that an item is *done*, and
inferring `done` from a commit message is exactly the false confidence the
`done`-confidence ladder exists to prevent.

With a tracker, delegate to `atlassian-expert`:

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
name how a next round gets planned (`/board-flow:triage` with a tracker;
otherwise offer to write the next plan from the repo's source of demands). Do
not manufacture a next step from an empty plan.

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

Without a tracker the shape is the same, minus the divergence block, plus one
honest line about what wasn't checked:

```
Próximo passo: P12 — "produtor de plano sem tracker"
  porque: sem ele, um repo como este só ganha plano se alguém pedir na mão

Pendente com você (1):
  • P9 — rodar bin/install.sh --clean e reiniciar; nada está live até isso

Fila depois dele: P14 (depende de uso, não de código)
Bloqueado: nenhum
ℹ Sem tracker neste repo — os status acima são os do plano, auto-declarados.
  Ninguém conferiu.
```

Rules for the report:

- **Exactly one recommendation**, with its `why` from the plan — never a menu of
  equally-weighted options. A list of possibilities is the very state the user is
  stuck in when they run this.
- **Human debt is listed even when empty** — "nothing to validate by hand" is an
  answer; silence is the ambiguity that started all this.
- **Divergences are stated, never absorbed.** If the plan and the board disagree,
  the report says so before it says what to do.
- **Say which kind of answer this is.** Reconciled against a tracker, or read
  from a plan nobody verified — under `--offline` or with no tracker wired, that
  line is not optional.

## Constraints

- **Read-only unless `--sync`.** No tracker write ever — this command reports,
  it doesn't transition. `atlassian-expert`, when used at all, is read-only.
- **A tracker is optional; a plan is not.** With no `board-flow.yaml` the command
  still works from the plan file — it just says the statuses are self-reported.
- **Never invents an order.** Absent a plan, or for items outside it, the honest
  answer is "these have no position yet" plus the way to give them one.
- **Doesn't execute anything.** It names the next step; `/board-flow:execute`,
  `/fix` and `/drain` do the work where a tracker exists.
- **Refuses a parallel-waves plan** — that's `/maestro:run`'s document.
