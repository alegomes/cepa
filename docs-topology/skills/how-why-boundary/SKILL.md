# how-why-boundary

The one discipline this whole topology exists to protect: separate the **HOW**
(extractable from code) from the **WHY** (elicitable — owner / commit / ADR /
tracker), and **never invent rationale**. A naive documentation generator produces
a confident HOW and a hallucinated WHY; the hallucination is worse than an admitted
gap because it reads as authoritative and misleads the very newcomer the docs are for.

## When to apply

Apply when extracting facts (how-extractor, flow-tracer), when digging rationale
(rationale-archaeologist), and when writing any documentation prose (doc-author,
tutorial-author). The reviewer (consistency-reviewer) enforces it at the gate.

## The two categories

**HOW — extractable, verifiable, no human needed.** What the system does and how
to operate it: endpoints, config keys, migrations, build/run commands, the call
chain of a flow, the states of an entity. The source is the code. Every HOW fact
cites a `file:line` (or a canonical generated spec).

**WHY — elicitable, needs a source that records intent.** Why it was built this
way: why this timeout, why block instead of auto-resolve, why this term, why this
rule. The source is an ADR, a commit body, a tracker ticket, an intent-bearing
comment, or — for everything else — the owner, captured at the checkpoint as
`SOURCED: owner`.

## The rule

A WHY with no source is **not a WHY — it is a question.**

- If you can cite it (`ADR-0004`, `commit 1c39e32`, `WEGO-1683`, `owner`), write it.
- If you cannot, do **not** write a plausible reason. Either:
  - park it as an owner question (rationale-archaeologist → `open-questions.md`), or
  - in authored prose, flag `<!-- UNSOURCED: <the claim> — no source for the rationale -->`
    and, if useful, document the HOW while stating plainly that the rationale is
    undocumented.

## What "what" vs "why" looks like

- A commit "rename EQUIPE_CLINICA → PRESTADOR" tells you *what* changed. It does
  **not** tell you *why* that term was chosen. If the body doesn't say, the why is
  an open question — even though the change is well recorded.
- "Timeout is 10s (`FooClient.java:42`)" is HOW — cite the line. "10s because the
  upstream P99 is 8s" is WHY — needs a source, or it's a question.

## Why it matters

The reader can trace any claim to its origin, and sourced docs age gracefully —
when the code moves, a cited fact visibly goes stale instead of silently lying. A
fabricated rationale does the opposite: it's confidently wrong forever.
