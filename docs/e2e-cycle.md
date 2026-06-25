# E2E spec cycle

Four build-hex commands forming a directed cycle between spec, code,
and tests. Each command has a clear direction; none silently does
work in the wrong one.

```
                         intent (TASK.md / freeform)
                                    │
                                    │ /build-hex:spec-e2e
                                    ▼
                              ┌─────────────┐
                              │    spec     │   specs/e2e-assertions.md
                              │             │
                              └──┬──────────┘
                                 │      ▲
                                 │      │
              /build-hex:resync-e2e   │ /build-hex:document-e2e
                                 │      │
                                 ▼      │
                              ┌──────────┐                 ┌──────────┐
                              │  tests   │ ◄─────────────► │   code   │
                              └──────────┘   /build-hex:  └──────────┘
                                              audit-e2e
                                          (read-only 3-way diff)
```

## The four commands

| Command | Direction | Writes |
|---|---|---|
| `/build-hex:spec-e2e <ep> "<intent>"` or `--task <TASK.md>` | **intent → spec** (prescriptive) | `specs/e2e-assertions.md` |
| `/build-hex:document-e2e <ep>` | **code → spec** (descriptive) | `specs/e2e-assertions.md` |
| `/build-hex:resync-e2e <ep>` or `--all` | **spec → tests** | `*/src/test/**` |
| `/build-hex:audit-e2e <ep>` or `--all` | **read-only 3-way diff** | nothing |

All four delegate to `integration-analyst` (spec author) and/or
`qa-engineer` (test author and 3-way comparator). Neither writes
outside its lane.

## Prescriptive vs. descriptive: a critical distinction

The same endpoint can have a spec authored two ways:

### Prescriptive (`/spec-e2e`) — INTENT is authoritative

> "I want a /users endpoint that returns the current user's profile.
> Filter by `?status=active|inactive`. 404 for non-existent users.
> 401 for missing auth."

Output: a spec section describing what the endpoint **should** do,
derived from your description. Code may not exist yet. For values not
specified in intent, the agent uses `<TBD>` markers — never fabricates
plausible-looking IDs / emails / dates.

Use when:
- Designing a new endpoint before implementation.
- Re-specifying an endpoint whose current behavior is wrong (spec the
  correct behavior, not the buggy state).
- Inside `plan-build-validate`, `engineering-lead`'s ARCHITECT phase
  invokes this automatically with the TASK.md as intent.

### Descriptive (`/document-e2e`) — CODE is authoritative

The endpoint exists. Read controller + use case + adapter + seed;
document what it does today.

Output: a spec section reflecting actual behavior. Every value in the
JSON example must trace to seed data or a documented derivation
(citing `file:line`). If the seed doesn't cover a field, that's an
open question — not a placeholder.

Use when:
- Backfilling specs for endpoints already shipped.
- Freezing current behavior before a refactor or migration.
- Capturing as-is to compare against a desired spec.

### Don't mix them up

The names matter because the failure modes are different:

- Running `/document-e2e` on a non-existent endpoint → refused
  (no code to read).
- Running `/spec-e2e` on an existing endpoint whose code diverges
  from your intent → succeeds, but flags the divergence loudly. You're
  now committed to either changing the code, changing the spec, or
  both.

`integration-analyst`'s playbook (in its agent spec) has explicit
"Mode A — Descriptive" and "Mode B — Prescriptive" sections with
different read orders, different authority sources, and different
value-handling rules.

## When you'll use each

### Day-to-day flow

```
Story arrives → TASK.md authored by engineering-lead
              ↓
              integration-analyst (auto, via ARCHITECT step 2a)
              ↓
              /build-hex:spec-e2e (prescriptive, from TASK.md)
              ↓
              spec section appended to specs/e2e-assertions.md
              ↓
              dev worker implements against the spec
              ↓
              qa-engineer reads spec, translates assertions to tests
              ↓
              tests run green, code-reviewer APPROVES, Story ships
```

