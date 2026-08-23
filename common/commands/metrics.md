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

- Comandos e skills podem registrar eventos próprios (aparecem em "Eventos
  custom") via:
  `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_telemetry.py" emit <evento> chave=valor ...`
- O ledger não guarda payloads nem comandos completos — só categorias, status
  e rótulos curtos. Apagar `~/.claude/cepa-telemetry/` zera o histórico sem
  quebrar nada.
