// Reads the YAML subset that `cepa-intent` writes to `.claude/session-intent`.
// The writer is unique (common/bin/cepa-intent) and only emits `key: "value"`,
// `step: N` and the `plan:` list of quoted items; `history:` is ignored.
// The old keys (proposito, para_quando, plano, passo, ...) are still read.

export type Intent = {
  purpose: string
  byWhen: string
  plan: string[]
  step: number
  stepSince: string
  sessionId: string
  openedAt: string
}

const unquote = (raw: string): string => {
  const v = raw.trim()
  if (v.startsWith('"')) {
    try {
      return JSON.parse(v)
    } catch {
      return v.slice(1, -1)
    }
  }
  return v
}

export const parseIntent = (text: string): Intent | null => {
  const fields: Record<string, string> = {}
  const plan: string[] = []
  let block = ''
  for (const line of text.split('\n')) {
    if (line.startsWith('  - ')) {
      if (block === 'plan' || block === 'plano') plan.push(unquote(line.slice(4)))
      continue
    }
    if (line.startsWith(' ') || line.trim() === '') continue
    const i = line.indexOf(':')
    if (i < 0) continue
    block = line.slice(0, i)
    fields[block] = unquote(line.slice(i + 1))
  }
  const purpose = fields.purpose ?? fields.proposito
  if (!purpose) return null
  return {
    purpose,
    byWhen: fields.by_when ?? fields.para_quando ?? '',
    plan,
    step: Number(fields.step ?? fields.passo ?? '1') || 1,
    stepSince: fields.step_since ?? fields.passo_desde ?? '',
    sessionId: fields.session_id ?? '',
    openedAt: fields.opened_at ?? fields.aberto_em ?? '',
  }
}

export const age = (since: string, now: number): string => {
  const t = Date.parse(since)
  if (Number.isNaN(t) || now <= 0) return ''
  const min = Math.max(0, Math.floor((now - t) / 60000))
  if (min < 60) return `há ${min} min`
  const h = Math.floor(min / 60)
  if (h < 48) return `há ${h} h`
  return `há ${Math.floor(h / 24)} dias`
}
