# Backlog — ideias e pendências da Cepa

Itens ainda **não implementados**. Cada um descreve o problema, o esboço de solução
e onde provavelmente mora. Sem ordem de prioridade fixa.

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

**Status:** EM CONSTRUÇÃO — passo 1 (spike do porteiro) FEITO 2026-07-15, VIÁVEL
(`maestro/spike-gatekeeper/SPIKE-RESULTS.md`); design rev2.1 · **Lar:**
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
  `~/.herdr/worktrees/<repo>/` (fora do repo/Insync, mesmo princípio do ccw),
  com workspace próprio; `worktree remove` limpa. ✓
- `agent send` / `pane send-text` injetam input em sessões interativas. ✓ (não testado
  a fundo)
- **Pegadinha real:** o pane fecha quando o processo termina e o output some — filhas
  precisam de wrapper (`sh -c 'claude -p ... | tee resultado.txt; echo MAESTRO-EXIT:$?;
  sleep N'`) que persista o resultado em arquivo e segure o pane.
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
