---
description: Executa a onda corrente de um plano do Maestro com uma ação — gc de órfãos, intake gate (cepa-dor), sobe o porteiro (shadow-mode no 1º programa), forka cada slice num worktree herdr com settings geradas + wrapper normativo, roda o event loop por arquivo, aterrissa a onda pelo merge train (reusa os guards do worktree-merge com verify pós-cada-merge) e relata. Morte da sessão é recuperável por /maestro:resume. Lê EXCLUSIVAMENTE o plan.yaml (invariante de costura). ⚠ Precisa do herdr rodando e do plugin instalado (bin/install.sh --clean).
argument-hint: [nome-do-programa] [--wave N] [--shadow] [--port P] · sem argumento, lista o que dá para rodar
interaction: routine
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
`acceptance_cmd`. **O modo listagem (Passo 0) não exige nada disso** — só lê
arquivos, e é justamente o que responde antes de o usuário ter um nome na mão.

## Variables

- `PROG` = `$1` (nome do programa). **Ausente = modo listagem, ver Passo 0** —
  o comando não roda nada e imprime as opções. · `PROGDIR` =
  `<raiz-principal>/.claude/programs/$PROG`
- `--wave N` (default: primeira onda `status: pending`)
- `--shadow` — força shadow-mode do porteiro (default: shadow SE for o 1º
  programa executado, senão deny ativo — ver Passo 3)
- `--port` (default 8765) — porta do porteiro

## Steps

0. **Sem `$1`: listar e parar.** Descobrir as opções custava dois comandos de
   shell e o conhecimento de dois campos que um `ls` não mostra — `mode` (um
   plano `single-track` não roda aqui) e o `status` das ondas (qual é a próxima
   pendente). Rode:
   ```
   python3 maestro/bin/maestro-programs .
   ```
   Ele lê a MESMA raiz que os passos abaixo (o clone principal), imprime por
   programa o modo, a próxima onda pendente e o veredito `RODA` / `não roda:
   <motivo>` — com a linha de comando pronta para copiar — e sinaliza restos de
   execução anterior (`wave-state.yaml`, porteiro órfão). Mostre a saída ao
   usuário e **pare aqui**: sem nome de programa não há onda a forkar. Não
   escolha um programa por conta própria.

1. **Carregar e validar o plano.** Leia `PROGDIR/plan.yaml`. Aceite
   `schema_version` 1 (legado, só ondas) e 2 (`mode` explícito); recuse
   qualquer outra. Confira `mode`: ausente (só em v1) ou `parallel-waves` segue o
   fluxo; **`single-track` não é executável aqui** — pare e diga que aquele
   plano é de um item por vez (`/common:next` responde qual é o próximo),
   e que promovê-lo a onda exige declarar superfície e aceite por item, com
   `/maestro:program-plan`. Qualquer outro valor é erro (ver
   `common/plan-schema.yaml`). Selecione a onda alvo (`--wave` ou a primeira
   pending).

   **Capturar o pane-lar da onda, AGORA — não na hora do fork.** Rode
   `herdr pane current` e guarde `pane_id`, `tab_id` e `workspace_id` (essa é
   a aba/Space que vai receber TODAS as filhas desta onda). O motivo de
   capturar aqui, antes até do intake gate, e não no passo 6 (spawn): entre
   este ponto e o primeiro fork se passam minutos (gc de órfãos, intake gate,
   subida do porteiro), e o foco muda nesse intervalo por qualquer clique do
   dono — o foco na hora do spawn é exatamente o valor errado. Na onda
   WEGO-paralelo (2026-08-24) o spawn não recebia `--tab`/`--workspace`
   nenhum e forkava a aba que estivesse em foco no momento; a evidência no
   `herdr-server.log` foi cinco `pane.spawn.start` sucessivos com a largura
   caindo pela metade a cada um (173 → 87 → 44 → 22 → 11 colunas) — a
   assinatura de cinco divisões da MESMA aba, que não era a do `/maestro:run`.
   Se `herdr pane current` falhar (sessão fora do herdr), o pane-lar não é "a
   aba que tiver foco quando alguém notar": abra uma aba nova e previsível,
   `herdr tab create --label <PROG> --no-focus`, e use o `root_pane` dela.
   Este pane-lar é persistido no passo 5 (`maestro-wave-state set-home`) e é
   contra ele — nunca contra o foco corrente — que o passo 6c divide.

