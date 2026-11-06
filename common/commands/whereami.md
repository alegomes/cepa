---
description: Answers "where are we?" at any point in the session, opening with the project's Epic altitude (cycles closed, in progress, without a queue, open owner questions, derived by cepa-plan epics): purpose, by when, the plan with the current step marked and how long the cursor has been on it. Also lists the owner's dated reminders (.claude/reminders) so no recorded decision is cited as if the owner remembered it. Reads the intent recorded in .claude/session-intent (written only by cepa-intent) and checks the cursor against the latest prompts in the session-log. Only proposes advancing the cursor, never advances it on its own. With no recorded intent, teaches the way; in a cepa-until run, delegates to /common:next.
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
the only writer is `cepa-intent`.

**First mention of an owner decision.** The first time in a session you cite a
decision or reminder of the owner, say "você decidiu isso em <data>, no contexto
<frase>; ainda vale?". Never use a recorded decision as a premise the owner is
assumed to remember (fb-20261104-3, 2026-11-04, owner: "eu disse? nem lembrava").

## Workflow

### 0. The project's altitude

If `docs/epics/` exists, run:

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-plan" epics --repo .
```

and show its output (pt-BR, verbatim, not rewritten) above the session block,
under a line "Onde estamos no Epic:". No output means no Epic: say nothing
about Epics. The summary is derived from the Epic and its queues, never written
by hand.

### 1. Read the state

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intent" state
```

The first line of the output is `state: <empty|normal|fulfilled|other-session>`.
Show the owner the rest of the output, in Brazilian Portuguese (pt-BR), without
rewriting the facts, according to the state:

- **`empty`** (empty): the output says "Esta sessão não tem intenção gravada.
  Diga o propósito e eu proponho o plano." Say that and stop; when the owner
  states the purpose, propose it in three lines (purpose, by when, numbered plan)
  and record it with `cepa-intent write`. If the output carries
  `delegate: /common:next` (a `cepa-until` run, where the intent is the
  `queue.yaml` item), **run `/common:next`** and bring
  its answer in place of this one.
- **`other-session`** (another session): the file was recorded by another
  session. Show the date and the question the output carries ("continuo ou abro
  nova?") and wait for the owner. Continuing is `cepa-intent continue`;
  opening a new one is `cepa-intent write ... --reason "..."`. Do not treat the
  intent as this session's and do not do the step 2 check.
- **`fulfilled`** (done): the output says "Os M passos estão feitos. Ponto de
  parada: ... Próximo: `/common:wrap-up`." Repeat that; there is no cursor to
  check.
- **`normal`**: show the four answers (purpose, by when, plan with the `>` on the
  current step, current step with its age) and go on to step 2.

### 1b. Lembretes do dono

The `state` output may end with a `lembretes do dono (N):` block (date, text and
context of each reminder the owner left, oldest first, with the line "Ao citar um
deles, diga a data e o contexto e pergunte se ainda vale."). Show it verbatim
beside the plan, in all four states. In a `cepa-until` run, show it along with
the `/common:next` answer. No block, nothing to say. `cepa-intent reminders`
prints only this block.

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
`python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intent" --step N` (N = the step that
becomes in progress; `N = M+1` means the plan is done).

## Constraints

- **Read-only.** The only possible write is the `--step N` approved by the owner.
- **Never advances the cursor on its own**, not even "because the step is over".
- **Never reclassifies the state by eye**: if the output says `empty`, it is
  `empty`.
- **Never cites an owner decision or reminder without its date and context**
  in the session's first mention of it, and asks whether it still holds.
- Size: short. This command is read mid-session, when attention is already spent.
