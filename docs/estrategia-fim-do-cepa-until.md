# O que o dono faz quando o `cepa-until` termina, e como reduzir esse atrito

Status: proposta de estratégia. Nada implementado.
Data: 2026-09-26. Base: `common/bin/cepa-until` (1425 linhas), `docs/cepa-until.md`,
run `WEGO` `2026-09-26-1102` no `wego-acessos-backend` (registro `.jsonl`, análise
`.review.md` e o resumo impresso no terminal).

## O que é cada coisa

- **`cepa-until`**: o supervisor que executa a fila `single-track` de um repo por uma janela
  de tempo (`--for 4h`). Cada item roda num subprocesso `claude -p`.
- **Branch da noite**: `until/<run>`, numa worktree fora da árvore sincronizada. Todo commit
  do run vai para ela. A `main` e o `origin` nunca são tocados pelo run (decisão 3 do dono em
  `docs/cepa-until.md`).
- **Build completo do supervisor** (`verify`): o `./mvnw -B clean verify` que o supervisor
  roda na branch da noite depois de cada item `done`.
- **Branch lateral do vermelho**: `until/<run>-vermelho-<card>`. Quando o build completo fica
  vermelho depois de um item, o supervisor move os commits do item para ela, volta a branch
  da noite e marca o item `blocked` (`desfaz_item`, `cepa-until:779`).
- **Análise** (`.review.md`): o que o `/common:until-review` escreve no fim do run. É um texto
  livre, redigido por um modelo, que termina em perguntas fechadas com recomendação.
- **Aterrissar**: levar a branch da noite para a `main` e fazer o push. Hoje é à mão.

## O atrito, medido no run de 26/09

**A1. O terminal termina apontando um arquivo, não dizendo o que fazer.**
As últimas linhas do resumo são `análise: rodando…` e `análise: <caminho>.review.md`
(`cepa-until:1405` e `:1411`). As decisões estão dentro do arquivo. O dono perguntou "ao
final do cepa-until, o que eu devo fazer?" com o resumo na tela.

**A2. Depois de decidir, a execução é manual e tem duas receitas.**
A linha impressa é `no clone, git merge until/<run> (ou /common:worktree-merge), build
completo, push` (`cepa-until:1391`). Para o 2320, o dono ainda teria de fazer cherry-pick da
lateral, devolver o item para `done` na fila e rodar o build. Nenhum comando junta isso.

**A3. O rótulo "travado" mentiu.**
O WEGO-2320 foi marcado `blocked` porque o teste
`CadastroComTagsE2ETest.doisCadastrosSimultaneosComMesmaTagNovaCriamUmaTagSo` falhou. O card
não toca cadastro nem tags, e o mesmo código passou no build das 14:22 (3.176 testes, 0
falhas) contra o das 14:47 (3.176 testes, 1 falha). Fonte: relatórios em
`~/.wego-acesso/test-reports/20260926-*`, conferidos pela análise do run.

**A4. O mesmo item aparece em três listas.** O 2320 está em "Travados", "Build vermelho" e
"Sem progresso". Lê-se como três problemas.

**A5. A separação do vermelho só pega a última tentativa.** `desfaz_item` recebe `antes`, o
HEAD do começo da tentativa atual. O 2320 levou duas tentativas: a lateral ficou com os 2
commits de documentação da segunda (`efd455f7`, `2e9f8700`), e os 9 commits de código da
primeira ficaram na branch da noite. Conferido com `git log` nas duas branches.

**A6. Ruído no cabeçalho e no resumo.** 13 linhas de configuração com termos sem explicação
(disjuntor, reserva, folga). Caminhos absolutos pela pasta do Insync ocupam meia tela. O custo
(US$ 32,86 = 8,07 + 2,99 + 4,56 + 14,15 + 3,09, o `total_cost_usd` das 5 rodadas arredondado a centavos; a análise do run diz 32,87, provavelmente somando os valores antes de arredondar) só aparece
na análise.

