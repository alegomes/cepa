export const meta = {
  name: 'gauntlet-pilot-bashpathlock',
  description: 'Piloto Gauntlet Loop: 3 designs concorrentes para o furo interpreter-bypass do bash-path-lock, julgados às cegas contra barra pré-declarada',
  phases: [
    { title: 'Barra', detail: 'critérios de qualidade concretos, escritos ANTES de qualquer builder' },
    { title: 'Builders', detail: '3 designs independentes, ângulos distintos, isolados entre si' },
    { title: 'Julgamento', detail: '3 juízes cegos: só objetivo + barra + artefatos' },
    { title: 'Revisão', detail: 'vencedor revisado contra os gaps apontados + checagem final' },
  ],
}

const REPO = '/Users/alegomes/Insync/alegomes@gmail.com/GoogleDrive/2026/coding/cepa'

const CONTEXT = `
CONTEXT — the problem (from BACKLOG.md, item "O bash-path-lock bloqueia cp, mas deixa passar a mesma escrita via python3 -c", found 2026-08-13):

The cepa harness (a Claude Code plugin marketplace at ${REPO}) ships a PreToolUse hook "bash-path-lock" (copies in build-hex/hooks/bash-path-lock.py and 4 sibling topologies, alongside path-lock.py which guards Write/Edit). It blocks Bash commands that write outside an agent's allowed globs, by pattern-matching known write utilities (cp, mv, tee, redirection). During a real card (WEGO-1936), the qa-engineer agent needed to temporarily revert a src/main file to prove a test goes RED — a legitimate perturbation. The hook blocked his "cp". He then did THE SAME WRITE to THE SAME PATH via python3 -c "open(p,'w').write(...)" — and it passed. Any inline interpreter (python3 -c, perl -e, node -e, heredoc to sh) is arbitrary write that doesn't look like write.

Why it matters: the path-lock exists to FORCE DELEGATION between agents (QA hands findings to the dev worker, never writes production code), not to prevent damage. A lock bypassable with one line of Python forces nothing — it only filters out the agents who didn't think of the bypass. And the failure is silent: reports read "hook blocked me, I found another way" as cleverness, not violation.

Constraint that must survive: legitimate perturbations (like the RED proof above) must remain possible — the harness's proof-reviewer deliberately perturbs code in throwaway worktrees.

Three sketched directions in the backlog (you may adopt, combine, or reject them):
1. Deny-by-default: interpreter with inline code (-c/-e) becomes blocked for path-locked agents; real needs request explicit exception. Simple, probably annoying in legit cases.
2. Treat path-lock as a convention and move the guarantee to where it's verifiable: code-reviewer compares the final diff against the globs of who claimed to write what. Detects rather than prevents — detects the case that matters.
3. Accept the hole and document it. Honest, but a knowingly-fake lock corrodes trust in the other hooks.

The harness's design philosophy (relevant): independent gates verify work instead of trusting executor self-report; enforcement in depth (multiple layers); hooks are small Python scripts with pytest-style tests in tests/; every fix lands in ALL 5 hook-bearing topology copies; compile-fail preferred over runtime-bridge; the owner values diagnose-before-patch and dislikes coupling.
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
        text: { type: 'string', description: 'concrete, judgeable criterion' },
        how_to_judge: { type: 'string', description: 'how a blind critic scores this 0-10 from the design text alone' },
      },
    }},
    reference_bar: { type: 'string', description: 'an AMBITIOUS reference description — need not be reachable; gives direction' },
  },
}

const DESIGN_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['title', 'mechanism', 'surfaces', 'legit_case_handling', 'failure_modes', 'test_plan', 'cost'],
  properties: {
    title: { type: 'string' },
    mechanism: { type: 'string', description: 'full design: what changes, how it works, why this over alternatives. Cite real files/lines you read.' },
    surfaces: { type: 'array', items: { type: 'string' }, description: 'files/prompts/hooks touched' },
    legit_case_handling: { type: 'string', description: 'exactly how the legitimate RED-perturbation case still works' },
    failure_modes: { type: 'string', description: 'how this design itself can be bypassed or misfire, honestly' },
    test_plan: { type: 'string', description: 'acceptance: which tests, which cases, RED/GREEN expectations' },
    cost: { type: 'string', description: 'build effort + runtime friction estimate' },
  },
}

const VERDICT_SCHEMA = {
  type: 'object', additionalProperties: false,
  required: ['ranking', 'scores', 'biggest_gaps'],
  properties: {
    ranking: { type: 'array', items: { type: 'string' }, description: 'design labels best-first, e.g. ["B","A","C"]' },
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
      properties: { label: { type: 'string' }, gap: { type: 'string', description: 'the single largest gap vs the bar' } },
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

// ---- Phase 1: quality bar, written BEFORE any builder runs ----
phase('Barra')
log('Escrevendo a barra de qualidade antes de qualquer builder')
const bar = await agent(`${CONTEXT}

