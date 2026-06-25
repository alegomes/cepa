# Discovery topology (continuous product discovery)

You have access to a **discovery** topology: 6 agents that translate raw
product signals into validated opportunities ready for engineering handoff.
This is *upstream* of build topologies — it owns "should we build this and
what exactly," not "how do we build it."

## When to use this topology

Use the discovery agents when:
- A user signal (complaint, idea, support ticket, sales feedback) needs
  framing before it becomes a backlog Epic.
- A vague problem space needs research, assumption mapping, and lightweight
  experiments before committing to build.
- An Opportunity card on a discovery board needs to advance through its
  lifecycle (Inbox → Framing → Researching → Validating → Validated → Handed off).

Do **not** use it when:
- The work is already a well-specified backlog item (use a build topology).
- The user is asking a one-off opinion question (just answer).

## Agent roster

| Agent | Phase | Does what |
|---|---|---|
| `discovery-lead` | orchestrator | Routes work across columns; never executes |
| `opportunity-framer` | Framing | Problem statement, target user, desired outcome |
| `user-researcher` | Researching | Interview synthesis, signal aggregation, behavioral patterns |
| `assumption-tester` | Researching → Validating | Ranks riskiest assumptions; designs test plan with pre-declared success criteria for each |
| `evidence-auditor` | Validating → Validated/Discarded | Reads collected evidence against the test plan's pre-declared criteria; returns Confirmed / Invalidated / Inconclusive |
| `epic-briefer` | Validated → Handed off | Writes a delivery brief at `docs/discovery/<card>/handoff.md`; engineering's `epic-author` (if installed) reads it to author the Epic |

## Artifact layout

All discovery artifacts live under `docs/discovery/<card-key>/`:

```
docs/discovery/
  WEGO-1234/
    framing.md            # opportunity-framer's output
    research.md           # user-researcher's synthesis
    assumptions.md        # assumption-tester's ranked assumptions + test plans
    evidence/             # raw artifacts the human collected (transcripts, CSVs, screenshots)
    audit.md              # evidence-auditor's verdict against pre-declared criteria
    handoff.md            # epic-briefer's delivery brief (only at handoff)
```

The path-lock enforces `docs/discovery/**` — discovery agents cannot write
code, only research artifacts.

## Continuous discovery flow

This topology is **continuous**, not bounded-sprint. There's no
`/discovery:plan-build-validate` equivalent. Instead, an Opportunity card
moves forward one column at a time, often looping back as assumptions get
tested:

```
Inbox → Framing → Researching → Validating ⇄ Researching
                                      ↓
                                 Validated → Handed off
                                      or
                                 Discarded
```

A single card may cycle Validating → Researching multiple times as
assumptions get tested one batch at a time. That loop is the point of
continuous discovery — each pass burns down risk.

## Commands

- `/discovery:capture <description>` — drop a raw signal as an Opportunity
  card on the discovery board, lands in Inbox. Lightweight: no framing,
  no research, just tracking.
- `/board-flow:advance <card-key>` — move a card to its next column,
  invoking the column's `on_enter` agent. Generic across topologies; reads
  `board-flow.yaml` (project root). (Provided by `board-flow@alegomes`.)

## Composition

- `discovery` alone → produces validated opportunities as local artifacts
  under `docs/discovery/`.
- `discovery + board-flow` → same, plus board lifecycle on your discovery
  Jira board. `epic-briefer` publishes a brief; the next agent in the chain
  picks it up.
- `discovery + board-flow + build-hex` (or `+ build-team`) → end-to-end:
  signal → validated solution → engineer-board Epic → Stories → code → ship.
  The handoff is two-step: discovery's `epic-briefer` writes the brief and
  links a card to the engineer board; engineering's `epic-author` reads the
  brief and authors the Epic on its own board.

## Boundary with build topologies

Discovery owns *briefs*. Engineering owns *Epics*. The brief is the only
artifact that crosses the plugin boundary. Discovery does not create or
modify backlog items on the engineer board — it links to them after the
build topology's planning-lead has authored them from the brief.

## Constraints

- Discovery agents do not write code. The path-lock enforces this.
- The `evidence-auditor` returns verdicts grounded in *pre-declared* success
  criteria from the assumption-tester's test plan. Don't post-hoc rationalize.
- Validation evidence comes from real users, real data, real prototypes.
  Agents do not synthesize evidence — they only structure the work and
  audit what the human collected.
- Continuous mode means cards move forward (or sideways, or back) one
  deliberate step at a time. Don't auto-advance through multiple columns.