**A7. Nada lembra que um run espera aterrissagem.** Não há notificação no fim (`grep` por
`osascript`/`notify` no `cepa-until`: zero). A abertura da sessão lista worktrees de sessão
não mescladas, mas não branches `until/*`. É o mesmo modo de falha do item "Onda termina e
ninguém aterrissa" do BACKLOG (maestro, 24/08): o estado não distingue "trabalhando" de
"terminou e ninguém veio buscar".

## Riscos que qualquer caminho tem que respeitar

- **R1. A `main` só muda com o dono presente.** A decisão 3 do dono proíbe o run de mexer na
  `main`. Um comando que aterrissa só vale se for disparado pelo dono.
- **R2. Texto livre não é contrato.** A análise é redigida por um modelo. Um comando
  determinístico não pode executar "a pergunta 2" se a pergunta 2 muda de redação a cada run.
  As ações precisam ser de um conjunto fechado.
- **R3. "Teste alheio" é heurística, não prova.** Um card pode quebrar um teste de outro
  módulo por acoplamento de comportamento (banco, cache, Keycloak compartilhado). Classificar
  como instável sem nenhuma checagem vira `done` falso.
- **R4. O build leva ~15 min.** Toda checagem extra no vermelho custa relógio da janela.

## Caminhos considerados

### Caminho 1: comando determinístico `cepa-until aterrissar <run>`

O supervisor passa a gravar, além do `.jsonl`, uma lista fechada de **ações propostas** do
run, cada uma com id estável e recomendação:

| Ação | Quando aparece | O que executa |
|---|---|---|
| `reincorporar <card>` | item com lateral `-vermelho-` | cherry-pick da lateral, `cepa-plan finish --status done`, build |
| `devolver <card>` | item `blocked` | `cepa-plan` volta o item para `pending` |
| `aterrissar` | branch da noite à frente da `main` | merge no clone, build, push |
| `descartar-lateral <card>` | lateral existente | apaga a branch lateral |

No fim do run o terminal imprime essas ações numeradas (resolve A1). O comando
`cepa-until aterrissar <run>` mostra a lista, aceita `1 sim, 2 não` e executa na ordem
(resolve A2). A análise do modelo continua existindo, mas **comenta** as ações, com a
recomendação de cada uma; não as define.

- A favor: repetível, testável, respeita R1 e R2.
- Contra: a análise às vezes acha ações que não estão na lista fechada (abrir card para teste
  instável, corrigir o `reconcile`). Essas continuam como texto, fora do comando.

### Caminho 2: skill de sessão `/common:until-land <run>`

Uma skill que lê a análise, faz as perguntas e executa conversando, como o `/board-flow:decide`.
Nenhuma mudança no `cepa-until` além de imprimir no fim `próximo passo: /common:until-land
<run>`.

- A favor: aproveita a análise inteira, inclusive as ações fora da lista; custo de construção
  baixo.
- Contra: fere R2. Cada execução depende da redação do modelo; o mesmo run pode gerar
  execuções diferentes. Exige abrir sessão de Claude para aterrissar.

### Caminho 3: aterrissar sozinho quando tudo ficou verde

Se todos os itens fecharam `done` com build verde e a `main` não andou, o supervisor mescla e
faz o push no fim do run.

- A favor: zero atrito no caso feliz.
- Contra: fere R1 e reabre a decisão 3 do dono. Descartado neste documento; fica registrado
  para o painel confirmar ou contestar.

### Caminho 4: só lembrete, sem comando novo

Notificação no fim (A7), branch `until/*` pendente na abertura da sessão e no
`/common:doctor`, resumo reescrito (A4, A6). Aterrissar continua manual.

- A favor: barato, nenhum risco.
- Contra: não resolve A2 nem A3, que foram os atritos deste run.

