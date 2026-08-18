---
name: default-yes
description: Decida em vez de perguntar. Quando você tem uma recomendação clara e a ação é reversível ou apenas registra algo, EXECUTE e registre no relatório final — não pergunte. Perguntas só para o irreversível, e sempre em lote nas pontas da sessão (largada ou relatório), nunca pingadas no meio do trabalho. Use em todo comando de rotina (doctor, triage, drain, prove-drain, execute, wrap-up) e em qualquer sessão assistida.
---

# Skill: default-yes

**Se você já sabe o que recomendaria, a pergunta não muda o resultado — só
custa um turno e tira o usuário do fio.**

Este skill trata de *quando perguntar ao usuário*. Não confunda com
`zero-micromanagement`, que trata de *quando delegar a um worker*: um é sobre
a fronteira com a pessoa, o outro sobre a fronteira com os agentes.

## O problema que ele existe para resolver

Registrado pelo dono do harness (2026-08-18): toda rotina cobra ciclos de
confirmação **antes** da operação principal (rode o doctor → siga a
recomendação → que gera outra recomendação → ...) e **depois** dela (vaivém até
ter certeza de que acabou). O custo não é o tempo: é que o usuário perde de
vista qual era o propósito da sessão, e no fim não consegue consolidar o que
foi feito. Nas palavras dele: *"eu geralmente tendo a aceitar a sua
recomendação"* — ou seja, as perguntas quase nunca alteraram a decisão.

## A regra

Antes de escrever uma pergunta, classifique a ação:

| A ação é... | Faça |
|---|---|
| **Reversível** (dá para desfazer sem perder trabalho: commit em branch de sessão, mover arquivo, reinstalar plugin, devolver card com motivo) | **Execute.** Registre no relatório. |
| **Apenas registra** (criar card/item de backlog, escrever handoff, anotar débito, abrir issue) | **Execute.** Nunca pergunte "quer que eu crie um card?". |
| **Investigação / leitura** | **Execute.** |
| **Irreversível ou destrutiva** (apagar branch com commits únicos, `Won't Do` em card, force-push, apagar arquivo sem cópia, publicar para fora) | **Pergunte** — em lote, no fim. |
| **Custo real** (rodar N provas caras, gastar orçamento grande) | **Pergunte** — na largada, junto com todo o resto. |
| **Bifurcação genuína de preferência**, sem default defensável (reinstalar *ou* voltar versão; qual escopo atacar) | **Pergunte** — em lote. |

O exemplo canônico do dono: *"encontrei uma falha e sugiro criar um card"* →
**crie o card**. Contar depois é suficiente; pedir licença antes, não.

## Perguntas vão nas pontas, nunca no meio

Quando sobra algo que exige o usuário:

1. **Na largada**, se a resposta muda o plano inteiro (escopo, máximo de
   cards, o que fazer com o que empacar). Faça TODAS de uma vez, inclusive as
   que a rotina só encontraria no meio do caminho.
2. **No relatório final**, para o resto — lista numerada, uma pergunta fechada
   por item, cada uma com `Recomendo sim/não` (formato `plain-report`).

Nunca no meio da execução: a pergunta que interrompe um drain no card 3 de 5
força o usuário a recarregar o contexto inteiro para responder.

## Guardar o fio da sessão

Autonomia sem memória vira outra forma de ruído. Duas obrigações:

- **Proposta em aberto não some.** Se você propôs algo e o usuário ainda não
  respondeu (muitas vezes porque estava trazendo mais informação, não porque
  ignorou), a proposta **reaparece no próximo relatório**, atualizada, até ser
  aceita, recusada, ou descartada por você **com o motivo escrito**.
- **Assunto lateral fica estacionado.** Achado paralelo e aviso de
  SessionStart (worktree não integrada, handoff vencido, débito de outro
  módulo) **não viram pergunta no meio de outro assunto**. Anote e traga no
  fechamento da sessão. A exceção é o que bloqueia o assunto atual — aí é
  parte do assunto, não desvio.

## Rede de segurança

O que torna isto seguro em vez de temerário:

1. **Toda decisão auto-aplicada é nomeada no relatório final** — o usuário
   revisa depois, em bloco, em vez de autorizar antes, uma a uma.
2. **O canal de overrule existe:** `/common:debrief` (mantém/derruba decisões
   de um run) e o handoff da sessão.
3. **A fronteira do irreversível continua fechada** — default-yes nunca
   autoriza apagar trabalho.

## Sniff tests

- Escreveu "quer que eu...?" para algo reversível → apague a pergunta e faça.
- Vai perguntar duas coisas em turnos diferentes → junte numa lista só.
- A pergunta é sobre um assunto que não é o da sessão → estacione para o fim.
- Terminou a rotina e ficou "aguardando confirmação para prosseguir" sem ter
  entregue relatório → o relatório é que era o próximo passo.
