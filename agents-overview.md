# Agents — at a glance

A denormalized view of every agent across all topologies in this
marketplace. Source of truth for each agent's prose is its own file
under `<topology>/agents/`. Source of truth for write-glob enforcement
is `hooks/path-lock.py` (multi-team only — solo-pair has no enforcement
hook yet, see indydev-Dan-gaps section below).

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

**Hook:** `hooks/path-lock.py` enforces the *Writes* column on every
`Edit` / `Write` / `MultiEdit` / `NotebookEdit` call. Drift between this
file and the hook will silently break things at runtime.

---

## solo-pair

Lightweight 2-agent topology for tasks where multi-team's overhead isn't
worth it. Sequential dev → reviewer; no leads.

| Agent | Role | Reports to | Delegates to | Tools | Writes |
|---|---|---|---|---|---|
| (orchestrator — main session) | apex | user | dev → reviewer (sequential) | Task | (none) |
| `pair-dev` | worker | orchestrator | — | Read, Glob, Grep, Edit, Write, MultiEdit, Bash | host project source (no path-lock yet) |
| `pair-reviewer` | worker | orchestrator | — | Read, Glob, Grep, Bash | — (read-only) |

**Models:** workers = `sonnet`. No leads.

**Hook:** none — solo-pair currently has no enforcement. Documented as a
known gap in the indydev-Dan-gaps section below.

---

## Skills (loaded by description-match in CC)

| Skill | One-liner | Audience |
|---|---|---|
| `mental-model` | Read your expertise file at task start; update at task end. | every agent |
| `active-listener` | Read context (delegation prompt, prior worker output, conversation log) before responding. | every agent |
| `zero-micromanagement` | You delegate, you don't execute. The urge to fix it yourself is the signal to delegate. | leads + orchestrator only |
| `conversational-response` | Lead with the answer, bullets for parallels, file:line refs, single next-step close. | every agent that reports verbally |

The `skills/` directory ships with `multi-team` (at the repo root). When
both topologies are installed in the same session, all four skills are
available globally via CC's session-wide skill namespace. When solo-pair
is installed *alone*, the skills are missing — one driver of the
sharing-design proposal.

---

## indydev-Dan gaps (audit at last commit)

What's captured ✅ and what's still loose 🟡 / missing ❌:

- ✅ Single-orchestrator pattern (orchestrator = main CC session)
- ✅ Lead/worker model split (`opus` for reasoning, `sonnet` for execution)
- ✅ Three-team taxonomy (planning, engineering, validation)
- ✅ Domain locks via path-lock hook (multi-team)
- ✅ Four mindset skills present and described
- ✅ Per-agent expertise file convention (`.claude/expertise/<name>-mental-model.yaml`)
- ✅ Workflow: plan → build → validate (encoded in `/plan-build-validate`)
- 🟡 Cost/budget guardrails — Pi config had `max_minutes: 30`, `max_dollars: 15.00`. CC has no budget hook; we mention it as prose in the topology snippet only.
- 🟡 Skills auto-loading inside subagents — relies on CC's description-match auto-invocation; behavior in subagent context isn't formally documented.
- ❌ solo-pair has no path-lock enforcement (workers can write anywhere).
- ❌ solo-pair doesn't ship the four mindset skills — only available if the user also installs multi-team.
- ❌ `.claude/expertise/` directory isn't stubbed/gitignored anywhere — first-task UX is rough.
