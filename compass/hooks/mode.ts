// Reads the session mode (`.claude/session-mode`) and the deviations (`.claude/deviations.md`, legacy `.claude/desvios.md`).
// The mode is written by `cepa` as shallow `key: value` lines (`mode`, `routine`, `budget`,
// `opened_at`; the old pt-BR keys and mode names are still read); `null` and empty mean absent,
// as in `read_mode` of common/hooks/session-mode.py. Deviations are the lines
// `- [ ]` (open) and `- [x]` (resolved) that the off-mode-capture skill appends.

// Old (pt-BR) mode name -> the new one; `cepa-modes --json` only knows the new ones.
const OLD_MODES: Record<string, string> = {
  exploracao: 'exploration',
  descoberta: 'discovery',
  construcao: 'construction',
  reforma: 'refactor',
  reflexao: 'reflection',
  documentacao: 'documentation',
}

export type Mode = { name: string; budget: string; openedAt: string }

export type Deviations = { open: number; resolved: number; last: string }

export const parseMode = (text: string): Mode | null => {
  const fields: Record<string, string> = {}
  for (const line of text.split('\n')) {
    const i = line.indexOf(':')
    if (i < 0) continue
    const v = line.slice(i + 1).trim().replace(/^"|"$/g, '')
    if (v !== '' && v !== 'null') fields[line.slice(0, i).trim()] = v
  }
  const name = fields.mode ?? fields.modo
  if (!name) return null
  return {
    name: OLD_MODES[name] ?? name,
    budget: fields.budget ?? fields.orcamento ?? '',
    openedAt: fields.opened_at ?? fields.aberto_em ?? '',
  }
}

export const countDeviations = (text: string): Deviations => {
  const d: Deviations = { open: 0, resolved: 0, last: '' }
  for (const line of text.split('\n')) {
    const m = /^- \[( |x|X)\]\s*(.*)$/.exec(line)
    if (!m) continue
    if (m[1] === ' ') d.open += 1
    else d.resolved += 1
    // `date · modo: X · what`: the warning shows only the "what".
    const parts = m[2]!.split(' · ')
    d.last = parts.length > 2 ? parts.slice(2).join(' · ') : m[2]!
  }
  return d
}

// The exit condition lives in common/hooks/_modes.py; `cepa-modes --json` exposes it.
export const readExits = (json: string): Record<string, string> => {
  try {
    const table = JSON.parse(json) as Record<string, { saida?: string }>
    const exits: Record<string, string> = {}
    for (const [name, d] of Object.entries(table)) if (d.saida) exits[name] = d.saida
    return exits
  } catch {
    return {}
  }
}
