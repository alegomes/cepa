# Especificação: resposta do `cepa-until decide` vira trabalho com dono

**Status:** ready-to-build
**Aberta em:** 2026-11-18            **Fechada em:** 2026-11-18
**Fontes lidas:** common/bin/cepa-plan (cmd_answer, cmd_reword_route, cmd_add, not_an_answer), common/bin/cepa-until (decide, ROUTE_READER_PROMPT), common/commands/until-review.md (bloco cepa-decisoes), common/commands/drain-plan.md (finish com --if-yes/--if-no)

## Como chegamos aqui
Em 2026-11-18, depois de responder várias perguntas num `cepa plan decide` da fila kairos-etapa-1 (repo wego-digitacao-backend), o dono perguntou: "O que podemos fazer para garantir que decisões tomadas via `cepa plan decide` não caiam no limbo e fiquem sem follow up?"

## Problema
O dono responde "sim" a perguntas como "Ponho na fila um item para...?" e a resposta só fecha a pendência humana. O item prometido não nasce, a próxima rodada encontra a fila vazia e a decisão some do `/common:next` e do `/common:whereami`. Pior: o `answer` apaga o `owner_summary` (o texto "se sim"/"se não"), então nem o registro do que o "sim" prometia sobra no item.

## Escopo
### Entra
- Quem escreve a pergunta ao dono declara, junto, o item que a resposta cria; a resposta cria esse item na fila na hora, sem agente.
- Vale para toda resposta (sim ou não) cujo efeito muda trabalho e que não devolve o próprio item para `pending`.
- A declaração é obrigatória: quem escreve a pergunta diz o item de cada resposta sem retorno, ou "nenhum" explícito.
- O item declarado pode nascer "precisa do dono", já com pendência humana aberta.
- O item criado entra na mesma fila do item respondido, no fim.
- Rota antiga sem declaração: a resposta é gravada, nada é criado, e a saída avisa com o comando `cepa-plan add` pronto.
### Não entra
- Pergunta gravada como resposta (caso C1-34, "como/onde conferir"): é outro defeito, no filtro `not_an_answer`; vira item de backlog separado.
- Recuperar respostas antigas (A1 a A4 da kairos-etapa-1 e outras): o texto "se sim" delas já foi apagado, uma varredura adivinharia.

## Estado e migração
Itens e respostas já gravados não mudam. O item da fila ganha dois campos opcionais na seção do dono (`owner_summary`): o item que o "sim" cria e o item que o "não" cria, cada um com título e a marca "precisa do dono". Rotas antigas, sem esses campos, continuam respondíveis e caem no aviso do CS-5. Nenhuma fila existente precisa ser reescrita.

## Critérios de sucesso

### CS-1: o `cepa-plan finish` recusa pergunta ao dono sem o item de cada resposta sem retorno
Rota aberta em item `done` sem item declarado para o "sim", ou qualquer rota sem item declarado para o "não", sai com código 2 e nada é gravado. "nenhum" explícito é aceito. A mesma regra vale para `reword-route` e para o bloco `cepa-decisoes` do `/common:until-review`.
**Surface:** cli
**Red test:** `cepa-plan finish <fila> <id> --status done --human-pending "..." --route-kind open-question --question "Ponho na fila um item para X?" --if-yes "..." --if-no "..."`, sem declarar item, sai com código 2 e a fila fica igual byte a byte; hoje sai 0 e grava a rota.

### CS-2: o "sim" a uma pergunta com item declarado cria esse item no fim da mesma fila
O item nasce `pending`, com o título declarado e com evidência que cita o item de origem, a data, a pergunta e a resposta. A saída do `answer` imprime o id do item novo.
**Surface:** cli
**Red test:** numa fila com item `done` cuja rota declara o item "calibrar X" para o "sim", `cepa-plan answer <fila> <id> --answer "sim: ..."` deixa a fila com um item a mais, no fim, `pending`, título "calibrar X" e evidência citando `<id>`; hoje a fila sai com o mesmo número de itens.

### CS-3: o item declarado "precisa do dono" nasce com pendência humana aberta e aparece como ação do dono
**Surface:** cli
**Red test:** com a declaração marcada "precisa do dono", depois do `answer` o item novo tem `human_pending` preenchido e `cepa-plan queue <fila> --json` o lista entre os adiados com motivo `human_pending`; hoje o item nem existe.

