// Lê o estado do build (`.claude/last-build.json`). O escritor é o hook
// common/hooks/capture-build-result.py (SUCCESS, FAILURE ou EMPTY, com `at`) e o
// common/hooks/mark-build-stale.py, que troca o status por STALE depois de uma
// edição em código-fonte, guardando a última execução real em `last_known_*`.

import { idade } from './intent'

export type Estado = 'verde' | 'vermelho' | 'vazio' | 'desatualizado' | 'desconhecido'

export type Build = { estado: Estado; em: string; anterior: Estado | null; anteriorEm: string }

const ESTADOS: Record<string, Estado> = { SUCCESS: 'verde', FAILURE: 'vermelho', EMPTY: 'vazio', STALE: 'desatualizado' }

const estado = (status: unknown): Estado => ESTADOS[String(status ?? '').toUpperCase()] ?? 'desconhecido'

const texto = (v: unknown): string => (typeof v === 'string' ? v : '')

export const parseBuild = (json: string): Build | null => {
  let dados: Record<string, unknown>
  try {
    dados = JSON.parse(json)
  } catch {
    return null
  }
  if (dados === null || typeof dados !== 'object') return null
  const atual = estado(dados.status)
  if (atual !== 'desatualizado') return { estado: atual, em: texto(dados.at), anterior: null, anteriorEm: '' }
  const anterior = estado(dados.last_known_status)
  return {
    estado: 'desatualizado',
    em: texto(dados.since),
    anterior: anterior === 'desatualizado' ? 'desconhecido' : anterior,
    anteriorEm: texto(dados.last_known_at),
  }
}

export const COR: Record<Estado, string | undefined> = {
  verde: 'green',
  vermelho: 'red',
  vazio: 'yellow',
  desatualizado: 'yellow',
  desconhecido: undefined,
}

const comIdade = (nome: string, desde: string, agora: number): string => {
  const quando = idade(desde, agora)
  return quando === '' ? nome : `${nome} ${quando}`
}

// `verde há 12 min`, `vermelho há 2 h`, `desatualizado há 3 min · era verde há 1 h`.
export const linhaBuild = (b: Build, agora: number): string => {
  const base = comIdade(b.estado, b.em, agora)
  if (b.estado !== 'desatualizado' || b.anterior === null || b.anterior === 'desconhecido') return base
  return `${base} · era ${comIdade(b.anterior, b.anteriorEm, agora)}`
}
