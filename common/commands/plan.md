---
description: Escreve a fila de execução `single-track` do repo — `.claude/programs/<nome>/plan.yaml`, o documento que guarda a ORDEM e o PORQUÊ de cada item estar naquela posição, que é o que o tracker perde. Aceita três fontes: `--from-spec`, que transforma cada critério de sucesso de uma especificação do /common:spec num item herdando a ordem do texto (e dizendo que herdou); `--from-jira`, que pega a classificação do /board-flow:triage — quem lê os cards e caça evidência no código — e grava a ordem que ela propôs; e a fila ditada à mão, para repo sem tracker e sem spec. Não exige Jira. É o ÚNICO escritor da fila, e recusa gravar por cima de um plano de ondas do /maestro:program-plan. Quem lê a fila depois é o /common:next.
argument-hint: <nome> [--from-spec docs/spec/<slug>.md | --from-jira [coluna|repasse.json]] [--dry-run] [--on-missing refuse|keep|drop]
interaction: conversational
---

# /common:plan

## Purpose

Dar um autor à fila `single-track` em repo que não tem tracker.

O documento existe desde 2026-07-28 e resolve uma dor real: o Jira guarda a
FILA (a coluna To Do) e não guarda a ORDEM nem o PORQUÊ dela, então a
priorização decidida numa sessão virava prosa no handoff e evaporava. Só que o
único comando capaz de escrever esse arquivo era o `/board-flow:triage`, que
exige Jira. O resultado é o buraco que este comando fecha:

- **repo sem tracker não tinha fila** — e sem fila o `/common:next` não tem o
  que ler, então a pergunta "e agora, o que eu faço?" volta a não ter resposta
  escrita em lugar nenhum;
- **o `/common:spec` não tinha saída** — ele foi feito de propósito para não
  exigir quadro configurado, e mesmo assim o que ele produz (uma especificação
  fechada, com critérios de sucesso já medidos) só continuava andando com um.

