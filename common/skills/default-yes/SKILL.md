---
name: default-yes
description: Decide instead of asking. When you have a clear recommendation and the action is reversible or only records something, EXECUTE it and report it in the final report, do not ask. Questions are only for the irreversible, and always batched at the edges of the session (kickoff or report), never dribbled out in the middle of the work. Use in every routine command (doctor, triage, drain, prove-drain, execute, wrap-up) and in any assisted session.
---

# Skill: default-yes

**If you already know what you would recommend, the question does not change the
outcome: it only costs a turn and pulls the user off the thread.**

This skill is about *when to ask the user*. Do not confuse it with
`zero-micromanagement`, which is about *when to delegate to a worker*: one is
about the boundary with the person, the other about the boundary with the agents.

## The problem it exists to solve

Recorded by the harness owner (2026-08-18): every routine charges confirmation
cycles **before** the main operation (run the doctor, follow the recommendation,
which generates another recommendation, ...) and **after** it (back and forth
until you are sure it is over). The cost is not the time: it is that the user
loses sight of what the purpose of the session was, and in the end cannot
consolidate what was done. In their words: *"I usually tend to accept your
recommendation"* (original: "eu geralmente tendo a aceitar a sua recomendação"),
meaning the questions almost never changed the decision.

## The rule

Before writing a question, classify the action:

| The action is... | Do |
|---|---|
| **Reversible** (can be undone without losing work: commit on a session branch, move a file, reinstall a plugin, return a card with a reason) | **Execute.** Record it in the report. |
| **Only records** (create a card/backlog item, write a handoff, note a debt, open an issue) | **Execute.** Never ask "do you want me to create a card?". |
| **Investigation / reading** | **Execute.** |
| **Irreversible or destructive** (delete a branch with unique commits, `Won't Do` on a card, force-push, delete a file with no copy, publish externally) | **Ask**, in a batch, at the end. |
| **Real cost** (run N expensive proofs, spend a large budget) | **Ask**, at kickoff, together with everything else. |
| **Genuine fork of preference**, with no defensible default (reinstall *or* roll back a version; which scope to tackle) | **Ask**, in a batch. |

The owner's canonical example: *"I found a flaw and I suggest creating a card"*
(original: "encontrei uma falha e sugiro criar um card") -> **create the card**.
Telling them afterwards is enough; asking permission beforehand is not.

## Questions go at the edges, never in the middle

When something is left that requires the user:

1. **At kickoff**, if the answer changes the whole plan (scope, maximum number of
   cards, what to do with whatever gets stuck). Ask ALL of them at once, including
   the ones the routine would only find midway.
2. **In the final report**, for the rest: a numbered list, one closed question per
   item, each with `I recommend yes/no` (`plain-report` format).

Never in the middle of execution: a question that interrupts a drain at card 3 of
5 forces the user to reload the entire context in order to answer.

## Keep the thread of the session

Autonomy without memory becomes another form of noise. Three obligations:

- **An open proposal does not vanish.** If you proposed something and the user has
  not answered yet (often because they were bringing more information, not
  because they ignored it), the proposal **reappears in the next report**,
  updated, until it is accepted, refused, or dropped by you **with the reason
  written down**.
- **A side topic gets parked.** A parallel finding and a SessionStart warning
  (unintegrated worktree, expired handoff, debt in another module) **do not become
  a question in the middle of another topic**. Note it and bring it up at the
  close of the session. The exception is what blocks the current topic: then it is
  part of the topic, not a detour.
- **After the wrap-up, nothing new opens.** The parking lot is emptied in the
  wrap-up itself, into the handoff, the BACKLOG or `cepa-feedback add`. A report
  after "Safe to exit" never proposes the next thing: it says where the topic was
  recorded and ends.

## Safety net

What makes this safe instead of reckless:

1. **Every self-applied decision is named in the final report**: the user reviews
   afterwards, in bulk, instead of authorizing beforehand, one by one.
2. **The overrule channel exists:** `/common:debrief` (keeps/overturns the
   decisions of a run) and the session handoff.
3. **The irreversible boundary stays closed**: default-yes never authorizes
   deleting work.

## Sniff tests

- You wrote "do you want me to...?" for something reversible: delete the question
  and do it.
- You are about to ask two things in different turns: merge them into one list.
- The question is about a topic that is not the session's: park it for the end.
- You finished the routine and are "awaiting confirmation to proceed" without
  having delivered a report: the report was the next step.
