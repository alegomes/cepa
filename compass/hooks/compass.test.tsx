import { expect, mock, test } from 'claude-code/testing'

import { linhaBuild, parseBuild } from './build'
import { idade, parseIntent } from './intent'
import { contaDesvios, leSaidas, parseModo } from './modo'
import { avisoDe, contagem, duracao, hora, parseRun, rotuloDoFim, tempoDoRun } from './until'
import { leBloqueio, leGuarda } from './gate'
import { contaFila } from './filas'
import { estadoDoCiclo, filaDoCiclo, linhaDoCiclo, parseEpic } from './epics'

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
  on('fs.list', async ($: any, e: any) => {
    // `.claude/queues` lista só as pastas que de fato têm arquivo (como o fs real);
    // o resto da lista abaixo é fixa e serve a `.claude/programs`.
    if (e.path.endsWith('/.claude/queues')) {
      const nomes = [...new Set(dentro(e.path).map(k => k.slice(e.path.length + 1).split('/')[0]))]
      return { value: nomes.map(name => ({ name, kind: 'dir', size: 0, mtimeMs: 0, isLink: false })) }
    }
    if (!e.path.endsWith('/until') && !e.path.endsWith('/docs/epics')) {
      return {
        value: ['zerada', 'cepa', 'velha', 'mods', 'maestro', 'cepa-espiral-c1', 'outro-c1'].map(name => ({
          name, kind: 'dir', size: 0, mtimeMs: 0, isLink: false,
        })),
      }
    }
    // Como o fs real: listar pasta que não existe é erro, não lista vazia.
    if (dentro(e.path).length === 0) throw new Error(`ENOENT: ${e.path}`)
    return {
      value: dentro(e.path).map(k => ({ name: k.slice(e.path.length + 1), kind: 'file', size: 0, mtimeMs: 0, isLink: false })),
    }
  })
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

test('nível 1 lê .claude/queues/<n>/queue.yaml; nome nos dois layouts, o novo ganha e aparece uma vez', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, {
    // `mods` existe nos dois layouts (programs: 2 pend, 1 and, 1 feito); `maestro` só no novo.
    '/repo/.claude/queues/mods/queue.yaml': FILA('single-track', ['pending']),
    '/repo/.claude/queues/maestro/queue.yaml': FILA('single-track', ['done', 'done', 'blocked']),
  })
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  const linha = (nome: string) => textos.slice(textos.indexOf(nome), textos.indexOf(nome) + 6)
  expect(linha('mods')).toEqual(['mods', '1', '·', '·', '·', '·'])
  expect(linha('maestro')).toEqual(['maestro', '·', '·', '1', '2', '·'])
  expect(linha('cepa')).toEqual(['cepa', '·', '·', '1', '1', '1'])
  expect(textos.filter((t: string) => t === 'mods')).toHaveLength(1)
  expect(textos.filter((t: string) => t === 'maestro')).toHaveLength(1)
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

// `find` casa por trecho; `exato` exige o texto inteiro.
const exato = async (ui: any, texto: string) => {
  const n = await ui.find({ type: 'Text', text: texto })
  return n && n.text === texto ? n : undefined
}

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
  // Uma segunda pausa, depois da retomada, avisa de novo: o estado não ficou preso na cota.
  arquivos[caminho] += ev({ evento: 'pausa_de_cota', acorda: LOCAL(400), quando: LOCAL(0) })
  await relogio.advance(5000)
  expect(avisos).toEqual([
    `cepa-until parado pela cota · retoma às ${HM(263)}`,
    `cepa-until parado pela cota · retoma às ${HM(400)}`,
  ])
  expect(sons.length).toBe(2)
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
  expect(await exato(ui, 'build há 9min')).toBeTruthy()
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

// ── nível 4: perturbações sobreviventes da 1ª rodada do proof-reviewer ───────

test('parseRun: item bloqueado ou devolvido sai da tela; verify vermelho não conta entrega', async () => {
  const bloqueado = ev({ evento: 'item_end', id: 'CS-1', status: 'blocked', quando: '2026-10-19T09:05:00' })
  const r = parseRun(RUN_START + CS1_START + bloqueado, 'cepa', 'x')!
  expect(r.fase).toBe('rodando')
  expect(r.item).toBe(null)
  expect(r.travados).toBe(1)
  const devolvido = ev({ evento: 'item_end', id: 'CS-1', status: 'pending', quando: '2026-10-19T09:05:00' })
  expect(parseRun(RUN_START + CS1_START + devolvido, 'cepa', 'x')!.item).toBe(null)
  const vermelho = ev({ evento: 'verify', id: 'CS-1', verde: false, motivo: 'saiu 1', quando: '2026-10-19T09:15:00' })
  const r2 = parseRun(RUN_START + CS1_START + CS1_END + vermelho, 'cepa', 'x')!
  expect(r2.entregues).toBe(0)
  expect(r2.item?.etapa).toBe('build')
  const r3 = parseRun(RUN_START + CS1_START + CS1_END + CS1_VERDE, 'cepa', 'x')!
  expect(r3.item).toBe(null)
  const separado = ev({ evento: 'verify_vermelho', id: 'CS-1', quando: '2026-10-19T09:20:00' })
  const r4 = parseRun(RUN_START + CS1_START + CS1_END + vermelho + separado, 'cepa', 'x')!
  expect(r4.item).toBe(null)
  expect(r4.vermelhos).toBe(1)
})