É a etapa 1 do desenho "um escritor, três fontes" (`BACKLOG.md`, "Cinco portas
de planejamento", aprovado pelo dono em 2026-08-24): uma fila, um autor, várias
fontes. As outras etapas consomem o arquivo que este comando passa a escrever.

A etapa 2 fechou o outro lado: o `/board-flow:triage` **parou de escrever** o
`plan.yaml` e passou a entregar a classificação para cá. Desde então "um
escritor" é literal — a fila tem um autor só, e a fonte Jira é uma das três em
vez de o pré-requisito.

**Isto não planeja ondas.** `mode: parallel-waves` é outro documento, com outro
autor (`/maestro:program-plan`) e outro executor (`/maestro:run`): tem
superfície disjunta, fork point e aceite executável por slice. Os dois moram no
mesmo diretório e são distinguidos por um campo interno, então este comando
**recusa** gravar num nome que já é plano de ondas, em vez de apagá-lo.

## Variables

- `<nome>` — o nome do programa, que vira
  `<raiz-principal>/.claude/programs/<nome>/plan.yaml`. Num repo com tracker, o
  costume é usar a chave do projeto (`WEGO`); sem tracker, o nome do repo ou da
  leva.
- `--from-spec docs/spec/<slug>.md` — cada critério de sucesso da especificação
  vira um item da fila.
- `--from-jira [coluna|repasse.json]` — a fila sai da classificação de uma
  triagem. Com um arquivo, grava um repasse que uma triagem já produziu; com um
  nome de coluna (ou nada, que é `Backlog`), roda o `/board-flow:triage` antes e
  grava o repasse dele.
- `--source "texto"` — de onde as demandas vieram, para rastreio. Sem a flag, o
  comando preenche a partir da fonte que usou.
- `--dry-run` — mostra o arquivo que seria gravado e não grava.
- `--on-missing refuse|keep|drop` — o que fazer com item que já está na fila do
  disco e a lista nova não menciona. Default `refuse`: sumir com ele em silêncio
  apaga posição e `why` que alguém decidiu.

**`--from-jira` não consulta o Jira por conta própria.** A ordem de uma fila
vinda de um board sai da CLASSIFICAÇÃO, nunca da coluna: quem lê os cards,
procura evidência no código e roteia os quatro baldes é o `/board-flow:triage`.
Este comando grava o que ele classificou. Montar a fila aqui a partir de uma
consulta crua ao Jira devolveria a ordem do rank do quadro — que é exatamente a
ordem que este documento existe para substituir.

## Instructions

**A ordem e o `why` são do dono, nunca seus.** Este comando escreve o documento
que registra uma decisão de priorização — inventar um `why` plausível é pior do
que não ter nenhum, porque o texto inventado se lê, meses depois, como critério
que alguém escolheu. Onde o `why` já está escrito (numa spec, num card, no
`BACKLOG.md`), herde e diga de onde veio. Onde não está, pergunte.

Por isso este comando é `conversational`: a política `default-yes` não é
injetada aqui, e a skill `guided-interrogation` vale enquanto a fila estiver
sendo ditada à mão. Perguntar a ordem é o trabalho, não o último recurso.

**Não execute nada.** O comando escreve um arquivo. Quem aponta o próximo passo
é o `/common:next`; quem executa em lote é o `/common:drain-plan` (etapa 3,
construída em 2026-08-25), na ordem que esta fila guardar.

**A gravação é mecânica.** Quem valida, funde e grava é
`common/bin/cepa-plan` — não escreva o YAML na mão com `Write`. O script recusa
`why` vazio, `id` repetido, `blocked_by` apontando para item inexistente, ciclo
de bloqueio e `human_pending` sem a chave; se você escrever o arquivo por fora,
nenhuma dessas recusas acontece.

## Workflow

### 1. Resolver a raiz e conferir o nome

A fila mora no **clone principal**: `<raiz-principal>/.claude/programs/<nome>/`,
onde `<raiz-principal>` é o pai de `git rev-parse --git-common-dir` sem o
`/.git` final — dentro de uma worktree ligada isso é o clone PRINCIPAL, não esta
árvore. Gravar contra o diretório corrente é a perda de 2026-08-18: num repo
cujo `.gitignore` cobre `.claude/`, o plano fica invisível ao git e morre junto
com a worktree, sem uma palavra (`docs/execution-plan.md`, "Where the file
lives").

Você não precisa resolver isso à mão — o `cepa-plan` resolve pela mesma regra —
mas precisa saber, porque é o caminho que vai no relatório.

```
python3 common/bin/cepa-plan check-name <nome> --repo .
```

Exit 3 é **colisão com um plano de ondas**: pare e diga o nome do programa que
está lá. Não sugira `--force`, não existe: apagar as ondas é perder a superfície
e o aceite de cada slice. Peça outro nome.

Exit 0 com a nota "nome ocupado por uma fila" é reescrita, o fluxo normal de
repriorizar — siga, sabendo que a fila de lá vai ser fundida no passo 4.

### 2. Juntar os itens

#### Com `--from-spec`

**A leitura da spec é mecânica**, não sua:

```
python3 common/bin/cepa-plan from-spec docs/spec/<slug>.md
```

Ele devolve a lista de itens em JSON — **um item por critério de sucesso**
(`### CS-N`), na ordem em que aparecem no texto — e avisa no stderr quando a
spec ainda está em rascunho, quando sobrou pergunta `- [ ]` ou quando algum
critério não declara **Teste vermelho:**. Não é enfeite que isso seja código: a
frase que registra a herança da ordem precisa aparecer no arquivo gravado, e
uma instrução em prosa só prova que o comando PROMETE escrevê-la.

O que sai de lá é rascunho para você revisar com o dono, não resultado final:

- `id` — `CS-1`, `CS-2`… ou o slug do critério; o que importa é ser estável, é
  por ele que o `blocked_by` aponta.
- `title` — o critério em termos observáveis, a linha do próprio `### CS-N`.
- `why` — o script monta com o que a especificação já escreveu: a
  **Superfície** onde o critério é observável, o **Teste vermelho** declarado, e
  a frase que registra a herança — **"herdado da ordem do texto da
  especificação; ninguém priorizou os critérios entre si"**. Onde a seção
  Problema/Escopo disser por que aquele critério vem antes dos outros, troque a
  frase de herança por esse motivo, que é melhor. O relatório repete em voz alta
  o que ficou herdado.
- `blocked_by` — o script devolve sempre vazio: dependência entre critérios não
  se lê do texto. Acrescente só onde a spec declarar uma, e não deduza
  dependência de dois critérios tocarem o mesmo arquivo.
- `human_pending` — `null`. Na hora de planejar ainda não existe rota a cobrar;
  o campo é preenchido depois, quando o item fecha e o Implementation Summary
  diz qual é a rota de validação humana.

**Ordem herdada, e dito.** Os critérios de uma spec não vêm priorizados entre
si. A preferência registrada no desenho é herdar a ordem do texto e **dizer que
herdou** — não perguntar item a item, que transfere ao dono um trabalho que ele
já fez uma vez. Ofereça reordenar em UMA pergunta fechada no fim, com a fila
inteira à vista.

**Spec ainda em rascunho.** Se o `**Status:**` não for `pronta-para-construir`,
diga quantas perguntas `- [ ]` ainda estão abertas e faça UMA pergunta fechada:
fechar a especificação antes (`/common:spec --fechar <slug>`) ou escrever a fila
assim mesmo. Recomende fechar antes — um critério sem superfície observável vira
um item de fila que ninguém sabe quando terminou.

#### Com `--from-jira`

A fonte aqui é a **classificação** de uma triagem, não a coluna do quadro.

**Se veio um arquivo** (`--from-jira <repasse.json>`), uma triagem já rodou e o
repasse dela está no disco — normalmente em
`<raiz-principal>/.claude/programs/<nome>/triagem-<YYYY-MM-DD>.json`, onde o
`/board-flow:triage` o deixa. Pule para o passo 3.

**Se veio um nome de coluna** (ou nada, que é `Backlog`), a triagem ainda não
rodou. Exija as duas coisas de que ela depende, e pare nomeando a que faltar:

- o plugin `board-flow` instalado — sem ele não há quem fale com o Jira
  (`atlassian-expert` é o único caminho de escrita do harness);
- um `board-flow.yaml` na raiz do projeto (ou o legado
  `.claude/board-flow.lifecycle.yaml`), de onde sai o `defaults.project_key` e
  o `status_map`.

Faltando qualquer uma, **não improvise uma consulta ao Jira**: diga que a fila
por board precisa da triagem, e ofereça as duas saídas que existem sem ela —
`--from-spec`, se houver especificação fechada, ou a fila ditada à mão.

Com as duas presentes, rode o `/board-flow:triage <coluna>` e siga o workflow
dele até o passo 9, que é onde ele grava o repasse. O que volta de lá é a
classificação nos quatro baldes com a ordem de execução **que o dono confirmou
no passo 7** — a ordem é dele e da evidência que a triagem juntou, não sua.

**A leitura do repasse é mecânica**, não sua:

```
python3 common/bin/cepa-plan from-triage <repasse.json>
```

Pelo mesmo motivo do `from-spec`: as regras abaixo moravam na prosa do
`triage.md`, e prosa de comando erode sem nenhum teste ficar vermelho. O script
aplica, e recusa quando não dá:

- **só card `ready` vira item `pending`.** Card `implemented` foi para In
  Review e pertence à fila de PROVA (`/board-flow:prove-drain`); card
  `needs-refinement` fica no backlog. Os dois saem da fila e o script DIZ
  quais, com a contagem — repita isso no relatório.
- **card `obsolete` entra como `dropped`, com o motivo.** O card sai da fila e
  o documento continua explicando por quê; apagá-lo faz a próxima varredura
  propor a mesma demanda de novo.
- **card READY sem `why` é recusa**, não item com `why` inventado. O `why` de
  cada posição já foi dito no passo 7 da triagem — se sumiu no caminho,
  pergunte, não preencha.
- **card ainda em `needs-decision` é recusa.** A grelha do passo 6 não
  terminou, e gravar assim esconderia uma pergunta em aberto dentro de uma fila
  que se lê como decidida.
- **dependência para fora da fila sai do `blocked_by`, e é dita.** Um card
  READY que dependia de um card que foi para In Review perde o `blocked_by`
  (o `/common:next` só sabe esperar por item da própria fila) e o aviso nomeia
  os dois — a partir daí a dependência é do dono, para vigiar.
- **`--max` nunca é silencioso.** O `remaining_in_column` do repasse vira uma
  nota `PARCIAL` na linha `source` do plano, e é o que impede uma fila de 15
  cards de 27 de ser lida, meses depois, como o quadro inteiro.

Quando nada mudou no que o `from-triage` devolveu, `--from-triage <arquivo>` faz
a leitura e a gravação de uma vez, no lugar do `--items`. A linha `source` sai
do próprio repasse (projeto, coluna, escopo, data, e a nota de parcialidade).

#### Sem flag — a fila ditada à mão

O caso do repo sem tracker e sem spec (este repo é um). Antes de perguntar
qualquer coisa, **leia a fonte de demandas que o repo já tem**: `BACKLOG.md`, os
documentos em `docs/`, os handoffs em `<raiz-principal>/.claude/handoffs/`.
Pergunta cuja resposta estava no repo queima a paciência do dono.

Depois, em rodadas de no máximo quatro perguntas:

1. **quais demandas entram** — proponha a lista que você leu, com a âncora de
   cada uma na fonte (`"P9 do BACKLOG"`, um ADR, um número de issue), e deixe o
   dono cortar;
2. **em que ordem** — proponha uma, com o motivo de cada posição, e deixe o dono
   corrigir. Proposta com motivo é bem mais barata de responder que uma pergunta
   aberta;
3. **o `why` de cada posição** — o que você não conseguiu tirar da fonte,
   pergunte. Um item sem `why` não é gravável, e o `cepa-plan` recusa a fila
   inteira por causa dele.

### 3. Mostrar a fila antes de gravar

Sempre. Rode com `--dry-run` e mostre a fila em três colunas — posição, item,
`why` em uma linha — mais o que a fila do disco já tinha, se for reescrita.
**Uma pergunta fechada** ("grava assim?"), não uma revisão item a item.

### 4. Gravar

```
python3 common/bin/cepa-plan write <nome> \
  --items <arquivo.json> --source "<de onde veio>" --quando <YYYY-MM-DD> --repo .
```

Quando nada mudou no que o `from-spec` (ou o `from-triage`) devolveu,
`--from-spec <arquivo>` / `--from-triage <arquivo>` faz as duas coisas de uma
vez, no lugar do `--items`.

Escreva os itens num arquivo JSON temporário (ou mande por stdin com `-`). O
script:

- valida tudo e **não grava nada** se qualquer item tiver lacuna — a fila é um
  documento só, meia fila gravada é pior que nenhuma;
- funde com o que já está no disco: a lista nova manda na ordem, no `title` e no
  `why`, que são decisão de planejamento; o disco manda no `status` e no
  `human_pending`, que vieram da execução. **Isso não é detalhe**: só o humano
  fecha um `human_pending`, então uma reescrita que os zerasse apagaria dívida
  que ninguém pagou;
- copia o arquivo anterior para `plan.yaml.bak` antes de sobrescrever, porque os
  comentários escritos à mão (a evidência de cada `done`, por exemplo) não
  sobrevivem à reescrita.

Exit 4 é item do disco que a lista nova não menciona: **não passe
`--on-missing drop` por conta própria** — mostre os ids e pergunte.

### 5. Relatar e apontar para frente

Diga onde gravou, quantos itens, de que fonte, e o que **não** foi decidido
aqui. Termine nomeando quem lê o arquivo agora: `/common:next`.

## Report

```
Fila gravada: <raiz-principal>/.claude/programs/cepa/plan.yaml
  7 itens · fonte: docs/spec/planejador-de-lotes.md (7 critérios de sucesso)

Ordem herdada do texto da especificação. Ninguém priorizou os critérios entre
si — se a ordem importa, é a hora de dizer.

  1. CS-1 — planejador aceita uma fonte que não é o BACKLOG
     porque: é o único critério que os outros seis pressupõem
  2. CS-2 — ...

Nada pendente com você: nenhum item nasceu com rota de validação humana; esse
campo se preenche quando o item fecha.

Próximo passo: /common:next (nomeia UM item e o porquê dele).
```

## Constraints

- **Nunca inventa ordem nem `why`.** Herda de uma fonte escrita e diz de onde,
  ou pergunta. Um `why` plausível escrito por você se lê depois como critério
  que alguém escolheu, e é exatamente a mentira que a fila existe para não
  contar.
- **Nunca grava por cima de um plano de ondas.** Colisão é recusa nomeada, sem
  escape.
- **Nunca consulta o Jira direto.** Com `--from-jira`, quem lê os cards e
  classifica é o `/board-flow:triage`; este comando grava o que ele classificou.
  Uma fila montada de uma consulta crua à coluna herda a ordem do rank do
  quadro, que é a ordem que este documento existe para substituir.
- **Nunca escreve o YAML à mão.** A gravação passa por `common/bin/cepa-plan`,
  que é onde as recusas moram.
- **Não fecha `human_pending` de ninguém.** Item que vem do disco com pendência
  aberta continua com ela. Quem fecha é o dono, no `/common:next --sync`.
- **Não executa e não mexe no tracker.** O único arquivo que este comando
  escreve é o plano (mais o `.bak` da versão anterior).
- **Uma fila por nome.** Ao encontrar uma existente, funde; não cria
  `<nome>-2`.

## See also

- [`docs/execution-plan.md`](../../docs/execution-plan.md) — o mecanismo inteiro e por que o arquivo mora no clone principal
- [`common/plan-schema.yaml`](../plan-schema.yaml) — o schema anotado, os dois modos
- `/common:next` — o consumidor da fila
- `/common:spec` — a fonte que `--from-spec` lê
- `/board-flow:triage` — a fonte que `--from-jira` lê: ele classifica os cards e entrega a ordem; desde a etapa 2 ele não escreve mais o `plan.yaml`
