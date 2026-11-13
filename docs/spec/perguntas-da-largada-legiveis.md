# Especificação: perguntas da largada do cepa-until legíveis e formatadas

**Status:** ready-to-build
**Aberta em:** 2026-11-12            **Fechada em:** 2026-11-13
**Fontes lidas:** common/bin/cepa-until (linhas 2459-2481, 2640-2720, 2795-2990, 3105-3260, 4395-4450), common/bin/cepa-plan (linhas 3440-3485), docs/spec/perguntar-antes-do-run.md, .claude/acceptance/interface-in-english.yaml, duas capturas de tela do dono (run `until/2026-11-12-1941` da fila `kairos-etapa-1`)

## Como chegamos aqui
Em 2026-11-12 o dono perguntou: "O cepa until agora me faz perguntas no início da execução. Por quê? E por que essas perguntas estão tão mal formatadas (sem formatação)? Por que essas perguntas estão tão mal escritas (ambíguas, confusas)?" (feedback fb-20261112-1).

## Problema
A largada do `cepa-until` (o supervisor que executa a fila sem o dono presente) passou a perguntar antes do primeiro item, por decisão da especificação `perguntar-antes-do-run`. As perguntas chegam em dois formatos, e os dois falham:

- As escolhas da leitura prévia (o agente só de leitura que abre cada item antes do run) saem como texto corrido, sem moldura nem rótulo, e quebram no meio da palavra.
- A rota sem pergunta escrita recebe a frase fixa "done already? With yes, the task closes and the item goes back to the queue.". Rota é a tarefa ou pergunta que só o dono fecha, gravada no campo `human_pending` do item. O dono não soube o que responder em C1-45 e C1-47, e a resposta dele em C1-45 foi recusada sem nada gravado.

## O que a leitura mostrou (2026-11-12)

- **L1. A leitura prévia não usa o painel.** `ask_preferences` (`common/bin/cepa-until:3221-3230`) escreve com `print`. As rotas antigas usam a classe `Panel`, que desenha moldura, rótulos, cor e quebra de linha na largura do terminal.
- **L2. A frase fixa supõe que toda rota é tarefa do dono.** `common/bin/cepa-until:2892-2897` pergunta "done already?" sempre que o item tem `human_pending` e não tem pergunta escrita. Em C1-45 o campo guarda um bloqueio e uma dúvida aberta ("a pergunta sobre de onde esse número deve vir continua aberta"). Em C1-47 guarda três bloqueios externos.
- **L3. Pergunta e legenda descrevem o mesmo "sim" de dois jeitos.** A pergunta diz "the task closes and the item goes back to the queue". A legenda (`answers_legend`, linha 2472) diz "yes = the item goes back to the queue with your answer". "Task" é o texto do rótulo `Task` acima, e a tela não diz isso.
- **L4. "Não entendi" não tem tecla.** O dono usou `[t]` para escrever que não entendeu. O `cepa-plan answer` recusa texto que pede esclarecimento (`not_an_answer`, `common/bin/cepa-plan:3471-3482`) e manda responder "sim/não e o porquê" ao texto da rota, que em C1-45 não é uma pergunta.
- **L5. A pergunta da leitura prévia é fechada, a resposta é texto livre.** O leitor devolve uma pergunta de sim ou não e um padrão. A tela pede "Your choice, in one line", e o que o dono digitar vira a escolha inteira. Um "Não" sozinho chega ao agente do item sem dizer o que fazer no lugar.

