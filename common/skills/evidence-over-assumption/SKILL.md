---
name: evidence-over-assumption
description: When reporting back, distinguish what you verified from what you assumed. Use when describing system behavior, dependencies, or expected outcomes. Be explicit about which claims are tested vs. inferred.
---

# Skill: evidence-over-assumption

Reports that blur "I checked it" and "I think it does that" compound across delegations. The next agent treats both as facts; reviewers can't tell what to re-verify; bugs hide in the "I assumed" layer.

## When to apply

- Any time you describe system behavior — endpoint responses, database state, API contracts, error handling.
- Any time you state a dependency works or doesn't work.
- Any time you say "this should..." — that wording is your tell.

## What to do

Distinguish the two cleanly in your reply:

- ✅ **Verified**: "I ran `curl -X GET /api/foo` and got `404` with body `{...}`."
- ✅ **Assumed**: "I'm assuming `pytest` is the test runner because `pyproject.toml` references it (didn't run it)."
- ❌ **Blurred**: "The endpoint returns 404 on missing keys." (Did you check, or do you think?)

For verified claims: say HOW you verified — "by running X", "by reading file:line", "by tracing through Y."

For assumed claims: prefix with "assuming" or "I think" — and name the basis: "because the framework usually does this," "because the README says so but I didn't test."

## Why this matters

- Reviewers know what to re-check.
- Other agents don't act on phantom facts.
- When a bug surfaces later, "we assumed X" is a faster diagnosis than re-deriving what was actually tested.

## Failure modes this prevents

- Cascading false confidence: agent A asserts X, agent B builds on X, ship is delayed when X turns out to be unverified.
- "It works on my machine" — except it was never actually run.
- Documentation that drifts from reality because no one wrote down what was tested.

## What this is NOT

- Not "verify everything before claiming anything." Some claims are reasonable inference; the skill is about *labeling*, not eliminating, assumptions.
- Not "exhaustive evidence in every reply." A sentence like "I ran the test, it passed" is enough; you don't need a paste of full output.
