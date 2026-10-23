---
name: off-mode-capture
description: Use when the session has an active working mode (the session-mode hook injected "[modo] Esta sessão opera em X", meaning "[mode] This session operates in X") and the next action you were about to execute does not belong to that mode. Record the detour on your own and carry on with the mode's work; do not ask, do not execute the detour. The captures go into the final report. Do not trigger without an active mode: then normal behavior applies (board-flow:suggest-capture, if installed).
---

# Detour capture

## The problem

The symptom that gave rise to the modes: *"I start specifying a feature, jump to
development, dive into micro-adjustments and spend energy on documentation before
finishing"* (original: "eu começo a especificar uma funcionalidade, pulo pro
desenvolvimento, mergulho em micro-ajustes e gasto energia na documentação antes
de terminar").

The cause is not a lack of discipline: it is a lack of a **destination for the
detour**. When the detour shows up and there are only two exits (do it now, or
lose it), doing it now always wins, because losing hurts. This skill is the third
exit.

## The test, in one question

> Is this action necessary for the **exit condition of the active mode**?

- **Yes** -> it is the mode's work. Execute it, however much it looks like
  something else.
- **No** -> it is a detour. Record it and carry on.

The test is the exit condition, not the appearance of the action. Writing a test
during Construction looks like QA work and is the mode's work. Fixing a bug that
keeps the `proof-reviewer` from running looks like Reform and is the mode's work.
Renaming an ugly variable in the file next door, on the other hand, is no mode's
work: it is a detour, even if it takes ten seconds. **The cheap thing is exactly
what leaks.**

## What counts as a detour, by mode

The mode names are the literal keys the hook uses, so they stay in Portuguese
(English meaning in parentheses).

| Active mode | Typical detour |
|---|---|
| exploração (exploration) | starting to specify acceptance criteria, opening code to "just check" |
| descoberta (discovery) | implementing, refactoring, writing documentation |
| design (design) | implementing the design; touching the design system beyond what the feature uses |
| construção (construction) | micro-adjustment outside the criterion, opportunistic refactoring, documentation |
| reforma (reform) | anything outside the declared budget; changing observable behavior |
| reflexão (reflection) | **fixing** what you found (the finding becomes a card, not a patch) |
| documentação (documentation) | fixing the code that the documentation revealed to be crooked |

## What is NOT a detour

- A clarifying question, reading code, searching: none of that changes the repo.
- Whatever the user asks for **explicitly in this turn**: they own the boundary
  and may cross it. Record that it was crossed, and carry on.
- A real blocker: if without it the mode's exit condition is unreachable, it is
  the mode's work. Say in one line, in the report, why it was a blocker.

## What to do

**Record and carry on. Do not ask.** Asking hands back to the user the
micro-interaction that the mode exists to eliminate (`default-yes`).

Destination, in this order:

1. **With `board-flow.yaml` in the repo** -> a card via `/board-flow:capture`, with
   the active mode and the session in the description.
2. **Without board-flow** -> one line in `.claude/desvios.md` (create it if it does
   not exist). The line below is written in the user's language (Portuguese example):

```markdown
- [ ] 2026-08-18 · modo: construcao · o resolver de contatos duplica a query N vezes; vi ao passar por ContactResolver.java:88
```

Each line says **what**, **where I saw it** and **which mode I was in**. No
analysis, no proposed fix: analyzing is already taking the detour.

## In the final report

A block of its own, counting how many there were. The block below is written in
the user's language (Portuguese example):

```
**Desviei e registrei (3):** duplicação de query no ContactResolver ·
migration sem rollback · README apontando para endpoint que mudou de nome
```

If no detour showed up, do not write the block. Absence does not need a line.

## Limit

This skill records; it does not prioritize or decide. A captured card joins the
queue like any other and goes through normal triage. You are not enqueueing
approved work: you are keeping the detour from becoming work **now**.
