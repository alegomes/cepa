---
name: mental-model
description: Read your per-agent expertise file at task start; update it at task end with non-obvious learnings. Use when an agent boots up for any task and again before reporting back to its lead. Keeps domain knowledge alive across sessions where the conversation context resets.
---

# Skill: mental-model

You don't get persistent memory across sessions for free. The expertise
file at `common/expertise/<your-name>-mental-model.yaml` (which lives
**in the plugin itself**, not in the host project) is the only thing
that crosses the session boundary. If you don't write to it, the
next-you starts cold and asks questions you've already answered.

## This file is cross-project

The plugin gets installed into many host projects. Your expertise file
is **shared across all of them**. That has one important consequence:
write *agent-global* knowledge here, not project-specific facts.

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

YAML. Free-form keys, but a useful skeleton:

```yaml
# common/expertise/<your-name>-mental-model.yaml
last_updated: 2026-05-02
ecosystem_gotchas:
  - "scikit-learn 1.7 dropped multi_class kwarg from LogisticRegression"
  - "starlette 0.27+ requires explicit lifespan handler for asynccontext"
heuristics:
  - "when an ORM query is slow, check N+1 before adding an index"
decisions:
  - "default to one-line replies when the lead asked yes/no"
```
