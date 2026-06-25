# proof-gate

An automated gate for the **Review** column. The `completion-auditor`
([acceptance-completeness](acceptance-completeness.md)) proves the criteria
*someone wrote down* are demonstrated at their altitude — it runs on the way
*into* Review. The proof-gate runs on the way *out*: it interrogates the whole
diff and proves every changed line of behavior is **load-bearing at the external
surface**, independent of any criterion. A backlogged Review column is triaged
by evidence, not by a human reading every card.

## Why this exists

Two true things at once:

1. A team's Review column grows past the human's capacity to review it.
2. The reviewer's real fear is not code taste — it's the change that lives in
   the domain but is never reflected in the application's *external* behavior.
   A validation that throws in a use case but never surfaces as the documented
   `422`. A new feature whose wiring to the endpoint is half-done. A bug fix
   whose regression test passes before *and* after the fix.

The `completion-auditor` catches this **for the criteria that were written**.
But it is criterion-driven — it cannot see code that no criterion mentions. The
proof-gate is **change-driven**: it interrogates the diff itself.

## The governing principle

> A passing test is necessary, not sufficient. **Green is not evidence.
> Green → red-when-I-break-it → green is evidence.** If a changed line can be
> broken and no *external* test goes red, that line is not externally
> observable — which is exactly the failure the reviewer fears.

This is [`defense-in-depth`](../common/skills/defense-in-depth) mechanized.

## The ladder of evidence

Four levels, weakest to strongest. The default ruler is **all four**, with the
noisy top level routed so it can never produce a false rejection.

| Level | Question | Tooling (build-hex / Quarkus) | Verdict effect |
|---|---|---|---|
| **L2 coverage pre-filter** | Is every changed line even touched by a test at its claimed altitude? | `quarkus-jacoco` (the Quarkus-aware JaCoCo) ∩ diff, or structural | `gap` → UNPROVEN |
| **L3 load-bearing** | If I break a changed line, does the test that should guard it — *external* where the change is externally-observable — go red? | **perturbation** (universal: revert hunk → re-run covering test → require RED) + **PIT** as the fast path on non-Quarkus layers | survives / surviving mutant → UNPROVEN |
| **L4 adversarial input** | Is there externally-observable behavior that no assertion covers? | jqwik / RestAssured fuzz on touched endpoints | finding → NEEDS-HUMAN |
| **Bug: regression-red-at-base** | Does the regression test actually capture the bug? | run the test at `base_commit` with the fix reverted | green-at-base → UNPROVEN |

L2 catches new code no test reaches. L3 is the real load-bearing proof —
"executed" isn't "guarded." L4 catches the *unknown unknowns* (behaviors no
criterion mentioned) and is the only noisy level.

### L3 on Quarkus: perturbation is the mechanism, PIT is the fast path

The principle is *break it and watch a test go red*. The realization splits by
layer, because **PIT cannot instrument `@QuarkusTest`** (Quarkus rewrites
bytecode at test time; PIT mutates the original; the two fight):

- **Inner layers** (`domain`, `application`, `infrastructure` — pure JUnit5
  tests): PIT runs, diff-scoped, and gives an exhaustive verdict fast. This is
  most cards.
- **External surface** (`@QuarkusTest` + RestAssured, which here run under
  *surefire*, not failsafe): PIT can't touch it, so the gate **perturbs** — it
  reverts the changed hunk in its throwaway worktree and re-runs the
  `@QuarkusTest`, requiring RED.

The rule that addresses the core fear: **a green PIT against unit tests never
substitutes for an external proof.** Domain behavior that scores 100% on its unit
tests can still never reach the endpoint — and that gap lives precisely in the
`@QuarkusTest` layer PIT can't see. For an externally-observable change, only the
perturbation-vs-`@QuarkusTest` proof clears it. A low PIT kill ratio on the inner
layers is reported as a complementary finding (weak unit tests), not the verdict.

> Validated on `wego-assinatura-backend` (Quarkus 3.17.5), WEGO-1698: the
> regression-red-at-base check passed cleanly; PIT ran on application (81% killed)
> and infrastructure (42% — weak adapter tests, a finding in itself); but the
> external proof was blocked because the PlugSign test double is a no-op, so the
> 422 is unobservable at the HTTP surface → correctly NEEDS-HUMAN.

### Why L4 can be set to max without flooding you

