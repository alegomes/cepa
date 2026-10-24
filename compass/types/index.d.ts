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

export type Ciclo = { numero: number; rotulo: string }

export type Epic = {
  arquivo: string
  nome: string
  status: string
  padraoFila: string
  ciclos: Ciclo[]
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
      until: { fila: string; id: string; texto: string } | null
      gate: { gate: 'gate-advance' | 'acceptance-gate' | 'worktree-guard'; frase: string; quando: string; vezes: number } | null
    }
  }
}
