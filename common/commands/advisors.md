---
description: Panel of advisors over a decision artifact (design doc, ADR, plan, PR) — a parallel and ISOLATED fan-out of review lenses (5 fixed + up to 2 domain specialists), followed by a synthesis that NAMES the disagreements between lenses instead of mediating. Prospective — runs BEFORE the decision is closed. To review past decisions of a run use /common:debrief; to hunt bugs in the diff use /code-review.
argument-hint: <artifact> [--area=seguranca|api-contrato|dados|ux|arquitetura] [--lentes=a,b,c]
interaction: routine
---

# /common:advisors

## Purpose

A single look has a blind spot. Given a decision artifact, this command spawns
a panel of reviewers **in parallel and isolated** — each one with a fixed lens,
without seeing the others' output (isolation is what prevents premature
convergence) — and then synthesizes by **naming the disagreements** between the
lenses, never mediating nor choosing silently. A panel's most valuable finding
is usually exactly where two lenses disagree.

## Variables

- `$ARGUMENTS` — `<artifact>` (path or PR reference; required),
  `--area=<x>` (declares the area and skips the inference confirmation),
  `--lentes=a,b,c` (assembles the panel by hand; overrides default AND
  specialists).

## Instructions

You are the orchestrator. You assemble the panel, launch the workflow and
**synthesize personally** — the synthesis is not delegated to an agent. Apply
the `name-the-disagreement` skill in the synthesis. The lens registry lives in
`common/advisors/lenses.md` (via the plugin: `${CLAUDE_PLUGIN_ROOT}/advisors/lenses.md`).

## Workflow

### 0. Usage floor

Before anything else, assess: is the artifact's decision **trivial or easily
reversible**? (a local rename, a choice of utility library, a tweak a
`git revert` undoes painlessly). If so, **do not convene the panel** — tell the
user so (in pt-BR, along the lines of "this decision is reversible at low cost;
a panel of 5+ agents costs more than getting it wrong and fixing it") and
suggest going ahead without it. Only proceed if the user insists.

### 1. Read the artifact

Read the whole artifact. If it is a PR reference, read the diff + description.
If the path does not exist, stop and say so.

### 2. Infer the area + confirm

If `--area` was passed: validate it against the registry's areas (`seguranca`,
`api-contrato`, `dados`, `ux`, `arquitetura`) and **skip the confirmation**.
Invalid area → list the valid ones and stop.

Otherwise, **infer the area** from the artifact's content (contracts and
endpoints → api-contrato; auth/secrets/attack surface → seguranca;
schema/volume/retention → dados; user screens/flows → ux;
components/deploy/coupling → arquitetura; nothing dominant → no area, panel
with only the 5 defaults). Then **confirm with the user before the fan-out**.
The rendered confirmation is in Brazilian Portuguese (pt-BR):

> Looks like an **api-contrato** decision — panel: 5 default + consumidor-externo +
> versionamento-breaking-change (7 lenses). Ok? (or tell me another area / `--lentes=...`)

Wait for the answer. The user may accept, change the area or dictate the
lenses.

### 3. Assemble the panel

Read `common/advisors/lenses.md` and build the list of lenses:

- **Default:** the 5 fixed ones (contrarian, fundamentalista, expansionista,
  outsider, executor) + **up to 2** specialists from the confirmed area.
  **Absolute ceiling: 7.**
- **`--lentes=a,b,c`:** overrides everything — use exactly those lenses (any
  combination of names from the registry), still under the ceiling of 7. A name
  outside the registry → list the valid ones and stop.

For each lens, extract its `system-prompt-fragment` from the registry — it is
the profile of that lens's agent.

### 4. Run the fan-out (Workflow tool)

Write the script below to a temporary file in the scratchpad and pass it to the
**Workflow tool**, with the input built in step 3. Each `agent()` runs
isolated: it receives the artifact, its own lens's profile and NOTHING from the
others.

