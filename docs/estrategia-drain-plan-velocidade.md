# Por que o `/common:drain-plan` demora, e o que fazer a respeito

Status: proposta de estratégia. Nada implementado.
Data: 2026-08-26. Base: `common/commands/drain-plan.md` (242 linhas), `common/bin/cepa-plan`
(1497 linhas), `build-hex/agents/proof-reviewer.md` (404 linhas).

## O que é cada coisa

- **Fila `single-track`**: o arquivo `.claude/programs/<nome>/plan.yaml` com `mode:
  single-track`. Guarda uma lista ordenada de itens de trabalho, cada um com um campo `why`
  dizendo por que está naquela posição. Quem escreve é o `/common:plan`.
- **`/common:drain-plan`**: executa essa fila em lote, na ordem dela, até `--max` itens.
- **Gate de aceite** (`completion-auditor`): agente que confere se cada critério de aceite tem
  um teste na superfície que o critério nomeia. Devolve COMPLETE ou INCOMPLETE.
- **Gate de prova** (`proof-reviewer`): agente que prova que o código novo é carregado por
  algum teste. O mecanismo é **perturbação**: quebrar o código de propósito e exigir que o
  teste que deveria guardá-lo fique vermelho.
- **Perturbação**: uma reversão de um trecho mudado (`git checkout <ref> -- <arquivo>`) feita
  numa worktree descartável, seguida de recompilação e reexecução do teste guardião.

## Onde o tempo vai

**F1 — um item da fila dispara ~21 chamadas de agente.**
O passo 3.b do comando manda o item para o flow da topologia. Em `build-hex`
(`build-hex/commands/plan-build-validate.md`), a composição é:

| Fase | Agentes |
|---|---|
| planning-lead + epic-author, product-manager, integration-analyst | 4 |
| engineering-lead + o laço por Task (dev → qa-engineer → refactor-advisor → code-reviewer) | 1 + 4×T |
| validation-lead + security-reviewer + completion-auditor | 3 |
| proof-reviewer | 1 |

Conta: 4 + 1 + 4T + 3 + 1 = **9 + 4T**, onde T é o número de Tasks em que o item foi
decomposto. Com T = 3, são 21 agentes por item; com o `--max 3` default, 63 no lote.
Ressalva: T = 3 é uma suposição de trabalho, não uma medição. O laço por Task ainda repete
quando o `code-reviewer` devolve REJECT (`build-hex/agents/engineering-lead.md:28`), então 21
é piso, não média.

**F2 — o relógio está nas compilações Maven, não nas chamadas de agente.**
Contagem por item:

| Origem | Builds | Fonte |
|---|---|---|
| `qa-engineer` exige `mvnw` com saída literal `BUILD SUCCESS`, por Task | T | `engineering-lead.md:36` |
| `validation-lead` roda `./mvnw verify` completo, obrigatório | 1 | `validation-lead.md:28` |
| `proof-reviewer` estabelece o verde inicial | 1 | `proof-reviewer.md:121` |
| `proof-reviewer` roda **um ciclo build+test por perturbação** | P | `proof-reviewer.md:107` |

Conta: T + 2 + P. Com T = 3 e P = 6 trechos perturbados, são **11 builds por item, 33 no lote
default**. E o teste externo é `@QuarkusTest`, que sobe a aplicação inteira a cada execução
(`proof-reviewer.md:91`).

**F3 — o `drain-plan` faz o trabalho de dois comandos do mundo Jira.**
Comparando o que cada lote cobre do ciclo:

| Comando | Constrói | Gate de aceite | Gate de prova | `--max` default |
|---|---|---|---|---|
| `/board-flow:drain` | sim | sim | **não** | 5 |
| `/board-flow:prove-drain` | não | não | sim | 5 |
| `/common:drain-plan` | sim | sim | sim | 3 |

`/board-flow:execute` termina em In Review (`board-flow/commands/execute.md:167`); a prova é um
comando separado, disparado depois. O `drain-plan` junta as duas metades no mesmo item. Um item
dele custa aproximadamente **um card de `drain` mais um card de `prove-drain`** — é essa soma,
e não uma ineficiência de implementação, que o `--max 3` reconhece
(`common/bin/cepa-plan:151`, `TETO_PADRAO = 3`).