## Triagem do vermelho (vale para qualquer caminho, resolve A3 e A5)

Antes de marcar `blocked` por build vermelho, o supervisor:

1. lê os relatórios do surefire e extrai os testes que falharam;
2. roda de novo **só esses testes** (`-Dtest=...`), uma vez;
3. se passarem, o item fecha `done` com a marca `build-instavel` e o nome do teste; a ação
   proposta vira "abrir card para o teste instável";
4. se falharem de novo, segue como hoje: lateral e `blocked`.

O critério "o teste é de um arquivo que o card não tocou" **não** decide sozinho (R3): ele só
entra no texto da evidência, para o dono julgar.

E `desfaz_item` passa a usar o HEAD do começo da **primeira** tentativa do item, gravado no
`.jsonl`, não o da tentativa atual (A5).

Custo (R4): a reexecução de uma classe `@QuarkusTest` sobe a aplicação uma vez; é da ordem de
minutos, não dos 15 min do build inteiro. Não medido.

## Recomendação

Caminho 1 como núcleo, com a triagem do vermelho, mais o Caminho 4 como complemento. O
Caminho 2 é mais barato, mas coloca a execução na mão de um texto que muda a cada run, que é
o tipo de acoplamento que já falhou em outros gates deste repo. O Caminho 3 fica descartado
enquanto a decisão 3 do dono valer.

Sequência:

1. Triagem do vermelho + correção do `desfaz_item` (A3, A5). É o que mais gerou confusão, e é
   mudança local no supervisor.
2. Lista fechada de ações gravada pelo supervisor e impressa no fim do terminal (A1).
3. `cepa-until aterrissar <run>` executando a lista (A2).
4. Resumo por item, cabeçalho curto, caminhos relativos, custo (A4, A6).
5. Notificação e lembrete na abertura da sessão e no `/common:doctor` (A7), junto com o item
   do maestro no BACKLOG, que tem o mesmo defeito.

Fora deste documento, já no BACKLOG ou na análise do run: o `cepa-plan reconcile` que reabre
cards prontos, e o build longo que encerra a sessão esperando
(`Build longo dentro do cepa-until vira trava para o dono`).

---

# Revisão pós-painel de advisors (7 lentes, 2026-09-26)

Painel: as 5 lentes fixas (contrarian, fundamentalista, expansionista, outsider, executor)
mais `primeiro-uso` (área ux) e `operador-sre` (área arquitetura), montado à mão porque a
decisão cruza as duas áreas. Cada lente leu o documento sozinha, sem ver as outras. 69 achados
no total.

## Conferências feitas pelo autor depois do painel

**A3 conferido no disco, não só pela análise.** Três lentes (contrarian, fundamentalista,
outsider) apontaram que A3 se apoiava no texto do modelo. Conferência:

- O último commit de código do 2320 é das 14:06 (`808b6b6f`). Depois dele só entraram
  `efd455f7` (14:40) e `2e9f8700` (14:46), os dois em `docs/`.
- O build completo do próprio agente em `~/.wego-acesso/test-reports/20260926-144407` (5
  módulos) terminou com 3.161 testes e 0 falhas, e o `CadastroComTagsE2ETest` passou.
- O build do supervisor começou por volta de 14:47 (fim 15:03:59 menos 978 s do evento
  `verify` no `.jsonl`) e falhou só em `doisCadastrosSimultaneosComMesmaTagNovaCriamUmaTagSo:136`
  (`expected: <201> but was: <500>`, linha 113733 do `.log`).

Conclusão: o mesmo código passou num build e falhou no seguinte. Os números 3.176 da análise
não aparecem nesses relatórios; os que valem aqui são os acima. O título de A3 fica mais
fraco do que estava: **"o rótulo travado provavelmente está errado"**. Uma falha de
concorrência que some na execução seguinte também pode ser corrida real (ver C1).

