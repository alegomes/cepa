---
description: "[frozen since 2026-10-08: the cepa-until conductor will absorb fork and merge train (decision 1 of docs/estrategia-cepa-proximo-nivel.md); do not use for new work] Plans a Maestro program — talks through a universe of demands (default BACKLOG.md), proposes waves of slices with disjoint surfaces and fork points, writes .claude/programs/<name>/plan.yaml (schema v2, canonical in common/plan-schema.yaml; v1 is still read without migration) and runs the intake gate (cepa-dor) until every slice comes out READY or has its gap named. Executes nothing — /maestro:run (step 3 of the build order) is what forks. Usage floor: ≥4 demands (D7); with fewer, /board-flow:drain or a single session wins. With --sweep, it scans the ENTIRE source instead of a hand-picked list of demands and proposes the next 2-3 waves by itself. With --from-plan NAME, the source is the repo's `single-track` queue (.claude/programs/NAME/plan.yaml) instead of a prose file — it is the queue → waves promotion, and the answer to \"how do I use program-plan in a project with Jira\", since the queue accepts Jira as a source and --source does not."
argument-hint: [program-name] [--source FILE] [--demandas "P9,P10,..."] [--sweep] [--from-plan NAME]
interaction: conversational
---

# /maestro:program-plan

## Purpose

Turn "I want to run these N demands in parallel" into a plan.yaml that the
engine can execute without improvised mediation. v0 (melhorias-2026-07)
proved the format and paid for a lesson: two slices touched the same file because
the surface was neither declared nor checked — 1 real merge conflict. This
command exists so that EVERY plan is born with surfaces declared, disjoint
and mechanically verified before any fork.

Talk to the user in Brazilian Portuguese (pt-BR): the questions, the wave proposal
table and the closing summary are all rendered in pt-BR.

**Seam invariant:** `/maestro:run` reads exclusively the plan.yaml. This
command is the only place where BACKLOG.md (or another source) is interpreted.

**`--sweep` mode:** instead of a hand-picked list of demands, it scans the
entire source and PROPOSES which ones go into the next waves — nobody today reads the
109 titles of the whole backlog and comes back with "this can run in parallel without
tripping over itself" (docs/spec/planejador-de-lotes-paralelos.md, CS-1). It is still a
proposal, just like the normal mode: it goes into the step 3 conversation, it never writes the
plan by itself. The differences are marked in the steps below with the label
`sweep` plus an identifier in bold and brackets — the identifier is used
by `common/bin/cepa-promptcov` to cross-check against the regression lock
(`tests/test_program_plan_sweep.py`) and point out any piece without coverage; see
docs/promptcov.md.

