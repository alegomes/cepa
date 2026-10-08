# O Cepa no próximo nível: do card ao pacote de trabalho em espiral

**Status:** estratégia em exploração, revisão 3 (revisão 2 após painel de advisors de 2026-10-07, registro em `docs/reviews/2026-10-07-painel-cepa-proximo-nivel.md`; revisão 3 após as perguntas do dono de 2026-10-08) · **Data:** 2026-10-08 · **Modo da sessão:** exploração
**Fontes:** telemetria do harness (`~/.claude/cepa-telemetry/events-2026-0{7,8,9,10}.jsonl`, 25.253 eventos, 2026-07-11 a 2026-10-07), ledger de feedback (`~/.claude/cepa-feedback/`, 16 entradas), 463 transcrições de sessão em `~/.claude/projects/`, `BACKLOG.md` do Cepa, `docs/modos-de-trabalho.md`, `docs/execution-plan.md`, `docs/maestro.md`, e as três sessões de 2026-10-07 e 2026-10-06 citadas pelo dono.

## 1. A dor, reformulada

O dono descreveu quatro sintomas: muito tempo em pergunta e resposta; conversas que saem do foco; o harness mandou abrir duas sessões em vez de resolver sozinho; e as demandas são pequenas porque ele não sabe escrever o critério de aceite de um lote grande. O desejo: um pacote de trabalho que faça o produto nascer em ciclos, cada ciclo entregando valor numa aplicação que já funciona desde o primeiro.

Depois de medir, a dor se reformula assim: **o Cepa automatiza o que acontece dentro de um card e deixa com o humano tudo o que acontece entre cards, entre modos e entre sessões.** O dono virou o escalonador do sistema. A granularidade pequena, o pingue-pongue e o "abra duas sessões" são três faces desse mesmo fato.

## 2. O que os dados dizem

Cada número traz a conta.

**F1. O dono conversa; o harness só sabe rodar rotina.** Dos 4.684 prompts registrados pela telemetria, 4.098 são prosa (87%), 374 são comando avulso (8%) e 61 são rotina (1,3%). Ressalva do painel: a telemetria e as transcrições (F11) contam universos diferentes; 312 dos 374 comandos são as rodadas `drain-plan --max 1` do cepa-until, não digitação do dono. Tirando-as, a prosa é 4.098 em 4.372 (94%). As rotinas (drain, triage, prove-drain, session) são onde os gates e os sub-agentes vivem. Quase tudo o que o dono faz acontece fora delas.

**F2. Um quarto do que o dono digita é "1. sim".** Nas 911 mensagens não-slash das transcrições, 52% começam com item numerado (`1. sim`, `Q2.`, `F8.`), 37% são sim, não ou número puro, e `1. sim` mais `1. sim 2. sim` somam 205 ocorrências. O harness fabrica perguntas fechadas, o dono carimba, e o resultado quase nunca muda (o BACKLOG já registrou isso em 2026-08-10: de 20 interrupções, 10 eram mecânica reversível que ele só carimbou).

**F3. A rotina acaba e a sessão continua por mais 18 turnos.** Nas 52 sessões com rotina, houve 16 prompts antes dela e 931 depois (931 ÷ 52 = 17,9 por sessão). Ressalva do painel: não há corte antes/depois da política default-yes (agosto) nesta conta, então o número descreve o estado, não prova que a política falhou.

**F4. O desvio de foco é induzido pelo próprio harness.** Na sessão de 2026-10-06 (`ac145a5d`, "limpe a worktree", 6 turnos, 10 minutos) o SessionStart injetou o aviso "telemetria sem revisão há uma semana, sugira /common:metrics"; o agente o converteu em "Rodo /common:metrics agora? Recomendo sim"; o dono disse sim; o relatório gerou "Abro sessão no cepa para endurecer o lint? Recomendo sim"; o dono disse sim; a sessão terminou com commit no repo `cepa`. Nenhum dos dois passos era trabalho da sessão. A cadeia é sempre a mesma: aviso lateral → pergunta fechada com "Recomendo sim" → sim.

