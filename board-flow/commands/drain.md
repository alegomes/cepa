---
description: Bulk-execute Jira cards from a column (default = `defaults.status_map.to_do` from `board-flow.yaml`, fallback "To Do"). Iterates through up to N cards in the order the single-track queue (`<programs>/<project_key>/plan.yaml`) puts them, when one exists — cards outside the queue follow, in Jira priority/rank order; with no queue, falls back to Jira priority/rank order as before. Stops on first BLOCKED to avoid wasting budget on a stuck card. Heavy operation — each card runs the full execution flow. The split between Backlog (unrefined) and `to_do` (ready for dev) is intentional: drain only pulls from `to_do`, so unrefined Backlog items stay safe.
argument-hint: [column] [--max N] [--scope "<jql>"] [--no-scope]
interaction: routine
---

# /board-flow:drain

## Purpose

Bulk-execute pending Jira cards. Iterates through cards in a column (default = `defaults.status_map.to_do` from `board-flow.yaml`, fallback `"To Do"`), running the equivalent of `/board-flow:execute` on each. Stops on first BLOCKED card.

Why `to_do` and not Backlog: the project convention encoded in `status_map` is that Backlog holds unrefined / unprioritized items, and `to_do` holds items refined and ready for development. Drain pulls only from `to_do` so the team's grooming process stays meaningful.

**Heavy operation:** each card runs the full plan-track-build-validate flow. Use `--max` to cap the number of cards processed in a single drain. Default `--max 5`.

## Variables

- `$ARGUMENTS` — typically the column name followed optionally by `--max N`. If empty, defaults: column = `defaults.status_map.to_do` from `board-flow.yaml` (fallback `"To Do"` if no config), max = 5.
- `--scope "<jql>"` — a raw JQL fragment that narrows the drain to a slice of the column for this run only, overriding any configured scope.
- `--no-scope` — ignore configured scope entirely; sweep the whole column.

**Scope** lets you drain a slice of the column (a sprint, a team, a label) instead of all of it. By default the drain applies the effective scope resolved from `board-flow.yaml` (`defaults.scope` / `scope_overrides.drain` / the active topology's `scope`); the two flags above override that for one run. You don't resolve the precedence yourself — pass the command name and any flag to `atlassian-expert`, which resolves and reports the effective fragment.

## Instructions

You are the orchestrator. Iterate through pending cards. Stop on first BLOCKED. Apply `till-done` within each card's execution loop, `scope-discipline` across the drain (don't process more than `--max`).

## Workflow

### 1. Parse arguments

- Column name: `$ARGUMENTS` minus any flag (`--max N`, `--scope "..."`, `--no-scope`). If empty, read `defaults.status_map.to_do` from `board-flow.yaml`; if config missing entirely, fallback to literal `"To Do"`.
- Max cards: parse `--max N` from `$ARGUMENTS`. Default: 5.
- **Claim id do run:** gere um, agora, como descrito em **Reserva do card**. Ele identifica ESTE run em todos os cards que ele tocar.
- Scope flags: detect `--no-scope` and `--scope "<jql>"`. They are mutually exclusive; if both appear, abort with "pass either --scope or --no-scope, not both." Build the **scope directive** to hand to `atlassian-expert`: `--no-scope` → `Scope: none`; `--scope "<jql>"` → `Scope: <jql>`; neither → omit the line (atlassian-expert resolves the effective scope from config).

### 2. List pending cards

Resolve the single-track queue first, because it changes how many cards to ask
for: `<programs>/<project_key>/plan.yaml` (`<programs>` = `<main-root>/.claude/programs`,
`<main-root>` = the main clone, never the current worktree's own `.claude/`;
`<project_key>` from `board-flow.yaml`). Check whether that file exists before
delegating.

Delegate to `atlassian-expert` (the `Command:` line tells it to resolve scope for `drain`; include the scope directive only if a flag was passed):

> Command: drain
> <Scope: ... — only if a flag was passed>
>
> List Jira issues where `status = "<column>"` in the project, applying the effective drain scope, ordered by priority and rank. Limit to <the whole column, no limit, if the single-track queue exists — otherwise <max>> cards. Return key + summary + priority for each, plus the effective scope you used.

