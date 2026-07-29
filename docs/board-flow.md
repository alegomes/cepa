# board-flow

The Jira lifecycle layer. Pairs with any topology to keep cards in
sync with build/discovery state.

## Config file: `board-flow.yaml` at project root

Project-team data — your team's Jira site, project, board, status names.
Lives at the **project root** (not under `.claude/` — that directory is
for CC plumbing). Visible to `ls`, version-controlled.

Created by `bin/install.sh --topology=NAME` with placeholders. Replace
the placeholders by hand or run `/board-flow:configure` for an
interactive walkthrough.

### Full schema

```yaml
schema_version: 1

# --- Defaults: identity values for every Jira operation ---
defaults:
  site: acme.atlassian.net           # YOUR Jira cloud site
  project_key: ACME                  # default project for new cards
  board_id: 766                      # default board, used by /board-flow:drain
  status_map:
    # Literal Jira status names. Backlog is implicit (project's create
    # default); to_do is "refined and ready" — what /board-flow:drain
    # pulls from. The split between Backlog and to_do is the team's
    # grooming convention — drain only pulls from to_do, so unrefined
    # items in Backlog stay safe.
    to_do:       "To Do"
    in_progress: "In Progress"
    in_review:   "In Review"
    blocked:     "Blocked"           # set to null if your project lacks this status
  issue_types:
    story: "Story"
    bug: "Bug"
    epic: "Epic"
    task: "Task"
  required_fields:
    # Custom fields with project-mandated defaults. Auto-filled on
    # every createIssue.
    - { id: customfield_10010, name: "Team", value: "Engineering" }
  scope:
    # Raw JQL fragment AND-ed into the *-drain column queries. '' = whole
    # column. See "Scoping the *-drain commands" below.
    jql: 'sprint in openSprints()'
  scope_overrides:
    # Per-command scope. Keys: drain, prove_drain, triage. Replaces defaults.scope
    # for that command.
    prove_drain: { jql: 'labels = needs-review' }

# --- Default topology for build/validate flows ---
default_topology: build-hex       # which topology's leads /board-flow:execute delegates to

# --- Per-topology overrides (optional) ---
# When a topology is active, fields here REPLACE the matching field
# in `defaults` for that topology's operations. Common use: same Jira
# project, different Team field per topology (engineering vs product).
topologies:
  discovery:
    required_fields:
      - { id: customfield_10010, name: "Team", value: "Product" }
    # project_key: DISC          # if discovery uses a different Jira project
  build-hex:
    required_fields:
      - { id: customfield_10010, name: "Team", value: "Engineering" }
    scope: { jql: 'component = backend' }   # drain backend work only when build-hex is active

# --- Lifecycles for /board-flow:advance ---
lifecycles:
  - topology: discovery
    project_key: WEGO
    issue_type: Story
    columns:
      - { name: Inbox,       status: "To Do" }
      - { name: Framing,     status: "Framing",     on_enter: opportunity-framer }
      - { name: Researching, status: "Researching", on_enter: user-researcher }
      - { name: Validating,  status: "Validating",  enter_gate: "assumption-tester wrote test plan" }
      - { name: Validated,   status: "Validated",   enter_gate: "evidence-auditor verdict = Confirmed" }
      - { name: "Handed off", status: "Done",       on_enter: epic-briefer }
      - { name: Discarded,    status: "Won't Do" }
```

### Field-by-field

- **`defaults.site`** — your Jira cloud hostname (e.g.,
  `acme.atlassian.net`). `atlassian-expert` is forbidden to infer this
  from your repo name or any other context; missing here means every
  Jira write refuses.
- **`defaults.project_key`** — default Jira project key for new cards.
  Operations targeting a different project must name it explicitly in
  the orchestrator's request.
- **`defaults.board_id`** — numeric board ID (find in Jira's URL when
  viewing the board: `/jira/software/projects/<KEY>/boards/<ID>`). Used
  by `/board-flow:drain` to query the board's columns.
