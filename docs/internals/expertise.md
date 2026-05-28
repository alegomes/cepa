# Expertise files

The per-agent learning store. Read at task boot, updated at task end,
written to by `/common:debrief` after autonomous runs.

## File location and the symlink trick

Live at `common/expertise/<agent>-mental-model.yaml` in the plugin
source.

In a host project, `bin/install.sh` creates a symlink:

```
<host-project>/.claude/expertise/  →  <plugin-source>/common/expertise/
```

Result: every agent in every project reads and writes the **same**
expertise files. Accumulated learnings follow you across projects
instead of being trapped per-project.

Why a symlink and not a copy: copies drift. A learning recorded in
project A wouldn't reach project B. The symlink keeps the single
source of truth in the plugin, accessed via a project-local path.

### Why `<agent>-mental-model.yaml` not just `<agent>.yaml`

The `is_own_expertise_file` structural check in path-lock requires
both the filename suffix (`-mental-model.yaml`) AND the parent
directory name (`expertise`). The redundancy is defensive — without
the structural pattern, an agent could write a same-named file
elsewhere and the hook would think it was the expertise file.

## File shape

```yaml
# common/expertise/engineering-lead-mental-model.yaml
#
# Centralized expertise for the engineering-lead agent. Captures
# agent-global knowledge; project-specific facts go in the host
# project's CLAUDE.md. See common/skills/mental-model/SKILL.md.

last_updated: "2026-05-13"

feedback:
  - run_id: 2026-05-09-wego-1567
    date: "2026-05-09"
    topic: "Rename strategy — big-bang vs deprecation window"
    original_choice: "Option C — big-bang for EQUIPE_CLINICA (internal-only), deprecation window for Arquivo→Documento (more consumers)"
    user_verdict: refine
    user_reason: "I'd have chosen A. We don't have active clients yet. It's time to keep the house clean"
    refined_rationale: "When there are no active external clients, prefer big-bang rename over deprecation windows — transitional routes add complexity without protecting anyone."
    tag: principle

  - run_id: 2026-05-08-api-fixes-features-batch
    date: "2026-05-09"
    topic: "WEGO-1655 — q='exem' false positives: NOT-A-BUG vs BUG"
    original_choice: "Conclusão NOT-A-BUG: todos os pedidos do seed têm @exemplo.com"
    user_verdict: overrule
    user_reason: "A conclusão foi prematura. Existem pedidos com signatarios:[] que ainda aparecem no resultado..."
    tag: principle
```

### Top-level fields

| Field | Required | Description |
|---|---|---|
| `last_updated` | Yes | ISO date of the most recent edit. The `mental-model` skill checks staleness; the `debrief` command refreshes on every write. |
| `feedback` | Optional (empty list = `feedback: []`) | List of feedback entries from `/common:debrief`. New entries appended; capped at 20 (with `principle` exemption). |
| Other | Yes | Agent-specific top-level keys for free-form mental model content. Example: `lane: api-rest REST surface` for `api-dev`. |

### Reserved sections

Three top-level keys carry schema meaning across the marketplace:

| Section | Owner | Purpose |
|---|---|---|
| `feedback:` | `/common:debrief` (machine-written) | Per-decision verdicts from user. Schema below. |
| `heuristics:` | Worker / lead / human (hand-written) | Durable rules of thumb. Two acceptable shapes: short string (one-line rule) OR structured object with `id` / `when` / `why_it_bites` / `verdict_rule`. Examples in `validation-lead-mental-model.yaml` post-2026-05-28. |
| `ecosystem_gotchas:` | Worker (hand-written) | Optional flat list of one-line version-specific gotchas. |

Other keys (`agent:`, `lane:`, `decisions:`, etc.) are role-specific
free-form context. `/common:debrief` only touches `feedback:`; it
ignores all other sections.

### Feedback entry shape

| Field | Source | Notes |
|---|---|---|
| `run_id` | The autonomous run that produced the decision | Format: `<YYYY-MM-DD>-<slug-or-jira-key>` |
| `date` | When the debrief happened (not the original run date) | ISO date |
| `topic` | The decision's topic line from the formal `### Decision:` block | One-liner |
| `original_choice` | The agent's chosen option from the Decision block | Verbatim |
| `user_verdict` | One of `keep` / `overrule` / `refine` / `skip` | Required |
| `user_reason` | The user's verbatim reason for the verdict | Don't paraphrase; the agent reads this raw |
| `refined_rationale` | Only present when verdict is `refine` | The user's improved rationale |
| `tag` | `principle` or `example` (default: `example`) | `principle` entries are exempt from auto-prune |

## The lifecycle: mental-model skill ↔ debrief

### At task boot — `mental-model` skill loads expertise

The `common/skills/mental-model/SKILL.md` skill instructs every agent
to read its expertise file at the start of every task. The agent
absorbs the `feedback` entries (especially `principle`-tagged) and the
agent-global knowledge before responding.

Without this, accumulated learnings would be ignored. The skill is the
bridge between "expertise file exists" and "agent honors it."

