---
description: Records, at any point in the session, feedback about Cepa itself — the command that asked too much, the gate that blocked what it shouldn't, the unreadable report, the agent that did what nobody asked. The record is GLOBAL (~/.claude/cepa-feedback/), because the annoyance happens in the client's repo and the target is the harness; the session's repo, branch and mode are filled in automatically. With no argument, lists what is open. With --triar, and only inside the Cepa repo, turns the open ones into BACKLOG.md items and marks each with its destination. Fixes nothing and does not interrupt the turn's work.
argument-hint: [<feedback text>] | [--alvo X] | [--listar [--todos]] | [--triar]
interaction: routine
---

# /common:feedback

## Purpose

Give the annoyance a destination the moment it shows up.

Feedback about the harness is born in the middle of another task, in a repo that
is almost never Cepa's. The two ways out that existed were to drop the task and
open another repository's `BACKLOG.md`, or to carry on and forget — and carrying
on and forgetting always wins. The result was measured in anecdote: "the harness
asks too much" is true and not actionable, because the episode that would prove
it was never kept.

This command keeps the episode: the owner's text verbatim, plus the context that
makes it reconstructible months later (repo, branch, session mode, target).

## Variables

- `$ARGUMENTS` — one of four forms:
  - **text** → records the feedback (default form).
  - **empty** or `--listar` → lists the open feedback (`--todos` includes the already triaged ones).
  - `--alvo <x>` → goes with the text; names the responsible command/hook/agent.
  - `--triar` → turns the open ones into `BACKLOG.md` items. Only makes sense in the Cepa repo.

## Where the record lives

`~/.claude/cepa-feedback/feedback-AAAA-MM.jsonl` — global and append-only
(`CEPA_FEEDBACK_DIR` overrides it). Global and not per repo because the target is
Cepa and the annoyance happens in the client's repo: one file per project would
scatter the same complaint across five places nobody rereads. Append-only because
triage is another line citing the `id`, never a rewrite of what the owner said.

The writer is `cepa-feedback` (the plugin's bin), never your text editor: it is
what refuses an empty or one-word record, generates the `id`, captures
repo/branch/mode and replays the ledger's `aberto`/`triado` state.

## Workflow

### 1. Record (default form)

When `$ARGUMENTS` carries text:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" add \
  "<owner's text, verbatim>" --alvo <target if any> --origem comando
```

**Verbatim.** Do not summarize, do not rewrite, do not "improve" the owner's
wording. If they wrote four lines of irritation, the four lines go in. A summary
swaps the complaint for your reading of it — and your reading is usually the
problem.

You fill `--alvo` from the turn's context when it is clear (the command that just
ran, the hook that just blocked, the agent that just returned the report). Do not
invent: with no evident target, record without it.

Output to the owner: **one line** with the id and the target. After that, go
back to what they were asking for. The turn belongs to the task, not to the
complaint.

If the bin refuses (text too short, empty), pass the refusal on in one line and
ask for the full sentence — without turning it into an interrogation.

### 2. List

With no argument, or with `--listar`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" list --sem-cor
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" list --status todos --sem-cor   # with --todos
```

Pass the list on as it came, grouped by target when there are more than five
items. Do not classify, do not prioritize, do not propose a fix: here you are a
shop window.

### 3. Triage (`--triar`) — only in the Cepa repo

Triage is what keeps the ledger from becoming a dead archive: each open feedback
leaves it with a named destination.

1. **Check that this is the Cepa repo** — there is a `BACKLOG.md` at the root and
   `common/.claude-plugin/plugin.json`. If it is not, stop and say in one line
   that triage runs in the harness repo (the record is global; turning it into a
   card is not).
2. Read the open ones with `list --status aberto --json`.
3. For each one, choose among three destinations — and **you decide**, with the
   recommendation recorded, without asking item by item (`default-yes`):
   - **New item in `BACKLOG.md`** — the annoyance is not described in any
     existing section. Write the section in the file's format (title, `**Status:**
     pendente · **Lar provável:** <plugin> · **Origem:** feedback `<id>`,
     `<date>`), with the owner's text quoted and the record's context.
   - **Attached to an existing item** — there is already a section about that
     annoyance. Add the episode there, with the id, instead of opening a rival
     section.
   - **Already solved** — the behavior complained about no longer exists. The
     destination is the commit or version that solved it, and you only mark the
     triage.
4. Mark each one:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" triar <id> \
     --destino "BACKLOG.md § <title>" --nota "<one line, if it helps>"
   ```
   The bin refuses an empty destination, a nonexistent id and re-triage — a
   second triage would silently erase the first decision.
5. Report in the `plain-report` format (in pt-BR): how many came in, how many
   became a new item, how many were attached, how many were already solved.

## Limits

- **Does not fix.** Not even the trivial annoyance, not even in the Cepa repo.
  Recording and fixing in the same turn is exactly the detour the work mode
  exists to block; the fix comes in through the queue, like any item.
- **Does not judge.** "The gate was right" may be true and is not the record's
  business. The ledger keeps the episode; triage checks the facts.
- **Is not a project card.** A bug in the client's code, a third-party API, a
  broken build → `/board-flow:capture` or `.claude/desvios.md`. The test is one
  question: would reinstalling Cepa on another machine bring the annoyance along?

## Relation to the rest

- The `common:feedback-capture` skill makes the same record **without you typing
  any command** — complaining in prose is enough. The `feedback-nudge` hook
  (UserPromptSubmit) is what makes sure the moment to record is noticed, once per
  session.
- `/common:metrics` measures the harness from the mechanical side (blocks,
  verdicts, friction at the session's ends). This command is the side only the
  owner sees: what bothered them, in their own words.
