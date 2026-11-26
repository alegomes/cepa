# Especificação: dúvida sobre a pergunta no painel do `cepa run decide`

**Status:** ready-to-build
**Aberta em:** 2026-11-26            **Fechada em:** 2026-11-26
**Fontes lidas:** common/bin/cepa-run (legend_lines, laço do painel `decide`, `_apply_answer`, `unclear`, `rewrite`), common/bin/cepa-queue (`not_an_answer`, recusa do `answer`), docs/spec/perguntas-da-largada-legiveis.md, docs/spec/campo-de-resposta-until.md, docs/spec/teclas-em-ingles.md

## Como chegamos aqui
Em 2026-11-26 o dono mostrou a tela do item C1-47 e perguntou: "O que houve aqui? Como proceder se eu tiver dúvidas sobre a pergunta que está sendo feita?". Ele tinha escolhido `w` e digitado "O que é a variante O?", e o painel recusou sem indicar outro caminho.

## Problema
A pergunta do item usa um termo que o dono não conhece ("variante O"). O caminho que parece natural para perguntar de volta é `w`, mas o texto de `w` é gravado como resposta e a próxima rodada lê esse texto sem ninguém para responder. O painel recusa o texto que termina em `?`, manda "repita com --force" (opção que só existe em `cepa-queue answer`) e joga o item para depois, sem dizer que as teclas `e`, `?` e Enter existem para esse caso. A ajuda da tecla `?` ainda omite que a pergunta é reescrita em seguida.

## Escopo
### Entra
- **Dúvida digitada em `w` ou `v`.** Quando o texto digitado termina em `?` ou pede esclarecimento (a mesma regra `not_an_answer` de `cepa-queue answer`), o painel pergunta "Is this a doubt about the question? [Y/n]" antes de gravar qualquer coisa.
- **Dúvida vira reescrita.** Com sim, o painel age como a tecla `?`: registra a pergunta como mal escrita, não grava resposta no item e manda o leitor reescrever a pergunta, entregando a ele o texto da dúvida.
- **Não é dúvida, é resposta.** Com não, o texto é gravado no item como resposta, sem o dono sair do painel.
- **Tecla `?` pede a dúvida.** Ao apertar `?`, o painel mostra uma linha opcional "What did you not understand? [Enter skips]". O texto, quando existe, vai para o leitor e para o registro de feedback.
- **Até duas reescritas por item.** A segunda só acontece quando traz uma dúvida digitada.
- **Recusa que fica no item.** Quando o painel recusa um texto (por exemplo, só pontuação), o menu do mesmo item reaparece e a mensagem cita só teclas que estão na tela. A frase "repita com --force" não aparece no painel.
- **Ajuda da tecla `?`.** A legenda passa a dizer que a pergunta é reescrita em seguida, em até 60 segundos.
- **Ajuda do Enter.** A legenda passa a dizer que o item fica para depois e que a dúvida pode ser levada a uma sessão de chat, citando a fila e o item.

### Não entra
- A tela das escolhas da leitura prévia (`y`, `n`, `w` antes do run). Ela não tem a tecla `?` nem rota gravada para reescrever.
- A recusa de `cepa-queue answer` na linha de comando. Lá `--force` existe e a mensagem continua como está.
- Mostrar a tecla `e` em item sem detalhe técnico. Resposta da Q3.
- Um bloco pronto para colar numa sessão de chat. Resposta da Q4.
- O modo sem terminal (`--from-chat`). Não há menu nem teclas nele.
- Fazer o agente escrever perguntas sem termo desconhecido. Isso é a regra de abrir rota (CS-12 de `perguntas-da-largada-legiveis`), outro assunto.

## Estado e migração
O `queue.yaml` não ganha campo novo. A dúvida digitada não é gravada no item: ela vai para o leitor (campo novo no pedido de reescrita, ao lado de `pergunta_mal_escrita`) e para a linha de feedback de `cepa-feedback add`. A pergunta reescrita é gravada como hoje, por `cepa-queue reword-route --replace`. Itens e rotas já gravados não mudam.

## Critérios de sucesso

### CS-1: texto que parece dúvida, digitado em `w`, faz o painel perguntar se é dúvida antes de gravar
**Surface:** cli
**Red test:** num pseudo-terminal, escolher `w` num item do painel e digitar "O que é a variante O?" mostra a linha "Is this a doubt about the question? [Y/n]" e o `queue.yaml` continua igual; hoje a tela pergunta "Send the item back to the queue with that answer? [y/N]" e depois mostra "not recorded".

