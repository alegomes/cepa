---
description: Start a new book project — profile the target audience by interviewing the author, then design the full chapter map. Produces manuscript/audience.md and manuscript/BOOK.md. Run once per book.
argument-hint: "<book title or brief vision>"
---

# /book:inception

## Purpose

Bootstrap a new book project. Two outputs:
- `manuscript/audience.md` — who the reader is, what they know, what they should be able to do
- `manuscript/BOOK.md` — the full chapter map with learning arc, objectives, and dependencies

Run this once. Every subsequent `/book:write-chapter` call reads these files.

## Variables

- `$ARGUMENTS` — the book's working title or a one-line vision statement.

## Workflow

### 1. Interview the author

Before delegating anything, ask the author these questions directly. Wait for answers before proceeding.

---

I need to understand your intended reader before we design the book structure. Please answer these:

1. **Who is your reader?** (e.g., "a mid-senior software engineer who has shipped production code but has no ML background" or "a data scientist comfortable with Python and statistics who wants to move into LLM engineering")

2. **What do they already know?** List 3–5 things they can be assumed to know coming in.

3. **What should they be able to DO after finishing the book?** (Be specific — not "understand AI" but "build a RAG pipeline", "evaluate model fine-tuning trade-offs", "design an agent orchestration system")

4. **What's the tone?** Tutorial-heavy with lots of code? Conceptual with applied examples? Reference-style? Something else?

5. **Are there topics you want to explicitly exclude?** (e.g., "no hardware/GPU setup", "no math derivations", "no cloud-specific content")

---

### 2. Delegate inception to book-architect

Once the author has answered, delegate to `book-architect`:

> The author is writing: **$ARGUMENTS**
>
> Author's answers to the audience interview:
> 1. Reader: <answer>
> 2. Prior knowledge: <answer>
> 3. Outcomes: <answer>
> 4. Tone: <answer>
> 5. Exclusions: <answer>
>
> Produce:
> - `manuscript/audience.md` — structured audience profile (via audience-profiler)
> - `manuscript/BOOK.md` — full chapter map with learning arc, per-chapter objectives, prerequisites, depth, and code/exercise flags
>
> Reply with both file paths and a summary of the chapter list.

### 3. Show structure to author

Display the chapter list from BOOK.md to the author. Ask:

> Here's the proposed book structure. Review it and tell me:
> - Any chapters to add, remove, or reorder?
> - Any scope concerns (too broad, too narrow)?
> - Any chapter where the depth (introductory / intermediate / advanced) feels off?

### 4. (Conditional) Revise

If the author requests changes, delegate back to `book-architect`:

> The author reviewed the proposed structure and requests these changes: <author's feedback>.
> Update `manuscript/BOOK.md` accordingly.

Repeat until the author approves.

### 5. Report

Once approved:

- **Book:** $ARGUMENTS
- **Audience profile:** `manuscript/audience.md`
- **Chapter map:** `manuscript/BOOK.md` — N chapters
- **Next step:** Run `/book:write-chapter <slug>` for any chapter in the list.

## Constraints

- Don't skip the author interview. A chapter map built without a clear audience profile will produce mis-calibrated content.
- `manuscript/` directory must exist before book-architect writes. Create it if absent.
- Don't start writing chapters during inception. The map comes first.
