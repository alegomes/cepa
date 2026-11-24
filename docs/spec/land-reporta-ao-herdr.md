# Especificação: cepa-until land reports its status to the Herdr desktop app

**Status:** ready-to-build
**Aberta em:** 2026-11-24    **Fechada em:** 2026-11-24
**Fontes lidas:** common/bin/cepa-until (`_hc_status`, `_hc_title`, `herdr_report`, `herdr_blocked`, `herdr_release`, `_decide_reporting`, `cmd_land`, `_cmd_land`, `main`), docs/spec/herdr-agent-status.md

## Como chegamos aqui
"O cepa-until land não cria um working agent no Herdr" (owner, 2026-11-24, with a screenshot of `cepa-until land all/2026-11-24-1139 --yes` 32 minutes into the full build while the Agents panel listed only idle agents).

## Problema
`cepa-until land <queue>/<run> --yes` merges the run branch, runs the full build (about 30 minutes in this repo), pushes and installs. During all of it the Agents panel of the Herdr desktop app shows nothing for that terminal, so the owner cannot tell from the panel that a landing is running, nor that it ended or stopped on a red build. The earlier spec (`docs/spec/herdr-agent-status.md`, "Não entra") left `land` out on the grounds that the subcommands "are short and interactive", which is false for a landing with a full build.

## Escopo
### Entra
- `cepa-until land <queue>/<run> --yes` reports `working` to the Herdr desktop app from the moment the landing starts, with the step in progress in the terminal title: merge, full build, push, install.
- The landing's ending is reported: Done when everything went through, "Needs you" when it stopped on a step or when the plugin install was left for the owner.
- `cepa-until close-dead <queue>/<run> --yes` reports the same way around its full build.
- `cepa-until pending` reports `working` only while it closes a landed run and reinstalls the plugins, and drops the row when it exits.
### Não entra
- `land` and `close-dead` without `--yes`: they only print the plan, nothing ran.
- `cepa-until decide`: it already reports, and a landing started from inside it keeps that reporting.
- The `herdr` command-line multiplexer (`herdr pane report-agent`): the owner works in the desktop app.
- Changing what the main run reports, or the Agents panel itself (`~/.config/herdr-app/mods/agents/main.js`).
- A "Needs you" row from `pending` when runs wait for the owner: the owner chose the row dropped at the exit.

## Estado e migração
Nada in files: the status is an escape sequence written to the terminal (OSC 7501 for the state, OSC 2 for the title). No file, record or queue format changes. The line of `docs/spec/herdr-agent-status.md` that leaves `pending|decide|land|close-dead` out ("they are short and interactive") is superseded by this spec for `land`, `close-dead` and `pending`; the docstrings in `common/bin/cepa-until` that say "the subcommands never report" stop being true and are rewritten with the code.

## Critérios de sucesso

