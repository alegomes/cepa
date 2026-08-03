---
name: plain-report
description: O formato obrigatório do relatório de trabalho feito — abertura leiga de até 3 frases, o que é do usuário, o detalhe técnico, e no fim a lista objetiva de decisões e próximos passos. Use ao fechar uma tarefa, entregar um veredito ou reportar um diagnóstico. Não se aplica a conversa, pergunta curta ou ida-e-volta de design.
---

# Skill: plain-report

O usuário disse, em 03/08/2026: *"o seu estilo de redação é confuso, o uso
excessivo de jargões internos cria muito atrito na leitura, geralmente eu tenho
que ler mais de uma vez pra conseguir entender algo"*.

A regra já existia no CLAUDE.md global dele — "2 frases leigas, recomendação
default, detalhe técnico por último" — e vinha sendo aplicada só a *findings*
técnicos isolados, nunca ao relatório inteiro. Esta skill fecha essa brecha de
leitura e vale para **todo relatório de trabalho feito**.

## Quando se aplica

Quando você fecha uma tarefa, entrega um veredito, reporta um diagnóstico —
qualquer resposta que conte o que foi feito. Reconhecível por um sinal
mecânico: **o turno alterou alguma coisa** (escrita, edição, commit).

Não se aplica a conversa, resposta de uma linha, pergunta de esclarecimento ou
discussão de design em andamento. Formatar um "sim, existe" em três blocos
seria pior que o problema.

## O formato

```
<Abertura: até 3 frases, zero jargão. O resultado, não o mecanismo.>

**Pra você:** <quantas decisões e quantos passos esperam por você — ou "nada">

### Detalhe técnico
<livre: arquivos, nomes, evidência, mecanismo>

### Decisões e próximos passos
*Responda por número: sim, não, ou "vamos falar".*
1. **<A pergunta fechada, respondível sem abrir nada.>**
   Recomendo **sim/não** — <o porquê em uma linha>.
   Se **<a outra resposta>**: <o que acontece então>.
```

Regras duras:

- **Abertura: no máximo 3 frases, e nenhum termo da seção "Traduzir sempre" do
  `common/glossario.md`.** Se você não consegue escrever a abertura sem um
  desses termos, você não entendeu o que fez — o termo está fazendo o trabalho
  que o entendimento deveria fazer.
- **`Pra você:` sempre presente**, mesmo quando a resposta é "nada pra
  decidir". O usuário precisa saber que pode parar de ler ali.
- **`### Decisões e próximos passos` sempre presente, e sempre por último.**
  Nada vem depois dela — é o lugar onde o usuário volta quando terminou de ler.
- **Teto de 200 palavras** somando abertura e `Pra você:`. O detalhe técnico é
  livre — quem não quer, para no cabeçalho.
- **Ordem: resultado antes de mecanismo.** Nunca abra por como funciona.
- **Abertura diz o que mudou, não o que eu fiz.** Lista de passos executados
  não é resultado — ver "O teste do 'e daí?'" abaixo.

## A lista do fim

