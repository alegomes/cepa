## Painel de advisors — `docs/estrategia-durabilidade.md` (area: `arquitetura`, 7 lenses)

Rodado em 2026-11-05 sobre a revisão 1 do documento. 66 achados: contrarian 10, fundamentalista 9, expansionista 8, outsider 10, executor 11, operador-sre 10, custo-de-manutenção 8. Síntese pelo orquestrador da sessão. Toda afirmação de lente usada abaixo foi conferida no disco antes de entrar; as conferências estão na seção "Conferências" e corrigem dois números do próprio documento.

**Vereditos por lente**

- contrarian: "O1 itens 2, 3 e 5 são razoáveis (o item 2 fica melhor com `--session-id`), mas o item 1 como escrito barra a operação normal do dia seguinte, O2 persegue um problema que os próprios ledgers não mostram e o documento ignora a opção mais barata de todas, encolher o item."
- fundamentalista: "A tese respeita o desenho do cepa-until, mas repete a troca de decisão 3 por R1 que o painel anterior já condenou, apresenta como pendente uma garantia que o BACKLOG marca como feita, e deixa passar três quebras de doutrina (sexto depósito no O1.4, harness-ops no O1.5, escritor único da fila na pergunta 2)."
- expansionista: "O1 é o caminho certo, mas quatro dos cinco itens estão um grau estreitos demais: como módulo leitor, memo, fork e campo de motivo ao lado do session_id, entregam de graça o cockpit, a auditoria da tentativa cortada e a idempotência de Jira."
- outsider: "Memorando interno legível só por quem viveu as sessões: Cepa, cepa-until, item, fila e condutor nunca são enunciados, e a conta central (48 sem progresso = custo de não retomar) é um salto que o próprio texto desmente em O2."
- executor: "Dá para começar na segunda com o item 2 de O1 e nada mais: os outros quatro chegam sem decisão de desenho fechada, numa fila travada por human_pending, e O2 depende de uma semana de runs que ninguém está lançando."
- operador-sre: "O1 é operável, mas o documento não define um sinal de saúde do run em voo nem recuperação para as falhas novas que cria (start recusado por SHA, --resume que falha, finish de dois donos); O2 como está é um modo de falha a mais sem runbook."
- custo-de-manutenção: "Itens 1 e 2 de O1 pagam a própria carga; itens 3, 4, 5 e o flag de O2 criam conceitos permanentes para dores que o texto marca como não medidas, e a alternativa mais barata, eliminar depósitos e tornar efeitos idempotentes na origem, não foi considerada."

### Legenda

