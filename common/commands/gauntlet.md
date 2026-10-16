---
description: Competição de designs com julgamento cego (Gauntlet Loop) para uma decisão de design ABERTA — escreve a barra de qualidade antes, faz N builders isolados produzirem designs de ângulos distintos, 3 juízes cegos ranqueiam por Borda, o vencedor é revisado e checado contra a barra, e o resultado vai para docs/internals/gauntlet-<slug>.md. Opt-in e caro (~600k tokens). Para julgar UM artefato já escrito por várias lentes use /common:advisors.
argument-hint: <alvo> [--builders=3] [--angulos=a,b,c] [--slug=<slug>]
interaction: routine
---

# /common:gauntlet

## Purpose

Uma decisão de design aberta costuma sair com o primeiro desenho que alguém
pensou. Este comando faz o contrário: escreve **antes** a barra do que seria um
bom desenho, manda N builders **isolados** produzirem desenhos concorrentes de
ângulos diferentes, e deixa 3 juízes **cegos** (que só veem objetivo, barra e
desenhos anonimizados) ranquearem. O vencedor é revisado contra as lacunas que
os juízes apontaram e checado de novo contra a barra. Sai um documento durável
com o caminho todo, não só a conclusão.

## Variables

- `$ARGUMENTS` — `<alvo>` (obrigatório): texto livre descrevendo a decisão, OU o
  título de uma seção `## ` do `BACKLOG.md` (nesse caso a seção inteira vira o
  contexto dos agentes).
- `--builders=N` — número de builders (default 3). Cada um recebe um ângulo;
  se N passar do número de ângulos, eles ciclam.
- `--angulos=a,b,c` — escolhe os ângulos por `key` no registry (default:
  `mecanismo-novo`, `estender-o-que-existe`, `livre`).
- `--slug=<slug>` — nome do arquivo de saída (default: kebab-case do `<alvo>`).

## Instructions

Você é o orchestrator. Você monta o contexto, dispara o workflow, grava o
documento e relata — a execução dos 9 agentes é do script. O registry de ângulos
vive em `common/gauntlet/angulos.md` (via plugin:
`${CLAUDE_PLUGIN_ROOT}/gauntlet/angulos.md`) e o script canônico em
`${CLAUDE_PLUGIN_ROOT}/gauntlet/gauntlet.workflow.js`.

## Workflow

### 0. Piso de uso

Este comando é **opt-in e caro**: ~600k tokens, ~13 minutos, 9 agentes no default
(barra 1 + builders 3 + juízes 3 + revisor 1 + checagem 1). Só rode
se o usuário pediu explicitamente (ou confirma depois de ouvir o custo).

**Recuse** e aponte o caminho certo quando o alvo for:

- **código de correção provável** (dá para provar com teste, suíte ou build):
  o juiz certo é o gate de prova, não um painel de opiniões;
- **tarefa mecânica** (rename, ajuste cuja forma só tem uma resposta);
- decisão **trivial ou reversível a custo baixo**;
- decisão que **não dá para julgar em texto** (depende de medir algo no mundo).

O Gauntlet serve a decisão de design **aberta**, em que vários desenhos
plausíveis competem e um leitor atento consegue julgá-los pelo texto.

### 1. Montar o CONTEXT

Se o `<alvo>` bate com um título `## ` do `BACKLOG.md`, cole essa seção inteira
como contexto. Senão, use o texto do alvo e leia o que ele cita. O contexto
precisa ter: (a) o **objetivo** em poucas frases; (b) **o que já existe e deve
ser estendido**, não duplicado (com caminhos); (c) a **filosofia do harness**
relevante (enforcement em profundidade: regra só em prosa decai, gate mecânico
dura; gates independentes do executor); (d) a lista de **arquivos para ler**
(`reads`). Incidentes reais que motivam a decisão entram aqui: a barra e os
builders trabalham em cima deles.

### 2. Escolher os ângulos

Leia `${CLAUDE_PLUGIN_ROOT}/gauntlet/angulos.md`. Sem `--angulos`, use o
default (`mecanismo-novo`, `estender-o-que-existe`, `livre`). Com `--angulos`,
selecione por `key` (key fora do registry: liste as válidas e pare). Cada
builder recebe um ângulo; `--builders` maior que o número de ângulos cicla, menor
usa os N primeiros. Monte `angles: [{key, brief}]` com o `brief` do registry.

### 3. Executar o workflow

Passe à **Workflow tool** o script
`${CLAUDE_PLUGIN_ROOT}/gauntlet/gauntlet.workflow.js` (lido do arquivo, sem
alterar) com `args` = `{repo, goal, context, angles: [{key, brief}], reads: [paths]}`.
O `repo` é a raiz do repositório atual (`git rev-parse --show-toplevel`).

