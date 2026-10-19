import { expect, mock, test } from 'claude-code/testing'

import { linhaBuild, parseBuild } from './build'
import { idade, parseIntent } from './intent'
import { contaDesvios, leSaidas, parseModo } from './modo'
import { avisoDe, contagem, duracao, parseRun, tempoDoRun } from './until'

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
  const dentro = (dir: string) => Object.keys(arquivos).filter(k => k.startsWith(`${dir}/`))
  on('fs.exists', async ($: any, e: any) => ({
    value: acha(e.path) !== undefined || e.path === '/repo/.claude/programs' || dentro(e.path).length > 0,
  }))
  on('fs.read', async ($: any, e: any) => ({ value: acha(e.path) }))
  on('fs.list', async ($: any, e: any) => ({
    value: e.path.endsWith('/until')
      ? dentro(e.path).map(k => ({ name: k.slice(e.path.length + 1), kind: 'file', size: 0, mtimeMs: 0, isLink: false }))
      : ['zerada', 'cepa', 'velha', 'mods', 'maestro'].map(name => ({
        name, kind: 'dir', size: 0, mtimeMs: 0, isLink: false,
      })),
  }))
  on('process.run', async ($: any, e: any) => ({
    value: e.argv[0] === 'cepa-modos'
      ? { exitCode: 0, stdout: e.argv.join(' ') === 'cepa-modos --json' ? MODOS_JSON : 'tabela em texto', stderr: '' }
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
  expect(contaDesvios('- [X] 2026-10-19 · modo: reforma · marcado em maiúscula\n').resolvidos).toBe(1)
})

test('saídas vêm do cepa-modos --json; json quebrado não derruba', async () => {
  expect(leSaidas(MODOS_JSON).construcao).toBe('completion-auditor COMPLETE e proof-reviewer PROVEN')
  expect(leSaidas('não é json')).toEqual({})
})

test('nível 3: modo, condição de saída e desvios, depois do nível 2', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, { '.claude/session-mode': MODO, '.claude/desvios.md': DESVIOS })
  expect(await ui.find({ type: 'Text', text: 'construcao' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'fecha quando: completion-auditor COMPLETE e proof-reviewer PROVEN' })).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: '2 desvios abertos' }))?.props?.color).toBe('yellow')
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
  expect(await ui.find({ type: 'Text', text: 'Esta sessão não declarou modo.' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'nenhum desvio registrado' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: /fecha quando/ })).toEqual([])
})

test('sem modo e sem desvios, o nível 3 diz isso (sem intenção)', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', null)
  expect(await ui.find({ type: 'Text', text: 'sem modo' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'nenhum desvio registrado' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: /fecha quando/ })).toEqual([])
})

test('singular para um desvio aberto e um resolvido', async ($, on) => {
  const um = '- [x] 2026-08-18 · modo: construcao · a\n- [ ] 2026-08-19 · modo: construcao · b\n'
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, { '.claude/desvios.md': um })
  expect(await ui.find({ type: 'Text', text: /^1 desvio aberto$/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /^ · 1 resolvido$/ })).toBeTruthy()
})