**A2 não é caso único.** O contrarian argumentou que A2 foi visto num run só. Contagem no
`wego-acessos-backend`: 42 registros `.jsonl` de `cepa-until` desde 30/08. O formato do
registro mudou no caminho, então não dá para dizer com o que existe quantos deixaram trabalho
para aterrissar. A aterrissagem manual, porém, é passo obrigatório de todo run que entrega.

## Convergências (2 ou mais lentes, de forma independente)

**C1. A triagem não pode fechar `done` com o build completo vermelho.** Contrarian,
fundamentalista, outsider e operador-sre. Viola o green-or-revert. O teste do caso é de
concorrência, justamente o tipo em que uma segunda execução verde não separa teste instável
de corrida introduzida pelo card. E, pelo fundamentalista, cada vermelho convertido em `done`
deixa de contar para o disjuntor da decisão 2. **Revisão:** a reexecução muda o **rótulo e a
recomendação**, não o status. O item continua fora da branch da noite, com a evidência
"falhou 1 vez, passou na reexecução: provável teste instável", e a ação proposta é
`reincorporar`, com recomendação sim. Quem fecha `done` é o dono.

**C2. `reincorporar` grava `done` antes do build.** Contrarian, fundamentalista, operador-sre
e executor. **Revisão:** cherry-pick, build, e só com verde `cepa-plan finish --status done`.
Build vermelho: desfaz o cherry-pick e para.

**C3. `aterrissar` só descreve o caminho feliz e cria uma terceira receita de merge.**
Primeiro-uso, operador-sre, fundamentalista, executor e contrarian. **Revisão:** `aterrissar`
reusa os guardas do `/common:worktree-merge` (build verde, dono único, parar no conflito) em
vez de reimplementar. Regras do lote: para na primeira falha; nunca faz push com build
vermelho; grava o ponto de retorno (SHA da `main` antes do merge); rodar de novo retoma da
ação que falhou. Cada ação grava os SHAs de quando foi proposta e, na hora de executar,
recusa se o estado mudou (operador-sre).

**C4. A5 é quebra de garantia, não confusão de leitura.** Fundamentalista, outsider,
executor, operador-sre e contrarian. A garantia "o próximo card nunca começa sobre código
que não passou" falhou: os 9 commits da primeira tentativa do 2320 nunca passaram pelo build
do supervisor. Desta vez não houve dano, porque o 2320 foi o último item do run. O executor
achou a causa exata: quando a primeira tentativa termina sem progresso, `bloqueia_item` e o
caminho da nova tentativa não desfazem commit nenhum (`cepa-until:1090`, `:1291-1307`).
**Revisão:** tratar A5 como defeito de garantia, com prioridade 1. O reset só pode acontecer
depois de duas checagens: o SHA gravado é ancestral do HEAD (`git merge-base --is-ancestor`),
e nenhum outro item fechou `done` desde então. Se uma das duas falhar, o supervisor para e
avisa em vez de resetar.

**C5. A triagem supõe Maven com surefire.** Operador-sre, executor e contrarian. O `verify`
é genérico (`VERIFY_POR_ARQUIVO`, `cepa-until:193-196`). O E2E pode estar no failsafe
(`-Dit.test`). E o build pode ficar vermelho sem nenhum teste falhar: erro de compilação ou
tempo estourado. **Revisão:** sem teste reprovado identificável no relatório, a triagem não
roda e o item segue como hoje. A primeira versão só cobre Maven, e as outras ferramentas
ficam declaradas fora.

**C6. A lista de ações precisa de estado gravado, não de aviso.** Operador-sre, expansionista
e primeiro-uso. A notificação some se ninguém estiver na tela, ou se o run vier do launchd.
**Revisão:** o supervisor grava, ao lado do `.jsonl`, um estado do run: `rodando`,
`esperando-dono`, `aterrissado` ou `descartado`. O `/common:next` e o `/common:doctor` leem
esse estado. A notificação passa a ser só um extra, e o texto dela traz o comando exato.

