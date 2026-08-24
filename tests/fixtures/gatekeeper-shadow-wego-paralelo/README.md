# Lote de sombra do porteiro — onda 1 do programa WEGO-paralelo (2026-08-24)

Cópia fiel do estado que `maestro-gatekeeper` produziu na PRIMEIRA vez que rodou
contra trabalho real: 5 slices em paralelo no repo wego-acesso-backend, porteiro
em `--shadow` (aprova tudo, registra o que TERIA decidido), como o design manda
para o 1º programa.

- `decisions.jsonl` — 74 decisões, uma por linha (31 liberações + 43
  escalações). Sem quebra de linha no fim, então `wc -l` diz 73. Campos: `comando`, `regra`,
  `decisao` (o veredito real do motor), `effective` (o que valeu — em sombra é
  sempre `allow`), `slice`, `escalation_id`, `latency_ms`.
- `escalations/` — 43 YAMLs, um por escalação. Todos `estado: pending`: ninguém
  respondeu e o TTL de 1h venceu.

Serve de fixture para a calibração descrita em `BACKLOG.md` ("Calibrar as regras
do porteiro do Maestro com o 1º lote de sombra"). O critério de pronto de lá é
reprocessar ESTE arquivo com as regras novas e comparar os vereditos.

Origem: `<wego-acesso-backend>/.claude/programs/WEGO-paralelo/gatekeeper/`.
Varrido por segredo antes de entrar aqui — os únicos casamentos de "token" são o
nome de uma classe de teste (`TravaTokenInjecaoTest`).
