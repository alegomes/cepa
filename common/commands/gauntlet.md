---
description: Design competition with blind judging (Gauntlet Loop) for an OPEN design decision — writes the quality bar first, has N isolated builders produce designs from distinct angles, 3 blind judges rank them by Borda count, the winner is revised and checked against the bar, and the result goes to docs/internals/gauntlet-<slug>.md. Opt-in and expensive (~600k tokens). To judge ONE already-written artifact through several lenses use /common:advisors.
argument-hint: <target> [--builders=3] [--angulos=a,b,c] [--slug=<slug>]
interaction: routine
---

# /common:gauntlet

## Purpose

An open design decision usually ships with the first design someone thought of.
This command does the opposite: it writes **first** the bar for what a good
design would be, sends N **isolated** builders to produce competing designs from
different angles, and lets 3 **blind** judges (who see only the goal, the bar and
the anonymized designs) rank them. The winner is revised against the gaps the
judges pointed out and checked against the bar again. Out comes a durable
document with the whole path, not just the conclusion.

## Variables

- `$ARGUMENTS` — `<target>` (required): free text describing the
  decision, OR the title of a `## ` section of `BACKLOG.md` (in that case the
  whole section becomes the agents' context).
- `--builders=N` — number of builders (default 3). Each one gets an angle; if N
  exceeds the number of angles, they cycle.
- `--angulos=a,b,c` — picks the angles by `key` in the registry (default:
  `mecanismo-novo`, `estender-o-que-existe`, `livre`).
- `--slug=<slug>` — output file name (default: kebab-case of `<target>`).

## Instructions

You are the orchestrator. You assemble the context, launch the workflow, write
the document and report — running the 9 agents is the script's job. The angle
registry lives in `common/gauntlet/angulos.md` (via the plugin:
`${CLAUDE_PLUGIN_ROOT}/gauntlet/angulos.md`) and the canonical script in
`${CLAUDE_PLUGIN_ROOT}/gauntlet/gauntlet.workflow.js`.

## Workflow

### 0. Usage floor

This command is **opt-in and expensive**: ~600k tokens, ~13 minutes, 9 agents by
default (bar 1 + builders 3 + judges 3 + reviser 1 + check 1). Only run it if
the user asked explicitly (or confirms after hearing the cost).

**Refuse** and point to the right path when the target is:

- **code whose correctness is provable** (a test, the suite or the build can
  prove it): the right judge is the proof gate, not a panel of opinions;
- a **mechanical task** (rename, an adjustment whose shape has only one answer);
- a **trivial decision, or one reversible at low cost**;
- a decision that **cannot be judged in text** (it depends on measuring something
  in the world).

The Gauntlet serves the **open** design decision, where several plausible designs
compete and an attentive reader can judge them from the text.

### 1. Assemble the CONTEXT

If `<target>` matches a `## ` title in `BACKLOG.md`, paste that whole section as
the context. Otherwise, use the target text and read what it cites. The context
needs: (a) the **goal** in a few sentences; (b) **what already exists and must be
extended**, not duplicated (with paths); (c) the relevant **harness philosophy**
(enforcement in depth: a rule only in prose decays, a mechanical gate lasts;
gates independent of the executor); (d) the list of **files to read** (`reads`).
Real incidents that motivate the decision go here: the bar and the builders work
on top of them.

### 2. Choose the angles

Read `${CLAUDE_PLUGIN_ROOT}/gauntlet/angulos.md`. Without `--angulos`, use the
default (`mecanismo-novo`, `estender-o-que-existe`, `livre`). With `--angulos`,
select by `key` (a key outside the registry: list the valid ones and stop). Each
builder gets an angle; `--builders` larger than the number of angles cycles,
smaller uses the first N. Build `angles: [{key, brief}]` with the registry's
`brief`.

### 3. Run the workflow

Pass the **Workflow tool** the script
`${CLAUDE_PLUGIN_ROOT}/gauntlet/gauntlet.workflow.js` (read from the file,
unchanged) with `args` = `{repo, goal, context, angles: [{key, brief}], reads: [paths]}`.
`repo` is the root of the current repository (`git rev-parse --show-toplevel`).

Do not rewrite the script per invocation: it is the canonical copy of the two
validated pilots (`docs/internals/gauntlet-pilot-*.workflow.js`). Whatever varies
goes in `args`. `args` may arrive as a JSON string — the script has the guard.

The five stages the script runs, in this order:

1. **Bar** — one agent writes 5 to 8 judgeable criteria (with a rubric) and an
   ambitious reference, before any design exists.
2. **Isolated builders** — N agents in parallel, each with an angle; none sees
   another's output.
3. **Blind judges** — 3 judges receive only goal + bar + anonymized designs
   (A, B, C...), **in an order rotated per judge**, score each criterion from 0
   to 10 and rank.
4. **Borda and revision** — sum of points (1st place = N points, where N is the
   number of designs); the winner is revised against the gaps pointed out, with
   grafts of superior ideas from the rivals.
5. **Final check** — an agent with fresh context checks whether the revised
   design meets the bar (every criterion >= 7/10) and lists what is left.

If the Workflow tool **is not available** in this session, degrade: launch the
same agents through manual Agent calls **in the same message** (builders in
parallel, then judges in parallel), with the same prompts as the script, keeping
the builders isolated and the judges blind.

The script returns `{bar, designs, full_designs, verdicts, borda_points, winner,
revised_design, final_check}`; on failure it returns `{error, designs}` (fewer
than 2 designs, or no judge answered): report the failure and stop, without
inventing a winner.

### 4. Write the durable output

Write `docs/internals/gauntlet-<slug>.md` (slug = `--slug` or kebab-case of
`<target>`) with the pilots' structure. The document is in pt-BR; keep these
headings literally, as in the pilots:

- header: `# Gauntlet — <target>`, a line with the run id, date, agents, tokens and
  minutes, and a line on the method;
- `## Barra de qualidade (escrita antes de qualquer design)` (the quality bar,
  written before any design) — each criterion and the reference;
- `## Designs concorrentes e julgamento` (competing designs and judging) with one
  `### Design A (<ângulo>) — <título>` per design (full content) and
  `### Vereditos dos N juízes cegos` (verdicts of the N blind judges): each
  judge's ranking, **a Borda points table with the arithmetic shown** (1st = N
  points, 2nd = N-1, ...; sum per design) and the biggest gaps;
