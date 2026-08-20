---
description: Conduz um interrogatório até uma ideia de alto nível virar especificação construível — e para ali, sem escrever uma linha de código. Você descreve o que quer em prosa; o comando pergunta em rodadas, registra cada resposta num markdown versionado no repo, e só declara a especificação pronta quando todo critério de sucesso tem uma superfície observável (http/cli/ui/event/domain/application) e um teste vermelho declarado nela. Não exige Jira nem quadro configurado — ao fechar, oferece registrar Epic + Stories se board-flow estiver instalado. Retomável: rodar de novo sobre a mesma especificação continua de onde parou.
argument-hint: <a ideia em prosa> | --continuar <slug> | --fechar <slug> | --lista
---

# /common:spec

## Purpose

Cobrir a fase que o harness não tinha: **de uma ideia de alto nível até uma
especificação rica o bastante para ser construída depois**, sem que nada seja
construído agora.

O que existia antes deste comando, e por que não servia:

- `/board-flow:plan-track-build-validate` aceita prosa e quebra em Stories, mas
  não tem parada: registra Epic e Stories nos passos 1 a 3 e no passo 4 já
  escolhe uma Story para implementar. A parada só existia como promessa do
  agente em prosa — dependia de ele lembrar de parar.
- `/board-flow:capture` para de verdade, mas é deliberadamente burro: um card,
  sem quebra e sem especificação.
- A topologia `discovery` tem seis agentes e um comando (`/discovery:capture`).
  O resto anda por `/board-flow:advance`, que exige card no Jira, exige quadro
  de descoberta configurado, e move uma coluna por invocação. Nenhum agente dela
  sustenta conversa: o contrato do `discovery-lead` diz, com essas palavras,
  "uma mensagem concisa por invocação".

Nenhum deles **pergunta**. E é disso que a especificação vive: a informação que
falta não está em lugar nenhum que se possa ler — está na cabeça do dono e não
foi escrita ainda.

**Isto não é o `discovery` em miniatura.** A topologia de descoberta responde
"vale a pena resolver isto?" com evidência de usuário. Este comando assume que
já vale, e responde "o que exatamente vamos construir?". Se a pergunta em aberto
ainda é se o problema é real, o lugar é `/discovery:capture` e a topologia de
descoberta, não aqui.

## Variables

- `$ARGUMENTS` — a ideia em prosa, do jeito que você contaria para uma pessoa.
  Não precisa ser organizada; organizá-la é o trabalho do comando.
- `--continuar <slug>` — retomar uma especificação existente de onde parou.
- `--fechar <slug>` — rodar só o crivo de encerramento sobre uma existente e,
  se passar, oferecer o registro no tracker.
- `--lista` — listar as especificações do repo com o status de cada uma.

## Instructions

Você é o entrevistador, não o planejador. Carregue a skill
`guided-interrogation` e opere sob ela do primeiro turno ao último: dentro deste
frame, `active-listener`, `zero-micromanagement` e `default-yes` estão
suspensas — perguntar é o trabalho, não o último recurso. Fora do frame, no
turno seguinte a este comando fechar, as três voltam a valer.

**Não implemente nada.** Nem um arquivo de código, nem um teste, nem um
esqueleto "só para ilustrar". O único arquivo que este comando escreve é a
própria especificação. Se você se pegar querendo escrever código para descobrir
a resposta de uma pergunta, a pergunta é para o dono.

**Não delegue a subagente.** O interrogatório é entre você e o dono; um
subagente não tem como conversar com ele, e a rodada de perguntas voltaria como
suposição. Ler o código para se preparar, sim — `Explore` serve. Conduzir, não.

## Workflow

### 1. Localizar ou abrir a especificação

O diretório é `docs/spec/` na raiz do repo (crie se não existir). O arquivo é
`docs/spec/<slug>.md`, com `<slug>` derivado do assunto em kebab-case.

- Com `--lista`: leia o campo `Status` de cada `docs/spec/*.md` e devolva a
  tabela (slug · status · nº de critérios · nº de perguntas em aberto). Pare.
- Com `--continuar <slug>` ou `--fechar <slug>`: leia o arquivo e vá para o
  passo 4 (continuar) ou 5 (fechar).
- Sem flag: se já existe `docs/spec/<slug>.md` para um assunto claramente igual,
  **não crie um segundo** — diga que existe e pergunte se é para continuar
  aquela. Duas especificações do mesmo assunto divergindo em silêncio é pior do
  que nenhuma.

Escreva o esqueleto com `**Status:** rascunho` (o formato está no passo 6). O
gate `spec-readiness-gate` nunca incomoda enquanto o status for `rascunho`.

### 2. Ler antes de perguntar

Antes da primeira rodada, gaste um passo lendo o que já responde parte das
perguntas: o código da área que o assunto toca, os documentos em `docs/`, o
`BACKLOG.md`, e — se `board-flow.yaml` existir — os cards abertos do assunto via
`atlassian-expert` (leitura, sem escrever nada).

Pergunta cuja resposta estava no repo queima a paciência do dono e ensina que o
interrogatório é burocracia. A pergunta boa é a que sobra depois de ler.

### 3. Interrogar, em rodadas

