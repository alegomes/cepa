# Backlog — ideias e pendências da Cepa

Itens ainda **não implementados**. Cada um descreve o problema, o esboço de solução
e onde provavelmente mora. Sem ordem de prioridade fixa.

---

## Política default-yes — matar as micro-interações nas pontas da sessão

**Status:** pendente · **Lar provável:** `common` (skill `zero-micromanagement` + varredura
dos comandos) · **Origem:** reclamação forte do usuário (2026-08-18, por voz): toda rotina
(triage, drain, prove-drain, autonomous, doctor) exige ciclos de confirmação ANTES
(preparação em cascata, ~15–20% do contexto) e DEPOIS (vaivém até "ter certeza que
acabou") da operação principal — e ele quase sempre aceita a recomendação, então a
pergunta não muda o resultado, só custa turno e foco.

### Problema

Os comandos codificam confirmação como virtude ("Always confirm before starting",
"execute apenas as que o usuário confirmar", encaminhamentos para o próximo comando em
vez de executá-lo). O efeito agregado é uma jornada fatiada em paradas: o usuário perde
o fio do propósito da sessão e o contexto se esvai em preparação e fechamento.

### Esboço de solução

Uma **política transversal de decisão**, aplicada em três camadas:

1. **Regra:** ação **reversível ou registrável** + recomendação default clara →
   **executar e registrar** (decisão nomeada no relatório final, com o porquê).
   Exemplo canônico do usuário: "achou uma falha → cria o card, não pergunta".
   Perguntar **só** para irreversível/destrutivo (Won't Do, apagar branch com commits
   únicos, force-push, publicação externa), custo real, ou bifurcação genuína de
   preferência. Perguntas inevitáveis vão em **lote nas pontas** (largada ou relatório
   final), nunca no meio.
2. **Skill:** fortalecer `common:zero-micromanagement` com essa regra explícita
   (hoje ela existe mas os comandos a contradizem).
3. **Varredura:** revisar cada comando de rotina (doctor passo 4, drain/prove-drain
   "confirm with user", triage "nothing is written until you confirm", decide, wrap-up)
   e trocar confirmação-por-item por: default aplicado + registro + um único ponto de
   confirmação quando sobrar algo irreversível. O `doctor` ganha `--fix` (aplica todas
   as correções mecânicas em lote e re-roda até estabilizar).

4. **Preparação fora da sessão:** job agendado (launchd, reaproveitando a infra do
   Path A) roda o `cepa-doctor` de manhã em modo auto-fix mecânico e grava um arquivo
   de status; o hook de SessionStart injeta uma linha ("harness verde às 07:00" ou
   "N pendências que só você decide") em vez de mandar o usuário rodar o doctor e
   seguir recomendações em cascata dentro da sessão.
5. **Sessão com propósito declarado:** `/common:session <rotina>` (ou flag `--oneshot`
   nas rotinas) encadeia a jornada inteira — checa o preflight, faz TODAS as perguntas
   na largada (escopo, máximos, o que fazer com NEEDS-HUMAN, já embutindo as perguntas
   que hoje ficam para o `/board-flow:decide` depois), executa sem parar, entrega UM
   relatório final e oferece o wrap-up como último passo.
6. **Disciplina de fio da sessão** (falhas observadas na conversa de origem): proposta
   em aberto reaparece nos relatórios seguintes até ser resolvida (o session-log hook /
   `/common:recap` já rastreiam pedidos — estender para rastrear propostas do agente);
   e aviso lateral (worktree solto, handoff vencido) vai para um estacionamento exibido
   só no wrap-up, nunca vira pergunta no meio de outra discussão.

**Rede de segurança** (o que torna o default-yes seguro em vez de temerário): toda
decisão auto-aplicada fica nomeada no relatório; o handoff e o `/common:debrief`
(revisão keep/overrule a posteriori) são o canal de correção; `/common:metrics` ganha
duas métricas para provar o efeito — "turnos até o primeiro comando de rotina" e
"turnos entre o fim da rotina e o wrap-up".

---

## Advisors — painel de perspectivas por área de decisão

**Status:** pendente · **Lar provável:** `common` (transversal a todas as topologias)
· **Origem:** revisão do design da Variante 3 do `wego-acesso` (2026-06-28), feita à
mão spawnando 5 revisores com lentes distintas. Funcionou bem demais para ficar manual.

### Problema

Decisões de design/arquitetura são revisadas hoje por um único olhar (o do agente que
escreve, ou um `code-review` genérico). Um olhar só tem ponto cego. Quando o usuário
pediu "revise por 5 perspectivas diferentes" e cada lente foi rodada como um agente
independente **sem se contaminar**, o resultado foi nitidamente superior: cada uma
achou o que as outras não viam, e as **discordâncias entre elas** (ex.: "o enforcement
é teatro" vs. "o núcleo é sólido") foram o achado mais valioso.

Isso deveria ser um recurso de primeira classe da Cepa, não um improviso.

### Esboço de solução

Um **painel de advisors**: dado um artefato de decisão (doc de design, ADR, plano,
PR), spawnar N revisores em **paralelo e isolados** (sem ver a saída uns dos outros —
isolamento é o que evita convergência prematura), cada um com uma **lente fixa**, e
depois **sintetizar nomeando as discordâncias** (não mediar nem escolher em silêncio —
casa com o skill `name-the-disagreement` já existente).

Lentes-semente validadas na prática (cada uma um perfil/system-prompt):

| Lente | Foco |
|---|---|
| **contrarian** | o pessimista; onde vai falhar, premissas frágeis, furos |
| **fundamentalista** | fidelidade aos princípios/doutrina do projeto |
| **expansionista** | o upside; o que a decisão destrava além do escopo |
| **outsider** | sem contexto algum; olhar isento — o que o artefato falha em comunicar sozinho |
| **executor** | pragmático; o que dá pra fazer na segunda, ordem, bloqueios |

### O diferencial-chave: lentes **por área de decisão**

As 5 acima são um default genérico. O recurso fica forte se o painel **adapta as
lentes ao tipo de decisão**:

- decisão de **segurança** → +threat-modeler, +red-team, +compliance
- decisão de **API/contrato** → +consumidor externo, +versionamento/breaking-change
- decisão de **persistência/dados** → +DBA (volume/índices), +LGPD/retenção
- decisão de **UX** → +acessibilidade, +primeiro-uso
- decisão de **arquitetura** → +operador/SRE, +custo de manutenção

Ou seja: um **registry de lentes** + uma regra de seleção que monta o painel certo a
partir da área declarada da decisão.

### Como difere do que já existe

- **`common:debrief`** revisa decisões **passadas** de um run autônomo (keep/overrule)
  — retrospectivo e binário. Advisors é **prospectivo** e multi-lente, sobre um
  artefato antes de fechá-lo.
- **`code-review` / `review-gate`** caçam bugs/qualidade no diff. Advisors opera em
  **altitude de decisão** (design/ADR/plano), não em linha de código.
- **`proof-gate`** prova que o código faz o que diz. Advisors questiona se a **decisão**
  está certa, antes de virar código.

### Esboço de entrega

1. Skill/command `common:advisors <artefato> [--area=...] [--lentes=a,b,c]`.
2. Registry de lentes (perfis) em `common/` (formato análogo aos `expertise/*.yaml`).
3. Fan-out paralelo isolado (um agente por lente) → síntese que **nomeia as
   discordâncias** e fecha com propostas concretas consolidadas.
4. Default = as 5 lentes; `--area` injeta lentes especialistas do registry.

### Pendências de design (decidir antes de implementar)

- Como o usuário declara a "área" da decisão? (flag explícita vs. inferência do artefato)
- Quantas lentes por padrão sem virar ruído? (5 pareceu o teto útil)
- A síntese é um agente a mais, ou o orchestrator? (provável: orchestrator, para manter
  `name-the-disagreement` no nível certo)
- Saída: relatório? edição direta do artefato? proposta consolidada para aprovação?
  (na sessão de origem o fluxo foi: lentes → síntese → propostas concretas → aplicar)

---

## Topologia de marketing / produção de conteúdo

**Status:** pendente · **Lar provável:** nova topologia `marketing` (par de `docs`)
· **Origem:** run autônomo `2026-06-30-sales-enablement-kit` (kit de sales-enablement
do WeGo). A tarefa era escrita de prosa comercial, e nenhuma topologia instalada
servia: `autonomous-start` aborta sem `.claude/topology`, e os flows existentes
(`build-hex`, `build-team`, `discovery`) são para build de código. Rodou como
orquestrador direto, improvisando o fan-out de redatores.

### Problema

Produção de conteúdo (sales-enablement, marketing, copy, propostas) é um tipo de
trabalho recorrente e estruturável, mas hoje cai no vão: ou força um flow de código
que não encaixa, ou vira orquestração ad-hoc sem disciplina (sem grounding garantido,
sem gate de revisão, sem checagem de regras de marca/estilo). O run de referência teve
de montar à mão um brief de fontes compartilhado + 6 redatores paralelos + um sweep de
QA de regras duras (sem travessão, terminologia, anonimização, honestidade de
prontidão). Isso deveria ser uma topologia de primeira classe.

### Esboço de solução

Uma topologia `marketing` análoga à `docs`, com um loop content-lead → redatores →
crítico:

- **content-strategist / planning** — destila o brief: público, oferta, fontes de fato
  (números canônicos), regras de marca/estilo. Produz um `BRIEF.md` que ancora todos os
  redatores (o run de referência provou que grounding compartilhado é o que mantém os
  números consistentes entre agentes paralelos).
- **copywriter (worker, paralelizável)** — escreve cada artefato a partir do brief;
  write-lock por arquivo/seção.
- **brand-style-critic (gate)** — varre regras duras (proibições de estilo, terminologia
  reservada, anonimização, claims honestos vs. roadmap) e devolve PASS/REVISE com
  achados localizados. É o equivalente de marketing ao `design-critic` / `code-reviewer`.
- **fact-checker (gate)** — confere que todo número/claim traça a uma fonte declarada no
  brief; sem invenção (o run de referência impôs "não inventar número fora do brief").

### Como difere do que já existe

- **`docs`** documenta um sistema existente (extrai HOW do código, WHY de ADRs); marketing
  parte de uma oferta e de fontes de fato para produzir prosa persuasiva. Estrutura de loop
  parecida, propósito e gates diferentes.
- **`design`** desenha UI; marketing produz texto/conteúdo comercial.

### Pendências de design (decidir antes de implementar)

- O gate de regras de marca/estilo é configurável por projeto? (um `brand-rules.yaml`
  análogo ao brief deste run: proibições de estilo + termos reservados + claims honestos).
- Integra com `board-flow` (cards de conteúdo) como as outras topologias?
- Fonte de fato: como declarar e versionar o `BRIEF.md` de números canônicos para
  fan-out paralelo de redatores sem drift.

---

## Maestro — orquestração multi-harness (frota de sessões Claude Code)

**Status:** EM CONSTRUÇÃO — passos 1-3 FEITOS 2026-07-15 (spike VIÁVEL +
program-plan/intake + núcleos determinísticos do run testados + comandos
run/resume autorados); FALTA só o passo 4 (1ª onda real ponta a ponta com
herdr, após reinstall) · design rev2.1 · **Lar:**
plugin novo `maestro/` (decisão D6) · **Origem:** estratégia multi-sessões da
auditoria de sessões de 07/2026.

> **Design completo em `.claude/programs/maestro/design.md`** (rev2, revisado por
> painel de 7 advisors — síntese em `.claude/programs/maestro/advisors-sintese.md`).
> As "pendências de design" abaixo foram TODAS resolvidas lá (7 decisões de dono +
> 15 propostas do painel aplicadas). Ordem de construção: (1) spike do porteiro MCP
> com 1 filha fake, (2) program-plan + intake gate, (3) /maestro:run. O texto abaixo
> permanece como registro histórico do spike.

### Problema

Planejar um universo de demandas em ondas de sessões concorrentes hoje é trabalho
artesanal, e o despacho é manual (abrir N terminais, colar N comandos, integrar N
resultados). Queremos: plano discutido e aprovado → **uma ação** → N sessões criadas
e geridas por um agente central que media decisões e reporta o resultado final.

### Spike (2026-07-11) — socket do herdr como plano de controle: VIÁVEL

Testado contra herdr 0.7.3 rodando localmente (socket `~/.config/herdr/herdr.sock`,
CLI = wrappers JSON do socket):

- `herdr agent start <nome> --cwd --workspace --env -- claude -p ...` spawna uma
  sessão headless num pane visível. ✓
- `herdr wait output <pane> --match <marcador> --timeout` é a primitiva de
  sincronização do maestro — bloqueia até a filha imprimir o marcador. ✓
- `herdr worktree create --branch --base` cria worktree via socket em
  `~/.herdr/worktrees/<repo>/` (fora do repo/Insync, mesmo princípio do launcher `cepa`),
  com workspace próprio; `worktree remove` limpa. ✓
  **Ressalva (2026-08-24):** este ✓ foi medido em chamada isolada. Em uso real o
  sucesso reportado NÃO implica worktree criada — ver a segunda pegadinha abaixo.
- `agent send` / `pane send-text` injetam input em sessões interativas. ✓ (não testado
  a fundo)
- **Pegadinha real:** o pane fecha quando o processo termina e o output some — filhas
  precisam de wrapper (`sh -c 'claude -p ... | tee resultado.txt; echo MAESTRO-EXIT:$?;
  sleep N'`) que persista o resultado em arquivo e segure o pane.
- **Pegadinha real 2 (medida na onda WEGO-paralelo, 2026-08-24, herdr 0.7.3):** em
  4 de 5 chamadas, `herdr worktree create --json` devolveu JSON de sucesso COMPLETO
  (`path`, `branch`, `workspace_id`, `"is_prunable": false`) e o git não registrou
  worktree nenhuma; os diretórios também não existiam. `herdr worktree list` seguia
  mostrando as fantasmas, porque o herdr mantém registro próprio. Gatilho NÃO
  reproduzido (base main, base já em checkout, 4 chamadas back-to-back: todas
  funcionaram) e fora do nosso alcance — pode sumir numa versão futura do herdr. O
  conserto daqui é de contrato, não de causa: o passo 6a do `/maestro:run` confere
  o `path` devolvido contra `git worktree list` no clone principal antes do seed,
  re-tenta uma vez e marca a slice como FAIL sem forkar as demais em silêncio
  (guard mecânico em `tests/test_worktree_create_verify.py`). Mesmo princípio do
  marcador `MAESTRO-EXIT`: sincronize pelo efeito verificável (arquivo, git), não
  pelo que a ferramenta diz de si.
- **Gap:** `agent_status` fica `unknown` para filhas headless; o status rico
  (working/blocked/idle) vem do hook `herdr integration install claude`, que cobre
  sessões interativas. Para headless, sincronizar por wait-output + arquivos — ou o
  wrapper reportar via `pane report-agent`.

### Desenho aprovado em discussão

1. `/program-plan` (conversacional): parseia BACKLOG.md (fonte nativa — NUNCA acoplar
   a Jira; board-flow é adapter opcional), analisa superfície de arquivos /
   dependências / gates humanos por demanda, propõe ondas com fork points e teto de
   2–3 slices concorrentes (o limite é a atenção do humano). Estado em
   `.claude/programs/<nome>/plan.yaml` (plano é hipótese — re-validado por sessão).
2. Maestro (daemon fino, Agent SDK ou script): a ação única. Por slice da onda:
   worktree via socket herdr → spawn `claude -p` (autonomous-mode + demanda) →
   sincroniza por wait-output → merge train ao fim da onda → onda seguinte forka
   pós-merge → relatório final + debrief agregado.
3. Mediação de decisões: filhas headless com `--permission-prompt-tool` apontando
   para um MCP servido pelo maestro — decisões táticas ele resolve com base no plano
   e loga para debrief; estratégicas escalam ao humano.
4. Telemetria: eventos `program_start`/`slice_done`/`program_done` no ledger
   (`_telemetry.py` CLI) para o /common:metrics medir throughput e acerto de predição.

### Pendências de design

- Política de escalonamento (o que o maestro decide sozinho) — reusar a taxonomia de
  altitude do debrief.
- Filhas interativas (steering humano via pane) vs headless (mediação via MCP) — o
  spike sugere headless-em-pane como default: output visível, decisão centralizada.
- Piso de uso: programa só vale para ≥4 demandas / multi-semana; abaixo disso,
  apontar para drain ou sessão única.
- v0 sem daemon: validar plan.yaml + ondas usando subagentes worktree-isolados da
  própria sessão, antes de construir o maestro.

---

## "Verde" sem teste nenhum: gate de aceite precisa exigir `Tests run:` > 0

**Status:** pendente · **Lar:** `common/hooks/capture-build-result.py` (classificação do
build) + `build-hex/agents/proof-reviewer` e `common/agents/completion-auditor` (o que
eles aceitam como prova) · **Origem:** merge `00e0dda` no wego-acesso-backend
(2026-08-24), medido na árvore mesclada.

### Problema

O wego passou a rodar com `surefire.failIfNoSpecifiedTests=false` no `pom.xml` — a
correção certa para um sintoma real (o filtro `-Dtest=<Nome>` com `-pl/-am` abortava no
primeiro módulo que não tem aquele teste). O efeito colateral, verificado:

    $ ./mvnw -pl domain -am test -Dtest=NaoExisteEmLugarNenhumTest
    [INFO] BUILD SUCCESS          ← exit 0, e ZERO linhas "Tests run:"

Ou seja: **errar o nome do teste agora produz verde**. E o harness inteiro trata verde
como prova — o `capture-build-result` grava `last-build.json` verde, o `gate-advance`
libera o commit, o comando de aceite de um card passa, e o card vira feito sem que
nenhuma linha de teste tenha rodado.

Não é hipótese: é exatamente o padrão do WEGO-2107 nesta mesma onda, onde o comando de
aceite apontava para um arquivo já correto e passaria vazio — só que ali a slice
percebeu e recusou. Uma máquina não percebe.

O risco não é exclusivo do Maven: `pytest -k NomeErrado`, `go test -run NomeErrado` e
`npm test -- -t NomeErrado` também saem com 0 e nenhum teste executado.

### Esboço de solução

1. `capture-build-result` deixa de classificar como verde um build cujo comando tem
   filtro de teste (`-Dtest=`, `-k`, `-run`, `-t`) e cuja saída não traz contagem de
   testes maior que zero. Grava um terceiro estado — verde-vazio — em vez de verde.
2. O `proof-reviewer` e o `completion-auditor` passam a exigir a contagem: "o comando
   de aceite passou" só vale com N > 0 testes executados. Verde-vazio vira UNPROVEN com
   motivo nomeado, não NEEDS-HUMAN genérico.
3. Onde o repo quiser o modo estrito de volta numa rodada, o caminho continua existindo
   (`-Dsurefire.failIfNoSpecifiedTests=true` no wego) — mas o gate não pode depender de
   alguém lembrar de passar a flag.

### Critério de pronto

Rodar um comando de aceite com nome de teste inexistente e o harness NÃO deixar o
commit passar nem declarar o card feito — hoje deixa as duas coisas.

---

## Onda termina e ninguém aterrissa: o merge train não roda sozinho

**Status:** pendente · **Lar:** `maestro/commands/run.md` (passo 8, merge train) +
`maestro/bin/maestro-wave-state` · **Origem:** onda 1 do programa `WEGO-paralelo`
(2026-08-24). Duas branches prontas e verdes ficaram paradas até alguém reparar.

### Problema

O `/maestro:run` tem um último passo que aterrissa a onda: percorre as branches das
slices que terminaram e as mescla na branch de integração, reusando os guards do
`worktree-merge` com verificação depois de cada merge. Esse passo **só roda enquanto a
sessão do maestro está viva e chega até ele**. Na onda 1 a sessão morreu antes (as
filhas terminaram, o event loop nunca reconciliou — ver o defeito do `maestro-poll`,
já consertado em 0.4.3), e o resultado foi:

- S-2050, S-2059 e S-2070 aterrissaram porque uma pessoa mesclou à mão, horas depois;
- S-2067 e S-2107 ficaram paradas até outra sessão notar, meio dia depois, e mesclar
  também à mão (`0a92b95`, `26cec13`);
- o `landed:` do `wave-state.yaml` seguiu `[]` o tempo todo, então nada em disco dizia
  que faltava aterrissar — o estado parecia "onda rodando", não "onda esperando você".

O modo de falha é o mesmo do falso TIMEOUT: **o estado não distingue "ainda
trabalhando" de "terminou e ninguém veio buscar"**. A diferença é cara porque a
segunda exige ação humana e a primeira não.

### Esboço de solução

1. `maestro-wave-state` ganha um estado terminal explícito por slice: `DONE` (a filha
   terminou) e `LANDED` (a branch está na integração). Hoje só existe o primeiro, e o
   `landed:` é uma lista solta no topo, fácil de ficar para trás.
2. `/common:next` e `/common:doctor` passam a olhar programas com slice `DONE` e não
   `LANDED` e a nomear isso como **ação humana pendente** — que é a distinção que o
   `next` já sabe fazer para outros casos.
3. O `/maestro:resume` reaterrissa: ao retomar um programa cuja onda inteira está
   `DONE`, ele deve ir direto ao merge train em vez de concluir "não há nada rodando".
4. Retentativa forkada durante a onda (S-2067R, S-2107R nasceram assim) precisa entrar
   no `wave-state.yaml` no momento em que é criada. Na onda 1 elas apareceram só na
   onda seguinte, o que é como duas sessões acabaram achando que eram donas delas.

### Critério de pronto

Matar a sessão do maestro logo depois de a última filha terminar e, na sessão
seguinte, o `/common:next` dizer "5 slices terminadas esperando merge" em vez de
silêncio — sem que ninguém precise abrir o `wave-state.yaml`.

---

## Calibrar as regras do porteiro do Maestro com o 1º lote de sombra (43 escalações)

**Status:** PARCIAL — o conserto do motor de classificação aterrissou (maestro 0.4.3,
`allow_mecanico` + `_shellscan`, teste
`tests/test_gatekeeper_classifica_linha_inteira.py`). Medido reprocessando o lote
congelado: liberações que escrevem 8 → **0**, falso `delete-broad` 1 → **0**,
escalações 43 → **29** (35 `read-only` + 10 `base-pipeline` + 29 zona cinza, soma 74).
As 29 restantes são todas escrita de arquivo por shell — a zona cinza legítima.

**O QUE FALTA, adiado de propósito (2026-08-24, decisão do dono):** liberar sozinho a
escrita cujo arquivo-alvo cai DENTRO da superfície declarada da slice — o item 2 abaixo.
É a metade que muda o que passa SEM perguntar, então espera a 0.4.3 rodar pelo menos uma
onda de verdade antes de entrar. Enquanto não entrar, essas 29 param a filha e pedem
decisão humana uma a uma. · **Lar:** `maestro/bin/maestro-gatekeeper` (constantes `STRATEGIC` e
`load_rules`) · **Origem:** onda 1 do programa `WEGO-paralelo` em wego-acesso-backend
(2026-08-24) — a primeira vez que o porteiro rodou contra trabalho real.

O porteiro rodou em `--shadow` (modo sombra: aprova tudo e só registra o que TERIA
mandado o dono decidir), como manda o design para o 1º programa. Produziu 73 decisões:
31 liberadas pela regra `read-only` e **43 escalações que ninguém olhou** — o TTL de 1h
venceu e o dado morre sem virar calibração se não for lido agora. Ledger:
`<repo>/.claude/programs/WEGO-paralelo/gatekeeper/decisions.jsonl` (uma linha JSON por
decisão, com `comando`, `regra`, `decisao`, `effective`, `slice`) + um YAML por escalação
em `gatekeeper/escalations/`.

### O que o lote mostra

Distribuição por regra: 42 `gray-zone` (zona cinza = nenhuma regra mecânica casou, então
escala por default) + 1 `delete-broad`. Por slice: S-2050 18, S-2059 8, S-2067 8,
S-2070 8, S-2107 1 — ou seja, escalação é rotina, não exceção, e com o porteiro ligado
pra valer a onda teria parado 43 vezes esperando o dono.

**O achado grave está do outro lado, nos ALLOWs.** Das 31 liberações automáticas,
**8 escrevem arquivo** e o motor as classificou como `read-only`. A regra é uma
expressão regular ancorada no INÍCIO da linha (`^(ls|cat|pwd|echo|grep|...)`), então
tudo depois da primeira palavra é invisível para ela: `cat > <arquivo> <<'EOF'` casa
por causa do `cat`. Passaram assim a escrita de um teste Java de verdade
(`cat > api-rest/.../CaminhoNormalizadoPolicyTest.java`), dois arquivos em /tmp e
cinco `resultado.txt` — e uma dessas linhas terminava em
`git add -A && git -c user.name=alegomes commit -q -m "..."`, ou seja o porteiro
liberou um commit achando que era leitura. Em sombra não custou nada; ligado pra
valer, é a camada 3 inteira decorativa para qualquer coisa escrita como
`<comando-de-leitura> && <o-que-eu-quiser>`. **FEITO** (maestro 0.4.3): a regex saiu e
entrou `allow_mecanico`, que usa o `_shellscan` para ler a linha inteira e só libera
quando toda cabeça de comando está no conjunto pré-aprovado E nada é escrito.

Do lado das escalações, três achados, cada um com um conserto diferente:

1. **Ruído puro (23 das 42):** `sed -n '340,420p' <arquivo>` (12) e `./mvnw -pl X -am
   test -Dtest=Y 2>&1 | tail -30` (11). Os dois comandos JÁ estão no `BASE_BASH` das
   settings geradas, mas o allow do Claude Code casa `Bash(cmd:*)` e não sobrevive ao
   pipe nem ao redirecionamento — então caem no catch-all `ask` e viram zona cinza.
   **FEITO** (maestro 0.4.3): a regra olha todas as cabeças da linha. Leitura pura sai
   como `read-only`; build e teste saem como `base-pipeline`, nome próprio para "não é
   leitura, mas é o trabalho que a slice existe para fazer". Detalhe que custou uma
   rodada: os redirecionamentos têm de ser removidos ANTES de quebrar em segmentos,
   porque `2>&1` tem um `&` e a quebra o lia como separador de comando.
2. **Escrita por Bash, que é a zona cinza LEGÍTIMA (10+):** as filhas escreveram Java
   com `python3 - <<'EOF'` (heredoc), `perl -0pi -e`, `cp /tmp/X.bak <arquivo>` e
   `cat > <arquivo> <<'EOF'`. É exatamente a família `bash-pathlock-bypass` já conhecida
   do repo — a superfície declarada da slice não protege nada se a filha escreve por
   shell. Aqui o porteiro escalar está CERTO; o que falta é ele decidir sozinho o caso
   fácil: extrair o arquivo-alvo do comando e liberar quando o alvo está dentro da
   superfície da slice (o `slice=` já vem na URL), escalando só o que cai fora.
3. **Falso positivo de `delete-broad` (1):** um `mkdir -p bin/tests && cat > ... <<'EOF'`
   foi classificado como remoção ampla porque o padrão `rm -rf?` casou com texto DENTRO
   do heredoc — o corpo do script sendo criado. É o mesmo defeito já corrigido nos hooks
   em 2026-08 ("texto citado não é shell"), cujo motor virou `common/hooks/_shellscan.py`.
   **FEITO** (maestro 0.4.3): `sem_corpo_de_heredoc` tira o corpo antes de qualquer
   varredura, e os padrões estratégicos passaram a ler o texto sem aspas em vez do
   payload cru. Um `rm -rf build/` de verdade continua visível.

### Critério de pronto

Reprocessar este mesmo `decisions.jsonl` com as regras novas e exigir: zero
`delete-broad`, as 23 de ruído viram `allow`, e as escalações restantes são só escrita
fora da superfície. Além disso: nenhum ALLOW pode escrever arquivo nem commitar.

O lote está congelado em `tests/fixtures/gatekeeper-shadow-wego-paralelo/`
(`decisions.jsonl` + os 43 YAMLs + um README que explica os campos), então o teste de
calibração tem contra o que rodar. O que é perecível são os worktrees das filhas em
`~/.herdr/worktrees/wego-acesso-backend/session-wego-paralelo-*`, que guardam o
`resultado.txt` de cada slice — a explicação de por que cada comando foi rodado.

---

## Baseline cega para builds longos (> teto de foreground do Bash)

**Status:** pendente · **Lar:** `common/hooks/capture-build-result.py` (+ possivelmente
`gate-advance.py`) · **Origem:** sessão wego 2026-07-20 — build Maven de ~14:30 nunca
grava baseline, diagnóstico confirmado como limite de desenho, não uso errado.

### Problema

Choque entre duas medidas fixas: o `capture-build-result` decide verde/vermelho pelo
**marcador literal no `tool_response`** (`BUILD SUCCESS` etc. — por desenho, já que o
tool_response omite exit code no sucesso), e o Bash do CC tem **teto de foreground de
10 minutos**. Build que dura mais que o teto é movido para background e o
`tool_response` vira só "moved to background" — sem marcador, sem gravação. Resultado:
**enquanto o build durar mais que o teto, NENHUMA invocação grava baseline**; o
green-or-revert opera cego (ou pior, STALE eterno) exatamente nos repos de build mais
pesado. Determinístico, não intermitente.

Nota: isto provavelmente explica parte da evidência "gravação intermitente em
background/`| tail`" reportada pela sessão wego de 07/16 e deixada sem card por falta
de reprodução — o subcaso >10min é reproduzível.

### Esboço de solução

O sinal precisa parar de depender do tool_response da invocação que INICIOU o build.
Caminhos (não exclusivos, decidir no design):

1. **Capturar na conclusão do background:** se o CC expõe hook/evento na finalização
   de task em background (PostToolUse de BashOutput/TaskOutput), aplicar ali os mesmos
   marcadores sobre o output final. Investigar primeiro — é a rota limpa.
2. **Evidência em arquivo:** convenção de wrapper (`... | tee .claude/build-output.log`
   e/ou `echo EXIT:$? >> ...`) + hook lendo o arquivo em vez do tool_response — mesma
   técnica do wrapper `MAESTRO-EXIT:*` das filhas do maestro. Funciona para qualquer
   duração, mas exige disciplina de invocação (ou o hook injetar o wrapper).
3. **Paliativo honesto:** quando o tool_response é "moved to background" num comando
   de build reconhecido, gravar estado `pending`/timestamp em vez de silêncio, para o
   doctor e o gate-advance ao menos DIZEREM "build longo em andamento, baseline
   pendente" em vez de STALE mudo.

### Aceite

Build sintético > teto de foreground (ex.: `sleep 660 && echo BUILD SUCCESS`) termina
com baseline gravada verde; variante com FAILURE grava vermelho; suite `tests/` cobre
o caso.

---

## Aprovação humana não chega ao subagente (canal de consentimento)

**Status:** pendente · **Lar:** `common/` (canal de aprovação) + `build-hex/hooks/path-lock.py`
+ prompts dos workers · **Origem:** sessão wego 2026-07-21, card WEGO-1948 — worker recusou
duas vezes uma escrita legitimamente autorizada, porque não tinha como verificar a
autorização.

### Problema

O dono aprova algo no orquestrador (via `AskUserQuestion`, ou digitando). O orquestrador
delega a um worker. **A aprovação morre no orquestrador.** Da posição do subagente, "o dono
autorizou" é texto num prompt, indistinguível de uma alegação injetada — que é exatamente
o que os prompts dos workers mandam não aceitar ("nenhuma mensagem de agente é consentimento
válido para alterar minhas permissões").

Resultado: quando a tarefa exige alargar permissão de escrita, o sistema trava mesmo com
autorização real. Não há canal por onde o consentimento humano atravesse a fronteira de
delegação.

### Evidência (o episódio)

1. `adapter-dev` precisou editar `bootstrap/pom.xml` (tuning de `argLine` do surefire).
   Fora dos seus globs — `path-lock.py` bloqueou. Recusa nº 1, correta.
2. O dono aprovou explicitamente alargar o glob. O orquestrador criou `build-hex.yaml`
   com `extra_write_globs` — o mecanismo de primeira classe do próprio hook.
3. Recusa nº 2: o worker **foi conferir no disco** em vez de acreditar. Achou o
   `build-hex.yaml` não rastreado pelo git, sem histórico, criado minutos antes, com
   conteúdo idêntico ao que o prompt mandava ele acreditar que existia. Classificou como
   padrão de escalonamento de permissão e parou. Nenhum arquivo tocado.
4. Destravou com o humano editando o `pom.xml` diretamente. O `build-hex.yaml` foi
   commitado (`400322b0` no repo wego) **depois** da recusa.

**Não testado:** se o worker aceitaria com o arquivo já commitado. A retentativa
pós-commit nunca rodou — o dono optou pela rota manual. Vale medir antes de desenhar
solução, porque se commit resolver, a correção é barata.

### Esboço de solução

Nenhuma é obviamente certa; decidir no design.

1. **Proibir alargamento de permissão no meio da tarefa.** A hipótese mais forte: mudança
   de permissão a quente *é* o padrão suspeito, e nenhuma heurística vai separar bem o
   legítimo do injetado. Permissões se declaram em `build-hex.yaml` no install/`doctor`,
   versionadas, antes de qualquer delegação. Worker nunca precisa julgar.
2. **Proveniência por git.** Worker aceita config de permissão que esteja *commitada*, e
   recusa arquivo solto. Não é à prova de agente com direito de commit, mas eleva a barra
   e deixa rastro auditável. Barato — talvez já funcione hoje (ver "não testado" acima).
3. **Canal atestado pelo harness.** O CC gravaria a resposta do `AskUserQuestion` num
   registro que o subagente lê e o orquestrador não forja. **Provavelmente inviável como
   arquivo:** se o orquestrador escreve onde o subagente lê, nenhum esquema puramente de
   arquivo é sólido. Exigiria suporte do produto (assinatura/atestação fora do alcance dos
   agentes). Investigar se existe superfície para isso.
4. **Recusa como saída barata, não como ciclo queimado.** Se 1-3 falharem, ao menos tornar
   `NEEDS-HUMAN-APPROVAL` um retorno de primeira classe e imediato, em vez de o worker
   gastar a delegação inteira para depois recusar. Aqui custou ~4 min por recusa, duas vezes.

### Pendências de design

- Testar a hipótese barata primeiro: worker aceita `build-hex.yaml` commitado?
- Se a política virar "permissão só se declara no install", o `doctor` precisa detectar o
  caso "worker sem dono para arquivos de build" **antes** da tarefa esbarrar nele. Hoje
  nenhum dos 10 workers da `build-hex` tinha escrita em `pom.xml` de módulo, e ninguém
  soube disso até uma tarefa parar.
- Instrumentar: contar recusas por permissão na telemetria (`/common:metrics`), para saber
  se isso é raro ou crônico antes de investir.

### Prova de campo — matéria-prima de marketing

O episódio é uma demonstração limpa de defesa contra deputado confuso dentro da própria
equipe de agentes, e o dono pediu para guardar como material de produto. A história, como
ela aconteceu:

> Um agente de código recebeu, do seu próprio orquestrador, a instrução de editar um
> arquivo fora da sua área. O pedido vinha acompanhado da frase "o dono do projeto
> autorizou" e de um arquivo de configuração que, de fato, concedia a permissão.
>
> O agente não obedeceu. Foi conferir no histórico do projeto e descobriu que o arquivo de
> permissão tinha sido criado minutos antes, não estava versionado e não tinha nenhum
> registro de autoria humana. A única prova de autorização era a própria frase de quem
> estava pedindo. Ele parou e devolveu o caso para o humano.
>
> A autorização era verdadeira. Mas o agente não tinha como saber, e agiu como se não
> fosse. É esse o comportamento que separa uma frota de agentes de um único ponto de
> falha: se um prompt malicioso um dia pedir a mesma coisa com as mesmas palavras, a
> resposta será a mesma.

Pontos de apoio para quem for escrever a peça:

- O custo real foi um ciclo de trabalho perdido. O benefício é que a trava não depende da
  boa-fé de quem pede.
- É verificação, não obediência: o agente checou uma fonte independente (o histórico do
  projeto) em vez de confiar no texto que recebeu.
- Vale como contraste com o modo de falha oposto, já registrado nesta base: agente que
  afirma fato de handoff sem conferir. Mesma disciplina, dois sentidos.

⚠️ Antes de publicar: passar pelo gate de honestidade de claims (ver "Topologia de
marketing"). O que está provado é **um** episódio real, não uma taxa de detecção. Não
transformar em número.

---

## `summary-nulls-gate` bloqueia summary honesto por formatação (falso positivo)

**Status:** ✅ CORRIGIDO 2026-07-21 (pendente `bin/install.sh` para valer na cópia
instalada) · **Lar:** `common/hooks/summary-nulls-gate.py` (+
`tests/test_summary_nulls_gate.py`) · **Origem:** sessão wego 2026-07-21, validação da
Leva 1 via `/board-flow:execute WEGO-1948`.

> **Correção aplicada.** `MARKER` passou a aceitar negrito, heading markdown (`###`),
> heading de wiki (`h3.`) e bullet; a ordem das palavras no pt-BR ficou frouxa; e a
> mensagem separa "ausente" de "presente em formato não reconhecido". A suíte foi de 19
> para 27 checks; prova por perturbação: revertendo o hook, 6 dos 8 checks novos ficam
> vermelhos. **Segundo defeito achado durante o conserto** e corrigido junto: o
> `SUMMARY_HEADING_RE` só reconhecia heading markdown, então um summary em wiki do Jira
> com ZERO campos **passava em silêncio** — o buraco era pior que o falso positivo que
> originou o card.

### Problema

O gate exige os 4 campos de nulos explícitos em `**negrito**`, com redação exata. Um
Implementation Summary que **responde as quatro perguntas de boa-fé**, mas usa markup de
wiki do Jira (`h3.`) em vez de markdown, é bloqueado — e a mensagem de erro afirma que
**os quatro campos estão faltando**, quando os quatro estão respondidos logo abaixo.

Três condições do ambiente conspiram para isso reincidir sempre:

1. O harness manda escrever em **pt-BR** (regra transversal do dono).
2. Comentário de Jira usa **markup de wiki** (`h3.`), não markdown — é o formato natural
   de quem está escrevendo para o Jira.
3. O regex exige `\*\*` e **ordem exata das palavras**: aceita `Dívida nova introduzida`,
   mas rejeita `Nova dívida introduzida`.

O regex atual (`REQUIRED_FIELDS`) já contempla variantes pt-BR, então a intenção
bilíngue existe — o defeito é de forma, não de idioma.

### Evidência (2026-07-21, hook exercitado diretamente)

```
passou    (exit 0)  1. EN completo (4/4)
BLOQUEOU  (exit 2)  2. EN faltando 1 → aponta: Human validation route
BLOQUEOU  (exit 2)  3. EN faltando 2 → aponta: Release needed + Human validation route
passou    (exit 0)  4. PT-BR completo em negrito
BLOQUEOU  (exit 2)  5. PT-BR completo, mas com header h3.  ← FALSO POSITIVO
passou    (exit 0)  6. comentário comum, sem heading de summary
```

Casos 2, 3 e 6 provam que **o gate funciona** — bloqueia por omissão real, nomeia o campo
certo, e não barra comentário que não é summary. O defeito é isolado ao caso 5.

Caso 5 aconteceu de verdade no WEGO-1948: primeira tentativa de publicar o summary foi
rejeitada, e o agente "corrigiu" reformatando. Funcionou, mas pelo motivo errado.

### Por que isso é pior que um bug cosmético

Um gate que dá falso positivo ensina o agente que **o bloqueio é ruído de formatação**.
A partir daí ele contorna mecanicamente em vez de tratar a pergunta como pergunta — que é
exatamente o hábito que o gate existe para impedir. Gate que erra treina desprezo por
gate.

Agrava: a mensagem de erro é ativamente enganosa (diz "faltando" sobre campo presente),
então nem o agente nem o humano aprendem a causa real. Na sessão de origem, a explicação
que circulou foi "o gate só aceita inglês" — falsa, e repetida adiante como fato.

### Esboço de solução

Mudança pequena, no regex de `REQUIRED_FIELDS`:

1. **Aceitar cabeçalho além de negrito:** prefixo `(?:\*\*|#{1,6}\s*|h[1-6]\.\s*)` cobrindo
   markdown bold, heading markdown e heading de wiki do Jira.
2. **Afrouxar a ordem das palavras no variante pt-BR**, ou casar por palavras-chave
   (`dívida.*introduzida`) em vez de frase literal.
3. **Corrigir a mensagem de erro:** quando o rótulo aparece no corpo mas fora do formato
   esperado, dizer *"campo presente mas em formato não reconhecido"* em vez de *"faltando"*.
   Distinguir os dois casos é o que impede a explicação errada de circular.

### Aceite

- `tests/test_summary_nulls_gate.py` cobre os 6 casos da tabela acima. Hoje a suíte
  (141 linhas) já cobre o variante pt-BR em negrito, mas **não** o caso de cabeçalho wiki.
- Caso 5 passa (exit 0).
- Casos 2 e 3 seguem bloqueando, com o nome do campo faltante correto — a proteção não
  pode ser afrouxada junto.
- A mensagem de erro distingue "ausente" de "presente em formato não reconhecido".

### Nota sobre a validação da Leva 1

A demanda de origem pedia validar em card real que (a) o summary sai com os 4 campos e
(b) o gate bloqueia se faltar. **(a) foi validado organicamente; (b) não.** Rodar um card
real quase nunca produz summary com campo faltando, porque quem escreve está tentando
acertar — o cenário de omissão só aparece em teste sintético. Vale registrar como padrão:
*gate de omissão não se valida por uso, só por teste.*

## `prove-drain` não tem disjuntor: falha de ambiente reprova a coluna inteira

**Status:** 🔵 ABERTO · **Lar:** `board-flow/commands/prove-drain.md` · **Origem:**
painel de advisors sobre `docs/estrategia-drain-plan-velocidade.md`, 2026-08-26
(discordância D2, levantada pelas lentes `operador-sre` e `contrarian`). Decisão do dono
no mesmo dia: registrar, não construir agora.

O `/board-flow:prove-drain` **não para no primeiro UNPROVEN**, e isso é de propósito:
esvaziar a coluna Review é o ponto, e um card não provado não deve bloquear os outros. O
buraco é que a política não distingue **card ruim** de **ambiente quebrado**. Se o Docker
está fora, ou uma ferramenta do gate sumiu, a prova falha por motivo que não é do card —
e o lote segue reprovando um card atrás do outro, em série, gastando o orçamento inteiro
e devolvendo uma coluna de UNPROVEN que não significa nada.

O `/board-flow:drain` não tem esse risco porque para no primeiro BLOCKED. O `prove-drain`
abriu mão dessa parada sem colocar nada no lugar.

### Esboço de solução

Um disjuntor por UNPROVEN **consecutivos**, não por total: 2 seguidos param o lote e
pedem olho humano. Card ruim isolado não dispara (o próximo passa); ambiente quebrado
dispara na segunda tentativa. O mesmo teto cabe no `/common:drain-plan`, se ele algum dia
ganhar o lote de prova separado — que hoje NÃO é recomendado, pelos motivos no documento
de estratégia.

### Por que não foi feito junto

A sessão que levantou isso estava medindo por que o `/common:drain-plan` demora, e a
resposta foi outra (espera ativa dos leads, corrigida em `9ce9760`). O disjuntor é
problema real e menor, de outra rotina — misturar os dois inflaria um diagnóstico que já
tinha entregado o que precisava.


## O modo é prosa: desvio vira pergunta, pergunta vira "sim", e o modo não segurou nada

**Status:** ✅ FEITO em 2026-08-26 (`common/hooks/modo-escrita-gate.py`, common
2.11.0 — **não está live até `bin/install.sh --clean` + restart**) · **Lar:**
`common/hooks/` (irmão do `reforma-gate.py`) ·
**Origem:** a própria sessão `session/drain-plan-speed`, 2026-08-26 — o agente furou o modo
sete vezes seguidas e só parou quando o dono perguntou "se esta é uma sessão de exploração,
por que você está construindo tantas coisas?".

O `session-mode.py` injeta a cada turno: *ação fora deste modo NÃO vira pergunta e NÃO vira
trabalho agora; registre pelo `off-mode-capture` e siga*. Nada barra. O agente fez o oposto
das duas: transformou cada desvio numa pergunta fechada com "Recomendo sim", colheu o sim, e
construiu.

**Evidência, da sessão que descobriu isso.** A condição de saída da exploração — documento de
estratégia com 2+ caminhos, passado pelo painel de advisors — foi satisfeita no **primeiro**
dos sete commits (`95bebcd`). Dos sete, três são do modo e **quatro são construção**:
`9ce9760` (hook + `cepa-clock`), `f7341cb` (10 specs de agente), `72b1162` (teste de deriva),
`e7a3c1e` (`/common:modos`) — mais uma edição na statusline, fora do repo. **Nenhuma captura
de desvio foi registrada**; o `off-mode-capture` não foi invocado uma vez sequer.

Duas skills se aplicavam e nunca foram confrontadas: a `default-yes` manda decidir sozinho em
ação reversível, o modo manda não trabalhar fora dele. A `default-yes` ganhou todas. O agente
nunca nomeou o conflito para o dono.

É o padrão que este repo já catalogou três vezes (memória
`gate-por-nome-de-ferramenta-falha-aberto`): **controle que depende do agente se comportar não
é controle.** A diferença aqui é que o contorno teve aval do dono a cada passo, o que o torna
mais difícil de enxergar, não menos real.

### Esboço de solução: `common/hooks/modo-escrita-gate.py`

Irmão exato do `reforma-gate.py`, que já é um gate de escrita escopado por modo (bloqueia
editar teste externo enquanto a reforma corre, em Edit/Write/MultiEdit **e** em Bash). Aqui a
regra é uma lista branca de destinos por modo — o que aquele modo **produz**:

| modo | pode escrever | bloqueado |
|---|---|---|
| `exploracao` | `docs/**`, `.claude/**` | código, hook, comando, agente, teste |
| `descoberta` | `docs/discovery/**`, `docs/spec/**`, `.claude/**` | idem |
| `design` | `docs/design/**`, `.claude/**` | idem |
| `reflexao` | `.claude/reflexao/**`, `docs/**` | idem |
| `documentacao` | `docs/**`, `.claude/**` | código, hook, comando, agente |
| `construcao` | tudo | — (o `completion-auditor` e o `proof-reviewer` é que cobram) |
| `reforma` | tudo menos teste externo | — (já é o `reforma-gate`) |

Três exigências, todas aprendidas na marra neste repo:

1. **Cobrir Bash também.** Barrar só `Write`/`Edit` deixa `sed -i`, `cat >`, `tee` passarem —
   memória `bash-pathlock-bypass`, custou um conserto em 5 topologias. Reusar
   `common/hooks/_shellscan.py`, que já é a fonte única desse parsing.
2. **O escape não pode ser barato.** `# modo-ok` no comando seria a mesma fuga de novo: o
   agente digita e segue. O escape honesto é `CEPA_MODO=off` (já existe, desliga a mecânica
   inteira e é visível) ou fechar o modo e abrir outro — que é uma sessão nova, e é o custo
   certo, porque trocar de atividade DEVERIA custar.
3. **A mensagem tem que dizer o que fazer:** registrar pelo `off-mode-capture` e seguir; se o
   trabalho é mesmo necessário agora, encerrar este modo e abrir o modo dele.

**O que este gate NÃO alcança:** a metade "não vira pergunta". Isso é texto do agente, não
chamada de ferramenta, e nenhum hook lê a redação de uma resposta. Mas a trava de escrita
torna a pergunta inútil — não há o que oferecer quando o passo seguinte está barrado. Vale
medir depois: se o agente passar a *perguntar se pode desligar o gate*, o buraco só mudou de
lugar, e aí o próximo degrau é telemetria de `modo_escrita_block` no `/common:metrics`.

### O que foi construído

A tabela acima virou o campo `escrita` de cada modo em `common/hooks/_modos.py`
(a tabela de modos já era fonte única; uma segunda no hook seria a doença que
aquele arquivo trata) e o hook `common/hooks/modo-escrita-gate.py`, registrado
em `PreToolUse` para Bash e para Edit|Write|MultiEdit|NotebookEdit.

Três desvios do esboço, todos deliberados:

1. **`BACKLOG.md` entrou em todas as listas brancas.** A tabela do esboço não o
   previa, e sem ele a Reflexão não consegue cumprir a própria condição de saída
   — "nenhum achado sem destino, cada um virou card" — porque é aqui que este
   repo registra card. O mesmo vale para exploração e descoberta, que produzem
   achado e oportunidade.
2. **Escrita fora da raiz da sessão passa.** Não estava no esboço. Sem isso, a
   worktree de perturbação em `/tmp` e o scratchpad ficariam sob o modo, que é
   exatamente o estrago da memória `path-lock-out-of-root` (5 cards presos em
   NEEDS-HUMAN) repetido de outro ângulo.
3. **A exigência 1 (reusar o `_shellscan.py`) cobrava mais do que o módulo
   tinha.** Ele parava no parsing; a pergunta "que arquivos esta linha escreve?"
   estava respondida em duas versões divergentes — a do `bash-path-lock` (que
   conhece `git mv` e conta a origem de um `mv`) e uma mais pobre no
   `enforcement-guard`. A do `bash-path-lock` foi portada para o `_shellscan.py`
   e o detector de divergência passou a comparar as duas fontes também nessas
   funções. Um defeito real apareceu no caminho e foi consertado no molde e nas
   5 cópias: a forma BSD `sed -i '' 's/a/b/' arquivo` deixa o `''` como
   operando, e o SCRIPT do sed era contado como arquivo escrito.

**Dívida deixada de pé, de propósito:** o `enforcement-guard.py` mantém a versão
própria e mais pobre dessas duas funções. Fazê-lo importar do `_shellscan` muda
o comportamento de um gate de enforcement (passaria a barrar `git mv` e a origem
de um `mv`) e não é deste card. A telemetria de `modo_escrita_block` no
`/common:metrics`, que o esboço já colocava como degrau seguinte, também segue
aberta.

### Por que não foi feito junto

Porque construí-lo em modo exploração seria a oitava violação, e a primeira depois de ela ter
sido nomeada. **O gate bloquearia a própria construção dele** — é um hook, e hook está na
lista de bloqueados da exploração. O caminho certo custa um comando ao dono: sessão nova com
`cepa --modo construcao`, que é a mecânica funcionando como projetada.


---

# Programa melhorias-2026-07

Universo de demandas da auditoria de sessões de 07/2026 + discussão de lacunas.
Plano de execução em ondas: `.claude/programs/melhorias-2026-07/plan.yaml`.
Também é o v0 do Maestro: valida o formato de plano/ondas antes do daemon existir.

## P1. Lint editorial como hook

**Onda 1 · Lar:** `common` · **Status:** ver plan.yaml

Regras de estilo (zero travessão, LinkedIn-ês, hashtags genéricas) hoje dependem de
re-ensino do usuário a cada sessão (2+ correções idênticas na auditoria). Solução:
hook PostToolUse em Write/Edit/MultiEdit, **opt-in por projeto** via
`.claude/editorial-lint` (globs, um por linha — sem o arquivo, hook inerte). Ao
detectar travessão/frases-marca/hashtag genérica em arquivo casado, devolve aviso ao
modelo (exit 2 em PostToolUse = feedback não-bloqueante). Aceite: escrever "foo — bar"
num arquivo coberto gera o aviso; arquivo fora dos globs não gera nada.

## P2. Nudges de manutenção (doctor diário, metrics semanal)

**Onda 1 · Lar:** `common` · **Status:** ver plan.yaml

O doctor e o metrics só valem se rodarem; hoje dependem de memória do usuário.
Solução: `session-registry` (SessionStart) injeta sugestão de `/common:doctor` se o
repo está >24h sem rodá-lo (stamp `.claude/doctor-last-run`, gravado pelo próprio
doctor) e de `/common:metrics` se >7d sem revisão (stamp no dir de telemetria, gravado
pelo cepa-metrics). Nudge, nunca bloqueio. Nota: o item era "cron do metrics" via
/schedule, mas routine cloud não lê o ledger local (~/.claude) — adaptado para nudge
local; um launchd job fica como evolução se o nudge se provar fraco.

## P3. Manifesto de ambiente (.claude/env.yaml)

**Onda 2 · Lar:** `common` · **Status:** pendente

O cepa modela código, não runtime — e as fricções de sessões paralelas foram todas de
runtime (porta 8083, ~/.m2, .env, containers). Solução: `.claude/env.yaml` por projeto
(portas usadas, serviços dependentes, comando de subida, healthcheck, arquivos a
seedar). Consumidores: preflight do worktree-start (vira mecânico), cepa-doctor
(checa portas/serviços), seed-worktree (lista de seeds). Aceite: doctor acusa porta
ocupada declarada no manifest; worktree-start seeda o que o manifest lista.

## P4. Consolidação periódica de mental-models

**Onda 2 · Lar:** `common` · **Status:** pendente

Entries de expertise acumulam com prune por contagem, nunca re-verificados — mesmo
defeito do handoff pré-"hipótese". Solução: comando `/common:consolidate` que funde
entries redundantes, aposenta os que o código atual contradiz (verificando contra o
repo) e marca proveniência. Aceite: rodar no expertise mais gordo reduz entries sem
perder nenhuma regra ainda-válida (diff revisável antes de gravar).

## P5. Cascata multi-repo no board-flow

**Onda 2 · Lar:** `board-flow` · **Status:** pendente

Trabalho backend+frontend+extensão exige fechamento manual de cards em cada repo
("feche o WEGO-1940 nos dois brokers"). Solução: convenção de cards vinculados
(link type configurável) + no fechamento do pai, atlassian-expert lista filhos
abertos e propõe cascata. Sempre via seam opcional — nada disso vira premissa para
projetos sem Jira. Aceite: fechar card pai com 2 filhos linkados gera proposta de
fechamento dos 2.

## P6. Proof-gate de UI/extensão

**Onda 3 (design interativo) · Lar:** novo agente em `common` ou plugin próprio ·
**Status:** pendente — TEM decisão de design aberta (onde mora a superfície
Playwright: por repo frontend vs genérico no cepa)

O proof-reviewer prova o backend; a superfície onde o usuário mais sofre (SPA +
extensão Chrome) não tem gate. Solução: irmão do proof-reviewer para UI — Playwright
como superfície externa (carrega extensão unpacked, percorre o fluxo, asserta efeito
no backend), screenshot-diff para regressão visual. Aceite: regressão plantada na
extensão do wego-acesso é pega pelo gate.

## P7. Advisors como Workflow

**Onda 3 (design interativo) · Lar:** `common` · **Status:** pendente — resolver as 3
pendências do item "Advisors" acima (declaração de área, nº de lentes, quem sintetiza)

O item Advisors deste backlog implementado como Workflow script (fan-out isolado
determinístico + síntese name-the-disagreement), não como prosa de orquestração.
Meta-aceite: usar o advisors recém-nascido para revisar o design do P6.

## P8. Revisão com evidência (fecha o programa)

**Onda 4 · Status:** aguarda ~2 semanas de telemetria

`/common:metrics --days 30`: bloqueios de gate caíram? proof_blocks apareceram?
builds vermelhos mudaram? O que a métrica apontar vira a próxima fornada de cards.

---

# Programa ariad-leva2

Leva 2 de mecanismos garimpados na segunda avaliação do Ariad (2026-07-16/20;
avaliação completa em `memory/ariad-evaluation.md` dos dois espaços de projeto).
Mesmo método da Leva 1: hook primeiro, prosa depois. Plano de execução em ondas:
`.claude/programs/ariad-leva2/plan.yaml`.

**Pré-requisito (passo 0, antes da Onda 1):** rodar o reinstall pendente
(`bin/install.sh --clean` + restart) e validar a Leva 1 viva num card WEGO real —
A4 e A6 estendem o próprio summary-nulls-gate e não devem ser construídos sobre
gate não-validado.

## A1. Validation seeds + carry-forward no handoff do discovery

**Onda 2 · Lar:** `discovery` + hook em `common` · **Status:** ver plan.yaml

Quando exploração vira entrega, o handoff deve carregar sementes de validação
(pensadas ANTES de implementar) e achados implementation-relevant. Template do
`handoff.md` do epic-briefer ganha `Validation seeds:` e `Carry-forward notes:`
obrigatórios (nulo explícito permitido, ausência não); dente = hook
`handoff-seeds-gate.py` (PreToolUse no Write de `docs/discovery/*/handoff.md`,
string-match nos rótulos); seeds viajam para a descrição do card criado. Aceite:
Write de handoff sem os rótulos é bloqueado; com "none" passa.

## A2. Updates operacionais do harness (classes + rota mínima)

**Onda 3 · Lar:** `bin/install.sh` + `common:doctor` + docs · **Status:** ver plan.yaml

Mudança em common/hooks/bin/settings = update **operacional** (muda a superfície
em que o próximo agente opera) e exige rota mínima: estado atual, alvo, rollback,
validação. `install.sh --clean` grava `.claude/ops/last-install.json` (versões
live antes → alvo → resultado) e preserva o cache anterior (`--rollback`
restaura); doctor ganha 2 checks: drift live-vs-repo com idade, e último install
incompleto. Prosa curta em `docs/harness-ops.md` ("na dúvida, é operacional;
ausência de rota de recuperação é fato que o humano vê antes"). Ataca a dor
crônica "NOT live until reinstall". Aceite: install interrompido no meio é
acusado pelo doctor; --rollback restaura o estado anterior.

## A3. Teste "BDD ou substrato" no cepa-dor

**Onda 1 · Lar:** `maestro` · **Status:** ver plan.yaml

Se o plano de um slice/card só nomeia passos privados de implementação — nenhum
Given/When/Then observável em alguma superfície — não é US: ou declara-se
substrato (TS) ou é NOT-READY. `plan-template.yaml` ganha `acceptance_form:
bdd | substrate`; intake gate do `program-plan` reprova slice sem uma das duas
formas, nomeando a lacuna. Aceite: `tests/test_cepa_dor.py` com +2 casos (US sem
BDD reprova; substrato declarado passa).

## A4. Razão obrigatória em bounce-back

**Onda 1 · Lar:** `common/hooks` + `board-flow` (prove*) · **Status:** ver plan.yaml

Card devolvido de Review sem razão estruturada obriga re-arqueologia na próxima
sessão. Hook novo `bounce-reason-gate.py` (mesma técnica do summary-nulls-gate):
comentário de devolução sem `Reason:`/`Motivo:` + texto é bloqueado; templates de
devolução em prove.md/prove-drain.md/atlassian-expert.md ganham o campo. Regra
anexa em prosa: "Attention não é estado — nomeie a condição real (Blocked/
Deferred/Dropped + razão)". Aceite: teste novo + devolução real bloqueada sem razão.

## A5. Regras de fechamento acoplado no drain

**Onda 2 · Lar:** `board-flow` (drain*) + `build-hex:proof-reviewer` · **Status:** ver plan.yaml

Fechar cards em lote só quando causalmente acoplados com fronteira de validação
compartilhada — e mesmo aí, evidência/razão/impacto de dívida POR card; proibido
com risco ou dívida independentes. Seção normativa em drain.md e prove-drain.md;
proof-reviewer recusa veredito agregado ("evidência por card ou NEEDS-HUMAN").
Inclui (vindo do A8) o critério de término: drain não encerra com card sem
outcome terminal nomeado. Enforcement por disciplina + telemetria (contar lote
sem evidência por card se aparecer na prática). Aceite: prove-drain real com
outcome e evidência nomeados por card.

## A6. Dívida com revisit trigger no Implementation Summary

**Onda 1 · Lar:** `common/hooks/summary-nulls-gate.py` + templates board-flow · **Status:** ver plan.yaml

Estende o campo da Leva 1: se `New debt introduced` ≠ none/unknown, o gate passa
a exigir `Revisit trigger:` (e aceita `Closure condition:` opcional). Templates
dos 5 produtores atualizados; dívida que sobrevive ao card vira card Jira com
label `debt` (o board é o ledger — sem sistema de arquivos novo); triage propõe
"Debt Payment" quando o trigger de um card debt disparou; bônus: linha do
critério BDD-ou-substrato (A3) no bucket READY do triage. Aceite:
test_summary_nulls_gate.py +3 casos (dívida sem trigger bloqueia; com trigger
passa; none não exige).

## A7. Lista do incomprimível (regras de compressão por gate)

**Onda 4 · Lar:** docs · **Status:** ver plan.yaml

Do conceito de cadence do Ariad, o exportável é a regra de compressão EXPLÍCITA:
documentar, por checkpoint/gate existente do cepa, o que pode ser comprimido em
trabalho trivial e o que NUNCA pode (rota humana de US; os 4 nulos do summary; a
razão de bounce do A4; "no release needed" dito em vez de pulado). Não cria gate
novo — é o spec de crescimento dos gates. Entra no commit de docs da Onda 4.

## A8. Fronteira de mutação + outcome terminal por onda

**Onda 2 · Lar:** `maestro` · **Status:** ver plan.yaml

Do Refinement do Ariad: revisão nunca edita — achou mudança necessária, abre
card/CR; e nada fecha com item sem outcome terminal. No cepa: check mecânico no
`maestro-wave-state` — merge train/relatório não completa com slice sem estado
terminal (DONE/FAIL/TIMEOUT/ESCALATED); frase normativa nos agentes revisores
com Write (proof-reviewer, completion-auditor): "veredito em YAML, mudança vira
card, nunca edit". (A parte de drain foi para o A5.) Aceite: caso novo em
tests/test_maestro_run_cores.py — onda com slice não-terminal não aterrissa.

## A9. Precedência de instruções em 5 camadas

**Onda 4 · Lar:** docs/`common` · **Status:** ver plan.yaml

Ordem explícita: instrução da sessão > contrato do projeto (CLAUDE.md do repo) >
preferências do usuário (CLAUDE.md global) > defaults dos plugins > guidance
geral; conflito com camada superior = parar e expor. Doc de ~15 linhas
referenciado pelos agentes lead. Entra no commit de docs da Onda 4.

## A10. Versionamento pelo nível que colapsou + release note narrativa

**Onda 4 · Lar:** docs · **Status:** ver plan.yaml

Convenção para bumps dos plugins (contrato de hook quebrado → MAJOR; gate/feature
novo → MINOR; fix → PATCH — formaliza o de facto) e release note/commit de
release citando o que foi **conscientemente excluído**. Entra no commit de docs
da Onda 4.

---

## Fio condutor: "e agora, o que eu faço?" entre sessões e entre cards

**Status:** as 3 peças CONSTRUÍDAS (2026-07-28/29, commits `8d752e3` · `21b73fa`
· `2e8b953` · `86416a4`) — **nenhuma validada em board real** · **Lar:** schema em `common`, produtor e
consumidores em `board-flow`, `maestro` como consumidor irmão · **Origem:**
relato do dono ao fim da sessão do WEGO-1958 (2026-07-28), depois de ~horas de
execução com muitos desdobramentos.

> **Decidido e feito (2026-07-28).** O schema de plano subiu para
> `common/plan-schema.yaml` e ganhou `mode: single-track | parallel-waves` —
> `board-flow` e `maestro` são consumidores irmãos, nenhum depende do outro.
> O schema foi para **v2**, onde `mode` é explícito e obrigatório; a **v1**
> (só ondas, sem `mode`) segue aceita por todos os consumidores, então nenhum
> plano no disco precisou de migração. O número existe para que um consumidor
> que só entende ondas possa dizer "não sei ler isto" em vez de tratar a
> ausência de `waves` como plano vazio. `/board-flow:triage` passou a
> persistir a fila **ordenada** com o `why` por item, e `execute`/`fix`/`prove`
> fecham com "And now?" — rota de validação humana + próximo item do plano.
> `/common:next` responde a pergunta sob demanda (perda 3), reconciliando o
> plano contra o board vivo e nomeando **um** passo com o `why` — nunca um menu.
> Travado por `tests/test_fio_condutor.py` (prova de perturbação em 3 cortes).
>
> **O que falta é uso, não código.** Nada disso rodou num board real: o
> `/board-flow:triage` nunca escreveu um plano de verdade, e o `next` nunca
> reconciliou contra Jira vivo. Os testes travam contrato de prompt, não
> comportamento em produção. Primeira validação honesta = rodar `triage` num
> board com fila real e ver se a ordem proposta sobrevive à revisão do dono.
> Aberto de propósito, para decidir com uso: se o plano deve aparecer no
> `SessionStart` ao lado do handoff, e se vale promover single-track → onda.

### O relato, na voz do dono

> Estamos há algumas horas trabalhando nesta sessão. Começamos com a execução do
> card WEGO-1958, tentamos fazer o prove dele e tivemos que lidar com vários
> desdobramentos. Depois de tantas idas e vindas, a minha memória se perde e eu
> não sei o que fazer na sequência. Sim, o harness me sugeriu fazer um handoff
> agora mas, e depois? O que eu tenho mesmo que fazer depois do WEGO-1958? Tenho
> que testá-lo manualmente? Ou tenho que executar um próximo card? Com muita
> frequência, eu me perco. No entanto, o card 1958 executado nesta sessão nasceu
> em uma sessão anterior na qual ele foi priorizado junto a vários outros. Quais
> são mesmo esses outros? Qual era mesmo a ordem de execução? Percebe o problema?
> Houve um momento de planejamento. Eu comecei a execução. Mas me perdi no meio do
> caminho.

### O problema, destrinchado

São três perdas distintas que hoje se apresentam como uma só sensação de
"me perdi":

1. **A ordem de execução não sobrevive à sessão que a produziu.** Houve um momento
   de planejamento em que vários cards foram priorizados juntos. Essa priorização
   virou prosa no handoff e descrição de card (o WEGO-1958 diz "Pendência 1 do
   handoff"), mas **a lista e a ordem não existem como artefato consultável**. O
   Jira guarda a fila (`To Do`) e não a ordem nem o porquê dela.

2. **O fim de um card não aponta para o próximo passo.** O card fecha com
   Implementation Summary, veredito de prova e status Done. Nada responde
   "e agora?". As duas respostas plausíveis competem em silêncio: *validar à mão*
   ou *puxar o próximo card*.

3. **A sessão longa dissolve o fio.** Uma execução com desdobramentos (3 rodadas de
   proof gate, 4 cards abertos, 2 decisões de escopo) enterra o objetivo original
   sob o rastro do caminho. O `/common:recap` reconstrói o que **foi feito**;
   nenhum comando reconstrói o que **falta fazer**.

### Por que o que já existe não cobre

- **`/common:handoff`** e o nudge de wrap-up salvam contexto e olham para trás.
  Ótimos para retomar *esta* linha de trabalho; mudos sobre a fila que a
  antecedia.
- **`/common:recap`** é explicitamente retrospectivo (você pediu / eu entreguei).
- **`/board-flow:drain`** executa a coluna inteira em ordem de prioridade, mas é
  tudo-ou-nada e sem parada humana: não serve para "um card por vez, sabendo
  qual é o próximo".
- **`maestro:program-plan`** é o parente mais próximo e já resolve metade: escreve
  `.claude/programs/<nome>/plan.yaml` com ondas e slices, e `maestro:resume`
  reconstrói estado. Mas nasceu para **execução paralela em worktrees** (piso de
  uso ≥4 demandas), o que é peso demais para "tenho 6 cards priorizados e vou
  tocar um de cada vez, em sessões diferentes".
- **A1** (validation seeds + carry-forward) toca a mesma família, mas está preso
  ao handoff do `discovery`.

### Esboço de solução (a discutir, nada decidido)

Três peças que podem ser independentes:

1. **Plano de execução persistente e leve** — o "single-track" do
   `maestro:program-plan`: um artefato versionado (`.claude/programs/<nome>/`?)
   que registre a lista priorizada, a ordem, o porquê da ordem, e o estado de cada
   item. Produzido no momento do planejamento, consultado no começo de toda
   sessão. Candidato natural a virar o que o `SessionStart` mostra, ao lado do
   handoff.

2. **`/common:next`** — comando que responde a pergunta literal: dado o estado
   do board e do plano, **qual é o próximo passo e por quê**. Precisa distinguir
   os dois tipos de "próximo": *ação humana pendente* (validar à mão, rotacionar
   segredo, aprovar PR) e *próximo card*. A matéria-prima do primeiro tipo já é
   produzida hoje e se perde: o campo **Human validation route** do Implementation
   Summary é escrito por card e nunca agregado numa lista.

3. **Fechamento de card que aponta adiante** — ao fim de `execute`/`fix`/`prove`,
   fechar com "o que ficou pendente de você" + "o próximo item do plano", em vez
   de só o relatório do que foi feito. Barato, e ataca a dor no ponto exato em
   que ela aparece.

### Sinal de que o problema é real

Nesta mesma sessão o dono perguntou "o que devo fazer?" sobre os follow-ups, e a
sessão terminou com quatro cards novos abertos (1962, 1963, 1964, 1965) — todos
com ordem relativa indefinida e nenhum vínculo com a priorização original que
gerou o WEGO-1958. A dor se reproduz sozinha a cada card executado.

---

## Atrito de decisão — o harness pergunta demais, e pergunta cedo demais

**Status:** pendente · **Lar provável:** `common` (faixas de autonomia, registro de
atestados) + `board-flow` (auditar antes de perguntar, perguntas por sub-task)
· **Origem:** sessão de triagem/drain do WEGO em 2026-08-03 a 2026-08-10, e um pedido
literal do dono ao fim dela: *"Eu só quero que as tarefas fluam pelo quadro, com o
menor atrito possível. Toda vez que você aponta alguma pendência em um card eu tenho
que parar tudo, abrir o card, interpretá-lo, verificar o código e tomar a decisão."*

### Problema

Naquela sessão o dono foi interrompido cerca de **20 vezes**. Classificando as
interrupções depois:

- **5 eram genuinamente dele** — decisão de produto (staging deve recusar requisição
  sem tenant?), atestado sobre o que não está no código (o SMTP está configurado no
  painel do fornecedor?), e priorização entre cards.
- **~10 eram mecânica reversível** que o agente já havia recomendado e o dono apenas
  carimbou: rodar o build curto, criar um card de dívida, empurrar branch ou mesclar,
  commitar 7 documentos de processo, apagar 6 branches órfãos já contidos no `main`,
  apagar 3 handoffs vencidos. Em todas o relatório dizia "Recomendo sim" e em todas a
  resposta foi "sim". A pergunta não carregava informação.
- **~4 eram defeito do próprio harness travestido de tarefa do dono** — instruções
  passo a passo para expor o campo Labels na tela de Task do Jira; o `last-build.json`
  que não grava quando o build roda em segundo plano (e o build do módulo `bootstrap`
  leva 26 min, ou seja, NUNCA cabe em primeiro plano); o `bounce-reason-gate` barrando
  um comentário por conter a palavra "UNPROVEN" numa frase que dizia justamente para
  *não* reprovar; o `summary-nulls-gate` exigindo os quatro rótulos em inglês num
  comentário escrito em pt-BR.
- **1 foi pergunta feita cedo demais, e custou uma reversão.** O agente pediu ao dono
  para decidir o fechamento do Epic WEGO-1406 olhando uma fatia de 15 cards. O dono
  respondeu "pode concluir". Só então o agente auditou e encontrou **41 filhas, 22
  ainda abertas**, das quais 10 eram desenvolvimento não entregue — inclusive os três
  primeiros itens da fila de execução do próprio plano. A resposta certa era mecânica:
  bastava enumerar as filhas ANTES de perguntar.

### Esboço de solução

**1. Faixas de autonomia por reversibilidade.** Hoje "pergunto ou faço?" é julgamento
do agente a cada turno, e o viés observado é perguntar demais. Escrever na configuração:

- *Executa e reporta* (reversível): rodar build, commit local, criar card, apagar
  branch já contido na base, mover arquivo dentro do repo, escrever/atualizar plano.
- *Sempre pergunta* (irreversível ou de fora): empurrar para remoto, mesclar em branch
  de integração, descartar trabalho, transição terminal no board, qualquer coisa que
  envolva segredo, qualquer coisa que saia para terceiros.

O relatório continua listando o que foi feito na faixa automática — o ganho é que vira
*informação*, não *pergunta*.

**2. Auditar antes de perguntar.** Regra dura, no `board-flow:triage` e no
`board-flow:decide`: card com filhos nunca vira pergunta sem enumerar os filhos e o
status de cada um; card que cita `arquivo:linha` nunca vira pergunta sem conferir a
linha. O custo da auditoria é de um minuto; o custo de pular foi uma decisão errada do
dono e a reversão dela.

**3. Registro de atestados.** Quando o dono afirma "isso está concluído", isso vira
fato datado e com escopo num arquivo durável (candidato: `.claude/attestations.yaml`),
não uma frase no chat. Em 2026-08-03 o dono atestou que o pacote operacional do
onboarding PlugSign estava concluído; em 2026-08-04 outra sessão triou o mesmo cluster
como fila de desenvolvimento e tirou 10 cards do escopo por lista de chaves. A
contradição só apareceu em 08-10. Um atestado registrado teria evitado as duas coisas.

**4. Perguntas objetivas por sub-task quando o Epic não decide.** Pedido explícito do
dono (2026-08-10): *"quando um epic possuir subtasks e você não conseguir decidir o
que está e o que não está feito, crie perguntas objetivas para cada card."*

Ou seja: o fallback de um Epic indecidível NÃO é uma pergunta genérica sobre o Epic
("posso fechar?"), e também não é silêncio. É **uma pergunta fechada por sub-task**,
cada uma respondível com sim/não sem abrir o card — no formato que o
`board-flow:decide` já usa para a coluna Review, respondidas em lote ("1 sim, 2 não").
A pergunta tem de citar o que o agente já verificou, para o dono não refazer o
trabalho. **E o nível de detalhe não é fixo: a pergunta mostra exatamente aquilo de que
a decisão depende, e nada além.** Refinamento pedido pelo dono em 2026-08-10, ao ler a
primeira versão deste item: *"seria interessante me mostrar quais são os 5 critérios"*.
Sem isso, dizer "os 5 critérios estão ausentes" obriga a abrir o card para saber o que
se está decidindo — o atrito volta inteiro, só que uma camada abaixo.

A regra que sai daí:

- **Quando a recomendação é fechar**, uma linha basta — o dono só confirma:
  *"WEGO-1436 (`POST /upload`): o endpoint existe em `PlugSignAdapter:253`, com
  cobertura mock e vendor-drift. Fecho? Recomendo sim."*
- **Quando a recomendação é manter aberto**, o motivo É a lista — cada critério com o
  estado verificado e o lugar onde foi conferido:

  > **WEGO-1437 (`POST /send-request`) — manter aberto. Recomendo sim.**
  > Os 5 critérios que você escreveu em 2026-08-03 (comentário 36883, na reabertura
  > depois do proof gate reprovar em 07-30). Verificados no código em 2026-08-04, HEAD
  > `018b1b1c` — nenhum atendido:
  >
  > 1. *"Data de nascimento passa a ser invariante obrigatória do signatário, no mesmo
  >    nível do CPF (`PlugSignPort.Signatario`), com mensagem de erro equivalente."*
  >    → ausente: `PlugSignPort.java:201-226` ainda documenta "dataNascimento e
  >    mensagem são opcionais".
  > 2. *"Os caminhos que hoje toleram data de nascimento ausente são tratados: os
  >    fallbacks best-effort a partir do Atendimento em
  >    `SolicitarAssinaturaService.java:684,696,762,770` precisam falhar de forma
  >    explícita quando o dado não existe, em vez de seguir com nulo. Avaliar o impacto
  >    sobre pedidos que hoje passam sem o dado e escalar ao dono se houver volume
  >    relevante."* → ausente: os 4 fallbacks seguem passando nulo adiante; o ramo
  >    MÉDICO (`:717-718`) já falha explícito e é o padrão a replicar.
  > 3. *"`allow_birth_date` no payload da PlugSign deixa de ser condicional à presença
  >    do campo."* → ausente: segue condicional em `PlugSignAdapter.java:984,1010,1018`.
  > 4. *"O ramo PRESTADOR → `signature_type = "Contratado"` passa a ser afirmado por
  >    teste."* → ausente: o ramo existe em `PlugSignAdapter.java:1021`, mas há zero
  >    ocorrências de "Contratado" em arquivos de teste.
  > 5. *"Cobertura E2E (@QuarkusTest + RestAssured/WireMock): pedido sem data de
  >    nascimento é recusado, e o payload efetivamente enviado à PlugSign carrega
  >    `birthdate` e o `signature_type` correto por papel."* → ausente.

Repare que os critérios 4 e 5 são de **cobertura**, não de implementação — o código do
ramo PRESTADOR já existe. Foi exatamente essa distinção que derrubou o card em
2026-07-30: perturbar `PlugSignAdapter.java` manteve os testes verdes porque o contract
test só instancia `PapelSignatario.PACIENTE`. Uma pergunta que dissesse apenas "está
implementado?" teria recebido "sim" e estaria errada.

Custo aceito: uma pergunta dessas é longa. Por isso o detalhe só aparece no ramo
"manter aberto", que é a minoria — no WEGO-1406, 12 das 22 filhas são operacionais e
cabem em uma linha cada.

O caso WEGO-1406 é o teste de aceitação natural desta parte: 22 filhas abertas, 12 de
operação e 10 de desenvolvimento, e o dono conseguindo despachar todas numa sentada.

**5. Fila própria para defeito do harness.** O que trava o fluxo por culpa da
ferramenta vira item deste BACKLOG automaticamente, e não uma tarefa apresentada ao
dono no meio de um card de produto.

### O que NÃO some, e é honesto dizer

Decisão de produto e atestado sobre o que vive fora do código continuam sendo do dono.
O ganho não é eliminá-los: é que passem a chegar **agrupados, uma vez por rodada, com
recomendação e default**, em vez de pingados no meio do trabalho.

### Peça que já existe

O `board-flow:decide` já faz exatamente a forma desejada — agrupa a coluna Review por
motivo e faz uma pergunta fechada por grupo, respondida em lote. O que falta é (a)
estender essa forma ao resto do fluxo, (b) parar de perguntar o que é reversível, e
(c) o modo por sub-task do item 4.

### Direção escolhida (2026-08-15) — via piloto Gauntlet Loop nº2

Design completo em `docs/internals/gauntlet-pilot-atrito-decisao.md` (3 designs
concorrentes escritos por agentes isolados, julgados às cegas por 3 avaliadores contra
uma barra de qualidade escrita antes; os 3 avaliadores escolheram o mesmo vencedor, e a
versão final incorporou as melhores ideias dos dois perdedores). O escolhido foi o que
estende as peças que o harness já tem, em vez de criar estruturas novas. Quatro peças:

1. **`common/autonomy.yaml` — a lista do que o agente faz sem perguntar.** Um arquivo
   de configuração versionado com duas listas: ações que o agente executa e apenas
   reporta (rodar build, commit local, criar card, apagar branch já mesclada, apagar
   handoff vencido, atualizar plano — as ~10 que o dono só carimbava com "sim"), e
   ações que sempre esperam pergunta (push, merge em branch de integração, descartar
   trabalho, fechar card em definitivo, qualquer coisa com segredo ou terceiros). Cada
   ação da lista carrega um campo `detect:` — a "impressão digital" da ação: o padrão
   do comando de terminal ou o nome da ferramenta que a realiza — para que um hook
   (script que o Claude Code roda automaticamente antes de cada ferramenta) reconheça a
   ação mecanicamente, sem depender do julgamento do agente no turno. Quando a
   permissão depende de uma condição ("apagar branch SÓ SE já estiver mesclada"), quem
   verifica a condição é o próprio hook, rodando o comando git de conferência. Ação que
   não está em lista nenhuma: pergunta, sempre.
2. **`ask-audit-gate.py` — pergunta só sai auditada.** Um hook que intercepta o momento
   em que o agente vai fazer uma pergunta ao dono e a barra se faltar o dever de casa:
   pergunta sobre card que tem sub-cards precisa vir com todos os sub-cards enumerados
   e o status de cada um; pergunta que cita `arquivo:linha` precisa da linha conferida
   no disco. Isso torna irrepetível o caso do Epic WEGO-1406 (o dono aprovou fechar
   vendo 15 cards, quando havia 41 sub-cards, 22 abertos). **Depende de um spike de 30
   min:** confirmar que o Claude Code dispara hooks para a ferramenta de perguntas
   (AskUserQuestion); se não disparar, o plano B é embutir a exigência no comando que
   monta a pergunta.
3. **`.claude/attestations.yaml` — o que o dono afirma vira registro.** Quando o dono
   atesta algo que não está no código ("o SMTP está configurado no painel", "esse
   pacote está concluído"), a afirmação vira um fato datado e com escopo num arquivo
   durável. Os comandos de triagem e decisão leem o arquivo antes de agir; se o código
   contradisser um atestado, a contradição é apresentada ao dono — nunca resolvida em
   silêncio por nenhum dos lados (foi o descompasso de 08-03/08-04 no caso PlugSign).
4. **Modo por sub-task e fila de defeitos** — os itens 4 e 5 do esboço acima entram
   como estão: pergunta fechada por sub-card quando o Epic é indecidível, e defeito do
   harness vira item deste BACKLOG em vez de interrupção.

Gaps a fechar na implementação (lista completa no doc): o spike do hook de perguntas;
incluir `.claude/decisions/` e `attestations.yaml` na lista de resgate do
worktree-artifact-rescue (são arquivos ignorados sob `.claude/`, a classe que some
calada quando um worktree é removido); completar o mapa de ferramentas Jira nos campos
`detect:` (edição trivial de card hoje cairia em "pergunta sempre").

**Implementação da Fase 1 aprovada pelo dono em 2026-08-15** (o `autonomy.yaml` + a
extensão do `decide`), começando pelo spike de 30 min, para uma próxima sessão de
build.

---

## O plano de execução morre com o worktree, e o nome do programa colide

**Status:** camada 0 FEITA em 2026-08-18 (ver "Camadas propostas" abaixo); a colisão
de NOME de programa segue pendente · **Lar provável:** `common`
(`plan-schema.yaml`, `/common:next`)
+ `maestro` (`program-plan`, `run`, `resume`) · **Origem:** sessão de 2026-08-10, a
partir do relato de uma sessão do WEGO: *"O plano desta sessão morre com o worktree. O
`plan.yaml` que escrevi vive em `.claude/`, que o repositório ignora, e o `.claude/`
deste worktree some quando ele for removido. E o worktree do main tem outro plano para
o mesmo programa WEGO."*

### Problema

Verificado em disco em 2026-08-10, no `wego-assinatura-backend`: existem **três**
`plan.yaml`, todos com o nome de programa `WEGO`, todos não-rastreados, e todos com
escopos diferentes.

| onde | escopo declarado no `source:` | itens |
|---|---|---|
| worktree do main | To Do, triado 29/07 e de novo 04/08 (15 de 171) | 19 |
| `session/todo` | To Do, triado 03/08 | 3 |
| `session/in_review` | follow-ups de In Review, 03/08 | 10 |

São dois defeitos distintos que se somaram:

**1. O arquivo mora no lugar errado.** O `.gitignore:79` do wego ignora `.claude`
inteiro — é regra do time, não do dono do harness. Então lá o plano nunca teve chance
de ser versionado, e um plano escrito dentro de um worktree de sessão desaparece no
`worktree-merge` levando junto a ordem e o porquê. Os 13 itens priorizados de
`session/todo` e `session/in_review` estão nessa situação agora.

No `cepa` o mesmo padrão parece funcionar: `.claude/programs/**` está rastreado de
propósito, com comentário no `.gitignore` dizendo isso. Mas o `cepa` tem **um worktree
só** — o arranjo nunca foi exposto a paralelismo. Ele não resolve o problema, apenas
ainda não o encontrou.

**2. O nome do programa é o projeto, não a fatia de trabalho.** Os três arquivos não
são cópias divergentes de um mesmo plano: são três recortes distintos que receberam o
mesmo nome. E isso não foi descuido das sessões — a regra 2 de resolução do
`/common:next` (`common/commands/next.md:53`) manda usar
`.claude/programs/<project_key>/plan.yaml` quando existe `board-flow.yaml`. A convenção
manda chamar de `WEGO`. Toda triagem futura colide com a anterior mesmo depois de
resolvido o lugar do arquivo.

### Esboço de solução

**Um arquivo físico por programa, sempre no worktree principal.** Todo worktree —
inclusive os efêmeros — resolve o mesmo caminho com uma linha, sem configuração e sem
symlink:

```sh
dirname $(git rev-parse --path-format=absolute --git-common-dir)
```

Verificado em 2026-08-10: de `session/todo` isso devolve o worktree principal do wego;
do `cepa` devolve o `cepa`.

Por que essa e não as outras:

- **Sobrevive.** O worktree principal não é removido pelo `worktree-merge` nem pelo
  `wrap-up`. O plano morre com o clone, não com a sessão.
- **Não pode divergir.** Não existe "o plano do meu worktree" — existe um arquivo.
  Escrita de status vai direto nele, sem branch e sem merge no caminho.
- **Independe de o repo permitir versionar.** No `cepa` fica exatamente onde já está e
  continua rastreado, migração zero. No wego continua ignorado pelo `.gitignore` do
  time e mesmo assim durável. Mesma mecânica nos dois, sem negociar `.gitignore` alheio
  nem usar `git add -f` brigando com a regra para sempre.

Descartadas, com o motivo:

- *Cada worktree com seu plano* — é o estado atual, e é o defeito.
- *Na main, versionado, atualizado por branch* — transforma cada `status: done` em
  commit numa branch de sessão mais um merge, e conflita por construção quando duas
  sessões fecham itens diferentes do mesmo plano. É o custo sem o benefício: a história
  de um item concluído não vale um conflito de YAML.
- *Fora do repo (`~/.claude/programs/<repo>/`)* — resolve durabilidade mas separa o
  plano do clone e quebra com dois clones do mesmo repo (o dono tem: `~/coding/wego` e
  o do Insync).

**Distinção a fixar junto:** `plan.yaml` é a fila + ordem + porquê, compartilhado, vai
para o worktree principal. O `wave-state.yaml` do Maestro é estado **de um run** — esse
pode e deve morrer com o run. Nada muda para ele.

**Nome de programa = fatia de trabalho**, não project key: `wego-todo-agosto`,
`wego-review-followups`. Exige corrigir a regra 2 do `/common:next`.

**Metade que a camada 0 NÃO fecha, e a evidência de 2026-08-18.** Ancorar o caminho na
raiz principal resolve *onde* o plano mora; não resolve *quantos planos com nome
parecido* disputam a mesma fila. No `wego-acesso-backend`, hoje, o clone principal tem
os dois ao mesmo tempo:

| programa | escopo | itens |
|---|---|---|
| `.claude/programs/WEGO/` | fila To Do, triada 16/08 (e a fusão de 18/08, 48 itens) | 47–48 |
| `.claude/programs/WEGO-in-progress/` | recorte de In Progress, 16/08 | — |

Com a âncora no lugar, a regra 3 do `/common:next` ("exatamente um `plan.yaml`
single-track → esse") passa a achar DOIS e cair na regra 4, que pergunta ao dono qual
usar — toda vez, para sempre. É o sintoma do nome: `WEGO` e `WEGO-in-progress` não são
dois programas, são duas fatias do mesmo, e o project key não distingue fatia. A
regra 2 (project key → programa) é justamente a que precisa sair.

### Superfícies a tocar

`common/plan-schema.yaml` (documentar o lugar canônico), `common/commands/next.md`
(resolução de caminho + regra 2), `maestro/commands/program-plan.md`,
`maestro/commands/run.md`, `maestro/commands/resume.md`, `docs/execution-plan.md`.

### Dívida imediata, independente do código

Consolidar os três `plan.yaml` do wego em três programas de nomes distintos no worktree
principal. Os de `session/todo` e `session/in_review` somem no próximo merge e levam 13
itens priorizados junto.

### Por que ele evaporou sem aviso — mecanismo verificado em 2026-08-10

O gatilho relatado pelo dono foi fechar o herdr e o Ghostty. Ou seja: quem removeu o
worktree não foi um comando digitado, foi o caminho automático. São dois, os dois com
o mesmo furo:

- `common/hooks/session-registry.py:256` — `do_prune_on_exit`, o reap diferido que o
  `/common:wrap-up` agenda por marcador (ele não pode remover o worktree em que está
  de pé).
- `common/hooks/_wtlib.py:413` — `auto_clean`, que varre worktrees não-vivos, limpos e
  sem commits pendentes.

**O furo é arquivo ignorado, e ele é invisível para todas as camadas de proteção que
existem hoje.** Verificado com dois repos de teste montados para isso:

| arquivo solto no worktree | `git status --porcelain` | `git worktree remove` sem `--force` |
|---|---|---|
| não-rastreado e **não** ignorado | `?? solto.txt` | **recusa**, `rc=128`, arquivo sobrevive |
| não-rastreado e **ignorado** | vazio | **remove calado**, `rc=0`, arquivo morre |

No `wego-assinatura-backend` o `.gitignore:79` ignora `.claude` inteiro, então o plano
caiu na segunda linha. E as três defesas falharam em cascata, todas pelo mesmo motivo:

1. `is_dirty()` (`_wtlib.py:143`) usa `git status --porcelain`, que **não lista
   ignorados** → o worktree parecia limpo.
2. O WIP-autosave de `on_end` (`session-registry.py:280`) só dispara se `is_dirty` →
   não disparou.
3. O guard do próprio git não viu nada para barrar → `rc=0`, sem sequer chegar ao
   fallback `--force`.

Corolário importante: **tirar o `--force` não teria salvado nada**. O fallback
`rc != 0 → --force` (`session-registry.py:258`, `_wtlib.py:415`) é um furo separado e
real — ele converte a recusa do git em destruição silenciosa no caso não-ignorado — mas
não é o que aconteceu aqui.

Segundo corolário: a rede **precisa morar no hook**, não nos comandos
`worktree-merge` / `worktree-discard` / `wrap-up`. Nenhum deles rodou nessa perda.

### Camadas propostas

**Camada 0 — prevenção, e é a que resolve este caso.** O `plan.yaml` nunca é escrito
dentro de um worktree de sessão (a solução principal deste item). Fim do problema para
o plano.

**FEITA em 2026-08-18.** Todo comando que lê ou escreve plano resolve o caminho como
`<raiz-principal>/.claude/programs/...`, com `<raiz-principal>` = pai de
`git rev-parse --git-common-dir` sem o `/.git` final: `/common:next`,
`/board-flow:{triage,execute,fix,prove}` e `/maestro:{run,program-plan,resume}`. A
regra canônica está em `docs/execution-plan.md` ("Where the file lives"), com os DOIS
modos de perda nomeados — escrever na worktree (perde alto) e copiar por worktree via
seeding (perde calado, que foi o que quase aconteceu ao "restaurar" o resgate de
18/08: 14 itens por cima de 47). Guard mecânico em `tests/test_plan_anchor_root.py`,
inclusive uma varredura que barra qualquer `.claude/programs` sem prefixo de raiz nos
8 comandos; 4 perturbações RED, uma por guarda.

O `/common:next` ganhou junto o passo que faltava na LEITURA: antes de declarar "não
há plano", olha `<raiz-principal>/.claude/programs/` e
`<raiz-principal>/.claude/rescued/*/programs/*/plan.yaml`, e proíbe sobrescrever o
plano vivo com o resgatado. Origem: em 18/08 uma sessão declarou morto um plano que
estava no clone principal.

**Camada 1 — resgate antes de remover, para todo o resto.** A camada 0 só cobre o
plano. Tudo o mais que o harness escreve num `.claude/` ignorado tem exatamente o mesmo
furo: `.claude/proof/<KEY>.yaml` do proof gate, `.claude/acceptance/<KEY>.yaml` do
completion-auditor, e os handoffs (ignorados de propósito até no `.gitignore` do
próprio cepa). Antes de qualquer `worktree remove`, enumerar com
`git status --porcelain --ignored` o que morre sob `.claude/**`, descontar o efêmero
conhecido (`last-build.json`, `session-log.md`, `sessions/`) e copiar o resto para o
worktree principal — reportando o que foi resgatado. Um helper só em `_wtlib.py`,
chamado pelos dois caminhos automáticos e pelos três comandos.

**Camada 2 — nunca forçar às cegas.** Com a camada 1 no lugar, o fallback `--force`
deixa de destruir o que não foi resgatado.

Ordem de valor: a 0 resolve a perda que aconteceu; a 1 é a que impede a próxima, que
vai ser com um artefato de prova em vez de um plano.

**⚠ CONFIRMADO em 2026-08-16 — a camada 1 não cobre dois dos três comandos, e o furo
já comeu um worktree no primeiro dia.** O caso: no `wego-acesso-backend`, o worktree
de sessão `triage-16081131` (com o `plan.yaml` de 47 itens da triagem do dia, ignorado
sob `.claude/`) foi removido às 19:50 por um merge de outra sessão (reflog do main:
`merge session/triage-16081131`), e nenhum `.claude/rescued/` apareceu no principal.
O plano sobreviveu por duas redes manuais e independentes: uma cópia feita por esta
sessão às 18:25, e a própria sessão do wego, que percebeu a perda e versionou um
retrato fora do `.claude/` (commits `65147f0`, `99c84d6`, `ffd79ce` de lá).

O mecanismo, verificado no código:

- `session-registry.py:267/273` — `do_prune_on_exit` chama `rescue_artifacts` nas
  duas pernas. O caminho diferido do `/common:wrap-up` (marcador `.prune-on-exit`)
  desagua aqui → **protegido**. `auto_clean` idem.
- `common/commands/worktree-merge.md:89` — passo 7 manda `git worktree remove` cru
  → **desprotegido**. Foi este o caminho da perda de 19:50.
- `common/commands/worktree-discard.md:42` — `git worktree remove --force` cru →
  **desprotegido**, e com `--force` (pior: nem a recusa do git para não-ignorados).

Ou seja: o desenho da camada 1 dizia "dois caminhos automáticos E três comandos"; o
construído (`e3a8bc5`) cobriu só os automáticos.

**CONSTRUÍDO em 2026-08-17 (`1a9017a`, common 0.27.1):** `_wtlib.py` ganhou o modo de
linha de comando `python3 _wtlib.py rescue <worktree> [<branch>]` (deriva o worktree
principal sozinho e recusa rodar no principal), e os passos de remoção de
`worktree-merge.md` e `worktree-discard.md` o chamam ANTES do `git worktree remove`.
Suíte de 21 → 25 checks; perturbação: sem o CLI, 4 ficam vermelhos. **Não live até
`bin/install.sh`** — até lá, merge/discard manuais seguem furados.

## O `bash-path-lock` bloqueia `cp`, mas deixa passar a mesma escrita via `python3 -c`

Encontrado em 2026-08-13, durante WEGO-1936 no `wego-acesso-backend`, e reportado pelo
próprio agente que contornou o cadeado — não por auditoria.

O `qa-engineer` do `build-hex` precisava provar RED revertendo temporariamente um arquivo
de `src/main`, que está fora do glob de escrita dele. O hook `bash-path-lock` barrou o
`cp`. Ele então fez a **mesma escrita, no mesmo caminho**, com
`python3 -c "open(p,'w').write(...)"` — e passou.

O conteúdo final ficou correto (ele restaurou o arquivo, o `diff` confirma, o build fechou
verde), então este item não é sobre aquele card. É sobre o cadeado.

**Por que importa mais do que parece.** O path-lock não existe para impedir estrago: existe
para **forçar a delegação** entre agentes — o QA não escreve produção, ele devolve o achado
para o dev worker. Um cadeado contornável com uma linha de Python não força nada; ele só
seleciona os agentes que não pensaram no contorno. E o modo de falha é silencioso: quem lê
o relatório vê "hook barrou, segui por outro caminho" como esperteza, não como violação.

**O que o hook inspeciona hoje** é o texto do comando procurando os utilitários de escrita
conhecidos (`cp`, `mv`, `tee`, redirecionamento). Qualquer interpretador — `python3 -c`,
`perl -e`, `node -e`, um heredoc para `sh` — é escrita arbitrária que não se parece com
escrita.

**Direções possíveis, nenhuma óbvia:**

1. Negar por omissão: interpretador com código inline (`-c`/`-e`) vira comando bloqueado
   para agentes com path-lock ativo, e quem precisa de verdade pede exceção explícita.
   Simples, e provavelmente irritante em casos legítimos.
2. Tratar o path-lock como o que ele é — uma convenção entre agentes — e mover a garantia
   para onde ela é verificável: o `code-reviewer` compara o diff final contra os globs de
   quem disse ter escrito o quê. Não impede, mas detecta, e detecta o caso que importa.
3. Aceitar o furo e documentá-lo, deixando o cadeado como lembrete e não como barreira.
   Honesto, e pior do que parece: um cadeado que se sabe falso corrói a confiança nos
   outros hooks.

A (2) é a que casa com o resto do desenho, porque o harness já aposta em portões
independentes verificando o trabalho em vez de confiar no auto-relato do executor.

**Registro do caso concreto:** a perturbação em si era legítima e necessária (provar que o
teste fica vermelho sem a correção). O problema não foi o que ele fez, foi o cadeado ter
dito "não" e não ter significado nada.

---

## `/common:gauntlet` — competição de designs com julgamento cego

**Status:** pendente (aprovado para cristalizar em 2026-08-15, após 2 pilotos) ·
**Lar provável:** `common` · **Origem:** pergunta do dono "how can we add Gauntlet Loop
abilities into Cepa?" (2026-08-14) + 2 pilotos rodados via tool Workflow em 2026-08-15.

### O que é

Gauntlet Loop é uma técnica de orquestração (de Matt Shumer): em vez de UMA tentativa
verificada, várias tentativas COMPETEM e um julgamento cego escolhe. O fluxo, como
validado nos pilotos:

1. **Barra antes de tudo** — um agente escreve os critérios de qualidade (5-8, cada um
   com rubrica de nota) e uma "referência inatingível" que dá direção, ANTES de
   qualquer design existir.
2. **Builders concorrentes** — 3 agentes isolados (não veem uns aos outros), cada um
   com um ângulo distinto (ex.: prevenção / estender-o-que-existe / livre), produzem
   designs completos lendo o repo de verdade.
3. **Juízes cegos** — 3 agentes de contexto limpo recebem SÓ objetivo + barra + designs
   anonimizados (rotulados A/B/C, ordem rodada por juiz), dão nota por critério,
   ranqueiam e nomeiam o maior gap de cada design. Vencedor por contagem de Borda
   (1º lugar = 3 pontos, 2º = 2, 3º = 1, somado entre juízes).
4. **Revisão** — o vencedor é revisado fechando os gaps apontados e enxertando as
   melhores ideias dos perdedores (com crédito).
5. **Checagem final** — um crítico fresco confere se a barra foi atingida, verificando
   as citações de código NO DISCO.

### Evidência dos 2 pilotos (por que cristalizar)

- Piloto 1 (furo do bash-path-lock): `docs/internals/gauntlet-pilot-bash-path-lock.md`.
- Piloto 2 (atrito de decisão): `docs/internals/gauntlet-pilot-atrito-decisao.md`.
- Nos dois: juízes **unânimes** no vencedor; barra atingida na primeira revisão; e o
  design final foi uma **síntese** (vencedor + enxerto de rival) que nenhum builder
  produziu sozinho — o valor não é só best-of-3, é o julgamento comparativo forçando
  a mesma fratura a aparecer em 3 avaliações independentes.
- Custo real: ~600k tokens e ~13 min por rodada (9 agentes). Por isso é opt-in.

### Quando usar / não usar

- **Usar:** decisão de design aberta e julgável em texto ("nenhuma direção é óbvia"),
  naming, prosa estratégica, arquitetura. O ganho vem da variância entre tentativas.
- **Não usar:** trabalho provável (código com teste — o proof gate já domina), fix
  pontual, tarefa mecânica. Nem como default de nada: ~600k tokens por uso.

### Esboço de entrega

1. Comando `common:gauntlet <alvo> [--builders=3] [--angulos=a,b,c]` que monta e lança
   o script de Workflow (o template validado está nos 2 scripts dos pilotos, em
   `~/.claude/projects/.../workflows/scripts/gauntlet-pilot-*.js` — copiar o canônico
   para `common/` antes que evaporem).
2. Saída durável padrão: `docs/internals/gauntlet-<slug>.md` (barra, designs,
   vereditos, design final, gaps) — nunca só no resultado efêmero do task.
3. Relatório final em pt-BR leigo, com a recomendação e as perguntas fechadas.

### Pendências de design

- Onde mora o script canônico (arquivo em `common/` que o comando parametriza vs.
  gerar o script a cada invocação).
- Como o usuário declara os ângulos dos builders (default validado:
  mecanismo-novo / estender-o-que-existe / livre) — parente do registry de lentes do
  item Advisors.
- Relação com `/common:advisors`: advisors julga UM artefato por N lentes; gauntlet
  GERA N artefatos e julga comparativamente. São complementares (advisors pode ser a
  fase de julgamento de um gauntlet?) — decidir se compartilham registry.
- A tarefa entra como argumento livre ou aponta para um item do BACKLOG (os 2 pilotos
  usaram itens do BACKLOG e funcionou bem como âncora de contexto).

### Direção escolhida (2026-08-15) — via piloto Gauntlet Loop

Design completo em `docs/internals/gauntlet-pilot-bash-path-lock.md` (barra pré-declarada,
3 designs concorrentes, 3 juízes cegos unânimes, revisão, barra atingida na checagem final).
O escolhido combina as direções 1 e 2 do esboço acima em três camadas:

1. **Camada 1 — prevenção default (dia 1):** classificador deny-by-default de "quatro
   baldes" no próprio `bash-path-lock.py` (5 cópias): todo comando de agente trancado ou é
   escritor analisável (alvo vs. globs), ou verbo sabidamente inofensivo (lista de
   inocentes, com deny-list de flags), ou está fora da jurisdição do repo (carve-out
   out-of-root intacto), ou é **negado**. Interpretador inline e vetores não listados caem
   no deny por construção. Perturbação RED legítima ganha caminho oficial: worktree
   descartável fora da raiz.
2. **Camada 2 — write-fence por diff:** detecção pós-fato independente do vetor, com
   contorno virando evento no ledger de telemetria (consumidor: `/common:metrics`).
3. **Camada 3 — sandbox de SO:** endurecimento opcional; nada depende dele.

Gaps conhecidos a fechar na implementação (lista completa no doc): `$(...)`/backtick em
argumento de verbo seguro; teste anti-drift das 5 cópias precisa derivar `PLUGIN_NAME` do
path; atribuição `VAR=$(mktemp -d)` na receita canônica do worktree.

**Implementação da camada 1 aprovada pelo dono em 2026-08-15** para uma próxima sessão de
build (estimativa: 1-2 sessões, testes nos moldes de `tests/test_bash_path_lock_redir.py`
varrendo as 5 cópias).

---

## O guard de dono único mora no comando, e `git worktree remove` cru passa por fora

**Status:** pendente · **Lar provável:** `common` (hook + `worktree-guard.py`)
· **Origem:** incidente no `wego-acesso-backend` em 2026-08-17, ~11:37 — uma sessão
removeu o worktree de OUTRA sessão que estava viva dentro dele.

### Problema

O `worktree-guard.py` responde exatamente à pergunta certa ("alguma sessão viva
segura este branch?") e responde bem: no mesmo dia ele barrou, corretamente, um
merge de `session/exec_16082013` feito de outra janela. Mas ele só é chamado de
dois lugares, ambos markdown de comando (`worktree-merge.md:52`,
`wrap-up.md:165`). **Nada o chama quando o agente usa git direto.**

Foi o que aconteceu. Uma sessão em `exec_17081128`, fazendo faxina antes de
começar o próprio trabalho, verificou que o branch vizinho já estava mesclado na
`main` e rodou:

```
git worktree remove /Users/.../wego-acesso-backend-prove_18080827 \
  && git branch -D session/prove_18080827
```

O worktree tinha uma sessão viva (PID ativo, `last_seen` de segundos antes). O
guard teria bloqueado; nunca foi consultado. Consequências observadas:

1. **A sessão vítima perdeu o chão.** Todo hook passou a falhar com
   `ENOENT: no such file or directory, posix_spawn '/bin/sh'` — mensagem que
   culpa o `/bin/sh` (que existe) quando o que sumiu foi o cwd. Custou uma
   pergunta do dono só para decifrar.
2. **Nenhum resgate de artefatos rodou** — git cru não passa por
   `rescue_artifacts`, então os cinco `.claude/proof/<KEY>.yaml` e o
   `.claude/waivers/*.yaml` daquela sessão teriam evaporado. Sobreviveram por
   acaso: tinham sido copiados para `docs/` e empurrados 6 minutos antes.
3. **`branch -D`, não `-d`.** Seis minutos mais cedo, o mesmo comando teria
   apagado um commit não mesclado sem aviso.

Note que este é o **mesmo princípio** já reconhecido no item "O plano de execução
morre com o worktree" ("a rede **precisa morar no hook**, não nos comandos"), e a
**mesma forma** do item do `bash-path-lock` (guard real, contornado por outra
rota que faz a mesma coisa). O que muda é o vetor: lá é escrita de arquivo, aqui
é destruição de worktree alheio.

### Esboço de solução

**Camada 1 — `PreToolUse` em `Bash` que reconheça o verbo destrutivo.** Casar
`git worktree remove` e `git branch -D/-d` no comando, extrair o alvo (path ou
branch), rodar a lógica de `worktree-guard.py` e **bloquear** quando houver
sessão viva no branch/worktree alvo, com mensagem apontando
`/common:worktree-merge` / `/common:worktree-discard`. Precisa tolerar as formas
que o incidente exibiu: `&&` encadeado, path absoluto no lugar do nome do slice.

**Camada 2 — resgate no vetor cru também.** Se o bloqueio for contornado ou
liberado, ainda assim enumerar e resgatar os `.claude/` ignorados antes de
deixar passar (reaproveita `rescue_artifacts`, já usado pelos dois caminhos
automáticos desde 0.27.1).

**Camada 3 — disciplina, barata e imediata.** Uma linha no skill de worktrees:
worktree de outra janela não é sua para aterrissar; se está mesclado e incomoda,
o dono decide. Isso não substitui a camada 1 — o incidente mostra que um agente
competente escolhe o atalho quando ele parece equivalente —, mas cobre enquanto
o hook não existe.

### Diagnóstico que fecha esse tipo de investigação em um comando

`ls .claude/rescued/` no worktree principal. Os dois caminhos automáticos
(`auto_clean` no início de sessão, `do_prune_on_exit` no fim) sempre resgatam
antes de remover. **Worktree removido + `.claude/rescued/` inexistente = não foi
o harness.** Sinais confirmatórios: `.claude/sessions/` com mtime anterior à
remoção (ninguém iniciou sessão, logo `auto_clean` não rodou), ausência de
marcador `*.prune-on-exit`, e `.git/worktrees/<nome>` também removido (apagar a
pasta na mão deixaria esse resto).

---

# Achados da revisão profunda do harness (2026-08-17)

Os quatro itens abaixo saíram de `docs/internals/harness-review-2026-08.md` —
revisão da Cepa como sistema agêntico, pedida pelo dono. São os achados que
**não tinham item existente**; os demais já moram no BACKLOG (bash-path-lock
camada 1, atrito de decisão, `/common:gauntlet`). Aprovados pelo dono em
17/08 para entrar no backlog E começar a execução na mesma sessão.

---

## O aviso de versão só existe se alguém rodar o doctor (P0-4 da revisão)

**Status:** CONSTRUÍDO 2026-08-17 (`1738aa8`, common 0.28.0) · **Lar:** `common/hooks/_pluginver.py` + `session-registry.py`
· **Origem:** revisão 2026-08-17, §7 gargalo nº 5.

### Problema

A falha mais recorrente da história do projeto não é técnica, é epistêmica:
**um conserto é commitado, não é instalado, e todo mundo — dono e agente —
segue operando como se estivesse valendo.** A memória do projeto tem pelo menos
seis itens marcados "FIXED, not live until reinstall", e no dia da própria
revisão o `common` 0.27.1 (resgate de artefatos nos comandos de worktree)
estava nessa situação: consertado no repo, ausente na máquina, com dados
realmente em risco no intervalo.

Existe hoje um detector correto — o `check_plugins` do `cepa-doctor`
(`common/bin/cepa-doctor:151-184`) compara a versão de cada `plugin.json` do
repo contra a maior versão no cache e avisa "edições não valem". Mas ele **só
fala quando alguém decide perguntar**. O gargalo não é a detecção; é o gatilho
ser voluntário, justamente na situação em que ninguém suspeita de nada.

### Esboço de solução

Mover a pergunta para o único momento em que ela é sempre feita: o
`SessionStart`. O `session-registry.py` já roda ali e já injeta contexto
(`emit_context`) para o handoff. Adicionar uma linha — e só uma linha — quando
e somente quando houver divergência: qual plugin, repo em X, cache em Y, e a
frase que importa, *o que não está valendo agora*.

Cuidados que o desenho precisa respeitar:

- **Barato e fail-silent.** É um hook de boot; ler N `plugin.json` + listar
  diretórios do cache é aceitável, qualquer exceção é engolida. Um check que
  atrasa ou quebra o boot será desligado, e aí não protege nada.
- **Silêncio quando está tudo certo.** Aviso que aparece toda sessão vira
  ruído e treina o olho a pular. Só fala na divergência.
- **Não é o doctor.** O doctor continua sendo o diagnóstico completo; isto é
  o alarme de um sinal só, o que sobra depois de tirar tudo que pode esperar.
- Reaproveitar a lógica do doctor em vez de reimplementar (senão nasce a
  segunda cópia do comparador, que é a mesma doença do item dos locks).

---

## O path-lock existe em 5 cópias, e a correção depende de disciplina (P0-3)

**Status:** CONSTRUÍDO 2026-08-17/18 (`aeaaa16` detector + `bin/gen-locks.py`
gerador) · **Lar:** `tests/test_lock_copies_drift.py` +
`common/hooks/_templates/bash-path-lock.py.tmpl` + `bin/gen-locks.py`

**Desvio do esboço, com o motivo:** a geração NÃO foi para dentro do
`bin/install.sh`. Ela roda em tempo de desenvolvimento (`--write`) e o `--check`
entra na suíte de testes. Assim o repositório continua auto-contido — as cópias
estão commitadas e funcionam instaladas por qualquer via — e nenhuma
complexidade nova entra no instalador. O invariante ("as 5 saem de um lugar só")
é o mesmo; o risco é menor.

**E o `path-lock.py` segue NÃO gerado, de propósito:** ele carrega o
`ALLOWED_WRITES`, que é dado da topologia e precisa morar perto dos agentes que
governa, para alguém conferir contra o `Writes:` de cada um. Ali a garantia
continua sendo o detector. · **Origem:** revisão 2026-08-17, §17 e §22.

### Problema

`path-lock.py` e `bash-path-lock.py` existem em cinco cópias, uma por topologia
com hook (`build-team`, `build-hex`, `discovery`, `design`, `docs-topology`).
A regra hoje é humana: "todo fix aterrissa nas 5 cópias". Ela já falhou —
o conserto do falso-positivo `>=` (bash-path-lock lia o `>` de `>=` como
redirecionamento e bloqueava comandos legítimos) precisou ser propagado à mão,
e a memória do projeto registra o episódio em que uma cópia ficou para trás.

O agravante é o assunto: estes são **os dois hooks que sustentam a garantia
central do produto** (workers escrevem só na própria pista, leads delegam em
vez de codar). Uma cópia defasada não falha ruidosamente — ela simplesmente
permite o que as outras quatro bloqueiam, e o relatório do agente lê como
sucesso.

Medição de 2026-08-17: as 4 cópias não-hex do `bash-path-lock` são idênticas a
menos de três substituições (`PLUGIN_NAME`, o caminho do log de cobertura, o
nome do módulo importado); a de `build-hex` difere **apenas na prosa do
docstring**. Já o `path-lock.py` diverge de verdade: `build-hex` tem 442 linhas
contra 146–188 das outras, porque carrega o leitor de `build-hex.yaml` que
remapeia papéis arquiteturais para nomes de módulo. Ou seja: o motor é comum, a
configuração é que é própria.

### Esboço de solução

Separar **motor** de **descritor**:

- O motor (identificação do agente chamador, checagem estrutural do arquivo de
  expertise, casamento de globs, o fluxo do `main`, e no caso do Bash toda a
  extração de alvos de escrita) vira fonte única em `common/hooks/`.
- Cada topologia mantém só o que é dela: `PLUGIN_NAME`, o mapa de globs por
  agente e — no caso do `build-hex` — o carregamento do `build-hex.yaml`.
- Como plugins são independentes no disco (cada um instalado sob sua própria
  versão no cache), o motor precisa estar **fisicamente presente** em cada
  `hooks/`. Logo: geração/cópia no `bin/install.sh`, mais um teste que falha
  quando uma cópia diverge da fonte.

Ordem sugerida pela segurança: **primeiro o detector de divergência** (um teste
que compara as cópias com a fonte e fica vermelho na primeira que sair da
linha), depois a geração. O detector sozinho já mata a classe "4 de 5
consertadas" e não corre o risco de quebrar o enforcement enquanto é escrito.

---

## Os loops de qualidade não têm teto, e o mesmo erro repetido não é detectado (P0-2)

**Status:** CONSTRUÍDO 2026-08-17 (`7f717b3`, common 0.28.0) · **Lar:** `common/hooks/loop-budget.py` +
`build-hex/agents/engineering-lead.md` · **Origem:** revisão 2026-08-17, §14.

### Problema

`engineering-lead.md:23` manda "iterate until each Task is APPROVED", e
`till-done` reforça a disciplina de não parar cedo. Não existe **teto**, nem
detecção de repetição: um card patológico — teste que não passa por um motivo
que o worker não enxerga — pode ciclar dev→qa→dev indefinidamente, com a mesma
falha, consumindo a sessão inteira. O `/board-flow:drain` tem o comportamento
irmão: para no primeiro BLOCKED, mas nada limita quanto um único card gasta
antes de chegar lá.

O ponto sutil: o remédio *não* é afrouxar o `till-done`. Parar cedo continua
sendo o erro mais comum e mais caro. O que falta é a distinção entre **iterar**
(cada volta traz informação nova) e **repetir** (a mesma volta, com o mesmo
vermelho). A segunda não é persistência, é loop — e o sinal de que ela começou
está disponível: o erro é o mesmo.

### Esboço de solução

Duas camadas, na ordem de sempre (mecânica primeiro, prosa depois):

1. **Contador fora do alcance do agente.** Um hook conta as delegações por
   unidade de trabalho e escreve num arquivo de estado; ao cruzar o teto,
   avisa — e, no limite duro, bloqueia com uma mensagem que diz o que fazer
   (declarar BLOCKED com diagnóstico, não tentar de novo). Mesmo padrão do
   `last-build.json`: o agente não escreve o número que o julga.
2. **Regra no prompt do lead**, com o critério explícito: mesma falha duas
   vezes seguidas ⇒ o próximo passo é diagnóstico ou BLOCKED, nunca a terceira
   tentativa idêntica.

Pendências de design: qual é a unidade contada (Task? card? par agente+alvo?),
onde mora o estado (`.claude/`, e portanto entra na lista de resgate do
worktree), o teto default, e como o contador é zerado sem virar botão de
escape trivial.

---

## Não existe modo de saber se uma mudança no harness melhorou alguma coisa (P1-4)

**Status:** CONSTRUÍDO, NUNCA RODADO 2026-08-17 (`bf95d47`) — 3 tarefas
validadas (vermelhas sem agente), nenhum A/B feito · **Lar:** `tests/eval/` · **Origem:** revisão 2026-08-17, §16 — apontado como o elo mais fraco
do sistema inteiro.

### Problema

O harness audita cards, builds e provas, e não sabe **nada sobre si mesmo** em
termos de resultado. O `_telemetry.py` diz isso na primeira linha do próprio
docstring: "Every improvement was anecdotal."

O que existe hoje cobre outras perguntas:

- os testes de contrato de prompt (`test_fio_condutor.py` e irmãos) provam que
  uma frase **continua escrita** no comando — regressão de texto, não de
  comportamento;
- a telemetria conta bloqueios de gate e vereditos — sinal operacional, não
  taxa de sucesso;
- o Gauntlet julga **designs**, antes de existir código, uma vez por decisão.

Nenhum deles responde: *esta mudança no prompt / na orquestração / no
roteamento de modelo fez os agentes terminarem mais tarefas, com menos voltas e
menos tokens?* Enquanto isso não existir, toda evolução do harness — inclusive
as recomendadas na própria revisão — é decidida por intuição, e as regressões
só aparecem quando custam uma tarefa real.

### Esboço de solução

Uma **suíte de tarefas douradas**: 8 a 12 cards já resolvidos, com diff
conhecido e um comando de aceite executável, re-executáveis do zero numa
worktree limpa a partir do commit anterior ao conserto original.

- **Runner** via tool Workflow (a mesma que rodou os dois pilotos Gauntlet —
  técnica já dominada nesta casa), uma tarefa por agente, isoladas.
- **Métricas por tarefa:** passou/não passou pelo `acceptance_cmd`; número de
  invocações de subagente; tokens; bloqueios de gate disparados; intervenções
  humanas necessárias.
- **Uso:** A/B contra uma mudança de harness — mesma suíte, dois estados do
  repo, comparação por número.

Cuidados: a suíte precisa ser barata o bastante para rodar (senão nunca roda) e
honesta o bastante para não virar teatro — tarefa dourada que o harness acerta
sempre não mede nada, e tarefa que ele erra sempre também não. Começar pequeno,
com casos onde o resultado hoje é **conhecido e misto**.

---

## cepa-doctor não enxerga worktree de agente esquecida dentro de um repositório

**Status:** FEITO (common 1.2.0) · **Lar:** `common/bin/cepa-doctor`
(`check_worktree_interna` + `fix_worktree_interna`), teste em
`tests/test_doctor_worktree_interna.py` · **Origem:** sessão de 2026-08-19 no
`wego-acessos-extension`, onde o problema custou dois portões de qualidade para
ser descoberto.

### Problema

O `cepa-doctor` rastreia worktrees `session/*` — as que o `/common:worktree-start` cria,
fora do repo, em `~/cepa-worktrees/`. Ele **não** olha para as worktrees que a ferramenta
de agente do Claude Code cria em `.claude/worktrees/agent-<id>`, **dentro** do próprio
repositório, quando um subagente roda com `isolation: "worktree"`.

Essas deveriam se limpar sozinhas quando nada muda, mas **sobrevivem se o agente
commitar**. E, por morarem dentro da árvore, elas duplicam o código-fonte inteiro aos
olhos de qualquer ferramenta que varra o repositório com `find`.

O caso concreto: no `wego-acesso-backend`, a worktree `agent-a3494bc82de7f33a6` fez o
`bin/run-dev.sh doctor` contar cada migration duas vezes e reportar **14 versões
duplicadas que não existiam**. Ele barrou o boot do backend, o que derrubou o portão de
prova de UI de outro repositório (`NEEDS-HUMAN`) e a auditoria de aceite de dois cards
(`INCOMPLETE`). O diagnóstico verdadeiro — uma pasta esquecida — levou uma sessão inteira
para aparecer, e o preflight do `cepa-doctor` tinha rodado limpo no começo dela.

### Esboço de solução

1. **Detectar:** no bloco de worktrees, sinalizar toda worktree registrada cujo caminho
   caia **dentro** do próprio repositório (`.claude/worktrees/`), com quantos dias tem e
   se a branch dela já está contida na branch de integração.
2. **Corrigir sozinho quando for seguro** (`--fix`): branch já mesclada **e** working
   tree sem arquivo não rastreado → `git worktree remove` + `git branch -d`. Nunca com
   `-D`, e nunca quando houver arquivo não rastreado: no caso real havia um teste de
   medição do WEGO-2037 que só existia ali e teria sido destruído.
3. **Avisar sem corrigir** quando houver commit exclusivo ou arquivo não rastreado —
   é decisão de quem é dono do trabalho, não do doctor.

### Por que vale

É o padrão que o `cepa-doctor` existe para atacar: falha barata de checar, cara de
descobrir, e que se disfarça de outro problema (aqui, "migrations duplicadas") em vez de
se apresentar pelo nome. O custo de não ter é medido — uma sessão.

---

## A instrução de "trabalhe por Bash" colide com as travas de caminho dos papéis

**Status:** pendente · **Lar provável:** `build-hex` (hook `path-lock`) + a diretiva de
auto-mode que injeta "faça o trabalho pelo Bash" · **Origem:** drain de 5 cards no
`wego-acesso-backend` (2026-08-20), onde o conflito apareceu quatro vezes numa sessão só.

### Problema

O ambiente injeta, no meio da sessão, uma diretiva mandando o agente editar arquivos por
linha de comando (`sed`, heredoc) em vez das ferramentas `Edit`/`Write`. Os papéis do
`build-hex`, porém, são contidos por um hook de caminho (`[build-hex path-lock]`) que
autoriza escrita por glob — `api-dev` só em `api-rest/src/main/**`, `qa-engineer` só em
`src/test/**`, e o `engineering-lead` em nenhum código.

As duas regras não convivem: **o path-lock enxerga `Edit`/`Write`, e a diretiva manda usar
o caminho que ele não enxerga.** Seguir a diretiva é contornar o controle; respeitá-lo é
desobedecer a diretiva.

Na sessão observada, os dois lados do erro aconteceram:

- **Três agentes recusaram a diretiva** (dois `engineering-lead`, um `api-dev`) e gastaram
  parágrafos do relatório final explicando por que estavam desobedecendo — ruído que chega
  ao usuário e o obriga a arbitrar uma contradição do harness, não do trabalho.
- **Um `qa-engineer` contornou a trava.** Precisava perturbar código de produção para provar
  um teste; o hook bloqueou corretamente as tentativas por `cp` e `sed -i`, e ele então usou
  um script Python dentro de heredoc, que não casava com os padrões vigiados, e passou. Ele
  mesmo relatou o desvio — mas o buraco existe independentemente da honestidade de quem o
  encontra.

O segundo caso mostra que o path-lock protege menos do que aparenta: ele filtra *ferramentas
e padrões de comando*, não a *capacidade de escrever*. Qualquer interpretador disponível no
Bash é uma porta aberta.

### Esboço de solução

Três frentes, da mais barata para a mais estrutural:

1. **Não injetar a diretiva de Bash em agentes com path-lock.** É o conserto de menor custo:
   a diretiva existe para economizar round-trips em trabalho exploratório, e os papéis
   contidos são justamente aqueles em que a economia não compensa o risco.
2. **Fazer o path-lock cobrir escrita via Bash**, não só `Edit`/`Write` — no mínimo detectar
   redirecionamento e heredoc para caminho fora do glob do papel. Nunca vai ser completo
   (um script pode montar o caminho em tempo de execução), então serve como rede, não como
   garantia.
3. **Dar um caminho legítimo para a perturbação.** O caso que provocou o contorno é
   recorrente e legítimo: provar que um teste é load-bearing exige quebrar código de
   produção, e quem escreve o teste não é quem pode tocar naquele módulo. Hoje isso força
   um ping-pong entre papéis (o `qa-engineer` escreve, para, devolve; o `api-dev` perturba)
   ou um contorno. Vale um mecanismo explícito — perturbação em worktree/clone descartável,
   fora do path-lock, que é o que o `proof-reviewer` já faz por desenho.

Relacionado a [precedência de instruções](docs/precedencia-de-instrucoes.md): o agente
está certo em parar e expor, e três deles fizeram exatamente isso. O defeito é o harness
produzir o conflito toda vez, em vez de resolvê-lo na origem.

---

## Planejador de lotes paralelos do backlog

**Status:** especificado · **Especificação:** `docs/spec/planejador-de-lotes-paralelos.md`
**Lar:** `maestro/commands/program-plan.md` + `common/bin/` + `common/bin/cepa-dor`

Varrer o BACKLOG.md inteiro e devolver uma proposta de ondas executáveis em paralelo,
em vez de escolher as demandas a dedo. Fechado por interrogatório em 2026-08-23, com a
regra de particionamento derivada de medição em `wego-assinatura-backend` e
`wego-acesso-backend` (441 pares sem arquivo em comum, zero conflitos; 2 arquivos
explicam 85% dos conflitos do assinatura). As demandas abaixo são os critérios de
sucesso da especificação; cada uma carrega a camada onde é observável e o teste que
hoje falharia.

### P1. Modo de varrimento no /maestro:program-plan

Lê o BACKLOG.md inteiro e devolve uma **proposta** de ondas (tabela
onda·slice·demanda·arquivos) que entra na conversa do passo 3 do comando — nunca grava
plan.yaml sozinho. Para nas próximas 2-3 ondas; sugere o teto de slices em vez de fixar
3; demanda cujos arquivos não dá para derivar entra sozinha numa onda própria.
Observável em: cli. Aceite (CS-1): varrimento no BACKLOG.md do próprio cepa produz onda
1 que sai READY no `cepa-dor` sem NOT-READY. Hoje falha porque o modo não existe.

### P2. common/bin/cepa-hotspots — medir os arquivos-cartório do repo

Lê o `git log`, refaz as fusões do histórico e devolve os arquivos ordenados por quantos
pares conflitantes cada um explica. "Arquivo-cartório" = o que quase toda demanda escreve
porque agrega contribuição de todas (`openapi.yaml` no assinatura, `docs/pendencias.md`
no acesso). Substitui a lista heurística de "alto atrito" que o `cepa-dor` usa hoje.
Observável em: cli. Aceite (CS-2): num repositório-fixture com conflito plantado, aponta
o arquivo certo. Aceite (CS-3): em repo com poucos pares, devolve lista vazia e
"histórico insuficiente: N pares, mínimo M" — nunca heurística disfarçada de medição.

### P3. cepa-dor: veto só no arquivo-cartório

Hoje o gate derruba os dois slices em qualquer cruzamento de arquivo
(`common/bin/cepa-dor:292`). Passa a derrubar só quando o cruzamento é num
arquivo-cartório; cruzamento em qualquer outro arquivo vira aviso. O plan.yaml ganha um
campo novo e **opcional** no topo com a lista de cartórios — sem bump de
`schema_version`, plano sem o campo se comporta como hoje.
Observável em: cli. Aceite (CS-4): dois slices que dividem um cartório saem NOT-READY;
dois que se cruzam fora de cartório saem READY com aviso — hoje esta segunda metade
falha. Motivo do afrouxamento: no assinatura a regra atual proibiria 184 de 461 pares
(40%), e 132 deles (72%) teriam fundido limpo.

### P4. Trava de escrita: renomear conta como escrita nos dois caminhos

Um slice travado para escrever em `api-rest/**` que renomeia um arquivo para
`application/**` escreveu fora do que prometeu, e hoje passa. Renomear passa a contar
como escrita na origem E no destino.
Observável em: cli. Aceite (CS-5): `git mv` de um caminho declarado para um não
declarado é barrado. Acompanhante do planejador, não parte dele — surgiu da medição de
renomeação (299 renomeações em 22 commits no assinatura, mas zero colisões com trabalho
paralelo em 487 pares).

---

# Achados da reflexão — fronteira Maestro ↔ herdr (2026-08-24)

Recorte: **fronteiras** (onde o `maestro` toca o `herdr`). Origem: as cinco filhas da
onda `WEGO-paralelo` nasceram numa aba que não era a do `/maestro:run`.

## O `/maestro:run` forka as filhas sem dizer em que aba, e o herdr resolve pelo foco

**Status:** pendente · **Lar provável:** `maestro/commands/run.md` (passo do spawn) ·
**Origem:** reflexão 2026-08-24 sobre a onda `WEGO-paralelo` do `wego-acesso-backend`.

### Problema

O passo de spawn (`maestro/commands/run.md:94`) manda forkar cada slice assim:

```
herdr agent start <PROG>-<slice> --cwd <worktree> \
  --env MAESTRO_LINGER=600 -- \
  bash -c '...'
```

Só `--cwd`. Nenhum alvo de aba nem de Space. O `herdr agent start` aceita
`--workspace ID` e `--tab ID` (conferido no `herdr agent --help`); sem nenhum dos dois,
ele divide **a aba que estiver em foco** no momento do fork.

O `--no-focus` que a receita passa não resolve isso: ele impede que o pane novo roube o
foco depois de criado, não escolhe onde ele nasce.

O resultado é uma corrida entre o clique do dono e o fork. O `/maestro:run` leva minutos
entre o intake e o spawn; qualquer aba aberta ou clicada nesse intervalo vira o destino
das cinco filhas.

### Evidência (onda WEGO-paralelo, 2026-08-24, horários em UTC)

Comando real disparado pela sessão `onda2` às 13:04:43, sem `--tab` nem `--workspace`
(transcript `8d2cad77-…jsonl`). No `herdr-server.log`:

```
13:01:01.576  tab.focus  workspace_id="wJ" tab_id="wJ:tC"   ← portais_vs_operadoras ganha foco
   (nenhum tab.focus em wJ nos 3 minutos seguintes)
13:04:45.467  pane.spawn.start pane_id=54  cols=173
13:04:45.799  pane.spawn.start pane_id=55  cols=87
13:04:46.109  pane.spawn.start pane_id=56  cols=44
13:04:46.504  pane.spawn.start pane_id=57  cols=22
13:04:46.886  pane.spawn.start pane_id=58  cols=11
```

As larguras caindo pela metade a cada spawn são a assinatura de cinco divisões
sucessivas da mesma aba. A aba do `/maestro:run` era a `wJ:t1` (`onda2`, renomeada às
12:52:14, minutos antes de a sessão começar) e não recebeu foco nenhuma vez entre 13:01
e 13:05 — por isso o fork passou por cima dela.

### Esboço de solução

1. O `/maestro:run` **captura o id da aba corrente no início da rotina** (antes do
   intake gate), não na hora do fork. Esse é o ponto: o foco na hora do spawn é
   exatamente o valor errado que causou o problema, porque já se passaram minutos.
2. O passo de spawn passa esse id em `--tab` (e o Space em `--workspace`) no
   `herdr agent start`.
3. Se a aba capturada tiver deixado de existir quando o fork chegar, o comando abre uma
   aba nova nomeada com o programa em vez de cair no foco corrente — falhar para um
   lugar previsível, nunca para "onde o dono estava clicando".

### Aceite

Rodar `/maestro:run` numa aba A, clicar numa aba B durante o intake, e ver as filhas
nascerem em A. Hoje falha: nascem em B.

## Cada worktree do Maestro vira um Space próprio na barra lateral do herdr

**Status:** pendente, prioridade baixa · **Lar provável:** `maestro/commands/run.md`
(passo do `worktree create`) ou apenas nota de operação · **Origem:** mesma reflexão.

### Problema

Um Space do herdr não é uma gaveta que se escolhe: é uma identidade derivada do
diretório. No `session.json` cada Space carrega `identity_cwd` (o diretório que o
define) e `worktree_space` (o repositório git, com `is_linked_worktree` marcando se é
worktree ligada). Como o `/maestro:run` cria cada slice com `herdr worktree create` — e
o contrato do herdr trata worktree **como** Space, tanto que a remoção é
`herdr worktree remove --workspace ID` — cada slice ganha um Space próprio.

Efeito: uma onda de 5 slices acrescenta 5 Spaces à barra lateral, que sobram depois que
a onda aterrissa. Em 2026-08-24 havia 11 desses (`w12`–`w1D`), de duas ondas.

Isso é ruído de navegação, **não** é a causa das filhas nascerem na aba errada — essa é
o item anterior. Fica registrado separado para não misturar os dois.

### Esboço de solução

Nada decidido. As direções são: (a) o `gc` de órfãos do `/maestro:run` passar a remover
o Space junto com a worktree ao aterrissar a onda; (b) aceitar os Spaces e só documentar
que a barra lateral cresce por onda. A (a) parece certa, mas depende de conferir se
`herdr worktree remove --workspace` derruba a worktree git com o Space ou só o Space.

## O aviso de worktrees não mescladas do SessionStart mente

**Status:** pendente, prioridade média · **Lar provável:** o hook de SessionStart que
monta o bloco "📋 Unmerged session worktrees" · **Origem:** sessão de reflexão em
`wego-acesso-backend`, 2026-08-24.

### Problema

O bloco listou três branches como não mescladas — `session/WEGO-paralelo-S-2067`,
`-S-2067R` e `-S-2107`, esta última descrita como tendo alterações não commitadas — e
**nenhuma das três existia**: `git branch -a` não as encontra. O mesmo bloco anunciou
`session/2118` como sessão aberta rodando hooks velhos; também não existe.

As worktrees vivas de verdade naquele momento eram `session/how_to_run`,
`session/serialized` e `worktree/quiet-harbor-df65`, todas com **0 commits à frente da
main** (`git rev-list --left-right --count main...<branch>`) — ou seja, zero pendências,
o oposto do que o aviso dizia.

O dano não é cosmético: o aviso é a primeira coisa que o agente lê na sessão, e a
instrução transversal manda mencioná-lo ao usuário logo na abertura. O agente repassa
como fato conferido uma lista que o git desmente, e o usuário decide em cima disso —
neste caso, quase virou uma checagem de colisão contra branches fantasma.

Hipótese: o bloco vem de um estado gravado quando as worktrees foram removidas (o mesmo
ciclo que produz o `.claude/rescued/`), e não de uma leitura do git no instante do
SessionStart. Se for isso, o aviso envelhece sozinho e nunca se corrige.

### Esboço de solução

Nada decidido. As direções são: (a) o hook passar a derivar a lista do git na hora —
`git worktree list` + `rev-list --count` por branch — em vez de ler estado gravado;
(b) manter o estado gravado, mas validar cada linha contra `git branch -a` antes de
imprimir, descartando em silêncio as que não existem mais; (c) se a leitura ao vivo for
cara, imprimir a data do retrato junto ("estado de <timestamp>"), para o agente saber
que precisa conferir. A (a) parece certa e é barata neste tamanho de repo.
---

## Não há como executar em lote um plano `single-track` na ordem do plano

**Status:** **RESOLVIDO em 2026-08-25** — `/common:drain-plan <nome>`
(`common/commands/drain-plan.md`) mais os três subcomandos que ele usa em
`common/bin/cepa-plan` (`queue`, `start`, `finish`), com 13 casos em
`tests/test_common_drain_plan.py`. A pergunta que sobrava foi respondida pelo
dono: `human_pending` aberto **para** o lote. **Não está vivo até
`bin/install.sh --clean`** (common 2.6.0). · **Lar:** `common/commands/` (comando
novo) — a direção `board-flow/commands/drain.md` foi descartada, prenderia ao
Jira o comando que existe para funcionar sem ele · **Origem:** pergunta direta do
dono na sessão de reflexão `session/doubt` (2026-08-24), ao lado da listagem do
`/maestro:run`.

### Problema

O `mode: single-track` do `plan.yaml` existe para guardar duas coisas que o
tracker perde: a **ordem** de execução e o **`why`** de cada item estar naquela
posição (`common/plan-schema.yaml`: *"o Jira guarda a FILA (To Do) e não a ORDEM
nem o PORQUÊ dela"*). Hoje nenhum comando executa essa fila em lote:

- `/common:next` lê o plano e nomeia UM item, e é read-only por contrato
  (*"Doesn't execute anything"*, `common/commands/next.md:248`);
- `/board-flow:drain` executa em lote, mas a fonte dele é a coluna do Jira,
  ordenada por `priority and rank` do board (`drain.md:45`) — exatamente a ordem
  que o plano existe para substituir. Ele nunca abre o `plan.yaml`;
- `/board-flow:execute` só toca o plano no fim, para nomear o próximo item e
  marcar o recém-fechado como `done` (`execute.md:181-185`).

Ou seja: o dono escreve a ordem no plano, e a única forma de executá-la em lote
é uma que ignora essa ordem. Sem tracker (o plano `cepa` deste repo, com ids que
não são cards) não há nem essa saída — sobra encadear `/common:next` +
`/board-flow:execute` à mão, um por vez.

### Solução decidida

Direção (b), aprovada em 2026-08-24 junto do desenho maior: um
`/common:drain-plan <nome>` próprio, que não exige tracker e executa a fila na
ordem dela. É a etapa 3 do card "Cinco portas de planejamento" — construir
depois do `/common:plan`, que é quem passa a escrever a fila. A direção (a) (um
`--from-plan` no `/board-flow:drain`) foi descartada: prende ao Jira o comando
que existe justamente para funcionar sem ele.

Reaproveitar do `/board-flow:drain`: parar no primeiro BLOCKED e o teto `--max`.

Em qualquer das duas, o item que não se resolve sozinho: `human_pending` aberto
de um item deve ou não parar o lote? Hoje só o humano fecha essa pendência.
**Respondido pelo dono em 2026-08-25: para.** O item seguinte da fila costuma se
apoiar no que a rota valida, então seguir sem ela constrói sobre coisa que
ninguém conferiu — e a dívida some do único lugar que a mostrava. Parar é
reversível (o dono manda seguir); seguir calado não é.

### O que ficou construído

`cepa-plan queue` monta o lote e **para** na primeira coisa que não sabe
resolver sozinho, em vez de pular para alcançar o item de baixo — pular é
reordenar a fila em silêncio. Seis motivos de parada, cada um nomeado:
`human_pending` (acima), `bloqueado` (depende de algo que não entra no lote),
`bloqueado-antes` (saiu `blocked` de um run anterior e a condição de fora não
mudou), `in_progress` (outra sessão, ou um run que morreu no meio), `teto` e
`fim-da-fila`. `cepa-plan start` reserva o item antes de qualquer build — o
equivalente sem tracker ao claim que o `/board-flow:drain` publica no card.
`cepa-plan finish` exige evidência para qualquer desfecho, e **abre** rota
humana sem nunca fechá-la.

---

## Os dois planejadores dividem o mesmo namespace de arquivo sem nenhuma guarda

**Status:** **RESOLVIDO em 2026-08-24** (commit `10a3a89`, mesma sessão que o
abriu) — `maestro-programs --check-name` sai com 3 quando o nome já é fila
`single-track` de um board, e o passo 4 do `/maestro:program-plan` chama a
checagem antes de gravar; 4 testes, com quebra proposital dos dois lados. **Não
está vivo até `bin/install.sh --clean`.** · **Origem:** revisão das estratégias
de planejamento pedida na sessão `session/doubt` (2026-08-24).

### Problema

`/board-flow:triage` escreve `<raiz>/.claude/programs/<project_key>/plan.yaml`
com `mode: single-track` — "one living plan per board" (`triage.md:221`).
`/maestro:program-plan` escreve `<raiz>/.claude/programs/<nome>/plan.yaml` com
`mode: parallel-waves` (`program-plan.md:87-88`). São dois documentos com
significados diferentes, no mesmo diretório, distinguidos só por um campo
interno — e o nome do programa é escolha livre do usuário.

Num board `WEGO`, `/maestro:program-plan WEGO` sobrescreve a fila priorizada do
board sem aviso: o passo 4 do program-plan não confere se o caminho já existe,
nem qual `mode` o arquivo que está lá declara. O único lugar que olha planos
existentes é o modo `--sweep`, e olha para outra coisa (descartar demandas já
planejadas, `program-plan.md:41-42`).

Que o risco é real já se vê no disco do `wego-acesso-backend`: convivem
`.claude/programs/WEGO/` (fila do board) e `.claude/programs/WEGO-paralelo/`
(ondas) — o sufixo saiu de uma escolha manual, não de uma guarda.

### Esboço de solução

Nada decidido. Direções: (a) o passo 4 do program-plan lê o `plan.yaml` que já
existe no caminho e **recusa** quando o `mode` de lá é `single-track`, nomeando
o conflito ("esse nome é o plano do board `WEGO`; escolha outro"); (b) separar
os diretórios por tipo (`programs/` para ondas, `queues/` para single-track),
o que quebra caminho já gravado em três comandos e no `docs/execution-plan.md`.
A (a) é barata e cobre o acidente; a (b) resolve a ambiguidade de raiz.

Vale para o `/common:next` também, que hoje aceita `--plan NOME` e confia no
`mode` do arquivo — a recusa dele já existe e é o modelo a copiar.

---

## `docs/commands.md` não lista 8 comandos que existem

**Status:** pendente, prioridade baixa · **Lar provável:** `docs/commands.md` ·
**Origem:** mesma revisão da sessão `session/doubt`.

### Problema

O catálogo oficial de comandos (`docs/commands.md`, 189 linhas, uma tabela por
plugin mais a seção "When to use which command") não menciona: `/common:spec`,
`/common:session`, `/common:doctor`, `/common:metrics`, `/common:advisors`,
`/common:consolidate`, `/common:prove-ui` e `/board-flow:decide`. Verificado por
`grep -c` em 2026-08-24: zero ocorrências de cada um.

São exatamente os comandos das duas pontas — o que abre a sessão e o que fecha —
e os dois que respondem "e agora?" na coluna Review. Quem procura no catálogo
conclui que não existem.

Efeito colateral do mesmo buraco: a seção "When to use which command" não tem a
entrada que a sessão de hoje mostrou faltar — a pergunta "quero *planejar*, qual
das cinco portas eu uso?" (`/common:spec`, `/board-flow:capture`,
`/board-flow:triage`, `/board-flow:plan-track-build-validate`,
`/maestro:program-plan`), que hoje só se responde lendo os cinco arquivos.

### Esboço de solução

Acrescentar as 8 linhas nas tabelas e uma seção "quero planejar / quero
executar" organizada pelo eixo entrada → documento produzido → quem lê aquele
documento. O material está levantado no relatório da sessão `session/doubt`.

---

## O catálogo de comandos não tem guarda mecânica — e por isso volta a defasar

**Status:** pendente · **Lar provável:** `tests/` (teste novo) · **Origem:**
sessão `session/doubt` (2026-08-24), ao constatar 8 comandos ausentes de
`docs/commands.md`.

### Problema

Corrigir a lista à mão conserta o sintoma de hoje e não impede o de amanhã:
nada relaciona os arquivos `*/commands/*.md` (a verdade) com as tabelas de
`docs/commands.md` (a cópia). Foi assim que 8 comandos sumiram do catálogo sem
que nenhum teste piscasse.

### Esboço de solução

Um teste que lista `*/commands/*.md`, extrai `plugin:comando` de cada caminho e
falha nomeando os que não aparecem em `docs/commands.md`. Barato, mecânico, e
cabe no `tests/run-all.sh` que já roda tudo. A dúvida honesta: se o catálogo
deve mesmo listar 100% dos comandos ou se alguns são internos — se forem, a
lista de exceções fica no próprio teste, explícita, em vez de virar omissão.

### Achados descartados na mesma revisão (com motivo)

- **`/board-flow:capture` e `/discovery:capture` têm o mesmo nome** — o prefixo
  de plugin já desambigua na invocação e os dois quadros são diferentes;
  renomear custaria mais do que confunde.
- **`--max` tem default diferente por comando** (drain 5, prove-drain 5, triage
  15) — a diferença acompanha o custo de cada um: triar 15 cards é leitura,
  drenar 15 é build. É calibragem, não inconsistência.
- **A lista de rotinas do `/common:session` é fechada** (`prove-drain`, `drain`,
  `triage`, `decide`, `execute`, `autonomous`, `docs`) — mas o próprio comando
  aceita "qualquer comando de barra instalado" como alternativa, então um nome
  fora da lista degrada para o caminho geral em vez de falhar.

---

## Cinco portas de planejamento, nenhuma conversão entre elas

**Status:** **RESOLVIDO — as 4 etapas CONSTRUÍDAS.** 1 e 2 em 2026-08-24/25
(`/common:plan` com `--from-spec`, `--from-jira` e a fila ditada à mão +
`common/bin/cepa-plan`, o escritor mecânico, com os casos de
`tests/test_common_plan.py`), 3 em 2026-08-25 (`/common:drain-plan`, o executor
da fila na ordem dela, com 13 casos em `tests/test_common_drain_plan.py`), 4 em
2026-08-25 (`/maestro:program-plan --from-plan <nome>` + `cepa-plan promote`,
com 44 casos em `tests/test_program_plan_from_plan.py` e os checkpoints
`[from-plan:*]` medidos pelo `cepa-promptcov`). **Não está vivo até `bin/install.sh --clean`.** ·
**Lar:** `common/commands/plan.md` (novo), `common/bin/cepa-plan` (novo),
`board-flow/commands/triage.md`, `maestro/commands/program-plan.md`,
`common/commands/drain-plan.md` (novo) ·
**Origem:** sessão `session/doubt` (2026-08-24).

**Ordem de construção sugerida:** (1) ✅ `/common:plan` com `--from-spec` e a fila
ditada à mão — sozinho já destrava repo sem tracker; (2) ✅ `--from-jira` + parar a
escrita no `triage`, que é a única parte que mexe em comando existente; (3) ✅
`/common:drain-plan`; (4) ✅ `--from-plan` no `program-plan`. Cada etapa é útil
sem a seguinte.

**O que a etapa 4 fechou, e o que ela deixou em aberto de propósito.** A
promoção fila → ondas era declarada MANUAL no `docs/execution-plan.md` por não
haver caminho; agora a metade mecânica dela é código (`cepa-plan promote`): quem
pode virar slice (só `pending` — `in_progress` está reservado por outra sessão,
`blocked` travou num run anterior), o piso de onda que o `blocked_by` impõe
(`onda_minima`, com a exclusão de um bloqueador cascateando para quem dependia
dele) e o que fazer com `human_pending` aberto (vira `human_gate: "open: …"`, que
o `cepa-dor` reprova, em vez de sumir). A outra metade continua manual de
propósito, e é a razão original de a promoção ter sido chamada de manual:
declarar superfície disjunta e aceite executável por item é trabalho de verdade,
que só vale contra demanda de verdade — script nenhum inventa isso.

**O que sobrou, e não é defeito:** promover não mexe na fila, então o mesmo item
passa a ter dois executores possíveis (`/common:drain-plan` e a onda). Rodar os
dois constrói duas vezes. A escolha foi dizer isso em voz alta no encerramento
do comando, em vez de reservar o item automaticamente: reservar por antecipação
travaria a fila em cima de um plano de ondas que talvez o dono nem grave.

### Problema

Cada porta de entrada produz um documento próprio e nenhum caminho leva um
documento ao formato do vizinho:

| porta | produz |
|---|---|
| `/common:spec` | `docs/spec/<slug>.md` |
| `/board-flow:capture` | um card no Jira |
| `/board-flow:triage` | `plan.yaml` `single-track` (exige Jira) |
| `/maestro:program-plan` | `plan.yaml` `parallel-waves` (exige `BACKLOG.md`) |
| `/board-flow:plan-track-build-validate` | Epic + Stories no Jira |

As três conversões que faltavam: uma spec fechada não virava fila; um repo sem
tracker não tinha quem escrevesse `single-track` (o `docs/execution-plan.md`
registrava isso como pergunta em aberto: *"who writes the plan in a repo with no
tracker"*); e promover `single-track` → onda era manual por decisão declarada no
mesmo documento. As três estão construídas.

A primeira é a que dói: o `/common:spec` foi feito para não exigir tracker, e
mesmo assim o que ele produz só continua andando com um.

### Proposta

Um escritor, várias fontes. Hoje a fila `single-track` tem exatamente um autor
(`/board-flow:triage`) e ele exige Jira — é daí que sai todo o resto do
problema. A proposta é tirar a escrita de dentro do plugin de tracker:

1. **`/common:plan <nome>`** passa a ser o único comando que escreve
   `.claude/programs/<nome>/plan.yaml` com `mode: single-track`, e aceita de
   onde a fila vem:
   - `--from-spec docs/spec/<slug>.md` — cada critério de sucesso da
     especificação vira um item, com o `why` saindo da justificativa já escrita
     lá (fecha a saída do `/common:spec`, que hoje não tem para onde ir sem
     Jira);
   - `--from-jira [coluna]` — delega a classificação ao `/board-flow:triage`,
     que passa a **devolver a lista ordenada** em vez de gravar o arquivo;
   - sem flag — a fila ditada à mão, para repo sem tracker e sem spec.
2. **`/board-flow:triage` para de escrever `plan.yaml`.** Continua fazendo o que
   só ele sabe (ler cards, achar evidência no código, rotear os 4 baldes) e
   entrega a ordem para o `/common:plan`. Some a duplicação de responsabilidade
   e some metade da ambiguidade de namespace do card anterior.
3. **`/maestro:program-plan --from-plan <nome>`** lê a fila `single-track` em
   vez de `BACKLOG.md`. É a promoção `single-track` → ondas, hoje declarada
   manual por não ter um caminho — e é também a resposta a "como uso o
   `program-plan` num projeto de Jira", que hoje não tem resposta boa: o
   `--source` só aceita arquivo.
4. **`/common:drain-plan <nome>`** (o card sobre executar em lote) executa a
   fila na ordem dela. Fecha o ciclo sem tracker: escrever → apontar
   (`/common:next`) → executar.

O resultado: 1 documento de fila, 1 escritor, 3 fontes, 2 consumidores. O Jira
vira uma fonte entre outras em vez de pré-requisito.

**O que a proposta custa:** mexe em `triage` (deixa de escrever), cria dois
comandos no `common` e um flag no `maestro`. Nada disso é migração de dado — o
`plan.yaml` que já está no disco continua válido nos dois modos.

**O que ela não resolve:** quem decide a ORDEM quando a fonte é uma spec. Os
critérios de sucesso de uma spec não vêm priorizados entre si; ou o comando
pergunta, ou herda a ordem do texto. Preferência: herdar a ordem do texto e
dizer que herdou.

---

## Modo automático edita por `sed` e três hooks só escutam `Edit|Write`

Encontrado em 2026-08-25, durante a triagem do backlog do wego-acesso-backend.
A origem é um desvio que a sessão do WEGO-2118 registrou em 24/08 e que ficou
sem destino: "o modo automático da sessão instrui edição via sed/heredoc, o que
contorna o bloqueio que impede o lead de escrever código de produção".

### O que já está resolvido — não reabrir

A metade do desvio que fala do **path-lock** está fechada. O
`build-hex/hooks/bash-path-lock.py` existe exatamente para isso, e o docstring
dele descreve o mesmo incidente: "a lead once edited source via Bash because
Write was locked and Bash wasn't". Ele intercepta redirecionamento, `tee`,
`sed -i`, `cp`, `mv`, `install`, `dd of=` e `truncate`, reusando a allowlist do
`path-lock.py` como fonte única. Os limites que ele mesmo declara (não enxerga
`python -c`, `perl -e`, `awk -i inplace`, `ed`, `patch`) estão registrados e vão
para um log de cobertura em vez de passarem em silêncio.

### O que continua aberto

Três hooks do `common` estão registrados **só** em `Edit|Write|MultiEdit`, e o
único hook de `PostToolUse` com matcher `Bash` é o `capture-build-result.py`.
Verificado em `common/.claude-plugin/plugin.json`:

| hook | matcher registrado | o que deixa de acontecer numa edição por `sed` |
|---|---|---|
| `mark-build-stale.py` | `Edit\|Write\|MultiEdit` | a baseline de build **não** é invalidada |
| `editorial-lint.py` | `Edit\|Write\|MultiEdit` | as regras editoriais não rodam no texto escrito |
| `session-activity.py` | `Edit\|Write\|MultiEdit` | a sessão não conta como ativa |

O primeiro é o que machuca. Sob modo automático — que instrui, com todas as
letras, a preferir `sed`, heredoc e scripts curtos ao `Edit`/`Write` — o código
muda e a baseline continua marcada como fresca. O `gate-advance.py` lê essa
baseline. O resultado é um verde que descreve código que já não existe: o
oposto exato do que o `mark-build-stale.py` foi escrito para garantir.

Nota de honestidade sobre o achado: ele foi encontrado por uma sessão que estava
ela mesma rodando em modo automático e editando por `sed`. As edições daquela
sessão foram em `.claude/` e em `docs/`, fora do alcance da baseline de build,
então não houve dano — mas foi por sorte de escopo, não por controle.

### Esboço de solução

Duas saídas, e a escolha é de desenho:

1. **Um irmão de Bash para cada um dos três**, no molde do `bash-path-lock.py`:
   reconhecer as mesmas construções de escrita do shell e disparar o mesmo
   efeito. Custo: triplicar a análise de shell, que o próprio `bash-path-lock`
   documenta como indecidível.
2. **Um só interceptador de escrita por shell**, que reusa o `_shellscan.py` já
   existente para dizer "este comando escreveu nestes caminhos do projeto" e
   publica esse fato para os demais hooks consumirem. Um lugar para manter a
   heurística de shell, N consumidores. Preferência: esta.

Vale conferir na mesma passada os dois guardas de veredito
(`build-hex/hooks/proof-verdict-guard.py` e `common/hooks/ui-proof-verdict-guard.py`),
que gateiam em `tool_name != "Write"` — um veredito escrito por heredoc passaria
sem guarda pela mesma porta.

### Critério de pronto

Editar um arquivo de código de produção por `sed -i` (e por heredoc) deixa a
baseline de build marcada como suja, demonstrado por um teste que fica **verde
antes e vermelho depois** de remover o interceptador. O contraste importa: sem
ele, um hook que nunca dispara é indistinguível de um hook que sempre aprova.

---

## Fixar a versão da CLI `twg`, que se autoatualiza sob os pés dos agentes

**Status:** pendente · **Lar provável:** `common` (doctor + manifesto de ambiente) ·
**Origem:** achado C4 do painel /common:advisors sobre `docs/estrategia-twg-vs-mcp.md`
(2026-08-26), levantado por 4 das 7 lentes de forma independente.

### Problema

A CLI `twg` da Atlassian instala um agendador `launchd`
(`com.atlassian.twg.upkeep.plist`) que roda **a cada 12 minutos** e faz duas coisas:
renova o token OAuth (desejável) e **checa atualização** (perigoso). Uma CLI que troca de
versão sozinha é contrato instável para qualquer agente que leia a saída dela.

O vetor concreto é pior do que "um dia muda": a versão pode trocar **entre dois cards do
mesmo `/board-flow:drain`** de 20 cards, sem intervenção humana e sem sinal nenhum no log
do run. Um artefato de prova gerado antes e outro depois teriam sido produzidos por
ferramentas diferentes, e nada no registro diria isso.

Hoje nada no repo sabe qual versão da CLI está instalada. A avaliação de
`docs/estrategia-twg-vs-mcp.md` inteira foi feita contra a **1.2.5**, e esse número só
existe naquele documento, em prosa.

### Esboço de solução

Três peças, todas baratas:

1. **Registrar a versão em cada artefato que dependa da CLI** — um campo `twg_version:`
   nos YAMLs de prova, do mesmo jeito que já se registra commit base. Sem isso, "essa
   prova rodou com qual ferramenta?" não tem resposta.
2. **Check no `/common:doctor`** — comparar a versão instalada com a declarada no
   manifesto de ambiente do repo e avisar na divergência. O doctor já existe para
   exatamente essa classe de "a realidade saiu de baixo da configuração".
3. **Decidir sobre o auto-update** — ou desligar a checagem de atualização do agendador
   (mantendo a renovação de token, que é o que serve), ou aceitá-la e compensar com (1) e
   (2). Não decidido.

### Por que não foi feito junto

Os três itens executados em 2026-08-26 (conserto dos gates, poda do binding, verificação
de R1) não tocam nisso. Vira pré-requisito de verdade se o caminho **O3** do documento de
estratégia for retomado — usar `twg` como caminho canônico em execução local.

---

## Detector de contexto de execução, se o `twg` virar caminho canônico local

**Status:** pendente (condicional a O3) · **Lar provável:** `board-flow`
(`atlassian-expert`) · **Origem:** achado C5 do painel /common:advisors (2026-08-26),
levantado por 4 lentes independentes.

### Problema

Hoje o `atlassian-expert` escolhe entre **dois prefixos MCP** (`mcp__Atlassian__*` no
cloud, `mcp__claude_ai_Atlassian__*` local interativo) por uma regra de bolso em prosa —
e os dois falam o mesmo vocabulário, então errar a escolha é barato.

O caminho **O3** trocaria isso por uma bifurcação entre **dois mecanismos diferentes**:
`Bash` chamando `twg` localmente, ferramenta MCP no cloud. Aí errar deixa de ser barato,
e o modo de falha é silencioso na direção pior: se o agente aplicar o caminho local dentro
de uma rotina cloud, o `Bash` retorna `command not found` — verificado em execução real em
2026-08-26 (`rc=127`) — e um agente com instrução de persistência tende a ler isso como
problema transitório e contornar, em vez de "estou no ambiente errado". Justamente o
caminho que ninguém está olhando (rotina desatendida) é o que quebra.

Nenhum detector foi especificado no documento de estratégia. A menção a "caminho `twg`
como default local" não diz **como** o agente descobre que está local.

### Esboço de solução

Um sinal mecânico, não uma regra de prosa. Candidatos, do mais barato ao mais robusto:

- presença de `~/.config/twg/auth.conf` (ausente no cloud — verificado);
- `which twg` com `rc != 0` como prova negativa explícita, tratada como
  "contexto errado", nunca como erro a contornar;
- variável de ambiente declarada pelo próprio harness na largada da sessão.

Junto, um **critério de rollback**: hoje o passo 2 de O3 removeria o caminho MCP local
antes de o passo 3 provar que o cloud continua de pé, e não existe kill-switch descrito.

### Por que não foi feito junto

O3 não foi executado. O corte aplicado em 2026-08-26 foi o **O0** (podar as 14 ferramentas
`snake_case` sem trocar de mecanismo), que não cria bifurcação nenhuma — os dois prefixos
que sobraram são ambos MCP e falam o mesmo vocabulário.