## Escopo
### Entra
- **Tipo da rota.** O agente que abre a rota grava o tipo dela: `owner-task` (tarefa que só o dono faz, fora do repositório), `external-block` (algo de fora que precisa existir e não depende de decisão do dono) ou `open-question` (dúvida que o dono responde).
- **Rota só abre com pergunta fechada.** `cepa-plan finish --human-pending` recusa a rota sem tipo, sem uma pergunta de sim ou não, ou sem dizer o que o sim e o que o não causam no trabalho.
- **Painel sem a frase fixa.** A frase "done already?" some. O rótulo do texto da rota muda com o tipo, a pergunta é a que o agente escreveu, e a legenda traz uma frase por tecla.
- **Rota antiga reescrita na largada.** A leitura prévia (o agente só de leitura que abre cada item antes do run) lê a rota gravada sem tipo ou sem pergunta e devolve tipo, pergunta fechada e o que cada resposta causa. O resultado é gravado no item.
- **Tecla "não entendi".** A tecla `?` no menu registra a pergunta como mal escrita, não grava resposta no item e manda o leitor reescrever a pergunta na hora, no mesmo painel, em até 60 segundos.
- **Leitura prévia no mesmo painel.** As escolhas que a leitura prévia acha usam a moldura, os rótulos e as teclas das rotas.
- **Recusa que aponta a saída.** Quando `cepa-plan answer` recusa um texto que pede esclarecimento, a mensagem aponta a tecla `?` do painel.

### Não entra
- Traduzir os rótulos fixos do painel para português: a interface em inglês é decisão do item `interface-in-english`, de 2026-10-23.
- Mudar quando a largada pergunta ou o que a leitura prévia procura em item sem rota: é o escopo de `perguntar-antes-do-run`, já construído.
- Mudar a listagem sem terminal (`pending_as_text`): ela não pergunta nada, só lista.
- Reescrever as rotas em item já entregue (`done` com `human_pending`): a largada não as mostra (CS-3 de `perguntar-antes-do-run`), e são 24 das 41 rotas medidas em 2026-11-10.
- Medir quantas perguntas o dono marcou como "não entendi" num relatório: o registro é gravado aqui, o relatório vem depois.

## Estado e migração
- `queue.yaml`: o item ganha a chave opcional `route_kind`, com um dos três valores. A pergunta e o que o sim e o não causam usam os campos que já existem (`question` e, em `owner_summary`, `se_sim` e `se_nao`). Fila antiga sem `route_kind` continua válida.
- Rotas já gravadas: não há migração em lote. Cada rota antiga em item aberto é reescrita pela leitura prévia na primeira largada que a encontrar, e o resultado fica gravado no item. O texto de `human_pending`, o `status` e a `evidence` não mudam.
- `common/plan-schema.yaml`: documenta `route_kind`.
- Nenhum arquivo de estado novo. O registro de "não entendi" vai para o arquivo de feedback que já existe em `~/.claude/cepa-feedback/`.

## Critérios de sucesso

### CS-1: `cepa-plan finish` recusa abrir rota sem tipo, sem pergunta fechada ou sem o efeito do sim e do não
**Surface:** cli
**Red test:** `cepa-plan finish <fila> <id> --status pending --human-pending "falta o acesso" --evidence "x"`, sem `--question`, sai com código diferente de 0, nomeia o que falta e deixa o `queue.yaml` igual; hoje sai com 0 e grava a rota.

### CS-2: a rota gravada com tipo aparece no painel com o rótulo do tipo e com a pergunta do agente
**Surface:** cli
**Red test:** num pseudo-terminal, `cepa-until decide <fila>` sobre um item com `route_kind: external-block` mostra o rótulo "Blocked outside" ao lado do texto da rota e a pergunta gravada; hoje o rótulo é sempre "Task".

### CS-3: nenhuma rota recebe a frase "done already?", e a legenda traz uma frase por tecla
**Surface:** cli
**Red test:** num pseudo-terminal, a saída de `cepa-until decide <fila>` sobre um item com `human_pending` e sem pergunta não contém "done already" nem "the task closes and the item goes back", e a legenda tem uma linha para cada tecla do menu; hoje contém as duas frases e a legenda é uma linha só.

### CS-4: a largada reescreve a rota antiga como pergunta fechada e grava o resultado no item
**Surface:** cli
**Red test:** numa fila com um item `pending` que tem `human_pending` e não tem `question`, com um leitor falso em `CEPA_UNTIL_LEITOR` que devolve tipo, pergunta e os dois efeitos, a largada num pseudo-terminal mostra a pergunta do leitor, e depois dela o `queue.yaml` traz `route_kind` e `question` nesse item com `human_pending`, `status` e `evidence` iguais; hoje a tela mostra "done already?" e o item não muda.

