// Reads an Epic from /common:epic (`docs/epics/<name>.md`): the name, the status and the
// cycles of the value ladder; and links each cycle to the `single-track` queue that
// builds it, so the panel tells where each rung stands without opening a file.

import type { Epic, Queue } from '../types'

const RE_TITLE = /^#\s+Epic:\s*(.+?)\s*$/m
const RE_STATUS = /\*\*Status:\*\*\s*([^\s·|]+)/
// On the `**Construção:**` line, the backtick span that carries `<N>` is the name
// pattern of the queues, one per cycle: `.claude/programs/cepa-espiral-c<N>/plan.yaml`
// becomes `cepa-espiral-c<N>`.
const RE_PATTERN = /\*\*Construção:\*\*[^\n]*?`([^`\n]*<N>[^`\n]*)`/
const RE_CYCLE = /^(\d+)\s*[.):-]?\s*(.*)$/

const cells = (line: string): string[] => {
  let s = line.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1)
  return s.split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, '|'))
}

export const parseEpic = (file: string, text: string): Epic | null => {
  const title = RE_TITLE.exec(text)
  if (title === null) return null
  const pattern = RE_PATTERN.exec(text)?.[1] ?? ''
  const epic: Epic = {
    file: file.replace(/\.md$/, ''),
    name: title[1]!,
    status: RE_STATUS.exec(text)?.[1] ?? 'rascunho',
    queuePattern: pattern.split('/').find(p => p.includes('<N>')) ?? '',
    cycles: [],
  }
  // The ladder is the first table after `## Value ladder` (or the old `## Escada de valor`); the first column
  // is the cycle (`1. Encadear`). Header and separator rows are left out.
  const i = text.search(/^##\s+(?:Value ladder|Escada de valor)\s*$/m)
  if (i < 0) return epic
  const body = text.slice(i).split('\n').slice(1)
  for (const line of body) {
    if (/^##\s/.test(line)) break
    if (!line.trim().startsWith('|')) continue
    const cols = cells(line)
    if (cols.every(c => /^:?-+:?$/.test(c) || c === '')) continue
    const m = RE_CYCLE.exec(cols[0] ?? '')
    if (m === null) continue
    epic.cycles.push({ number: Number(m[1]), label: cols[0]! })
  }
  return epic
}

// The queue of a cycle, in this order: (1) the queue's `source:` cites the Epic file
// and `ciclo N`, which is what `/common:plan --from-epic` writes; (2) the queue name
// matches the pattern of the Construção line with `<N>` swapped in; (3) `<file>-c<N>`.
export const queueOfCycle = (epic: Epic, cycle: number, queues: readonly Queue[]): Queue | null => {
  const cites = new RegExp(`\\b(?:ciclo|cycle)\\s+${cycle}\\b`)
  const bySource = queues.find(f => f.source.includes(`docs/epics/${epic.file}.md`) && cites.test(f.source))
  if (bySource) return bySource
  const byPattern = epic.queuePattern === '' ? null : queues.find(f => f.name === epic.queuePattern.replace('<N>', String(cycle)))
  return byPattern ?? queues.find(f => f.name === `${epic.file}-c${cycle}`) ?? null
}

export type CycleState = 'sem fila' | 'demonstrável' | 'travado' | 'andando'

export const cycleState = (f: Queue | null): CycleState => {
  if (f === null) return 'sem fila'
  const open = f.pending + f.inProgress + f.blocked
  if (open === 0 && f.done > 0) return 'demonstrável'
  if (f.blocked > 0 && f.inProgress === 0) return 'travado'
  return 'andando'
}

// What the cycle line says: `sem fila`, `demonstrável`, `travado · 1/3 feitos`
// or `1/2 feitos`. Dropped items stay out of the count: they are not work to do.
export const cycleLine = (f: Queue | null): string => {
  const e = cycleState(f)
  if (f === null || e === 'demonstrável') return e
  const count = `${f.done}/${f.pending + f.inProgress + f.blocked + f.done} feitos`
  return e === 'travado' ? `travado · ${count}` : count
}

export const MARK: Record<CycleState, { symbol: string; color: string | undefined }> = {
  'sem fila': { symbol: '○', color: undefined },
  andando: { symbol: '▶', color: 'cyan' },
  travado: { symbol: '✗', color: 'red' },
  demonstrável: { symbol: '✓', color: 'green' },
}
