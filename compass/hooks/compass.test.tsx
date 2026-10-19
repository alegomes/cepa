import { expect, mock, test } from 'claude-code/testing'

import { idade, parseIntent } from './intent'
import { contaDesvios, leSaidas, parseModo } from './modo'

const ARQUIVO = `proposito: "Construir o M1, painel da intenção"
para_quando: "painel aparece no terminal"
plano:
  - "guardar M2-M6 na fila mods"
  - "ler exemplos e tipos do mod"
  - "escrever o mod e testes"
passo: 2
passo_desde: "2026-10-19T10:00:00Z"
session_id: "sessao-a"
branch: "session/oncoto"
aberto_em: "2026-10-18T20:03:58Z"
resumo: "passo 2/3 · ler exemplos e tipos do mod · Construir o M1"
historico:
  - em: "2026-10-18T20:03:58Z"
    proposito: "Outra coisa"
`

test('lê propósito, plano e passo e ignora o histórico', async () => {
  const intent = parseIntent(ARQUIVO)
  expect(intent?.proposito).toBe('Construir o M1, painel da intenção')
  expect(intent?.plano).toEqual([
    'guardar M2-M6 na fila mods',
    'ler exemplos e tipos do mod',
    'escrever o mod e testes',
  ])
  expect(intent?.passo).toBe(2)
  expect(intent?.sessionId).toBe('sessao-a')
})

test('arquivo sem propósito não é intenção', async () => {
  expect(parseIntent('passo: 1\n')).toBe(null)
})

test('idade do cursor em minutos, horas e dias', async () => {
  const t = Date.parse('2026-10-19T10:00:00Z')
  expect(idade('2026-10-19T10:00:00Z', t + 12 * 60000)).toBe('há 12 min')
  expect(idade('2026-10-19T10:00:00Z', t + 3 * 3600000)).toBe('há 3 h')
  expect(idade('2026-10-19T10:00:00Z', t + 72 * 3600000)).toBe('há 3 dias')
})

const FILA = (modo: string, status: string[]) =>
  `mode: ${modo}\nitems:\n` +
  status.map((st, i) => `- id: X${i}\n  title: 'Item ${i} da fila, com título
    longo dobrado e aspas do ''yaml'''\n  why: 'x'\n  status: ${st}\n`).join('')

const ARQUIVOS: Record<string, string> = {
  '/repo/.claude/programs/mods/plan.yaml': FILA('single-track', ['done', 'pending', 'in_progress', 'pending']),
  '/repo/.claude/programs/cepa/plan.yaml': FILA('single-track', ['done', 'blocked', 'dropped']),
  '/repo/.claude/programs/velha/plan.yaml': FILA('parallel-waves', ['pending']),
  '/repo/.claude/programs/zerada/plan.yaml': FILA('single-track', ['done']),
}

const prepara = async ($: any, on: any, sessao: string, texto: string | null, extras: Record<string, string> = {}) => {
  const relogio = mock.clock(on, { now: Date.parse('2026-10-19T10:12:00Z') })
  const arquivos: Record<string, string> = { ...ARQUIVOS, ...extras }
  if (texto !== null) arquivos['.claude/session-intent'] = texto
  // O engine entrega o caminho relativo já resolvido contra o diretório da sessão.
  const acha = (path: string) => {
    if (arquivos[path] !== undefined) return arquivos[path]
    const rel = Object.keys(arquivos).find(k => k.startsWith('.claude/') && path.endsWith(`/${k}`))
    return rel === undefined ? undefined : arquivos[rel]
  }
  on('fs.exists', async ($: any, e: any) => ({
    value: acha(e.path) !== undefined || e.path === '/repo/.claude/programs',
  }))
  on('fs.read', async ($: any, e: any) => ({ value: acha(e.path) }))
  on('fs.list', async () => ({
    value: ['zerada', 'cepa', 'velha', 'mods', 'maestro'].map(name => ({
      name, kind: 'dir', size: 0, mtimeMs: 0, isLink: false,
    })),
  }))
  on('process.run', async ($: any, e: any) => ({
    value: e.argv[0] === 'cepa-modos'
      ? { exitCode: 0, stdout: MODOS_JSON, stderr: '' }
      : { exitCode: 0, stdout: '/repo/.git\n', stderr: '' },
  }))
  on('session.id', async () => ({ value: sessao }))
  on('command.register', async () => ({ value: { command: 'compass' } }))
  on('ui.open', async () => ({ value: { isPlaced: true } }))
  on('session.start', async () => ({ cwd: '/repo' }))
  await $.session.start({ cwd: '/repo', surface: 'terminal', source: 'startup' })
  return { arquivos, relogio }
}

