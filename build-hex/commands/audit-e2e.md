---
description: Read-only 3-way alignment check between specs/e2e-assertions.md, the implementation code, and the existing E2E tests. Reports drift in any direction without propagating anything. Use when you suspect divergence but want to see the gaps before deciding which side is wrong. For one endpoint or `--all` to sweep every spec section.
argument-hint: [--all] [<METHOD /path/to/endpoint>]   (mutually exclusive — one endpoint, or `--all`)
---

# /build-hex:audit-e2e

## Purpose

`/build-hex:document-e2e` propagates code → spec (descriptive). `/build-hex:spec-e2e` propagates intent → spec (prescriptive). `/build-hex:resync-e2e` propagates spec → tests. This command propagates nothing — it just reports the 3-way diff so you can decide which side is wrong before fixing it.

Three sources, three pairwise comparisons:

- **Spec ↔ Code:** does the implementation actually do what the spec says? (Spec might be stale, or code might be incorrect.)
- **Spec ↔ Tests:** do the tests assert what the spec says? (Tests might be stale, or might be over-asserting things the spec doesn't require.)
- **Code ↔ Tests:** do the tests cover what the code actually does? (Tests might miss behavior, or test obsolete behavior.)

For each pairwise gap, the audit names the divergence and points to evidence on both sides — the human picks the fix direction.

## Variables

- `$ARGUMENTS` — `--all` for sweep, or `<METHOD> <path>` for single endpoint. Mutually exclusive. Both missing → error.

## Instructions

You are the orchestrator. Don't write or modify anything; this is a read-only operation. Delegate to `qa-engineer` (which already has spec-as-authoritative + green-build awareness from its agent spec). Apply `scope-discipline` per endpoint.

## Workflow

### 1. Parse arguments

Same as `/build-hex:resync-e2e` step 1.

### 2. Locate spec doc and collect endpoints

Same as `/build-hex:resync-e2e` step 2. Collect the spec sections to audit.

### 3. For each endpoint (sequentially), delegate to qa-engineer

> Audit 3-way alignment for `<METHOD> <path>`. Read-only — do NOT edit any file, do NOT run any test. Sources to read:
>
> 1. **Spec section** in `<spec file>` (paste verbatim).
> 2. **Code:** controller (`api-rest/src/main/.../<endpoint>Controller.java`), DTO, use case, adapter, seed values referenced by the spec.
> 3. **Tests:** the existing E2E test class for this endpoint (`*/src/test/**` REST-assured tests against the path).
>
> Produce a structured report with three subsections:
>
> - **Spec ↔ Code drift** — for each spec assertion, does the code actually implement it? Cite `file:line` for the code evidence. List divergences as: `<assertion from spec>` ↔ `<what code actually does, file:line>` ↔ "spec stale / code wrong / undecided".
>
> - **Spec ↔ Tests drift** — for each spec assertion, is there a test asserting it? List: spec-assertion-without-test, test-without-spec-assertion, value-mismatch-between-spec-and-test.
>
> - **Code ↔ Tests drift** — independent of spec, does the test exercise what the code can do? List: code-branch-not-tested, test-asserts-behavior-code-doesn't-have.
>
> If any subsection has zero drift, say so explicitly ("No Spec↔Code drift detected"). Don't omit empty subsections — silence is ambiguous.
>
> Bottom line: a single-line verdict per endpoint — `ALIGNED`, `MINOR-DRIFT` (cosmetic / non-blocking), or `MAJOR-DRIFT` (one or more behavioral divergences requiring decision before next release).
>
> Do NOT propose fixes — that's the human's call after reading the audit. Don't run the build. Don't modify any file.

Wait for qa-engineer's reply.

### 4. (sweep mode only) Iterate

For each remaining endpoint, repeat step 3. Audits are read-only, so unlike re-sync there's no stop-on-failure — keep going through every endpoint and aggregate.

### 5. Final report

A single structured summary:

- **Mode:** single / sweep (N endpoints audited)
- **Aligned:** count
- **Minor drift:** count + list
- **Major drift:** count + list (each with one-line summary of the worst divergence)
- **Per-endpoint detail:** for each MINOR or MAJOR endpoint, paste the qa-engineer's three-subsection report verbatim. ALIGNED endpoints get one line each.
- **Recommended next steps:** for each MAJOR drift, the most natural next command:
  - Spec stale (code is what should be specced) → `/build-hex:document-e2e <endpoint>` (re-document from code).
  - Spec stale (spec should describe correct intent, code is wrong or incomplete) → `/build-hex:spec-e2e <endpoint>` with intent prose to re-author prescriptively.
  - Tests stale → `/build-hex:resync-e2e <endpoint>` (propagate spec to tests).
  - Code wrong → `/build-hex:reproduce-fix-verify <description>` (treat as a bug).
  - Undecided → flag for engineering-lead.

## Constraints

- **Read-only.** No `Edit`, `Write`, `MultiEdit`. No `mvnw`. No `git` mutations. The audit is observation, not action.
- **Don't pick a fix direction.** When a divergence exists, the human decides whether spec, code, or tests is wrong. The audit names the gap with evidence on each side; that's where its responsibility ends.
- **Sweep aggregates; don't bail.** Unlike re-sync (which stops on BLOCKED to avoid wasting budget on broken state), audit always walks every endpoint — its output is the list, and incomplete lists are misleading.
- **Don't audit endpoints not in the spec doc.** Audit's premise is "spec exists, check alignment." For endpoints with no spec: `/build-hex:document-e2e <endpoint>` if the implementation exists and is correct (capture current behavior), or `/build-hex:spec-e2e <endpoint> "<intent>"` if you're designing or want to re-spec from intent. Then audit becomes meaningful.
