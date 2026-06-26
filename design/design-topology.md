# Design topology (product design → build-ready spec)

You have access to a **design** topology: a design-lead plus 5 workers that
turn a feature brief into a **build-ready design spec** — interaction flows,
visual direction, design-system reconciliation, a shareable prototype, and an
adversarial critique. This sits *between* discovery ("should we build this")
and engineering ("how do we build it"): design owns *what the experience is*.

## When to use this topology

Use the design agents when:
- A validated feature needs its UX and visual design worked out before
  engineering builds it.
- An existing screen needs a redesign or a critique against heuristics +
  accessibility.
- A design card on a board needs to advance through its lifecycle
  (Brief → Explore → Systematize → Prototype → Critique → Spec'd → Handed off).

Do **not** use it when:
- The feature is purely backend / has no user-facing surface.
- The design already exists and you just need it built (use a build topology).
- The user is asking a one-off opinion question (just answer).

## Agent roster

| Agent | Phase | Does what | Model |
|---|---|---|---|
| `design-lead` | orchestrator | Routes across phases; synthesizes; never produces | opus |
| `ux-architect` | Explore | "How it works" — IA, flows, interaction patterns, full state sets | sonnet |
| `visual-designer` | Explore | "How it looks" — hierarchy, layout, type, color, per-state visuals | sonnet |
| `design-system-keeper` | Systematize | Reconciles every choice to an existing token/component; kills one-offs | sonnet |
| `prototyper` | Prototype | Sole holder of Gamma/Canva MCP; makes the design viewable | sonnet |
| `design-critic` | Critique | Adversarial gate — heuristics, a11y, consistency → SHIP/REVISE/BLOCK | sonnet |

`ux-architect` is deliberately distinct from `discovery:user-researcher` and
`build-team:ux-researcher`: it designs *interaction*, it does not generate user
*evidence*. If you need user research, compose with discovery.

## Artifact layout

All design artifacts live under `docs/design/<slug>/`:

```
docs/design/
  <feature-slug>/
    flows.md          # ux-architect — IA, flows, states
    visual.md         # visual-designer — visual spec per state
    system.md         # design-system-keeper — token/component reconciliation
    prototype.md      # prototyper — Gamma/Canva link + per-screen mapping
    design-spec.md    # design-lead — the build-ready entry point (assembled last)
  reviews/
    <feature-slug>.md # design-critic — verdict + located findings
```

The path-lock enforces `docs/design/**` — design agents cannot write code,
only artifacts. The `design-critic` is scoped to `docs/design/reviews/**`.

## The design loop

```
Brief → Explore → Systematize → Prototype → Critique ⇄ Explore
   (ux-architect ∥ visual-designer)              ↓
                                            Spec'd → Handed off
```

Explore runs the two cuts in parallel. Systematize, Prototype, and Critique
are sequential gates. The Critique → Explore loop is the point — each pass
burns down design risk before engineering touches it. A design isn't "Spec'd"
until `design-critic` returns SHIP.

## Entry points

This topology has **two** entry points, matching how design work actually
happens:

- **Linear (bounded feature):** `/design:explore-critique-spec <feature>`
  runs the whole loop in sequence and assembles `design-spec.md`. Use for a
  well-scoped feature you want designed end-to-end in one go.
- **Per-column (board-driven / continuous):** delegate to `design-lead`
  directly, or — with `board-flow` installed — use `/board-flow:advance <card>`
  to step a design card forward one column at a time. The lead's routing table
  (in `design-lead.md`) maps each column to its worker. Use when design is
  tracked on a board and loops between Critique and Explore over several passes.

To wire the per-column flow to a board, declare the columns in the host
project's `board-flow.yaml` (or `.claude/board-flow.lifecycle.yaml`) with each
column's `on_enter` agent — `/board-flow:advance` reads it generically.

## Composition

- `design` alone → produces design specs as local artifacts under `docs/design/`.
- `discovery → design` → discovery validates the opportunity and hands off a
  brief; design turns it into a spec. The brief is the crossing artifact.
- `design → build-team` (or `→ build-hex`) → design owns `design-spec.md`;
  engineering's `frontend-dev` reads it and builds. The design spec is the only
  artifact that crosses the boundary — design does not write code, engineering
  does not redesign.
- `design + board-flow` → the per-column lifecycle runs against a design board.

End-to-end: signal → (discovery) validated opportunity → (design) build-ready
spec → (engineering) shipped feature.

## Boundary with build topologies

Design owns the *spec*. Engineering owns the *build*. The `design-spec.md` is
the handoff: it tells `frontend-dev` what to build (flows, visual decisions,
which tokens to use), but design never writes or edits application code, and
engineering never silently redesigns. A design change goes back through the
design loop; an implementation question goes to engineering.

## Constraints

- Design agents do not write code. The path-lock enforces `docs/design/**`.
- `prototyper` is the only agent that touches Gamma/Canva. If those tools are
  unavailable (headless / unauthenticated run), it falls back to a written
  walkthrough rather than blocking the loop.
- `design-critic` is adversarial and never self-certifies — it reviews, it does
  not redesign. Its verdict maps deterministically to severity (any BLOCKER →
  BLOCK; any MAJOR → REVISE; else SHIP).
- The design loop moves one deliberate step at a time in per-column mode. Don't
  auto-advance through multiple phases — let the critique loop do its work.

## Per-project customization

The workers write to `docs/design/**` and reconcile against whatever design
system the project has. If your project keeps tokens/components somewhere
non-obvious, name those paths in your delegation prompt so `visual-designer`
and `design-system-keeper` reconcile against the right source. To change a
worker's domain, override it locally in `.claude/agents/<name>.md` — project-
local files win over plugin-shipped ones.