| código | lente | achado em uma frase |
|---|---|---|
| CR1 | contrarian | Os 48 encerramentos "sem progresso" não são cortes externos; `exit_code` já permite classificá-los hoje, e o corte por cota já é retomado no mesmo run. |
| CR2 | contrarian | A regra "SHA ancestral do HEAD" em `start` recusa toda manhã seguinte, porque a branch da noite nunca é ancestral do HEAD do clone até o dono mergear. |
| CR3 | contrarian | "Task de fundo pertence ao harness" não tem canal de retorno: um `claude -p` não recebe evento. |
| CR4 | contrarian | Falta a opção de encolher o item (sub-itens com `start`/`finish` próprios) em vez de retomar a conversa. |
| CR5 | contrarian | O número 72 de `hook_so_apos_reinstalar` não se reproduz; o defeito é quase exclusivo do repo do próprio Cepa. |
| CR6 | contrarian | `claude --session-id <uuid>` existe: o supervisor gera o id antes de lançar e nunca fica sem ele. |
| CR7 | contrarian | O2 retoma uma transcrição que acha que tem reserva assinada por um pid morto, num cwd que pode ter sumido, com contexto alto. |
| CR8 | contrarian | "Todo depósito novo nasce lido pelo leitor único" é convenção sem gate. |
| CR9 | contrarian | Itens de durabilidade na fila do ciclo 2 não aparecem no roteiro de demonstração do ciclo. |
| FU1 | fundamentalista | O documento cita "decisão 3" com o texto do R1, e a decisão 3 já foi revogada para filhos do condutor (D7 de 2026-10-08), justamente o ciclo 2. |
| FU2 | fundamentalista | A checagem de SHA ancestral já existe no supervisor desde 2026-09-28, com teste; o que falta é a fila gravar o SHA no `finish`. |
| FU3 | fundamentalista | O item 4 de O1 (efeitos externos já feitos) precisa de um escritor novo e é o sexto depósito que R3 proíbe. |
| FU4 | fundamentalista | Pôr itens ditados à mão em `cepa-espiral-c2` contorna o escritor único (`--from-epic`) e a coluna "Quando" do ciclo 2. |
| FU5 | fundamentalista | Hooks pelo clone ou reinstalação noturna quebram a rota de `docs/harness-ops.md` (Estado, Alvo, Rollback, Validação) sem declarar. |
| FU6 | fundamentalista | O2 toca o único comando de lançamento e não cita as provas `docs/proof/cepa-until*.yaml` que o Epic declara como invariante. |
| FU7 | fundamentalista | Aposentar o `no-background-build` reverte a decisão 5 do dono sobre X5 (2026-10-08) sem nomear. |
| EP1 | expansionista | O leitor dos cinco depósitos deve ser módulo importado por `next`, `doctor`, `until-review` e `whereami`, não um quinto comando leitor. |
| EP2 | expansionista | Ao lado do `session_id`, gravar a classificação do fim (`motivo_fim`) no `item_end`; sem ela a classificação dos 59 continua manual. |
| EP3 | expansionista | `--resume <id> --fork-session` preserva a transcrição da tentativa cortada como registro do abortado. |
| EP4 | expansionista | Idempotência de Jira como memo "primeira escrita vence" checado no hook `_jiramut`, que já intercepta toda mutação, e não no `drain-plan`. |
| EP5 | expansionista | Um `cepa build` entre turnos já cabe no supervisor de hoje; dentro do turno é caro. O documento tem de dizer qual dos dois quer. |
| EP6 | expansionista | A dor de "multijogador" no Cepa é a de dois agentes (sessão do dono e supervisor na mesma fila), já coberta por guards; a tabela diz "nenhum". |
| OU1 | outsider | Cepa, cepa-until, item, fila e `claude -p` nunca são definidos. |
| OU2 | outsider | A motivação (preparar o condutor) só aparece no fim da seção 3. |
| OU3 | outsider | "progresso: false" não é definido e não autoriza a leitura "custo de não retomar". |
| OU4 | outsider | Somas "24 + 21 + 8 + 3 + 2 + 1" sem rótulo das parcelas. |
| OU5 | outsider | "C4" nomeia duas coisas (diagnóstico deste documento e regra da revisão de 2026-09-26). |
| EX1 | executor | Os dois itens de `cepa-espiral-c2` carregam `human_pending` ligado ao Epic Contratos; cinco itens novos ali não rodam, ou furam a condição. |
| EX2 | executor | Item 1 não diz qual SHA (`finish --commit` só commita o `queue.yaml`), o que fazer com `done` sem commit, nem o que é "no meio". |
| EX3 | executor | Item 3 tem dois nomes, nenhum formato e nenhuma regra para depósito ausente ou congelado. |
| EX5 | executor | Item 5 oferece duas soluções com custos diferentes (61 hooks vs. uma linha no supervisor) e não escolhe. |
| EX6 | executor | "Uma semana de runs" não tem dono nem data; o último run é de 2026-10-25. |
| EX7 | executor | "Mesmo item com e sem retomada" não é executável; um corte real não se repete sob encomenda. |
| EX8 | executor | O2 precisa de um spike de uma hora: `--resume` depende do mesmo cwd, da transcrição não truncada por SIGKILL e da reserva órfã. |
| EX9 | executor | "Cada um cabe numa noite" não tem base; nenhum item tem critério de aceite observável. |
| SR1 | operador-sre | O2 sem fallback para processo novo, sem limite de uma retomada por item, sem evento `item_retomado` e sem número para "contexto cheio". |
| SR2 | operador-sre | A recusa de `start` por SHA trava a fila inteira numa madrugada (squash, rebase, patch da lateral) e não tem comando de desbloqueio. |
| SR3 | operador-sre | `cmd_finish` não compara `claimed_by` com o chamador nem exige `in_progress`: dois processos fecham o mesmo item e o segundo apaga a evidência. |
| SR4 | operador-sre | Nenhum caminho define saúde do run em voo; `estado.json: rodando` só diz que estava vivo quando gravou. Falta heartbeat. |
| SR5 | operador-sre | Item 4: a chave de idempotência deve morar no efeito (marcador `cepa:<run>/<item>` no comentário; checar status antes de transitar), não num log local. |
| SR6 | operador-sre | Troca de hooks a quente sem carimbo de versão em cada `item_start` deixa o diagnóstico às 3h sem saber qual código rodou. |
| SR7 | operador-sre | "Supervisor dono de todo build" herda cinco perguntas sem resposta: concorrência, árvore em edição, timeout, morte do supervisor, destino do resultado. |
| SR9 | operador-sre | Reserva de pid em outro host só expira por idade (24h): laptop fechado prende o item uma noite inteira sem evento. |
| CM1 | custo-de-manutenção | O leitor de cinco formatos congela os cinco para sempre; `estado.json` e o registro de sessões vivas são candidatos a eliminação. |
| CM2 | custo-de-manutenção | `--retomar-conversa` é um segundo caminho de lançamento sem critério de remoção. |
| CM3 | custo-de-manutenção | Item 1 vira a terceira guarda do mesmo invariante (com `reconcile` e a regra do BACKLOG) em vez de substituir as duas. |
| CM4 | custo-de-manutenção | Lista fechada de efeitos é conceito novo para dor não medida; idempotência na origem custa zero conceito. |
| CM5 | custo-de-manutenção | Hooks pelo clone é um ramo condicional em 61 arquivos; a reinstalação pelo supervisor é um comando a mais num lugar só. |
| CM7 | custo-de-manutenção | Itens 1 e 2 são garantia e medição; 3, 4 e 5 são conceitos permanentes. Não devem entrar na mesma fila com o mesmo rótulo. |

