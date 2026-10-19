import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { Fila } from '../types'
import { aberta, COLUNAS, contaFila } from './filas'
import { idade, parseIntent } from './intent'
import { COR, linhaBuild, parseBuild } from './build'
import { contaDesvios, leSaidas, parseModo } from './modo'
import { leBloqueio, leGuarda } from './gate'
import type { Barrada } from './gate'
import { avisoDe, contagem, hora, parseRun, rotuloDoFim, tempoDoItem, tempoDoRun } from './until'
import type { Run } from './until'

// Painel de orientação em níveis, do mais alto ao mais baixo:
// 1. filas do repo e um resumo dos itens; 2. intenção, plano e passo da sessão;
// 3. modo da sessão, a condição de saída dele, o estado do build e os desvios registrados;
// 4. o run mais recente do cepa-until: item atual, tempo, contagem e como acabou.
// O cartão Modo mostra também o último gate que barrou uma ação, em uma frase leiga.
const PANE = 'compass'
const ABRE = { id: PANE, title: 'Compass', columns: 48 }
const ARQUIVO = '.claude/session-intent'
const MODO = '.claude/session-mode'
const DESVIOS = '.claude/desvios.md'
const BUILD = '.claude/last-build.json'
const texto = atom({ plugin: 'compass', key: 'texto' } as const, null)
const agora = atom({ plugin: 'compass', key: 'agora' } as const, 0)
const filas = atom({ plugin: 'compass', key: 'filas' } as const, [])
const modo = atom({ plugin: 'compass', key: 'modo' } as const, null)
const desvios = atom({ plugin: 'compass', key: 'desvios' } as const, null)
const build = atom({ plugin: 'compass', key: 'build' } as const, null)
const saidas = atom({ plugin: 'compass', key: 'saidas' } as const, {})
const until = atom({ plugin: 'compass', key: 'until' } as const, null)
const gate = atom({ plugin: 'compass', key: 'gate' } as const, null)
const SOM_DO_FIM = 'sons/fim.wav'

let passoAnterior = 0
let desviosAnteriores = -1
let runAnterior: Run | null = null
// Caminho do `.jsonl` mais recente, achado a cada 30 s junto com as filas.
let registroDoRun: { caminho: string; fila: string; id: string } | null = null

const leSe = async ($: EngineInterface, caminho: string) =>
  (await $.fs.exists(caminho)) ? await $.fs.read(caminho) : null

async function releia($: EngineInterface) {
  const novo = await leSe($, ARQUIVO)
  const ms = await $.clock.now()
  await update($, agora, () => ms)
  await releiaModo($)
  await releiaRun($)
  if (novo === (await read($, texto))) return
  await update($, texto, () => novo)
  const intent = novo === null ? null : parseIntent(novo)
  if (intent && passoAnterior > 0 && intent.passo !== passoAnterior) {
    const nome = intent.plano[intent.passo - 1]
    $.ui.toast(nome ? `Passo ${intent.passo}: ${nome}` : 'Plano cumprido')
  }
  passoAnterior = intent?.passo ?? 0
}

async function releiaModo($: EngineInterface) {
  const textoModo = await leSe($, MODO)
  await update($, modo, () => textoModo)
  const textoDesvios = await leSe($, DESVIOS)
  await update($, desvios, () => textoDesvios)
  const textoBuild = await leSe($, BUILD)
  await update($, build, () => textoBuild)
  const d = contaDesvios(textoDesvios ?? '')
  const total = d.abertos + d.resolvidos
  if (desviosAnteriores >= 0 && total > desviosAnteriores) $.ui.toast(`Desvio registrado: ${d.ultimo}`)
  desviosAnteriores = total
}

// O registro do run é relido a cada 5 s: o item atual e o tempo mudam sem novo turno.
async function releiaRun($: EngineInterface) {
  const reg = registroDoRun
  const textoRun = reg === null ? null : await leSe($, reg.caminho)
  const r = textoRun === null || reg === null ? null : parseRun(textoRun, reg.fila, reg.id)
  await update($, until, () => (reg === null || textoRun === null ? null : { fila: reg.fila, id: reg.id, texto: textoRun }))
  if (r !== null) {
    const aviso = avisoDe(runAnterior, r)
    if (aviso !== null) {
      $.ui.toast(aviso)
      void $.audio.play({ asset: SOM_DO_FIM }).catch(() => {
        // sem player (Linux, Windows) ou sem o arquivo: o toast já avisou
      })
    }
  }
  runAnterior = r
}

