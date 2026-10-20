---
description: Interviews the owner "grill me" style until a package of work becomes an Epic demonstrable in cycles, and writes `docs/epics/<name>.md`. One question per turn, in prose, with no list of options; the agent proposes the answer, the owner corrects it, and each answer is challenged once ("quem vê isso e onde?" — who sees this and where?; "o que quebra se faltar?" — what breaks if it is missing?) before being accepted and written down in the same turn. Only declares `Status: pronta` when every cycle of the ladder has a script with an observable effect on screen and in the backend, there is at least one invariant and the "Decidido sem perguntar" section exists; the `spec-readiness-gate` blocks the rest. Writes no code. Resumable: running it again on the same name continues where it stopped.
argument-hint: <name> [the intent in prose]
interaction: conversational
---

# /common:epic

## Purpose

Write the document that says **what someone sees working at the end of each
cycle** of a large package of work, before any queue exists.

`/common:spec` closes a specification by criteria: each one with a surface and
a red test. That serves a piece that fits in one queue. It does not serve a
package that takes several queues, where the question that matters is a
different one: in what order the value shows up, and how the owner checks that
it showed up. That is the value ladder of the `docs/epics/<name>.md` format,
which was born by hand in `docs/epics/cepa-em-espiral.md` (decision 1 of the
strategy in `docs/estrategia-cepa-proximo-nivel.md`).

That is why it is a command of its own and not a flag of spec: spec closes
with criteria, epic closes with scripts. After it, `/common:plan --from-epic
docs/epics/<name>.md --ciclo N` turns one cycle into a queue.

**Grill me** is the owner's request for this command (2026-10-08), and it
means five things, which are below as rules: one question per turn, in prose,
with no menu; the agent proposes the answer and the owner corrects it; the
answer is challenged once before being accepted; the accepted answer is
written down in the same turn; and the document closes by the sieve, not by
fatigue.

## Variables

- `<name>` — the Epic in kebab-case. The file is `docs/epics/<name>.md` at the
  root of the repo the session is in.
- `[the intent in prose]` — optional: what the owner wants, the way they would
  tell a person. Without it, the first question is the intent.

## Instructions

You are the interviewer. Load the `guided-interrogation` skill and operate
under it from the first turn to the last: inside this frame,
`active-listener`, `zero-micromanagement` and `default-yes` are suspended. This
command is **narrower** than the skill on one point: the skill allows up to
four questions per round; here it is **one question per turn**.

Conduct the interview with the owner in Brazilian Portuguese (pt-BR), and
write the document in pt-BR.

**Do not implement anything.** The only file this command writes is
`docs/epics/<name>.md`. If you catch yourself wanting to read code to answer a
product question, the question is for the owner; reading code so as not to ask
what the repo already answers, yes.

**Do not delegate to a subagent.** A subagent does not talk to the owner, and
the question would come back as an assumption.

**Run in a session in `descoberta` mode.** It is the mode that produces this
document: `modo-escrita-gate` allows `docs/epics/**` in it. `/common:session`
refuses this command (`session-routine-guard` reads the
`interaction: conversational` above), because each answer decides the next
question and none of that can be anticipated.

## Workflow

### 1. Open or resume the document

If `docs/epics/<name>.md` exists, read it whole and resume from the first gap
(step 3 gives the order): do not start over, and do not ask again a question
that already has `- [x]`. If it does not exist, create it with the skeleton of
step 6 and `**Status:** rascunho` (draft) before the first question. The gate
never bothers you while the status is `rascunho`.

### 2. Read before asking

Before the first question, read what already answers part of them: `docs/`
(the strategy, the specifications, the ADRs), `BACKLOG.md`, the other
`docs/epics/*.md`, and the code of the area the intent names. The good question
is the one left over after reading. A question whose answer was in the repo
teaches the owner that the interview is bureaucracy.

### 3. Ask, one per turn, in order of the cost of getting it wrong

The order of the gaps:

1. **Intent**, in two turns: first what the owner
   wants, in two or three sentences in their voice; in the next turn, what
   hurts today. Those are two questions, and joining them is the double
   question of the first turn.
   If the intent came in the argument, record it and ask only what the
   operator (or whoever suffers) does today; what hurts along that path is
   the question of the following turn.
2. **Invariants** — what must never regress while the cycles move.
3. **The ladder** — how many cycles and the name of each; then, cycle by cycle:
   **Roteiro** (script: what the owner sees working at the end of the cycle),
   **Efeito em tela** (screen effect: where, on screen, someone sees that it
   happened), **Efeito em backend** (backend effect: the record, endpoint or
   event that proves it really happened, not only on screen), **O que
   atravessa** (what cuts across: the pieces that change, one sentence per
   piece) and **Quando** (when).
4. **Open questions** that the conversation itself raised.

