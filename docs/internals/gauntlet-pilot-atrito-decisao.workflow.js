export const meta = {
  name: 'gauntlet-pilot-atrito-decisao',
  description: 'Piloto Gauntlet Loop nº2: 3 designs concorrentes para o item "Atrito de decisão" do BACKLOG (harness pergunta demais e cedo demais), julgados às cegas contra barra pré-declarada',
  phases: [
    { title: 'Barra', detail: 'critérios concretos escritos ANTES de qualquer builder' },
    { title: 'Builders', detail: '3 designs independentes, ângulos distintos, isolados' },
    { title: 'Julgamento', detail: '3 juízes cegos: só objetivo + barra + artefatos' },
    { title: 'Revisão', detail: 'vencedor revisado contra os gaps + checagem final' },
  ],
}

const REPO = '/Users/alegomes/Insync/alegomes@gmail.com/GoogleDrive/2026/coding/cepa'

const CONTEXT = `
CONTEXT — the problem: the cepa harness (a Claude Code plugin marketplace at ${REPO}) interrupts its owner too often and too early with questions. In a real triage/drain session (2026-08-03 to 08-10 on the WEGO Jira board) the owner was interrupted ~20 times. Post-classification: 5 were genuinely his (product decisions, attestations about things outside the code, prioritization); ~10 were reversible mechanics he merely rubber-stamped (run build, create debt card, push/merge, delete orphan branches already contained in main — every one had "Recomendo sim" and every answer was "sim"); ~4 were harness defects disguised as owner tasks; 1 was asked TOO EARLY and cost a reversal (agent asked whether to close Epic WEGO-1406 seeing 15 cards; auditing AFTER the "yes" revealed 41 children, 22 open, 10 undelivered).

The owner's literal request: "Eu só quero que as tarefas fluam pelo quadro, com o menor atrito possível. Toda vez que você aponta alguma pendência em um card eu tenho que parar tudo, abrir o card, interpretá-lo, verificar o código e tomar a decisão."

READ the full backlog item before designing — it is the section titled "## Atrito de decisão — o harness pergunta demais, e pergunta cedo demais" in ${REPO}/BACKLOG.md (roughly lines 788-927). It sketches 5 parts: (1) autonomy bands by reversibility (execute-and-report vs always-ask), (2) hard rule audit-before-ask (never ask about a card with children without enumerating them first), (3) attestation registry (owner statements like "this is concluded" become dated, scoped facts in a durable file, e.g. .claude/attestations.yaml — a real contradiction in 08-03/08-04 cost a rework), (4) one closed question per sub-task when an Epic is undecidable, with detail exactly where the decision depends on it (the WEGO-1437 example in the item shows the exact desired form), (5) harness defects get their own queue (this BACKLOG) instead of interrupting product work.

What already exists and must be built upon, not duplicated: board-flow:decide (${REPO}/board-flow/commands/decide.md) already groups the Review column by reason and asks one closed question per group, answered in batch; the plain-report skill (${REPO}/common/skills/plain-report/SKILL.md) already mandates numbered closed questions with "Recomendo sim/não"; docs/needs-human-motivos.md taxonomizes NEEDS-HUMAN reasons; the debrief command has an altitude taxonomy (strategic vs tactical). The three sub-items marked as harness state: sub-item 5 partially exists as discipline, nothing enforced.

Harness design philosophy (relevant): enforcement in depth — prose rules decay, mechanical gates (hooks, versioned config) endure; independent gates over executor self-report; every rule that only lives in a prompt has already been observed to decay across sessions; the owner dislikes coupling and likes diagnose-before-patch; hooks are small tested Python scripts; changes land in versioned config, not chat.

The design goal: reduce ~20 interruptions/session to the ~5 that are genuinely the owner's, WITHOUT the agent silently doing irreversible things, and WITHOUT the asked-too-early failure mode. A design is judged on mechanism, not intention.
`

const BAR_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['criteria', 'reference_bar'],
  properties: {
    criteria: { type: 'array', minItems: 5, maxItems: 8, items: {
      type: 'object', additionalProperties: false,
      required: ['id', 'text', 'how_to_judge'],
      properties: {
        id: { type: 'string' },
        text: { type: 'string' },
        how_to_judge: { type: 'string', description: 'how a blind critic scores this 0-10 from the design text alone' },
      },
    }},
    reference_bar: { type: 'string', description: 'ambitious, possibly unreachable ideal — gives direction' },
  },
}