Não reescreva o script por invocação: ele é a cópia canônica dos dois pilotos
validados (`docs/internals/gauntlet-pilot-*.workflow.js`). O que varia vai em
`args`. O `args` pode chegar como string JSON — o script tem a guarda.

As cinco etapas que o script executa, nesta ordem:

1. **Barra** — um agente escreve 5 a 8 critérios julgáveis (com rubrica) e uma
   referência ambiciosa, antes de qualquer design existir.
2. **Builders isolados** — N agentes em paralelo, cada um com um ângulo; nenhum
   vê a saída de outro.
3. **Juízes cegos** — 3 juízes recebem só objetivo + barra + designs
   anonimizados (A, B, C...), **em ordem rotacionada por juiz**, pontuam cada
   critério de 0 a 10 e ranqueiam.
4. **Borda e revisão** — soma de pontos (1º lugar = N pontos, onde N é o número
   de designs); o vencedor é revisado contra as lacunas apontadas, com enxertos
   de ideias superiores dos rivais.
5. **Checagem final** — um agente de contexto novo confere se o design revisado
   cumpre a barra (todo critério >= 7/10) e lista o que sobrou.

Se a Workflow tool **não estiver disponível** nesta sessão, degrade: dispare os
mesmos agentes por chamadas Agent manuais **na mesma mensagem** (builders em
paralelo, depois juízes em paralelo), com os mesmos prompts do script,
mantendo o isolamento dos builders e a cegueira dos juízes.

O script devolve `{bar, designs, full_designs, verdicts, borda_points, winner,
revised_design, final_check}`; em falha devolve `{error, designs}` (menos de 2
designs, ou nenhum juiz respondeu): relate a falha e pare, sem inventar vencedor.

### 4. Gravar a saída durável

Escreva `docs/internals/gauntlet-<slug>.md` (slug = `--slug` ou kebab-case do
`<alvo>`) com a estrutura dos pilotos:

- cabeçalho: `# Gauntlet — <alvo>`, linha com id do run, data, agentes, tokens e
  minutos, e uma linha de método;
- `## Barra de qualidade (escrita antes de qualquer design)` — cada critério e a
  referência;
- `## Designs concorrentes e julgamento` com um `### Design A (<ângulo>) — <título>`
  por design (conteúdo completo) e `### Vereditos dos N juízes cegos`: ranking de
  cada juiz, **tabela de pontos Borda com a conta mostrada** (1º = N pontos, 2º =
  N-1, ...; soma por design) e as maiores lacunas;
- `## Design final (vencedor X revisado, com enxertos de ...)`;
- `## Checagem final contra a barra` — `bar_met`, lacunas restantes, nota.

**Vencedor:** maior soma Borda. Empate: vence o design que ficou em 1º lugar com
mais juízes; persistindo, o primeiro na ordem dos designs — e o relatório
**nomeia o empate**.

### 5. Relatar (pt-BR, formato `plain-report`)

Siga o skill `plain-report`: abertura leiga, `**Pra você:**`, detalhe técnico,
`### Decisões e próximos passos`. Explique em linguagem leiga quem venceu e por
quê, com a conta Borda, diga se a barra foi cumprida e o que sobrou. Termine com
perguntas fechadas numeradas, cada uma com `Recomendo sim/não` (ex.: "Abro um
item de fila para implementar o design vencedor?"). Nunca devolva a decisão
sem recomendação.

### 6. Telemetria

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_telemetry.py" emit gauntlet_run \
  builders=<n> judges=3 winner=<angulo> bar_met=<true|false>
```

(Se `${CLAUDE_PLUGIN_ROOT}` não estiver no ambiente, use o path absoluto de
`common/hooks/_telemetry.py`.)

## Notes

- **Isolamento é inegociável.** Builders nunca veem uns aos outros; juízes só
  veem objetivo + barra + designs anonimizados com ordem rotacionada. Não passe a
  saída de um agente a outro fora do fluxo do script.
- **O comando nunca implementa o design vencedor.** Ele grava o documento e
  relata; implementar é outro item, decidido pelo dono.
- **Piso de uso repetido porque importa:** código provável ou tarefa mecânica
  não merece Gauntlet (passo 0).
- **Relação com `/common:advisors`:** o advisors julga **um** artefato que já
  existe, por N lentes, e sintetiza nomeando as discordâncias. O gauntlet
  **gera** N artefatos concorrentes e os julga comparativamente, às cegas, com
  vencedor por Borda. Use o advisors para revisar uma decisão escrita; use o
  gauntlet para escolher entre desenhos que ainda não existem.
- O script não usa `Date.now` nem `Math.random`: o run é determinístico no que
  depende do orchestrator.
