---
name: active-listener
description: Read the relevant context (delegation prompt, prior worker output, conversation history) before responding. Use when boot up for any task — most "I need clarification" replies are actually unread context. Workers and leads both need this; orchestrators most of all.
---

# Skill: active-listener

This is a multi-agent system. By the time it's your turn, other agents
may have already answered, partially answered, contradicted each other,
or delegated to you specifically. Replying without reading the room
means duplicating work, ignoring constraints another agent already
surfaced, or — worst — confidently contradicting the team.

## When to apply

Before every substantive response. Quick acknowledgements are fine, but
anything that changes files, makes a recommendation, or escalates back
up the chain needs context first.

## What to read, in order

1. **Your own delegation prompt** — what specifically were you asked to do?
2. **Messages addressed to you or your team** — `@you`, `@your-team`, or
   the most recent message from your lead/orchestrator.
3. **Constraints, deadlines, or budgets** anyone has surfaced.
4. **Anything tagged `BLOCKER`, `RISK`, or already-answered** — don't
   repeat work.

## How to apply

- If another agent already answered the question, **do not re-answer**.
  Either agree concisely, or *only* add the dimension they missed.
- If two agents disagree, **name the disagreement** and propose a
  tiebreaker — do not silently pick a side.
- If your delegation prompt contradicts what an earlier agent said, **say
  so explicitly** in your reply rather than executing the contradiction.

## What this is not

This is not a license to read the entire log on every turn. Read what's
relevant to the specific delegation you're handling. The log is
searchable; use targeted reads.

## Anti-pattern: clarification ping-pong

If you're about to ask "can you clarify what you want me to do?" — first
re-read the delegation prompt. 80% of the time the answer is in there.
The other 20% of the time, name the specific ambiguity ("you said X but
referenced Y — which takes priority?") rather than a generic "please
clarify."
