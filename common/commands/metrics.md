---
description: Relatório de telemetria do próprio harness — sessões por repo, taxa de builds vermelhos, bloqueios do gate-advance por motivo, distribuição de vereditos do proof gate, `proven` sobre-declarados barrados pelo guard, e o **atrito das pontas da sessão** (quantos turnos você gasta antes de conseguir disparar a rotina, e quantos gasta depois dela até encerrar). Lê o ledger em ~/.claude/cepa-telemetry/ alimentado automaticamente pelos hooks. Use para decidir com evidência onde o harness atrapalha em vez de ajudar.
argument-hint: [--days N | --month YYYY-MM] [--repo <nome>]
interaction: routine
---

# /common:metrics

## Purpose

O harness audita cards, builds e provas — este comando audita o harness. Os
hooks (`gate-advance`, `capture-build-result`, `session-registry`,
`proof-verdict-guard`, `session-log`) emitem eventos fail-silent para
`~/.claude/cepa-telemetry/events-YYYY-MM.jsonl`; o agregador transforma isso em
respostas: onde o gate bloqueia demais, qual repo queima mais builds, quantos
`proven` sobre-declarados o guard barrou.

Desde 03/08/2026 inclui a seção **Formato de relatório** — quantas respostas de
trabalho feito saíram do padrão `plain-report` e por qual motivo. É o número que
decide se o aviso do `report-style-lint` precisa virar bloqueio.

## Steps

1. Rode o agregador, repassando os argumentos do usuário verbatim:

   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-metrics" $ARGUMENTS
   ```

2. Mostre o relatório ao usuário **na íntegra** (ele já sai em pt-BR e
   formatado). Não resuma por conta própria — os números são o produto.

3. Se a seção "Leituras sugeridas" apontar algo acionável (ex.: repo que
   merece `.claude/no-build`, loop de verify lento), destaque a UMA ação de
   maior retorno e ofereça executá-la. Não execute sem confirmação.

4. Se não houver eventos ainda, explique que a telemetria começou a acumular
   nesta versão dos plugins e sugira rodar de novo após alguns dias de uso.

## Notes

- **Para onde foi o relógio de UMA sessão**, o agregador não serve — ele conta
  eventos, não mede tempo. Quem mede é o `cepa-clock`, que lê o transcript da
  sessão (e o de cada subagente) e reparte o relógio em espera ativa, build,
  bash normal e geração dos agentes:

  ```
  python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-clock"            # a última sessão deste repo
  python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-clock" --emit     # e grava no ledger
  ```

  Com `--emit`, a repartição entra aqui como a seção "Relógio medido". Rode-o
  depois de uma rotina longa que pareceu lenta — foi assim que se descobriu, em
  2026-08-26, que o gargalo era lead sondando disco (19% a 52% do relógio) e não
  build (3% a 17%).

- **Tokens** (desde 12/09/2026): no fim de cada sessão o `session-registry`
  dispara o `cepa-tokens` em segundo plano, que lê o transcript e grava um
  evento `token_usage` (contexto novo, cache lido e saída, por tipo de agente,
  mais o tamanho do que cada ferramenta devolveu). A seção "Tokens" responde
  onde o gasto está: agente, repo ou leitura de arquivo. Sessões anteriores à
  instalação entram com uma varredura única:

  ```
  python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-tokens" --todas --days 30 --emit
  ```

- Comandos e skills podem registrar eventos próprios (aparecem em "Eventos
  custom") via:
  `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_telemetry.py" emit <evento> chave=valor ...`
- O ledger não guarda payloads nem comandos completos — só categorias, status
  e rótulos curtos. Apagar `~/.claude/cepa-telemetry/` zera o histórico sem
  quebrar nada.
