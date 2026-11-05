# cepa and its terminal subcommands

Reference for the terminal side of the harness: the `cepa` launcher and the
`cepa-*` scripts in `common/bin/`. Slash commands (`/common:queue`,
`/board-flow:prove`...) are in [commands.md](commands.md); this page covers only
what you type in a shell.

Every script answers `--help`. `cepa <subcommand> --help` and
`cepa-<subcommand> --help` are the same thing: the launcher just runs
`common/bin/cepa-<subcommand>` with the rest of the arguments. The scripts are
self-contained Python 3 files; the design notes at the top of each one remain
the source of truth, and this page is the condensed map.

## The launcher: `cepa`

`cepa` replaces `claude` and does one extra thing: if another live session
already occupies this working tree, it isolates the new one in its own git
worktree (`session/<name>`) so the two cannot collide. Without a conflict it
starts a normal session in place.

| Form | What it does |
|---|---|
| `cepa` | Opens a session; isolates into a worktree only if needed. |
| `cepa <subcommand> [args]` | Runs `common/bin/cepa-<subcommand>`. A lone word within two typos of a subcommand (`cepa untl`) is refused with the nearest name instead of becoming the first prompt. |
| `cepa help`, `cepa --help`, `cepa -h` | Lists the subcommands (one line each, read from the script's header) and the launcher flags. |
| `cepa -s <name>` / `--slice <name>` | Forces or resumes the worktree `session/<name>`. Without a name, offers a menu of recent worktrees to resume. |
| `cepa -m <mode>` / `--mode <mode>` | The session's work mode. `--mode help` lists the purpose of each mode and exits. See [modos-de-trabalho.md](modos-de-trabalho.md). |
| `cepa --budget <scope>` | The closed budget the `refactor` mode requires. |
| `cepa --purpose "..." --by-when "..." --plan "a" "b"` | Records the session intent at launch (same fields as `cepa-intent write`). |
| `cepa --prompt <name\|path>` | Appends a custom system prompt. `--prompt-substitui` replaces the whole default prompt; see [system-prompt-customizado.md](system-prompt-customizado.md). |
| anything else | Goes straight to `claude` (`cepa --resume`, `cepa WEGO-123`). |

On launch the launcher runs `cepa-doctor --fix --brief --if-stale 12` as a
silent preflight: nothing is printed unless something needs you.

## The subcommands, by what you are doing

| You want to... | Command |
|---|---|
| Check the harness installation | `cepa doctor` |
| Know what mode you are in and what closes it | `cepa modes`, `cepa modes --exit` |
| Record or advance the session's intent | `cepa intent` |
| Write, inspect or reconcile the single-track queue | `cepa plan <subcommand>` |
| Run the queue unattended for a time window | `cepa until <queue> --for 12h` |
| Read what an unattended run left for you | `cepa until decide <queue>/<run>`, `cepa until pendentes` |
| Summarise an unattended run for a review | `cepa until-digest <run>.jsonl` |
| Prove the Jira Review column for a time window | `cepa prove --for 3h` |
| Complain about the harness without leaving the task | `cepa feedback add "..."` |
| See the harness's own numbers | `cepa metrics`, `cepa metrics scorecard` |
| See where a session's time or tokens went | `cepa clock`, `cepa tokens` |
| Ask the autonomy file whether an action asks or does | `cepa autonomy classificar ...` |
| Gate a parallel-waves plan before forking | `cepa dor <plan.yaml>` |
| Find a repo's registry files before planning waves | `cepa hotspots <repo>` |
| Measure test coverage of a conversational command | `cepa promptcov <cmd.md> <test.py>` |

`cepa intencao` and `cepa modos` are the old names of `intent` and `modes`;
they still work and are listed as aliases.

## Conventions shared by every script

- **Human output in pt-BR, `--json` for code.** Reports, questions and menus
  are printed in Portuguese; every script that a hook or command consumes has a
  `--json` flag with stable keys (some keys keep pt-BR names, such as
  `relogio_s` or `entrada`, because the telemetry ledger already uses them).
- **English flags with pt-BR aliases.** `--all`/`--todas`, `--yes`/`--sim`,
  `--no-color`/`--sem-cor`, `--purpose`/`--proposito`. Both spellings are
  accepted; the English one is the documented one.
- **`--repo DIR`** on anything that reads a repository (default: the current
  directory). **`--dry-run`** on anything that writes or launches.
- **Exit codes mean something.** `0` ok; `1` a soft verdict (warnings,
  uncovered, insufficient history); `2` invalid usage or refused; higher codes
  are documented per script below.
- **Refusals name the reason.** A script never writes half a thing: a rule
  that fails (empty `why`, a `blocked` item without a question, a plan with a
  blocking cycle) refuses before touching the disk, and says which rule.

## Reference, one section per script

### `cepa-autonomy`

Queries the autonomy bands in `common/autonomy.yaml`, the file that decides
"ask or do" instead of the agent of the turn. `/board-flow:decide` uses it to
classify an action before turning it into a question for the owner.

```
cepa-autonomy listar [--repo DIR] [--json]
cepa-autonomy classificar (--bash CMD | --mcp TOOL | --path P [--op OP] | --slash S | --id ID)
                          [--cond KEY=VALUE ...] [--repo DIR] [--json]
```

Bands: `executa_e_reporta` (do it and report one line), `sempre_pergunta`
(goes into the owner's batch of questions), not listed (ask, and propose the
id). Exit `0` whenever the query ran, `2` on an invalid argument.

### `cepa-clock`

Where a session's wall clock went: active wait (a Bash command blocked without
working, which `no-busy-wait.py` now forbids), build, other. Reads the
transcript in `~/.claude/projects/<slug>/` plus one file per subagent, and
merges overlapping intervals so parallel agents do not count the same minute
twice.