You are the GAUNTLET BAR-SETTER. Your job: write the concrete quality bar that blind critics will later use to judge competing design proposals for fixing this hole. You write the bar BEFORE any design exists — do not design the solution yourself.

First READ the real code so the bar is grounded, not generic:
- ${REPO}/build-hex/hooks/bash-path-lock.py (the hook with the hole)
- ${REPO}/build-hex/hooks/path-lock.py (its Write/Edit sibling)
- ${REPO}/tests/test_bash_path_lock_redir.py (existing test style)
- ${REPO}/docs/internals/path-lock.md (design intent)

Then produce 5-8 concrete, independently judgeable criteria. They must cover at least: (a) does the design actually close or reliably detect the interpreter-bypass class (not just python3 -c literally), (b) does the legitimate RED-perturbation flow survive, (c) enforcement honesty — no security theater, the design says truthfully what it prevents vs detects, (d) fit with the harness philosophy (independent gates, 5-topology replication, tested hooks), (e) build + friction cost. Each criterion gets a how_to_judge rubric a critic can apply to a design TEXT.

Also write reference_bar: a short description of the ideal, possibly-unreachable solution (e.g. what an OS-sandbox-grade guarantee would look like here) — it gives critics a direction to compare against, per the Gauntlet Loop method.`,
  { label: 'bar-setter', phase: 'Barra', schema: BAR_SCHEMA })

const barText = JSON.stringify(bar, null, 2)

// ---- Phase 2: 3 competing builders, distinct angles, mutually isolated ----
const ANGLES = [
  { key: 'enforcement-first', brief: 'Your angle: PREVENTION. Make the lock actually hold at Bash-time. Start from backlog direction 1 (deny inline interpreters by default) but make it LIVABLE: design the exception mechanism, the allowlist, how proof-reviewer/qa-engineer legitimate perturbations flow through without a human in the loop every time.' },
  { key: 'detection-first', brief: 'Your angle: VERIFICATION. Start from backlog direction 2: the guarantee moves to an independent gate that verifies the final diff against per-agent write globs (who claimed to write what vs who actually wrote what). Design where that check lives, what evidence it reads, what happens on violation, and what the Bash-time hook becomes (keep, soften, or repurpose it).' },
  { key: 'unconstrained', brief: 'Your angle: FREE. Ignore the three sketched directions if you want. Consider mechanisms the others will not: OS-level sandbox profiles per agent (macOS sandbox-exec, Bash tool sandboxing), snapshot/diff of the worktree around each Bash call, filesystem watches, combining prevention+detection in layers, or something else entirely. Novelty only counts if it is buildable in this harness.' },
]

phase('Builders')
log('3 builders em paralelo, isolados entre si')
const rawDesigns = await parallel(ANGLES.map(a => () => agent(`${CONTEXT}

You are a GAUNTLET BUILDER competing blindly against other builders you cannot see. Produce the best complete DESIGN (not code) for fixing the bash-path-lock interpreter-bypass hole. A blind critic will judge your design text against this pre-declared quality bar — optimize for it:

${barText}

${a.brief}

