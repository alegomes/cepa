# Revisão da Cepa como harness de engenharia agêntica (2026-08-17)

> Revisão profunda solicitada pelo dono: "quão forte é a Cepa como harness de
> coding agents frente à fronteira atual, e o que a melhora materialmente?"
> Feita em sessão única (Fable 5), leitura direta do repo — sem subagentes.
>
> **Convenções.** "Verificado" = lido no repo nesta sessão, com caminho citado.
> "Inferido" = conclusão arquitetural a partir do que foi lido. "A validar" =
> hipótese que precisa de experimento.
>
> **Base de leitura:** `docs/internals/` (architecture, hooks, expertise,
> path-lock), `docs/` (proof-gate, execution-plan, maestro, autonomous-mode,
> context-forking, incomprimivel), prompts de agentes-chave (`engineering-lead`,
> `proof-reviewer`), comandos maiores (`triage`, `execute`, `next`,
> `worktree-merge`), `plan-schema.yaml`, hooks na íntegra (`gate-advance.py`,
> `_telemetry.py`), `cepa-metrics`/`cepa-doctor`, pilotos Gauntlet, BACKLOG,
> suíte `tests/` (22 arquivos).

---

## 1. Avaliação executiva

A Cepa é o sistema mais sofisticado que já vi construído por um único dono
sobre plugins de Claude Code — e em uma dimensão ela está **à frente** da
fronteira pública de agentic engineering: a **arquitetura de verificação**.
"Verde não é evidência; verde→vermelho-quando-eu-quebro→verde é evidência",
com veredito computado mecanicamente por hook e proibição estrutural de
auto-certificação, é melhor do que o que a maioria dos harnesses comerciais
faz (confiar no auto-relato do executor, ou num revisor LLM sem mecanismo).

Os três maiores riscos, em ordem:

1. **Massa de prompt como camada de controle.** 4.526 linhas só nos comandos
   de `board-flow`+`common` (conta: `wc -l` na sessão da revisão), 396 linhas
   no prompt do `proof-reviewer`. Muita lógica determinística (precedência de
   argumentos, tabelas de reconciliação, montagem de templates) vive em prosa
   que o modelo reexecuta a cada invocação — caro, e o modo de falha é drift
   silencioso, já pago várias vezes (os prompts documentam os incidentes).
2. **Pipeline de tamanho fixo.** A topologia é escolhida por *projeto*, não
   por *tarefa*. Todo card no `build-hex` paga o loop dev→qa→refactor-advisor→
   code-reviewer inteiro, mesmo com diff de 5 linhas. A Cepa quase nunca
   sub-verifica; ela sobre-cerimonializa o caso pequeno.
3. **Ausência de avaliação de regressão do próprio harness.** Os testes travam
   contratos de prompt, a telemetria conta bloqueios, o Gauntlet avalia
   *designs* — mas nada mede se uma mudança no harness melhora ou piora a taxa
   de sucesso dos agentes em tarefas repetíveis. `_telemetry.py` admite:
   "Every improvement was anecdotal".

Veredito curto: **fundação de verificação classe A; economia de contexto e
adaptatividade classe C; avaliação classe D (nascente)**. As recomendações
atacam nessa ordem inversa.

---

## 2. O que a Cepa realmente é (verificado)

Um marketplace de 9 plugins de Claude Code (49 agentes, 44 comandos — números
de `docs/internals/architecture.md`, batem com os diretórios):

- **6 topologias** (topologia = time de subagentes + snippet de orquestração
  importado no `CLAUDE.md` do projeto hospedeiro): `build-solo` (2 agentes),
  `build-team` (9), `build-hex` (14, backend hexagonal Quarkus), `discovery`,
  `design`, `docs`.
- **2 camadas transversais**: `board-flow` (ciclo Jira; um único agente com
  MCP Atlassian) e `review-gate` (PR).
- **Substrato `common`**: 28 hooks Python, 14 skills, 21 comandos, expertise
  por agente, telemetria, `cepa-doctor`, `cepa-dor` (gate de Definition of
  Ready), `cepa-metrics`.
