---
name: suggest-capture
description: Use when the user makes a new work request — a feature, bug fix, refactor, investigation, or anything that would normally become a Jira card — and no existing Jira key has been mentioned in the conversation. Suggest running /board-flow:capture to register the work before starting. Do NOT trigger for clarifying questions, opinion requests, code reads, or follow-ups on already-tracked work.
---

# Suggest capture

When board-flow is active, Jira should be the source of truth for tracked work. But auto-creating a card on every user message is noisy and brittle (most messages aren't work items). This skill threads the needle: when the user clearly asks for new work and there's no card yet, **suggest** capturing — don't do it silently.

## When to fire

The user message is a new work request AND no Jira key (e.g., `WEGO-1234`) has been mentioned earlier in this session.

Examples that should fire:
- "Add a contact-alternative validator to the subscription flow."
- "Fix the bug where the resolver returns null for empty input."
- "Refactor the auth middleware to use the new session store."
- "Investigate why p99 latency spiked yesterday."

Examples that should **not** fire:
- "What do you think about X?" (opinion / discussion)
- "Read foo.py and explain the loop." (read-only request)
- "WEGO-1559 is failing — fix it." (already tracked; existing key)
- "Can you also rename `bar` to `baz` while you're in there?" (follow-up on in-flight work)
- "ls" / "git status" / typo corrections (not a work item)

## What to do when it fires

Before starting work, give the user a one-line suggestion and wait:

> This looks like new work. Want me to register it as a Jira card first? Run `/board-flow:capture <description>` (or paste a Jira key if it already exists). Otherwise I'll proceed without tracking.

Then:
- If the user runs `/board-flow:capture` or supplies a key → reference the key in the work going forward.
- If the user says "skip" / "just do it" / proceeds without answering → drop it; do **not** ask again this session for the same request.
- If the request is the cross-repo half of work already carded in another repo (the user names a sibling key, or says "same as X, but on the frontend/extension"), note in the suggestion that the captured card should be linked to its sibling — see "Cascata multi-repo" in `agents/atlassian-expert.md` (`defaults.sibling_link_type`).

Suggest at most **once per request**. Don't nag. If the same kind of work comes up later, suggest again — but never twice for the same item.

## Why this exists

Auto-classifying every prompt as work-or-not requires an LLM call per turn (latency + cost) and still misclassifies. A one-shot suggestion at the moment of intent is cheaper, transparent, and gives the user agency. They opt in; they don't get spammed.
