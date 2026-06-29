# Loop engineering — scheduled autonomous routines

> **Status:** Path A plugin-side **scaffolded** (slice `session/loop-pathA`, 2026-06-29) —
> server chosen (official Rovo, API-token), `atlassian-expert` dual-bound, preflight added,
> `.mcp.json` template shipped. Remaining: owner supplies the token + a live read-the-board
> test (see end of Path A). Reconstructed from the parked `session/loop-engineering` design
> session (2026-06-19), brought current to the post-rebrand world (`cepa`, `board-flow`).

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

### 1. Register a static-token Atlassian MCP server — ✅ resolved: official Rovo, API-token mode

**Server chosen: Atlassian's official Rovo MCP server in API-token mode** (remote HTTP,
`https://mcp.atlassian.com/v1/mcp`). A 2026 capability that postdates the original design
session — it authenticates from a static `Authorization: Basic base64(email:token)` header,
so it survives headless/scheduled runs. Decisive advantage over the community servers
(`sooperset/mcp-atlassian`, `aashari`): it exposes the **exact same tool base-names** as the
OAuth connector (`searchJiraIssuesUsingJql`, `transitionJiraIssue`, …), which turns Part 2
from a rewrite into a prefix add.

Template: **`board-flow/atlassian-mcp.example.json`** — copied into the *host* project's
`.mcp.json`, with the credential supplied via env (`${ATLASSIAN_MCP_BASIC_AUTH}`), never the
literal token in git. The token is a **secret only the owner can generate**
(id.atlassian.com → API token), and an **org admin must enable** API-token auth in
Atlassian Administration → Rovo → Rovo MCP server. The token is **not bound to a `cloudId`**,
so `atlassian-expert` resolves it via `getAccessibleAtlassianResources` on first use.

### 2. Re-bind `atlassian-expert` — ✅ done (dual-bind)

`board-flow/agents/atlassian-expert.md` is now **dual-bound**: the `tools:` frontmatter lists
both `mcp__claude_ai_Atlassian__*` (OAuth, interactive) **and** `mcp__atlassian__*` (Rovo
token, headless), and a new *Tool binding* section tells the agent to prefer the token prefix
when available and fall back to OAuth otherwise. Because the base-names are identical, the
entire operational prose stayed valid — no capability-abstraction rewrite needed. This keeps
the zero-config OAuth path working for interactive users while unlocking headless runs.

### 3. Read-board-or-hard-fail preflight — ✅ done

> **The single most important safety rule.** The failure mode is *silent success*.

Every routine's **first act** must prove it can READ the board (a probe against the configured
project), and **hard-fail loudly** if it can't — never proceed as if the board were simply
empty. A real empty column and a broken auth connection must produce **different,
unmistakable** outcomes. Implemented as the **Board-read preflight** rule in
`atlassian-expert.md`: the first Jira op of a run probes `getAccessibleAtlassianResources` /
`getVisibleJiraProjects`; on failure it replies `BLOCKED: … AUTH/connection failure, NOT an
empty board` instead of returning zero cards.

### What remains for the owner to finish Path A

1. Generate an id.atlassian.com API token; have an org admin enable Rovo API-token auth.
2. `export ATLASSIAN_MCP_BASIC_AUTH=$(printf '%s' 'you@co.com:TOKEN' | base64)` in the routine env.
3. Copy `board-flow/atlassian-mcp.example.json`'s `mcpServers` block into the host project's
   `.mcp.json`.
4. **Live test:** delegate a board read to `atlassian-expert` and confirm it returns cards via
   `mcp__atlassian__*` (and that the preflight fails loudly when the token is wrong).

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
