# Especificação: próximo passo quando o dono abre a sessão sem saber o que fazer

**Status:** ready-to-build
**Aberta em:** 2026-11-23   **Fechada em:** 2026-11-24
**Fontes lidas:** common/commands/whereami.md, common/commands/next.md, BACKLOG.md (entrada de `fb-20261104-3`), docs/spec/resposta-do-decide-vira-trabalho.md, docs/spec/perguntar-antes-do-run.md, docs/spec/until-todas-as-filas.md, saída de `cepa-plan --help`, `cepa-plan epics`, `cepa-intent --help` e `cepa-until --help`

## Como chegamos aqui
Em 2026-11-23 o dono disse: "Esta é uma situação muito recorrente para a qual eu te peço uma solução. Eu entro no repositório de um projeto, abro uma sessão interativa do Claude, não faço ideia do que fazer e o comando whereami não é capaz de me ajudar." Junto veio a captura de tela de uma sessão no repositório wego-digitacao-backend.

## Problema
O dono abre uma sessão interativa e pergunta "Qual o atual status do projeto? O que devo fazer agora?". Na captura, as duas filas do repositório estavam terminadas (assinaturas-sim-nao com 7 de 7 itens, kairos-etapa-1 com 41 itens, 30 concluídos e 11 descartados). A resposta listou 3 pendências com o dono, 2 cards fora de fila, terminou em "montar a próxima fila com /common:queue" e devolveu a pergunta "essa meta ainda vale?". O dono saiu sem saber o que fazer.

O que os comandos fazem hoje, lido no código:
- `/common:whereami` sem intenção gravada na sessão responde "Diga o propósito e eu proponho o plano". Ele só sabe da sessão, e uma sessão recém-aberta não tem nada.
- `/common:next` com a fila terminada tem a regra escrita "Do not manufacture a next step from an empty plan" e "Never invents an order". Por desenho ele para em "não há próximo item" e aponta o comando que monta outra fila.

## Escopo
### Entra
- Um subcomando novo do `cepa-plan` (o programa que já lê filas e Epics), chamado aqui de `cepa plan propose`, que lista os candidatos a próximo passo na ordem das fontes e imprime um menu numerado.
- Três situações: todas as filas terminadas, repositório sem fila nenhuma, fila em que tudo o que sobra espera o dono.
- Com várias filas abertas e itens prontos, a opção 1 é `cepa until --all --until 06:00` (o `cepa until` é o supervisor que roda as filas sem o dono presente, e `--all` roda todas).
- Um comando novo, `/common:whatnext` (o dono pediu `/whatnext`; comando de plugin leva o prefixo do plugin), que roda o `cepa plan propose` e mostra a resposta. É o único jeito de pedir a resposta.
- Formato da resposta: um menu de até 10 opções numeradas, na ordem das fontes, a primeira marcada "(recomendado)", cada uma com o porquê em uma linha. Depois a opção `0) Outra coisa`, a contagem do que mais espera o dono e a linha que ensina a responder.
- Cada opção aceita duas letras: `R` (Run, rodar) e `D` (Detail, detalhe). O dono responde `2r` ou `2d` dentro da sessão.
- Mostrar o menu não grava fila, não grava intenção e não executa nada. Só o `<n>r` do dono executa, e executa na própria sessão.
- Sempre que a ação indicada é construir algo, o comando é o `cepa until` (em renome para `cepa run`): uma fila com item pronto dá `cepa until <fila> --until 06:00`.
- A frase de beco sem saída do `/common:next` e do `/common:whereami` passa a ser "rode /common:whatnext".
- Sem nenhuma fonte: uma pergunta ("o que você quer ver funcionando aqui?") acompanhada de sugestões tiradas da leitura do código, e a resposta abre `/common:spec`.

### Não entra
- Mostrar a resposta sozinha na abertura da sessão. O dono respondeu "só quando eu perguntar".
- Adaptar o `/common:next` e o `/common:whereami` para dar a resposta, e gatilho por texto livre. O dono vetou em 2026-11-24: "quanto mais determinístico, melhor".
- Mudar a leitura do Jira. Com `board-flow.yaml` reconcilia como hoje, com `--offline` não.
- Escolher entre várias filas abertas dentro da sessão. O dono pediu a sugestão do `cepa until`, não uma escolha de fila.
- Gravar o que o dono não escolheu, ou esconder opção do menu. Escolher outra opção já é o não.
- Proposta única com "sim/não". O dono trocou pelo menu em 2026-11-24.