// Só observa o resultado da chamada: o gate que barrou já respondeu, e a resposta
// volta igual. Nada aqui reescreve a chamada nem o motivo.
async function observaGate($: EngineInterface, comando: string, r: { isError?: true; text?: string; result?: unknown }) {
  let b = null
  if (r.isError === true && typeof r.text === 'string') b = leBloqueio(r.text)
  else if (comando !== '' && r.isError === undefined) {
    const saida = r.result as { stdout?: unknown } | null | undefined
    const stdout = typeof saida?.stdout === 'string' ? saida.stdout : typeof r.text === 'string' ? r.text : ''
    b = leGuarda(comando, stdout)
  }
  if (b === null) return
  const quando = new Date(await $.clock.now()).toISOString()
  const anterior = await read($, gate)
  const nova: Barrada = { ...b, quando, vezes: (anterior?.vezes ?? 0) + 1 }
  await update($, gate, () => nova)
  $.ui.toast(b.frase, { timeoutMs: 8000 })
}

// A tabela dos modos não muda durante a sessão; lida uma vez.
async function releiaSaidas($: EngineInterface) {
  try {
    const r = await $.process.run(['cepa-modos', '--json'])
    if (r.exitCode === 0) await update($, saidas, () => leSaidas(r.stdout))
  } catch {
    // cepa-modos fora do PATH: o cartão mostra o modo sem a condição de saída
  }
}

