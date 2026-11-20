# Especificação: listar e decidir o que espera o dono em todas as filas

**Status:** ready-to-build
**Aberta em:** 2026-11-20            **Fechada em:** 2026-11-20
**Fontes lidas:** common/bin/cepa-plan (cmd_ready, ready_of_queue, cmd_answer, status de uma fila), common/bin/cepa-until (cmd_decide, ask_at_launch_all, OWNER_REASON, pending), docs/spec/until-todas-as-filas.md

## Como chegamos aqui
"Assim como existe o comando `cepa plan ready` que lista os itens prontos para serem construídos de todas as listas, crie algum outro comando para listar todas as pendências que esperam resposta minha decisão. Aproveite e crie também o comando para realizar o processo de decisão de todos os itens de uma só vez." (dono, 2026-11-20, depois de ver a fila pyyaml aparecer como "fila fechada" no `cepa plan ready` com duas perguntas escondidas em CS-4 e CS-6, feedback fb-20261120-1)

## Problema
Não existe uma tela que mostre tudo o que espera o dono no repo. `cepa plan ready` só cita as perguntas de itens parados e chama de "fila fechada" uma fila cujos itens concluídos ainda deixaram tarefa para o dono. Para responder, o dono roda `cepa-until decide <fila>` fila por fila, e precisa adivinhar quais filas têm pergunta.

## Escopo
### Entra
- `cepa plan waiting [--repo DIR] [--json]`: só leitura, todas as filas `single-track` na ordem do `cepa plan ready`. Por fila, os itens que esperam o dono: rota humana aberta em item não concluído, item `blocked` e tarefa que sobrou em item `done`. Cada linha traz id, motivo e a pergunta cortada numa linha.
- Na mesma saída, uma seção à parte com os runs que esperam o dono (os mesmos que `cepa until pending` lista), cada um com o comando que o resolve.
- Rotas que o dono já respondeu "não" aparecem contadas por fila, com a data da última e o comando para revisitar, e não como linhas.
- `cepa until decide --all`, e `cepa until decide` sem argumento com o mesmo efeito: um painel único, numerado entre filas, com as perguntas de item de todas as filas, gravando cada resposta na fila do item e commitando no fim.
- `cepa plan ready` deixa de dizer "tudo concluído ou descartado" quando um item `done` da fila ainda tem tarefa para o dono.
### Não entra
- Aterrissar run ou consertar build vermelho dentro do `decide --all` (Q2: `land` tem fluxo próprio e build vermelho pede conserto, não resposta).
- Mudar o comportamento de `cepa until decide <fila>` e `cepa until decide <fila>/<run>` (continuam iguais).
- Filas `parallel-waves` do Maestro (não são `single-track`, o `ready` já as ignora).
- Mudar o formato do `queue.yaml` ou o texto das perguntas gravadas.

## Estado e migração
Nenhum dado existente muda. As filas e os registros de run ficam como estão. Muda a saída de `cepa plan ready` para a fila fechada com tarefa sobrando (texto e um campo novo no `--json`), e `cepa until decide` passa a aceitar o alvo vazio e `--all`. As respostas da decisão em lote são gravadas nos `queue.yaml` das filas exatamente como o `decide <fila>` grava hoje.

## Critérios de sucesso

### CS-1: `cepa plan waiting` lista, agrupados por fila, os itens que esperam o dono em todas as filas, cada um com id, motivo e pergunta
**Surface:** cli
**Red test:** num repo de teste com a fila `a` (item `a1` `blocked` com `owner_question` "Rodo X à mão?") e a fila `b` (item `b1` `done` com `human_pending` "Rotacionar o segredo"), `cepa plan waiting` sai com 0 e a saída traz a seção `a` antes de `b`, com `a1`, o motivo "item travado" e "Rodo X à mão?", e `b1`, o motivo "tarefa que sobrou em item concluído" e "Rotacionar o segredo"; hoje sai com 2 porque o subcomando `waiting` não existe.

### CS-2: `cepa plan waiting` mostra, numa seção à parte, os runs que esperam o dono, cada um com o comando que o resolve
**Surface:** cli
**Red test:** com um registro de run da fila `a` esperando aterrissar (o mesmo que faz `cepa until pending` listar `a/<run>`), `cepa plan waiting` imprime uma seção de runs com `a/<run>` e `cepa-until land a/<run>`; hoje o subcomando não existe.

### CS-3: Rotas já respondidas "não" aparecem só contadas por fila, com a data e o comando para revisitar
**Surface:** cli
**Red test:** com o item `a1` cuja evidência traz uma resposta "não" do dono em 2026-11-18, `cepa plan waiting` não lista `a1` como linha e imprime "1 que você já respondeu \"não\" (última em 18/11)" junto com `cepa until decide a`; hoje o subcomando não existe.

### CS-4: Sem nada esperando, `cepa plan waiting` diz isso em uma linha e sai com 0; sem nenhuma fila, sai com 2
**Surface:** cli
**Red test:** num repo com uma fila só de itens `done` sem rota e nenhum run pendente, `cepa plan waiting` imprime "nada espera você" e sai com 0; num repo sem `.claude/queues/`, sai com 2; hoje sai com 2 nos dois casos porque o subcomando não existe.

### CS-5: `cepa plan waiting --json` devolve filas, itens, runs e totais em JSON válido
**Surface:** cli
**Red test:** no repo do CS-1, `cepa plan waiting --json` sai com 0 e o JSON tem `filas[0].itens[0].id == "a1"`, `total_itens == 2` e a chave `runs`; hoje o subcomando não existe.