test('parseRun: limite de uso sem espera não é pausa; interrupção guarda o sinal', async () => {
  const limite = ev({ evento: 'limite_de_uso', id: 'CS-1', reset_em: '2026-10-19T15:00:00', espera: false, quando: '2026-10-19T10:40:00' })
  const r = parseRun(RUN_START + CS1_START + limite, 'cepa', 'x')!
  expect(r.fase).toBe('rodando')
  expect(r.cota).toBe(null)
  expect(r.item?.id).toBe('CS-1')
  const sinal = ev({ evento: 'run_interrompido', sinal: 'SIGTERM', id: 'CS-1', quando: '2026-10-19T10:50:00' })
  const r2 = parseRun(RUN_START + CS1_START + sinal, 'cepa', 'x')!
  expect(r2.fim).toEqual({ motivo: 'interrompido', detalhe: 'sinal SIGTERM', quando: '2026-10-19T10:50:00' })
})

test('duracao arredonda para baixo, não fica negativa e completa os minutos com zero', async () => {
  expect(duracao(0, 59 * 1000)).toBe('0min')
  expect(duracao(0, 59_500)).toBe('0min')
  expect(duracao(0, 3_599_900)).toBe('59min')
  expect(duracao(0, 3599 * 1000)).toBe('59min')
  expect(duracao(0, 3600 * 1000)).toBe('1h00')
  expect(duracao(0, 3661 * 1000)).toBe('1h01')
  expect(duracao(0, (2 * 3600 + 59 * 60 + 59) * 1000)).toBe('2h59')
  expect(duracao(10_000, 0)).toBe('0min')
  expect(duracao(0, NaN)).toBe('')
})

test('hora completa com zero e devolve vazio para texto que não é data', async () => {
  expect(hora('2026-10-19T09:05:00')).toBe('09:05')
  expect(hora('2026-10-19T23:59:30')).toBe('23:59')
  expect(hora('')).toBe('')
  expect(hora('ontem')).toBe('')
})

test('rotuloDoFim traduz o que conhece e repete o resto', async () => {
  expect(rotuloDoFim('fim-da-fila')).toBe('fila acabou')
  expect(rotuloDoFim('limite-de-uso')).toBe('parou pela cota')
  expect(rotuloDoFim('prazo')).toBe('prazo chegou')
  expect(rotuloDoFim('xpto')).toBe('xpto')
})

test('avisoDe: run diferente em fase diferente não avisa; cota sem hora avisa sem a hora', async () => {
  const rodando = parseRun(RUN_START + CS1_START, 'cepa', 'r1')!
  const fimOutro = parseRun(RUN_START + ev({ evento: 'run_end', motivo: 'prazo', detalhe: 'x', quando: '2026-10-19T11:00:00' }), 'cepa', 'r2')!
  expect(avisoDe(rodando, fimOutro)).toBe(null)
  const cotaSemHora = parseRun(RUN_START + ev({ evento: 'pausa_de_cota', quando: '2026-10-19T10:31:00' }), 'cepa', 'r1')!
  expect(avisoDe(rodando, cotaSemHora)).toBe('cepa-until parado pela cota')
  const semEntrega = parseRun(RUN_START + ev({ evento: 'run_end', motivo: 'disjuntor', detalhe: 'x', quando: '2026-10-19T11:00:00' }), 'cepa', 'r1')!
  expect(avisoDe(rodando, semEntrega)).toBe('cepa-until cepa: disjuntor')
})

test('nível 4: item travado sai da tela, conta como travado e o run segue entre itens', async ($, on) => {
  const bloqueado = ev({ evento: 'item_end', id: 'CS-1', status: 'blocked', quando: LOCAL(-9) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + bloqueado))
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
  expect(await exato(ui, '1 travado · prazo 18:00')).toBeTruthy()
})

test('nível 4: depois do build verde o item sai da tela e a entrega conta', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + CS1_END + CS1_VERDE))
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
  expect(await exato(ui, '1 entregue · prazo 18:00')).toBeTruthy()
})