**C7. Uma lista só.** Executor, primeiro-uso e operador-sre. As ações são gravadas e impressas
**antes** da análise do modelo, porque a análise pode falhar por cota. O `/common:until-review`
passa a ler a mesma lista e comentar cada ação pelo id, sem numeração própria. Ações que o
comando não executa ("abrir card para o teste instável") aparecem num bloco separado, "fica
com você".

**C8. Contador de testes instáveis entre runs.** Expansionista e operador-sre. Cada reexecução
grava uma linha com teste, card, run e resultado, num registro que sobrevive entre runs. A
partir da terceira falha de um mesmo teste em cards sem relação, a evidência deixa de ser "o
card não tocou esse arquivo" e passa a ser "esse teste falhou em N cards".

## Discordâncias nomeadas

**D1. Construir o `aterrissar` ou ficar no Caminho 4 com a triagem.**
O contrarian diz que, com a triagem resolvendo A3, só sobra A2 para justificar um subcomando
com estado novo, e isso com um caso só. O primeiro-uso, o operador-sre e o expansionista dizem
que o comando vale a pena, desde que venha com as proteções. **O que decide:** se A2 se repete.
A contagem acima mostra que aterrissar à mão é passo de todo run que entrega, e o dono ainda
perguntou "o que eu faço?" no run 42. **Recomendação do sintetizador:** construir, mas como
fina camada sobre o `worktree-merge` (C3), não como motor novo. Isso também reduz o custo
que o contrarian temia.

**D2. Generalizar agora ou entregar local.**
O expansionista quer três coisas genéricas desde o início: o arquivo de pendências no mesmo
formato do maestro, a reexecução de testes como executável em `common/bin`, e a mesma gramática
de resposta do `/board-flow:decide`. O executor quer separar do maestro, para o lembrete do
`until/*` não esperar outro plugin (`maestro/bin/maestro-wave-state`). O contrarian alerta
contra desenhar lista fechada em volta de poucos casos. **O que decide:** o custo marginal de
cada generalização. **Recomendação:** generalizar só o que custa uma decisão de formato, e não
código a mais. Isso inclui o formato do arquivo de estado do run, que o `next` e o `doctor`
leem, e a gramática "1 sim, 2 não". O executável comum de reexecução fica para quando um
segundo consumidor pedir, e a entrega do maestro segue separada.

**D3. Perguntar tudo ou executar o reversível.**
O fundamentalista aponta que a doutrina default-yes manda executar e registrar o reversível.
Pela lista de ações, `devolver` é reversível, e só `aterrissar` (mexe na `main`) e
`descartar-lateral` (apaga commits) exigem pergunta. O primeiro-uso quer toda ação confirmada,
com uma frase leiga de efeito e a opção "tudo como recomendado". **O que decide:** se o dono
quer ser perguntado sobre `devolver`. **Recomendação:** as duas coisas cabem juntas. Cada ação
leva a frase leiga e a entrada aceita `tudo`. As ações irreversíveis nunca entram no `tudo`
sem aparecer nomeadas na tela.

**D4. O que fazer com as branches laterais.**
O contrarian e o fundamentalista dizem que o Caminho 1 transforma em rotina justamente a
"pilha de branches esperando alguém notar" que a decisão 3 proíbe. O documento original as
tratava como normais. **O que decide:** é decisão do dono, porque reinterpreta a decisão 3.
**Recomendação:** manter a lateral, porque sem ela o código vermelho se perde. Mas ela nasce
com validade: com o estado `esperando-dono` (C6), ela aparece no `next` e no `doctor`. Depois
de 7 dias sem resposta, vira patch arquivado ao lado do `.jsonl` e a branch é apagada.

## O que muda na recomendação