```
cepa-clock [--slug SLUG] [--all] [--days N] [--emit] [--json]
```

Absolute minutes are the reliable number; percentages are only comparable
between unattended runs, because an interactive session's clock includes the
time it waited for you. `--emit` also writes to the telemetry ledger.

### `cepa-doctor`

Validates the installation against reality in 30 seconds. Global checks:
`settings.json` parses, plugins enabled and at the installed version, every
cached hook compiles, telemetry writable, open sessions running hooks from a
version the cache no longer has. Project checks: git repo, `board-flow.yaml`
structure, build baseline status and age, stale or orphan `session/*`
worktrees, an agent worktree forgotten inside the repo, handoffs older than
30 days, queue diverging from `BACKLOG.md`, unattended runs waiting for the
owner or with a dead supervisor, the environment manifest's ports and
containers, the `twg` version.

```
cepa-doctor [--fix] [--brief] [--projeto] [--if-stale H]
```

`--fix` applies the mechanical corrections (reinstall plugins, archive an
expired handoff, prune an orphan worktree) and leaves the decisions to you.
`--brief` prints one line, or nothing when there is nothing to say; with
`--if-stale H` it only runs when the last diagnosis is older than H hours.
That pair is the launcher's preflight. The live check against Jira is not
here (no MCP in a script): `/common:doctor --live` delegates it. Exit `0` all
ok, `1` warnings, `2` failures. See [harness-ops.md](harness-ops.md).

### `cepa-dor`

Definition of Ready for the slices of a parallel-waves `plan.yaml`: `READY`
or `NOT-READY` per slice, with the gaps named. Read-only; the intake gate that
`/maestro:program-plan` iterates with you.

```
cepa-dor <plan.yaml> [--wave N] [--fork-point REF] [--repo DIR] [--json]
                     [--enforcement-zone GLOB ...]
```

Checks: schema version and `mode: parallel-waves` (a single-track queue is
refused); at least four demands; surfaces disjoint from the other slices on
the plan's registry files (an intersection elsewhere is a warning, not a
veto); nothing inside the enforcement zone; an acceptance criterion (an
executable `acceptance_cmd` in a `.claude/no-build` repo); an observable
Given/When/Then or a declared `acceptance_form: substrate`; no open
strategic decision; minimum context; green baseline at the fork point. Exit
`0` all READY, `1` READY with warnings, `2` some NOT-READY or invalid plan.
See [maestro.md](maestro.md).

### `cepa-feedback`

The harness's own complaint notebook. The ledger is global
(`~/.claude/cepa-feedback/feedback-YYYY-MM.jsonl`, `CEPA_FEEDBACK_DIR`
overrides) and append-only; repo, branch and session mode are captured for
you; the text is stored verbatim.

```
cepa-feedback add "<text>" [--target X] [--origin comando|skill|hook|manual] [--repo DIR] [--json]
cepa-feedback list [--status aberto|triado|todos] [--repo NAME] [--max N] [--json] [--no-color]
cepa-feedback triage <id> --destination "<where>" [--note ...] [--queue QUEUE --why ...] [--repo DIR]
```

`triage --queue` also appends the item to a single-track queue through
`cepa-plan add`. Exit `0` ok, `2` invalid usage, `3` unknown id, `4` already
triaged. The slash command is `/common:feedback`.

### `cepa-hotspots`

