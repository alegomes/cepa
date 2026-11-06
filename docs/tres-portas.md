# As três portas da entrevista: como usar

Antes de você abrir uma entrevista com `/common:spec` (que transforma uma ideia em especificação pronta para construir) ou com `/common:epic` (que transforma um pacote de trabalho num Epic demonstrável em ciclos), às vezes alguém já pensou no assunto e deixou isso escrito. Este guia diz o que fazer com cada um desses três escritos, que chamamos de **portas**:

1. **O brief do `discovery`:** o arquivo `docs/discovery/<card>/handoff.md`, que o agente `epic-briefer` escreve quando uma oportunidade foi validada com evidência de usuário.
2. **A spec do `planning-lead`:** o arquivo `spec/<slug>.md` (plugin `build-hex`) ou `specs/<slug>.md` (plugin `build-team`), que o agente `planning-lead` escreve sozinho, sem entrevistar ninguém.
3. **As decisões sem veredito:** as linhas da seção `## Decided without asking` de specs e Epics já escritos. São as decisões que o agente tomou sem perguntar, cada uma com um "Vete aqui se discordar" que até agora ninguém lia de volta.

As duas primeiras portas alimentam uma entrevista nova. A terceira é o que sobra de uma entrevista antiga e precisa da sua resposta.

## O que já existe e o que chega com a fila `tres-portas-c1`

