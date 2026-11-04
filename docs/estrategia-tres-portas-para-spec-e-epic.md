# Três portas para o `/common:spec` e o `/common:epic`: discovery, planning-lead e "Decided without asking"

**Status:** estratégia em exploração, revisão 2 (revisão 1 passou pelo painel de advisors de 2026-11-04, síntese com as discordâncias nomeadas em `docs/reviews/2026-11-04-painel-tres-portas.md`; o dono aprovou O2' e as decisões D1 a D7 da seção 6 em bloco em 2026-11-04; próximo passo é uma sessão de `/common:spec` sobre os oito itens de O2', sem fila ainda) · **Data:** 2026-11-04 · **Modo da sessão:** exploração
**Fontes:** os agentes `discovery/agents/{discovery-lead,epic-briefer}.md`, `build-hex/agents/{planning-lead,product-manager,epic-author}.md`, `build-team/agents/planning-lead.md`, o comando `discovery/commands/capture.md`, os comandos `common/commands/{spec,epic,debrief}.md`, o skill `common/skills/autonomous-mode/SKILL.md`, os hooks `common/hooks/{spec-readiness-gate,write-mode-gate,_modes,handoff-seeds-gate,expertise-append}.py`, o CLI `common/bin/cepa-plan`, os documentos `docs/spec/*.md`, `docs/epics/cepa-em-espiral.md`, a fila `.claude/queues/cepa-espiral-c1/queue.yaml` e o `BACKLOG.md`, todos lidos no disco em 2026-11-04.

## 0. Quem é quem

Para quem chega de fora (pedido do painel). **Dono** é a pessoa que decide o que o produto faz, neste repositório o autor do harness. **Cepa** é este repositório, o harness de plugins para o Claude Code. Os plugins citados:

| Plugin | O que é | Agentes e comandos que aparecem aqui | O que produz |
|---|---|---|---|
| `common` | base, de que os outros dependem | `/common:spec`, `/common:epic`, `/common:debrief`, `cepa-plan`, `spec-readiness-gate` | `docs/spec/<slug>.md`, `docs/epics/<name>.md`, filas |
| `discovery` | valida uma oportunidade com evidência de usuário, card a card num board Jira | `discovery-lead` (roteia), `epic-briefer` (escreve o brief final) | `docs/discovery/<card>/{framing,research,assumptions,audit,handoff}.md` e um card Epic no board de engenharia |
| `build-hex` e `build-team` | constroem código; variantes do mesmo fluxo para backend hexagonal e para time full-stack | `planning-lead` (orquestra), que chama `product-manager` e `epic-author` em paralelo | `spec/<slug>.md` (hex) ou `specs/<slug>.md` (team), lida pelo `engineering-lead` |
| `board-flow` | ponte com o Jira; único caminho de escrita é o `atlassian-expert` | `/board-flow:execute`, `/board-flow:advance` | transições e comentários de card |

**Por que a entrevista vale mais que um rascunho autônomo.** O `/common:spec` e o `/common:epic` existem porque a informação que falta numa especificação não está em lugar nenhum que se possa ler: está na cabeça do dono. Um rascunho escrito por agente preenche os campos com o que o agente imaginou, e o gate aceita, porque o gate confere forma, não verdade. A estratégia anterior (`docs/estrategia-cepa-proximo-nivel.md`, achado F8) mediu isso no gate de prova: em 11% dos vereditos o agente se declarou provado quando não estava. Uma spec "pronta" sem o dono repete o mesmo defeito uma camada antes, e o custo de uma decisão de escopo errada é código construído em cima dela.

## 1. A pergunta

Hoje há três lugares onde alguém já pensou sobre o que construir, e nenhum chega até a entrevista:

- o plugin `discovery`, que entrega um `handoff.md` antes de qualquer entrevista;
- o `planning-lead`, cujo `product-manager` já responde segmento e métrica de sucesso, dois dos campos que o `/common:epic` passou a exigir em 2026-11-03 (commit 8da04f7);
- a seção "Decided without asking", que os dois comandos de entrevista escrevem ao fim com um "Vete aqui se discordar" que ninguém lê de volta. O painel apontou, com razão, que esta não é uma porta de entrada como as outras duas: é saída da entrevista. Ela entra aqui porque tem dois problemas distintos, ninguém a reaproveita na entrevista seguinte e ninguém a veta, e as duas soluções são tratadas separadamente abaixo.

A pergunta: como cada porta passa a alimentar a entrevista, sem que a entrevista deixe de ser entrevista.

## 2. O que cada porta produz e quem lê (mapa)

Cada achado traz onde foi lido.

**F1. O `discovery` entrega um brief e um card, e ninguém do lado da construção abre o brief.** O `epic-briefer` escreve `docs/discovery/<card>/handoff.md` e cria um Epic no board de engenharia com uma frase na descrição: "Build-side planning-lead / epic-author: read the brief for full context" (`epic-briefer.md`, passo 5). O esqueleto do brief:

