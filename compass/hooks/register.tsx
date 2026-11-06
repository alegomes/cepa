import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { Epic, Queue } from '../types'
import { queueOfCycle, cycleLine, cycleState, MARK, parseEpic } from './epics'
import { isOpen, COLUMNS, countQueue } from './queues'
import { age, parseIntent } from './intent'
import { COLOR, buildLine, parseBuild } from './build'
import { countDeviations, readExits, parseMode } from './mode'
import { readBlock, readGuard } from './gate'
import type { Blocked } from './gate'
import { noticeFor, tally, timeOfDay, parseRun, endLabel, itemTime, runTime } from './until'
import type { Run } from './until'

// Orientation panel in levels, from the highest to the lowest:
// 0. Epics from docs/epics and the state of the queue of each ladder cycle;
// 1. the repo's queues and a summary of their items; 2. the session's intent, plan and step;
// 3. the session mode, its exit condition, the build state and the registered deviations;
// 4. the most recent cepa-until run: current item, time, tally and how it ended.
// The Modo card also shows the last gate that blocked an action, in one plain sentence.
const PANE = 'compass'
const OPEN = { id: PANE, title: 'Compass', columns: 48 }
const INTENT_FILE = '.claude/session-intent'
const MODE_FILE = '.claude/session-mode'
const DEVIATIONS_FILE = '.claude/deviations.md'
// Legacy name, still present in client repos that predate the rename.
const DEVIATIONS_LEGACY = '.claude/desvios.md'
const BUILD_FILE = '.claude/last-build.json'
const intentText = atom({ plugin: 'compass', key: 'texto' } as const, null)
const now = atom({ plugin: 'compass', key: 'agora' } as const, 0)
const queues = atom({ plugin: 'compass', key: 'filas' } as const, [])
const epics = atom({ plugin: 'compass', key: 'epics' } as const, [])
const mode = atom({ plugin: 'compass', key: 'modo' } as const, null)
const deviations = atom({ plugin: 'compass', key: 'desvios' } as const, null)
const build = atom({ plugin: 'compass', key: 'build' } as const, null)
const exits = atom({ plugin: 'compass', key: 'saidas' } as const, {})
const until = atom({ plugin: 'compass', key: 'until' } as const, null)
const gate = atom({ plugin: 'compass', key: 'gate' } as const, null)
const END_SOUND = 'sons/fim.wav'

let previousStep = 0
let previousDeviations = -1
let previousRun: Run | null = null
// Path of the most recent `.jsonl`, found every 30 s along with the queues.
let runLog: { path: string; queue: string; id: string } | null = null

const readIfExists = async ($: EngineInterface, path: string) =>
  (await $.fs.exists(path)) ? await $.fs.read(path) : null

const readDeviations = async ($: EngineInterface) => (await readIfExists($, DEVIATIONS_FILE)) ?? (await readIfExists($, DEVIATIONS_LEGACY))

async function reread($: EngineInterface) {
  const fresh = await readIfExists($, INTENT_FILE)
  const ms = await $.clock.now()
  await update($, now, () => ms)
  await rereadMode($)
  await rereadRun($)
  if (fresh === (await read($, intentText))) return
  await update($, intentText, () => fresh)
  const intent = fresh === null ? null : parseIntent(fresh)
  if (intent && previousStep > 0 && intent.step !== previousStep) {
    const name = intent.plan[intent.step - 1]
    $.ui.toast(name ? `Passo ${intent.step}: ${name}` : 'Plano cumprido')
  }
  previousStep = intent?.step ?? 0
}

async function rereadMode($: EngineInterface) {
  const modeText = await readIfExists($, MODE_FILE)
  await update($, mode, () => modeText)
  const deviationsText = await readDeviations($)
  await update($, deviations, () => deviationsText)
  const buildText = await readIfExists($, BUILD_FILE)
  await update($, build, () => buildText)
  const d = countDeviations(deviationsText ?? '')
  const total = d.open + d.resolved
  if (previousDeviations >= 0 && total > previousDeviations) $.ui.toast(`Desvio registrado: ${d.last}`)
  previousDeviations = total
}

