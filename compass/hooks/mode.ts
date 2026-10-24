// Lê o modo da sessão (`.claude/session-mode`) e os desvios (`.claude/desvios.md`).
// O modo é gravado pelo `cepa` com `chave: valor` raso (`mode`, `routine`, `budget`,
// `opened_at`; as chaves e os nomes de modo antigos em pt-BR ainda são lidos); `null` e vazio são ausência,
// como no `read_mode` do common/hooks/session-mode.py. Os desvios são as linhas
// `- [ ]` (aberto) e `- [x]` (resolvido) que o skill off-mode-capture acrescenta.

// Nome antigo (pt-BR) do modo -> o novo; `cepa-modes --json` só conhece os novos.
const MODOS_ANTIGOS: Record<string, string> = {
  exploracao: 'exploration',
  descoberta: 'discovery',
  construcao: 'construction',
  reforma: 'refactor',
  reflexao: 'reflection',
  documentacao: 'documentation',
}

export type Modo = { nome: string; orcamento: string; abertoEm: string }

export type Desvios = { abertos: number; resolvidos: number; ultimo: string }

export const parseModo = (text: string): Modo | null => {
  const campos: Record<string, string> = {}
  for (const linha of text.split('\n')) {
    const i = linha.indexOf(':')
    if (i < 0) continue
    const v = linha.slice(i + 1).trim().replace(/^"|"$/g, '')
    if (v !== '' && v !== 'null') campos[linha.slice(0, i).trim()] = v
  }
  const nome = campos.mode ?? campos.modo
  if (!nome) return null
  return {
    nome: MODOS_ANTIGOS[nome] ?? nome,
    orcamento: campos.budget ?? campos.orcamento ?? '',
    abertoEm: campos.opened_at ?? campos.aberto_em ?? '',
  }
}

export const contaDesvios = (text: string): Desvios => {
  const d: Desvios = { abertos: 0, resolvidos: 0, ultimo: '' }
  for (const linha of text.split('\n')) {
    const m = /^- \[( |x|X)\]\s*(.*)$/.exec(linha)
    if (!m) continue
    if (m[1] === ' ') d.abertos += 1
    else d.resolvidos += 1
    // `data · modo: X · o quê`: o aviso mostra só o quê.
    const partes = m[2]!.split(' · ')
    d.ultimo = partes.length > 2 ? partes.slice(2).join(' · ') : m[2]!
  }
  return d
}

// A condição de saída mora em common/hooks/_modos.py; `cepa-modes --json` a expõe.
export const leSaidas = (json: string): Record<string, string> => {
  try {
    const tabela = JSON.parse(json) as Record<string, { saida?: string }>
    const saidas: Record<string, string> = {}
    for (const [nome, d] of Object.entries(tabela)) if (d.saida) saidas[nome] = d.saida
    return saidas
  } catch {
    return {}
  }
}
