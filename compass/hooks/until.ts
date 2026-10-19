// Lê o registro de um run do `cepa-until` (`.claude/programs/<fila>/until/<run>.jsonl`).
// O escritor é o `registra()` de common/bin/cepa-until: uma linha JSON por evento,
// cada uma com `evento` e `quando` (ISO local, sem fuso). Os eventos que interessam
// aqui: `run_start`, `item_start`, `item_end`, `verify`, `verify_vermelho`,
// `pausa_de_cota`, `limite_de_uso`, `run_interrompido` e `run_end`.

export type Fase = 'rodando' | 'cota' | 'encerrado' | 'interrompido'

export type ItemDoRun = {
  id: string
  titulo: string
  desde: string
  tentativa: number
  // `item` é o `claude` trabalhando no card; `build` é o verify completo depois do done.
  etapa: 'item' | 'build'
}

export type Run = {
  fila: string
  id: string
  inicio: string
  prazo: string
  fase: Fase
  item: ItemDoRun | null
  entregues: number
  vermelhos: number
  travados: number
  // `retoma` é quando o supervisor acorda depois da pausa pela cota de 5h.
  cota: { retoma: string } | null
  fim: { motivo: string; detalhe: string; quando: string } | null
}

const texto = (v: unknown): string => (typeof v === 'string' ? v : '')

export const parseRun = (jsonl: string, fila: string, id: string): Run | null => {
  let run: Run | null = null
  for (const linha of jsonl.split('\n')) {
    if (linha.trim() === '') continue
    let e: Record<string, unknown>
    try {
      e = JSON.parse(linha)
    } catch {
      continue
    }
    if (e === null || typeof e !== 'object') continue
    const quando = texto(e.quando)
    if (e.evento === 'run_start') {
      run = {
        fila: texto(e.fila) || fila,
        id,
        inicio: quando,
        prazo: texto(e.prazo),
        fase: 'rodando',
        item: null,
        entregues: 0,
        vermelhos: 0,
        travados: 0,
        cota: null,
        fim: null,
      }
      continue
    }
    if (run === null) continue
    switch (e.evento) {
      case 'item_start':
        run.item = {
          id: texto(e.id),
          titulo: texto(e.title),
          desde: quando,
          tentativa: Number(e.tentativa) || 1,
          etapa: 'item',
        }
        run.cota = null
        run.fase = 'rodando'
        break
      case 'item_end':
        if (e.status === 'blocked') run.travados += 1
        if (e.status === 'done' && run.item) run.item = { ...run.item, desde: quando, etapa: 'build' }
        else run.item = null
        break
      case 'verify':
        if (e.verde === true) {
          run.entregues += 1
          run.item = null
        }
        break
      case 'verify_vermelho':
        run.vermelhos += 1
        run.item = null
        break
      case 'pausa_de_cota':
        run.fase = 'cota'
        run.cota = { retoma: texto(e.acorda) }
        break
      case 'limite_de_uso':
        if (e.espera === true) {
          run.fase = 'cota'
          run.cota = { retoma: texto(e.reset_em) }
          run.item = null
        }
        break
      case 'run_interrompido':
        run.fase = 'interrompido'
        run.item = null
        run.fim = { motivo: 'interrompido', detalhe: `sinal ${texto(e.sinal)}`, quando }
        break
      case 'run_end':
        run.fase = 'encerrado'
        run.item = null
        run.cota = null
        run.fim = { motivo: texto(e.motivo), detalhe: texto(e.detalhe), quando }
        break
    }
  }
  return run
}

// O `quando` do cepa-until é hora local sem fuso; `Date.parse` lê no fuso da máquina,
// que é a mesma máquina onde o run roda.
const ms = (iso: string): number => {
  const t = Date.parse(iso)
  return Number.isNaN(t) ? NaN : t
}

// `1h23`, `12min`: mesmo formato do `humano()` do cepa-until.
export const duracao = (deMs: number, ateMs: number): string => {
  if (Number.isNaN(deMs) || Number.isNaN(ateMs)) return ''
  const total = Math.max(0, Math.floor((ateMs - deMs) / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  return h > 0 ? `${h}h${String(m).padStart(2, '0')}` : `${m}min`
}

// Tempo do run: até agora enquanto roda ou espera a cota; até o fim quando acabou.
export const tempoDoRun = (r: Run, agora: number): string =>
  duracao(ms(r.inicio), r.fim === null ? agora : ms(r.fim.quando))

export const tempoDoItem = (i: ItemDoRun, agora: number): string => duracao(ms(i.desde), agora)

export const hora = (iso: string): string => {
  const t = ms(iso)
  if (Number.isNaN(t)) return ''
  const d = new Date(t)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const MOTIVOS: Record<string, string> = {
  'fim-da-fila': 'fila acabou',
  prazo: 'prazo chegou',
  'limite-de-uso': 'parou pela cota',
  disjuntor: 'disjuntor',
  'fila-travada': 'fila travada',
  'item-preso': 'item preso',
  'verify-vermelho': 'build vermelho',
  'sem-rede': 'sem rede',
  'git-quebrado': 'git quebrado',
  'branch-mudou': 'branch mudou',
  interrompido: 'interrompido',
}

export const rotuloDoFim = (motivo: string): string => MOTIVOS[motivo] ?? motivo

// `3 entregues · 1 vermelho · 2 travados`, só o que não é zero.
export const contagem = (r: Run): string => {
  const partes: string[] = []
  if (r.entregues > 0) partes.push(`${r.entregues} ${r.entregues === 1 ? 'entregue' : 'entregues'}`)
  if (r.vermelhos > 0) partes.push(`${r.vermelhos} ${r.vermelhos === 1 ? 'vermelho' : 'vermelhos'}`)
  if (r.travados > 0) partes.push(`${r.travados} ${r.travados === 1 ? 'travado' : 'travados'}`)
  return partes.join(' · ')
}

// O aviso (toast e som) que uma mudança de fase pede; `null` quando não pede nenhum.
// Avisa quando o run acaba (qualquer motivo) e quando para pela cota de 5h.
export const avisoDe = (antes: Run | null, agora: Run): string | null => {
  // Run visto pela primeira vez nesta sessão não gera aviso: não há antes para comparar.
  if (antes === null || antes.id !== agora.id || antes.fase === agora.fase) return null
  if (agora.fase === 'cota') {
    const quando = agora.cota ? hora(agora.cota.retoma) : ''
    return quando === '' ? `cepa-until parado pela cota` : `cepa-until parado pela cota · retoma às ${quando}`
  }
  if (agora.fim !== null) {
    const c = contagem(agora)
    return `cepa-until ${agora.fila}: ${rotuloDoFim(agora.fim.motivo)}` + (c === '' ? '' : ` · ${c}`)
  }
  return null
}
