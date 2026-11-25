# cepa-until: run the queue for a time window, with nobody awake

`cepa-until` is a terminal command (not a slash command) that runs the repo's
single-track queue for **a window of time** instead of for a number of items. It lives at
`common/bin/cepa-until` in the Cepa clone. This page is a condensed version of the design
notes at the top of that script, which remain the source of truth.

```sh
cepa-until my-queue --for 12h
cepa-until my-queue --until 07:00
cepa-until my-queue --for 3h --dry-run     # prints the schedule of the run, executes nothing
```

`my-queue` is the name of a queue written by `/common:queue`, stored at
`.claude/queues/<name>/queue.yaml`. See [execution-plan.md](execution-plan.md).

## Why it exists

The three bulk executors (`/board-flow:drain`, `/common:queue-run`,
`/board-flow:prove-drain`) are limited by **count**: `--max N`. Count is the wrong unit for
using idle time. You don't know how many items fit in a night. You know how many hours you
have.

A clock alone does not solve it, because what kills a long session is not time, it is
**context**. A 12-hour session overflows long before 12 hours, and the one who resumes it is a
person typing `/common:autonomous-resume`. At 3 a.m. nobody types.

So the design is **one item per subprocess**. The supervisor launches

```sh
claude -p "/common:queue-run <queue> --max 1"
```

once per item, in a new process every time. A full context window stops being a failure and
becomes the normal end of a subprocess. The supervisor launches the next one with a clean
window. That is what makes 12 hours possible.

## What it does not do, on purpose

It does not reserve items, record outcomes, know the topology or know what a card is.
`/common:queue-run` and `cepa-queue` do that, with a state machine that already exists and is
tested:

- `cepa-queue start` reserves the item and **signs** the reservation (session, pid, host).
- `cepa-queue queue` hands back as runnable any reservation whose pid died. A dead subprocess
  cannot lock the queue forever.
- `cepa-queue finish` records the outcome, including the route only a human can close.

`cepa-until` is the wiring around that: clock, circuit breaker and log.

## The four owner decisions (2026-08-30)

1. **The source is the queue on disk**, not the board column. The queue keeps the order and
   the reason for it, and does not depend on Jira being up at 3 a.m.
2. **Circuit breaker at 3 failures in a row** (`--max-failures`). Below that it is bad luck.
   Above it, the window is being burned on a systemic problem.
3. **One commit per item, on a single branch.** No merge train, no pile of branches waiting
   for someone to notice. This is a guard, not an intention: the starting branch is recorded
   and checked between items, and the run ends if it changed (`branch-mudou`). Git not
   answering in the night's worktree is not a branch change: the supervisor rebuilds the
   worktree's link to the clone (`.git/worktrees/<name>`, which vanished on 2026-09-25)
   and carries on; if that fails the run ends as `git-quebrado`, with git's own error.
4. **`--dangerously-skip-permissions` is on by default.** Without it the subprocess hangs at
   the first permission prompt and the night dies silently. It is printed in the banner and
   can be turned off with `--with-permissions`, which only makes sense with someone watching.

## Where the cut happens

Between items, never in the middle of one. Killing an item halfway leaves a dirty tree and a
dangling reservation. Two margins control it:

| Flag | Default | Meaning |
|---|---|---|
| `--min-reserve` | 25m | Do not **start** an item if less than this remains. An item that does not fit is wasted work. |
| `--slack` | 60m | How far past the deadline an item **already running** may go before being killed. Past that it is a timeout, recorded, and the orphaned reservation returns to the queue on the next run. |
| `--attempts-per-item` | 2 | Subprocesses the same window spends on the same item before marking it `blocked` and moving on. |

## The account's 5-hour usage cap

The Claude account has a usage quota per 5-hour window. On 2026-09-17 a run hit the cap at
01:00 with the reset at 03:20 and the window open until 06:17. The run stopped, about 3 hours
of window went unused, and the item in flight lost its work. Two rules came out of that:

- **Wait for the reset when the cap hits.** If the reset time is known and fits in the
  window, the supervisor sleeps until reset plus a margin (`CEPA_RUN_RESET_MARGIN`, default
  120s) and resumes the **same** item. The cut attempt does not count against the item's
  attempts or the circuit breaker. Three cuts in a row with no progress end the run.
