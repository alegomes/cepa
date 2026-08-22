---
description: Bulk-prove the Review column. Iterates cards in `defaults.status_map.in_review` (priority order) and runs the equivalent of /board-flow:prove on each — change-driven proof, then routes the verdict. Unlike /board-flow:drain, it does NOT stop on a failed card: UNPROVEN bounces back and the drain continues, because clearing the queue is the whole point. PROVEN auto-advances (if a done status is configured), NEEDS-HUMAN stays for you. Use to triage a backlogged Review column.
argument-hint: [--max N] [--scope "<jql>"] [--no-scope]
interaction: routine
---

# /board-flow:prove-drain

## Purpose

Drain the *Review* column through the change-driven proof gate. The Review pile
grows because manual review is the bottleneck; this iterates the column and lets
`proof-reviewer`'s evidence triage it — PROVEN out, UNPROVEN back, NEEDS-HUMAN
held for the human. What's left in Review afterward is precisely the set that
actually needs a person.

**Heavy operation:** each card runs a full proof (integration build + JaCoCo +
PIT, in a throwaway worktree). Use `--max` to cap per run. Default `--max 5`.

## Variables

- `$ARGUMENTS` — optionally `--max N`. Default max = 5.
- `--scope "<jql>"` — a raw JQL fragment that narrows the drain to a slice of the Review column for this run only, overriding any configured scope.
- `--no-scope` — ignore configured scope entirely; sweep the whole Review column.

**Scope** lets you triage a slice of Review (e.g. one team's cards, or `labels = needs-review`) instead of the entire column. By default the drain applies the effective scope resolved from `board-flow.yaml` (`defaults.scope` / `scope_overrides.prove_drain` / the active topology's `scope`); the two flags above override that for one run. You don't resolve the precedence yourself — pass the command name and any flag to `atlassian-expert`, which resolves and reports the effective fragment.

## Instructions

