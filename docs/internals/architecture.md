# Architecture

## The three-tier model

Every topology except `solo-pair` follows the same shape:

```
        ┌──────────────────────────────┐
        │  orchestrator (main session) │   delegate-only, no Edit/Write
        └──────────────┬───────────────┘
                       │ Task tool
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
  planning-lead   engineering-lead   validation-lead    Opus, delegate-only
       │               │                │
       ▼               ▼                ▼
   PM/UX/...     dev workers       qa/security/...    Sonnet, write code
```

- **Orchestrator** — the CC session you're typing into. Behavior set by
  the topology snippet imported via `CLAUDE.md`. Delegates via `Task`,
  doesn't edit code itself.
- **Leads** — Opus subagents with `Read`, `Glob`, `Grep`, `Task`,
  `Write` (no `Edit` / `MultiEdit`). They write specs and TASK.md but
  cannot edit source code. The lack of edit tools is the enforcement,
  not the prompt.
- **Workers** — Sonnet subagents with edit tools but path-locked write
  globs. The path-lock PreToolUse hook (`path-lock.py`) blocks writes
  outside each worker's allowlist.

`solo-pair` skips the lead tier entirely. `pair-dev` writes;
`pair-reviewer` is read-only via tool allowlist (no path-lock).

## What's enforced vs. what's convention

| Guarantee | How | Bypassable? |
|---|---|---|
| Leads can't write code | tool allowlist (no `Edit`/`Write`/`MultiEdit` in `tools:` frontmatter) | No — CC enforces tool allowlists |
| Workers stay in their domain | `path-lock.py` PreToolUse hook, exit 2 | No (multi-team, hex-backend, discovery, book); solo-pair has no hook |
| Orchestrator delegates instead of coding | prompt-only (`zero-micromanagement` skill + topology snippet) | **Yes** — strong tendency, not a hard block |
| Plan → build → validate ordering | prompt-only (in command + topology) | Yes — orchestrator can reorder |
| jira-flow only mutates Jira via MCP | tool allowlist (`atlassian-expert` is the only agent with Atlassian MCP tools) | No |
| Build state honesty | `gate-advance` PreToolUse hook on Bash commit/push/PR/deploy | No (hook returns exit 2 on STALE/FAILURE) |
| Verify before claiming runtime state | `green-or-revert` skill + `.claude/last-build.json` | Soft — model honors the skill, but file says the truth |
| Decision logging in autonomous mode | `autonomous-mode` skill + `### Decision:` format | Soft — debrief dual-scan catches drift retroactively |
| Jira write read-back verification | agent-spec rule in `atlassian-expert` | Soft (agent-level), but well-tested rule pattern |
| Review-style transition requires Implementation Summary | agent-spec rule in `atlassian-expert` | Soft, refuses with BLOCKED at delegation |

Soft enforcement (rules in prompts/skills) keeps the agents honest;
hard enforcement (tool allowlists + hooks) catches the cases where the
agent would otherwise drift. Where possible, soft + hard work in
combination (e.g., `qa-engineer` PASS requires BUILD SUCCESS evidence
in the reply, AND the `gate-advance` hook independently blocks commits
when `last-build.json` is STALE).

## Plugin anatomy

A plugin in this marketplace follows this directory shape:

```
<plugin-name>/
├── .claude-plugin/
│   └── plugin.json                # name, version, description, hooks declaration
├── agents/                        # subagent system prompts (auto-discovered by CC)
│   └── <agent-name>.md            # YAML frontmatter + body
├── commands/                      # slash commands (auto-discovered)
│   └── <command-name>.md          # YAML frontmatter (description, argument-hint) + body
├── skills/                        # skills (REQUIRED explicit declaration in plugin.json)
│   └── <skill-name>/
│       └── SKILL.md               # YAML frontmatter (name, description) + body
├── hooks/                         # PreToolUse / PostToolUse / etc. (declared in plugin.json)
│   └── *.py                       # executable Python scripts
└── <plugin-name>-topology.md      # optional: the @-import target for CLAUDE.md
```

Notable patterns:

- **Auto-discovery for agents and commands.** Listing `"agents": "..."`
  or `"commands": "..."` in `plugin.json` causes validation failure.
  Just put the files in `agents/` and `commands/`.
- **Explicit declaration for skills.** `"skills": "./skills/"` MUST be
  in `plugin.json`, or the skills won't load. (Asymmetric with agents
  and commands; CC quirk, not a design choice.)
- **Hooks must be registered.** `plugin.json` declares hook events,
  matchers, and the executable command. CC has no convention for
  auto-discovery.

## Per-plugin layout in this marketplace

