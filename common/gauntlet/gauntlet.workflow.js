// Script canônico do /common:gauntlet — cópia consolidada dos dois pilotos
// (docs/internals/gauntlet-pilot-*.workflow.js). NÃO reescreva por invocação:
// tudo que varia vem de `args` = {repo, goal, context, angles:[{key,brief}], reads:[paths]}.
//
// A Workflow tool entrega o input no global `args` — e pode entregá-lo como
// STRING JSON. A guarda abaixo é obrigatória.
//
// O `return` no topo é válido no dialeto da Workflow tool (o corpo roda em
// contexto async); um `node --check` acusa "Illegal return statement" e isso
// NÃO é um erro real.

export const meta = {
  name: 'gauntlet',
  description: 'Gauntlet Loop: barra de qualidade pré-declarada, N designs concorrentes isolados, 3 juízes cegos com contagem de Borda, revisão do vencedor e checagem final',
  phases: [
    { title: 'Barra', detail: 'critérios concretos escritos ANTES de qualquer builder' },
    { title: 'Builders', detail: 'N designs independentes, ângulos distintos, isolados' },
    { title: 'Julgamento', detail: '3 juízes cegos: só objetivo + barra + artefatos' },
    { title: 'Revisão', detail: 'vencedor revisado contra os gaps + checagem final' },
  ],
}

const A = typeof args === "string" ? JSON.parse(args) : args

const REPO = A.repo
const ANGLES = A.angles
const READS = A.reads || []
const CONTEXT = `
GOAL:
${A.goal}

CONTEXT:
${A.context}
`
const readsList = READS.length ? READS.map(p => `- ${p}`).join('\n') : '- (no files named; explore the repo at ' + REPO + ' as needed)'

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
    worst_case_handling: { type: 'string', description: 'how the design handles the hardest cases named in the goal, the context and the bar (real incidents first, then the plausible misclassification or misuse)' },
    failure_modes: { type: 'string', description: 'how this design itself decays, gets bypassed, or misfires — honestly' },
    test_plan: { type: 'string' },
    cost: { type: 'string', description: 'build effort + residual cost or friction that remains' },
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

First READ, to ground the bar in reality (repo at ${REPO}):
${readsList}

Produce 5-8 concrete, independently judgeable criteria. Cover at least: (a) does the mechanism actually solve the problem stated in the goal, judged on mechanism and not on intention; (b) does it handle the real incidents and worst cases named in the context; (c) enforcement depth: which parts are mechanical (hooks, versioned config, tests) vs prose, honestly labeled; (d) fit with what already exists, extending it instead of duplicating it; (e) build cost and residual cost, with the calculation shown. Add criteria specific to this goal. Each criterion gets a how_to_judge rubric applicable to design TEXT.

reference_bar: describe the ideal end state (possibly unreachable) so the builders have a direction.`,
  { label: 'bar-setter', phase: 'Barra', schema: BAR_SCHEMA })

const barText = JSON.stringify(bar, null, 2)

phase('Builders')
log(`${ANGLES.length} builders em paralelo, isolados entre si`)
const rawDesigns = await parallel(ANGLES.map((a, i) => () => agent(`${CONTEXT}

You are a GAUNTLET BUILDER competing blindly against other builders you cannot see. Produce the best complete DESIGN (not code) for the goal above. A blind critic will judge your design text against this pre-declared quality bar — optimize for it:

${barText}

${a.brief}

Ground the design in the real repo (${REPO}): READ these first, plus whatever else you need:
${readsList}
Cite actual files/lines. Be honest in failure_modes — critics reward honesty over bluster.`,
  { label: ANGLES.filter(x => x.key === a.key).length > 1 ? `builder:${a.key}:${i + 1}` : `builder:${a.key}`, phase: 'Builders', schema: DESIGN_SCHEMA })))

const designs = rawDesigns.map((d, i) => ({ label: 'ABCDEFGHIJ'[i], angle: ANGLES[i].key, design: d })).filter(x => x.design)
if (designs.length < 2) { return { error: 'menos de 2 designs sobreviveram — gauntlet sem competição', designs } }

const renderDesign = x => `=== DESIGN ${x.label} ===\n${JSON.stringify(x.design, null, 2)}`

phase('Julgamento')
log(`${designs.length} designs anonimizados indo a 3 juízes cegos`)
const verdicts = (await parallel([0, 1, 2].map(j => () => {
  const order = designs.map((_, i) => designs[(i + j) % designs.length])
  return agent(`${CONTEXT}

You are a GAUNTLET CRITIC. You receive ONLY: the goal above, the quality bar below, and the anonymized design artifacts. You know nothing about who produced each design and must not guess. Judge the TEXT against the BAR, criterion by criterion, harshly and independently. The reference_bar is the direction; reasonable is not the target. Tiebreaker: enforcement honesty (prose-vs-mechanism labeling) and fit with the harness philosophy stated in the context. You may verify a design's claims about the repo by reading the cited files — miscitation loses points.

QUALITY BAR:
${barText}

DESIGNS:
${order.map(renderDesign).join('\n\n')}

Score every design on every criterion (0-10), rank best-first using the design labels (A, B, ...), and for each design name its single biggest gap versus the bar.`,
    { label: `judge-${j + 1}`, phase: 'Julgamento', schema: VERDICT_SCHEMA })
}))).filter(Boolean)

if (!verdicts.length) { return { error: 'nenhum juiz retornou veredito', designs } }

const points = {}
const firsts = {}
const known = new Set(designs.map(d => d.label))
verdicts.forEach((v, j) => {
  const valid = v.ranking.filter(label => {
    if (!known.has(label)) { log(`AVISO: juiz ${j + 1} ranqueou o rótulo desconhecido "${label}" — ignorado na contagem de Borda`); return false }
    return true
  })
  v.ranking.forEach((label, idx) => {
    if (!known.has(label)) return
    points[label] = (points[label] || 0) + (designs.length - idx)
  })
  if (valid.length && v.ranking[0] === valid[0]) firsts[valid[0]] = (firsts[valid[0]] || 0) + 1
})
// Borda; empate -> mais 1º lugares; persistindo, o primeiro na ordem dos designs.
const pos = l => designs.findIndex(d => d.label === l)
const ordered = Object.entries(points).sort((a, b) =>
  (b[1] - a[1]) || ((firsts[b[0]] || 0) - (firsts[a[0]] || 0)) || (pos(a[0]) - pos(b[0])))
const winnerLabel = ordered[0][0]
const tied = ordered.filter(e => e[1] === ordered[0][1]).map(e => e[0])
const winner = designs.find(d => d.label === winnerLabel) || designs[0]
const winnerGaps = verdicts.flatMap(v => v.biggest_gaps.filter(g => g.label === winner.label).map(g => g.gap))
const runnerUps = designs.filter(d => d.label !== winner.label)
log(`Vencedor da rodada: DESIGN ${winner.label} (${winner.angle}) — pontos Borda: ${JSON.stringify(points)}${tied.length > 1 ? ` — empate em pontos entre ${tied.join(', ')}` : ''}`)

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
