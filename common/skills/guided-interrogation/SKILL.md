---
name: guided-interrogation
description: Use inside a specification frame, /common:spec, or when the user explicitly asks to be "grilled", interviewed or interrogated until a scope closes. Suspends, and ONLY inside that frame, the three skills that push the agent to decide on its own (active-listener, zero-micromanagement, default-yes). Outside the frame, they keep applying. Triggers (Portuguese, as the user types them, with English equivalents): "me interrogue" (interrogate me), "me grelhe" (grill me), "me entreviste" (interview me), "pergunta até fechar" (ask until it closes), "quero detalhar antes de construir" (I want to detail before building), "especificação de alto nível" (high-level specification), "não implemente ainda" (don't implement yet).
---

# Skill: guided-interrogation

The harness is built **not** to ask. `active-listener` says that 80% of requests
for clarification are unread context. `zero-micromanagement` and `default-yes`
say to decide on your own whatever is reversible and account for it afterwards.
That is right in construction, where each question costs the owner a turn and the
answer was almost always already on the card.

In specification it is the opposite, and for a structural reason: **the missing
information is not anywhere the agent can read.** It is in the owner's head and
has not been written yet. Guessing here does not save a turn: it produces a
plausible and wrong specification, which only reveals itself as wrong after it
has been built.

## What this skill suspends, and only here

Inside a declared interrogation frame:

| Skill | Normal rule | Inside the frame |
|---|---|---|
| `active-listener` | do not ask for clarification, reread the context | reread first, **and then ask anyway**: the context does not contain the answer |
| `zero-micromanagement` | do not hand the choice back to the owner | handing the choice back **is** the job |
| `default-yes` | decide the reversible on your own | a scope decision here is not reversible: it becomes code |

Outside the frame (same session, next turn, any other command) all three apply
again in full. The suspension belongs to the frame, not to the session.

## How to interrogate

**One round per turn, at most four questions.** An interrogation is not a form:
each answer changes what the next questions are. Dumping fifteen at once
transfers to the owner the work of ordering them, which is yours.

**Ask what changes what will be built.** Before writing a question, answer
yourself: *do two different answers here produce different code?* If not, do not
ask: decide and record it. Style preference, variable name, field order: decide.

**Every question carries a recommendation.** "If you have no opinion, do X,
because Y." The owner must be able to answer "yes, yes, no" and move on. A
question without a recommendation hands back the whole job.

**Attack first what has the most consequence.** The order is by cost of being
wrong, not by the order in which topics showed up in the conversation. Scope
boundary and contract before edge case.

**Record the answer on the spot.** Each answer goes into the document in the same
turn. An interrogation whose answers exist only in the conversation history is
lost at the first context compaction.

**Name what you decided on your own.** What did not become a question and was
decided anyway appears in a separate list in the document, so the owner can veto
it. A silent decision is the same hole in different clothes.

## When the interrogation ends

It does not end from fatigue, and it does not end because the agent thought it was
good enough. It ends when the specification passes a mechanical sieve:

- every success criterion has a **surface** from the closed vocabulary
  (`http`, `cli`, `ui`, `event`, `domain`, `application`): the outermost layer
  the criterion names;
- every criterion has a declared **red test** on that surface: the test sentence
  that fails today and will pass when the thing exists;
- no open question remains unanswered.

It is the same yardstick as the [`acceptance-completeness`](../acceptance-completeness/SKILL.md)
skill, applied one phase earlier. There it judges whether a card is ready to go
to review; here, whether a specification is ready to become code. Using the same
yardstick at both ends is the point: the specification is born already measured
by the gate that would judge it at the end.

The field is called **Superfície** (surface) and not *Altitude* on purpose:
`Altitude` is already a decision-block field, with a different closed vocabulary
(`strategic`/`tactical`/`implementation`) and a gate of its own at write time. Two
fields with the same name and different vocabularies is how one learns to ignore
both.

## What this skill is not

It is not a license to ask anywhere. Outside a declared frame, asking remains the
last resort, not the first. And it is not a license to ask what can be found out
by reading: before each round, read the code, the board and the documents that
exist. The good question is the one that is left after that.