- **`maestro`**: orquestração multi-sessão em ondas de worktrees paralelas —
  núcleos determinísticos testados, **nunca rodado ponta a ponta**
  (`docs/maestro.md`, status 2026-07-16).

Propósito: transformar um agente solo que "mente sobre done" num time cujo
"done" é provado por gates independentes e mecânicos antes de ser acreditado.

## 3. Modelo de execução atual

```
card Jira ──/board-flow:execute──▶ auditoria de detalhe (planning-lead)
   │                                    │
   │                              base_commit gravado (.claude/cards/<KEY>.yaml)
   ▼                                    ▼
In Progress ──▶ engineering-lead: decompõe em TASK.md ──▶ workers (worktrees paralelas)
   │                 loop por task: dev → qa → refactor-advisor → code-reviewer
   ▼
validation-lead ──▶ completion-auditor (gate de entrada do Review, por critério)
   │                 acceptance-gate.py BLOQUEIA a transição sem artefato COMPLETE
   ▼
In Review ──▶ proof-reviewer (gate de saída: perturbação/PIT sobre o diff inteiro)
   │            proof-verdict-guard.py recomputa o veredito no Write do artefato
   ▼
PROVEN → Done | UNPROVEN → volta | NEEDS-HUMAN → fila do humano
```

Em paralelo, malha de estado mantida por hooks e fora do controle do agente:
`last-build.json` (STALE/SUCCESS/FAILURE; `gate-advance` bloqueia commit/push
com estado ruim), handoff contínuo por turno (`session-checkpoint.py`),
registry de sessões, log de intents.

**Inferência:** o loop real é *plan → execute → verify (2 gates independentes)
→ route*, com replanejamento delegado ao humano via `/common:next` +
`plan.yaml`. Não há replanejador automático — deliberado e, na escala atual,
correto.

## 4. Topologia de agentes atual

Supervisor hierárquico em 3 camadas: orquestrador (sessão principal,
delegate-only por convenção), leads Opus (delegate-only por *allowlist de
tools* — enforcement real), workers Sonnet (path-locked por hook). Sobrepostos:
pipeline com gates (fluxo de card) e, no Maestro, fan-out de sessões inteiras.

Forte: separação thinker/doer imposta por capacidade, não por prompt; tabela
honesta "enforced vs convention" em `architecture.md`. Frágil: (a) orquestrador
delegate-only é só prompt (admitido); (b) 14 agentes no build-hex incluem
papéis discutíveis como agente separado (§10); (c) topologia fixada por
projeto — sem roteamento por tarefa.

## 5. Primitivas atuais

| Primitiva | Implementação | Qualidade |
|---|---|---|
| Estado de build confiável | `last-build.json` hook-escrito + `gate-advance` | Excelente |
| Prova de carga | perturbação + PIT, enums fechados, guard recomputa veredito | Excelente |
| Aceitação por altitude | `completion-auditor` + `acceptance-gate.py` | Muito boa |
| Campos incomprimíveis | `summary-nulls-gate`, `bounce-reason-gate` (`incomprimivel.md`) | Conceito original e forte |
| Fila que sobrevive à sessão | `plan.yaml` v2 + `/common:next` | Boa; não exercitada em board real (admitido) |
| Continuidade | handoff AUTO+NOTE por turno, resume por branch, state.yaml | Muito boa |
| Isolamento | worktrees de sessão + merge green-gate + resgate de artefatos | Boa (0.27.1 não live) |
| Aprendizado | expertise YAML + `/debrief` | Boa ideia, ROI não medido |
| Intake | `cepa-dor` (DoR executável) | O padrão certo: prompt chama binário |
| Telemetria/saúde | `_telemetry` + `cepa-metrics` + `cepa-doctor` | Semente certa, rasa |

**Ausentes com impacto:** grafo de dependência intra-card, orçamento de
retry/iteração, tokens por delegação, mapa de repositório cacheado, suíte de
benchmark. **Reimplementam CC:** `/branch`+`/return` vs forks nativos; partes
do worktree-lifecycle vs `isolation: "worktree"`; gatekeeper do Maestro vs
permission-modes+sandbox (parcialmente justificado por ser multi-sessão).

## 6. O que a Cepa faz particularmente bem (preservar, e por quê)

