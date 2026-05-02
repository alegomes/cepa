# Agents — at a glance

A denormalized view of every agent across all topologies in this
marketplace. Source of truth for each agent's prose is its own file
under `<topology>/agents/`. Source of truth for write-glob enforcement
is `multi-team/hooks/path-lock.py` (multi-team only — solo-pair has no enforcement
hook, by design).

---

## multi-team

Three teams, each with one Opus lead and two Sonnet workers, plus the
orchestrator (the main session itself). Canonical workflow: plan → build → validate.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| (orchestrator — main session) | apex | user | three leads in parallel | Task | (none — orchestrator runs in the host CC session) |
| `planning-lead` | lead | orchestrator | `product-manager`, `ux-researcher` | Read, Glob, Grep, Task, Write | `specs/**`, own expertise |
| `engineering-lead` | lead | orchestrator | `frontend-dev`, `backend-dev` | Read, Glob, Grep, Task, Bash (RO) | own expertise only |
| `validation-lead` | lead | orchestrator | `qa-engineer`, `security-reviewer` | Read, Glob, Grep, Task, Bash (RO) | own expertise only |
| `product-manager` | worker | `planning-lead` | — | Read, Glob, Grep, Write | `specs/**`, own expertise |
| `ux-researcher` | worker | `planning-lead` | — | Read, Glob, Grep, Write | `specs/**`, own expertise |
| `frontend-dev` | worker | `engineering-lead` | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | `apps/*/web/**`, `apps/*/frontend/**`, own expertise |
| `backend-dev` | worker | `engineering-lead` | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | `apps/*/api/**`, `apps/*/backend/**`, `apps/*/migrations/**`, `apps/classifier/**`, own expertise |
| `qa-engineer` | worker | `validation-lead` | — | Read, Glob, Grep, Edit, Write, Bash | `tests/**`, `apps/*/tests/**`, `apps/*/__tests__/**`, own expertise |
| `security-reviewer` | worker | `validation-lead` | — | Read, Glob, Grep, Write | `specs/security-reviews/**`, own expertise |

**Models:** orchestrator + leads = `opus`; workers = `sonnet`. Splits
cost-and-quality the way indydev Dan's source intends (better reasoning
for delegation/synthesis at the top, faster instruction-following at the
bottom).

**Hook:** `multi-team/hooks/path-lock.py` enforces the *Writes* column on every
`Edit` / `Write` / `MultiEdit` / `NotebookEdit` call. Drift between this
file and the hook will silently break things at runtime.

---

## solo-pair

Lightweight 2-agent topology for tasks where multi-team's overhead isn't
worth it. Sequential dev → reviewer; no leads.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| (orchestrator — main session) | apex | user | dev → reviewer (sequential) | Task | (none) |
| `pair-dev` | worker | orchestrator | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | host project source (no path-lock) |
| `pair-reviewer` | worker | orchestrator | — | Read, Glob, Grep, Bash | — (read-only via tool allowlist) |

**Models:** workers = `sonnet`. No leads.

**Hook:** none. solo-pair relies on `pair-reviewer`'s tool allowlist
(no Edit/Write) for read-only enforcement; `pair-dev` is unrestricted by
design — the topology is for small tasks where domain locks don't earn
their complexity.

---

## Skills (loaded by description-match in CC)

| Skill | One-liner | Audience |
|---|---|---|
| `mental-model` | Read your expertise file at task start; update at task end. | every agent |
| `active-listener` | Read context (delegation prompt, prior worker output, conversation log) before responding. | every agent |
| `zero-micromanagement` | You delegate, you don't execute. The urge to fix it yourself is the signal to delegate. | leads + orchestrator only |
| `conversational-response` | Lead with the answer, bullets for parallels, file:line refs, single next-step close. | every agent that reports verbally |
| `till-done` | Don't stop until the job is fully complete. "Almost done" is the signal to keep going. | every agent |

The five skills ship in the **`common@alegomes` plugin** (`common/skills/`).
Both topologies require `common`; install it once per project and the
skills are available to every subagent via CC's session-wide skill
namespace.

---

## indydev Dan idea audit (against the canonical list)

Status legend: ✅ captured · 🟡 partial / convention only · 🔴 CC limitation

### Mindset and architecture

| Idea | Status | Where / how |
|---|---|---|
| Team of agents | ✅ | 9-agent multi-team + 2-agent solo-pair |
| 3 tiers (orchestrator / leaders / workers) | ✅ | topology snippets, agent files |
| Thinkers (orchestrator, leads) vs doers (workers) | ✅ | leads have no `Edit`/`Write` tools; workers do |
| Thinkers don't write code; they understand, refine, organize, delegate, aggregate | ✅ | `zero-micromanagement` skill + lead front-matter tool list |
| Specific model per agent | ✅ | front-matter `model:` (`opus` for thinkers, `sonnet` for doers) |
| Only worker agents write code | ✅ | path-lock hook + leads' tool allowlists exclude `Edit`/`Write`/`MultiEdit` |
| Highly specialized agents | ✅ | 9 distinct roles, each with a tight write-glob domain |
| Orchestrator must do prompt engineering | ✅ | "You are the team's prompt engineer" section in both topology snippets |
| Till-done — work until job is fully complete | ✅ | `common/skills/till-done/SKILL.md` + topology rule + command instruction |
| Building a system that will build systems | ✅ | framing in README + "Frame" section in both topology snippets |
| Agents must learn and improve themselves | ✅ | `mental-model` skill + per-agent `expertise/<name>-mental-model.yaml` |
| Mental model evolves over time | ✅ | `mental-model` skill describes read-at-start / update-at-end |

