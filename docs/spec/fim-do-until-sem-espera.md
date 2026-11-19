# Especificação: o fim do `cepa-until` faz o merge sozinho ou encerra sem esperar, num relatório TUI

**Status:** ready-to-build
**Aberta em:** 2026-11-19            **Fechada em:** 2026-11-19
**Fontes lidas:** common/bin/cepa-until (close_with_owner, ask_mid_run, o painel do meio do laço principal, o relatório depois de "ended at", land_action, o painel "aterrissar", _cmd_land), common/bin/cepa-plan (o detalhe da parada `end-of-queue`), os prints do dono das runs kairos-etapa-1/2026-11-18-1725 (wego-digitacao-backend) e resposta-do-decide/2026-11-18-1731 (cepa)

## Como chegamos aqui
Em 2026-11-19 o dono comparou duas runs noturnas, ambas `cepa until <fila> --until 6:00`, e perguntou: "Why did they finish different from each other?" Também disse que o "Land now? [y/N/q] nobody answered in 10 min" vai acontecer quase sempre e pediu uma proposta, além de tirar o português da tela e melhorar o layout do relatório e do `land`.

## Problema
1. O fim da run pergunta "Land now?" e espera 10 min. A run é desatendida por desenho, então ninguém responde e o merge fica para a manhã, mesmo numa run limpa (fast-forward, builds verdes, nada esperando).
2. O fim tem dois formatos. Quando a fila esvazia com itens do dono adiados, o painel do meio pergunta primeiro, ninguém responde, e o fim só lista o merge como texto (`mid_run_silent`). Sem itens adiados, o fim faz a pergunta do merge. A regra é a mesma, mas a ordem muda e o dono lê como inconsistência.
3. O merge aparece até três vezes no mesmo relatório ("Actions", "waiting on you", o painel da pergunta). O motivo de um item travado ocupa cinco linhas. As escolhas do pré-read e as decisões são duas listas separadas sobre os mesmos itens.
4. Português na tela: o id `aterrissar` e o detalhe de parada do `cepa-plan` "a fila acabou — nenhum item executável sobrou...".
5. O `cepa-until land --yes` imprime linhas soltas, sem número de etapa nem duração, e "rescued 2 artifact(s)" não diz o que fazer com os arquivos.

## Escopo
### Entra
- Pré-autorização do merge na largada, como flag e como pergunta da largada.
- O merge feito pela própria run quando a pré-autorização vale e a run está limpa.
- O fim da run nunca pergunta "Land now?".
- O nome da ação na tela: "merge into `<branch>`" (com "build + push"), nunca `aterrissar`. O comando continua `cepa-until land`.
- Inglês nos dois detalhes de parada do `cepa-plan`.
- O relatório final e a saída do `land` redesenhados como painéis TUI.
### Não entra
- Renomear o id `aterrissar` gravado no `.estado.json` e o estado `aterrissado`: quem lê runs antigas depende deles.
- Merge só local (merge + build, sem push). O dono escolheu merge com push.
- As outras frases em português do `cepa-plan` que nunca chegam à tela do `cepa-until`.

## Estado e migração
O estado da run (`.estado.json`) ganha `auto_land` (`true`/`false`) e, quando a run faz o merge sozinha, o mesmo registro `aterrissagem` que o `land` grava hoje. Estado antigo sem `auto_land` é lido como `false`. Os ids gravados não mudam. `cepa-until land` numa run antiga funciona como hoje.

## Critérios de sucesso

### CS-1: `--auto-land` faz uma run limpa fazer o merge sozinha no fim
"Limpa" é mecânico: a branch de destino do clone não andou desde a base da run (fast-forward), o último build completo da branch da run está verde e nenhum item terminou travado ou esperando o dono. Aí a run faz exatamente o que `cepa-until land --yes` faz (merge, build completo, push, ponto de retorno gravado) e o estado termina `aterrissado`.
**Surface:** cli
**Red test:** uma run com `--auto-land` sobre uma fila cujo único item entrega verde, com o `main` do clone intocado, termina com o commit da branch da run no `main` e o estado `aterrissado`; hoje a flag não existe e o argparse sai com 2.

### CS-2: uma run não limpa com `--auto-land` não faz o merge e diz qual condição falhou
**Surface:** cli
**Red test:** uma run com `--auto-land` em que um item termina travado acaba com estado `esperando-dono`, `main` intocado e uma linha que nomeia a condição que falhou ("not merged: WEGO-2542 is stuck"); hoje a flag não existe.

### CS-3: sem a flag, a largada pergunta a pré-autorização uma vez, junto com as outras perguntas da largada
A pergunta é "If the run ends clean (fast-forward, green build, nothing waiting on you), merge into `main` and push without asking?". A resposta é gravada como `auto_land`, e sem resposta vale não. `--no-auto-land` pula a pergunta. Run sem terminal nunca pergunta e lê como não.
**Surface:** cli
**Red test:** num pseudo-terminal, lançar sem `--auto-land` mostra essa pergunta antes do primeiro item, e responder `y` grava `"auto_land": true` no estado da run; hoje a pergunta não existe.