## Estado e migração
- Arquivo novo `common/commands/whatnext.md`.
- `common/commands/next.md`: onde hoje manda nomear o `/common:queue` com a fila terminada ou ausente, passa a mandar dizer "rode /common:whatnext". O resto não muda, inclusive a regra "nunca inventa ordem", que continua valendo para ele.
- `cepa-intent state` no estado `empty`: a frase "Diga o propósito e eu proponho o plano" ganha "ou rode /common:whatnext".
- Nenhum arquivo novo de estado: o menu é recalculado a cada chamada.
- Filas existentes não mudam. Itens descartados continuam descartados até o dono aceitar uma proposta que os traga de volta.

## Critérios de sucesso

### CS-1: com todas as filas terminadas e um ciclo de Epic sem fila, a opção 1 é montar a fila desse ciclo
**Surface:** cli
**Red test:** num repositório de teste com uma fila toda `done` e um Epic com o ciclo 2 sem fila, a opção 1 de `cepa plan propose` tem como fonte o Epic, traz "(recomendado)" e o comando dela é `/common:queue <nome> --from-epic <arquivo> --cycle 2`; hoje o subcomando não existe e o `cepa-plan` sai com erro de uso.

### CS-2: a ordem das opções segue as fontes: Epic, especificação pronta, meta gravada, descartados, cards soltos, BACKLOG
**Surface:** cli
**Red test:** com um ciclo de Epic sem fila, uma especificação `ready-to-build` sem fila, um lembrete do dono que nomeia uma meta e itens `dropped` na última fila, `cepa plan propose` lista as quatro opções nessa ordem, a do lembrete com a data dele; tirando o Epic, a especificação passa a ser a opção 1; hoje o subcomando não existe.

### CS-3: a saída é um menu de até 10 opções, com a opção 0 e a contagem do resto
**Surface:** cli
**Red test:** com 12 candidatos, 3 pendências do dono que não impedem nenhum deles e 2 cards fora de fila, `cepa plan propose` imprime as opções 1 a 10 (cada uma com uma linha de porquê, só a 1 com "(recomendado)"), depois `0) Outra coisa`, depois uma linha que diz que 2 candidatos ficaram de fora (12 - 10) e que mais 5 coisas esperam o dono (3 + 2), sem nomear nenhuma, e a última linha ensina `<n>r` e `<n>d`; hoje o subcomando não existe.

### CS-4: repositório sem fila nenhuma recebe o mesmo menu
**Surface:** cli
**Red test:** num repositório sem `.claude/queues` e com uma especificação `ready-to-build`, a opção 1 de `cepa plan propose` é a especificação, com o comando `/common:queue <nome> --from-spec`; hoje o subcomando não existe e o `/common:next` manda dizer "não há plano".

### CS-5: fila em que tudo o que sobra espera o dono põe na opção 1 a pendência que destrava mais itens
**Surface:** cli
**Red test:** numa fila com 4 itens `pending`, em que a pendência do item A bloqueia 2 itens e a do item B bloqueia 1, a opção 1 de `cepa plan propose` é a pergunta fechada da pendência de A e a opção 2 é a de B; empate se resolve pela ordem da fila; hoje o subcomando não existe.

### CS-6: com várias filas abertas e itens prontos, a opção 1 é rodar todas com o `cepa until`
**Surface:** cli
**Red test:** com duas filas que têm item pronto, o comando da opção 1 de `cepa plan propose` é `cepa until --all --until 06:00` e nenhuma pergunta "qual fila?" aparece; hoje o subcomando não existe.

### CS-7: sem nenhuma fonte, o menu só tem a opção 0 e a pergunta
**Surface:** cli
**Red test:** num repositório sem Epic, sem especificação, sem lembrete, sem fila e sem BACKLOG.md, `cepa plan propose` sai com código 0, diz "nenhuma fonte", imprime só `0) Outra coisa` e a pergunta "O que você quer ver funcionando aqui?"; hoje o subcomando não existe.

### CS-8: o detalhe de uma opção mostra a fonte, o porquê, o comando exato e o que ele altera, e não grava nada
**Surface:** cli
**Red test:** `cepa plan propose --detail 2` imprime, para a opção 2 do menu, o caminho do arquivo de onde ela veio, o porquê completo, o comando que o `R` roda e o que esse comando altera; `--detail` sem número lista pelo nome as coisas que esperam o dono e não viraram opção; `--detail 11` num menu de 3 opções sai com erro que diz quantas opções existem; depois de qualquer dessas chamadas nenhum arquivo do repositório mudou; hoje o subcomando não existe.

### CS-9: a fila que nasce de uma opção rodada diz de onde veio
**Surface:** cli
**Red test:** depois de rodar o comando de uma opção de itens descartados, `cepa plan show <fila>` mostra em cada item o porquê "proposta do agente, aceita pelo dono em <data>"; hoje não há como gravar uma fila a partir de uma opção do menu.

