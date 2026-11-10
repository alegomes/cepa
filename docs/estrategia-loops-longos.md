# Longer `cepa-until` loops: what Factory Engineering teaches and where the window is lost

**Status:** strategy in exploration, revision 1 · **Date:** 2026-11-10 · **Session mode:** exploration
**Sources:** transcripts of four videos (listed in section 1); every `*.jsonl` run record under
`~/**/.claude/queues/*/until/` on this machine (count in section 2); `common/bin/cepa-until`
(stop branch at lines 3863-3867); `docs/cepa-until.md`; `docs/estrategia-durabilidade.md`;
`docs/epics/cepa-em-espiral.md`.

## 0. Context

**`cepa-until`** is the supervisor that runs a repo's queue (`.claude/queues/<name>/queue.yaml`,
written only by `cepa-plan`) for a **window** of hours, one `claude -p` subprocess per item. A run
**ends** at the first of: deadline (`prazo`), no runnable item (`fim-da-fila`/`end-of-queue`),
circuit breaker (`disjuntor`, 3 failures in a row), stuck queue (`fila-travada`, 3 blocked in a
row), usage cap, branch change. A **deferred** item (`adiado`) is a pending item the queue skips
because it waits on the owner (`human_pending`, `blocked` from an outside cause) or on another
deferred item. The **conductor** is the not-yet-built piece (cycle 2 of the Epic
`cepa-em-espiral`) that chains discovery, build, proof and landing of an Epic cycle.

The question this document answers: how does Cepa use more of the window it is given?

## 1. Factory Engineering, as the four videos describe it

| Code | Source | Idea that matters here |
|---|---|---|
| V1 | Zach Lloyd, Warp, "Software Engineering Is Becoming Factory Engineering" (youtube.com/watch?v=tUPPVhBBcoM) | The engineer builds the thing that builds the product. The loop: intake, agent triage (easy and unambiguous goes straight to implementation, hard gets a product spec and a tech spec), cloud implementation, agent review before human review, verification by real use, CI/CD, monitoring that feeds the top again. Self-improvement loops: an observer agent sees where humans corrected a skill and improves it. Metric: software shipped per human hour and per token cost. |
| V2 | IndyDevDan, "Tiny Software Factories" lessons 1 and 2 (youtube.com/watch?v=1v7ldJiyH-Y, youtube.com/watch?v=GRlcm3wmOqs) | In the loop (you prompt), near the loop (the agent works and stops only at a decision point with a result waiting for you), out of the loop. "It doesn't wait for you to work, it works for you, then waits." Durable agent plus trigger (cron prompt) plus sandbox. Sub-agents with time and spend budgets. The author calls these shortcuts that do not scale, and the videos sell a course. |
| V3 | Valdemar, Tech Leads Club (youtube.com/watch?v=5UwvjCVPigM, first part) | Humans own intent, research and risky review. An always-on teammate agent with its own identity and the team's skills. Every request enters through one funnel, the board is the system of record. Pieces: work plane (intake, record), control plane (dispatcher), brain (company context), runtime, gates. Model chosen by the item's impact. |
| V4 | Felipe, Tech Leads Club (same video, second part) | A bot-run factory produced 8 approved PRs, 4 reverting the other 4. The fix: a deterministic 8-step pipeline where the agent is step 5 only. Typed JSON contracts, single-use token per role, no blind retry, circuit breaker on 429/500/timeout, dedup by deterministic run name, hourly cap, approval bound to the commit hash, at most 3 review rounds, only the factory writes the deploy result. "Prose asks, the contract guarantees." |

Cepa is already on the V4 side: a deterministic supervisor, a circuit breaker, proof verdicts
computed by a reviewer and not declared by the implementer, signed reservations, the quota wait.
What Cepa lacks from V1, V2 and V3 is **intake and decision inside the loop**.

## 2. Where the window goes

Sweep: every `*.jsonl` under `~/*/.claude/queues/*/until/`, `~/*/*/...` and `~/*/*/*/...`,
deduplicated by (queue name, file name). 98 runs carry both `run_start` and `run_end`. Window
asked = `run_start.prazo` − `run_start.quando`. Window used = `run_end.quando` −
`run_start.quando`.

