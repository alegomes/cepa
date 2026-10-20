---
description: Turns the Review column into a short list of closed questions, instead of a list of cards to open one by one. Reads the cards that are in Review NOW, takes each one's proof artifact (docs/proof/<KEY>.yaml), classifies the NEEDS-HUMAN reason into the seven reasons of docs/needs-human-motivos.md, takes off your plate what is nobody's decision (Docker down, missing tool), groups the rest by reason and asks ONE question per group with a recommendation. You answer in batch ("1 yes, 2 no") and the command applies it. Runs no proof at all — /board-flow:prove is what proves.
argument-hint: [--max N] [--scope "<jql>"] [--no-scope] [--dry-run]
interaction: routine
---

# /board-flow:decide

## Purpose

`/board-flow:prove-drain` leaves the Review column triaged by evidence, and what
remains is the NEEDS-HUMAN pile. Today that pile is a list of card keys: to know
what is being asked, the human opens card after card, reads the description,
reads the gate's comment and decodes the proof levels. This command walks that
path once, mechanically, and hands back questions.

**It proves nothing.** It doesn't spin up a worktree, doesn't run a build,
doesn't perturb code. It reads artifacts that already exist. Running it is cheap
— run it whenever Review has something in it, not once a week.

## What it does NOT do

- It doesn't decide for you on anything that is your decision. Only `nao-rodou`
  (the proof never got to run) leaves the queue without going through you,
  because there is no decision there: nobody has an opinion about a Docker that
  didn't come up.
- It doesn't invent a reason. A card that matches none of the seven **stops the
  command**, with the card named. See "A lista é fechada" ("The list is closed")
  in [docs/needs-human-motivos.md](../../docs/needs-human-motivos.md).
- It writes nothing to Jira before you answer — except what
  `common/autonomy.yaml` puts in the band
  `executa_e_reporta` (step 5b: re-run the proof, aggregated
  infra card, comment), which is done and reported.
  Advancing a card is always a question.

## Variables

- `--max N` — cap on cards analyzed. Default 20 (it's file reading, not proof;
  the cap exists so the report fits on the screen).
- `--scope "<jql>"` / `--no-scope` — same semantics as `/board-flow:prove-drain`;
  `atlassian-expert` resolves the precedence, not you.
- `--dry-run` — builds and shows the queue, asks nothing and writes nothing.

## Workflow

### 1. The queue is the cards in Review NOW — never the files on disk

Delegate to `atlassian-expert`:

> Command: decide
> <Scope: ... — only if a flag was passed>
>
> List the issues in `status = "<in_review>"` in the project, applying the
> effective scope, by priority and rank. Limit <max>. Return key + summary +
> type + priority, and the effective scope used.

**Why this way, and not by sweeping `docs/proof/*.yaml`:** the artifact records
the verdict of that round and is not rewritten when the card moves on later. In
the survey of 03/08/2026, of the 33 cards with a `needs-human` artifact on disk,
**29 were already Done**. A queue built from the files would be almost entirely
closed cards — the opposite of what the command exists to do.

Zero cards → "Nada em Review (escopo: <efetivo>)." ("Nothing in Review (scope:
<effective>).", said to the owner in pt-BR) and stop, naming the scope: a filter
that is too tight must not pass for an empty queue.

### 2. For each card, the artifact comes in as supporting reading

Read `docs/proof/<KEY>.yaml` — and, if it isn't there, `.claude/proof/<KEY>.yaml`,
where the artifacts from rounds before the destination change live. With no
artifact in either, the card enters the queue as
**"never proven"** — it's not NEEDS-HUMAN, it's work for
`/board-flow:prove`. Say so and move on.

### 3. Classify the reason — mechanically, not by reading

Run `board-flow/bin/classify_needs_human.py` (or import `classify`). The rule
looks at the artifact's fields and only falls back to the text where the field
isn't enough. It accepts both spellings of level names that exist on disk.

It returns `(slug, evidence)`. The evidence is the sentence that made the rule
match — that's what the user sees, so they don't have to open the file.

`sem-motivo` **stops the command**: list the cards, say what the artifact has,
and ask the owner for a decision about a new reason. Never force it into the
closest-looking reason.

### 4. Take off the plate what is nobody's decision

The `nao-rodou` cards don't become questions. For them:

- Regroup by concrete cause (coverage tool missing, Docker down, base commit
  gone, harness lock).