### Conferências

Feitas no disco depois do painel, porque três lentes contestaram números do documento.

- **Contagem de runs e de `hook_so_apos_reinstalar`.** Varredura explícita: todo `*.jsonl` em `.claude/queues/*/until/` e `.claude/programs/*/until/` abaixo de `~`, excluindo `Library`. 147 arquivos em 11 raízes (62 em `wego-acessos-backend`, 18 em cada uma das quatro cópias do repo cepa, o resto em outros repos wego). Chave de deduplicação: nome da fila + nome do arquivo, que colapsa as quatro cópias do cepa. Resultado: **93 runs únicos, 530 `item_end`**, como no documento. O número de `hook_so_apos_reinstalar` **estava errado: são 24, não 72** (15 na fila `cepa`, 4 em `intencao-c1`, 3 em `cepa-espiral-c1`, 2 em `fb-2026-10`; todos em filas do repo do próprio Cepa). CR5 confirmado; a divergência 88 vs 93 runs da contrarian vem de ela ter varrido só `queues/`.
- **Os 59 encerramentos sem fechar, por `exit_code`.** 40 saíram com código 0 (19 `pending` sem progresso, 11 `in_progress` sem progresso, 5 `pending` com progresso, 3 `pending` com progresso e `human_pending`, 2 `in_progress` com progresso); 15 saíram com código 1 (13 `in_progress`, 2 `pending`, nenhum com progresso); 4 saíram com código 143 (SIGTERM, os 4 `timeout: true`). Logo **40 dos 59 são o `claude -p` terminando por conta própria sem fechar o item**, e no máximo 19 (os de código 1 e 143) são candidatos a corte externo. CR1, OU3 e SR8 confirmados: a frase do documento "esses 48 são o custo de não retomar a conversa" não se sustenta.
- **`claude --session-id <uuid>`** existe no `claude --help` desta máquina (linha 224). CR6 confirmado.
- **`merge-base --is-ancestor`** aparece em 5 pontos do `cepa-until` (linhas 1316, 1516, 1746, 2817, 2907) e o BACKLOG marca a garantia das duas checagens como "Feito em 2026-09-28". FU2 confirmado: o que falta é só o `finish` gravar o SHA na fila.
- **`cmd_finish`** não tem nenhuma referência a `claimed_by`, `in_progress` ou estado terminal no corpo da função. SR3 confirmado.
- **`cepa-espiral-c2`**: C2-1 e C2-2 têm `human_pending` "Condição do Epic, coluna Quando". EX1 e FU4 confirmados.
- **`docs/harness-ops.md`**, `docs/proof/until-avisa-hook-so-vale-apos-reinstalar.yaml`, `docs/proof/cepa-until.yaml` e `docs/proof/cepa-until-cota.yaml` existem. FU5 e FU6 confirmados.
- **`common/bin/cepa-until`** tem 4.234 linhas, não 3.900. CR10, EX10 e CM8 confirmados.
- **Reserva em outro host** só expira por idade, texto literal em `cepa-plan:319-321`. SR9 confirmado.

