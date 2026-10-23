---
name: feedback-capture
description: Use when the user complains about the harness (the command that asked too much, the gate that blocked what it should not have, the unreadable report, the agent that did what was not asked) or when they explicitly ask to record feedback about Cepa. Record the complaint verbatim through `cepa-feedback add` and carry on with the turn's work; do not ask whether to record it, do not argue whether the complaint is fair, do not fix the harness now. Do not trigger for complaints about the project's CODE (that is a card, not harness feedback).
---

# Harness feedback capture

## The problem

Annoyance with Cepa never shows up on its own. It shows up in the middle of
another task, in the client's repo, with the whole context loaded, and at that
instant there are two exits: drop the task to open Cepa's `BACKLOG.md` (which is
almost never the open repo), or carry on and forget. Carrying on and forgetting
always wins, because stopping hurts. This skill is the third exit, and it has the
same shape as [off-mode-capture](../off-mode-capture/SKILL.md): recording costs
one line, so the detour does not need to become work now.

What is lost without it has a name: the complaint exists as the owner's text,
written in the heat of the episode, with the command that caused it still on the
screen. A month later what remains is "the harness asks too much", which is true
and not actionable.

## When to trigger

Trigger when the target of the complaint is **Cepa**: a command, a hook, a gate,
an agent, a report, a prompt, the flow of a routine.

Do not trigger when the target is the **project**: a bug in the code, a
third-party API, a broken build, a product decision. That is a card:
`/board-flow:capture`, or a line in `.claude/desvios.md` if there is no board.

The test, in one question:

> Would reinstalling Cepa on another machine take the annoyance along?

Yes -> harness feedback. No -> project card.

## What to do

One call, then carry on with the turn's work:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" add \
  "<the owner's text, verbatim>" --alvo <comando|hook|agente> --origem skill
```

(Outside a session with the plugin loaded, the path is `common/bin/cepa-feedback`
in the Cepa repo.)

Three rules about the text:

1. **Verbatim.** Record what the owner wrote, not your summary of it. The summary
   swaps the complaint for your reading of the complaint, and your reading is the
   part that tends to be wrong: if you had understood, the annoyance would not
   have happened.
2. **`--alvo` whenever possible.** `modo-escrita-gate`, `board-flow:drain`,
   `proof-reviewer`. It is what turns "the harness gets in the way" into
   something someone can open. With no identifiable target, record it anyway:
   feedback without a target is still a signal; unrecorded feedback is nothing.
3. **No analysis, no proposed fix.** Analyzing is already taking the detour. The
   record keeps the episode; triage decides what to do, later.

Repo, branch and session mode enter the record on their own: you do not type them.

## What NOT to do

- **Do not ask whether to record it.** The question hands back to the owner the
  micro-interaction that `default-yes` exists to kill. Record it and say in one
  line that you did.
- **Do not fix the harness now.** Even if it looks trivial: the fix is the work of
  another session, in a repo that is probably not this one, and the turn in
  progress has an owner. If the owner explicitly asks for the fix, then it is an
  order: comply and record that it crossed over.
- **Do not argue the complaint.** "Actually the gate was right" may be true and
  this is not the time. The record keeps what they felt; triage checks the facts.
- **Do not record the same episode twice.** A complaint repeated in the same turn
  is a single record.

## How it shows up in the reply

One line, at the end of what you were already going to answer. The line below is
written in the user's language (Portuguese example):

```
**Feedback registrado (fb-20260826-2):** o gate de escrita barrou um commit legítimo · alvo: modo-escrita-gate
```

Nothing beyond that. The turn belongs to the task the owner asked for.

## Afterwards

`/common:feedback` lists what is open and, in the Cepa repo, turns it into a
`BACKLOG.md` item with the episode and context attached. Recording is not
approving work: the item joins the queue and goes through triage like any other.