**F5. O "abra duas sessões" é desenho, não acidente.** Na sessão de hoje do wego-product (`73bd3f8b`, 14 turnos, 6h55, 2 compactações de contexto, 0 sub-agentes), o modo exploração barrou às 18:59 um `mv` fora de `docs/`; o agente registrou o desvio em `.claude/desvios.md`, acumulou 8 itens aprovados pelo dono, e às 21:19 recomendou "sessão sem modo para os 8 itens, depois sessão em descoberta". A regra "uma sessão = um modo, trocar exige sessão nova" (`docs/modos-de-trabalho.md`, `cepa-modos`) não dá ao harness nenhuma forma de abrir a sessão irmã. Sub-agente não resolveria: o gate de escrita é PreToolUse e vale para ele também. A segunda sessão (`b646bf40`) executou os 8 itens em 22 minutos e 2 turnos e parou no guard de dono único, porque a primeira ainda estava aberta.

**F6. As unidades de planejamento fatiam por arquivo, não por valor.** `/maestro:program-plan` agrupa slices por superfície disjunta de globs; `/common:plan` ordena itens de fila; `/common:spec` exige teste vermelho por critério. Nenhuma das cinco portas de planejamento tem o conceito "o que alguém consegue ver funcionando ao fim deste ciclo". A ordem de construção do ADR 0013 (gabarito → Contratos → demo → Regras → demo → Bradesco) saiu linear porque o harness não oferece outro formato. E o critério que o dono fixou hoje ("os módulos consomem o cadastro se, e somente se, uma demonstração responder com confiança às 34 perguntas") já é uma escada de valor pronta, que ninguém transformou em plano.

**F7. O harness briga com o modelo em vez de estruturar o trabalho.** Desde setembro: 506 bloqueios de build em segundo plano, 441 de parada com build pendente, 308 de monitor sem fim, 159 de espera ocupada, 377 negações de path-lock, 396 de reactor Maven. Soma: 2.187 bloqueios de higiene de processo em cinco semanas. O guard do Maven barrou o mesmo erro 1.731 vezes desde julho (232 + 1.103 + 389 + 7), com queda forte em setembro, o que sugere que algo ensinou. Ressalva do painel: 377 negações de path-lock e 396 do reactor não são higiene de processo e não somem com um supervisor rodando build; e os 506 bloqueios de build em segundo plano só disparam dentro do cepa-until (`CEPA_UNTIL_RUN`), onde um `claude -p` que deixa build em segundo plano morre em 15 segundos e leva o build junto. O `loop-budget` avisou 576 vezes, todas no `domain-dev`. Cada bloqueio custa um turno e contexto, e nenhum deles ensina nada permanente: o diretório de memória do projeto está vazio, e das 16 entradas de feedback só 1 foi triada.

**F8. Build vermelho em 35% das vezes, e o agente se declara provado quando não está.** 2.436 falhas em 6.889 builds (35,4%). No proof gate, 366 vezes o agente declarou `proven` e o guard computou outra coisa (272 needs-human, 94 unproven), 11% dos 3.284 vereditos. O gate funciona; o que ele revela é que o julgamento do agente sobre o próprio trabalho não é confiável, e isso justifica os gates, mas também mostra que eles produzem 546 vereditos needs-human (470 + 76), cada um uma pergunta para o dono.

**F9. O relatório ainda não é legível.** Em 1.055 relatórios medidos pelo `report-style-lint`, os desvios mais frequentes são abstração (185), falta do bloco "Pra você" (115), jargão (107) e falta de próximos passos (102). A reclamação de 2026-10-06 ("as providências não ficam claras") tem lastro.

**F10. Um quinto da atenção vai para o harness.** 819 dos 4.684 prompts (17,5%) e 181 das 927 sessões (19,5%) são no repo `cepa`. 674 commits no `cepa` desde julho (64 + 255 + 346 + 9). O BACKLOG tem 75 seções, 27 feitas, 48 abertas, quase todas sobre defeito do próprio harness (gate cego em worktree, hook que lê heredoc, path-lock em 5 cópias, loops sem teto, "não existe modo de saber se uma mudança no harness melhorou algo"). O repo tem 57.788 linhas de Python e 35.158 de Markdown, com 53 hooks só no plugin `common`.

**F11. O volume de sessões é do cepa-until, não do dono.** 324 das 460 sessões interativas são um único `/common:drain-plan --max 1` disparado pelo supervisor noturno. Sobram 136 sessões conduzidas pelo dono: mediana 7 turnos, p90 16, mediana 3 horas de janela. O cepa-until é a peça mais usada e a única que opera sem o dono na frente. Ele é o protótipo do que falta.

## 3. Diagnóstico: quatro causas

**C1. O humano é o escalonador.** Modo é por sessão, rotina é por card, worktree é por sessão. Nada no Cepa abre uma sessão, troca de modo ou encadeia descoberta → construção → prova sozinho. Só o cepa-until faz isso, e só para um tipo de item. Consequência direta: F3, F5, a mediana de 7 turnos por sessão conduzida.

