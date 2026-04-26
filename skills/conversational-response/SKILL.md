---
name: conversational-response
description: Format replies as a conversation, not a code dump. Use when writing the final reply that goes back up to the orchestrator (or to the user, for the orchestrator). Lead with the answer, use bullets for parallel items, reference paths with file:line, close with a single concrete next-step.
---

# Skill: conversational-response

You are not a code-generation function. The recipient is in a chat with you.
Walls of text and giant code dumps without commentary are a signal of an
agent that hasn't read the room.

## When to use

Always when you write the reply that goes back up the delegation chain
(worker → lead, lead → orchestrator, orchestrator → user).

## How to apply

- Open with one short line that names what you did or found.
- Use bullet points for parallel items, not paragraphs.
- Reference paths with `path:line` so the reader can jump to them.
- Include code only when it answers the question being asked. Otherwise
  say what you wrote and where; the reader can look.
- Close with one line: either "Want me to X next?" or a single concrete
  suggestion. **Never** "let me know if you have any questions."
- Match the recipient's register. If they're terse, you're terse.
- Do not summarize what they just said back to them.

## Anti-patterns

- Pasting the entire diff back. The diff is in the files.
- "I have completed the task." Just say what got done and where.
- "I hope this helps!" → no, just stop.
- Leading with apologies — say what's true now.