- **Do not start an item with the quota nearly gone.** Each subprocess reports the 5-hour
  window usage. Before each item the supervisor projects usage: last reading plus the largest
  item cost measured in this window. If the next item does not fit, or with no history the
  reading is already above 90%, it waits for the reset before starting.

If the wait does not fit in the window, the run stops (`limite-de-uso` or `cota-no-fim`)
instead of starting an item that would be cut halfway.

## When it stops

At the first of: deadline reached, no runnable item in the queue (`end-of-queue`, `blocked`,
`blocked-before`, as reported by `cepa-queue queue`), circuit breaker, a stuck queue, or a
usage cap whose wait does not fit in the window. (The queue reasons used to be Portuguese —
`fim-da-fila`, `teto`, `bloqueado`, `reservado`, `depende-de-adiado`, `bloqueado-antes`; the old
spelling is still accepted during the transition.)

A **stuck queue** (`fila-travada`) is N items in a row that ended `blocked` (`--max-blocked`,
default 3). `blocked` counts as progress, so the circuit breaker never sees it: the item left
the queue with a reason. But a queue where every item blocks on the same outside cause burns
the window rediscovering it. On 2026-09-23 that was 20 rounds and US$ 14.30; on 2026-09-15,
7 in a row in 11 minutes. Any other outcome (`done`, `dropped`, a human route) resets the
count; an attempt with no progress belongs to the circuit breaker and leaves it alone.

In a `--all` run the limit is **per queue**: the streak of queue `a` is not touched by the
items of queue `b`. When a queue reaches `--max-blocked` it **leaves this run** instead of
ending it: a line names the queue and its blocked items, the run record gets a
`fila_saiu_do_run` event (and `run_end` lists `filas_fora`), no further item of that queue
starts, and the run carries on with the other queues. The queue is out only for this run;
the next one picks it up again. `--max-failures` still ends the whole run.

## O que o registro grava por tentativa (`versao_registro: 2`)

O `run_start` traz `versao_registro: 2`; registros sem o campo são do formato antigo e o
`cepa-until-digest` não os cobra. Num run novo, cada tentativa deixa:

- **`session_id`** em `item_start` e `item_end`: um UUID novo por lançamento, gerado pelo
  supervisor e passado ao `claude` com `--session-id`. É o que liga a linha do registro à
  conversa (transcrição) que a executou.
- **`motivo_fim`** em `item_end`, de um conjunto fechado, derivado só do que o supervisor já
  observa. O primeiro que casar vence, nesta ordem: `folga` (o supervisor matou no limite da
  folga), `sinal` (o processo morreu por sinal externo), `cota` (teto de uso da conta),
  `rede` (o `claude` não alcançou a API), `contexto` (o `result` final fala de contexto
  estourado), `hook` (o `result` final é erro e cita um hook que bloqueou), `ok` (saída 0),
  `desconhecido` (o resto).
- **`heartbeat`** em `<run>.estado.json`, gravado com o deslocamento de fuso (ex.: `-03:00`, para quem lê de outro host) e regravado a cada `CEPA_RUN_HEARTBEAT` segundos
  (padrão 60) enquanto o `claude`, o build ou uma espera (reset de cota, sonda de rede)
  estão em andamento, com `item`, `tentativa`, `session_id` e `fase` do que está em voo. O
  `cepa-queue` usa a idade dele para reservas de OUTRO host (onde o pid não pode ser
  sondado): se existe um `*.estado.json` com o mesmo `host` e `arvore` da reserva, ela é
  `viva` só se o run está `rodando` e o heartbeat tem menos de `CEPA_HEARTBEAT_ORPHAN`
  segundos (padrão 900); senão é `orfa`. Sem esse arquivo vale a regra de 24h de antes.
  No mesmo host continua valendo a sonda de pid.
- **`item_pulado`** (`id`, `motivo: reservado`, `detalhe`): o item que a fila adiou porque
  uma reserva está em mãos de outro (viva, ou sem dono registrado e portanto indecidível). Uma vez por item por run.

O `cepa-until-digest` imprime `sessão` e `fim` em cada rodada e, num run `versao_registro >= 2`,
avisa quando algum `item_end` veio sem `session_id` ou `motivo_fim`.