// The run log is reread every 5 s: the current item and the time change without a new turn.
async function rereadRun($: EngineInterface) {
  const reg = runLog
  const runText = reg === null ? null : await readIfExists($, reg.path)
  const r = runText === null || reg === null ? null : parseRun(runText, reg.queue, reg.id)
  await update($, until, () => (reg === null || runText === null ? null : { queue: reg.queue, id: reg.id, text: runText }))
  if (r !== null) {
    const notice = noticeFor(previousRun, r)
    if (notice !== null) {
      $.ui.toast(notice)
      void $.audio.play({ asset: END_SOUND }).catch(() => {
        // no player (Linux, Windows) or no file: the toast already warned
      })
    }
  }
  previousRun = r
}

// Only observes the result of the call: the gate that blocked already answered, and the answer
// comes back unchanged. Nothing here rewrites the call or the reason.
async function observeGate($: EngineInterface, command: string, r: { isError?: true; text?: string; result?: unknown }) {
  let b = null
  if (r.isError === true && typeof r.text === 'string') b = readBlock(r.text)
  else if (command !== '' && r.isError === undefined) {
    const output = r.result as { stdout?: unknown } | null | undefined
    const stdout = typeof output?.stdout === 'string' ? output.stdout : typeof r.text === 'string' ? r.text : ''
    b = readGuard(command, stdout)
  }
  if (b === null) return
  const when = new Date(await $.clock.now()).toISOString()
  const previous = await read($, gate)
  const entry: Blocked = { ...b, when, times: (previous?.times ?? 0) + 1 }
  await update($, gate, () => entry)
  $.ui.toast(b.phrase, { timeoutMs: 8000 })
}

// The modes table does not change during the session; read once.
async function rereadExits($: EngineInterface) {
  try {
    const r = await $.process.run(['cepa-modes', '--json'])
    if (r.exitCode === 0) await update($, exits, () => readExits(r.stdout))
  } catch {
    // cepa-modes not on the PATH: the card shows the mode without the exit condition
  }
}

// The Epics also live in the main checkout: `docs/epics/<name>.md`, one per file.
async function rereadEpics($: EngineInterface, dir: string) {
  const loaded: Epic[] = []
  if (await $.fs.exists(dir)) {
    for (const file of await $.fs.list(dir)) {
      if (file.kind !== 'file' || !file.name.endsWith('.md')) continue
      const e = parseEpic(file.name, await $.fs.read(`${dir}/${file.name}`))
      if (e) loaded.push(e)
    }
  }
  loaded.sort((a, b) => a.name.localeCompare(b.name))
  await update($, epics, () => loaded)
}