Measures a repository's registry files ("arquivos-cartório"): the files
almost every demand writes to, which a wave plan must declare in
`cartorios:` so `cepa-dor` can veto overlapping surfaces. Method: replay each
pair of real merges of the history with `git merge-tree`, count a point per
file that conflicts, rank. Without enough history it returns an empty list
and says why, never a heuristic.

```
cepa-hotspots <repo> [--ref REF] [--min-pairs N] [--limit N] [--json]
```

Exit `0` list produced (even empty), `1` insufficient history, `2` error.

### `cepa-intent`

The single writer of `.claude/session-intent`: purpose, stopping point, a plan
of one to six steps, and the cursor. Readers: `/common:whereami`,
`/common:next`, `/common:recap` and the session hook.

```
cepa-intent write --purpose "..." --by-when "..." --plan "step 1" "step 2" [--reason ...]
cepa-intent --step N                  # step N is now in progress; M+1 = plan fulfilled
cepa-intent --purpose "..." --reason "..."
cepa-intent --plan "a" "b" [--reason ...]
cepa-intent [show] | continue | state | close
```

Rules: a plan item has no `:`; with `write`, the action comes before `--plan`
(which consumes everything up to the next option); `--purpose` and a rewrite
over an existing intent require `--reason`; `continue` adopts another
session's intent; `state` and `close` only read. The old action names
(`gravar`, `mostrar`, `continuar`, `estado`, `encerrar`) and option names
(`--proposito`, `--para-quando`, `--plano`, `--passo`, `--motivo`) still
work. Exit `0` ok, `2` invalid usage or writer rule refused, `3` no intent
recorded, `4` an intent exists and `--reason` is missing. See
[estrategia-intencao-da-sessao.md](estrategia-intencao-da-sessao.md).

### `cepa-metrics`

Aggregates the telemetry ledgers (`~/.claude/cepa-telemetry/events-YYYY-MM.jsonl`)
into a readable report: sessions per repo, gate blocks by reason, build
trend, proof verdicts, turns before and after a routine.

```
cepa-metrics [--days N | --month YYYY-MM] [--repo NAME] [--json]
cepa-metrics scorecard [--json]
```

`scorecard` prints the three scorecard numbers (turns after a routine, red
builds, sessions in the cepa repo) in three windows, each with its
arithmetic. The slash command is `/common:metrics`.

### `cepa-modes`

The table of work modes, from `common/hooks/_modes.py`, the same source the
session hook reads. For each mode: what it is for, what it enters with, what
it produces, what closes it, and the mechanical gate.

```
cepa-modes [<mode>] [--purposes] [--exit] [--json] [--no-color]
```

`--exit` is the exit verdict of this session's mode, read from the disk: `0`
closed, `1` still open, `2` the mode has no mechanical verdict. The slash
command is `/common:modes`; the design is in
[modos-de-trabalho.md](modos-de-trabalho.md).

### `cepa-plan`

The mechanical writer of the single-track queue,
`.claude/queues/<name>/queue.yaml`, the document that keeps the order of the
items and the `why` of each position. `/common:queue` holds the conversation
and hands the list here; `/common:drain-plan` and `cepa-until` execute it;
`/common:next` and `/common:queue-status` read it. It only knows
`mode: single-track`; waves belong to `/maestro:program-plan`.

| Family | Subcommands |
|---|---|
| Sources (read only, return JSON) | `from-spec <spec.md>`, `from-epic <epic.md> --cycle N`, `from-triage <handoff.json\|->` |
| Writing | `write <name> (--items F \| --from-spec F \| --from-epic F --cycle N \| --from-triage F) [--source ...] [--when YYYY-MM-DD] [--on-missing refuse\|keep\|drop] [--dry-run]`, `add <name> <id> --title ... [--before ID --why ...] [--blocked-by ID,ID]`, `migrate [<name> \| --all] [--dry-run]`, `check-name <name>`, `validate <file>` |
| Reading | `queue <name> [--max N]`, `ready`, `status [<name>] [--status S]`, `show <name>`, `epics [--brief]`, `promote <name> [--when ...]`, `order <name> --keys K1,K2` |
| One item's cycle | `start <name> <id> [--commit]`, `finish <name> <id> --status done\|blocked\|pending --evidence ... [--human-pending ROUTE] [--question ...] [--pedido\|--pronto\|--impede\|--se-sim\|--se-nao TEXT] [--commit]`, `answer <name> <id> --answer ... [--keep \| --drop] [--force] [--author ...] [--no-commit]` |
| Against the Jira board | `reconcile <name> --board FILE [--apply]`, `landed --board FILE [--into REF]`, `divergence <name> [--board FILE] [--backlog FILE]` |