**F4 — a fila não tem onde um item meio-feito descansar.**
Os estados válidos de um item são cinco: `pending`, `in_progress`, `done`, `blocked`, `dropped`
(`common/bin/cepa-plan:150`). Não existe equivalente da coluna In Review — nenhum estado que
signifique "construído e auditado, falta provar". É por isso que a prova roda colada na
construção: não há onde parar entre as duas sem mentir sobre o estado do item.

**F5 — o lote é serial por decisão registrada, não por limite técnico.**
"A ordem é o dado" (`drain-plan.md`, seção Instructions): não pular, não reordenar, porque
pular um item travado para alcançar o de baixo reordena a fila em silêncio. O comando inclusive
recusa um plano `parallel-waves` em vez de linearizá-lo. Paralelismo existe só **dentro** de um
item, entre Tasks com caminhos previstos disjuntos
(`plan-build-validate.md:96-99`).

## Riscos que qualquer caminho tem que respeitar

**R1 — a prova é o que separa `done` de "o agente disse que fez".**
Baratear a prova baixando o rigor devolve o harness ao estado que o gate existe para tirar. A
memória `done-confidence-ladder` registra a escada: código existe (L0) não é o mesmo que
carregado na superfície (L4). Qualquer caminho que corte perturbação precisa dizer **qual
degrau** está abrindo mão.

**F4 é armadilha, não só constatação.** Introduzir um estado novo na fila mexe no `cepa-plan`,
que é o único escritor legítimo do `plan.yaml` e o dono das recusas (reserva dupla, desfecho
sem evidência, fechar rota humana). Estado novo mal desenhado vira item que fica parado para
sempre entre duas metades.

**R2 — item pulado é fila reordenada em silêncio.**
Vale para qualquer caminho que introduza "faça os rápidos primeiro". O documento do comando já
trata isso como o estado que ele existe para eliminar.

## Caminhos considerados

**O1 — Status quo, com `--max` menor.**
Rodar `--max 1` e repetir. Ganho: zero trabalho, e o lote fica previsível.
Custo: não muda nada no custo por item; só troca um run longo por vários curtos, com o
overhead de reabrir contexto a cada vez.
Veredito: é o que dá para fazer hoje à noite, não é resposta à pergunta.

**O2 — Separar construir de provar, como o mundo Jira já faz.** *(candidato principal)*
Introduzir na fila o estado que falta (F4) — algo como `built`, significando construído e com
aceite COMPLETE, prova pendente — e um segundo comando que drena só os `built` pelo gate de
prova, sem parar no primeiro UNPROVEN (copiando a política do `/board-flow:prove-drain`).
Ganho: o lote de construção deixa de carregar 1+P builds por item; o `--max` do lote de
construção pode subir para 5, igualando o `drain`. E a prova, que hoje é a metade cara,
vira um run que você dispara quando quiser (almoço, noite).
Custo: um estado novo no `cepa-plan` e no schema, mais um comando novo. E cria a dívida que o
Jira também tem: uma coluna Review que enche.
Veredito: ataca a causa nomeada em F3 e F4, e é o único caminho que não mexe no rigor.

**O3 — Baratear a prova: menos subidas do Quarkus por item.**
Hoje é uma subida por perturbação (F2). Três sub-caminhos, do mais barato ao mais invasivo:
(a) agrupar perturbações independentes num único `mvnw` com vários `-Dtest=`;
(b) escopar perturbação por risco, provando os trechos de maior risco e declarando no artefato
quais ficaram de fora (o próprio agente já prevê isso para diffs grandes,
`proof-reviewer.md:107-108`);
(c) reusar a JVM entre perturbações.
Ganho: mexe direto no multiplicador P, que é o maior termo da conta de F2.
Custo: (b) baixa o degrau da escada de confiança e precisa de R1 respondido explicitamente;
(c) é trabalho de infra de build, não de harness, e pode não caber no `@QuarkusTest`.
Veredito: (a) é ganho quase de graça e independe dos outros caminhos. (b) é troca de rigor
disfarçada de otimização. (c) é o maior ganho e o maior trabalho.

