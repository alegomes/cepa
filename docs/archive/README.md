# Arquivo

Registros de decisões já tomadas. Explicam por que algo foi feito do jeito que foi, mas não
ensinam a usar nada. O que eles decidiram já está no código e nos guias de `docs/`.

| Documento | Data | O que registra |
|---|---|---|
| [estrategia-drain-plan-velocidade.md](estrategia-drain-plan-velocidade.md) | 2026-08-26 | Onde ia o tempo dos runs do `/common:drain-plan` (espera ativa dos leads, não compilação) e por que a correção foi nas specs dos agentes mais o hook `no-busy-wait`. |
| [estrategia-twg-vs-mcp.md](estrategia-twg-vs-mcp.md) | 2026-08-26 | A avaliação de trocar o MCP da Atlassian pela CLI `twg`, e os 4 gates de Jira consertados para cobrir a CLI. A troca em si ficou adiada. |
| [harness-review-2026-08.md](harness-review-2026-08.md) | 2026-08-17 | Revisão do harness inteiro. Os itens urgentes viraram o `loop-budget`, o `gen-locks` com o detector de divergência entre cópias, e o `_pluginver`. |

Os relatórios dos dois pilotos de competição de designs continuam em `docs/internals/`,
porque são material de consulta do item S1 da fila `lotes-sweep-verify`, ainda pendente.