`ready` is the repo-wide view: the items a run would take now, across
every single-track queue, each in its recorded order; `status` answers
the same for one queue.

What it refuses, by design: an empty `why`, a duplicate id, a `blocked_by`
pointing at a ghost item, a blocking cycle, writing a queue over a waves plan
(`check-name` exit `3`), `finish --status done` with an empty build
(`.claude/last-build.json` that matched zero tests) or without a
`READY-TO-SHIP` validation when the topology has a validation-lead, closing
a `human_pending` from anywhere but `answer` in a terminal, and demoting a
`done` item during `reconcile`. `answer`, `add` and `write` commit the queue
file by themselves unless `--no-commit`. Every subcommand has its own
`--help`. See [execution-plan.md](execution-plan.md).

### `cepa-promptcov`

Coverage of annotated checkpoints in a conversational command. A command's
behaviour blocks are tagged `**[tag:id]**`; a test's checks embed the same
`[tag:id]` in their name; the script flags every id no check references.
With no tag in the command it says there is nothing to measure, never 100%.

```
cepa-promptcov <command.md> <test.py> [--tag TAG] [--json]
```

Exit `0` every checkpoint covered, `1` some uncovered, `2` error. See
[promptcov.md](promptcov.md).

### `cepa-prove`

Proves the Jira Review column for a time window, one card per subprocess:
each round runs `claude -p "/board-flow:prove-drain --max 1 --skip <keys
already handled>"` in a fresh process until the window closes or the column
is empty. The supervisor never talks to Jira; it keeps the clock, the
circuit breaker, the quota pause, the log, the list of keys already handled,
and reads each round's outcome from `docs/proof/<KEY>.yaml`, which it
commits on the current branch (`proof: <KEY> <VERDICT>`).

```
cepa-prove (--for 3h | --until 07:00) [--repo DIR] [--max N] [--max-failures N]
           [--min-reserve 20m] [--slack 30m] [--scope JQL | --no-scope]
           [--with-permissions] [--no-commit] [--dirty-ok] [--dry-run]
```

The cut happens between rounds, never mid-proof. The run's record is
`.claude/prove/<run>.jsonl`. See [proof-gate.md](proof-gate.md).

### `cepa-tokens`

How many tokens a session spent, and on whom. Same source as `cepa-clock`;
each `message.id` counted once, by the `usage` of its last line. Four numbers
per response: `entrada` (uncached input), `cache_w` (written to cache),
`cache_r` (read from cache), `saida` (output). "New context" is `entrada +
cache_w`, the number that grows when a large file enters the conversation;
tool results are also sized in characters so you can see what entered.

```
cepa-tokens [--file FILE.jsonl] [--all] [--days N] [--emit] [--json]
```

### `cepa-until`

Runs the repo's single-track queue for a time window with nobody awake. One
item per subprocess (`claude -p "/common:drain-plan <queue> --max 1"`), inside
the `until/<run>` worktree the supervisor opens at launch; a full build after
every `done` item (red: the item becomes `blocked` and the branch goes back);
circuit breakers on consecutive failures and consecutive `blocked` items; a
pause for the account's 5-hour quota. Nothing goes to `main` or `origin`.

```
cepa-until <queue> (--for 12h | --until 07:00) [--repo DIR]
           [--max-failures 3] [--max-blocked 3] [--attempts-per-item 2]
           [--min-reserve 45m] [--slack 60m] [--with-permissions] [--dirty-ok]
           [--verify CMD | --no-verify] [--no-analysis] [--full-title] [--dry-run]

cepa-until pendentes [--repo DIR] [--json]       runs waiting for the owner, dead supervisors
cepa-until decide <queue>[/<run>] [--repo DIR]   one closed question at a time, applied on the spot
cepa-until aterrissar <queue>/<run> [--yes]      merge + full build + push to the clone's branch
cepa-until fecha-morto <queue>/<run> [--yes]     the build a dead supervisor never ran
```

Full design, with the dated decisions, in [cepa-until.md](cepa-until.md).

### `cepa-until-digest`

The summary of a `cepa-until` run that fits in one session. The run's `.log`
is stream-json of every subprocess and runs past 10 MB; this script chooses
mechanically what to read and says what it chose: the whole ledger, each
round's final report (`--result-max` characters), agent calls by type, tool
errors, cost, the process signals (a worktree opened by anyone other than the
proof-reviewer, a build gate bypassed with another module's green), the tail
of each supervisor build, and the current status and evidence of every item
touched. `/common:until-review` interprets it; this script does not opine.

```
cepa-until-digest <run>.jsonl [--result-max 3000]
```

Exit `0` ok, `2` the ledger does not exist.