**O4 — Promover a fila para ondas e paralelizar.**
O `/maestro:program-plan --from-plan NOME` já existe exatamente para converter a fila
`single-track` em ondas `parallel-waves`, e o `/maestro:run` executa cada slice numa worktree
própria.
Ganho: o único caminho que ataca F5. Itens com superfícies disjuntas rodam ao mesmo tempo.
Custo: exige o herdr rodando e o plugin instalado; e o pré-requisito de fato é que os itens
**tenham** superfícies disjuntas, o que numa fila escrita para ser sequencial costuma ser
falso. O piso de uso declarado do Maestro é ≥4 demandas.
Veredito: resolve outro problema (vazão de um programa grande), não a lentidão de uma fila
curta. Não compete com O2.

## Recomendação

**O2, com O3(a) junto.** O2 é o que reconhece o que F3 e F4 mostram: o `drain-plan` está lento
porque faz o trabalho de dois lotes sem ter o estado intermediário que permitiria separá-los.
O3(a) — agrupar perturbações numa execução Maven só — é ganho independente e não custa rigor,
então entra em qualquer cenário.

O que **não** recomendo sem uma decisão explícita sua: O3(b). Provar só os trechos de maior
risco é baixar o degrau da escada de confiança, e essa é decisão de dono, não otimização.

Sequência proposta:
1. Medir, antes de mexer: instrumentar um run de `drain-plan` e contar builds e tempo por fase.
   As contas de F1 e F2 são aritmética sobre a prosa dos agentes, não medição. Sem isso, não dá
   para dizer que O2 economizou.
2. O3(a): agrupar perturbações independentes num `mvnw` só.
3. O2: estado `built` no `cepa-plan` + comando de drenagem de prova.
4. Reavaliar O3(c) com o número do passo 1 na mão.

---

# Revisão pós-painel de advisors (7 lentes, área arquitetura, 2026-08-26)

O painel derrubou a recomendação original. As correções abaixo **substituem** a seção
"Recomendação". O texto acima fica como registro do raciocínio, não como proposta viva.

## Convergências (achado independente de 2+ lentes)

**C1 — O3(a) não é ganho de graça; é a única proposta que quebra o mecanismo da prova.
(contrarian, fundamentalista, outsider, executor, operador-sre, custo-de-manutencao — 6 de 7
lentes, isoladas.)**
O custo P é por **reversão**, não por teste. Então agrupar não tem meio-termo: ou você reverte
um trecho por vez e passa vários `-Dtest=`, e P não cai; ou reverte vários trechos e roda um
`mvnw` só, e perde a correspondência um-para-um entre perturbação e vermelho — que é o
mecanismo inteiro do veredito. Pior: uma reversão pode quebrar a compilação (o comando usa
`-am`, recompilando módulos upstream do fonte), deixando tudo vermelho e produzindo PROVEN
falso para trechos que teste nenhum carrega. O documento propunha "perturbações independentes"
sem nenhum mecanismo para estabelecer independência — que é justamente o dado caro. **O3(a)
sai da recomendação.**

**C2 — O modelo de custo inteiro descreve um repo que talvez não seja o repo da dor.
(contrarian; verificado por mim no disco.)**
F1 e F2 estão ancorados em `build-hex`, `mvnw` e `@QuarkusTest`. O repo onde moram as 5 filas
reais (`.claude/programs/{ariad-leva2,cepa,lotes-2026-08-23,lotes-sweep-verify,maestro,
melhorias-2026-07}`) **não tem** `mvnw`, **não tem** `pom.xml`, **não tem** `package.json` e
**não tem** `.claude/topology` — que é exatamente o arquivo que o passo 3.b do comando lê para
despachar. Tem `.claude/no-build`. Se a lentidão foi sentida drenando uma dessas filas, F2 é
irrelevante e O2, que existe para tirar builds do lote, ataca um custo que não está lá. O
documento nunca nomeia em que repo o run lento aconteceu. **Esta é a pergunta que precede todas
as outras.**

