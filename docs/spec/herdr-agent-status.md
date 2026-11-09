# Specification: herdr shows `cepa until` and `cepa prove` as running agents

**Status:** ready-to-build
**Opened on:** 2026-11-09            **Closed on:** 2026-11-09

**Sources read:** `common/bin/cepa-until` · `common/bin/cepa-prove` · `tests/test_cepa_until.py` · `tests/test_cepa_prove.py` · `~/.claude/hooks/herdr-agent-state.sh` (herdr's Claude integration, v7) · herdr 0.9.5 docs "Add Herdr support to your agent" and "CLI reference" · `BACKLOG.md` (spike 2026-07-11, gap "`agent_status` stays `unknown` for headless children")

## Como chegamos aqui (how we got here)
On 2026-11-09 the owner asked: "O herdr não identifica quando o cepa está rodando sem uma sessão interativa do Claude. [...] É possível?" The session proved it is, in a throwaway herdr tab, and the owner approved: criteria per state, label `cepa-until` / `cepa-prove` with the current item in the message, no resume command. The heading keeps the Portuguese name because `spec-readiness-gate` only accepts that one.

## Problem
herdr recognizes an agent by its process or by reading its screen. `cepa-until` and `cepa-prove` are Python supervisors that run `claude -p` (no TUI), and herdr's Claude hook only reports the session id, never the state. The pane stays `unknown`, so a window that runs for hours looks idle in the sidebar and in `herdr agent list`.

## Evidence (feasibility, 2026-11-09, herdr 0.9.5)
- A script in a fresh pane called `"$HERDR_BIN_PATH" pane report-agent "$HERDR_PANE_ID" --source cepa-until --agent cepa-until --state working --message "item 2/5" --seq <ts>`. `herdr agent list` showed `cepa-until working`, then `cepa-until blocked` after a second report, and the pane went back to `unknown` after `pane release-agent`.
- Same script with a real `claude -p "responda apenas: ok"` running as its child: the label stayed `cepa-until working` for the whole call. The Claude hook only stored its session id (`agent_session.agent = claude`) and did not take the pane.
- A report sent from a pane sitting at its shell prompt is accepted (`{"type":"ok"}`) and cleared at once. herdr's docs say the same: it clears the agent when the pane is back at its idle shell prompt. So the reports must come from the long-running supervisor itself.

## Scope
### In
- `cepa-until` (the window, not its subcommands) and `cepa-prove` report `working` while they run, with the current item in `--message`, and release the pane on every exit path.
- Reports only when `HERDR_ENV=1`, `HERDR_PANE_ID` and `HERDR_BIN_PATH` are set. A failing or slow herdr never slows or changes the run.
### Out
- The resume command (`-- <argv>` on `report-agent`). Owner decision 2026-11-09: relaunching an unattended run by itself after a herdr restart could reprocess the queue unseen. Alternative proposed to the owner, not built here: see "Risks and what stayed out".
- Reporting from `cepa until pending|decide|land|close-dead`: they are short and interactive.
- An end-of-run herdr notification.

## Success criteria

### CS-1: while the `cepa-until` window runs inside herdr, the pane reports `working` as agent `cepa-until`, with a message naming the queue, the item position and its id, and a new report for each item
**Surface:** cli
**Red test:** a test in the shape of `tests/test_cepa_until.py` sets `HERDR_ENV=1`, `HERDR_PANE_ID=w9:p9` and `HERDR_BIN_PATH` to a fake `herdr` that appends its argv to a file; a queue `q` with two items and a fake `claude` that marks each done. After the run, the file holds `pane report-agent w9:p9 --source cepa-until --agent cepa-until --state working` with a `--message` containing `q`, `1/2` and the first id, then the same with `2/2` and the second id, every `--seq` strictly greater than the previous one. Today it fails: the file is never created.

### CS-2: during a 5h quota pause, `cepa-until` keeps `working` and the message says it is paused and until when
**Surface:** cli
**Red test:** same harness, with the fake `claude` producing the quota reading that `quota_pause` turns into a wait; the fake herdr log holds a `--state working` report whose `--message` contains "paused" and the resume time as `HH:MM`, before the next item's report. Today it fails: no report.

### CS-3: `cepa-until` releases the pane on every exit: end of queue, end of window, circuit breaker, a `blocked` item stopping the batch, SIGTERM and Ctrl+C
**Surface:** cli
**Red test:** same harness, one run per exit path (end of queue; `--for 1s`; three red items with `--max-failures 3`; one item the fake marks `blocked`; SIGTERM sent to the supervisor mid-item; SIGINT sent mid-item). In each, the last line of the fake herdr log is `pane release-agent w9:p9 --source cepa-until --agent cepa-until` with a `--seq` greater than every earlier one. Today it fails: the log is empty.

### CS-4: `cepa-prove` reports `working` as agent `cepa-prove` with the round number and the cards already handled, and releases the pane on every exit
**Surface:** cli
**Red test:** a test in the shape of `tests/test_cepa_prove.py` with the same fake herdr and the fake `claude` proving `WEGO-1` then `WEGO-2`: the log holds `--source cepa-prove --agent cepa-prove --state working` reports whose messages contain `round 1` and then `round 2` with `WEGO-1`, and the last line is `pane release-agent`; a second run killed with SIGTERM mid-round also ends in `pane release-agent`. Today it fails: the log is empty.

### CS-5: outside herdr nothing is called, and a broken herdr changes neither the duration nor the result of a run
**Surface:** cli
**Red test:** (a) the CS-1 run without `HERDR_ENV` creates no log file and its ledger matches the CS-1 ledger event by event, ignoring times; (b) the CS-1 run with a fake herdr that sleeps 30 s and exits 1 finishes in less than 2 s more than (a) per report, with the same exit code and ledger; (c) `cepa until pending` with `HERDR_ENV=1` creates no log file. Today (a) and (c) pass by absence and (b) passes because nothing is called; the test goes red against any implementation that calls herdr without a timeout or from a subcommand, which is what it guards.

## Open questions
None.

## Decided without asking
1. The message is in English (`q: item 1/2 WEGO-12`, `paused for 5h quota until 03:40`), like the rest of `cepa-until`'s screen output.
2. A quota pause stays `working`, not `blocked`: herdr's `blocked` means "needs a decision from you", and a pause needs nothing from the owner.
3. A `blocked` item that stops the batch does not report `blocked` before releasing: the process exits right after, and herdr clears the label at the shell prompt anyway.
4. `--seq` is `time.time_ns()`, which herdr's docs recommend and which grows across runs.
5. Each report is a subprocess with a 1 s timeout whose failure is ignored, as herdr's docs ask ("Send reports in the background or with a short timeout, and ignore failures").

## Risks and what stayed out
- **R1. herdr changes the report contract.** The probe ran on 0.9.5. `report-agent` is a documented, public API for third-party agents, so the risk is low; CS-1 to CS-4 catch a break only against the fake, not the real herdr.
- **Proposed alternative to the resume command (not built, needs owner approval).** Report `cepa until pending --repo <absolute repo path>` as the resume command, instead of the command that started the run. After a herdr restart the pane comes back showing the interrupted run and the one command that closes it (`cepa until close-dead <queue>/<run>`). It is an existing, read-only command: it never starts an item.
- **A1 (risky assumption, tested 2026-11-09, FALSE): the supervisor survives a herdr server restart.** Test: a script that copies `cepa-until`'s signal handling (ignores SIGHUP, records SIGTERM/SIGINT and exits, keeps a child in its own session) ran in a pane of a separate session, `herdr --session cepa-test`; then `herdr session stop cepa-test`. herdr sent SIGTERM and the supervisor exited 0.6 s later (`SIGNAL SIGTERM -> exit` in its log). The real `cepa-until` would record `run_interrompido` and kill its `claude` child. So after a restart the run is always interrupted, and a watcher that follows a live run (the first idea, `cepa until watch`) has nothing to follow; `cepa until pending` covers the only case that happens.
- **A2 (tested 2026-11-09, TRUE): herdr runs the resume command of a process that died by SIGTERM during the stop.** Same harness, with `report-agent ... -- touch <file>`: after `herdr --session cepa-test server` started again, the file existed. It held in three rounds, including one where the SIGTERM handler called `pane release-agent` first: that call failed with `server_unavailable: server is shutting down`, so the release CS-3 asks for does not erase the resume command in the restart case, and on a normal exit the release does clear it, as intended.