1. **Veredito mecânico, agente só mede** — `proof-verdict-guard.py` recomputa
   no Write e bloqueia `proven` contraditório; `/prove` re-deriva. Remove a
   classe "o agente se convenceu". A decisão saiu do espaço de tokens.
2. **Enforcement por capacidade em profundidade** — allowlist → path-lock →
   bash-path-lock → enforcement-guard. Cada camada nasceu de um furo real.
3. **Estado estruturado hook-mantido** — o agente não consegue esquecer nem
   mentir sobre o que o disco registra sozinho.
4. **Honestidade epistêmica encodada** — "plano é hipótese", "triage não prova
   nada", PARTIAL nunca arredonda, escada done L0–L4, `n/a` ≠ `skipped`.
5. **Testes de contrato de prompt com perturbação** (`test_fio_condutor.py`) —
   prompts tratados como código testável.
6. **Gauntlet Loop** — N designs independentes → juízes cegos contra barra
   pré-declarada; validado em 2 pilotos via tool Workflow.
7. **Tradução na fronteira humana** — altitude leiga obrigatória nos vereditos
   (o que significa / recomendação default / técnica por último).

## 7. Gargalos primários (ordem de custo estimado)

1. Custo fixo de cerimônia por tarefa (card pequeno paga pipeline de grande).
2. Redescoberta de repositório a cada spawn (nada cacheado entre cards).
3. Lógica determinística em prosa (tokens + drift).
4. Loops sem orçamento ("iterate until APPROVED", `engineering-lead.md:23`,
   sem teto; drains sem circuit-breaker).
5. Fosso construído↔live (classe de falha mais recorrente da história do
   projeto; neste momento 0.27.1 não está live).
6. Sem métrica de sucesso de tarefa — impossível saber se 1–5 melhoram.

## 8. Engenharia de contexto

Fluxo push-heavy: orquestrador cola conteúdo verbatim nas delegações; workers
leem o repo por conta; artefatos em disco fazem a comunicação durável — **a
coordenação já é majoritariamente artifact-based** (bom). Problemas: (a)
redescoberta — triage fan-outa 1 Explore/card e cada um reaprende o repo; a
topologia `docs` produz exatamente o mapa necessário (`docs/_survey/*`) e
nenhum agente de build a consome (verificado: zero referências cruzadas); (b)
prompt fixo grande independentemente do tamanho da tarefa; (c) redundância
skill/agente/hook (defesa em profundidade intencional, mas só o hook segura —
as outras cópias custam tokens sempre); (d) handoff NOTE é prosa — mais campos
estruturados verificáveis reduziriam a classe "fato stale".

**Maiores alavancas:** pacote de contexto por repo (`repo-map.yaml` cacheado)
e pacote de contexto por tarefa (payload de delegação com schema).

## 9. Decomposição e planejamento

Dois níveis: programa→itens (`plan.yaml` ordenado com `why` obrigatório — a
*ordem é o dado*; desenho excelente) e story→tasks (TASK.md com seams
nomeados). Dependências: `blocked_by` no plano; entre tasks, heurística de
paths sobrepostos (sem grafo explícito). Replanejamento: humano-mediado
(`/next` nomeia divergências, nunca absorve — epistemicamente correto).
Fraquezas: decomposição acontece uma vez por card; trabalho oculto vira "Scope
captured" mas não realimenta o plano; o single-track nunca rodou num board
vivo. Veredito: planos adaptativos com humano no loop, acima da média; elo
fraco é a granularidade fixa story→task.

## 10. Sub e sobre-agentamento (build-hex)

- planning-lead + epic-author + product-manager: **sobre-agentado** para card
  já refinado — colapsar num planner que fan-outa só em card abstrato.
  `integration-analyst` (modo prescritivo de spec E2E) tem valor único.
- domain/api/adapter-dev: separação existe para servir o path-lock por camada;
  num diff coeso cross-camada vira 3 handoffs. Trade-off real, hoje aceitável.
- refactor-advisor: **candidato a fusão** no code-reviewer (advisory, nunca
  bloqueia) ou passe batch por story.