### CS-10: existe o comando `/common:whatnext`, com as respostas `<n>r` e `<n>d`
**Surface:** cli
**Red test:** um teste que lê `common/commands/whatnext.md` exige que o arquivo exista, que ele mande mostrar o menu do `cepa plan propose` sem reordenar nem renumerar, que diga que `<n>r` roda o comando que o `cepa plan propose --detail <n>` imprime e nenhum outro, que `<n>d` e `<n>` sozinho mostram o detalhe, que `0` faz a pergunta "O que você quer ver funcionando aqui?" e que nada é executado antes de um `<n>r` do dono; hoje o arquivo não existe.

### CS-11: com uma fila só e item pronto, a opção 1 é rodar a fila, e mostrar o menu não mexe nela
**Surface:** cli
**Red test:** numa fila com o item B1 pronto, o comando da opção 1 de `cepa plan propose` é `cepa until <fila> --until 06:00`, o porquê é o do item B1 e, depois da chamada, o `queue.yaml` está byte a byte igual e B1 continua `pending` sem reserva; hoje o subcomando não existe.

### CS-12: os comandos antigos apontam o novo no beco sem saída
**Surface:** cli
**Red test:** numa sessão sem `.claude/session-intent`, `cepa-intent state` imprime `state: empty` e uma frase que contém `/common:whatnext`; e um teste que lê `common/commands/next.md` exige `/common:whatnext` no trecho da fila terminada; hoje nenhum dos dois cita o comando.

## Perguntas em aberto
- [x] Q1. Na captura de tela, qual teria sido a última linha certa da resposta? — Próxima meta proposta: "Próximo: PoC web da leitura de guias, começando pela tela de upload. Diga sim e eu monto a fila e começo." (dono, 2026-11-23)
- [x] Q2. Com a fila terminada, o agente pode propor sozinho a próxima meta e a ordem dos itens, para o dono só dizer sim? — Sim, como proposta: UMA meta com a ordem, marcada como proposta do agente, e só vira fila com o sim do dono. (dono, 2026-11-23)
- [x] Q3. A resposta deve aparecer sozinha na abertura da sessão, ou só quando o dono perguntar? — Só quando o dono perguntar: texto livre ("o que faço agora?") e `/common:next` dão a mesma resposta, e `/common:whereami` sem intenção gravada entrega essa resposta. (dono, 2026-11-23)
- [x] Q4. O que não é a ação escolhida (outras pendências, cards fora de fila, estado das filas) aparece na resposta? — Só a contagem: uma ação, o porquê em uma linha, e quantas outras coisas esperam o dono, com o detalhe sob pedido. (dono, 2026-11-23)
- [x] Q5. De onde sai a meta proposta, e em que ordem de preferência entre as fontes? — (1) ciclo de Epic sem fila, (2) especificação pronta sem fila, (3) meta que o dono gravou em lembrete ou memória, (4) itens descartados da última fila, (5) cards soltos em To Do, (6) BACKLOG.md. (dono, 2026-11-23)
- [x] Q6. Quais becos sem saída entram? — Todas as filas terminadas, repositório sem fila nenhuma, fila travada no dono. E, nas palavras do dono: "Se houver várias filas abertas, sugira um cepa until --all". (dono, 2026-11-23)
- [x] Q7. Quando nenhuma fonte tem candidato, o que a resposta faz? — Nas palavras do dono: "Que tal o item (1) a partir de algumas sugestões da leitura do código?". Lido como: a pergunta "o que você quer ver funcionando aqui?" que abre `/common:spec`, acompanhada de sugestões tiradas da leitura do código. (dono, 2026-11-23)
- [x] Q8. Quando o dono responde "não" à proposta, o que vem em seguida? — Próximo candidato, até 2 propostas; depois pergunta o que o dono quer. O não fica gravado para a meta não voltar. (dono, 2026-11-23)
- [x] Q9. O texto de ajuda do `cepa until` diz que `--all` só roda com `--dry-run`. Com várias filas abertas, o que a ação sugere? — Nas palavras do dono: "O cepa until --all está pronto sim. Estou utilizando-o neste exato momento!". Conferido: há 4 registros de run em `.claude/queues/_all/until/` do clone principal, o mais novo de 2026-11-23, e o código não recusa `--all` sem `--dry-run`. O texto de ajuda está desatualizado. A ação sugere `--all`. (dono, 2026-11-24)
- [x] Q11. Como a resposta é pedida? — Nas palavras do dono: "Prefiro muito mais um novo comando do que a adaptação de comandos existentes ou o uso de texto livre. Pra mim, quanto mais determinístico, melhor. Que tal um comando `/whatnext`?". Substitui a parte da Q3 que punha a resposta no `/common:next`, no `/common:whereami` e no texto livre. (dono, 2026-11-24)
- [x] Q12. O `/common:next` e o `/common:whereami` ficam intocados, ou a frase de beco sem saída deles passa a nomear o `/common:whatnext`? — Só apontam o comando novo: continuam como são, e a frase final do beco sem saída passa a ser "rode /common:whatnext". (dono, 2026-11-24)
- [x] Q13. O `/common:whatnext` responde também quando há uma fila só com item pronto? — Nas palavras do dono: "Eu não quero que o whatnext execute nada, apenas indique o próximo passo. Nesse caso, seu resultado seria similar a um common:next --dry-run". Lido como: responde sempre, inclusive com item pronto, e nunca grava nem executa. (dono, 2026-11-24)
- [x] Q14. Com item pronto, que comando a ação indica? — Nas palavras do dono: "Gostaria que, quando a ação sugerida com a construção de algo, que se priorizasse o `cepa until` (que está sendo renomeado para `cepa run`)". (dono, 2026-11-24)
- [x] Q15. Proposta única com "não" na sessão, ou menu de opções? — Nas palavras do dono: "Troca pelo menu. Mas acho que pode apresentar mais opções. Que tal 10?". Substitui a Q4 (uma ação só) e a Q8 (recusa gravada). (dono, 2026-11-24)
- [x] Q16. Ao escolher uma opção, o agente executa na sessão? — Nas palavras do dono: "E se houver múltiplas opções para cada item do menu? Exemplo: (R)un, (D)etail". Lido como: cada opção tem `R` para rodar na sessão e `D` para ver o detalhe. Substitui a parte da Q13 que dizia "nunca executa". (dono, 2026-11-24)
- [x] Q10. Que janela de tempo vai no comando `cepa until` sugerido? — `--until 6:00`. (dono, 2026-11-24)