test('nível 4: build vermelho não conta entrega, e o item ainda está no build até o verify_vermelho', async ($, on) => {
  const vermelho = ev({ evento: 'verify', id: 'CS-1', verde: false, motivo: 'saiu 1', quando: LOCAL(-3) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + CS1_END + vermelho))
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
  expect(await exato(ui, 'nada entregue ainda · prazo 18:00')).toBeTruthy()
})

test('nível 4: depois do verify_vermelho o item sai da tela e conta como vermelho', async ($, on) => {
  const vermelho = ev({ evento: 'verify', id: 'CS-1', verde: false, motivo: 'saiu 1', quando: LOCAL(-3) })
  const separado = ev({ evento: 'verify_vermelho', id: 'CS-1', quando: LOCAL(-3) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + CS1_END + vermelho + separado))
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await exato(ui, '1 vermelho · prazo 18:00')).toBeTruthy()
})

test('nível 4: parado pela cota não mostra o item; cota sem hora fica só "parado pela cota"', async ($, on) => {
  const pausa = ev({ evento: 'pausa_de_cota', acorda: LOCAL(263), quando: LOCAL(-7) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + pausa))
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
  expect(await ui.findAll({ type: 'Text', text: 'entre itens' })).toEqual([])
})

test('nível 4: cota sem hora de retomar fica só "parado pela cota"', async ($, on) => {
  const semHora = ev({ evento: 'pausa_de_cota', quando: LOCAL(-7) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + semHora))
  expect(await exato(ui, 'parado pela cota')).toBeTruthy()
})

test('nível 4: limite de uso sem espera não vira pausa', async ($, on) => {
  const limite = ev({ evento: 'limite_de_uso', id: 'CS-1', reset_em: LOCAL(300), espera: false, quando: LOCAL(-5) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + limite))
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: 'parado pela cota' })).toEqual([])
})

test('nível 4: run encerrado não mostra "entre itens" nem o prazo; motivo desconhecido sai em vermelho', async ($, on) => {
  const fim = ev({ evento: 'run_end', motivo: 'xpto', detalhe: 'coisa nova', quando: LOCAL(-12) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START + CS1_END + CS1_VERDE + fim))
  const motivo = await ui.find({ type: 'Text', text: 'xpto há 12 min' })
  expect(motivo).toBeTruthy()
  expect(motivo.props.color).toBe('red')
  expect(await ui.findAll({ type: 'Text', text: 'entre itens' })).toEqual([])
  expect(await exato(ui, '1 entregue')).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: 'prazo 18:00' })).toEqual([])
})

test('nível 4: run interrompido mostra o sinal e o tempo congela no fim', async ($, on) => {
  const inicio = ev({ evento: 'run_start', fila: 'cepa', prazo: LOCAL(8 * 60), quando: LOCAL(-72) })
  const sinal = ev({ evento: 'run_interrompido', sinal: 'SIGTERM', id: 'CS-1', quando: LOCAL(-12) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(inicio + CS1_START + sinal))
  expect(await ui.find({ type: 'Text', text: 'interrompido há 12 min' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'sinal SIGTERM' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'cepa · 1h00' })).toBeTruthy()
})

test('nível 4: run sem prazo não mostra "prazo"', async ($, on) => {
  const inicio = ev({ evento: 'run_start', fila: 'cepa', prazo: '', quando: LOCAL(-72) })
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(inicio + CS1_START))
  expect(await exato(ui, 'nada entregue ainda')).toBeTruthy()
})

test('só .jsonl conta como run, e o mais novo vence mesmo listado primeiro', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, {
    '/repo/.claude/programs/cepa/until/2026-10-19-1100.jsonl': ev({ evento: 'run_start', fila: 'cepa', prazo: '', quando: LOCAL(-2) }),
    '/repo/.claude/programs/cepa/until/2026-10-19-1100.log': 'log do run',
    '/repo/.claude/programs/cepa/until/2026-10-19-1200.review.md': RUN_START + CS1_START,
    ...UNTIL(RUN_START + CS1_START),
  })
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
})

test('um run novo que começa e acaba entre duas varreduras não avisa', async ($, on) => {
  const avisos: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  const { arquivos, relogio } = await prepara($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START))
  await relogio.advance(5000)
  arquivos['/repo/.claude/programs/mods/until/2026-10-19-1200.jsonl'] =
    ev({ evento: 'run_start', fila: 'mods', prazo: '', quando: LOCAL(-2) })
    + ev({ evento: 'run_end', motivo: 'fim-da-fila', detalhe: 'x', quando: LOCAL(-1) })
  await relogio.advance(30000)
  expect(avisos).toEqual([])
})

