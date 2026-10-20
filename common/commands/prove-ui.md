---
description: Proves the project's UI/extension surface through the mechanical gate — delegates to ui-proof-reviewer, which brings the app up, runs the flows declared in docs/ui-proof.yaml via Playwright (unpacked Chrome extension included) and requires a verifiable effect in the backend, with green→red→green proof when the change's diff is known. Returns PROVEN / UNPROVEN / NEEDS-HUMAN with a plain-language report in pt-BR. Without a manifest, the command does not guess — it returns NEEDS-HUMAN saying exactly what to declare. With --draft, it PROPOSES a commented manifest skeleton from the repo's structure (an explicit proposal, never proof).
argument-hint: [flow | --all | --draft]
interaction: routine
---

# /common:prove-ui

## Purpose

`/board-flow:prove` closes the backend gate; this command closes the gate of the
surface where the user suffers — SPA and Chrome extension. It is deliberately
thin: **the one who decides the verdict is `common:ui-proof-reviewer`**, from
evidence; the command only resolves the scope, delegates and applies the report
contract. What to prove lives in the project's repo, in `docs/ui-proof.yaml`
(format: `docs/ui-proof-manifest.md` in cepa). It lived in `.claude/ui-proof.yaml`
until 22/08/2026 and the agent still reads from there when the new one does not
exist — but `.claude/` is gitignored in those projects, so the manifest went away
together with the session's worktree.

## Variables

- `$ARGUMENTS` — the name of ONE flow declared in the manifest (e.g.
  `registrar-acesso`), or `--all` for all of them. Empty = `--all`.
  `--draft` = proposal mode: instead of proving, it PROPOSES a manifest skeleton
  (see step 0).

## Instructions

You are the orchestrator. Apply `defense-in-depth`, `evidence-over-assumption`,
`scope-discipline`. You do NOT decide the verdict — `ui-proof-reviewer` decides,
mechanically, from the statuses it measured. You do not relax the verdict, do
not re-run a flow "to confirm", do not edit the artifact.

## Workflow

### 0. `--draft` mode — propose the manifest, never prove it

If `$ARGUMENTS` contains `--draft`, this run proves nothing — it **proposes**.
Inspect the repo's structure (an extension `manifest.json`? a `package.json`
with `build`/`serve`/`preview` scripts? a `docs/env.yaml` with `up:`/`ports:`?
obvious SPA routes?) and write a **commented** skeleton of `docs/ui-proof.yaml`
to `docs/ui-proof.draft.yaml` following `docs/ui-proof-manifest.md` (from cepa):
fields `up`, `base_url`, `build`, `serve`, `extension_dir` when applicable, and
one or two placeholder `flows` with `steps`, `assert` (including the freshness
`{nonce}`) and `covers` — each uncertain value marked with `# TODO(humano):`.

Make it explicit in the file and in the report: **an explicit proposal ≠ proof.**
The draft does not count as a manifest — the product owner reviews, adjusts and
renames it to `docs/ui-proof.yaml`; until then, the gate keeps returning
NEEDS-HUMAN for a missing manifest. This does not violate the doctrine "the agent
does not invent flows": inventing would be *proving* against a guess; proposing a
draft for the human to validate is the opposite. Stop here — do not delegate to
ui-proof-reviewer in `--draft` mode.

### 1. Resolve scope and change context

- Parse `$ARGUMENTS`: a flow name, or `--all`/empty.
- **Diff context (optional, but valuable):** if the conversation has a change in
  play (a card with `base_commit` in `.claude/cards/<KEY>.yaml`, a branch with a
  diff against the base, an Implementation Summary), pass it on — it is what
  enables the green→red→green proof. With no known diff, the gate still runs the
  flows, but the perturbation proof comes out `n/a` and the agent reports that.

### 2. Delegate to ui-proof-reviewer

Delegate to the `common:ui-proof-reviewer` subagent with:

> Scope: <named flow | all flows in the manifest>
> Diff: <base_commit..HEAD + list of touched files | "none — run without perturbation">
> Slug: <card key if any; otherwise a short slug of the branch/feature>
>
> Read `docs/ui-proof.yaml` (or `.claude/ui-proof.yaml`, if the repo has not
> moved the manifest yet), run the in-scope flows according to your mechanics
> (Playwright preflight, up via manifest/env.yaml, scripts in
> `docs/ui-proof/runs/`, verifiable effect required for strong proof,
> green→red→green where the diff allows) and write
> `docs/proof/ui-<slug>.yaml`. Return the computed verdict.

Do not run Playwright yourself; do not "get ahead" of the agent's steps.

### 3. Apply the report contract

Pass the agent's report on to the user **checking the contract** first:

- Verdict identical to the artifact's `verdict` field (if they diverge, that is
  an agent bug — report the divergence, never pick one of the two).
- In pt-BR; for EACH finding: 2 plain-language sentences → default
  recommendation → technical detail last. If the agent returned raw jargon, you
  are the one who translates — the user never receives "perturbation survived"
  without the plain-language layer.
- Visual-only assertions that passed show up as **weak evidence**, never as
  proof — with the concrete suggestion of an `assert.backend` to add to the
  manifest.
- NEEDS-HUMAN for a missing manifest comes with the minimal skeleton of the
  `docs/ui-proof.yaml` to create (fields `up`, `base_url`, `flows`) and the
  pointer to `docs/ui-proof-manifest.md` — and with the suggestion to run
  `/common:prove-ui --draft` to generate a commented draft to review.

### 4. Optional board seam (no Jira here)

This command does **not** touch Jira. If the project has `board-flow.yaml` and the
verdict needs to become a card transition, that is the board orchestrator's
decision (e.g. `/board-flow:prove` and the like) — mention the possibility in one
line at the end of the report when you detect `board-flow.yaml` at the root, and
stop there.

## Verdicts

- **PROVEN** — every in-scope flow green with a verifiable effect and, when there
  is a diff, red under perturbation. Nothing to do but move on.
- **UNPROVEN** — declared behavior demonstrably does not hold (the flow failed,
  or stayed green with the change broken). Goes back to the implementer with the
  finding.
- **NEEDS-HUMAN** — an input is missing (manifest, toolchain, credential,
  verifiable assert, viable perturbation). The decision queue is yours — each
  item comes with a default recommendation.
