# diataxis-discipline

Keep each document in **one** of the four Diátaxis modes. The documentation chaos
this topology fixes comes from two things: mixing the four modes inside one
document, and blurring the line between documentation and the by-products of
producing it. This skill is the antidote to the first; `how-why-boundary` and the
declutter phase handle the second.

## When to apply

Apply when classifying existing docs (diataxis-inventory), when deciding where a
new doc goes and how to write it (doc-author, tutorial-author), and when reviewing
the tree for shelf violations (consistency-reviewer).

## The four modes

| Mode | Orientation | Answers | Reader is… | Shape |
|---|---|---|---|---|
| **Tutorial** | learning | "teach me by doing" | a newcomer, knows nothing | one happy path to a first win |
| **How-to** | task | "how do I X?" | knows what they want | a recipe, imperative steps |
| **Reference** | information | "what exactly is X?" | needs a precise fact | dry, complete, lookup-shaped |
| **Explanation** | understanding | "why is it like this?" | wants the mental model | discursive, rationale, context |

## The discipline

- **One mode per document.** A how-to padded with three paragraphs of rationale is
  two documents wearing one filename — split the rationale into `explanation/`. A
  reference page that editorializes has drifted off its shelf.
- **Tutorial ≠ how-to.** A tutorial is a *learning* path with a single track that
  always works and ends in a visible success. A how-to is a *task* recipe for
  someone who already knows the goal and can handle branches. Don't write a
  "tutorial" that's really a how-to with prerequisites assumed.
- **Reference is generated-truth-shaped.** Prefer carrying citations from the HOW
  ledger so facts stay verifiable. Don't narrate in reference; don't tabulate in
  explanation.
- **Explanation is where the WHY lives** — and every WHY there obeys
  `how-why-boundary` (sourced or flagged, never invented).

## The single front door

One entry point (`docs/README.md`) routes to the shelves. Other "start here" files
(a rival README, an AGENTS.md) become links, not parallel copies — divergent front
doors are how drift starts.

## The test

For any document, ask: *what is the reader trying to do right now?* Learn → tutorial.
Accomplish a task → how-to. Look something up → reference. Understand why → explanation.
If the answer is "two of these", the document is two documents.
