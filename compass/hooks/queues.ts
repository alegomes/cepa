// Resume uma fila `single-track` (.claude/queues/<nome>/queue.yaml, ou .claude/programs/<nome>/plan.yaml no layout antigo): contagem
// por status, o primeiro item pendente e o primeiro bloqueado, na ordem da fila.
// Filas de outro formato (as `parallel-waves` do maestro) ficam de fora: o
// /common:next não as lê.

import type { Fila, ItemFila } from '../types'

// `title:` vem sem aspas, entre aspas simples ou duplas, e o serializador
// dobra o texto longo em linhas seguintes com recuo maior.
const leTitulo = (bloco: string[]): string => {
  const i = bloco.findIndex(l => /^\s{2}title:/.test(l))
  if (i < 0) return ''
  const partes = [bloco[i]!.replace(/^\s{2}title:\s*/, '')]
  for (const l of bloco.slice(i + 1)) {
    if (!/^\s{4,}\S/.test(l)) break
    partes.push(l.trim())
  }
  const t = partes.join(' ').trim()
  if (t.startsWith("'")) return t.slice(1, -1).replace(/''/g, "'")
  if (t.startsWith('"')) {
    try {
      return JSON.parse(t)
    } catch {
      return t.slice(1, -1)
    }
  }
  return t
}

// `source:` pode dobrar em linhas seguintes com recuo; o cabeçalho acaba em `items:`.
const leFonte = (texto: string): string => {
  const m = /^source:\s*(.*)$/m.exec(texto)
  if (m === null) return ''
  const partes = [m[1]!]
  for (const l of texto.slice(m.index + m[0].length + 1).split('\n')) {
    if (!/^\s+\S/.test(l)) break
    partes.push(l.trim())
  }
  return partes.join(' ').trim().replace(/^['"]|['"]$/g, '')
}

export const contaFila = (nome: string, texto: string): Fila | null => {
  if (!/^mode:\s*single-track\s*$/m.test(texto)) return null
  const fila: Fila = {
    nome, fonte: leFonte(texto), pendentes: 0, emAndamento: 0, bloqueados: 0, feitos: 0, descartados: 0, proximo: null, travado: null,
  }
  const blocos = texto.split(/^(?=- id:)/m).slice(1)
  for (const b of blocos) {
    const linhas = b.split('\n')
    const id = linhas[0]!.replace(/^- id:\s*/, '').replace(/^['"]|['"]$/g, '').trim()
    const status = (/^\s{2}status:\s*(\w+)/m.exec(b)?.[1] ?? '').toLowerCase()
    const item: ItemFila = { id, titulo: leTitulo(linhas) }
    if (status === 'pending') {
      fila.pendentes += 1
      fila.proximo ??= item
    }
    if (status === 'in_progress') fila.emAndamento += 1
    if (status === 'blocked') {
      fila.bloqueados += 1
      fila.travado ??= item
    }
    if (status === 'done') fila.feitos += 1
    if (status === 'dropped') fila.descartados += 1
  }
  return fila
}

export const aberta = (f: Fila): boolean => f.pendentes + f.emAndamento + f.bloqueados > 0

// Colunas da tabela do painel, na ordem do ciclo de vida de um item.
export const COLUNAS = [
  { rotulo: 'pend', campo: 'pendentes', cor: 'yellow' },
  { rotulo: 'and', campo: 'emAndamento', cor: 'cyan' },
  { rotulo: 'bloq', campo: 'bloqueados', cor: 'red' },
  { rotulo: 'feito', campo: 'feitos', cor: 'green' },
  { rotulo: 'desc', campo: 'descartados', cor: 'gray' },
] as const