- `## Design final (vencedor X revisado, com enxertos de ...)` (final design:
  winner X revised, with grafts from ...);
- `## Checagem final contra a barra` (final check against the bar) — `bar_met`,
  remaining gaps, note.

**Winner:** highest Borda sum. Tie: the design ranked 1st by the most judges
wins; if still tied, the first in the order of the designs — and the report
**names the tie**.

### 5. Report (pt-BR, `plain-report` format)

Follow the `plain-report` skill: plain-language opening, `**Pra você:**`,
technical detail, `### Decisões e próximos passos`. Explain in plain language who
won and why, with the Borda arithmetic, say whether the bar was met and what is
left. End with numbered closed questions, each with `Recomendo sim/não` (e.g.
"Abro um item de fila para implementar o design vencedor?" — "Do I open a queue
item to implement the winning design?"). Never hand back the decision without a
recommendation.

### 6. Telemetry

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_telemetry.py" emit gauntlet_run \
  builders=<n> judges=3 winner=<angulo> bar_met=<true|false>
```

(If `${CLAUDE_PLUGIN_ROOT}` is not in the environment, use the absolute path of
`common/hooks/_telemetry.py`.)

## Notes

- **Isolation is non-negotiable.** Builders never see each other; judges see
  only goal + bar + anonymized designs in rotated order. Do not pass one agent's
  output to another outside the script's flow.
- **The command never implements the winning design.** It writes the document and
  reports; implementing is another item, decided by the owner.
- **Usage floor repeated because it matters:** provable code or a mechanical task
  does not deserve a Gauntlet (step 0).
- **Relation to `/common:advisors`:** advisors judges **one** artifact that
  already exists, through N lenses, and synthesizes by naming the disagreements.
  The gauntlet **generates** N competing artifacts and judges them comparatively,
  blind, with a winner by Borda. Use advisors to review a written decision; use
  the gauntlet to choose among designs that do not exist yet.
- The script uses neither `Date.now` nor `Math.random`: the run is deterministic
  in whatever depends on the orchestrator.