## When it ends: the questions

The end of the run is a report of four panels and one line, in this order:

1. **Header** (`── ended at HH:MM · <reason>`): the stop reason and its detail, the window
   with its progress bar, one totals line (attempts, delivered, stuck, no progress, items for
   you, commits, cost), the run branch, and one row each for run-wide facts (inherited branch,
   usage cap, 5h quota waits, tight quota, network drops).
2. **Items (N)**: one row per item, with an icon, the id in an aligned column and the reason cut
   to the terminal width (the whole reason stays in the `.review.md` and in the `.estado.json`).
3. **Decisions (N)**, only when there are any: the choices the pre-read handed to the agent
   (`followed`) and the choices committed without asking (`decided`, with the commit), together
   and grouped by item.
4. **Next**, always last and numbered: the merge (`merge into <branch>` with its command, and
   "not recommended: <why>" when the run is not clean; or "merged ... by this run" after
   `--auto-land`), then the owner questions (ids, the first five questions, and the
   `cepa-until decide <queue>/<run>` command), then what the run state leaves with the owner
   (the plugin reinstall).
5. One dim line with the paths of the record, the log and the analysis.

The merge is named once, in Next. On a terminal the panels are cards with box-drawing borders
in the usual palette; without one (or with `NO_COLOR`) they are `── title` and indented rows.

The first three panels print as the run ends and Next after the analysis and the questions,
so it shows what is still open. On a terminal, between them, `cepa-until` asks the owner, one at a time, about everything that waits on them:
every deferred item that only the owner unblocks
(`blocked` from an outside condition, open `human_pending` route). Each item shows the closed
question the agent recorded with `cepa-queue finish --question` (or the one the
`/common:run-review` analysis wrote in its `cepa-decisoes` block), with the recommendation.
Each item is one block, with the full title, then labelled lines: why it stopped, the task left
to the owner, the analysis' `contexto` (lay words), the question, and `instrucao` (the technical
instruction the next run receives if the answer is yes, recorded together with the yes). A
question over 25 words or carrying a branch, test class or file name is shown anyway, with a
warning that the analysis broke the rules.

On a terminal each question waits up to 10 minutes (`CEPA_RUN_ANSWER_WAIT`, in seconds) for a keystroke; with none, the run prints the `cepa-until decide` command and exits, because an overnight run ends with nobody at the keyboard and a prompt without a limit left the process alive for days (PID 84993, 2026-10-07).

An answer is applied on the spot by `cepa-queue answer`: a `blocked` item goes back to
`pending` and an open route closes, with the owner's answer in the item's evidence, where the
next run reads it. `m` records the answer and keeps the item as it was (still `blocked`,
route still open), for answers like "keep it blocked". Enter leaves an item for later; `q`
stops asking.

