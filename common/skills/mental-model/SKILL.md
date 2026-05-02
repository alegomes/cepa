---
name: mental-model
description: Read your per-agent expertise file at task start; update it at task end with non-obvious learnings. Use when an agent boots up for any task and again before reporting back to its lead. Keeps domain knowledge alive across sessions where the conversation context resets.
---

# Skill: mental-model

You don't get persistent memory across sessions for free. The expertise
file at `.claude/expertise/<your-name>-mental-model.yaml` is the
only thing that crosses the session boundary. If you don't write to it,
the next-you starts cold and asks questions you've already answered.

## When to apply

- **At task start**: read your expertise file before doing real work.
- **At task end**: append at most a few short lines if there's something
  durable worth remembering.

## What goes in

- **Domain facts** that took non-trivial work to discover (table shapes,
  rate limits, undocumented behavior, the actual on-disk layout).
- **Decisions** and the *why* behind them — you'll forget the why faster
  than the decision itself.
- **Failure modes** specific to this codebase (where the tests lie, what
  the lint rules don't catch, which migrations need manual steps).
- **People-and-places**: who owns what, which docs are stale.

## What does NOT go in

- The current task's TODO list — that's session state.
- Verbatim quotes — paraphrase the durable rule.
- Things that are easy to re-derive from `git log`, `grep`, or the README.
- Apologies or self-corrections — write what is true now.

## Pruning

- If something you wrote previously is now wrong, **edit or delete it**.
  Do not just append a contradicting note.
- Stay under your `max-lines` budget. When you hit it, the oldest
  least-used notes get dropped — write to keep, not to fill.

## File format

YAML. Free-form keys, but a useful skeleton:

```yaml
# .claude/expertise/<your-name>-mental-model.yaml
last_updated: 2026-04-26
codebase_facts:
  - "classifier.py uses joblib for model persistence under apps/classifier/models/"
  - "training_data.py: 60 examples, 20/20/20 across low/mid/high"
decisions:
  - "We picked LR over CNB because LR owns the LOW class better — see DEMO.md"
gotchas:
  - "scikit-learn 1.7 dropped multi_class kwarg from LogisticRegression"
people:
  - "expertise/ is gitignored by default — agents own these"
```
