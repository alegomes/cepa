# Advisors — painel de perspectivas sobre uma decisão

`/common:advisors <artefato>` spawna um painel de revisores em **paralelo e
isolados** — cada um com uma lente fixa, sem ver a saída dos outros — sobre um
artefato de decisão (doc de design, ADR, plano, PR), e sintetiza **nomeando as
discordâncias** entre as lentes em vez de mediar ou escolher em silêncio.

Nasceu de uma revisão manual (Variante 3 do `wego-acesso`, 2026-06-28) em que 5
lentes independentes acharam, cada uma, o que as outras não viam — e a
discordância entre elas foi o achado mais valioso.

## Quando usar — e quando NÃO

| Ferramenta | Quando | Altitude |
|---|---|---|
| **`/common:advisors`** | ANTES de fechar uma decisão — o artefato existe, a decisão não está tomada | decisão (design/ADR/plano) |
| **`/common:debrief`** | DEPOIS de um run autônomo — revisar decisões já tomadas (keep/overrule) | decisão, retrospectivo |
| **`/code-review` / review-gate** | diff pronto — caçar bugs e qualidade no código | linha de código |
| **proof-gate** | card em Review — provar que o código faz o que diz | comportamento na superfície |

Em uma frase: advisors questiona se a **decisão está certa antes de virar
código**; os outros verificam o código depois.

**Piso de uso:** decisão trivial ou facilmente reversível não merece painel — o
próprio comando aponta isso e sugere seguir sem. Convoque advisors quando errar
sai caro: contrato publicado, migração de dados, estrutura que todo mundo vai
herdar.

## Como funciona

1. Lê o artefato e **infere a área** da decisão, confirmando com você antes do
   fan-out ("parece decisão de api-contrato — painel: 5 default +
   consumidor-externo + versionamento. Ok?"). `--area=<x>` pula a confirmação.
2. Monta o painel: **5 lentes fixas sempre** (contrarian, fundamentalista,
   expansionista, outsider, executor) + **até 2 especialistas** da área. Teto: 7.
   `--lentes=a,b,c` monta o painel à mão. Registry completo em
   `common/advisors/lenses.md`.
3. Fan-out **paralelo e isolado** via Workflow tool — cada lente devolve JSON
   estruturado (achados com severidade e localização, veredito, premissas que
   desafia).
4. O orchestrator sintetiza: **Convergências** (2+ lentes isoladas apontando o
   mesmo = sinal forte) / **DISCORDÂNCIAS NOMEADAS** (lente A diz X, lente B diz
   Y, e o que decide entre elas) / **Propostas consolidadas priorizadas**.

## Custo esperado

Um painel default são 5–7 agentes lendo o artefato inteiro em paralelo — na
prática, o custo de ~6 revisões completas mais a síntese. Para um doc de design
de algumas páginas isso é minutos e um punhado de dólares em tokens; barato
contra uma decisão de contrato errada, caro contra um rename. Daí o piso de uso.

## Exemplo

```
/common:advisors docs/design/ui-proof-gate.md
# → "parece decisão de arquitetura — painel: 5 default + operador-sre +
#    custo-de-manutencao (7 lentes). Ok?"

/common:advisors specs/openapi.yaml --area=api-contrato
# pula a confirmação; painel: 5 default + consumidor-externo +
# versionamento-breaking-change

/common:advisors docs/adr/007-cache.md --lentes=contrarian,executor,dba-volume-indices
# painel à mão, 3 lentes
```

A saída é um relatório com propostas — o comando **não edita o artefato**;
aplicar as propostas é o passo seguinte, com sua aprovação.