### Convergências

1. **A atribuição dos 48 "sem progresso" ao custo de não retomar é falsa, e a classificação pode ser feita hoje.** CR1, OU3, SR8, EP2 (4 lentes). Conferido acima: 40 dos 59 saíram com código 0. O documento tem de corrigir a seção 2 e O2 perde a base numérica que tinha.
2. **O item 4 de O1 (efeitos externos não repetíveis) é um sexto depósito e deve virar idempotência no próprio efeito.** FU3, EX4, SR5, EP4, CM4 (5 lentes). Posição comum: a chave mora no Jira (marcador no comentário, status checado antes da transição) e a checagem fica no hook `_jiramut`, que já intercepta toda mutação. Nenhuma lente defendeu a lista fechada.
3. **O item 1 de O1 está subdefinido e, como escrito, barra a operação normal.** CR2, EX2, SR2, CM3, FU2 (5 lentes). Pontos: qual SHA (o `finish --commit` só commita o `queue.yaml`); `done` legítimo sem commit; "nenhum outro item fechou no meio" não definido; a branch da noite nunca é ancestral do HEAD do clone na manhã seguinte; a checagem já existe no supervisor por tentativa; precisa de comando de desbloqueio e de aposentar `reconcile` para esse caso.
4. **O item 5 de O1 tem de fechar na reinstalação pelo supervisor, não em hooks lendo do clone.** CM5, EX5, EP8 (3 lentes), com FU5 exigindo que a quebra de `harness-ops` seja declarada e SR6 exigindo o SHA dos hooks em cada `item_start`.
5. **"Task de fundo pertence ao harness" não fecha com `claude -p`.** CR3, CM6, SR7, EP5 (4 lentes): não há canal de retorno; a versão barata é "entre turnos", a cara é "dentro do turno". FU7 acrescenta que o texto reverte a decisão 5 do dono (X5) sem nomear.
6. **Os cinco itens não podem entrar em `cepa-espiral-c2` como está.** EX1, FU4, CR9, CM7 (4 lentes): a fila tem fonte declarada (`--from-epic`), seus itens estão travados por `human_pending` do Epic Contratos, o roteiro do ciclo não demonstra durabilidade, e os itens 1 e 2 têm natureza diferente dos 3, 4 e 5.
7. **O2 não tem runbook nem protocolo de medição executável.** SR1, EX6, EX7, EX8, CR7, CM2, FU6 (7 menções em 5 lentes): sem fallback, sem limite de retomadas, sem evento no registro, sem número para "contexto cheio", sem dono da semana de runs, sem braço comparável, e tocando o comando de lançamento que quatro provas protegem.
8. **O `session_id` deve nascer no supervisor (`--session-id`) e vir acompanhado de `motivo_fim` de conjunto fechado.** CR6, EP2, SR8 (3 lentes).
9. **Números e referências do documento não se reproduzem ou colidem.** CR5, CR10, EX10, CM8, OU4, OU5, OU6 (5 lentes): 72 eventos (são 24), 3.900 linhas (são 4.234), somas sem rótulo, "C4" com dois significados, "decisão 3" com o texto do R1 (FU1).
10. **O documento não se sustenta para leitor de fora.** OU1, OU2, OU7, OU8 (1 lente, 4 achados, 2 críticos). Mesmo achado X10 do painel de 2026-10-07; fica registrado, e desta vez entra um parágrafo de contexto na revisão 2, porque o documento vai para uma fila.

