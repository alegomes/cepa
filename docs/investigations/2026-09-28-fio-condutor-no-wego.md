# Fio condutor contra o Jira vivo do WEGO (2026-09-28)

Item da fila `cepa`: `validar-fio-condutor-em-board-real`. Re-roda as duas
checagens que falharam em 2026-09-25 (ver o `evidence` do item), agora com
`reconcile-nao-rebaixa-done` (8f84bb2) e `triagem-parcial-preserva-ordem`
(15da11b) na main.

Tudo aqui é leitura: nenhum card do Jira foi tocado e o
`wego-assinatura-backend/.claude/programs/WEGO/plan.yaml` tem o mesmo md5
antes e depois (`861987bcd0abba27e516e1867e77cb98`).

## 1. Reconcile contra o quadro vivo não rebaixa `done`

Status dos 25 ids da fila WEGO lidos pelo `atlassian-expert` via `twg`
(`2026-09-28-fio-condutor-wego/quadro-vivo.json`). Os três cards do incidente
seguem divergindo do mesmo jeito que em 09-25: fila `done`, quadro
WEGO-1550 In Review, WEGO-1982 In Review, WEGO-1973 In Progress.

```
python3 common/bin/cepa-plan reconcile WEGO --board quadro-vivo.json \
    --repo ../wego/wego-assinatura-backend --json      # sem --apply
```

- WEGO-1550 e WEGO-1982: `in_sync` (In Review conta como fechado do lado da fila).
- WEGO-1973: aviso "não rebaixei (regra R3)", nenhuma divergência gravável.
- Divergências reais: só WEGO-1412 (`pending` → `done`, fechou no quadro).
- Ruído: os 12 descartados aparecem em `divergences` com `de: dropped`,
  `para: dropped`, uma divergência que não muda nada.

## 2. Triagem parcial preserva a ordem da fila

Repasse da triagem de 09-25 (5 cards de 157, teto) aplicado sobre a fila de 25
itens, sem gravar:

- sem `--on-missing`: exit 4, recusa sumir com os 25 itens e nomeia todos
  (`write-sem-on-missing.txt`);
- com `--on-missing keep`: os 25 itens saem na mesma ordem e idênticos campo a
  campo; os 3 `ready` (WEGO-1438, 1439, 1440) entram no fim; os 2
  `needs-refinement` ficam fora com aviso (`write-keep-dry-run.yaml`).

Conta: `new[:25] == old` verdadeiro; itens antigos com qualquer campo diferente = 0.

## O que isto não cobre

Uma triagem nova do `/board-flow:triage` classificando cards ao vivo e o dono
revisando a fila resultante. A triagem transiciona cards (In Review,
Descartados) e pede confirmação, então não roda num lote desatendido.