Ground the design in the real repo: READ ${REPO}/build-hex/hooks/bash-path-lock.py, ${REPO}/build-hex/hooks/path-lock.py, ${REPO}/tests/test_bash_path_lock_redir.py, and skim ${REPO}/common/hooks/enforcement-guard.py and ${REPO}/build-hex/agents/qa-engineer.md if useful. Cite actual files/lines. Be honest in failure_modes — critics reward honesty over bluster, and one criterion is enforcement honesty.`,
  { label: `builder:${a.key}`, phase: 'Builders', schema: DESIGN_SCHEMA })))

const designs = rawDesigns.map((d, i) => ({ label: 'ABC'[i], angle: ANGLES[i].key, design: d })).filter(x => x.design)
if (designs.length < 2) { return { error: 'menos de 2 designs sobreviveram — gauntlet sem competição', designs } }

// anonymized artifact block; rotated presentation order per judge to vary primacy
const renderDesign = x => `=== DESIGN ${x.label} ===\n${JSON.stringify(x.design, null, 2)}`

phase('Julgamento')
log(`${designs.length} designs anonimizados indo a 3 juízes cegos`)
const JUDGES = [0, 1, 2]
const verdicts = (await parallel(JUDGES.map(j => () => {
  const order = designs.map((_, i) => designs[(i + j) % designs.length])
  return agent(`${CONTEXT}

You are a GAUNTLET CRITIC. You receive ONLY: the goal above, the quality bar below, and the anonymized design artifacts. You know nothing about who or what produced each design, and you must not guess. Judge the TEXT against the BAR, criterion by criterion, harshly and independently. Reasonable is not the target — the reference_bar is the direction. If two designs are close, the tiebreaker is enforcement honesty and fit with the harness philosophy. You may verify claims a design makes about the repo by reading the cited files — a design that miscites the code should lose points.

QUALITY BAR:
${barText}

DESIGNS:
${order.map(renderDesign).join('\n\n')}

Score every design on every criterion (0-10), rank best-first, and for each design name its single biggest gap versus the bar.`,
    { label: `judge-${j + 1}`, phase: 'Julgamento', schema: VERDICT_SCHEMA })
}))).filter(Boolean)

if (!verdicts.length) { return { error: 'nenhum juiz retornou veredito', designs } }

// aggregate: Borda count across judges
const points = {}
for (const v of verdicts) v.ranking.forEach((label, idx) => { points[label] = (points[label] || 0) + (designs.length - idx) })
const winnerLabel = Object.entries(points).sort((a, b) => b[1] - a[1])[0][0]
const winner = designs.find(d => d.label === winnerLabel) || designs[0]
const winnerGaps = verdicts.flatMap(v => v.biggest_gaps.filter(g => g.label === winner.label).map(g => g.gap))
const runnerUps = designs.filter(d => d.label !== winner.label)
log(`Vencedor da rodada: DESIGN ${winner.label} (${winner.angle}) — pontos Borda: ${JSON.stringify(points)}`)

// ---- Phase 4: one revision round (the loop), then final bar check ----
phase('Revisão')
const revised = await agent(`${CONTEXT}

You are the GAUNTLET REVISER. The design below won a blind judging round against ${runnerUps.length} rival(s), but the critics named gaps. Produce the REVISED design: keep the winning mechanism, close every gap listed, and graft in any clearly superior idea from the rivals' designs (credit which rival idea you grafted, by its label). Stay honest in failure_modes.

QUALITY BAR:
${barText}

WINNING DESIGN (${winner.label}):
${JSON.stringify(winner.design, null, 2)}

CRITICS' BIGGEST GAPS ON THE WINNER:
${winnerGaps.map((g, i) => `${i + 1}. ${g}`).join('\n')}

RIVAL DESIGNS (graft their best ideas where superior):
${runnerUps.map(renderDesign).join('\n\n')}`,
  { label: 'reviser', phase: 'Revisão', schema: DESIGN_SCHEMA })

const finalCheck = revised ? await agent(`${CONTEXT}

You are the FINAL GAUNTLET CRITIC, fresh context. Below are a pre-declared quality bar and one revised design. Judge strictly: is the bar met (every criterion >= 7/10 in your judgment)? List any remaining gaps. You may read the repo files the design cites to verify claims.

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