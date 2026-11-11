# Especificação: modos opinativos (menu de ações na entrada de cada modo)

**Status:** ready-to-build
**Aberta em:** 2026-11-10            **Fechada em:** 2026-11-11
**Fontes lidas:** common/hooks/_modes.py, common/hooks/session-mode.py, common/bin/cepa, common/commands/metrics.md, common/commands/modes.md, common/bin/cepa-modes, tests/test_cepa_mode.py, docs/modos-de-trabalho.md, .claude/handoffs/session-mkt-mode.md, .claude/deviations.md, ~/.claude/cepa-telemetry/events-2026-*.jsonl, ~/.zsh_history (só a contagem de `cepa --mode`)

## Como chegamos aqui
Em 2026-11-10 o dono disse: "quero que o modo seja mais opinativo, que cada modo carregue um repertório de ações comuns àquele modo de atuação, a um comando de distância, para conduzir quem sabe que algo tem que ser feito mas não sabe ao certo o quê." A frase veio depois de ele perguntar, na sessão que testou a topologia marketing: "o modo é só isso? Uma entrada numa tabela mais algumas restrições de escrita?"

## Problema
Hoje o modo diz o que a sessão não pode fazer (onde escrever, quando pode fechar) e não diz o que ela pode fazer. Quem abre `cepa --mode discovery` sem saber qual comando rodar recebe a condição de saída do modo e mais nada. O repertório de comandos de cada modo existe, mas só na cabeça de quem já o decorou.

## Escopo
### Entra
- Um campo novo por modo em `common/hooks/_modes.py` (a tabela única dos modos), com 3 a 5 ações. Cada ação tem uma frase leiga e o comando que a dispara.
- A exibição do menu quando a sessão abre sem rotina e sem pedido.
- Menu preenchido só nos modos mais usados. Nos outros o campo existe com lista vazia.
- A reconciliação da seção "Modo não é Rotina" de `docs/modos-de-trabalho.md`.

### Não entra
- A jornada guiada por estado do disco (o modo ler o disco e sugerir o passo seguinte). Exige um leitor de estado por modo e hoje só `exploration` tem um.
- Comandos novos. O menu é mapa para comandos que já existem. Onde não houver comando, a ação aparece marcada "(sem comando ainda)" (P6).
- Gravar a ação escolhida em `routine:` de `.claude/session-mode` (P3).
- O modo `marketing`. Ele ainda não está na tabela e entra depois desta especificação, para não escrever a entrada dele duas vezes.

## Estado e migração
- `common/hooks/_modes.py`: cada um dos 7 modos ganha a chave `actions` (lista ordenada). Os 4 modos sem menu recebem `[]`. Nenhuma chave existente muda de nome nem de valor.
- `cepa-modes --json` (a saída que o painel compass lê) ganha a chave `actions` por modo. As chaves antigas em pt-BR (`saida`, `proposito` e as outras) ficam como estão.
- `.claude/session-mode` não muda. `routine:` continua `null`.
- `common/bin/cepa`: quando abre sem prompt inicial, passa a mandar um prompt de abertura ao `claude`. Sessões abertas com prompt, sessões encadeadas (que já levam o brief como prompt) e runs do `cepa-until` não mudam.
- `~/.claude/cepa-telemetry/events-*.jsonl`: dois eventos novos, `mode_menu.shown` e `mode_menu.chosen`. Os eventos antigos não mudam, e não há dado antigo para converter.
- `docs/modos-de-trabalho.md`: a seção "Modo não é Rotina" mantém a tabela e a frase, e ganha um parágrafo. O bloco de status do topo e a lista "O que precisa ser construído" ganham a linha do menu.
- Sessões já abertas quando a mudança entrar não veem menu sozinho. Nelas o menu aparece pelo `/common:modes`.

## Critérios de sucesso

