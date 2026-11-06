// Reads the record of a `cepa-until` run (`.claude/queues/<queue>/until/<run>.jsonl`, or `.claude/programs/...` in the old layout).
// The writer is the `registra()` of common/bin/cepa-until: one JSON line per event,
// each with `evento` and `quando` (local ISO, no timezone). The events that matter
// here: `run_start`, `item_start`, `item_end`, `verify`, `verify_vermelho`,
// `pausa_de_cota`, `limite_de_uso`, `run_interrompido` and `run_end`.

export type Phase = 'rodando' | 'cota' | 'encerrado' | 'interrompido'

export type RunItem = {
  id: string
  title: string
  since: string
  attempt: number
  // `item` is `claude` working on the card; `build` is the full verify after done.
  stage: 'item' | 'build'
}

export type Run = {
  queue: string
  id: string
  start: string
  deadline: string
  phase: Phase
  item: RunItem | null
  delivered: number
  reds: number
  blocked: number
  // `resumes` is when the supervisor wakes up after the pause for the 5h quota.
  quota: { resumes: string } | null
  end: { reason: string; detail: string; when: string } | null
}

const text = (v: unknown): string => (typeof v === 'string' ? v : '')

export const parseRun = (jsonl: string, queue: string, id: string): Run | null => {
  let run: Run | null = null
  for (const line of jsonl.split('\n')) {
    if (line.trim() === '') continue
    let e: Record<string, unknown>
    try {
      e = JSON.parse(line)
    } catch {
      continue
    }
    if (e === null || typeof e !== 'object') continue
    const when = text(e.quando)
    if (e.evento === 'run_start') {
      run = {
        queue: text(e.fila) || queue,
        id,
        start: when,
        deadline: text(e.prazo),
        phase: 'rodando',
        item: null,
        delivered: 0,
        reds: 0,
        blocked: 0,
        quota: null,
        end: null,
      }
      continue
    }
    if (run === null) continue
    switch (e.evento) {
      case 'item_start':
        run.item = {
          id: text(e.id),
          title: text(e.title),
          since: when,
          attempt: Number(e.tentativa) || 1,
          stage: 'item',
        }
        run.quota = null
        run.phase = 'rodando'
        break
      case 'item_end':
        if (e.status === 'blocked') run.blocked += 1
        if (e.status === 'done' && run.item) run.item = { ...run.item, since: when, stage: 'build' }
        else run.item = null
        break
      case 'verify':
        if (e.verde === true) {
          run.delivered += 1
          run.item = null
        }
        break
      case 'verify_vermelho':
        run.reds += 1
        run.item = null
        break
      case 'pausa_de_cota':
        run.phase = 'cota'
        run.quota = { resumes: text(e.acorda) }
        break
      case 'limite_de_uso':
        if (e.espera === true) {
          run.phase = 'cota'
          run.quota = { resumes: text(e.reset_em) }
          run.item = null
        }
        break
      case 'run_interrompido':
        run.phase = 'interrompido'
        run.item = null
        run.end = { reason: 'interrompido', detail: `sinal ${text(e.sinal)}`, when }
        break
      case 'run_end':
        run.phase = 'encerrado'
        run.item = null
        run.quota = null
        run.end = { reason: text(e.motivo), detail: text(e.detalhe), when }
        break
    }
  }
  return run
}

// The `quando` of cepa-until is local time with no timezone; `Date.parse` reads it in the machine's timezone,
// which is the same machine where the run happens.
const ms = (iso: string): number => {
  const t = Date.parse(iso)
  return Number.isNaN(t) ? NaN : t
}

// `1h23`, `12min`: same format as the `humano()` of cepa-until.
export const duration = (fromMs: number, toMs: number): string => {
  if (Number.isNaN(fromMs) || Number.isNaN(toMs)) return ''
  const total = Math.max(0, Math.floor((toMs - fromMs) / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  return h > 0 ? `${h}h${String(m).padStart(2, '0')}` : `${m}min`
}

// Time of the run: up to now while it runs or waits for the quota; up to the end when it is over.
export const runTime = (r: Run, now: number): string =>
  duration(ms(r.start), r.end === null ? now : ms(r.end.when))

export const itemTime = (i: RunItem, now: number): string => duration(ms(i.since), now)

export const timeOfDay = (iso: string): string => {
  const t = ms(iso)
  if (Number.isNaN(t)) return ''
  const d = new Date(t)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const REASONS: Record<string, string> = {
  'end-of-queue': 'fila acabou',
  'fim-da-fila': 'fila acabou', // old .jsonl records still carry it
  prazo: 'prazo chegou',
  'limite-de-uso': 'parou pela cota',
  disjuntor: 'disjuntor',
  'fila-travada': 'fila travada',
  'item-preso': 'item preso',
  'verify-vermelho': 'build vermelho',
  'sem-rede': 'sem rede',
  'git-quebrado': 'git quebrado',
  'branch-mudou': 'branch mudou',
  interrompido: 'interrompido',
}

export const endLabel = (reason: string): string => REASONS[reason] ?? reason

// `3 entregues · 1 vermelho · 2 travados`, only what is not zero.
export const tally = (r: Run): string => {
  const parts: string[] = []
  if (r.delivered > 0) parts.push(`${r.delivered} ${r.delivered === 1 ? 'entregue' : 'entregues'}`)
  if (r.reds > 0) parts.push(`${r.reds} ${r.reds === 1 ? 'vermelho' : 'vermelhos'}`)
  if (r.blocked > 0) parts.push(`${r.blocked} ${r.blocked === 1 ? 'travado' : 'travados'}`)
  return parts.join(' · ')
}

// The notice (toast and sound) a phase change asks for; `null` when it asks for none.
// It notices when the run ends (any reason) and when it stops for the 5h quota.
export const noticeFor = (before: Run | null, current: Run): string | null => {
  // A run seen for the first time in this session raises no notice: there is no before to compare.
  if (before === null || before.id !== current.id || before.phase === current.phase) return null
  if (current.phase === 'cota') {
    const when = current.quota ? timeOfDay(current.quota.resumes) : ''
    return when === '' ? `cepa-until parado pela cota` : `cepa-until parado pela cota · retoma às ${when}`
  }
  if (current.end !== null) {
    const c = tally(current)
    return `cepa-until ${current.queue}: ${endLabel(current.end.reason)}` + (c === '' ? '' : ` · ${c}`)
  }
  return null
}
