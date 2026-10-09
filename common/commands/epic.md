---
description: Entrevista o dono no estilo "grill me" até um pacote de trabalho virar Epic demonstrável por ciclos, e escreve `docs/epics/<nome>.md`. Uma pergunta por turno, em prosa, sem lista de opções; o agente propõe a resposta, o dono corrige, e cada resposta é desafiada uma vez ("quem vê isso e onde?", "o que quebra se faltar?") antes de ser aceita e gravada no mesmo turno. Só declara `Status: pronta` quando cada ciclo da escada tem roteiro com efeito observável em tela e em backend, há pelo menos um invariante e a seção "Decidido sem perguntar" existe; o `spec-readiness-gate` barra o resto. Não escreve código. Retomável: rodar de novo sobre o mesmo nome continua de onde parou.
argument-hint: <nome> [a intenção em prosa]
interaction: conversational
---

# /common:epic

## Purpose

Escrever o documento que diz **o que alguém vê funcionando no fim de cada
ciclo** de um pacote de trabalho grande, antes de qualquer fila existir.

O `/common:spec` fecha uma especificação por critérios: cada um com superfície e
teste vermelho. Isso serve para um pedaço que cabe numa fila. Não serve para um
pacote que leva várias filas, em que a pergunta que importa é outra: em que
ordem o valor aparece, e como o dono confere que apareceu. Essa é a escada de
valor do formato `docs/epics/<nome>.md`, que nasceu à mão em
`docs/epics/cepa-em-espiral.md` (decisão 1 da estratégia em
`docs/estrategia-cepa-proximo-nivel.md`).

Por isso é um comando à parte e não uma flag do spec: o spec fecha com
critérios, o epic fecha com roteiros. Depois dele, o `/common:plan --from-epic
docs/epics/<nome>.md --ciclo N` transforma um ciclo em fila.

**Grill me** é o pedido do dono para este comando (2026-10-08), e quer dizer
cinco coisas, que estão abaixo como regra: uma pergunta por turno, em prosa,
sem menu; o agente propõe a resposta e o dono corrige; a resposta é desafiada
uma vez antes de ser aceita; a resposta aceita é gravada no mesmo turno; e o
documento fecha pelo crivo, não por cansaço.

## Variables

- `<nome>` — o Epic em kebab-case. O arquivo é `docs/epics/<nome>.md` na raiz do
  repo onde a sessão está.
- `[a intenção em prosa]` — opcional: o que o dono quer, do jeito que contaria a
  uma pessoa. Sem ela, a primeira pergunta é a intenção.

## Instructions

Você é o entrevistador. Carregue a skill `guided-interrogation` e opere sob ela
do primeiro turno ao último: dentro deste frame, `active-listener`,
`zero-micromanagement` e `default-yes` estão suspensas. Este comando é **mais
estreito** que a skill num ponto: a skill admite até quatro perguntas por
rodada; aqui é **uma pergunta por turno**.

**Não implemente nada.** O único arquivo que este comando escreve é
`docs/epics/<nome>.md`. Se você se pegar querendo ler código para responder uma
pergunta de produto, a pergunta é para o dono; ler código para não perguntar o
que o repo já responde, sim.

**Não delegue a subagente.** Um subagente não conversa com o dono, e a pergunta
voltaria como suposição.

**Rode na sessão em modo `descoberta`.** É o modo que produz este documento: o
`modo-escrita-gate` libera `docs/epics/**` nele. O `/common:session` recusa este
comando (o `session-routine-guard` lê o `interaction: conversational` acima),
porque cada resposta decide a pergunta seguinte e nada disso é antecipável.

## Workflow

### 1. Abrir ou retomar o documento

Se `docs/epics/<nome>.md` existe, leia-o inteiro e retome da primeira lacuna
(passo 3 diz a ordem): não recomece, e não faça de novo uma pergunta que já tem
`- [x]`. Se não existe, crie com o esqueleto do passo 6 e `**Status:**
rascunho` antes da primeira pergunta. O gate nunca incomoda enquanto o status
for `rascunho`.

