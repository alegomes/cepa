---
name: design-craft
description: Apply real design judgment to any user-facing surface — visual hierarchy before decoration, consistency over novelty, every state designed, accessibility as a floor not a feature. Use when designing or critiquing a UI, specifying a component's look/behavior, or reviewing frontend work. Counters generic, AI-default aesthetics with deliberate, justified choices.
---

# Skill: design-craft

Good design is a sequence of deliberate decisions, each serving the user's
task. Most weak design — especially the generic, default-template look that
AI tends toward — comes from skipping that sequence: reaching for decoration
before hierarchy, novelty before consistency, the happy path before the full
state set. This skill is the order of operations and the floors you don't go
below.

## When to apply

- Designing a screen, component, or flow's visual treatment.
- Critiquing or reviewing a UI (design spec, prototype, or shipped frontend).
- Writing frontend code where you're making visual/interaction decisions.
- Any time you're tempted to "make it look nice" without saying *how* or *why*.

## The order of operations

Design in this order. Each step constrains the next; doing them out of order
produces the muddle that reads as "AI-generated."

1. **Hierarchy first.** Decide what the user should notice first, second,
   third — *before* any styling. Establish it with size, weight, contrast,
   and position. If everything is emphasized, nothing is.
2. **Spacing rhythm.** A consistent spacing scale (e.g. 4/8/16/24) does more
   for perceived quality than any color choice. Whitespace is structure, not
   leftover.
3. **Type scale.** A small set of type roles (display / heading / body /
   caption) mapped to real steps. Resist inventing a one-off size per element.
4. **Color with intent.** Color carries meaning — primary action, danger,
   muted/secondary. Decorative color that carries no meaning is noise. Default
   to the product's existing palette.
5. **Decoration last, and only if it earns its place.** Shadows, gradients,
   borders, icons — each must serve hierarchy or meaning, or it's cut.

## The floors you don't go below

- **Every state is designed.** Loading, empty, error, success, and the edge
  cases (no permission, partial data, offline). The empty state and the error
  state get the same care as the happy path. A design that only covers the
  happy path is unfinished.
- **Consistency over novelty.** Reuse the product's existing patterns, tokens,
  and components. A new pattern is a tax every future screen pays — only admit
  one when no existing pattern fits, and say why. Novelty for its own sake is a
  defect, not a flourish.
- **Accessibility is a floor, not a feature.** WCAG AA minimums on every state:
  contrast, keyboard reachability, focus order, screen-reader labels, target
  size, respect for reduced-motion. A beautiful screen a keyboard user can't
  operate is broken.
- **Specify, don't gesture.** "16px vertical rhythm; primary CTA at the highest
  contrast step; secondary actions de-emphasized" — not "make it pop" or "clean
  and modern." A decision you can't state precisely isn't a decision yet.

## The tell of generic design

If a design could be dropped into any product unchanged, it's not designed for
*this* one. Distinctiveness comes from serving this product's actual task and
matching its established language — not from a flashier template. When a choice
feels generic, ask: what does *this* user, doing *this* task, need to see
first? Design back from that answer.

## The goal

Every visual and interaction choice traces to a reason a user would recognize.
A reviewer should be able to ask "why is this here / this size / this color?"
about any element and get an answer better than "it looked nice."
