# Especificação: três portas para o spec e o Epic (caminho O2')

**Status:** ready-to-build
**Aberta em:** 2026-11-04            **Fechada em:** 2026-11-06

**Fontes lidas:** `docs/estrategia-tres-portas-para-spec-e-epic.md` (seção 4, O2', e seção 6, D1 a D7) · `docs/reviews/2026-11-04-painel-tres-portas.md` · `BACKLOG.md` (fb-20261104-1) · `common/hooks/spec-readiness-gate.py` · `common/bin/cepa-plan` · `tests/test_cepa_until_dead_supervisor.py` · `common/commands/spec.md` · `common/commands/epic.md` · `common/commands/doctor.md` · `discovery/agents/epic-briefer.md` · `docs/proof/CS-5-transcricao.md`

## Como chegamos aqui
Em 2026-11-04 o dono perguntou: "há três lugares onde alguém já pensou sobre o que construir, por que nenhum deles chega até a entrevista do `/common:spec` e do `/common:epic`?" No mesmo dia aprovou o caminho O2' e pediu que os oito itens passem por `/common:spec` antes de virar fila.

## Problema
**Contexto.** Os três lugares: o brief que o plugin `discovery` escreve ao validar uma oportunidade; a spec que o `planning-lead` do `build-hex` escreve sozinho; e a seção "Decidido sem perguntar" que toda entrevista anterior deixa com um "vete aqui" que ninguém lê de volta. A sessão escreveu `docs/estrategia-tres-portas-para-spec-e-epic.md`, passou por um painel de sete revisores e o dono aprovou o caminho chamado O2': o arquivo no disco vira o canal, sem Jira, com um leitor só em código. Esta especificação é o passo seguinte: dizer, item por item, o que muda e como se prova.

**O que dói hoje.** Quando já existe um brief ou uma spec, o dono responde na entrevista o que já está escrito. E as decisões que o agente tomou sozinho nunca recebem veredito: ficam gravadas como se o dono tivesse concordado.

**O que O2' faz, em uma frase por item.**
- 0. Tira da suíte o teste intermitente do supervisor morto do `cepa-until`. Já resolvido antes desta especificação (ver Perguntas em aberto).
- 1. O passo "ler antes de perguntar" dos dois comandos passa a nomear os arquivos que lê, e toda proposta tirada de um arquivo diz de onde veio: `evidência` ou `proposta de agente`.
- 2. Proposta vem antes da pergunta no mesmo turno, e nada vira `- [x]` sem resposta do dono.
- 3. Um comando, `cepa-plan decisions <arquivo>`, lista as decisões de uma spec ou Epic e diz quais já têm veredito.
- 4. Ao reabrir uma spec ou Epic, o comando mostra as decisões sem veredito (até quatro por rodada na spec, uma por turno no Epic) e grava "mantida", "vetada" ou "refinada" na própria linha.
- 5. O `/common:doctor` conta quantas decisões sem veredito existem no repo.
- 6. Ao gravar `ready`, o comando imprime essa contagem.
- 7. O card que o `discovery` cria aponta para o caminho do brief, e a regra "Brief, not Epic" diz quem o lê.

## Escopo
### Entra
- Sete dos oito itens de O2' (o item 0, quarentena do teste vermelho, saiu: o teste já está verde na `main`): 1 entradas nomeadas e rótulos; 2 ritmo e regra do `- [x]`; 3 `cepa-plan decisions`; 4 veto nos comandos; 5 check no `doctor`; 6 contagem no fechamento; 7 `epic-briefer` e regra "Brief, not Epic".
### Não entra
- Arquivo de expertise para a entrevista (D5).
- O atalho `--from <arquivo>` do item 1: o `discovery` não roda no Cepa (R4) e não há arquivo para apontar hoje.
- A conta do R1 no `cepa-metrics`: nenhum registro guarda hoje se a proposta foi aceita ou alterada.
- Unificar `spec/`, `specs/` e `docs/spec/` (D7, sem gatilho).
- Mudar o `/common:debrief` (D1).
- Desfazer o que já virou código a partir de decisão vetada: o veto é registro.

## Estado e migração
- Specs e Epics já fechados não mudam de texto: não passam de novo pela passagem `draft` → `ready` e por isso não recebem a contagem do item 6. As 5 decisões sem veredito deles (3 em `cepa-espiral-c1` + 2 em `planejador-de-lotes-paralelos` = 5) aparecem no `doctor` (item 5) e recebem veredito pela caminhada do item 4 quando o dono os reabrir.
- O `doctor` passa de 0 para 1 no código de saída deste repo enquanto essas 5 estiverem sem veredito: é o efeito pedido, não regressão.
- O Epic `cepa-em-espiral` (2 decisões, `rascunho`) só entra na contagem quando fechar.
- `cepa-plan` ganha dois subcomandos (`decisions`, `verdict`); nenhum subcomando existente muda.
- Cards do `discovery` já criados não são reescritos: só os novos levam a linha do repositório.

## Critérios de sucesso

### CS-1: ao liberar uma spec em `ready-to-build` ou um Epic em `ready`/`closed`, o `spec-readiness-gate` mostra ao dono "N decisões sem veredito neste arquivo", contando as linhas da seção "Decided without asking" sem `· mantida em`, `· vetada em` nem `· refinada em` (item 6)
**Surface:** event
**Red test:** dado o evento de Write de `docs/spec/x.md` com `Status: ready-to-build`, crivo completo e três decisões na seção, uma delas com `· mantida em 2026-11-06`, o hook sai com 0 e a saída mostrada ao dono contém "2 decisões sem veredito"; com a seção sem nenhuma linha pendente, contém "0 decisões sem veredito"; sem a seção, contém "sem seção Decided without asking"; e um segundo Write sobre o mesmo arquivo, já `ready-to-build` no disco, não imprime a contagem. Hoje falha: o hook sai com 0 sem imprimir nada.

### CS-2: o leitor da seção "Decided without asking" mora num módulo compartilhado que o hook importa, lê os nomes antigo e novo da seção e devolve as linhas com e sem veredito (item 6, base do item 3)
**Surface:** domain
**Red test:** importar o módulo e ler os quatro documentos reais de hoje (`docs/spec/cepa-espiral-c1.md`, `docs/spec/planejador-de-lotes-paralelos.md`, `docs/epics/cepa-em-espiral.md` e um fixture com `## Decidido sem perguntar` e uma linha) devolve 3, 2, 2 e 1 linhas sem veredito, nas mesmas palavras do arquivo. Hoje falha: o módulo não existe.

### CS-3: o passo de fechamento de `/common:spec` e de `/common:epic` manda repetir no relatório final o número que o hook mostrou (item 6)
**Surface:** application
**Red test:** um teste que lê `common/commands/spec.md` e `common/commands/epic.md` encontra, no passo de fechamento, a instrução de repetir "decisões sem veredito" no relatório. Hoje falha: nenhum dos dois cita a contagem.

### CS-4: `cepa-plan decisions` lista, por arquivo, as decisões da seção "Decided without asking" separadas em com e sem veredito; sem argumento varre `docs/spec/` e `docs/epics/` (item 3)
**Surface:** cli
**Red test:** num repo de teste com uma spec (duas decisões, uma com `· vetada em 2026-11-06: fora do ciclo`) e um Epic (uma decisão sem marcador), `cepa-plan decisions` sai com 0 e imprime os dois caminhos com "1 sem veredito" cada e o texto das linhas pendentes; `cepa-plan decisions <spec> --json` devolve as duas linhas com o campo de veredito preenchido só na vetada; `cepa-plan decisions inexistente.md` sai com código diferente de 0. Hoje falha: o subcomando `decisions` não existe.

### CS-5: o `doctor` mostra a área `decisoes` com ⚠ e o total de decisões sem veredito nas specs e Epics fora de `draft`/`rascunho`, um arquivo por linha com o comando que abre o veto (item 5)
**Surface:** cli
**Red test:** num repo de teste com uma spec `ready-to-build` (duas decisões, uma com `· mantida em 2026-11-06`), uma spec `draft` (três decisões sem marcador) e um Epic `rascunho` (uma sem marcador), `cepa-doctor --project` sai com 1, mostra "⚠ [decisoes] 1 decisão sem veredito" com o caminho da spec pronta e `/common:spec --continuar <slug>`, não cita os dois arquivos em rascunho, repete a linha em "Precisa de você", e `--brief` conta o aviso; no repo do Cepa de 2026-11-06 o total seria 5 (3 em `cepa-espiral-c1` + 2 em `planejador-de-lotes-paralelos`; o Epic `cepa-em-espiral` está em `rascunho`). Hoje falha: o `doctor` não tem a área `decisoes`.

### CS-6: `cepa-plan verdict <arquivo> <n> mantida|vetada|refinada` grava na linha `<n>` da seção "Decided without asking" o marcador com a data do dia, e ao vetar ou refinar avisa quando uma fila já foi derivada do arquivo (item 4)
**Surface:** cli
**Red test:** num repo de teste com uma spec de três decisões e uma fila cujo `source:` cita essa spec com um item `done`, `cepa-plan verdict <spec> 2 vetada --reason "fora do ciclo"` sai com 0, a linha 2 termina em `· vetada em <hoje>: fora do ciclo`, as linhas 1 e 3 não mudam, `Status` não muda, a saída contém "já virou código na fila" com o nome da fila e "1 item done"; repetir o comando na linha 2 sai com código diferente de 0; `vetada` sem `--reason` sai com código diferente de 0. Hoje falha: o subcomando `verdict` não existe.

### CS-7: `/common:spec --continuar`/`--fechar` e `/common:epic` sobre documento existente abrem com a caminhada do veto antes de retomar a entrevista ou o crivo: até quatro decisões por rodada na spec, uma por turno no Epic, cada resposta gravada por `cepa-plan verdict`, decisão pulada fica sem marcador (item 4)
**Surface:** application
**Red test:** um teste que lê `common/commands/spec.md` e `common/commands/epic.md` encontra, no passo de abertura de documento existente e antes do passo da entrevista, a chamada a `cepa-plan decisions` e a `cepa-plan verdict`, o limite de quatro por rodada em `spec.md` e de uma por turno em `epic.md`, e a frase de que decisão pulada não trava. Hoje falha: nenhum dos dois cita a caminhada do veto.

### CS-8: `/common:spec`, num repo com um brief do `discovery` e uma spec do `planning-lead` sobre o assunto, nomeia as fontes lidas, rotula cada proposta tirada delas e não marca `- [x]` sem resposta do dono (itens 1 e 2)
**Surface:** application
**Red test:** uma transcrição gravada com `claude -p --plugin-dir common` num repo descartável com `docs/discovery/<card>/handoff.md` e `specs/<slug>.md` semeados mostra: o documento criado tem `**Fontes lidas:**` com os dois caminhos; toda proposta tirada deles aparece como opção recomendada com o rótulo `evidência` (do brief) ou `proposta de agente` (da spec) e o caminho; nenhuma linha vira `- [x]` antes de uma fala do dono que a responda; decisão herdada da spec do `planning-lead` aparece em "Decided without asking" com a origem, não como pergunta respondida. Hoje falha: o passo 2 não cita `docs/discovery/` nem `specs/`, e nenhuma proposta sai rotulada.

### CS-9: `/common:epic`, no mesmo repo semeado, faz o mesmo em prosa: fontes nomeadas, proposta rotulada antes da pergunta e desafiada uma vez, nenhum `- [x]` sem resposta do dono (itens 1 e 2)
**Surface:** application
**Red test:** uma transcrição gravada como a de CS-8, com `/common:epic`, mostra `**Fontes lidas:**` no cabeçalho do Epic, em cada turno com proposta tirada de arquivo o rótulo e o caminho antes da única pergunta do turno, cada proposta rotulada desafiada uma vez ("quem vê isso e onde?" ou "o que quebra se faltar?") antes de ser gravada, e nenhuma linha `- [x]` sem fala do dono. Hoje falha: o comando não rotula proposta nem nomeia `docs/discovery/` e `specs/` no passo 2.

### CS-10: o card que o `epic-briefer` cria aponta o caminho do brief e o repositório onde ele vive, e a regra "Brief, not Epic" nomeia os dois leitores (item 7)
**Surface:** application
**Red test:** um teste que lê `discovery/agents/epic-briefer.md` encontra, no modelo da descrição do card do passo 5, uma linha de repositório preenchida com `git remote get-url origin` e o caminho local como reserva, ao lado da linha `Delivery brief:`; nenhum comando literal (`/common:epic ...`) no modelo do card; e a regra "Brief, not Epic" citando `epic-author` e `/common:epic`. Hoje falha: o modelo não tem linha de repositório e a regra cita só o `epic-author`.

## Perguntas em aberto
- [x] Item 0: quarentenar só, sem consertar a corrida do supervisor? — resolvido pela evidência, sem pergunta: o item `test-dead-supervisor-corrida-sinal` da fila `cepa` consertou a corrida (commits 2c4d085, c3fe821, 15cbf52, na `main`); em 2026-11-06 o módulo passou 20/20 em três rodadas seguidas. Item 0 sai do escopo.
- [x] Item 0: quarentena = módulo inteiro marcado `skip`? — caiu junto com a anterior: sem teste vermelho, não há o que quarentenar.
- [x] Item 6: a contagem sai do próprio hook `spec-readiness-gate` no momento em que ele libera o `ready`, e o comando só a repete no relatório? — sim (dono, 2026-11-06).
- [x] Item 6: a contagem é só do arquivo que está fechando, deixando o total do repo para o `doctor` (item 5)? — sim, só o arquivo (dono, 2026-11-06).
- [x] Item 6: o item 6 escreve o leitor da seção num módulo compartilhado, e o item 3 (`cepa-plan decisions`) só o reaproveita, mantendo a ordem 6 antes de 3? — sim; a ordem segue 6, 3, 5, 4, 1, 2, 7 (dono, 2026-11-06).
- [x] Item 6: com zero decisões sem veredito, o fechamento imprime "0" em vez de ficar calado? — sim, imprime o zero (dono, 2026-11-06).
- [x] Item 6: o hook imprime a contagem só na passagem de `draft` para `ready` (arquivo no disco ainda não está pronto), e não a cada edição posterior de um arquivo já pronto? — sim, só na passagem (dono, 2026-11-06).
- [x] Item 6: spec sem a seção "Decided without asking" fecha com a linha "sem seção Decided without asking" em vez de "0"? — sim, linha própria; a seção continua não obrigatória em spec (dono, 2026-11-06).
- [x] Item 3: `cepa-plan decisions` sem argumento varre `docs/spec/` e `docs/epics/`, e com argumentos lê só os arquivos dados, para o `doctor` (item 5) chamar o mesmo comando? — sim (dono, 2026-11-06).
- [x] Item 3: o comando sai sempre com código 0, mesmo com pendência, deixando a gravidade para quem chama? — sim; erro só para arquivo inexistente ou ilegível (dono, 2026-11-06).
- [x] Item 3: dizer "isto já virou código na fila X" (mitigação de R2, lendo o `source:` das filas) fica no item 4 e não no `cepa-plan decisions`? — sim, fica no item 4 (dono, 2026-11-06).
- [x] Item 5: pendência de veto aparece no `doctor` como aviso (⚠, conta no código de saída 1, no resumo de `--brief` e no bloco "Precisa de você")? — sim, aviso (dono, 2026-11-06).
- [x] Item 5: o `doctor` conta só arquivos fora de `draft`, deixando a spec ou Epic em entrevista para a contagem do fechamento (item 6)? — sim, só fechados; `rascunho` conta como `draft` (dono, 2026-11-06).
- [x] Item 4: no `/common:spec`, a caminhada do veto mostra até quatro decisões por rodada (o ritmo do comando), e só o `/common:epic` fica com uma por turno? — sim, quatro por rodada na spec e uma por turno no Epic; muda o que O2' escreveu (dono, 2026-11-06).
- [x] Item 4: quem grava o marcador `· mantida em`/`· vetada em`/`· refinada em` na linha é um subcomando do `cepa-plan` (data do relógio, formato exato), e não o agente editando o texto à mão? — sim, subcomando do `cepa-plan` (dono, 2026-11-06).
- [x] Item 4: a caminhada do veto roda antes de retomar a entrevista ou o crivo, e decisão deixada sem resposta segue sem marcador, sem travar o comando? — sim, pular não trava (dono, 2026-11-06).
- [x] Itens 1 e 2: a prova é uma transcrição gravada com `claude -p` num repo descartável, como `docs/proof/CS-5-transcricao.md`, com um brief e uma spec de agente semeados, mostrando cada proposta rotulada e desafiada uma vez e nenhum `- [x]` sem fala do dono? — sim, transcrição gravada, uma por comando (dono, 2026-11-06).
- [x] Item 1: o atalho `--from <arquivo>` fica fora deste ciclo? — sim, fora (dono, 2026-11-06).
- [x] Item 2: a conta do R1 no `cepa-metrics` (propostas rotuladas aceitas sem alteração versus alteradas) fica fora desta especificação? — sim, fora (dono, 2026-11-06).
- [x] Item 7: o repositório do brief entra no card como o endereço do remote do git (`git remote get-url origin`), e só cai para o caminho local quando não há remote? — sim (dono, 2026-11-06).

## Decided without asking
- Item 7: o card do `epic-briefer` já leva o caminho do brief (`Delivery brief: docs/discovery/<key>/handoff.md`, passo 5 do agente); o item 7 só acrescenta a linha do repositório e reescreve a regra "Brief, not Epic" para nomear os dois leitores, `epic-author` no board e `/common:epic` em arquivo, sem pôr comando literal no card e deixando o `<slug>` do Epic para a entrevista (D6). Vete aqui se discordar.
- Item 7 é provado por leitura do texto de `discovery/agents/epic-briefer.md`, não por transcrição: a mudança são duas linhas de modelo de texto, e o `discovery` não roda no Cepa para gravar uma sessão (R4). Vete aqui se discordar.
- Item 1: o passo 2 dos dois comandos nomeia três fontes com caminho: o brief do `discovery` (`docs/discovery/<card>/handoff.md`), a spec do `planning-lead` (`spec/` e `specs/` na raiz do repo) e a seção "Decided without asking" das outras specs e Epics (`docs/spec/`, `docs/epics/`). Vete aqui se discordar.
- Item 1: a linha `**Fontes lidas:**` vai no cabeçalho do documento uma vez, com os caminhos lidos, e nenhum rótulo entra na linha do critério, que o gate parseia (O2' já dizia). Vete aqui se discordar.
- Item 2: no `/common:spec` a proposta tirada de um arquivo vira a opção recomendada da pergunta, com o rótulo (`evidência` ou `proposta de agente`) e o caminho na descrição; no `/common:epic` vira a proposta em prosa que antecede a pergunta, como o comando já manda. Vete aqui se discordar.
- Item 2: "nada vira `- [x]` sem resposta do dono" é regra de texto nos dois comandos, sem hook: nenhum hook sabe quem respondeu. Decisão herdada de outra entrevista entra em "Decided without asking" com a origem, nunca como pergunta respondida (O2' já dizia). Vete aqui se discordar.
- Item 4: o subcomando se chama `cepa-plan verdict <arquivo> <n> mantida|vetada|refinada`, onde `<n>` é a posição da linha na seção como `cepa-plan decisions` a numera; `vetada` exige `--reason`; `refinada` exige `--text` com o novo texto da decisão e troca o texto antes de pôr o marcador; linha que já tem marcador é recusada. Vete aqui se discordar.
- Item 4: o aviso de R2 ("isto já virou código na fila X") sai do próprio `cepa-plan verdict` ao gravar `vetada` ou `refinada`, quando alguma `.claude/queues/*/queue.yaml` cita o caminho do arquivo no `source:`, e diz o nome da fila e quantos itens dela estão `done`. Vete aqui se discordar.
- Item 5: a área do `doctor` se chama `decisoes`, entra nos checks de projeto (vale com `--project`), não tem conserto automático no `--fix`, e cada arquivo pendente sai com o comando que abre o veto: `/common:spec --continuar <slug>` para spec, `/common:epic <nome>` para Epic. Repo sem `docs/spec/` nem `docs/epics/` não mostra a área; com eles e zero pendência, mostra ✓ com o zero. Vete aqui se discordar.
- Item 3: `cepa-plan decisions` imprime texto por padrão e aceita `--json`, como os outros comandos de leitura do `cepa-plan`; entra no grupo "reading" da ajuda. Vete aqui se discordar.
- CS-1 tem Surface `event`: o hook reage ao evento de escrita do Claude Code, e o teste o dirige como o Claude Code dirige, com o payload no stdin. Vete aqui se discordar.
- CS-3 é prova por leitura do texto do comando, não por transcrição: a contagem mecânica já está em CS-1, e repetir no relatório é cortesia. Vete aqui se discordar.
- A seção "Como chegamos aqui" virou seção própria (antes era um parágrafo dentro de Problema), porque o `spec-readiness-gate` recusa `ready-to-build` sem ela. Vete aqui se discordar.
- Item 6 vale para os dois comandos: spec em `ready-to-build` e Epic em `ready` ou `closed`, porque a seção "Decided without asking" existe nos dois formatos e o hook já distingue os dois. Vete aqui se discordar.
- "Sem veredito" é linha de lista da seção sem `· mantida em`, `· vetada em` nem `· refinada em`, como O2' já define para o veto. Hoje são 7 no repo (contagem de 2026-11-06: `cepa-espiral-c1` 3 + `planejador-de-lotes-paralelos` 2 + Epic `cepa-em-espiral` 2 = 7, nenhuma com marcador). Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- O ciclo tem sete itens e dez critérios; a estratégia estimou um ciclo só.
- R1 (proposta rotulada aceita sem desafio) fica provado só nas duas transcrições gravadas, sem medida contínua depois da entrega: a conta no `cepa-metrics` saiu desta especificação.
- As transcrições de CS-8 e CS-9 custam modelo a cada gravação; regravar depois de mudar o texto dos comandos é custo recorrente.