```
claude-multi-team-plugin/
├── .claude-plugin/marketplace.json    # 7-plugin marketplace registry
├── bin/install.sh                     # one-command installer + per-project wiring
├── common/                            # cross-topology layer
│   ├── .claude-plugin/plugin.json
│   ├── commands/                      # autonomous-start, autonomous-resume, debrief, recap
│   ├── expertise/                     # per-agent mental-model.yaml stubs (centralized via host symlink)
│   ├── hooks/                         # session-log, autonomous-checkpoint, mark-build-stale, capture-build-result, gate-advance
│   └── skills/                        # 10 skills (8 mindset + autonomous-mode + green-or-revert)
├── multi-team/                        # 9-agent generic topology
├── solo-pair/                         # 2-agent lightweight topology
├── hex-backend/                       # 13-agent hexagonal-architecture topology
├── discovery/                         # 6-agent product-discovery topology
├── jira-flow/                         # Jira lifecycle layer (1 agent + 6 commands)
├── book/                              # 10-agent book-writing topology
├── docs/                              # user-facing documentation
│   └── internals/                     # this directory
├── agents-overview.md                 # cross-agent matrix
└── README.md                          # entry point
```

## The marketplace surface, in numbers

| Plugin | Agents | Commands | Hooks | Skills |
|---|---|---|---|---|
| common | 0 | 4 | 5 | 10 |
| multi-team | 9 | 1 | 1 | 0 |
| solo-pair | 2 | 0 | 0 | 0 |
| hex-backend | 13 | 7 | 1 | 0 |
| discovery | 6 | 1 | 1 | 0 |
| jira-flow | 1 | 6 | 0 | 1 |
| book | 10 | 5 | 1 | 2 |

Total: 41 agents, 24 commands, 9 hooks, 13 skills, across 7 plugins.

## Path-lock allowlists at a glance

| Agent / Plugin | Writes |
|---|---|
| (orchestrator, main session) | (none — main session is fail-open via no-colon `agent_type`) |
| `planning-lead` (multi-team) | `specs/**` |
| `planning-lead` (hex-backend) | `spec/**`, `specs/**`, `docs/**` |
| `engineering-lead` (multi-team) | (none — delegate-only) |
| `engineering-lead` (hex-backend) | `docs/tasks/**`, `docs/investigations/**`, `pom.xml`, `**/pom.xml` |
| `validation-lead` (any) | (none — delegate-only) |
| `domain-dev` | `domain/src/main/**`, `application/src/main/**` |
| `api-dev` | `api-rest/src/main/**` |
| `adapter-dev` | `infrastructure/src/main/**`, `bootstrap/src/main/**` |
| `qa-engineer` (hex-backend) | `*/src/test/**` |
| `qa-engineer` (multi-team) | `tests/**`, `apps/*/tests/**`, `apps/*/__tests__/**` |
| `refactor-advisor` | `docs/housekeeping/**` |
| `security-reviewer` (any) | `docs/security-reviews/**` (hex) or `specs/security-reviews/**` (multi-team) |
| `code-reviewer` | (none — advisory verdict only) |
| `epic-author`, `product-manager`, `integration-analyst` (hex-backend) | `spec/**`, `specs/**`, `docs/**` |
| `ux-researcher`, `product-manager` (multi-team) | `specs/**` |
| `frontend-dev` (multi-team) | `apps/*/web/**`, `apps/*/frontend/**` |
| `backend-dev` (multi-team) | `apps/*/api/**`, `apps/*/backend/**`, `apps/*/migrations/**`, `apps/classifier/**` |
| `atlassian-expert` (jira-flow) | (none — only Jira state via MCP) |

Every agent also gets a structural pass to write its own
`<agent>-mental-model.yaml` regardless of disk location (see
[`expertise.md`](expertise.md)).

## Where state lives

| State | Path | Owner | Lifecycle |
|---|---|---|---|
| Active topology | `.claude/topology` | `bin/install.sh` (write) / commands (read) | Per project; set at install, persists |
| Per-agent expertise | `common/expertise/<agent>-mental-model.yaml` (symlinked to host's `.claude/expertise/`) | `mental-model` skill (write), `debrief` (write) | Cross-project; grows over time, pruned at 20 entries (except `principle`-tagged) |
| Topology snippet | `.claude/<topology>-topology.md` | `bin/install.sh` (copy) | Per project; copied snapshot, edits don't propagate back |
| Jira config | `jira-flow.yaml` (project root) | `bin/install.sh` seed / `/jira-flow:configure` interactive / manual edits | Per project; team-edited |
| Session intent log | `.claude/session-log.md` | `session-log` hook | Per project; append-only, manually rotate |
| Autonomous run state | `docs/autonomous/<run-id>/state.yaml` | `/common:autonomous-start` (create) / `autonomous-checkpoint` hook (append) | Per run; survives session restart |
| Build state | `.claude/last-build.json` | `mark-build-stale` + `capture-build-result` hooks (write); `gate-advance` (read) | Per session; rewritten on edits + verify runs |
| Plan-build-validate artifacts | `docs/tasks/<story>/**` (TASK.md, RESULT.md, MERGE.md) | `engineering-lead`, dev workers (write) | Per Story; lives with the code |
| E2E spec | `specs/e2e-assertions.md` | `integration-analyst` (write); `qa-engineer` (read) | Per project; team-edited |

## When you can stop reading

If you just want to *use* the agents, none of this matters — head back
to [`../`](../). If you want to know why a hook does what it does, why
a write got blocked, or how to add something new, the other internals
pages cover the specifics.
