---
description: Reads a finished `cepa-until` run (the `.jsonl` record and the `.log` output of the subprocesses) and says what the owner has to do from it, as closed questions with a recommendation. Runs by itself at the end of each run (`cepa-until` writes the result to `<run>.review.md`) and by hand for an old run or one the usage cap stopped. Does not read the whole `.log`, which passes 10 MB: reads the mechanical digest of `cepa-until-digest` and checks in git whatever it states. Read-only: does not merge, touch the queue or talk to Jira.
argument-hint: [<run>.jsonl | latest] [--fila NAME]
interaction: routine
---

# /common:until-review

## Purpose

The summary `cepa-until` prints at the end only counts: so many delivered, so
many stuck, so many usage-cap waits. What the owner needs to decide is
somewhere else, in each subprocess's final report and in the `evidence` of
each queue item: the card that got stuck for the same reason as 19 others, the
build that ran before the last refactor, the migration that has to land before
the others. On 2026-09-24 that reading was done by hand, in a session opened
after the run, and it found all of that. This command does that reading on
purpose, at the end of every run.

## Variables

- `<run>.jsonl` — the run record. `latest` (default) is the most recent
  `.jsonl` in `<raiz-principal>/.claude/queues/<fila>/until/` (main root,
  queue name).
- `--fila NAME` — which queue, when the repo has more than one and the
  argument is `latest`.

## Instructions

**Read-only.** No `git merge`, no `cepa-plan finish`, no card
transition, no build, no push, no file edit. Every course of action becomes
a question for the owner. Whoever runs you at the end of the run is a `claude -p` with nobody watching, and an
irreversible action executed at 4 a.m. is worse than a question waiting at
8 a.m.

**Read the digest, not the `.log`.** The `.log`
of the 2026-09-23 run was 10.6 MB, about 2.6 million tokens (10,617,662 bytes ÷
~4 bytes per token). A grep-driven reading covers what the grep found, and
what was left out disappears silently. `cepa-until-digest` picks what to read
mechanically and says what it picked. Open a stretch of the `.log` only to
check something the digest points to, and say that you opened it.

**Check before you state.** The digest and the
`evidence` describe the moment of the run. Before saying "branch X was not
merged" or "worktree Y still exists", run the cheap command that confirms it
(`git branch --merged`, `git worktree list`, `git rev-list --count A..B`) and
say the result.

## Workflow

### 1. Resolve the run and generate the digest

```
python3 common/bin/cepa-until-digest <run>.jsonl
```

If the `.jsonl` does not exist, stop and say which path you looked for.

Also read the run state, `<run>.estado.json`, next to the `.jsonl` (same name,
different suffix). `cepa-until` writes that file before calling you:
`estado` (`esperando-dono` or `encerrado`), `itens` (one line per item),
`acoes` (the closed list of what a command executes; today only `aterrissar`)
and `fica_com_voce` (what no command executes). A run older than 2026-09-28
does not have the file: say so and continue with the digest alone.

**Dead or interrupted supervisor.** Two states say the run did not reach the
end:

- `interrompido`: the supervisor received SIGTERM or Ctrl+C and wrote the
  `run_interrompido` event to the `.jsonl`, with the `sinal` and the item in
  flight (`id`, `fase` and the `pid_filho`, the `claude` or the build that runs
  in its own session and may have carried on by itself).
- `rodando` with no `run_end` in the `.jsonl`: either the run is still
  running, or the supervisor died silently (the WEGO run 2026-09-28-2003
  stopped at `item_start`, the card closed `done` by itself and the full build
  never ran). Do not guess: run
  `python3 common/bin/cepa-until pendentes --json` and look at the `mortos`
  list (dead runs), which checks the `pid` and the `host` recorded in the state
  (a run with no pid counts as dead 3h after the deadline; an `interrompido`
  run is also on the list). If the run is there, the first question of the
  report is to close it with the command in the `fechar` field
  (`cepa-until fecha-morto <fila>/<run> --sim`): it runs the missing full build
  in the night worktree and, if green, writes the `run_end` and leaves the run
  `esperando-dono` with the `aterrissar` action. The in-flight item with status
  `done` is in the queue without that build. If it is not on the list, the run
  is still running: say so and stop.