- security-reviewer: por gatilho (diff toca auth/input/dados), não sempre.
- qa-engineer, code-reviewer, completion-auditor, proof-reviewer,
  atlassian-expert, engineering-lead: **manter** — são onde a independência
  paga os tokens.
- Sub-agentamento: nenhum caso. O que falta é *roteador* de pipeline, não
  agente novo.

## 11. Inteligência de repositório

Praticamente inexistente como camada: cada spawn faz Grep/Glob do zero; o
conhecimento por repo é CLAUDE.md, `build-hex.yaml` (bom exemplo do que quero
mais), `board-flow.yaml`, handoffs. Oportunidade barata: `.claude/repo-map.yaml`
(~1-2k tokens: módulos, comandos de verify por escopo, convenções de teste,
entrypoints, hot files), gerado sob demanda, validade no doctor, anexado a toda
delegação. Não é índice vetorial — é sumário estruturado.

## 12. Eficiência e custo

Sem contabilidade de tokens (telemetria não registra uso). Estruturalmente:
card build-hex feliz ≈ 1 + N×4 + 2 + 1-2 invocações Opus/Sonnet; card trivial
paga ~8 onde 2-3 bastariam. Roteamento de modelo estático; Haiku não usado
(candidatos: buscas de evidência do triage, formatação de summary, higiene de
sessão). Maior fonte histórica de retry é infraestrutural (baseline stale,
reactor Maven, cache) — já atacada por hooks; boa priorização.

## 13. Paralelismo

Intra-sessão: fan-out Explore no triage, dev workers em worktrees com
classificação de conflito no merge (decomposition-error / scope-creep /
semantic — `engineering-lead.md:73-75`, muito bom). Inter-sessão: Maestro —
superfícies disjuntas via `cepa-dor`, merge train com verify pós-merge, teto =
atenção humana. Desenho conservador correto; risco = não validado + dependência
herdr + duas casas de worktree. Guard-rail cultural certo: floor D7 (≥4).

## 14. Recuperação de falhas

Forte: checkpoint por turno (crash-proof), autonomous-resume que não re-executa
aprovadas, wave-state em toda transição + resume idempotente que reconcilia
contra a realidade, WIP-autosave, resgate de artefatos (0.27.1, não live).
Lacunas: sem orçamento de retry; malformed output tratado ad-hoc; ausência
tardia de `.claude/cards/<KEY>.yaml` só o proof-reviewer trata.

## 15. Fronteira humano/autonomia

Madura: estratégico sempre humano (waiver, Won't Do por card, ordem aprovada,
`human_pending` só o humano fecha), mecânico automatizado; `needs-human-motivos`
separa decisão de infraestrutura caída. Problema já diagnosticado por vocês
(piloto Gauntlet 2): atrito tático — confirmações em série treinam aprovação
cega. A direção escolhida (funil `decide` + `detect:` + attestations) é a
correta; depende do spike PreToolUse-em-AskUserQuestion.

## 16. Avaliação e benchmarking — o elo mais fraco

Existe: testes de contrato de prompt (regressão de texto), telemetria de gates,
Gauntlet (design pontual, ~600k tokens/rodada). Não existe: suíte de tarefas
repetíveis, taxa de sucesso, custo por tarefa, taxa de intervenção, taxonomia
de falhas. Proposta: 8–12 golden tasks (cards já resolvidos com
`acceptance_cmd`), runner via Workflow, métricas pass/invocações/tokens/
bloqueios/intervenções.

## 17. Alavancagem de Claude Code

Nota alta; quirks documentados são um ativo. Pontos: (a) **5 cópias de
path-lock/bash-path-lock** — gerar do template no install; (b) `/branch`+
`/return` — manter para o caso interativo, não expandir; (c) gatekeeper do
Maestro — reavaliar contra sandbox nativo antes de investir mais; (d)
dependência mais perigosa: payload de hook / `agent_type` sem contrato estável
do CC — vale teste de contrato automático pós-upgrade.

## 18. Arquitetura de prompts

