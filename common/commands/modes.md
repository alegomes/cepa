---
description: Shows the table of work modes — what each mode asks for to enter, what it produces, and what must be true to close it. Answers "what mode am I in again, and what was it for?" without opening the 307-line document. Marks the current session's mode. Read-only, changes no mode.
argument-hint: [mode-name]
interaction: conversational
---

# /common:modes

## Purpose

Every session declares a mode, and the mode is a **state that lasts** until its
exit condition is met — not a label. But the definition of each one lives in
`docs/modos-de-trabalho.md`, 307 lines long, and nobody opens that in the middle
of the work. What happens instead is guessing the purpose of the mode you are in.

This command is the table and nothing more.

**It does not switch modes.** Switching takes a new session (`cepa --mode <x>`),
on purpose: if you could switch midway, the mode would go back to being a label.

## Steps

1. Run, passing the argument through verbatim:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-modes" $ARGUMENTS
   ```

2. Show the output **in full**. It already comes out in Brazilian Portuguese
   (pt-BR) and formatted — do not summarize, do not reorder, do not pick "the
   most relevant". The whole table is the product: whoever asked forgot which
   was which, and a summary brings back the same problem.

3. If the user named a mode (`/common:modes refactor`), the script already
   filters — you do not filter anything on your own.

4. With no argument and a mode declared in this tree, the output ends with
   that mode's numbered menu of common actions (the same text as
   `cepa-modes --menu <mode>`, already filtered by this repo). Show it as it
   came: it answers the question that follows "what was this mode for?",
   which is "so what do I do now?". A mode without actions shows no menu.

## Notes

- The source is `common/hooks/_modes.py`, the same file `session-mode.py` reads
  to inject the exit condition on every turn. One table, two readers;
  `tests/test_modes_single_source.py` fails if the list of valid names in `cepa`
  diverges from it.
- There are 7 modes. The document's 8th, `deploy`, is out of this round by the
  owner's decision — it is the only one that depends on external infra
  (environment, credential, pipeline) and would block the others if it came in
  together.
- To know only which mode you are in, without the table: the statusline shows
  `🎯 <mode>`.