The `integration-analyst` invocation in step 2a was previously
descriptive — and structurally broken for new endpoints whose code
didn't exist yet. Now it's prescriptive with the TASK.md as intent.

### Backfilling old endpoints

You inherited a codebase with no E2E specs:

```
/build-hex:document-e2e GET /api/v1/users
# → reads controller + use case + adapter + seed
# → writes specs/e2e-assertions.md section reflecting current behavior

# repeat for other endpoints
```

After enough endpoints are documented, you can:

```
/build-hex:audit-e2e --all
# → reports drift across spec/code/tests for every section
# → tells you which endpoints to /resync-e2e (tests stale)
#   vs. /document-e2e (re-document if code changed)
#   vs. /spec-e2e (re-author intent if behavior changed)
```

### Spec edited, tests need to follow

You updated `specs/e2e-assertions.md` (added a case, changed an
assertion, dropped an obsolete check):

```
/build-hex:resync-e2e GET /api/v1/users
# → reads the spec section
# → diffs against existing test cases
# → adds missing tests, updates value mismatches, removes obsolete
# → runs ./mvnw verify with BUILD SUCCESS evidence rule
# → reports diff
```

Or for a sweep across all sections:

```
/build-hex:resync-e2e --all
# → walks every spec section sequentially
# → stops on first BLOCKED (same logic as /jira-flow:drain)
```

### Code suspected of drift

```
/build-hex:audit-e2e GET /api/v1/users
# → 3-way diff: Spec↔Code, Spec↔Tests, Code↔Tests
# → verdict: ALIGNED / MINOR-DRIFT / MAJOR-DRIFT
# → for MAJOR drift, suggests the most natural next command:
#   spec stale → /document-e2e (re-document from code)
#   tests stale → /resync-e2e (propagate spec to tests)
#   code wrong → /reproduce-fix-verify (treat as bug)
```

Audit is read-only — it observes and names gaps, doesn't pick a side.
You decide the fix direction.

## qa-engineer's spec-as-authoritative rule

When `qa-engineer` is invoked (in a Story, or via the spec commands)
to author or evaluate E2E tests for an endpoint, it:

1. Looks for a section matching `#### <METHOD> <path>` in
   `specs/e2e-assertions.md`.
2. **If present:** uses spec assertions as source of truth. Translates
   each into a test case. Doesn't re-derive what the spec says.
3. **If the spec contradicts the code:** FLAGS the gap with file:line
   evidence on both sides — `engineering-lead` decides which side is
   wrong. Doesn't silently choose.
4. **If no spec section exists:** proceeds with derivation from
   controller + use case + adapter + seed; notes the gap; suggests
   running `/document-e2e` or `/spec-e2e` after to formalize.

This is what makes the spec doc useful beyond documentation — it's an
input to test authoring. Drift surfaces explicitly instead of being
quietly re-derived away.

## Style rules (preserved across modes)

- Heading: `#### <METHOD> /path/to/endpoint`
- Short prose for context; JSON examples in code blocks; bullets for
  assertion lists; bold subsections for grouping.
- **Never invent seed values.** Descriptive mode: every value traces
  to seed/derivation — flag missing as open question. Prescriptive
  mode: use `<TBD: replace once seed is updated>` markers — never
  fabricate plausible-looking numbers/dates.
- Apply `evidence-over-assumption`: cite `file:line` for non-obvious
  assertions (descriptive: code reference; prescriptive: TASK.md or
  intent reference).
- Apply `scope-discipline`: one endpoint per invocation; adjacent
  observations go in an "Adjacent observations (not specced)" trailing
  section.

## What this cycle doesn't cover

- **Unit test coverage.** The cycle is about HTTP-endpoint behavior.
  Domain-level unit tests are still `qa-engineer`'s lane via the
  per-Task quality loop, not driven by `specs/e2e-assertions.md`.
- **Performance / load specs.** The spec doc is about correctness, not
  SLOs.
- **Cross-service contracts** (when calling out to another service).
  That's `integration-analyst`'s contract-analysis output (in
  `spec/<feature>.md`), separate concern.
