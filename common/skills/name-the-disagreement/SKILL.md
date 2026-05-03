---
name: name-the-disagreement
description: When synthesizing reports from multiple sub-agents that disagree, surface the disagreement explicitly. Use whenever integrating two or more agents' outputs. Don't average, pick silently, or paper over conflicts.
---

# Skill: name-the-disagreement

Silently picking a winner when two sub-agents disagree is the most common synthesis failure. The disagreement carries information: it tells the next reader (orchestrator, user, downstream agent) that the situation is contested. Burying it loses that signal.

## When to apply

- Whenever you're integrating outputs from two or more sub-agents as a lead or orchestrator.
- Whenever findings conflict — different verdicts, contradictory recommendations, mismatched assumptions.
- Whenever sub-agents define a term differently or scope a problem differently.

## What to do

In your synthesis reply:

1. **State the disagreement** in one line: *"qa-engineer says PASS, security-reviewer says BLOCK on the same auth flow."*
2. **Quote each side briefly** — what does each agent claim, with what evidence?
3. **Propose a resolution** — your recommendation as the synthesizer. If you can't resolve it from the inputs alone, say what you'd need to decide.
4. **Don't average.** "PASS-WITH-CAVEATS" isn't always the right blend; sometimes one side is right and one is wrong.

## What does NOT count as resolution

- Picking the lead's preferred view because it's the lead's view.
- Picking the more confident-sounding reply.
- Ignoring the conflict and reporting only the verdict you liked.
- "Both have a point" without actually deciding.

## Failure modes this prevents

- Silent overrides where one team's finding gets buried.
- The user discovers two contradictory claims days later in different artifacts.
- Downstream agents receive a confident verdict that has unspoken doubt baked in.
- Repeated re-litigation of the same disagreement across sessions because no one wrote down what was decided and why.

## What this is NOT

- Not "every minor difference is a disagreement." If both agents agree on the verdict but emphasize different details, that's complementary, not conflicting.
- Not "let the user decide every time." Synthesis is your job — propose a resolution. Escalate only when you genuinely lack the inputs.