## Decided without asking
- O arquivo se chama `proximo-passo-sem-fila` — o caso da captura é fila terminada; se o escopo crescer para "fila com itens", o nome continua servindo de rótulo. Vete aqui se discordar.
- Não nasce comando novo: a resposta mora no `/common:next`, e o `/common:whereami` sem intenção gravada chama o `/common:next` — a resposta à Q3 pede a mesma resposta nos dois, e duas implementações divergem. Vete aqui se discordar. · vetada em 2026-11-24: O dono prefere um comando novo a adaptar comandos existentes ou usar texto livre: quanto mais determinístico, melhor. Pediu /whatnext.
- A lista de candidatos e a ordem entre eles saem de um subcomando do `cepa-plan` (o programa que já lê filas e Epics), e o agente só redige a frase — regra em prosa dentro do comando não tem teste, e o `/common:next` já faz assim na reconciliação com o Jira. Vete aqui se discordar.
- Pendência do dono só vira a ação principal quando impede a meta proposta; as outras entram na contagem — segue da resposta à Q1, em que 3 pendências que não impediam trabalho novo perderam para a meta. Vete aqui se discordar.
- Quando a meta proposta vem de uma decisão antiga do dono, a frase cita a data e o contexto, e rodar o comando indicado vale como 'ainda vale'; não há segunda pergunta. · refinada em 2026-11-24
- O /common:whatnext não grava nem executa nada: a ação é um comando que o dono roda (por exemplo /common:queue <nome> --from-epic ...). Rodar esse comando é o aceite; a fila que nasce dele leva em cada item o porquê 'proposta do agente, aceita pelo dono em <data>'. O dono disse em 2026-11-24: 'não quero que o whatnext execute nada, apenas indique o próximo passo'. · refinada em 2026-11-24
- A leitura do Jira antes de responder fica como está hoje (com `board-flow.yaml` reconcilia, com `--offline` não) — o pedido é sobre o que a resposta diz, não sobre de onde lê os status. Vete aqui se discordar.
- Na fonte 3, o `cepa-plan` lê sozinho os lembretes do dono (`.claude/reminders`); a memória do agente não é arquivo do repositório, então o agente lê a memória e passa a meta ao `cepa plan propose` por argumento, com a data — o programa não enxerga a pasta de memória do Claude. Vete aqui se discordar.
- Pergunta em texto livre não ganha gatilho novo (hook ou skill) — na captura o agente já levou a pergunta livre ao `/common:next` sozinho; o que faltou foi a resposta. Vete aqui se discordar.
- Sem fonte, as sugestões da leitura do código são no máximo 3 e redigidas pelo agente; o `cepa-plan` só avisa "nenhuma fonte" — ler código para sugerir meta não é coisa que um programa sem modelo faz. Vete aqui se discordar.
- Proposta recusada fica fora até o dono nomeá-la ele mesmo; não expira com o tempo — uma recusa que expira volta a ser a mesma pergunta. Vete aqui se discordar. · vetada em 2026-11-24: O menu de opções substitui a recusa: escolher outra opção já é o não, e nada fica gravado. Decidido pelo dono em 2026-11-24 ("Troca pelo menu").
- "Até 2 propostas" conta por dia e por repositório, não por sessão — o `cepa-plan` não sabe de sessão, e a data ele sabe. Vete aqui se discordar. · vetada em 2026-11-24: O menu de opções substitui a recusa: escolher outra opção já é o não, e nada fica gravado. Decidido pelo dono em 2026-11-24 ("Troca pelo menu").

