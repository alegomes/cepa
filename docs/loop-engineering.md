# Loop engineering — scheduled autonomous routines

> **Status:** design + Path A in progress (slice `session/loop-pathA`, started 2026-06-29).
> Reconstructed from the parked `session/loop-engineering` design session (2026-06-19),
> brought current to the post-rebrand world (`cepa` marketplace, `board-flow`, `build-*`).

## The goal

A **fleet of scheduled, unattended routines** that drain the Jira board on their own —
no human typing a slash command into a live session. Each routine is a `/schedule`
cloud-cron job that wraps one existing board-flow command:

| Routine | Column it works | Command it wraps | Exists? |
|---|---|---|---|
| triage | Backlog | `/board-flow:triage` | ✅ |
| **execution** | **To Do** | `/board-flow:drain` | ✅ |
| proof | In Review | `/board-flow:prove-drain` | ✅ |
| security | (validation) | a security-review command | partial |
| enrichment / refinement | Backlog→To Do | a command that **does not yet exist** | ❌ |

The routines form a **pipeline, not independent jobs**: triage grooms Backlog → execution
drains To Do → proof sweeps In Review. Their cron times must be **staggered** (triage
before execution) so they don't race on the same board.

**First routine to build = execution, To-Do column only.** Backlog is deliberately
excluded — unrefined work doesn't become a build.

## The blocker that defines Path A: auth-in-headless

A scheduled routine runs on Anthropic cloud infra, in a **fresh session with no browser**.
The official claude.ai Atlassian connector authenticates with **OAuth**, and:

- the OAuth token is **in-memory per interactive session** — it does not persist to a
  scheduled run;
- a fresh scheduled connection is **unauthenticated**, and the connector's `authenticate`
  tool needs a **browser** to complete the flow.

> **Verdict (researched 2026-06-19, ref Claude Code issue #46228):** a scheduled routine
> using `mcp__claude_ai_Atlassian__*` tools fails **silently** — it connects, reads zero
> cards, and reports "0 tasks, nothing to do." The classic *"ran, did nothing, reported
> success"* trap.

This is why the architectural fork below matters, and why **auth is the foundation** — it
gates every routine at once.

### The fork (resolved)

| Path | Approach | Verdict |
|---|---|---|
| **A** ✅ | **Static API token** — register an Atlassian MCP server that authenticates with an `id.atlassian.com` API token in committed `.mcp.json` / routine env. | **Chosen.** Survives headless; unblocks *all* routines at once. |
| **B** ❌ | `/loop` in a live, interactive session (OAuth already warm). | Rejected. Pins one live session per routine — doesn't scale to a fleet. |

## Path A — the foundation (this slice)

Three parts. Part 2 is the non-trivial one (plugin surgery).

### 1. Register a static-token Atlassian MCP server

Add a token-auth Atlassian MCP server to a committed `.mcp.json` (or routine env). It
registers under a **different server name** → a **different tool prefix** than
`mcp__claude_ai_Atlassian__*`, and likely **different tool base-names** too (e.g.
`jira_search` vs `searchJiraIssuesUsingJql`).

> **Server choice: TBD** — being researched (token-auth Atlassian MCP options: cred model,
> tool naming, headless-friendliness). Candidates: `sooperset/mcp-atlassian`, `aashari`'s
> jira server, others. The exact tool names from the chosen server drive Part 2.

Credentials are a **secret only the owner can generate** (id.atlassian.com → API token).
The committed `.mcp.json` references them via env var (never the literal token in git).

### 2. Re-bind `atlassian-expert` to the new server

Today `board-flow/agents/atlassian-expert.md` is hard-locked to `mcp__claude_ai_Atlassian__*`
in two ways:

- the `tools:` frontmatter line (15 explicit tool names), and
- the prose body, which names specific tools (`getJiraIssue`, `searchJiraIssuesUsingJql`,
  `transitionJiraIssue`, `getTransitionsForJiraIssue`, `addCommentToJiraIssue`, …).

Re-binding means mapping each capability to the new server's tool name, updating both the
frontmatter allowlist and every in-body reference. **This is plugin surgery, not config.**
Open question to settle during the build: do we *replace* the OAuth binding, or make the
agent **dual-bound** (both tool sets in the allowlist) so the same agent works interactively
*and* headless? Dual-binding is more robust but the prose can only name one set cleanly — lean
toward a capability-abstraction (refer to operations, not literal tool names, with a small
tool-name map up top).

### 3. Read-board-or-hard-fail preflight

> **The single most important safety rule.** The failure mode is *silent success*.

Every routine's **first act** must be to prove it can READ the board (a trivial JQL probe
against the configured project), and **hard-fail loudly** if it can't — never proceed as if
the board were simply empty. A real empty column and a broken auth connection must produce
**different, unmistakable** outcomes.

## What's already in place (we're wiring, not building)

- **Card-selection loop:** `/board-flow:drain` already lists To-Do cards in priority order
  and iterates, stopping on first BLOCKED (`board-flow/commands/drain.md`).
- **Per-card autonomous runs:** `/common:autonomous-start` + the `autonomous-checkpoint`
  hook + `docs/autonomous/<run-id>/state.yaml` already handle run-id generation, state, and
  dispatch into the project's topology. `CLAUDE_AUTONOMOUS_RUN_ID` can be set externally
  (the hook just reads `os.environ`), which is exactly what a headless launcher needs.
- **Cron substrate:** the Claude Code `/schedule` skill (cloud routines) is the cron — no
  repo-side scheduler to build.

## Open threads (post-Path-A)

- **Confirmation gate:** `drain`/`triage`/`prove-drain` all require interactive user
  confirmation before acting. An unattended variant must skip that gate — likely by running
  under `autonomous-mode` (which already encodes "never ask the user"), or a `--yes`/headless
  flag. Decide during the execution-routine build, *after* Path A.
- **Concurrency / locking:** no atomic claim today. The Jira status transition (To Do →
  In Progress at run start) is the closest thing to an advisory lock — a card mid-run leaves
  the To-Do query. Good enough for a staggered pipeline; revisit if routines overlap.
- **Per-run hard cap:** `drain` stops on first BLOCKED, but an unattended overnight run wants
  an explicit ceiling on cards/tokens.
- **Cadence:** not fixed. Suggested 1–2×/day for the build routine; staggered after triage.
- **Enrichment command:** does not exist yet — must be built before the enrichment routine.
- **Security routine:** needs a dedicated validation command.

## References

- Recovered design session: `.claude/handoffs/session-loop-engineering.md` (in the main
  checkout; untracked, session-local).
- Autonomous machinery: `common/commands/autonomous-start.md`,
  `common/commands/autonomous-resume.md`, `common/hooks/autonomous-checkpoint.py`,
  `common/skills/autonomous-mode/SKILL.md`, `docs/autonomous-mode.md`.
- Board layer: `docs/board-flow.md`, `board-flow/agents/atlassian-expert.md`,
  `board-flow/commands/drain.md`, `discovery/board-flow.example.yaml`.