test('o run é relido a cada 5 s e as filas a cada 30 s, não antes', async ($, on) => {
  const { arquivos, relogio } = await prepara($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + CS1_START))
  const ui = await monta($)
  arquivos['/repo/.claude/programs/cepa/until/2026-10-19-0900.jsonl'] += CS1_END + CS1_VERDE
  await relogio.advance(4000)
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
  await relogio.advance(1000)
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  arquivos['/repo/.claude/programs/mods/until/2026-10-19-1200.jsonl'] = ev({ evento: 'run_start', fila: 'mods', prazo: '', quando: LOCAL(-2) })
  await relogio.advance(24000)
  expect(await ui.findAll({ type: 'Text', text: 'mods · 2min' })).toEqual([])
  await relogio.advance(1000)
  expect(await ui.find({ type: 'Text', text: 'mods · 2min' })).toBeTruthy()
})

test('nível 4: item na primeira tentativa não mostra "tentativa"', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, UNTIL(RUN_START + ev({ evento: 'item_start', id: 'CS-1', title: 'primeiro item da fila', tentativa: 1, quando: LOCAL(-12) })))
  expect(await exato(ui, 'item há 12min')).toBeTruthy()
})

test('parseRun aguenta registro malformado: linha null, run_start sem fila, item_end sem item_start', async () => {
  const r = parseRun(RUN_START + 'null\n' + CS1_START, 'cepa', 'x')!
  expect(r.item?.id).toBe('CS-1')
  const semFila = ev({ evento: 'run_start', prazo: '', quando: '2026-10-19T09:00:00' })
  expect(parseRun(semFila, 'mods', 'x')!.fila).toBe('mods')
  const orfao = ev({ evento: 'item_end', id: 'CS-9', status: 'done', quando: '2026-10-19T09:05:00' })
  expect(parseRun(RUN_START + orfao, 'cepa', 'x')!.item).toBe(null)
})

// ─── Aviso de gate ───────────────────────────────────────────────────────────

const GA_BASELINE = `[gate-advance] BLOCKED: sharing operation requires a build baseline.
  Command: git push
  No .claude/last-build.json found — no build has been verified at
  this project yet.`
const GA_STALE = `[gate-advance] BLOCKED: cannot run advancement command — build is STALE since edit to src/a.py at 2026-10-19T10:00:00 (0 day(s) ago).
  Command: git commit -m x
  Suggestion: Run your project's verify command.`
const GA_EMPTY = `[gate-advance] BLOCKED: cannot run advancement command — build is EMPTY since 2026-10-19T10:00:00: the test filter in \`pytest -k nada\` matched zero tests — it exited green, but no test ran, so it proves nothing.`
const GA_FAIL = `[gate-advance] BLOCKED: cannot run advancement command — build is FAILURE since 2026-10-19T10:00:00 (command: \`pytest\`).
  Suggestion: Fix the failing tests / build errors, re-run the verify command, and try again.`
const GA_PARADO = `[gate-advance] BLOCKED: cannot run advancement command — build is FAILURE since 2026-10-19T10:00:00 (command: \`pytest\`): stopped by claude-code.
  Suggestion: The build did not fail — it was stopped before it ended. Re-run it with a \`timeout\` that fits it.`
const GA_OUTRO = `[gate-advance] BLOCKED: cannot run advancement command — build status is 'X' — unrecognized.`
const AG_DONE = `[acceptance-gate] BLOCKED: cannot move WEGO-1891 to done — no acceptance audit found
  Searched:
    - /repo/.claude/acceptance/WEGO-1891.yaml`
const AG_REVIEW = `[acceptance-gate] BLOCKED: cannot move WEGO-2202 to review — acceptance audit is 'incomplete', not 'complete'.
  Artifact: /repo/.claude/acceptance/WEGO-2202.yaml`
const AG_EMPTY = `[acceptance-gate] BLOCKED: cannot move WEGO-2218 to done — the last real build is EMPTY: the test filter in \`pytest -k x\` matched zero tests (recorded 2026-10-19 in /repo/.claude/last-build.json).`
const WG_SRC = `BLOCK: 1
  source \`session/oncoto\` is held by a LIVE session — mac:/repo (active 2 min ago)
    its history may be rewritten under you; ask it to land or close first.`
const WG_AMBOS = `BLOCK: 2
  source \`session/oncoto\` is held by a LIVE session — mac:/repo (active 2 min ago)
  destination \`main\` is held by a LIVE session — mac:/repo2 (active 1 min ago)`