- Quando a ação indicada é construir algo, o comando é o cepa until (em renome para cepa run): com uma fila, cepa until <fila> --until 06:00; com várias, cepa until --all --until 06:00. A saída usa o nome que o programa tiver no dia da construção. O dono pediu em 2026-11-24 que a construção priorize o cepa until. · refinada em 2026-11-24
- O comando de recusa aparece na penúltima linha da resposta ("se não for isso: cepa plan propose --decline <id>"), para a ação continuar sendo a última — sem isso o dono não tem como saber o identificador da proposta. Vete aqui se discordar. · vetada em 2026-11-24: O menu de opções substitui a recusa: escolher outra opção já é o não, e nada fica gravado. Decidido pelo dono em 2026-11-24 ("Troca pelo menu").

- A recusa tem como ser vista e desfeita: `cepa plan propose --declined` lista e `--undecline <id>` desfaz — sem isso uma recusa por engano tira a meta da lista para sempre. Vete aqui se discordar. · vetada em 2026-11-24: O menu de opções substitui a recusa: escolher outra opção já é o não, e nada fica gravado. Decidido pelo dono em 2026-11-24 ("Troca pelo menu").

- Número sem letra mostra o detalhe, não roda (`2` é o mesmo que `2d`) — um número digitado por engano não inicia um `cepa until` de horas. Vete aqui se discordar. · mantida em 2026-11-24
- O detalhe de uma opção mostra quatro coisas: de que fonte ela veio (com o caminho do arquivo), o porquê completo, o comando exato que o `R` vai rodar e o que esse comando altera. Vete aqui se discordar.
- A opção "Outra coisa" é sempre a `0` e não conta nas 10 — assim o número dela não muda de uma chamada para outra. Vete aqui se discordar.
- Dentro de uma mesma fonte, os candidatos saem na ordem do arquivo (ciclos do Epic pelo número, especificações pelo nome) — ninguém priorizou entre eles. Vete aqui se discordar.
- Quando sobram candidatos além dos 10, a linha de contagem diz quantos ficaram de fora. Vete aqui se discordar.
- `d` sem número lista as coisas que esperam o dono e que não viraram opção. Vete aqui se discordar.
- O `R` de uma opção que é `cepa until` inicia o comando em segundo plano na sessão — ele roda por horas e a sessão não pode ficar presa. Vete aqui se discordar.
- O `R` de uma opção que nasce de decisão antiga do dono vale como "ainda vale", e a fila que nasce de um `R` leva em cada item o porquê "proposta do agente, aceita pelo dono em <data>". Substitui o texto das decisões 5 e 6, que falavam de comando rodado por fora. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- O renome de `cepa until` para `cepa run` está em andamento na branch `session/command_rename`. Os testes vermelhos citam `cepa until`; quem construir usa o nome vigente.
- A parte redigida pelo agente (a frase da proposta, as sugestões do CS-7) não tem teste mecânico. Os critérios cobrem a saída do `cepa-plan`, que é o que o agente recebe.
- O texto de ajuda do `cepa until` ainda diz que `--all` só roda com `--dry-run`, o que é falso desde pelo menos 2026-11-15 (data do registro de run mais antigo em `_all/until/`). Corrigir a ajuda fica fora desta especificação.
- Itens descartados (fonte 4) podem ter sido descartados de propósito e voltam a aparecer no menu a cada chamada, porque nada do que o dono deixa de escolher fica gravado.
- Com 10 opções o menu ocupa cerca de 25 linhas (10 opções com porquê, mais o cabeçalho e o rodapé). O dono pediu 10 em 2026-11-24.
- Ficou de fora: escolher entre várias filas dentro da sessão, e mostrar o próximo passo na abertura da sessão.