### At task end — `mental-model` skill optionally updates

The same skill says: update the expertise file at task end with
non-obvious learnings. Specifically:

- New patterns you noticed about this kind of work.
- Counter-intuitive constraints you discovered.
- Trade-offs that became clear only after doing the work.

Not for:
- One-off facts (project-specific → CLAUDE.md).
- Bug-fix recipes (the commit message captures that).
- Repeating what's already in the agent's spec.

The update is gated by the structural-exemption path-lock check, so
any agent can write its own expertise file regardless of plugin or
project layout.

### After a debrief — feedback entries land

`/common:debrief` walks every `### Decision:` block from a run's
artifacts (TASK.md, RESULT.md, investigation reports, MERGE.md). For
each:

1. Surface the decision to the user with topic + options + chosen +
   rationale.
2. Take the user's verdict.
3. Append an entry to the relevant agent's expertise file under
   `feedback`.

The relevant agent is whoever authored the artifact containing the
Decision block. Path-lock allowlists indicate ownership: a Decision in
`docs/tasks/<story>/<task>.md` belongs to `engineering-lead` (the only
agent allowed to write `docs/tasks/**`); a Decision in
`<task-slug>-result.md` belongs to the dev worker that wrote the
RESULT.

### Format drift detection

When the dual-scan in `/common:debrief` finds informal decision prose
(no formal `### Decision:` heading) outnumbering formal blocks, the
command surfaces the drift loudly and offers to record a
`principle`-tagged feedback entry on each drifting agent:

```yaml
- run_id: 2026-05-09-seed-q-filter-status-bugs
  date: "2026-05-09"
  topic: "format compliance — investigation report decisions"
  user_verdict: overrule
  user_reason: "Used a markdown table instead of the required ### Decision: blocks. Future runs MUST use the formal block — Options considered / Chosen / Rationale — even for single-option decisions."
  tag: principle
```

The `principle` tag protects the entry from auto-prune. The next run
boots with this rule in context, and (in practice) the agent uses the
formal block.

## The 20-entry cap

Each agent's `feedback` list caps at **20 entries**. When at cap, the
debrief command prunes the oldest non-`principle` entries first.
`principle`-tagged entries never auto-prune.

Rationale:

- Without a cap, files grow unbounded; eventually the boot read takes
  meaningful context.
- The most recent entries are the most predictive (project state
  evolves).
- Principles encode permanent corrections that shouldn't be lost just
  because they're old.

To manually prune, edit the file directly. To explicitly tag a
prior-recent entry as `principle` (preventing prune), edit `tag:
example` → `tag: principle`.

## Reading order at agent boot

The `mental-model` skill instructs the agent to:

1. Read the expertise file.
2. Pay special attention to `principle`-tagged feedback entries (these
   are durable corrections).
3. Read recent `example`-tagged entries (recent project context).
4. Note `last_updated`; if stale (e.g., 6+ months old), be cautious —
   patterns may have evolved.

## What expertise files don't store

- **Project-specific facts.** `WEGO is on Jira project key WEGO` is
  per-project — goes in the host's `CLAUDE.md` or `jira-flow.yaml`.
  Not in the cross-project expertise.
- **Sensitive data.** Expertise files are version-controlled in the
  plugin repo. Don't put credentials, tokens, customer data, etc.
- **Detailed runbooks.** If you find yourself writing a checklist of
  10+ steps, that's documentation (`docs/`). Expertise is "mental
  model" — patterns and principles, not procedures.

## Agent-global vs. project-specific (the guardrail)

The `mental-model` skill explicitly states: expertise captures
**agent-global** knowledge; **project-specific facts go in CLAUDE.md**.

Example of agent-global:
> "When there are no active external clients, prefer big-bang renames
> over deprecation windows."

Example of project-specific (does NOT belong in expertise):
> "WEGO's API is consumed by partner Acme via their `/integrate`
> endpoint."

The agent-global rule applies to every project this agent works on.
The project-specific rule is irrelevant outside this project. Mixing
them poisons cross-project applicability.

When a debrief verdict's reason is project-specific, the user should
overrule the principle interpretation and frame it agent-globally
before saving. (Today this is manual discipline; future tooling could
detect the pattern.)

## Adding a new expertise file

When you add a new agent to the marketplace, also add its expertise
stub:

```sh
cat > common/expertise/<agent-name>-mental-model.yaml <<'EOF'
# Centralized expertise for the <agent-name> agent. Captures
# agent-global knowledge; project-specific facts go in the host
# project's CLAUDE.md. See common/skills/mental-model/SKILL.md.

last_updated: null
EOF
```

Then the agent body should reference the file at task boot per the
[agent-anatomy](agent-anatomy.md) convention.

## Memory references

- `common/skills/mental-model/SKILL.md` — the skill that reads and
  writes expertise.
- `/common:debrief` command spec — the writer of `feedback` entries
  with format-drift dual-scan.
- `user_preferences` memory — the user's recurring framing on
  "principle vs example" tagging.
