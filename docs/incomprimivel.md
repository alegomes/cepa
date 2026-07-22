# A lista do incomprimível

Trabalho repetitivo empurra todo agente a comprimir: pular a etapa óbvia,
responder em bloco, assumir o default. Quase sempre isso é saudável. O
problema é que alguns campos existem **justamente para não serem comprimidos**,
e a pressão de compressão não distingue um do outro.

Este doc é a regra explícita, por gate existente do cepa: o que pode virar
trabalho trivial e o que **nunca** pode, por mais rotineira que a tarefa
pareça. Não cria gate novo. É o spec de crescimento dos gates que já existem:
quando alguém for estender um deles, o critério de "isto é incomprimível" mora
aqui.

## O princípio

Um campo é **incomprimível** quando a sua ausência é indistinguível de uma
resposta negativa honesta. "Não há dívida" e "não pensei em dívida" produzem o
mesmo silêncio. Para um agente LLM, silêncio é invisível: ninguém consegue
auditar uma pergunta que não foi feita. O gate transforma a pergunta em algo
que um `string-match` alcança, e é por isso que ela tem que ser respondida —
mesmo (sobretudo) quando a resposta é "nenhum".

Comprimir um campo incomprimível não economiza trabalho. Ele adia o custo para
o momento em que alguém precisa da informação que ninguém registrou, e aí ela
não existe mais.

## Por gate

### `summary-nulls-gate` — os quatro nulos do Implementation Summary

Incomprimível. Todo summary responde, mesmo em negativo:

- **New debt introduced** — `none` dito, nunca pulado.
- **Scope captured outside the card** — follow-ups capturados, não absorvidos.
- **Release needed** — `no` dito é diferente de campo ausente.
- **Human validation route** — ou uma rota real (comando/URL + observação
  esperada + condição de falha), ou o explícito "not applicable (internal
  substrate)". Teste automatizado nunca substitui em silêncio a checagem
  humana de comportamento visível; o humano nunca é convocado em silêncio para
  validar encanamento.

Condicional, mas igualmente incomprimível: se `New debt introduced` ≠
none/unknown, o **Revisit trigger** passa a ser obrigatório. Declarar dívida e
parar aí é como a dívida sobrevive ao card sem ninguém segurando a corda.

**Comprimível aqui:** a redação. O gate prova que a pergunta foi respondida,
não como foi fraseada — pt-BR ou inglês, ordem das palavras solta, markdown ou
wiki. Reformatar o rótulo é trivial; omitir o campo, nunca.

### `bounce-reason-gate` — a razão da devolução

Incomprimível. Um card devolvido (UNPROVEN, retorno para rework, "devolução")
carrega um **Reason:/Motivo:** com texto. A próxima sessão não pode ter que
re-derivar do diff por que o card voltou.

**Comprimível aqui:** nada que dispense a razão POR card. Uma razão única
colada em N cards de um lote é exatamente a falha que o gate combate: lê como
respondida enquanto não diz nada sobre nenhum card individual (ver
[versionamento](versionamento.md) e a regra de fechamento acoplado do
`prove-drain`).

### `acceptance-gate` — a auditoria de aceite antes do In Review

Incomprimível. O card não transita para In Review enquanto a auditoria de
aceite estiver incompleta. Cada critério é fixado à sua altitude e um teste o
demonstra AQUELA superfície ponta a ponta. "As duas metades cobertas em
separado" é INCOMPLETE, não rodapé.

**Comprimível aqui:** nada. Um gap justificado continua sendo gap; deem-no ao
humano em vez de julgá-lo aceitável sozinho.

### `check-terminal` do maestro — o estado de cada slice ao aterrissar

Incomprimível. A onda não chega ao merge train nem ao relatório com slice em
`pending`/`running`. Esses não são resultados: são a ausência de um. "Precisa
de atenção" não é estado. A saída honesta quando não dá para concluir é
`ESCALATED` com o motivo, não silêncio.

**Comprimível aqui:** qual dos quatro estados terminais
(DONE/FAIL/TIMEOUT/ESCALATED) — isso o event loop decide. O que não se comprime
é a exigência de que haja um.

### `green-or-revert` — o estado de build antes de commit/push

Incomprimível. Não se commita, faz push ou deploy com o build vermelho, e o
agente não reivindica correção de runtime sem prova. `git diff` vazio não diz
nada sobre o build passar.

**Comprimível aqui:** o repo pode optar por `.claude/no-build` quando não há
baseline a cobrar — mas isso é uma declaração explícita, não uma omissão.

## Como usar esta lista

Ao estender um gate ou criar um novo, a pergunta não é "isto incomoda?" — todo
gate incomoda. A pergunta é: **a ausência da resposta é indistinguível de uma
negativa honesta?** Se sim, o campo é incomprimível e o gate o exige com nulo
explícito permitido. Se não, é preferência de forma e não merece um gate.

E a regra que segura todas as outras: um gate que erra — que bloqueia uma
resposta honesta por causa de formatação — ensina o agente que bloqueio é ruído
e a contornar mecanicamente. Por isso todo gate desta lista separa "não
respondeu" de "respondeu num formato que não reconheço". Gate que confunde os
dois destrói a própria autoridade.