**No máximo quatro perguntas por turno**, com recomendação em cada uma
(`Recomendo X, porque Y`), ordenadas por custo de errar: fronteira de escopo e
contrato antes de caso de borda. Use `AskUserQuestion` quando as respostas forem
escolhas fechadas; prosa quando for aberta.

O teste para saber se algo vira pergunta: **duas respostas diferentes aqui
produzem código diferente?** Se não, decida sozinho e registre a decisão na
seção "Decidido sem perguntar" — o dono veta lá se quiser.

Cubra, ao longo das rodadas, o que sempre falta e sempre custa caro:

- **Fronteira de escopo** — o que explicitamente NÃO entra. A lista do que fica
  de fora vale mais que a do que entra, porque é a que ninguém escreve.
- **Contrato e formato** — o que entra e o que sai, em termos observáveis.
- **Estado e migração** — o que muda no que já existe, e o que acontece com o
  dado que já está lá. (Este é o buraco que motivou o comando: é aqui que o
  modelo de dados aparece, como consequência do escopo, não como assunto
  separado.)
- **Casos de borda e erro** — o que acontece quando dá errado, e quem vê.
- **Critérios de sucesso** — a frase observável que diz que funcionou.

### 4. Registrar cada resposta no mesmo turno

Depois de cada rodada, escreva o que foi respondido no arquivo **antes** de
fazer a próxima pergunta. Resposta que só existe no histórico da conversa se
perde no primeiro compactar de contexto, e o dono responde tudo de novo.

Uma pergunta feita vira `- [ ]` na seção "Perguntas em aberto"; respondida, vira
`- [x]` com a resposta na mesma linha. É assim que `--continuar` sabe onde parou.

### 5. Fechar pelo crivo, nunca por cansaço

A especificação vira `**Status:** pronta-para-construir` quando, e só quando:

- todo critério tem `**Superfície:**` do vocabulário fechado — `http`, `cli`,
  `ui`, `event`, `domain`, `application` — a camada mais externa onde o critério
  é observável;
- todo critério tem `**Teste vermelho:**`: a frase do teste que **hoje**
  falharia naquela superfície e passará quando a coisa existir;
- nenhuma `- [ ]` sobrou.

É a mesma régua da skill `acceptance-completeness`, que do outro lado do muro
decide se um card pode ir a revisão. Usar a mesma nas duas pontas é o ponto: a
especificação nasce medida pelo gate que a julgaria no fim.

O hook `spec-readiness-gate` bloqueia a escrita do `Status: pronta-para-construir`
enquanto faltar qualquer um. Se ele bloquear, **a resposta certa é voltar a
perguntar**, nunca amaciar o campo até passar.

O campo se chama **Superfície** e não *Altitude* de propósito: `Altitude` já é
um campo de bloco de decisão, com outro vocabulário fechado
(`strategic`/`tactical`/`implementation`) e gate próprio na escrita. Dois campos
homônimos com vocabulários diferentes é como se aprende a ignorar os dois.

### 6. O formato do arquivo

```markdown
# Especificação: <assunto>

**Status:** rascunho
**Aberta em:** <data>            **Fechada em:** <data ou ->

## Problema
<o que dói hoje, em duas ou três frases, na voz do dono>

## Escopo
### Entra
- ...
### Não entra
- ...  (com o porquê, em meia linha)

## Estado e migração
<o que muda no que já existe; o que acontece com o dado que já está lá; "nada"
é resposta válida e explícita>

## Critérios de sucesso

### CS-1: <o critério em termos observáveis>
**Superfície:** http
**Teste vermelho:** <a frase do teste que hoje falharia>

## Perguntas em aberto
- [x] <pergunta> — <resposta do dono>
- [ ] <pergunta ainda sem resposta>

## Decidido sem perguntar
- <decisão> — <porquê>. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- ...
```

### 7. Oferecer o tracker, nunca impor

Fechada a especificação, se `board-flow.yaml` existir no repo, ofereça **uma**
pergunta fechada: registrar Epic + Stories no Jira a partir dos critérios, ou
deixar só o arquivo. Recomende registrar — o arquivo não aparece na fila de
ninguém.

Se o dono aceitar, delegue a `atlassian-expert` (único caminho de escrita no
Jira): um Epic com o Problema e o Escopo, uma Story por critério de sucesso,
cada uma carregando sua Superfície e seu Teste vermelho no corpo, e o caminho do
arquivo no Epic. Grave as chaves de volta no arquivo, numa seção `## Registrado
em`. Sem `board-flow.yaml`, não pergunte: diga que ficou só o arquivo e qual é o
caminho.

**Nem aqui você implementa.** O comando termina com Stories escritas e nenhuma
linha de código.

## Constraints

- **Nunca escreve código, teste ou migração.** Só `docs/spec/<slug>.md` (e as
  chaves do tracker, se o dono pedir).
- **Nunca declara pronta uma especificação que o crivo recusa.** Se o gate
  bloquear, volte a perguntar.
- **No máximo quatro perguntas por turno.** Quinze de uma vez transfere ao dono
  o trabalho de ordenar, que é seu.
- **Toda pergunta traz recomendação.** Pergunta sem recomendação devolve o
  trabalho inteiro.
- **Uma especificação por assunto.** Ao encontrar uma existente, continue-a.
- **Não delega o interrogatório.** Ler para se preparar, sim; conduzir, não.
