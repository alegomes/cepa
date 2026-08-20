---
name: guided-interrogation
description: Use dentro de um frame de especificação — /common:spec, ou quando o usuário pede explicitamente para ser "grelhado", entrevistado ou interrogado até fechar um escopo. Suspende, e SÓ dentro desse frame, as três skills que empurram o agente a decidir sozinho (active-listener, zero-micromanagement, default-yes). Fora do frame, elas continuam valendo. Gatilhos — "me interrogue", "me grelhe", "me entreviste", "pergunta até fechar", "quero detalhar antes de construir", "especificação de alto nível", "não implemente ainda".
---

# Skill: guided-interrogation

O harness é construído para **não** perguntar. `active-listener` diz que 80%
dos pedidos de esclarecimento são contexto não lido. `zero-micromanagement` e
`default-yes` mandam decidir sozinho o que é reversível e prestar conta depois.
Isso é certo na construção, onde cada pergunta custa um turno do dono e a
resposta quase sempre já estava no card.

Na especificação é o contrário, e é o contrário por um motivo estrutural: **a
informação que falta não está em lugar nenhum que o agente possa ler.** Ela está
na cabeça do dono e não foi escrita ainda. Adivinhar aqui não economiza turno —
produz uma especificação plausível e errada, que só se revela errada depois de
construída.

## O que esta skill suspende, e só aqui

Dentro de um frame de interrogação declarado:

| Skill | Regra normal | Dentro do frame |
|---|---|---|
| `active-listener` | não peça esclarecimento, releia o contexto | releia primeiro, **e depois pergunte assim mesmo** — o contexto não contém a resposta |
| `zero-micromanagement` | não devolva escolha ao dono | devolver escolha **é** o trabalho |
| `default-yes` | decida o reversível sozinho | uma decisão de escopo aqui não é reversível: ela vira código |

Fora do frame — mesma sessão, turno seguinte, qualquer outro comando — as três
voltam a valer integralmente. A suspensão é do frame, não da sessão.

## Como interrogar

**Uma rodada por turno, no máximo quatro perguntas.** Interrogatório não é
formulário: cada resposta muda quais são as próximas perguntas. Despejar
quinze de uma vez transfere ao dono o trabalho de ordenar, que é seu.

**Pergunte o que muda o que vai ser construído.** Antes de escrever uma
pergunta, responda a si mesmo: *duas respostas diferentes aqui produzem código
diferente?* Se não, não pergunte — decida e registre. Preferência de estilo,
nome de variável, ordem de campo: decida.

**Toda pergunta traz recomendação.** "Se você não tiver opinião, faça X, porque
Y." O dono precisa poder responder "sim, sim, não" e seguir. Pergunta sem
recomendação devolve o trabalho inteiro.

**Ataque primeiro o que tem mais consequência.** A ordem é por custo de errar,
não pela ordem em que os assuntos apareceram na conversa. Fronteira de escopo e
contrato antes de caso de borda.

**Registre a resposta na hora.** Cada resposta vai para o documento no mesmo
turno. Interrogatório cuja resposta só existe no histórico da conversa se perde
no primeiro compactar de contexto.

**Nomeie o que você decidiu sozinho.** O que não virou pergunta e mesmo assim
foi decidido aparece numa lista à parte do documento, para o dono poder vetar.
Decisão silenciosa é o mesmo furo, com outra roupa.

## Quando o interrogatório acaba

Não acaba por cansaço, e não acaba porque o agente achou que está bom. Acaba
quando a especificação passa num crivo mecânico:

- todo critério de sucesso tem uma **superfície** do vocabulário fechado
  (`http`, `cli`, `ui`, `event`, `domain`, `application`) — a camada mais
  externa que o critério nomeia;
- todo critério tem um **teste vermelho** declarado naquela superfície: a frase
  do teste que hoje falharia e que passará quando a coisa existir;
- nenhuma pergunta em aberto continua sem resposta.

É a mesma régua da skill [`acceptance-completeness`](../acceptance-completeness/SKILL.md),
aplicada uma fase antes. Lá ela julga se um card está pronto para ir a revisão;
aqui, se uma especificação está pronta para virar código. Usar a mesma régua nas
duas pontas é o ponto: a especificação nasce já medida pelo gate que a julgaria
no fim.

O campo se chama **Superfície** e não *Altitude* de propósito: `Altitude` já é
um campo de bloco de decisão, com outro vocabulário fechado
(`strategic`/`tactical`/`implementation`) e um gate próprio na escrita. Dois
campos de mesmo nome e vocabulário diferente é como se aprende a ignorar os dois.

## O que esta skill não é

Não é licença para perguntar em qualquer lugar. Fora de um frame declarado, a
pergunta continua sendo o último recurso, não o primeiro. E não é licença para
perguntar o que dá para descobrir lendo: antes de cada rodada, leia o código, o
board e os documentos que existem. A pergunta boa é a que sobra depois disso.
