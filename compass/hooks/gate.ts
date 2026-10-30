// Translates the text the three Python gates print when they block an action into
// a plain-language sentence. Read-only: the `[gate-advance] BLOCKED:` and the
// `[acceptance-gate] BLOCKED:` arrive as the deny reason (common/hooks/gate-advance.py and
// acceptance-gate.py, exit 2 with the text on stderr); the `BLOCK: <n>` of
// worktree-guard is the first line of the stdout of a Bash that calls it
// (common/hooks/worktree-guard.py, always exit 0).

export type Gate = 'gate-advance' | 'acceptance-gate' | 'worktree-guard'

export type Block = { gate: Gate; phrase: string }

// Last block seen in the session, with when it happened and how many so far.
export type Blocked = Block & { when: string; times: number }

const between = (text: string, re: RegExp): string => text.match(re)?.[1]?.trim() ?? ''

const gateAdvance = (text: string): string => {
  if (text.includes('requires a build baseline')) {
    return 'Compartilhar barrado: nenhum build foi verificado neste projeto ainda. Rode o verify do projeto antes.'
  }
  if (text.includes('build is STALE')) {
    const file = between(text, /since edit to (\S+)/)
    return `Barrado: o código mudou depois do último build${file ? ` (${file})` : ''}. Rode o verify de novo.`
  }
  if (text.includes('build is EMPTY')) {
    return 'Barrado: o último build passou sem rodar teste nenhum. Corrija o filtro de testes e rode de novo.'
  }
  if (text.includes('build is FAILURE')) {
    if (text.includes('stopped before it ended')) {
      return 'Barrado: o último build foi interrompido antes de acabar. Rode de novo com tempo suficiente.'
    }
    return 'Barrado: o último build falhou. Conserte e rode o verify de novo.'
  }
  return 'Barrado pelo gate-advance: o build não está verde.'
}

const acceptanceGate = (text: string): string => {
  const key = between(text, /cannot move (\S+) to/)
  const who = key || 'O card'
  if (text.includes('no acceptance audit found')) {
    return `${who} barrado: não vai para Done sem a auditoria do completion-auditor.`
  }
  const status = between(text, /acceptance audit is '([^']*)'/)
  if (status !== '') {
    return `${who} barrado: a auditoria de aceite está '${status}', não completa. Feche as lacunas e rode o completion-auditor de novo.`
  }
  if (text.includes('build is EMPTY')) {
    return `${who} barrado: o último build não rodou teste nenhum, então não prova nada.`
  }
  return `${who} barrado pelo acceptance-gate.`
}

const worktreeGuard = (text: string): string => {
  const held = [...text.matchAll(/(source|destination) `([^`]+)` is held by a LIVE session/g)].map(m => m[2])
  if (held.length === 0) return 'Merge barrado: outra sessão viva está na branch. Peça para ela fechar ou aterrissar antes.'
  const which = held.length === 1 ? `a branch ${held[0]} está` : `as branches ${held.join(' e ')} estão`
  return `Merge barrado: ${which} em uso por outra sessão viva. Peça para ela fechar ou aterrissar antes.`
}

// The reason of a deny: gate-advance or acceptance-gate; any other error is null.
export const readBlock = (text: string): Block | null => {
  if (text.includes('[gate-advance] BLOCKED:')) return { gate: 'gate-advance', phrase: gateAdvance(text) }
  if (text.includes('[acceptance-gate] BLOCKED:')) return { gate: 'acceptance-gate', phrase: acceptanceGate(text) }
  return null
}

// The stdout of a Bash that called worktree-guard: `BLOCK: <n>` on the first line.
export const readGuard = (command: string, stdout: string): Block | null => {
  if (!command.includes('worktree-guard')) return null
  if (!/^BLOCK: \d+/.test(stdout.trimStart())) return null
  return { gate: 'worktree-guard', phrase: worktreeGuard(stdout) }
}
