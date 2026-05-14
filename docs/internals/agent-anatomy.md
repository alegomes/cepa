# Agent anatomy

The shape every subagent in this marketplace follows. Same conventions
across topologies — if you're authoring a new agent, mirror an existing
one and you'll fit in.

## File location

`<plugin>/agents/<agent-name>.md` — auto-discovered by CC. Don't
declare `"agents": "..."` in `plugin.json`; that triggers validation
failure.

## YAML frontmatter

```yaml
---
name: domain-dev
description: Use when engineering-lead needs domain logic or use-case code written or modified — pure business rules, aggregates, value objects, ports (in/out), application services. Worker, never delegates further. Write-locked to domain/ and application/ source.
tools: Read, Glob, Grep, Edit, Write, MultiEdit, Bash
model: sonnet
color: green
---
```

### `name` (required)

The agent's identifier. Must match the `agent_type` CC sends in hook
payloads (after stripping `<plugin>:` prefix). Lowercase + hyphens by
convention. Match the filename.

### `description` (required, trigger-critical)

How CC decides when to invoke this agent. Two purposes:

1. **Auto-trigger from main session.** When the orchestrator decides
   "I need someone to do X," CC matches X against agent descriptions
   semantically. Write the description from the **caller's**
   perspective: "Use when you need X." Avoid jargon — use the words a
   lead would use when describing the task.
2. **Self-documenting.** This is what appears in `/agents` listings.

Pattern that works: `Use when <caller> needs <thing>. <Role
positioning>. <Major constraint>.`

Example from `domain-dev`: "Use when engineering-lead needs domain
logic or use-case code written or modified — pure business rules,
aggregates, value objects, ports (in/out), application services.
Worker, never delegates further. Write-locked to domain/ and
application/ source."

### `tools` (required)

Comma-separated CC tool names the agent can use. This is the HARD
guarantee — CC enforces tool allowlists; an agent without `Edit` in
its `tools:` cannot edit, no matter what its prompt says.

Standard sets:

- **Leads** — `Read, Glob, Grep, Task` (+ `Write` if they author specs;
  `Bash` for read-only diagnosis). Never `Edit` / `Write` source code.
- **Workers (code-writing)** — `Read, Glob, Grep, Edit, Write,
  MultiEdit, Bash`.
- **Workers (read-only / advisory)** — `Read, Glob, Grep` (+ `Write`
  if they output reports to a docs allowlist).
- **`atlassian-expert`** — `Read, Glob, Grep` + the Atlassian MCP tool
  names. The ONLY agent in the marketplace with Atlassian MCP access.

### `model` (required)

`opus` or `sonnet`. By convention:

- **Opus** — orchestrator + leads. Larger context, better synthesis.
- **Sonnet** — workers. Faster, cheaper, focused execution.

### `color` (optional)

Used by CC's `/agents` UI for visual differentiation. Pick something
distinct from sibling agents in the same plugin.

## Body section: the standard table header

Every agent body starts with this 6-row table:

