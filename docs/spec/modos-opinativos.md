# Especificação: modos opinativos (menu de ações na entrada de cada modo)

**Status:** draft
**Aberta em:** 2026-11-10            **Fechada em:** -
**Fontes lidas:** common/hooks/_modes.py, common/hooks/session-mode.py, common/bin/cepa, common/commands/metrics.md, docs/modos-de-trabalho.md, .claude/handoffs/session-mkt-mode.md, .claude/deviations.md, ~/.claude/cepa-telemetry/events-2026-*.jsonl, ~/.zsh_history (só a contagem de `cepa --mode`)

## Como chegamos aqui
Em 2026-11-10 o dono disse: "quero que o modo seja mais opinativo, que cada modo carregue um repertório de ações comuns àquele modo de atuação, a um comando de distância, para conduzir quem sabe que algo tem que ser feito mas não sabe ao certo o quê." A frase veio depois de ele perguntar, na sessão que testou a topologia marketing: "o modo é só isso? Uma entrada numa tabela mais algumas restrições de escrita?"

## Problema
Hoje o modo diz o que a sessão não pode fazer (onde escrever, quando pode fechar) e não diz o que ela pode fazer. Quem abre `cepa --mode discovery` sem saber qual comando rodar recebe a condição de saída do modo e mais nada. O repertório de comandos de cada modo existe, mas só na cabeça de quem já o decorou.

## Escopo
### Entra
- Um campo novo por modo em `common/hooks/_modes.py` (a tabela única dos modos), com 3 a 5 ações. Cada ação tem uma frase leiga e o comando que a dispara.
- A exibição do menu quando a sessão abre sem rotina e sem pedido.
- Menu preenchido só nos modos mais usados. Nos outros o campo existe com lista vazia.
- A reconciliação da seção "Modo não é Rotina" de `docs/modos-de-trabalho.md`.

### Não entra
- A jornada guiada por estado do disco (o modo ler o disco e sugerir o passo seguinte). Exige um leitor de estado por modo e hoje só `exploration` tem um.
- Comandos novos. O menu é mapa para comandos que já existem. Onde não houver comando, a lacuna fica à vista.
- O modo `marketing`. Ele ainda não está na tabela e entra depois desta especificação, para não escrever a entrada dele duas vezes.

## Estado e migração
<a preencher depois da rodada 1>

## Critérios de sucesso
<a preencher: nenhum critério escrito ainda>

## Perguntas em aberto
- [ ] P1. Quais modos saem com menu preenchido nesta especificação?
- [ ] P2. Onde e em que momento o menu aparece?
- [ ] P3. Escolher uma ação do menu grava a rotina da sessão (campo `routine:` de `.claude/session-mode`)? E como fica a frase "Modo não é Rotina" do documento?

## Decided without asking
- A contagem de uso dos modos veio do histórico do shell (`~/.zsh_history`, ocorrências de `cepa --mode <nome>`), e não do `/common:metrics` — o evento `session_start` da telemetria não grava o modo (conferido em `events-2026-11.jsonl`), então o `/common:metrics` não tem como responder. Contagem em 2026-11-10, somando nome antigo e novo: construction 74 (37+37), discovery 15 (11+4), exploration 13 (7+6), documentation 4, design 0, refactor 0, reflection 0. Total 106. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- A telemetria não grava o modo da sessão. "Modos mais usados" hoje só se mede pelo histórico do shell de uma máquina.