### CS-1: `cepa-modes --menu <modo>` imprime o menu do modo, numerado, com frase leiga e comando por ação, lido do campo `actions` de `_modes.py`
**Surface:** cli
**Red test:** rodar `cepa-modes --menu discovery` num repo sem `board-flow.yaml` e com o plugin discovery instalado e exigir saída com código 0 contendo, nesta ordem, "1) Detail an idea until it becomes a build-ready specification" com `/common:spec`, e as linhas de `/common:spec --continuar`, `/common:epic`, `/discovery:capture` e `/common:queue`. Hoje falha porque `cepa-modes` recusa a flag `--menu` com código 2.

### CS-2: ação cujo requisito o repo não cumpre some do menu, e o menu mostra no máximo as 5 primeiras que passam
**Surface:** cli
**Red test:** rodar `cepa-modes --menu construction` em dois repos descartáveis. No primeiro, sem `board-flow.yaml` e com `.claude/topology` igual a `build-solo`, exigir que a saída não contenha `/board-flow:` e contenha `/build-solo:reproduce-fix-verify`, `/build-solo:plan-build-validate` e "Write the red test of the criterion (no command yet)". No segundo, com `board-flow.yaml`, exigir exatamente 5 ações numeradas, com `/board-flow:execute` entre elas, com a ação "Fix a bug" mostrando `/board-flow:capture Bug:` seguido de `/board-flow:fix`, e sem `/board-flow:prove-drain`. Hoje falha porque a flag `--menu` não existe.

### CS-3: `cepa --mode <modo>` sem prompt inicial abre a sessão com um prompt de abertura que carrega o menu, e com prompt inicial não manda nada a mais
**Surface:** cli
**Red test:** em `tests/test_cepa_mode.py`, com o `claude` falso que grava os argumentos recebidos, rodar `cepa --mode discovery` sem argumentos e exigir que o `claude` falso receba um argumento de prompt contendo o marcador `[menu do modo]` e a linha `/common:spec`. Rodar em seguida `cepa --mode discovery "arruma o teste X"` e exigir que os argumentos sejam só os do dono. Hoje a primeira asserção falha: o `claude` falso não recebe prompt nenhum.

### CS-4: modo com lista vazia abre como hoje, sem prompt de abertura
**Surface:** cli
**Red test:** em `tests/test_cepa_mode.py`, exigir que `cepa-modes --menu design` saia com código 0 e saída vazia, e que `cepa --mode design` sem argumentos não entregue prompt ao `claude` falso. Hoje a primeira asserção falha porque `--menu` devolve código 2.

### CS-5: no turno de abertura, o hook do modo instrui o agente a mostrar o menu traduzido para a língua do dono, sem mudar a ordem, a numeração nem os comandos, e a tratar a resposta seguinte: número ou comando dispara a ação, ação com argumento recebe antes uma pergunta de uma linha, ação sem comando é conduzida em conversa, texto livre é pedido normal
**Surface:** cli
**Red test:** em `tests/test_cepa_mode.py`, entregar ao hook `session-mode.py` um payload de `UserPromptSubmit` cujo prompt é o prompt de abertura do modo discovery e exigir que o `additionalContext` contenha a regra de exibição (traduzir as frases, manter ordem, numeração e comandos), a pergunta de argumento da ação 1 ("What is the idea?") e a regra do texto livre. Entregar também o prompt de abertura do modo construction num repo com `board-flow.yaml` e exigir a regra da ação "Fix a bug": se a resposta for a chave de um card, rodar só `/board-flow:fix`, e se for uma descrição, rodar `/board-flow:capture Bug:` e depois `/board-flow:fix` na chave criada. Hoje falha: o hook devolve só as linhas `[modo]` e `[intenção]`.

### CS-6: o prompt de abertura não conta como prompt do dono na linha `[intenção]`
**Surface:** cli
**Red test:** em `tests/test_cepa_mode.py`, com `.claude/session-log.md` contendo o prompt de abertura seguido de "quero especificar X", rodar o hook sem intenção gravada e exigir que a lista "Primeiros prompts" contenha "quero especificar X" e não contenha `[menu do modo]`. Hoje falha: o hook lista todo prompt do log.

