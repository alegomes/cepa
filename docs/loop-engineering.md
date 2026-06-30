# Loop engineering — scheduled autonomous routines

> **Status:** Path A **cloud auth SOLVED + live-verified** (slice `session/loop-pathA`,
> 2026-06-30). The headless blocker that defined Path A turned out to be a **non-issue for the
> cloud-cron substrate**: a real `/schedule` routine read the live WEGO board through the
> **claude.ai Atlassian OAuth connector** with zero human intervention — its refresh token is
> stored server-side and silently exchanged, so no browser and no warm session are needed.
> The autonomous fleet therefore just **attaches the OAuth connector** to each routine; no
> static token, no `.mcp.json`, no org-admin gate. `atlassian-expert` is **triple-bound**:
> `mcp__claude_ai_Atlassian__*` (local interactive) + `mcp__Atlassian__*` (cloud routine,
> camelCase, the proven path) + `mcp__mcp-atlassian__*` (community uvx server, for a *local*
> headless launcher only). Preflight added. Remaining: build the first real routine
> (execution / To-Do) and the confirmation-gate-skip. Reconstructed from the parked
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

## The blocker that defined Path A: auth-in-headless — RESOLVED (it doesn't apply to cloud)

The original worry (2026-06-19): a scheduled routine runs on Anthropic cloud infra in a
**fresh session with no browser**, the claude.ai Atlassian connector authenticates with
**OAuth**, and the OAuth token was assumed to be **in-memory per interactive session** — so a
fresh scheduled connection would be unauthenticated, read zero cards, and report "nothing to
do" (the silent-success trap, ref Claude Code issue #46228).

> **That assumption was wrong for the cloud-cron substrate. Verified 2026-06-30:** a one-shot
> `/schedule` routine with the `claude.ai Atlassian` connector attached called
> `getAccessibleAtlassianResources` (resolved cloudId silently), `getVisibleJiraProjects` (saw
> WEGO), and `searchJiraIssuesUsingJql` (returned the real cards WEGO-1887/1886/1885/1881/1884)
> — **headless, zero human intervention.** When a connector is attached to a routine, its OAuth
> **refresh** token is stored **server-side by claude.ai** and exchanged for an access token at
> call time. #46228 is about a *local* headless connection going cold; it does not apply to a
> cloud routine with a server-side connector grant.

So the fleet's auth story is simply: **attach the OAuth connector to each routine.** No static
token, no `.mcp.json`, no org-admin gate. The forks below are now historical context.

### The forks (resolved)

| Fork | Options considered | Resolution |
|---|---|---|
| **Cloud auth mechanism** | (A) static API-token server in `.mcp.json`/env; (B) `/loop` in a warm interactive session. | **Neither needed** — the OAuth *connector* works headless in cloud (proven). B still doesn't scale; A is now reserved for the *local* headless case only. |
| **If a token server were needed, which one** | official Rovo HTTP (needs org-admin to enable token auth; was never connected here) vs community `mcp-atlassian` (uvx, personal token, no admin gate, live-verified locally). | `mcp-atlassian` — but only relevant for a **local** headless launcher, since cloud routines use the connector. |

The journey: the first scaffold chased Rovo HTTP → re-eval flipped it to `mcp-atlassian` →
the cloud test then showed **no token server is needed in cloud at all**. The static-token
work survives as the local-headless option (`mcp__mcp-atlassian__*`), not the cloud path.

## Path A — the foundation (this slice)

### 1. Cloud auth = attach the OAuth connector — ✅ resolved & verified

For the **cloud `/schedule` fleet**, the auth foundation is simply: **attach the `claude.ai
Atlassian` OAuth connector to each routine** (in the routine's `mcp_connections`, under the
connector name `Atlassian`). The connector's tools then appear under the prefix
**`mcp__Atlassian__*`** with the familiar camelCase names (`searchJiraIssuesUsingJql`,
`transitionJiraIssue`, …), and they **work headless** — the connector's refresh token lives
server-side at claude.ai and is exchanged at call time. **No static token, no `.mcp.json`, no
org-admin gate, no `cloudId` plumbing** (the agent resolves it via
`getAccessibleAtlassianResources` if a call ever needs it).