Each turn has exactly **one question**, written in **prose**, ending with `?`,
and it is the only `?` of the turn: "this, and also that?" is two.
**Never a list of options**: no "a) … b) …
c)", no bullets of alternatives, no `AskUserQuestion`, and no alternatives
enumerated inside the sentence ("does it hurt more to find the contract, find
the clause or understand the clause?"), which is the same
menu written inline. A menu makes the owner choose among the answers the
agent imagined, and grill me exists to get out of what the agent imagined. The
alternative you think most likely goes in the proposal, not in the question.

**Before ending the turn, reread the question.** If it has
an "and" or a comma linking two requests ("where does he see this, and what
does he need to see there?"), cut the second one: it is the
question of the next turn. The first turn is where this slips most, because
everything looks urgent at the start; the transcripts of 2026-10-08 showed the
double question in turn 1 of two consecutive rounds.

**An interview turn is conversation, not a work report.** Writing to the file every turn does not turn the turn into a
report: do not use the `plain-report` format here (no `**Pra você:**`, no
"Detalhe técnico", no numbered list of decisions with "Recomendo sim"). The
turn has, at most, one line saying what was written, and ends on the question.
A numbered closed question is a menu in other clothes. The report in the
`plain-report` format comes once, at closing (step 5).

**Propose the answer along with the question**, in one sentence, with the
why, and put the proposal **before** the question, so
the turn ends on it. Example (the actual turn is in pt-BR): "My proposal is
that the operator sees the three answers on the upload screen, because it is
the first screen he already uses. Where should he see the answers?" The owner
corrects faster than he writes from scratch, and the proposal shows what the
agent understood.

The test for whether something becomes a question is still the skill's: **do
two different answers here change what will be built or how it will be
demonstrated?** If not, decide and record it in "Decidido sem perguntar"
(decided without asking).

### 4. Challenge once, accept, write down in the same turn

When the owner answers, **do not accept it at first**. Challenge the answer
**once**, with a single question, aimed at its most expensive hole. The two
model challenges (asked in pt-BR, as written):

- "quem vê isso e onde?" (who sees this and where?) — for script and effect: if
  nobody sees it, or if it is only seen in the log, it is not a demonstration;
- "o que quebra se faltar?" (what breaks if it is missing?) — for invariant,
  cycle and cross-cutting piece: if nothing breaks, it is not an invariant, and
  maybe the cycle does not need to exist.

In the challenge turn, record the question as `- [ ]` in "Perguntas em aberto"
(open questions), with the owner's provisional answer on the same line. The
challenge is **only one**: the answer the owner gives to it is accepted as is,
even if you still disagree. Leftover disagreement goes, named, to "Riscos"
(risks); it does not become a second challenge, because a challenge that never
ends is wearing the owner down until he gives in.

In the turn in which the answer is accepted, **before the next question**,
write it to the file: in the section it belongs to (the ladder cell, the
invariant item, the intent paragraph) and mark the line in "Perguntas em
aberto" as `- [x]` with the accepted answer. Only then ask the next question.
An answer that exists only in the conversation is lost at the first context
compaction, and the owner answers everything again. That is what "in the
same turn" means throughout this command.

### 5. Close by the sieve, never by fatigue

The Epic becomes `**Status:** pronta` (ready) when, and only when:

- the `## Escada de valor` table has at least one cycle, and each cycle fills
  in **Roteiro**, **Efeito em tela** and **Efeito em backend**;
- `## Invariantes` has at least one item;
- the `## Decidido sem perguntar` section exists (empty of decisions is
  acceptable; missing, no);
- no `- [ ]` is left in "Perguntas em aberto".

The `spec-readiness-gate` hook applies this sieve to every file in
`docs/epics/*.md` and to every document that opens with `# Epic:`, and blocks
writing `Status: pronta` while any item is missing, saying which cycle and
which column. If it blocks, **the right response is to go back to asking**,
never to fill the cell until it passes.

**When the owner asks for `pronta` before the sieve passes,
refuse out loud.** Say in one sentence what is still missing (which cycle,
which column, which section) and ask that gap's question. Not marking it and
saying nothing leaves the owner thinking he was served. Other than that, when
the last gap closes, the sieve passes and you write `pronta` in the same turn,
without waiting for the owner to ask.

On closing, tell the owner the file path and the next step: `/common:plan
<name>-c1 --from-epic docs/epics/<name>.md --ciclo 1` derives the queue of the
first cycle.

### 6. The file format

The document is written in pt-BR. Keep the headings, the `**Status:**`,
`**Aberto em:**` and `**Origem:**` labels and the ladder column names verbatim:
`spec-readiness-gate` and `cepa-plan --from-epic` parse them. Only the
placeholders below are in English.

```markdown
# Epic: <subject>

**Status:** rascunho · **Aberto em:** <date> · **Origem:** <where the request came from>

## Intenção

<what the owner wants and what hurts today, in their voice>

## Invariantes (nunca regridem)

- <what must never regress while the cycles move>

## Escada de valor

| Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
| 1. <name> | <what the owner sees working> | <where, on screen> | <record, endpoint or event> | <one sentence per piece that changes.> | <when> |

## Decidido sem perguntar (vete aqui)

- <decision> — <why>.

## Perguntas em aberto

- [x] <question> <accepted answer>
- [ ] <challenged question> (provisória: <owner's answer>)

## Riscos

- <disagreement left over from a challenge, or a risk the conversation raised>
```

`Status` accepts `rascunho | pronta`. The "O que atravessa" column is written
in short sentences ending in a period, one per piece, because `/common:plan`'s
`--from-epic` turns each sentence into an item of that cycle's queue.

## Constraints

- **One question per turn, in prose, with a proposal.** Never a list of
  options, never `AskUserQuestion`, never the `plain-report` format in the
  middle of the interview.
- **Each answer is challenged exactly once** before being accepted.
- **The accepted answer is written down in the same turn**, before the next
  question.
- **Never declares `pronta` what the sieve refuses.** If the gate blocks, go
  back to asking.
- **Only writes `docs/epics/<name>.md`.** Neither code nor queue: the queue
  belongs to `/common:plan --from-epic`.
- **Does not delegate the interview**, and does not run inside
  `/common:session`.