**C3 — O2 redistribui custo e foi vendido como redução. (contrarian, outsider, operador-sre.)**
Os `1+P` builds não somem: migram para o segundo lote, que ainda paga recriar worktree e
restabelecer o verde inicial sem contexto quente. O que O2 entrega é latência percebida ("o
`--max` pode subir para 5"), não vazão. E `--max 5` na construção são 5 dívidas de prova, não 5
itens prontos.

**C4 — A recomendação precede a medição que o próprio documento exige, e não há limiar.
(contrarian, outsider, operador-sre, custo-de-manutencao.)**
Se a medição do passo 1 pode mudar a conclusão, a conclusão não podia estar escrita. Não existe
critério do tipo "se os builds forem menos de X% do relógio, O2 sai da fila". Nem baseline
("levou N minutos") nem meta ("aceitável é M"). F2 conclui sobre **tempo** a partir de uma
contagem de **eventos** — 21 chamadas de agente com contexto grande podem dominar 11 builds, e
nada no documento mede nenhum dos dois em segundos.

**C5 — O custo de O2 foi listado pela metade. (executor, custo-de-manutencao, expansionista.)**
"Um estado novo no `cepa-plan` e no schema, mais um comando novo" ignora os outros leitores do
`plan.yaml`: `common/bin/cepa-dor`, `maestro/bin/maestro-programs`,
`maestro/bin/maestro-fork-settings`, mais o `common/plan-schema.yaml` (v1 ainda em circulação).
Verifiquei o pior deles: `maestro-programs:111` monta a lista de pendentes com
`status in (None, "pending", "in_progress")` — um item `built` **desaparece da contagem de
pendentes sem erro nenhum**. É o modo de falha silenciosa que este repo já catalogou três vezes
(memória `gate-por-nome-de-ferramenta-falha-aberto`).

**C6 — Prova adiada prova contra uma base que andou. (custo-de-manutencao, executor;
verificado.)**
A perturbação reverte contra um commit de base. O mundo Jira tem esse commit porque o
`/board-flow:execute` grava `.claude/cards/<KEY>.yaml` **antes** de escrever código
(`execute.md:90`). A fila não tem: as chaves do item são `id`, `title`, `why`, `status`,
`blocked_by`, `human_pending` (`cepa-plan:334`) — não há `base_commit`. Entre construir o item
e provar de noite, os itens seguintes moveram o HEAD. **O2 exige um invariante que a fila hoje
não guarda**, e isso não estava no custo.

## Discordâncias nomeadas

**D1 — O que falta na fila: um estado, um campo que já existe, ou um registro de gates?**
O documento diz "falta o estado `built`". O **fundamentalista** diz que o campo já existe:
`human_pending` é o lugar de "falta uma coisa neste item". O **expansionista** diz que ambos
erram a granularidade — o que falta é registrar **quais gates o item já passou**, não um estado
a mais na máquina.
*O que decide:* a semântica escrita do campo. `cepa-plan:326-327` diz que `human_pending` **só
o humano fecha, agente nenhum troca o texto por null por conta própria**. Prova é mecânica, e
o `proof-reviewer` é agente. Pôr prova ali cria dívida que a máquina não pode quitar.
**Resolvo contra o fundamentalista e a favor do expansionista:** se algo entrar, é um registro
de gates cumpridos, não um sexto estado nem uma carona no `human_pending`.

**D2 — O lote de prova é paralelizável ou não?**
O **expansionista** diz que sim, e que essa é a oportunidade mais barata do sistema: a
perturbação já roda em worktree descartável isolada, logo provar N itens em paralelo não exige
o pré-requisito de superfícies disjuntas que fez O4 ser descartado. O **operador-sre** e o
**contrarian** dizem que um lote que não para no primeiro UNPROVEN não tem disjuntor: uma falha
ambiental (Docker fora, ferramenta ausente) reprova todos os itens em série sem ninguém notar.
*O que decide:* os dois estão certos sobre coisas diferentes — isolamento de worktree é real,
disjuntor ausente também. **Recomendo:** se O2 andar, o lote de prova nasce com teto de
UNPROVEN consecutivos (para depois de 2 seguidos), que é o disjuntor que o `prove-drain` também
não tem.

**D3 — Adiar a prova viola o mesmo princípio que o documento usa para proibir pular itens?**
O **contrarian** diz que sim: o `drain-plan` proíbe pular item porque a ordem é o dado, mas
adiar a prova de todos os itens constrói o item 2 sobre código não provado — e um UNPROVEN no
item 1 invalida a base de 2..N. O documento tratava isso como neutro.
*O que decide:* se o item N+1 depende de fato do código do item N. Numa fila cuja tese é a
ordem, o default é que dependa. **Concordo com o contrarian:** O2 não pode ser adotado sem
responder o que acontece com os itens 2..N quando o 1 sai UNPROVEN.

**D4 — Qual dos dois rebaixa o rigor em silêncio, O2 ou O3(b)?**
O documento mandava O3(b) (provar só os trechos de maior risco) para decisão do dono e liberava
O2 sozinho. O **fundamentalista** e o **contrarian** invertem: O3(b) rebaixa de forma
**explícita, escopada e registrada** — o `proof-reviewer` já loga o que ficou de fora. O2
rebaixa de forma **silenciosa e ilimitada**: a fila de `built` que enche é um monte de itens
parados no degrau baixo da escada `done-confidence-ladder`, sem dono, prazo nem alarme.
*O que decide:* o critério do próprio R1 — "qualquer caminho que corte prova precisa dizer de
qual degrau abre mão". **Aceito a inversão:** a régua foi aplicada assimetricamente. O2 também
precisa passar por R1, e hoje não passa.

## O que fica de pé

Nenhuma das quatro opções sobrevive intacta. O que o painel não derrubou:

- **F3 e F4 seguem válidos como diagnóstico**: o `drain-plan` faz o trabalho de dois lotes e a
  fila não tem estado intermediário. O que caiu foi a conclusão de que criar esse estado é a
  jogada.
- **A pergunta certa mudou.** Não é "como acelerar o `drain-plan`", é **"em qual repo o run foi
  lento, e o relógio foi para agentes ou para builds"**. Enquanto isso não estiver medido, C2
  torna toda a aritmética de F1/F2 uma hipótese sobre um cenário possivelmente errado.

## Sequência revisada

1. **Nomear o run lento** — qual repo, qual fila, quantos itens, quanto tempo. Sem isso, nada.
2. **Medir onde o relógio vai**, em segundos, separando tempo de agente de tempo de build, e
   gravando no ledger de telemetria (`/common:metrics`) em vez de num andaime descartável
   — sugestão do expansionista que sobreviveu.
3. **Declarar o limiar antes de medir**: qual repartição do relógio mandaria O2 para a fila, e
   qual a mandaria para o lixo.
4. Só então reabrir o espaço de opções. O3(a) está morto (C1). O2 precisa antes responder C6
   (base congelada), C5 (leitores do schema), D3 (itens 2..N) e D4 (passar por R1).

---

# Medição do run real (2026-08-26, `session/drain-plan-0840`)

O run lento foi nomeado pelo dono e medido. **Ele derruba F2, que era o achado central do
documento, e nenhuma das quatro opções ataca a causa real.**

Fonte: o transcript da sessão e os 41 transcripts de subagente em
`~/.claude/projects/-Users-alegomes-cepa-worktrees-wego-acesso-backend-drain-plan-0840/`.
Repo: `wego-acesso-backend` (tem `mvnw` e `pom.xml`, então C2 se dissolve — o modelo build-hex
era o certo). Janela: 08:40 → 11:41 local = **183 minutos para 2 cards** (WEGO-2111, WEGO-2112).

## Para onde foram os 183 minutos

Método: para cada chamada de ferramenta, a duração é o intervalo entre a mensagem do agente que
a disparou e o registro do resultado. Intervalos sobrepostos (agentes em paralelo) foram unidos
antes de somar, para não contar o mesmo minuto duas vezes.

| Onde | Minutos | % do relógio | Chamadas |
|---|---|---|---|
| **Espera ativa** (`until … sleep`, laços de queima) | **84** | **46%** | 35 |
| Geração de texto dos agentes (não é ferramenta) | ~74 | 40% | — |
| Maven (`mvnw`) | 23,5 | 13% | 61 |
| Bash normal (ler, procurar, git) | 11 | 6% | 338 |

**F2 estava errado.** Eu tinha escrito que "o relógio está nas compilações Maven": elas são
13%. A mediana de uma execução Maven foi 15 segundos; só 6 das 61 passaram de 1 minuto.
O contrarian acertou o método: contar eventos não diz onde o tempo está.

**F1 estava certo por acidente.** Estimei ~21 agentes por item; foram 41 agentes para 2 itens.
A contagem de builds errei por 3× (estimei 11 por item, foram 30) — e não importou, porque
builds não são o gargalo.

## A causa real: o lead fica esperando por arquivo

Os 84 minutos de espera estão quase todos num agente só: o `build-hex:engineering-lead` (78
min; o `validation-lead` responde pelos outros 6). O padrão, verbatim do transcript:

```
until grep -q "CredenciaisDoFuncionarioE2ETest" .claude/last-build.json; do sleep 20; done   601s
until ls bootstrap/src/test/java/.../ | grep -q "Credenciais"; do sleep 10; done             543s
until git status --short | grep -q "CofrePortFalhaGenuina"; do sleep 10; done                422s
until [ -f api-rest/src/test/java/.../CredencialHabilitadaResponse.java ]; do sleep 10; done  421s
until [ -f /dev/null ]; do sleep 5; done; echo aguardando                                     120s
for i in $(seq 1 6000); do git log --all --stat >/dev/null 2>&1; done; date                   590s
for i in $(seq 1 6000); do git log --all --stat >/dev/null 2>&1; done; date                   590s
```

Duas coisas acontecem aí, e as duas são defeito:

**M1 — o lead espera por arquivo em vez de esperar pelo retorno da delegação.** Ele lança um
worker e depois fica sondando o disco até o arquivo do worker aparecer ("Vou lançar o dev e, em
paralelo, a redação prescritiva do contrato E2E" / "Aguardando o levantamento"). O resultado da
delegação já chegaria pronto; a sondagem só adiciona latência, em blocos de 5 a 10 minutos.

**M2 — `sleep` em primeiro plano é bloqueado pelo harness, e o agente contorna com laço de
queima.** `for i in $(seq 1 6000); do git log --all --stat; done` não faz nada útil: é um
`sleep` improvisado que ainda por cima consome CPU. Rodou duas vezes, 590 segundos cada — quase
20 minutos só nisso. E `until [ -f /dev/null ]` é uma espera por uma condição que já é
verdadeira, ou seja, o agente nem sabia mais o que estava esperando.

## O que isso faz com o resto do documento

- **O1 (`--max` menor)**: continua sendo só paliativo, e agora nem isso — o custo por item é
  dominado por espera, que não escala com o `--max`.
- **O2 (separar construir de provar)**: ataca 13% do relógio. Mesmo se funcionasse de graça (e
  o painel mostrou que não, C3/C5/C6), o teto de ganho é pequeno.
- **O3 (baratear a prova)**: mesmo teto, e O3(a) já estava morto por C1.
- **O4 (paralelizar em ondas)**: irrelevante aqui — o problema não é falta de paralelismo, é um
  agente que **simula** paralelismo esperando no disco.

**A opção que não estava na mesa, e que agora é a única com tamanho:** proibir espera ativa nos
leads. Se os 84 minutos virassem zero, o mesmo run teria levado ~99 minutos em vez de 183 —
**46% mais rápido sem tocar em gate, rigor ou schema**. Isso é maior do que qualquer coisa que
O1 a O4 poderiam entregar somadas, e não custa nenhum degrau da escada de confiança.

## Sequência revisada (2ª vez)

1. **Confirmar que M1 é sistemático e não um azar deste run** — medir a mesma proporção de
   espera ativa em outro run de `drain-plan` ou `drain` já gravado no disco.
2. **Barrar espera ativa por hook**, no mesmo lugar onde o `bash-path-lock` já inspeciona
   comando de Bash: recusar `until`/`while` com `sleep`, e recusar laço de queima. A recusa tem
   que dizer o que fazer no lugar (aguardar o retorno da delegação), senão o agente inventa a
   terceira variante — que é exatamente o que a memória
   `gate-por-nome-de-ferramenta-falha-aberto` descreve.
3. **Só depois** reabrir O2/O3, com os 13% de Maven na mão como teto realista.

---

# Confirmação: a espera é sistemática (2026-08-26)

O passo 1 da sequência revisada pedia confirmar que M1 não era azar de um run.
Medi mais cinco sessões já gravadas em `~/.claude/projects/`:

| Sessão | Relógio | Espera ativa | % | Onde |
|---|---|---|---|---|
| `drain-plan-0840` | 328 min | 155 min | 47% | engineering-lead 149 |
| `todo-1413` | 1098 min | 241 min | 22% | engineering-lead 232 |
| `todo-21081818` | 924 min | 194 min | 21% | engineering-lead 190 |
| `todo-22081827` | 913 min | 176 min | 19% | engineering-lead 161 |
| `exec-17081128` | 636 min | 146 min | 23% | engineering-lead 114 |
| `credentials-crud` | 2393 min | 33 min | 1% | validation-lead 25 |
| `prove-1940` (sem lead) | 116 min | **0** | 0% | — |
| `drain-1107-0920` (sem lead) | — | **0** | 0% | — |

Ressalva de método: o relógio vai do primeiro ao último evento da sessão, então
sessão interativa inclui o tempo parada esperando o dono, e o percentual sai
diluído. **Os minutos absolutos são o número confiável.** Somados, os cinco runs
com lead perderam **912 minutos — 15 horas — em comando que não fazia nada.**

Os dois runs sem lead têm espera **zero**. Isso localiza o defeito com precisão:
não é a topologia nem o gate, é o lead. E o `credentials-crud`, com o lead
presente mas em 0 minutos de espera, mostra que o comportamento não é obrigatório
— é um hábito que aparece quando o lead delega em paralelo.

## O que foi construído a partir disso (commit `9ce9760`)

- **`common/hooks/no-busy-wait.py`** — recusa, no Bash, laço com `sleep`,
  `while true`, laço de queima (`for i in $(seq 1 N)` com N ≥ 200) e `sleep`
  de 30s ou mais. A recusa diz o que fazer no lugar, na ordem: aguardar o retorno
  da delegação, usar `run_in_background`, usar a ferramenta `Monitor`, ou marcar
  `# espera-ok` se for mesmo estado externo sem notificação. Barra o **efeito**
  (bloquear a sessão sem trabalhar), não uma lista de comandos — a lição da
  memória `gate-por-nome-de-ferramenta-falha-aberto`.
- **`tests/test_no_busy_wait.py`** — 8 casos de bloqueio copiados verbatim dos
  transcripts e 9 de liberação (build de verdade, texto citado, `sleep` curto,
  escape hatch).
- **`common/bin/cepa-clock`** — reparte o relógio de uma sessão lendo o
  transcript dela e o de cada subagente, unindo intervalos sobrepostos para não
  contar o mesmo minuto duas vezes. Com `--emit`, grava no ledger e a repartição
  passa a aparecer no `/common:metrics`.

Validação contra os transcripts reais: o detector bloquearia **161 comandos, 632
minutos de relógio**, e liberaria **3.436 comandos, 348 minutos** — e os
liberados mais lentos são todos `mvnw verify` de verdade, entre 3 e 5 minutos.
Nenhum build foi confundido com espera.

**Nada disso está no ar até o `bin/install.sh --clean` e o restart do Claude
Code.** Sessão em execução segura os hooks antigos em memória.