const DESIGN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['title', 'mechanism', 'surfaces', 'worst_case_handling', 'failure_modes', 'test_plan', 'cost'],
  properties: {
    title: { type: 'string' },
    mechanism: { type: 'string', description: 'full design: what changes, how it works, why this over alternatives. Cite real files/lines you read.' },
    surfaces: { type: 'array', items: { type: 'string' } },
    worst_case_handling: { type: 'string', description: 'how the design handles: (a) the asked-too-early Epic case, (b) an irreversible action the agent wrongly classifies as reversible, (c) an attestation that later contradicts reality' },
    failure_modes: { type: 'string', description: 'how this design itself decays, gets bypassed, or misfires — honestly' },
    test_plan: { type: 'string' },
    cost: { type: 'string', description: 'build effort + how much residual friction remains for the owner' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ranking', 'scores', 'biggest_gaps'],
  properties: {
    ranking: { type: 'array', items: { type: 'string' } },
    scores: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['label', 'per_criterion', 'total', 'note'],
      properties: {
        label: { type: 'string' },
        per_criterion: { type: 'array', items: {
          type: 'object', additionalProperties: false,
          required: ['id', 'score'],
          properties: { id: { type: 'string' }, score: { type: 'number' }, note: { type: 'string' } },
        }},
        total: { type: 'number' },
        note: { type: 'string' },
      },
    }},
    biggest_gaps: { type: 'array', items: {
      type: 'object', additionalProperties: false,
      required: ['label', 'gap'],
      properties: { label: { type: 'string' }, gap: { type: 'string' } },
    }},
  },
}

const FINAL_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['bar_met', 'remaining_gaps', 'verdict_note'],
  properties: {
    bar_met: { type: 'boolean' },
    remaining_gaps: { type: 'array', items: { type: 'string' } },
    verdict_note: { type: 'string' },
  },
}

phase('Barra')
log('Escrevendo a barra de qualidade antes de qualquer builder')
const bar = await agent(`${CONTEXT}

You are the GAUNTLET BAR-SETTER. Write the concrete quality bar that blind critics will use to judge competing designs. Do NOT design the solution yourself.

First READ, to ground the bar in reality:
- the "Atrito de decisão" section of ${REPO}/BACKLOG.md
- ${REPO}/board-flow/commands/decide.md (the existing piece with the desired form)
- ${REPO}/common/skills/plain-report/SKILL.md
- skim ${REPO}/common/commands/debrief.md for the decision-altitude taxonomy

Produce 5-8 concrete, independently judgeable criteria covering at least: (a) does the mechanism actually convert rubber-stamp questions into report lines while keeping irreversible actions gated — and is the reversible/irreversible boundary DECLARED in versioned config rather than per-turn agent judgment; (b) does audit-before-ask become mechanical (the Epic case cannot recur); (c) do attestations become durable, dated, scoped facts with a defined consumer and a defined conflict behavior; (d) does the per-sub-task closed-question form match what the owner specified (detail exactly where the decision depends on it); (e) enforcement depth — which parts are hooks/config (endure) vs prose (decay), honestly labeled; (f) fit with existing pieces (decide, plain-report, needs-human-motivos) without duplication; (g) build cost + residual friction estimate. Each criterion gets a how_to_judge rubric applicable to design TEXT.

reference_bar: describe the ideal end state (possibly unreachable) — e.g. a session where the owner is consulted exactly once per round, in batch, every question closed and pre-audited, everything else flowing as information.`,
  { label: 'bar-setter', phase: 'Barra', schema: BAR_SCHEMA })

const barText = JSON.stringify(bar, null, 2)

const ANGLES = [
  { key: 'config-first', brief: 'Your angle: MECHANISM/CONFIG. The autonomy bands live in versioned config (per-repo and/or per-user), and enforcement is mechanical wherever possible: hooks or command preambles that consult the config before asking, an attestation file with schema and consumers, a lint/gate that blocks a question lacking its audit. Design the config schema concretely.' },
  { key: 'workflow-first', brief: 'Your angle: EXTEND WHAT EXISTS. Minimal new machinery: generalize board-flow:decide into the universal question-funnel (all questions batch through it), extend plain-report rules, put audit-before-ask into the commands that ask (triage/decide/execute), attestations as a lightweight convention. Optimize for shipping in one session and for not creating new surfaces that drift.' },
  { key: 'unconstrained', brief: 'Your angle: FREE. Ignore the sketched 5 parts if you have something better. Consider: a decision-queue file the agent appends to and the owner drains once per round; AskUserQuestion batching policies; risk-scoring actions instead of a binary reversible/irreversible; learning from the answer history (every "sim" to a Recomendo-sim is training data that the question was unnecessary — telemetry exists at ~/.claude/cepa-telemetry); or something else entirely. Novelty counts only if buildable in this harness.' },
]

