---
description: Triage (groom) a backlog column — classify every card into one of four buckets and route it. Reads each card, inspects the codebase + git for evidence, and proposes per card: ALREADY-IMPLEMENTED → In Review (with an assembled Implementation Summary; the proof gate still applies), READY → To Do, OBSOLETE → Won't Do (list with reasons), or NEEDS-DECISION → grills you interactively. Read-heavy and scope-aware; nothing is written until you confirm the plan. Unlike /drain it does not build anything — it grooms the queue.
argument-hint: [source-column] [--max N] [--scope "<jql>"] [--no-scope] [--dry-run]
---

# /board-flow:triage

## Purpose

Groom a backlog column. For every card you decide one of four things:

1. **ALREADY-IMPLEMENTED** — the behavior already exists in the codebase → propose moving to **In Review** (`defaults.status_map.in_review`). The card carries an Implementation Summary built from the code/git evidence. **Triage proves nothing** — it routes by evidence so the real proof gate (`/board-flow:prove`) has a queue to work on.
2. **READY** — refined enough to start (clear outcome + acceptance criteria + bounded scope) → propose moving to **To Do** (`defaults.status_map.to_do`), where `/board-flow:drain` can pick it up.
3. **OBSOLETE** — no longer makes sense (superseded, duplicate, the area was removed, the need is gone) → **listed for you with reasons**; proposed for **Won't Do** but never auto-cancelled.
4. **NEEDS-DECISION** — a human call is required before it can be routed (ambiguous requirement, conflicting acceptance criteria, a missing product/scope call) → **grills you** with a focused question; your answer re-routes the card into one of the buckets above.

Anything that fits none of these — not implemented, not obsolete, but too thin to start — **stays in the backlog** flagged `needs-refinement`.

This is the grooming counterpart to the execution sweeps. `/board-flow:drain` *builds* cards from `to_do`; `/board-flow:prove-drain` *proves* cards in `in_review`; `/board-flow:triage` *sorts the backlog into those lanes*. It is read-heavy and writes nothing until you confirm.

## Variables

- `$ARGUMENTS` — optionally a source-column name, plus flags. If no column is given, default to the literal `"Backlog"` (the unrefined column; `status_map` has no `backlog` key by convention).
- `--max N` — cap how many cards are classified this run. Default 15. Triage is lighter than `/drain` (no builds) but each card spends an evidence search, so the cap still matters.
- `--scope "<jql>"` — raw JQL fragment narrowing the column for this run only, overriding configured scope.
- `--no-scope` — ignore configured scope; sweep the whole column.
- `--dry-run` — classify and report only; make **no** Jira writes even if you confirm. Use to preview a groom.

