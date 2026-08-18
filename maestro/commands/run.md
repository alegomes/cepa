---
description: Executa a onda corrente de um plano do Maestro com uma ação — gc de órfãos, intake gate (cepa-dor), sobe o porteiro (shadow-mode no 1º programa), forka cada slice num worktree herdr com settings geradas + wrapper normativo, roda o event loop por arquivo, aterrissa a onda pelo merge train (reusa os guards do worktree-merge com verify pós-cada-merge) e relata. Morte da sessão é recuperável por /maestro:resume. Lê EXCLUSIVAMENTE o plan.yaml (invariante de costura). ⚠ Precisa do herdr rodando e do plugin instalado (bin/install.sh --clean).
argument-hint: <nome-do-programa> [--wave N] [--shadow] [--port P]
---

# /maestro:run

## Purpose

A ação única do Maestro: sair de um `plan.yaml` aprovado para N sessões reais
criadas, geridas e integradas. Este comando NÃO planeja (isso é
`/maestro:program-plan`) e NÃO interpreta o BACKLOG — lê só
`PROGDIR/plan.yaml`.

**`PROGDIR` = `<raiz-principal>/.claude/programs/<nome>`**, e `<raiz-principal>`
é o pai de `git rev-parse --git-common-dir` sem o `/.git` final — em worktree
ligada isso aponta para o CLONE PRINCIPAL, não para a árvore atual; fora dela é o
mesmo que `git rev-parse --show-toplevel`. O plano é estado do repo, não da
sessão: escrito dentro de worktree de sessão, morre com ela (e num repo cujo
`.gitignore` cobre `.claude/` inteiro, nenhuma guarda do caminho de remoção
enxerga o arquivo). Vale para ler e para escrever. Ver
`docs/execution-plan.md`, "Where the file lives".

**Pré-condições** (pare e diga ao usuário se faltar): herdr rodando
(`herdr agent list` responde); plugin instalado após `bin/install.sh --clean`;
plano existe e passa no intake. Repo `.claude/no-build`: cada slice traz
`acceptance_cmd`.

## Variables

- `PROG` = `$1` (nome do programa) · `PROGDIR` = `<raiz-principal>/.claude/programs/$PROG`
- `--wave N` (default: primeira onda `status: pending`)
- `--shadow` — força shadow-mode do porteiro (default: shadow SE for o 1º
  programa executado, senão deny ativo — ver Passo 3)
- `--port` (default 8765) — porta do porteiro

## Steps

1. **Carregar e validar o plano.** Leia `PROGDIR/plan.yaml`. Aceite
   `schema_version` 1 (legado, só ondas) e 2 (`mode` explícito); recuse
   qualquer outra. Confira `mode`: ausente (só em v1) ou `parallel-waves` segue o
   fluxo; **`single-track` não é executável aqui** — pare e diga que aquele
   plano é de um item por vez (`/common:next` responde qual é o próximo),
   e que promovê-lo a onda exige declarar superfície e aceite por item, com
   `/maestro:program-plan`. Qualquer outro valor é erro (ver
   `common/plan-schema.yaml`). Selecione a onda alvo (`--wave` ou a primeira
   pending).

2. **gc de órfãos** (o análogo do que o cepa-doctor faz para cepa-worktrees —
   restos de programas anteriores custam a próxima onda):
   - `herdr worktree list --json` → worktrees de programas já concluídos;
   - porteiro órfão: `PROGDIR/gatekeeper/gatekeeper.pid` de PID morto;
   - panes zumbis (`herdr agent list` sem processo vivo);
   - escalações expiradas (`estado: pending`, `ttl` vencido).
   Liste o que achou e ofereça limpar. Só remova o que o usuário confirmar
   (exceto restos claramente do MESMO programa nesta reexecução).

3. **Intake gate.** Rode
   `python3 common/bin/cepa-dor PROGDIR/plan.yaml --wave N --repo .`.
   Qualquer NOT-READY **barra a onda** — mostre as lacunas nomeadas e pare;
   o conserto é no `/maestro:program-plan`, não aqui. Avisos ⚠ passam.

4. **Subir o porteiro.** Decida o modo: **shadow-mode** se este é o 1º programa
   do Maestro (não há `~/.claude/cepa-telemetry` com `program_done` anterior)
   OU `--shadow` foi passado; senão deny ativo. Suba:
   ```
   python3 maestro/bin/maestro-gatekeeper --state-dir PROGDIR/gatekeeper \
     --port <P> [--shadow] &
   ```
   Confirme `GET http://127.0.0.1:<P>/health` = 200. Registre:
   `maestro-wave-state set-gk PROGDIR --pid <PID> --url http://127.0.0.1:<P>/mcp`.

5. **Inicializar o estado da onda.**
   `python3 maestro/bin/maestro-wave-state init PROGDIR --plan PROGDIR/plan.yaml --wave N`.

