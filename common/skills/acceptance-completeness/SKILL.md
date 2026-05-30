---
name: acceptance-completeness
description: Use whenever about to declare a card/feature/bug-fix "done", move a card to In Review, or claim an acceptance criterion is met. A green build proves the parts compile and pass — it does NOT prove the criterion is demonstrated at the surface it was written at. Pin each acceptance criterion to its altitude and require a test that exercises that exact surface end-to-end. Triggers — phrases that should activate this skill — "mover para In Review", "card pronto", "está pronto", "está feito", "implementação completa", "critério de aceite atendido", "POST retorna", "endpoint retorna 4xx/2xx", "ready for review", "acceptance criteria met", "done", "as duas metades estão cobertas".
---

# Skill: acceptance-completeness

A green build is necessary, not sufficient. It proves the code compiles
and the tests that exist pass. It says nothing about whether the *literal
acceptance criterion* — the one written in user/HTTP/UI terms — is actually
demonstrated by a test at the surface it names.

This is the failure this skill exists to stop: a criterion that says **"POST
/api/v1/assinaturas returns 422"** gets "satisfied" by a unit test proving
the use-case throws an exception (mocked), plus a separate pre-existing test
for the REST→422 mapper. Both halves are covered in isolation; the literal
"POST → 422" is never exercised end-to-end. The card moves to In Review. The
last mile is missing and nobody owns noticing.

(Real cases: `wego-assinatura-backend` WEGO-1705 and WEGO-1706, 2026-05-30.
Two cards in a row, same family. Advice alone did not stop the second.)

## The core rule: test at the criterion's altitude

Every acceptance criterion is written at some **altitude** — the outermost
surface it references:

| Criterion phrasing | Altitude | A test "at that altitude" means |
|---|---|---|
| "POST /api/v1/x returns 422" | `http` | an integration/E2E test that issues the HTTP request and asserts the status + body |
| "the CLI prints N rows" | `cli` | a test that runs the command and asserts stdout |
| "the user sees an error toast" | `ui` | a component/e2e test that renders the flow and asserts the UI |
| "an event is published on save" | `event` | a test that triggers save and asserts the event was emitted |
| "the use case rejects X" | `domain`/`application` | a unit test on the use case |

**A test of the parts does not substitute for a test of the requirement.**
If the criterion names the HTTP surface, a use-case unit test — however
correct — does not demonstrate it. The demonstrating test must live at the
criterion's altitude.

"Both halves tested in isolation" is the anti-pattern, not the defense. It is
a *defensible* coverage shape and an *indefensible* acceptance claim. When you
catch yourself writing "cada metade está coberta, mas não é o X literal do
aceite" — that is an INCOMPLETE verdict, not a footnote.

## The outermost layer must actually change and be exercised

The sibling failure: a feature implemented only in `domain`/`application`,
with no controller/DTO/wire change, so the user-facing behavior never moves.
If the criterion implies a user-observable change, the outermost layer the
user touches must (a) actually change and (b) be exercised by a test. Inner-
layer-only is INCOMPLETE.

## The artifact: `.claude/acceptance/<KEY>.yaml`

Completion is not a feeling; it is a filled-in contract. For a tracked card,
the audit produces `.claude/acceptance/<KEY>.yaml` — one entry per acceptance
criterion, each pinned to its altitude and the test that demonstrates it:

```yaml
schema_version: 1
card: WEGO-1706
status: incomplete            # complete | incomplete  (complete iff EVERY criterion is complete)
audited_at: 2026-05-30T18:12:00-03:00
criteria:
  - id: AC1
    text: "POST /api/v1/assinaturas com menor sem responsável retorna 422"
    altitude: http
    surface: "POST /api/v1/assinaturas"
    demonstrated_by:
      test: "AssinaturaResourceIT#post_menorSemResponsavel_retorna422"
      layer: api-rest
      evidence: missing       # verified (test run, green) | assumed (exists, not run) | missing
      run: null               # the literal command + result line when verified
    verdict: incomplete       # complete | incomplete
    gap: "no test issues POST /api/v1/assinaturas and asserts 422; only the use-case throw (mocked) and the mapper are covered, separately"
```

`status: complete` **iff** every criterion's `verdict: complete` **and** its
`evidence: verified`. Anything else is `incomplete`.

The artifact is the structural teeth: the `acceptance-gate` hook reads it and
**blocks the In-Review transition** while `status` is not `complete`. (See
[`green-or-revert`](../green-or-revert/SKILL.md) for the same hook+state+gate
pattern applied to build state.)

## What this skill is — and is not

- It is **not** "write more tests for everything." It is "the criterion's
  altitude dictates where its proving test lives." One test at the right
  altitude beats five at the wrong one.
- Honesty is the limit the structure cannot enforce. The hook checks the
  artifact *exists and says complete*; it cannot verify the evidence is true.
  That is why the audit is done by an **independent** reviewer
  (`completion-auditor` / the topology's reviewer), never the implementer
  self-certifying — and why `evidence: verified` requires a pasted run, not a
  claim. Apply [`evidence-over-assumption`](../evidence-over-assumption/SKILL.md):
  `assumed` is not `verified`.
- A genuine, named deferral is allowed — but it goes in `gap:` with a
  follow-up card, and it keeps the criterion `incomplete`. Silent last-mile
  gaps are the thing being stopped.
