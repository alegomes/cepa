---
name: scope-discipline
description: Don't expand the work beyond what was asked. Use when tempted to fix or refactor something tangential to the assigned task. While-I-was-in-there findings are follow-ups, not silent inclusions.
---

# Skill: scope-discipline

The "while I was in there I noticed X" instinct feels helpful. It's not. Silently expanding scope means:

- Reviewers can't see the full diff against the original request.
- Unrelated changes ride along on the wrong commit.
- Time and budget overruns are invisible to the user.
- The next agent in the chain inherits work it didn't sign up for.

## When to apply

- Any time you're tempted to fix something tangential to the assigned task.
- Any time you find a code smell, dead code, typo, or test gap outside your task's blast radius.
- Any time a "small refactor" suggests itself while implementing a feature.

## What to do instead

- **Name the finding** in your reply, with a one-line description and a severity hint (LOW / MEDIUM / HIGH).
- **Don't fix it.** Trust the lead to route a follow-up task if it matters.
- If the finding is genuinely blocking your assigned task, say so explicitly: "I can't proceed without addressing X" — then wait for the lead to decide.

## Approval scope

Scope discipline also applies to what a confirmation *covers*. An approval releases work **until the next checkpoint, not through the entire lifecycle**: "go ahead" after a plan means implement and validate — it does not mean merge, push, transition the card, or close the story. When you reach the next decision the user would want to see (a share-boundary operation, a verdict, a scope change), stop again. Treating one "sim" as blanket consent is scope creep on the approval itself.

## What this is NOT

- Not "ignore obvious bugs that block the task." Genuine blockers always come back to the lead.
- Not "never improve anything." Improvements are first-class work — they go through the same plan/build/validate cycle, not as silent passengers.

## Failure modes this prevents

- Drive-by refactors landing in unrelated PRs.
- "Quick" formatting changes contaminating diffs.
- Silent dependency upgrades, file moves, or rename cascades.
- "I made the test better while I was at it" — even improvements break review hygiene when uninvited.