**C2. A unidade de trabalho é o card.** Todo artefato de aceite (spec, acceptance, proof) é por card ou por critério; o aceite de "um lote" não existe. Sem unidade maior, o dono só consegue pedir pequeno (F6). Isso é o que ele chama de "não sei especificar critério de aceite de lote".

**C3. O harness fabrica interrupção.** Avisos laterais no SessionStart, "Recomendo sim" como forma obrigatória de qualquer decisão, bloqueios que devolvem o erro ao modelo sem ensinar (F2, F4, F7). O default-yes reduziu perguntas nas pontas e normalizou a pergunta fechada como moeda: hoje toda decisão vira "1. sim".

**C4. O harness cresce mais rápido do que se mede.** 20% da atenção, 48 itens abertos, zero memória consolidada, 1 feedback triado em 16 (F7, F10). Não há ciclo de aprendizado: a mesma falha reincide (Maven 1.731 vezes), e não há forma de saber se uma mudança no harness melhorou algo (item P1-4 do BACKLOG, aberto).

## 4. Caminhos considerados

### O1. Consolidar e endurecer (incremental)

Manter a arquitetura (modos, rotinas, gates, filas) e tratar os 48 itens do BACKLOG: fechar os furos dos gates, fundir os 5 path-locks, tornar o veredito de saída de cada modo mecânico, tirar avisos do SessionStart.

- Ganho: reduz F7, F9, parte de F4. Risco baixo, tudo é conhecido.
- O que não resolve: C1 e C2 ficam intactos. O dono continua escalonador e continua pedindo pequeno. É o caminho que o Cepa já percorre há três meses, e os números de setembro são o resultado dele.
- Custo: ~48 itens, cada um uma sessão. Perpetua F10.

### O2. Inverter o eixo: o pacote de trabalho como unidade, o harness como condutor

Trocar a unidade de "card" por **Epic**: um pacote de trabalho declarado pelo dono em prosa, que o harness transforma numa **escada de valor** de **incrementos** (ciclos), e conduz de ponta a ponta, abrindo as sessões que precisar, sem o dono na frente, com dois pontos de contato por ciclo.

Terminologia (revisão 3): a revisão 2 chamava o pacote de "empreitada", termo inventado. O pacote passa a se chamar **Epic**, que o Jira, o board-flow e o `/common:spec` já usam, e o ciclo passa a se chamar **incremento**, no sentido do Scrum: o resultado de um ciclo que funciona de ponta a ponta. O que o Epic do Jira não tem, e este documento acrescenta, é o ciclo e o roteiro de demonstração. Os termos vizinhos na literatura são o *bet* do Shape Up (pacote com apetite fixo, moldado em prosa, executado em ciclo) e o MMF do Kanban (Minimum Marketable Feature, o menor lote vendável). O texto abaixo usa "ciclo" e "incremento" como sinônimos.

Três peças novas, e o resto é poda:

**P1. Epic e escada de valor** (`docs/epics/<nome>.md` + uma fila `single-track` por ciclo com o campo `demonstra:` no cabeçalho; ver decisão 2).
- O dono escreve a intenção em prosa e responde a UMA pergunta por ciclo: *"ao fim deste ciclo, o que alguém consegue ver funcionando, que não via antes?"* Essa resposta é o **roteiro de demonstração** do ciclo. O roteiro é o critério de aceite do lote; o harness deriva dele os critérios por item e os testes vermelhos. O dono não escreve critério de item nunca mais.
- Cada ciclo é vertical: atravessa carga, modelo, API, tela e, quando houver, motor. O ciclo 1 é a versão 0.0.1 da funcionalidade: a implementação mínima que já prova o conceito e responde a uma pergunta real (não um *walking skeleton*, que é só encanamento sem resposta). Cada ciclo seguinte é a mesma funcionalidade com uma camada a mais de robustez ou sofisticação, ou uma jornada nova quando o roteiro de demonstração pedir. É o modelo em espiral de Boehm: cada volta ataca a maior incerteza restante. Nenhum ciclo entrega "uma camada" horizontal.
- Invariantes do pacote (o que nunca pode regredir) ficam declarados uma vez e viram testes que todo ciclo roda.
- A prova do ciclo é a que já existe no `ui-proof-reviewer`: o roteiro roda na superfície real, com efeito fresco (nonce), e o dono assiste ou lê o veredito. Nada novo de gate; o gate muda de altitude.