// The queues live in the main checkout (where `cepa-plan` writes), not in the worktree.
async function rereadQueues($: EngineInterface) {
  const git = await $.process.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'])
  if (git.exitCode !== 0) return
  const root = git.stdout.trim().replace(/\/\.git$/, '')
  await rereadEpics($, `${root}/docs/epics`)
  const loadedQueues: Queue[] = []
  let latest: { path: string; queue: string; id: string } | null = null
  // Two layouts during the transition: `.claude/queues/<n>/queue.yaml` (new) wins over
  // `.claude/programs/<n>/plan.yaml` (old) when the name exists in both.
  const seen = new Set<string>()
  for (const [base, planFile] of [['.claude/queues', 'queue.yaml'], ['.claude/programs', 'plan.yaml']]) {
    const dir = `${root}/${base}`
    if (!(await $.fs.exists(dir))) continue
    for (const dirEntry of await $.fs.list(dir)) {
      if (dirEntry.kind !== 'dir' || seen.has(dirEntry.name)) continue
      seen.add(dirEntry.name)
      const planPath = `${dir}/${dirEntry.name}/${planFile}`
      if (await $.fs.exists(planPath)) {
        const queue = countQueue(dirEntry.name, await $.fs.read(planPath))
        if (queue) loadedQueues.push(queue)
      }
      // The most recent run across all queues: the `.jsonl` name is the start date and time.
      const runsDir = `${dir}/${dirEntry.name}/until`
      if (!(await $.fs.exists(runsDir))) continue
      for (const file of await $.fs.list(runsDir)) {
        if (file.kind !== 'file' || !file.name.endsWith('.jsonl')) continue
        const id = file.name.slice(0, -'.jsonl'.length)
        if (latest === null || id > latest.id) latest = { path: `${runsDir}/${file.name}`, queue: dirEntry.name, id }
      }
    }
  }
  runLog = latest
  const openCount = (f: Queue) => f.pending + f.inProgress + f.blocked
  loadedQueues.sort((a, b) => openCount(b) - openCount(a) || a.name.localeCompare(b.name))
  await update($, queues, () => loadedQueues)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'compass',
      description: 'Abre o painel de orientação: épicos, filas, intenção, modo, build, desvios e o run do cepa-until',
    })
    await rereadExits($)
    await rereadQueues($)
    await reread($)
    $.clock.every(5000, () => reread($))
    $.clock.every(30000, () => rereadQueues($))
    void $.ui.open(OPEN)

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    await rereadQueues($)
    await reread($)

    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const r = await next(e)
    try {
      await observeGate($, e.tool === 'Bash' ? e.command : '', r)
    } catch {
      // the notice never gets in the way of the call: the result comes back unchanged
    }

    return r
  })

  on('command.run', { command: 'compass' }, async $ => {
    await $.ui.open(OPEN)

    return { text: 'Painel de orientação aberto.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const raw = await read($, intentText)
    const intent = raw === null ? null : parseIntent(raw)
    const queueList = await read($, queues)
    const openQueues = queueList.filter(isOpen)
    const epicList = await read($, epics)
    const modeText = await read($, mode)
    const m = modeText === null ? null : parseMode(modeText)
    const exitText = m ? (await read($, exits))[m.name] ?? '' : ''
    const deviationsText = await read($, deviations)
    const d = countDeviations(deviationsText ?? '')
    const buildText = await read($, build)
    const b = buildText === null ? null : parseBuild(buildText)
    const nowMs = await read($, now)
    const rawRun = await read($, until)
    const r = rawRun === null ? null : parseRun(rawRun.text, rawRun.queue, rawRun.id)
    const g = await read($, gate)

    const card = (title: string, right: string, body: RenderChildren) => (
      <Box flexDirection="column" borderStyle="round" borderDimColor paddingX={1}>
        <Box flexDirection="row" justifyContent="space-between">
          <Text bold>{title}</Text>
          <Text dimColor>{right}</Text>
        </Box>
        {body}
      </Box>
    )

    const epicsLevel = card(
      'Épicos',
      epicList.length === 0 ? 'docs/epics' : epicList.length === 1 ? '1 Epic' : `${epicList.length} Epics`,
      <Box flexDirection="column" marginTop={1}>
        {epicList.length === 0 && <Text dimColor>nenhum Epic em docs/epics</Text>}
        {epicList.map((e, i) => (
          <Box flexDirection="column" marginTop={i === 0 ? 0 : 1}>
            <Box flexDirection="row" justifyContent="space-between">
              <Text bold wrap="truncate-end">{e.name}</Text>
              <Text dimColor>{e.status}</Text>
            </Box>
            {e.cycles.length === 0 && <Text dimColor>escada de valor sem ciclos</Text>}
            {e.cycles.map(c => {
              const f = queueOfCycle(e, c.number, queueList)
              const state = cycleState(f)
              const mark = MARK[state]
              return (
                <Box flexDirection="row" justifyContent="space-between">
                  <Box flexGrow={1} flexShrink={1} minWidth={0}>
                    <Text color={mark.color} dimColor={state === 'sem fila'} wrap="truncate-end">{`${mark.symbol} ${c.label}`}</Text>
                  </Box>
                  <Box flexShrink={0} marginLeft={1}>
                    <Text color={mark.color} dimColor={state === 'sem fila'}>{cycleLine(f)}</Text>
                  </Box>
                </Box>
              )
            })}
          </Box>
        ))}
      </Box>,
    )

    const WIDTH = 6
    const queuesLevel = card(
      'Filas',
      openQueues.length === 1 ? '1 aberta' : `${openQueues.length} abertas`,
      <Box flexDirection="column" marginTop={1}>
        {queueList.length === 0 && <Text dimColor>nenhuma fila single-track</Text>}
        {queueList.length > 0 && (
          <Box flexDirection="row">
            <Box flexGrow={1} flexShrink={1} minWidth={0}><Text dimColor>fila</Text></Box>
            {COLUMNS.map(c => (
              <Box width={WIDTH} flexShrink={0} justifyContent="flex-end"><Text dimColor>{c.label}</Text></Box>
            ))}
          </Box>
        )}
        {queueList.map(f => (
          <Box flexDirection="row">
            <Box flexGrow={1} flexShrink={1} minWidth={0}>
              <Text bold={isOpen(f)} dimColor={!isOpen(f)} wrap="truncate-end">{f.name}</Text>
            </Box>
            {COLUMNS.map(c => (
              <Box width={WIDTH} flexShrink={0} justifyContent="flex-end">
                {f[c.field] === 0
                  ? <Text dimColor>·</Text>
                  : <Text color={c.color} dimColor={!isOpen(f)}>{String(f[c.field])}</Text>}
              </Box>
            ))}
          </Box>
        ))}
      </Box>,
    )

    const modeLevel = card(
      'Modo',
      m ? m.name : 'sem modo',
      <Box flexDirection="column" marginTop={1}>
        {m === null && <Text dimColor>Esta sessão não declarou modo.</Text>}
        {m !== null && exitText !== '' && <Text>fecha quando: {exitText}</Text>}
        {m !== null && m.budget !== '' && <Text dimColor>orçamento: {m.budget}</Text>}
        <Box flexDirection="row" marginTop={1}>
          <Text dimColor>build: </Text>
          {b === null && <Text dimColor>nenhum registrado</Text>}
          {b !== null && <Text color={COLOR[b.state]} bold={b.state === 'vermelho'}>{buildLine(b, nowMs)}</Text>}
        </Box>
        <Box flexDirection="row">
          {d.open + d.resolved === 0 && <Text dimColor>nenhum desvio registrado</Text>}
          {d.open + d.resolved > 0 && (
            <Text color={d.open > 0 ? 'yellow' : undefined} dimColor={d.open === 0}>
              {d.open === 1 ? '1 desvio aberto' : `${d.open} desvios abertos`}
            </Text>
          )}
          {d.resolved > 0 && <Text dimColor>{` · ${d.resolved} ${d.resolved === 1 ? 'resolvido' : 'resolvidos'}`}</Text>}
        </Box>
        {g !== null && (
          <Box flexDirection="column" marginTop={1}>
            <Text color="yellow" wrap="wrap">{g.phrase}</Text>
            <Text dimColor>
              {`${g.gate} ${age(g.when, nowMs)}` + (g.times > 1 ? ` · ${g.times}º bloqueio da sessão` : '')}
            </Text>
          </Box>
        )}
      </Box>,
    )

    const END_COLOR: Record<string, string> = { 'end-of-queue': 'green', 'fim-da-fila': 'green', interrompido: 'yellow' }
    const runLevel = card(
      'Run',
      r === null ? 'cepa-until' : `${r.queue} · ${runTime(r, nowMs)}`,
      <Box flexDirection="column" marginTop={1}>
        {r === null && <Text dimColor>nenhum run do cepa-until</Text>}
        {r !== null && r.phase === 'rodando' && r.item !== null && (
          <Box flexDirection="column">
            <Text bold color="cyan" wrap="truncate-end">{`▶ ${r.item.id} · ${r.item.title}`}</Text>
            <Text dimColor>
              {`${r.item.stage === 'build' ? 'build' : 'item'} há ${itemTime(r.item, nowMs)}`
                + (r.item.attempt > 1 ? ` · tentativa ${r.item.attempt}` : '')}
            </Text>
          </Box>
        )}
        {r !== null && r.phase === 'rodando' && r.item === null && <Text dimColor>entre itens</Text>}
        {r !== null && r.phase === 'cota' && (
          <Text color="yellow">
            {'parado pela cota' + (r.quota && timeOfDay(r.quota.resumes) !== '' ? ` · retoma às ${timeOfDay(r.quota.resumes)}` : '')}
          </Text>
        )}
        {r !== null && r.end !== null && (
          <Box flexDirection="column">
            <Text color={END_COLOR[r.end.reason] ?? 'red'} bold>
              {`${endLabel(r.end.reason)} ${age(r.end.when, nowMs)}`}
            </Text>
            {r.end.detail !== '' && <Text dimColor wrap="truncate-end">{r.end.detail}</Text>}
          </Box>
        )}
        {r !== null && (
          <Text dimColor>
            {(tally(r) === '' ? 'nada entregue ainda' : tally(r))
              + (r.end === null && timeOfDay(r.deadline) !== '' ? ` · prazo ${timeOfDay(r.deadline)}` : '')}
          </Text>
        )}
      </Box>,
    )

    if (intent === null) {
      return (
        <Box flexDirection="column">
          {epicsLevel}
          {queuesLevel}
          {card(
            'Sessão',
            'sem intenção',
            <Box flexDirection="column" marginTop={1}>
              <Text dimColor>Esta sessão ainda não tem intenção gravada.</Text>
              <Text dimColor>Grave com cepa-intent write.</Text>
            </Box>,
          )}
          {modeLevel}
          {runLevel}
        </Box>
      )
    }

    const session = await $.session.id()
    const fromOther = intent.sessionId !== '' && intent.sessionId !== session
    const total = intent.plan.length
    const fulfilled = intent.step > total
    const elapsed = age(intent.stepSince, await read($, now))

    return (
      <Box flexDirection="column">
        {epicsLevel}
        {queuesLevel}
        {card(
          'Sessão',
          fulfilled ? `${total}/${total} cumprido` : `passo ${intent.step}/${total}`,
          <Box flexDirection="column">
            {fromOther && (
              <Box marginTop={1}>
                <Text color="yellow">
                  Gravada em outra sessão ({intent.openedAt.slice(0, 10)}): continua ou abre nova?
                </Text>
              </Box>
            )}
            <Box flexDirection="column" marginTop={1}>
              <Text>{intent.purpose}</Text>
              {intent.byWhen !== '' && <Text dimColor>meta: {intent.byWhen}</Text>}
            </Box>
            <Box flexDirection="column" marginTop={1}>
              {intent.plan.map((name, i) => {
                const n = i + 1
                if (n < intent.step) return <Text dimColor>✓ {name}</Text>
                if (n === intent.step) {
                  return (
                    <Box flexDirection="row" justifyContent="space-between">
                      <Text bold color="cyan">▶ {name}</Text>
                      {elapsed !== '' && <Text dimColor>{elapsed}</Text>}
                    </Box>
                  )
                }
                return <Text>○ {name}</Text>
              })}
            </Box>
            {fulfilled && (
              <Box marginTop={1}>
                <Text color="green">Plano cumprido. Hora de /common:wrap-up.</Text>
              </Box>
            )}
          </Box>,
        )}
        {modeLevel}
        {runLevel}
      </Box>
    )
  })
}