### CS-4: a próxima rodada encontra o trabalho criado pela resposta
**Surface:** cli
**Red test:** depois do `answer` do CS-2, `cepa-plan queue <fila> --max 1` devolve o item novo no lote; hoje, no cenário do print (só itens `done` e uma pendência), responde lote vazio.

### CS-5: resposta sem retorno em rota antiga, sem item declarado, avisa em vez de calar
A resposta é gravada, nada é criado, e a saída imprime "esta resposta não cria trabalho" com o comando `cepa-plan add <fila> ...` pronto para copiar. O fechamento do `cepa-until decide` repete o aviso para cada item nessa situação.
**Surface:** cli
**Red test:** `cepa-plan answer` num item `done` com rota antiga sem declaração imprime a linha "esta resposta não cria trabalho" e um `cepa-plan add`; hoje imprime só "rota humana fechada".

### CS-6: a resposta guarda na evidência o que cada opção prometia
O `answer` deixa de apagar sem registro o texto "se sim"/"se não": antes de remover a seção do dono, copia a pergunta e o efeito escolhido para a evidência.
**Surface:** cli
**Red test:** depois de `cepa-plan answer ... --answer "sim: ..."`, a evidência do item contém o texto do `se_sim`; hoje não contém.

### CS-7: o fechamento do `cepa-until decide` lista os itens criados pelas respostas
**Surface:** cli
**Red test:** um `cepa-until decide <fila>` com uma resposta que cria item termina com uma linha "itens criados pelas suas respostas:" seguida do id e do título; hoje o fechamento não tem essa linha.

## Perguntas em aberto
- [x] Quem cria o trabalho que um "sim" promete? — A pergunta declara a ação: quem escreve a pergunta grava o item que a resposta cria, e a resposta cria esse item na hora, sem agente.
- [x] Quais respostas entram na regra? — Toda resposta (sim ou não) cujo efeito muda trabalho e que não devolve o próprio item para `pending`.
- [x] O caso C1-34 (pergunta gravada como resposta) entra? — Fica de fora, vira item de backlog separado.
- [x] Recupera as respostas já perdidas? — Não, só daqui pra frente.
- [x] A declaração do item é obrigatória? — Sim, com "nenhum" explícito aceito.
- [x] Rota antiga sem declaração recebe resposta sem retorno: o que acontece? — Grava, avisa e mostra o comando `cepa-plan add`.
- [x] O item declarado pode nascer "precisa do dono"? — Sim, já com pendência humana aberta.
- [x] Em que fila e posição o item entra? — Mesma fila, no fim.

## Decided without asking
- "Resposta sem retorno" fica definida mecanicamente: o "sim" de rota em item `done` e o "não" de qualquer rota (que deixa o item como está). O "sim" de item `blocked` devolve o item a `pending`, então não pede declaração. Assim a obrigatoriedade não cobra campo inútil. Vete aqui se discordar.
- A obrigatoriedade vale para os três lugares que escrevem pergunta na fila: `cepa-plan finish`, `cepa-plan reword-route` (o leitor que reescreve rota antiga) e o bloco `cepa-decisoes` do `/common:until-review`. Deixar um de fora reabre o buraco. Vete aqui se discordar.
- O item que nasce "precisa do dono" leva `route_kind: owner-task`, a pendência humana com o texto declarado, e declarações "nenhum" para as próprias respostas. Evita uma cadeia infinita de declarações. Vete aqui se discordar.
- Os nomes exatos das flags e campos (por exemplo `--if-yes-item`, `--if-no-item`, `--item-needs-owner`) ficam para a construção. Não mudam o comportamento. Vete aqui se discordar.
- O id do item novo segue a regra do `cepa-plan add` que já existe. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- Agente que declara "nenhum" por preguiça quando a pergunta promete trabalho. A trava só garante que alguém decidiu; não lê a intenção da pergunta.
- O caso C1-34 (pergunta gravada como resposta) fica para um item de backlog separado.
- As respostas já perdidas (A1 a A4 da kairos-etapa-1) dependem do `cepa plan add` que a sessão do wego ofereceu.
