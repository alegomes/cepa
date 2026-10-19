import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { Fila } from '../types'
import { aberta, COLUNAS, contaFila } from './filas'
import { idade, parseIntent } from './intent'
import { contaDesvios, leSaidas, parseModo } from './modo'

// Painel de orientação em níveis, do mais alto ao mais baixo:
// 1. filas do repo e um resumo dos itens; 2. intenção, plano e passo da sessão;
// 3. modo da sessão, a condição de saída dele e os desvios registrados.
const PANE = 'compass'
const ABRE = { id: PANE, title: 'Compass', columns: 48 }
const ARQUIVO = '.claude/session-intent'
const MODO = '.claude/session-mode'
const DESVIOS = '.claude/desvios.md'
const texto = atom({ plugin: 'compass', key: 'texto' } as const, null)
const agora = atom({ plugin: 'compass', key: 'agora' } as const, 0)
const filas = atom({ plugin: 'compass', key: 'filas' } as const, [])
const modo = atom({ plugin: 'compass', key: 'modo' } as const, null)
const desvios = atom({ plugin: 'compass', key: 'desvios' } as const, null)
const saidas = atom({ plugin: 'compass', key: 'saidas' } as const, {})

let passoAnterior = 0
let desviosAnteriores = -1

const leSe = async ($: EngineInterface, caminho: string) =>
  (await $.fs.exists(caminho)) ? await $.fs.read(caminho) : null

async function releia($: EngineInterface) {
  const novo = await leSe($, ARQUIVO)
  const ms = await $.clock.now()
  await update($, agora, () => ms)
  await releiaModo($)
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
  const d = contaDesvios(textoDesvios ?? '')
  const total = d.abertos + d.resolvidos
  if (desviosAnteriores >= 0 && total > desviosAnteriores) $.ui.toast(`Desvio registrado: ${d.ultimo}`)
  desviosAnteriores = total
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
  for (const entrada of await $.fs.list(dir)) {
    const plano = `${dir}/${entrada.name}/plan.yaml`
    if (entrada.kind !== 'dir' || !(await $.fs.exists(plano))) continue
    const fila = contaFila(entrada.name, await $.fs.read(plano))
    if (fila) lidas.push(fila)
  }
  const abertos = (f: Fila) => f.pendentes + f.emAndamento + f.bloqueados
  lidas.sort((a, b) => abertos(b) - abertos(a) || a.nome.localeCompare(b.nome))
  await update($, filas, () => lidas)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'compass',
      description: 'Abre o painel de orientação: filas, intenção, modo e desvios da sessão',
    })
    await releiaSaidas($)
    await releia($)
    await releiaFilas($)
    $.clock.every(5000, () => releia($))
    $.clock.every(30000, () => releiaFilas($))
    void $.ui.open(ABRE)

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    await releia($)
    await releiaFilas($)

    return next(e)
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
        <Box flexDirection="row" marginTop={m === null ? 0 : 1}>
          {d.abertos + d.resolvidos === 0 && <Text dimColor>nenhum desvio registrado</Text>}
          {d.abertos + d.resolvidos > 0 && (
            <Text color={d.abertos > 0 ? 'yellow' : undefined} dimColor={d.abertos === 0}>
              {d.abertos === 1 ? '1 desvio aberto' : `${d.abertos} desvios abertos`}
            </Text>
          )}
          {d.resolvidos > 0 && <Text dimColor>{` · ${d.resolvidos} ${d.resolvidos === 1 ? 'resolvido' : 'resolvidos'}`}</Text>}
        </Box>
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
      </Box>
    )
  })
}