Melhor: contratos de saída explícitos, enums fechados, regras com o porquê e o
incidente de origem (resiste a drift). Pior: volume + lógica determinística em
prosa. **Prompt→código** (padrão já provado: `cepa-dor`, guards): reconciliação
do `/next` (a tabela de 5 divergências é um algoritmo), merge de plano do
triage (passo 9), precedência de escopo/argumentos (repetida em drain/triage/
execute), montagem do Implementation Summary. **Código→raciocínio:** quase
nada; `session-subject` ("lexical propõe, modelo dispõe") é o equilíbrio certo.

## 19–21. Ambiente, verificação, estado — síntese

- Feedback: sinal de build rápido, determinístico, auto-capturado. Falta
  granularidade (baseline por módulo/escopo). `maven-reactor-guard` = classe
  rara "impedir feedback falso"; expandir (npm workspaces, pytest cache).
- Verificação: estado da arte do repo. Cuidado: custo do proof-gate linear com
  o diff; política de amostragem "highest-risk hunks" está em prosa — virar
  política explícita (score por hunk) + cache de greens.
- Estado/memória: separação limpa efêmero/trabalho/durável. Expertise com cap
  20 + `principle` responde os 4 critérios de memória justificada; ROI nunca
  medido — experimento antes de expansão.

## 22. Manutenibilidade

Hooks: limpos, stdlib-only, fail-open/closed escolhido por caso, telemetria
fail-silent, testes sem deps. Riscos: quintuplicação dos locks; 2 testes
vermelhos por pytest ausente no Python local; `multi-agent/` com 2.0 GB de
protótipo legado no working tree (untracked, mas vive no Insync);
`agents-overview.md` (43 KB) provavelmente driftando.

## 23. Segurança

Modelo de ameaça correto e raro: o adversário é o próprio agente sob pressão
de completar; camadas nasceram de incidentes reais. Buraco aberto conhecido:
**interpreter bypass** (`python3 -c` escreve o que `cp` não pode) — camada 1
aprovada via Gauntlet, não construída. Assunção nomeada: conteúdo de card Jira
entra verbatim em delegações (injeção via card não tratada; risco baixo em
board próprio).

## 24. Tetos de capacidade

Minutos–dezenas de minutos: ok. Horas: teto = contexto do orquestrador
(handoff amortece, re-boot custa). Múltiplos workstreams: Maestro é a resposta,
até validar o teto é 1 sessão. Repos grandes: sem repo-intel, descoberta cresce
superlinear. Refactors largos: path-lock por identidade-camada atrapalha
mudança coesa cross-lane (limite estrutural do modelo de lock). Fundamental: o
orquestrador como sessão interativa única — sem scheduler persistente fora de
sessão (aceitável enquanto o produto é "um dono, um teclado").

## 25–26. Técnicas modernas: adotar / não adotar

**Adotar:** extração determinística; repo-map; roteamento por tarefa;
orçamentos de retry; golden tasks; tokens por delegação; Haiku em estágios
mecânicos; single-source dos locks. **Não adotar ainda:** RAG vetorial (o
repo-map cobre 80% com ~0 infra); grafo dinâmico + scheduler (linear não
saturou); reflexão genérica (os gates já são a versão que paga o que vale);
memória episódica ampliada (medir ROI da atual); daemon do Maestro (gatilho
medido já definido); swarms.

---

## 27. Recomendações P0–P3

### P0-1 · Fechar o interpreter-bypass do bash-path-lock (camada 1 já aprovada)
Problema: escrita arbitrária via `python3 -c` passa pelo lock que existe para
forçar delegação. Evidência: BACKLOG + piloto Gauntlet 1 (WEGO-1936).
Consequência: o enforcement central vira filtro de ingenuidade. Mudança:
deny-by-default de 4 baldes (design pronto), com exceção para perturbação
legítima. Validação: testes RED do piloto + replay do WEGO-1936.

### P0-2 · Orçamentos de iteração nos loops de qualidade e drains
Problema: "iterate until APPROVED" sem teto; falha idêntica repetida não é
detectada. Mudança: teto (ex.: 3 ciclos/task) + "mesmo erro 2× → BLOCKED com
diagnóstico", no prompt E num contador mecânico. Validação: injetar teste
impassável e medir em quantos ciclos o sistema para.

### P0-3 · Single-source dos hooks quintuplicados
Template em `common/` + geração por topologia no `bin/install.sh` (só
`PLUGIN_NAME`+`ALLOWED_WRITES` variam). Mata a classe "4 de 5 consertadas".
Validação: teste que diffa as cópias geradas contra o template.

