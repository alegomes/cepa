# jira-flow

The Jira lifecycle layer. Pairs with any topology to keep cards in
sync with build/discovery state.

## Config file: `jira-flow.yaml` at project root

Project-team data — your team's Jira site, project, board, status names.
Lives at the **project root** (not under `.claude/` — that directory is
for CC plumbing). Visible to `ls`, version-controlled.

Created by `bin/install.sh --topology=NAME` with placeholders. Replace
the placeholders by hand or run `/jira-flow:configure` for an
interactive walkthrough.

### Full schema

```yaml
schema_version: 1

# --- Defaults: identity values for every Jira operation ---
defaults:
  site: wego.atlassian.net           # YOUR Jira cloud site
  project_key: WEGO                  # default project for new cards
  board_id: 766                      # default board, used by /jira-flow:drain
  status_map:
    # Literal Jira status names. Backlog is implicit (project's create
    # default); to_do is "refined and ready" — what /jira-flow:drain
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

# --- Default topology for build/validate flows ---
default_topology: hex-backend       # which topology's leads /jira-flow:execute delegates to

# --- Per-topology overrides (optional) ---
# When a topology is active, fields here REPLACE the matching field
# in `defaults` for that topology's operations. Common use: same Jira
# project, different Team field per topology (engineering vs product).
topologies:
  discovery:
    required_fields:
      - { id: customfield_10010, name: "Team", value: "Product" }
    # project_key: DISC          # if discovery uses a different Jira project
  hex-backend:
    required_fields:
      - { id: customfield_10010, name: "Team", value: "Engineering" }

# --- Lifecycles for /jira-flow:advance ---
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
  `wego.atlassian.net`). `atlassian-expert` is forbidden to infer this
  from your repo name or any other context; missing here means every
  Jira write refuses.
- **`defaults.project_key`** — default Jira project key for new cards.
  Operations targeting a different project must name it explicitly in
  the orchestrator's request.
- **`defaults.board_id`** — numeric board ID (find in Jira's URL when
  viewing the board: `/jira/software/projects/<KEY>/boards/<ID>`). Used
  by `/jira-flow:drain` to query the board's columns.
- **`defaults.status_map`** — literal Jira status names. Different teams
  call them different things (`"Doing"` / `"Code Review"` / `"Done"`
  vs. defaults). Commands read this map instead of hardcoding strings.
  Four entries:
  - `to_do` — refined-and-ready column. `/jira-flow:drain` pulls from
    here, NOT from Backlog. The split is intentional: Backlog holds
    unrefined items the team hasn't groomed yet; `to_do` holds items
    ready for development.
  - `in_progress` — `/jira-flow:execute` and `/common:autonomous-start`
    transition into this when work begins.
  - `in_review` — destination after the flow completes successfully,
    with an Implementation Summary comment. **Must match the board's
    literal name** — some boards call this column `"Review"`, not
    `"In Review"`. `/jira-flow:prove` and `/jira-flow:prove-drain` pull
    from this status, so a mismatch makes them find zero cards.
  - `blocked` — optional; if your project lacks a Blocked column set
    to `null` and blocked cards stay in `in_progress` with a comment.
  - `done` — optional; the status *after* `in_review`. When set,
    `/jira-flow:prove` auto-advances a PROVEN card here. Leave unset
    (or `null`) for triage-only: a PROVEN card gets a ✅ comment but
    stays in Review for you to move manually. See
    [proof-gate.md](proof-gate.md).
- **`defaults.issue_types`** — literal type names for `createIssue`
  calls. Standard names usually work; custom Jira setups may differ.
- **`defaults.required_fields`** — project-mandated custom fields with
  default values, auto-filled on every `createIssue`. Format:
  `{id, name, value}` objects. Currently only supports static defaults
  (no per-card overrides via this mechanism).
- **`default_topology`** — which build topology
  `/jira-flow:plan-track-build-validate` and `/jira-flow:execute`
  delegate to (e.g., `hex-backend` → `hex-backend:engineering-lead`).
- **`topologies.<name>`** — per-topology overrides applied when that
  topology is the active one. Each block can override any field from
  `defaults` (most useful: `required_fields`, `project_key`,
  `status_map`). Common use: same Jira project, different `Team`
  field per topology (Engineering for hex-backend, Product for
  discovery). Merge semantics: per-field replacement, atomic for
  lists (the topology's `required_fields` replaces the entire
  `defaults.required_fields`, not merged item-by-item). Topologies
  without a block here inherit `defaults` wholesale.
- **`lifecycles[]`** — custom column workflows for `/jira-flow:advance`.
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

## The contract atlassian-expert enforces

The `atlassian-expert` agent (the only Jira write path) has three
non-negotiable rules.

### 1. Read config first, every time

At the start of every invocation, `atlassian-expert` reads
`jira-flow.yaml` (falling back to legacy `.claude/jira-flow.lifecycle.yaml`).
It extracts the `defaults` block and uses those values verbatim.

### 2. Never infer or fabricate identifiers

Site URLs, project keys, board IDs, issue types, custom field values —
all come from the config or from the orchestrator's request payload.

**Forbidden:** deriving a site URL from the repo name
(`wego-assinatura-backend` → `wego.atlassian.net` is forbidden),
guessing from conversation context, falling back to typical Atlassian
URL patterns, or substituting a value seen in earlier context.

Missing config + missing request → refuse with `BLOCKED: <field> not
found in jira-flow.yaml defaults block; cannot infer. Add it to the
config and retry.`

This rule exists because the agent once invented `wego.atlassian.net`
when the real site was different — a hallucinated URL is worse than
asking, because everyone downstream debugs an auth issue against a fake
site instead of seeing the real bug.

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

- `/jira-flow:execute` step 7 — assembled from `engineering-lead`'s
  report + `qa-engineer`'s BUILD SUCCESS evidence.
- `/jira-flow:plan-track-build-validate` step 8 — same.
- `/common:autonomous-start` step 9 — same, with the run-id appended.
- `/jira-flow:advance` step 6 — assembled from preceding flow context if
  available; otherwise asks the user.

If the orchestrator's delegation reaches `atlassian-expert` without a
summary on a review-style transition, `atlassian-expert` refuses with
`BLOCKED: review-style transition requires Implementation Summary;
re-delegate with the summary.` This is agent-level enforcement —
hard-coded, can't be bypassed by command drift.

## Composition rules

- **Lead-based commands** (`/jira-flow:execute`,
  `/jira-flow:plan-track-build-validate`) require a topology with
  `planning-lead` + `engineering-lead` + `validation-lead`. `hex-backend`
  and `multi-team` ship those; `solo-pair` doesn't.
- **Generic commands** (`/jira-flow:advance`, `/jira-flow:capture`,
  `/jira-flow:drain`, `/jira-flow:configure`) work with any topology
  (including `solo-pair` and `discovery`).
- **Discovery's column flow** rides on `/jira-flow:advance` reading the
  `discovery` entry in `lifecycles[]`. No `/discovery:advance` — the
  generic command does the work.

## Migration from legacy config location

Earlier the config lived at `.claude/jira-flow.lifecycle.yaml`. It
moved to `jira-flow.yaml` at project root (visible, not hidden under
plugin plumbing). Every command falls back to the legacy location with
a one-time deprecation note if the new file is absent.

To migrate manually:

```sh
mv .claude/jira-flow.lifecycle.yaml jira-flow.yaml
```

Or use `/jira-flow:configure --migrate` (offers to move + delete the
legacy file in one step).
