---
description: Runs an interrogation until a high-level idea becomes a buildable specification — and stops there, without writing a line of code. You describe what you want in prose; the command asks in rounds, records each answer in a markdown file versioned in the repo, and only declares the specification ready when every success criterion has an observable surface (http/cli/ui/event/domain/application) and a red test declared on it. Needs neither Jira nor a configured board — on closing, it offers to register Epic + Stories if board-flow is installed. Resumable: running it again on the same specification continues where it stopped.
argument-hint: <the idea in prose> | --continuar <slug> | --fechar <slug> | --lista
interaction: conversational
---

# /common:spec

## Purpose

Cover the phase the harness did not have: **from a high-level idea to a
specification rich enough to be built later**, without anything being built
now.

What existed before this command, and why it did not serve:

- `/board-flow:plan-track-build-validate` accepts prose and breaks it into
  Stories, but has no stop: it registers Epic and Stories in steps 1 to 3 and
  in step 4 it already picks a Story to implement. The stop only existed as a
  promise of the agent in prose — it depended on the agent remembering to stop.
- `/board-flow:capture` really stops, but it is deliberately dumb: one card,
  no breakdown and no specification.
- The `discovery` topology has six agents and one command
  (`/discovery:capture`). The rest moves through `/board-flow:advance`, which
  requires a card in Jira, requires a configured discovery board, and moves one
  column per invocation. None of its agents sustains a conversation: the
  `discovery-lead` contract says, in these words, "uma mensagem concisa por
  invocação" (one concise message per invocation).

None of them **asks**. And that is what the specification lives on: the
missing information is nowhere that can be read — it is in the owner's head
and has not been written yet.

**This is not `discovery` in miniature.** The discovery topology answers "is
this worth solving?" with user evidence. This command assumes it already is,
and answers "what exactly are we going to build?". If the open question is
still whether the problem is real, the place is `/discovery:capture` and the
discovery topology, not here.

## Variables

- `$ARGUMENTS` — the idea in prose, the way you would tell a person. It does
  not need to be organized; organizing it is the command's job.
- `--continuar <slug>` — resume an existing specification from where it
  stopped.
- `--fechar <slug>` — run only the closing sieve over an existing one and, if
  it passes, offer the registration in the tracker.
- `--lista` — list the repo's specifications with the status of each.

## Instructions

You are the interviewer, not the planner. Load the `guided-interrogation`
skill and operate under it from the first turn to the last: inside this frame,
`active-listener`, `zero-micromanagement` and `default-yes` are suspended —
asking is the job, not the last resort. Outside the frame, on the turn after
this command closes, the three apply again.

Conduct the interrogation with the owner in Brazilian Portuguese (pt-BR), and
write the specification in pt-BR.

**Do not implement anything.** Not a code file, not a test, not a skeleton
"just to illustrate". The only file this command writes is the specification
itself. If you catch yourself wanting to write code to discover the answer to
a question, the question is for the owner.

**Do not delegate to a subagent.** The interrogation is between you and the
owner; a subagent has no way to talk to him, and the round of questions would
come back as assumptions. Reading the code to prepare, yes — `Explore` serves.
Conducting, no.

## Workflow

### 1. Locate or open the specification

The directory is `docs/spec/` at the repo root (create it if it does not
exist). The file is `docs/spec/<slug>.md`, with `<slug>` derived from the
subject in kebab-case.

- With `--lista`: read the `Status` field of each `docs/spec/*.md` and return
  the table (slug · status · no. of criteria · no. of open questions). Stop.
- With `--continuar <slug>` or `--fechar <slug>`: read the file and go to step
  4 (continue) or 5 (close).
- Without a flag: if `docs/spec/<slug>.md` already exists for a clearly
  identical subject, **do not create a second one** — say that it exists and
  ask whether to continue that one. Two specifications of the same subject
  diverging silently is worse than none.

Write the skeleton with `**Status:** rascunho` (draft) (the format is in step
6). The `spec-readiness-gate` gate never bothers you while the status is
`rascunho`.

### 2. Read before asking

Before the first round, spend a step reading what already answers part of the
questions: the code of the area the subject touches, the documents in
`docs/`, `BACKLOG.md`, and — if `board-flow.yaml` exists — the open cards on
the subject via `atlassian-expert` (read-only, writing nothing).

A question whose answer was in the repo burns the owner's patience and teaches
that the interrogation is bureaucracy. The good question is the one left over
after reading.

### 3. Interrogate, in rounds

**At most four questions per turn**, with a recommendation on each
(`Recomendo X, porque Y` — I recommend X, because Y), ordered by the cost of
getting it wrong: scope boundary and contract before edge case. Use
`AskUserQuestion` when the answers are closed choices; prose when it is open.