- Re-run `/board-flow:prove` on the cards whose
  cause is transient (Docker, build) — don't propose it: it's the `rerodar-prove`
  action of the `executa_e_reporta` band of `common/autonomy.yaml`, and it
  becomes an information line in the report. The general consultation rule is
  step 5b; here the classification is already known
  (`cepa-autonomy classificar --id rerodar-prove` confirms it).
- For a persistent cause (a tool that isn't installed in the project), create
  **one** infra card aggregating all of them —
  never one card per stuck card. Also an
  automatic band (`card-infra-agregado`: card with label `infra`, pass
  `--cond label=infra` in the query). In the survey of 03/08/2026 there were
  11 cards with the same cause (`wego-assinatura-backend` without quarkus-jacoco/PIT),
  which became WEGO-2004.
- With `--dry-run`, both go back to being proposals: nothing is executed.

### 5. Apply the waivers you have already given

Before asking anything, use `board-flow/bin/waivers.py`:
`carregar(repo)` and, per group, `aplicavel(waivers, motivo, escopo)`. If a
waiver comes back: apply the recorded decision and only **inform** — don't ask
again. This step is what keeps the queue from repeating the same question every
week.

Matching is by **reason + scope**, never by card (every card is new; matching
by card wouldn't save a single question). `PlugSignAdapter` and `plugsign adapter`
are the same scope.

Expiry only happens by **date** inside the `revisit_trigger`. A prose trigger
("when the adapter changes") is shown to you and never interpreted by the
code — code that decided on its own that the condition occurred would be
waiving on its own account. An expired waiver becomes a question again, saying
it expired.

A malformed waiver (no author, reason or trigger) is ignored; it doesn't count
as a waiver.

### 5b. Check the autonomy band before turning an action into a question

Every action this command is about to propose to the owner (re-run the proof,
create the infra card, comment on a card, create the card for the missing test,
advance a card to Done) first goes through `common/autonomy.yaml` — the
versioned file that says, per action, whether the agent **does and reports** or
**asks**. Code reads the file, not you:

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-autonomy" classificar --mcp <tool>   # or --bash "<command>", --path <file>, --slash </command>, --id <action>
#   --cond key=value for a detect condition you've already checked (label=infra, branch_atual=main)
```

(`${CLAUDE_PLUGIN_ROOT}/bin/cepa-autonomy` is a shortcut to the real
`common/bin/cepa-autonomy`, like `cepa-plan`; inside the cepa repo,
`python3 common/bin/cepa-autonomy` amounts to the same.)

What the answer changes:

- **`executa_e_reporta`** (reversible: run a build, local commit, create a
  non-terminal card, comment on a card, re-run the proof, aggregated infra card)
  → do it, and what was done becomes an **information line** in the report's
  `### Detalhe técnico` ("Re-ran the proof of 3 cards with Docker down; created
  WEGO-2004 aggregating 11 cards without PIT"). **Never** a numbered item of
  `### Decisões e próximos passos`: in the session of 2026-08-03 to 08-10, ~10 of the ~20
  interruptions were questions in this band that the owner just rubber-stamped
  with "sim". If the answer carries `precondicao`, check it before acting (e.g.:
  delete a branch only if `git merge-base --is-ancestor` says it's contained);
  if it fails, the action is `descartar-trabalho` and falls into the question band.
  `git branch -D` without that check is forbidden: in Phase 1 you are the one who runs the precondition,
  because the hook that runs it on its own belongs to Phase 2.
- **`sempre_pergunta`** (irreversible or external: push, merge into integration,
  discard work, terminal board transition, secret, third parties) → goes into
  the batch of step 6, as always. Advancing a card to Done is
  `transicao-terminal`: it is still a question.
- **not listed** → ask (the default is `sempre-pergunta`: asking too much costs
  seconds, acting too much is the worktree-artifact-rescue all over again) and
  end the question with "proponho adicionar `<id>` ao `common/autonomy.yaml`"
  ("I propose adding `<id>` to `common/autonomy.yaml`"). The list grows by
  versioned diff, never by judgment in the turn.

The repo can harden the list in `.claude/autonomy.yaml` (move an action to
`sempre_pergunta`); never loosen it. `cepa-autonomy listar` shows the merged
list and where each item came from.

### 6. Group by reason and ask ONCE per group

Seven cards stuck on "there is no external test covering adapter X" are ONE
question with seven cards attached, not seven questions. Queue order: the
classifier's `ORDEM_FILA` — descending risk, not Jira priority. Whoever gives up
halfway down the list must be giving up on the least serious part.

Each group comes out like this, and the format is mandatory (`plain-report` +
`conversational-response`). The rendered question is written to the owner in
Brazilian Portuguese (pt-BR); the group label is the classifier's literal label
(`board-flow/bin/classify_needs_human.py`), kept verbatim:

```
[3 cards] O teste não consegue enxergar essa mudança
   WEGO-1540, WEGO-1619, WEGO-1529 — all in PlugSignAdapter

   What this means: the test passes today and would pass just the same if the
   code were broken, because the fake object standing in for PlugSign records
   nothing.

   Question: do I accept the internal proof on these three and send them to Done?
   I recommend no — it's the adapter that talks to the vendor; a card for the
   external test costs less than finding this out in production.
```

No `L4`, `altitude`, `waiver` or raw `n/a` in the question text, in the option
label or in the option description. The technical detail stays in the artifact,
and at the end of the answer for whoever wants to check.

### 7. Batch answer, batch application

The user answers in one line (`1 sim, 2 não, 3 sim`). Only then do you write.
Per accepted group:

- **accept the proof as is** → `waivers.gravar(...)` with reason, scope, the
  user's rationale, author and `revisit_trigger` (all mandatory — a waiver with
  no deadline or condition is a waiver forever, and nobody decided that); then
  advance the cards via `atlassian-expert`. The waiver is **the human's**: the
  `proof-reviewer` still cannot waive anything and the proof artifact still has
  no field for it.
  **In an autonomous run** (`CEPA_UNTIL_RUN` or `CLAUDE_AUTONOMOUS_RUN_ID` in
  the environment) there is no owner in front of you: `waivers.gravar` records a
  **proposal** (`status: proposta`, `autor: null`), not a waiver. Pass
  `fila=`/`item=` and open the human route on the item: `cepa-plan finish <fila> <id> --status
  blocked|pending --human-pending "Aceitar ou recusar a dispensa de <escopo>
  (<motivo>)" --pergunta "Aceito a dispensa de <escopo> por <razão>? Recomendo
  <sim/não>: <porquê>"`. Only the owner's `cepa-plan responde <fila> <id> --resposta "sim:
  ..."`, in a terminal, converts the proposal into a waiver (fb-20261014-3).
- **don't accept** → create the card for the missing test (one per real gap,
  not one per stuck card) and send the cards back with `**Reason:**` **per
  card** — `bounce-reason-gate` blocks a comment without it, and the same reason
  pasted across N cards is exactly the failure it exists to catch.
- **`fora-do-alcance`** → the decision is *who this goes to*: record the owner
  and the condition on the card and name the real state (**Blocked** waiting on
  X / **Deferred** until Y). "Needs attention" is not a state.

### 8. Close

The closing block is rendered to the owner in Brazilian Portuguese (pt-BR):

```
Review: <N> cards
  weren't your decision:  <n>  (<cause> ×<k>, ...)
  waiver already on file: <n>  (applied, didn't ask)
  questions:              <n>  in <g> groups
  stopped without reason: <n>  (the command stopped on these)
```

Always with the explicit arithmetic — `N − n = n`. The number that matters is
how many questions are left, and it only means anything next to what was cut.

## Constraints

- **Read-only by default.** Nothing is written to Jira or to `.claude/waivers/`
  before the user's answer — with one declared exception: an action in the
  `executa_e_reporta` band of `common/autonomy.yaml` (step 5b: re-run the proof,
  aggregated infra card, comment) is done and reported, not asked.
  `--dry-run` neither asks nor executes.
- **The band belongs to the file, not to you.** `cepa-autonomy classificar`
  decides whether an action is a question or information; an unlisted action is
  a question, and the question proposes the id. Promoting an action to the
  automatic band is a diff in `common/autonomy.yaml`, never a decision in the turn.
- **In an autonomous run, never record a waiver:** `waivers.gravar` becomes a
  proposal and the item gets a human route; the owner's `cepa-plan responde` is
  what converts it.
- `atlassian-expert` is the only write path to Jira.
- **One question per group, never per card** — the cost this command attacks is
  the number of times you stop to decide.
- **Every question is closed and comes with a recommendation.** Handing back the
  raw decision ("evaluate", "check") is what this command exists to eliminate.
- An unknown reason stops the command; it never becomes the closest-looking reason.