Pedido do usuário em 03/08/2026: *"ao final de cada report, uma lista objetiva
de decisões a serem tomadas ou próximos passos a serem seguidos"*. O `Pra
você:` do topo respondia *se* existe algo pendente; ele não respondia *o que
fazer agora*, e estava em prosa no meio de um parágrafo.

Os dois convivem sem repetir: **o topo dá a contagem, o fim dá a lista.**

> **Pra você:** duas perguntas e um passo manual — lista no fim.

### Todo item é uma pergunta fechada

Segunda correção do usuário, no mesmo dia: a primeira versão da lista dizia o
**assunto** e devolvia a decisão. *"Qual de fato é a decisão que tenho que
tomar? Do jeito que está, preciso interpretar o texto, acessar o card, entender
todo o contexto, para poder elaborar uma próxima instrução."*

O item que ele reprovou:

> - **Decidir —** WEGO-1631, critério 6 (recusar pedido de documento com tipo
>   nulo, havendo linhas legadas em base). Derivei isso da sua regra "recusar
>   documento sem tipo"; se não tiver opinião, mantenha e confira o volume em
>   produção antes de implementar.

Não tem pergunta, e o "confira o volume antes" devolve trabalho em vez de
resolver. O mesmo item mastigado:

> 3. **Mantenho no WEGO-1631 o critério que recusa pedido sem tipo de
>    documento, mesmo que isso passe a barrar os pedidos legados?**
>    Recomendo **sim** — é a sua regra "sem tipo, não emite", e o critério só
>    vale na entrada nova.
>    Se **não**: tiro o critério 6 do card e os pedidos sem tipo seguem
>    passando como hoje.

Regras da lista:

- **Numerada.** O usuário responde "1 sim, 2 não, 3 vamos falar" sem citar
  texto. Lista com marcador obriga ele a copiar o item de volta.
- **Uma pergunta fechada por item, terminando em `?`.** Se você não consegue
  fechar a pergunta, você ainda não entendeu a escolha — investigue antes em
  vez de repassar a dúvida.
- **Respondível sem abrir nada.** O fato que a resposta exige (o critério em
  português, o número, o arquivo) vem dentro do item. Se responder obriga a
  abrir o card, o item está incompleto.
- **Sempre com `Recomendo sim` ou `Recomendo não`**, e o porquê em uma linha.
  Vale para os três tipos de item — inclusive "rodo o prove-drain?".
- **"Vamos falar" é sempre a terceira resposta**, dita uma vez no cabeçalho da
  seção, nunca repetida item a item.
- **Proibido devolver a decisão.** "Avalie na implementação", "confira o volume
  antes", "vale checar" não são recomendações: são o meu trabalho voltando pra
  ele. Ou eu recomendo, ou o item vira uma pergunta sobre investigar
  ("Investigo o volume de linhas legadas antes de decidir?").
- **Nunca vazia.** Sem nada pendente, escreva uma linha só: *Nada pendente.*
- **Ordenada por quem trava o quê:** o que bloqueia os outros vem primeiro.
- **Fora do teto de 200 palavras** — o teto vale só até o detalhe técnico. Mas
  lista de mais de 5 itens é sinal de que o turno fez coisa demais junto.

Os três tipos continuam existindo; agora eles só mudam **o verbo da pergunta**:

| Tipo | A pergunta soa assim |
|---|---|
| escolha de mérito | "Mantenho o critério X?" · "Troco Y por Z?" |
| ação que só ele faz | "Você roda `bin/install.sh --clean` agora?" — e o item diz o que quebra se não rodar |
| trabalho meu esperando o "vai" | "Rodo o `/board-flow:prove-drain` nos dois cards de In Review?" — e o item diz o custo |

## A regra que vale no texto inteiro

O bloco de detalhe técnico tem liberdade de **tamanho**, não de clareza. A
primeira versão desta skill o tratava como zona franca, e o usuário achou lá
dentro, no mesmo dia: *"virou um sinal mecânico"*, *"nunca são medidas"*,
*"chega por um caminho indireto"*. Nenhuma delas é jargão do projeto — são
categorias inventadas na hora que ocupam o lugar do fato.

**Nomeie a coisa, não a categoria da coisa.** Toda frase precisa sobreviver à
pergunta *"que sinal? que caminho? medido como?"*:

| Categoria | A coisa |
|---|---|
| "virou um sinal mecânico" | "o hook olha se o turno usou Edit ou Write" |
| "nunca são medidas" | "o hook não conta as frases nem procura os termos" |
| "chega por um caminho indireto" | "grava num arquivo e lê no turno seguinte" |

Dois corolários:

- **Quem age vem antes do que aconteceu.** "são medidas" esconde quem mede.
  Diga o sujeito: *o hook conta*, *o guard bloqueia*, *o teste falha*.
- **Se dá para nomear o arquivo, a classe ou o comando, nomeie.** "a peça
  responsável" custa as mesmas palavras que `report-style-lint.py`.

A lista de abstrações vive na seção "Abstrações a evitar" do
`common/glossario.md` e cresce com evidência: toda vez que o usuário apontar
uma frase obscura, ela entra lá.

## O teste do "e daí?"

Um relatório pode passar em tudo acima — frases curtas, zero jargão, cada coisa
nomeada — e ainda assim o usuário fechar a leitura pensando *"so what?"*. Foi o
que aconteceu em 03/08/2026 com o relatório da drenagem de Review: ele contava
**o que eu fiz**, passo a passo, e em nenhum momento **o que aquilo mudou**.

Toda frase tem que sobreviver à pergunta *"e daí?"*. A resposta é sempre uma
destas três, e cada uma tem um destino:

| Resposta a "e daí?" | O que fazer |
|---|---|
| "e daí que agora você pode X" / "e daí que Y deixou de ser risco" | escreva **isso** — é a frase que faltava |
| "e daí que está tudo normal" | corte a frase (ver "Higiene (não relatar)" no glossário) |
| "e daí que preciso que você decida" | é `Pra você:`, não abertura |

Os três jeitos de errar, todos no mesmo relatório:

**Procedimento no lugar do efeito.** *"Confirmei a correção no disco, reexecutei
o portão nos três cards, os três passaram, e foram para Done."* É o roteiro do
que fiz. O efeito: *"o verificador tinha um defeito que reprovava card bom;
corrigido, os três cards presos passaram — desta vez com prova refeita, então o
Done deles vale."*

**Evidência sem a conclusão que ela sustenta.** *"de 21 verdes para 4 falhas,
incluindo exatamente os dois testes do card"* prova alguma coisa — mas o
relatório nunca diz qual: *"o teste do card pega o bug de verdade"*. Número e
log vêm **depois** da frase que eles sustentam, nunca no lugar dela.

**Número sem consequência.** *"3 de 15 cards fechados nesta rodada (20%)"* soa
como progresso e não é: os 3 eram exatamente os que estavam presos, os outros 12
nunca chegaram a ser tentados. A conta obrigatória (regra do CLAUDE.md) precisa
vir com o que ela significa, ou vira ruído com aparência de rigor.

## O erro característico

Abertura real, de um relatório de 03/08/2026:

> "O portão agora falha fechado. Cada `status:` é conferido contra o enum
> fechado do seu nível, não contra uma lista de proibidos."

Quatro termos internos em duas frases, e o leitor ainda não sabe o que ganhou.
A mesma coisa dentro do formato:

> "O verificador de provas aceitava qualquer palavra que não estivesse numa
> lista de proibidas — um erro de digitação virava aprovação. Agora ele só
> aceita as palavras previstas.
>
> **Pra você:** nada pra decidir, um passo manual — lista no fim.
>
> [...]
>
> ### Decisões e próximos passos
> *Responda por número: sim, não, ou "vamos falar".*
> 1. **Você roda `bin/install.sh --clean` agora?** Recomendo **sim** — sem
>    isso a correção não vale na sessão de amanhã. Se **não**: o verificador
>    segue aceitando erro de digitação como aprovação."

## Relação com as outras skills

`conversational-response` continua valendo para a resposta que sobe a cadeia de
delegação (worker → lead). Esta aqui é mais estrita e vale na ponta, onde o
leitor é o usuário. Onde as duas se aplicam, esta ganha.

O `report-style-lint.py` mede o resultado ao fim do turno e devolve o desvio no
turno seguinte. Ele **avisa, não bloqueia** — a decisão de apertar depende do
que a telemetria mostrar (`/common:metrics`).

O que ele consegue medir do "e daí?" é só a parte literal: as frases de higiene
da lista do glossário, e apenas na abertura e no `Pra você:`. Distinguir
"reexecutei o portão nos três cards" (procedimento) de "os três cards presos
passaram" (efeito) exige entender o assunto, e nenhuma regex faz isso — essa
parte é minha, não do hook.
