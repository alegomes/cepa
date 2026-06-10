---
description: Run ONLY the hygiene gate on the current local diff — lint/style/simplify/obvious bugs via /code-review — without opening a PR. Standalone pre-flight; use it to see (or fix) what the gate would catch before you commit to opening the PR. /review-gate:open runs this same gate and then opens the PR.
argument-hint: [base-ref]   (optional: diff against this ref instead of the repo's default branch)
---

# /review-gate:review

## Purpose

The **hygiene axis** of the gate, run in isolation. This is form, not behavior: lint, style, standardization, simplification, and obvious bugs — the cheap, fast pass. It does NOT touch Bitbucket and does NOT open a PR. The QA axis (is it correct, is every line load-bearing) is a separate, heavier gate that lives at merge — see `/jira-flow:prove`.

Use this when you want the gate's verdict (or fixes) decoupled from opening the PR.

## Variables

- `$ARGUMENTS` — optional base ref to diff against. Default: the repo's main branch (from `review-gate.yaml` `default_dest`, else detected).

## Instructions

You are the orchestrator.

1. **Read `review-gate.yaml`** for `review.effort` and `review.on_findings`. If the file is absent, tell the user to run `/review-gate:configure` first — or proceed with defaults (effort=medium, on_findings=report) and say so.
2. **Scope the diff.** `git diff <base>...HEAD` (and uncommitted changes). If there's nothing to review, say so and stop.
3. **Run the hygiene review** by invoking the `/code-review` skill at the configured effort, scoped to the diff. Do not re-implement review judgment inline — `/code-review` is the reviewer.
4. **Apply `on_findings`:**
   - `fix` → invoke `/code-review` (or `/simplify`) in fix mode to apply the findings to the working tree, then report what changed.
   - `report` → print the findings, change nothing.
   - `block` → print the findings and stop with a clear "gate not passed" verdict.
5. **Report** the verdict (clean / fixed / findings-remain), the effort used, and the next step (`/review-gate:open` to open the PR).

## Notes

- This command never calls `bitbucket-expert`. It's the gate without the PR.
- Project-specific review conventions belong in the host repo's `CLAUDE.md`, where `/code-review` will pick them up — not in this command.
