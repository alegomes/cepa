---
description: Executa em lote a fila `single-track` do repo — `.claude/programs/<nome>/plan.yaml` — NA ORDEM QUE ELA GUARDA. É a etapa 3 do desenho "um escritor, três fontes", e fecha o ciclo sem tracker: `/common:plan` escreve a fila, `/common:next` aponta UM passo, este comando executa vários. Não exige Jira e nunca consulta um: o único lote que existia até aqui, o `/board-flow:drain`, tira a ordem do rank do quadro — exatamente a ordem que o plano existe para substituir. Copia do drain o que vale: parar no primeiro item travado e o teto `--max`. Para também quando o item tem uma rota que só o humano fecha. Reserva cada item antes de tocá-lo e registra o desfecho de todos.
argument-hint: <nome> [--max N] [--dry-run]
interaction: routine
---

# /common:drain-plan

## Purpose

Executar a fila na ordem dela.

O `mode: single-track` do `plan.yaml` existe para guardar as duas coisas que o
tracker perde: a **ordem** de execução e o **`why`** de cada item estar naquela
posição. Até aqui nenhum comando executava essa fila em lote:

- o `/common:next` lê o plano e nomeia UM item, e é read-only por contrato;
- o `/board-flow:drain` executa em lote, mas a fonte dele é a coluna do Jira,
  ordenada pelo `priority and rank` do board — a ordem que o plano existe para
  substituir. Ele nunca abre o `plan.yaml`;
- num repo sem tracker (a fila `cepa` deste repo, cujos ids não são cards) não
  havia nem essa saída: sobrava encadear `/common:next` + execução à mão, um
  item por vez.

Ou seja: o dono escrevia a ordem no plano, e a única forma de executá-la em
lote era uma que ignorava essa ordem. Este comando fecha o ciclo — escrever
(`/common:plan`) → apontar (`/common:next`) → executar (aqui) — sem tracker
nenhum no caminho.

**Isto não executa ondas.** `mode: parallel-waves` é outro documento, com outro
autor (`/maestro:program-plan`) e outro executor (`/maestro:run`), que forka
worktrees em paralelo. Este comando **recusa** um plano de ondas em vez de
tentar linearizá-lo.

## Variables

- `<nome>` — o programa cuja fila será executada, isto é
  `<raiz-principal>/.claude/programs/<nome>/plan.yaml`. Sem o argumento, a
  resolução é a mesma do `/common:next`: `board-flow.yaml` → `project_key`, ou
  a única fila `single-track` que existir; mais de uma, o comando lista e
  pergunta em vez de escolher por você.
- `--max N` — teto de itens neste lote. Default **3**. É mais baixo que o do
  `/board-flow:drain` (5) porque um item de fila costuma ser maior que um card:
  cada um roda o flow inteiro da topologia mais os dois gates (aceite e prova).
- `--dry-run` — mostra o lote que rodaria, com a parada e o porquê de cada
  item, e não executa nem marca nada.

## Instructions

**A ordem é o dado.** Não escolha itens, não pule um item travado para alcançar
o de baixo, não reordene por "esse é mais rápido". Pular é reordenar a fila em
silêncio — e uma fila reordenada em silêncio é a mesma coisa que não ter fila,
que é o estado que este documento existe para tirar.

**Quem monta o lote é o `cepa-plan`, não o seu olho.** Enquanto as regras de
"o que dá para executar agora" viviam na prosa de um comando, o único teste
possível era grepar a prosa — que prova que o comando PROMETE respeitar a
ordem, nunca que uma execução respeitou. Rode `cepa-plan queue` e execute o
que ele devolveu.

**Nunca edite o `plan.yaml` à mão** — nem com `Write`, nem com `sed`. A
marcação passa por `cepa-plan start` / `cepa-plan finish`, que recusam desfecho
sem evidência, recusam reserva dupla e recusam fechar uma rota humana. Escrito
por fora, nenhuma dessas recusas acontece.

**Nenhum tracker.** Este comando não fala com Jira, não delega ao
`atlassian-expert` e não transiciona card nenhum. Se o repo também tem quadro,
quem cuida do card é o `/board-flow:execute`; aqui a fila é a verdade.

## Workflow

### 1. Resolver a fila e montar o lote