- **`defaults.status_map`** — literal Jira status names. Different teams
  call them different things (`"Doing"` / `"Code Review"` / `"Done"`
  vs. defaults). Commands read this map instead of hardcoding strings.
  Four entries:
  - `to_do` — refined-and-ready column. `/board-flow:drain` pulls from
    here, NOT from Backlog. The split is intentional: Backlog holds
    unrefined items the team hasn't groomed yet; `to_do` holds items
    ready for development.
  - `in_progress` — `/board-flow:execute` and `/common:autonomous-start`
    transition into this when work begins.
  - `in_review` — destination after the flow completes successfully,
    with an Implementation Summary comment. **Must match the board's
    literal name** — some boards call this column `"Review"`, not
    `"In Review"`. `/board-flow:prove` and `/board-flow:prove-drain` pull
    from this status, so a mismatch makes them find zero cards.
  - `blocked` — optional; if your project lacks a Blocked column set
    to `null` and blocked cards stay in `in_progress` with a comment.
  - `done` — optional; the status *after* `in_review`. When set,
    `/board-flow:prove` auto-advances a PROVEN card here. Leave unset
    (or `null`) for triage-only: a PROVEN card gets a ✅ comment but
    stays in Review for you to move manually. See
    [proof-gate.md](proof-gate.md).
- **`defaults.issue_types`** — literal type names for `createIssue`
  calls. Standard names usually work; custom Jira setups may differ.
- **`defaults.required_fields`** — project-mandated custom fields with
  default values, auto-filled on every `createIssue`. Format:
  `{id, name, value}` objects. Currently only supports static defaults
  (no per-card overrides via this mechanism).
