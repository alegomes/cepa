import { expect, mock, test } from 'claude-code/testing'

import { buildLine, parseBuild } from './build'
import { age, parseIntent } from './intent'
import { countDeviations, readExits, parseMode } from './mode'
import { noticeFor, tally, duration, timeOfDay, parseRun, endLabel, runTime } from './until'
import { readBlock, readGuard } from './gate'
import { countQueue } from './queues'
import { cycleState, queueOfCycle, cycleLine, parseEpic } from './epics'

const INTENT_FILE = `purpose: "Construir o M1, painel da intenção"
by_when: "painel aparece no terminal"
plan:
  - "guardar M2-M6 na fila mods"
  - "ler exemplos e tipos do mod"
  - "escrever o mod e testes"
step: 2
step_since: "2026-10-19T10:00:00Z"
session_id: "sessao-a"
branch: "session/oncoto"
opened_at: "2026-10-18T20:03:58Z"
summary: "passo 2/3 · ler exemplos e tipos do mod · Construir o M1"
history:
  - at: "2026-10-18T20:03:58Z"
    purpose: "Outra coisa"
`

// The same file as the old `cepa-intencao` wrote it (pt-BR keys).
const OLD_INTENT_FILE = `proposito: "Construir o M1, painel da intenção"
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
  const intent = parseIntent(INTENT_FILE)
  expect(intent?.purpose).toBe('Construir o M1, painel da intenção')
  expect(intent?.plan).toEqual([
    'guardar M2-M6 na fila mods',
    'ler exemplos e tipos do mod',
    'escrever o mod e testes',
  ])
  expect(intent?.step).toBe(2)
  expect(intent?.sessionId).toBe('sessao-a')
})

test('intenção gravada com as chaves antigas (pt-BR) ainda é lida', async () => {
  expect(parseIntent(OLD_INTENT_FILE)).toEqual(parseIntent(INTENT_FILE))
  expect(parseIntent(OLD_INTENT_FILE)?.step).toBe(2)
})

test('arquivo sem propósito não é intenção', async () => {
  expect(parseIntent('step: 1\n')).toBe(null)
  expect(parseIntent('passo: 1\n')).toBe(null)
})

test('idade do cursor em minutos, horas e dias', async () => {
  const t = Date.parse('2026-10-19T10:00:00Z')
  expect(age('2026-10-19T10:00:00Z', t + 12 * 60000)).toBe('há 12 min')
  expect(age('2026-10-19T10:00:00Z', t + 3 * 3600000)).toBe('há 3 h')
  expect(age('2026-10-19T10:00:00Z', t + 72 * 3600000)).toBe('há 3 dias')
})

const QUEUE_YAML = (mode: string, status: string[]) =>
  `mode: ${mode}\nitems:\n` +
  status.map((st, i) => `- id: X${i}\n  title: 'Item ${i} da fila, com título
    longo dobrado e aspas do ''yaml'''\n  why: 'x'\n  status: ${st}\n`).join('')

const FILES: Record<string, string> = {
  '/repo/.claude/programs/mods/plan.yaml': QUEUE_YAML('single-track', ['done', 'pending', 'in_progress', 'pending']),
  '/repo/.claude/programs/cepa/plan.yaml': QUEUE_YAML('single-track', ['done', 'blocked', 'dropped']),
  '/repo/.claude/programs/velha/plan.yaml': QUEUE_YAML('parallel-waves', ['pending']),
  '/repo/.claude/programs/zerada/plan.yaml': QUEUE_YAML('single-track', ['done']),
}

const prepare = async ($: any, on: any, session: string, text: string | null, extras: Record<string, string> = {}) => {
  const clock = mock.clock(on, { now: Date.parse('2026-10-19T10:12:00Z') })
  const files: Record<string, string> = { ...FILES, ...extras }
  if (text !== null) files['.claude/session-intent'] = text
  // The engine delivers the relative path already resolved against the session directory.
  const lookup = (path: string) => {
    if (files[path] !== undefined) return files[path]
    const rel = Object.keys(files).find(k => k.startsWith('.claude/') && path.endsWith(`/${k}`))
    return rel === undefined ? undefined : files[rel]
  }
  const under = (dir: string) => Object.keys(files).filter(k => k.startsWith(`${dir}/`))
  on('fs.exists', async ($: any, e: any) => ({
    value: lookup(e.path) !== undefined || e.path === '/repo/.claude/programs' || under(e.path).length > 0,
  }))
  on('fs.read', async ($: any, e: any) => ({ value: lookup(e.path) }))
  on('fs.list', async ($: any, e: any) => {
    // `.claude/queues` lists only the folders that actually have a file (like the real fs);
    // the rest of the list below is fixed and serves `.claude/programs`.
    if (e.path.endsWith('/.claude/queues')) {
      const names = [...new Set(under(e.path).map(k => k.slice(e.path.length + 1).split('/')[0]))]
      return { value: names.map(name => ({ name, kind: 'dir', size: 0, mtimeMs: 0, isLink: false })) }
    }
    if (!e.path.endsWith('/until') && !e.path.endsWith('/docs/epics')) {
      // Fixed names (including 'maestro', which has no plan.yaml) plus the fixtures' folders.
      const fixed = ['zerada', 'cepa', 'velha', 'mods', 'maestro', 'cepa-espiral-c1', 'outro-c1']
      const fromFixtures = Object.keys(files)
        .map(k => k.match(/^\/repo\/\.claude\/programs\/([^/]+)\//)?.[1])
        .filter((n): n is string => n !== undefined && !fixed.includes(n))
      return {
        value: [...fixed, ...fromFixtures].map(name => ({
          name, kind: 'dir', size: 0, mtimeMs: 0, isLink: false,
        })),
      }
    }
    // Like the real fs: listing a folder that does not exist is an error, not an empty list.
    if (under(e.path).length === 0) throw new Error(`ENOENT: ${e.path}`)
    return {
      value: under(e.path).map(k => ({ name: k.slice(e.path.length + 1), kind: 'file', size: 0, mtimeMs: 0, isLink: false })),
    }
  })
  on('process.run', async ($: any, e: any) => ({
    value: e.argv[0] === 'cepa-modes'
      ? { exitCode: 0, stdout: e.argv.join(' ') === 'cepa-modes --json' ? MODES_JSON : 'tabela em texto', stderr: '' }
      : { exitCode: 0, stdout: '/repo/.git\n', stderr: '' },
  }))
  on('session.id', async () => ({ value: session }))
  on('command.register', async () => ({ value: { command: 'compass' } }))
  on('ui.open', async () => ({ value: { isPlaced: true } }))
  on('session.start', async () => ({ cwd: '/repo' }))
  await $.session.start({ cwd: '/repo', surface: 'terminal', source: 'startup' })
  return { files, clock }
}

const mountPane = ($: any) =>
  $.ui.mount({
    plugin: 'compass',
    surface: 'terminal',
    component: 'Pane',
    requestId: 'compass',
    props: { title: 'Compass', isFocused: false, bodyColumns: 60, placement: 'dock' },
  })

const openPane = async ($: any, on: any, session: string, text: string | null, extras: Record<string, string> = {}) => {
  await prepare($, on, session, text, extras)
  return $.ui.mount({
    plugin: 'compass',
    surface: 'terminal',
    component: 'Pane',
    requestId: 'compass',
    props: { title: 'Compass', isFocused: false, bodyColumns: 60, placement: 'dock' },
  })
}

const MODES_JSON = JSON.stringify({
  construction: { saida: 'completion-auditor COMPLETE e proof-reviewer PROVEN', gate: 'x' },
  refactor: { saida: 'o orçamento declarado exaurido' },
})

const MODE = 'mode: construction\nroutine: null\nbudget: null\nopened_at: 2026-10-19T13:46:36Z\n'
// The same file as the old `cepa` wrote it.
const OLD_MODE = 'modo: construcao\nrotina: null\norcamento: null\naberto_em: 2026-10-19T13:46:36Z\n'

const DEVIATIONS = `# Desvios capturados

Texto de abertura com - [ ] no meio da linha, que não conta.

- [x] 2026-08-18 · modo: construcao · RESOLVIDO em 0.16.0
- [ ] 2026-08-23 · modo: descoberta · gate só enxerga new_string
  continuação da linha anterior
- [ ] 2026-09-27 · modo: exploracao · bash-path-lock lê sed -i errado
`

test('lê o modo e trata null como ausência', async () => {
  expect(parseMode(MODE)).toEqual({ name: 'construction', budget: '', openedAt: '2026-10-19T13:46:36Z' })
  expect(parseMode('mode: refactor\nbudget: "só o filas.ts"\n')?.budget).toBe('só o filas.ts')
  expect(parseMode('mode: null\n')).toBe(null)
})

test('session-mode antigo (modo: construcao) ainda é lido como construction', async () => {
  expect(parseMode(OLD_MODE)).toEqual(parseMode(MODE))
  expect(parseMode('modo: reforma\norcamento: "só o filas.ts"\n')).toEqual({
    name: 'refactor', budget: 'só o filas.ts', openedAt: '',
  })
  expect(parseMode('modo: null\n')).toBe(null)
})

test('conta desvios abertos e resolvidos e guarda o quê do último', async () => {
  expect(countDeviations(DEVIATIONS)).toEqual({ open: 2, resolved: 1, last: 'bash-path-lock lê sed -i errado' })
  expect(countDeviations('')).toEqual({ open: 0, resolved: 0, last: '' })
  expect(countDeviations('- [X] 2026-10-19 · modo: reforma · marcado em maiúscula\n').resolved).toBe(1)
})

test('saídas vêm do cepa-modes --json; json quebrado não derruba', async () => {
  expect(readExits(MODES_JSON).construction).toBe('completion-auditor COMPLETE e proof-reviewer PROVEN')
  expect(readExits('não é json')).toEqual({})
})

test('nível 3: modo, condição de saída e desvios, depois do nível 2', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, { '.claude/session-mode': MODE, '.claude/deviations.md': DEVIATIONS })
  expect(await ui.find({ type: 'Text', text: 'construction' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'fecha quando: completion-auditor COMPLETE e proof-reviewer PROVEN' })).toBeTruthy()
  expect((await ui.find({ type: 'Text', text: '2 desvios abertos' }))?.props?.color).toBe('yellow')
  expect(await ui.find({ type: 'Text', text: ' · 1 resolvido' })).toBeTruthy()
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(texts.indexOf('Sessão') < texts.indexOf('Modo')).toBe(true)
})

test('nível 3 mostra o orçamento da reforma', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, { '.claude/session-mode': 'mode: refactor\nbudget: "só o filas.ts"\n' })
  expect(await ui.find({ type: 'Text', text: 'fecha quando: o orçamento declarado exaurido' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'orçamento: só o filas.ts' })).toBeTruthy()
})

test('sem modo e sem desvios, o nível 3 diz isso (com intenção)', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE)
  expect(await ui.find({ type: 'Text', text: 'sem modo' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'Esta sessão não declarou modo.' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'nenhum desvio registrado' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: /fecha quando/ })).toEqual([])
})

test('sem modo e sem desvios, o nível 3 diz isso (sem intenção)', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', null)
  expect(await ui.find({ type: 'Text', text: 'sem modo' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'nenhum desvio registrado' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: /fecha quando/ })).toEqual([])
})

test('singular para um desvio aberto e um resolvido', async ($, on) => {
  const one = '- [x] 2026-08-18 · modo: construcao · a\n- [ ] 2026-08-19 · modo: construcao · b\n'
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, { '.claude/deviations.md': one })
  expect(await ui.find({ type: 'Text', text: /^1 desvio aberto$/ })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /^ · 1 resolvido$/ })).toBeTruthy()
})

test('nível 3 cai no .claude/desvios.md legado quando o novo não existe', async ($, on) => {
  const one = '- [x] 2026-08-18 · modo: construcao · a\n- [ ] 2026-08-19 · modo: construcao · b\n'
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, { '.claude/desvios.md': one })
  expect(await ui.find({ type: 'Text', text: /^1 desvio aberto$/ })).toBeTruthy()
})

test('desvio novo que já nasce resolvido também gera aviso', async ($, on) => {
  const toasts: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  const { files, clock } = await prepare($, on, 'sessao-a', INTENT_FILE, { '.claude/deviations.md': DEVIATIONS })
  files['.claude/deviations.md'] = `${DEVIATIONS}- [x] 2026-10-19 · modo: construcao · resolvido na hora\n`
  await clock.advance(5000)
  expect(toasts).toEqual(['Desvio registrado: resolvido na hora'])
})

test('desvio novo gera aviso; os que já existiam na abertura, não', async ($, on) => {
  const toasts: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  const { files, clock } = await prepare($, on, 'sessao-a', INTENT_FILE, { '.claude/deviations.md': DEVIATIONS })
  await clock.advance(5000)
  expect(toasts).toEqual([])
  files['.claude/deviations.md'] = `${DEVIATIONS}- [ ] 2026-10-19 · modo: construcao · o mod não lê o build\n`
  await clock.advance(5000)
  expect(toasts).toEqual(['Desvio registrado: o mod não lê o build'])
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: '3 desvios abertos' })).toBeTruthy()
})

test('nível 1: tabela com uma linha por fila e uma coluna por estado', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE)
  expect(await ui.find({ type: 'Text', text: 'Filas' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '2 abertas' })).toBeTruthy()
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  const line = (name: string) => texts.slice(texts.indexOf(name), texts.indexOf(name) + 6)
  expect(line('fila')).toEqual(['fila', 'pend', 'and', 'bloq', 'feito', 'desc'])
  expect(line('mods')).toEqual(['mods', '2', '1', '·', '1', '·'])
  expect(line('cepa')).toEqual(['cepa', '·', '·', '1', '1', '1'])
  expect(line('zerada')).toEqual(['zerada', '·', '·', '·', '1', '·'])
  expect(texts.filter((t: string) => /Item|▸|✗/.test(t))).toEqual([])
  expect(texts.filter((t: string) => /velha/.test(t))).toEqual([])
})

test('nível 1 lê .claude/queues/<n>/queue.yaml; nome nos dois layouts, o novo ganha e aparece uma vez', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, {
    // `mods` exists in both layouts (programs: 2 pend, 1 and, 1 feito); `maestro` only in the new one.
    '/repo/.claude/queues/mods/queue.yaml': QUEUE_YAML('single-track', ['pending']),
    '/repo/.claude/queues/maestro/queue.yaml': QUEUE_YAML('single-track', ['done', 'done', 'blocked']),
  })
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  const line = (name: string) => texts.slice(texts.indexOf(name), texts.indexOf(name) + 6)
  expect(line('mods')).toEqual(['mods', '1', '·', '·', '·', '·'])
  expect(line('maestro')).toEqual(['maestro', '·', '·', '1', '2', '·'])
  expect(line('cepa')).toEqual(['cepa', '·', '·', '1', '1', '1'])
  expect(texts.filter((t: string) => t === 'mods')).toHaveLength(1)
  expect(texts.filter((t: string) => t === 'maestro')).toHaveLength(1)
})

test('nível 1 vem antes do nível 2 e as abertas em ordem de itens abertos', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE)
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  const pos = (t: string) => texts.indexOf(t)
  expect(pos('Filas') < pos('mods')).toBe(true)
  expect(pos('mods') < pos('cepa')).toBe(true)
  expect(pos('cepa') < pos('Sessão')).toBe(true)
})

test('sem intenção, o nível 1 continua lá', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', null)
  expect(await ui.find({ type: 'Text', text: 'mods' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /ainda não tem intenção/ })).toBeTruthy()
})

test('painel marca feitos, o passo atual com a idade e os pendentes', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE)
  expect(await ui.find({ type: 'Text', text: '✓ guardar M2-M6 na fila mods' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '▶ ler exemplos e tipos do mod' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'há 12 min' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'passo 2/3' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'meta: painel aparece no terminal' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '○ escrever o mod e testes' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: /outra sessão/ })).toEqual([])
})

test('intenção de outra sessão pede confirmação', async ($, on) => {
  const ui = await openPane($, on, 'sessao-b', INTENT_FILE)
  expect(await ui.find({ type: 'Text', text: /outra sessão \(2026-10-18\)/ })).toBeTruthy()
})

test('sem arquivo, diz que não há intenção', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', null)
  expect(await ui.find({ type: 'Text', text: /ainda não tem intenção/ })).toBeTruthy()
})

test('plano cumprido aponta o wrap-up', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE.replace('step: 2', 'step: 4'))
  expect(await ui.find({ type: 'Text', text: /Plano cumprido/ })).toBeTruthy()
})

test('no último passo o plano ainda não está cumprido', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE.replace('step: 2', 'step: 3'))
  expect(await ui.findAll({ type: 'Text', text: /Plano cumprido/ })).toEqual([])
})

test('colunas de número não encolhem quando o nome da fila é longo', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE)
  const boxes = (await ui.findAll({ type: 'Box' })).filter((b: any) => b.props?.width === 6)
  // header + 3 single-track queues, 5 columns each
  expect(boxes.length).toBe(20)
  expect(boxes.every((b: any) => b.props.flexShrink === 0)).toBe(true)
})

const BUILD = (status: string, at: string, extra = '') => `{"status": "${status}", "at": "${at}", "command": "x", "kind": "pytest"${extra}}`

const BUILD_STALE = `{"status": "STALE", "since": "2026-10-19T10:09:00Z", "after_edit_to": "compass/hooks/register.tsx",
  "last_known_status": "FAILURE", "last_known_at": "2026-10-19T08:12:00Z", "last_known_command": "pytest"}`

test('parseBuild traduz os quatro status e guarda o anterior do STALE', async () => {
  const t = Date.parse('2026-10-19T10:12:00Z')
  expect(parseBuild(BUILD('SUCCESS', '2026-10-19T10:00:00Z'))).toEqual({ state: 'verde', at: '2026-10-19T10:00:00Z', previous: null, previousAt: '' })
  expect(parseBuild(BUILD('failure', '2026-10-19T10:00:00Z'))?.state).toBe('vermelho')
  expect(parseBuild(BUILD('EMPTY', '2026-10-19T10:00:00Z', ', "tests_run": 0'))?.state).toBe('vazio')
  expect(parseBuild(BUILD_STALE)).toEqual({ state: 'desatualizado', at: '2026-10-19T10:09:00Z', previous: 'vermelho', previousAt: '2026-10-19T08:12:00Z' })
  expect(parseBuild('{"status": "ALGO"}')?.state).toBe('desconhecido')
  expect(parseBuild('{"status": "STALE"}')).toEqual({ state: 'desatualizado', at: '', previous: 'desconhecido', previousAt: '' })
  expect(parseBuild('não é json')).toBe(null)
  expect(parseBuild('null')).toBe(null)
  expect(parseBuild('[1]')?.state).toBe('desconhecido')
  expect(buildLine(parseBuild(BUILD('SUCCESS', '2026-10-19T10:00:00Z'))!, t)).toBe('verde há 12 min')
  expect(buildLine(parseBuild(BUILD_STALE)!, t)).toBe('desatualizado há 3 min · era vermelho há 2 h')
  expect(buildLine(parseBuild('{"status": "STALE"}')!, t)).toBe('desatualizado')
  expect(buildLine(parseBuild('{"status": "SUCCESS"}')!, t)).toBe('verde')
})

test('nível 3: build verde com a idade, em verde', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, { '.claude/session-mode': MODE, '.claude/last-build.json': BUILD('SUCCESS', '2026-10-19T10:00:00Z') })
  const line = await ui.find({ type: 'Text', text: 'verde há 12 min' })
  expect(line?.props?.color).toBe('green')
  expect(line?.props?.bold).toBeFalsy()
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(texts.indexOf('Modo') < texts.indexOf('verde há 12 min')).toBe(true)
})

test('nível 3: build vermelho em vermelho e negrito', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, { '.claude/last-build.json': BUILD('FAILURE', '2026-10-19T08:12:00Z') })
  const line = await ui.find({ type: 'Text', text: 'vermelho há 2 h' })
  expect(line?.props?.color).toBe('red')
  expect(line?.props?.bold).toBe(true)
})

test('nível 3: build vazio em amarelo', async ($, on) => {
  const empty = await openPane($, on, 'sessao-a', INTENT_FILE, { '.claude/last-build.json': BUILD('EMPTY', '2026-10-19T10:00:00Z') })
  expect((await empty.find({ type: 'Text', text: 'vazio há 12 min' }))?.props?.color).toBe('yellow')
})

test('nível 3: build desatualizado mostra o que era antes', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', null, { '.claude/last-build.json': BUILD_STALE })
  expect((await ui.find({ type: 'Text', text: 'desatualizado há 3 min · era vermelho há 2 h' }))?.props?.color).toBe('yellow')
})

test('sem last-build.json, o nível 3 diz que não há build registrado', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE)
  expect(await ui.find({ type: 'Text', text: 'nenhum registrado' })).toBeTruthy()
})

test('o build é relido a cada 5 s: o verde vira desatualizado sem novo turno', async ($, on) => {
  const { files, clock } = await prepare($, on, 'sessao-a', INTENT_FILE, { '.claude/last-build.json': BUILD('SUCCESS', '2026-10-19T10:00:00Z') })
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: 'verde há 12 min' })).toBeTruthy()
  files['.claude/last-build.json'] = BUILD_STALE
  await clock.advance(5000)
  expect(await ui.find({ type: 'Text', text: 'desatualizado há 3 min · era vermelho há 2 h' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: 'verde há 12 min' })).toEqual([])
})

test('o build é relido no fim de cada turno, sem esperar o relógio', async ($, on) => {
  on('turn.complete', async () => ({ text: 'x' }))
  const { files } = await prepare($, on, 'sessao-a', INTENT_FILE, { '.claude/last-build.json': BUILD('SUCCESS', '2026-10-19T10:00:00Z') })
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: 'verde há 12 min' })).toBeTruthy()
  files['.claude/last-build.json'] = BUILD_STALE
  await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer' })
  expect(await ui.find({ type: 'Text', text: 'desatualizado há 3 min · era vermelho há 2 h' })).toBeTruthy()
})

test('status desconhecido sai sem cor, e o rótulo "build:" fica ao lado do estado', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, { '.claude/last-build.json': '{"status": "ALGO", "at": "2026-10-19T10:00:00Z"}' })
  const line = await ui.find({ type: 'Text', text: 'desconhecido há 12 min' })
  expect(line?.props?.color).toBe(undefined)
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(texts.indexOf('build: ') + 1).toBe(texts.indexOf('desconhecido há 12 min'))
})

// ── level 4: the cepa-until run ──────────────────────────────────────────────

const ev = (e: Record<string, unknown>) => JSON.stringify(e) + '\n'
const RUN_START = ev({ evento: 'run_start', fila: 'cepa', prazo: '2026-10-19T18:00:00', quando: '2026-10-19T09:00:00' })
const CS1_START = ev({ evento: 'item_start', id: 'CS-1', title: 'primeiro item da fila', tentativa: 1, quando: '2026-10-19T09:00:05' })
const CS1_END = ev({ evento: 'item_end', id: 'CS-1', status: 'done', segundos: 300, quando: '2026-10-19T09:05:00' })
const CS1_GREEN = ev({ evento: 'verify', id: 'CS-1', verde: true, quando: '2026-10-19T09:15:00' })
const CS2_START = ev({ evento: 'item_start', id: 'CS-2', title: 'segundo item', tentativa: 2, quando: '2026-10-19T10:00:00' })
// The `quando` of cepa-until is local time with no timezone. The render tests write the
// instant relative to the tests' clock (10:12Z) in the machine's timezone, and read the
// expected time with the same arithmetic, so as not to depend on the timezone of whoever runs the suite.
const NOW = Date.parse('2026-10-19T10:12:00Z')
const two = (n: number) => String(n).padStart(2, '0')
const LOCAL = (minutesAfter: number) => {
  const d = new Date(NOW + minutesAfter * 60000)
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}T${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`
}
const HM = (minutesAfter: number) => LOCAL(minutesAfter).slice(11, 16)

test('parseRun: item atual, etapa de build, contagem e fim', async () => {
  const r = parseRun(RUN_START + CS1_START + CS1_END, 'cepa', '2026-10-19-0900')!
  expect(r.phase).toBe('rodando')
  expect(r.item).toEqual({ id: 'CS-1', title: 'primeiro item da fila', since: '2026-10-19T09:05:00', attempt: 1, stage: 'build' })
  const r2 = parseRun(RUN_START + CS1_START + CS1_END + CS1_GREEN + CS2_START, 'cepa', 'x')!
  expect(r2.delivered).toBe(1)
  expect(r2.item?.id).toBe('CS-2')
  expect(r2.item?.attempt).toBe(2)
  const end = ev({ evento: 'run_end', motivo: 'fim-da-fila', detalhe: 'a fila acabou', quando: '2026-10-19T11:00:00' })
  const r3 = parseRun(RUN_START + CS1_START + CS1_END + CS1_GREEN + end, 'cepa', 'x')!
  expect(r3.phase).toBe('encerrado')
  expect(r3.item).toBe(null)
  expect(r3.end).toEqual({ reason: 'fim-da-fila', detail: 'a fila acabou', when: '2026-10-19T11:00:00' })
  expect(runTime(r3, 0)).toBe('2h00')
})

test('parseRun: vermelho, travado, pausa de cota e interrupção', async () => {
  const redEv = ev({ evento: 'verify_vermelho', id: 'CS-1', quando: '2026-10-19T09:20:00' })
  const blockedEv = ev({ evento: 'item_end', id: 'CS-2', status: 'blocked', quando: '2026-10-19T10:30:00' })
  const pauseEv = ev({ evento: 'pausa_de_cota', uso: 0.9, acorda: '2026-10-19T14:35:00', quando: '2026-10-19T10:31:00' })
  const r = parseRun(RUN_START + CS1_START + CS1_END + redEv + CS2_START + blockedEv + pauseEv, 'cepa', 'x')!
  expect(r.reds).toBe(1)
  expect(r.blocked).toBe(1)
  expect(r.phase).toBe('cota')
  expect(r.quota).toEqual({ resumes: '2026-10-19T14:35:00' })
  expect(tally(r)).toBe('1 vermelho · 1 travado')
  const limitEv = ev({ evento: 'limite_de_uso', id: 'CS-2', reset_em: '2026-10-19T15:00:00', espera: true, quando: '2026-10-19T10:40:00' })
  const r2 = parseRun(RUN_START + CS2_START + limitEv, 'cepa', 'x')!
  expect(r2.phase).toBe('cota')
  expect(r2.quota).toEqual({ resumes: '2026-10-19T15:00:00' })
  const signalEv = ev({ evento: 'run_interrompido', sinal: 'SIGTERM', id: 'CS-2', quando: '2026-10-19T10:50:00' })
  const r3 = parseRun(RUN_START + CS2_START + signalEv, 'cepa', 'x')!
  expect(r3.phase).toBe('interrompido')
  expect(r3.end?.reason).toBe('interrompido')
  expect(parseRun('lixo\n' + CS2_START, 'cepa', 'x')).toBe(null)
})

test('duracao no formato do cepa-until', async () => {
  expect(duration(0, 12 * 60000)).toBe('12min')
  expect(duration(0, 83 * 60000)).toBe('1h23')
  expect(duration(NaN, 1)).toBe('')
})

test('avisoDe: só na mudança de fase do mesmo run; fim e cota avisam', async () => {
  const running = parseRun(RUN_START + CS1_START, 'cepa', 'r1')!
  const end = parseRun(RUN_START + CS1_START + CS1_END + CS1_GREEN + ev({ evento: 'run_end', motivo: 'prazo', detalhe: 'x', quando: '2026-10-19T11:00:00' }), 'cepa', 'r1')!
  const quota = parseRun(RUN_START + ev({ evento: 'pausa_de_cota', acorda: '2026-10-19T14:35:00', quando: '2026-10-19T10:31:00' }), 'cepa', 'r1')!
  expect(noticeFor(null, end)).toBe(null)
  expect(noticeFor(running, running)).toBe(null)
  expect(noticeFor(end, { ...end, id: 'r2' })).toBe(null)
  expect(noticeFor(running, end)).toBe('cepa-until cepa: prazo chegou · 1 entregue')
  expect(noticeFor(running, quota)).toBe('cepa-until parado pela cota · retoma às 14:35')
})

const UNTIL = (text: string) => ({ '/repo/.claude/programs/cepa/until/2026-10-19-0900.jsonl': text })

// `find` matches by fragment; `exact` requires the whole text.
const exact = async (ui: any, text: string) => {
  const n = await ui.find({ type: 'Text', text: text })
  return n && n.text === text ? n : undefined
}

test('nível 4: item atual com tempo e tentativa, contagem e prazo, depois do nível 3', async ($, on) => {
  const startEv = ev({ evento: 'run_start', fila: 'cepa', prazo: LOCAL(8 * 60), quando: LOCAL(-72) })
  const item = ev({ evento: 'item_start', id: 'CS-2', title: 'segundo item', tentativa: 2, quando: LOCAL(-12) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(startEv + CS1_START + CS1_END + CS1_GREEN + item))
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(texts.indexOf('Modo')).toBeLessThan(texts.indexOf('Run'))
  expect(await ui.find({ type: 'Text', text: 'cepa · 1h12' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '▶ CS-2 · segundo item' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'item há 12min · tentativa 2' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: `1 entregue · prazo ${HM(8 * 60)}` })).toBeTruthy()
})

test('nível 4: run encerrado mostra o motivo em verde, a idade e a contagem sem prazo', async ($, on) => {
  const end = ev({ evento: 'run_end', motivo: 'fim-da-fila', detalhe: 'a fila acabou', quando: LOCAL(-12) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + CS1_END + CS1_GREEN + end))
  const text = await ui.find({ type: 'Text', text: 'fila acabou há 12 min' })
  expect(text).toBeTruthy()
  expect(text.props.color).toBe('green')
  expect(await ui.find({ type: 'Text', text: 'a fila acabou' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: '1 entregue' })).toBeTruthy()
})

test('nível 4: parado pela cota em amarelo, com a hora de retomar', async ($, on) => {
  const pauseEv = ev({ evento: 'pausa_de_cota', acorda: LOCAL(263), quando: LOCAL(-7) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + CS1_END + CS1_GREEN + pauseEv))
  const text = await ui.find({ type: 'Text', text: `parado pela cota · retoma às ${HM(263)}` })
  expect(text).toBeTruthy()
  expect(text.props.color).toBe('yellow')
})

test('sem run, o nível 4 diz isso (com e sem intenção)', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE)
  expect(await ui.find({ type: 'Text', text: 'nenhum run do cepa-until' })).toBeTruthy()
})

test('sem intenção, o nível 4 continua lá', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', null)
  expect(await ui.find({ type: 'Text', text: 'nenhum run do cepa-until' })).toBeTruthy()
})

test('o run mais recente vence entre as filas', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, {
    ...UNTIL(RUN_START + CS1_START),
    '/repo/.claude/programs/mods/until/2026-10-19-1100.jsonl': ev({ evento: 'run_start', fila: 'mods', prazo: '', quando: LOCAL(-2) }),
  })
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
})

test('o fim do run avisa com toast e som, uma vez; a abertura com run já encerrado não avisa', async ($, on) => {
  const toasts: string[] = []
  const sounds: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('audio.play', async ($: any, e: any) => {
    sounds.push(e.clip.asset)
    return { value: undefined }
  })
  const path = '/repo/.claude/programs/cepa/until/2026-10-19-0900.jsonl'
  const { files, clock } = await prepare($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + CS1_END))
  await clock.advance(5000)
  expect(toasts).toEqual([])
  files[path] += CS1_GREEN + ev({ evento: 'run_end', motivo: 'limite-de-uso', detalhe: 'x', quando: LOCAL(-1) })
  await clock.advance(5000)
  expect(toasts).toEqual(['cepa-until cepa: parou pela cota · 1 entregue'])
  expect(sounds).toEqual(['sons/fim.wav'])
  await clock.advance(5000)
  expect(sounds).toEqual(['sons/fim.wav'])
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: 'parou pela cota há 1 min' })).toBeTruthy()
})

test('a pausa pela cota avisa com som; a retomada não', async ($, on) => {
  const toasts: string[] = []
  const sounds: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('audio.play', async ($: any, e: any) => {
    sounds.push(e.clip.asset)
    return { value: undefined }
  })
  const path = '/repo/.claude/programs/cepa/until/2026-10-19-0900.jsonl'
  const { files, clock } = await prepare($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + CS1_END + CS1_GREEN))
  files[path] += ev({ evento: 'pausa_de_cota', acorda: LOCAL(263), quando: LOCAL(-1) })
  await clock.advance(5000)
  expect(toasts).toEqual([`cepa-until parado pela cota · retoma às ${HM(263)}`])
  expect(sounds.length).toBe(1)
  files[path] += CS2_START
  await clock.advance(5000)
  expect(toasts.length).toBe(1)
  expect(sounds.length).toBe(1)
  // A second pause, after the resume, warns again: the state did not get stuck on the quota.
  files[path] += ev({ evento: 'pausa_de_cota', acorda: LOCAL(400), quando: LOCAL(0) })
  await clock.advance(5000)
  expect(toasts).toEqual([
    `cepa-until parado pela cota · retoma às ${HM(263)}`,
    `cepa-until parado pela cota · retoma às ${HM(400)}`,
  ])
  expect(sounds.length).toBe(2)
})

test('um run novo que começa depois da abertura é lido na próxima varredura das filas', async ($, on) => {
  const { files, clock } = await prepare($, on, 'sessao-a', INTENT_FILE)
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: 'nenhum run do cepa-until' })).toBeTruthy()
  Object.assign(files, UNTIL(RUN_START + CS1_START))
  await clock.advance(30000)
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
})

test('nível 4: depois do done o item fica na etapa de build, sem tentativa quando é a primeira', async ($, on) => {
  const item = ev({ evento: 'item_start', id: 'CS-1', title: 'primeiro item da fila', tentativa: 1, quando: LOCAL(-20) })
  const end = ev({ evento: 'item_end', id: 'CS-1', status: 'done', quando: LOCAL(-9) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + item + end))
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
  expect(await exact(ui, 'build há 9min')).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'nada entregue ainda · prazo 18:00' })).toBeTruthy()
})

test('abrir a sessão com um run já encerrado não avisa, nem no relógio de 5 s, nem no de 30 s', async ($, on) => {
  const toasts: string[] = []
  const sounds: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('audio.play', async ($: any, e: any) => {
    sounds.push(e.clip.asset)
    return { value: undefined }
  })
  const end = ev({ evento: 'run_end', motivo: 'fim-da-fila', detalhe: 'a fila acabou', quando: LOCAL(-12) })
  const { clock } = await prepare($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + CS1_END + CS1_GREEN + end))
  await clock.advance(5000)
  await clock.advance(30000)
  expect(toasts).toEqual([])
  expect(sounds).toEqual([])
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: 'fila acabou há 12 min' })).toBeTruthy()
})

// ── level 4: perturbations that survived the 1st proof-reviewer round ────────

test('parseRun: item bloqueado ou devolvido sai da tela; verify vermelho não conta entrega', async () => {
  const blockedEv = ev({ evento: 'item_end', id: 'CS-1', status: 'blocked', quando: '2026-10-19T09:05:00' })
  const r = parseRun(RUN_START + CS1_START + blockedEv, 'cepa', 'x')!
  expect(r.phase).toBe('rodando')
  expect(r.item).toBe(null)
  expect(r.blocked).toBe(1)
  const returnedEv = ev({ evento: 'item_end', id: 'CS-1', status: 'pending', quando: '2026-10-19T09:05:00' })
  expect(parseRun(RUN_START + CS1_START + returnedEv, 'cepa', 'x')!.item).toBe(null)
  const redEv = ev({ evento: 'verify', id: 'CS-1', verde: false, motivo: 'saiu 1', quando: '2026-10-19T09:15:00' })
  const r2 = parseRun(RUN_START + CS1_START + CS1_END + redEv, 'cepa', 'x')!
  expect(r2.delivered).toBe(0)
  expect(r2.item?.stage).toBe('build')
  const r3 = parseRun(RUN_START + CS1_START + CS1_END + CS1_GREEN, 'cepa', 'x')!
  expect(r3.item).toBe(null)
  const separateEv = ev({ evento: 'verify_vermelho', id: 'CS-1', quando: '2026-10-19T09:20:00' })
  const r4 = parseRun(RUN_START + CS1_START + CS1_END + redEv + separateEv, 'cepa', 'x')!
  expect(r4.item).toBe(null)
  expect(r4.reds).toBe(1)
})

test('parseRun: limite de uso sem espera não é pausa; interrupção guarda o sinal', async () => {
  const limitEv = ev({ evento: 'limite_de_uso', id: 'CS-1', reset_em: '2026-10-19T15:00:00', espera: false, quando: '2026-10-19T10:40:00' })
  const r = parseRun(RUN_START + CS1_START + limitEv, 'cepa', 'x')!
  expect(r.phase).toBe('rodando')
  expect(r.quota).toBe(null)
  expect(r.item?.id).toBe('CS-1')
  const signalEv = ev({ evento: 'run_interrompido', sinal: 'SIGTERM', id: 'CS-1', quando: '2026-10-19T10:50:00' })
  const r2 = parseRun(RUN_START + CS1_START + signalEv, 'cepa', 'x')!
  expect(r2.end).toEqual({ reason: 'interrompido', detail: 'sinal SIGTERM', when: '2026-10-19T10:50:00' })
})

test('duracao arredonda para baixo, não fica negativa e completa os minutos com zero', async () => {
  expect(duration(0, 59 * 1000)).toBe('0min')
  expect(duration(0, 59_500)).toBe('0min')
  expect(duration(0, 3_599_900)).toBe('59min')
  expect(duration(0, 3599 * 1000)).toBe('59min')
  expect(duration(0, 3600 * 1000)).toBe('1h00')
  expect(duration(0, 3661 * 1000)).toBe('1h01')
  expect(duration(0, (2 * 3600 + 59 * 60 + 59) * 1000)).toBe('2h59')
  expect(duration(10_000, 0)).toBe('0min')
  expect(duration(0, NaN)).toBe('')
})

test('hora completa com zero e devolve vazio para texto que não é data', async () => {
  expect(timeOfDay('2026-10-19T09:05:00')).toBe('09:05')
  expect(timeOfDay('2026-10-19T23:59:30')).toBe('23:59')
  expect(timeOfDay('')).toBe('')
  expect(timeOfDay('ontem')).toBe('')
})

test('rotuloDoFim traduz o que conhece e repete o resto', async () => {
  expect(endLabel('fim-da-fila')).toBe('fila acabou')
  expect(endLabel('limite-de-uso')).toBe('parou pela cota')
  expect(endLabel('prazo')).toBe('prazo chegou')
  expect(endLabel('xpto')).toBe('xpto')
})

test('avisoDe: run diferente em fase diferente não avisa; cota sem hora avisa sem a hora', async () => {
  const running = parseRun(RUN_START + CS1_START, 'cepa', 'r1')!
  const otherEnd = parseRun(RUN_START + ev({ evento: 'run_end', motivo: 'prazo', detalhe: 'x', quando: '2026-10-19T11:00:00' }), 'cepa', 'r2')!
  expect(noticeFor(running, otherEnd)).toBe(null)
  const quotaNoTime = parseRun(RUN_START + ev({ evento: 'pausa_de_cota', quando: '2026-10-19T10:31:00' }), 'cepa', 'r1')!
  expect(noticeFor(running, quotaNoTime)).toBe('cepa-until parado pela cota')
  const noDelivery = parseRun(RUN_START + ev({ evento: 'run_end', motivo: 'disjuntor', detalhe: 'x', quando: '2026-10-19T11:00:00' }), 'cepa', 'r1')!
  expect(noticeFor(running, noDelivery)).toBe('cepa-until cepa: disjuntor')
})

test('nível 4: item travado sai da tela, conta como travado e o run segue entre itens', async ($, on) => {
  const blockedEv = ev({ evento: 'item_end', id: 'CS-1', status: 'blocked', quando: LOCAL(-9) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + blockedEv))
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
  expect(await exact(ui, '1 travado · prazo 18:00')).toBeTruthy()
})

test('nível 4: depois do build verde o item sai da tela e a entrega conta', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + CS1_END + CS1_GREEN))
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
  expect(await exact(ui, '1 entregue · prazo 18:00')).toBeTruthy()
})

test('nível 4: build vermelho não conta entrega, e o item ainda está no build até o verify_vermelho', async ($, on) => {
  const redEv = ev({ evento: 'verify', id: 'CS-1', verde: false, motivo: 'saiu 1', quando: LOCAL(-3) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + CS1_END + redEv))
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
  expect(await exact(ui, 'nada entregue ainda · prazo 18:00')).toBeTruthy()
})

test('nível 4: depois do verify_vermelho o item sai da tela e conta como vermelho', async ($, on) => {
  const redEv = ev({ evento: 'verify', id: 'CS-1', verde: false, motivo: 'saiu 1', quando: LOCAL(-3) })
  const separateEv = ev({ evento: 'verify_vermelho', id: 'CS-1', quando: LOCAL(-3) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + CS1_END + redEv + separateEv))
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await exact(ui, '1 vermelho · prazo 18:00')).toBeTruthy()
})

test('nível 4: parado pela cota não mostra o item; cota sem hora fica só "parado pela cota"', async ($, on) => {
  const pauseEv = ev({ evento: 'pausa_de_cota', acorda: LOCAL(263), quando: LOCAL(-7) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + pauseEv))
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
  expect(await ui.findAll({ type: 'Text', text: 'entre itens' })).toEqual([])
})

test('nível 4: cota sem hora de retomar fica só "parado pela cota"', async ($, on) => {
  const noTime = ev({ evento: 'pausa_de_cota', quando: LOCAL(-7) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + noTime))
  expect(await exact(ui, 'parado pela cota')).toBeTruthy()
})

test('nível 4: limite de uso sem espera não vira pausa', async ($, on) => {
  const limitEv = ev({ evento: 'limite_de_uso', id: 'CS-1', reset_em: LOCAL(300), espera: false, quando: LOCAL(-5) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + limitEv))
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: 'parado pela cota' })).toEqual([])
})

test('nível 4: run encerrado não mostra "entre itens" nem o prazo; motivo desconhecido sai em vermelho', async ($, on) => {
  const end = ev({ evento: 'run_end', motivo: 'xpto', detalhe: 'coisa nova', quando: LOCAL(-12) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START + CS1_END + CS1_GREEN + end))
  const reason = await ui.find({ type: 'Text', text: 'xpto há 12 min' })
  expect(reason).toBeTruthy()
  expect(reason.props.color).toBe('red')
  expect(await ui.findAll({ type: 'Text', text: 'entre itens' })).toEqual([])
  expect(await exact(ui, '1 entregue')).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: 'prazo 18:00' })).toEqual([])
})

test('nível 4: run interrompido mostra o sinal e o tempo congela no fim', async ($, on) => {
  const startEv = ev({ evento: 'run_start', fila: 'cepa', prazo: LOCAL(8 * 60), quando: LOCAL(-72) })
  const signalEv = ev({ evento: 'run_interrompido', sinal: 'SIGTERM', id: 'CS-1', quando: LOCAL(-12) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(startEv + CS1_START + signalEv))
  expect(await ui.find({ type: 'Text', text: 'interrompido há 12 min' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'sinal SIGTERM' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'cepa · 1h00' })).toBeTruthy()
})

test('nível 4: run sem prazo não mostra "prazo"', async ($, on) => {
  const startEv = ev({ evento: 'run_start', fila: 'cepa', prazo: '', quando: LOCAL(-72) })
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(startEv + CS1_START))
  expect(await exact(ui, 'nada entregue ainda')).toBeTruthy()
})

test('só .jsonl conta como run, e o mais novo vence mesmo listado primeiro', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, {
    '/repo/.claude/programs/cepa/until/2026-10-19-1100.jsonl': ev({ evento: 'run_start', fila: 'cepa', prazo: '', quando: LOCAL(-2) }),
    '/repo/.claude/programs/cepa/until/2026-10-19-1100.log': 'log do run',
    '/repo/.claude/programs/cepa/until/2026-10-19-1200.review.md': RUN_START + CS1_START,
    ...UNTIL(RUN_START + CS1_START),
  })
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  expect(await ui.findAll({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toEqual([])
})

test('um run novo que começa e acaba entre duas varreduras não avisa', async ($, on) => {
  const toasts: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  const { files, clock } = await prepare($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START))
  await clock.advance(5000)
  files['/repo/.claude/programs/mods/until/2026-10-19-1200.jsonl'] =
    ev({ evento: 'run_start', fila: 'mods', prazo: '', quando: LOCAL(-2) })
    + ev({ evento: 'run_end', motivo: 'fim-da-fila', detalhe: 'x', quando: LOCAL(-1) })
  await clock.advance(30000)
  expect(toasts).toEqual([])
})

test('o run é relido a cada 5 s e as filas a cada 30 s, não antes', async ($, on) => {
  const { files, clock } = await prepare($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + CS1_START))
  const ui = await mountPane($)
  files['/repo/.claude/programs/cepa/until/2026-10-19-0900.jsonl'] += CS1_END + CS1_GREEN
  await clock.advance(4000)
  expect(await ui.find({ type: 'Text', text: '▶ CS-1 · primeiro item da fila' })).toBeTruthy()
  await clock.advance(1000)
  expect(await ui.find({ type: 'Text', text: 'entre itens' })).toBeTruthy()
  files['/repo/.claude/programs/mods/until/2026-10-19-1200.jsonl'] = ev({ evento: 'run_start', fila: 'mods', prazo: '', quando: LOCAL(-2) })
  await clock.advance(24000)
  expect(await ui.findAll({ type: 'Text', text: 'mods · 2min' })).toEqual([])
  await clock.advance(1000)
  expect(await ui.find({ type: 'Text', text: 'mods · 2min' })).toBeTruthy()
})

test('nível 4: item na primeira tentativa não mostra "tentativa"', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, UNTIL(RUN_START + ev({ evento: 'item_start', id: 'CS-1', title: 'primeiro item da fila', tentativa: 1, quando: LOCAL(-12) })))
  expect(await exact(ui, 'item há 12min')).toBeTruthy()
})

test('parseRun aguenta registro malformado: linha null, run_start sem fila, item_end sem item_start', async () => {
  const r = parseRun(RUN_START + 'null\n' + CS1_START, 'cepa', 'x')!
  expect(r.item?.id).toBe('CS-1')
  const noQueue = ev({ evento: 'run_start', prazo: '', quando: '2026-10-19T09:00:00' })
  expect(parseRun(noQueue, 'mods', 'x')!.queue).toBe('mods')
  const orphan = ev({ evento: 'item_end', id: 'CS-9', status: 'done', quando: '2026-10-19T09:05:00' })
  expect(parseRun(RUN_START + orphan, 'cepa', 'x')!.item).toBe(null)
})

// ─── Gate notice ─────────────────────────────────────────────────────────────

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
const GA_STOPPED = `[gate-advance] BLOCKED: cannot run advancement command — build is FAILURE since 2026-10-19T10:00:00 (command: \`pytest\`): stopped by claude-code.
  Suggestion: The build did not fail — it was stopped before it ended. Re-run it with a \`timeout\` that fits it.`
const GA_OTHER = `[gate-advance] BLOCKED: cannot run advancement command — build status is 'X' — unrecognized.`
const AG_DONE = `[acceptance-gate] BLOCKED: cannot move WEGO-1891 to done — no acceptance audit found
  Searched:
    - /repo/.claude/acceptance/WEGO-1891.yaml`
const AG_REVIEW = `[acceptance-gate] BLOCKED: cannot move WEGO-2202 to review — acceptance audit is 'incomplete', not 'complete'.
  Artifact: /repo/.claude/acceptance/WEGO-2202.yaml`
const AG_EMPTY = `[acceptance-gate] BLOCKED: cannot move WEGO-2218 to done — the last real build is EMPTY: the test filter in \`pytest -k x\` matched zero tests (recorded 2026-10-19 in /repo/.claude/last-build.json).`
const WG_SRC = `BLOCK: 1
  source \`session/oncoto\` is held by a LIVE session — mac:/repo (active 2 min ago)
    its history may be rewritten under you; ask it to land or close first.`
const WG_BOTH = `BLOCK: 2
  source \`session/oncoto\` is held by a LIVE session — mac:/repo (active 2 min ago)
  destination \`main\` is held by a LIVE session — mac:/repo2 (active 1 min ago)`

test('leBloqueio traduz cada motivo do gate-advance em uma frase leiga', async () => {
  expect(readBlock(GA_BASELINE)).toEqual({
    gate: 'gate-advance',
    phrase: 'Compartilhar barrado: nenhum build foi verificado neste projeto ainda. Rode o verify do projeto antes.',
  })
  expect(readBlock(GA_STALE)?.phrase).toBe('Barrado: o código mudou depois do último build (src/a.py). Rode o verify de novo.')
  expect(readBlock(GA_EMPTY)?.phrase).toBe('Barrado: o último build passou sem rodar teste nenhum. Corrija o filtro de testes e rode de novo.')
  expect(readBlock(GA_FAIL)?.phrase).toBe('Barrado: o último build falhou. Conserte e rode o verify de novo.')
  expect(readBlock(GA_STOPPED)?.phrase).toBe('Barrado: o último build foi interrompido antes de acabar. Rode de novo com tempo suficiente.')
  expect(readBlock(GA_OTHER)?.phrase).toBe('Barrado pelo gate-advance: o build não está verde.')
})

test('leBloqueio traduz o acceptance-gate com a chave do card', async () => {
  expect(readBlock(AG_DONE)).toEqual({
    gate: 'acceptance-gate',
    phrase: 'WEGO-1891 barrado: não vai para Done sem a auditoria do completion-auditor.',
  })
  expect(readBlock(AG_REVIEW)?.phrase).toBe(
    "WEGO-2202 barrado: a auditoria de aceite está 'incomplete', não completa. Feche as lacunas e rode o completion-auditor de novo.",
  )
  expect(readBlock(AG_EMPTY)?.phrase).toBe('WEGO-2218 barrado: o último build não rodou teste nenhum, então não prova nada.')
  expect(readBlock('[acceptance-gate] BLOCKED: algo novo')?.phrase).toBe('O card barrado pelo acceptance-gate.')
})

test('leBloqueio ignora erro que não é gate; o aviso de commit sem baseline não é bloqueio', async () => {
  expect(readBlock('Error: command not found: foo')).toBe(null)
  expect(readBlock('⚠  COMMIT WITHOUT BUILD VERIFICATION ⚠ ... will be BLOCKED until')).toBe(null)
  expect(readBlock('')).toBe(null)
})

test('leGuarda só lê stdout de Bash que chamou o worktree-guard e começa com BLOCK:', async () => {
  const cmd = 'python3 "/x/hooks/worktree-guard.py" session/oncoto'
  expect(readGuard(cmd, WG_SRC)).toEqual({
    gate: 'worktree-guard',
    phrase: 'Merge barrado: a branch session/oncoto está em uso por outra sessão viva. Peça para ela fechar ou aterrissar antes.',
  })
  expect(readGuard(cmd, WG_BOTH)?.phrase).toBe(
    'Merge barrado: as branches session/oncoto e main estão em uso por outra sessão viva. Peça para ela fechar ou aterrissar antes.',
  )
  expect(readGuard(cmd, 'BLOCK: 1\n  (detalhe fora do formato)')?.phrase).toBe(
    'Merge barrado: outra sessão viva está na branch. Peça para ela fechar ou aterrissar antes.',
  )
  expect(readGuard(cmd, 'OK\nNo other live session')).toBe(null)
  expect(readGuard('cat registro.txt', WG_SRC)).toBe(null)
  expect(readGuard(cmd, 'aviso: BLOCK: 1')).toBe(null)
})

// The deny of the Python hook reaches the mod's tool.call as an error result with the reason in text.
const blockAsPython = (on: any, reason: string) => {
  on('classic.PreToolUse', async () => ({ deny: reason }))
}

test('gate-advance barra o push: toast com a frase leiga e linha no cartão Modo', async ($, on) => {
  const toasts: any[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e)
    return { value: undefined }
  })
  blockAsPython(on, GA_BASELINE)
  await prepare($, on, 'sessao-a', INTENT_FILE, { '.claude/session-mode': MODE })
  const r: any = await $.tool.call({ tool: 'Bash', command: 'git push' })
  expect(r.isError).toBe(true)
  expect(r.text).toBe(GA_BASELINE)
  expect(toasts.map(a => a.text)).toEqual([
    'Compartilhar barrado: nenhum build foi verificado neste projeto ainda. Rode o verify do projeto antes.',
  ])
  expect(toasts[0].timeoutMs).toBe(8000)
  const ui = await mountPane($)
  const phrase = await ui.find({ type: 'Text', text: 'Compartilhar barrado: nenhum build foi verificado neste projeto ainda. Rode o verify do projeto antes.' })
  expect(phrase?.props?.color).toBe('yellow')
  expect(await ui.find({ type: 'Text', text: 'gate-advance há 0 min' })).toBeTruthy()
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(texts.indexOf('Modo') < texts.indexOf('gate-advance há 0 min')).toBe(true)
  expect(texts.indexOf('gate-advance há 0 min') < texts.indexOf('Run')).toBe(true)
})

test('acceptance-gate barra a transição no Jira (MCP): toast com a chave do card', async ($, on) => {
  const toasts: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  blockAsPython(on, AG_REVIEW)
  await prepare($, on, 'sessao-a', INTENT_FILE)
  const r: any = await $.tool.call({
    tool: 'mcp__Atlassian__transitionJiraIssue',
    cloudId: 'c', issueIdOrKey: 'WEGO-2202', transition: { id: '31' },
  } as any)
  expect(r.isError).toBe(true)
  expect(toasts).toEqual([
    "WEGO-2202 barrado: a auditoria de aceite está 'incomplete', não completa. Feche as lacunas e rode o completion-auditor de novo.",
  ])
})

test('worktree-guard imprime BLOCK: no stdout de um Bash que saiu com 0: toast, e o resultado volta igual', async ($, on) => {
  const toasts: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  const reply = { result: { stdout: WG_SRC, stderr: '', interrupted: false } }
  on('tool.call', { tool: 'Bash' }, async () => reply)
  await prepare($, on, 'sessao-a', INTENT_FILE)
  const r: any = await $.tool.call({ tool: 'Bash', command: 'python3 "/x/hooks/worktree-guard.py" session/oncoto' })
  expect(r.result).toEqual(reply.result)
  expect(r.deny).toBe(undefined)
  expect(toasts).toEqual([
    'Merge barrado: a branch session/oncoto está em uso por outra sessão viva. Peça para ela fechar ou aterrissar antes.',
  ])
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: 'worktree-guard há 0 min' })).toBeTruthy()
})

test('worktree-guard com OK, Bash comum e erro que não é gate: nem toast nem linha no cartão', async ($, on) => {
  const toasts: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  let forbids = false
  on('classic.PreToolUse', async () => (forbids ? { deny: 'Error: this command is forbidden by another plugin' } : {}))
  on('tool.call', { tool: 'Bash' }, async ($: any, e: any) =>
    e.command.includes('worktree-guard')
      ? { result: { stdout: 'OK\nNo other live session is on `session/x` — safe to merge.', stderr: '', interrupted: false } }
      : { result: { stdout: 'BLOCK: 1\nisto é só a saída de um cat', stderr: '', interrupted: false } })
  await prepare($, on, 'sessao-a', INTENT_FILE)
  await $.tool.call({ tool: 'Bash', command: 'python3 "/x/hooks/worktree-guard.py" session/x' })
  await $.tool.call({ tool: 'Bash', command: 'cat registro.txt' })
  forbids = true
  const r: any = await $.tool.call({ tool: 'Bash', command: 'rm -rf x' })
  expect(r.isError).toBe(true)
  expect(toasts).toEqual([])
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: /bloqueio|barrad/ })).toBeFalsy()
})

test('segundo bloqueio substitui o primeiro no cartão e conta as vezes; a idade cresce com o relógio', async ($, on) => {
  const toasts: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  let reason = GA_STALE
  on('classic.PreToolUse', async () => ({ deny: reason }))
  const { clock } = await prepare($, on, 'sessao-a', INTENT_FILE)
  await $.tool.call({ tool: 'Bash', command: 'git commit -m x' })
  reason = AG_DONE
  await $.tool.call({ tool: 'mcp__Atlassian__transitionJiraIssue', transition: { id: '41' } } as any)
  expect(toasts).toEqual([
    'Barrado: o código mudou depois do último build (src/a.py). Rode o verify de novo.',
    'WEGO-1891 barrado: não vai para Done sem a auditoria do completion-auditor.',
  ])
  await clock.advance(3 * 60000)
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: 'WEGO-1891 barrado: não vai para Done sem a auditoria do completion-auditor.' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /o código mudou/ })).toBeFalsy()
  expect(await ui.find({ type: 'Text', text: 'acceptance-gate há 3 min · 2º bloqueio da sessão' })).toBeTruthy()
})

test('sem bloqueio na sessão, o cartão Modo não tem a linha do gate', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, { '.claude/session-mode': MODE })
  expect(await ui.find({ type: 'Text', text: /bloqueio|barrad/ })).toBeFalsy()
})

// ─── Survivors of the 1st proof-reviewer round ───────────────────────────────

test('toast que lança não atrapalha a chamada: o resultado do gate volta intacto', async ($, on) => {
  on('ui.toast', async () => {
    throw new Error('sem tela')
  })
  blockAsPython(on, GA_BASELINE)
  await prepare($, on, 'sessao-a', INTENT_FILE)
  const r: any = await $.tool.call({ tool: 'Bash', command: 'git push' })
  expect(r.isError).toBe(true)
  expect(r.text).toBe(GA_BASELINE)
})

test('STALE sem o arquivo da edição sai sem parênteses', async () => {
  expect(readBlock('[gate-advance] BLOCKED: cannot run advancement command — build is STALE.')?.phrase)
    .toBe('Barrado: o código mudou depois do último build. Rode o verify de novo.')
})

test('leGuarda: linha em branco antes do BLOCK: conta; BLOCK: sem número ou sem espaço não conta', async () => {
  const cmd = 'python3 "/x/hooks/worktree-guard.py" session/x'
  expect(readGuard(cmd, '\n\n' + WG_SRC)?.gate).toBe('worktree-guard')
  expect(readGuard(cmd, 'BLOCK: abc\n  source `session/x` is held by a LIVE session')).toBe(null)
  expect(readGuard(cmd, 'BLOCK:1\n  source `session/x` is held by a LIVE session')).toBe(null)
})

test('stdout com BLOCK: de uma ferramenta que não é Bash não é o worktree-guard', async ($, on) => {
  const toasts: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('tool.call', { tool: 'mcp__x__run' }, async () => ({ result: { stdout: WG_SRC, stderr: '' } }))
  await prepare($, on, 'sessao-a', INTENT_FILE)
  await $.tool.call({ tool: 'mcp__x__run', command: 'python3 worktree-guard.py session/x' } as any)
  expect(toasts).toEqual([])
})

test('resultado sem erro cujo texto cita o gate-advance não é bloqueio', async ($, on) => {
  const toasts: string[] = []
  on('ui.toast', async ($: any, e: any) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('tool.call', { tool: 'Bash' }, async () => ({
    result: { stdout: GA_BASELINE, stderr: '', interrupted: false },
    text: GA_BASELINE,
  }))
  await prepare($, on, 'sessao-a', INTENT_FILE)
  await $.tool.call({ tool: 'Bash', command: 'cat registro-do-gate.txt' })
  expect(toasts).toEqual([])
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: /barrad/ })).toBeFalsy()
})

// ── level 0: the Epics and the queue state of each cycle ─────────────────────

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
  '/repo/.claude/programs/cepa-espiral-c1/plan.yaml': QUEUE_YAML('single-track', c1),
})

test('parseEpic lê nome, status, padrão de fila e os ciclos da escada', async () => {
  const e = parseEpic('cepa-em-espiral.md', EPIC)!
  expect(e.file).toBe('cepa-em-espiral')
  expect(e.name).toBe('Cepa em espiral')
  expect(e.status).toBe('rascunho')
  expect(e.queuePattern).toBe('cepa-espiral-c<N>')
  expect(e.cycles).toEqual([{ number: 1, label: '1. Encadear' }, { number: 2, label: '2. Conduzir' }])
  expect(parseEpic('x.md', '# Outra coisa\n')).toBe(null)
  expect(parseEpic('x.md', '# Epic: Sem escada\n\n**Status:** pronta\n')!.cycles).toEqual([])
  // with no Status line, the Epic is a draft (rascunho)
  expect(parseEpic('x.md', '# Epic: Novo\n').status).toBe('rascunho')
  // two-digit cycle
  const ten = parseEpic('x.md', '# Epic: Dez\n\n## Escada de valor\n\n| Ciclo | R |\n|---|---|\n| 10. Dez | x |\n')!
  expect(ten.cycles).toEqual([{ number: 10, label: '10. Dez' }])
  // only the ladder table: "3. algo" prose in the section and a table of the next section stay out
  const withJunk = EPIC.replace('| 2. Conduzir | O dono dorme | z | depois |\n', '| 2. Conduzir | O dono dorme | z | depois |\n\n3. isto é prosa, não ciclo\n')
    + '\n| 4. Extra | de outra tabela |\n|---|---|\n| 5. Mais | y |\n'
  expect(parseEpic('cepa-em-espiral.md', withJunk)!.cycles.map(c => c.number)).toEqual([1, 2])
})

test('filaDoCiclo: pelo source do --from-epic, pelo padrão da Construção, pelo nome do arquivo', async () => {
  const e = parseEpic('cepa-em-espiral.md', EPIC)!
  const queue = (name: string, source: string) => countQueue(name, `mode: single-track\nsource: ${source}\nitems:\n`)!
  const bySource = queue('qualquer', 'docs/epics/cepa-em-espiral.md, ciclo 2 (3 peças de "O que\n  atravessa"; ordem herdada do texto)')
  const byPattern = queue('cepa-espiral-c2', 'docs/spec/x.md')
  const byFile = queue('cepa-em-espiral-c2', 'BACKLOG.md')
  expect(bySource.source).toBe('docs/epics/cepa-em-espiral.md, ciclo 2 (3 peças de "O que atravessa"; ordem herdada do texto)')
  expect(queueOfCycle(e, 2, [byFile, byPattern, bySource])).toBe(bySource)
  expect(queueOfCycle(e, 2, [byFile, byPattern])).toBe(byPattern)
  expect(queueOfCycle(e, 2, [byFile])).toBe(byFile)
  expect(queueOfCycle(e, 1, [byFile, byPattern, bySource])).toBe(null)
  // the source must cite THIS Epic: `outro.md, ciclo 2` does not link to the cycle 2 here
  expect(queueOfCycle(e, 2, [queue('q', 'docs/epics/outro.md, ciclo 2')])).toBe(null)
  // `ciclo 12` is not cycle 1
  expect(queueOfCycle(e, 1, [queue('q', 'docs/epics/cepa-em-espiral.md, ciclo 12')])).toBe(null)
})

test('estado do ciclo: sem fila, andando, travado, demonstrável; descartados fora da conta', async () => {
  const f = (st: string[]) => countQueue('f', QUEUE_YAML('single-track', st))
  expect(cycleLine(null)).toBe('sem fila')
  expect(cycleLine(f(['done', 'pending', 'dropped']))).toBe('1/2 feitos')
  expect(cycleState(f(['done', 'pending']))).toBe('andando')
  expect(cycleLine(f(['done', 'blocked', 'pending']))).toBe('travado · 1/3 feitos')
  expect(cycleState(f(['blocked', 'in_progress']))).toBe('andando')
  expect(cycleLine(f(['done', 'done', 'dropped']))).toBe('demonstrável')
  expect(cycleState(f(['dropped']))).toBe('andando')
  // in progress counts as open: it is not demonstrable and enters the total
  expect(cycleState(f(['done', 'in_progress']))).toBe('andando')
  expect(cycleLine(f(['done', 'in_progress']))).toBe('1/2 feitos')
  expect(cycleLine(f(['done', 'in_progress', 'pending']))).toBe('1/3 feitos')
})

test('nível 0: um bloco por Epic, uma linha por ciclo com o estado da fila, antes de Filas', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, EPICS())
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(texts.indexOf('Épicos')).toBeGreaterThanOrEqual(0)
  expect(texts.indexOf('Épicos')).toBeLessThan(texts.indexOf('Filas'))
  expect(await ui.find({ type: 'Text', text: '1 Epic' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'Cepa em espiral' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'rascunho' })).toBeTruthy()
  const line = (label: string) => texts.slice(texts.indexOf(label), texts.indexOf(label) + 2)
  expect(line('▶ 1. Encadear')).toEqual(['▶ 1. Encadear', '1/2 feitos'])
  expect(line('○ 2. Conduzir')).toEqual(['○ 2. Conduzir', 'sem fila'])
  expect((await ui.find({ type: 'Text', text: '1/2 feitos' })).props.color).toBe('cyan')
})

test('nível 0: ciclo demonstrável em verde e travado em vermelho', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, {
    ...EPICS(['done', 'done']),
    '/repo/.claude/programs/outro-c1/plan.yaml': QUEUE_YAML('single-track', ['blocked', 'done']),
    '/repo/docs/epics/outro.md': '# Epic: Outro\n\n**Status:** pronta\n\n## Escada de valor\n\n| Ciclo | Roteiro |\n|---|---|\n| 1. Só | x |\n',
  })
  const green = await ui.find({ type: 'Text', text: 'demonstrável' })
  expect(green.props.color).toBe('green')
  expect((await ui.find({ type: 'Text', text: '✓ 1. Encadear' })).props.color).toBe('green')
  const redEv = await ui.find({ type: 'Text', text: 'travado · 1/2 feitos' })
  expect(redEv.props.color).toBe('red')
  expect(await ui.find({ type: 'Text', text: '2 Epics' })).toBeTruthy()
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  // alphabetical order by name: Cepa em espiral before Outro
  expect(texts.indexOf('Cepa em espiral')).toBeLessThan(texts.indexOf('Outro'))
})

test('sem docs/epics, o nível 0 diz isso', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE)
  expect(await ui.find({ type: 'Text', text: 'nenhum Epic em docs/epics' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'docs/epics' })).toBeTruthy()
})

test('sem intenção, o nível 0 continua lá', async ($, on) => {
  const ui = await openPane($, on, 'sessao-b', null, EPICS())
  expect(await ui.find({ type: 'Text', text: '○ 2. Conduzir' })).toBeTruthy()
})

test('nível 0: item em andamento mantém o ciclo andando e entra na conta', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, EPICS(['done', 'in_progress']))
  expect(await lineOf(ui, '▶ 1. Encadear')).toEqual(['▶ 1. Encadear', '1/2 feitos'])
  expect(await ui.find({ type: 'Text', text: 'demonstrável' })).toBeFalsy()
})

test('nível 0: source que cita outro Epic não liga a fila a este', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, {
    '/repo/docs/epics/cepa-em-espiral.md': EPIC,
    '/repo/.claude/programs/qualquer/plan.yaml': QUEUE_WITH_SOURCE('docs/epics/outro.md, ciclo 2', ['done', 'pending']),
  })
  expect(await lineOf(ui, '○ 2. Conduzir')).toEqual(['○ 2. Conduzir', 'sem fila'])
})

test('nível 0: um .md sem "# Epic:" em docs/epics é ignorado, não derruba o painel', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, { ...EPICS(), '/repo/docs/epics/README.md': '# Como escrever um Epic\n' })
  expect(await ui.find({ type: 'Text', text: '1 Epic' })).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: 'Cepa em espiral' })).toBeTruthy()
})

test('nível 0: Epics em ordem alfabética pelo nome, não pela ordem dos arquivos', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, {
    '/repo/docs/epics/zz.md': '# Epic: Alfa\n',
    '/repo/docs/epics/aa.md': '# Epic: Zulu\n',
    '/repo/docs/epics/mm.md': '# Epic: Mike\n',
  })
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  const order = ['Alfa', 'Mike', 'Zulu'].map(n => texts.indexOf(n))
  expect(order.every(i => i >= 0)).toBe(true)
  expect(order).toEqual([...order].sort((a, b) => a - b))
})

test('sem intenção, Épicos também vem antes de Filas', async ($, on) => {
  const ui = await openPane($, on, 'sessao-b', null, EPICS())
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  expect(texts.indexOf('Épicos')).toBeGreaterThanOrEqual(0)
  expect(texts.indexOf('Épicos')).toBeLessThan(texts.indexOf('Filas'))
})

// Queue with `source:` in the format that /common:plan --from-epic writes.
const QUEUE_WITH_SOURCE = (source: string, status: string[]) =>
  QUEUE_YAML('single-track', status).replace('items:\n', `source: ${source}\nitems:\n`)

const lineOf = async (ui: any, label: string) => {
  const texts = (await ui.findAll({ type: 'Text' })).map((t: any) => t.text)
  return texts.slice(texts.indexOf(label), texts.indexOf(label) + 2)
}

test('nível 0, regra 1: fila de nome qualquer entra no ciclo que o source cita', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, {
    '/repo/docs/epics/cepa-em-espiral.md': EPIC,
    '/repo/.claude/programs/qualquer/plan.yaml': QUEUE_WITH_SOURCE('docs/epics/cepa-em-espiral.md, ciclo 2 (1 peça)', ['done', 'done', 'pending']),
  })
  expect(await lineOf(ui, '▶ 2. Conduzir')).toEqual(['▶ 2. Conduzir', '2/3 feitos'])
  expect(await lineOf(ui, '○ 1. Encadear')).toEqual(['○ 1. Encadear', 'sem fila'])
})

test('nível 0, regra 3: sem source e sem o padrão da Construção, vale <arquivo do epic>-c<N>', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, {
    '/repo/docs/epics/cepa-em-espiral.md': EPIC,
    '/repo/.claude/programs/cepa-em-espiral-c1/plan.yaml': QUEUE_YAML('single-track', ['done', 'done']),
  })
  expect(await lineOf(ui, '✓ 1. Encadear')).toEqual(['✓ 1. Encadear', 'demonstrável'])
  expect(await lineOf(ui, '○ 2. Conduzir')).toEqual(['○ 2. Conduzir', 'sem fila'])
})

test('nível 0, precedência: o source vence o padrão da Construção, que vence o nome do arquivo', async ($, on) => {
  const ui = await openPane($, on, 'sessao-a', INTENT_FILE, {
    '/repo/docs/epics/cepa-em-espiral.md': EPIC,
    '/repo/.claude/programs/qualquer/plan.yaml': QUEUE_WITH_SOURCE('docs/epics/cepa-em-espiral.md, ciclo 1', ['done', 'pending', 'pending']),
    '/repo/.claude/programs/cepa-espiral-c1/plan.yaml': QUEUE_YAML('single-track', ['done', 'done']),
    '/repo/.claude/programs/cepa-em-espiral-c1/plan.yaml': QUEUE_YAML('single-track', ['blocked']),
    '/repo/.claude/programs/cepa-espiral-c2/plan.yaml': QUEUE_YAML('single-track', ['done', 'pending']),
    '/repo/.claude/programs/cepa-em-espiral-c2/plan.yaml': QUEUE_YAML('single-track', ['blocked']),
  })
  // cycle 1: source (1/3), not the pattern (demonstrável) nor the file (travado)
  expect(await lineOf(ui, '▶ 1. Encadear')).toEqual(['▶ 1. Encadear', '1/3 feitos'])
  // cycle 2: no source, pattern (1/2), not the file (travado)
  expect(await lineOf(ui, '▶ 2. Conduzir')).toEqual(['▶ 2. Conduzir', '1/2 feitos'])
})

test('os Epics são relidos no fim do turno: um arquivo novo aparece sem reiniciar', async ($, on) => {
  on('turn.complete', async () => ({ text: 'x' }))
  const { files } = await prepare($, on, 'sessao-a', INTENT_FILE)
  const ui = await mountPane($)
  expect(await ui.find({ type: 'Text', text: 'nenhum Epic em docs/epics' })).toBeTruthy()
  Object.assign(files, EPICS())
  await $.turn.complete({ answer: 'x', durationMs: 1, isAborted: false, turnId: 't1', reason: 'answer' })
  expect(await ui.find({ type: 'Text', text: 'Cepa em espiral' })).toBeTruthy()
})
