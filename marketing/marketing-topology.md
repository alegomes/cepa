# Marketing topology (brief → reviewed, grounded commercial prose)

You have access to a **marketing** topology: a content-lead plus 4 workers
that turn a raw content request into a **reviewed set of pieces** —
sales-enablement kits, ad copy, proposal sections — grounded in a shared,
sourced brief and gated on both brand/style and factual accuracy.

## When to use this topology

Use the marketing agents when:
- A content request needs commercial prose written (sales-enablement,
  marketing copy, proposals) and no build topology fits — this is prose
  production, not code.
- Multiple pieces need to be written from the same facts and stay
  numerically consistent with each other.
- The output has to clear a brand/style bar (banned terms, reserved
  terminology, anonymization, honest claims vs. roadmap) and a factual bar
  (every number traces to a declared source) before it ships.

Do **not** use it when:
- The task is documenting an existing system (`docs` — HOW from code, WHY
  from ADRs, not persuasive prose from an offer).
- The task is designing a UI or a user flow (`design`).
- It's a one-off opinion question or a short reply — just answer.

## Agent roster

| Agent | Phase | Does what | Model |
|---|---|---|---|
| `content-lead` | orchestrator | Routes across phases; synthesizes; never produces | opus |
| `content-strategist` | Strategize | Distills the brief — audience, offer, sourced canonical numbers, brand/style rules, piece list | sonnet |
| `copywriter` | Write | Writes one piece per invocation, parallelizable, write-locked per file, never invents a number | sonnet |
| `brand-style-critic` | Review (gate ∥) | Style prohibitions, reserved terminology, anonymization, honest claims → PASS/REVISE | sonnet |
| `fact-checker` | Review (gate ∥) | Every number/claim traces to a canonical-numbers row → PASS/REVISE | sonnet |

## Artifact layout

All marketing artifacts live under `docs/marketing/<slug>/`:

```
docs/marketing/
  brand-rules.yaml         # optional, project-level — see marketing/brand-rules.example.yaml
  <slug>/
    BRIEF.md                # content-strategist — audience, offer, canonical numbers, brand rules, piece list
    pecas/
      <piece-1>.md           # copywriter — one file per piece
      <piece-2>.md
      ...
  reviews/
    <slug>-brand.md          # brand-style-critic — verdict + located findings
    <slug>-facts.md          # fact-checker — verdict + located findings
```

The path-lock enforces `docs/marketing/**` — marketing agents cannot write
code, only artifacts. `content-strategist` is the only agent allowed to
write `BRIEF.md`; `copywriter` reads it read-only. The two critics write only
to `docs/marketing/reviews/**`.

## The content loop

```
Brief → Strategize → Write (copywriters ∥, one per piece)
                        ↓
                     Review (brand-style-critic ∥ fact-checker) ⇄ Write
                        ↓
                    Delivered
```

Write fans out in parallel, one copywriter invocation per piece. Review runs
both gates in parallel over the same pieces. A REVISE from either gate loops
back to Write (or to `content-strategist`, if the finding is a genuinely
missing brief row) — capped at 2 revise rounds, after which the loop stops
BLOCKED with the disagreement named rather than spinning silently.

## Entry points

- **Linear (bounded content request):** `/marketing:brief-write-review
  <request>` runs the whole loop in sequence: brief → write → review ⇄ write
  → delivery report. Use for a well-scoped request you want produced
  end-to-end in one go.
- **Per-column (board-driven / continuous):** delegate to `content-lead`
  directly, or — with `board-flow` installed — use `/board-flow:advance
  <card>` to step a content card forward one column at a time, the same
  seam `design` uses today. Declare the columns in the host project's
  `board-flow.yaml` (or `.claude/board-flow.lifecycle.yaml`) with each
  column's `on_enter` agent — `/board-flow:advance` reads it generically.
  This ships no new board-flow code; it composes with what `board-flow`
  already provides.

## Decisões

Answers to the three open design questions the backlog item raised
(`cepa/topologia-marketing`), applied in this implementation:

1. **Gate configurável por projeto?** Sim. `docs/marketing/brand-rules.yaml`
   é opcional, no nível do projeto (proibições de estilo, termos
   reservados, lista de anonimização, regras de claims honestos). O
   `brand-style-critic` o lê; se ausente, aplica só as regras universais e
   **diz isso no relatório** ("no brand-rules file found: universal rules
   only"), em vez de aplicar silenciosamente um subconjunto menor. Um
   exemplo comentado vem em `marketing/brand-rules.example.yaml`.
2. **Integra com board-flow?** Do mesmo jeito que `design` já faz hoje:
   `content-lead` pode ser dirigido coluna a coluna via
   `/board-flow:advance`, desde que o projeto declare as colunas em
   `board-flow.yaml`. Nenhum código novo de `board-flow` foi escrito: a
   composição é a mesma que já existe para `design` e `discovery`.
   O quadro é **opcional**: sem `board-flow.yaml` (ou sem Jira), o
   `/marketing:brief-write-review` roda o fluxo inteiro com artefatos locais
   em `docs/marketing/`. Confirmado pelo dono em 2026-09-27.
3. **Fonte de fato versionada sem drift?** `BRIEF.md` é versionado no
   próprio repositório do projeto (`docs/marketing/<slug>/BRIEF.md`), e a
   tabela de números canônicos é a única fonte de verdade para figuras.
   `copywriter` nunca edita essa tabela, só lê. Uma mudança de número volta
   por `content-strategist`, que atualiza `BRIEF.md` e registra o que
   mudou. `fact-checker` confere sempre contra a versão do brief **corrente
   no momento da revisão**, não uma cópia congelada: é por isso que o
   número mora só no brief e nunca é copiado para dentro de uma peça como
   valor independente.

## Composition

- `marketing` alone → produces content artifacts as local artifacts under
  `docs/marketing/`.
- `discovery → marketing` → discovery validates the opportunity and hands
  off enough context to brief a content request from it (the brief is the
  crossing artifact, same shape as `discovery → design`).
- `marketing + board-flow` → the per-column lifecycle runs against a content
  board.

## Boundary with other topologies

- **`docs`** documents an existing system — HOW from code, WHY from a
  source of record. `marketing` starts from an offer and a set of sourced
  facts to produce *persuasive* prose. Same loop shape (lead → workers →
  critic), different purpose and different gates.
- **`design`** designs the UI/UX. `marketing` produces text/commercial
  content. Neither writes the other's artifact type.

## Constraints

- Marketing agents do not write code. The path-lock enforces
  `docs/marketing/**`.
- `content-strategist` is the only agent that writes `BRIEF.md`. A
  copywriter that needs a number the brief lacks routes back through
  `content-lead` to `content-strategist` — it never estimates one.
- Both `brand-style-critic` and `fact-checker` are adversarial and never
  self-certify — they review, they do not rewrite. Their verdicts are
  independent; both must PASS before a piece is Delivered.
- The revise loop is capped at 2 rounds. A third round doesn't happen
  silently — the loop reports BLOCKED with the specific disagreement named.

## Per-project customization

The workers write to `docs/marketing/**`. If your project keeps a
brand-rules file somewhere non-obvious, name that path in your delegation
prompt so `brand-style-critic` reconciles against the right source — though
the default `docs/marketing/brand-rules.yaml` location is what it checks
without being told otherwise. To change a worker's domain, override it
locally in `.claude/agents/<name>.md` — project-local files win over
plugin-shipped ones.