### CS-7: a telemetria grava `mode_menu.shown` quando o menu é mostrado e `mode_menu.chosen` quando a resposta seguinte é um número do menu ou um comando do menu, os dois com o modo
**Surface:** event
**Red test:** com `CEPA_TELEMETRY_DIR` apontando para um diretório descartável, entregar ao hook `session-mode.py` o prompt de abertura do modo discovery e depois o prompt "1", e exigir no arquivo de eventos uma linha `mode_menu.shown` com `mode: discovery` e uma linha `mode_menu.chosen` com `mode: discovery`, `action: 1` e `command: /common:spec`. Entregar depois "quero outra coisa" e exigir que nenhum `mode_menu.chosen` novo apareça. Hoje falha: nenhum dos dois eventos existe.

### CS-8: `/common:metrics` mostra a conta de uso do menu por modo
**Surface:** cli
**Red test:** rodar `cepa-metrics` sobre um arquivo de eventos descartável com 4 `mode_menu.shown` e 1 `mode_menu.chosen` do modo discovery e exigir na saída a linha do modo discovery com "1 ÷ 4 = 25%". Hoje falha: o relatório não tem seção do menu.

### CS-9: `/common:modes` mostra o menu do modo da sessão, depois da tabela
**Surface:** cli
**Red test:** num repo descartável com `.claude/session-mode` em `mode: exploration`, rodar `cepa-modes` sem argumentos (o que `/common:modes` executa) e exigir que a saída termine com o menu de exploration, incluindo "Write the strategy document with 2 or more paths (no command yet)" e `/common:advisors`. Hoje falha: a saída termina na tabela.

### CS-10: todo comando citado num menu existe no repo do Cepa, e todo requisito usa um dos três tipos fechados
**Surface:** domain
**Red test:** em `tests/test_modes_single_source.py`, percorrer `MODES[*]["actions"]` e exigir que cada comando (o `command` único ou cada um da sequência) no formato `/<plugin>:<nome>` tenha o arquivo `<plugin>/commands/<nome>.md`, que cada requisito seja `file:`, `topology:` ou `plugin:`, que toda ação tenha frase leiga, e que construction, discovery e exploration tenham de 3 a 8 ações e os outros 4 modos tenham lista vazia. Hoje falha com `KeyError: 'actions'`.

### CS-11: `docs/modos-de-trabalho.md` descreve o menu sem desfazer a distinção entre modo e rotina
**Surface:** domain
**Red test:** em `tests/test_modes_single_source.py`, ler `docs/modos-de-trabalho.md` e exigir que a seção "Modo não é Rotina" ainda contenha a frase "Uma sessão = um modo obrigatório + no máximo uma rotina" e contenha um parágrafo que cite o campo `actions` e o comando `cepa-modes --menu`. Hoje falha: o documento não cita nenhum dos dois.

### CS-12: `/common:modes --exit` é um argumento declarado do comando e chega ao `cepa-modes` como veio
**Surface:** domain
**Red test:** em `tests/test_modes_single_source.py`, ler `common/commands/modes.md` e exigir que a linha `argument-hint:` do cabeçalho contenha `--exit` e que o passo que roda `cepa-modes` continue repassando `$ARGUMENTS`. Hoje falha: o `argument-hint` declara só `[mode-name]`.

