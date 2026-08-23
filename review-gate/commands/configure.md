---
description: Interactive setup for review-gate.yaml at project root. Walks the user through host, default destination branch, close-source behavior, and the review policy (effort + on_findings). Detects whether board-flow.yaml is present and offers to wire the optional Jira seam. Use once per repo after installing review-gate, before the first /review-gate:open.
argument-hint: (no arguments)
interaction: conversational
---

# /review-gate:configure

## Purpose

Write `review-gate.yaml` at project root for THIS repo. Without it, `bitbucket-expert` has no host/destination to act on and will refuse. This command asks for each value and writes the file. There is a template at `${CLAUDE_PLUGIN_ROOT}/review-gate.yaml.template`.

This is one of the few commands where **asking the user questions is the point** — `autonomous-mode`, if active, does NOT suppress questions here. Configuration comes from the user, not inference.

## Instructions

You are the orchestrator. Drive the user through each value; don't fabricate any.

### 1. Read existing config

If `review-gate.yaml` already exists at project root, read it and show the current values — you're editing, not starting cold.

### 2. Ask for each value

- **host** — only `bitbucket` is supported today. If the repo's `origin` remote isn't a `bitbucket.org` URL (`git remote get-url origin`), warn that the bundled adapter won't work and stop.
- **default_dest** — the branch PRs target, and the branch the fence protects. Offer the repo's main branch as the default (detect it: `git symbolic-ref refs/remotes/origin/HEAD` or fall back to `main`).
- **close_source_branch** — true/false. Default true.
- **strategy** — merge_commit | squash | fast_forward. Default merge_commit. (Used by `/review-gate:merge`.)
- **auto_merge** — true/false. Default false. Explain it merges automatically once the QA gate is PROVEN; false keeps the merge a human decision. Recommend false unless they explicitly want hands-off merging.
- **review.effort** — low | medium | high | max. Default medium. (Passed to `/code-review`.)
- **review.on_findings** — fix | report | block. Default fix. Explain the three: fix applies the findings then opens; report opens anyway; block stops until handled.

Write all of these (the merge keys too) — `/review-gate:merge` reads `strategy` and `auto_merge`, so omitting them forces it onto silent fallbacks.

### 3. Detect the board-flow seam

Check for `board-flow.yaml` at project root AND that the board-flow plugin is actually installed (the seam delegates to board-flow's `atlassian-expert` / `/board-flow:prove` — a config file alone isn't enough).
- **Both present** → ask whether to wire the Jira seam. If yes, include the `jira:` block (on_open / on_merge / qa_gate). Use the status names from `board-flow.yaml`'s `defaults.status_map` so the transitions match this project's actual Jira columns — don't hard-code "In Review".
- **yaml present but plugin NOT installed** → warn that the seam would reference an absent `atlassian-expert`, and omit the `jira:` block (or write it but tell the user it's inert until board-flow is installed).
- **Absent** → omit the `jira:` block entirely. review-gate runs standalone.

### 4. Write the file

Write `review-gate.yaml` at project root with the collected values. Read back the written file and show it to the user. Confirm the next step: `/review-gate:open` once there's a feature branch with changes to ship.

## Notes

- Credentials are NOT configured here — `bin/open-pr.sh` reads `~/.netrc` (see its header). If `~/.netrc` lacks a `machine api.bitbucket.org` entry, point the user there; do not put any secret in `review-gate.yaml`.