```javascript
export const meta = {
  name: "advisors-panel",
  description: "Fan-out paralelo e isolado de lentes de revisao sobre um artefato de decisao",
  phases: [{ title: "Pareceres" }],
};

// The Workflow tool delivers the input in the global `args` — and may deliver
// it as a JSON STRING (observed on the first real use). The guard is mandatory.
const A = typeof args === "string" ? JSON.parse(args) : args;
// A.artifact_path: the artifact's path; A.artifact_content: full content
// (or diff+description, for a PR); A.lenses: [{ name, profile }] — max. 7,
// profile copied verbatim from the registry.

const lensOutputSchema = {
  type: "object",
  additionalProperties: false,
  required: ["lente", "achados", "veredito_da_lente", "premissas_que_desafio"],
  properties: {
    // the lens identifies itself INSIDE the schema — enriching it later via
    // .then() does not show up in the per-agent journal and makes debugging harder
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

Execution notes:

- Invoke the Workflow tool with this script in the `script` field and the input
  in the `args` field as a JSON object: `{artifact_path, artifact_content,
  lenses: [{name, profile}]}` — `artifact_content` in full, `profile` copied
  verbatim from the registry (step 3).
- The script is deterministic on purpose: no `Date.now`, no `Math.random`,
  `meta` as a pure literal. Do not "improve" it with any of that. The top-level
  `return` is valid in the Workflow tool's dialect (the body runs in an async
  context) — a `node --check` reports "Illegal return statement" and that is
  NOT a real error.
- Lessons from the first real use (2026-07-11, the P6 panel): `args` may arrive
  as a JSON string (hence the guard at the top); and the lens's identity goes
  INSIDE the output schema, because enrichment via `.then()` does not show up
  in the per-agent journal.
- If the Workflow tool is not available in this session, degrade to the manual
  equivalent: one `Task` per lens, **all in the same block** (parallel), each
  with the same prompt as the `agent()` above. Isolation and the JSON schema
  remain mandatory.

### 5. Synthesize (you, the orchestrator — `name-the-disagreement` skill)

With the N JSONs in hand, produce the synthesis. **Never mediate, never choose
silently, never "they are all right".** Mandatory structure — the rendered
synthesis is in Brazilian Portuguese (pt-BR), and the section labels below
(`Painel de advisors`, `Vereditos por lente`, `Convergências`,
`DISCORDÂNCIAS NOMEADAS`, `O que decide entre elas`, `Propostas consolidadas
priorizadas`) stay verbatim:

> ## Painel de advisors — `<artifact>` (area: `<area>`, N lenses)
>
> **Vereditos por lente** (verdicts per lens) — one line each: `contrarian: "<verdict>"`, ...
>
> ### Convergências
>
> (Convergences.) Findings that 2+ lenses pointed out independently (isolation
> makes convergence a strong signal). Each with the lenses that converged and
> the artifact snippet.
>
> ### DISCORDÂNCIAS NOMEADAS
>
> (Named disagreements.) For each real conflict between lenses (opposite
> verdicts, incompatible premises, the same snippet assessed in opposite
> directions):
>
> - **Lens A says X** (cite its argument) **vs. lens B says Y** (same).
> - **O que decide entre elas:** (what decides between them) the criterion or
>   information that would settle it — and your recommendation as synthesizer,
>   if the inputs are enough to have one. If they are not, say exactly what is
>   missing. "Both have a point" is not a resolution.
>
> ### Propostas consolidadas priorizadas
>
> (Consolidated, prioritized proposals.) An ordered list (severity ×
> convergence) of concrete changes to the artifact. Each proposal traces back
> to the lenses that motivated it. Proposals that depend on a still-open
> disagreement are marked as conditional.

Findings of severity `critica`/`alta` from a single lens (no convergence) still
go into the proposals — convergence prioritizes, it does not filter.

### 6. Telemetry

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/_telemetry.py" emit advisors_run \
  area=<area> lenses=<n-lentes> findings=<n-achados-total>
```

(`area=none` when the panel ran with only the defaults. If `${CLAUDE_PLUGIN_ROOT}`
is not in the environment, use the absolute path of `common/hooks/_telemetry.py`.)

## Notes

- **Usage floor (repeating because it matters):** a trivial/reversible decision
  does not deserve a panel. The command points this out and suggests going
  ahead without it (step 0).
- **Isolation is non-negotiable.** Do not pass one lens's output to another, do
  not run the lenses in sequence "reusing context". Independent convergence is
  what gives the panel its statistical value.
- **The synthesis belongs to the orchestrator**, not to a dedicated agent — to
  keep `name-the-disagreement` at the level of whoever answers the user.
- The output is a **report with proposals** — the command does not edit the
  artifact. Applying the proposals is a following step, with the user's
  approval.
- Prospective vs. retrospective: for decisions already taken in an autonomous
  run, the ritual is `/common:debrief`. For code quality in a diff,
  `/code-review`. Full comparison in `docs/advisors.md`.