**`--from-plan NAME` mode:** the source is the `single-track` queue that already exists in the
repo (`<main-root>/.claude/programs/NAME/plan.yaml`), written by
`/common:plan` from a spec, from a Jira triage or dictated by hand.
It is stage 4 of the "one writer, three sources" design (BACKLOG.md, "Cinco portas
de planejamento") and the only promotion that was missing: queue → waves was declared
manual in `docs/execution-plan.md` because there was no path. It is also the answer to
*"how do I use program-plan in a project with Jira"* — `--source` only accepts a
file, and the queue accepts the board as a source.

What reads the queue is `common/bin/cepa-plan promote`, not this prose. The rule of
what may become a slice lives in the code for the same reason as stages 1 and 2: a
paragraph that says "promote only the `pending` ones" can only be proven by a grep on
itself, which shows the PROMISE and never the execution. The blocks annotated with the
`from-plan` family below say what to do with what the script returns — the
same convention as `--sweep`, measured by `cepa-promptcov`.

## Steps

1. **Source and universe.** Read the source (`--source`, default `BACKLOG.md`) and
   identify the candidate demands (the ones passed in `--demandas`, or the ones
   the user describes). Fewer than 4 demands → stop and say the floor (D7) was not
   reached; recommend /board-flow:drain or a single session.

   **[sweep:full-source]** Read the ENTIRE source, from start to end — not only the part the
   user pointed at. Discard what already has `Status: FEITO/CONSTRUÍDO/✅` or already
   belongs to an existing plan (a `plan.yaml` in
   `<main-root>/.claude/programs/*/`); among the rest, stop at the next
   **2-3 waves** (do not try to partition the whole backlog at once — it is a
   hypothesis, revalidated per session). Prefer demands
   whose surface lies OUTSIDE cepa-dor's enforcement zone (`.claude/
   settings*`, `.claude-plugin/*`, `*/hooks/*`, `*/plugins/*`) — intake vetoes
   that zone unconditionally, so a demand whose real work is editing
   a hook is not a candidate for autonomous fork; name that to the user and suggest a
   supervised session instead of forcing the wave.

   **[from-plan:source]** With `--from-plan NAME`, do not read `BACKLOG.md`: run

   ```
   python3 common/bin/cepa-plan promote <NAME> --repo . --json
   ```

   and treat `demands[]` as the universe — in the ORDER they come in, which is the
   queue's order. What was left out comes in `excluded[]` with the reason per item
   (`done`/`dropped` have already left the queue, `in_progress` is reserved by another
   session, `blocked` got stuck in a previous run); **show that list to the user**
   instead of keeping quiet — an item they expect to see in the wave and that does not appear is the
   question they will ask, and the answer is already in the JSON. The D7 floor is
   mechanical here: **exit 4 = stop** and recommend `/common:drain-plan <NAME>`,
   which runs the same queue serially, with no worktree at all. Exit 3 = the name
   points to a waves plan, not to a queue.

2. **Analysis per demand** (reading the repo, writing nothing):
   - **surface**: which files/globs the demand realistically touches —
     derive it from the demand text + grep/glob in the code; when in doubt, declare the
     widest honest glob;
   - **dependencies** between demands (one creates what the other consumes → different
     waves, `fork_after`);
   - **human gate**: is there an open strategic decision (scope, contract,
     user-facing naming, breaking change)? It has to be made NOW, in the
     conversation, and recorded in `human_gate` — or the demand stays out of the wave;
   - **executable acceptance criterion** (`acceptance` + `acceptance_cmd` — the
     repo is `.claude/no-build`, so `acceptance_cmd` is mandatory);
   - **acceptance shape** (`acceptance_form`): if the demand only names private
     implementation steps — no observable Given/When/Then on any
     surface — it is not a US. Either the `acceptance` gains the observable triple
     (`acceptance_form: bdd`), or the slice **admits** it is substrate
     (`acceptance_form: substrate`). Without one of the two, intake fails it.

   **[from-plan:carry-why]** Each demand's `why` comes ready from the queue and is
   COPIED, never rewritten: it is the criterion that put that item in that
   position, and rewriting it here erases the prioritization the queue exists to
   keep. It goes into the slice's `context:` (or into `demanda:`, next to the
   `id`); what this conversation adds is what the queue does not have — surface,
   acceptance and human gate.

   **[from-plan:human-gate]** A demand that arrives with `human_gate` other than
   `none` carries a route only the human closes (the queue's `human_pending`). Either the
   decision is made NOW, in the conversation, and the slice's `human_gate` records what
   was decided — or the slice stays out of the wave. Do not copy the `open:` into the
   plan hoping to resolve it later: `cepa-dor` fails it, and rightly so, because
   forking a child on top of something nobody validated is building in the
   dark.

   **[sweep:solo-wave]** A demand whose surface cannot be derived with confidence
   (prose too vague, or it touches too large an area for an honest glob) does NOT
   share a wave with others — it goes **alone into its own wave**,
   treated as if it touched the whole repo. It is a consciously accepted cost:
   each such demand consumes an entire wave; if the sweep produces many
   one-slice waves, that is the symptom to report to the user, not to
   hide by forcing a dubious glob.

3. **Wave proposal.** Group slices with disjoint surfaces into the same wave
   (ceiling `max_concurrent_slices`, default 3); dependencies and heavy decisions
   push to later waves. Present the proposal to the user as a table
   (wave · slice · demand · surface · human gate · acceptance) and discuss it.

   **[from-plan:deps-to-waves]** With `--from-plan`, each demand's `onda_minima`
   is a FLOOR, not a suggestion: it comes from the queue's `blocked_by`, and two items
   where one depends on the other cannot fork in the same wave even if the
   surfaces are disjoint — the lower child would fork before what it
   consumes exists. Group by surface WITHIN the floor, never above it,
   and use `fork_after: "wave-<N-1>"` in wave N. An item may move up a wave
   (surface collided, ceiling full); down, never.

   **[sweep:wave-cap]** The ceiling of slices per wave is not fixed at 3 — **suggest** the ceiling
   by looking at the measured notary files (step 4): the more concentrated
   the conflicts are in few files, the lower the safe ceiling; a repo without a clear
   notary file supports a larger wave. Propose the number to the user with the why, do not
   write it without review.

4. **Write the plan.** Before writing any byte, check that the name
   is free:
   ```
   python3 maestro/bin/maestro-programs . --check-name <name>
   ```
   **Exit 3 = stop.** That path already holds the `single-track` queue of a board
   (it is `/board-flow:triage` that writes it, one plan per board) and writing waves
   over it erases the order of the items and the `why` of each one — the data the plan
   exists to keep, and that Jira does not have. Show the message to the user and
   ask for another name; do not invent a suffix on your own. Exit 0 with a warning of
   "name taken by a parallel-waves plan" is the normal case of replanning the
   waves of the same program: go on.

   **[from-plan:other-name]** With `--from-plan NAME`, `--check-name <NAME>`
   ALWAYS exits 3 — `NAME` is the queue, and it is where the demands came from. This is
   the mechanism working, not an error to work around: writing the waves there
   would erase the queue that was just promoted. The waves plan needs a name
   OF ITS OWN, and the one who chooses it is the user — do not invent a suffix on your own
   (`NAME-ondas` looks harmless and becomes a second document that
   nobody knows where it came from). Ask, and run `--check-name` again with the
   chosen name.

   **[from-plan:traceable-source]** Write into `source:` the line that
   `cepa-plan promote` returns in `source` — it says which queue, which
   path and how many items out of how many came, and it is the other end of the thread that
   each slice's `demanda:` (the item's `id`) starts. Without it the waves plan
   is born orphaned: months later nobody knows which queue that slice came from, nor in
   what state it was when it was promoted.

   With the design agreed and the name cleared, write the plan to
   `<main-root>/.claude/programs/<name>/plan.yaml`, following
   `common/plan-schema.yaml` (`schema_version: 2`, `mode: parallel-waves`). One
   slice per demand, unless a large demand the user agrees to slice. `mode` is explicit because
   the same schema also serves board-flow's `single-track` — it is the field that
   tells whoever reads it which of the two this plan is. v1 plans on disk (without `mode`)
   remain valid and **do not need to be migrated**.

   **`<main-root>`** is the parent of `git rev-parse --git-common-dir` without the
   trailing `/.git` — in a linked worktree this points to the MAIN CLONE, not
   to the current tree; outside one it is the same as `git rev-parse --show-toplevel`.
   The plan is repo state, not session state: written inside a session
   worktree, it dies with it, and in a repo whose `.gitignore` covers all of `.claude/`
   no guard on the removal path sees the file. This holds for reading and for
   writing. See `docs/execution-plan.md`, "Where the file lives".

   **[sweep:cartorios]** Before writing, run `python3 common/bin/cepa-hotspots
   <main-root> --json` and write the `hotspots[].path` list into the new and
   optional field `cartorios:` at the TOP of the plan (sibling of `schema_version`/`mode`,
   documented in `common/plan-schema.yaml`) — it is the data `cepa-dor` uses
   to veto only the intersection that falls on a real notary file, instead
   of any crossing. Insufficient history → the script says so
   explicitly; leave `cartorios:` absent, do not invent the list.

5. **Intake gate.** Run:

   ```
   python3 common/bin/cepa-dor <main-root>/.claude/programs/<name>/plan.yaml --wave 1 --repo .
   ```

   For each NOT-READY, fix it WITH the user (adjust globs, record the
   human_gate decision, write acceptance_cmd) and run again, until wave 1
   comes out READY (⚠ warnings are acceptable and get noted in the plan). Repeat for
   the other waves if the user wants to get ahead.

6. **Closing.** Show cepa-dor's final verdict and the plan's path.
   Say explicitly: execution is `/maestro:run` (not built yet —
   step 3 of the build order; until then, the plan serves for manual waves
   with worktrees, as in v0).

## Notes

- This command does NOT execute demands, does not create worktrees, does not bring up the gatekeeper.
- **[from-plan:queue-untouched]** Promoting does not touch the queue: `cepa-plan promote`
  only reads, and the items remain `pending` there. The queue remains the document of the
  ORDER; the waves plan is a hypothesis about a slice of it. The risk that
  remains is human and is worth saying out loud to the user at the close: the same
  item now has two possible executors (`/common:drain-plan` and the wave), and
  running both builds it twice.
- Surface is a promise about writing, not reading — the child may read the whole
  repo; it only writes inside the globs (layer 1 of the generated settings).
- The enforcement zone (plugins/, hooks/, .claude/settings*, plugin-cache) is an
  unconditional veto of cepa-dor: no slice glob may include it.
- Undeclared high-friction files (lockfiles, migrations, index/barrel)
  become a warning, not a veto — the post-merge verify of the merge train is what catches
  incidental conflicts.
- `acceptance_form: substrate` is not an escape hatch: it is a **declaration**. A
  substrate slice accepts being verified by a technical criterion because nobody
  pretends it has an observable surface. Marking `substrate` on a demand that
  the user can see is lying to the gate — and the gate believes it.