In every criterion "the terminal" is a pseudo-terminal with `HC_TERMINAL_ID` set, which is how a terminal of the Herdr desktop app looks to the program; "status" is the OSC 7501 sequence (`ESC ] 7501 ; state=...:app=cepa-until:msg=<base64> ESC \`) and "title" is the OSC 2 sequence, both read from the bytes the command wrote to that terminal.

### CS-1: While `land --yes` runs, the terminal is a `working` agent whose title names the step in progress
**Surface:** cli
**Red test:** `cepa-until land q/<run> --yes` in the terminal, on a run waiting for the owner with a green build and an upstream, writes status `state=working` and the titles `q: landing, merge`, `q: landing, full build` and `q: landing, push`, in that order, each before the `[n/3]` line of its step; in the cepa repo it also writes `q: landing, install` before the install. Today the output has no OSC 7501 and no OSC 2.

### CS-2: A landing that went through ends in Done
**Surface:** cli
**Red test:** the CS-1 landing ends with status `state=done` and title `q: landed` as the last status and title written, and exit code 0. Today nothing is written.

### CS-3: A landing that stopped ends in "Needs you" naming the step
**Surface:** cli
**Red test:** (a) with a merge conflict the last status is `state=blocked` and the title `q: landing stopped, merge conflict`; (b) with a red build, `q: landing stopped, build RED`; (c) with a refused push, `q: landing stopped, push failed`; (d) with the command killed by SIGTERM during the build, `state=blocked` and `q: landing stopped by SIGTERM`; (e) with Ctrl+C (SIGINT) during the build, the last status is `state=clear` and the last title is empty. The exit codes are the ones of today. Today nothing is written in any of the five.

### CS-4: A landing whose plugin install was left for the owner ends in "Needs you"
**Surface:** cli
**Red test:** in the cepa repo, a landing with merge, build and push green whose install was skipped (`instalacao_adiada`) or rolled back (`reinstalacao_desfeita`) ends with status `state=blocked` and title `q: landed, install waits for you`, exit code 0. Today nothing is written.

### CS-5: `close-dead --yes` reports like a landing
**Surface:** cli
**Red test:** `cepa-until close-dead q/<run> --yes` in the terminal on a dead run writes status `state=working` with title `q: closing, full build` before the build; with a green build the last status is `state=done` and the title `q: run closed, waiting to land`; with a red build, `state=blocked` and `q: closing stopped, build RED`. Today nothing is written.

### CS-6: `pending` is `working` only while it closes a landed run, and drops the row at the exit
**Surface:** cli
**Red test:** (a) `cepa-until pending` in the terminal, in the cepa repo, with one run already landed upstream and not yet closed, writes status `state=working` with title `closing landed run <run>, install` before the install and ends with `state=clear` and an empty title; (b) with nothing to close it writes no status and no title at all. Today (a) writes nothing.

### CS-7: Where nothing ran, or nobody is looking at a Herdr terminal, not one byte is written
**Surface:** cli
**Red test:** the output has no OSC 7501 and no OSC 2 in each of: `land` without `--yes`; `close-dead` without `--yes`; `land --yes` refused before the merge (run not waiting for the owner, uncommitted changes in the clone, run already landed); `land --yes`, `close-dead --yes` and `pending` with stdout piped; the same three in a pseudo-terminal without `HC_TERMINAL_ID`; `pending --json`. This test passes today and must keep passing after CS-1 to CS-6: it is the guard, and it goes red if the reporting is wired before the `--yes` check, before the refusals or around the tty rule.

## Perguntas em aberto
- [x] When the landing ends well (merge, green build, push, install), what does the panel show: the row moved to Done, or the row dropped? — Row in Done, title `<queue>: landed` (owner, 2026-11-24).
- [x] When the landing stops on a conflict, a red build or a failed push, what does the panel show: "Needs you" with the step that failed, or the row dropped? — "Needs you" with the step that failed (owner, 2026-11-24).
- [x] Does this cut cover only `land --yes`, or also the other subcommands that can run long (`close-dead`, `pending`)? — All subcommands: `land`, `close-dead` and `pending` report (owner, 2026-11-24, against the recommendation of `land --yes` only).
- [x] Does the title name the step in progress (merge, full build, push, install), or stay one fixed text for the whole landing? — The step in progress (owner, 2026-11-24).
- [x] `pending` on a terminal: what does the panel show when it exits? — `working` only while it closes a landed run and reinstalls, and the row is dropped at the exit (owner, 2026-11-24).
- [x] The landing went through but the plugin install was skipped or rolled back (the screen asks for `sh bin/install.sh` by hand): Done or "Needs you"? — "Needs you", title `<queue>: landed, install waits for you` (owner, 2026-11-24).
- [x] `land` and `close-dead` without `--yes` (plan only): silent, or do they report too, now that every subcommand reports? — Silent (owner, 2026-11-24).

## Decided without asking
- Only the Herdr desktop app is reported to (OSC 7501 and the title); no call to the `herdr` command-line multiplexer (`herdr pane report-agent`) — same cut as `cepa-until decide`, and the owner works in the desktop app. Vete aqui se discordar.
- The owner's Ctrl+C during a landing drops the row (`state=clear`, empty title) — same as the main run. Vete aqui se discordar.
- Same writing rules as today: only inside a Herdr desktop terminal (`HC_TERMINAL_ID` set) and only when stdout is that terminal; a piped or captured landing stays byte-clean. Vete aqui se discordar.
- `close-dead --yes` follows the same rules as `land --yes`: `working` with the step in the title while the full build runs, Done on green (`<queue>: run closed, waiting to land`), "Needs you" on red — it is the same full build with the same two endings. Vete aqui se discordar.
- A refusal before the work starts (run in the wrong state, uncommitted changes in the clone, run already landed) reports nothing — it returns at once, with the owner at the terminal. Vete aqui se discordar.
- A landing or a `close-dead` that dies on an exception or a SIGTERM ends in "Needs you" (`state=blocked`, not `state=error`) — the panel draws `error` as a transparent dot among the idle rows, the reason the main run already uses `blocked`. Vete aqui se discordar.
- `pending --json` reports nothing even on a terminal — its stdout is JSON for code and nothing else. Vete aqui se discordar.
- For an `--all` run the title prefix is `all`, the queue part of the target as typed (`all/2026-11-24-1139`) — same label `decide` uses. Vete aqui se discordar.
- The Done or "Needs you" row stays until the next program in that terminal writes a status or a title — same as the main run's `<queue>: finished`. Vete aqui se discordar.
- A landing triggered from inside `cepa-until decide` keeps the reporting `decide` already does; this spec does not change it. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- CS-7 is a guard that is green today; the proof that it bites is breaking the `--yes` check or the tty rule and seeing it go red.
- The Agents panel itself cannot be read by the agent: verification goes through the `status` field of `hc get <terminal> --json`, not through the drawn panel.
