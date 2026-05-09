# audience-calibration

Check whether a passage's depth and assumed prior knowledge match the target reader profile in `manuscript/audience.md`.

## When to apply

Apply this skill whenever writing or reviewing chapter content — before submitting a draft (technical-writer), during technical review (technical-reviewer), and during copy edit (copy-editor).

## How to apply

1. Read `manuscript/audience.md`. Note: prior knowledge assumed, depth/tone calibration, what the reader should be able to do.

2. For each section or passage being evaluated, ask:
   - **Too shallow:** Is the explanation so basic that it condescends to a reader with the listed prior knowledge? Signs: defining terms the reader clearly knows, over-explaining obvious steps, no nuance.
   - **Too dense:** Does the passage assume knowledge NOT in the prior-knowledge list? Signs: unexplained jargon, skipped logical steps, references to concepts not introduced earlier in the book.
   - **Misaligned tone:** Does the passage feel like a research paper when the audience profile says tutorial-heavy, or vice versa?

3. Flag findings inline with HTML comments:
   - `<!-- SHALLOW: <brief note on what's too basic> -->`
   - `<!-- DENSE: <brief note on assumed knowledge gap> -->`
   - `<!-- TONE: <brief note on tone mismatch> -->`

4. In your review output, list flagged passages under an "Audience calibration check" heading.

## The goal

Every reader in the target profile should feel the book was written for them: not talked down to, not left behind.
