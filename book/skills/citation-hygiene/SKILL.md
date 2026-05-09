# citation-hygiene

Ensure every non-obvious factual claim in research notes and chapter drafts traces to a verifiable source.

## When to apply

Apply when producing research notes (researcher) and when reviewing chapter drafts for accuracy (technical-reviewer).

## What needs a citation

**Always cite:**
- Quantitative claims ("GPT-4 achieves X% on benchmark Y")
- Capability comparisons ("model A outperforms model B at task C")
- Dates and version facts ("introduced in 2023 with version X")
- Design decisions attributed to a system or team ("OpenAI chose X because...")
- Claims about what the field has or hasn't solved

**Never cite:**
- Well-established fundamentals that any practitioner knows (e.g., "transformers use attention mechanisms")
- Definitions of widely-understood terms
- The author's own analysis or opinion (clearly marked as such)

## Citation format

Inline in prose: `[Author Year]` for academic sources, or a Markdown link `[description](URL)` for web sources.

In `references.md`: full entry per citation.

## When a source can't be found

Do NOT invent a citation. Instead:
- In research notes: `<!-- UNSOURCED: <the claim> -->`
- In draft prose: `<!-- UNSOURCED: <the claim> — researcher could not find a source -->`

These flags are for the author to resolve: they may know the source, may choose to rephrase as the author's opinion, or may cut the claim.

## Contradicting sources

If two credible sources disagree on a claim: note both in research.md with `<!-- CONFLICT: source A says X, source B says Y -->`. Don't pick a winner — let the author decide.

## The goal

A reader should be able to trace any factual claim back to its source. In a fast-moving field like AI/LLM engineering, sourced claims also age more gracefully — readers can check whether the source has been superseded.