**Scope** works exactly as in `/board-flow:drain`: the effective scope is resolved by `atlassian-expert` from `board-flow.yaml` (`defaults.scope` / `scope_overrides.triage` / the active topology's `scope`); the two flags override it for one run. You don't resolve precedence yourself — pass the command name and any flag to `atlassian-expert` and it reports the effective fragment.

## Instructions

You are the orchestrator. You classify and route; you do not implement. Hard rules:

- **`atlassian-expert` is the only Jira write path.** Never call Atlassian MCP tools directly. If it isn't installed, abort.
- **Evidence before verdict.** A card is `ALREADY-IMPLEMENTED` only with concrete code evidence (`file:line` + the commit that introduced it). "There's a comment saying it's done" is not evidence — it's a hint to go look. Apply `evidence-over-assumption` and `acceptance-completeness`: the evidence must demonstrate the card's acceptance criteria at the surface they're written at, not just that *some* related code exists.
- **Triage ≠ proof.** Moving a card to In Review here means "looks done, queue it for proof," never "proven." Always end by pointing the freshly-moved cards at `/board-flow:prove-drain`. Don't let triage's confidence leak into a done claim.
- **Nothing destructive without a yes — mas UM yes, no lote.** Won't Do entra na rodada única do passo 6/7 como qualquer outra decisão, listando cada card com o motivo e o card canônico. O usuário responde em lote ("os dedups sim, o 1236 não"). **Não** peça confirmação card a card: Won't Do é reversível no Jira, e a confirmação individual custava mais atenção que o próprio risco — numa fila com K obsoletos eram K interrupções, contradizendo o `default-yes` que o passo 6 deste mesmo arquivo manda aplicar. Evidência: a sessão de triagem de 2026-08-18 começou 20:25 e às 21:45 ainda não tinha chegado ao plano de execução.
- **Apply `scope-discipline`** across the sweep (never exceed `--max`) and `name-the-disagreement` when the evidence is mixed (e.g. partially implemented).

## Workflow

### 1. Parse arguments

- Source column: `$ARGUMENTS` minus flags. If empty → `"Backlog"`.
- `--max N` (default 15), `--dry-run` (boolean), and the scope flags (`--scope`/`--no-scope`, mutually exclusive — if both, abort: "pass either --scope or --no-scope, not both"). Build the scope directive for `atlassian-expert` the same way `/drain` does (`--no-scope` → `Scope: none`; `--scope "<jql>"` → `Scope: <jql>`; neither → omit).

### 2. Load project config

Read `board-flow.yaml` at project root (fallback legacy `.claude/board-flow.lifecycle.yaml` with a one-time deprecation note). Extract `defaults.status_map`: `to_do`, `in_review`, and optionally a discard status (`cancelled` / `wont_do`; fallback literal `"Won't Do"`). If config is missing entirely, fall back to literal status names and tell the user once that you're guessing them. Note the `default_topology` — write delegations include `Topology: <default_topology>`.

### 3. List backlog cards

Delegate to `atlassian-expert` (include the scope directive only if a flag was passed):

> Command: triage
> <Scope: ... — only if a flag was passed>
>
> List Jira issues where `status = "<source-column>"` in the project, applying the effective triage scope, ordered by priority and rank. Limit to <max> cards. For each return: key, summary, full description, acceptance criteria, issue type, last 3 comments, and linked issues. Also return the effective scope you used.

If 0 cards → report "Nothing in column <source-column>" (note the effective scope, so an over-narrow filter isn't mistaken for an empty backlog) and stop.

### 4. Classify each card (fan-out evidence search)

For each card, you need an implementation-evidence verdict grounded in the actual codebase. **Fan out one read-only `Explore` agent per card** (in a single message, several at a time, respecting `--max`) so the searches run concurrently:

> Card <KEY>: "<summary>".
> Acceptance criteria / expected behavior:
> <criteria or description>
>
> Question: is this behavior already implemented in THIS codebase? Search broadly (by feature name, by the entities/endpoints/functions the card describes, by related test names). For each acceptance criterion, report one of: IMPLEMENTED (with `file:line` of the code that satisfies it AND the `git log` commit/SHA that introduced it), PARTIAL (what exists, what's missing), or ABSENT. Do not judge whether it's *correct* — only whether code that targets each criterion exists. Return a per-criterion verdict, never a blanket yes/no.

When `Explore` reports back, **first run the cheap L1 check that costs nothing and prevents the most expensive mistake:** match the evidence against the card's *verbatim* acceptance criteria from step 3 — not your paraphrase of them. The Explore agent searched against the criteria you handed it; confirm those were the real ACs and that each cited `file:line` actually targets the AC *as written*. If the real ACs say more, or something different, than what was searched, re-run the evidence search with the correct ACs before bucketing. Catching "proved the wrong card" here is free; catching it at the proof gate is not.

Then assign the bucket by this **precedence**:

1. **NEEDS-DECISION** wins first — if routing the card requires a human call the evidence can't settle (ambiguous/conflicting criteria, the card asks for a product decision, or the evidence is genuinely split and the right action depends on intent), bucket it here. Don't guess a route you'd have to undo.
2. **ALREADY-IMPLEMENTED** — every *verbatim* acceptance criterion came back IMPLEMENTED with `file:line` + commit, AND the cited code targets the AC at the surface it's written at. (Mixed/PARTIAL does **not** qualify — name the gap and fall through; a partially-done card is usually READY or NEEDS-DECISION, not done.) For each Bucket-1 card also record two attributes, carried into steps 5–8 so the proof gate isn't blindsided:
   - **proof-strategy hint** — how the proof gate should later attack it, inferred from the card's type: **Bug** → the regression test must go RED at `base_commit` (highest false-positive risk — "code looks fixed + a test exists" is the classic false-green); **AC at an external surface (REST endpoint / outbound payload) but only a unit test covers it** → altitude gap, expect `completion-auditor` INCOMPLETE / an E2E is needed; **already has contract + E2E** → load-bearing proof should be cheap and pass; **boot/config behavior** → perturbation (force the bad config, e.g. the feature flag off in prod, require fail-fast abort).
   - **not-perturbable flag** — set it for cards whose "done" can't be shown by breaking prod code and re-running a test (seed / reference data, pure configuration). Their confidence comes from inspection/query, not proof — flag them so `/board-flow:prove-drain` treats them as inspect-not-prove instead of bouncing them UNPROVEN.
3. **OBSOLETE** — superseded, a **duplicate of another card (dedup)**, or targets code/an area that no longer exists. A dedup card is **not** "done" even if the behavior exists — bucket it OBSOLETE, not In Review, and before proposing Won't Do confirm the **canonical** card's real state (it may itself be unfinished). Always cite the canonical key in the reason. O cancelamento entra na rodada única — cite a chave canônica ali, para o usuário decidir o lote com a evidência à vista.
4. **READY** — clear outcome, acceptance criteria present, bounded scope; nothing blocks a developer from starting. Apply the same **BDD-or-substrate** test the maestro's intake gate applies (`cepa-dor`): if the card's acceptance criteria only name private implementation steps — no Given/When/Then observable at *some* surface — it is not READY unless the card explicitly declares itself substrate (technical work whose legitimate acceptance is technical). Otherwise it falls to NEEDS-REFINEMENT with that named as the gap. A card nobody can verify from outside is a card whose "done" will be argued about later.
5. **NEEDS-REFINEMENT (stays in backlog)** — none of the above; too thin to start, not obsolete, not done.

### 4b. Sweep the debt ledger (Debt Payment proposals)

Debt declared in an Implementation Summary carries a **Revisit trigger** — the
condition that brings it back into view (`summary-nulls-gate` requires it
whenever the declared debt is anything other than none/unknown). **The board is
the ledger**: debt that outlives its card lives as a Jira card labeled `debt`,
not in a file the harness would have to invent and then keep in sync.

Triage is where the ledger gets read. Via `atlassian-expert`, search the project
for open cards labeled `debt`, and for each one read its Revisit trigger:

- **Trigger clearly fired** (the named condition happened — that endpoint did
  change, the contract did add retries, the table did cross the threshold):
  propose it as a **Debt Payment** card in this run's write plan — bucket
  **READY → To Do**, with the trigger quoted as the reason and the card that
  introduced the debt cited. Its acceptance is the debt's `Closure condition:`
  when one was declared.
- **Trigger clearly not fired:** leave it. Say nothing beyond a count — a
  ledger that reports every unfired trigger every run trains the user to skip
  the section.
- **Can't tell from the trigger's own words:** bucket it **NEEDS-DECISION** and
  ask in the grill (step 6). Do not decide that a vague trigger fired; a
  fabricated "it's time" is how debt payment loses the user's trust.

Debt Payment proposals go through the same confirmation as everything else in
step 7 — nothing is created without a yes. If the project has no `debt`-labeled
cards, skip this step silently.

### 5. Triage report

Present one table to the user before any write:

```
Triage of "<source-column>" (scope: <effective scope, or "none — whole column">) — N cards

KEY        BUCKET             PROPOSED ACTION              EVIDENCE / REASON                                  PROOF HINT
WEGO-1234  ✅ IMPLEMENTED     → In Review                  PlugSignClient.java:88 (a1b2c3d) covers both ACs   bug → regression must go RED at base
WEGO-1235  ▶️  READY           → To Do                      ACs + scope clear                                  —
WEGO-1236  🗑️  OBSOLETE        → Won't Do (confirm)         dedup of WEGO-1240 (canonical: in Review, pending)  —
WEGO-1237  ❓ NEEDS-DECISION  → grill (below)              two ACs conflict on auth scope                     —
WEGO-1238  ✋ NEEDS-REFINEMENT → stays (no change)          no acceptance criteria; outcome vague              —
WEGO-1652  ✅ IMPLEMENTED     → In Review (not-perturbable) seed rows present in V12__seed.sql (e4f5g6h)        inspect-not-prove (seed/data)
```

For IMPLEMENTED rows, show the specific `file:line` + commit in EVIDENCE, and the per-card **proof-strategy hint** (and the `not-perturbable` marker, if set) in the PROOF HINT column — that's what `/board-flow:prove-drain` reads to attack the card correctly. For OBSOLETE/dedup rows, name the canonical key and its real state. Honesty over tidiness: if a card is PARTIAL, say so in the reason rather than rounding it up to IMPLEMENTED.

### 6. Grill the NEEDS-DECISION bucket

**Não abra uma rodada de perguntas por card.** Aplique `default-yes`: junte
TODAS as decisões deste balde numa única rodada, e junte a ela a confirmação do
passo 7 e os Won't Do — o usuário responde uma vez só, em lote ("1 sim, 2
admins, 3 não"). Uma pergunta por card, em turnos separados, é o que fazia o
groom de um backlog consumir a sessão inteira antes de escrever qualquer coisa.

Cada decisão vem com **sua recomendação explícita** e o porquê em uma linha;
se a evidência já aponta um caminho claro, recomende-o em vez de devolver a
escolha crua. Onde a resposta não muda o roteamento (só muda um comentário no
card), **não pergunte** — decida e registre no relatório.

Para cada card NEEDS-DECISION, formule a pergunta (use `AskUserQuestion` quando as escolhas são discretas; prosa quando aberto). The question, every option label, and every option description are last-hop user-facing text — apply `conversational-response`'s "translate jargon at the human boundary" (plain headline, protocol code in parens; never a bare `L4` / `altitude` / `waiver` / `AC binário` in a label). Frame the actual decision and what each answer implies for routing — e.g.:

> WEGO-1237 — criteria conflict: criterion 2 says "any authenticated user", criterion 4 says "admins only". Which holds?
> • Any authenticated user → card becomes READY (→ To Do)
> • Admins only → card becomes READY, but scope changes (note it in the card)
> • This needs a product call I can't make → leave in backlog, I'll comment the open question

Apply the user's answers to re-bucket those cards. A NEEDS-DECISION card always leaves the grill as IMPLEMENTED / READY / OBSOLETE / stays — never still "needs-decision."

### 7. Confirm the write plan

Summarize the resolved plan and ask for a single go-ahead (skip this and step 8 entirely if `--dry-run`):

```
Proposed transitions:
  → In Review (N): WEGO-1234, ...        (each gets an Implementation Summary; proof gate still applies)
  → To Do (M), in execution order:
      1. WEGO-1235  — unblocks 1237 and 1240, which touch the same hook
      2. WEGO-1240  — needs the hook stabilised by 1235
      3. WEGO-1237  — independent; last because it is the largest
  → Won't Do (K):  WEGO-1236  (dedup de WEGO-1240)   ← reversível no Jira
  No change (J):   WEGO-1238 (needs-refinement)

Apply? yes / no / pick (e.g. "only the To Do moves").
```

**The To Do list is ORDERED, and every item carries the reason it sits where it
sits.** Propose the order yourself from the evidence you already gathered —
dependencies first, then blast radius, then size — and let the user correct it;
an order they merely approved still beats one that was never written down. This
is the moment the execution order exists; step 9 is what makes it survive the
session. A list without `why` records the order but not the criterion, so the
first "does this still make sense?" forces a re-priorisation from scratch.

Wait for confirmation. Os Won't Do continuam exigindo um **sim explícito por
card** — cancelar card é irreversível na prática, e essa é exatamente a
fronteira que `default-yes` não cruza. Mas peça os K de uma vez, nomeando cada
um com o motivo, e aceite a resposta em lote ("1 e 3 sim, 2 não"): o que estava
errado era o vaivém de um turno por card, não a exigência do sim.

### 8. Execute transitions (via atlassian-expert only)

Group the work; every write delegation starts with `Topology: <default_topology>`.

- **→ In Review.** Moving into a review status requires an Implementation Summary (see `atlassian-expert`'s "Transition to Review with Implementation Summary"). Assemble it from the `Explore` evidence — the `file:line`s satisfying each criterion and the commit SHAs — and **mark it triage-sourced**, e.g. a header line "Routed by /board-flow:triage from code evidence; not yet proven — pending /board-flow:prove." Append the card's **proof-strategy hint** and, if set, the **not-perturbable** marker so `/board-flow:prove-drain` attacks the card correctly instead of bouncing it. Then delegate:

  > Transition Jira issue <KEY> to status `<defaults.status_map.in_review>` with the Implementation Summary below. Post the summary as a comment first, then run the transition.
  > ```markdown
  > ## Implementation summary (triage-routed, pending proof)
  > <per-criterion evidence: verbatim AC → file:line → commit SHA>
  >
  > **Proof strategy (for /board-flow:prove):** <hint, e.g. "bug — regression test must go RED at base_commit" / "altitude — AC is at the REST surface, needs an E2E, expect completion-auditor" / "has contract+E2E — proof should be cheap">
  > <if not-perturbable:> **Not perturbable:** confidence is by inspection/query (seed/data or pure config), not by break-and-RED. Do not bounce as UNPROVEN on missing perturbation.
  >
  > **New debt introduced:** unknown (triage-routed — implementation predates this audit; assess at proof)
  >
  > **Scope captured outside the card:** none | <anything the triage inspection surfaced, captured as follow-ups>
  >
  > **Release needed:** <no, or yes: what — judge from whether the shipped behavior is user-visible>
  >
  > **Human validation route:** <for user-visible behavior: command/URL + expected observation + fail condition; else "not applicable (internal substrate)">
  > ```
  The four explicit-null fields are mandatory (summary-nulls-gate blocks the comment without them); in the triage context "unknown" is an honest value for debt — the proof gate is where it gets assessed.

- **→ To Do.** Delegate: `Transition Jira issue <KEY> to status \`<defaults.status_map.to_do>\`.`

- **→ Won't Do** (os que o usuário aprovou na rodada única — não os que ele tirou do lote). Delegate the transition to the discard status, and first post a short comment with the obsolescence reason so the cancellation is auditable.

- **No change.** For NEEDS-REFINEMENT cards, **post** a comment naming what's missing (acceptance criteria, scope) so the next grooming pass is cheaper. Não pergunte se pode comentar: um comentário é registro, não mutação de estado — é o caso canônico de `default-yes`, e a alternativa (perguntar) custa um turno para uma resposta que é sempre sim. Diga no relatório quantos cards foram anotados.

### 9. Persist the execution plan

Triage is the moment the queue gets an order and a rationale. Both used to die
in the chat: Jira stores the *queue* (To Do), never the *order* nor the *why*.
Write them down.

Update `<programs>/<project_key>/plan.yaml` — **one living plan per board**,
schema `common/plan-schema.yaml`, `mode: single-track`.

**`<programs>` = `<main-root>/.claude/programs`**, where `<main-root>` is the
parent of `git rev-parse --git-common-dir` with the trailing `/.git` removed —
the MAIN clone when you are running inside a linked worktree. Writing the plan
under the current tree instead is how a triage dies: the worktree is removed and
the order goes with it, invisible to git in any repo whose `.gitignore` covers
`.claude/` (that is exactly what happened on 2026-08-18). One plan per board,
one copy, at the main root — never a copy per worktree, which diverges in
silence. See `docs/execution-plan.md`, "Where the file lives".

```yaml
schema_version: 2
mode: single-track
program: <project_key>
source: "Jira <project_key> · <source-column>, triaged <YYYY-MM-DD>"
items:
  - id: WEGO-1235
    title: "<card summary>"
    why: "unblocks 1237 and 1240, which touch the same hook"
    status: pending
    blocked_by: []
    human_pending: null
```

Rules:

- **Merge, never overwrite.** Items already `done` stay, with their
  `human_pending` intact — that field is the answer to "do I still have to
  validate this by hand?", and a re-triage that wipes it re-creates the very
  loss this plan exists to prevent. Cards moved to Won't Do become
  `status: dropped` (kept, so the plan explains why they left), not deletions.
- **Only `→ To Do` cards become `pending` items.** Cards routed to In Review
  belong to the proof queue, not the build queue.
- **The plan is a hypothesis, not a contract** (same rule as the maestro's):
  whoever executes re-validates the item against the board's current state.
- Say in the report that the file was written, and where.

### 10. Final report

A single summary:

- **Triaged from:** <source-column> (scope: <effective scope, or "none">)
- **Cards classified:** N
- **→ In Review:** list of keys (or "none")
- **→ To Do:** keys **in execution order**, each with its one-line `why`
- **Execution plan:** `<programs>/<project_key>/plan.yaml` (written | updated: N new, M preserved)
- **→ Won't Do:** list of keys (or "none — none confirmed")
- **Stayed (needs-refinement):** list of keys
- **Remaining in column (not classified this run):** count, if `--max` was hit
- **Next steps:** name the *first item of the plan* by key and title — not a generic pointer. Then: "Run `/board-flow:prove-drain` to prove the cards just moved to In Review (triage routed them by evidence, it did not prove them). Run `/board-flow:drain` to build the To Do cards in one go, or work the plan one card at a time and use `/common:next` when you lose the thread." If `--dry-run`, note that nothing was written — **including the plan**.

## Constraints

- **Default `--max 15`.** Each card costs an evidence search; raise deliberately.
- **The order and its `why` are outputs, not chat.** A triage run that transitions cards but leaves `<programs>/<project_key>/plan.yaml` unwritten has done half the job: the queue moved and the reasoning evaporated. Under `--max`, the plan holds only the cards actually classified — say so, never let a truncated plan read as the whole queue.
- **Read-heavy, write-late.** No Jira write happens before the step-7 confirmation (and none at all under `--dry-run`).
- **In Review here is a candidacy, not a verdict.** Triage routes by code evidence; `/board-flow:prove` is what proves load-bearing behavior at the surface. Never report a triaged-to-Review card as "done."
- **PARTIAL never rounds up to IMPLEMENTED.** If a single acceptance criterion is unmet, the card is not done — bucket it READY or NEEDS-DECISION and name the gap.
- **L1 before proof.** Anchor every IMPLEMENTED verdict on the card's *verbatim* Jira ACs, not your paraphrase — confirming the AC↔evidence match is free and prevents the "proved the wrong card" mistake that the proof gate would only catch expensively.
- **Dedup is OBSOLETE, not done.** A card that duplicates another never goes to In Review even if the behavior exists — it goes to Won't Do with the canonical key cited (and the canonical card's real state confirmed first).
- **Every Bucket-1 card carries a proof-strategy hint** (and a `not-perturbable` marker where it applies) into its Implementation Summary, so `/board-flow:prove-drain` attacks it correctly — bugs at regression-RED-at-base, REST-altitude ACs via E2E, seed/config by inspection.
- **Won't Do is never batch-applied.** Per-card confirmation, with an audit comment.
- **`atlassian-expert` is the only Jira write path.** If it can't list cards (permissions, bad column name, rejected scope JQL), abort with a clear error — a rejected scope fragment is a config/flag problem, not an empty backlog.
- **Scope narrows, never widens** — same rule as `/drain`. Always show the effective scope on the report so the user sees what's excluded.