O desenho foi aprovado em 2026-11-04 (`docs/estrategia-tres-portas-para-spec-e-epic.md`, caminho O2'). A especificação foi fechada em 2026-11-06 (`docs/spec/tres-portas-spec-epic.md`). A construção está na fila `tres-portas-c1` (`.claude/queues/tres-portas-c1/queue.yaml`), que ainda não rodou. Até ela rodar, use o modo "hoje" de cada porta.

| Porta | Hoje | Depois da fila (critério que entrega) |
|---|---|---|
| Brief do `discovery` | você cita o caminho na primeira frase do pedido | o comando procura `docs/discovery/` sozinho e rotula cada proposta como `evidência` (CS-8, CS-9) |
| Spec do `planning-lead` | você cita o caminho na primeira frase do pedido | o comando procura `spec/` e `specs/` sozinho e rotula cada proposta como `proposta de agente` (CS-8, CS-9) |
| Decisões sem veredito | você abre o arquivo e edita a linha à mão | o `doctor` avisa, o fechamento conta, o comando abre a revisão e `cepa-plan verdict` grava (CS-1 a CS-7) |
| Card do `discovery` no Jira | aponta só o caminho do brief | aponta o caminho e o repositório onde o brief vive (CS-10) |

## Porta 1: o brief do `discovery`

**Quando usar.** Uma oportunidade passou pelo `discovery` e chegou a `Validated`. O brief existe e o card Epic foi criado no board de engenharia. A pergunta "vale a pena resolver isso?" já está respondida. Falta responder "o que exatamente vamos construir?".

**Como usar.**

1. Abra a entrevista no repositório onde o brief vive. O card do Jira diz qual é.
2. Hoje, cite o brief no pedido: `/common:spec "<a ideia> · leia docs/discovery/WEGO-123/handoff.md antes de perguntar"`. Depois da fila, basta a ideia: o comando encontra o brief pelo assunto.
3. O agente lê o brief e transforma o que ele já responde em proposta. Cada proposta chega como a opção recomendada da pergunta, com o rótulo `evidência` e o caminho do arquivo.
4. Responda mesmo assim. O brief foi validado com usuário, então a proposta costuma estar certa, mas é você quem decide o escopo.

**O que o brief responde bem.** "Who benefits?" vira o "para quem" do Epic. "Boundaries" vira o "Não entra". "Validation seeds" (o sinal que mostraria que funcionou) é a melhor fonte para a métrica de resultado.

**Quando não usar.** Se a dúvida ainda é se o problema existe, o lugar é `/discovery:capture` e o fluxo do `discovery`, não a entrevista.

## Porta 2: a spec do `planning-lead`

**Quando usar.** Um `planning-lead` já rodou sobre o assunto e deixou uma spec de uma página (Goal, Approach, Trade-offs, Proposed Stories). Você quer que isso vire uma especificação com critérios medidos, ou um Epic.

**Como usar.**

1. Hoje, cite a spec no pedido: `/common:spec "<a ideia> · leia specs/<slug>.md antes de perguntar"`. Depois da fila, o comando procura em `spec/` e `specs/` sozinho.
2. Cada proposta tirada dela chega com o rótulo `proposta de agente`. O rótulo é diferente do da porta 1 de propósito: o `planning-lead` não falou com usuário nenhum, ele imaginou. Trate como palpite de colega, não como evidência.
3. O que a spec decidiu sem você não vira pergunta respondida. Entra na seção `## Decided without asking` do documento novo, com a origem anotada, para você vetar.

**Cuidado.** A spec do `planning-lead` não tem `**Surface:**` nem `**Red test:**`. O `spec-readiness-gate` (o hook que bloqueia uma spec que se declara pronta sem passar no crivo) não a lê e o `cepa-plan from-spec` não a transforma em fila. Ela só serve como insumo da entrevista, nunca como substituta.

## Porta 3: as decisões sem veredito

**O que são.** Toda entrevista termina com uma seção `## Decided without asking`: o que o agente decidiu sozinho porque duas respostas diferentes não mudariam o código. Uma decisão está **sem veredito** enquanto a linha não termina com um destes marcadores:

- `· mantida em <data>`: você concorda;
- `· vetada em <data>: <razão>`: você discorda;
- `· refinada em <data>`: você trocou o texto da decisão.

**Onde você vê a pendência (depois da fila).**

- No `/common:doctor`: a área `decisoes` aparece como aviso ⚠, com um arquivo por linha e o comando que abre a revisão. Conta só specs e Epics fechados, porque um documento em `draft` ainda está em entrevista. Em 2026-11-06 seriam 5: 3 em `docs/spec/cepa-espiral-c1.md` + 2 em `docs/spec/planejador-de-lotes-paralelos.md` = 5.
- No fechamento de uma spec ou Epic: ao passar de `draft` para pronto, o hook mostra "N decisões sem veredito neste arquivo". Mostra o zero também, e mostra "sem seção Decided without asking" quando a seção não existe.
- Em qualquer momento: `cepa-plan decisions` lista tudo de `docs/spec/` e `docs/epics/`. `cepa-plan decisions <arquivo>` lista um arquivo só.

**Como dar o veredito (depois da fila).**

1. Reabra o documento: `/common:spec --continuar <slug>` para spec, `/common:epic <nome>` para Epic.
2. Antes de retomar qualquer outra coisa, o comando mostra as decisões sem veredito. Na spec são até quatro por rodada. No Epic é uma por turno, em prosa.
3. Responda mantida, vetada (com a razão) ou refinada (com o texto novo). O agente grava com `cepa-plan verdict <arquivo> <n> <veredito>`, que põe a data do dia e o formato exato.
4. Pode pular. A decisão pulada fica sem marcador, volta no próximo `doctor` e não trava a entrevista.

**Hoje, sem a fila.** Rode você mesmo `cepa-plan verdict <arquivo> <n> mantida`, `... vetada --reason "<razão>"` ou `... refinada --text "<texto novo>"`, com o `<n>` que o `cepa-plan decisions` mostra. Escrever o marcador à mão também vale: o `cepa-plan decisions` lê do mesmo jeito.

**O que o veto não faz.**

- Não desfaz código. Se uma fila já foi gerada do arquivo, o `cepa-plan verdict` avisa "isto já virou código na fila X" e diz quantos itens dela estão `done`. Desfazer é um item novo de fila, decidido por você.
- Não muda o `Status` do documento. Uma decisão vetada só vira pergunta em aberto se você mandar, no mesmo turno.
- Não passa pelo `/common:debrief`. O debrief continua sendo a revisão das decisões de runs autônomos. As decisões de entrevista se revisam na própria entrevista.

## Regras que valem nas três portas

- **Proposta não é resposta.** Nada vira `- [x]` na lista de perguntas sem uma fala sua que responda. Um arquivo lido gera proposta, nunca resposta.
- **De onde veio fica escrito.** O cabeçalho do documento ganha uma linha `**Fontes lidas:**` com os caminhos lidos. Os rótulos (`evidência`, `proposta de agente`) aparecem no turno da pergunta, nunca na linha do critério, que o hook lê.
- **Toda proposta é desafiada uma vez** antes de ser gravada ("quem vê isso e onde?", "o que quebra se faltar?"). Isso evita que a entrevista vire carimbo de um texto que ninguém questionou.

## Fluxo típico

1. O `discovery` valida uma oportunidade e o card Epic aparece no board de engenharia, com o caminho do brief e o repositório.
2. Você abre `/common:epic <nome>` naquele repositório. As propostas tiradas do brief chegam com o rótulo `evidência`, e você responde turno a turno.
3. No fechamento, o hook mostra quantas decisões o agente tomou sozinho.
4. Dias depois, o `doctor` ainda lista essas decisões. Você roda `/common:epic <nome>`, mantém ou veta cada uma, e só então segue para `/common:queue <nome>-c1 --from-epic docs/epics/<nome>.md --cycle 1`.

## De onde veio

- O desenho e as decisões D1 a D7: `docs/estrategia-tres-portas-para-spec-e-epic.md`.
- O painel de revisores que derrubou a primeira versão: `docs/reviews/2026-11-04-painel-tres-portas.md`.
- Os critérios e as respostas do dono: `docs/spec/tres-portas-spec-epic.md`.
