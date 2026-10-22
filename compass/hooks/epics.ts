// Lê um Epic do /common:epic (`docs/epics/<nome>.md`): o nome, o status e os
// ciclos da escada de valor; e liga cada ciclo à fila `single-track` que o
// constrói, para o painel dizer em que pé está cada degrau sem abrir arquivo.

import type { Epic, Fila } from '../types'

const RE_TITULO = /^#\s+Epic:\s*(.+?)\s*$/m
const RE_STATUS = /\*\*Status:\*\*\s*([^\s·|]+)/
// Na linha `**Construção:**`, o trecho entre crases que traz `<N>` é o padrão de
// nome das filas, uma por ciclo: `.claude/programs/cepa-espiral-c<N>/plan.yaml`
// vira `cepa-espiral-c<N>`.
const RE_PADRAO = /\*\*Construção:\*\*[^\n]*?`([^`\n]*<N>[^`\n]*)`/
const RE_CICLO = /^(\d+)\s*[.):-]?\s*(.*)$/

const celulas = (linha: string): string[] => {
  let s = linha.trim()
  if (s.startsWith('|')) s = s.slice(1)
  if (s.endsWith('|') && !s.endsWith('\\|')) s = s.slice(0, -1)
  return s.split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, '|'))
}

export const parseEpic = (arquivo: string, texto: string): Epic | null => {
  const titulo = RE_TITULO.exec(texto)
  if (titulo === null) return null
  const padrao = RE_PADRAO.exec(texto)?.[1] ?? ''
  const epic: Epic = {
    arquivo: arquivo.replace(/\.md$/, ''),
    nome: titulo[1]!,
    status: RE_STATUS.exec(texto)?.[1] ?? 'rascunho',
    padraoFila: padrao.split('/').find(p => p.includes('<N>')) ?? '',
    ciclos: [],
  }
  // A escada é a primeira tabela depois de `## Escada de valor`; a primeira coluna
  // é o ciclo (`1. Encadear`). Linhas de cabeçalho e de separador ficam de fora.
  const i = texto.search(/^##\s+Escada de valor\s*$/m)
  if (i < 0) return epic
  const corpo = texto.slice(i).split('\n').slice(1)
  for (const linha of corpo) {
    if (/^##\s/.test(linha)) break
    if (!linha.trim().startsWith('|')) continue
    const cel = celulas(linha)
    if (cel.every(c => /^:?-+:?$/.test(c) || c === '')) continue
    const m = RE_CICLO.exec(cel[0] ?? '')
    if (m === null) continue
    epic.ciclos.push({ numero: Number(m[1]), rotulo: cel[0]! })
  }
  return epic
}

// A fila de um ciclo, nesta ordem: (1) o `source:` da fila cita o arquivo do Epic
// e `ciclo N`, que é o que `/common:plan --from-epic` escreve; (2) o nome da fila
// casa com o padrão da linha Construção com `<N>` trocado; (3) `<arquivo>-c<N>`.
export const filaDoCiclo = (epic: Epic, ciclo: number, filas: readonly Fila[]): Fila | null => {
  const cita = new RegExp(`\\bciclo\\s+${ciclo}\\b`)
  const porFonte = filas.find(f => f.fonte.includes(`docs/epics/${epic.arquivo}.md`) && cita.test(f.fonte))
  if (porFonte) return porFonte
  const porPadrao = epic.padraoFila === '' ? null : filas.find(f => f.nome === epic.padraoFila.replace('<N>', String(ciclo)))
  return porPadrao ?? filas.find(f => f.nome === `${epic.arquivo}-c${ciclo}`) ?? null
}

export type EstadoDoCiclo = 'sem fila' | 'demonstrável' | 'travado' | 'andando'

export const estadoDoCiclo = (f: Fila | null): EstadoDoCiclo => {
  if (f === null) return 'sem fila'
  const abertos = f.pendentes + f.emAndamento + f.bloqueados
  if (abertos === 0 && f.feitos > 0) return 'demonstrável'
  if (f.bloqueados > 0 && f.emAndamento === 0) return 'travado'
  return 'andando'
}

// O que a linha do ciclo diz: `sem fila`, `demonstrável`, `travado · 1/3 feitos`
// ou `1/2 feitos`. Descartados não entram na conta: não são trabalho a fazer.
export const linhaDoCiclo = (f: Fila | null): string => {
  const e = estadoDoCiclo(f)
  if (f === null || e === 'demonstrável') return e
  const conta = `${f.feitos}/${f.pendentes + f.emAndamento + f.bloqueados + f.feitos} feitos`
  return e === 'travado' ? `travado · ${conta}` : conta
}

export const MARCA: Record<EstadoDoCiclo, { simbolo: string; cor: string | undefined }> = {
  'sem fila': { simbolo: '○', cor: undefined },
  andando: { simbolo: '▶', cor: 'cyan' },
  travado: { simbolo: '✗', cor: 'red' },
  demonstrável: { simbolo: '✓', cor: 'green' },
}
