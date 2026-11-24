# Especificação: próximo passo quando o dono abre a sessão sem saber o que fazer

**Status:** ready-to-build
**Aberta em:** 2026-11-23      **Fechada em:** 2026-11-24
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
- Um subcomando novo do `cepa-plan` (o programa que já lê filas e Epics), chamado aqui de `cepa plan propose`, que lista os candidatos a próxima meta na ordem das fontes e imprime UMA ação.
- Três situações: todas as filas terminadas, repositório sem fila nenhuma, fila em que tudo o que sobra espera o dono.
- Com várias filas abertas e itens prontos, a ação é `cepa until --all --until 06:00` (o `cepa until` é o supervisor que roda as filas sem o dono presente, e `--all` roda todas).
- Um comando novo, `/common:whatnext` (o dono pediu `/whatnext`; comando de plugin leva o prefixo do plugin), que roda o `cepa plan propose` e mostra a resposta. É o único jeito de pedir a resposta.
- Formato da resposta: uma ação, o porquê em uma linha, a contagem do que mais espera o dono. A ação é a última linha.
- O `/common:whatnext` só indica: não grava fila, não grava intenção, não executa item. A ação é um comando que o dono roda.
- Sempre que a ação indicada é construir algo, o comando é o `cepa until` (em renome para `cepa run`): uma fila com item pronto dá `cepa until <fila> --until 06:00`.
- A recusa é um comando à parte (`cepa plan propose --decline`), que o dono roda. Ela fica gravada e a chamada seguinte traz o segundo candidato, até 2 propostas.
- A frase de beco sem saída do `/common:next` e do `/common:whereami` passa a ser "rode /common:whatnext".
- Sem nenhuma fonte: uma pergunta ("o que você quer ver funcionando aqui?") acompanhada de sugestões tiradas da leitura do código, e a resposta abre `/common:spec`.

### Não entra
- Mostrar a resposta sozinha na abertura da sessão. O dono respondeu "só quando eu perguntar".
- Adaptar o `/common:next` e o `/common:whereami` para dar a resposta, e gatilho por texto livre. O dono vetou em 2026-11-24: "quanto mais determinístico, melhor".
- Mudar a leitura do Jira. Com `board-flow.yaml` reconcilia como hoje, com `--offline` não.
- Escolher entre várias filas abertas dentro da sessão. O dono pediu a sugestão do `cepa until`, não uma escolha de fila.
- Fila com item pronto e uma fila só. O `/common:next` já responde esse caso.

## Estado e migração
- Arquivo novo `common/commands/whatnext.md`.
- `common/commands/next.md`: onde hoje manda nomear o `/common:queue` com a fila terminada ou ausente, passa a mandar dizer "rode /common:whatnext". O resto não muda, inclusive a regra "nunca inventa ordem", que continua valendo para ele.
- `cepa-intent state` no estado `empty`: a frase "Diga o propósito e eu proponho o plano" ganha "ou rode /common:whatnext".
- Arquivo novo de propostas recusadas, gravado só pelo `cepa-plan`, no clone principal ao lado das filas. Repositórios existentes começam sem o arquivo, e a ausência significa "nada recusado".
- Filas existentes não mudam. Itens descartados continuam descartados até o dono aceitar uma proposta que os traga de volta.

## Critérios de sucesso

### CS-1: com todas as filas terminadas e um ciclo de Epic sem fila, a saída propõe esse ciclo
**Surface:** cli
**Red test:** num repositório de teste com uma fila toda `done` e um Epic com o ciclo 2 sem fila, `cepa plan propose` imprime uma proposta cuja fonte é o Epic e cuja ação é `/common:queue <nome> --from-epic <arquivo> --cycle 2`; hoje o subcomando não existe e o `cepa-plan` sai com erro de uso.

### CS-2: a ordem entre as fontes é Epic, especificação pronta, meta gravada, descartados, cards soltos, BACKLOG
**Surface:** cli
**Red test:** com uma especificação `ready-to-build` sem fila e itens `dropped` na última fila, `cepa plan propose` propõe a especificação; tirando a especificação, propõe os itens descartados; com um lembrete do dono que nomeia uma meta e itens descartados, propõe a meta do lembrete com a data dele; hoje o subcomando não existe.

### CS-3: a saída tem uma ação só, na última linha, e conta o resto sem listar
**Surface:** cli
**Red test:** com 3 pendências do dono que não impedem a meta e 2 cards fora de fila, a última linha de `cepa plan propose` é a ação da meta, uma linha anterior diz "mais 5 coisas esperam você" (3 + 2) e nenhuma das 5 aparece pelo nome; com `--detail` as 5 aparecem; hoje o subcomando não existe.

### CS-4: repositório sem fila nenhuma recebe a mesma proposta
**Surface:** cli
**Red test:** num repositório sem `.claude/queues` e com uma especificação `ready-to-build`, `cepa plan propose` propõe a especificação com a ação `/common:queue <nome> --from-spec`; hoje o subcomando não existe e o `/common:next` manda dizer "não há plano".