### Topology config (Pi has machine-readable YAML; we have CC-shaped conventions)

| Idea | Status | Where / how |
|---|---|---|
| Topology / multi-team-config concept | 🟡 | We have `*-topology.md` snippets (CC orchestrator instructions). Pi has a YAML config the harness reads; CC has no equivalent. The snippet *is* the topology in CC. |
| Orchestrator name + path + color | 🟡 | Orchestrator = main CC session (no separate file/path). Color N/A for main session. |
| Agent paths | ✅ | `agents/` (multi-team) and `solo-pair/agents/` |
| Session paths | 🔴 | CC manages session storage internally; not exposed |
| Shared context (files all agents should know) | ✅ | "Shared context" section in both topology snippets |
| Teams[] declaration | 🟡 | Implicit in agent set + this matrix |

### Per-team

| Idea | Status | Where / how |
|---|---|---|
| `consult-when` (when to activate the team) | 🟡 | In each lead's front-matter `description:` |
| Lead: name + file + color | ✅ | front-matter `name:`, file path is the agent file, `color:` set on every agent |
| Members list | ✅ | encoded in topology snippet + each lead's `Delegates to` table row |

### Per-agent header (Pi YAML blocks vs CC front matter + tabular header)

| Idea | Status | Where / how |
|---|---|---|
| Agent name | ✅ | front-matter `name:` |
| Color | ✅ | front-matter `color:` set on all 11 agents |
| When to use | ✅ | front-matter `description:` |
| Which model | ✅ | front-matter `model:` |
| Expertise (path / use-when / updatable / max-lines) | 🟡 | Stub files ship in `common/expertise/<agent>-mental-model.yaml` (centralized so accumulated knowledge follows the agent across topologies and projects). The path-lock hook allows each agent to write its own expertise file regardless of disk location via a structural filename check. Pi's full schema (`use-when`, `updatable`, `max-lines`) isn't mirrored — CC has no harness layer to act on those fields. |
| Skills list with `use-when` per skill | 🟡 | tabular header lists skills by name; CC auto-loads them by description match (no per-agent `use-when` field) |
| Tools list | ✅ | front-matter `tools:` |
| Domain (path × read/upsert/delete) | 🟡 | path-lock hook enforces *writes* (Edit/Write/MultiEdit) per glob; doesn't distinguish create vs upsert vs delete |

### Per-agent body

| Idea | Status | Where / how |
|---|---|---|
| Purpose section | ✅ | `## Purpose` paragraph in every agent body, after the tabular header |
| Variables (env vars injected at startup) | 🔴 | CC only injects `${CLAUDE_PLUGIN_ROOT}` for hooks — no per-subagent env-var injection. `{{SESSION_DIR}}` and `{{CONVERSATION_LOG}}` from Pi don't translate. |
| Instructions section | ✅ | Body of each agent (currently labeled `## Rules` / `## Approach` / `## Workflow`) |

### Commands (slash commands ≈ Pi pre-saved prompts)

| Idea | Status | Where / how |
|---|---|---|
| Description + argument-hint | ✅ | front-matter |
| Purpose | ✅ | `## Purpose` section in `/plan-build-validate` |
| Variables | ✅ | `## Variables` section in `/plan-build-validate` (`$ARGUMENTS`) |
| Instructions | ✅ | `## Instructions` section in `/plan-build-validate` |
| Workflow (the most important part — talk-to-orchestrator) | ✅ | `## Workflow` heading in `/plan-build-validate` |
| Report (back to the user) | ✅ | `## Report` section in `/plan-build-validate` |

### Sharing across topologies

| Idea | Status | Where / how |
|---|---|---|
| Shared mindset skills available across topologies | ✅ | `common@alegomes` plugin ships the five skills; required by both `multi-team` and `solo-pair` |

---

## Outstanding work

- 🟡 If you want to capture the team-topology config more strictly,
  add a non-driving `topology.yaml` per topology as documentation
  (CC won't read it; risk of drift). Recommend: skip until needed.
- 🟡 Consider extending `path-lock.py` to support read/upsert/delete
  granularity. Modest scope; only worth it if a real workflow demands
  the distinction.
- 🟡 Versioned changelog (separate `CHANGELOG.md`) — currently the git
  log fills this role. Worth adding when there are external users.
- 🔴 Session env vars (`{{SESSION_DIR}}`, `{{CONVERSATION_LOG}}`) — not
  implementable in CC without harness changes.