You are the orchestrator. Iterate the Review column, prove each card, route each
verdict. Apply `scope-discipline` (don't exceed `--max`). **Do not stop on
UNPROVEN** — sending a card back is forward progress, not a blocker (this is the
deliberate difference from `/board-flow:drain`).

## Workflow

### 1. Parse arguments & resolve config

- Max cards: parse `--max N`. Default 5.
- Scope flags: detect `--no-scope` and `--scope "<jql>"` (mutually exclusive; if both appear, abort with "pass either --scope or --no-scope, not both"). Build the **scope directive**: `--no-scope` → `Scope: none`; `--scope "<jql>"` → `Scope: <jql>`; neither → omit the line (atlassian-expert resolves the effective scope from config).
- **Claim id do run:** gere um, agora, como descrito em **Reserva do card**. Ele
  identifica ESTE run em todos os cards que ele tocar.
- Read `default_topology` and `defaults.status_map.in_review` from
  `board-flow.yaml`. Confirm the topology ships `proof-reviewer` (else abort as in
  `/board-flow:prove`).

### 2. List cards in Review

Delegate to `atlassian-expert` (the `Command:` line tells it to resolve scope for `prove_drain`; include the scope directive only if a flag was passed):

> Command: prove_drain
> <Scope: ... — only if a flag was passed>
>
> List Jira issues where `status = "<in_review>"` in the project, applying the
> effective prove_drain scope, ordered by priority and rank. Limit to <max>.
> Return key + summary + issue type + priority, plus the effective scope you used.

If 0 cards → "Nothing in Review (scope: <effective scope, or 'none'>)." — call out
the scope so an over-narrow filter isn't mistaken for an empty queue. Stop.

### 3. Confirm with user

```
Found N cards in Review (column "<in_review>", scope: <effective scope, or "none — whole column">):
  WEGO-1234 (Bug, P1) — <summary>
  WEGO-1235 (Story, P2) — <summary>
  ...

Prove these? Each runs the change-driven proof gate (integration coverage +
diff-scoped mutation + adversarial input, in a throwaway worktree).
  · PROVEN     → auto-advances (if a done status is configured)
  · UNPROVEN   → returned to In Progress with the gap (drain CONTINUES)
  · NEEDS-HUMAN→ stays in Review for you

E, no fim, os que pararem em NEEDS-HUMAN (nem provados, nem devolvidos —
os que dependem de uma decisão sua):
  (a) aplico a recomendação de cada motivo e só te conto o que fiz   ← default
  (b) seguro todos e te pergunto um por um no relatório

Reply yes / no / first-N to prove a subset, e (a) ou (b) para os NEEDS-HUMAN.
Só "sim" vale como sim + (a).
```

Wait for confirmation. **Esta é a ÚNICA parada do run** — aplique `default-yes`:
junte a esta confirmação tudo que você perguntaria depois. Uma pergunta no meio
do drain custa ao usuário recarregar o contexto inteiro para responder.

**A alternativa (a)/(b) tem que estar ESCRITA na tela acima, não implícita.**
O passo 6 só dispensa a segunda rodada de perguntas "se o usuário já respondeu
essa política na confirmação do passo 3" — e uma tela que mostra a contagem de
cards e pergunta "posso ir?" não colhe resposta nenhuma sobre NEEDS-HUMAN. Um
"sim" a ela não fecha aquela condicional, o passo 6 pergunta tudo de novo no
fim, e o run que se anunciou como parada ÚNICA cobra duas. Foi assim até
22/08/2026. Um "sim" seco continua valendo: é (a), o default.

Se o run veio de `/common:session`, essas respostas já foram colhidas na largada
— não pergunte de novo.

### 4. Iterate

For each confirmed card, in priority order:

  a. **Reserve o card primeiro** — releia status + comentários e publique o claim,
     conforme **Reserva do card** abaixo. Se o card foi pulado (saiu da coluna ou
     está reservado por outra sessão), registre `SKIPPED` e vá para o próximo
     card SEM rodar prova nenhuma.
  b. Run the equivalent of `/board-flow:prove <card-key>` (proof + verdict-driven
     transition).
  c. Capture the verdict and the action taken.
  d. **Continue regardless of verdict** — UNPROVEN does not stop the drain.
     Every card returned on UNPROVEN carries its own `**Reason:**` — the
     concrete gap for THAT card, not the batch's. `bounce-reason-gate` blocks
     the comment without it, and a shared reason pasted across N cards is the
     failure it exists to prevent: it reads as answered while telling the next
     session nothing about any individual card. Where a card stops for
     something other than rework, name the real condition — **Blocked**
     (waiting on X) / **Deferred** (until Y) / **Dropped** (because Z).
     "Attention" is not a state.
  e. If `proof-reviewer` returns a hard environmental failure for a card (can't
     create a worktree, build infra down), record it as `ERROR` for that card
     and continue to the next — one broken card shouldn't sink the batch. Um
     card que termina em `ERROR` não recebeu veredito, então **publique a
     liberação do claim** (`🔓`) antes de seguir.
  f. Before recording any card's outcome, apply **Coupled closure** below. The
     batch is a scheduling convenience; it is never the unit of evidence.

### 5. Final report

```
Proved from Review (max <N>, scope: <effective scope, or "none">):
  PROVEN → advanced:    <count>   (keys)
  UNPROVEN → returned:  <count>   (keys + one-line gap each)
  NEEDS-HUMAN → held:   <count>   (keys + what to look at)
  ERROR:                <count>   (keys + reason)
  SKIPPED (reservado/movido): <count>   (keys + qual sessão ou qual status)

Remaining in Review (not attempted this run): <count>
```

The table above is the at-a-glance count. For each card in the NEEDS-HUMAN set —
the only one that costs the user attention — expand it in plain language (apply
`conversational-response`'s "translate jargon at the human boundary"): the one
decision you need and why, not a wall of `assumed`/`L2`/`altitude` the user has
to decode. If you put any held card's decision to the user interactively (an
`AskUserQuestion`), the same rule covers the question, every option label, and
every option description — never a bare `L4` / `waiver` / `altitude` in a label.
Suggest re-running for the next batch if cards remain, and point the user at the
NEEDS-HUMAN set as their actual review queue.

**Quando a contagem de NEEDS-HUMAN for 1 ou mais, NÃO mande o usuário rodar
outro comando — faça o agrupamento aqui, no mesmo relatório.** Aplique a lógica
de `/board-flow:decide` sobre o conjunto que ESTE run acabou de produzir:
classifique cada card nos sete motivos de `docs/needs-human-motivos.md`, tire da
frente o que não é decisão de ninguém (Docker fora, ferramenta ausente — resolva
ou registre, não pergunte), agrupe o resto por motivo e faça **uma pergunta
fechada por grupo, com recomendação**, aceitando resposta em lote ("1 sim, 2
não").

**Se o usuário respondeu (a) no passo 3 — ou respondeu só "sim", que é (a) —
não pergunte nada aqui.** Aplique a recomendação de cada motivo e relate o que
foi feito, card por card, com o motivo ao lado. As perguntas fechadas por grupo
acima são o caminho (b), e só ele.

Por que aqui e não em outro comando: o run que produziu os cards é o run que
sabe quais são e por quê. Encerrar dizendo "agora rode `/board-flow:decide`"
devolve ao usuário um segundo ciclo de leitura e decisão sobre o mesmo material
— o custo que o `decide` existia para remover, reintroduzido no ponto de
entrega. `/board-flow:decide` continua existindo para quando a coluna Review
acumulou fora de um drain (cards de outras sessões, de outro dia).

## Reserva do card — a fila é o recurso disputado

A lista montada no passo 2 é uma **foto**, não uma reserva. Entre a listagem e o
momento em que este run chega ao card N, outra sessão (outra worktree, outra
máquina, o mesmo usuário em duas janelas) pode ter pegado o mesmo card — e o
custo não é um conflito de arquivo, é o trabalho inteiro refeito. O recurso
compartilhado é a coluna do board, então a reserva é feita no board.

**Claim id.** Gere UM por run, no passo 1, e use o mesmo para todos os cards:

```bash
echo "$(basename "$PWD")-$(python3 -c 'import uuid;print(uuid.uuid4().hex[:8])')"
```

**Antes de tocar em cada card** (é o primeiro passo do 4, antes de qualquer
build, worktree ou delegação), delegue a `atlassian-expert`:

> Leia o card `<KEY>`: status atual, responsável, e os comentários das últimas
> 90 minutos. Devolva sem alterar nada.

E decida, mecanicamente:

- **Status ≠ `<coluna do run>`** → o card saiu da fila desde a listagem. **Pule**,
  registre `SKIPPED (saiu da coluna: agora em <status>)` e siga para o próximo.
- **Existe um comentário de claim de OUTRO claim id, com menos de 90 minutos e
  sem o `🔓` de liberação** → outra sessão está nele agora. **Pule**, registre
  `SKIPPED (reservado por <claim-id> às <hh:mm>)` e siga.
- **Caso contrário** → reserve, publicando o comentário via `atlassian-expert`:

  > `🔒 claim: <claim-id> — <nome do comando> em andamento desde <timestamp>.`
  > `Outra sessão deve pular este card. A reserva expira em 90 minutos.`

  Só depois desse comentário existir o card pode ser trabalhado.

**Liberação.** O veredito do card encerra a reserva — o comentário de resultado
(prova, bounce com `**Reason:**`, resumo de implementação) já é o sinal de que a
reserva acabou. Quando o card termina SEM veredito (`ERROR`, interrupção, aborto
do run), publique a liberação explícita, senão o card fica intocável por 90 min:

> `🔓 claim <claim-id> liberado — <motivo>.`

**Por que 90 minutos e não um lock permanente:** uma sessão que morre no meio
não pode congelar a fila. A janela é maior que o tempo de um card (a prova leva
de 9 a 12 minutos) e menor que um turno de trabalho, então uma reserva órfã se
resolve sozinha sem ninguém precisar destravar nada à mão.

**Cards pulados não consomem `--max`** — nenhum trabalho rodou neles. Eles
aparecem no relatório final com o motivo, porque "sumiu da lista sem explicação"
é exatamente o buraco que este mecanismo existe para fechar.

## Coupled closure — the batch is not the unit of evidence

Draining N cards in one run creates a standing temptation: prove once, close
many. The saving is real and the reasoning is almost never valid. Two cards that
merely rode the same commit are not the same change.

**Closing cards together is allowed only when both hold:**

1. **Causally coupled** — they are one change split across cards (the same hunk
   satisfies them; fixing one necessarily fixes the other), not merely adjacent,
   same-file, same-sprint, or same-author.
2. **Shared validation boundary** — a single external surface exercises all of
   them, so one perturbation going RED demonstrably covers every card in the set.

**Forbidden outright — no matter how coupled they look:** cards carrying
independent risk, or independent debt. A shared proof cannot speak for a risk
only one of them introduces.

**Even when both conditions hold, every card gets its own line:**

- its **evidence** — the specific run line / perturbation that covers THAT card;
- its **reason** — the `**Reason:**` required by `bounce-reason-gate`, written
  for that card, never pasted across the set;
- its **debt impact** — the `New debt introduced` value for that card, and (per
  `summary-nulls-gate`) the `Revisit trigger` when that value isn't none/unknown.

A batch-level "all proven, same fix" is not evidence — it is the absence of
evidence formatted to look like a conclusion. When you cannot write the per-card
line, the card is not closed: route it individually.

**Telemetry, not enforcement (this wave).** No hook checks this yet. If a batch
without per-card evidence appears in practice, record it as a counted occurrence
so the next wave knows whether prose was enough. Discipline first; a gate only
once the failure is observed.

## Constraints

- Default `--max 5`. Each card is an expensive proof; raise deliberately.
- **Coupled closure or individual closure — never batch-by-convenience.** See the
  section above; per-card evidence, reason, and debt impact are required even for
  a legitimately coupled set.
- **No stop-on-failure.** UNPROVEN and NEEDS-HUMAN are normal outcomes; the drain
  processes the whole confirmed batch. (Contrast `/board-flow:drain`, which stops
  on BLOCKED.)
- **Reserve antes de provar, card a card.** A listagem é uma foto; a reserva no
  board é o que impede duas sessões de provarem o mesmo card. Sem o claim
  publicado, o card não é trabalhado.
- Always confirm before starting. Don't prove N cards without buy-in. Mas
  confirme **uma vez só**: a confirmação do passo 3 carrega também a política
  para o que parar em NEEDS-HUMAN (`default-yes`).
- Per-card proof is FULL — don't shortcut to save time across cards.
- **Scope narrows, never widens.** It only subtracts cards from Review; `--no-scope` returns the full sweep. Show the effective scope on the confirmation screen, and surface a rejected scope JQL fragment as a config/flag error — not an empty Review queue.
- `atlassian-expert` is the only Jira write path.