2. **gc de órfãos** (o análogo do que o cepa-doctor faz para cepa-worktrees —
   restos de programas anteriores custam a próxima onda):
   - `herdr worktree list --cwd <raiz-principal> --json` → worktrees de programas
     já concluídos (o `--cwd` é obrigatório: sem ele o herdr 0.9.1 lista o repo
     do Space em FOCO, não o do diretório corrente);
   - porteiro órfão: `PROGDIR/gatekeeper/gatekeeper.pid` de PID morto;
   - panes zumbis (`herdr agent list` sem processo vivo);
   - escalações expiradas (`estado: pending`, `ttl` vencido).
   Liste o que achou e ofereça limpar. Só remova o que o usuário confirmar
   (exceto restos claramente do MESMO programa nesta reexecução). Worktree de
   programa concluído com `open_workspace_id` nessa lista:
   remova com `herdr worktree remove --workspace <open_workspace_id>` — é isso
   que derruba o Space junto (um `git worktree remove` puro tira a worktree do
   git e deixa o Space fantasma na barra lateral do herdr). Só sem
   `open_workspace_id` (o dono já fechou o Space à mão) use `git worktree
   remove` puro.

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
   Logo em seguida, persista o pane-lar capturado no passo 1:
   `python3 maestro/bin/maestro-wave-state set-home PROGDIR --pane <pane_id> --tab <tab_id> --workspace <workspace_id>`.
   É esse registro em disco — não uma variável da sessão — que o passo 6c e o
   `/maestro:resume` consultam para saber onde nascem as filhas.