### CS-5: fila em que tudo o que sobra espera o dono aponta a pendência que destrava mais itens
**Surface:** cli
**Red test:** numa fila com 4 itens `pending`, em que a pendência do item A bloqueia 2 itens e a do item B bloqueia 1, a ação de `cepa plan propose` é a pergunta fechada da pendência de A, e a de B entra na contagem; empate se resolve pela ordem da fila; hoje o subcomando não existe.

### CS-6: com várias filas abertas e itens prontos, a ação é um comando do `cepa until`
**Surface:** cli
**Red test:** com duas filas que têm item pronto, a última linha de `cepa plan propose` é `cepa until --all --until 06:00` e nenhuma pergunta "qual fila?" aparece; hoje o subcomando não existe.

### CS-7: sem nenhuma fonte, a saída diz que não achou e traz a pergunta
**Surface:** cli
**Red test:** num repositório sem Epic, sem especificação, sem lembrete, sem fila e sem BACKLOG.md, `cepa plan propose` sai com código 0, diz "nenhuma fonte" e imprime a pergunta "O que você quer ver funcionando aqui?"; hoje o subcomando não existe.

### CS-8: o "não" fica gravado, traz o segundo candidato e para na segunda recusa
**Surface:** cli
**Red test:** depois de `cepa plan propose --decline <id> --reason "..."`, a chamada seguinte propõe o segundo candidato e não repete o primeiro; depois da segunda recusa a saída traz a pergunta do CS-7 em vez de uma terceira proposta; numa chamada de outro dia o candidato recusado continua fora; `cepa plan propose --declined` lista as recusas com data e motivo, e `--undecline <id>` devolve o candidato à lista; hoje o subcomando não existe.

### CS-9: a fila que nasce de uma proposta aceita diz de onde veio
**Surface:** cli
**Red test:** depois de o dono rodar o comando indicado por uma proposta de itens descartados, `cepa plan show <fila>` mostra em cada item o porquê "proposta do agente, aceita pelo dono em <data>"; hoje não há como gravar uma fila a partir de uma proposta.

### CS-10: existe o comando `/common:whatnext`, e ele só mostra o que o `cepa plan propose` imprime
**Surface:** cli
**Red test:** um teste que lê `common/commands/whatnext.md` exige que o arquivo exista, que ele se declare somente leitura, que o único programa que ele manda rodar seja `cepa plan propose` e que mande mostrar a saída sem reescrever a ação; hoje o arquivo não existe.

### CS-11: com uma fila só e item pronto, a ação é executar esse item, e nada é executado
**Surface:** cli
**Red test:** numa fila com o item B1 pronto, a última linha de `cepa plan propose` é `cepa until <fila> --until 06:00`, o porquê é o do item B1 e, depois da chamada, o `queue.yaml` está byte a byte igual e B1 continua `pending` sem reserva; hoje o subcomando não existe.

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
- Proposta recusada fica fora até o dono nomeá-la ele mesmo; não expira com o tempo — uma recusa que expira volta a ser a mesma pergunta. Vete aqui se discordar.
- "Até 2 propostas" conta por dia e por repositório, não por sessão — o `cepa-plan` não sabe de sessão, e a data ele sabe. Vete aqui se discordar.

- Quando a ação indicada é construir algo, o comando é o cepa until (em renome para cepa run): com uma fila, cepa until <fila> --until 06:00; com várias, cepa until --all --until 06:00. A saída usa o nome que o programa tiver no dia da construção. O dono pediu em 2026-11-24 que a construção priorize o cepa until. · refinada em 2026-11-24
- O comando de recusa aparece na penúltima linha da resposta ("se não for isso: cepa plan propose --decline <id>"), para a ação continuar sendo a última — sem isso o dono não tem como saber o identificador da proposta. Vete aqui se discordar.

- A recusa tem como ser vista e desfeita: `cepa plan propose --declined` lista e `--undecline <id>` desfaz — sem isso uma recusa por engano tira a meta da lista para sempre. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- O renome de `cepa until` para `cepa run` está em andamento na branch `session/command_rename`. Os testes vermelhos citam `cepa until`; quem construir usa o nome vigente.
- A parte redigida pelo agente (a frase da proposta, as sugestões do CS-7) não tem teste mecânico. Os critérios cobrem a saída do `cepa-plan`, que é o que o agente recebe.
- O texto de ajuda do `cepa until` ainda diz que `--all` só roda com `--dry-run`, o que é falso desde pelo menos 2026-11-15 (data do registro de run mais antigo em `_all/until/`). Corrigir a ajuda fica fora desta especificação.
- Itens descartados (fonte 4) podem ter sido descartados de propósito. A proposta os traz de volta só com o sim, e o não fica gravado (CS-8).
- Ficou de fora: escolher entre várias filas dentro da sessão, e mostrar o próximo passo na abertura da sessão.