### CS-2: com sim, a pergunta é reescrita com a dúvida do dono e reaparece no mesmo item
**Surface:** cli
**Red test:** no cenário do CS-1, responder Enter com um leitor falso que grava o pedido recebido: o pedido traz "O que é a variante O?" como dúvida do dono, a tela mostra a pergunta nova no bloco do mesmo item e pede a resposta de novo, o item segue sem resposta gravada e o arquivo de feedback ganha uma linha com o id do item, a pergunta e a dúvida; hoje o leitor nunca é chamado a partir de `w`.

### CS-3: com não, o texto é gravado como resposta sem sair do painel
**Surface:** cli
**Red test:** no cenário do CS-1, responder `n` e depois `y` em "Send the item back to the queue with that answer?" grava "O que é a variante O?" na evidência do item como resposta do dono e a tela mostra a confirmação de gravado; hoje a tela mostra "not recorded: resposta recusada" e nada é gravado.

### CS-4: a dúvida digitada no editor (`v`) segue o mesmo caminho do `w`
**Surface:** cli
**Red test:** num pseudo-terminal com um editor falso que salva "não entendi a pergunta", escolher `v` mostra "Is this a doubt about the question? [Y/n]"; hoje a tela mostra "not recorded: resposta recusada" e o item vai para depois.

### CS-5: a tecla `?` pede em uma linha opcional o que o dono não entendeu
**Surface:** cli
**Red test:** num pseudo-terminal com um leitor falso que grava o pedido recebido, apertar `?` mostra "What did you not understand? [Enter skips]"; digitar "variante O" faz o pedido ao leitor trazer esse texto, e Enter vazio faz o pedido ir sem dúvida, como hoje; hoje `?` chama o leitor sem perguntar nada.

### CS-6: depois de um `?` sem texto, uma dúvida digitada dispara a segunda reescrita, e a terceira tentativa deixa o item para depois
**Surface:** cli
**Red test:** num pseudo-terminal com um leitor falso que conta as chamadas, apertar `?` com Enter vazio e depois digitar uma dúvida em `w` chama o leitor duas vezes e mostra a segunda pergunta nova no mesmo item; uma terceira dúvida não chama o leitor, mostra uma linha dizendo que o item fica para depois e o item aparece em "for later" no fecho; hoje o leitor é chamado no máximo uma vez por item.

### CS-7: um segundo `?` sem texto não dispara reescrita
**Surface:** cli
**Red test:** no cenário do CS-6, apertar `?` duas vezes com Enter vazio nas duas chama o leitor uma vez só, e a tela diz que a pergunta não será reescrita de novo sem uma dúvida escrita; hoje a mensagem diz só "the reader rewrites once per item", sem citar que uma dúvida escrita dispara outra.

### CS-8: texto recusado devolve o menu do mesmo item e a mensagem não cita `--force`
**Surface:** cli
**Red test:** num pseudo-terminal, escolher `w` e digitar "..." mostra uma linha de recusa sem a palavra "--force", que cita só teclas presentes no menu daquele item, e o menu do mesmo item reaparece pronto para outra tecla; hoje a tela mostra "repita com --force" e passa ao item seguinte.

### CS-9: a mensagem de recusa não cita a tecla `e` quando o item não tem detalhe técnico
**Surface:** cli
**Red test:** no cenário do CS-8 com um item sem `evidence`, a linha de recusa não traz "[e]"; com um item com `evidence`, traz; hoje a recusa não cita tecla nenhuma.

### CS-10: a legenda da tecla `?` diz que a pergunta é reescrita em seguida
**Surface:** cli
**Red test:** num pseudo-terminal, a linha da legenda que começa com "? =" contém "rewritten" e "60"; hoje ela diz "it is recorded as badly written and nothing is answered".

### CS-11: a legenda do Enter diz que a dúvida pode ir a uma sessão de chat, com a fila e o item
**Surface:** cli
**Red test:** num pseudo-terminal com a fila `f1` e o item `C1-47`, a linha da legenda que começa com "Enter =" contém "chat", "f1" e "C1-47"; hoje ela diz "leaves the question for later".