test('desvio novo que já nasce resolvido também gera aviso', async ($, on) => {
  const avisos: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  const { arquivos, relogio } = await prepara($, on, 'sessao-a', ARQUIVO, { '.claude/desvios.md': DESVIOS })
  arquivos['.claude/desvios.md'] = `${DESVIOS}- [x] 2026-10-19 · modo: construcao · resolvido na hora\n`
  await relogio.advance(5000)
  expect(avisos).toEqual(['Desvio registrado: resolvido na hora'])
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

const BUILD = (status: string, at: string, extra = '') => `{"status": "${status}", "at": "${at}", "command": "x", "kind": "pytest"${extra}}`

const BUILD_STALE = `{"status": "STALE", "since": "2026-10-19T10:09:00Z", "after_edit_to": "compass/hooks/register.tsx",
  "last_known_status": "FAILURE", "last_known_at": "2026-10-19T08:12:00Z", "last_known_command": "pytest"}`

test('parseBuild traduz os quatro status e guarda o anterior do STALE', async () => {
  const t = Date.parse('2026-10-19T10:12:00Z')
  expect(parseBuild(BUILD('SUCCESS', '2026-10-19T10:00:00Z'))).toEqual({ estado: 'verde', em: '2026-10-19T10:00:00Z', anterior: null, anteriorEm: '' })
  expect(parseBuild(BUILD('failure', '2026-10-19T10:00:00Z'))?.estado).toBe('vermelho')
  expect(parseBuild(BUILD('EMPTY', '2026-10-19T10:00:00Z', ', "tests_run": 0'))?.estado).toBe('vazio')
  expect(parseBuild(BUILD_STALE)).toEqual({ estado: 'desatualizado', em: '2026-10-19T10:09:00Z', anterior: 'vermelho', anteriorEm: '2026-10-19T08:12:00Z' })
  expect(parseBuild('{"status": "ALGO"}')?.estado).toBe('desconhecido')
  expect(parseBuild('{"status": "STALE"}')).toEqual({ estado: 'desatualizado', em: '', anterior: 'desconhecido', anteriorEm: '' })
  expect(parseBuild('não é json')).toBe(null)
  expect(parseBuild('null')).toBe(null)
  expect(parseBuild('[1]')?.estado).toBe('desconhecido')
  expect(linhaBuild(parseBuild(BUILD('SUCCESS', '2026-10-19T10:00:00Z'))!, t)).toBe('verde há 12 min')
  expect(linhaBuild(parseBuild(BUILD_STALE)!, t)).toBe('desatualizado há 3 min · era vermelho há 2 h')
  expect(linhaBuild(parseBuild('{"status": "STALE"}')!, t)).toBe('desatualizado')
  expect(linhaBuild(parseBuild('{"status": "SUCCESS"}')!, t)).toBe('verde')
})

test('nível 3: build verde com a idade, em verde', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, { '.claude/session-mode': MODO, '.claude/last-build.json': BUILD('SUCCESS', '2026-10-19T10:00:00Z') })
  const linha = await ui.find({ type: 'Text', text: 'verde há 12 min' })
  expect(linha?.props?.color).toBe('green')
  expect(linha?.props?.bold).toBeFalsy()
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(textos.indexOf('Modo') < textos.indexOf('verde há 12 min')).toBe(true)
})

test('nível 3: build vermelho em vermelho e negrito', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, { '.claude/last-build.json': BUILD('FAILURE', '2026-10-19T08:12:00Z') })
  const linha = await ui.find({ type: 'Text', text: 'vermelho há 2 h' })
  expect(linha?.props?.color).toBe('red')
  expect(linha?.props?.bold).toBe(true)
})

test('nível 3: build vazio em amarelo', async ($, on) => {
  const vazio = await sobe($, on, 'sessao-a', ARQUIVO, { '.claude/last-build.json': BUILD('EMPTY', '2026-10-19T10:00:00Z') })
  expect((await vazio.find({ type: 'Text', text: 'vazio há 12 min' }))?.props?.color).toBe('yellow')
})

test('nível 3: build desatualizado mostra o que era antes', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', null, { '.claude/last-build.json': BUILD_STALE })
  expect((await ui.find({ type: 'Text', text: 'desatualizado há 3 min · era vermelho há 2 h' }))?.props?.color).toBe('yellow')
})

test('sem last-build.json, o nível 3 diz que não há build registrado', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO)
  expect(await ui.find({ type: 'Text', text: 'nenhum registrado' })).toBeTruthy()
})

test('o build é relido a cada 5 s: o verde vira desatualizado sem novo turno', async ($, on) => {
  const { arquivos, relogio } = await prepara($, on, 'sessao-a', ARQUIVO, { '.claude/last-build.json': BUILD('SUCCESS', '2026-10-19T10:00:00Z') })
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: 'verde há 12 min' })).toBeTruthy()
  arquivos['.claude/last-build.json'] = BUILD_STALE
  await relogio.advance(5000)
  expect(await ui.find({ type: 'Text', text: 'desatualizado há 3 min · era vermelho há 2 h' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: 'verde há 12 min' })).toEqual([])
})

test('o build é relido no fim de cada turno, sem esperar o relógio', async ($, on) => {
  on('turn.complete', async () => ({ text: 'x' }))
  const { arquivos } = await prepara($, on, 'sessao-a', ARQUIVO, { '.claude/last-build.json': BUILD('SUCCESS', '2026-10-19T10:00:00Z') })
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: 'verde há 12 min' })).toBeTruthy()
  arquivos['.claude/last-build.json'] = BUILD_STALE
  await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer' })
  expect(await ui.find({ type: 'Text', text: 'desatualizado há 3 min · era vermelho há 2 h' })).toBeTruthy()
})