```
# Delivery brief: <título>
## What user-visible change is being committed to?
## Who benefits?
## What has been validated? / invalidated? / inconclusive?
## Validation seeds        (Signal, Expected direction, Falsifier)
## Carry-forward notes
## Boundaries (IN scope / OUT of scope)
## Suggested starter Stories
```

`grep "docs/discovery\|handoff.md"` em `build-hex/`, `build-team/`, `board-flow/` e `common/commands/` devolve zero linhas: nenhum consumidor é mandado ler o brief. O `handoff-seeds-gate.py` existe em `common/hooks/` e exige os rótulos `Validation seeds` e `Carry-forward notes` na escrita do brief.

**F2. O `discovery` exige Jira para começar.** `/discovery:capture` aborta sem `board-flow`. No Cepa, o único arquivo em `docs/discovery/` é `until-fim-sem-dono/revisao-3.md`, escrito à mão fora do formato (sem card, sem framing, sem audit): é a revisão de uma estratégia que passou por um painel e cujas correções o dono aprovou, guardada ali por falta de lugar melhor. O formato oficial nunca rodou aqui.

**F3. O `planning-lead` escreve uma spec de uma página num formato que o `/common:spec` não lê.** Seções: Goal, Approach, Trade-offs, Open questions, Assumptions, Biggest risk, Proposed Stories com acceptance (`planning-lead.md`, passo 3). Diretório `spec/` no `build-hex` e `specs/` no `build-team`. Sem `**Surface:**` nem `**Red test:**`, o `spec-readiness-gate` não a vê e o `cepa-plan from-spec` não a transforma em fila. Não há nenhuma no Cepa: o `planning-lead` nunca rodou neste repositório.

**F4. O `product-manager` já responde parte do que o Epic pede.** Seus cinco bullets: Goal, Segment, Priority, Scope boundaries, Success metric. O `/common:epic` exige `## Who it is for`, `## Out of scope` e `## Outcome metric` com Baseline, Target e Source. Segment responde "para quem", Scope boundaries responde "fora", Success metric dá o Target. Baseline e Source ninguém responde antes de medir. Tudo isso é proposta de um agente que não leu usuário nenhum, o que importa na seção 4.

**F5. O `planning-lead` roda sem perguntar e registra decisões no formato que o `/common:debrief` lê.** Em run autônomo, toda decisão que cruza a fronteira de uma Task vira um bloco `### Decision:` com Altitude, Options considered, Chosen e Rationale. O `/common:debrief` localiza o run em `docs/autonomous/<run>/state.yaml`, percorre os blocos com o dono (keep, overrule, refine) e grava o veredito no arquivo de expertise do agente, que o agente lê ao iniciar. Esse circuito existe para o que nasce de run.

**F6. A seção "Decided without asking" não tem leitor que a devolva ao dono.** Quem a lê, por `grep -rli`: o `spec-readiness-gate`, que confere só a existência (`spec-readiness-gate.py`, linha 350); testes; `docs/commands.md` e `docs/internals/hooks.md`, que a descrevem; e a fila `cepa-espiral-c1`, onde um construtor a usa como restrição de escopo ("a spec (Decidido sem perguntar) manda ler só o ledger", `queue.yaml`, linha 67). O `/common:debrief` não a lê: só resolve runs, e o Pass B procura frases em inglês. As sete decisões reais (3 em `cepa-espiral-c1.md`, 2 em `planejador-de-lotes-paralelos.md`, 2 em `cepa-em-espiral.md`, contadas nas linhas `- ` da seção), nenhuma com registro de mantida ou vetada:

1. `/common:epic` reusa a skill e o hook do `/common:spec`, como comando novo e não flag.
2. O brief do encadeamento é o parágrafo "Próximo passo" do handoff, não arquivo novo.
3. O scorecard lê as mesmas fontes que o `cepa-metrics`.
4. CS-5 (trava de escrita) entra na spec do planejador mesmo sendo de outro assunto.
5. O planejador é um modo do `/maestro:program-plan`, não comando novo.
6. O Epic de produto Contratos tem documento próprio em `wego-product/docs/epics/`.
7. A demo do Contratos vive em repositório próprio `wego-contratos-demo`.

As decisões 1, 5, 6 e 7 são de escopo e arquitetura; as três já viraram código ou repositório. Nenhuma linha segue um formato fixo: há frase corrida, bullet de quatro linhas com negrito e referência a ADR.

**F7. Os dois comandos leem `docs/` antes de perguntar, mas sem nome.** O `/common:spec` manda ler "os documentos em `docs/`"; o `/common:epic`, "a estratégia, as especificações, os ADRs" (passo 2 de cada um). Nenhum cita `docs/discovery/`, `spec/` ou a seção de decisões de outra spec.