**P2. Condutor** (evolução do `cepa-until`).
- Um supervisor por Epic que percorre os estágios de um ciclo: descoberta (gabarito e roteiro), construção (itens derivados, fila single-track, drain), prova (roteiro na superfície), aterrissagem (merge na integração). Cada estágio é um `claude -p` em worktree própria e no modo certo; o modo sai de "por sessão" e vira "por estágio". O gate de escrita continua existindo, aplicado ao filho.
- A sessão interativa deixa de ser onde o trabalho acontece e vira o **cockpit**: o dono abre, vê o estado do Epic, decide o que só ele decide, fecha. O "abra duas sessões" de hoje seria o condutor abrindo a sessão sem modo para os 8 itens e depois a de descoberta, sozinho, com o dono lendo o resultado.
- Dois pontos de contato por ciclo, e só dois: aprovar a escada (antes) e aceitar a demonstração (depois). Tudo o mais é decidido e registrado (`debrief` já existe para o keep/overrule). As decisões mecânicas do condutor (classificar um needs-human nos sete motivos, detectar bloqueio reincidente, decidir se um veredito para o ciclo) são candidatas a um modelo de decisão tipada como o Jev da TypeSafe AI (early access em 2026-10, métricas só do fornecedor); fica como item do P2, não como pré-requisito.
- As perguntas que hoje nascem no meio (needs-human do proof, decisões de escopo) vão para um estacionamento do ciclo e chegam juntas no segundo ponto de contato, classificadas pelos sete motivos de `docs/needs-human-motivos.md`.

**P3. Poda e aprendizado.**
- Hooks de higiene de processo (build em segundo plano, monitor, espera ocupada, parada pendente) saem do caminho do agente e viram comportamento do condutor: quem roda build é o supervisor, com teto e registro, não o modelo. Os 2.187 bloqueios em cinco semanas são o custo de pedir ao modelo que não faça o que ele vai tentar fazer.
- Aviso lateral só no wrap-up, nunca no SessionStart. "Recomendo sim" em decisão reversível deixa de existir: executa e registra. Pergunta fechada fica reservada a irreversível, custo real ou bifurcação de preferência.
- Bloqueio que reincide vira memória: todo bloqueio de hook com o mesmo motivo acima de N vezes num repo escreve uma entrada no diretório de memória do projeto e a injeta no filho seguinte. O guard do Maven já distingue instalação recente (`fresh-root-install`); o passo de ensinar é o mecanismo inteiro, e ainda não existe.
- Scorecard semanal com quatro números, para o BACKLOG P1-4: turnos depois da rotina por sessão (hoje 17,9), builds vermelhos (35,4%), needs-human por ciclo, e fração de sessões no repo cepa (19,5%). Mudança no harness que não move um dos quatro não entra.

- Ganho: ataca C1, C2, C3 e C4 de uma vez. Reusa o que funciona: cepa-until (o único pedaço que já roda sem o dono), proof e ui-proof (o único aceite mecânico que mede valor na superfície), plan.yaml, debrief, worktree-merge.
- Risco: é uma mudança de centro de gravidade; o cepa-until hoje tem 3.352 linhas e 13 arquivos de teste (o número 1.425 da revisão 1 era o de 2026-09-26), quase todas tratando falha de um único estágio (cota, rede, SIGHUP, worktree sumida, lateral). Promovê-lo a condutor de quatro estágios multiplica esse custo por quatro. E o `/maestro:run` já é um condutor de filhos em worktree com merge train e `resume`, que rodou uma vez (agosto) e ficou na prateleira; o P2 precisa da autópsia dele antes de nascer.
- Custo: três peças, cada uma um ciclo do próprio Epic "Cepa em espiral". Dá para entregar o P1 sozinho e já mudar o que o dono escreve.

### O3. Condutor contínuo como serviço (daemon)

Igual ao O2 no desenho, mas o condutor vira um processo residente que observa o repo, a fila e o board, e age em eventos (card novo, build verde, veredito), sem janela de tempo. A sessão interativa é só uma vista.

- Ganho: zero latência entre estágios, nada espera o dono abrir terminal.
- Risco: infraestrutura (processo vivo, reinício, log, cota de uso da conta) para uma pessoa; a decisão 3 do cepa-until ("a main só muda com o dono presente") teria de ser revista; o modo de falha silencioso à noite já custou órfãos em 2026-09-26.
- Custo: O2 mais um serviço. Só vale depois de o O2 provar que os dois pontos de contato bastam.

