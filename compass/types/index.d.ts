export type ItemFila = { id: string; titulo: string }

export type Fila = {
  nome: string
  fonte: string
  pendentes: number
  emAndamento: number
  bloqueados: number
  feitos: number
  descartados: number
  proximo: ItemFila | null
  travado: ItemFila | null
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
      filas: Fila[]
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