| End reason | Runs | Asked | Used | Lost (asked − used) |
|---|---|---|---|---|
| queue empty (`fim-da-fila` 41 + `end-of-queue` 3) | 44 | 373.5h | 112.5h | **261.0h** |
| circuit breaker | 7 | 50.7h | 15.8h | 34.9h |
| stuck queue | 4 | 43.7h | 13.1h | 30.6h |
| branch changed | 3 | 27.0h | 5.9h | 21.1h |
| usage cap (`limite-de-uso`) | 6 | 45.4h | 24.6h | 20.8h |
| deadline (`prazo`) | 32 | 133.8h | 137.9h | none (slack past deadline) |

- All runs: 319.7h used of 686.1h asked, 319.7 ÷ 686.1 = 47%. Lost: 686.1 − 319.7 = 366.4h.
- Queue empty: 261.0 ÷ 366.4 = **71% of the lost window**.
- In 36 of those 44 runs the `run_end.detalhe` says items were left deferred ("N ficaram
  adiados"). Sum of N: 346. The same item can count in several runs, so 346 is deferrals, not
  distinct items.
- The code confirms the mechanism: when `cepa-plan queue` returns no batch, the supervisor
  `break`s at once (`common/bin/cepa-until:3863-3867`). No notice, no wait, the questions appear
  only in the end-of-run panel or in `cepa-until decide`.

**Diagnosis.** Runs do not end early because processes die (that was the durability strategy,
closed: DUR-1 to DUR-4 done). They end early because the queue runs dry while the remaining work
waits on the owner. The owner is asleep or away, the questions are invisible until the next
terminal visit, and the window closes unused.

## 3. Paths considered

### P1. Wait for the answer instead of ending (near the loop)

When the queue has no runnable item, **deferred items wait on the owner**, and at least
`--min-reserve` remains, the supervisor:

1. sends one notice per newly deferred item, with the closed question already recorded by
   `cepa-plan finish --question`;
2. sleeps, re-reading the queue every `CEPA_UNTIL_ESPERA_DONO` seconds (proposed default 300),
   writing the heartbeat with `fase: aguardando-dono`;
3. resumes as soon as an answer makes an item runnable, or ends at the deadline with the new
   reason `aguardou-dono` (distinct from `fim-da-fila`, so the digest can measure it).

Items deferred only on another item, with no owner question underneath, do not trigger the wait.

- Gain: targets the 36 runs above directly. The lost hours become hours the owner can recover
  with a phone answer.
- Open questions the item must answer before building:
  - **Q1. Notice channel.** The supervisor is a Python script outside Claude Code, so the
    `PushNotification` tool is not available. Candidates: macOS `osascript` (only when the owner
    is at the Mac), an ntfy-style HTTP push (external service, needs owner approval), Slack
    webhook. Not decided.
  - **Q2. Where the answer is written.** `cepa-until decide` commits `queue.yaml`. The run reads
    the queue from the clone while its commits go to `until/<run>` in another worktree. The item
    must prove that an answer given mid-run does not trip the dirty-tree or `branch-mudou` guards.
  - **Q3. Answering away from the terminal.** `cepa-plan answer` refuses without a TTY on
    purpose (an agent cannot close a human route). A phone answer needs a path that keeps that
    guarantee, for example an SSH session to the Mac. Without it, P1 only helps when the owner
    comes back to the terminal before the deadline.
- Cost: one supervisor change, one new end reason, tests for the wait and for the resume.

### P2. Refill the queue from inside the run (intake and triage)

When the queue empties, a feeder step pulls the next ready work from sources the owner already
ordered: the next ready entry in `BACKLOG.md`, triaged `cepa-feedback`, READY cards from
`/board-flow:triage`. It admits only items classified easy and unambiguous (V1's triage rule).
Hard ones get a draft spec and wait. The next cycle of an Epic stays out: that is the conductor.

- Gain: covers the 8 queue-empty runs with nothing deferred, and keeps the run busy while P1
  waits.
- Risk: the queue exists to hold the owner's order and the reason for each position. A feeder
  that reorders or invents items breaks that. Rule: append only, never reorder, never create an
  item without a written source line.
- Cost: higher than P1. Needs a classifier with a typed output (V4's contract style), a writer
  path through `cepa-plan`, and a cap per run.

### P3. Self-improvement loop on repeated failure

The `until-review` analysis already reads each run. When the same cause ends two runs (circuit
breaker, stuck queue), it records a `cepa-feedback` entry with the evidence. That is V1's
observer, applied to the harness.

- Gain: aims at the 65.5h of circuit breaker plus stuck queue (34.9 + 30.6).
- Cost: low, but the gain depends on someone acting on the feedback. Comes after P1 and P2.

### P4. Model by item impact

A cheaper model for low-impact items so more items fit in the 5-hour quota (V3, V2).

- Gain: at most the 20.8h lost to the cap. Low.
- Risk: lower first-pass quality turns into more attempts, which costs window too.

### Not taken

- **An always-on loose bot with its own identity** (V3's Hermes agent). That is the design that
  produced V4's 8 self-reverting PRs. Cepa's deterministic supervisor is the right side.
- **One super-agent that does everything** (V2 argues against it as well).

## 4. Recommendation

P1 first, in a new queue `loops-longos`, after this document passes the `/common:advisors`
panel. Then P2 as a second item, with its source rule written into the item. P3 and P4 stay
recorded, without a queue, until P1 has run for 10 runs and the digest shows how many hours
`aguardou-dono` recovered.

Why a new queue and not `cepa-durabilidade`: that queue is closed (4 of 4 done) and its scope
was surviving a crash. Why not `cepa-espiral-c2`: both of its items are `human_pending` on the
Epic condition, so a P1 item there would never run.

## 4.1 Measurement after the panel (2026-11-10, owner decision on X1)

The panel (`docs/reviews/2026-11-10-painel-loops-longos.md`) asked whether the owner answers
before the run's deadline. Method: for each queue-empty run that ended with deferred items
(37 runs, same sweep as section 2), take the repo's commits whose subject is an owner answer
(`owner's answer`, `resposta do dono`, `dono responde`) **for that queue**, and keep those
between `run_end.quando` and `run_start.prazo`. Then check whether a new run of the same queue
started before the deadline.

| Result | Runs |
|---|---|
| No answer before the deadline | 32 of 37 |
| Answer before the deadline, owner relaunched by hand | 4 (gaps from end to relaunch: 8 min, 7 min, 48 min, 2h08) |
| Answer before the deadline, no relaunch | 1 (answer 2h03 after the end, 11.1h of window left) |

Reading:

- A run that stays alive waiting (P1) would have recovered window in **1 run of 37**, about
  11.1h. In the 32 runs with no answer it recovers 0h. That does not pay the permanent cost the
  panel listed (CM1, SR1 to SR8). **P1 as a live wait is dropped.**
- When the owner does answer, it is minutes after the run ends, at the terminal, through the
  end-of-run question panel (first answers at +3, +7, +18 and +26 min). The cheap gain is there:
  **an answer given in the end-of-run panel resumes the same run** instead of ending it, when
  the window still has `--min-reserve`. It would have saved the 4 relaunch gaps (8 min + 7 min +
  48 min + 2h08 = 3h11) and the 11.1h of the fifth run, with no sleeping process, no notice
  channel and no concurrent write to `queue.yaml`, because the panel already runs inside the
  supervisor's own process.
- The 32 unanswered runs are a question problem, not a loop problem. The two levers are asking
  before the run starts (CM2) and asking fewer questions on reversible actions (the owner's
  "1. sim" pattern). Both belong to discovery, not to this queue.

## 5. Risks every path must respect

- **R1.** No `done` without a green full build.
- **R2.** The main branch only changes with the owner present (R1 of 2026-09-26).
- **R3.** No new state store: the wait phase lives in the existing `estado.json` heartbeat.
- **R4.** An agent never closes a human route (the TTY rule of `cepa-plan answer` stays).