### DISCORDÂNCIAS NOMEADAS

**X1. O que fazer com O2 (retomar a conversa cortada).**
- **Contrarian diz: descartar agora.** CR1: os dados mostram no máximo 4 cortes por folga e 7 runs por cota em 530 subprocessos, e o corte por cota já é retomado no mesmo run; CR4: a opção mais barata para C1 é encolher o item, não retomar a transcrição. **vs. operador-sre e custo-de-manutenção dizem: manter só com runbook e prazo de remoção.** SR1 pede fallback, uma retomada por item, evento `item_retomado` e número para contexto cheio; CM2 pede experimento com prazo e regra escrita de que o flag sai do código se não houver ganho. **vs. expansionista diz: se for fazer, fazer com `--fork-session`.** EP3: o fork preserva a transcrição da tentativa 1 como registro do abortado, que é o mecanismo do post sem código. **vs. executor diz: a medição como descrita não é executável.** EX7: não existe "mesmo item com e sem retomada".
- **O que decide entre elas:** quantos dos 15 encerramentos com código 1 são cortes externos (rede, cota não tratada) e quantos são erro do próprio `claude`. Isso só o `motivo_fim` gravado responde. Recomendação do sintetizador: **O2 sai do plano como item e vira uma condição**: só volta se, depois de o `motivo_fim` rodar por 20 runs, os cortes externos passarem de 5% dos `item_end`. Enquanto isso, a alternativa CR4 (sub-itens com `start`/`finish` próprios) entra como O4 no documento, sem item de fila ainda. Isso revê a resposta "sim" do dono à pergunta 3 da revisão 1, dada antes dos números corrigidos.
- **Decisão do dono:** sim (2026-11-05): O2 sai do plano como item e vira condição (volta só se o `motivo_fim` mostrar fins externos acima de 5% dos `item_end` em 20 runs); O4 entra como caminho preferido para C1.

**X2. Onde os itens de O1 vivem.**
- **Fundamentalista diz: editar o Epic primeiro e regravar com `--from-epic`.** FU4: a fila tem fonte declarada e escritor único; itens à mão ali fazem o `cepa-plan epics` derivar um ciclo que o Epic não descreve. **vs. executor diz: fila própria.** EX1: em `c2` os itens herdam o `human_pending` do Contratos e não rodam. **vs. custo-de-manutenção diz: só 1 e 2 são pré-requisitos; 3, 4 e 5 esperam medição.** CM7. **vs. contrarian diz: o roteiro do ciclo 2 precisa demonstrar durabilidade ou os itens ficam sem aceite.** CR9.
- **O que decide entre elas:** se o dono aceita que o Epic `cepa-em-espiral` ganhe uma frase em "O que atravessa" do ciclo 2 ("o estado do run sobrevive ao corte: id de sessão e motivo do fim por tentativa, SHA do commit por item fechado") e que a coluna "Quando" distinga esses itens (podem rodar antes do Contratos medido) dos dois atuais (não podem). Recomendação do sintetizador: **fila própria `cepa-durabilidade` com os itens 2, 1 e 5 (nesta ordem), e uma linha no Epic dizendo que o ciclo 2 depende dela**; itens 3 e 4 ficam fora de qualquer fila até o `motivo_fim` medir a dor. Isso revê a resposta "sim" do dono à pergunta 2 da revisão 1.
- **Decisão do dono:** sim (2026-11-05): fila própria `cepa-durabilidade`, com uma linha no Epic dizendo que o ciclo 2 depende dela. Por decisão em X3 o leitor (item 3) também entra nela, depois do heartbeat; o item 4 fica fora até medição.

