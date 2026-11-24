# Especificação: filas fechadas saem da vista

**Status:** ready-to-build
**Aberta em:** 2026-11-24            **Fechada em:** 2026-11-24
**Fontes lidas:** .claude/queues/*/queue.yaml, common/bin/cepa-plan (`queue_closed`, `single_track_queues`, `status`, `ready`, `epics`, `decisions`), common/bin/cepa-until (`all_queue_names`, `every_queue_file`), common/hooks/_queuepath.py (`queue_files`), common/commands/queue-status.md, common/commands/wrap-up.md, docs/spec/decisoes-de-todas-as-filas.md, BACKLOG.md

## Como chegamos aqui
"Como tratar o acúmulos de filas vazias para que não virem um grande cemitério de tarefas concluídas?" (dono, 2026-11-24)

## Problema
Toda especificação vira uma fila em `.claude/queues/<nome>/`, e a fila continua lá depois que o último item fecha. Em 2026-11-23 o repo tinha 26 filas com `queue.yaml` e 21 delas só tinham itens `done` ou `dropped` (contagem: `grep status:` em cada `queue.yaml` do commit 6eade96). `cepa-plan status` sem nome responde "há mais de uma fila; diga qual:" seguido de todos os nomes, e `cepa-plan ready` imprime uma linha "fila fechada: tudo concluído ou descartado" por fila. As 5 filas com trabalho aberto ficam no meio das fechadas. O mesmo acontece em `docs/spec/`, que guarda a especificação de cada fila já construída.

## Escopo
### Entra
- Comando novo `cepa-plan archive [--dry-run] [--repo DIR]`: varre as filas `single-track` e move para `.claude/queues/_archive/<nome>/` cada fila que está fechada e parada há 7 dias ou mais. A pasta vai inteira (o `queue.yaml` e a subpasta `until/` com os registros dos runs).
- Fila fechada: tem pelo menos um item, todo item está `done` ou `dropped`, e nada nela espera o dono pela regra que o `cepa-plan waiting` já usa (rota humana aberta, item `blocked`, tarefa que sobrou em item `done`, run por pousar).
- Parada há 7 dias: a data do último commit que tocou `.claude/queues/<nome>/` é igual ou anterior a hoje menos 7 dias.
- A especificação de origem vai junto: quando o `source:` da fila aponta para `docs/spec/<slug>.md`, o arquivo é movido para `docs/spec/_archive/<slug>.md` e o `source:` da fila arquivada passa a apontar para o lugar novo. A varredura imprime quantas decisões sem veredito foram junto e em que arquivo.
- `cepa-until land` e `/common:wrap-up` chamam a varredura sozinhos, e o que ela moveu entra no commit deles.
- `cepa-plan status` sem nome e `cepa-plan ready` mostram primeiro as filas com trabalho aberto e depois uma única linha "fechadas, aguardando arquivo: a, b, c". Fila arquivada não aparece.
- Comando de leitura com o nome de uma fila arquivada (`cepa-plan status <nome>`) mostra a fila e avisa "arquivada em <data>".
- Comando de escrita com o nome de uma fila arquivada (`cepa-plan add`, `cepa-plan write`) traz a pasta e a especificação de volta para o lugar original antes de gravar, e avisa que restaurou.
- `cepa-plan epics` continua dizendo que o ciclo fechou quando a fila `<nome>-c<N>` do ciclo está no arquivo.
### Não entra
- Itens fechados dentro de fila ainda aberta (caso da fila `cepa`, 140 de 147 itens em 2026-11-23): o dono deixou fora em 2026-11-24.
- Apagar fila ou especificação: o histórico continua legível no disco.
- Mover Epic (`docs/epics/`), `BACKLOG.md` ou documento de estratégia que seja o `source:` de uma fila: servem a mais de uma fila.
- Corrigir outros textos que citam o caminho antigo da especificação (outras especificações, Epics, `evidence` de itens): só o `source:` da própria fila é reescrito.
- Filas `parallel-waves` do Maestro e o layout antigo `.claude/programs/`: a varredura não toca.
- A pasta `.claude/queues/_all/` (registros dos runs de todas as filas): não é fila e fica onde está.
- Prazo configurável: 7 dias é constante no código.

## Estado e migração
Nenhum formato de arquivo muda. A primeira varredura move de uma vez todas as filas que já cumprem a regra, com as especificações de origem. Pelo retrato de 2026-11-23 são cerca de 13 das 21 filas fechadas (as que tinham último commit até 2026-11-17: `git log -1 --format=%cs -- .claude/queues/<nome>/`); as outras 8 aparecem na linha "fechadas, aguardando arquivo" até completarem 7 dias. As pastas `_archive` nascem na primeira movimentação. `queue_files` procura `*/queue.yaml` em um nível só, então quem lista filas por ele deixa de ver as arquivadas sem mudança de código.

## Critérios de sucesso

### CS-1: a varredura move a fila fechada e parada há 7 dias, e só ela
**Surface:** cli
**Red test:** num repo de fixture com a fila `velha` (todo item `done`, último commit há 8 dias, com `until/r1.jsonl`), a fila `recente` (todo item `done`, último commit há 6 dias) e a fila `aberta` (um item `pending`), `cepa-plan archive` sai com código 0; depois existem `.claude/queues/_archive/velha/queue.yaml` e `.claude/queues/_archive/velha/until/r1.jsonl`, não existe `.claude/queues/velha/`, e `recente` e `aberta` continuam no lugar. Com `--dry-run` a saída nomeia `velha` e nada é movido. Hoje o subcomando `archive` não existe.

### CS-2: fila com algo esperando o dono não é arquivada
**Surface:** cli
**Red test:** num repo de fixture, quatro filas com todo item `done` ou `dropped` e último commit há 8 dias: uma com tarefa que sobrou num item `done`, uma com rota humana aberta, uma com run por pousar e uma com `items: []`. `cepa-plan archive` não move nenhuma e a saída diz, por fila, o motivo. Hoje o subcomando não existe.

### CS-3: a especificação de origem vai junto, e o que foi junto é avisado
**Surface:** cli
**Red test:** na fixture do CS-1, `velha` tem `source: docs/spec/velha.md`, e esse arquivo tem duas linhas em "Decided without asking" sem veredito. Depois de `cepa-plan archive`: existe `docs/spec/_archive/velha.md`, não existe `docs/spec/velha.md`, o `source:` de `.claude/queues/_archive/velha/queue.yaml` começa com `docs/spec/_archive/velha.md`, e a saída contém "2 decisões sem veredito foram junto em docs/spec/_archive/velha.md". Uma segunda fila fechada com `source: docs/epics/x.md, ciclo 1` é movida e `docs/epics/x.md` continua no lugar. Hoje nada disso existe.

### CS-4: as listas separam abertas, fechadas em espera e arquivadas
**Surface:** cli
**Red test:** com as filas `aberta-1` e `aberta-2` (itens `pending`), `recente` (fechada há 6 dias) e `velha` (já em `_archive`), `cepa-plan status` sem nome lista `aberta-1` e `aberta-2`, depois uma linha "fechadas, aguardando arquivo: recente", e não cita `velha`. `cepa-plan ready` imprime os blocos de `aberta-1` e `aberta-2`, a mesma linha única para `recente` e nenhum bloco "fila fechada: tudo concluído ou descartado". Hoje `status` lista os nomes misturados e `ready` imprime um bloco por fila fechada.

### CS-5: nomear uma fila arquivada num comando de leitura mostra a fila
**Surface:** cli
**Red test:** com `velha` em `_archive`, `cepa-plan status velha` sai com código 0, lista os itens dela e contém "arquivada em" seguido da data do commit que a moveu. Hoje a resposta é "`.claude/queues/velha/queue.yaml` não existe".

### CS-6: gravar numa fila arquivada restaura a fila e a especificação
**Surface:** cli
**Red test:** com `velha` em `_archive` e `docs/spec/_archive/velha.md`, `cepa-plan add velha N-1 --title "novo"` sai com código 0; depois existem `.claude/queues/velha/queue.yaml` (com os itens antigos, o item `N-1` e `source:` começando com `docs/spec/velha.md`), `.claude/queues/velha/until/r1.jsonl` e `docs/spec/velha.md`; não existe `.claude/queues/_archive/velha/`; a saída contém "restaurada do arquivo". Hoje o `add` responde que a fila não existe.

### CS-7: o pouso de um run arquiva e commita o que a varredura moveu
**Surface:** cli
**Red test:** num repo de fixture com um run pronto para pousar na fila `aberta` e a fila `velha` fechada há 8 dias, `cepa-until land aberta/<run> --yes` termina com `velha` em `_archive`, `git status --porcelain` vazio, a movimentação presente num commit do branch de destino, e a saída contém "archived: velha". Hoje `velha` continua em `.claude/queues/velha/`.

### CS-8: o wrap-up chama a varredura antes do commit da sessão
**Surface:** cli
**Red test:** um teste sobre `common/commands/wrap-up.md` (como `tests/test_wrapup_next_step.py` faz) acha, antes do passo que commita a worktree da sessão, um passo que roda `cepa-plan archive` e manda incluir o que foi movido no commit e listar no relatório final. Hoje o arquivo não cita `cepa-plan archive`.

### CS-9: o Epic continua vendo o ciclo fechado depois que a fila do ciclo é arquivada
**Surface:** cli
**Red test:** com `docs/epics/x.md` de dois ciclos e a fila `x-c1` fechada dentro de `_archive`, `cepa-plan epics` mostra o ciclo 1 como fechado com a contagem de itens. Hoje, sem `.claude/queues/x-c1/`, o ciclo 1 aparece como sem fila.

## Perguntas em aberto
- [x] Q1. O que é o cemitério: os nomes que os comandos listam, as pastas no disco, ou os dois? — As listas (dono, 2026-11-24).
- [x] Q2. O que acontece com a pasta da fila fechada: fica onde está, vai para uma pasta de arquivo, ou é apagada? — Vai para uma pasta de arquivo (dono, 2026-11-24).
- [x] Q3. A fila conta como fechada sozinha (todo item `done`/`dropped`) ou só por um comando do dono? — Sozinha: todo item `done` ou `dropped`, sem pergunta pendente para o dono e sem run por pousar (dono, 2026-11-24).
- [x] Q4. Os 140 itens fechados dentro da fila `cepa`, que continua aberta, entram nesta especificação? — Não, fica fora (dono, 2026-11-24).
- [x] Q5. Quem move a pasta da fila fechada para o arquivo, e em que momento? — Um comando que varre todas as filas fechadas, chamado sozinho pelo `cepa-until land` e pelo `/common:wrap-up`; o commit entra junto com o deles (dono, 2026-11-24).
- [x] Q6. A fila vai para o arquivo assim que fecha ou depois de um tempo parada? — Depois de 7 dias parada (dono, 2026-11-24).
- [x] Q7. O que acontece quando alguém nomeia uma fila arquivada (consultar, ou gravar item novo nela)? — Comando de leitura acha a fila no arquivo e avisa "arquivada em <data>"; gravar item novo traz a pasta de volta com o histórico e avisa que restaurou (dono, 2026-11-24).
- [x] Q8. Como a fila fechada aparece nas listas durante os 7 dias de espera? — Separada: primeiro as filas com trabalho aberto, depois uma única linha "fechadas, aguardando arquivo: a, b, c" (dono, 2026-11-24).
- [x] Q9. As especificações em `docs/spec/` cuja fila foi arquivada entram nesta especificação? — Sim: a especificação de origem vai para o arquivo junto com a fila (dono, 2026-11-24).
- [x] Q10. A especificação de origem que ainda tem decisão sem veredito em "Decided without asking" vai para o arquivo junto com a fila? — Vai, e a varredura avisa quantas decisões sem veredito foram junto e em que arquivo (dono, 2026-11-24).

## Decided without asking
- O arquivo das filas é `.claude/queues/_archive/<nome>/` e o das especificações é `docs/spec/_archive/<slug>.md` — o prefixo `_` já marca em `.claude/queues/_all/` uma pasta que não é fila. Vete aqui se discordar.
- "Parada há 7 dias" se mede pela data do último commit que tocou a pasta da fila, não pela data em que o último item fechou — o commit é o que o git guarda sem campo novo no `queue.yaml`. Vete aqui se discordar.
- Rodado à mão, `cepa-plan archive` faz o próprio commit, só com o que moveu; chamado pelo `land` e pelo wrap-up, deixa o commit para eles. Vete aqui se discordar.
- Com as fechadas fora da conta, `cepa-plan status` sem nome abre direto a fila quando só uma tem trabalho aberto, em vez de pedir o nome — é a regra "uma fila só, usa ela" aplicada às abertas. Vete aqui se discordar.
- Uma especificação só é movida quando toda fila que a cita em `source:` está arquivada. Vete aqui se discordar.
- Se já existe uma pasta com o mesmo nome no arquivo, a varredura não move essa fila, diz isso na saída e segue com as outras. Vete aqui se discordar.
- `cepa until decide --all` e os runs de todas as filas deixam de ver fila arquivada sem código novo, porque listam por `queue_files`; fila arquivada não tem nada esperando o dono, por definição. Vete aqui se discordar.
- `/common:spec --lista` e `--continuar` não mudam: leem `docs/spec/*.md` e por isso não veem especificação arquivada. Vete aqui se discordar.
- Não há comando `unarchive` separado: a volta acontece quando um comando de escrita nomeia a fila (Q7). Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- 13 das 20 especificações de `docs/spec/` têm decisão sem veredito (contagem: última linha de `cepa-plan decisions <arquivo>` em cada uma, 2026-11-24). Depois de arquivadas, só o aviso da varredura lembra o dono delas.
- `/common:spec` não acha especificação arquivada ao conferir se o assunto já existe, então pode nascer uma segunda especificação do mesmo assunto.
- Textos que citam `docs/spec/<slug>.md` fora do `source:` da fila ficam com o caminho antigo.
- O BACKLOG propõe casar branch lateral com a fila pela existência de `.claude/queues/<fila>/until/<run>.jsonl`. Quem construir aquilo precisa olhar também em `_archive`.
- O wrap-up roda a varredura na worktree da sessão. Se outra sessão restaurar a mesma fila na `main` no intervalo, o merge dá conflito de pasta movida, que aparece como conflito normal do git.
- A fila `cepa` continua com 140 itens fechados dentro dela.