- **`defaults.scope`** — a raw JQL fragment (`{ jql: '...' }`) that
  narrows which cards the auto-selecting `*-drain` commands sweep. `''`
  (the default) means whole-column, the original behavior. See
  [Scoping the *-drain commands](#scoping-the--drain-commands) below.
- **`defaults.scope_overrides`** — per-command scope. Keys are command
  names (`drain`, `prove_drain`, `triage`); each is a `{ jql: '...' }` that
  *replaces* `defaults.scope` for that one command. Lets you, e.g.,
  scope `drain` to a sprint but `prove_drain` to a review label, or
  `triage` to a single epic's children.
- **`default_topology`** — which build topology
  `/board-flow:plan-track-build-validate` and `/board-flow:execute`
  delegate to (e.g., `build-hex` → `build-hex:engineering-lead`).
- **`topologies.<name>`** — per-topology overrides applied when that
  topology is the active one. Each block can override any field from
  `defaults` (most useful: `required_fields`, `project_key`,
  `status_map`, `scope`). Common use: same Jira project, different `Team`
  field per topology (Engineering for build-hex, Product for
  discovery). Merge semantics: per-field replacement, atomic for
  lists (the topology's `required_fields` replaces the entire
  `defaults.required_fields`, not merged item-by-item). Topologies
  without a block here inherit `defaults` wholesale.
- **`lifecycles[]`** — custom column workflows for `/board-flow:advance`.
  Each lifecycle has `project_key`, optional `issue_type`, and an
  ordered `columns[]` list with optional `on_enter` agent and
  `enter_gate` precondition.

### Active-topology resolution order

When `atlassian-expert` does a write operation, it picks which
`topologies.<active>` block to merge over `defaults`:

1. **Explicit `Topology: <name>` line** in the orchestrator's
   delegation prompt (preferred — commands include this for write
   operations).
2. **`.claude/topology`** marker file (one-line text).
3. **`defaults.default_topology`** from the config.
4. **No topology resolvable** → use `defaults` alone.

For read operations (`getJiraIssue`, `searchJiraIssuesUsingJql`),
topology overrides usually don't matter — `defaults` is enough.

## Scoping the *-drain commands

By default `/board-flow:drain` and `/board-flow:prove-drain` sweep an
*entire* status column (`to_do` and `in_review` respectively). On a busy
board that's often more than you want to process in one run. **Scope**
narrows the sweep to a slice — a sprint, a team, a component, a label —
declared once in `board-flow.yaml` instead of typed on every invocation.

`scope.jql` is a **raw JQL fragment**, AND-ed into the command's status
query before ordering:

```
status = "<column>" AND (<effective scope>) ORDER BY priority, rank
```

Write it exactly as you'd type it into Jira's advanced search — the
parentheses are added for you. An empty fragment (`''`) is the original
whole-column behavior.

### Precedence

When more than one scope could apply, the **effective scope** is resolved
by precedence — *first match wins, no merging* (a more specific level
*replaces* the baseline, it does not AND onto it):

1. `--no-scope` flag → no scope at all (full column).
2. `--scope "<jql>"` flag → that fragment, this run only.
3. `defaults.scope_overrides.<command>.jql` (per-command; keys `drain`, `prove_drain`).
4. `topologies.<active>.scope.jql` (per-topology; active topology resolved as for any override).
5. `defaults.scope.jql` (the baseline).
6. None of the above non-empty → no scope.

`atlassian-expert` does the resolution centrally (it already reads the
config); the commands just pass it a `Command:` line and any flag. The
effective fragment is always echoed on the drain's confirmation screen
and final report, so an empty result from an over-narrow filter reads as
"scope excluded everything," never as "the board is empty."

### Per-run flags

Both drains accept:

- `--scope "<jql>"` — override the configured scope for this run.
- `--no-scope` — ignore configured scope entirely; sweep the whole column.

They're mutually exclusive. Example:

```sh
/board-flow:prove-drain --max 10 --scope 'labels = hotfix'
/board-flow:drain --no-scope        # whole To Do column, ignore config
```

### Single-card commands warn, they don't filter

`/board-flow:execute`, `/board-flow:prove`, `/board-flow:fix`, and
`/board-flow:advance` act on a card you named by key — so scope can't
*select* for them. Instead they **warn and proceed**: if the named card
falls outside the effective scope, you get a one-line heads-up
("⚠ WEGO-1234 is outside the configured scope … running it anyway") and
the command continues. Pass `--no-scope` to silence the warning. This
catches accidental cross-team / cross-sprint work without ever blocking a
deliberate one-off.

> **Known double-warn:** `/board-flow:execute` on a Bug card auto-dispatches
> to `/board-flow:fix`, and both fetch the card — so an out-of-scope Bug
> warns twice (once in `execute`, once in `fix`). It's cosmetic; the work
> still proceeds. `--no-scope` carries through the dispatch and silences
> both.

### What scope does *not* touch

The card-*creation* commands — `/board-flow:capture` and
`/board-flow:plan-track-build-validate` — ignore scope. A raw JQL filter
selects existing cards; it can't supply field defaults for new ones.
Use `required_fields` (and per-topology overrides) to stamp team /
component / label values onto created cards.

## The contract atlassian-expert enforces

The `atlassian-expert` agent (the only Jira write path) has three
non-negotiable rules.

### 1. Read config first, every time

At the start of every invocation, `atlassian-expert` reads
`board-flow.yaml` (falling back to legacy `.claude/board-flow.lifecycle.yaml`).
It extracts the `defaults` block and uses those values verbatim.

### 2. Never infer or fabricate identifiers

Site URLs, project keys, board IDs, issue types, custom field values —
all come from the config or from the orchestrator's request payload.

**Forbidden:** deriving a site URL from the repo name
(`acme-billing-service` → `acme.atlassian.net` is forbidden),
guessing from conversation context, falling back to typical Atlassian
URL patterns, or substituting a value seen in earlier context.

Missing config + missing request → refuse with `BLOCKED: <field> not
found in board-flow.yaml defaults block; cannot infer. Add it to the
config and retry.`

This rule exists because the agent once invented a site URL by pasting
the repo's name prefix in front of `.atlassian.net`, when the real site
was different — a hallucinated URL is worse than asking, because
everyone downstream debugs an auth issue against a site that doesn't
exist instead of seeing the real bug. Two corollaries, both learned the
hard way (2026-07-28):

- **Every hostname in these prompts is deliberately fictional**
  (`acme.atlassian.net`). A negative example that is plausible and
  specific to the repo in front of the agent reads as a suggestion, not
  as a prohibition — the agent that broke this rule had copied the
  hostname straight out of the sentence forbidding it.
- **A missing site is a `BLOCKED`, never an auth request.** Asking the
  user to authorize or reauthorize a site implies the site is real; if
  the hostname was invented, the user goes hunting for permission to a
  domain that doesn't resolve. When auth looks broken, name the
  configured site verbatim so a wrong target is visible at a glance.

### 3. Read-back verification on every write

Every Jira write tool is followed by an immediate read to confirm the
write actually landed:

| Write | Read-back |
|---|---|
| `createJiraIssue` → returns key | `getJiraIssue(key)` — confirms exists. Else `BLOCKED: create reported success but card does not exist.` |
| `transitionJiraIssue` | `getJiraIssue` + assert `status.name == target_status`. Else `BLOCKED: transition reported success but card is in <actual_status>.` |
| `addCommentToJiraIssue` | Fetch recent comments, confirm body matches. Else BLOCKED. |
| `editJiraIssue` | `getJiraIssue` + assert field changed. Else BLOCKED. |
| `createIssueLink` | Fetch links, confirm exists. Else BLOCKED. |

Doubles MCP calls per write; that's the price of honesty. Never trust
the write response in isolation. Never fabricate "succeeded" because
the call returned 200.

## Implementation Summary contract

Every transition into a status whose name contains `review` or `qa`
(case-insensitive) — or any column flagged `requires_summary: true` in
a custom lifecycle — requires an **Implementation Summary** posted as a
comment **before** the transition. Sequence is comment-first,
transition-second so anyone watching the card sees the rationale before
the status change.

Canonical template:

```markdown
## Implementation summary

**Files touched:**
- `<path1>`
- `<path2>`

**Tests added/updated:**
- `<test path>`

**Build verification:** `./mvnw verify` → BUILD SUCCESS (commit `<SHA>`)

**Caveats / follow-ups:**
- <none, or list>
```

Producers of this summary:

- `/board-flow:execute` step 7 — assembled from `engineering-lead`'s
  report + `qa-engineer`'s BUILD SUCCESS evidence.
- `/board-flow:plan-track-build-validate` step 8 — same.
- `/common:autonomous-start` step 9 — same, with the run-id appended.
- `/board-flow:advance` step 6 — assembled from preceding flow context if
  available; otherwise asks the user.

If the orchestrator's delegation reaches `atlassian-expert` without a
summary on a review-style transition, `atlassian-expert` refuses with
`BLOCKED: review-style transition requires Implementation Summary;
re-delegate with the summary.` This is agent-level enforcement —
hard-coded, can't be bypassed by command drift.

## The execution plan (`mode: single-track`)

Jira stores the **queue** — the To Do column — and neither the **order** you
decided to work it in nor the **why** behind that order. Both used to live only
in the chat that produced them, so a session boundary erased them. The symptom
was a specific question, asked after hours of work with detours: *what do I do
next — validate this by hand, or pull another card?*

`/board-flow:triage` is where the order is actually decided, so it is where the
order gets written down: `.claude/programs/<project_key>/plan.yaml`, one living
plan per board, schema annotated in
[`common/plan-schema.yaml`](../common/plan-schema.yaml).

```yaml
schema_version: 2
mode: single-track
program: ACME
source: "Jira ACME · To Do, triaged 2026-07-28"
items:
  - id: ACME-1235
    title: "Block a bounce comment with no reason"
    why: "first — unblocks 1237 and 1240, which touch the same hook"
    status: pending
    blocked_by: []
    human_pending: null
```

Three fields carry the three losses:

| Field | Answers |
|---|---|
| the order of `items` | "which one was first, again?" |
| `why` | "does this order still make sense?" — without it you re-prioritise from scratch |
| `human_pending` | "do I still have to validate this by hand?" |

`human_pending` is fed from the **Human validation route** of the Implementation
Summary — a field that is already mandatory (the `summary-nulls-gate` hook
blocks the comment without it) and was simply never aggregated anywhere.

**Same schema as the maestro, different mode.** `mode: parallel-waves` is the
maestro's (waves of slices forked into worktrees, floor of ≥4 demands);
`single-track` is one item at a time across sessions. Neither plugin depends on
the other — both read the schema in `common`. Point a single-track plan at
`/maestro:run` (or at `cepa-dor`) and it refuses by naming the right command,
instead of failing downstream with "no pending wave".

Schema **v2** is where `mode` became explicit and required. **v1** (waves only,
no `mode`) is still read by every consumer, so plans already on disk need no
migration — but `mode: single-track` in a v1 plan is an error, and the consumer
tells you to raise the version rather than guessing what you meant.

**The plan is a hypothesis, not a contract** — whoever executes an item
re-validates it against the board's current state. Re-running triage merges into
the plan rather than overwriting it: `done` items keep their `human_pending`,
and cancelled cards become `dropped` so the plan still explains why they left.

### Reading the plan: `/board-flow:next`

The plan answers the question only if something asks it. Three moments do:

| When | What answers |
|---|---|
| A card closes | `execute` / `fix` / `prove` end with "And now?" |
| Mid-session, thread lost | **`/board-flow:next`** |
| The order needs deciding | `/board-flow:triage` writes it |

`/board-flow:next` reconciles the plan against the live board before answering —
a card marked `pending` may already be done, and one marked `done` may have
bounced back. Every divergence is named rather than absorbed, because each one
means something happened outside the plan, and a plan that silently absorbs
reality is a plan that lies. Cards sitting in To Do but absent from the plan are
reported, never folded in: they were never given a position or a rationale, and
inventing one would forge the decision this whole mechanism exists to preserve.

It ends with **one** recommendation and its `why` — never a menu, since a list
of equally-weighted options is precisely the state you're stuck in when you run
it. Read-only unless you pass `--sync`.

**Closing human debt is the user's move alone.** A `human_pending` clears by
becoming `null`, and only the person who ran the route can say it ran — never a
green test, a card status, or elapsed time. A list that closes itself is
decoration, and the debt goes back to being invisible.

## Composition rules

- **Lead-based commands** (`/board-flow:execute`,
  `/board-flow:plan-track-build-validate`) require a topology with
  `planning-lead` + `engineering-lead` + `validation-lead`. `build-hex`
  and `build-team` ship those; `build-solo` doesn't.
- **Generic commands** (`/board-flow:advance`, `/board-flow:capture`,
  `/board-flow:drain`, `/board-flow:configure`) work with any topology
  (including `build-solo` and `discovery`).
- **Discovery's column flow** rides on `/board-flow:advance` reading the
  `discovery` entry in `lifecycles[]`. No `/discovery:advance` — the
  generic command does the work.

## Migration from legacy config location

Earlier the config lived at `.claude/board-flow.lifecycle.yaml`. It
moved to `board-flow.yaml` at project root (visible, not hidden under
plugin plumbing). Every command falls back to the legacy location with
a one-time deprecation note if the new file is absent.

To migrate manually:

```sh
mv .claude/board-flow.lifecycle.yaml board-flow.yaml
```

Or use `/board-flow:configure --migrate` (offers to move + delete the
legacy file in one step).