**X3. Leitor dos cinco depósitos (item 3): comando, módulo, ou menos depósitos.**
- **Custo-de-manutenção diz: matar depósitos antes de ler cinco.** CM1: `estado.json` poderia ser evento no `.jsonl` e o registro de sessões vivas repete a reserva assinada. **vs. expansionista diz: módulo importado pelos quatro comandos que já leem, com conformidade.** EP1: como comando é o quinto leitor parcial. **vs. operador-sre diz: ler não é operar; sem heartbeat qualquer leitor responde "rodando" para um run morto.** SR4, SR9. **vs. contrarian diz: a conformidade é convenção sem gate.** CR8.
- **O que decide entre elas:** quantos consumidores de verdade existem para o leitor (hoje quatro comandos) e se o `estado.json` tem consumidor que o `.jsonl` não serve (o `cepa-until pendentes` lê os dois). Recomendação do sintetizador: **o item 3 não entra agora**. Entra, no lugar, um campo `heartbeat` no `estado.json` que já existe (SR4) e a regra de órfã por idade do heartbeat para pid em outro host (SR9), ambos no mesmo item 2. O leitor único fica para quando o condutor tiver um cockpit para alimentar, e nasce como módulo (EP1) com um teste que falha ao aparecer arquivo de estado desconhecido em `.claude/` (CR8).
- **Decisão do dono:** sim ao heartbeat E sim ao leitor dos cinco depósitos (2026-11-05): o `heartbeat` no `estado.json` e a órfã por idade entram no item 2; o leitor não é adiado, entra como módulo (EP1) com o teste de depósito desconhecido (CR8), na fila `cepa-durabilidade`, bloqueado pelo item do heartbeat.

**X4. Hooks a quente (item 5): quem troca e sob qual doutrina.**
- **Custo-de-manutenção, executor e expansionista dizem: o supervisor reinstala, em um lugar só.** CM5, EX5, EP8 (na abertura do run, em qualquer repo). **vs. fundamentalista diz: as duas soluções quebram `harness-ops` (uma máquina, um harness live; Estado, Alvo, Rollback, Validação) e tornam um commit não mesclado o harness live de todos os repos até de manhã.** FU5. **vs. operador-sre diz: só reinstalar depois do build verde do item que mudou o hook, com SHA dos hooks em todo `item_start`, e regra de rollback escrita.** SR6.
- **O que decide entre elas:** se o dono aceita que a noite troque o harness live da máquina. Hoje os 24 eventos estão todos em filas do repo cepa, então a dor é só do Cepa editando a si mesmo. Recomendação do sintetizador: **reinstalação pelo supervisor, só quando a fila é do repo cepa, só depois de build verde do item que tocou `hooks/` ou `bin/`, com SHA gravado no `item_start` e `hooks_reinstalados` no `.jsonl`; a exceção entra em `docs/harness-ops.md` como rota declarada, e a prova `until-avisa-hook-so-vale-apos-reinstalar.yaml` passa a cobrir o caso "repo não é o cepa: avisa, não troca".**
- **Decisão do dono:** sim (2026-11-05): reinstalação pelo supervisor restrita ao repo cepa, só após build verde do item que tocou `hooks/` ou `bin/`, SHA dos hooks em todo `item_start`, exceção declarada em `docs/harness-ops.md`.

