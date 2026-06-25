# acceptance-completeness

A structural safeguard against the "both halves are covered" failure
mode. A green build proves the *parts* compile and pass; it never proves
the *acceptance criterion* is demonstrated at the surface it was written
at. A card doesn't reach In Review until an independent audit confirms a
test exercises each criterion end-to-end at its own altitude.

## Why this exists

A common failure path:

1. The criterion says **"POST /api/v1/assinaturas returns 422"**.
2. The implementer writes a unit test proving the use-case throws (mocked),
   and there's a separate pre-existing test for the REST→422 mapper.
3. Both halves are covered in isolation. The build is green.
4. The literal "POST → 422" is never exercised end-to-end.
5. The card moves to In Review. The last mile is missing and nobody owns
   noticing.

A green build says the tests that exist pass. It says nothing about
whether the test that *demonstrates the requirement* exists. "Both halves
tested separately" is a defensible coverage shape and an indefensible
acceptance claim — they are not the same thing.

This was not hypothetical: `wego-assinatura-backend` WEGO-1705 and
WEGO-1706 (2026-05-30), two cards in a row, same family. Advice alone did
not stop the second one. The skill + agent + hook below make this failure
structurally hard — the same hook+state+gate pattern as
[`green-or-revert`](green-or-revert.md), but the state is per-card
acceptance evidence instead of build greenness.

## The core concept: altitude

Every acceptance criterion is written at some **altitude** — the outermost
surface it names. A test "at that altitude" is one that exercises *that*
surface, not an inner part of it.

| Criterion phrasing | Altitude | A test at that altitude |
|---|---|---|
| "POST /api/v1/x returns 422" | `http` | integration/E2E test that issues the request and asserts status + body |
| "the CLI prints N rows" | `cli` | test that runs the command and asserts stdout |
| "the user sees an error toast" | `ui` | component/e2e test that renders the flow and asserts the UI |
| "an event is published on save" | `event` | test that triggers save and asserts the event was emitted |
| "the use case rejects X" | `domain`/`application` | unit test on the use case |

**A test of the parts does not substitute for a test of the requirement.**
If the criterion names the HTTP surface, a use-case unit test — however
correct — does not demonstrate it; the demonstrating test must live at the
criterion's altitude. The sibling failure is the same shape inverted: a
feature implemented only in `domain`/`application` with no controller/DTO/
wire change, so the user-facing behavior never moves. If the criterion
implies a user-observable change, the outermost layer the user touches
must actually change *and* be exercised by a test.

## The state file: `.claude/acceptance/<KEY>.yaml`

Completion is not a feeling; it is a filled-in contract. **The orchestrator
does not own the writes** — the `completion-auditor` agent does, one entry
per acceptance criterion, each pinned to its altitude and the test that
demonstrates it:

```yaml
schema_version: 1
card: WEGO-1706
status: incomplete            # complete | incomplete
audited_at: 2026-05-30T18:12:00-03:00
criteria:
  - id: AC1
    text: "POST /api/v1/assinaturas com menor sem responsável retorna 422"
    altitude: http
    surface: "POST /api/v1/assinaturas"
    demonstrated_by:
      test: "AssinaturaResourceIT#post_menorSemResponsavel_retorna422"
      layer: api-rest
      evidence: missing       # verified | assumed | missing
      run: null               # the literal command + result line when verified
    verdict: incomplete       # complete | incomplete
    gap: "no test issues POST /api/v1/assinaturas and asserts 422; only the use-case throw (mocked) and the mapper are covered, separately"
```

`status: complete` **iff** every criterion's `verdict: complete` **and**
its `evidence: verified`. Anything else is `incomplete`.

It lives under `.claude/acceptance/` — the same transient-state home as
`.claude/last-build.json` and `.claude/forks/`. Untracked, not part of the
plugin. `/jira-flow:fix` deletes a stale `<KEY>.yaml` at the start of a run
so a prior verdict can't poison a fresh start.

## The state machine

For the purpose of the gate, the only thing that matters is whether the
artifact exists and what its `status` says:

```
   absent ───── completion-auditor runs ─────► incomplete ◄──┐
   (audit                                          │         │ re-audit after a
    not run)                                        │         │ gap is closed but
                                                    │         │ still short
                                                    ▼         │
                                                 complete ────┘
                                            (every criterion verified)
```

| `status` | Meaning | Gate behavior |
|---|---|---|
| absent | Audit hasn't run yet (e.g. To Do → In Progress). | ALLOW — nothing to enforce. |
| `incomplete` | At least one criterion isn't demonstrated at its altitude, or its evidence isn't `verified`. | BLOCK the In-Review transition. |
| `complete` | Every criterion has a demonstrating test at its altitude, run green. | ALLOW. |
| unparseable | Malformed artifact. | BLOCK (treated as not-complete). |

`incomplete` set by an audit stays `incomplete` until a fresh audit lands
`complete`. Editing the file by hand to say `complete` is cheating, and the
skill flags it — the recovery is to close the altitude gap, not to fake the
verdict.

## The agent: `completion-auditor`

An independent, adversarial last-mile gate (`common/agents/
completion-auditor.md`; Sonnet; tools `Read, Glob, Grep, Bash, Write`).
**Independence is the whole point** — it did not write the code, has no
`Edit`/`MultiEdit`, and never self-certifies. Per criterion it asks one
question: *is there a test that demonstrates this literal criterion at the
surface it was written at, and did that test actually run green?*

Its rules:

