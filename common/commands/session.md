---
description: Opens a session with a declared purpose and carries it from start to finish without ping-pong — gets the harness ready (doctor --fix in a batch), asks ALL the questions at the start (including the ones the routine would only hit midway), runs the whole routine without stopping, delivers ONE final report and offers the wrap-up. Replaces the pattern "run the doctor → follow the recommendations → run the routine → answer the back-and-forth at the end", which used up more attention than the task itself.
argument-hint: <routine> [routine args] | --help [routine]   e.g.: /common:session prove-drain --max 5
interaction: routine
---

# /common:session

## Purpose

A session has ONE purpose. Today it charges the user three things before it
gets to that purpose (diagnosis, cascading fixes, the routine's confirmations)
and one more afterwards (back-and-forth until they are sure it is over). This
command makes the whole journey fit into: **you say what you want → answer
once → get the report → close.**

It is not an autonomous mode: you still decide what is irreversible. What
changes is *when* you decide — everything together at the start, nothing
dripped in along the way.

## Variables

- `$ARGUMENTS` — the routine's name and its arguments.
  Recognised routines: `prove-drain`, `drain`, `drain-plan`, `triage`,
  `decide`, `execute`, `autonomous`, `docs`, or any installed slash command
  (pass the name without the `/`, e.g. `board-flow:prove-drain`).
- `--help [routine]` — lists the routines and the parameters of each, and runs
  nothing (see step 0). With a routine, shows only that one.

## Instructions

You are the session's conductor. Activate the skills `default-yes` (decide
instead of asking; questions only at the ends) and `till-done` (do not stop
midway). `plain-report` applies to the final report.

**The rule that governs this command:** between the start and the report, you
ask nothing. If an irreversible choice shows up midway, you record it, carry on
with the rest of the batch and bring it to the report — you only interrupt if it
literally blocks the routine from continuing.

## Workflow

### 0. `--help` (read-only, ends here)

If the first token of `$ARGUMENTS` is `--help` or `-h`, do **not** run the
doctor, ask nothing and run no routine. Answer and stop.

Read the parameters **from the target commands' files now**, never from a copy
written here: a copied list goes stale silently when a command gains a flag.
For each alias from step 1 (or only the requested one, if `--help <routine>` was
given):

1. resolve the alias to the real command and open its file (the installed
   copy; in the cepa repo, `<plugin>/commands/<cmd>.md`, with `docs` in
   `docs-topology/`);
2. merge the frontmatter's `argument-hint:` with the `## Variables` section. The
   two sometimes diverge (a flag documented in only one of them); list the union
   and mark a flag that appears in only one with "(só no cabeçalho)" (header
   only) or "(só em Variables)" (Variables only).

Answer format, in plain Brazilian Portuguese (pt-BR):

- a table `alias → real command`;
- a numbered list per routine: each parameter on one line with what it does and
  the default when omitted;
- one line saying that any installed command works by its name with `:`, and
  that commands with `interaction: conversational` are refused (list them with
  `grep -rl "^interaction: conversational"` over the installed plugins).

### 1. Resolve the routine (without asking)

Map the first token of `$ARGUMENTS` to the real command: `prove-drain` →
`/board-flow:prove-drain`, `drain` → `/board-flow:drain`, `drain-plan` →
`/common:drain-plan` (the batch over the queue, no Jira), `triage` →
`/board-flow:triage`, `decide` → `/board-flow:decide`, `execute` →
`/board-flow:execute`, `autonomous` → `/common:autonomous-start`, `docs` →
`/docs:survey`. A name with `:` is used literally.

If the routine does not exist or its plugin is not installed, stop here and
say which — it is the only silent abort allowed.

**A conversational routine is refused here.** Open the target command's file
and look at the frontmatter's `interaction:` field. If it says `conversational`,
**do not run it**: tell the owner to call the command directly and stop. The
`session-routine-guard` hook already blocks the invocation before you see the
prompt; this rule exists for the case where it is not installed.

The reason is that the two contradict each other, not that one is worse. This
command activates the `default-yes` skill and, in step 3, front-loads
everything the target would ask later. A conversational command like
`/common:spec` loads the `guided-interrogation` skill, which **suspends**
`default-yes`, and asks in rounds because each answer decides what the next
questions are — nobody asks about data migration before knowing the scope
boundary. Squeezed into a single round, the rest of its work would be guessed,
and would come out well-formatted enough to pass the gates without anyone
noticing that the answers did not come from the owner.