> **Verified 2026-06-30** with a throwaway one-shot routine — it read WEGO
> (WEGO-1887/1886/1885/1881/1884) through `mcp__Atlassian__*` with zero human intervention.
> Keep routines using the standard connector name `Atlassian` so the prefix stays
> `mcp__Atlassian__`.

**Local-headless option (not the cloud path).** If you ever run an *unattended* `claude` on
your **own machine** (a cron/launchd job, no claude.ai connector wired), the OAuth session is
cold and you instead register the community **`mcp-atlassian`** server (sooperset, `uvx`,
static API token in `env`: `JIRA_URL`/`JIRA_USERNAME`/`JIRA_API_TOKEN`). Template:
**`board-flow/atlassian-mcp.example.json`** → host project's `.mcp.json`, token via
`${JIRA_API_TOKEN}` (never inline). It exposes **snake_case** tools (`jira_search`, …), with
its site fixed by `JIRA_URL` (no `cloudId`) which must match `defaults.site`. This is the only
place a token + token server is needed.

> ⚠ **Secret hygiene.** The local `mcp-atlassian` install had its API token written **inline
> in `~/.claude.json`**. Migrated 2026-06-30 to `${JIRA_API_TOKEN}` (the literal token now
> lives in `~/.zsecrets`, chmod 600, sourced from `~/.zprofile`). Rotate it if it was ever
> synced/backed up.

### 2. Bind `atlassian-expert` — ✅ done (triple-bind, two vocabularies)

`board-flow/agents/atlassian-expert.md` is **triple-bound** in its `tools:` frontmatter:
`mcp__claude_ai_Atlassian__*` (local interactive, camelCase) + `mcp__Atlassian__*` (cloud
routine, camelCase — **the proven headless path**) + `mcp__mcp-atlassian__*` (local-headless,
snake_case). The *Tool binding* section maps the three prefixes to two vocabularies: the two
OAuth prefixes share the canonical camelCase names verbatim, and only the snake_case token
server goes through the **translation table** (`getJiraIssue` ↔ `jira_get_issue`, etc.). The
agent uses whichever prefix is connected in its run context, preferring an OAuth/camelCase one
when more than one is present (no translation needed).

### 3. Read-board-or-hard-fail preflight — ✅ done

> **The single most important safety rule.** The failure mode is *silent success*.

Every routine's **first act** must prove it can READ the board, and **hard-fail loudly** if it
can't — never proceed as if the board were simply empty. A real empty column and a broken auth
connection must produce **different, unmistakable** outcomes. Implemented as the **Board-read
preflight** in `atlassian-expert.md`: the first Jira op probes `getVisibleJiraProjects`
(OAuth) / `jira_get_all_projects` (token server) and confirms `project_key` is in the list; on
failure it replies `BLOCKED: … AUTH/connection failure, NOT an empty board` instead of
returning zero cards.

### What remains for the owner to finish Path A

Cloud auth is done — the rest is wiring the first real routine:

1. **Build the execution routine** (To-Do column): a `/schedule` cloud-cron job that attaches
   the `Atlassian` connector and runs `/board-flow:drain`, under `autonomous-mode` so it skips
   the interactive confirmation gate (see Open threads). Stagger it after triage.
2. Confirm the **preflight fails loudly** in-routine when the connector is detached or the
   project isn't visible (the silent-success guard), so a broken fleet member aborts instead
   of reporting "0 cards."
3. Land the slice + reinstall.
4. *(Only if a local-headless launcher is ever wanted)* finish the `mcp-atlassian` setup:
   personal id.atlassian.com token (no admin step), `${JIRA_API_TOKEN}` in env, template into
   `.mcp.json`.

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