## 5. Recomendação

**O2, nesta ordem: P1, depois P3, depois P2.** P1 sozinho muda a conversa (o dono passa a escrever roteiro de demonstração, não card) e cabe num ciclo. P3 corta o ruído que hoje come 20% da atenção e dá o scorecard que mede os outros dois. P2 é o que elimina o escalonador humano e deve nascer do cepa-until, não do zero. O3 fica como horizonte, condicionado ao scorecard.

O1 não é descartado: é absorvido. Dos 48 itens do BACKLOG, os que sobrevivem à poda do P3 entram como itens de construção dos ciclos; os outros são fechados com motivo.

### O primeiro Epic é o Contratos e Regras

O exemplo concreto, com o material de hoje:

| Ciclo | Roteiro de demonstração (o que alguém vê) | O que atravessa |
|---|---|---|
| 1 | Operador carrega o PDF do Cassi 2004 e a tela da demo responde 3 das 34 perguntas (prazo de pagamento, exigência de autorização, reajuste) mostrando instrumento, página e trecho | carga → cláusula tipada → API de leitura → `wego-contratos-demo` |
| 2 | As mesmas 3 perguntas para Cassi com a carta e o e-mail de 2022, com precedência entre instrumentos; mais 7 perguntas; conferência de carga marcando certo/errado | precedência no modelo → gabarito persistido → conferência de carga |
| 3 | Cenário "esta guia, nesta data": preço e prazo calculados pelo Regras lendo o Contratos só pela API | `wego-regras-backend` nasce → contrato público em `wego-platform-contracts` → `wego-regras-demo` |
| 4 | Bradesco inteiro no gabarito, sem tocar no Cassi; completude por regime | tipos novos de cláusula → invariante "Cassi não regride" |

A bancada de prova (`wego-contratos-demo` subindo, `docs/env.yaml` com portas e healthcheck, `docs/ui-proof.yaml` com um fluxo, Playwright) são os primeiros itens do ciclo 1, não um ciclo zero: sozinha ela não entrega valor, e sem ela o primeiro veredito sai NEEDS-HUMAN por manifesto ausente.

**Mapa de cobertura.** O risco que o dono nomeou (2026-10-08) é eleger mal as operadoras e nunca construir um tipo de cláusula importante. Nenhum método garante a escolha; a espiral garante que o erro custa um ciclo, não uma reescrita, porque o modelo cresce uma cláusula por vez e os invariantes barram regressão. Dois mecanismos reduzem o risco: (1) na descoberta de cada ciclo o harness monta o mapa de cobertura, tipos de cláusula e de instrumento presentes em todos os contratos em mãos contra os já modelados, e a próxima operadora é a que acrescenta mais tipos novos, não a mais importante comercialmente; (2) decisões estruturais caras de refazer (precedência entre instrumentos, vigência, regime) entram de propósito nos ciclos 1 e 2, mesmo com uma operadora só. O mapa depende de quantos contratos o dono tem além do Cassi; esse número não está neste documento.

Cada ciclo é uma demonstração que vale sozinha, e o ciclo 1 já é a demonstração que o dono pediu hoje em forma mínima.

**Como os quatro ciclos são executados.** Eles não são trabalho no repo cepa. São o primeiro Epic real, executado nos repositórios wego (`wego-contratos-backend`, `wego-contratos-demo`, depois `wego-regras-*`), e ao mesmo tempo o teste de uso do P1: o documento do Epic, o roteiro por ciclo e a derivação dos itens nascem fazendo o ciclo 1, não antes dele. O ciclo 1 roda com a ferramenta de hoje (fila `single-track` + `cepa-until`), com o dono fazendo à mão o papel do condutor entre estágios. O P2 (condutor) só entra quando houver pelo menos um ciclo inteiro medido.

**Quem escreve os critérios por item.** O harness, no formato que o `/common:spec` já exige (superfície observável + teste vermelho), derivando do roteiro de demonstração; o dono veta na seção "Decidido sem perguntar" do documento do Epic. As fundações técnicas não dependem disso: hoje o dono já não escreve critério técnico, escreve critério de comportamento; a qualidade técnica sempre foi dos gates (proof-reviewer, completion-auditor, code-reviewer do build-hex, arquitetura hexagonal) e dos ADRs, e isso não muda. O que protege a fundação no novo desenho é o primeiro ponto de contato: a escada aprovada traz, por ciclo, o esqueleto técnico que será criado (módulos, contratos, tabelas), e é ali que o dono veta antes de qualquer item existir. A ordem linear do ADR 0013 (modelo inteiro, depois API inteira, depois demo) deixa de existir; o modelo cresce uma cláusula por vez, puxado pela pergunta que o ciclo responde.