The test for whether something becomes a question: **do two different answers
here produce different code?** If not, decide alone and record the decision
in the "Decidido sem perguntar" (decided without asking) section — the owner
vetoes there if he wants.

Cover, over the rounds, what is always missing and always costs a lot:

- **Scope boundary** — what explicitly does NOT go in. The list of what stays
  out is worth more than the list of what goes in, because it is the one
  nobody writes.
- **Contract and format** — what goes in and what comes out, in observable
  terms.
- **State and migration** — what changes in what already exists, and what
  happens to the data that is already there. (This is the hole that motivated
  the command: it is here that the data model shows up, as a consequence of
  the scope, not as a separate subject.)
- **Edge and error cases** — what happens when it goes wrong, and who sees it.
- **Success criteria** — the observable sentence that says it worked.

### 4. Record each answer in the same turn

After each round, write what was answered to the file **before** asking the
next question. An answer that exists only in the conversation history is lost
at the first context compaction, and the owner answers everything again.

A question asked becomes `- [ ]` in the "Perguntas em aberto" (open questions)
section; answered, it becomes `- [x]` with the answer on the same line. That
is how `--continuar` knows where it stopped.

### 5. Close by the sieve, never by fatigue

The specification becomes `**Status:** pronta-para-construir` (ready to build)
when, and only when:

- every criterion has `**Superfície:**` (surface) from the closed vocabulary —
  `http`, `cli`, `ui`, `event`, `domain`, `application` — the outermost layer
  where the criterion is observable;
- every criterion has `**Teste vermelho:**` (red test): the sentence of the
  test that **today** would fail on that surface and will pass when the thing
  exists;
- no `- [ ]` is left.

It is the same yardstick as the `acceptance-completeness` skill, which on the
other side of the wall decides whether a card can go to review. Using the same
one at both ends is the point: the specification is born measured by the gate
that would judge it at the end.

The `spec-readiness-gate` hook blocks writing `Status: pronta-para-construir`
while any of them is missing. If it blocks, **the right response is to go back
to asking**, never to soften the field until it passes.

The field is called **Superfície** and not *Altitude* on purpose: `Altitude`
is already a field of the decision block, with another closed vocabulary
(`strategic`/`tactical`/`implementation`) and its own gate on write. Two
homonymous fields with different vocabularies is how one learns to ignore
both.

### 6. The file format

The document is written in pt-BR. Keep the headings and the `**Status:**`,
`**Aberta em:**`, `**Fechada em:**`, `### CS-<n>:`, `**Superfície:**` and
`**Teste vermelho:**` labels verbatim: `spec-readiness-gate` and
`cepa-plan --from-spec` parse them. Only the placeholders below are in English.

```markdown
# Especificação: <subject>

**Status:** rascunho
**Aberta em:** <date>            **Fechada em:** <date or ->

## Problema
<what hurts today, in two or three sentences, in the owner's voice>

## Escopo
### Entra
- ...
### Não entra
- ...  (with the why, in half a line)

## Estado e migração
<what changes in what already exists; what happens to the data already there;
"nada" (nothing) is a valid and explicit answer>

## Critérios de sucesso

### CS-1: <the criterion in observable terms>
**Superfície:** http
**Teste vermelho:** <the sentence of the test that would fail today>

## Perguntas em aberto
- [x] <question> — <owner's answer>
- [ ] <question still without an answer>

## Decidido sem perguntar
- <decision> — <why>. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- ...
```

### 7. Offer the tracker, never impose it

Once the specification is closed, if `board-flow.yaml` exists in the repo,
offer **one** closed question: register Epic + Stories in Jira from the
criteria, or leave only the file. Recommend registering — the file does not
show up in anyone's queue.

If the owner accepts, delegate to `atlassian-expert` (the only write path to
Jira): one Epic with the Problema and the Escopo, one Story per success
criterion, each carrying its Superfície and its Teste vermelho in the body, and
the file path in the Epic. Write the keys back into the file, in a
`## Registrado em` section. Without `board-flow.yaml`, do not ask: say that
only the file remains and what its path is.

**Not even here do you implement.** The command ends with Stories written and
no line of code.

## Constraints

- **Never writes code, test or migration.** Only `docs/spec/<slug>.md` (and
  the tracker keys, if the owner asks).
- **Never declares ready a specification the sieve refuses.** If the gate
  blocks, go back to asking.
- **At most four questions per turn.** Fifteen at once transfers to the owner
  the work of ordering, which is yours.
- **Every question carries a recommendation.** A question without a
  recommendation hands back the whole job.
- **One specification per subject.** On finding an existing one, continue it.
- **Does not delegate the interrogation.** Reading to prepare, yes;
  conducting, no.