**X5. "Task de fundo pertence ao harness" e o `no-background-build`.**
- **Contrarian e custo-de-manutenção dizem: incompatível com `claude -p`, não entra como princípio.** CR3, CM6. **vs. operador-sre diz: direção certa, mas só com as cinco perguntas respondidas como critério de pronto do item do ciclo 2** (concorrência, árvore em edição, timeout, morte do supervisor, destino do resultado). SR7. **vs. expansionista diz: a versão "entre turnos" já cabe no supervisor de hoje.** EP5. **vs. fundamentalista diz: o texto reverte a decisão 5 do dono sobre X5 sem nomear; o hook só sai depois que o supervisor for dono do build.** FU7.
- **O que decide entre elas:** se o agente precisa do resultado do build dentro do mesmo turno (então não há canal barato) ou se basta recebê-lo no turno seguinte por hook de UserPromptSubmit (então cabe hoje). Recomendação do sintetizador: **o princípio fica no documento como pergunta de desenho do condutor, com as cinco perguntas de SR7 como critério de pronto, e a frase "aposenta o `no-background-build`" sai**: a decisão 5 de 2026-10-08 (hook fica, mensagem curta) continua valendo até o supervisor ser dono do build.
- **Decisão do dono:** sim (2026-11-05): o princípio fica como pergunta de desenho do condutor com as cinco perguntas de SR7 como critério de pronto; a frase que aposentava o `no-background-build` sai e a decisão 5 de 2026-10-08 continua valendo.

### Propostas consolidadas priorizadas

1. **Corrigir os números e a atribuição** (convergências 1 e 9; CR1, CR5, OU3, OU4, OU5, FU1): 24 eventos de hook, 4.234 linhas, tabela dos 59 por `exit_code`, retirar "esses 48 são o custo de não retomar", renomear a referência externa "C4" e citar a decisão 3 pelo texto dela, mantendo a revogação D7 para filhos do condutor. Aplicado na revisão 2.
2. **Item 2 de O1 reescrito** (convergência 8; CR6, EP2, SR4, SR9): o supervisor gera o `session_id` com `--session-id`, grava em `item_start` e `item_end`; `item_end` ganha `motivo_fim` de conjunto fechado (`ok`, `contexto`, `cota`, `rede`, `folga`, `sinal`, `hook`, `desconhecido`); `estado.json` ganha `heartbeat`; órfã em outro host por idade do heartbeat; `item_pulado` com motivo. Critério de aceite: todo `item_end` de um run novo traz os dois campos, verificado pelo `cepa-until-digest`. É o único item que começa amanhã (EX11).
3. **Item 1 de O1 reescrito** (convergência 3; FU2, EX2, SR2, SR3, CM3): `finish --status done` exige worktree limpa e grava o HEAD daquele instante; `finish` recusa se `claimed_by.session_id` não é o chamador ou se o status já é terminal, e registra a recusa; `start` não recusa por ancestralidade (a checagem por tentativa já existe no supervisor), apenas grava e deixa o `landed_check` e o `aterrissar` usarem o SHA; o item do BACKLOG "antecessor done sem merge" é fechado como superado. Condicional a X2 (onde entra).
4. **Item 5 de O1 fechado na reinstalação pelo supervisor** (convergência 4; CM5, EX5, FU5, SR6). Condicional a X4.
5. **Item 4 de O1 substituído por idempotência no efeito** (convergência 2; SR5, EP4, CM4, FU3): marcador `cepa:<fila>/<item>/<tentativa>` no corpo do comentário e checagem no `_jiramut` antes de comentar; status atual checado antes de transitar. Sem lista, sem depósito. Só entra depois de medido (CM4): o `motivo_fim` e o `until-review` passam a contar comentários duplicados por item.
6. **Item 3 de O1 adiado** (X3), substituído pelo heartbeat da proposta 2.
7. **O2 vira condição, não item** (X1); O4 "encolher o item" entra no documento como caminho considerado (CR4).
8. **Princípio "task de fundo" reescrito** (X5; SR7, FU7, EP5) sem a frase que aposenta o hook.
9. **Parágrafo de contexto e definição dos termos** no topo do documento (convergência 10; OU1, OU2, OU7). Aplicado na revisão 2.
10. **Fila própria `cepa-durabilidade`** com os itens 2, 1 e 5 e uma linha no Epic (X2). Condicional à decisão do dono.
