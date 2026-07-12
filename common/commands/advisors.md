---
description: Painel de advisors sobre um artefato de decisão (doc de design, ADR, plano, PR) — fan-out paralelo e ISOLADO de lentes de revisão (5 fixas + até 2 especialistas da área), seguido de síntese que NOMEIA as discordâncias entre lentes em vez de mediar. Prospectivo — roda ANTES de fechar a decisão. Para revisar decisões passadas de um run use /common:debrief; para caçar bugs no diff use /code-review.
argument-hint: <artefato> [--area=seguranca|api-contrato|dados|ux|arquitetura] [--lentes=a,b,c]
---

# /common:advisors

## Purpose

Um olhar só tem ponto cego. Dado um artefato de decisão, este comando spawna um
painel de revisores em **paralelo e isolados** — cada um com uma lente fixa, sem
ver a saída dos outros (isolamento é o que evita convergência prematura) — e
depois sintetiza **nomeando as discordâncias** entre as lentes, nunca mediando
nem escolhendo em silêncio. O achado mais valioso de um painel costuma ser
exatamente onde duas lentes discordam.

## Variables

- `$ARGUMENTS` — `<artefato>` (path ou referência de PR; obrigatório),
  `--area=<x>` (declara a área e pula a confirmação de inferência),
  `--lentes=a,b,c` (monta o painel à mão; sobrepõe default E especialistas).

## Instructions

Você é o orchestrator. Você monta o painel, dispara o workflow e **sintetiza
pessoalmente** — a síntese não é delegada a um agente. Aplique o skill
`name-the-disagreement` na síntese. O registry de lentes vive em
`common/advisors/lenses.md` (via plugin: `${CLAUDE_PLUGIN_ROOT}/advisors/lenses.md`).

## Workflow

### 0. Piso de uso