### CS-5: rota antiga que o leitor não reescreve no teto recebe uma pergunta neutra
**Surface:** cli
**Red test:** no cenário do CS-4 com um leitor falso que não responde dentro do teto, a tela mostra "Send this item back to the queue for the next run to try again?" e o rótulo "Left for you"; hoje mostra "done already?".

### CS-6: a tecla `?` registra a pergunta mal escrita sem gravar resposta no item
**Surface:** cli
**Red test:** num pseudo-terminal, apertar `?` numa pergunta do painel deixa o item igual no `queue.yaml` e acrescenta uma linha ao arquivo de feedback com alvo `cepa-until`, o id do item e o texto da pergunta; hoje a tela responde que `?` não é uma das opções.

### CS-7: depois do `?`, a pergunta reescrita aparece no mesmo bloco em até 60 segundos
**Surface:** cli
**Red test:** no cenário do CS-6 com um leitor falso que devolve outra pergunta, a tela mostra a pergunta nova no bloco do mesmo item e pede a resposta de novo, e o `queue.yaml` passa a trazer a pergunta nova; hoje não existe reescrita.

### CS-8: se a reescrita falha, ou no segundo `?` do mesmo item, o item fica para depois e a largada segue
**Surface:** cli
**Red test:** no cenário do CS-6 com um leitor falso que não responde em 60 segundos, a tela mostra uma linha dizendo que a pergunta não foi reescrita e que o item fica para depois, passa ao item seguinte e lista o item em "for later" no fecho do painel; hoje não existe esse caminho.

### CS-9: as escolhas da leitura prévia aparecem na moldura do painel, sem linha mais larga que o terminal
**Surface:** cli
**Red test:** num pseudo-terminal de 80 colunas, com um leitor falso que devolve uma preferência cujo texto tem 200 caracteres, nenhuma linha do bloco passa de 80 colunas, o bloco abre com a linha `N/M · <id>` da moldura e traz os rótulos "Choice", "Agent's default" e o menu de teclas; hoje o texto sai numa linha de mais de 80 colunas e sem menu.

### CS-10: na escolha da leitura prévia, `s` ou Enter aceita o padrão, `n` exige uma linha com o que fazer no lugar, `t` grava uma resposta livre
**Surface:** cli
**Red test:** no cenário do CS-9, responder `n` e depois "usar a data da guia" grava no evento `largada` do registro do run a escolha "não: <pergunta>. Em vez disso: usar a data da guia" com `fonte` "dono", e responder `n` com a linha vazia volta ao menu sem gravar; hoje qualquer texto digitado vira a escolha inteira e não existe `n`.

### CS-11: a recusa de `cepa-plan answer` a um texto que pede esclarecimento aponta a tecla `?`
**Surface:** cli
**Red test:** `cepa-plan answer <fila> <id> --answer "não entendi a pergunta"` sai com código 6 e a mensagem cita a tecla `?` de `cepa-until decide <fila>`, sem a frase "responda a essa pergunta (sim/não e o porquê)"; hoje a mensagem traz essa frase.

### CS-12: o agente do item recebe a regra de como abrir rota
**Surface:** application
**Red test:** o texto do pedido que o `cepa-until` monta para o agente de um item cita `--route-kind`, os três valores e a exigência de pergunta fechada com o efeito do sim e do não; hoje o texto não cita nenhum dos três.

## Perguntas em aberto
- [x] Q1. De onde vem o tipo da rota (tarefa do dono, bloqueio externo, dúvida aberta): o agente que abre a rota grava, ou a tela deduz do texto? — O agente grava (dono, 2026-11-13). A tela muda o rótulo e a legenda conforme o tipo.
- [x] Q2. Rota sem pergunta escrita: o `cepa-plan finish` passa a recusar abrir rota sem uma pergunta fechada, ou a tela continua com uma frase fixa melhor? — A gravação recusa (dono, 2026-11-13): sem pergunta de sim ou não e sem dizer o que o sim e o não causam, a rota não abre.
- [x] Q3. O menu ganha uma tecla "não entendi a pergunta", que não grava resposta e marca a pergunta como mal escrita? — Sim, tecla própria (dono, 2026-11-13): não grava resposta no item e registra a pergunta mal escrita, com o texto dela, para a triagem do harness.
- [x] Q4. As escolhas da leitura prévia passam a usar o mesmo painel e as mesmas teclas das rotas? — Sim (dono, 2026-11-13): moldura e rótulos iguais; `s` ou Enter aceita o padrão do agente, `n` pede uma linha dizendo o que fazer no lugar, `t` escreve uma resposta livre.
- [x] Q5. Rota antiga, gravada antes desta mudança, sem tipo e sem pergunta (C1-45, C1-47): a tela mostra uma pergunta neutra fixa, ou a leitura prévia da largada reescreve a rota como pergunta fechada? — A leitura prévia reescreve (dono, 2026-11-13). A pergunta neutra só vale quando o leitor não termina no teto.
- [x] Q6. Pergunta que o dono marcou como "não entendi": quem a reescreve? — Na hora, no mesmo painel (dono, 2026-11-13): a tecla dispara o leitor ali mesmo e a pergunta reescrita aparece antes do primeiro item.

