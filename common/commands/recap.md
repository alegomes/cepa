---
description: Render a "you asked / I delivered" recap of the current session. Reads .claude/session-log.md (intent log written by the session-log hook) and the conversation context (delivery — slash commands run, files written, commits made, blockers hit), then surfaces a structured per-request status. Use when you've forgotten what you asked for, or want to confirm everything's accounted for before stopping.
argument-hint: [--since=YYYY-MM-DD]   (optional; defaults to "today" if the session-log has today's entries, otherwise the most recent date in the log)
---

# /common:recap

## Purpose

Long sessions blur the line between what you asked for and what's actually been done. This command renders that explicitly: each user request, paired with what the agents delivered (or didn't), so you can sanity-check progress, catch dropped requests, and decide what to do next.

## Variables

- `$ARGUMENTS` — optional `--since=YYYY-MM-DD` filter to scope the recap to entries from that date onward. Default: today's entries; fall back to the most recent date with entries if today has none.

## Instructions

You are the orchestrator. Read `.claude/session-log.md` (intent), reason over the current conversation context (delivery), and produce a structured recap. **Don't ask the user questions** unless something in the log is so ambiguous you can't reason about it at all.

If the session-log file doesn't exist, reply: "No session log at `.claude/session-log.md`. The session-log hook may not be installed (run `bin/install.sh --clean` from the plugin repo) or this is a fresh project. Recapping from conversation context alone:" and then proceed with conversation-only recap.

## Workflow

### 1. Load the intent log

Read `.claude/session-log.md`. Parse it into a list of `{ timestamp, prompt }` entries (the file uses date headers `## YYYY-MM-DD` and time headers `### HH:MM:SS UTC` followed by the prompt body).

Apply the `--since` filter (default = today, or most recent date with entries).

If the resulting list is empty, reply with that and stop. Don't fabricate.

### 2. Pair each request with delivery evidence

For each prompt, scan conversation context for what happened *after* that prompt and *before* the next one. Categorize the outcome as one of:

- **Done** — work completed; cite specifics (commits made, files written, command verdicts).
- **Partial** — some progress but not complete; cite what's done and what's left.
- **Blocked** — hit a blocker; cite the reason (missing creds, wrong topology, hook collision, etc.).
- **Discussion only** — the prompt was a question or design conversation; no work expected.
- **Skipped** — the prompt didn't get answered or the request was lost in transition.

Be concrete. "Worked on X" is useless; "commit `abc1234` adds `foo.py:42` (function `bar`)" is useful.

### 3. Render the recap

Output a structured table (or list, whichever is more readable for the count). Recommended format:

```markdown
## Recap — <date range>

| Time | Asked | Status | Delivered |
|---|---|---|---|
| 19:45 | "Add a new task to the orchestrator..." | Done | Commit `30e8d84`. Adds Implementation Summary requirement. |
| 19:46 | "Wait. Should I run common:recap..." | Discussion only | (No work expected.) |
| 19:50 | "apply v1" | Done | Commits `abc1234`, `def5678`. Hook + command. |
| 20:05 | "schedule documentation routine" | Partial | Routine `trig_...` created. PR not yet opened (fires at 04:00 UTC). |

### Open items
- <Partial / Blocked items recapped with what's left>

### Suggested next steps
- <one-line concrete recommendations, max 3>
```

If a request mapped to no clear delivery (skipped, or interleaved with other work and never returned to), call it out explicitly under "Open items" — that's the entire point of the recap.

### 4. Don't speculate

If you genuinely can't tell what happened with a request (context too thin, /compact happened, no evidence in log or chat), mark it `Status: unclear` rather than guessing. The user can clarify.

## Constraints

- **Read-only.** Don't edit code, don't make commits, don't transition Jira state. The recap is a view, not an action.
- **Scope to the filtered window.** If `--since=2026-05-01`, don't include entries from before that date even if they're in the log.
- **Scan order.** Work through the prompts chronologically — the recap should read like the session unfolded, not be re-sorted by status.
- **Deduplication.** If two consecutive prompts are clearly clarifications of the same request (e.g., "1. correct, 2. agreed, 3. apply"), merge them into a single row; don't pad the table with one-word entries.
- **Don't paraphrase the prompt.** Quote it (truncated to ~80 chars if long, with `…`). The user wrote what they wrote; preserving it is the audit trail.