const monta = ($: any) =>
  $.ui.mount({
    plugin: 'compass',
    surface: 'terminal',
    component: 'Pane',
    requestId: 'compass',
    props: { title: 'Compass', isFocused: false, bodyColumns: 60, placement: 'dock' },
  })

const sobe = async ($: any, on: any, sessao: string, texto: string | null, extras: Record<string, string> = {}) => {
  await prepara($, on, sessao, texto, extras)
  return $.ui.mount({
    plugin: 'compass',
    surface: 'terminal',
    component: 'Pane',
    requestId: 'compass',
    props: { title: 'Compass', isFocused: false, bodyColumns: 60, placement: 'dock' },
  })
}

const MODOS_JSON = JSON.stringify({
  construcao: { saida: 'completion-auditor COMPLETE e proof-reviewer PROVEN', gate: 'x' },
  reforma: { saida: 'o orçamento declarado exaurido' },
})

const MODO = 'modo: construcao\nrotina: null\norcamento: null\naberto_em: 2026-10-19T13:46:36Z\n'

const DESVIOS = `# Desvios capturados

Texto de abertura com - [ ] no meio da linha, que não conta.

- [x] 2026-08-18 · modo: construcao · RESOLVIDO em 0.16.0
- [ ] 2026-08-23 · modo: descoberta · gate só enxerga new_string
  continuação da linha anterior
- [ ] 2026-09-27 · modo: exploracao · bash-path-lock lê sed -i errado
`

test('lê o modo e trata null como ausência', async () => {
  expect(parseModo(MODO)).toEqual({ nome: 'construcao', orcamento: '', abertoEm: '2026-10-19T13:46:36Z' })
  expect(parseModo('modo: reforma\norcamento: "só o filas.ts"\n')?.orcamento).toBe('só o filas.ts')
  expect(parseModo('modo: null\n')).toBe(null)
})

test('conta desvios abertos e resolvidos e guarda o quê do último', async () => {
  expect(contaDesvios(DESVIOS)).toEqual({ abertos: 2, resolvidos: 1, ultimo: 'bash-path-lock lê sed -i errado' })
  expect(contaDesvios('')).toEqual({ abertos: 0, resolvidos: 0, ultimo: '' })
})

test('saídas vêm do cepa-modos --json; json quebrado não derruba', async () => {
  expect(leSaidas(MODOS_JSON).construcao).toBe('completion-auditor COMPLETE e proof-reviewer PROVEN')
  expect(leSaidas('não é json')).toEqual({})
})

test('nível 3: modo, condição de saída e desvios, depois do nível 2', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, { '.claude/session-mode': MODO, '.claude/desvios.md': DESVIOS })
  expect(await ui.find({ type: 'Text', text: 'construcao' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'fecha quando: completion-auditor COMPLETE e proof-reviewer PROVEN' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '2 desvios abertos' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: ' · 1 resolvido' })).toBeTruthy()
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(textos.indexOf('Sessão') < textos.indexOf('Modo')).toBe(true)
})

test('nível 3 mostra o orçamento da reforma', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, { '.claude/session-mode': 'modo: reforma\norcamento: "só o filas.ts"\n' })
  expect(await ui.find({ type: 'Text', text: 'fecha quando: o orçamento declarado exaurido' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'orçamento: só o filas.ts' })).toBeTruthy()
})

test('sem modo e sem desvios, o nível 3 diz isso (com intenção)', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO)
  expect(await ui.find({ type: 'Text', text: 'sem modo' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'nenhum desvio registrado' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: /fecha quando/ })).toEqual([])
})

