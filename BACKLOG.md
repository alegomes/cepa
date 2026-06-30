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
