// Traduz o texto que os três gates Python imprimem quando barram uma ação em
// uma frase leiga. Só lê: o `[gate-advance] BLOCKED:` e o `[acceptance-gate]
// BLOCKED:` chegam como motivo do deny (common/hooks/gate-advance.py e
// acceptance-gate.py, exit 2 com o texto em stderr); o `BLOCK: <n>` do
// worktree-guard é a primeira linha do stdout de um Bash que o chama
// (common/hooks/worktree-guard.py, exit 0 sempre).

export type Gate = 'gate-advance' | 'acceptance-gate' | 'worktree-guard'

export type Bloqueio = { gate: Gate; frase: string }

// Último bloqueio visto na sessão, com quando foi e quantos já houve.
export type Barrada = Bloqueio & { quando: string; vezes: number }

const entre = (texto: string, re: RegExp): string => texto.match(re)?.[1]?.trim() ?? ''

const gateAdvance = (texto: string): string => {
  if (texto.includes('requires a build baseline')) {
    return 'Compartilhar barrado: nenhum build foi verificado neste projeto ainda. Rode o verify do projeto antes.'
  }
  if (texto.includes('build is STALE')) {
    const arquivo = entre(texto, /since edit to (\S+)/)
    return `Barrado: o código mudou depois do último build${arquivo ? ` (${arquivo})` : ''}. Rode o verify de novo.`
  }
  if (texto.includes('build is EMPTY')) {
    return 'Barrado: o último build passou sem rodar teste nenhum. Corrija o filtro de testes e rode de novo.'
  }
  if (texto.includes('build is FAILURE')) {
    if (texto.includes('stopped before it ended')) {
      return 'Barrado: o último build foi interrompido antes de acabar. Rode de novo com tempo suficiente.'
    }
    return 'Barrado: o último build falhou. Conserte e rode o verify de novo.'
  }
  return 'Barrado pelo gate-advance: o build não está verde.'
}

const acceptanceGate = (texto: string): string => {
  const chave = entre(texto, /cannot move (\S+) to/)
  const quem = chave || 'O card'
  if (texto.includes('no acceptance audit found')) {
    return `${quem} barrado: não vai para Done sem a auditoria do completion-auditor.`
  }
  const status = entre(texto, /acceptance audit is '([^']*)'/)
  if (status !== '') {
    return `${quem} barrado: a auditoria de aceite está '${status}', não completa. Feche as lacunas e rode o completion-auditor de novo.`
  }
  if (texto.includes('build is EMPTY')) {
    return `${quem} barrado: o último build não rodou teste nenhum, então não prova nada.`
  }
  return `${quem} barrado pelo acceptance-gate.`
}

const worktreeGuard = (texto: string): string => {
  const presas = [...texto.matchAll(/(source|destination) `([^`]+)` is held by a LIVE session/g)].map(m => m[2])
  if (presas.length === 0) return 'Merge barrado: outra sessão viva está na branch. Peça para ela fechar ou aterrissar antes.'
  const quais = presas.length === 1 ? `a branch ${presas[0]} está` : `as branches ${presas.join(' e ')} estão`
  return `Merge barrado: ${quais} em uso por outra sessão viva. Peça para ela fechar ou aterrissar antes.`
}

// O motivo de um deny: gate-advance ou acceptance-gate; outro erro é null.
export const leBloqueio = (texto: string): Bloqueio | null => {
  if (texto.includes('[gate-advance] BLOCKED:')) return { gate: 'gate-advance', frase: gateAdvance(texto) }
  if (texto.includes('[acceptance-gate] BLOCKED:')) return { gate: 'acceptance-gate', frase: acceptanceGate(texto) }
  return null
}

// O stdout de um Bash que chamou o worktree-guard: `BLOCK: <n>` na primeira linha.
export const leGuarda = (comando: string, stdout: string): Bloqueio | null => {
  if (!comando.includes('worktree-guard')) return null
  if (!/^BLOCK: \d+/.test(stdout.trimStart())) return null
  return { gate: 'worktree-guard', frase: worktreeGuard(stdout) }
}