O Caminho 1 continua sendo o núcleo, mas mudou de forma. O comando `aterrissar` passa a ser
uma camada fina sobre o `worktree-merge`. A triagem só troca o rótulo e a recomendação,
nunca o status. E o A5 sobe de "confusão" para "garantia quebrada". O Caminho 3 segue
descartado, e o expansionista propôs uma forma de reabri-lo com dados: registrar, por run,
quando todos os itens ficaram verdes, a `main` não andou e o dono aceitou aterrissar sem
mudar nada.

## Sequência revisada

0. **Medir antes de escrever código** (executor). Rodar só o `CadastroComTagsE2ETest` na
   worktree de 26/09 e cronometrar. O número fixa o tempo máximo da reexecução.
1. **A5 como garantia** (C4): o `desfaz_item` e o caminho de tentativa sem progresso passam a
   levar os commits de todas as tentativas do item para a lateral, com as duas checagens
   antes do reset. Teste vermelho: um item com duas tentativas, e a lateral deve conter os
   commits das duas.
2. **Estado do run e lista de ações**, gravados antes da análise e impressos no fim do
   terminal; o `until-review` lê a mesma lista (C6, C7). Vai junto com A4 (uma linha por
   item), porque os dois mexem no mesmo trecho (`cepa-until:1375-1411`).
3. **`cepa-until aterrissar <fila>/<run>`** sobre os guardas do `worktree-merge` (C2, C3),
   entregue junto com o passo 2. O primeiro-uso notou que uma lista numerada sem comando que a
   execute piora o atrito, em vez de reduzir.
4. **Triagem do vermelho** (C1, C5, C8): só Maven, e só muda rótulo e recomendação.
5. Cabeçalho curto, caminhos relativos e custo (A6). O `next` e o `doctor` leem o estado do
   run (C6).

O run de 26/09 é resolvido à mão, com as decisões da análise. Nenhum passo acima é pré-requisito
para ele.

## Perguntas ao dono

1. **A triagem só troca o rótulo e a recomendação, e quem fecha `done` depois de um vermelho é
   sempre você?** Recomendo sim: quatro lentes mostraram que uma reexecução verde de teste de
   concorrência não prova que o card é inocente.
2. **O `aterrissar` vira camada fina sobre o `/common:worktree-merge`, e não receita nova?**
   Recomendo sim: os guardas contra vermelho, conflito e dono duplicado já existem e estão
   testados.
3. **A branch lateral do vermelho ganha validade de 7 dias, depois vira patch arquivado?**
   Recomendo sim: mantém o código recuperável sem criar a pilha de branches que a decisão 3
   proíbe.
4. **O A5 entra como passo 1, antes de qualquer melhoria de tela?** Recomendo sim: é a única
   peça que quebra a garantia de que um card não começa sobre código não verificado.

---

# Revisão 2: o vermelho se resolve sem o dono (2026-09-26)

O dono respondeu às quatro perguntas da revisão pós-painel:

- **Pergunta 1** (quem fecha o card depois de um vermelho é o dono): **não**. Pedido literal: "eu
  não quero ter que fazer qualquer intervenção. Faça outra proposta que possibilite o problema
  se auto-resolver."
- **Pergunta 2** (o `aterrissar` como camada fina sobre o `/common:worktree-merge`): **sim**.
- **Pergunta 3** (validade de 7 dias para a branch lateral): **não**. Resposta: "seria mais uma
  coisa pra eu ter que me lembrar?"
- **Pergunta 4** (commitar o documento e registrar os passos no BACKLOG): **sim**.

Esta revisão substitui C1 (a triagem que só trocava o rótulo) e D4 (a branch lateral com
validade). O restante da revisão pós-painel continua valendo.

## A ideia: o supervisor repete a prova inteira e, quando não resolve, a fila ganha o conserto

A objeção do painel à triagem original era que **uma reexecução só dos testes que falharam
não é o mesmo portão** que o build completo. A saída sem dono é repetir **o mesmo portão**, e
não um portão mais fraco. Quando nem isso resolve, o trabalho de consertar vira um item da
própria fila, e o próximo run o executa.