1. **Adversarial default: INCOMPLETE.** If it can't point to a single test
   exercising the criterion's stated surface end-to-end, the criterion is
   `incomplete`. The burden of proof is on completeness.
2. **`verified` requires a run, not a claim.** It runs the demonstrating
   test itself (Bash) and pastes the literal command + result line. If it
   can't run it, `evidence: assumed` — and `assumed` never lets a criterion
   be `complete`. (`evidence-over-assumption` applies.)
3. **Altitude is non-negotiable.** It reads the criterion's words and pins
   the outermost surface; it does not let the test drift below it.
4. **Outermost-layer check.** Inner-layer-only (domain/application with no
   controller/wire change or test) is `incomplete`.
5. **A named deferral stays incomplete.** A genuine, justified gap goes in
   `gap:` with a suggested follow-up — but the criterion stays `incomplete`.
   Deeming a known gap acceptable is the human's call at review, not the
   auditor's.

It writes `.claude/acceptance/<KEY>.yaml` and returns `COMPLETE` or
`INCOMPLETE` with the precise missing altitude per gap, so the flow can
route the fix without coming back to ask.

## The hook: `acceptance-gate.py`

A PreToolUse hard gate (`common/hooks/acceptance-gate.py`). It matches the
Atlassian MCP transition tool (`transitionJiraIssue`, any server prefix),
extracts the issue key from the tool input, and reads
`.claude/acceptance/<KEY>.yaml`:

| Artifact state | Hook |
|---|---|
| absent | ALLOW (audit hasn't run; not gated) |
| present, `status: complete` | ALLOW |
| present, `status:` anything else | BLOCK (exit 2) |
| key not extractable | ALLOW (never spuriously block a transition) |

### The temporal trick

The hook **gates the In-Review transition without ever decoding which
status is being targeted.** It needs no transition-id table because of
*when* the artifact appears:

- The `completion-auditor` writes `<KEY>.yaml` only *after* implementation,
  right before the flow tries to move the card to In Review.
- Earlier transitions (To Do → In Progress) run with **no artifact on
  disk** → the gate fails open (nothing to enforce yet).
- The In-Review transition runs with the artifact **present** → the gate
  reads its `status` and blocks unless it's `complete`.

The artifact's temporal existence *is* the signal. The hook stays generic
across every Jira lifecycle — it never has to know that "31" means In
Review on one board and something else on another.

When it fires, the block message names the card, the current status, the
open per-criterion gaps (scraped from `gap:` lines), and the recovery —
close the altitude gap and re-run the auditor, not edit the artifact.

## How it's wired into the flows

The discipline is enforced at two layers — a prompt-level precondition that
fails early and clearly, and the hook that catches it structurally even if
the prompt is ignored.

### `build-hex:reproduce-fix-verify` — step 4, "Acceptance audit"

After Verify (green build + code review prove the change is correct and
minimal), the orchestrator invokes `completion-auditor` **directly — not
through `engineering-lead`.** The chain that built the fix does not get to
certify its own completeness. INCOMPLETE routes the named gap back to the
right dev/qa worker (write the missing altitude test), re-runs Verify, and
re-audits. A READY-TO-SHIP verdict requires a `completion-auditor`
COMPLETE; `till-done` makes the last mile part of the job, not a follow-up.
Even the regression test in step 1 is required to sit at the criterion's
altitude — a mocked use-case test is not "the spec" for an HTTP-surface
criterion.

### `jira-flow:fix` — precondition before In-Review

The bug-flow wrapper runs `reproduce-fix-verify`, then before transitioning
to `in_review` checks that the report carries a `completion-auditor`
COMPLETE and the `.claude/acceptance/<KEY>.yaml` path. INCOMPLETE (or
absent) → it does **not** transition; the card stays in `in_progress` until
the missing altitude test lands. The `acceptance-gate` hook is the
backstop: even if the orchestrator tried to transition anyway, the hook
reads the artifact and blocks the `transitionJiraIssue` call. The
precondition just fails earlier and more clearly. (`/jira-flow:execute`
auto-routes Bug cards here.)

## What this doesn't protect against

- **Dishonest evidence.** The hook checks the artifact *exists and says
  complete* — it cannot verify the evidence is *true*. This is the limit the
  structure cannot enforce, and the reason the audit is done by an
  **independent** reviewer (never the implementer) and `evidence: verified`
  requires a *pasted run*, not a claim. Honesty in the artifact is the one
  thing the hook cannot supply.
- **Criteria the auditor mis-reads.** If it pins the wrong altitude, the
  gate enforces the wrong thing. Altitude is read from the criterion's
  words; vague criteria produce vague audits.
- **Cards with no Jira key.** The hook gates `transitionJiraIssue`; work
  tracked outside Jira (a slug, an untracked task) gets the artifact and the
  auditor's verdict, but not the transition gate. The discipline still
  applies; only the structural backstop is Jira-specific.
- **Wrong-but-green tests.** Same caveat as `green-or-revert`: if a test at
  the right altitude is itself buggy and falsely passes, the audit trusts
  the green result.

The gate eliminates the specific, recurring failure: a card reaching In
Review while a criterion is only demonstrated by its parts. Everything else
is still on the team and the human reviewer.

## Disabling temporarily

Don't. The recovery path is to close the altitude gap and re-run the
auditor, not to silence the gate. Hand-editing `<KEY>.yaml` to say
`complete` is the one move the whole design exists to prevent — and the
skill flags it.
