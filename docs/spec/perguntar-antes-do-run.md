# Especificação: perguntar antes do run e perguntar menos em ação reversível

**Status:** ready-to-build
**Aberta em:** 2026-11-10            **Fechada em:** 2026-11-10
**Fontes lidas:** BACKLOG.md (entrada do topo), docs/estrategia-loops-longos.md (seções 2 a 5), common/bin/cepa-until, common/bin/cepa-plan, common/autonomy.yaml, common/commands/session.md, registros `*.jsonl` de 37 runs em `~/**/.claude/queues/*/until/`, os 21 `queue.yaml` em `~/**/.claude/queues/`

## Como chegamos aqui
Em 2026-11-10 o dono pediu: "Abrir sessão em modo descoberta sobre perguntar antes do run e perguntar menos em ação reversível (entrada no topo do BACKLOG.md)". A entrada nasceu da medição da seção 4.1 de `docs/estrategia-loops-longos.md`: em 32 de 37 runs que acabaram com a fila vazia e itens adiados, o dono não respondeu nenhuma pergunta antes do prazo do run.

## Problema
O run do `cepa-until` (o supervisor que executa a fila sem o dono presente) acaba cedo porque os itens que sobram esperam o dono, e a pergunta só aparece no painel do fim do run, quando ele já saiu. A janela pedida se perde: 261,0h das 366,4h perdidas (71%) são de runs que acabaram com a fila vazia.

## O que a leitura mostrou (2026-11-10)

- **L1. A maior parte dos adiados já estava adiada na largada.** Nos 37 runs, os `run_end` somam 347 adiamentos e os `item_end` com `status: blocked` somam 60. 347 − 60 = 287, e 287 ÷ 347 = 83% dos adiamentos não nasceram no run que os contou: a fila já os trazia. O registro não separa adiado por rota do dono de adiado por reserva ou por dependência, então 83% é teto para "esperava o dono desde a largada".
- **L2. Um terço dos itens executados trava no meio.** 60 `blocked` em 196 `item_end` = 31%.
- **L3. A largada não mostra o que a fila guarda para o dono.** `pending_as_text` e `decide` só são chamados no fim do run e em `cepa-until decide` (`common/bin/cepa-until:2795-2864`).
- **L4. As rotas abertas hoje são, na maioria, tarefa fora do repositório.** Nos 21 `queue.yaml` há 41 rotas ou bloqueios abertos: 24 em item já entregue (não impedem nenhum item de rodar) e 17 em item ainda aberto. Das 17, nenhuma é confirmação de ação reversível: são provisionar papel no Keycloak, validar em ambiente real, resposta jurídica, token vencido, conversa do dono que ainda não aconteceu. Das 24 em item entregue, 4 são confirmação de uma escolha que o agente já fez (WEGO-2496, WEGO-2388, DUR-3, interface-in-english). 4 ÷ 41 = 10%. É a foto de hoje, não dos 37 runs.

## Escopo
### Entra
- **Previsão.** A largada do `cepa-until` (o supervisor que executa a fila sem o dono presente) mostra quantos itens rodam e quantos esperam o dono.
- **Painel na largada.** O painel de perguntas que hoje só aparece no fim do run aparece antes do primeiro item, para as rotas do dono em item ainda aberto. Rota é a tarefa ou pergunta que só o dono fecha, gravada no campo `human_pending` do item ou num item `blocked`.
- **Linha resumida.** Rota que o dono já respondeu "não" não vira pergunta de novo na largada.
- **Leitura prévia.** Na largada, um agente só de leitura lê cada item executável, em paralelo, por no máximo 5 minutos, e devolve o que falta: uma pré-condição (algo de fora que precisa existir antes) ou uma preferência (uma escolha em que o agente tem um padrão reversível).
- **Corte restrito.** Escolha de comportamento que o agente já commitou na branch do run deixa de abrir rota e vira linha de informação no relatório do run.
- **Medição.** A largada grava no registro do run quantas perguntas mostrou, quantas foram respondidas e o que a leitura achou.