Only the **deterministic** levels (L2, L3, and the bug check) make auto-decisions
— advance or send back. **L4 never auto-decides**: a finding routes the card to
`NEEDS-HUMAN`, never to a bounce. So turning the ruler up to L4 cannot create a
false rejection; worst case it routes one extra card to your queue — exactly what
you do today, but now with the adversarial input in hand. If L4 is too noisy in
practice, dial it down without touching the levels that gate the auto-actions.

## Verdict routing

```
L2 = gap  OR  L3 = survived  OR  bugfix = green-on-base
        → UNPROVEN     → back to In Progress + the precise gap     (deterministic, auto)

deterministic levels pass, but L4 found something OR a level couldn't run
        → NEEDS-HUMAN  → stays in Review, annotated                (escalates to you)

every deterministic level passed (verified), L4 clean, nothing assumed
        → PROVEN       → advances to Done (if configured)          (auto)
```

`assumed`/`skipped` (a level that couldn't run) never permits PROVEN — same
`evidence-over-assumption` discipline as the `completion-auditor`. Lack of
evidence routes to the human, not to a clear.

## How a card maps to its diff

There is no branch-per-card convention. Instead:

- `/jira-flow:execute` and `/jira-flow:fix` record `base_commit` (the HEAD before
  any code is written) in `.claude/cards/<KEY>.yaml` when the card enters In
  Progress.
- The **Implementation Summary** comment posted at the In Review transition
  carries the head commit SHA and the touched-files list.
- `proof-reviewer` reconstructs the card's diff as `base_commit..HEAD` intersected
  with the touched files, so unrelated commits in the range don't pollute the
  scope.

## The pieces

| Piece | Lives in | Role |
|---|---|---|
| `proof-reviewer` (agent) | `build-hex` | The change-driven proof mechanics (L2/L3/L4 + bug check). Writes `.claude/proof/<KEY>.yaml`. Never edits code; works in a throwaway git worktree. |
| `/jira-flow:prove <KEY>` | `jira-flow` | Topology-agnostic. Resolves the topology, delegates to `<topology>:proof-reviewer`, applies the verdict to the card via `atlassian-expert`. |
| `/jira-flow:prove-drain [--max N]` | `jira-flow` | Iterates the Review column. Does NOT stop on UNPROVEN — a bounce is progress. |
| `base_commit` capture | `jira-flow` execute/fix | Records the change baseline at In Progress entry. |
| `status_map.done` | `jira-flow.yaml` | Optional. Set it to auto-advance PROVEN cards; leave unset for triage-only. |

The split is deliberate: `jira-flow` stays topology-agnostic (it just prefixes
the agent name and drives Jira), while the Java/Maven-specific proof mechanics
live in `build-hex` — mirroring how `/jira-flow:fix` delegates to
`/<topology>:reproduce-fix-verify`. A JS topology would ship its own
`proof-reviewer` backed by Stryker; `jira-flow` would not change.

## Configuration

In `jira-flow.yaml`:

```yaml
defaults:
  status_map:
    in_review: "Review"   # MUST match the board's literal column name
    done:      "Done"      # optional — enables auto-advance of PROVEN cards
```

If your board calls the column `"Review"` (not `"In Review"`), set `in_review`
accordingly or the prove commands find zero cards.

## The artifact

`proof-reviewer` writes `.claude/proof/<KEY>.yaml` — the per-card evidence record
(verdict, the diff scope, and per-level run lines). It is the proof-gate analogue
of `.claude/acceptance/<KEY>.yaml`. A `pass` on any level is invalid without a
`run:` line containing the literal command and its result.

**The `verdict` is mechanical — there is no waiver.** It is computed from the
levels: any `assumed`/`skipped`/`gap`/`survived`/`green-at-base` level makes
`proven` structurally unavailable. The agent never writes `proven` next to an
unmet level and never embeds a self-granted waiver (waiving a structural gap is
the human's call at review). As defense-in-depth, `/jira-flow:prove` re-derives
the verdict from the levels rather than trusting the `verdict` field, so a
malformed artifact can't auto-advance a card — a `proven` that contradicts its
own levels is treated as NEEDS-HUMAN and flagged.

## Relationship to the rest of the flow

```
To Do → In Progress → [build + security + completion-auditor] → Review → [proof-gate] → Done
                       └─ inbound gate: criterion-driven ─┘              └─ outbound gate: change-driven ─┘
```

The two gates are complementary, not redundant. The inbound gate is cheap and
stops work that shouldn't enter Review. The outbound gate is expensive (it
mutates and re-runs the IT suite) and clears the human's Review queue.
