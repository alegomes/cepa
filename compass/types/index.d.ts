export type ItemFila = { id: string; titulo: string }

export type Fila = {
  nome: string
  pendentes: number
  emAndamento: number
  bloqueados: number
  feitos: number
  descartados: number
  proximo: ItemFila | null
  travado: ItemFila | null
}

declare module 'claude-code' {
  interface PluginState {
    compass: {
      texto: string | null
      agora: number
      filas: Fila[]
      modo: string | null
      desvios: string | null
      build: string | null
      saidas: Record<string, string>
    }
  }
}
