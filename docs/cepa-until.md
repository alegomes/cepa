# cepa-until: run the queue for a time window, with nobody awake

`cepa-until` is a terminal command (not a slash command) that runs the repo's
single-track queue for **a window of time** instead of for a number of items. It lives at
`common/bin/cepa-until` in the Cepa clone. This page is a condensed version of the design
notes at the top of that script, which remain the source of truth.

```sh
cepa-until my-queue --for 12h
cepa-until my-queue --until 07:00
cepa-until my-queue --for 3h --dry-run     # prints the plan of the run, executes nothing
```

`my-queue` is the name of a queue written by `/common:plan`, stored at
`.claude/programs/<name>/plan.yaml`. See [execution-plan.md](execution-plan.md).

## Why it exists

The three bulk executors (`/board-flow:drain`, `/common:drain-plan`,
`/board-flow:prove-drain`) are limited by **count**: `--max N`. Count is the wrong unit for
using idle time. You don't know how many items fit in a night. You know how many hours you
have.

A clock alone does not solve it, because what kills a long session is not time, it is
**context**. A 12-hour session overflows long before 12 hours, and the one who resumes it is a
person typing `/common:autonomous-resume`. At 3 a.m. nobody types.

So the design is **one item per subprocess**. The supervisor launches

```sh
claude -p "/common:drain-plan <queue> --max 1"
```

once per item, in a new process every time. A full context window stops being a failure and
becomes the normal end of a subprocess. The supervisor launches the next one with a clean
window. That is what makes 12 hours possible.

## What it does not do, on purpose

It does not reserve items, record outcomes, know the topology or know what a card is.
`/common:drain-plan` and `cepa-plan` do that, with a state machine that already exists and is
tested:

- `cepa-plan start` reserves the item and **signs** the reservation (session, pid, host).
- `cepa-plan queue` hands back as runnable any reservation whose pid died. A dead subprocess
  cannot lock the queue forever.
- `cepa-plan finish` records the outcome, including the route only a human can close.

`cepa-until` is the wiring around that: clock, circuit breaker and log.

## The four owner decisions (2026-08-30)

1. **The source is the queue on disk**, not the board column. The queue keeps the order and
   the reason for it, and does not depend on Jira being up at 3 a.m.
2. **Circuit breaker at 3 failures in a row** (`--max-falhas`). Below that it is bad luck.
   Above it, the window is being burned on a systemic problem.
3. **One commit per item, on a single branch.** No merge train, no pile of branches waiting
   for someone to notice. This is a guard, not an intention: the starting branch is recorded
   and checked between items, and the run ends if it changed.
4. **`--dangerously-skip-permissions` is on by default.** Without it the subprocess hangs at
   the first permission prompt and the night dies silently. It is printed in the banner and
   can be turned off with `--com-permissoes`, which only makes sense with someone watching.

## Where the cut happens

Between items, never in the middle of one. Killing an item halfway leaves a dirty tree and a
dangling reservation. Two margins control it:

| Flag | Default | Meaning |
|---|---|---|
| `--reserva-minima` | 25m | Do not **start** an item if less than this remains. An item that does not fit is wasted work. |
| `--folga` | 60m | How far past the deadline an item **already running** may go before being killed. Past that it is a timeout, recorded, and the orphaned reservation returns to the queue on the next run. |
| `--tentativas-por-item` | 2 | Subprocesses the same window spends on the same item before marking it `blocked` and moving on. |

## The account's 5-hour usage cap

The Claude account has a usage quota per 5-hour window. On 2026-09-17 a run hit the cap at
01:00 with the reset at 03:20 and the window open until 06:17. The run stopped, about 3 hours
of window went unused, and the item in flight lost its work. Two rules came out of that:

- **Wait for the reset when the cap hits.** If the reset time is known and fits in the
  window, the supervisor sleeps until reset plus a margin (`CEPA_UNTIL_MARGEM_RESET`, default
  120s) and resumes the **same** item. The cut attempt does not count against the item's
  attempts or the circuit breaker. Three cuts in a row with no progress end the run.
- **Do not start an item with the quota nearly gone.** Each subprocess reports the 5-hour
  window usage. Before each item the supervisor projects usage: last reading plus the largest
  item cost measured in this window. If the next item does not fit, or with no history the
  reading is already above 90%, it waits for the reset before starting.

If the wait does not fit in the window, the run stops (`limite-de-uso` or `cota-no-fim`)
instead of starting an item that would be cut halfway.

## When it stops

At the first of: deadline reached, no runnable item in the queue (`fim-da-fila`, `bloqueado`,
`bloqueado-antes`, as reported by `cepa-plan queue`), circuit breaker, or a usage cap whose
wait does not fit in the window.

## Before you leave it running

- **The tree must be clean.** It refuses a dirty working tree, because otherwise nothing
  separates what the run did from what was already there. `/common:doctor` warns about this
  when you open the session, so you don't find out at 11 p.m. `--sujo-ok` overrides it. If
  files show as deleted and you did not delete them, find out why before overriding.
- **Permissions are off by default** (decision 4 above). The gates still apply inside each
  subprocess: red build blocks commit, cards need acceptance evidence, verdicts are computed.
- **Use `--dry-run` first.** It prints the plan of the run and exits.

Proof of the tool itself: [`docs/proof/cepa-until.yaml`](proof/cepa-until.yaml) and
[`docs/proof/cepa-until-cota.yaml`](proof/cepa-until-cota.yaml).
