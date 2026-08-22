---
description: Transforma a coluna Review em uma lista curta de perguntas fechadas, em vez de uma lista de cards para abrir um a um. Lê os cards que estão em Review AGORA, pega o artefato de prova de cada um (docs/proof/<KEY>.yaml), classifica o motivo do NEEDS-HUMAN nos sete motivos de docs/needs-human-motivos.md, tira da sua frente o que não é decisão de ninguém (Docker fora, ferramenta ausente), agrupa o resto por motivo e faz UMA pergunta por grupo com recomendação. Você responde em lote ("1 sim, 2 não") e o comando aplica. Não roda prova nenhuma — quem prova é /board-flow:prove.
argument-hint: [--max N] [--scope "<jql>"] [--no-scope] [--dry-run]
---

# /board-flow:decide

## Purpose

`/board-flow:prove-drain` deixa a coluna Review triada por evidência, e o que
sobra é a pilha NEEDS-HUMAN. Essa pilha hoje é uma lista de chaves de card: para
saber o que está sendo perguntado, o humano abre card por card, lê a descrição,
lê o comentário do gate e decodifica os níveis da prova. Este comando faz esse
percurso uma vez, mecanicamente, e devolve perguntas.

**Ele não prova nada.** Não sobe worktree, não roda build, não perturba código.
Lê artefato que já existe. Rodar é barato — é para rodar sempre que a Review
tiver algo, não uma vez por semana.

## O que ele NÃO faz

- Não decide por você em nada que seja decisão sua. Só `nao-rodou` (a prova não
  chegou a rodar) sai da fila sem passar por você, porque ali não há decisão:
  ninguém opina sobre um Docker que não subiu.
- Não inventa motivo. Card que não casa com nenhum dos sete **para o comando**,
  com o card nomeado. Ver "A lista é fechada" em
  [docs/needs-human-motivos.md](../../docs/needs-human-motivos.md).
- Não escreve nada no Jira antes de você responder.

## Variables

- `--max N` — teto de cards analisados. Default 20 (é leitura de arquivo, não
  prova; o teto existe para o relatório caber na tela).
- `--scope "<jql>"` / `--no-scope` — mesma semântica de `/board-flow:prove-drain`;
  quem resolve a precedência é `atlassian-expert`, não você.
- `--dry-run` — monta e mostra a fila, não pergunta nada e não escreve nada.

## Workflow

### 1. A fila são os cards em Review AGORA — nunca os arquivos no disco

Delegue ao `atlassian-expert`:

> Command: decide
> <Scope: ... — só se veio flag>
>
> Liste as issues em `status = "<in_review>"` no projeto, aplicando o escopo
> efetivo, por prioridade e rank. Limite <max>. Devolva key + summary + tipo +
> prioridade, e o escopo efetivo usado.

**Por que assim, e não varrendo `docs/proof/*.yaml`:** o artefato registra o
veredito daquela rodada e não é reescrito quando o card anda depois. No
levantamento de 03/08/2026, dos 33 cards com artefato `needs-human` no disco,
**29 já estavam Done**. Uma fila montada a partir dos arquivos seria quase toda
de cards fechados — o oposto do que o comando existe para fazer.

Zero cards → "Nada em Review (escopo: <efetivo>)." e pare, nomeando o escopo:
filtro apertado demais não pode se passar por fila vazia.

### 2. Para cada card, o artefato entra como leitura de apoio

Leia `docs/proof/<KEY>.yaml` — e, se não houver, `.claude/proof/<KEY>.yaml`,
onde ficam os artefatos das rodadas anteriores à mudança de destino. Sem
artefato em nenhum dos dois, o card entra na fila como
**"nunca foi provado"** — não é NEEDS-HUMAN, é trabalho para
`/board-flow:prove`. Diga isso e siga.

### 3. Classifique o motivo — mecanicamente, não por leitura

Rode `board-flow/bin/classify_needs_human.py` (ou importe `classify`). A regra
olha os campos do artefato e só recorre ao texto onde o campo não basta. Ele
aceita as duas grafias de nome de nível que existem no disco.

Devolve `(slug, evidência)`. A evidência é a frase que fez a regra casar — é ela
que aparece para o usuário, para ele não ter que abrir o arquivo.

`sem-motivo` **para o comando**: liste os cards, diga o que o artefato tem, e
peça a decisão do dono sobre motivo novo. Nunca force para o motivo mais
parecido.

### 4. Tire da frente o que não é decisão de ninguém

Os `nao-rodou` não viram pergunta. Para eles:

- Reagrupe por causa concreta (ferramenta de cobertura ausente, Docker fora,
  commit-base sumido, trava do harness).
- Proponha re-rodar `/board-flow:prove` nos cards cuja causa é transitória
  (Docker, build).
