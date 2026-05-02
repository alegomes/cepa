---
name: till-done
description: Don't stop until the job is fully complete. Use when work feels "almost done" or "good enough" — finish boundary conditions, edge cases, and wrap-up steps before reporting back. Apply at the moment you're tempted to hand back partial work.
---

# Skill: till-done

The most common failure mode in agent work isn't getting things wrong —
it's declaring victory before the work is actually done. This skill is
the enforcement against that.

## When to apply

- **Before reporting back** to your lead or the orchestrator, ask: is
  every line of the original task actually done? Tests passing? Edge
  cases handled? Files saved with the new content?
- **When you hit a wall**, don't bounce back asking "should I continue?"
  Try the obvious next thing, *then* report, with a one-line note
  about what you tried.
- **When something is "almost done"**, "almost" is the signal to keep
  going. Almost-done tasks come back the next session with worse
  context and have to be re-loaded from scratch.

## What this is NOT

- Not "never ask clarifying questions." If the task is genuinely
  unresolvable from the context you have, ask — but finish what you
  can without that detail first, and flag the dependency.
- Not "ignore the budget." If the orchestrator or lead has signaled
  the session is over budget, stop. Till-done means push *through*
  reasonable friction, not through hard limits.

## Failure modes this prevents

- Reporting "I started X" when X isn't started, just planned.
- "Mostly works" tests that don't actually run.
- Saving incomplete edits because you got distracted.
- Returning `READY-WITH-CAVEATS` when the caveat is actually a
  `BLOCKED` you didn't want to say.
- Closing a session with "next time we should..." instead of doing it now.