test('status desconhecido sai sem cor, e o rótulo "build:" fica ao lado do estado', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, { '.claude/last-build.json': '{"status": "ALGO", "at": "2026-10-19T10:00:00Z"}' })
  const linha = await ui.find({ type: 'Text', text: 'desconhecido há 12 min' })
  expect(linha?.props?.color).toBe(undefined)
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(textos.indexOf('build: ') + 1).toBe(textos.indexOf('desconhecido há 12 min'))
})

// ── nível 4: o run do cepa-until ─────────────────────────────────────────────

const ev = (e: Record<string, unknown>) => JSON.stringify(e) + '\n'
const RUN_START = ev({ evento: 'run_start', fila: 'cepa', prazo: '2026-10-19T18:00:00', quando: '2026-10-19T09:00:00' })
const CS1_START = ev({ evento: 'item_start', id: 'CS-1', title: 'primeiro item da fila', tentativa: 1, quando: '2026-10-19T09:00:05' })
const CS1_END = ev({ evento: 'item_end', id: 'CS-1', status: 'done', segundos: 300, quando: '2026-10-19T09:05:00' })
const CS1_VERDE = ev({ evento: 'verify', id: 'CS-1', verde: true, quando: '2026-10-19T09:15:00' })
const CS2_START = ev({ evento: 'item_start', id: 'CS-2', title: 'segundo item', tentativa: 2, quando: '2026-10-19T10:00:00' })
// O `quando` do cepa-until é hora local sem fuso. Os testes de render escrevem o
// instante relativo ao relógio dos testes (10:12Z) no fuso da máquina, e leem a hora
// esperada com a mesma conta, para não depender do fuso de quem roda a suíte.
const AGORA = Date.parse('2026-10-19T10:12:00Z')
const dois = (n: number) => String(n).padStart(2, '0')
const LOCAL = (minutosDepois: number) => {
  const d = new Date(AGORA + minutosDepois * 60000)
  return `${d.getFullYear()}-${dois(d.getMonth() + 1)}-${dois(d.getDate())}T${dois(d.getHours())}:${dois(d.getMinutes())}:${dois(d.getSeconds())}`
}
const HM = (minutosDepois: number) => LOCAL(minutosDepois).slice(11, 16)

test('parseRun: item atual, etapa de build, contagem e fim', async () => {
  const r = parseRun(RUN_START + CS1_START + CS1_END, 'cepa', '2026-10-19-0900')!
  expect(r.fase).toBe('rodando')
  expect(r.item).toEqual({ id: 'CS-1', titulo: 'primeiro item da fila', desde: '2026-10-19T09:05:00', tentativa: 1, etapa: 'build' })
  const r2 = parseRun(RUN_START + CS1_START + CS1_END + CS1_VERDE + CS2_START, 'cepa', 'x')!
  expect(r2.entregues).toBe(1)
  expect(r2.item?.id).toBe('CS-2')
  expect(r2.item?.tentativa).toBe(2)
  const fim = ev({ evento: 'run_end', motivo: 'fim-da-fila', detalhe: 'a fila acabou', quando: '2026-10-19T11:00:00' })
  const r3 = parseRun(RUN_START + CS1_START + CS1_END + CS1_VERDE + fim, 'cepa', 'x')!
  expect(r3.fase).toBe('encerrado')
  expect(r3.item).toBe(null)
  expect(r3.fim).toEqual({ motivo: 'fim-da-fila', detalhe: 'a fila acabou', quando: '2026-10-19T11:00:00' })
  expect(tempoDoRun(r3, 0)).toBe('2h00')
})