test('leBloqueio traduz cada motivo do gate-advance em uma frase leiga', async () => {
  expect(leBloqueio(GA_BASELINE)).toEqual({
    gate: 'gate-advance',
    frase: 'Compartilhar barrado: nenhum build foi verificado neste projeto ainda. Rode o verify do projeto antes.',
  })
  expect(leBloqueio(GA_STALE)?.frase).toBe('Barrado: o código mudou depois do último build (src/a.py). Rode o verify de novo.')
  expect(leBloqueio(GA_EMPTY)?.frase).toBe('Barrado: o último build passou sem rodar teste nenhum. Corrija o filtro de testes e rode de novo.')
  expect(leBloqueio(GA_FAIL)?.frase).toBe('Barrado: o último build falhou. Conserte e rode o verify de novo.')
  expect(leBloqueio(GA_PARADO)?.frase).toBe('Barrado: o último build foi interrompido antes de acabar. Rode de novo com tempo suficiente.')
  expect(leBloqueio(GA_OUTRO)?.frase).toBe('Barrado pelo gate-advance: o build não está verde.')
})

test('leBloqueio traduz o acceptance-gate com a chave do card', async () => {
  expect(leBloqueio(AG_DONE)).toEqual({
    gate: 'acceptance-gate',
    frase: 'WEGO-1891 barrado: não vai para Done sem a auditoria do completion-auditor.',
  })
  expect(leBloqueio(AG_REVIEW)?.frase).toBe(
    "WEGO-2202 barrado: a auditoria de aceite está 'incomplete', não completa. Feche as lacunas e rode o completion-auditor de novo.",
  )
  expect(leBloqueio(AG_EMPTY)?.frase).toBe('WEGO-2218 barrado: o último build não rodou teste nenhum, então não prova nada.')
  expect(leBloqueio('[acceptance-gate] BLOCKED: algo novo')?.frase).toBe('O card barrado pelo acceptance-gate.')
})

test('leBloqueio ignora erro que não é gate; o aviso de commit sem baseline não é bloqueio', async () => {
  expect(leBloqueio('Error: command not found: foo')).toBe(null)
  expect(leBloqueio('⚠  COMMIT WITHOUT BUILD VERIFICATION ⚠ ... will be BLOCKED until')).toBe(null)
  expect(leBloqueio('')).toBe(null)
})

test('leGuarda só lê stdout de Bash que chamou o worktree-guard e começa com BLOCK:', async () => {
  const cmd = 'python3 "/x/hooks/worktree-guard.py" session/oncoto'
  expect(leGuarda(cmd, WG_SRC)).toEqual({
    gate: 'worktree-guard',
    frase: 'Merge barrado: a branch session/oncoto está em uso por outra sessão viva. Peça para ela fechar ou aterrissar antes.',
  })
  expect(leGuarda(cmd, WG_AMBOS)?.frase).toBe(
    'Merge barrado: as branches session/oncoto e main estão em uso por outra sessão viva. Peça para ela fechar ou aterrissar antes.',
  )
  expect(leGuarda(cmd, 'BLOCK: 1\n  (detalhe fora do formato)')?.frase).toBe(
    'Merge barrado: outra sessão viva está na branch. Peça para ela fechar ou aterrissar antes.',
  )
  expect(leGuarda(cmd, 'OK\nNo other live session')).toBe(null)
  expect(leGuarda('cat registro.txt', WG_SRC)).toBe(null)
  expect(leGuarda(cmd, 'aviso: BLOCK: 1')).toBe(null)
})

// O deny do hook Python chega ao tool.call do mod como resultado com erro e o motivo em text.
const barraComoPython = (on: any, motivo: string) => {
  on('classic.PreToolUse', async () => ({ deny: motivo }))
}

test('gate-advance barra o push: toast com a frase leiga e linha no cartão Modo', async ($, on) => {
  const avisos: any[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e)
    return { value: undefined }
  })
  barraComoPython(on, GA_BASELINE)
  await prepara($, on, 'sessao-a', ARQUIVO, { '.claude/session-mode': MODO })
  const r: any = await $.tool.call({ tool: 'Bash', command: 'git push' })
  expect(r.isError).toBe(true)
  expect(r.text).toBe(GA_BASELINE)
  expect(avisos.map(a => a.text)).toEqual([
    'Compartilhar barrado: nenhum build foi verificado neste projeto ainda. Rode o verify do projeto antes.',
  ])
  expect(avisos[0].timeoutMs).toBe(8000)
  const ui = await monta($)
  const frase = await ui.find({ type: 'Text', text: 'Compartilhar barrado: nenhum build foi verificado neste projeto ainda. Rode o verify do projeto antes.' })
  expect(frase?.props?.color).toBe('yellow')
  expect(await ui.find({ type: 'Text', text: 'gate-advance há 0 min' })).toBeTruthy()
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(textos.indexOf('Modo') < textos.indexOf('gate-advance há 0 min')).toBe(true)
  expect(textos.indexOf('gate-advance há 0 min') < textos.indexOf('Run')).toBe(true)
})