### P0-4 · Estreitar o fosso construído↔live
`session-registry` (SessionStart) compara versão repo vs cache sempre (o
doctor já sabe) e injeta 1 linha com o delta e o que NÃO está valendo.
Trivial; mata a classe "decisão sobre fato stale".

### P1-1 · Extrair o núcleo determinístico dos comandos para `cepa` CLI
Reconciliação do `/next`, merge de plano do triage, precedência de escopo,
montagem do Summary → subcomandos Python chamados pelo prompt (padrão
`cepa-dor`). Estimativa: 30–50% menos tokens nos comandos maiores (as seções
algorítmicas são ~metade das 262 linhas do triage). Testes unitários
substituem contrato de prosa nessas seções.

### P1-2 · Camada de inteligência de repositório (`repo-map.yaml`)
Sumário por repo (~1-2k tokens), gerado por comando, validade no doctor,
injetado em toda delegação. Validação: A/B em 5 cards — tokens de exploração
e nº de buscas por worker.

### P1-3 · Roteamento de pipeline por tarefa
Score (diff previsto × camadas × tipo) escolhe lane leve vs loop completo no
mesmo projeto; refactor-advisor por story; security por gatilho. Gates
universais intocados. Guarda: bounce-rate do proof não pode subir.

### P1-4 · Suíte de avaliação do harness (golden tasks)
8–12 cards resolvidos re-executáveis em worktree limpa com `acceptance_cmd`;
runner via Workflow; métricas pass/invocações/tokens/bloqueios/intervenções.

### P1-5 · Atrito de decisão fase 1 — manter a ordem do plano (spike primeiro).

### P2
Tokens por delegação na telemetria; fundir planning-trio em cards concretos;
expertise injetada no prompt de delegação (economiza um turn de boot);
baseline de build por escopo; teste de contrato do payload de hook pós-upgrade
do CC; agentes de build consumirem os ledgers do `docs`.

### P3
Prune de `multi-agent/` (2.0 GB no Insync); regenerar `agents-overview.md` de
fonte; pytest vermelho local; unificar as duas casas de worktree do Maestro.

---

## 28. Arquitetura-alvo

```
┌────────────────────────── humano ──────────────────────────┐
│  decisões estratégicas · ordem do plano · waivers · debrief │
└──────────────┬─────────────────────────────────────────────┘
               │
┌──────────────▼───────────────┐   ┌────────────────────────┐
│ ORQUESTRAÇÃO (sessão CC)     │   │ maestro (multi-sessão) │
│ comandos finos → cepa CLI    │◄──┤ validar antes de crescer│
└──────┬───────────────┬───────┘   └────────────────────────┘
       │ delegação c/  │
       │ pacote de ctx │
┌──────▼──────┐ ┌──────▼───────────────────────────────┐
│ AGENTES     │ │ CAMADA DETERMINÍSTICA (cepa CLI+hooks)│
│ planner*    │ │ dor · next-reconcile · plan-merge     │
│ eng-lead    │ │ summary-build · verdict-guards        │
│ dev(s)      │ │ locks (fonte única) · gate-advance    │
│ qa          │ │ retry-budget · telemetry              │
│ auditor ✦   │ └──────┬────────────────────────────────┘
│ proof ✦     │        │
└──────┬──────┘ ┌──────▼──────────┐  ┌───────────────────┐
       │        │ ESTADO/ARTEFATOS│  │ REPO-INTEL (novo) │
       └───────►│ plan.yaml cards │  │ repo-map.yaml     │
                │ proof/acceptance│  │ (docs ledgers)    │
                │ handoffs builds │  └───────────────────┘
                └──────┬──────────┘
                ┌──────▼──────────────────────────────────┐
                │ AVALIAÇÃO (novo): golden tasks · métricas│
                └──────────────────────────────────────────┘
   ✦ = gates independentes — intocáveis   * = trio de planning fundido
```