### CS-6: `cepa plan ready` avisa quando uma fila fechada tem tarefa sobrando em item concluído
**Surface:** cli
**Red test:** com a fila `p` cujos itens estão todos `done`, dois deles com `human_pending` aberto, `cepa plan ready` imprime "fila fechada, 2 tarefas esperam você (cepa until decide p)" e não imprime "tudo concluído ou descartado" para `p`; hoje imprime "fila fechada: tudo concluído ou descartado".

### CS-7: Num terminal, `cepa until decide --all` faz as perguntas de todas as filas num painel único e grava cada resposta na fila do item
**Surface:** cli
**Red test:** com a fila `a` tendo `a1` com rota aberta e a fila `b` tendo `b1` com rota aberta, `cepa until decide --all` num pseudo-terminal mostra um painel com as seções `a` e `b` numeradas 1 e 2; respondendo `y` às duas, `a1` e `b1` ficam com `human_pending: null` nos respectivos `queue.yaml` e o último commit toca os dois arquivos; hoje o comando sai com 2 recusando a fila `'--all'`.

### CS-8: `cepa until decide` sem argumento faz o mesmo que `--all`
**Surface:** cli
**Red test:** no repo do CS-7, `cepa until decide` num pseudo-terminal mostra o mesmo painel com as seções `a` e `b`; hoje sai com 2 por falta do argumento obrigatório.

### CS-9: Na decisão em lote, rotas já respondidas "não" não são perguntadas e uma fila com run vivo fica fora com aviso
**Surface:** cli
**Red test:** com `a1` já respondido "não" em 2026-11-18, a fila `c` com um run vivo (`*.estado.json` `rodando`, pid vivo) e `b1` com rota aberta, `cepa until decide --all` num pseudo-terminal pergunta só `b1`, imprime a linha das negadas de `a` com `cepa until decide a` e uma linha nomeando a fila `c` e o run dela; hoje o comando é recusado.

### CS-10: Fora de um terminal, `cepa until decide --all` imprime as perguntas pendentes de todas as filas como texto e não commita nada
**Surface:** cli
**Red test:** no repo do CS-7 com stdin que não é TTY, `cepa until decide --all` sai com 0, imprime as perguntas de `a1` e `b1` e o `git log` não ganha commit; hoje o comando é recusado.

### CS-11: Sem nada esperando, `cepa until decide --all` diz isso em uma linha e sai com 0
**Surface:** cli
**Red test:** num repo cujas filas não têm rota aberta, `cepa until decide --all` imprime "nada espera você" e sai com 0 sem commitar; hoje o comando é recusado.

## Perguntas em aberto
- [x] Q1. Onde moram os dois comandos? — Lista em `cepa plan waiting`, irmão do `ready`, só leitura. Decisão em `cepa until decide --all`.
- [x] Q2. O que conta como "espera o dono": só perguntas de item, ou também runs esperando aterrissagem e build vermelho? — A lista mostra os dois, runs numa seção à parte com o comando de cada um. A decisão em lote pergunta só os itens.
- [x] Q3. `cepa plan ready` para de dizer "fila fechada" quando há tarefa sobrando em item concluído? — Sim, corrige junto (fecha fb-20261120-1).
- [x] Q4. Rota que o dono já respondeu "não" antes volta a ser perguntada na decisão em lote? — Não volta. Aparece contada por fila, com a data e o comando para revisitar.
- [x] Q5. O que cada linha de `cepa plan waiting` mostra para um item? — Id, motivo e a pergunta cortada numa linha.
- [x] Q6. `cepa until decide` sem argumento passa a significar todas as filas? — Sim, sem argumento = todas, e `--all` é sinônimo.

## Decided without asking
- A decisão em lote grava cada resposta na fila do próprio item, pelo mesmo caminho do `cepa-until decide <fila>` (`cepa plan answer`), e commita no fim como ele já faz. Dois caminhos de gravação divergiriam. Vete aqui se discordar.
- A decisão em lote reaproveita o painel único numerado entre filas que `ask_at_launch_all` já monta na largada do `cepa until --all`, sem tempo limite de espera (quem chama está no terminal de propósito). Vete aqui se discordar.
- Fila com run vivo fica fora da decisão em lote com uma linha de aviso, como na largada do `--all`: o run dela já fez as perguntas. Vete aqui se discordar.
- Os motivos de cada linha usam os três motivos que o `cepa-until` já tem para o dono (item travado, tarefa só sua, tarefa que sobrou em item concluído), traduzidos. Um vocabulário só entre `waiting` e `decide`. Vete aqui se discordar.
- A seção de runs do `waiting` lê a mesma fonte do `cepa until pending`, sem regra própria. Duas regras para "run esperando" divergiriam. Vete aqui se discordar.
- Os códigos de saída do `waiting` copiam os do `ready`: 0 mostrado (inclusive com zero), 2 sem nenhuma fila. Fila ilegível vira aviso e fica fora. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- A pergunta cortada numa linha pode perder a parte que importa em rotas antigas, escritas antes do campo `owner_question`. O texto completo continua no `decide`.
- O `waiting` passa a depender do formato dos registros de run do `cepa-until` para a seção de runs. Se o `pending` mudar, os dois mudam juntos porque leem a mesma fonte.
