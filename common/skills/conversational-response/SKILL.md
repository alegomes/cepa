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

## Translate jargon at the human boundary

"Match the recipient's register" has a sharp exception: the **last hop to the
user**. Internal protocol vocabulary — verdict codes (`PROVEN` / `NEEDS-HUMAN`),
level numbers (`L2` / `L3`), `altitude`, `mutation`, `assumed` / `survived`,
`base_commit`, `red-at-base` — is precise and welcome *between agents and in
artifacts*. To a human reading a status update it is noise.

When the reply crosses to the user, translate — **gloss with an anchor**, don't
erase:

- **Plain-language headline; the code in parentheses.** Not
  "`L3 mutation: PASS — 0 survived`" but "Broke each changed line and the tests
  caught every one *(L3 mutation: 0 survived)*." The parenthetical keeps the
  trace to the docs/artifact; the sentence is what the human actually reads.
- **Each technical level becomes a question + a plain answer.** "Does the
  coverage reach the HTTP endpoint? — Can't tell: the project has no coverage
  tool installed" beats "L2: assumed."
- **Never lead with a code.** A reader who has never seen the protocol must
  still understand what happened and what they're being asked to decide.
- A coded term with no plain-language gloss anywhere in a user-facing reply is a
  defect — the same class of miss as a wall of undescribed diff.

### Interactive prompts are user-facing too

`AskUserQuestion` is the last hop to the user, not an internal channel — the
rule above applies to **every part of the dialog**, not just prose replies:

- **The question text** — frame the actual decision in plain words; the code
  goes in parentheses. Not "WEGO-1841: L4 surfaced an unasserted response on the
  touched endpoint — accept the L3 waiver?" but "WEGO-1841: the tests prove the
  fix works, but one error response isn't checked. Accept anyway? *(L4 finding,
  L3 proven)*."
- **Every option label** — labels are short (a few words), so jargon compresses
  worst exactly here. A label may carry a code only if it *also* reads in plain
  language: `Accept — fix is proven` over `Waiver → Done`, `Send back for one
  more pass` over `Exigir L4`.
- **Every option description** — this is where the gloss lives when the label
  has no room. State what choosing it *means and does* in plain words, code in
  parens. The description must stand on its own for a reader who has never seen
  the protocol.
- Same defect bar: a coded term with no plain-language gloss anywhere in the
  question or its options is a defect.

## Anti-patterns

- Pasting the entire diff back. The diff is in the files.
- "I have completed the task." Just say what got done and where.
- "I hope this helps!" → no, just stop.
- Leading with apologies — say what's true now.