### Não entra
- Run que fica vivo esperando a resposta (P1 da estratégia): descartado pelo dono em 2026-11-10, recuperaria janela em 1 de 37 runs.
- Resposta no painel do fim retomar o mesmo run: é o item LL-1 da fila `cepa-loops-longos`.
- Aceitar dispensa de prova e mover card para Done sem perguntar: resposta do dono à Q7, é a assinatura dele.
- Alargar o corte para a lista `executa_e_reporta` de `common/autonomy.yaml`: resposta do dono à Q7.
- Guardar o resultado da leitura prévia de um run para o seguinte: pré-condição muda com o tempo (token vence), então cada largada lê de novo.
- Canal de aviso fora do terminal (celular, Slack): a medição mostrou que o dono responde no terminal.
- Relatório da medição no `cepa-until-digest` ou no `/common:metrics`: o evento é gravado aqui, o relatório vem depois de 10 runs.
- Perguntas em sessão interativa: já são de `common/autonomy.yaml`.

## Estado e migração
- `queue.yaml`: o item ganha a chave opcional `decisions` (lista das escolhas commitadas, cada uma com texto e commit). A rota aberta pela leitura prévia usa os campos que já existem (`human_pending` e a pergunta). Fila antiga sem `decisions` continua válida. Nada a migrar.
- Registro do run (`<run>.jsonl`): dois eventos novos, `largada` e `leitura_previa`. Registros antigos não mudam.
- Nenhum arquivo de estado novo.

## Critérios de sucesso

### CS-1: a largada mostra quantos itens rodam e quantos esperam o dono, antes do primeiro item
**Surface:** cli
**Red test:** numa fila com 2 itens `pending` e 1 item com `human_pending` aberto, `cepa-until <fila> --dry` imprime uma linha com "2" itens que rodam e "1" que espera o dono; hoje o cabeçalho só traz "1st item" e a contagem de `pending` e `done`.

### CS-2: num terminal, a rota de um item aberto vira pergunta antes do primeiro item, e o "sim" faz o item rodar no mesmo run
**Surface:** cli
**Red test:** numa fila só com o item A, que tem `human_pending` aberto, a largada com a resposta "y" injetada grava `item_start` de A no `<run>.jsonl`; hoje o run acaba em `end-of-queue` sem `item_start` e a pergunta só aparece no fim.

### CS-3: rota em item já entregue não entra no painel da largada
**Surface:** cli
**Red test:** numa fila com um item `done` que tem `human_pending` aberto e um item `pending`, a saída da largada não traz a pergunta do item entregue antes do primeiro `item_start`; hoje não há painel na largada para comparar, então o teste falha por não achar o painel.

### CS-4: rota que o dono já respondeu "não" aparece numa linha resumida, não como pergunta
**Surface:** cli
**Red test:** numa fila com duas rotas cuja última resposta do dono foi "não" em 2026-11-02, a largada imprime uma linha com "2" e "02/11" e não pede resposta para elas, e `cepa-until decide <fila>` ainda pergunta as duas; hoje a largada não imprime a linha.

### CS-5: pré-condição que a leitura prévia acha adia o item sem gastar o run nele
**Surface:** cli
**Red test:** com um leitor falso que devolve `pre-condicao` para o item X, e sem resposta do dono, o `<run>.jsonl` traz o evento `leitura_previa` com X, não traz `item_start` de X, e o `queue.yaml` passa a ter a rota aberta em X; hoje X recebe `item_start`.

### CS-6: preferência que a leitura prévia acha roda com o padrão do agente quando o dono não responde, e com a resposta dele quando responde
**Surface:** cli
**Red test:** com um leitor falso que devolve `preferencia` com padrão "P" para o item Y: sem resposta, o prompt entregue ao agente de Y contém "P" e o resumo do fim do run lista a escolha; com a resposta "R" injetada no painel, o prompt contém "R"; hoje o prompt não contém nenhum dos dois.

### CS-7: a leitura prévia para no teto e o item não lido roda como hoje
**Surface:** cli
**Red test:** com o teto reduzido a 1 segundo por variável de ambiente e um leitor falso que demora 5 segundos, a largada segue depois do teto, o evento `leitura_previa` marca o item como não lido e o item recebe `item_start`; hoje não existe leitura nem evento.

### CS-8: as perguntas que a fila já tem aparecem antes de a leitura prévia acabar, e as da leitura entram no fim da mesma lista
**Surface:** cli
**Red test:** com um leitor falso que demora 2 segundos e uma fila com uma rota aberta, a saída mostra a pergunta da rota antes da pergunta que veio da leitura, e o total do painel soma as duas; hoje não há painel na largada.

