---
description: Lists the repo's whole `single-track` queue, grouped by status (in progress, pending, blocked, done, dropped), in the recorded order, with the reason of each block and the open human actions. Answers "how is the queue right now?" without opening plan.yaml. Read-only: does not reserve, execute or reconcile with Jira.
argument-hint: [queue-name] [--status pending|in_progress|blocked|done|dropped]
interaction: conversational
---

# /common:fila

## Purpose

The other queue commands answer other questions. `/common:next` names **one**
next step. `/common:drain-plan` executes. `cepa-plan queue` shows only what the
next batch would run, hides what has already closed and stops at the first
stuck item. None answers "how is the queue right now?", and on 2026-09-28 the
only way out was to open the 72-item `plan.yaml` by hand.

This command is the listing and nothing more.

**Read-only.** It does not reserve an item, does not change a
status, does not call Jira. To reconcile with the board, `/common:next --sync`.

## Steps

1. Run, passing the argument through verbatim:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-plan" status $ARGUMENTS --repo .
   ```

   With no name, the script uses the repo's only queue. With more than one, it
   exits with code 2 and lists the names: show the list and ask for the name,
   do not pick one.

2. Show the output **in full**, inside a code block. It already
   comes out in Brazilian Portuguese (pt-BR), grouped and in the recorded
   order. Do not summarize, do not reorder and do not pick "the most relevant":
   whoever asked wants the queue, and a summary brings back the same hole the
   command exists to fill.

3. Do not add a recommendation or a next step. If the user wants to know what
   to do, the command is `/common:next`.

## Notes

- The queue lives in the main clone (`<root>/.claude/programs/<name>/plan.yaml`),
  even when the session runs in a worktree. `cepa-plan` resolves that on its own.
- The number before each item is its position in the recorded queue, not the
  execution order: a pending item may be waiting for another one further down.
- Done and dropped items come out on one line each, without evidence. To see
  an item's evidence, `--status done` with `--json` brings everything.
