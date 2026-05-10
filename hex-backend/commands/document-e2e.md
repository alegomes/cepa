---
description: Document the E2E behavior of an EXISTING endpoint by reading its current implementation (controller + use case + adapter + seed). Produces a descriptive spec section in specs/e2e-assertions.md reflecting what the code actually does today. Use to backfill specs for endpoints already shipped, or to capture current behavior before refactoring. For NEW endpoints (spec-first / spec drives implementation), use /hex-backend:spec-e2e instead.
argument-hint: [--preview] <METHOD /path/to/endpoint>   (e.g., "GET /api/v1/assinaturas/resumo")
---

# /hex-backend:document-e2e

## Purpose

**Descriptive E2E spec authoring** — capture what an endpoint does today, traceable to the actual code + seed (no invented values), in the project's existing style. The spec lives in `specs/e2e-assertions.md` (or wherever the project's E2E spec doc is — the agent verifies on read).

This is the **code → spec** direction. For the **intent → spec** direction (you describe what an endpoint should do, the spec is authored from your description, code may not exist yet), use `/hex-backend:spec-e2e`.

**Use when:**
- The endpoint exists in code but isn't in the spec doc (backfill).
- You want to freeze current behavior before a refactor or migration.
- The implementation drifted from a stale spec and you want to capture the "as-is" before deciding which side to fix.

**Don't use when:**
- The endpoint doesn't exist yet — there's no code to read. Use `/hex-backend:spec-e2e` (prescriptive) instead.
- You're inside a `plan-build-validate` flow creating a new endpoint — `engineering-lead`'s ARCHITECT phase invokes `/hex-backend:spec-e2e` automatically (intent-driven, since code doesn't exist yet).

## Variables

- `$ARGUMENTS` — the endpoint as `<METHOD> <path>`. Method in uppercase (`GET`, `POST`, `PUT`, `DELETE`, `PATCH`). Path verbatim from OpenAPI / controller. Optional `--preview` flag (default behavior is **write** — adds or replaces the section in the spec file).

## Instructions

You are the orchestrator. Don't implement anything yourself; delegate to `integration-analyst`. Apply `scope-discipline` — one endpoint per invocation. Apply `evidence-over-assumption` — pass through any "open questions" the analyst surfaces; don't paper over them.

## Workflow

### 1. Parse arguments

- Extract `<METHOD>` and `<path>` from `$ARGUMENTS`. If parsing fails (missing method, no leading `/` on path, etc.), reply with the expected format and stop.
- Detect `--preview` flag. Default mode is **write**.

### 2. Sanity check

Confirm that:
- A spec file exists somewhere obvious (`specs/e2e-assertions.md`, `spec/e2e-assertions.md`, `docs/specs/e2e-assertions.md`). If multiple, ask the user which to extend. If none, ask: "No E2E spec doc found at the usual paths. Create `specs/e2e-assertions.md`? (yes / specify path)" — don't auto-create at a path the user didn't approve.
- The endpoint exists. Quick `Grep` for the method + path in `api-rest/src/main/**` to confirm there's a matching controller. If zero matches: "Endpoint `<METHOD> <path>` not found in `api-rest/src/main/**`. Verify the spelling and re-run." If multiple matches (e.g., versioned routes): show them and ask which.

### 3. Delegate to integration-analyst (descriptive mode)

> Document the E2E behavior of EXISTING endpoint `<METHOD> <path>`. Mode: descriptive (code → spec). Output mode: `<write | preview>`. Spec file: `<resolved path>`.
>
> Apply your "E2E behavior spec authoring — descriptive mode" playbook (in your agent spec): read the spec file's existing style first, then OpenAPI, controller, use case, adapter, seed; produce the section reflecting what the code currently does, in the project's heading + prose + JSON-example convention. Don't invent values — every value in the JSON example must trace to seed data or a documented derivation. Cite `file:line` for non-obvious assertions. Cover happy path, per-field assertions, cross-endpoint consistency, filters/params, tenant isolation, edge cases, error scenarios, and domain invariants.
>
> If write mode: replace any existing section for the same endpoint; otherwise append. Show the diff in your reply.
>
> If preview mode: show the proposed section text only; don't touch the file.
>
> Open questions (anything you couldn't determine from reading) go at the end of the section under "Open questions" — flag them, don't guess.

Wait for the analyst's reply.

### 4. Surface to user

A single concise message:

- **Endpoint:** `<METHOD> <path>`
- **Mode:** `write` → "Updated `<spec file>` (replaced existing section / appended new section)." OR `preview` → "Preview only — nothing written."
- **Open questions:** count + summary of each (where the analyst couldn't determine a value from sources). The user should resolve these before relying on the spec.
- **Adjacent observations:** anything the analyst flagged as out-of-scope-but-worth-noting (e.g., a sibling endpoint with similar issues).
- **Next step:** if there are open questions, suggest resolving them; if not, suggest authoring the E2E test (the spec is the test author's input).

## Constraints

- **One endpoint per invocation.** Don't batch even if the user supplies multiple — the read-many-files-then-write pattern is heavy; force the user to scope.
- **Don't invent values.** If the seed doesn't cover the field, the value is an open question — not a placeholder.
- **No code changes.** This command writes a spec doc, never controller / use case / adapter / test code. Routing test authoring lives elsewhere (qa-engineer, downstream).
- **No tenant guessing.** If the endpoint has tenant scoping that isn't obvious from controller + adapter, surface it as an open question. Don't fabricate "data from another tenant must not appear" without verifying that tenant filtering actually exists in code.