6. **Fork por slice** (respeitando `max_concurrent_slices`):
   Para cada slice READY da onda:
   a. **Worktree herdr**, herdando o modelo do launcher `cepa` (single-owner guard + seed):
      `herdr worktree create --base <fork_point> --branch session/<PROG>-<slice> --json`.
      Rode o seed (`.env` etc.) copiando do main — NÃO symlink (recopla ao tree
      sincronizado). Dívida nomeada: o worktree do herdr fica em `~/.herdr/...`,
      não `~/cepa-worktrees` — herda o guard e o seed; o que não herdar é exceção.
   b. **Settings geradas** (camada 1):
      `python3 maestro/bin/maestro-fork-settings PROGDIR/plan.yaml <slice> --port <P>`
      → grave em `<worktree>/.claude/settings.json`. Sem as regras `ask` o
      porteiro nunca é consultado (achado do spike — já embutido no gerador).
   c. **Spawn com o wrapper normativo** (pipefail + PIPESTATUS, senão toda
      filha que falha reporta sucesso — bug real da rev1):
      ```
      herdr agent start <PROG>-<slice> --cwd <worktree> \
        --env MAESTRO_LINGER=600 -- \
        bash -c 'set -o pipefail; claude -p "<prompt-do-slice>" \
          --permission-prompt-tool mcp__gatekeeper__permission_prompt \
          2>&1 | tee resultado.txt; ec=${PIPESTATUS[0]}; \
          echo "MAESTRO-EXIT:$ec"; sleep "$MAESTRO_LINGER"'
      ```
      O `<prompt-do-slice>` traz a demanda, a superfície, o `acceptance`/
      `acceptance_cmd`, o `context` e a disciplina autonomous-mode.
      `maestro-wave-state set-slice PROGDIR <slice> running --pane <id> --worktree <path>`.

7. **Event loop da onda** (obrigatório — sem ele há deadlock). Em rodízio, até a
   onda terminar:
   - `python3 maestro/bin/maestro-poll PROGDIR` (sincroniza por ARQUIVO, não
     pelo pane). Para cada transição, `set-slice` o estado terminal
     (DONE/FAIL/TIMEOUT/ESCALATED); em TIMEOUT, mate a filha via herdr.
   - **Escalações**: para cada uma pending, apresente ao humano (ação, slice,
     contexto, opções). Grave a decisão no próprio `escalations/<id>.yaml`
     (`estado: answered`) e **re-spawne a filha** injetando "decisão do dono
     sobre <id>: ..." no prompt — ela continua do worktree onde parou.
   - **Saúde do porteiro**: se `poll` reportar `gatekeeper.alive:false`,
     ressuba-o (mesma porta/state) e siga — filha sem porteiro recebe deny e
     escala (fail-mode declarado).
   - Aguarde entre iterações (o `poll` é barato; não faça busy-loop apertado).

8. **Fronteira de término** (antes do merge train — mecânica, não impressão de
   quem estava conduzindo):

   ```
   python3 maestro/bin/maestro-wave-state check-terminal PROGDIR
   ```

   Exit 0 = toda slice em estado terminal (`DONE|FAIL|TIMEOUT|ESCALATED`).
   Exit 2 = ainda há slice pendurada, e o comando nomeia quais. **Com exit 2 não
   siga para o merge train nem para o relatório**: volte ao event loop, ou force
   o estado terminal honesto (`set-slice PROGDIR <slice> ESCALATED --detail "<o
   que ficou sem resposta>"`). `pending`/`running` não são resultados — são a
   ausência de um, e a onda que aterrissa com slice ali dentro faz essa slice
   sumir do radar sem ninguém ter decidido nada sobre ela.

9. **Merge train** (pós-onda — REUSA os guards do `/common:worktree-merge`,
   nunca reimplementa):
   - só slices DONE entram; FAIL/TIMEOUT/ESCALATED re-forkam na onda seguinte a
     partir do main novo (a onda NÃO trava);
   - ordem determinística (ordem do plano); para cada: green-gate + single-owner
     + `git merge --no-ff`; **verify no main integrado após CADA merge** (não só
     o verify do slice — conflito semântico entre superfícies disjuntas só
     aparece aqui). Vermelho pós-merge → revert do merge, slice vira FAIL;
   - conflito → PARE e mostre (não auto-resolva);
   - `maestro-wave-state landed PROGDIR <slice>` a cada merge;
   - **prune só ao fim da onda inteira** (worktree é barato; evidência não volta).

10. **Relatório + debrief.** Só depois do passo 8 verde. Resuma: veredito de
   intake por slice, estados terminais, escalações e como foram decididas,
   merges aterrissados, o que re-forka. Liste as decisões de zona-cinza/escalada do porteiro (elas entram
   no debrief default independente da altitude). Emita a telemetria
   (`program_start/wave_done/...`) e diga o próximo passo (onda seguinte ou fim).

## Notes

- **Invariante de costura:** este comando lê só o plan.yaml. Fontes futuras
  (Jira/board-flow, discovery) entram escrevendo um plan.yaml válido.
- **Recuperação:** o wave-state é escrito a cada transição; se a sessão morrer,
  `/maestro:resume <PROG>` reconstrói a onda de onde parou.
- **Shadow-mode** (1º programa): o porteiro aprova tudo e loga o que TERIA
  negado/escalado — mede se o intake consegue zerar escalações, em vez de exigir
  plantar uma. Deny ativo a partir do 2º, com regras calibradas pelo log.
- **Escopo de aprovação (porteiro e escalações):** cada aprovação libera SÓ o
  comando/pedido apresentado, nunca a filha nem a onda. Uma escalação decidida
  pelo humano vale para aquela instância; a mesma classe de pedido volta ao
  porteiro na próxima ocorrência. "Aprovei uma vez" não vira allowlist implícita
  — allowlist é mudança de regra, feita nas settings geradas, com intenção.
- Sincronização é por arquivo (resultado.txt + wave-state); o pane do herdr é
  observabilidade. O contrato dos marcadores `MAESTRO-EXIT:*` é string-match
  versionado com o plugin — smoke-teste a cada upgrade do herdr E do Claude Code.