### Passo a passo, depois de um build completo vermelho

1. **Segundo build completo, no mesmo código.** O supervisor roda de novo o mesmo `verify`
   (`./mvnw -B clean verify`), sem trocar nada.
2. **Se o segundo ficar verde:** o item fecha `done`. A regra green-or-revert, que proíbe
   `done` sem build verde, é cumprida ao pé da letra, porque existe um build completo verde
   daquele código exato. O supervisor registra a instabilidade (item 4 abaixo).
3. **Se o segundo ficar vermelho no mesmo teste:** o supervisor trata como vermelho de
   verdade e segue três passos.
   - Leva os commits de **todas** as tentativas do item para a branch lateral, com as checagens
     de C4 (o SHA gravado é ancestral do HEAD e nenhum outro item fechou `done` no meio).
   - Acrescenta à fila, na frente, um item de conserto:
     `cepa-plan add WEGO FIX-<teste> --title "Consertar <teste>, vermelho depois do <card>"
     --antes-de <próximo> --why "<evidência>"`.
   - Devolve o item original para `pending` com `blocked-by FIX-<teste>`, que marca o item de
     conserto como pré-requisito dele, e com um campo apontando para a branch lateral.
4. **Registro de instabilidade.** Cada build que ficou vermelho e depois verde grava uma linha
   com teste, card, run e data num arquivo que sobrevive entre runs. Quando um teste aparece
   pela **segunda vez** em cards diferentes, o supervisor acrescenta à fila um item
   `FIX-<teste>` ("estabilizar <teste>"), que o próximo run executa como qualquer outro.
5. **Disjuntor.** Um vermelho seguido de verde não conta como falha. Dois vermelhos seguidos no
   mesmo item contam como uma falha, como hoje.

### A branch lateral some sozinha (resposta à pergunta 3)

Nada fica para o dono lembrar:

- Quando o item original volta a ser executado, porque o `FIX-<teste>` fechou, o supervisor faz
  o cherry-pick da branch lateral **antes** de chamar o agente. O trabalho do run anterior é
  aproveitado, e não refeito.
- Quando o item fecha `done` ou `dropped`, o supervisor apaga a branch lateral.
- No começo de cada run, o supervisor apaga as laterais cujo item já está em estado final na
  fila. Isso cobre o caso em que alguém resolveu à mão.

### O que o dono vê

No caso do 2320, nada: o segundo build provavelmente ficaria verde, o card fecharia `done` e o
registro guardaria a primeira ocorrência do `doisCadastrosSimultaneos...`. Se o teste falhar
de novo em outro card, a fila ganha o conserto dele sozinha.

### Custo

Um segundo build completo custa o mesmo que o primeiro, 978 s neste run (dado do evento
`verify` do WEGO-2320 no `.jsonl`), e só acontece quando o primeiro fica vermelho. Frequência
medida: 3 dos 42 registros de run do `wego-acessos-backend` têm um evento `verify_vermelho`
(`grep -l`). A reserva de tempo passa a considerar esses ~16 min: o supervisor só começa um
item se couberem o item e **dois** builds.

### Risco que sobra, dito sem enfeite

Uma corrida de verdade, introduzida pelo card, pode passar no segundo build e o card fechar
`done`. O risco era o mesmo antes: um build verde único também não pega uma corrida que
aparece 1 vez em 16. O registro de instabilidade é a rede. Na segunda aparição do teste,
o item `FIX-<teste>` investiga esse teste já com o código do card na base, e é ali que uma
corrida introduzida aparece.

### Pendente

Esta revisão **não** passou por um novo painel de advisors. O painel anterior revisou a
triagem com reexecução isolada. A mudança central daqui (repetir o build inteiro e colocar o
conserto na fila) responde à objeção principal dele, mas as lentes não a viram.