test('acceptance-gate barra a transição no Jira (MCP): toast com a chave do card', async ($, on) => {
  const avisos: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  barraComoPython(on, AG_REVIEW)
  await prepara($, on, 'sessao-a', ARQUIVO)
  const r: any = await $.tool.call({
    tool: 'mcp__Atlassian__transitionJiraIssue',
    cloudId: 'c', issueIdOrKey: 'WEGO-2202', transition: { id: '31' },
  } as any)
  expect(r.isError).toBe(true)
  expect(avisos).toEqual([
    "WEGO-2202 barrado: a auditoria de aceite está 'incomplete', não completa. Feche as lacunas e rode o completion-auditor de novo.",
  ])
})

test('worktree-guard imprime BLOCK: no stdout de um Bash que saiu com 0: toast, e o resultado volta igual', async ($, on) => {
  const avisos: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  const resposta = { result: { stdout: WG_SRC, stderr: '', interrupted: false } }
  on('tool.call', { tool: 'Bash' }, async () => resposta)
  await prepara($, on, 'sessao-a', ARQUIVO)
  const r: any = await $.tool.call({ tool: 'Bash', command: 'python3 "/x/hooks/worktree-guard.py" session/oncoto' })
  expect(r.result).toEqual(resposta.result)
  expect(r.deny).toBe(undefined)
  expect(avisos).toEqual([
    'Merge barrado: a branch session/oncoto está em uso por outra sessão viva. Peça para ela fechar ou aterrissar antes.',
  ])
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: 'worktree-guard há 0 min' })).toBeTruthy()
})

test('worktree-guard com OK, Bash comum e erro que não é gate: nem toast nem linha no cartão', async ($, on) => {
  const avisos: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  let proibe = false
  on('classic.PreToolUse', async () => (proibe ? { deny: 'Error: this command is forbidden by another plugin' } : {}))
  on('tool.call', { tool: 'Bash' }, async ($: any, e: any) =>
    e.command.includes('worktree-guard')
      ? { result: { stdout: 'OK\nNo other live session is on `session/x` — safe to merge.', stderr: '', interrupted: false } }
      : { result: { stdout: 'BLOCK: 1\nisto é só a saída de um cat', stderr: '', interrupted: false } })
  await prepara($, on, 'sessao-a', ARQUIVO)
  await $.tool.call({ tool: 'Bash', command: 'python3 "/x/hooks/worktree-guard.py" session/x' })
  await $.tool.call({ tool: 'Bash', command: 'cat registro.txt' })
  proibe = true
  const r: any = await $.tool.call({ tool: 'Bash', command: 'rm -rf x' })
  expect(r.isError).toBe(true)
  expect(avisos).toEqual([])
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: /bloqueio|barrad/ })).toBeFalsy()
})

test('segundo bloqueio substitui o primeiro no cartão e conta as vezes; a idade cresce com o relógio', async ($, on) => {
  const avisos: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  let motivo = GA_STALE
  on('classic.PreToolUse', async () => ({ deny: motivo }))
  const { relogio } = await prepara($, on, 'sessao-a', ARQUIVO)
  await $.tool.call({ tool: 'Bash', command: 'git commit -m x' })
  motivo = AG_DONE
  await $.tool.call({ tool: 'mcp__Atlassian__transitionJiraIssue', transition: { id: '41' } } as any)
  expect(avisos).toEqual([
    'Barrado: o código mudou depois do último build (src/a.py). Rode o verify de novo.',
    'WEGO-1891 barrado: não vai para Done sem a auditoria do completion-auditor.',
  ])
  await relogio.advance(3 * 60000)
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: 'WEGO-1891 barrado: não vai para Done sem a auditoria do completion-auditor.' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /o código mudou/ })).toBeFalsy()
  expect(await ui.find({ type: 'Text', text: 'acceptance-gate há 3 min · 2º bloqueio da sessão' })).toBeTruthy()
})

test('sem bloqueio na sessão, o cartão Modo não tem a linha do gate', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, { '.claude/session-mode': MODO })
  expect(await ui.find({ type: 'Text', text: /bloqueio|barrad/ })).toBeFalsy()
})

// ─── Sobreviventes da 1ª rodada do proof-reviewer ────────────────────────────

test('toast que lança não atrapalha a chamada: o resultado do gate volta intacto', async ($, on) => {
  on('ui.toast', async () => {
    throw new Error('sem tela')
  })
  barraComoPython(on, GA_BASELINE)
  await prepara($, on, 'sessao-a', ARQUIVO)
  const r: any = await $.tool.call({ tool: 'Bash', command: 'git push' })
  expect(r.isError).toBe(true)
  expect(r.text).toBe(GA_BASELINE)
})