// As filas moram no checkout principal (é onde o `cepa-plan` grava), não na worktree.
async function releiaFilas($: EngineInterface) {
  const git = await $.process.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'])
  if (git.exitCode !== 0) return
  const dir = `${git.stdout.trim().replace(/\/\.git$/, '')}/.claude/programs`
  if (!(await $.fs.exists(dir))) return
  const lidas: Fila[] = []
  let recente: { caminho: string; fila: string; id: string } | null = null
  for (const entrada of await $.fs.list(dir)) {
    if (entrada.kind !== 'dir') continue
    const plano = `${dir}/${entrada.name}/plan.yaml`
    if (await $.fs.exists(plano)) {
      const fila = contaFila(entrada.name, await $.fs.read(plano))
      if (fila) lidas.push(fila)
    }
    // O run mais recente de todas as filas: o nome do `.jsonl` é a data e hora da largada.
    const runs = `${dir}/${entrada.name}/until`
    if (!(await $.fs.exists(runs))) continue
    for (const arq of await $.fs.list(runs)) {
      if (arq.kind !== 'file' || !arq.name.endsWith('.jsonl')) continue
      const id = arq.name.slice(0, -'.jsonl'.length)
      if (recente === null || id > recente.id) recente = { caminho: `${runs}/${arq.name}`, fila: entrada.name, id }
    }
  }
  registroDoRun = recente
  const abertos = (f: Fila) => f.pendentes + f.emAndamento + f.bloqueados
  lidas.sort((a, b) => abertos(b) - abertos(a) || a.nome.localeCompare(b.nome))
  await update($, filas, () => lidas)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'compass',
      description: 'Abre o painel de orientação: filas, intenção, modo, build, desvios e o run do cepa-until',
    })
    await releiaSaidas($)
    await releiaFilas($)
    await releia($)
    $.clock.every(5000, () => releia($))
    $.clock.every(30000, () => releiaFilas($))
    void $.ui.open(ABRE)

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    await releiaFilas($)
    await releia($)

    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    const r = await next(e)
    try {
      await observaGate($, e.tool === 'Bash' ? e.command : '', r)
    } catch {
      // o aviso nunca atrapalha a chamada: o resultado volta igual
    }

    return r
  })

  on('command.run', { command: 'compass' }, async $ => {
    await $.ui.open(ABRE)

    return { text: 'Painel de orientação aberto.' }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const bruto = await read($, texto)
    const intent = bruto === null ? null : parseIntent(bruto)
    const lista = await read($, filas)
    const abertas = lista.filter(aberta)
    const textoModo = await read($, modo)
    const m = textoModo === null ? null : parseModo(textoModo)
    const saida = m ? (await read($, saidas))[m.nome] ?? '' : ''
    const textoDesvios = await read($, desvios)
    const d = contaDesvios(textoDesvios ?? '')
    const textoBuild = await read($, build)
    const b = textoBuild === null ? null : parseBuild(textoBuild)
    const momento = await read($, agora)
    const bruto4 = await read($, until)
    const r = bruto4 === null ? null : parseRun(bruto4.texto, bruto4.fila, bruto4.id)
    const g = await read($, gate)

    const cartao = (titulo: string, direita: string, corpo: RenderChildren) => (
      <Box flexDirection="column" borderStyle="round" borderDimColor paddingX={1}>
        <Box flexDirection="row" justifyContent="space-between">
          <Text bold>{titulo}</Text>
          <Text dimColor>{direita}</Text>
        </Box>
        {corpo}
      </Box>
    )

    const LARGURA = 6
    const nivelFilas = cartao(
      'Filas',
      abertas.length === 1 ? '1 aberta' : `${abertas.length} abertas`,
      <Box flexDirection="column" marginTop={1}>
        {lista.length === 0 && <Text dimColor>nenhuma fila single-track</Text>}
        {lista.length > 0 && (
          <Box flexDirection="row">
            <Box flexGrow={1} flexShrink={1} minWidth={0}><Text dimColor>fila</Text></Box>
            {COLUNAS.map(c => (
              <Box width={LARGURA} flexShrink={0} justifyContent="flex-end"><Text dimColor>{c.rotulo}</Text></Box>
            ))}
          </Box>
        )}
        {lista.map(f => (
          <Box flexDirection="row">
            <Box flexGrow={1} flexShrink={1} minWidth={0}>
              <Text bold={aberta(f)} dimColor={!aberta(f)} wrap="truncate-end">{f.nome}</Text>
            </Box>
            {COLUNAS.map(c => (
              <Box width={LARGURA} flexShrink={0} justifyContent="flex-end">
                {f[c.campo] === 0
                  ? <Text dimColor>·</Text>
                  : <Text color={c.cor} dimColor={!aberta(f)}>{String(f[c.campo])}</Text>}
              </Box>
            ))}
          </Box>
        ))}
      </Box>,
    )

    const nivelModo = cartao(
      'Modo',
      m ? m.nome : 'sem modo',
      <Box flexDirection="column" marginTop={1}>
        {m === null && <Text dimColor>Esta sessão não declarou modo.</Text>}
        {m !== null && saida !== '' && <Text>fecha quando: {saida}</Text>}
        {m !== null && m.orcamento !== '' && <Text dimColor>orçamento: {m.orcamento}</Text>}
        <Box flexDirection="row" marginTop={1}>
          <Text dimColor>build: </Text>
          {b === null && <Text dimColor>nenhum registrado</Text>}
          {b !== null && <Text color={COR[b.estado]} bold={b.estado === 'vermelho'}>{linhaBuild(b, momento)}</Text>}
        </Box>
        <Box flexDirection="row">
          {d.abertos + d.resolvidos === 0 && <Text dimColor>nenhum desvio registrado</Text>}
          {d.abertos + d.resolvidos > 0 && (
            <Text color={d.abertos > 0 ? 'yellow' : undefined} dimColor={d.abertos === 0}>
              {d.abertos === 1 ? '1 desvio aberto' : `${d.abertos} desvios abertos`}
            </Text>
          )}
          {d.resolvidos > 0 && <Text dimColor>{` · ${d.resolvidos} ${d.resolvidos === 1 ? 'resolvido' : 'resolvidos'}`}</Text>}
        </Box>
        {g !== null && (
          <Box flexDirection="column" marginTop={1}>
            <Text color="yellow" wrap="wrap">{g.frase}</Text>
            <Text dimColor>
              {`${g.gate} ${idade(g.quando, momento)}` + (g.vezes > 1 ? ` · ${g.vezes}º bloqueio da sessão` : '')}
            </Text>
          </Box>
        )}
      </Box>,
    )

    const COR_DO_FIM: Record<string, string> = { 'fim-da-fila': 'green', interrompido: 'yellow' }
    const nivelRun = cartao(
      'Run',
      r === null ? 'cepa-until' : `${r.fila} · ${tempoDoRun(r, momento)}`,
      <Box flexDirection="column" marginTop={1}>
        {r === null && <Text dimColor>nenhum run do cepa-until</Text>}
        {r !== null && r.fase === 'rodando' && r.item !== null && (
          <Box flexDirection="column">
            <Text bold color="cyan" wrap="truncate-end">{`▶ ${r.item.id} · ${r.item.titulo}`}</Text>
            <Text dimColor>
              {`${r.item.etapa === 'build' ? 'build' : 'item'} há ${tempoDoItem(r.item, momento)}`
                + (r.item.tentativa > 1 ? ` · tentativa ${r.item.tentativa}` : '')}
            </Text>
          </Box>
        )}
        {r !== null && r.fase === 'rodando' && r.item === null && <Text dimColor>entre itens</Text>}
        {r !== null && r.fase === 'cota' && (
          <Text color="yellow">
            {'parado pela cota' + (r.cota && hora(r.cota.retoma) !== '' ? ` · retoma às ${hora(r.cota.retoma)}` : '')}
          </Text>
        )}
        {r !== null && r.fim !== null && (
          <Box flexDirection="column">
            <Text color={COR_DO_FIM[r.fim.motivo] ?? 'red'} bold>
              {`${rotuloDoFim(r.fim.motivo)} ${idade(r.fim.quando, momento)}`}
            </Text>
            {r.fim.detalhe !== '' && <Text dimColor wrap="truncate-end">{r.fim.detalhe}</Text>}
          </Box>
        )}
        {r !== null && (
          <Text dimColor>
            {(contagem(r) === '' ? 'nada entregue ainda' : contagem(r))
              + (r.fim === null && hora(r.prazo) !== '' ? ` · prazo ${hora(r.prazo)}` : '')}
          </Text>
        )}
      </Box>,
    )

    if (intent === null) {
      return (
        <Box flexDirection="column">
          {nivelFilas}
          {cartao(
            'Sessão',
            'sem intenção',
            <Box flexDirection="column" marginTop={1}>
              <Text dimColor>Esta sessão ainda não tem intenção gravada.</Text>
              <Text dimColor>Grave com cepa-intencao gravar.</Text>
            </Box>,
          )}
          {nivelModo}
          {nivelRun}
        </Box>
      )
    }

    const sessao = await $.session.id()
    const deOutra = intent.sessionId !== '' && intent.sessionId !== sessao
    const total = intent.plano.length
    const cumprido = intent.passo > total
    const parado = idade(intent.passoDesde, await read($, agora))

    return (
      <Box flexDirection="column">
        {nivelFilas}
        {cartao(
          'Sessão',
          cumprido ? `${total}/${total} cumprido` : `passo ${intent.passo}/${total}`,
          <Box flexDirection="column">
            {deOutra && (
              <Box marginTop={1}>
                <Text color="yellow">
                  Gravada em outra sessão ({intent.abertoEm.slice(0, 10)}): continua ou abre nova?
                </Text>
              </Box>
            )}
            <Box flexDirection="column" marginTop={1}>
              <Text>{intent.proposito}</Text>
              {intent.paraQuando !== '' && <Text dimColor>meta: {intent.paraQuando}</Text>}
            </Box>
            <Box flexDirection="column" marginTop={1}>
              {intent.plano.map((nome, i) => {
                const n = i + 1
                if (n < intent.passo) return <Text dimColor>✓ {nome}</Text>
                if (n === intent.passo) {
                  return (
                    <Box flexDirection="row" justifyContent="space-between">
                      <Text bold color="cyan">▶ {nome}</Text>
                      {parado !== '' && <Text dimColor>{parado}</Text>}
                    </Box>
                  )
                }
                return <Text>○ {nome}</Text>
              })}
            </Box>
            {cumprido && (
              <Box marginTop={1}>
                <Text color="green">Plano cumprido. Hora de /common:wrap-up.</Text>
              </Box>
            )}
          </Box>,
        )}
        {nivelModo}
        {nivelRun}
      </Box>
    )
  })
}