test('sem modo e sem desvios, o nível 3 diz isso (sem intenção)', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', null)
  expect(await ui.find({ type: 'Text', text: 'sem modo' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'nenhum desvio registrado' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: /fecha quando/ })).toEqual([])
})

test('desvio novo gera aviso; os que já existiam na abertura, não', async ($, on) => {
  const avisos: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  const { arquivos, relogio } = await prepara($, on, 'sessao-a', ARQUIVO, { '.claude/desvios.md': DESVIOS })
  await relogio.advance(5000)
  expect(avisos).toEqual([])
  arquivos['.claude/desvios.md'] = `${DESVIOS}- [ ] 2026-10-19 · modo: construcao · o mod não lê o build\n`
  await relogio.advance(5000)
  expect(avisos).toEqual(['Desvio registrado: o mod não lê o build'])
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: '3 desvios abertos' })).toBeTruthy()
})

test('nível 1: tabela com uma linha por fila e uma coluna por estado', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO)
  expect(await ui.find({ type: 'Text', text: 'Filas' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '2 abertas' })).toBeTruthy()
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  const linha = (nome: string) => textos.slice(textos.indexOf(nome), textos.indexOf(nome) + 6)
  expect(linha('fila')).toEqual(['fila', 'pend', 'and', 'bloq', 'feito', 'desc'])
  expect(linha('mods')).toEqual(['mods', '2', '1', '·', '1', '·'])
  expect(linha('cepa')).toEqual(['cepa', '·', '·', '1', '1', '1'])
  expect(linha('zerada')).toEqual(['zerada', '·', '·', '·', '1', '·'])
  expect(textos.filter((t: string) => /Item|▸|✗/.test(t))).toEqual([])
  expect(textos.filter((t: string) => /velha/.test(t))).toEqual([])
})

test('nível 1 vem antes do nível 2 e as abertas em ordem de itens abertos', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO)
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  const pos = (t: string) => textos.indexOf(t)
  expect(pos('Filas') < pos('mods')).toBe(true)
  expect(pos('mods') < pos('cepa')).toBe(true)
  expect(pos('cepa') < pos('Sessão')).toBe(true)
})

test('sem intenção, o nível 1 continua lá', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', null)
  expect(await ui.find({ type: 'Text', text: 'mods' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /ainda não tem intenção/ })).toBeTruthy()
})

test('painel marca feitos, o passo atual com a idade e os pendentes', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO)
  expect(await ui.find({ type: 'Text', text: '✓ guardar M2-M6 na fila mods' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '▶ ler exemplos e tipos do mod' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'há 12 min' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'passo 2/3' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'meta: painel aparece no terminal' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '○ escrever o mod e testes' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: /outra sessão/ })).toEqual([])
})

test('intenção de outra sessão pede confirmação', async ($, on) => {
  const ui = await sobe($, on, 'sessao-b', ARQUIVO)
  expect(await ui.find({ type: 'Text', text: /outra sessão \(2026-10-18\)/ })).toBeTruthy()
})

test('sem arquivo, diz que não há intenção', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', null)
  expect(await ui.find({ type: 'Text', text: /ainda não tem intenção/ })).toBeTruthy()
})

test('plano cumprido aponta o wrap-up', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO.replace('passo: 2', 'passo: 4'))
  expect(await ui.find({ type: 'Text', text: /Plano cumprido/ })).toBeTruthy()
})

test('no último passo o plano ainda não está cumprido', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO.replace('passo: 2', 'passo: 3'))
  expect(await ui.findAll({ type: 'Text', text: /Plano cumprido/ })).toEqual([])
})

test('colunas de número não encolhem quando o nome da fila é longo', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO)
  const caixas = (await ui.findAll({ type: 'Box' })).filter((b: any) => b.props?.width === 6)
  // cabeçalho + 3 filas single-track, 5 colunas cada
  expect(caixas.length).toBe(20)
  expect(caixas.every((b: any) => b.props.flexShrink === 0)).toBe(true)
})