test('STALE sem o arquivo da edição sai sem parênteses', async () => {
  expect(leBloqueio('[gate-advance] BLOCKED: cannot run advancement command — build is STALE.')?.frase)
    .toBe('Barrado: o código mudou depois do último build. Rode o verify de novo.')
})

test('leGuarda: linha em branco antes do BLOCK: conta; BLOCK: sem número ou sem espaço não conta', async () => {
  const cmd = 'python3 "/x/hooks/worktree-guard.py" session/x'
  expect(leGuarda(cmd, '\n\n' + WG_SRC)?.gate).toBe('worktree-guard')
  expect(leGuarda(cmd, 'BLOCK: abc\n  source `session/x` is held by a LIVE session')).toBe(null)
  expect(leGuarda(cmd, 'BLOCK:1\n  source `session/x` is held by a LIVE session')).toBe(null)
})

test('stdout com BLOCK: de uma ferramenta que não é Bash não é o worktree-guard', async ($, on) => {
  const avisos: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  on('tool.call', { tool: 'mcp__x__run' }, async () => ({ result: { stdout: WG_SRC, stderr: '' } }))
  await prepara($, on, 'sessao-a', ARQUIVO)
  await $.tool.call({ tool: 'mcp__x__run', command: 'python3 worktree-guard.py session/x' } as any)
  expect(avisos).toEqual([])
})

test('resultado sem erro cujo texto cita o gate-advance não é bloqueio', async ($, on) => {
  const avisos: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    avisos.push(e.text)
    return { value: undefined }
  })
  on('tool.call', { tool: 'Bash' }, async () => ({
    result: { stdout: GA_BASELINE, stderr: '', interrupted: false },
    text: GA_BASELINE,
  }))
  await prepara($, on, 'sessao-a', ARQUIVO)
  await $.tool.call({ tool: 'Bash', command: 'cat registro-do-gate.txt' })
  expect(avisos).toEqual([])
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: /barrad/ })).toBeFalsy()
})

// ── nível 0: os Epics e o estado da fila de cada ciclo ───────────────────────

const EPIC = `# Epic: Cepa em espiral

**Status:** rascunho · **Aberto em:** 2026-10-08 · **Origem:** docs/estrategia.md
**Repositório:** cepa · **Construção:** filas \`single-track\` em \`.claude/programs/cepa-espiral-c<N>/plan.yaml\`, uma por ciclo · **Aceite:** o roteiro.

## Intenção

Prosa.

## Escada de valor

| Ciclo | Roteiro de demonstração (o que o dono vê) | O que atravessa | Quando |
|---|---|---|---|
| 1. Encadear | O dono vê \`a \| b\` | x; y | hoje |
| 2. Conduzir | O dono dorme | z | depois |

## Decidido sem perguntar (vete aqui)

- nada
`

const EPICS = (c1: string[] = ['done', 'pending']) => ({
  '/repo/docs/epics/cepa-em-espiral.md': EPIC,
  '/repo/.claude/programs/cepa-espiral-c1/plan.yaml': FILA('single-track', c1),
})

test('parseEpic lê nome, status, padrão de fila e os ciclos da escada', async () => {
  const e = parseEpic('cepa-em-espiral.md', EPIC)!
  expect(e.arquivo).toBe('cepa-em-espiral')
  expect(e.nome).toBe('Cepa em espiral')
  expect(e.status).toBe('rascunho')
  expect(e.padraoFila).toBe('cepa-espiral-c<N>')
  expect(e.ciclos).toEqual([{ numero: 1, rotulo: '1. Encadear' }, { numero: 2, rotulo: '2. Conduzir' }])
  expect(parseEpic('x.md', '# Outra coisa\n')).toBe(null)
  expect(parseEpic('x.md', '# Epic: Sem escada\n\n**Status:** pronta\n')!.ciclos).toEqual([])
})

test('filaDoCiclo: pelo source do --from-epic, pelo padrão da Construção, pelo nome do arquivo', async () => {
  const e = parseEpic('cepa-em-espiral.md', EPIC)!
  const fila = (nome: string, fonte: string) => contaFila(nome, `mode: single-track\nsource: ${fonte}\nitems:\n`)!
  const porFonte = fila('qualquer', 'docs/epics/cepa-em-espiral.md, ciclo 2 (3 peças de "O que\n  atravessa"; ordem herdada do texto)')
  const porPadrao = fila('cepa-espiral-c2', 'docs/spec/x.md')
  const porArquivo = fila('cepa-em-espiral-c2', 'BACKLOG.md')
  expect(porFonte.fonte).toBe('docs/epics/cepa-em-espiral.md, ciclo 2 (3 peças de "O que atravessa"; ordem herdada do texto)')
  expect(filaDoCiclo(e, 2, [porArquivo, porPadrao, porFonte])).toBe(porFonte)
  expect(filaDoCiclo(e, 2, [porArquivo, porPadrao])).toBe(porPadrao)
  expect(filaDoCiclo(e, 2, [porArquivo])).toBe(porArquivo)
  expect(filaDoCiclo(e, 1, [porArquivo, porPadrao, porFonte])).toBe(null)
  // `ciclo 12` não é o ciclo 1
  expect(filaDoCiclo(e, 1, [fila('q', 'docs/epics/cepa-em-espiral.md, ciclo 12')])).toBe(null)
})