A fila mora no **clone principal**: `<raiz-principal>/.claude/programs/<nome>/`,
onde `<raiz-principal>` é o pai de `git rev-parse --git-common-dir` sem o
`/.git` final — dentro de uma worktree ligada isso é o clone PRINCIPAL, não
esta árvore. Você não resolve isso à mão (o `cepa-plan` resolve pela mesma
regra), mas precisa saber, porque é o caminho que vai no relatório.

```
python3 common/bin/cepa-plan queue <nome> --max N --repo . --json
```

O que volta: `batch` (os itens executáveis agora, na ordem da fila, cada um com
o `why` que o colocou naquela posição), `stop` (por que o lote termina onde
termina), `warnings` e `totals`.

Exit 3 é **plano de ondas**: pare e diga que quem executa aquele documento é o
`/maestro:run`. Exit 2 sem fila: diga que não há fila e que quem escreve é o
`/common:plan <nome>` — não invente uma ordem, e não caia no
`/board-flow:drain` como substituto, porque ele executaria a ordem do quadro.

Os motivos de parada, e o que cada um quer de você:

| `stop.reason` | o que aconteceu |
|---|---|
| `teto` | o `--max` encheu; o item nomeado seria o próximo. Rode de novo depois. |
| `fim-da-fila` | não sobrou item pendente. Ofereça `/common:plan` para a próxima leva. |
| `human_pending` | o item tem uma rota que **só você** fecha. O lote para ali por decisão do dono (2026-08-25): o item seguinte costuma se apoiar no que a rota valida, e seguir sem ela é construir sobre coisa que ninguém conferiu. |
| `bloqueado` | o item depende de algo que não está feito nem entra neste lote. |
| `bloqueado-antes` | o item saiu `blocked` de um run anterior e a condição de fora não mudou. |
| `in_progress` | o item está reservado: ou outra sessão está nele agora, ou um run morreu e deixou o status para trás. |

### 2. Confirmar, uma vez só

Mostre o lote e pergunte **uma vez**, na largada — inclusive a pergunta que só
apareceria no meio do run:

```
Fila <nome> — <caminho>
Lote de N item(ns), na ordem da fila:
  1. <id> — <title>
     porque: <why>
  2. ...

Depois deles o lote para: <stop.reason> — <stop.detail>
<avisos, se houver>

Rodo? Cada item roda o flow inteiro da topologia + os gates de aceite e prova.

E se um item travar (BLOCKED — condição de fora, que só você resolve):
  (a) paro o lote ali e te chamo                      ← default
  (b) registro o motivo no item e sigo com os demais

Responda sim / não / "só os N primeiros", e (a) ou (b).
```

Esta é a **única parada planejada** do run — aplique `default-yes`. A
alternativa (a)/(b) tem que estar escrita aí, não implícita: perguntar no item
3 de 5 chega quando o usuário já perdeu o contexto da lista, e é esse custo que
a parada única existe para evitar. Se o run veio do `/common:session`, essas
respostas já foram colhidas — siga sem perguntar.

Com `--dry-run`, imprima essa tela e pare.

### 3. Executar, item a item