phase('Builders')
log('3 builders em paralelo, isolados entre si')
const rawDesigns = await parallel(ANGLES.map(a => () => agent(`${CONTEXT}

You are a GAUNTLET BUILDER competing blindly against other builders you cannot see. Produce the best complete DESIGN (not code) for the decision-friction problem. A blind critic will judge your design text against this pre-declared quality bar — optimize for it:

${barText}

${a.brief}

Ground the design in the real repo: READ the "Atrito de decisão" section of ${REPO}/BACKLOG.md, ${REPO}/board-flow/commands/decide.md, ${REPO}/common/skills/plain-report/SKILL.md, and whatever else you need (hooks in ${REPO}/common/hooks/, ${REPO}/common/commands/debrief.md). Cite actual files/lines. Be honest in failure_modes — one criterion is enforcement honesty, and critics reward honesty over bluster.`,
  { label: `builder:${a.key}`, phase: 'Builders', schema: DESIGN_SCHEMA })))

const designs = rawDesigns.map((d, i) => ({ label: 'ABC'[i], angle: ANGLES[i].key, design: d })).filter(x => x.design)
if (designs.length < 2) { return { error: 'menos de 2 designs sobreviveram — gauntlet sem competição', designs } }

const renderDesign = x => `=== DESIGN ${x.label} ===\n${JSON.stringify(x.design, null, 2)}`

phase('Julgamento')
log(`${designs.length} designs anonimizados indo a 3 juízes cegos`)
const verdicts = (await parallel([0, 1, 2].map(j => () => {
  const order = designs.map((_, i) => designs[(i + j) % designs.length])
  return agent(`${CONTEXT}

You are a GAUNTLET CRITIC. You receive ONLY: the goal above, the quality bar below, and the anonymized design artifacts. You know nothing about who produced each design and must not guess. Judge the TEXT against the BAR, criterion by criterion, harshly and independently. The reference_bar is the direction; reasonable is not the target. Tiebreaker: enforcement honesty (prose-vs-mechanism labeling) and fit with the harness philosophy. You may verify a design's claims about the repo by reading the cited files — miscitation loses points.

QUALITY BAR:
${barText}

DESIGNS:
${order.map(renderDesign).join('\n\n')}

Score every design on every criterion (0-10), rank best-first, and for each design name its single biggest gap versus the bar.`,
    { label: `judge-${j + 1}`, phase: 'Julgamento', schema: VERDICT_SCHEMA })
}))).filter(Boolean)

if (!verdicts.length) { return { error: 'nenhum juiz retornou veredito', designs } }

const points = {}
for (const v of verdicts) v.ranking.forEach((label, idx) => { points[label] = (points[label] || 0) + (designs.length - idx) })
const winnerLabel = Object.entries(points).sort((a, b) => b[1] - a[1])[0][0]
const winner = designs.find(d => d.label === winnerLabel) || designs[0]
const winnerGaps = verdicts.flatMap(v => v.biggest_gaps.filter(g => g.label === winner.label).map(g => g.gap))
const runnerUps = designs.filter(d => d.label !== winner.label)
log(`Vencedor da rodada: DESIGN ${winner.label} (${winner.angle}) — pontos Borda: ${JSON.stringify(points)}`)

phase('Revisão')
const revised = await agent(`${CONTEXT}

You are the GAUNTLET REVISER. The design below won a blind judging round against ${runnerUps.length} rival(s), but the critics named gaps. Produce the REVISED design: keep the winning mechanism, close every gap, and graft in any clearly superior rival idea (credit the rival label). Stay honest in failure_modes.

QUALITY BAR:
${barText}

WINNING DESIGN (${winner.label}):
${JSON.stringify(winner.design, null, 2)}

CRITICS' BIGGEST GAPS ON THE WINNER:
${winnerGaps.map((g, i) => `${i + 1}. ${g}`).join('\n')}

RIVAL DESIGNS:
${runnerUps.map(renderDesign).join('\n\n')}`,
  { label: 'reviser', phase: 'Revisão', schema: DESIGN_SCHEMA })

const finalCheck = revised ? await agent(`${CONTEXT}

You are the FINAL GAUNTLET CRITIC, fresh context. Judge strictly whether the revised design meets the bar (every criterion >= 7/10). List remaining gaps. Verify cited repo files where relevant.

QUALITY BAR:
${barText}

REVISED DESIGN:
${JSON.stringify(revised, null, 2)}`,
  { label: 'final-check', phase: 'Revisão', schema: FINAL_SCHEMA }) : null

return {
  bar,
  designs: designs.map(d => ({ label: d.label, angle: d.angle, title: d.design.title })),
  full_designs: designs,
  verdicts,
  borda_points: points,
  winner: { label: winner.label, angle: winner.angle },
  revised_design: revised,
  final_check: finalCheck,
}