6. **Fork por slice** (respeitando `max_concurrent_slices`):
   Para cada slice READY da onda:
   a. **Worktree herdr**, herdando o modelo do launcher `cepa` (single-owner guard + seed):
      `herdr worktree create --base <fork_point> --branch session/<PROG>-<slice> --json`.

      **Confirme pelo git antes de seguir — o `--json` de sucesso não basta.**
      Com o `path` devolvido pelo comando, rode no clone principal
      (`<raiz-principal>`, o pai de `git rev-parse --git-common-dir` sem o `/.git`):
      ```
      git -C <raiz-principal> worktree list --porcelain | grep -qx "worktree <path>"
      ```
      Só passe adiante (seed, settings, spawn) se essa linha existir.
      Por que a checagem existe: em 4 de 5 chamadas da onda WEGO-paralelo
      (2026-08-24, herdr 0.7.3), o `herdr worktree create` devolveu JSON de
      sucesso COMPLETO — com `path`, `branch`, `workspace_id` e
      `"is_prunable": false` — e o git não registrou worktree nenhuma; os
      diretórios também não existiam. O `herdr worktree list` seguia mostrando
      as fantasmas, porque ele mantém registro próprio. O gatilho não foi
      reproduzido e está fora do nosso alcance; o conserto daqui é não aceitar
      a palavra de ferramenta externa sobre um efeito que o git confere em um
      comando — mesmo padrão do marcador `MAESTRO-EXIT`, que sincroniza por
      ARQUIVO e não pelo pane. Sem a conferência, o seed, as settings e o
      `herdr agent start` rodam contra caminho inexistente e a onda inteira
      nasce morta falhando como se fosse problema das filhas.

      Se a linha não existir: remova o registro fantasma —
      `herdr worktree remove --workspace <workspace_id devolvido pelo create>
      --trust-repository`, tolerando erro (a forma posicional com o caminho
      direto NÃO existe no herdr 0.9.1 instalado: "unknown option: <path>",
      só `--workspace ID` identifica o alvo) — e tente **uma** vez mais.
      Persistindo, a slice é **FAIL** com detalhe nomeado —
      `maestro-wave-state set-slice PROGDIR <slice> fail --detail "worktree create reportou sucesso mas <path> não aparece em git worktree list (2 tentativas)"`
      — e as demais slices da onda **não** forkam em silêncio: pare o fork,
      mostre ao dono quais slices ficaram de fora e por quê.

      Rode o seed (`.env` etc.) copiando do main — NÃO symlink (recopla ao tree
      sincronizado). Dívida nomeada: o worktree do herdr fica em `~/.herdr/...`,
      não `~/cepa-worktrees` — herda o guard e o seed; o que não herdar é exceção.
   b. **Settings geradas** (camada 1) — o gerador grava o PAR de arquivos:
      `python3 maestro/bin/maestro-fork-settings PROGDIR/plan.yaml <slice> --port <P> --out-dir <worktree>`
      → `<worktree>/.claude/settings.json` (permissões) **e** `<worktree>/.mcp.json`
      (endereço do porteiro). Os dois são obrigatórios: sem as regras `ask` o
      porteiro nunca é consultado (achado do spike), e sem o `.mcp.json` a filha
      não enxerga a ferramenta do porteiro e morre na largada (achado da onda
      WEGO-paralelo, 2026-08-24 — `mcpServers` em settings.json é ignorado).
   c. **Spawn contra o pane-lar, com o wrapper normativo** (pipefail +
      PIPESTATUS, senão toda filha que falha reporta sucesso — bug real da
      rev1). O `herdr agent start` da versão instalada (0.9.1) não aceita mais
      `--cwd`, `--env`, `--tab`, `--workspace` nem um comando após `--`
      ("Start a supported interactive agent in an existing pane" — ele só
      inicia um agente numa pane que já existe); por isso o spawn é
      split-e-run contra o pane-lar registrado no passo 5
      (`maestro-wave-state get PROGDIR`, campo `home.pane`), NUNCA contra o
      pane que estiver em foco:
      ```
      herdr pane split <home.pane> --direction right --cwd <worktree> \
        --env MAESTRO_LINGER=600 --no-focus
      # → devolve o novo pane_id
      herdr pane rename <novo-pane> <PROG>-<slice>
      herdr pane run <novo-pane> "bash -c 'set -o pipefail; claude -p \"<prompt-do-slice>\" \
        --mcp-config .mcp.json --strict-mcp-config \
        --permission-prompt-tool mcp__gatekeeper__permission_prompt \
        2>&1 | tee resultado.txt; ec=\${PIPESTATUS[0]}; \
        echo \"MAESTRO-EXIT:\$ec\" | tee -a resultado.txt; \
        sleep \"\$MAESTRO_LINGER\"'"
      ```
      **O `\$` antes de `{PIPESTATUS[0]}`, `ec` e `MAESTRO_LINGER` é
      proposital, não sujeira de escape.** O `herdr pane run` acima roda no
      shell duplo-aspeado da PRÓPRIA sessão do maestro (quem está montando o
      comando), não no shell da filha. Sem o `\`, essas três variáveis
      expandem AQUI — vazias, porque não existem neste shell — antes do texto
      chegar à pane filha: o resultado seria `ec=`, `MAESTRO-EXIT:` sem
      código e `sleep ""`, quebrando silenciosamente a sincronização por
      arquivo que o `maestro-poll` depende (confirmado ao vivo: rodar a
      receita sem o `\` produz exatamente isso). Nunca "limpe" essas barras
      achando que sobraram por engano.
      **Nunca divida o pane que estiver em foco e nunca omita o id do
      pane-lar** — `--no-focus` só impede que o pane novo ROUBE o foco depois
      de criado, ele não escolhe onde o pane nasce (quem escolhe é o primeiro
      argumento de `herdr pane split`). `herdr pane split` cria o pane novo NA
      ABA do pane que você apontar, sem olhar qual aba está em foco no
      momento — é essa propriedade que resolve o item (probado ao vivo: uma
      aba sem foco recebeu o split e ficou com o pane novo; a aba com foco não
      mudou).
      `--mcp-config .mcp.json --strict-mcp-config` NÃO é opcional: sem ele a
      filha sobe sem o porteiro, `--permission-prompt-tool` aponta para ferramenta
      inexistente e o processo aborta com
      `MCP tool mcp__gatekeeper__permission_prompt not found` / exit 1 — a onda
      inteira nasce morta (aconteceu em WEGO-paralelo, 2026-08-24). O
      `--strict-mcp-config` ainda impede que os MCPs pessoais do dono vazem para
      a filha headless.
      O `tee -a` do marcador é o que deixa o `MAESTRO-EXIT:` no `resultado.txt`,
      não só no painel — é por arquivo que o `maestro-poll` sincroniza.
      O `<prompt-do-slice>` traz a demanda, a superfície, o `acceptance`/
      `acceptance_cmd`, o `context` e a disciplina autonomous-mode.
      `maestro-wave-state set-slice PROGDIR <slice> running --pane <novo-pane> --worktree <path>`.

      **Fallback: pane-lar morto.** Se o `herdr pane split` devolver
      `pane_not_found` (a aba do pane-lar foi fechada), não caia de volta no
      foco corrente — abra uma aba nova e previsível no mesmo Space:
      `herdr tab create --workspace <home.workspace> --label <PROG> --cwd <worktree> --env MAESTRO_LINGER=600 --no-focus`,
      use o `root_pane` devolvido como o pane desta slice (rename + run como
      acima) e **atualize o pane-lar** com
      `maestro-wave-state set-home PROGDIR --pane <root_pane> --tab <tab-da-nova-aba> --workspace <home.workspace>`
      para que as próximas slices desta onda também nasçam ali, em vez de cada
      uma abrir sua própria aba nova.

7. **Event loop da onda** (obrigatório — sem ele há deadlock). Em rodízio, até a
   onda terminar:
   - `python3 maestro/bin/maestro-poll PROGDIR` (sincroniza por ARQUIVO, não
     pelo pane). Para cada transição, `set-slice` o estado terminal
     (DONE/FAIL/TIMEOUT/ESCALATED); em TIMEOUT, mate a filha via herdr.
   - **Escalações**: para cada uma pending, apresente ao humano (ação, slice,
     contexto, opções). Grave a decisão no próprio `escalations/<id>.yaml`
     (`estado: answered`) e **re-spawne a filha** injetando "decisão do dono
     sobre <id>: ..." no prompt — ela continua do worktree onde parou. O
     re-spawn usa a MESMA receita do passo 6c (`herdr pane split` contra o
     pane-lar de `maestro-wave-state get PROGDIR` → `home.pane`, rename, `herdr
     pane run`) — nunca o foco corrente do momento.
   - **Retentativa com nome novo** (`S-2067R` nascendo de `S-2067`): forka pela
     mesma receita do passo 6c contra o pane-lar registrado, e registre-a
     no mesmo instante em que forka,
     `maestro-wave-state set-slice PROGDIR <slice>R running --pane <id> --worktree <path>
     --detail "retentativa de <slice>"`. Na onda 1 do WEGO-paralelo as
     retentativas só entraram no wave-state na onda seguinte, e duas sessões
     acharam que eram donas delas.
   - **Saúde do porteiro**: se `poll` reportar `gatekeeper.alive:false`,
     ressuba-o (mesma porta/state) e siga — filha sem porteiro recebe deny e
     escala (fail-mode declarado).
   - Aguarde entre iterações (o `poll` é barato; não faça busy-loop apertado).

8. **Fronteira de término** (antes do merge train — mecânica, não impressão de
   quem estava conduzindo):

   ```
   python3 maestro/bin/maestro-wave-state check-terminal PROGDIR
   ```

   Exit 0 = toda slice em estado terminal (`DONE|LANDED|FAIL|TIMEOUT|ESCALATED`).
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
   - `maestro-wave-state landed PROGDIR <slice>` a cada merge (a slice passa de
     `DONE` para `LANDED`). É isso que deixa `aguardando-merge` responder, depois
     de uma sessão morta, o que ficou para aterrissar: `DONE` sem `LANDED` é o
     que o `/common:next` e o doctor cobram como ação sua;
   - **prune só ao fim da onda inteira** (worktree é barato; evidência não
     volta): `python3 maestro/bin/maestro-prune PROGDIR --repo <raiz-principal>`.
     Cada slice é um Space na barra lateral do herdr (`herdr worktree create`
     cria worktree **e** Space); sem prune uma onda de 5 slices deixa 5 Spaces
     — em 2026-08-24 havia 11 sobrando de duas ondas. O `maestro-prune` remove
     Space + worktree só das slices LANDED (`herdr worktree remove --workspace`
     derruba os dois numa tacada, e o resultado é confirmado pelo git — não
     pela palavra do herdr, mesmo princípio do passo 6a); mantém as demais
     (DONE-não-aterrissada, FAIL/TIMEOUT/ESCALATED, pending, running) porque a
     evidência delas ainda pode servir; e nunca força uma worktree suja — reporta
     e deixa o dono decidir. Mostre a saída dele no relatório do passo 10.

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