Para cada item do lote, na ordem:

  a. **Reserve primeiro**, antes de qualquer build, worktree ou delegação:

     ```
     python3 common/bin/cepa-plan start <nome> <id> --repo .
     ```

     Exit 5 significa que o item deixou de ser reservável desde que o lote foi
     montado (outra sessão reservou, ou uma rota humana apareceu). Registre
     `SKIPPED` com o motivo que o comando devolveu e vá para o próximo **sem
     rodar nada** — item pulado não consome `--max`, porque trabalho nenhum
     rodou nele.

     A reserva é o equivalente, sem tracker, ao claim que o `/board-flow:drain`
     publica no card: a lista do passo 1 é uma foto, e entre a foto e a hora de
     chegar no item N outra janela pode ter pegado o mesmo item. O custo de não
     reservar não é conflito de arquivo, é o trabalho inteiro refeito.

  b. **Execute o item** pelo flow da topologia do repo (`.claude/topology`),
     como o `/common:autonomous-start` despacha: item de defeito vai para
     `reproduce-fix-verify`, o resto para `plan-build-validate`. O `title` e o
     `why` do item são a descrição; o `why` é contexto de prioridade, não
     escopo — não amplie o item para "aproveitar que estou aqui"
     (`scope-discipline`).

  c. **Passe pelos dois gates** antes de chamar o item de fechado — são os
     mesmos de qualquer construção deste harness, e o lote não os pula por ser
     lote: `completion-auditor` (COMPLETE) e, quando o item mudou
     comportamento, `proof-reviewer` (PROVEN). Veredito diferente disso não é
     `done`; é `blocked` ou volta para `pending`, com o motivo.

  d. **Registre o desfecho**, sempre:

     ```
     python3 common/bin/cepa-plan finish <nome> <id> --status done \
         --evidence "commits, vereditos, o que ficou de fora" --repo .
     ```

     `--evidence` é obrigatório: `done` é uma palavra, e o que a torna
     auditável meses depois é o que aconteceu. Se a execução produziu uma
     rota que só o humano fecha (validar na UI, aprovar um PR, rotacionar um
     segredo), abra-a com `--human-pending "<a rota, verbatim>"` — é assim que
     ela sobrevive à sessão. **Nunca feche uma rota**: só quem rodou sabe se
     ela passou, e o comando recusa.

  e. **Item travado:** siga a política escolhida no passo 2 — parar (default)
     ou seguir. Nos dois casos, `finish --status blocked --evidence "<a
     condição de fora e quem a resolve>"` antes de seguir, senão o item fica
     `in_progress` para sempre e trava o lote seguinte. Não pergunte nada
     agora: o usuário já respondeu isso na largada.

### 4. Desfecho terminal — nenhum item sai do lote sem nome

O lote não termina enquanto um item tocado estiver sem desfecho nomeado. Todo
item que você tocou acaba em exatamente um destes:

| Desfecho | Significa |
|---|---|
| `DONE` | fechou, com os dois gates e a evidência gravada |
| `BLOCKED` | travou numa condição de fora — nomeie a condição e quem a resolve |
| `DEFERRED` | adiado de propósito — nomeie o que precisa ser verdade para retomar |
| `DROPPED` | não vai ser feito — nomeie por quê |
| `ERROR` | o run em si falhou (infra, permissão) — nomeie a falha |
| `SKIPPED` | o item deixou de ser reservável desde a montagem do lote — diga qual dos casos |

"Em andamento", "quase lá" e silêncio **não** são desfechos. São a ausência de
uma decisão vestida de status, e é assim que um item volta na semana seguinte
sem ninguém saber o que houve com ele. Se você não sabe nomear, o desfecho
honesto é `BLOCKED` com o motivo "desfecho indeterminado: <o que você não
sabe>".

### 5. Relatório

Um relatório só, no formato `plain-report`, e em pt-BR:

- **Fila drenada:** `<nome>` — `<caminho>`
- **Itens tentados:** N, cada um com o desfecho terminal. A contagem de itens
  tentados TEM que bater com a de desfechos nomeados; se não bate, o lote não
  terminou.
- **Fechados:** lista com o veredito dos gates de cada um.
- **Travados / pulados:** com o motivo.
- **Pendente com você:** toda rota `human_pending` que este run abriu, verbatim.
  Nenhuma? Diga "nada a validar à mão" — silêncio aqui é a ambiguidade que o
  campo existe para matar.
- **Onde o lote parou e o que sobrou:** o `stop` do próximo `queue` e quantos
  pendentes ficaram.
- **E agora:** `/common:next` para o próximo passo, ou este comando de novo se
  a parada foi `teto`.

## Constraints

- **Default `--max 3`.** Cada item é o flow inteiro mais dois gates; valores
  altos arriscam um run caro que ninguém acompanha.
- **Parar no primeiro item travado é de propósito.** Não se empurra trabalho
  travado — copiado do `/board-flow:drain`, pelo mesmo motivo.
- **`human_pending` aberto para o lote.** Decisão do dono em 2026-08-25.
- **Reservar antes de executar, item a item.** Sem o `start`, o item não é
  trabalhado.
- **A marcação é mecânica** (`cepa-plan start` / `finish`). Editar o YAML à mão
  contorna todas as recusas.
- **Recusa plano `parallel-waves`** — quem executa ondas é o `/maestro:run`.
- **Não escreve a fila.** Item que falta na fila é do `/common:plan`; inventar
  posição e `why` aqui forjaria exatamente a decisão que o documento guarda.
- **Não fala com tracker nenhum.** É o ponto do comando.
