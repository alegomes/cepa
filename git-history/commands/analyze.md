---
description: Analyze the Git history of one or more repositories — produce a narrative of how the project evolved and/or a structured effort-allocation report across a single timeline. Drives the git-historian lead, which runs the deterministic collector + renderer, then the narrator. Outputs land in git-history-report/.
argument-hint: <repo-path> [<repo-path> ...] [--since DATE] [--until DATE] [--granularity auto|week|month|quarter] [--metric commits|churn|est_hours] [--story-only | --effort-only]
---

# /git-history:analyze

## Purpose

Run the full git-history flow on one or more repositories:

1. **Collect** — deterministic extraction of effort proxies (commits, line
   churn, time-clustered work hours, per-area attribution) and narrative
   signals (commit-message keywords, structural shifts, stack changes, reverts,
   gaps) into `git-history-report/datapack.json`, plus matplotlib charts.
2. **Narrate** — turn the facts into a project story (`narrativa.md`) and/or a
   structured effort report (`relatorio.md`), keeping evidence separate from
   inference.

For a single repo just pass its path; for cross-project effort analysis pass
several — they're placed on one shared timeline.

## Variables

- `$ARGUMENTS` — repo path(s) plus optional flags. If no path is given, default
  to the current directory (`.`) but confirm that's the intended target first.

## Instructions

You are the orchestrator. Do not run the analysis or write the report yourself.
Delegate the whole flow to `git-historian` and synthesize its return for the user.

Apply `evidence-over-assumption`: when you relay findings, preserve the
narrator's evidence-vs-inference distinction. Don't upgrade a "suggests" into a
"shows."

## Workflow

### 1. Delegate to `git-historian`

> Analyze the Git history for: **$ARGUMENTS**
>
> Determine which job(s) the user wants — the project *story*, the *effort*
> analysis, or both (default: both, unless `--story-only`/`--effort-only`).
> Drive `history-collector` to produce `git-history-report/datapack.json` + the
> charts, then `history-narrator` to write the deliverables. Report back the
> story spine, the headline effort finding, the evidence-vs-inference caveats,
> and the artifact paths.

Wait for `git-historian` to return.

### 2. Report to the user

A short synthesis:

- **Story:** the 2-3 phase arc (one or two sentences).
- **Effort:** where the bulk of the work went (repo / area / period).
- **Caveats:** workflow blind spots (squash/rebase flattening) and the proxy
  nature of every number — surfaced, not buried.
- **Read more:** `git-history-report/narrativa.md`, `relatorio.md`, plus the
  charts and `datapack.json`.

## Constraints

- Don't run `collect.py`/`render.py` yourself — that's the collector's job.
- Don't write the report yourself — that's the narrator's job.
- If no repo path was given and the cwd isn't clearly the intended target, ask
  before spending work.
- Keep the user-facing summary short; the full story lives in the artifacts.
