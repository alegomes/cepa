# Durabilidade no Cepa: o que o Pi Durable ensina e o que já temos

**Status:** estratégia em exploração, revisão 2 (revisão 1 de 2026-11-05 passou pelo painel de advisors no mesmo dia; registro em `docs/reviews/2026-11-05-painel-durabilidade.md`; as cinco discordâncias nomeadas esperam decisão do dono na seção 9) · **Data:** 2026-11-05 · **Modo da sessão:** exploração
**Fontes:** o post "Pi Durable" de 2026-10-01 (https://earendil.com/posts/pi-durable/); `common/bin/cepa-until` (4.234 linhas em 2026-11-05) e `common/bin/cepa-plan` (4.313 linhas); `docs/cepa-until.md`, `docs/handoff.md`, `docs/autonomous-mode.md`, `docs/maestro.md`, `docs/harness-ops.md`; `docs/estrategia-fim-do-cepa-until.md` (revisão pós-painel de 2026-09-26) e `docs/estrategia-cepa-proximo-nivel.md` (decisões 1 a 10 do dono em 2026-10-08); `docs/epics/cepa-em-espiral.md`; e os registros `.jsonl` de runs do `cepa-until` nesta máquina (contagem na seção 2).

## 0. Contexto, para quem não estava nas sessões

O **Cepa** é um conjunto de plugins do Claude Code (hooks, comandos e skills em Python e Markdown) que o dono usa para conduzir trabalho de software com agentes. Uma **fila** é um arquivo YAML (`.claude/queues/<nome>/queue.yaml`) com itens de trabalho em ordem, escrito só pelo comando `cepa-plan`. Um **item** é uma unidade de trabalho da fila, em geral um card de Jira ou uma demanda ditada. O **`cepa-until`** é o supervisor que executa a fila por uma janela de tempo (uma noite, por exemplo) sem ninguém acordado: para cada item lança um processo `claude -p` (o Claude Code em modo não interativo), espera, roda o build completo, e passa ao próximo. A **folga** é o tempo que um item já em andamento pode passar do fim da janela antes de ser morto. O **handoff** é um arquivo por branch que guarda o estado de uma sessão interativa para a próxima retomar. O **condutor** é a peça ainda não construída, decidida em 2026-10-08, que vai encadear descoberta, construção, prova e aterrissagem de um ciclo de um Epic sem o dono na frente; é o ciclo 2 do Epic `cepa-em-espiral`.

Este documento existe porque o condutor vai herdar toda lacuna de durabilidade do `cepa-until`, e o post do Pi Durable dá um vocabulário preciso para listar essas lacunas antes de ele nascer.

## 1. O que é "agente durável", na definição do post

O Pi Durable é um framework experimental da Earendil, lançado junto com o Pi 1.0, para agentes de longa duração. A definição cabe em uma frase: **uma conversa de agente é durável quando sobrevive a queda, reinício e redeploy do processo, pode correr por muito tempo e pode ser conduzida por mais de uma pessoa ao mesmo tempo.** O contraste explícito do post é com o agente de terminal conduzido por uma pessoa, em que processo morto significa "peça ao agente para continuar".

Os mecanismos concretos, cada um com nome próprio no post:

| Mecanismo | O que faz no Pi Durable |
|---|---|
| **Storage único** | Um backend (memória, SQLite ou JSONL) com suíte de conformidade. Só o conjunto de trabalho fica em memória; tudo o mais vai para o disco. |
| **Checkpoint por passo** | Cada passo de um run é uma *task* que grava checkpoint antes de seguir. |
| **Recuperação de queda** | Um processo novo abre o mesmo storage, encontra as tasks não terminadas e continua cada uma do último checkpoint. Um pedido ao modelo interrompido é reenviado, e a resposta parcial fica na transcrição marcada como abortada. |
| **Replay declarado** | Cada ferramenta declara `replay: "safe"` se pode rodar de novo. Senão, o modelo é avisado de que a chamada foi interrompida, com a saída até ali. |
| **Idempotência** | Um `requestId` torna uma submissão exatamente-uma-vez; chaves de idempotência em efeitos externos (pagamento); decisões de hooks ficam em "memos", onde a primeira escrita vence. |
| **Transcrição e documentos no mesmo commit** | O estado da aplicação vive em documentos tipados gravados no mesmo commit atômico da transcrição. Nunca um sem o outro. |
| **Fork** | Uma conversa bifurca em qualquer ponto da transcrição e vê a história do pai sem copiá-la. |
| **Compactação em segundo plano** | Resumo das mensagens antigas roda como task de fundo; as mensagens antigas continuam no storage. |
| **Subagente durável** | Um subagente é uma conversa pertencente a uma chamada de ferramenta, e sobrevive à queda como qualquer conversa. |
| **Extensões por nome** | A conversa guarda só o nome das extensões e ferramentas, e por isso pega o código novo depois do reinício. Reinstalar sob o mesmo nome troca a quente. |
| **Árvore de posse** | Tasks e conversas formam uma árvore; abortar o pai aborta o que ele possui, de baixo para cima. Tasks de fundo são isentas. |
| **Multijogador** | Qualquer cliente se conecta a qualquer conversa, recebe a vista atual e depois só as mudanças, e pode conduzir ou enfileirar um pedido. |

Os princípios por trás: interfaces pequenas, base de código legível por um agente (cerca de 15 mil linhas sem testes), storage e ambiente de execução como interfaces trocáveis. Os custos declarados: API experimental, TypeScript, código-fonte de 150 a 250 mil tokens, ferramentas inseguras não são repetidas (o modelo decide), e tasks de fundo são peças a mais para gerir.

## 2. O que o Cepa já tem, mecanismo a mecanismo

O Cepa não tem uma peça chamada "durabilidade", mas resolveu o problema da queda por um caminho diferente do Pi: **em vez de tornar a conversa durável, tornou a conversa descartável e pôs o estado no disco.** A frase de desenho do `cepa-until` é "um item por subprocesso": cada item roda num `claude -p` novo, e estourar o contexto deixa de ser falha e vira o fim normal do subprocesso. Dos doze mecanismos do post, sete estão cobertos por esse desenho ou não se aplicam (recuperação de queda, idempotência da reserva, fork, compactação, subagente, árvore de posse, multijogador), e cinco têm lacuna (storage único, checkpoint por passo, resposta parcial, replay declarado, transcrição e estado no mesmo commit, extensões por nome). A tabela abaixo cruza um a um.

| Mecanismo do Pi | O que o Cepa tem hoje | O que falta |
|---|---|---|
| Storage único | **Cinco** depósitos de estado, cada um com dono e regra de vida própria: a fila (`queue.yaml`, escrita só pelo `cepa-plan`), o registro do run (`<run>.jsonl` mais `<run>.estado.json`, do `cepa-until`), o handoff por branch (`.claude/handoffs/<branch>.md`, do hook de Stop), o registro de sessões vivas (`.claude/sessions/<chave>.json`, com pid e host) e o estado do run autônomo (`docs/autonomous/<run>/state.yaml`). Mais o `wave-state.yaml` do Maestro, orquestrador de ondas paralelas congelado em 2026-10-08. | Um leitor comum. Hoje `next`, `doctor`, `until-review` e `whereami` leem subconjuntos diferentes. E nenhum depósito diz se o run está **vivo agora**: `estado.json: rodando` só diz que estava vivo quando gravou. |
| Checkpoint por passo | Três granularidades, nenhuma contínua: por **item** (`cepa-plan start` e `finish`), por **turno** (o hook `session-checkpoint.py` reescreve o esqueleto do handoff a cada Stop) e por **chamada de subagente** (`autonomous-checkpoint.py`, só em run autônomo). | Checkpoint **dentro** do item que diga em que passo o agente estava. O handoff grava fatos (commits, diretórios, intenções), não a posição. |
| Recuperação de queda | A melhor peça do Cepa. A reserva do item é **assinada** (sessão, pid, host). Se o pid morreu, a reserva fica **órfã** e o próximo `start` a reclama. A worktree do item fica no disco com o que foi feito, e os commits de uma branch de noite anterior entram na nova por herança. É o que fechou o WEGO-2293, cortado aos 30 min em 2026-09-18 e fechado no run seguinte em 1h05. | Dois buracos conferidos no código: a reserva de um pid em **outro host** só expira por idade (24 h; `cepa-plan:319-321`), então um run morto num laptop fechado prende o item uma noite inteira sem evento; e o `finish` não compara `claimed_by` com quem está fechando nem exige `in_progress`, então dois processos sobre o mesmo item fecham os dois e o segundo apaga a evidência do primeiro. A **conversa** não é retomada (o único comando de lançamento, `cepa-until:750`, não passa `--resume`), mas a seção 2.1 mostra que isso dói menos do que a revisão 1 afirmava. |
| Resposta parcial marcada como abortada | Nada. A transcrição do `claude -p` morto existe em `~/.claude/projects/<projeto>/<sessão>.jsonl`, mas nenhum consumidor do Cepa a lê. O `cepa-until` extrai o `session_id` do stream-json para deduplicar custo (`round_costs`, linha 804) e o descarta. | Gravar o id por tentativa. O `claude` aceita `--session-id <uuid>`: o supervisor pode gerar o id **antes** de lançar e gravá-lo no `item_start`, e aí nenhuma queda, por mais precoce, deixa o registro sem ele. |
| Replay declarado | Implícito. O git é a chave de idempotência das edições de código: rodar de novo sobre uma worktree meio feita é seguro porque o estado está nos arquivos. Para efeitos externos (transição de Jira, comentário, push) não há declaração: os hooks `jira-write-lock` e `_jiramut` decidem **se** uma mutação pode passar, não se ela já aconteceu. | Idempotência **no próprio efeito**: comentário com marcador `cepa:<fila>/<item>/<tentativa>` no corpo, checado pelo `_jiramut` antes de comentar; status atual checado antes de transitar. Sem lista e sem depósito novo (correção do painel; a revisão 1 propunha uma lista fechada). Frequência do comentário duplicado: não medida. |
| Idempotência e memos | Dois exemplos exatos do padrão "primeira escrita vence": o arquivo `<branch>.claim` criado com `O_EXCL` que garante que um handoff é retomado uma vez só (`docs/handoff.md`), e a reserva assinada do `cepa-plan`. | Aplicar o mesmo padrão ao `finish` (ver linha "Recuperação de queda"). |
| Transcrição e estado no mesmo commit | Não existe atomicidade entre fila e git: `cepa-plan finish --status done` e o commit do agente são dois atos em dois lugares (`finish --commit` commita só o `queue.yaml`). Foi isso que produziu o A5 de `docs/estrategia-fim-do-cepa-until.md` (9 commits de código do WEGO-2320 na branch da noite sem passar pelo build do supervisor). **A metade do conserto já existe:** desde 2026-09-28 o supervisor checa, por tentativa, que o SHA gravado é ancestral do HEAD e que nenhum outro item fechou no meio antes de desfazer (`merge-base --is-ancestor` em cinco pontos do `cepa-until`; BACKLOG marca como feito). | A outra metade: a **fila** não sabe que commit fecha o item. `finish --status done` deveria exigir worktree limpa e gravar o HEAD daquele instante no item. O `start` **não** deve recusar por ancestralidade (a branch da noite nunca é ancestral do HEAD do clone na manhã seguinte, até o dono mergear); quem usa o SHA é o `landed_check` e o `aterrissar`. |
| Fork | O Cepa bifurca **worktrees** e documenta o fork de contexto (`docs/context-forking.md`). O `claude` tem `--fork-session`. | Ninguém usa o fork de conversa. Não é dor hoje. |
| Compactação em segundo plano | Substituída pelo desenho: a conversa é curta por construção. | Nada a fazer. |
| Subagente durável | O subagente (Task) morre com o pai. | Fora do alcance de um plugin: o Cepa não controla o runtime do subagente. |
| Extensões por nome, troca a quente | O **oposto**, mas só no repo do próprio Cepa. Os hooks rodam da cópia instalada no cache do plugin, não do clone. O evento `hook_so_apos_reinstalar` aparece **24 vezes** nos registros, todas em filas do repo cepa (15 em `cepa`, 4 em `intencao-c1`, 3 em `cepa-espiral-c1`, 2 em `fb-2026-10`). Nos repos de produto o defeito não aparece. A revisão 1 dizia 72, número errado. | Reinstalação pelo supervisor quando a fila é do repo cepa, sob as condições da seção 4 (item 5). A rota de `docs/harness-ops.md` (Estado, Alvo, Rollback, Validação) tem de ganhar essa exceção por escrito. |
| Árvore de posse | O `cepa-until` mata o grupo de processos do filho (`killpg`) no SIGTERM e no estouro de folga, e registra `run_interrompido`. Quando o grupo **não** morre, o handler imprime "segue sem supervisor" e o comando de recuperação é `cepa-until fecha-morto <fila>/<run>`. | A posse para na fronteira do `claude -p`: um build que o agente deixou em segundo plano morre com ele. Por isso existe o hook `no-background-build` (506 bloqueios em cinco semanas, F7 da estratégia de 2026-10-08). O post resolve isso com **tasks de fundo pertencentes ao harness**; a seção 5 diz por que isso não se transporta direto. |
| Multijogador | No Cepa a dor não é de dois humanos, é de **dois agentes**: a sessão interativa do dono e o supervisor na mesma fila e no mesmo repo. Já produziu peças: guard de dono único na worktree, reserva assinada, `.claim` do handoff, "a main só muda com o dono presente". | A segunda metade ("enfileirar um pedido para o run em andamento") só existe como SIGTERM. Fica para o cockpit do condutor. |

### 2.1 Onde o corte dói, em números

Varredura: todo `*.jsonl` em `.claude/queues/*/until/` e `.claude/programs/*/until/` abaixo de `~`, excluindo `Library`. 147 arquivos em 11 raízes (62 em `wego-acessos-backend`, 18 em cada uma das quatro cópias do repo cepa, 10 em outros repos wego). Deduplicação por nome da fila + nome do arquivo, que colapsa as quatro cópias do cepa.

| Medida | Conta | Resultado |
|---|---|---|
| Runs únicos | pares (fila, arquivo) distintos | 93 |
| Subprocessos de item encerrados | eventos `item_end` | 530 |
| Encerrados **sem fechar o item** (status final `in_progress` ou `pending`) | ver partição abaixo | 59, ou 11,1% (59 ÷ 530) |
| Desses, `claude -p` saiu com código 0 (fim normal sem fechar) | 19 `pending` sem progresso + 11 `in_progress` sem progresso + 5 `pending` com progresso + 3 `pending` com progresso e rota humana + 2 `in_progress` com progresso | 40 |
| Desses, saiu com código 1 (erro do processo) | 13 `in_progress` + 2 `pending`, nenhum com progresso | 15 |
| Desses, morto por SIGTERM ao estourar a folga (código 143, `timeout: true`) | 3 sem progresso + 1 com progresso | 4 |
| Itens que precisaram de 2 ou mais tentativas no mesmo run | pares (run, item) com 2+ `item_start` | 36 de 493 (7,3%) |
| Runs encerrados por `prazo` (janela acabou, não a fila) | `run_end` com motivo `prazo` | 34 de 93 (36,6%) |
| Runs encerrados por cota de uso | `limite-de-uso` 6 + `cota-no-fim` 1 | 7 de 93 (7,5%) |

Leitura (corrigida pelo painel): **um em cada nove subprocessos termina sem fechar o item, mas 40 dos 59 são o `claude -p` terminando por conta própria** (hook barrando, item devolvido, rota humana, agente que parou), não um corte externo. Só os 19 de código 1 e 143 são candidatos a corte, e o corte por cota já é tratado no mesmo run (o supervisor dorme até o reset e retoma o mesmo item sem contar tentativa). "Progresso" aqui é o campo `progresso` do `item_end`, que o supervisor marca quando a tentativa deixou commit ou mudou o status do item. O registro de hoje **não** diz por que o processo saiu; é o primeiro campo que a seção 4 propõe gravar.

## 3. Diagnóstico

**C1. A durabilidade do Cepa é por item, e o item é grande.** Um item leva de 20 min (o item CS-2 de uma fila de 2026-10-25 levou 1.319 s) a mais de 1 h. Cortar e recomeçar do disco funciona, mas o grão de recuperação é o item inteiro, enquanto no Pi é o passo. A medida corrigida mostra que o corte externo é raro (no máximo 19 em 530); o grão grande custa mais quando o item **sai sozinho** sem fechar (40 em 530) e a tentativa seguinte redescobre tudo.

**C2. Há cinco depósitos de estado e nenhum diz se o run está vivo.** Cada um nasceu para um comando. O custo aparece como "a onda termina e ninguém aterrissa" (Maestro), "o run espera dono e ninguém vê" (resolvido com `estado.json` em 2026-09-30) e "handoff retomado duas vezes" (resolvido com `.claim`). Falta um heartbeat.

**C3. Fila e git não fecham juntos, e o `finish` aceita qualquer dono.** É a única das lacunas que já quebrou uma garantia (A5). As outras custam tokens; esta custa confiança no `done`.

**C4. Os hooks não trocam a quente no repo do próprio Cepa.** 24 eventos, todos em filas do cepa; o supervisor sabe que está rodando código velho e segue. Nos repos de produto não há dor.

**C5. O que o Pi chama de "task de fundo" o Cepa proíbe por hook.** O `no-background-build` existe porque o build não tem dono fora da conversa, e um `claude -p` não tem caixa de entrada para receber um evento. O supervisor já roda o build completo após cada item.

O que o Pi Durable **não** resolve para o Cepa: a dor medida em 2026-10-08 (o dono como escalonador de sessões, a pergunta fechada como forma obrigatória de toda decisão, um quinto da atenção gasta no próprio harness) é de condução e decisão, não de queda. Durabilidade é pré-requisito do condutor, não substituto dele.

## 4. Caminhos considerados

### O1. Endurecer a durabilidade por disco (continuar o desenho atual)

Manter "um item por subprocesso" e fechar as lacunas de estado sem tocar na conversa. Itens reescritos depois do painel; a numeração da revisão 1 foi mantida para rastreio.

1. **SHA e dono no `finish`.** `finish --status done` exige worktree limpa e grava o HEAD daquele instante no item; `finish` recusa se `claimed_by.session_id` não é o chamador ou se o status já é terminal, e registra a recusa. O `start` não recusa por ancestralidade. O item do BACKLOG "antecessor done sem merge" é fechado como superado e a parte correspondente do `reconcile` sai. Aceite: teste em que dois `finish` sobre o mesmo item deixam a evidência do primeiro, e um `done` sem commit é recusado.
2. **Id de sessão, motivo do fim e heartbeat.** O supervisor gera o `session_id` e o passa com `--session-id`; `item_start` e `item_end` o gravam. `item_end` ganha `motivo_fim` de conjunto fechado (`ok`, `contexto`, `cota`, `rede`, `folga`, `sinal`, `hook`, `desconhecido`), derivado do que o supervisor já observa (`exit_code`, `timeout`, `rate_limit_event`, trecho do log). `estado.json` ganha `heartbeat` gravado a cada N segundos; a regra de órfã para pid em outro host passa a usar a idade do heartbeat; um `start` que pula item por reserva viva em outro host grava `item_pulado`. Aceite: todo `item_end` de um run novo traz `session_id` e `motivo_fim`, verificado pelo `cepa-until-digest`.
3. **Leitor comum dos depósitos.** Entra depois do heartbeat (decisão do dono em X3, 2026-11-05: heartbeat e leitor, os dois). Nasce como módulo importado por `next`, `doctor`, `until-review` e `whereami`, com um teste que falha se aparecer arquivo de estado desconhecido em `.claude/`; lê o `heartbeat` para não responder "rodando" a run morto. Aceite: os quatro comandos passam a importar o módulo e o teste de depósito desconhecido existe.
4. **Idempotência de efeitos em Jira.** Marcador `cepa:<fila>/<item>/<tentativa>` no corpo do comentário, checado pelo `_jiramut` antes de comentar; status atual checado antes de transitar. Só entra depois que o `until-review` contar comentários duplicados por item e mostrar que acontece.
5. **Reinstalação pelo supervisor.** Quando a fila é do repo cepa e o item que fechou tocou `hooks/` ou `bin/`, o supervisor roda `install.sh` depois do build verde desse item, grava `hooks_reinstalados` (SHA antes e depois) no `.jsonl` e o SHA dos hooks em vigor em todo `item_start`. A exceção entra em `docs/harness-ops.md`, e a prova `until-avisa-hook-so-vale-apos-reinstalar.yaml` passa a cobrir "repo não é o cepa: avisa, não troca". Hooks lendo do clone (alternativa da revisão 1) foi descartada: ramo condicional em 61 arquivos.

- Ganho: fecha C2, C3 e C4 com mudanças locais em código que já tem testes. Mantém a decisão de desenho que fez o `cepa-until` sobreviver às noites.
- Não resolve: C1 (grão grande) e C5.
- Custo: o item 2 cabe em uma sessão; 1, 5 e 3 entram na fila `cepa-durabilidade` nessa ordem depois dele; o 4 espera medição.

### O2. Retomar a conversa cortada

Na segunda tentativa do mesmo item no mesmo run, quando o `motivo_fim` for externo (`cota`, `rede`, `folga`, `sinal`), lançar `claude -p --resume <session_id> --fork-session` com um prompt curto. O fork preserva a transcrição da tentativa cortada como registro do abortado.

Depois do painel, **O2 deixa de ser item e vira condição**: os números corrigidos dão no máximo 19 candidatos em 530 (3,6%), e a cota já é retomada no mesmo run. O2 só volta a ser considerado se, com o `motivo_fim` gravado por 20 runs, os fins externos passarem de 5% dos `item_end`. Se voltar, entra com: fallback para processo novo quando o `--resume` falhar antes do primeiro turno; no máximo uma retomada por item por run; evento `item_retomado`; número para "contexto cheio"; reserva órfã reclamada pelo supervisor antes da retomada; mesmo cwd da tentativa anterior; e as quatro provas `docs/proof/cepa-until*.yaml` e `until-*.yaml` verdes como condição de aceite. A medição é por corte artificial em ponto fixo numa fila de teste, com limiar escrito antes, porque um corte real não se repete sob encomenda.

### O3. Trocar o runtime: condutor sobre um harness durável

Construir o condutor sobre o Pi Durable ou equivalente próprio: conversas, tasks e documentos em SQLite, build como task do supervisor, fork por ciclo, cockpit multijogador.

- Ganho: todos os doze mecanismos de uma vez.
- Risco: o Pi Durable fala com o modelo pela `pi-ai`, não pelo Claude Code. Descarta de uma vez os hooks, skills, comandos e gates (proof, acceptance, green-or-revert) que são a parte madura do Cepa. É TypeScript numa base Python de 57 mil linhas, e é experimental por declaração do próprio post.
- Custo: reescrita. Descartado.

### O4. Encolher o item (acrescentado pelo painel)

Atacar C1 pelo grão, não pela conversa: o `drain-plan` deriva sub-itens do plano do item, cada um com `start`/`finish` próprios, reserva assinada e commit. Isso dá checkpoint por passo com a máquina que já existe e zero flag novo no `cepa-until`. Custo: o `drain-plan` é uma skill (prompt), não código; a derivação de sub-itens precisa de formato e de um escritor (o `cepa-plan`). Não entra como item agora; fica como o caminho a preferir sobre O2 se C1 voltar a doer.

## 5. Recomendação

**O1 itens 2, 1, 5 e 3, nesta ordem, na fila `cepa-durabilidade`; O2 como condição; O3 não; O4 registrado.** Três ideias do post entram no desenho do condutor (ciclo 2 do Epic) como perguntas, não como código:

- **Task de fundo pertence ao harness.** Um `claude -p` não tem canal de retorno, então o princípio não se transporta direto. A versão barata é "o agente pede o build e recebe o resultado no turno seguinte, por hook"; a cara é "dentro do mesmo turno". O item do condutor tem de responder antes: quantos builds simultâneos, o que acontece com a árvore que o agente edita enquanto o build roda, timeout, morte do supervisor com build em voo, e para quem vai o resultado se o processo que pediu já terminou. O `no-background-build` fica, com mensagem curta, como o dono decidiu em 2026-10-08 (decisão 5 sobre X5), até o supervisor ser dono do build.
- **Extensão por nome.** O filho do condutor roda o código atual do clone; é o item 5 de O1 generalizado.
- **Um storage, uma conformidade.** Os depósitos continuam como arquivos, mas o leitor nasce como módulo com teste que falha ao aparecer depósito desconhecido. É o item 3, último da fila `cepa-durabilidade`.

## 6. O que não muda

"Um item por subprocesso" fica. A decisão 3 do `cepa-until` ("um commit por item, numa única branch, sem merge train", 2026-08-30) continua valendo para runs de fila comum, e a revogação dela para filhos do condutor (decisão 7 de 2026-10-08) continua valendo para o ciclo 2; este documento não reabre nenhuma das duas. O R1 de 2026-09-26 ("a main só muda com o dono presente") fica. O card avulso e o board-flow ficam.

## 7. Riscos que todo caminho tem de respeitar

- **R1.** Nenhum caminho faz `done` sem build completo verde.
- **R2.** Gravar o `session_id` liga o registro do run à transcrição em `~/.claude/projects/`, que fica fora do repo e some com limpeza de cache. O registro tem de sobreviver sem ela; por isso o `motivo_fim` vai no `.jsonl`, não na transcrição.
- **R3.** Nenhum depósito de estado novo. Por analogia com a decisão 4 de 2026-10-08 (sem estacionamento novo para pendências do dono), estendida aqui a estado do harness: é regra deste documento, não decisão já tomada pelo painel anterior.
- **R4.** Trocar o harness live da máquina à noite (item 5) é exceção a `docs/harness-ops.md` e só vale declarada lá, restrita ao repo cepa e condicionada a build verde.

## 8. Decisões do dono sobre a revisão 1

Respondidas em 2026-11-05, antes do painel: sim às três (passar pelo painel; cinco itens de O1 na fila `cepa-espiral-c2`; O2 como flag desligado). O painel mudou a base das respostas 2 e 3, e elas voltam como discordâncias X2 e X1 abaixo.

## 9. Discordâncias nomeadas pelo painel

Registro completo, legenda de achados e propostas em `docs/reviews/2026-11-05-painel-durabilidade.md`. Decididas pelo dono em 2026-11-05: sim às cinco, com uma correção em X3 (heartbeat E leitor, não heartbeat no lugar do leitor). Efeitos: fila `cepa-durabilidade` criada com os itens 2, 1, 5 e 3; linha no Epic `cepa-em-espiral`; exceção em `docs/harness-ops.md`.

1. **X1. O2 sai do plano como item e vira condição (volta só se o `motivo_fim` mostrar fins externos acima de 5% dos `item_end` em 20 runs), e O4 entra como caminho preferido para C1?** Recomendo sim: os números corrigidos (40 dos 59 saíram com código 0) tiram a base do flag, e a contrarian e a custo-de-manutenção mostraram que um flag desligado é código vivo sem critério de remoção.
2. **X2. Os itens 2, 1 e 5 de O1 vão para uma fila própria `cepa-durabilidade`, com uma linha no Epic dizendo que o ciclo 2 depende dela, e os itens 3 e 4 ficam fora de qualquer fila até medição?** Recomendo sim: em `cepa-espiral-c2` eles herdam o `human_pending` do Contratos e não rodam, e a fonte declarada daquela fila é o texto do Epic.
3. **X3. O leitor dos cinco depósitos (item 3) é adiado, e no lugar entra o `heartbeat` no `estado.json` e a órfã por idade do heartbeat, dentro do item 2?** Recomendo sim: ler não é operar; sem heartbeat qualquer leitor responde "rodando" para um run morto.
4. **X4. A reinstalação de hooks à noite fica restrita ao repo cepa, só após build verde do item que tocou `hooks/` ou `bin/`, com SHA gravado em todo `item_start`, e entra em `docs/harness-ops.md` como exceção declarada?** Recomendo sim: é a única forma que fecha C4 sem ramificar 61 hooks e sem quebrar a doutrina em silêncio.
5. **X5. O princípio "task de fundo pertence ao harness" fica como pergunta de desenho do condutor, com as cinco perguntas do operador-sre como critério de pronto, e a frase que aposentava o `no-background-build` sai?** Recomendo sim: um `claude -p` não recebe evento, e a decisão 5 de 2026-10-08 sobre o hook continua valendo.