### 2. Read looking for these questions

1. **What got done and where it is.** `done` items, commits on the night
   branch (`until/<run>`) or, in a run older than 2026-09-24, on loose
   `session/*` branches. Are they merged? (check in git)
2. **Why the rest did not move.** Group the stuck ones by cause. Several rounds
   stuck by the SAME cause is the main finding of the run: say how many, what
   they cost (time and US$, with the arithmetic) and what unblocks all of them
   at once.
3. **Build.** Did the supervisor's full build stay green after each `done`
   item? Does any report say the build ran before the last change, in parts,
   or did not run?
4. **Gates.** From the agent count of each delivered round: did
   completion-auditor and proof-reviewer run? And validation-lead and
   security-reviewer, when the topology has them?
5. **Merge order.** Migrations with a version number, files changed by more
   than one item, an enum that two items extend. What has to land before what?
6. **Is the queue lying?** A `blocked` item whose code is already on main, a
   `done` item whose branch did not merge, an empty `blocked_by` where the
   `evidence` says there is a dependency.
7. **The loop itself.** Usage-cap waits, network drops, `done_sem_commit`,
   leftovers saved in a stash, circuit breaker. Is any of this a defect of
   `cepa-until` and not of the item? If so, say it belongs to the harness.
8. **Process signals.** Each round carries the `sinais de processo` line
   (process signals): a worktree opened (via Bash, `EnterWorktree` or `Agent`
   with `isolation=worktree`) and a report of a build gate bypassed with another
   module's green, each with WHO. The `proof-reviewer` one with `--detach` is
   the allowed one, and comes annotated; any other breaks the night rule. An
   agent that is not a direct child (the `qa-engineer` called by the
   `engineering-lead`) does not have its calls in the `.log`: its signal comes
   from the report it returned and from RESULT.md, which is why the digest
   scans those texts. In run 2026-09-27-1632 the `qa-engineer` opened a
   worktree in 2 of 4 items and in WEGO-2329 presented another module's green
   build to get past the red-build hook, and none of that showed up in the
   digest.

A question with no finding does not go into the report.

### 3. Report

In the `plain-report` format, written in Brazilian Portuguese (pt-BR): an
opening of up to 3 sentences without jargon, `**Pra você:**` with the count of
decisions, `### Detalhe técnico` and, last, `### Decisões e próximos passos` as
a numbered list of closed questions, each with `Recomendo sim/não`
and the why in one line. Every number comes with its arithmetic. Every term is
explained on first mention.

The order of the questions is the order in which the owner should answer:
whatever unblocks the most work comes first.

**One list only** (C7 of `docs/estrategia-fim-do-cepa-until.md`). Comment on
each action in `acoes` by its id, with no numbering of your own: the question about it carries the id as its label
(`aterrissar`), states the effect with the `frase` from the state and brings
your recommendation. The items of `fica_com_voce` appear in a "Fica com você"
block (stays with you), with what the owner needs to do in each one.