test('estado do ciclo: sem fila, andando, travado, demonstrável; descartados fora da conta', async () => {
  const f = (st: string[]) => contaFila('f', FILA('single-track', st))
  expect(linhaDoCiclo(null)).toBe('sem fila')
  expect(linhaDoCiclo(f(['done', 'pending', 'dropped']))).toBe('1/2 feitos')
  expect(estadoDoCiclo(f(['done', 'pending']))).toBe('andando')
  expect(linhaDoCiclo(f(['done', 'blocked', 'pending']))).toBe('travado · 1/3 feitos')
  expect(estadoDoCiclo(f(['blocked', 'in_progress']))).toBe('andando')
  expect(linhaDoCiclo(f(['done', 'done', 'dropped']))).toBe('demonstrável')
  expect(estadoDoCiclo(f(['dropped']))).toBe('andando')
})

test('nível 0: um bloco por Epic, uma linha por ciclo com o estado da fila, antes de Filas', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, EPICS())
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(textos.indexOf('Épicos')).toBeLessThan(textos.indexOf('Filas'))
  expect(await ui.find({ type: 'Text', text: '1 Epic' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'Cepa em espiral' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'rascunho' })).toBeTruthy()
  const linha = (rotulo: string) => textos.slice(textos.indexOf(rotulo), textos.indexOf(rotulo) + 2)
  expect(linha('▶ 1. Encadear')).toEqual(['▶ 1. Encadear', '1/2 feitos'])
  expect(linha('○ 2. Conduzir')).toEqual(['○ 2. Conduzir', 'sem fila'])
  expect((await ui.find({ type: 'Text', text: '1/2 feitos' })).props.color).toBe('cyan')
})

test('nível 0: ciclo demonstrável em verde e travado em vermelho', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO, {
    ...EPICS(['done', 'done']),
    '/repo/.claude/programs/outro-c1/plan.yaml': FILA('single-track', ['blocked', 'done']),
    '/repo/docs/epics/outro.md': '# Epic: Outro\n\n**Status:** pronta\n\n## Escada de valor\n\n| Ciclo | Roteiro |\n|---|---|\n| 1. Só | x |\n',
  })
  const verde = await ui.find({ type: 'Text', text: 'demonstrável' })
  expect(verde.props.color).toBe('green')
  expect((await ui.find({ type: 'Text', text: '✓ 1. Encadear' })).props.color).toBe('green')
  const vermelho = await ui.find({ type: 'Text', text: 'travado · 1/2 feitos' })
  expect(vermelho.props.color).toBe('red')
  expect(await ui.find({ type: 'Text', text: '2 Epics' })).toBeTruthy()
  const textos = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  // ordem alfabética pelo nome: Cepa em espiral antes de Outro
  expect(textos.indexOf('Cepa em espiral')).toBeLessThan(textos.indexOf('Outro'))
})

test('sem docs/epics, o nível 0 diz isso', async ($, on) => {
  const ui = await sobe($, on, 'sessao-a', ARQUIVO)
  expect(await ui.find({ type: 'Text', text: 'nenhum Epic em docs/epics' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'docs/epics' })).toBeTruthy()
})

test('sem intenção, o nível 0 continua lá', async ($, on) => {
  const ui = await sobe($, on, 'sessao-b', null, EPICS())
  expect(await ui.find({ type: 'Text', text: '○ 2. Conduzir' })).toBeTruthy()
})

test('os Epics são relidos no fim do turno: um arquivo novo aparece sem reiniciar', async ($, on) => {
  on('turn.complete', async () => ({ text: 'x' }))
  const { arquivos } = await prepara($, on, 'sessao-a', ARQUIVO)
  const ui = await monta($)
  expect(await ui.find({ type: 'Text', text: 'nenhum Epic em docs/epics' })).toBeTruthy()
  Object.assign(arquivos, EPICS())
  await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer' })
  expect(await ui.find({ type: 'Text', text: 'Cepa em espiral' })).toBeTruthy()
})