- Para causa persistente (ferramenta que não está instalada no projeto),
  proponha **um** card de infra agregando todos — nunca um card por card
  travado. No levantamento de 03/08/2026 eram 11 cards com a mesma causa
  (`wego-assinatura-backend` sem quarkus-jacoco/PIT), que viraram o WEGO-2004.

### 5. Aplique os waivers que você já deu

Antes de perguntar qualquer coisa, use `board-flow/bin/waivers.py`:
`carregar(repo)` e, por grupo, `aplicavel(waivers, motivo, escopo)`. Voltou um
waiver: aplique a decisão registrada e apenas **informe** — não pergunte de
novo. É este passo que impede a fila de repetir a mesma pergunta toda semana.

O casamento é por **motivo + escopo**, nunca por card (todo card é novo; casar
por card não pouparia pergunta nenhuma). `PlugSignAdapter` e `plugsign adapter`
são o mesmo escopo.

Vencimento só acontece por **data** dentro do `revisit_trigger`. Gatilho em
prosa ("quando o adapter mudar") é mostrado a você e nunca interpretado pelo
código — um código que decidisse sozinho que a condição ocorreu estaria
dispensando por conta própria. Vencido volta a ser pergunta, dizendo que venceu.

Waiver malformado (sem autor, razão ou gatilho) é ignorado, não vale como
dispensa.

### 6. Agrupe por motivo e pergunte UMA vez por grupo

Sete cards travados por "não existe teste externo cobrindo o adapter X" são UMA
pergunta com sete cards pendurados, não sete perguntas. Ordem da fila:
`ORDEM_FILA` do classificador — risco decrescente, não prioridade do Jira. Quem
desiste no meio da lista tem que estar desistindo da parte menos grave.

Cada grupo sai assim, e o formato é obrigatório (`plain-report` +
`conversational-response`):

```
[3 cards] O teste não consegue enxergar essa mudança
   WEGO-1540, WEGO-1619, WEGO-1529 — todos no PlugSignAdapter

   O que isso quer dizer: o teste passa hoje e passaria igual se o código
   estivesse quebrado, porque o objeto falso que substitui a PlugSign não
   registra nada.

   Pergunta: aceito a prova interna nestes três e mando para Done?
   Recomendo não — é o adapter que fala com o fornecedor; um card para o teste
   externo custa menos que descobrir isso em produção.
```

Nada de `L4`, `altitude`, `waiver` ou `n/a` cru no texto da pergunta, no rótulo
de opção ou na descrição de opção. O detalhe técnico fica no artefato, e no fim
da resposta para quem quiser conferir.

### 7. Resposta em lote, aplicação em lote

O usuário responde numa linha (`1 sim, 2 não, 3 sim`). Só então você escreve.
Por grupo aceito:

- **aceitar a prova como está** → `waivers.gravar(...)` com motivo, escopo,
  razão do usuário, autor e `revisit_trigger` (todos obrigatórios — dispensa sem
  prazo nem condição é dispensa para sempre, e ninguém decidiu isso); depois
  avança os cards via `atlassian-expert`. A dispensa é **do humano**: o
  `proof-reviewer` continua sem poder dispensar nada e o artefato da prova
  continua sem campo para isso.
- **não aceitar** → cria o card do teste que falta (um por lacuna real, não um
  por card travado) e devolve os cards com `**Reason:**` **por card** — o
  `bounce-reason-gate` bloqueia comentário sem isso, e razão colada igual em N
  cards é exatamente a falha que ele existe para pegar.
- **`fora-do-alcance`** → a decisão é *para quem isso vai*: registre o
  responsável e a condição no card e nomeie o estado real (**Blocked** esperando
  X / **Deferred** até Y). "Precisa de atenção" não é estado.

### 8. Fecho

```
Review: <N> cards
  não eram decisão sua:   <n>  (<causa> ×<k>, ...)
  waiver já registrado:   <n>  (aplicado, não perguntei)
  perguntas:              <n>  em <g> grupos
  parados sem motivo:     <n>  (o comando parou nestes)
```

Sempre com a conta explícita — `N − n = n`. O número que interessa é quantas
perguntas sobraram, e ele só significa alguma coisa ao lado do que foi cortado.

## Constraints

- **Leitura por default.** Nada é escrito no Jira nem em `.claude/waivers/`
  antes da resposta do usuário. `--dry-run` nem pergunta.
- `atlassian-expert` é o único caminho de escrita no Jira.
- **Uma pergunta por grupo, nunca por card** — o custo que este comando ataca é
  o número de vezes que você para para decidir.
- **Toda pergunta é fechada e vem com recomendação.** Devolver a decisão crua
  ("avalie", "confira") é o que este comando existe para eliminar.
- Motivo desconhecido para o comando; nunca vira o motivo mais parecido.
