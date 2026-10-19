// Lê o subconjunto de YAML que o `cepa-intencao` grava em `.claude/session-intent`.
// O escritor é único (common/bin/cepa-intencao) e só emite `chave: "valor"`,
// `passo: N` e a lista `plano:` de itens entre aspas; `historico:` é ignorado.

export type Intent = {
  proposito: string
  paraQuando: string
  plano: string[]
  passo: number
  passoDesde: string
  sessionId: string
  abertoEm: string
}

const unquote = (raw: string): string => {
  const v = raw.trim()
  if (v.startsWith('"')) {
    try {
      return JSON.parse(v)
    } catch {
      return v.slice(1, -1)
    }
  }
  return v
}

export const parseIntent = (text: string): Intent | null => {
  const campos: Record<string, string> = {}
  const plano: string[] = []
  let bloco = ''
  for (const linha of text.split('\n')) {
    if (linha.startsWith('  - ')) {
      if (bloco === 'plano') plano.push(unquote(linha.slice(4)))
      continue
    }
    if (linha.startsWith(' ') || linha.trim() === '') continue
    const i = linha.indexOf(':')
    if (i < 0) continue
    bloco = linha.slice(0, i)
    campos[bloco] = unquote(linha.slice(i + 1))
  }
  if (!campos.proposito) return null
  return {
    proposito: campos.proposito,
    paraQuando: campos.para_quando ?? '',
    plano,
    passo: Number(campos.passo ?? '1') || 1,
    passoDesde: campos.passo_desde ?? '',
    sessionId: campos.session_id ?? '',
    abertoEm: campos.aberto_em ?? '',
  }
}

export const idade = (desde: string, agora: number): string => {
  const t = Date.parse(desde)
  if (Number.isNaN(t) || agora <= 0) return ''
  const min = Math.max(0, Math.floor((agora - t) / 60000))
  if (min < 60) return `há ${min} min`
  const h = Math.floor(min / 60)
  if (h < 48) return `há ${h} h`
  return `há ${Math.floor(h / 24)} dias`
}