### CS-9: uma opção na linha de comando pula a leitura e o painel, e sem terminal a leitura roda sem painel
**Surface:** cli
**Red test:** com a opção, o `<run>.jsonl` não traz `leitura_previa` e a saída não pede resposta, mas traz a linha do CS-1; sem terminal e sem a opção, o `<run>.jsonl` traz `leitura_previa`, a saída lista as perguntas como texto e nada espera entrada; hoje a opção é recusada como argumento desconhecido.

### CS-10: depois do painel, se nenhum item roda, o run não começa
**Surface:** cli
**Red test:** numa fila só com rotas respondidas "não", a largada termina dizendo que nenhum item roda e não cria o worktree `until/<run>`; hoje o run começa e acaba em `end-of-queue`.

### CS-11: escolha de comportamento já commitada é gravada sem abrir rota e aparece no relatório do run com o commit
**Surface:** cli
**Red test:** `cepa-plan finish <fila> <id> done --decision "lote pula credencial inativa" --commit <hash>` deixa `human_pending` nulo e grava a escolha em `decisions`; o resumo do fim do run a lista com o commit; `cepa-until decide <fila>` não pergunta sobre ela; hoje `--decision` é recusado como argumento desconhecido.

### CS-12: o agente do item recebe a regra do corte
**Surface:** cli
**Red test:** o prompt que o `cepa-until` entrega ao agente de um item contém a instrução de usar `--decision` para escolha de comportamento já commitada e de manter `--human-pending` para dispensa de prova, card para Done e tarefa fora do repositório; hoje o prompt não menciona `--decision`.

### CS-13: a largada grava a medição no registro do run
**Surface:** cli
**Red test:** depois de uma largada com 1 rota respondida, 1 rota resumida e 1 achado da leitura, o `<run>.jsonl` traz um evento `largada` com os campos itens que rodam, itens que esperam, perguntas mostradas, perguntas respondidas, rotas resumidas, itens lidos, achados por tipo e segundos gastos; hoje o evento não existe.

## Perguntas em aberto
- [x] Q1. Quais alavancas esta especificação cobre: só a largada, a largada mais o corte restrito à confirmação de escolha já feita pelo agente, ou só o corte? — Largada + corte restrito (dono, 2026-11-10).
- [x] Q2. O que a largada faz com o que a fila já guarda para o dono: painel de perguntas antes de começar, só uma previsão com confirmação, ou recusa abaixo de um mínimo de itens executáveis? — Painel + previsão: a linha "N itens rodam, M esperam você" e o painel do fim do run, só para item que impede outro de rodar (dono, 2026-11-10).
- [x] Q3. A largada lê antes cada item executável para descobrir a pergunta que ele faria no meio (31% travam), ou só mostra o que já está gravado na fila? — Sim, leitura prévia, nesta especificação (dono, 2026-11-10).
- [x] Q4. A intenção gravada da sessão é de 2026-11-06 ("Especificar o caminho O2' da estratégia das três portas", plano 4/4 cumprido). Gravo uma nova para este assunto? — Sim (dono, 2026-11-10).
- [x] Q5. Quando a leitura prévia roda: na largada com o dono esperando (com teto de tempo), antes da largada num comando separado, ou no fim do run anterior? — Na largada, com teto: leitura em paralelo mostrando "lendo 3 de 7", no máximo 5 minutos, depois o painel. Item não lido a tempo roda como hoje (dono, 2026-11-10).
- [x] Q6. O que acontece com o item quando a leitura prévia acha algo e o dono não responde: o item é adiado sempre, roda sempre com a escolha padrão do agente, ou depende do tipo (pré-condição que falta adia, preferência com padrão reversível roda)? — Depende do tipo: pré-condição que falta adia o item; preferência com padrão reversível roda com a escolha do agente e fica registrada (dono, 2026-11-10).
- [x] Q7. O que conta como "confirmação de escolha reversível" que deixa de virar rota: só escolha de comportamento já commitada na branch do run, isso mais a dispensa de prova, ou tudo o que `common/autonomy.yaml` lista em `executa_e_reporta`? — Só escolha de comportamento já commitada na branch do run. Dispensa de prova e mover card para Done continuam sendo pergunta (dono, 2026-11-10).
- [x] Q8. Rota que o dono já respondeu "não" (ex.: WEGO-2044, respondida "não" em 02/11 e 06/11): o painel da largada pergunta de novo a cada run, ou mostra só uma linha resumida? — Linha resumida: rota já respondida "não" vira uma linha com a contagem e a data; só volta a ser pergunta no `cepa-until decide` (dono, 2026-11-10).
- [x] Q9. A previsão, a leitura prévia e o painel entram ligados por padrão em toda largada, ou só com uma opção na linha de comando? — Ligado por padrão em toda largada num terminal; uma opção na linha de comando pula; sem terminal a leitura roda e adia o que tem pré-condição faltando, sem painel (dono, 2026-11-10).
- [x] Q10. Enquanto a leitura prévia roda, o painel das rotas que a fila já tem aparece ao mesmo tempo, ou só depois que a leitura acaba? — Painel já, leitura ao fundo: as perguntas que a fila já tem aparecem na hora e as da leitura entram no fim da mesma lista (dono, 2026-11-10).

