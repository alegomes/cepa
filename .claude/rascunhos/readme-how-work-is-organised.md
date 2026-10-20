<!-- Rascunho para o README.md, a inserir entre "What Cepa is" e "Work has modes".
     Bloqueado pelo modo descoberta em 2026-10-20; aplicar numa sessão em modo documentacao. -->

## How work is organised

Work has four heights, from largest to smallest. A **session** sits beside them: it is what
does the work.

| Height | What it is | Where it lives | Lasts |
|---|---|---|---|
| **Epic** | A package of work worth a demonstration. Lists the invariants that must never regress and a ladder of cycles. Written by `/common:epic`. | `docs/epics/<name>.md` | Months |
| **cycle** | One rung of the ladder. Closes when its demonstration script runs on screen and in the backend. `/common:plan --from-epic --ciclo N` turns it into a queue. | A section of the Epic | Weeks, many sessions |
| **queue** | The ordered list of items for one slice of work, with the reason each item sits where it sits. Written only by `/common:plan`. Read by `/common:next`, `/common:fila`, `/common:drain-plan` and `cepa-until`. | `.claude/programs/<name>/plan.yaml` | Until its last item closes |
| **item** | One line of a queue: `id`, `title`, `why`, `status`, `blocked_by`, `human_pending`, `evidence`. In a repo with Jira its mirror on the board is a **card**. The board keeps the status. The queue keeps the order and the why. | Inside the queue | Hours to days |

The session has two attributes:

- **mode**: what kind of work fits in it (exploration, discovery, construction, ...). It
  decides where the agent may write and what must be true before the session closes. See
  [Work has modes](#work-has-modes).
- **intent**: what this session will do inside its mode, as a purpose, a stopping point and
  one to six **steps**. Stored in `.claude/session-intent` by `cepa-intencao` and shown by
  `/common:whereami`. An unattended session (`cepa-until`) has no intent file: its intent is
  the next item of the queue.

Demands wait in **inboxes** before they get an order: `BACKLOG.md`, the feedback ledger
(`cepa-feedback`), `.claude/desvios.md`, GitHub issues and, with Jira, the backlog column.
Nothing runs from an inbox. `/common:plan` turns what is there into items.

Two names are in transition. The queue file is still called `plan.yaml`, under
`.claude/programs/`, with a `program:` key, and the command that writes it is still
`/common:plan`. All four are being renamed to *queue*. The `parallel-waves` queues of
`maestro` are frozen since 2026-10-08 and archived in `.claude/programs/archive/`.

The full vocabulary, with diagrams of an item's path, is in
[docs/how-it-fits.md](docs/how-it-fits.md#vocabulary).

<!-- Segunda troca, na seção "What you install": substituir o parágrafo
     "Experimental: **`maestro`** plans four or more demands ... does not run end to end yet." por: -->

Frozen since 2026-10-08: **`maestro`** plans four or more demands into waves of concurrent
sessions. It never ran end to end, and `cepa-until` is absorbing its fork and merge train.
See [docs/maestro.md](docs/maestro.md).