**Keep:** gates de prova/aceitação, malha last-build, enforcement por
capacidade, plan.yaml, handoff contínuo, expertise, telemetria, doctor, dor.
**Refine:** comandos (CLI), engineering-lead (orçamentos), Maestro (validar
wave 1). **Merge:** planning-trio; refactor-advisor→code-reviewer.
**Replace:** 5 cópias de lock→template gerado. **Remove:** `multi-agent/`;
conter `/branch`+`/return`. **Introduce:** repo-map, golden tasks,
retry-budget, token accounting, roteador de pipeline.

## 29. Roadmap

- **Estágio 1 (endurecer):** P0-1..4 + prune P3. Sucesso: bypass RED nos
  testes; zero episódios de fato stale de versão; diff-zero entre locks.
- **Estágio 2 (capacidade):** P1-1, P1-2, P1-3, tokens na telemetria (antes do
  roteador, para medir o corte). Risco: reescrever asserções dos testes de
  contrato para "chama o CLI". Sucesso: custo/card ↓, bounce do proof estável.
- **Estágio 3 (avaliação):** P1-4, taxonomia de falhas, gate de regressão de
  harness antes de release de plugin. Sucesso: primeira mudança de prompt
  rejeitada por número, não por opinião.
- **Estágio 4 (avançado, só com gatilho):** Maestro wave real; /common:gauntlet;
  daemon só se o Maestro validado saturar; lanes por task no path-lock só se
  refactors largos virarem demanda real.
- **Não construir ainda:** RAG vetorial, replanejador autônomo, memória
  episódica ampliada, swarms, LLM no caminho de permissão (D5 — manter).

## Top 10 por alavanca

1. Golden-task eval suite (P1-4) — destrava a medição de todas as outras.
2. Fechar interpreter-bypass (P0-1).
3. `cepa` CLI para o núcleo determinístico (P1-1).
4. `repo-map.yaml` nas delegações (P1-2).
5. Aviso de versão repo↔cache no SessionStart (P0-4).
6. Orçamentos de retry mecânicos (P0-2).
7. Roteador de pipeline por tarefa (P1-3).
8. Fonte única dos locks (P0-3).
9. Tokens por delegação na telemetria (P2).
10. Fusão planning-trio + refactor-advisor→reviewer.

## Se só 3 mudanças

1. **Golden-task eval suite** — muda como as mudanças são feitas.
2. **`cepa` CLI** — maior corte simultâneo de tokens, drift e superfície de
   prompt, com padrão já provado internamente.
3. **Interpreter-bypass camada 1** — a promessa central ("força delegação")
   precisa ser verdade; é o único ponto onde a distância entre o que a Cepa
   afirma e o que garante é conhecida e aberta.

## Experimentos

- **E1 repo-map:** hipótese: ↓≥30% tokens de exploração/worker. Bench: 5 cards
  do wego re-executados em worktree limpa; controle: sem o mapa. Falha: corte
  <10% ou regressão de pass.
- **E2 roteador:** cards ≤~30 linhas na lane leve sem subir bounce do proof.
  Bench: 10 cards pequenos históricos; sucesso: invocações ↓≥50%, bounce igual.
- **E3 comando fino:** `/next` via `cepa next-reconcile` = decisões idênticas.
  Bench: 10 estados sintéticos plano×board (5 divergências ×2). Falha: qualquer
  divergência absorvida em silêncio.
- **E4 ROI da expertise:** 5 tarefas com/sem o arquivo do agente. Sucesso: ≥1
  decisão muda na direção dos principles. Falha: zero → congelar memória.
- **E5 retry-budget:** card impassável consome ≤40% dos tokens atuais até
  escalar (teto 3 + erro repetido 2×).

---

## Pendências desta revisão (decisões abertas com o dono)

1. Rodar `/common:doctor` (2d sem rodar; 0.27.1 não live). Recomendado sim.
2. ~~Salvar este relatório em docs/internals/~~ — feito (este arquivo).
3. Adicionar ao BACKLOG os 4 itens sem lar: P0-2 (retry-budget), P0-3 (fonte
   única dos locks), P0-4 (aviso de versão no SessionStart), P1-4 (golden
   tasks). Recomendado sim; aguardando confirmação. As demais recomendações já
   têm item existente (bash-path-lock camada 1, atrito, gauntlet).
