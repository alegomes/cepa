import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register, RenderChildren } from 'claude-code'

import type { Fila } from '../types'
import { aberta, COLUNAS, contaFila } from './filas'
import { idade, parseIntent } from './intent'

// Painel de orientação em níveis, do mais alto ao mais baixo:
// 1. filas do repo e um resumo dos itens; 2. intenção, plano e passo da sessão.
const PANE = 'compass'
const ABRE = { id: PANE, title: 'Compass', columns: 48 }
const ARQUIVO = '.claude/session-intent'
const texto = atom({ plugin: 'compass', key: 'texto' } as const, null)
const agora = atom({ plugin: 'compass', key: 'agora' } as const, 0)
const filas = atom({ plugin: 'compass', key: 'filas' } as const, [])

let passoAnterior = 0

async function releia($: EngineInterface) {
  const novo = (await $.fs.exists(ARQUIVO)) ? await $.fs.read(ARQUIVO) : null
  const ms = await $.clock.now()
  await update($, agora, () => ms)
  if (novo === (await read($, texto))) return
  await update($, texto, () => novo)
  const intent = novo === null ? null : parseIntent(novo)
  if (intent && passoAnterior > 0 && intent.passo !== passoAnterior) {
    const nome = intent.plano[intent.passo - 1]
    $.ui.toast(nome ? `Passo ${intent.passo}: ${nome}` : 'Plano cumprido')
  }
  passoAnterior = intent?.passo ?? 0
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
      description: 'Abre o painel de orientação: filas e intenção da sessão',
    })
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
      </Box>
    )
  })
}