### CS-4: o fim da run nunca pergunta "Land now?"
Quando a run não faz o merge sozinha, o fim imprime o comando e encerra, sem esperar. As perguntas dos itens do dono continuam como hoje.
**Surface:** cli
**Red test:** num pseudo-terminal, uma run limpa sem pré-autorização sai segundos depois do relatório e a saída não contém "Land now?"; hoje imprime "Land now? [y/N/q]" e espera `CEPA_UNTIL_ESPERA_RESPOSTA` segundos.

### CS-5: nada de português na tela do fim
A ação aparece como "merge into `<branch>`" em todo lugar onde aparece. O detalhe de parada do `cepa-plan` diz "the queue is finished: no runnable item is left, and N were deferred (each with its reason in the report)".
**Surface:** cli
**Red test:** a saída do fim de uma run com um item adiado não contém "aterrissar" nem "a fila acabou"; hoje contém os dois.

### CS-6: o relatório final é um conjunto de painéis TUI, e o merge aparece uma vez só
O layout, nesta ordem:
1. Painel de cabeçalho: hora do fim, motivo da parada, janela com a barra de progresso, e uma linha de totais (entregues, travados, esperando você, commits, custo).
2. Painel "Items": uma linha por item, com ícone, id numa coluna alinhada e motivo cortado na largura do terminal (o motivo inteiro fica no `review.md`).
3. Painel "Decisions": as escolhas do pré-read e os commits "decided for you" juntos, agrupados por item, uma linha cada, com o commit.
4. Painel "Next", o último, numerado: o merge (com o comando e, quando a run não está limpa, por que não é recomendado), depois as perguntas do dono (ids e o comando `decide`), depois a reinstalação do plugin quando se aplica.
5. Uma linha esmaecida com os caminhos do registro, do log e da análise.

Os painéis usam bordas de box-drawing com título e a paleta de cores que já existe. Caem para texto simples sem cor quando o stdout não é terminal ou `NO_COLOR` está definido.
**Surface:** cli
**Red test:** com `COLUMNS=100`, a saída do fim de uma run com um item travado cujo motivo tem 400 caracteres não tem linha com mais de 100 colunas, contém "merge into" exatamente uma vez e não contém "Actions:", "Left with you" nem "waiting on you"; hoje o motivo quebra em várias linhas e o merge aparece duas vezes.

### CS-7: `cepa-until land --yes` imprime etapas numeradas com resultado e duração
A saída tem um cabeçalho (branch da run → destino, número de commits, fast-forward ou não, ponto de retorno), depois `[1/3] merge`, `[2/3] full build` e `[3/3] push`, cada uma com resultado e duração. Quando a worktree da run tinha arquivos fora do git, lista esses arquivos e diz para onde movê-los ou que podem ser apagados. Fecha com a hora do fim e "run worktree and branch removed".
**Surface:** cli
**Red test:** `cepa-until land <fila>/<run> --yes` numa run de fixture imprime linhas começando com `[1/3]`, `[2/3]` e `[3/3]`, e o bloco dos arquivos guardados contém "move to" ou "delete"; hoje imprime "full build:" e "pushed" sem número de etapa.

## Perguntas em aberto
- [x] Pré-autorização na largada ou flag? As duas: a flag `--auto-land` e a pergunta na largada quando a flag não vem.
- [x] Merge com push? Sim.
- [x] Que nome na tela? "merge into `<branch>`", com "build + push". O comando continua `land`.
- [x] O layout? Painéis TUI, como no CS-6 e no CS-7.

## Decided without asking
- "Limpa" reaproveita as condições que a análise já escrevia como "Recommend yes" (fast-forward, builds verdes, nada esperando), mas calculadas pelo código, não lidas do `review.md`, que pode falhar ou ficar sem cota. Vete aqui se discordar.
- Os nomes das flags são `--auto-land` e `--no-auto-land`. Vete aqui se discordar.
- O merge automático roda depois da análise e das perguntas dos itens do dono, como último passo antes do commit dos registros da run. Um sim a uma pergunta ainda devolve o item à run antes. Vete aqui se discordar.
- Os ids gravados no estado mantêm os nomes em português (`aterrissar`, `aterrissado`), e só a tela muda. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- O merge automático faz push no remoto à noite. O ponto de retorno e o `git revert` desfazem, mas quem fizer pull nesse intervalo recebe os commits.
- O build completo do merge automático roda dentro da janela. No wego-digitacao-backend levou 15 min, então uma run perto do prazo pode não terminar o merge. Quando a janela não comporta a duração do último build, o merge não começa e o painel "Next" diz por quê.
