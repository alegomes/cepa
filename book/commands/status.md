---
description: Show the current state of the book — which chapters are done, in progress, awaiting your review, or not started. No agents needed; reads artifact STATUS markers from disk.
argument-hint: ""
---

# /book:status

## Purpose

At-a-glance progress report for the whole book. Reads artifact files and their STATUS markers — no agent delegation, no writes. Safe to run at any time.

## Workflow

### 1. Read the master plan

Read `manuscript/BOOK.md`. Extract the ordered chapter list. If missing, report: "No BOOK.md found — run /book:inception first."

Read `manuscript/audience.md`. Note whether it exists.

### 2. Determine each chapter's state

For each chapter slug in BOOK.md order, read the following files and check their last line for STATUS markers:

| File | Present + STATUS: approved | Present + STATUS: complete | Present, no marker | Missing |
|---|---|---|---|---|
| `manuscript/<slug>/outline.md` | outline approved | outline awaiting approval | outline incomplete | — |
| `manuscript/<slug>/draft.md` | draft approved | draft awaiting approval | draft incomplete | — |
| `manuscript/<slug>/review-technical.md` | — | review done | review incomplete | — |
| `manuscript/<slug>/review-copy.md` | — | review done | review incomplete | — |

Derive the chapter state using this priority order (first match wins):

| State | Condition |
|---|---|
| `✓ complete` | Both review files STATUS: complete |
| `◀ awaiting your review — draft` | draft.md STATUS: complete (not approved) |
| `◀ awaiting your review — outline` | outline.md STATUS: complete (not approved) |
| `reviews running` | draft approved + at least one review file exists but not STATUS: complete |
| `draft in progress` | outline approved + draft.md exists but incomplete or missing marker |
| `outline approved` | outline STATUS: approved, no draft.md |
| `outline in progress` | outline.md exists but no STATUS: complete or approved |
| `not started` | outline.md missing |

Also check prerequisites from BOOK.md: if a chapter is `not started` and its prerequisites aren't `complete`, mark it `blocked (needs <prereq-slugs>)`.

### 3. Identify the last active chapter

The "last active" chapter is the one furthest along that isn't `complete`. If the author needs to act (awaiting review), flag it prominently.

### 4. Display

```
Book: <title from BOOK.md>
Audience profile: ✓ | ✗ missing — run /book:inception

Chapter progress:
  <slug>   <state>
  <slug>   <state>
  ...

Last active: <slug> — <state>
Suggested next step: <command>
```

State display format:

| State | Display |
|---|---|
| `✓ complete` | `✓  complete` |
| `◀ awaiting your review — draft` | `◀  draft ready for your review` |
| `◀ awaiting your review — outline` | `◀  outline ready for your review` |
| `reviews running` | `   reviews in progress` |
| `draft in progress` | `   draft in progress` |
| `outline approved` | `   outline approved · draft not started` |
| `outline in progress` | `   outline in progress` |
| `not started` | `   not started` |
| `blocked` | `   blocked (needs <slugs>)` |

Suggested next step:

- If any chapter is `awaiting your review`: `/book:write-chapter <slug>` (resumes at the checkpoint)
- If a chapter is `in progress` or `outline approved`: `/book:write-chapter <slug>`
- If all chapters are `complete`: `/book:finalize`
- If no chapters started: `/book:write-chapter <first-slug-from-BOOK.md>`

## Example output

```
Book: AI, LLM Engineering, and Agents Engineering
Audience profile: ✓

Chapter progress:
  ch01-foundations-of-llms        ✓  complete
  ch02-prompt-engineering         ✓  complete
  ch03-rag-pipelines              ◀  draft ready for your review
  ch04-fine-tuning                   outline approved · draft not started
  ch05-agent-architectures           blocked (needs ch03)
  ch06-evaluation-and-evals          not started
  ch07-production-llm-systems        not started

Last active: ch03-rag-pipelines — draft ready for your review
Next step: /book:write-chapter ch03-rag-pipelines
```

## Constraints

- Read-only. No writes, no agent delegation.
- Don't infer state from file content — only from STATUS markers on the last line.
- If a file exists but has no STATUS marker, treat it as incomplete (the agent was interrupted).
