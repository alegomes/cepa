# Desvios capturados

Achados que apareceram fora do modo da sessão em que nasceram. Registrados em
vez de trabalhados, para não virarem o próprio vazamento que os modos existem
para impedir (docs/modos-de-trabalho.md).

- [ ] 2026-08-18 · modo: construcao · `/board-flow:triage` proíbe agrupar
  exatamente a decisão mais repetitiva da triagem: *"Nothing destructive without
  a per-card yes. OBSOLETE → Won't Do is never batch-applied. Each cancellation
  is confirmed individually"* (`board-flow/commands/triage.md:38`). Isso
  contradiz o passo 6 do mesmo arquivo, que manda juntar TODAS as decisões numa
  rodada só aplicando `default-yes` (linha 133). Numa fila com K cards obsoletos
  são K interrupções, mais o grill, mais o "Apply?" do passo 7. Evidência: a
  sessão session/triage_2025 começou 20:25 para triar a coluna To Do e montar um
  plano de execução noturna e às 21:45 ainda não tinha chegado ao plano.
