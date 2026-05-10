---
description: Propagate updates in specs/e2e-assertions.md to the corresponding E2E tests. After the spec evolves (someone edited assertions, added cases, or removed obsolete ones), this command re-aligns the tests to match. For one endpoint or `--all` to sweep every spec section. Writes test changes; runs the build to verify alignment lands green. Use when you've updated the spec and want the tests to follow.
argument-hint: [--all] [<METHOD /path/to/endpoint>]   (mutually exclusive — one endpoint, or `--all`)
---

# /hex-backend:resync-e2e

## Purpose

Spec is the source of truth for E2E behavior (per `qa-engineer.md`'s authoritative-spec rule). When the spec changes, tests need to follow — otherwise drift accumulates and the next test failure becomes "is the spec wrong, or is the test wrong, or is the code wrong?". This command keeps the spec → tests direction in sync.

For the opposite direction (code changed, spec needs update), use `/hex-backend:document-e2e <endpoint>` (re-document from code) or `/hex-backend:spec-e2e <endpoint>` (re-author from intent if the new behavior is what should be specced). Use `--preview` on either to see the diff before writing. For 3-way alignment audit (no propagation), use `/hex-backend:audit-e2e`.

## Variables

- `$ARGUMENTS` — either:
  - `--all` — walk every section in the spec doc; re-sync each endpoint's tests.
  - `<METHOD> <path>` — a single endpoint (e.g., `GET /api/v1/assinaturas/resumo`).
  - Mutually exclusive. Both missing → error.

## Instructions

You are the orchestrator. Don't write tests yourself; delegate to `qa-engineer`. Apply `scope-discipline` — for `--all`, work endpoint by endpoint; don't batch into a single mega-prompt.

## Workflow

### 1. Parse arguments

- `--all` → mode = `sweep`. Identify the spec doc (`specs/e2e-assertions.md` or the project's equivalent — verify location).
- `<METHOD> <path>` → mode = `single`. Same parsing rules as `/hex-backend:spec-e2e` and `/hex-backend:document-e2e`.
- Both → error: "Pass either an endpoint OR `--all`, not both."
- Neither → error: "Specify an endpoint or `--all`."

### 2. Locate and parse the spec doc

Read the spec file. Extract every `#### <METHOD> <path>` section (heading + body until the next `####` or EOF).

In `single` mode: find the section matching the requested endpoint. If absent → error: "No spec section for `<METHOD> <path>`. Author one first — `/hex-backend:document-e2e <METHOD> <path>` (capture from existing code) or `/hex-backend:spec-e2e <METHOD> <path> '<intent>'` (author from intent)."

In `sweep` mode: collect all sections. If zero → error: "No `#### <METHOD> <path>` sections found in `<spec file>`. Nothing to re-sync."

### 3. For each endpoint (sequentially), delegate to qa-engineer

> Re-sync E2E tests for `<METHOD> <path>` to match the current spec section in `<spec file>` (paste the section verbatim).
>
> Workflow:
> 1. Find the existing E2E test class for this endpoint (search `*/src/test/**` for REST-assured tests against the path; controller naming usually mirrors the test class).
> 2. Compare each assertion in the spec to the existing test cases:
>    - **Spec assertion present, test missing** → add the test.
>    - **Spec assertion changed (different value, different expectation)** → update the test.
>    - **Test exists for an assertion no longer in the spec** → consider removal. If the test is structurally important (a passing happy path the spec dropped because it was implicit), keep with a comment; otherwise remove.
>    - **Test matches spec exactly** → leave alone.
> 3. Use the seed values referenced in the spec verbatim — don't substitute "equivalent" data; the spec is authoritative.
> 4. Run `./mvnw -pl <test-module> -am verify` after edits. Apply your green-build-evidence rule — paste the BUILD SUCCESS tail in your reply. If the build fails, return BLOCKED with the failure output; don't claim re-sync succeeded.
> 5. Reply with: test file paths touched, list of added/updated/removed tests (one line each), build evidence, and any open question (e.g., spec assertion that couldn't be translated to a concrete test — flag for engineering-lead).

Wait for qa-engineer's reply.

### 4. (sweep mode only) Iterate

For each remaining endpoint, repeat step 3. **Stop on first BLOCKED** — don't keep pushing through if the build is broken; the user fixes the underlying issue and re-runs `--all` to continue.

### 5. Final report

A single concise message:

- **Mode:** single (`<METHOD> <path>`) / sweep (N endpoints attempted)
- **Re-synced:** list of endpoints with one-line per-endpoint summary (added X, updated Y, removed Z, build green) — or "no changes needed" for endpoints already aligned.
- **Blocked:** 0 or 1 (endpoint + reason). In sweep mode, list the remaining-not-attempted endpoints separately.
- **Open questions:** assertions qa-engineer flagged as un-translatable to concrete tests.
- **Recommended next step:** if any open questions, suggest taking them to engineering-lead; if blocked, surface the build failure; if all green, confirm safe to commit.

## Constraints

- **Spec is authoritative; don't second-guess it.** If a spec assertion seems wrong, update the spec via `/hex-backend:document-e2e --preview` (re-document from code) or `/hex-backend:spec-e2e --preview` (re-author from intent), not by skipping the test or weakening the assertion in code. Re-sync re-aligns tests; it doesn't rewrite the spec.
- **Don't modify production code.** Re-sync touches `*/src/test/**` only. If an assertion can't be tested because the production code is missing the behavior, flag it as an open question — don't add the behavior. That's `engineering-lead`'s call.
- **Don't change the spec doc.** This is the propagation direction; the spec is the input. Spec edits go through `/hex-backend:spec-e2e` (intent → spec) or `/hex-backend:document-e2e` (code → spec).
- **Sweep is sequential.** No parallel re-sync across endpoints — tests in different modules can share fixtures, and concurrent edits risk merge conflicts.
- **Stop-on-first-BLOCKED in sweep.** Same logic as `/jira-flow:drain` — don't keep burning budget once the build is red.