test('parseRun: vermelho, travado, pausa de cota e interrupção', async () => {
  const vermelho = ev({ evento: 'verify_vermelho', id: 'CS-1', quando: '2026-10-19T09:20:00' })
  const bloqueado = ev({ evento: 'item_end', id: 'CS-2', status: 'blocked', quando: '2026-10-19T10:30:00' })
  const pausa = ev({ evento: 'pausa_de_cota', uso: 0.9, acorda: '2026-10-19T14:35:00', quando: '2026-10-19T10:31:00' })
  const r = parseRun(RUN_START + CS1_START + CS1_END + vermelho + CS2_START + bloqueado + pausa, 'cepa', 'x')!
  expect(r.vermelhos).toBe(1)
  expect(r.travados).toBe(1)
  expect(r.fase).toBe('cota')
  expect(r.cota).toEqual({ retoma: '2026-10-19T14:35:00' })
  expect(contagem(r)).toBe('1 vermelho · 1 travado')
  const limite = ev({ evento: 'limite_de_uso', id: 'CS-2', reset_em: '2026-10-19T15:00:00', espera: true, quando: '2026-10-19T10:40:00' })
  const r2 = parseRun(RUN_START + CS2_START + limite, 'cepa', 'x')!
  expect(r2.fase).toBe('cota')
  expect(r2.cota).toEqual({ retoma: '2026-10-19T15:00:00' })
  const sinal = ev({ evento: 'run_interrompido', sinal: 'SIGTERM', id: 'CS-2', quando: '2026-10-19T10:50:00' })
  const r3 = parseRun(RUN_START + CS2_START + sinal, 'cepa', 'x')!
  expect(r3.fase).toBe('interrompido')
  expect(r3.fim?.motivo).toBe('interrompido')
  expect(parseRun('lixo\n' + CS2_START, 'cepa', 'x')).toBe(null)
})

test('duracao no formato do cepa-until', async () => {
  expect(duracao(0, 12 * 60000)).toBe('12min')
  expect(duracao(0, 83 * 60000)).toBe('1h23')
  expect(duracao(NaN, 1)).toBe('')
})

test('avisoDe: só na mudança de fase do mesmo run; fim e cota avisam', async () => {
  const rodando = parseRun(RUN_START + CS1_START, 'cepa', 'r1')!
  const fim = parseRun(RUN_START + CS1_START + CS1_END + CS1_VERDE + ev({ evento: 'run_end', motivo: 'prazo', detalhe: 'x', quando: '2026-10-19T11:00:00' }), 'cepa', 'r1')!
  const cota = parseRun(RUN_START + ev({ evento: 'pausa_de_cota', acorda: '2026-10-19T14:35:00', quando: '2026-10-19T10:31:00' }), 'cepa', 'r1')!
  expect(avisoDe(null, fim)).toBe(null)
  expect(avisoDe(rodando, rodando)).toBe(null)
  expect(avisoDe(fim, { ...fim, id: 'r2' })).toBe(null)
  expect(avisoDe(rodando, fim)).toBe('cepa-until cepa: prazo chegou · 1 entregue')
  expect(avisoDe(rodando, cota)).toBe('cepa-until parado pela cota · retoma às 14:35')
})

const UNTIL = (texto: string) => ({ '/repo/.claude/programs/cepa/until/2026-10-19-0900.jsonl': texto })

test('nível 4: item atual com tempo e tentativa, contagem e prazo, depois do nível 3', async ($, on) => {
  const inicio = ev({ evento: 'run_start', fila: 'cepa', prazo: LOCAL(8 * 60), quando: LOCAL(-72) })
  const item = ev({ evento: 'item_start', id: 'CS-2', title: 'segundo item', tentativa: 2, quando: LOCAL(-12) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(inicio + CS1_START + CS1_END + CS1_VERDE + item))
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(textos.indexOf('Modo')).toBeLessThan(textos.indexOf('Run'))
  expect(await ui.find({ type: 'Text', text: 'cepa · 1h12' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '▶ CS-2 · segundo item' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'item há 12min · tentativa 2' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: `1 entregue · prazo ${HM(8 * 60)}` })).toBeTruthy()
})

test('nível 4: run encerrado mostra o motivo em verde, a idade e a contagem sem prazo', async ($, on) => {
  const fim = ev({ evento: 'run_end', motivo: 'fim-da-fila', detalhe: 'a fila acabou', quando: LOCAL(-12) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + CS1_END + CS1_VERDE + fim))
  const texto = await ui.find({ type: 'Text', text: 'fila acabou há 12 min' })
  expect(texto).toBeTruthy()
  expect(texto.props.color).toBe('green')
  expect(await ui.find({ type: 'Text', text: 'a fila acabou' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '1 entregue' })).toBeTruthy()
})

test('nível 4: parado pela cota em amarelo, com a hora de retomar', async ($, on) => {
  const pausa = ev({ evento: 'pausa_de_cota', acorda: LOCAL(263), quando: LOCAL(-7) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + CS1_END + CS1_VERDE + pausa))
  const texto = await ui.find({ type: 'Text', text: `parado pela cota · retoma às ${HM(263)}` })
  expect(texto).toBeTruthy()
  expect(texto.props.color).toBe('yellow')
})

test('sem run, o nível 4 diz isso (com e sem intenção)', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO)
  expect(await ui.find({ type: 'Text', text: 'nenhum run do cepa-until' })).toBeTruthy()
})

