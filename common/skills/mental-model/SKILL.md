---
name: mental-model
description: Read your per-agent expertise file at task start; update it at task end with non-obvious learnings. Use when an agent boots up for any task and again before reporting back to its lead. Keeps domain knowledge alive across sessions where the conversation context resets.
---

# Skill: mental-model

You don't get persistent memory across sessions for free. Your expertise
file at `.claude/expertise/<your-name>-mental-model.yaml` is the only
thing that crosses the session boundary. If you don't write to it, the
next-you starts cold and asks questions you've already answered.

## This file is centralized across projects

The path looks host-project-relative, but `.claude/expertise/` is a
**symlink** that `bin/install.sh` creates at install time, pointing at a
single shared directory inside the plugin
(`<plugin>/common/expertise/`). Every host project where the plugin is
installed reads and writes the same set of files. Your accumulated
knowledge follows you across topologies *and* across projects.

That has one important consequence: write *agent-global* knowledge here,
not project-specific facts.

- ✅ "scikit-learn 1.7 dropped `multi_class` kwarg from LogisticRegression"
  — applies to backend-dev work in any Python codebase.
- ❌ "this repo's classifier lives at `apps/classifier/`" — only true
  in one project; would pollute the file for every other project.

Project-specific knowledge belongs in the host project's `CLAUDE.md`,
in `specs/`, or in feature-level docs. Not here.

## When to apply

- **At task start**: read your expertise file before doing real work.
- **At task end**: append at most a few short lines if there's something
  durable, agent-global worth remembering.

## What goes in

- **Domain knowledge** that applies to your role anywhere: language /
  framework gotchas, library quirks, security patterns, common bug
  classes, ecosystem versioning issues.
- **Heuristics** you found in one task that would help next time —
  "when X looks like Y, check Z first."
- **Decisions about how you work** — output formats that landed well,
  delegation patterns that didn't.

## What does NOT go in

- **Project-specific facts**: file paths, table shapes, codebase layout,
  team-member names, internal product names, anything that's only true
  in one repo.
- The current task's TODO list — that's session state.
- Verbatim quotes — paraphrase the durable rule.
- Things easy to re-derive from `git log`, `grep`, or a README.
- Apologies or self-corrections — write what is true now.

## Pruning

- If something you wrote previously is now wrong, **edit or delete it**.
  Don't append a contradicting note.
- Stay under your `max-lines` budget. When you hit it, the oldest
  least-used notes get dropped — write to keep, not to fill.

## File format

YAML. Free-form keys, but three sections have schema meaning across the
marketplace and should follow the conventions below.

### Reserved sections

**`feedback:`** — written by `/common:debrief` after autonomous-mode
runs. Each entry is a per-decision verdict from the user (keep /
overrule / refine / skip). Entry shape:

```yaml
feedback:
  - run_id: 2026-05-09-wego-1567
    date: 2026-05-09
    topic: "Rename strategy — big-bang vs deprecation window"
    altitude: strategic | tactical | implementation
    original_choice: <Option X — description>
    user_verdict: keep | overrule | refine | skip
    user_reason: <verbatim from user>
    refined_rationale: <only on refine>
    tag: principle | example
```

Don't hand-write `feedback:` entries — `/common:debrief` owns this
section. `principle`-tagged entries are exempt from the 20-entry
auto-prune cap; everything else evicts oldest-first when at cap.

**`heuristics:`** — user-authored (or worker-authored at task end via
this skill) durable rules of thumb. Distinct from `feedback:` because
heuristics are general patterns, not tied to a specific run-id. Two
acceptable shapes:

```yaml
# Short form — a one-line rule of thumb:
heuristics:
  - "when an ORM query is slow, check N+1 before adding an index"

# Structured form — a recognizable failure pattern with diagnostic + verdict:
heuristics:
  - id: provided-scope-breaks-transitive-runtime-contract
    when: <one-paragraph description of when this pattern shows up>
    why_it_bites: <what goes wrong, and why it's easy to miss>
    verdict_rule: <how to act when you recognize the pattern>
```

The structured form is useful for verdict-shaped roles (validation-lead,
code-reviewer, security-reviewer) where the heuristic carries a
recommendation. Lead/worker roles can mix both forms — short for quick
rules, structured for patterns worth lifting to a checklist.

`/common:debrief` does NOT touch `heuristics:`. Workers / leads /
humans can edit freely.

**`ecosystem_gotchas:`** (optional, free-form list of short strings) — version-specific gotchas worth carrying across tasks:

```yaml
ecosystem_gotchas:
  - "scikit-learn 1.7 dropped multi_class kwarg from LogisticRegression"
  - "starlette 0.27+ requires explicit lifespan handler for asynccontext"
```

### Other keys

Beyond the reserved sections, free-form keys are fine for role-specific
context (`agent:`, `lane:`, `decisions:`, etc.). Keep it terse.

### Full skeleton

```yaml
# .claude/expertise/<your-name>-mental-model.yaml
# (symlink → <plugin>/common/expertise/<your-name>-mental-model.yaml)
last_updated: 2026-05-28

# Role-identifying free-form keys
agent: api-dev
lane: api-rest REST surface

# Version-specific gotchas
ecosystem_gotchas:
  - "Quarkus 3.20+ requires explicit @Path on resource roots"

# Durable rules of thumb (user-authored or worker-promoted)
heuristics:
  - "when a 415 hits a REST controller, check Content-Type before MediaType allowlist"
  - id: provided-scope-breaks-transitive-runtime-contract
    when: <...>
    why_it_bites: <...>
    verdict_rule: <...>

# Per-decision feedback (debrief-owned; don't hand-edit)
feedback:
  - run_id: ...
    ...
```
