---
description: Recupera uma onda do Maestro interrompida — reconstrói o estado a partir de .claude/programs/<nome>/wave-state.yaml (filhas vivas, estado por slice, porteiro, escalações pendentes, merges já aterrissados) e continua o event loop / merge train de onde parou. Nos moldes do /common:autonomous-resume. Use após morte da sessão, crash ou token-limit no meio de um /maestro:run.
argument-hint: <nome-do-programa>
interaction: routine
---

# /maestro:resume

## Purpose

Morte da sessão maestro é o modo de falha mais provável de uma sessão longa. O
`/maestro:run` escreve `wave-state.yaml` a cada transição justamente para que
esta retomada seja possível sem re-forkar o que já roda nem re-mergear o que já
aterrissou. Reusa o padrão do `/common:autonomous-resume` — não inventa outro.

## Steps

1. **Ler o estado.**
   `python3 maestro/bin/maestro-wave-state get <raiz-principal>/.claude/programs/$1 --json`
   — `<raiz-principal>` é o pai de `git rev-parse --git-common-dir` sem o `/.git`
   final (o clone principal, quando você está numa worktree ligada); o estado do
   programa é do repo, não desta árvore.
   Se não existir, pare: não há onda em andamento para este programa (talvez
   queira `/maestro:run $1`).

2. **Reconciliar contra a realidade** (o wave-state descreve o passado — CLAUDE.md
   manda verificar antes de afirmar):
   - **porteiro**: `GET /health` na URL registrada. Morto → ressuba
     (`maestro-gatekeeper --state-dir .../gatekeeper --port <P>` no mesmo modo)
     e atualize o pid via `set-gk`.
   - **filhas `running`**: confira se o pane ainda vive com
     `herdr pane get <pane>` (o id gravado em `slices.<slice>.pane`; a
     liveness NÃO é mais por agente — o herdr 0.9 já não tem esse comando de
     agente para isto) E se o `resultado.txt` já
     tem `MAESTRO-EXIT`. Filha morta sem marcador → trate como a próxima
     iteração do poll decidirá (TIMEOUT se estourou o prazo); filha viva →
     segue no loop. Qualquer re-spawn (filha morta, escalação respondida)
     usa o pane-lar gravado no wave-state
     (`maestro-wave-state get <PROGDIR> --json` → `home.pane`/`home.tab`/
     `home.workspace`), com a mesma receita `herdr pane split` + rename +
     `herdr pane run` do `/maestro:run` (passo 6c) — nunca o foco corrente
     desta sessão de resume, que pode nem ser a mesma aba da onda original.
   - **merges**: slice `LANDED` (ou, em wave-state antigo, nome na lista
     `landed:`) já entrou no main; não re-mergeie.

3. **Onda terminada sem merge vai direto ao merge train.** Se
   `maestro-wave-state check-terminal` sai 0 e
   `maestro-wave-state aguardando-merge` lista slices, a onda não está "sem nada
   rodando": está esperando você. Pule o event loop e retome o `/maestro:run` no
   Passo 9 (merge train) com essas slices. Concluir "não há nada rodando" e parar
   é o que deixou cinco branches prontas paradas na onda 1 do WEGO-paralelo.

4. **Continuar.** Nos outros casos, retome o `/maestro:run` a partir do Passo 7 (event loop):
   `maestro-poll` em rodízio → transições → escalações → merge train dos DONE
   ainda não em `landed`. Slices FAIL/TIMEOUT/ESCALATED da onda re-forkam na
   próxima onda, como no fluxo normal.

5. **Relatar** o que foi reconstruído (porteiro ressuscitado? filhas ainda
   vivas? merges já feitos?) antes de prosseguir, para o usuário ver o estado
   herdado — não afirme "retomado" sem mostrar a reconciliação.

## Notes

- Idempotente por desenho: reprocessar um `resultado.txt` já lido só reafirma o
  mesmo estado terminal; re-tentar um merge já em `landed` é pulado.
- Se o plano em si mudou desde a interrupção, PARE e avise — resume assume o
  mesmo plan.yaml da onda registrada.