```markdown
# Domain Dev

| Field | Value |
|---|---|
| Reports to | `engineering-lead` |
| Delegates to | — (worker, never delegates) |
| Skills | mental-model, active-listener, conversational-response, till-done, scope-discipline, evidence-over-assumption |
| Reads | anywhere |
| Writes | `domain/src/main/**`, `application/src/main/**`, `.claude/expertise/domain-dev-mental-model.yaml` |
| Output | RESULT.md path · summary · paths touched · API/contract changes · invariants added/removed |
```

### `Reports to`

Whoever invokes this agent. For workers, the lead in the same team.
For leads, `orchestrator`. For `atlassian-expert`, `orchestrator (cross-cutting; called from any Jira-aware command)`.

### `Delegates to`

For workers: `— (worker, never delegates)`. The em-dash + clarification
is the convention.

For leads: comma-separated list of subagent names with parenthesized
context (`product-manager + ux-researcher (parallel)` or
`dev workers + per-Task quality loop (qa, refactor-advisor, code-reviewer)`).

### `Skills`

Comma-separated mindset skills (from `common/skills/`) the agent should
honor. Every agent should reference `mental-model` and `active-listener`
at minimum. Add `zero-micromanagement` only for leads and the orchestrator
(it's about *delegating* not executing — meaningless for workers).
`name-the-disagreement` is for synthesizers (leads + orchestrator).

This is a soft reference — CC's skill auto-discovery loads the skills
session-wide anyway. The table entry tells the agent to use them.

### `Reads`

Where the agent can read. Usually `anywhere`. Tighten only for security
reasons (e.g., a reviewer might be limited to a specific subtree).

### `Writes`

Write allowlist, comma-separated. **MUST match the
`ALLOWED_WRITES` entry in the topology's `path-lock.py`** — the
agent's prose and the hook's enforcement should never drift apart.
Convention: end the list with `.claude/expertise/<agent>-mental-model.yaml`
(the structural-exemption file).

### `Output`

What the agent returns to its caller. Use `·` (middle-dot) as
separator. Concrete shape; not vague. Example: `coverage matrix · verdict
(PASS / PASS-WITH-CONCERNS / FAIL) · tests added (paths + names)`.

## Body section: Purpose

A 2-4 sentence paragraph stating what the agent does and what it
emphatically does NOT do. Example from `qa-engineer`:

> You scan the dev worker's RESULT.md and the implemented code for
> coverage gaps. For every gap, assign severity (CRITICAL / HIGH /
> MEDIUM / LOW). A Task may only advance to refactor-advisor if zero
> CRITICAL or HIGH gaps remain. You may add tests yourself in the test
> directories — but never modify production code (route bugs back to
> engineering-lead).

The "but never X" is the negative purpose — the constraint that keeps
the agent in its lane.

## Body section: Rules

Bulleted constraints, each with a bold lead-in. Each rule should have
a "why" embedded (one sentence) so a future reader knows the
motivation. Examples:

- **Don't modify the code under test.** If you find a bug, route it
  back via `engineering-lead`, don't fix it.
- **Realistic data, not unit-test-shaped.** A test using `"foo"` and
  `"bar"` finds nothing real. Use representative payloads.
- **No green build → no PASS.** A `PASS` verdict is only valid after
  you have run `./mvnw <scope> verify` AND observed `BUILD SUCCESS`
  in the literal output.

For agents that participate in a multi-layer enforcement chain (qa →
lead → code-reviewer), each rule cites its layer of the chain and
references the other layers.

## Body section: Workflow

For leads and complex workers, a numbered list of steps. Each step
describes the delegation prompt or action concretely (the agent reads
its own spec at runtime). Cross-references to other agents use
backticks: `qa-engineer`, `code-reviewer`.

For simple workers, the Workflow section can be omitted in favor of a
shorter "What you do" paragraph.

## Body section: Output shape (RESULT.md, etc.)

If the agent produces a file artifact (RESULT.md, MERGE.md,
investigation report), describe the exact section structure here. Use
`-` bullets to list each section, formatted as `**Section** —
one-line description`.

## Body section: closing thought

A one-line summary of what the agent does NOT do, cross-referencing
the agent that owns the adjacent concern. Examples:

- "You do not pick priority (`product-manager`) or write Epics
  (`epic-author`)."
- "Stay in your lane — `atlassian-expert` is the only agent that
  writes Jira state."

## Patterns that vary per role

### Lead agent body

Leads need the per-Task or per-flow workflow section, the synthesis
discipline (`name-the-disagreement`), and the explicit "I delegate;
workers execute" rule. Bash policy is read-only by default; some leads
(hex-backend's `engineering-lead`) extend to branch reconciliation
(`git merge --no-ff`, `git checkout -b`, `git worktree remove`) for
the parallel-worker merge flow.

### Worker agent body

Workers need: failing-test-first discipline (TDD), no-unsolicited-
refactoring rule (`scope-discipline`), Bash policy (verification only,
plus a mandatory commit before returning if invoked in a worktree).

### Reviewer agent body

Reviewers (`refactor-advisor`, `code-reviewer`, `security-reviewer`)
are advisory or gate-style. They emit verdicts (`APPROVE`/`REJECT`,
findings, severity ratings) but don't typically write source. Bodies
emphasize: what triggers their verdict, what evidence they cite,
what threshold for blocking vs. advisory.

## Cross-references between agents

Use backticks for agent names: `engineering-lead`, `qa-engineer`. Be
specific about what gets passed — TASK.md path, RESULT.md path, the
verdict.

## Expertise file reference

Every agent's body should mention its expertise file at task boot:

> Read `.claude/expertise/<agent-name>-mental-model.yaml` at task
> start. Update it at task end with non-obvious learnings (apply the
> `mental-model` skill).

This is what makes accumulated agent learnings persist across
sessions. The structural-exemption in path-lock means agents can
always write their own expertise file, regardless of layout.

## Common mistakes when authoring a new agent

1. **Tool allowlist too generous.** Granting `Edit`/`Write` to a lead
   undoes the structural guarantee that leads delegate. Don't.
2. **Description too vague.** "Reviews code" doesn't trigger
   reliably. "Use when engineering-lead needs..." does. Caller's
   perspective.
3. **Skills list copied verbatim from another agent.** Each agent
   needs only the skills that apply to its role. Workers don't need
   `zero-micromanagement` (they don't delegate).
4. **`Writes` row doesn't match `path-lock.py`.** Hook will block at
   runtime; agent's prose says it should work. Update both, ideally
   in the same commit.
5. **No `Output` row.** Caller can't synthesize a vague reply.
   Specify exactly what comes back.
6. **Workflow section invents subagents.** Cross-references must
   resolve to actual `<plugin>/agents/<name>.md` files.

## When you add a new agent

See [`extending.md`](extending.md)#add-a-new-agent for the checklist.