## 6. O que não muda

Os gates de construção (completion-auditor, proof-reviewer, green-or-revert, acceptance-gate) ficam como estão: são a parte madura e é por causa deles que o condutor pode decidir sozinho. O card avulso continua existindo: refinamento pequeno entra por `/board-flow:capture` e pela fila `single-track` de sempre, sem Epic por cima; o Epic é envelope opcional para o que merece ciclo e demonstração. O board-flow continua sendo o espelho no Jira. O plain-report continua sendo o formato do relatório, com a regra nova de que a lista final só traz o irreversível.

## 7. Riscos que todo caminho tem de respeitar

- **R1.** A main só muda com o dono presente (R1 do documento de 2026-09-26). A decisão 3 do cepa-until é outra, e mais restritiva: um commit por item, numa única branch, sem merge train. O P2, com worktree por estágio e aterrissagem na integração, revoga a decisão 3 paro Epics. Isso é decisão do dono (D7 abaixo), não detalhe.
- **R2.** Roteiro de demonstração em prosa não é contrato. O harness o traduz em fluxo do `docs/ui-proof.yaml` antes de construir, e o dono aprova a tradução, não a prosa.
- **R3.** Reduzir pergunta sem reduzir erro é só esconder o erro. O debrief e o scorecard são o que torna o default seguro; sem eles o P2 não entra.
- **R4.** Promover o cepa-until sem antes podar o resto apenas muda onde os 2.187 bloqueios acontecem.

## 8. Discordâncias do painel

Painel de 2026-10-07, sete lentes isoladas (contrarian, fundamentalista, expansionista, outsider, executor, operador-sre, custo-de-manutenção), área arquitetura. Registro completo em `docs/reviews/2026-10-07-painel-cepa-proximo-nivel.md`. Abaixo, o que as lentes discordaram entre si ou do documento. Nada aqui foi mediado; a decisão é do dono, na seção 9.

**X1. De onde nasce o condutor.** O documento diz "evolução do cepa-until". A contrarian e a custo-de-manutenção dizem que o P2 é o Maestro com outro nome (fork de filhos em worktree, event loop, merge train, resume já existem em `docs/maestro.md`) e que um terceiro orquestrador ao lado de dois que não fecham o ciclo é inaceitável: escolher um tronco e deprecar o outro. A expansionista diz que o condutor é a união dos dois (o Maestro dá o esqueleto de filhos, o cepa-until dá janela, cota, lateral e operação sem dono). A operador-sre diz que o que faz o cepa-until sobreviver à noite é fazer uma coisa só, e que quatro estágios herdam o custo de falha vezes quatro. Ninguém defendeu nascer do cepa-until sozinho, como o documento propôs.

**X2. `mode: espiral` no plan.yaml.** Quatro lentes (executor, custo, fundamentalista, expansionista) convergiram contra: o esquema declara dois modos, cada consumidor recusa o outro pelo nome, e um terceiro modo reabre `cepa-plan`, `next`, `drain-plan`, `maestro:run` e `cepa-dor`. A alternativa unânime: o Epic é um documento acima do plano, e cada ciclo materializa um `single-track` comum com um campo a mais no cabeçalho. Não há discordância; há correção do documento.

**X3. O custo de trocar de modo é defeito ou é desenho.** O documento lê o "abra duas sessões" como falha (F5). A fundamentalista cita a Peça 2b de `docs/modos-de-trabalho.md`: a fricção é deliberada, "trocar de atividade deveria custar", e o P2 a revoga em silêncio. A contrarian concorda: é regra que o dono escolheu, não limitação. A expansionista discorda dos dois: a troca de modo por filho `claude -p` com modo próprio é uma primitiva de sessão barata (`/common:modos --delegar`) que mata F5 hoje nas 136 sessões conduzidas, sem esperar condutor. A custo-de-manutenção aponta o preço: dois regimes de modo convivendo (sessão do dono e filho do condutor), com um `if` em cada hook de modo. O executor acrescenta um fato: hoje o cepa-until não passa modo nenhum ao filho, então "o gate continua valendo no filho" é falso até alguém escrever o arquivo de modo na worktree do estágio.