test('sem intenção, o nível 4 continua lá', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', null)
  expect(await ui.find({ type: 'Text', text: 'nenhum run do cepa-until' })).toBeTruthy()
})

test('o run mais recente vence entre as filas', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, {
    ...UNTIL(RUN_START + CS1_START),
    '/repo/.claude/programs/mods/until/2026-10-19-1100.jsonl': ev({ evento: 'run_start', fila: 'mods', prazo: '', quando: LOCAL(-2) }),
  })
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
})

test('o fim do run avisa com toast e som, uma vez; a abertura com run já encerrado não avisa', async ($, on) => {
  const avisos: string[] = []
  const sons: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  on('audio.play', async ($: any, e: any) => {
    sons.push(e.clip.asset)
    return { value: undefined }
  })
  const caminho = '/repo/.claude/programs/cepa/until/2026-10-19-0900.jsonl'
  const { arquivos, relogio } = await prepara($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + CS1_END))
  await relogio.advance(5000)
  expect(avisos).toEqual([])
  arquivos[caminho] += CS1_VERDE + ev({ evento: 'run_end', motivo: 'limite-de-uso', detalhe: 'x', quando: LOCAL(-1) })
  await relogio.advance(5000)
  expect(avisos).toEqual(['cepa-until cepa: parou pela cota · 1 entregue'])
  expect(sons).toEqual(['sons/fim.wav'])
  await relogio.advance(5000)
  expect(sons).toEqual(['sons/fim.wav'])
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: 'parou pela cota há 1 min' })).toBeTruthy()
})

test('a pausa pela cota avisa com som; a retomada não', async ($, on) => {
  const avisos: string[] = []
  const sons: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  on('audio.play', async ($: any, e: any) => {
    sons.push(e.clip.asset)
    return { value: undefined }
  })
  const caminho = '/repo/.claude/programs/cepa/until/2026-10-19-0900.jsonl'
  const { arquivos, relogio } = await prepara($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + CS1_END + CS1_VERDE))
  arquivos[caminho] += ev({ evento: 'pausa_de_cota', acorda: LOCAL(263), quando: LOCAL(-1) })
  await relogio.advance(5000)
  expect(avisos).toEqual([`cepa-until parado pela cota · retoma às ${HM(263)}`])
  expect(sons.length).toBe(1)
  arquivos[caminho] += CS2_START
  await relogio.advance(5000)
  expect(avisos.length).toBe(1)
  expect(sons.length).toBe(1)
})

test('um run novo que começa depois da abertura é lido na próxima varredura das filas', async ($, on) => {
  const { arquivos, relogio } = await prepara($, on, 'sessao-a', ARQUIVO)
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: 'nenhum run do cepa-until' })).toBeTruthy()
  Object.assign(arquivos, UNTIL(RUN_START + CS1_START))
  await relogio.advance(30000)
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
})

test('nível 4: depois do done o item fica na etapa de build, sem tentativa quando é a primeira', async ($, on) => {
  const item = ev({ evento: 'item_start', id: 'CS-1', title: 'primeiro item da fila', tentativa: 1, quando: LOCAL(-20) })
  const fim = ev({ evento: 'item_end', id: 'CS-1', status: 'done', quando: LOCAL(-9) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + item + fim))
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'build há 9min' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'nada entregue ainda · prazo 18:00' })).toBeTruthy()
})

test('abrir a sessão com um run já encerrado não avisa, nem no relógio de 5 s, nem no de 30 s', async ($, on) => {
  const avisos: string[] = []
  const sons: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  on('audio.play', async ($: any, e: any) => {
    sons.push(e.clip.asset)
    return { value: undefined }
  })
  const fim = ev({ evento: 'run_end', motivo: 'fim-da-fila', detalhe: 'a fila acabou', quando: LOCAL(-12) })
  const { relogio } = await prepara($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + CS1_END + CS1_VERDE + fim))
  await relogio.advance(5000)
  await relogio.advance(30000)
  expect(avisos).toEqual([])
  expect(sons).toEqual([])
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: 'fila acabou há 12 min' })).toBeTruthy()
})