### 2. Ler antes de perguntar

Antes da primeira pergunta, leia o que já responde parte delas: `docs/` (a
estratégia, as especificações, os ADRs), o `BACKLOG.md`, os outros
`docs/epics/*.md`, e o código da área que a intenção nomeia. A pergunta boa é a
que sobra depois de ler. Uma pergunta cuja resposta estava no repo ensina ao
dono que a entrevista é burocracia.

### 3. Perguntar, uma por turno, na ordem do custo de errar

A ordem das lacunas:

1. **Intenção** — o que o dono quer, em duas ou três frases na voz dele, e o que
   hoje dói.
2. **Invariantes** — o que nunca pode regredir enquanto os ciclos andam.
3. **A escada** — quantos ciclos e o nome de cada um; depois, ciclo a ciclo:
   **Roteiro** (o que o dono vê funcionando no fim do ciclo), **Efeito em tela**
   (onde, na tela, alguém vê que aconteceu), **Efeito em backend** (o registro,
   endpoint ou evento que prova que aconteceu de verdade, não só na tela), **O
   que atravessa** (as peças que mudam, uma frase por peça) e **Quando**.
4. **Perguntas em aberto** que a própria conversa levantou.

Cada turno tem exatamente **uma pergunta**, escrita em **prosa**, terminando
com `?`, e é o único `?` do turno: "isso, e também aquilo?" são duas. **Nunca
uma lista de opções**: nada de "a) … b) … c)", nada de bullets de
alternativas, nada de `AskUserQuestion`, e nada de alternativas enumeradas
dentro da frase ("dói mais achar o contrato, achar a cláusula ou entender a
cláusula?"), que é o mesmo menu escrito em linha. Menu faz o dono escolher
entre as respostas que o agente imaginou, e o grill me existe para sair do que
o agente imaginou. A alternativa que você acha mais provável vai na proposta,
não na pergunta.

**Turno de entrevista é conversa, não relatório de trabalho.** Gravar no
arquivo a cada turno não transforma o turno em relatório: não use o formato
`plain-report` aqui (nada de `**Pra você:**`, de "Detalhe técnico", de lista
numerada de decisões com "Recomendo sim"). O turno tem, no máximo, uma linha
dizendo o que foi gravado, e termina na pergunta. Pergunta fechada numerada é
menu com outra roupa. O relatório no formato `plain-report` vem uma vez, no
fechamento (passo 5).

**Proponha a resposta junto com a pergunta**, em uma frase, com o porquê, e
ponha a proposta **antes** da pergunta, para o turno terminar nela: "Minha
proposta é que o operador veja as três respostas na tela de upload, porque é a
primeira tela que ele já usa. Onde ele deveria ver as respostas?" O dono
corrige mais rápido do que escreve do zero, e a proposta mostra o que o agente
entendeu.

O teste para saber se algo vira pergunta continua o da skill: **duas respostas
diferentes aqui mudam o que vai ser construído ou como vai ser demonstrado?**
Se não, decida e registre em "Decidido sem perguntar".

### 4. Desafiar uma vez, aceitar, gravar no mesmo turno

Quando o dono responde, **não aceite de primeira**. Desafie a resposta **uma
vez**, com uma pergunta só, apontada para o buraco mais caro dela. Os dois
desafios-modelo:

- "quem vê isso e onde?" — para roteiro e efeito: se ninguém vê, ou se só se vê
  no log, não é demonstração;
- "o que quebra se faltar?" — para invariante, ciclo e peça que atravessa: se
  nada quebra, não é invariante, e talvez o ciclo não precise existir.

No turno do desafio, registre a pergunta como `- [ ]` em "Perguntas em aberto",
com a resposta provisória do dono na mesma linha. O desafio é **um só**: a
resposta que o dono dá a ele é aceita como está, mesmo que você ainda
discorde. Discordância que sobra vai, nomeada, para "Riscos"; não vira segundo
desafio, porque desafio que não acaba é cansar o dono até ele ceder.

No turno em que a resposta é aceita, **antes da próxima pergunta**, grave-a no
arquivo: na seção a que pertence (a célula da escada, o item de invariante, o
parágrafo da intenção) e marque a linha de "Perguntas em aberto" como `- [x]`
com a resposta aceita. Só então faça a próxima pergunta. Resposta que só existe
na conversa se perde no primeiro compactar de contexto, e o dono responde tudo
de novo.

### 5. Fechar pelo crivo, nunca por cansaço

O Epic vira `**Status:** pronta` quando, e só quando:

- a tabela de `## Escada de valor` tem pelo menos um ciclo, e cada ciclo
  preenche **Roteiro**, **Efeito em tela** e **Efeito em backend**;
- `## Invariantes` tem pelo menos um item;
- a seção `## Decidido sem perguntar` existe (vazia de decisões é aceitável;
  ausente, não);
- nenhuma `- [ ]` sobrou em "Perguntas em aberto".

O hook `spec-readiness-gate` aplica esse crivo a todo arquivo em
`docs/epics/*.md` e a todo documento que abre com `# Epic:`, e barra a escrita
do `Status: pronta` enquanto faltar qualquer item, dizendo qual ciclo e qual
coluna. Se ele barrar, **a resposta certa é voltar a perguntar**, nunca encher a
célula até passar.

**Quando o dono pede `pronta` antes do crivo passar, recuse em voz alta.** Diga
em uma frase o que ainda falta (qual ciclo, qual coluna, qual seção) e faça a
pergunta dessa lacuna. Não marcar e não dizer nada deixa o dono achando que
foi atendido. Fora isso, quando a última lacuna fecha, o crivo passa e você
grava `pronta` no mesmo turno, sem esperar o dono pedir.

Ao fechar, diga ao dono o caminho do arquivo e o próximo passo: `/common:plan
<nome>-c1 --from-epic docs/epics/<nome>.md --ciclo 1` deriva a fila do primeiro
ciclo.

### 6. O formato do arquivo

```markdown
# Epic: <assunto>

**Status:** rascunho · **Aberto em:** <data> · **Origem:** <de onde veio o pedido>

## Intenção

<o que o dono quer e o que hoje dói, na voz dele>

## Invariantes (nunca regridem)

- <o que nunca pode regredir enquanto os ciclos andam>

## Escada de valor

| Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
| 1. <nome> | <o que o dono vê funcionando> | <onde, na tela> | <registro, endpoint ou evento> | <uma frase por peça que muda.> | <quando> |

## Decidido sem perguntar (vete aqui)

- <decisão> — <porquê>.

## Perguntas em aberto

- [x] <pergunta> <resposta aceita>
- [ ] <pergunta desafiada> (provisória: <resposta do dono>)

## Riscos

- <discordância que sobrou de um desafio, ou risco que a conversa levantou>
```

O `Status` aceita `rascunho | pronta`. A coluna "O que atravessa" é escrita em
frases curtas terminadas em ponto, uma por peça, porque o `--from-epic` do
`/common:plan` faz de cada frase um item da fila daquele ciclo.

## Constraints

- **Uma pergunta por turno, em prosa, com proposta.** Nunca lista de opções,
  nunca `AskUserQuestion`, nunca o formato `plain-report` no meio da entrevista.
- **Cada resposta é desafiada exatamente uma vez** antes de ser aceita.
- **A resposta aceita é gravada no mesmo turno**, antes da próxima pergunta.
- **Nunca declara `pronta` o que o crivo recusa.** Se o gate barrar, volte a
  perguntar.
- **Só escreve `docs/epics/<nome>.md`.** Nem código, nem fila: a fila é do
  `/common:plan --from-epic`.
- **Não delega a entrevista**, e não roda dentro do `/common:session`.
