# Loop engineering — scheduled autonomous routines

> **Status:** Path A plugin-side **scaffolded + server live-verified** (slice
> `session/loop-pathA`; server choice corrected 2026-06-30). Server is the community
> **`mcp-atlassian`** (sooperset, uvx, static API token), **not** the Rovo HTTP server the
> first scaffold targeted — a live probe on 2026-06-30 read real WEGO cards through it
> headless with zero org-admin gating, so the binding was flipped to it. `atlassian-expert`
> dual-bound (OAuth + `mcp-atlassian`, with a tool-name translation table), preflight added,
> `.mcp.json` template shipped. Remaining: a live **scheduled-run** test (the interactive
> probe passed; the cloud-cron path is still unproven). Reconstructed from the parked
> `session/loop-engineering` design (2026-06-19), brought current to the post-rebrand world
> (`cepa`, `board-flow`).

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
| **A** ✅ | **Static API token** — register an Atlassian MCP server that authenticates with an `id.atlassian.com` API token in `.mcp.json` / routine env. | **Chosen.** Survives headless; unblocks *all* routines at once. |
| **B** ❌ | `/loop` in a live, interactive session (OAuth already warm). | Rejected. Pins one live session per routine — doesn't scale to a fleet. |

Within Path A there was a **second fork — which token server** — and the first scaffold
picked wrong. See §1 below.

## Path A — the foundation (this slice)

Three parts. Part 2 is the non-trivial one (plugin surgery).

### 1. Register a static-token Atlassian MCP server — ✅ resolved: community `mcp-atlassian` (sooperset)

**Server chosen: the community `mcp-atlassian` server (sooperset)**, run as a local `uvx`
subprocess (`uvx --python 3.13 mcp-atlassian`) authenticated from a static API token in its
own `env` block (`JIRA_URL` / `JIRA_USERNAME` / `JIRA_API_TOKEN`). Because the credential is
config-time, not session-time, it survives headless/scheduled runs.

> **The first scaffold targeted the wrong server.** It picked Atlassian's official Rovo MCP
> (remote HTTP, `mcp.atlassian.com`, `Authorization: Basic` header) on the theory that its
> tool base-names match the OAuth connector exactly, making the re-bind a one-line prefix add.
> Two problems surfaced on re-evaluation (2026-06-30): (a) the Rovo server needs an **org admin
> to enable API-token auth** — the gate that was stalling the owner steps — and was never
> live-tested; (b) it wasn't even connected in this environment. Meanwhile `mcp-atlassian`
> **was** connected, and a live probe (`jira_get_all_projects` + a `jira_search` on `WEGO`)
> **returned real cards headlessly with no admin gating**. Lower friction, actually verified —
> so the binding was flipped to it. The cost: its tool names are **different** (snake_case
> `jira_search`, not `searchJiraIssuesUsingJql`), so the re-bind needed a translation table,
> not a prefix add (see §2).

Template: **`board-flow/atlassian-mcp.example.json`** — copied into the *host* project's
`.mcp.json`, with the token supplied via `${JIRA_API_TOKEN}` env, never the literal token in
git. The token is a **personal API token the owner generates** (id.atlassian.com → API token);
crucially, **no org-admin action is required**. The site is **fixed by `JIRA_URL`** at
config time — there is **no `cloudId`** to resolve, and `JIRA_URL` must match
`defaults.site` in `board-flow.yaml` or the preflight hard-fails.

> ⚠ **Secret hygiene.** The currently-working install configures `mcp-atlassian` in
> `~/.claude.json` with the API token written **inline in plaintext**. That is a live
> credential sitting in a config file — the template deliberately uses `${JIRA_API_TOKEN}`
> by reference instead, and the owner should migrate the global config to match (and rotate
> the token if it has ever been synced/backed up).

### 2. Re-bind `atlassian-expert` — ✅ done (dual-bind + translation table)

`board-flow/agents/atlassian-expert.md` is now **dual-bound**: the `tools:` frontmatter lists
both `mcp__claude_ai_Atlassian__*` (OAuth, interactive) **and** `mcp__mcp-atlassian__*`
(token, headless). Because the two servers use **different tool vocabularies**, a new *Tool
binding* section carries a **translation table** (camelCase `getJiraIssue` ↔ snake_case
`jira_get_issue`, etc.); the doc keeps the OAuth camelCase names as its canonical vocabulary
and the agent translates when on the token server. The agent prefers the token server when
connected and falls back to OAuth otherwise — so the zero-config OAuth path still works for
interactive users while headless runs are unlocked.

### 3. Read-board-or-hard-fail preflight — ✅ done

> **The single most important safety rule.** The failure mode is *silent success*.

Every routine's **first act** must prove it can READ the board (a probe against the configured
project), and **hard-fail loudly** if it can't — never proceed as if the board were simply
empty. A real empty column and a broken auth connection must produce **different,
unmistakable** outcomes. Implemented as the **Board-read preflight** rule in
`atlassian-expert.md`: the first Jira op of a run probes `jira_get_all_projects` (token
server) / `getVisibleJiraProjects` (OAuth) and confirms the configured `project_key` is in
the list; on failure it replies `BLOCKED: … AUTH/connection failure, NOT an empty board`
instead of returning zero cards.

### What remains for the owner to finish Path A

1. Generate a personal id.atlassian.com API token. **No org-admin step needed.**
2. `export JIRA_API_TOKEN='…'` in the routine env (and migrate the inline token in
   `~/.claude.json` to this by-reference form — see the secret-hygiene note in §1).
3. Copy `board-flow/atlassian-mcp.example.json`'s `mcpServers` block into the host project's
   `.mcp.json`, setting `JIRA_URL` to match `defaults.site`.
4. **Live SCHEDULED-run test** (the interactive probe already passed 2026-06-30): create one
   `/schedule` cloud-cron routine and confirm `mcp-atlassian` is actually present and
   authenticated in the cloud session — the open premise is whether a local `uvx` stdio server
   + its env survive the cloud-cron substrate. If it doesn't, that's the real Path A blocker,
   not auth. Also confirm the preflight fails loudly when the token is wrong.

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