## 3. Diagnóstico

**C1. Cada porta escreve para um leitor que não existe.** O brief é escrito para um `epic-author` que só recebe prosa do orquestrador (F1); a spec do `planning-lead` não é medida por gate nenhum (F3); as decisões são escritas para um dono que não é convidado a lê-las (F6).

**C2. O único barramento ligado é o card do Jira, e ele carrega prosa, não campos.** Um campo com nome vira parágrafo, e o comando que precisa do campo pergunta de novo.

**C3. A entrevista nasce vazia por desenho.** O "ler antes de perguntar" é regra de bom senso, não passo com entrada declarada (F7). Quando há brief, o dono responde de novo o que já está escrito.

## 4. Caminhos considerados

### O0. Só nomear as entradas (proposto pelo painel, lente custo-de-manutencao)

Uma linha no passo 2 de cada comando: "antes de perguntar, leia `docs/discovery/*/handoff.md`, `spec/*.md`, `specs/*.md` e a seção de decisões das outras specs, se existirem, e proponha a resposta dizendo de onde veio". Sem flag, sem parser, sem conceito novo.

- Ganho: fecha F7 e C3 com o custo de duas edições de prompt. O agente já lê prosa.
- O que não resolve: F6 (o veto) fica intacto, porque ele precisa de um leitor em código para ser cobrado; e nada prova que a proposta foi desafiada em vez de aceita.
- Custo: o menor de todos.

### O1. Endurecer o barramento do Jira

O card passa a carregar os campos do Epic como seções nomeadas; o `/common:epic` ganha `--from-jira <KEY>`.

- Ganho: fecha F1 sem formato novo.
- O que não resolve: F2 (sem Jira, nada passa), F3, F6, C2.
- Custo: baixo.

### O2. O arquivo como barramento (revisão 1) e o que o painel derrubou

A revisão 1 propunha `--from <arquivo>` nos dois comandos, um parser de três formatos, o `/common:debrief` aceitando caminho e gravando vereditos no arquivo, e um arquivo de expertise para a entrevista. O painel derrubou quatro premissas, todas conferidas no disco depois:

- o `spec-readiness-gate` não rebaixa `Status`, só recusa a escrita; o debrief teria de gravar `draft` por conta própria, virando segundo escritor de um arquivo que os comandos declaram só deles;
- o formato de linha `- decisão — porquê` não casa com nenhuma das sete decisões reais, e o travessão é proibido pela regra editorial;
- `common/expertise/spec-interviewer-mental-model.yaml` não existe, os comandos não carregam expertise, e o `expertise-append.py` aborta em silêncio em arquivo ausente (linha 111);
- pré-preencher como `- [x]` no `/common:spec` declara que o dono respondeu o que nunca viu.

### O2'. O arquivo como barramento, revisado após o painel

Junta O0 com o mínimo de código que o veto exige.

**Entradas.** O passo 2 dos dois comandos nomeia as três fontes (O0). Toda proposta feita a partir de um arquivo lido traz, no turno, um de dois rótulos: `evidência` (brief do `discovery`, que carrega audit) ou `proposta de agente` (spec do `planning-lead`, decisão de outra entrevista). O cabeçalho do documento ganha uma linha `Fontes lidas:` com os caminhos, uma vez. Nenhum sufixo na linha do critério, que o gate parseia. `--from <arquivo>` existe como atalho opcional que só aponta um arquivo a mais para o passo 2.

**Ritmo.** Campo com proposta ocupa o turno da pergunta correspondente, com a proposta antes da pergunta, como o `/common:epic` já manda. Nada vira `- [x]` sem resposta do dono. Decisão herdada de outra entrevista entra na seção "Decided without asking" do documento novo, com a origem, nunca como pergunta respondida.

**Veto.** O ritual é dos próprios comandos: `/common:spec --continuar` e `--fechar`, e `/common:epic <name>` sobre um documento existente, abrem listando as linhas da seção sem veredito, uma por turno, e gravam `· mantida em <data>`, `· vetada em <data>: <razão>` ou `· refinada em <data>` na própria linha. A linha inteira é a decisão; não há separador obrigatório. `Status` não muda pelo veto: uma decisão vetada vira pergunta aberta só se o dono mandar, no mesmo turno. Só linhas sem marcador entram na caminhada. O `/common:debrief` não muda.

**Leitor em código.** Um único parser, `cepa-plan decisions <arquivo>`, lê a seção nos nomes pt-BR antigo e novo como o gate já faz, e devolve as linhas com e sem veredito. Ele serve ao veto e a um check do `/common:doctor`: "N decisões sem veredito em `docs/spec/` e `docs/epics/`", com o comando por arquivo. As sete de hoje aparecem no próximo `doctor`.