**Why the whole column when a queue exists:** `--max` caps how many cards this
run *executes*, not how many exist. Asking Jira for only the first `<max>` in
its own priority/rank order, then reordering by the queue, could cut off the
queue's actual first items if Jira's rank disagrees — the cap has to apply
*after* reordering (step 2b), never before.

If 0 cards → report "Nothing in column <column>" (note the effective scope, so an empty result from an over-narrow filter is obvious, not mistaken for an empty board) and stop.

### 2b. Reorder by the queue, if one exists

- No `plan.yaml` for `<project_key>` → keep Jira's priority/rank order exactly
  as listed in step 2 (today's behavior). Skip to step 3.
- `plan.yaml` exists → run:

  ```
  python3 common/bin/cepa-plan ordena <project_key> --keys <K1,K2,...> --json
  ```

  passing every key step 2 returned, in the order Jira gave them. The command
  returns the queue's order for keys that are items of it, then the rest —
  `fora_do_plano` — in the Jira order they came in. Use that combined order for
  steps 3 onward. Exit 2 (no queue after all — e.g. it was removed between the
  two calls) falls back to Jira order, same as "no `plan.yaml`" above.
- Cards in `fora_do_plano` are **named** in the step-3 confirmation screen and
  the final report, with the hint that `/common:plan <project_key> --from-jira`
  or `python3 common/bin/cepa-plan add <project_key> <key> --title "..."` is
  what puts a card into the queue.
- Apply `--max` to the reordered list now, not to the raw Jira listing from
  step 2.

### 3. Confirm with user

Show the user (order = the queue's, when step 2b found one; Jira's otherwise):

```
Found N cards in <column> (scope: <effective scope, or "none — whole column">)<, queue: <project_key> — if a plan.yaml drove the order>:
  WEGO-1234 (P1) — <summary>
  WEGO-1235 (P2) — <summary>  (fora do plano — só entra na fila com /common:plan <project_key> --from-jira ou cepa-plan add)
  ...

Drain these? Each card runs the full execute flow (planning audit + build + validate + Jira transitions).

E se um card travar (BLOCKED — condição fora do card, que só você resolve):
  (a) paro o run ali e te chamo                        ← default
  (b) pulo o card, registro o motivo e sigo com os demais

Reply yes / no / first-N (e.g., "first-2") to drain only a subset, e (a) ou (b)
para o card travado. Só "sim" vale como sim + (a).
```

Wait for user confirmation before proceeding. **Esta é a única parada
planejada do run** — aplique `default-yes`.

**A alternativa (a)/(b) tem que estar ESCRITA na tela acima, não implícita.**
Um "posso ir?" que só mostra a contagem de cards não colhe resposta nenhuma
sobre o card travado: no card 3 de 5 o run para para perguntar, e aí o usuário
já perdeu o contexto da lista — que é exatamente o custo que a parada única
existe para evitar. Perguntar na largada custa duas linhas de tela.

Se o run veio de `/common:session`, essas respostas já foram colhidas — siga
sem perguntar.

### 4. Iterate

For each card the user confirmed:

  a. **Reserve o card primeiro** — releia status + comentários e publique o claim, conforme **Reserva do card** abaixo. Se o card foi pulado (saiu da coluna ou está reservado por outra sessão), registre `SKIPPED` e vá para o próximo card SEM rodar nada.
  b. Run the equivalent of `/board-flow:execute <card-key>` (full detail audit + build + validate + transitions).
  c. Capture the verdict.
  d. **If verdict is BLOCKED:** siga a política escolhida na confirmação do
     passo 3 — parar (default) ou pular o card e continuar. Em ambos os casos:
     - Se o card parou sem receber comentário de veredito, publique a liberação do claim (`🔓`) antes de seguir.
     - Registre o card e o motivo para o relatório final; **não pergunte nada
       agora** — o usuário já respondeu essa pergunta na largada.
     - Parando: vá para o passo 5 (relatório final). Pulando: próximo card.
  e. **If READY-TO-SHIP or READY-WITH-CAVEATS:**
     - Continue to the next card.
  f. Record that card's **outcome terminal** before moving on (see below). A card
     you touched and cannot name an outcome for is an unfinished card, not a
     quiet success.

### 4b. Outcome terminal — no card leaves the drain unnamed

The drain does not finish while any attempted card lacks a named terminal
outcome. Every card you touched ends in exactly one of:

| Outcome | Means |
|---|---|
| `SHIPPED` | moved to In Review / done, verdict recorded |
| `BLOCKED` | stopped on a condition outside the card — name the condition and who clears it |
| `DEFERRED` | deliberately postponed — name what must be true to pick it up |
| `DROPPED` | will not be done — name why |
| `ERROR` | the run itself failed (infra, permissions) — name the failure |
| `SKIPPED` | outra sessão já tinha o card (reserva ativa) ou ele saiu da coluna — nomeie qual das duas |

"In progress", "partially done", "needs attention" and silence are **not**
outcomes. They are the absence of a decision wearing a status label, and they are
how a card returns to the board next week with nobody knowing what happened to
it. If you cannot name the outcome, the honest terminal is `BLOCKED` with the
reason "outcome undetermined: <what you don't know>".

This mirrors the same rule the maestro applies per wave (a wave doesn't land with
a non-terminal slice) — one discipline, two surfaces.

### 5. Final report

A single summary message:

- **Drained from column:** <column> (scope: <effective scope, or "none">)
- **Order:** queue `<project_key>` (`<programs>/<project_key>/plan.yaml`), or "Jira priority/rank (no queue for `<project_key>`)"
- **Out of the queue (drained in Jira order, after the queued ones):** keys, or "none" — only when a queue drove the order; name them and repeat the hint (`/common:plan <project_key> --from-jira` or `cepa-plan add`)
- **Cards attempted:** N — each with its outcome terminal (`SHIPPED` / `BLOCKED` / `DEFERRED` / `DROPPED` / `ERROR`). The count of attempted cards MUST equal the count of named outcomes; if it doesn't, the drain is not finished.
- **Moved to In Review:** M (list keys + verdicts)
- **Blocked:** 0 or 1 (key + reason)
- **Skipped:** count (keys + reserva de qual sessão, ou para qual status o card já tinha ido)
- **Remaining in column (not attempted this run):** count
- **Approximate cost:** sum of per-card durations (informational)
- **Next step suggestion:** if any blocked, surface the block; if all drained, suggest re-running for the next batch if more remain.

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
(resumo de implementação, bounce com `**Reason:**`) já é o sinal de que a reserva
acabou. Quando o card termina SEM veredito (`ERROR`, `BLOCKED` sem comentário,
interrupção do run), publique a liberação explícita, senão o card fica intocável
por 90 minutos:

> `🔓 claim <claim-id> liberado — <motivo>.`

**Por que 90 minutos e não um lock permanente:** uma sessão que morre no meio não
pode congelar a fila. A janela é maior que o tempo de um card e menor que um
turno de trabalho, então uma reserva órfã se resolve sozinha sem ninguém precisar
destravar nada à mão.

**Cards pulados não consomem `--max`** — nenhum trabalho rodou neles. Eles
aparecem no relatório final com o motivo, porque "sumiu da lista sem explicação"
é exatamente o buraco que este mecanismo existe para fechar. Um `SKIPPED` também
**não** para o drain: só `BLOCKED` para.

## Constraints

- Default `--max 5`. Higher values risk runaway cost; set explicitly to override.
- Stop-on-first-BLOCKED is intentional. We don't keep pushing through stuck work.
- Each card's per-Task loop is FULL — don't shortcut to "save time" across cards. The whole point of the topology is per-Task quality.
- If `atlassian-expert` can't list cards (permissions issue, malformed column name, or a rejected scope JQL fragment), abort with a clear error — surface a rejected scope fragment as a config/flag problem, not an empty column.
- **Scope narrows, never widens.** The effective scope only ever subtracts cards from the column; `--no-scope` is the way back to the full sweep. Always show the effective scope on the confirmation screen so the user sees what's being excluded.
- **Reserve antes de executar, card a card.** A listagem é uma foto; a reserva no board é o que impede duas sessões de construírem o mesmo card. Sem o claim publicado, o card não é trabalhado.
- Always confirm with the user before starting the drain. Don't auto-execute on N cards without buy-in.