Antes de qualquer coisa, avalie: a decisão do artefato é **trivial ou
facilmente reversível**? (rename local, escolha de lib utilitária, ajuste que um
`git revert` desfaz sem dor). Se sim, **não convoque o painel** — diga isso ao
usuário ("essa decisão é reversível a custo baixo; um painel de 5+ agentes custa
mais do que errar e corrigir") e sugira seguir sem. Só prossiga se o usuário
insistir.

### 1. Ler o artefato

Leia o artefato inteiro. Se for referência de PR, leia o diff + descrição. Se o
path não existir, pare e diga.

### 2. Inferir a área + confirmar

Se `--area` foi passada: valide contra as áreas do registry (`seguranca`,
`api-contrato`, `dados`, `ux`, `arquitetura`) e **pule a confirmação**. Área
inválida → liste as válidas e pare.

Senão, **infira a área** do conteúdo do artefato (contratos e endpoints →
api-contrato; auth/segredos/superfície de ataque → seguranca; schema/volume/
retenção → dados; telas/fluxos de usuário → ux; componentes/deploy/acoplamento →
arquitetura; nada dominante → nenhuma área, painel só com as 5 default). Então
**confirme com o usuário antes do fan-out**:

> Parece decisão de **api-contrato** — painel: 5 default + consumidor-externo +
> versionamento-breaking-change (7 lentes). Ok? (ou me diga outra área / `--lentes=...`)

Aguarde a resposta. O usuário pode aceitar, trocar a área ou ditar as lentes.

### 3. Montar o painel

Leia `common/advisors/lenses.md` e monte a lista de lentes:

- **Default:** as 5 fixas (contrarian, fundamentalista, expansionista, outsider,
  executor) + **até 2** especialistas da área confirmada. **Teto absoluto: 7.**
- **`--lentes=a,b,c`:** sobrepõe tudo — use exatamente essas lentes (qualquer
  combinação de nomes do registry), ainda sob o teto de 7. Nome fora do registry
  → liste os válidos e pare.

Para cada lente, extraia do registry o `system-prompt-fragment` — ele é o perfil
do agente daquela lente.

### 4. Executar o fan-out (Workflow tool)

Grave o script abaixo em um arquivo temporário no scratchpad e passe-o à
**Workflow tool**, com o input montado no passo 3. Cada `agent()` roda isolado:
recebe o artefato, o perfil da própria lente e NADA das outras.

```javascript
export const meta = {
  name: "advisors-panel",
  description: "Fan-out paralelo e isolado de lentes de revisao sobre um artefato de decisao",
  phases: [{ title: "Pareceres" }],
};

// A Workflow tool entrega o input no global `args` — e pode entregá-lo como
// STRING JSON (observado no primeiro uso real). A guarda é obrigatória.
const A = typeof args === "string" ? JSON.parse(args) : args;
// A.artifact_path: path do artefato; A.artifact_content: conteúdo integral
// (ou diff+descrição, para PR); A.lenses: [{ name, profile }] — máx. 7,
// profile copiado verbatim do registry.

const lensOutputSchema = {
  type: "object",
  additionalProperties: false,
  required: ["lente", "achados", "veredito_da_lente", "premissas_que_desafio"],
  properties: {
    // a lente se identifica DENTRO do schema — enriquecer depois via .then()
    // não aparece no journal por agente e dificulta o debug
    lente: { type: "string" },
    achados: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: ["titulo", "severidade", "onde", "argumento"],
        properties: {
          titulo: { type: "string" },
          severidade: { type: "string", enum: ["critica", "alta", "media", "baixa"] },
          onde: { type: "string", description: "secao/linha/trecho do artefato" },
          argumento: { type: "string" },
        },
      },
    },
    veredito_da_lente: { type: "string", description: "uma frase: a posicao desta lente" },
    premissas_que_desafio: { type: "array", items: { type: "string" } },
  },
};

const reports = await parallel(A.lenses.map((lens) => () =>
  agent(
    [
      "Voce e UMA lente de um painel de advisors. Voce NAO ve as outras lentes; nao especule sobre elas.",
      "SEU PERFIL (encarne-o integralmente):",
      lens.profile,
      "ARTEFATO EM REVISAO (" + A.artifact_path + "):",
      "---",
      A.artifact_content,
      "---",
      "Revise o artefato EXCLUSIVAMENTE pela sua lente. Ancore cada achado em um trecho concreto do artefato ('onde').",
      "No campo 'lente' do JSON de saida, escreva exatamente: " + lens.name,
    ].join("\n\n"),
    { label: "lente:" + lens.name, phase: "Pareceres", schema: lensOutputSchema }
  )
));

return reports.filter(Boolean);
```

Notas de execução:

- Invoque a Workflow tool com este script no campo `script` e o input no campo
  `args` como objeto JSON: `{artifact_path, artifact_content, lenses: [{name,
  profile}]}` — `artifact_content` integral, `profile` copiado verbatim do
  registry (passo 3).
- O script é determinístico de propósito: sem `Date.now`, sem `Math.random`,
  `meta` como literal puro. Não o "melhore" com nada disso. O `return` top-level
  é válido no dialeto da Workflow tool (corpo roda em contexto async) — um
  `node --check` acusa "Illegal return statement" e isso NÃO é um erro real.
- Lições do primeiro uso real (2026-07-11, painel do P6): `args` pode chegar
  como string JSON (daí a guarda no topo); e a identidade da lente vai DENTRO
  do schema de saída, porque enriquecimento via `.then()` não aparece no
  journal por agente.
- Se a Workflow tool não estiver disponível nesta sessão, degrade para o
  equivalente manual: um `Task` por lente, **todos no mesmo bloco** (paralelo),
  cada um com o mesmo prompt do `agent()` acima. O isolamento e o schema JSON
  continuam obrigatórios.

### 5. Sintetizar (você, orchestrator — skill `name-the-disagreement`)

Com os N JSONs em mãos, produza a síntese. **Nunca medie, nunca escolha em
silêncio, nunca "todas têm razão".** Estrutura obrigatória:

> ## Painel de advisors — `<artefato>` (área: `<area>`, N lentes)
>
> **Vereditos por lente** — uma linha cada: `contrarian: "<veredito>"`, ...
>
> ### Convergências
>
> Achados que 2+ lentes apontaram de forma independente (isolamento torna a
> convergência um sinal forte). Cada um com as lentes que convergiram e o trecho
> do artefato.
>
> ### DISCORDÂNCIAS NOMEADAS
>
> Para cada conflito real entre lentes (vereditos opostos, premissas
> incompatíveis, mesmo trecho avaliado em direções contrárias):
>
> - **Lente A diz X** (cite o argumento dela) **vs. lente B diz Y** (idem).
> - **O que decide entre elas:** o critério ou informação que resolveria — e a
>   sua recomendação de sintetizador, se os inputs bastam para tê-la. Se não
>   bastam, diga exatamente o que falta. "Ambas têm um ponto" não é resolução.
>
> ### Propostas consolidadas priorizadas
>
> Lista ordenada (severidade × convergência) de mudanças concretas no artefato.
> Cada proposta rastreia às lentes que a motivaram. Propostas que dependem de
> uma discordância ainda aberta são marcadas como condicionais.

Achados de severidade `critica`/`alta` de uma lente só (sem convergência) ainda
entram nas propostas — convergência prioriza, não filtra.

### 6. Telemetria

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_telemetry.py" emit advisors_run \
  area=<area> lenses=<n-lentes> findings=<n-achados-total>
```

(`area=none` quando o painel rodou só com as default. Se `${CLAUDE_PLUGIN_ROOT}`
não estiver no ambiente, use o path absoluto de `common/hooks/_telemetry.py`.)

## Notes

- **Piso de uso (repetindo porque importa):** decisão trivial/reversível não
  merece painel. O comando aponta isso e sugere seguir sem (passo 0).
- **Isolamento é inegociável.** Não passe a saída de uma lente para outra, não
  rode as lentes em sequência "aproveitando contexto". A convergência
  independente é o que dá valor estatístico ao painel.
- **A síntese é do orchestrator**, não de um agente dedicado — para manter
  `name-the-disagreement` no nível de quem responde ao usuário.
- A saída é um **relatório com propostas** — o comando não edita o artefato.
  Aplicar as propostas é um passo seguinte, com aprovação do usuário.
- Prospectivo vs. retrospectivo: para decisões já tomadas num run autônomo, o
  ritual é `/common:debrief`. Para qualidade de código em diff, `/code-review`.
  Comparação completa em `docs/advisors.md`.