**Fechamento.** Ao gravar `ready`, os comandos imprimem a contagem de decisões sem veredito.

**Discovery.** O `epic-briefer` grava no card o caminho do brief e o repositório onde ele vive, sem comando literal. O `<slug>` do Epic é escolhido na entrevista. A regra "Brief, not Epic" passa a nomear os dois consumidores: `epic-author` no board, `/common:epic` em arquivo.

- Ganho: fecha F1, F2, F3, F6 e F7 sem Jira, sem formato novo, com um parser só, sem segundo escritor e sem tocar no debrief.
- O que não resolve: o veto não reabre o que já foi construído (as decisões 1, 5, 6 e 7 já são código); é registro, não desfazimento. Continuam dois formatos de spec.
- Custo, com memória de cálculo: item 0, quarentenar `tests/test_cepa_until_dead_supervisor.py` (vermelho na base, para o drain no primeiro item); 1, passo 2 nomeado e rótulos nos dois comandos; 2, ritmo e regra do `- [x]` nos dois comandos, com teste de transcrição; 3, `cepa-plan decisions` com teste sobre os três documentos reais; 4, veto nos dois comandos; 5, check no `doctor`; 6, contagem no fechamento; 7, `epic-briefer` e regra "Brief, not Epic". Oito itens, um ciclo.

### O3. Unificar: todo caminho termina em `docs/spec/` ou `docs/epics/` no formato do comando

O `planning-lead` passa a escrever `docs/spec/<slug>.md` com Surface e Red test preenchidos por ele; o `epic-briefer` abre `docs/epics/<card>.md` em `draft`.

- Ganho: um formato, um diretório, um gate.
- O que não resolve: o `planning-lead` inventa Surface e Red test sem o dono, e o gate aceita (seção 0). O `epic-briefer` abrindo `docs/epics/` fere "Brief, not Epic" e cria dois donos para o mesmo arquivo.
- Custo: três plugins mudam de contrato ao mesmo tempo.

## 5. Recomendação

**O2'.** O0 sozinho não cobra o veto; O1 mantém o Jira obrigatório; O3 troca a entrevista por um rascunho que o gate aceitaria sem o dono. O2' é O0 mais o único parser que o veto precisa, e respeita a regra de um escritor por arquivo.

Ordem de construção: item 0, depois 6 (a contagem no fechamento é a mudança mais barata e a primeira que o dono vê), 3, 5, 4, 1, 2, 7.

## 6. Decisões (aprovadas pelo dono em 2026-11-04)

- **D1.** O veto mora nos comandos de entrevista, não no `/common:debrief`, e nunca muda `Status`.
- **D2.** Entradas nomeadas no passo 2 com dois rótulos de proveniência; `--from` só como atalho opcional.
- **D3.** Um parser só, `cepa-plan decisions`, lendo a linha inteira como decisão; nenhum separador obrigatório.
- **D4.** O `doctor` lista a dívida de veto.
- **D5.** Nenhum arquivo de expertise para a entrevista nesta rodada; regra que o dono quer fixar vai para o `CLAUDE.md` do repo.
- **D6.** O card do `discovery` carrega caminho e repositório do brief, sem comando literal; o `<slug>` é da entrevista; a regra "Brief, not Epic" nomeia os dois consumidores.
- **D7.** Unificar `spec/`, `specs/` e `docs/spec/` sai desta estratégia sem gatilho: não há spec do `planning-lead` no Cepa para justificar o parser de ponte.

## 7. Riscos

- **R1.** A proposta com rótulo é aceita sem desafio, e a entrevista encurta sem ganhar qualidade. Mitigação: teste de transcrição como o do CS-5 de `cepa-espiral-c1` (uma transcrição de teste do comando, lida pelo `proof-reviewer`), exigindo que toda proposta rotulada apareça desafiada uma vez; e uma conta no `cepa-metrics`, propostas rotuladas aceitas sem alteração versus alteradas, para medir o atalho depois de entregue.
- **R2.** O veto é registro sem efeito sobre o que já foi construído, e o dono pode achar que desfez algo. Mitigação: o turno do veto diz "isto já virou código em <fila>" quando a fila derivada da spec existe, lendo o `source:` das filas.
- **R3.** O parser da seção envelhece quando o formato muda. Mitigação: um parser só, em `cepa-plan`, com teste sobre os três documentos reais.
- **R4.** O `discovery` continua sem rodar no Cepa, e D6 fica sem uso. Aceito: custa duas linhas.

## 8. O que fica de fora

- Unificar os diretórios de spec (D7).
- Fazer o `discovery` funcionar sem Jira.
- Expertise para comandos de entrevista (D5).
- Propagar um veto para a fila ou para o código já construído.
- Mudar o bloco `### Decision:` do modo autônomo ou o `/common:debrief`.
