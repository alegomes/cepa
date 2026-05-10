---
description: Author an E2E behavior spec from INTENT (not from code). You describe what an endpoint should do — in prose, or via a TASK.md path — and integration-analyst produces the spec section in specs/e2e-assertions.md following project style. Use BEFORE implementation, when designing a new endpoint, or when re-specifying expected behavior independent of current code. For documenting an EXISTING endpoint's behavior from its code, use /hex-backend:document-e2e.
argument-hint: [--preview] [--task <path/to/TASK.md>] <METHOD /path/to/endpoint> ["<freeform intent description>"]
---

# /hex-backend:spec-e2e

## Purpose

**Prescriptive E2E spec authoring** — you provide intent (prose, a TASK.md, requirements), `integration-analyst` produces the spec section. The endpoint may not exist in code yet; that's fine. The spec describes what the endpoint **should** do, with the same level of detail (happy path, edge cases, errors, invariants) as the descriptive mode but driven by your description, not by reading existing code.

This is the **intent → spec** direction. For the opposite (existing code → spec, "document what's there"), use `/hex-backend:document-e2e`.

**Use when:**
- Designing a new endpoint before implementation. Spec drives dev work.
- Re-specifying an endpoint whose current behavior is wrong (you want to spec the *correct* behavior, not capture the buggy state).
- Inside `plan-build-validate`, `engineering-lead`'s ARCHITECT phase invokes this automatically using the TASK.md as intent (the new endpoint doesn't have code yet).

**Don't use when:**
- The endpoint exists and works correctly and you just need spec-from-code → use `/hex-backend:document-e2e`.

## Variables

- `$ARGUMENTS` — combination of:
  - `<METHOD> <path>` — required. The endpoint being specced.
  - Freeform intent description in quotes — optional. Plain English describing what the endpoint should do.
  - `--task <path>` — optional. Path to a TASK.md (or any markdown file) treated as authoritative intent. Useful when invoked from a Story flow.
  - `--preview` — optional. Show the proposed section, don't write.

  At least one of `--task` or freeform description must be present, otherwise there's nothing to spec from.

## Instructions

You are the orchestrator. Don't author the spec yourself; delegate to `integration-analyst`. Apply `scope-discipline` (one endpoint per invocation). Apply `evidence-over-assumption` — open questions surface to the user, don't get papered over.

## Workflow

### 1. Parse arguments

- Extract `<METHOD> <path>` (same parsing as `/document-e2e`).
- Detect `--preview` flag (default = write).
- Detect `--task <path>` flag — if present, verify the file exists.
- Capture any quoted freeform string as intent.
- Validate: at least one source of intent must be present (`--task` OR freeform). If neither, reply: "No intent provided. Pass `--task <path>` to a TASK.md, or describe the endpoint behavior in quotes after the path. The spec needs *something* to be authored from."

### 2. Sanity check the spec doc

Same as `/document-e2e` step 2 — locate `specs/e2e-assertions.md` (or equivalent), confirm or ask permission to create. Skip the "endpoint exists in code" check — endpoint may not exist yet (that's the whole point of prescriptive mode).

If the endpoint DOES exist in code (Grep finds a matching controller), surface a soft note: "Endpoint `<METHOD> <path>` exists in code at `<file:line>`. You're authoring a prescriptive spec — proceed if you intend the spec to describe desired behavior independent of (or differing from) the current implementation. Otherwise, `/hex-backend:document-e2e` would capture what the code does today." Don't block on it; the user picks.

### 3. Delegate to integration-analyst (prescriptive mode)

> Author E2E behavior spec for `<METHOD> <path>` from INTENT, not from code. Mode: prescriptive. Output mode: `<write | preview>`. Spec file: `<resolved path>`.
>
> Intent sources:
> - **TASK.md (if provided):** `<path to TASK.md>` — full content pasted below. Treat acceptance criteria, integration seams, and NFRs as authoritative.
>   ```
>   <verbatim TASK.md content>
>   ```
> - **Freeform description (if provided):** `<verbatim quoted string>`
>
> Apply your "E2E behavior spec authoring — prescriptive mode" playbook (in your agent spec):
>
> 1. Read the existing spec doc to match style (heading levels, prose tone, JSON-example formatting). Style continuity matters even when the content is new.
> 2. Read the OpenAPI yaml IF this endpoint has a contract entry — the OpenAPI is contract-of-record for shape/validation/codes. If there's no entry yet (greenfield), the spec describes what the OpenAPI WILL define and you note this for the api-dev to align.
> 3. From the intent, derive: happy path response shape (with placeholder values clearly marked as `<TBD-by-implementation>` if real seed values aren't determinable yet), per-field assertions, filters/params behavior, tenant isolation requirements, edge cases, error scenarios, domain invariants.
> 4. Where the intent is silent on something the spec needs (e.g., "what should happen on empty `q`?"), include the case but mark it as an "Open question" — don't invent the answer. The user resolves these.
> 5. NEVER invent seed values. If the intent doesn't specify concrete data, write `<TBD: replace with seed value once seed is updated>` rather than fabricating a number.
>
> Output mode handling:
> - `write` mode: replace any existing section for the same endpoint; otherwise append. Show diff in reply.
> - `preview` mode: show proposed section text; don't touch the file.

Wait for the analyst's reply.

### 4. Surface to user

A single concise message:

- **Endpoint:** `<METHOD> <path>`
- **Intent source:** `--task <path>` / freeform / both.
- **Mode:** write / preview.
- **Open questions:** count + summary. Prescriptive specs typically have more open questions than descriptive (intent rarely covers every edge case). Resolve them before authoring tests against this spec.
- **Code-existence note:** if the endpoint already has an implementation that contradicts the spec, surface the divergence loudly — the user is now committed to changing the code, the spec, or both.
- **Next step:** if open questions, suggest resolving; if endpoint doesn't exist yet, suggest dispatching to `engineering-lead` to implement against the spec; if code already exists and diverges, suggest `/hex-backend:audit-e2e <endpoint>` for the 3-way diff.

## Constraints

- **Intent is required.** No silent fallback to "read the code" if intent is missing — that would silently turn this into descriptive mode. Refuse with the "no intent provided" message.
- **Don't invent seed values.** Use `<TBD>` markers; the human (or a future Story) supplies real values.
- **Don't read existing controller/use-case as authoritative.** The intent is authoritative. Reading code is fine for context (e.g., to align styling) but never to override what the user said.
- **One endpoint per invocation.** Same as `/document-e2e`.
- **Spec doc is the only writable target.** No code changes. No test changes.