**X4. Dois pontos de contato por ciclo.** A contrarian: estacionar needs-human não elimina carimbo, só muda o momento, e F2 mostra que lote de pergunta fechada vira "1. sim 2. sim". A fundamentalista: aprovar a escada vira consentimento em branco para quatro estágios, contra a `scope-discipline` ("uma aprovação libera até o próximo checkpoint"). A operador-sre: needs-human em item com dependentes não pode esperar o fim do ciclo, porque os itens seguintes ou travam o run ou constroem sobre decisão não tomada; o ciclo deve parar em `aguardando-dono` com aviso. A outsider: quem classifica a decisão como estacionável é o mesmo agente que erra 11% dos `proven`. Do outro lado, a expansionista e a custo-de-manutenção: não criar estacionamento novo, o segundo ponto de contato é o `/board-flow:decide` filtrado pelos cards do ciclo, e o sexto lugar de pendência é o problema, não a solução.

**X5. Os hooks de higiene.** O documento manda tirá-los do caminho do agente. Executor e operador-sre: manter; o `no-background-build` só dispara sob o cepa-until e evita que o build morra com o `claude -p`; tirá-lo troca 506 bloqueios por 506 itens fechados sem build. A operador-sre propõe manter o guarda e tirar a conversa (bloquear sem texto longo). A contrarian lembra que o `expertise-append` e o debrief já gravam aprendizado; o que falta é uso, não mecanismo.

**X6. "Recomendo sim" em decisão reversível.** Três posições. Fundamentalista: a regra já existe na skill `default-yes` e é descumprida; o README diz que instrução não segura, logo a resposta é trava (o lint barrar item "Recomendo sim" sobre ação reversível), não mais texto. Executor: a obrigação de "Recomendo sim/não" por item está no `~/.claude/CLAUDE.md` do dono, fora do repo e acima de qualquer skill; sem mudar lá, a poda vira aumento de desvios no lint. Outsider: o documento não descarta a hipótese de que o dono diz "sim" porque as recomendações são boas, e não há contagem de "não".

**X7. O que prova um ciclo.** Fundamentalista e contrarian: o ciclo 3 ("só pela API") e o ciclo 4 ("Cassi não regride") não têm tela; a altitude é derivada do critério, não escolhida pela superfície conveniente, então o roteiro de UI prova o lote e a prova por item continua. Operador-sre: um ciclo vertical não tem unidade de rollback; a lateral do vermelho é por item, e "verde por item, vermelho por ciclo" não tem regra. Executor: o ciclo 1 nasce sem `docs/ui-proof.yaml`, sem `env.yaml`, sem Playwright na demo, e o primeiro veredito possível é NEEDS-HUMAN por manifesto ausente; falta um passo 0 com dono no repo-alvo. Ninguém contestou o roteiro de demonstração como origem dos critérios; a expansionista ainda viu nele o tutorial e o script de demo comercial saindo de graça se o formato for fixado agora.

**X8. O scorecard.** Executor: três dos quatro números já saem do `cepa-metrics`; publicar já, e a medição vem antes do P1, não depois. Custo-de-manutenção: não transformar em gate (seria o 54º hook lendo 25 mil eventos por merge). Contrarian: "turnos depois da rotina" cai a zero no dia em que a rotina rodar por `claude -p` sem nada melhorar, e "fração no cepa" sobe durante a próprio Epic do Cepa; o critério "não move, não entra" barra P1, P2 e P3. Expansionista: sem a versão do plugin em cada evento, o scorecard não atribui efeito a mudança.

**X9. Epic multi-repo.** Só a expansionista levantou, com severidade crítica: o ciclo 3 do exemplo atravessa três repositórios e tudo o que P1 reusa é por repo. Nenhuma outra lente contestou. Fica como lacuna do documento, não como discordância.

**X10. O documento não se sustenta sozinho.** A outsider: nenhum termo central (modo, rotina, card, gate, hook, cepa-until, Maestro) é definido no texto, e o exemplo do WeGo aparece sem contexto. Para leitor de fora, a recomendação parece gosto vestido de diagnóstico. Fica registrado; este documento é para o dono, e um glossário entra se ele virar leitura de terceiros.

## 9. Decisões do dono

Cada item é uma pergunta fechada, com a recomendação e o porquê. **Respostas do dono (2026-10-08): sim nas dez.** Na 4 o dono pediu confirmação do efeito: o ciclo é interrompido (`aguardando-dono`) só quando o needs-human cai em item que aparece no `blocked_by` de outros; needs-human em item sem dependentes não interrompe, a pergunta espera o fim do ciclo.