## Decided without asking
- A recusa de rota sem pergunta fechada vale para toda chamada de `cepa-plan finish --human-pending`, em run e em sessão interativa — é a única porta que abre rota. Vete aqui se discordar.
- A correção vale também para o painel do fim do run e para `cepa-until decide` — é a mesma função `decide`. Vete aqui se discordar.
- A pergunta deixa de descrever o que as teclas fazem; isso fica só na legenda, em uma frase por tecla. "Task" e "item" não aparecem juntos na mesma frase — L3. Vete aqui se discordar.
- O registro de "não entendi" vai para `cepa-feedback add` com alvo `cepa-until`, o mesmo arquivo global que `/common:feedback` tria — já existe e o dono já o lê. Vete aqui se discordar.
- Pré-condição achada pela leitura prévia cuja pergunta falha na validação abre a rota com o tipo `external-block` e a pergunta fixa "Does this exist now?", em vez de abrir sem pergunta como hoje (`open_precondition_route`, `common/bin/cepa-until:3396`) — consequência da Q2. Vete aqui se discordar.
- Os rótulos fixos do painel continuam em inglês — decisão anterior do item `interface-in-english` (2026-10-23). Vete aqui se discordar.
- Os valores de `route_kind` são em inglês (`owner-task`, `external-block`, `open-question`) e os rótulos na tela são "Task for you", "Blocked outside" e "Open question" — segue o item `stop-reasons-in-english`. Vete aqui se discordar.
- A tecla de "não entendi" é `?` — é o que se digita por instinto, e hoje não é tecla de nada. Vete aqui se discordar.
- A rota antiga espera o leitor dela e entra no fim da lista do painel, junto com as escolhas da leitura prévia; a rota que já tem pergunta escrita aparece logo, como manda o CS-8 de `perguntar-antes-do-run` — sem o leitor não há pergunta para mostrar. Vete aqui se discordar.
- A reescrita da rota antiga é gravada no item, ao contrário do resto da leitura prévia, que não se guarda de um run para o outro — a pré-condição muda com o tempo, o texto de uma rota gravada não. Vete aqui se discordar.
- A reescrita nunca toca o texto de `human_pending`, o `status` nem a `evidence` — a regra da fila é que só o humano fecha a rota. Vete aqui se discordar.
- O segundo `?` no mesmo item não dispara o leitor de novo: registra e deixa o item para depois — evita segurar a largada num laço. Vete aqui se discordar.
- O teto da reescrita na hora é 60 segundos, o número que a opção escolhida na Q6 citava. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- **O agente do run pode não conseguir abrir a rota.** Com a recusa do CS-1, um agente que escreve uma pergunta ruim é barrado mais vezes. O que acontece hoje com o item quando `finish` recusa não foi lido nesta especificação; o primeiro item da fila deve conferir isso antes de construir o CS-1.
- **O leitor pode classificar errado.** A reescrita de uma rota antiga é a leitura de um agente sobre o texto de outro. A tecla `[e]` continua mostrando o texto original.
- **A reescrita na hora segura a largada.** Cada `?` custa até 60 segundos de espera antes do primeiro item.
- **Rotas em item já entregue continuam com a frase antiga fora da largada.** `cepa-until decide` as mostra, e elas não são reescritas; recebem a pergunta neutra do CS-5.