## Perguntas em aberto
- [x] P1. Quais modos saem com menu preenchido nesta especificação? — Os 3 mais usados: construction, discovery e exploration (102 de 106 aberturas, 96%). documentation, design, refactor e reflection ficam com lista vazia. (dono, 2026-11-10)
- [x] P2. Onde e em que momento o menu aparece? — O launcher abre com o menu: quando `cepa --mode X` roda sem prompt inicial, o `cepa` manda um prompt de abertura e a primeira resposta da sessão é o menu, numerado, com a linha "Responda o número, o comando, ou escreva o que quer fazer". Com prompt inicial, nada aparece. (dono, 2026-11-10)
- [x] P3. Escolher uma ação do menu grava a rotina da sessão (campo `routine:` de `.claude/session-mode`)? E como fica a frase "Modo não é Rotina" do documento? — A frase fica. A seção ganha um parágrafo dizendo que o modo agora oferece as rotinas dele. Nada é gravado em `routine:`. (dono, 2026-11-10)
- [x] P4. De onde o menu pode tirar comandos, já que eles mudam de repo para repo? — Qualquer comando, com filtro: cada ação declara do que precisa (ex.: `board-flow.yaml`) e some do menu quando o repo não tem. O dono aceitou ler o disco na abertura para isso. (dono, 2026-11-11)
- [x] P5. Quando o dono responde só o número de uma ação que pede argumento, o que o agente faz? — Faz uma pergunta de uma linha pelo que falta e dispara o comando com a resposta. A ação no campo carrega essa pergunta. (dono, 2026-11-11)
- [x] P6. Ação comum do modo que ainda não tem comando entra no menu? — Entra, marcada "(sem comando ainda)". Se escolhida, o agente a conduz em conversa. (dono, 2026-11-11)
- [x] P7. O que uma ação pode declarar como requisito para aparecer? — Três tipos fechados: um arquivo existe na raiz do repo, o repo usa certa topologia (conteúdo de `.claude/topology`), ou certo plugin está instalado. (dono, 2026-11-11)
- [x] P8. Qual é o menu de construction? — A lista proposta, nesta ordem, mostrando as 5 primeiras que passam no filtro: (1) Fazer o próximo item da fila, `/common:next`; (2) Rodar a fila inteira em lote, `/common:drain-plan <fila>`; (3) Executar um card do Jira, `/board-flow:execute <chave>`, precisa de `board-flow.yaml`; (4) Corrigir um bug, `/board-flow:fix <chave>` com `board-flow.yaml`, senão `/<topologia>:reproduce-fix-verify` [revisto pelo dono em 2026-11-11, ver P13]; (5) Construir uma tarefa descrita em prosa, `/<topologia>:plan-build-validate`, precisa de topologia; (6) Provar o que está em Review, `/board-flow:prove-drain`, precisa de `board-flow.yaml`; (7) Escrever o teste vermelho do critério, sem comando ainda. (dono, 2026-11-11)
- [x] P9. Qual é o menu de discovery? — A lista proposta: (1) Detalhar uma ideia até virar especificação pronta para construir, `/common:spec <a ideia>`; (2) Continuar uma especificação aberta, `/common:spec --continuar <slug>`; (3) Desenhar um pacote grande em ciclos, `/common:epic <nome>`; (4) Registrar um sinal de usuário, `/discovery:capture <o sinal>`, precisa do plugin discovery; (5) Transformar a especificação pronta em fila de construção, `/common:queue <nome> --from-spec`; (6) Avançar um card de descoberta, `/board-flow:advance <chave>`, precisa de `board-flow.yaml` e do plugin discovery. (dono, 2026-11-11)
- [x] P10. Qual é o menu de exploration? — A lista proposta: (1) Escrever o documento de estratégia com 2 ou mais caminhos, sem comando ainda; (2) Passar o documento pelo painel de advisors, `/common:advisors <documento>`; (3) Ver o que falta para fechar a exploração, `/common:modes` [comando revisto pelo dono em 2026-11-11 para `/common:modes --exit`, ver P15]; (4) Ver em números onde o harness atrapalha, `/common:metrics`; (5) Rever as decisões de um run passado, `/common:debrief`. (dono, 2026-11-11)
- [x] P13. A ação "Corrigir um bug" pressupõe que todo bug já tem card. Como ela atende o bug que o dono acabou de achar? — Uma ação só, que pede a chave do card ou a descrição do bug. Com Jira e chave, o agente roda `/board-flow:fix <chave>`. Com Jira e descrição, roda `/board-flow:capture Bug: <descrição>` e em seguida `/board-flow:fix` na chave criada, para o bug ficar registrado. Sem Jira, roda `/<topologia>:reproduce-fix-verify <descrição>`. (dono, 2026-11-11: "às vezes, o pedido de correção de um bug é, ao mesmo tempo, o registro da existência do bug e o pedido de sua correção imediata")
- [x] P14. Em que língua ficam a frase leiga e a pergunta de argumento dentro de `_modes.py`? — Em inglês, como o resto da tabela. O agente traduz ao mostrar o menu. As frases aprovadas em P8, P9 e P10 valem como o texto que o dono lê, e a tabela guarda a tradução delas. Na tabela a marca da ação sem comando é "(no command yet)". (dono, 2026-11-11, ao vetar a decisão #3)
- [x] P15. `/common:modes` puro mostra só a tabela dos modos e não diz o que falta nesta sessão. Para onde aponta a ação "Ver o que falta para fechar a exploração"? — Para `/common:modes --exit`, que repassa ao `cepa-modes --exit` e devolve a conta do que falta no disco. A especificação ganha um critério que prova esse caminho de barra (CS-12), porque ele foi lido e não testado. (dono, 2026-11-11)
- [x] P11. A telemetria grava que o menu foi mostrado e qual ação foi escolhida? — Grava os dois, com o modo: um evento na exibição e outro quando a resposta seguinte é um número ou um comando do menu. (dono, 2026-11-11)
- [x] P12. O menu fica disponível no meio da sessão? — Sim, pelo `/common:modes`, que passa a mostrar também o menu do modo atual. Nada aparece sozinho. (dono, 2026-11-11)

## Decided without asking
- A contagem de uso dos modos veio do histórico do shell (`~/.zsh_history`, ocorrências de `cepa --mode <nome>`), e não do `/common:metrics` — o evento `session_start` da telemetria não grava o modo (conferido em `events-2026-11.jsonl`), então o `/common:metrics` não tem como responder. Contagem em 2026-11-10, somando nome antigo e novo: construction 74 (37+37), discovery 15 (11+4), exploration 13 (7+6), documentation 4, design 0, refactor 0, reflection 0. Total 106. Vete aqui se discordar. · mantida em 2026-11-11

- O formato de uma ação em `_modes.py` é um dicionário com `label` (a frase leiga), `command` (um comando, uma lista de comandos rodados em sequência, ou `None` na ação sem comando), `ask` (a pergunta de uma linha quando o comando pede argumento, ou ausente) e `needs` (lista de requisitos, ausente quando a ação vale em todo repo). A sequência entrou com a P13. · refinada em 2026-11-11
- A frase leiga e a pergunta de argumento ficam em pt-BR dentro de `_modes.py`, apesar de os outros valores da tabela estarem em inglês — o menu é lido pelo dono na resposta do agente, como as linhas `[intenção]` do mesmo arquivo, que já são pt-BR. Vete aqui se discordar. · vetada em 2026-11-11: o dono quer as frases em inglês como o resto da tabela; o agente traduz ao mostrar o menu
- Os requisitos se escrevem `file:<caminho relativo à raiz>`, `topology:<nome>` e `plugin:<nome>`, e uma ação com vários requisitos precisa de todos — é o que o item 6 de discovery pede (`board-flow.yaml` e plugin discovery). Vete aqui se discordar. · mantida em 2026-11-11
- "Corrigir um bug" e "Construir uma tarefa descrita em prosa" têm uma entrada por variante no campo, e o menu mostra só a primeira variante de mesma frase que passa no filtro. A variante com `file:board-flow.yaml` de "Corrigir um bug" é a sequência `/board-flow:capture Bug:` e `/board-flow:fix`: se o dono responder a chave de um card, o agente pula o capture. As outras variantes são uma por topologia (`build-solo`, `build-hex`). `build-team` não tem `reproduce-fix-verify`, então nele "Corrigir um bug" só aparece com Jira (P13). · refinada em 2026-11-11
- O campo aceita de 3 a 8 ações por modo preenchido, e o menu mostra no máximo 5 — o dono aprovou 7 candidatas em construction e a regra "as 5 primeiras que passam no filtro". Se menos de 3 passarem, o menu mostra as que houver. Vete aqui se discordar. · mantida em 2026-11-11
- "Plugin instalado" se confere pelo mesmo caminho que o `cepa-doctor` já usa para listar plugins habilitados, sem leitor novo — duas formas de responder a mesma pergunta divergem. Vete aqui se discordar. · mantida em 2026-11-11
- `cepa-modes --menu <modo>` é o único lugar que monta o texto do menu. O `cepa`, o hook `session-mode.py` e o `/common:modes` chamam esse comando — mesma razão da tabela única em `_modes.py`. Vete aqui se discordar. · mantida em 2026-11-11
- O prompt de abertura começa com o marcador fixo `[menu do modo]` e leva o menu já montado. O hook reconhece o turno de abertura por esse marcador — o launcher sabe com certeza se veio pedido, e o hook não precisa adivinhar se um prompt é vago. Vete aqui se discordar. · mantida em 2026-11-11
- "Sem pedido" quer dizer: o `cepa` não recebeu prompt inicial, não recebeu `-c`, `--continue`, `--resume` nem `-p`, e não está num run do `cepa-until` — retomar uma conversa já traz o pedido dela. Vete aqui se discordar. · mantida em 2026-11-11
- O menu aparece mesmo quando o branch tem handoff pendente. O aviso de handoff do início da sessão continua vindo como hoje, na mesma resposta — decidir entre menu e handoff seria ler o estado do disco, que ficou fora. Vete aqui se discordar. · mantida em 2026-11-11
- `CEPA_MENU=off` desliga o prompt de abertura, no padrão de `CEPA_PREFLIGHT=off`, e `CEPA_MODO=off` continua desligando tudo. Vete aqui se discordar. · mantida em 2026-11-11
- Modo com lista vazia abre exatamente como hoje, sem aviso de "este modo ainda não tem menu" — o aviso gastaria um turno para não oferecer nada. Vete aqui se discordar. · mantida em 2026-11-11
- A ação "Ver o que falta para fechar a exploração" aponta para `/common:modes --exit`, e não para `/common:modes` puro nem para `cepa-modes --exit` no terminal. O menu aponta comandos de barra, e o CS-12 prova que o `--exit` chega ao `cepa-modes` (P15). · refinada em 2026-11-11
- A exibição no `/common:modes` não emite `mode_menu.shown` — a conta "escolhas ÷ exibições" mede a abertura, e a consulta manual a distorceria. Vete aqui se discordar. · mantida em 2026-11-11

## Riscos e o que ficou de fora desta especificação
- A telemetria não grava o modo da sessão. "Modos mais usados" hoje só se mede pelo histórico do shell de uma máquina.
- Cada abertura sem pedido passa a gastar um turno do modelo para mostrar o menu. O CS-8 dá a conta para decidir se o gasto se paga.
- O agente pode reescrever o menu em vez de mostrá-lo como veio. O CS-5 confere a instrução que o hook injeta, e não a resposta do agente, porque nenhum hook lê a redação de uma resposta.
- Em construction, num repo com Jira, as ações 6 (provar o que está em Review) e 7 (escrever o teste vermelho) ficam fora das 5 mostradas.
- `mode_menu.chosen` só reconhece número ou comando do menu na resposta seguinte. Quem lê o menu e escreve o pedido em prosa conta como "não escolheu".
- Duas ações aparecem sem comando: escrever o documento de estratégia (exploration) e escrever o teste vermelho do critério (construction). São candidatas a comando novo, fora desta especificação.
- Reconsiderar o menu dos modos documentation, design, refactor e reflection, hoje com lista vazia. Pedido do dono em 2026-11-11, ao manter a decisão #13: "registre em algum lugar a reconsideração da necessidade de fazer o mesmo para esses outros modos". Momento de reabrir: quando o CS-8 tiver a conta de uso do menu nos 3 modos preenchidos. Registrado também em `.claude/reminders`.
- O menu traduzido pelo agente pode sair com redação diferente a cada abertura. A ordem, a numeração e os comandos são fixos, a frase não.
- Fora desta especificação: a jornada por estado do disco, o modo `marketing`, o menu dos modos documentation, design, refactor e reflection, e gravar o modo no evento `session_start`.