## Perguntas em aberto
- [x] Q1. Quando o dono digita uma dúvida em `w` ou `v`, o painel recusa e volta ao menu do mesmo item, ou trata a dúvida como a tecla `?` e reescreve a pergunta usando o texto digitado? Resposta (dono, 2026-11-26): o painel pergunta se o texto é uma dúvida sobre a pergunta; com sim, age como a tecla `?` e entrega o texto digitado ao leitor que reescreve a pergunta.
- [x] Q2. Depois da recusa, o item volta ao menu do mesmo item ou continua indo para depois, como hoje? Resposta (dono, 2026-11-26): volta ao menu do mesmo item.
- [x] Q3. Quando o item não tem detalhe técnico, a tecla `e` continua escondida ou aparece sempre? Resposta (dono, 2026-11-26): continua escondida, e as mensagens citam só as teclas que estão na tela.
- [x] Q4. O caminho "deixar para depois e tirar a dúvida numa sessão de chat" entra só como frase na tela, ou o painel entrega algo pronto para colar na sessão? Resposta (dono, 2026-11-26): só uma frase na ajuda do Enter, citando a fila e o item. Nenhum mecanismo novo.
- [x] Q5. Se o dono responde "não" à confirmação "isso é uma dúvida sobre a pergunta?", o texto é gravado como resposta ou o painel volta ao menu sem gravar? Resposta (dono, 2026-11-26): grava como resposta, sem mais perguntas além da que já existe sobre devolver o item à fila.
- [x] Q6. A reescrita com a dúvida digitada conta no limite de uma reescrita por item, ou é permitida uma vez mesmo depois de um `?` sem texto? Resposta (dono, 2026-11-26): é permitida mais uma com a dúvida. Até duas reescritas por item.
- [x] Q7. A tecla `?` passa a pedir, em uma linha opcional, o que o dono não entendeu? Resposta (dono, 2026-11-26): sim, linha opcional, Enter pula.

## Decided without asking
- A recusa de `cepa-queue answer` na linha de comando continua citando `--force`, porque lá a opção existe. Só o painel deixa de mostrar essa frase. Vete aqui se discordar.
- As frases novas do painel saem em inglês, como os outros rótulos fixos (decisão do item `interface-in-english`, 2026-10-23). Vete aqui se discordar.
- O texto exato das frases novas (legenda do `?`, legenda do Enter, linha de recusa) fica para a construção. Os critérios fixam só as palavras que o teste procura. Vete aqui se discordar.
- "Parece dúvida" usa a regra que já existe em `not_an_answer`: texto que termina em `?` ou que pede esclarecimento ("não entendi", "como assim"). Uma regra só evita o painel aceitar o que `cepa-queue answer` recusa. Vete aqui se discordar.
- Na confirmação "Is this a doubt about the question? [Y/n]", Enter vale sim. Quem digita uma pergunta quase sempre está perguntando. Vete aqui se discordar.
- A confirmação de dúvida vem antes de "Send the item back to the queue with that answer?". Com não, essa segunda pergunta aparece como hoje. Vete aqui se discordar.
- A regra das duas reescritas: a primeira sempre acontece, com ou sem dúvida escrita. A segunda só acontece com dúvida escrita. Não há terceira. Vete aqui se discordar.
- Em item sem rota aberta para reescrever (item já entregue ou sem pendência humana), a dúvida digitada é registrada no feedback e o item fica para depois, como a tecla `?` já faz nesse caso. Vete aqui se discordar.
- A linha de feedback de `cepa-feedback add` passa a trazer a dúvida do dono junto com a pergunta. É o que a triagem precisa para saber qual termo estava obscuro. Vete aqui se discordar.
- A volta ao menu do mesmo item vale para a recusa por texto que não é resposta (código 6 de `cepa-queue answer`). Outras falhas de gravação continuam mandando o item para depois, como hoje. Vete aqui se discordar.
- A dúvida do dono não é gravada no `queue.yaml`. A regra da fila é que a reescrita nunca toca `human_pending`, `status` nem `evidence` (decisão de `perguntas-da-largada-legiveis`). Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- A reescrita pode continuar sem explicar o termo. O leitor é só leitura e pode não achar no repositório o que é "variante O". Nesse caso o dono usa Enter e leva a dúvida a uma sessão de chat.
- Até duas reescritas somam até 120 segundos de espera num item (2 × 60 s, o teto de `UNCLEAR_REWRITE_SEC`).
- Resposta legítima que termina em `?` ganha uma pergunta a mais (a confirmação de dúvida). É o custo de não gravar dúvida como resposta.
- A causa de origem, a pergunta do C1-47 usar "variante O" sem apresentar o termo, não é tratada aqui.
