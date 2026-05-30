---
name: defense-in-depth
description: Use whenever about to relax/remove a validation, change an API contract, or claim "verify green = correct". Verify-green proves existing tests pass — it does NOT prove correctness of new changes. Trace the pipeline end-to-end before claiming a case works. Triggers — phrases that should activate this skill — "tornar opcional", "relaxar validação", "aceitar X também", "remover requireNonNull", "campo deveria ser nullable", "contrato agora aceita Y", "build verde, OK pra commit", "tests pass, ready to ship".
---

# defense-in-depth

**Verify green is necessary, not sufficient.** A green `./mvnw verify` (or equivalent) proves only that the **existing tests** pass — it says nothing about whether the new behavior you just introduced is actually correct end-to-end. If no test exercises the new case, no test will fail when the new case breaks.

The classic failure mode this skill prevents:

1. Agent relaxes a check at one layer (e.g., API validator) to enable a new case.
2. Agent writes a small focused test at that same layer asserting the relaxation.
3. Build is green. Agent commits.
4. The new case actually fails in production because **another layer** of the same pipeline (domain, persistence, integration adapter) still enforces the old rule — and that layer's `requireNonNull` / invariant / type constraint throws NPE / IAE / 500 when the new case reaches it.
5. The Swagger / docs that the agent updated as part of the same change now **documents the bug** — every consumer following the example hits the 500.

This pattern is concrete and recurring (e.g., WEGO-1705 in `wego-assinatura-backend` 2026-05-30 — validator relaxed, domain `Signatario.criar` and `PlugSignPort.Signatario` constructor still required the field; Swagger example used the exact broken payload).

The four rules below are the discipline. Apply all four — they cover each other.

## R1 — Pipeline-trace before relaxing

Before relaxing/removing a check at any layer (validator, service, dto, domain invariant, adapter), trace the field/rule across the **entire pipeline**:

```
HTTP/CLI → DTO → validator → application service → domain aggregate → persistence → external adapter
```

Concrete drill: `grep <field> -r` over all modules. List every site that assumes the old rule (`Objects.requireNonNull`, `if (x == null) throw`, `assert`, switch with no default, etc.). Each site needs one of:
- **Fix together** — relax/handle consistently at that layer (often the right answer).
- **Explicit justification** — "this layer keeps the strict rule because Y" (rare, must be intentional).

Skipping the trace and only fixing the reported surface is how silent bugs land.

## R2 — Test at the layer where the BEHAVIOR is observed, not just the LAYER you edited

If your code change is in the API validator but the behavior the user observes is "the request succeeds end-to-end", your test needs to hit `service.execute(command)` or an HTTP-level integration — **not just `validator.validate(req)`**.

- Validator change → at least one test that runs the request through the service (or E2E via RestAssured) and asserts the observable outcome.
- Service change → at least one test through the service (not just a unit on a private helper).
- Domain change → at least one test at the domain level **plus** one test at a higher layer that exercises the integrated path.

This catches the bugs R1 missed because R1 is human-driven and `grep` misses subtleties (e.g., constructor `requireNonNull` on a different type that the same field flows into).

The cost is ~10 lines of additional test setup; the benefit is catching pipeline bugs that single-layer tests can't see by construction.

## R3 — Declared test gap = follow-up card (never silent)

When you deliberately scope a test to one layer (legitimate — "happy path is fully covered in `OtherTest`"), do **two** things, not just one:

1. State the scope decision **in the test's javadoc / comment** so the next reader knows why.
2. Create a follow-up Jira card "E2E/integration test for X" and link it in the PR/commit description.

The discipline: **a deliberate scope is not the same as no scope**. If the gap is real, it's a tracked obligation. If it's silently skipped, it disappears.

## R4 — Smoke before ship-claim, for any contract-touching change

Before saying "ready to commit / ready to ship" on a change that touches contract surface (validator, OpenAPI, error mapping, HTTP status code, response shape), run **one real request** against a dev profile covering the exact new case.

- Cost: ~30 seconds.
- What it catches: the gap between "tests I wrote" and "what the user actually experiences" — including downstream layers `grep` missed, default values that don't quite match, error messages that read wrong.

Concrete: for validator changes, `curl localhost:8082/api/v1/endpoint -d '<exact new case payload>'` and confirm the response is what the docs/examples claim.

If you can't run smoke (no dev profile, no app, no curl access), say so explicitly in the report — don't substitute "verify green" for it.

## When to invoke

The auto-loader will surface this skill when its trigger phrases appear in the agent's reasoning (see frontmatter `description`). The agent (or orchestrator) is responsible for running through R1-R4 mentally before each contract-touching change, not waiting for someone to ask.

The discipline isn't four separate checklists — it's one stance: **the agent owns end-to-end correctness, not "I patched the layer I was asked to patch and tests still pass."**
