// Reads the build state (`.claude/last-build.json`). The writers are the hook
// common/hooks/capture-build-result.py (SUCCESS, FAILURE or EMPTY, with `at`) and
// common/hooks/mark-build-stale.py, which swaps the status to STALE after an
// edit to source code, keeping the last real run in `last_known_*`.

import { age } from './intent'

export type BuildState = 'verde' | 'vermelho' | 'vazio' | 'desatualizado' | 'desconhecido'

export type Build = { state: BuildState; at: string; previous: BuildState | null; previousAt: string }

const STATES: Record<string, BuildState> = { SUCCESS: 'verde', FAILURE: 'vermelho', EMPTY: 'vazio', STALE: 'desatualizado' }

const toState = (status: unknown): BuildState => STATES[String(status ?? '').toUpperCase()] ?? 'desconhecido'

const text = (v: unknown): string => (typeof v === 'string' ? v : '')

export const parseBuild = (json: string): Build | null => {
  let data: Record<string, unknown>
  try {
    data = JSON.parse(json)
  } catch {
    return null
  }
  if (data === null || typeof data !== 'object') return null
  const current = toState(data.status)
  if (current !== 'desatualizado') return { state: current, at: text(data.at), previous: null, previousAt: '' }
  const previous = toState(data.last_known_status)
  return {
    state: 'desatualizado',
    at: text(data.since),
    previous: previous === 'desatualizado' ? 'desconhecido' : previous,
    previousAt: text(data.last_known_at),
  }
}

export const COLOR: Record<BuildState, string | undefined> = {
  verde: 'green',
  vermelho: 'red',
  vazio: 'yellow',
  desatualizado: 'yellow',
  desconhecido: undefined,
}

const withAge = (name: string, since: string, now: number): string => {
  const when = age(since, now)
  return when === '' ? name : `${name} ${when}`
}

// `verde há 12 min`, `vermelho há 2 h`, `desatualizado há 3 min · era verde há 1 h`.
export const buildLine = (b: Build, now: number): string => {
  const base = withAge(b.state, b.at, now)
  if (b.state !== 'desatualizado' || b.previous === null || b.previous === 'desconhecido') return base
  return `${base} · era ${withAge(b.previous, b.previousAt, now)}`
}
