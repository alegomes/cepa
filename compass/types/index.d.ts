export type QueueItem = { id: string; title: string }

export type Queue = {
  name: string
  source: string
  pending: number
  inProgress: number
  blocked: number
  done: number
  dropped: number
  next: QueueItem | null
  stuck: QueueItem | null
}

export type Cycle = { number: number; label: string }

export type Epic = {
  file: string
  name: string
  status: string
  queuePattern: string
  cycles: Cycle[]
}

declare module 'claude-code' {
  interface PluginState {
    compass: {
      texto: string | null
      agora: number
      filas: Queue[]
      epics: Epic[]
      modo: string | null
      desvios: string | null
      build: string | null
      saidas: Record<string, string>
      until: { queue: string; id: string; text: string } | null
      gate: { gate: 'gate-advance' | 'acceptance-gate' | 'worktree-guard'; phrase: string; when: string; times: number } | null
    }
  }
}