11. **A demo do Contratos vive em repositório próprio (`wego-contratos-demo`), como no ADR 0013, e não como módulo do `wego-contratos-backend`?** Eu recomendei o módulo; o dono decidiu **repositório próprio** (2026-10-08). Consequência: o ciclo 1 do Contratos é multi-repo desde o início (X9), e o P1 precisa aceitar `demonstra:` apontando para a prova de UI em outro repositório.

**Quando o Cepa muda.** As três peças são elas mesmas um Epic, `docs/epics/cepa-em-espiral.md`, com quatro ciclos e seus roteiros, construído por filas `single-track` drenadas pelo `cepa-until` à noite, intercalado com o Epic de produto.

1. **O condutor nasce da união cepa-until + Maestro, com o cepa-until como tronco (janela, cota, lateral, estado em disco) e o fork de filhos e o merge train do Maestro extraídos como biblioteca, e o `/maestro:run` deprecado quando o condutor rodar a primeira onda paralela?** Recomendo sim: resolve X1 sem terceiro orquestrador e sem reimplementar o que o Maestro já provou numa onda real.
2. **O Epic é um documento acima do plano, e cada ciclo materializa um `single-track` comum com um campo `demonstra:` no cabeçalho, sem terceiro modo no esquema?** Recomendo sim: unanimidade do painel (X2), zero consumidor a mudar.
3. **A troca de modo por estágio fica permitida só para filhos do condutor, como revogação explícita e registrada da Peça 2b nesse escopo, enquanto a sessão interativa mantém o custo de trocar?** Recomendo sim: preserva a fricção onde ela protege o dono de si mesmo e tira onde só atrapalha a máquina (X3). O `/common:modos --delegar` da expansionista entra como primeiro uso da mesma primitiva.
4. **O ciclo para em `aguardando-dono` quando um needs-human cai em item com dependentes, e só o needs-human sem dependentes vai para o `/board-flow:decide` filtrado pelo ciclo, sem estacionamento novo?** Recomendo sim: fecha X4 pelos dois lados (sem consentimento em branco, sem sexta fila).
5. **Os hooks de higiene ficam, com a mensagem de bloqueio encurtada a uma linha?** Recomendo sim: X5 mostrou que o que custa é a conversa, não o guarda.
6. **Eu altero a regra transversal do seu `~/.claude/CLAUDE.md` para que "Recomendo sim/não" valha só em item irreversível, de custo real ou de preferência, e o lint passa a barrar "Recomendo sim" sobre ação reversível?** Recomendo sim: sem o primeiro a poda é impossível (X6), sem o segundo é só texto. É o seu arquivo; por isso pergunto. Medida de 2026-10-08, em todas as transcrições: de 1.096 itens com "Recomendo sim/não" respondidos pelo dono em 112 sessões, 895 concordaram (81,7%), 79 discordaram (7,2%) e 122 vieram como contrapergunta ou correção (11,1%); uns 10 dos 79 são "não entendi", logo a discordância real fica perto de 6%. A regra nova tem de prever os 20% em que a pergunta valeu, não eliminar a pergunta.
7. **A decisão 3 do cepa-until (uma branch, sem merge train) cai paro Epics: cada ciclo vive em branch própria, aterrissa na integração só depois do seu aceite, e o ciclo seguinte espera?** Recomendo sim: é a única regra que dá unidade de rollback ao ciclo (X7) e mantém R1.
8. **A ordem passa a ser: scorecard com os três números que já existem → P1 (Epic e escada, multi-repo desde o início, com a bancada de prova como primeiros itens do ciclo 1) → P2 (condutor) → poda guiada pelo scorecard?** Recomendo sim: X8 mostrou que medir antes é pré-requisito, e X5 que a poda sem condutor não entrega nada.
9. **O primeiro Epic é Contratos e Regras, e a bancada de prova (`wego-contratos-demo` subindo, `docs/env.yaml`, `docs/ui-proof.yaml` com um fluxo, Playwright) entra como primeiros itens do ciclo 1, sem ciclo zero?** Recomendo sim: é o material mais maduro que existe hoje (34 perguntas, gabarito Cassi); a bancada não entrega valor sozinha, por isso não ganha ciclo próprio, mas sem ela o primeiro veredito sai NEEDS-HUMAN por manifesto ausente.
10. **Cada evento de telemetria passa a gravar a versão do plugin que o emitiu?** Recomendo sim: um campo, e é o que permite dizer "a versão X moveu o número Y".