Each "Fica com você" task carries **the step by step in three lines** (on
14/10/2026 the owner rejected a report that only named the category: *"O que,
afinal, que eu tenho que fazer? Dê-me o passo a passo."* — "So what exactly do
I have to do? Give me the step by step."). Keep these three labels verbatim in
pt-BR:

- `Onde:` (where) the repo or directory, and the file when there is one;
- `Comando:` (command) in a code block, or the file to open and what to fill in;
- `Pronto quando:` (done when) what the owner sees on finishing, and what they
  tell me.

For every `human_pending` route, also write, ready to paste, the command the
owner runs when the task is done (`cepa-plan responde` closes the route or
returns the item to the queue; with `--mantem` it only records the answer):

```
python3 common/bin/cepa-plan responde <fila> <id> --resposta "<what you saw>" --repo <raiz-principal>
```

The report never lists a category ("the human routes", "the pending items") in
place of the tasks: one task per item, with `<fila>`, `<id>` and
`<raiz-principal>` already filled in. A task you can execute yourself is not
the owner's. Do not invent an action outside the list: whatever you find that
no command executes (opening a card for a flaky test, fixing the harness) goes
into "Fica com você".

### 4. Decision block for the terminal

After the report, and only at the end of the file, write a fenced block
```` ```json cepa-decisoes ```` that `cepa-until` reads to ask the owner, one at
a time, in the terminal (`cepa-until decidir`). The block does NOT decide what
gets executed: the actions come from a closed list in
`cepa-until` (aterrissar, and `cepa-plan responde`, which returns a `blocked`
item to the queue or closes the human route with the owner's answer, or, with
`--mantem`, only records the answer and leaves the item stuck). It only
provides the wording of the question and your recommendation.

Cover **all deferred items of the queue**, not only this run's: run
`python3 common/bin/cepa-plan queue <fila> --max 1 --json --repo <raiz>` and
take the `deferred` list. Those with reason `bloqueado-antes` and
`human_pending` go in; `reservado` and `depende-de-adiado` are not the owner's
and stay out. An item that already has a `question` (the question the agent
recorded with `finish --pergunta`) needs no line, unless you recommend
something else.

The string values of the block are shown to the owner and are written in
Brazilian Portuguese (pt-BR); the example below is in English for reference:

```json cepa-decisoes
{"aterrissar": {"recomendo": "sim", "porque": "one line"},
 "itens": [
   {"id": "WEGO-2336",
    "contexto": "The code is ready on a side branch and only one fixture test stayed red. The round over the 20 batches is the task that stayed with you, and it is only possible after the merge.",
    "pergunta": "Do I leave the 20-batch round for after the merge and return the item to the queue?",
    "instrucao": "resume from until/2026-10-15-1128-vermelho-WEGO-2336 and give ink above the cut to the textless fixture of PipelineMultimodalSemVazamentoNoLogTest, like the other 4",
    "recomendo": "sim",
    "porque": "the round is only possible after the merge, and the red test is a fixture the agent foresaw and knows how to fix"}
 ]}
```

Rules of the block (the terminal shows each field with its label, on separate
lines; whatever is outside the right field reaches the owner mixed up, and on
15/10 he read a 71-word question with a branch and a test class inside and
asked "o que diabos isso quer dizer?" — "what the hell does that mean?"):

- `pergunta` is closed, answerable without opening the card, in the voice of
  whoever is asking the owner. The terminal shows it with a fixed menu, in
  which **sim = o item volta para a fila com esta resposta** (yes = the item
  returns to the queue with this answer) and **não = fica como está** (no =
  stays as it is); write the question so that "sim" means that, and do not
  write the alternative in parentheses: it is always "não".
- Up to 25 words, in the owner's words: no branch name, test class, fixture
  or file name. The terminal checks it and warns the owner when the question
  goes over that. That detail goes in `instrucao`, and whatever is not an
  instruction stays in the item's evidence, which the terminal shows with
  `[e]`.
- `contexto` is what the owner needs to know to answer without opening
  anything, in up to two lay sentences: what the agent did, what stayed red or
  stuck, and why. No branch, class or file name. The terminal shows it before
  the question, together with the task that stayed with the owner. When the
  route is a task, the `contexto` says where it is done, what to do and how
  the owner knows it is finished (still within two sentences; the file goes in
  `instrucao`).
- `instrucao` is what the next run should do if the owner says yes: branch
  to resume from, test or fixture to fix, file to adjust. It is technical and
  goes to the agent: the terminal shows it as "Se sim, o próximo run recebe:"
  (if yes, the next run receives:) and records it together with the yes in the
  item's evidence. Only when there is something to send; without it, the yes
  records only the question.
- `recomendo` is `sim` or `não`; `porque` fits in one line.
- A `human_pending` route that is a task (validate by hand, run a real login):
  ask whether it has already been done and what was seen, and say what the
  owner needs to have at hand.
- Valid JSON. If there is nothing, write `{"itens": []}`.

## Constraints

- Never execute a course of action, even a reversible one. This command answers "what to do", and
  whoever does it is the owner or the session they open.
- Never state git state without having checked it in this execution.
- The result has to fit in a 5-minute read. Detail that changes no decision
  stays out.
