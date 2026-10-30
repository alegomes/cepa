// Summarizes a `single-track` queue (.claude/queues/<name>/queue.yaml, or .claude/programs/<name>/plan.yaml in the old layout): count
// by status, the first pending item and the first blocked one, in queue order.
// Queues in another format (the maestro's `parallel-waves`) are left out: /common:next
// does not read them.

import type { Queue, QueueItem } from '../types'

// `title:` comes unquoted, in single quotes or in double quotes, and the serializer
// folds long text onto following lines with a deeper indent.
const readTitle = (block: string[]): string => {
  const i = block.findIndex(l => /^\s{2}title:/.test(l))
  if (i < 0) return ''
  const parts = [block[i]!.replace(/^\s{2}title:\s*/, '')]
  for (const l of block.slice(i + 1)) {
    if (!/^\s{4,}\S/.test(l)) break
    parts.push(l.trim())
  }
  const t = parts.join(' ').trim()
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

// `source:` may fold onto following indented lines; the header ends at `items:`.
const readSource = (text: string): string => {
  const m = /^source:\s*(.*)$/m.exec(text)
  if (m === null) return ''
  const parts = [m[1]!]
  for (const l of text.slice(m.index + m[0].length + 1).split('\n')) {
    if (!/^\s+\S/.test(l)) break
    parts.push(l.trim())
  }
  return parts.join(' ').trim().replace(/^['"]|['"]$/g, '')
}

export const countQueue = (name: string, text: string): Queue | null => {
  if (!/^mode:\s*single-track\s*$/m.test(text)) return null
  const queue: Queue = {
    name, source: readSource(text), pending: 0, inProgress: 0, blocked: 0, done: 0, dropped: 0, next: null, stuck: null,
  }
  const blocks = text.split(/^(?=- id:)/m).slice(1)
  for (const b of blocks) {
    const lines = b.split('\n')
    const id = lines[0]!.replace(/^- id:\s*/, '').replace(/^['"]|['"]$/g, '').trim()
    const status = (/^\s{2}status:\s*(\w+)/m.exec(b)?.[1] ?? '').toLowerCase()
    const item: QueueItem = { id, title: readTitle(lines) }
    if (status === 'pending') {
      queue.pending += 1
      queue.next ??= item
    }
    if (status === 'in_progress') queue.inProgress += 1
    if (status === 'blocked') {
      queue.blocked += 1
      queue.stuck ??= item
    }
    if (status === 'done') queue.done += 1
    if (status === 'dropped') queue.dropped += 1
  }
  return queue
}

export const isOpen = (q: Queue): boolean => q.pending + q.inProgress + q.blocked > 0

// Columns of the panel table, in the order of an item's lifecycle.
export const COLUMNS = [
  { label: 'pend', field: 'pending', color: 'yellow' },
  { label: 'and', field: 'inProgress', color: 'cyan' },
  { label: 'bloq', field: 'blocked', color: 'red' },
  { label: 'feito', field: 'done', color: 'green' },
  { label: 'desc', field: 'dropped', color: 'gray' },
] as const
