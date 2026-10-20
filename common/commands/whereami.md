---
description: Answers "where are we?" at any point in the session: purpose, by when, the plan with the current step marked and how long the cursor has been on it. Reads the intent recorded in .claude/session-intent (written only by cepa-intencao) and checks the cursor against the latest prompts in the session-log. Only proposes advancing the cursor, never advances it on its own. With no recorded intent, teaches the way; in a cepa-until run, delegates to /common:next.
argument-hint: (none)
interaction: routine
---

# /common:whereami

## Purpose

A session drifts: two hours in, nobody can say precisely what was wanted, which
step we are on and when to stop. The session intent (purpose, stopping point,
plan, cursor) lives in one file per worktree, and this command prints the four
answers in full: **what we are doing, by when, what the plan is, where we are in
it.**

Design: `docs/estrategia-intencao-da-sessao.md` (D4 and "Estados do `whereami`").

## Instructions

Read-only. **The command classifies the state, not your eye**; your only job is
the check against the log (step 2). Never edit `.claude/session-intent` by hand:
the only writer is `cepa-intencao`.

## Workflow

### 1. Read the state

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intencao" estado
```

The first line of the output is `estado: <vazio|normal|cumprido|outra-sessao>`.
Show the owner the rest of the output, in Brazilian Portuguese (pt-BR), without
rewriting the facts, according to the state:

- **`vazio`** (empty): the output says "Esta sessão não tem intenção gravada.
  Diga o propósito e eu proponho o plano." Say that and stop; when the owner
  states the purpose, propose it in three lines (purpose, by when, numbered plan)
  and record it with `cepa-intencao gravar`. If the output carries
  `delegar: /common:next` (a `cepa-until` run, where the intent is the
  `plan.yaml` item), **run `/common:next`** and bring
  its answer in place of this one.
- **`outra-sessao`** (another session): the file was recorded by another
  session. Show the date and the question the output carries ("continuo ou abro
  nova?") and wait for the owner. Continuing is `cepa-intencao continuar`;
  opening a new one is `cepa-intencao gravar ... --motivo "..."`. Do not treat the
  intent as this session's and do not do the step 2 check.
- **`cumprido`** (done): the output says "Os M passos estão feitos. Ponto de
  parada: ... Próximo: `/common:wrap-up`." Repeat that; there is no cursor to
  check.
- **`normal`**: show the four answers (purpose, by when, plan with the `>` on the
  current step, current step with its age) and go on to step 2.

### 2. Check the cursor against the log (only in the `normal` state)

Read the latest prompts in `.claude/session-log.md` (the ones after the
`passo desde` date, or the last 3 if there are few) and compare them with the
plan. If they look like they belong to a step other than the marked one, say so
with both ends, in pt-BR: "o arquivo diz passo 2; os últimos 3 prompts parecem do
passo 3. Avanço?" ("the file says step 2; the last 3 prompts look like step 3.
Shall I advance?"). If the cursor has been still for a long time and the prompts
still match the step, just say its age. If there is no log or it is
inconclusive, say you did not check; do not guess.

**You propose; the owner decides.** Only after the
owner says yes, advance with
`python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intencao" --passo N` (N = the step that
becomes in progress; `N = M+1` means the plan is done).

## Constraints

- **Read-only.** The only possible write is the `--passo N` approved by the owner.
- **Never advances the cursor on its own**, not even "because the step is over".
- **Never reclassifies the state by eye**: if the output says `vazio`, it is
  `vazio`.
- Size: short. This command is read mid-session, when attention is already spent.