## Decided without asking
- O arquivo se chama `perguntar-antes-do-run`, o slug que o dono passou — as duas alavancas ficam numa especificação só, confirmado pela Q1. Vete aqui se discordar.
- "Item que impede outro de rodar" (resposta à Q2) foi lido como rota em item ainda aberto; rota em item já entregue fica fora do painel da largada (CS-3) — das 41 rotas de hoje, 24 estão em item entregue e não seguram nenhum item. Vete aqui se discordar.
- Os textos novos na tela saem em inglês — a interface do `cepa-until` já foi traduzida ("questions for you"). Vete aqui se discordar.
- A pré-condição achada pela leitura vira rota gravada no `queue.yaml` pelo `cepa-plan`, não uma anotação só do run — assim o próximo run a mostra no painel sem depender de ler de novo. Vete aqui se discordar.
- A leitura prévia não guarda resultado entre runs — token vence e ambiente muda; o custo em tokens é medido pelo CS-13 antes de pensar em guardar. Vete aqui se discordar.
- O leitor é um agente só de leitura que devolve um formato fechado (`pre-condicao`, `preferencia` ou nada) — sem escrita no repositório, e o formato fechado é o que deixa o teste usar um leitor falso. Vete aqui se discordar.
- O teto de 5 minutos e o modelo do leitor são configuráveis por variável de ambiente, com o modelo do run como padrão — o teste do CS-7 precisa de teto curto. Vete aqui se discordar.
- Os 5 minutos contam dentro da janela do run — a janela começa na largada, como hoje. Vete aqui se discordar.
- A leitura lê os itens na ordem da fila; o que não couber no teto roda como hoje — a ordem da fila é do dono. Vete aqui se discordar.
- Com zero itens executáveis depois do painel, o run não começa (CS-10) — começar para acabar em seguida só gera um registro vazio. Vete aqui se discordar.
- A linha "decidi por você" traz o commit e não ganha comando de veto — desfazer é um `git revert`, resposta à Q7. Vete aqui se discordar.
- O corte é regra no prompt do item mais a opção `--decision`; nenhum código tenta adivinhar pelo texto se uma rota era confirmação reversível — texto livre não dá para classificar por regra sem errar. Vete aqui se discordar.
- A medição grava o evento e não fixa meta numérica — a base de comparação é 31% de itens travados (60 de 196) e 32 de 37 runs sem resposta. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- L1 é teto, não medida exata: o `run_end` não grava o motivo de cada adiamento.
- L4 olha as filas como estão hoje. As perguntas dos 32 runs sem resposta já foram respondidas ou regravadas e não dá para reclassificá-las pelo `queue.yaml`.
- O painel da largada pode recuperar pouco: as 17 rotas em item aberto são tarefa fora do repositório, que o dono não fecha em um minuto. O ganho esperado está na leitura prévia (os 31% que travam no meio) e na previsão. O CS-13 mede isso.
- A leitura prévia pode adiar por engano um item que rodaria. O dono vê a rota no painel e a fecha com "sim".
- A leitura prévia gasta tokens e até 5 minutos em toda largada, em todos os repos.
- O corte pesa pouco hoje: 1 das 41 rotas (WEGO-2496) é escolha já commitada. Entrou porque o dono nomeou a alavanca.
- Não conferi se o `cepa-until-digest` ignora eventos que não conhece. Quem construir o CS-13 confere antes.