### 2. Batch preflight (do not delegate this to the user)

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-doctor" --fix
```

Report in **at most 3 lines**: what was fixed on its own, and what was left.
Do not paste the whole output — the user did not open the session to read a
diagnosis.

- Nothing left → go straight to step 3.
- Something left in the **Precisa de você** block (the doctor's "needs you"
  block) → do NOT open a round of questions here. Carry those items into the
  single question round of step 3, together with the routine's, each with its
  recommendation.
- An item prevents the routine from running (e.g. `board-flow.yaml` without
  `status_map` and the routine is a board one) → then it is blocking: say so in
  the step 3 question as the first item.

### 3. Start — ALL the questions at once

Read the target command's file and **anticipate every point where it would stop
to confirm**. Build a single round (`AskUserQuestion`, at most 4 questions)
with what actually changes the outcome:

- what the routine would confirm before starting (the list of cards, the
  `--max`, the scope);
- what it would ask **midway or at the end** (what to do with each card that
  stops at NEEDS-HUMAN, whether to send it back or hold it, whether to apply the
  default recommendation) — anticipating this is the point of the command;
- what was left from the preflight.

Rules for the round:

- Every question is **closed**, with its explicit recommendation and the why in
  one line; no "you decide".
- No jargon left unintroduced in the option labels (`plain-report`).
- If **no** question is irreversible or changes the plan, **ask nothing**:
  announce the defaults in two lines and go to step 4.
- Offer, as one of the questions, the **stopping policy**: "seguir até o fim
  aplicando as recomendações" (carry on to the end applying the
  recommendations; default) or "parar e me chamar se aparecer X" (stop and call
  me if X shows up). The questions are asked in pt-BR.

### 3b. Record the session intent (the routine records it, no second ritual)

Right after the answers to the start (or after announcing the defaults, when
there was nothing to ask), and **never on the `--help` path**, record the intent:

```
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intencao" gravar --proposito "<a rotina e o que ela vai entregar, com os parâmetros decididos na largada>" --para-quando "relatório único entregue e wrap-up oferecido" --plano "executar a rotina com os parâmetros da largada" "entregar o relatório único" "oferecer o wrap-up"
```

(The values are pt-BR on purpose: the intent is shown to the owner. The
purpose placeholder means "the routine and what it will deliver, with the
parameters decided at the start".)

- A plan item cannot contain `:` (the writer refuses it). That is why the
  routine's name (e.g. `board-flow:prove-drain`) goes in the purpose, never in
  the plan.
- Exit code 4 means there is already an intent in this tree (the chaining
  recorded the brief, or another session did): run the same command adding
  `--motivo "aberta por /common:session <rotina>"`.
- Advance the cursor with
  `python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intencao" --passo 2` before building
  the report and with `python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-intencao" --passo 3` when offering
  the wrap-up.
- This replaces the "propose it in three lines" that the `session-mode` hook
  asks for when there is no intent: do not propose it separately, it would be
  the second ritual.
- A writer failure does not stop the routine: note it in the report and carry
  on.

### 4. Execution — no interruptions

Run the routine with the parameters already decided. While it runs:

- the target command's internal confirmations **have already been answered** in
  step 3; do not repeat them to the user;
- a reversible decision, or one that only records (create a follow-up card,
  send a card back with a reason, note a debt, archive a handoff) → **execute
  and note it**;
- an irreversible, non-blocking decision → **do not execute, note it** for the
  report;
- a side topic that shows up (unintegrated worktree, debt in another module,
  SessionStart warning) → **park it**, do not turn it into a question.

### 5. Single report

A `plain-report` that closes the session on its own, written in Brazilian
Portuguese (pt-BR):

- the routine's result (what it produced, in plain language);
- **Decidi por você:** (decided for you) the list of what you applied on your
  own and why — this is what trades "ask permission first" for "account for it
  afterwards";
- **Estacionado:** (parked) the side topics that showed up and that you
  deliberately did not pull, each on one line (they are the agenda for the next
  session, not this one);
- the closed questions left over (irreversible), numbered, with
  `Recomendo sim/não`;
- the last line offers the close: `/common:wrap-up` (commit + handoff +
  merge) — and say it is the next and last step.

## Constraints

- **One round of questions, at most.** If you catch yourself asking twice, the
  second should have gone into the first or become a default.
- **Preflight never becomes a conversation.** `--fix` handles the mechanical;
  the rest goes to the single round.
- **Do not turn parking into work.** A parked item is one line in the report;
  pulling it is exactly the detour this command exists to avoid.
- **The report is mandatory even on failure.** A routine that aborted midway
  still closes with what ran, what did not run and the next step.
- An expensive routine (drain, prove-drain, autonomous) still respects `--max`
  and `scope-discipline` — decision autonomy is not spending autonomy.
