---
description: Prova a superfície de UI/extensão do projeto pelo gate mecânico — delega ao ui-proof-reviewer, que sobe o app, roda os fluxos declarados em docs/ui-proof.yaml via Playwright (extensão Chrome unpacked incluída) e exige efeito verificável no backend, com prova green→red→green quando o diff da mudança é conhecido. Retorna PROVEN / UNPROVEN / NEEDS-HUMAN com relatório leigo em pt-BR. Sem manifesto, o comando não chuta — devolve NEEDS-HUMAN dizendo exatamente o que declarar. Com --draft, PROPÕE um esqueleto comentado de manifesto a partir da estrutura do repo (proposta explícita, nunca prova).
argument-hint: [fluxo | --all | --draft]
---

# /common:prove-ui

## Purpose

O `/board-flow:prove` fecha o gate do backend; este comando fecha o da
superfície onde o usuário sofre — SPA e extensão Chrome. Ele é
deliberadamente fino: **quem decide o veredito é o `common:ui-proof-reviewer`**,
a partir de evidência; o comando só resolve o escopo, delega e aplica o
contrato de relatório. O que provar mora no repo do projeto, em
`docs/ui-proof.yaml` (formato: `docs/ui-proof-manifest.md` no cepa). Morava em
`.claude/ui-proof.yaml` até 22/08/2026 e o agente ainda lê de lá quando o novo
não existe — mas `.claude/` é gitignored nesses projetos, então o manifesto ia
embora junto com a worktree da sessão.

## Variables

- `$ARGUMENTS` — o nome de UM fluxo declarado no manifesto (ex.:
  `registrar-acesso`), ou `--all` para todos. Vazio = `--all`.
  `--draft` = modo proposta: em vez de provar, PROPÕE um esqueleto de
  manifesto (ver passo 0).

## Instructions

Você é o orquestrador. Aplique `defense-in-depth`, `evidence-over-assumption`,
`scope-discipline`. Você NÃO decide o veredito — o `ui-proof-reviewer` decide,
mecanicamente, a partir dos statuses que ele mediu. Você não relaxa o
veredito, não re-roda fluxo "para confirmar", não edita o artifact.

## Workflow

### 0. Modo `--draft` — propor o manifesto, nunca prová-lo

Se `$ARGUMENTS` contém `--draft`, este run não prova nada — ele **propõe**.
Inspecione a estrutura do repo (um `manifest.json` de extensão? um
`package.json` com scripts `build`/`serve`/`preview`? um `docs/env.yaml`
com `up:`/`ports:`? rotas óbvias de SPA?) e escreva um esqueleto de
`docs/ui-proof.yaml` **comentado** em `docs/ui-proof.draft.yaml`
seguindo `docs/ui-proof-manifest.md` (do cepa): campos `up`, `base_url`,
`build`, `serve`, `extension_dir` quando aplicável, e um ou dois `flows`
placeholder com `steps`, `assert` (incluindo o `{nonce}` de frescor) e
`covers` — cada valor incerto marcado com `# TODO(humano):`.

Deixe explícito no arquivo e no relatório: **proposta explícita ≠ prova.**
O rascunho não vale como manifesto — o dono do produto revisa, ajusta e
renomeia para `docs/ui-proof.yaml`; até lá, o gate continua devolvendo
NEEDS-HUMAN por manifesto ausente. Isso não viola a doutrina "o agente não
inventa fluxos": inventar seria *provar* contra um chute; propor um rascunho
para o humano validar é o oposto. Pare aqui — não delegue ao
ui-proof-reviewer no modo `--draft`.

### 1. Resolver escopo e contexto de mudança

- Parse de `$ARGUMENTS`: um nome de fluxo, ou `--all`/vazio.
- **Contexto de diff (opcional, mas valioso):** se a conversa tem uma mudança
  em jogo (um card com `base_commit` em `.claude/cards/<KEY>.yaml`, um branch
  com diff contra a base, um Implementation Summary), passe-a adiante — é ela
  que habilita a prova green→red→green. Sem diff conhecido, o gate ainda roda
  os fluxos, mas a prova de perturbação sai `n/a` e o agente reporta isso.

### 2. Delegar ao ui-proof-reviewer

Delegue ao subagente `common:ui-proof-reviewer` com:

> Escopo: <fluxo nomeado | todos os fluxos do manifesto>
> Diff: <base_commit..HEAD + lista de arquivos tocados | "nenhum — rode sem perturbação">
> Slug: <card key se houver; senão um slug curto do branch/feature>
>
> Leia `docs/ui-proof.yaml` (ou `.claude/ui-proof.yaml`, se o repo ainda não
> moveu o manifesto), rode os fluxos em escopo conforme sua mecânica
> (preflight do Playwright, up via manifest/env.yaml, scripts em
> `docs/ui-proof/runs/`, efeito verificável obrigatório para prova forte,
> green→red→green onde o diff permitir) e grave
> `docs/proof/ui-<slug>.yaml`. Retorne o veredito computado.

Não rode Playwright você mesmo; não "adiante" passos do agente.

### 3. Aplicar o contrato de relatório

Repasse ao usuário o relatório do agente **verificando o contrato** antes:

- Veredito idêntico ao campo `verdict` do artifact (se divergir, isso é bug
  do agente — reporte a divergência, nunca escolha um dos dois).
- Em pt-BR; para CADA finding: 2 frases leigas → recomendação default →
  detalhe técnico por último. Se o agente devolveu jargão cru, é você quem
  traduz — o usuário nunca recebe "perturbation survived" sem a camada leiga.
- Asserções só-visuais que passaram aparecem como **evidência fraca**, nunca
  como prova — com a sugestão concreta de `assert.backend` a adicionar no
  manifesto.
- NEEDS-HUMAN por manifesto ausente vem com o esqueleto mínimo do
  `docs/ui-proof.yaml` a criar (campos `up`, `base_url`, `flows`) e o
  apontador para `docs/ui-proof-manifest.md` — e com a sugestão de rodar
  `/common:prove-ui --draft` para gerar um rascunho comentado a revisar.

### 4. Seam opcional de board (sem Jira aqui)

Este comando **não** toca Jira. Se o projeto tiver `board-flow.yaml` e o
veredito precisar virar transição de card, isso é decisão do orquestrador de
board (ex.: `/board-flow:prove` e afins) — mencione a possibilidade em uma
linha no fim do relatório quando detectar `board-flow.yaml` na raiz, e pare
aí.

## Verdicts

- **PROVEN** — todos os fluxos em escopo verdes com efeito verificável e,
  havendo diff, vermelhos sob perturbação. Nada a fazer além de seguir.
- **UNPROVEN** — comportamento declarado demonstravelmente não se sustenta
  (fluxo falhou, ou ficou verde com a mudança quebrada). Volta para o
  implementador com o finding.
- **NEEDS-HUMAN** — falta insumo (manifesto, toolchain, credencial, assert
  verificável, perturbação viável). A fila de decisão é sua — cada item vem
  com recomendação default.
