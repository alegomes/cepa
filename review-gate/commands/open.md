---
description: Open a pull request for the current branch, gated by a hygiene review. Runs /code-review on the diff (handling findings per review-gate.yaml), drafts the PR title + body from the diff, then delegates the actual open to bitbucket-expert. If jira-flow.yaml is present and the Jira seam is configured, also transitions the linked card In Progress → In Review.
argument-hint: [dest-branch]   (optional: PR target; default = review-gate.yaml default_dest)
---

# /review-gate:open

## Purpose

The main gesture: turn the current feature branch into a reviewed PR instead of a direct merge to main. Hygiene gate first (cheap, blocks early), then open the PR with a description drafted from the diff.

The **QA axis is not here** — proving the change is correct and load-bearing belongs to the merge gate (`/jira-flow:prove`), by design. This command owns hygiene + transport, nothing more.

## Variables

- `$ARGUMENTS` — optional destination branch. Default: `review-gate.yaml` `default_dest`.

## Instructions

You are the orchestrator. You delegate the two things that aren't yours to decide: the review (to `/code-review`) and the Bitbucket call (to `bitbucket-expert`).

### 1. Preconditions

- Read `review-gate.yaml`. Absent → tell the user to run `/review-gate:configure` first; stop.
- Confirm the current branch is not the destination branch itself (you don't open a PR from main into main). `git rev-parse --abbrev-ref HEAD`.
- Confirm there is a diff to ship against the destination. Nothing to ship → say so, stop.

### 2. Hygiene gate

Run the same gate as `/review-gate:review`: invoke `/code-review` at `review.effort`, scoped to the branch diff, and apply `review.on_findings`:
- `fix` → apply findings, then continue to open the PR with the cleaned tree.
- `report` → continue to open the PR; carry the findings into the PR body as a "review notes" section.
- `block` → STOP. Do not open the PR. Report the findings and the "gate not passed" verdict.

### 3. Draft the PR title and body

- **Title** — concise summary of the change. If the branch name or a commit carries an issue key (e.g. `WEGO-1234`), lead the title with it. This is the command's judgment, not `bitbucket-expert`'s.
- **Body** — drafted from the diff: what changed and why, notable decisions, and (when `on_findings: report`) the residual review notes. Write it to a temp file to hand off as `-B`.

### 4. Open the PR

Delegate to **`bitbucket-expert`** with: the title, the body-file path, source (current branch), dest (`$ARGUMENTS` or config `default_dest`), and the `close_source_branch` setting. It returns the PR id + URL (or `ALREADY OPEN` if one exists for this source→dest).

### 5. Jira seam (only if configured)

If the **jira-flow plugin is installed** AND `review-gate.yaml` has a `jira:` block with `on_open`:
- Delegate to **`jira-flow`'s atlassian-expert** to transition the linked card per `on_open` (e.g. In Progress → In Review), including the Implementation Summary it requires (files touched, tests, build verification, the PR URL).
- jira-flow not installed (even if a stray `jira-flow.yaml` exists), or no `jira:` block → skip silently. review-gate works standalone. Don't delegate to an `atlassian-expert` that isn't there.

### 6. Report

PR URL + id, the gate verdict (clean / fixed / findings-carried), and — if applicable — the Jira transition. One concrete next step (e.g. "merge once the QA gate passes: `/jira-flow:prove <KEY>`").

## Notes

- Do not assemble curl or touch Bitbucket directly — that's `bitbucket-expert`'s exclusive lane.
- Do not transition Jira directly — that's atlassian-expert's lane.
- This command owns the OPEN boundary (hygiene gate). The QA gate + the actual merge are `/review-gate:merge` — point the user there as the next step.