A landing that ends green tags the landed commit `landed/<queue>/<run>` (the queue plus the
run's date and time), in the clone only: the tag is lightweight, so `git push` does not send it
even with `push.followTags`. It is the point to return to before a lot that touches a hook
(owner's decision on D4, `docs/reviews/2026-11-12-painel-lacunas-ecc.md`). A red build leaves no
tag, and a tag of the same name already on another commit is never moved.

**An answer can resume the same run (LL-1, 2026-11-10).** When the queue runs dry
(`end-of-queue`) with items waiting on the owner, the run is attached to a terminal and the
window still holds `--min-reserve`, the questions about those items come BEFORE the closing,
not after it. A yes that makes an item runnable puts it back into this same run: same branch,
same record (event `retomada_pelo_dono`), one `run_start` and one `run_end`. A no, Enter or
silence closes the run as before, and an item asked there is not asked again at the end (the
landing question still comes at the end, after the analysis). While the panel waits, the
state carries `fase: aguardando-dono`. Why: of 37 queue-empty runs measured, the owner answered
before the deadline in 5, always minutes after the end and at this terminal; 4 were relaunched
by hand (3h11 of gaps) and 1 was not (11.1h of window left) (`docs/estrategia-loops-longos.md`
section 4.1). No process sleeps waiting and no notice is sent: the panel already runs in the
supervisor's own process. `--no-resume-on-answer` turns it off.

`responde` refuses without a terminal: a `claude -p` subprocess has no TTY, so an agent cannot
close a human route in the owner's place. It also refuses a text that does not answer the
question (a "não entendi", a question back), showing the route's question, and it commits the
`queue.yaml` in the same step, so the queue is never left dirty for the next run's guard
(`--no-commit` writes without committing and says so). Without a terminal (`nohup`, cron) the run prints
the same list and the command to come back: `cepa-until decide <fila>/<run>`.

`cepa-until decide <fila>`, with no run, goes over the whole queue: every item a run skips
because it waits on the owner, plus the `done` items that still carry a task only the owner
does (create a role, validate by hand). Each card has `[d]`: on a pending or blocked item it
takes the item out of the queue (`dropped`); on a delivered one it closes the leftover task as
no longer needed. `sim` always means "back to the queue", so it cannot stand for "discard".

Items that ask the same question are asked once. Two items are "equal" when both carry a
proposed waiver (`.claude/waivers/*.yaml`, `status: proposta`) with the same `motivo`, or,
failing that, when both WRITTEN a question and the text is the same after collapsing whitespace
and case (and the route kind is the same). Delivered items (a leftover route after delivered
work) and blocked items are never in the same group, since `[y]` means something else for each:
for a delivered group it closes the task and leaves the work as it is. An item with no written question is never grouped by
text: the default question of the panel is not "the same question", the route text is what the
owner is asked, and it differs. `cepa-until decide` and `decide --all` show each group first as ONE
card, across queues too: it says how many items share the question, what they have in common,
lists the members and offers `[y]` yes to all, `[n]` no to all, `[a]` accept each item's own
recommendation (the "Recomendo sim/não" of its question; an item with none is asked one by one
afterwards), `[o]` ask them one by one, Enter for later and `[q]` to quit. Each member records
its own answer in its own queue, with the note `(respondida em grupo de N)`; one optional line
of comment is appended to all of them. Without a terminal the listing prints a group as a
single entry with the count and the ids. The launch panel of a run does not group.
`cepa-queue status` says which `pending` items are ready (the next run takes them) and which wait
on the owner or on another item; readiness is derived from the same rule the run uses, never
stored.

## What `cepa-until land --yes` prints

A header first: `land <run branch> → <destination>`, then `commits` (how many the run branch
brings, and whether it is a fast-forward: the run's own records commit, `until <queue>/<run>:
...`, does not count as the destination moving), `return point` (the destination's commit
before the merge, the one `git reset --keep` goes back to), and the effect, build, push and
install lines. Then three numbered steps, each with its result and duration: `[1/3] merge`
(`done: <sha> (Ns)`, `CONFLICT`, or `already done` when resuming), `[2/3] full build`
(`green`, `RED`, or `skipped` when the run waived the build) and `[3/3] push` (`done`,
`FAILED`, `not run` after a red build, or `skipped` with no upstream). When the run worktree
held files outside git, they are listed with where each goes: `move to <path>` when the clone
lacks it, `delete (same as <path>)` when the clone has the same bytes, or `compare with
<path>` when it differs; the copies wait in `.claude/rescued/<branch>/`. The last line is
`landed at HH:MM: ... run worktree and branch removed`.

## Hook that only counts after reinstalling

Hooks and plugin `bin/` run from the plugin cache, a copy of the clone at the last install, not from the night branch. By default the supervisor only warns (`hook_so_apos_reinstalar`) and charges `reinstalar-plugin` at the end.

Exception, in the cepa repo only (`.claude-plugin/marketplace.json` named `cepa` plus
`bin/install.sh`; owner decision X4, DUR-3): when an item closes `done`, its full build is
green, and it touched `<plugin>/hooks/**` or `<plugin>/bin/**` (both run from the cache),
the supervisor runs `sh bin/install.sh --clean` from the night worktree. `--clean` moves the
current cache to `<cache>.prev`, the point `bin/install.sh --rollback` returns to. The record
gains `hooks_reinstalados` (`sha_antes`, `sha_depois`: a content digest of the installed
`hooks/` and `bin/`, since the cache is not a git repo) and every `item_start` carries
`hooks_sha`, the digest in force. If the install fails the supervisor runs
`bin/install.sh --rollback` by itself and records `reinstalacao_desfeita`; the item stays
`done` and the night goes on. If not even the rollback gives the cache back, the run ends
with `reinstalacao-falhou`. Installing from the worktree re-points the marketplace
registration to the worktree path: after `aterrissar`, run `bin/install.sh` from the main
clone so it points back; `land --yes` does that by itself in the cepa repo, after the merge and the green build, and records `instalado_no_pouso`. The exception: if `~/.claude/ops/last-install.json` says `repo_dir` is the worktree of another run that is still alive (state `rodando`, live supervisor), the install is skipped so the plugins are not pulled from under that run. The landing records `instalacao_adiada` (the other run, its worktree, when), prints under "Fica com você" the request to run `sh bin/install.sh` in the clone when that run ends, and keeps its exit code. If the install itself fails, the landing runs `sh bin/install.sh --rollback` from the clone, records `reinstalacao_desfeita` (`ok` says whether the rollback went through, `motivo` why the install failed), and prints under "Fica com você" the request to run `sh bin/install.sh` in the clone by hand, with the path of the run's `.log`. If the rollback fails too (the real installer says "Nothing to roll back to" when no `--clean` ever left a rollback point), it says the plugins may be half installed and points at `/common:doctor`. The merge stands and the exit code is still 0 in every one of these cases. Open sessions keep the old hooks in memory until restarted. Two
reinstalls in one night keep only the previous cache in `.prev`. Without `--verify` there is
no build, so no reinstall: only the warning above. With less than 120 s left in the window the supervisor does not start the install (killing it halfway would leave the cache half moved): it records `reinstalacao_adiada` and falls back to the warning. In any other repo nothing changes.

## Quem lê o estado: `_state.py` (DUR-4)

O estado vive em cinco depósitos, e só neles: a fila (`queue.yaml`, ou `plan.yaml` no layout legado), o registro do run (`until/<run>.jsonl` e `<run>.estado.json`), o handoff por branch, as sessões vivas (`.claude/sessions/`) e o estado do modo autônomo (`docs/autonomous/<run>/state.yaml`). O módulo `common/hooks/_state.py` é o leitor único deles (só lê, nunca cria depósito) e traz o catálogo de tudo o que existe em `.claude/`. `next` (via `cepa-queue`), `doctor` (`cepa-doctor`), `run-review` (`cepa-until-digest`) e `whereami` (`cepa-intent`) importam o módulo. O `cepa-doctor` avisa na área `estado` quando aparece em `.claude/` uma entrada que o catálogo não conhece, e `tests/test_state_deposits.py` fica vermelho se alguém escrever em `.claude/<nome>` sem declarar o nome. A regra de vida de um run é uma só (`run_liveness`): `rodando` só conta como vivo com heartbeat recente (até `CEPA_HEARTBEAT_ORPHAN` segundos, padrão 900) e, na mesma máquina, com o pid respondendo; heartbeat velho é `morto`, e um registro `rodando` sem heartbeat (anterior ao DUR-1) é `desconhecido`, nunca `vivo`. O `cepa until pendentes` ainda tem a sua própria classificação de "mortos" (pid e prazo) e não usa essa regra.

## Before you leave it running

- **The tree must be clean.** It refuses a dirty working tree, because otherwise nothing
  separates what the run did from what was already there. `/common:doctor` warns about this
  when you open the session, so you don't find out at 11 p.m. `--dirty-ok` overrides it. If
  files show as deleted and you did not delete them, find out why before overriding.
- **Permissions are off by default** (decision 4 above). The gates still apply inside each
  subprocess: red build blocks commit, cards need acceptance evidence, verdicts are computed.
- **Use `--dry-run` first.** It prints the schedule of the run and exits.
- **On a terminal the output is decorated**: colour, one block per item with a bar of the
  window spent so far, a line that redraws every 30 s while the `claude` subprocess runs, and
  the item title cut to the terminal width (`--full-title` keeps it whole; the `.jsonl`
  always has it). Off a terminal (`nohup`, a file, `NO_COLOR`) the output is byte for byte
  the plain one; `CEPA_RUN_COLOR=sempre|nunca` forces either way.

Proof of the tool itself: [`docs/proof/cepa-until.yaml`](proof/cepa-until.yaml) and
[`docs/proof/cepa-until-cota.yaml`](proof/cepa-until-cota.yaml).
