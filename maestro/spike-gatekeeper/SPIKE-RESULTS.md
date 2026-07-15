# Spike do porteiro — resultados (2026-07-15)

**Veredito: VIÁVEL.** O elo nunca spikado do design v1 (Componente 3 — processo
separado servindo `--permission-prompt-tool` via MCP para filhas `claude -p`)
funciona ponta a ponta. CLI testada: Claude Code 2.1.210.

## O que foi provado (evidência em scratchpad/spike-run2)

| Cenário | Resultado | Evidência |
|---|---|---|
| allow por regra mecânica | ✓ | `spike-allowed-proof.txt` criado; log `rule: bash-base` |
| deny por regra mecânica | ✓ | `FORBIDDEN-file.txt` NÃO criado; filha respondeu NEGADO |
| zona cinza → escalação (3a) | ✓ | `escalations/e787f999.yaml` gravado; filha terminou o turno com `MAESTRO-EXIT:ESCALATED:e787f999` exato, sem loop de espera |
| 2 filhas concorrentes no mesmo servidor | ✓ | ambas servidas pelo mesmo processo/porta |

Latência do porteiro: sub-milissegundo por decisão (0.03–0.53 ms server-side);
irrelevante no caminho crítico.

## Decisões que o spike fecha (credencial/transporte/latência)

- **Transporte: HTTP streamable em loopback (127.0.0.1)**, servidor único
  compartilhado por N filhas. Implementável com stdlib Python (sem SDK MCP):
  basta responder `initialize`, `notifications/initialized` (202), `tools/list`
  e `tools/call`. stdio foi descartado: cada filha subiria seu próprio porteiro,
  matando o modelo "1 porteiro por onda" e a fila única de escalação.
- **Credencial:** nenhuma no spike. Para o v1, loopback já limita a máquina
  local; se quiser defesa extra, a mcp-config gerada suporta `headers` →
  bearer token por onda é trivial. Não é bloqueante.
- **Resposta:** JSON serializado como texto em `content[0].text`:
  `{"behavior":"allow","updatedInput":{...}}` ou `{"behavior":"deny","message":"..."}`.
  Confirmado aceito pela CLI.

## Achados que ALTERAM o design v1

1. **O flag `--permission-prompt-tool` está oculto no `--help` da 2.1.210, mas
   funciona.** Dívida nomeada: testar o flag a cada upgrade da CLI (mesmo
   tratamento da dívida do wrapper herdr).
2. **Sem regra que force a rota, o porteiro nunca é consultado.** No modo
   default do headless, comandos "seguros" (touch, mkdir…) são pré-aprovados
   pelo próprio Claude Code e a tool não é chamada (run1: 0 chamadas). As
   settings geradas no fork (camada 1) precisam, além do deny-by-default +
   allows da superfície, de **regras `ask` cobrindo a zona que deve chegar ao
   porteiro** (ex.: `"ask": ["Bash"]` menos os allows). Sem isso a camada 3
   é decorativa.
3. **O payload NÃO carrega identidade da filha:** só
   `{tool_name, input, tool_use_id}`. Para o porteiro saber QUAL slice pede
   (necessário para regras por-superfície e para a fila de escalação), a
   identidade tem de vir do lado do transporte — a mcp-config gerada por slice
   aponta para URL distinta (`http://127.0.0.1:P/mcp?slice=S1`) ou porta
   distinta. Recomendação: query param, 1 servidor só.
4. **A mensagem do deny chega ao modelo e ele a obedece.** O protocolo 3a
   ("termine o turno com MAESTRO-EXIT:ESCALATED:<id>") funcionou embutido na
   própria mensagem de deny, sem nada no prompt da filha. O contrato da fila
   pode viver inteiro no porteiro.

## Arquivos

- `gatekeeper.py` — servidor MCP mínimo (stdlib), regras mecânicas + zona
  cinza escala sempre (D5), `--shadow` já implementado (D3), log JSONL com
  payload integral, pidfile.
- `run-spike.sh` — bateria dos 4 cenários; uso: `run-spike.sh <dir-de-trabalho>`.

## Próximo passo da ordem de construção

Passo 2: `/maestro:program-plan` + intake gate (DoR invocável em `common/`) +
schema `plan.yaml` v1.
