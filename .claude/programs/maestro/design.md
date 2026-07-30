# Maestro v1 — design (rev2.1)

**Status:** rev2.1 — rev2 + achados do spike do porteiro (passo 1 da ordem de construção, 2026-07-15, VIÁVEL — evidência em `maestro/spike-gatekeeper/SPIKE-RESULTS.md`) · **Data:** 2026-07-12
**Origem:** BACKLOG.md § "Maestro — orquestração multi-harness" (spike herdr aprovado 2026-07-11)
**Decisões de dono:** 7 fechadas em 2026-07-12; D3 refinada e D5 ajustada na ratificação pós-painel (mesma data).
**Síntese do painel:** `.claude/programs/maestro/advisors-sintese.md` (7 lentes, 53 achados).

## Glossário (3 linhas)

- **Programa** — um universo de demandas aprovado pelo dono (ex.: melhorias-2026-07). **Demanda** — um item do BACKLOG dentro do programa (P1, P2…). **Slice** — a unidade de execução: uma demanda empacotada para UMA sessão em UM worktree (normalmente 1 demanda = 1 slice; uma demanda grande pode virar 2+ slices). **Onda** — um grupo de slices que rodam em paralelo a partir do mesmo fork point.
- **herdr** — gerenciador local de terminais/sessões (daemon com socket em `~/.config/herdr/herdr.sock`; CLI = wrappers JSON do socket). Oferece: spawnar processos em *panes* visíveis (`agent start`), esperar por um marcador no output (`wait output --match`), criar worktrees fora do repo (`worktree create` → `~/.herdr/worktrees/<repo>/`). Spike de viabilidade 2026-07-11 registrado em BACKLOG.md § Maestro.
- **Vocabulário da casa:** *merge train* = integrar os branches dos slices no main um a um, com verificação entre cada passo; *autonomous-mode* = disciplina de sessão sem perguntas ao humano, toda decisão logada (docs/autonomous-mode.md); *taxonomia de altitude* = classificação de decisões em `strategic` (escopo, contrato, breaking change, naming user-facing) / `tactical` / `implementation`, definida pelo /common:debrief; *`.claude/no-build`* = opt-out committado de repo sem build reconhecido; *ledger* = telemetria em `~/.claude/cepa-telemetry/` via `common/hooks/_telemetry.py`.

## Problema

Planejar um universo de demandas em ondas de sessões concorrentes hoje é trabalho
artesanal, e o despacho é manual (abrir N terminais, colar N comandos, integrar N
resultados). Queremos: plano discutido e aprovado → **uma ação** → N sessões criadas
e geridas por um agente central que media decisões e reporta o resultado final.

O v0 (programa melhorias-2026-07, `.claude/programs/melhorias-2026-07/plan.yaml`)
validou o formato plan.yaml + ondas + merge train usando subagentes worktree da
própria sessão: 3 ondas aterrissadas, 1 conflito real de merge (atlassian-expert.md,
Onda 2 — dois slices tocaram o mesmo arquivo porque a superfície não era declarada
nem checada; esse incidente motiva a checagem de superfície disjunta do intake).
O v1 formaliza isso como plugin, adiciona o intake gate e a mediação, e usa o
socket do herdr como plano de controle de sessões reais.

## Decisões de dono

| # | Decisão | Escolha | Alternativas rejeitadas e porquê |
|---|---------|---------|----------------------------------|
| D1 | Forma do v1 | **Sessão Claude Code interativa** (command/skill no plugin) | Agent SDK direto (robusto, mas construir o daemon antes de viver os requisitos é o maior arrependimento possível); híbrido script+sessão (duas partes para manter sem evidência de precisar). Daemon fica para o v2, com a lista real de dores após 1–2 programas. |
| D2 | Intake gate | **Barra: READY/NOT-READY** por slice, com Definition of Ready objetiva | Só avisar (repete o padrão que gerou mediação e conflito nas ondas manuais); barrar só o mecânico (deixa passar o preditor nº 1 de mediação — decisão estratégica aberta). |
| D3 | Mediação | **Porteiro de permissões já no v1, como processo separado** — *refinado pós-painel:* motor mínimo + **shadow-mode no primeiro programa** (ver Componente 3) | Sem mediação no v1 (dono quis o mecanismo desde já); mediação embutida na sessão (sessão interativa não serve MCP enquanto conversa). |
| D4 | Escalonamento | **Estratégico escala, resto loga** — reusa a taxonomia de altitude do debrief | Nada escala (decisão estratégica errada contamina a onda antes de ser vista); aprovação só por onda (não cobre o estratégico imprevisto). |
| D5 | Motor do porteiro | **Regras mecânicas; zona cinza SEMPRE escala** — *ajustado na ratificação pós-painel (2026-07-12):* o classificador LLM (Haiku) sai do v1 e entra no v2 SE a telemetria mostrar a fila afogando o humano | Original "regras + Haiku no cinza": 5 lentes apontaram custo recorrente, latência, não-determinismo e fail-open invertido num componente de segurança. Escalar-sempre é determinístico, grátis e gera o dataset para regras novas. |
| D6 | Nome/lar | **Plugin novo `maestro/`** no marketplace do cepa | `fleet` (menos personalidade); dentro do common (incha o common e acopla releases). |
| D7 | Piso de uso | **≥4 demandas** — memória de cálculo: é o menor programa que produz ≥2 ondas OU ≥2 slices paralelos com sobra, onde o overhead plano+intake+merge train (~1 sessão) fica abaixo de ~25% do trabalho total; com 3 ou menos, /board-flow:drain ou sessão única ganham | Sem piso (perde o critério objetivo); nota: o BACKLOG dizia "≥4 demandas / multi-semana" — o critério de duração foi **deliberadamente removido** (duração não é computável no intake; a contagem é). |

### Tensão nomeada e resolvida (D1 × D3)

Sessão interativa não consegue "servir" um MCP enquanto conversa com o humano.
Resolução: o porteiro é um **processo pequeno e separado** (script Python servindo
o protocolo MCP) que a sessão maestro sobe no início da onda. As filhas apontam
`--permission-prompt-tool` para ele. Ele decide pelo pipeline do Componente 3 e,
para o que escala, grava um pedido na fila em disco que a sessão maestro drena
pelo event loop (Componente 2a). O daemon v2 herda o porteiro tal-qual.

## Arquitetura v1

```
humano ⇄ sessão maestro (Claude Code interativa, plugin maestro)
              │
              ├─ intake gate (READY/NOT-READY por slice)          [pré-onda]
              ├─ gc de órfãos de programas anteriores             [pré-onda]
              ├─ porteiro (processo próprio; shadow no 1º prog.)  [sobe por onda]
              ├─ fork por slice: settings geradas + worktree herdr
              │     → spawn `claude -p` (autonomous-mode) com wrapper
              ├─ EVENT LOOP da onda (2a): wait curto em rodízio
              │     + fila de escalações + heartbeat + timeouts
              ├─ merge train com guards reusados (2b)             [pós-onda]
              └─ relatório + debrief agregado + telemetria
```

### Camadas de enforcement da filha (multi-layer, nunca camada única)

Lição paga do repo (bash-pathlock-bypass; enforcement-surface-guard): gate de
camada única é contornável. A filha roda sob TRÊS camadas, nomeadas:

1. **Settings geradas no fork** (a camada primária): o maestro gera o
   `settings.json` do worktree a partir do plan.yaml do slice — deny-by-default;
   allow de Write/Edit restrito aos globs da superfície declarada; allow de Bash
   restrito a um conjunto base (build/test/git local) + o que o slice declarar.
   Isso substitui a "allowlist da onda" da rev1 — não existe uma segunda
   allowlist paralela ao sistema de permissões nativo; a Regra 1 do porteiro
   da rev1 vira estas settings.
   **Achado do spike (obrigatório):** além de deny+allow, as settings geradas
   DEVEM conter regras `ask` cobrindo toda a zona que deve chegar ao porteiro
   (ex.: `"ask": ["Bash"]` por baixo dos allows). Sem `ask`, o modo default do
   headless pré-aprova comandos "seguros" (touch, mkdir…) e a camada 3 nunca é
   consultada — no spike, 0 chamadas chegaram ao porteiro até a regra existir.
2. **Hooks do harness ativos no worktree** (herdadas do seed): path-lock,
   bash-path-lock, enforcement-guard, gate-advance — as mesmas 5 topologias.
   **Deny incondicional da superfície de enforcement** (plugins/, hooks/,
   `.claude/settings*`, plugin-cache): nenhum glob de slice pode incluí-la;
   o intake REJEITA slice cuja superfície intersecte essa zona (no repo cepa,
   onde plugins são o produto, o slice declara a superfície normalmente e o
   enforcement-guard continua valendo para subagentes — a exceção é a filha
   top-level, e ela é o caso de uso; isso é a exceção nomeada e justificada).
3. **Porteiro** (a camada de julgamento): recebe só o que as camadas 1–2 não
   pré-decidiram, pelo `--permission-prompt-tool`.

### Componentes

1. **`/maestro:program-plan`** (conversacional): parseia BACKLOG.md, analisa
   superfície de arquivos / dependências / gates humanos por demanda, propõe
   ondas com fork points. Escreve `.claude/programs/<nome>/plan.yaml`.
   **Invariante de costura:** `/maestro:run` lê EXCLUSIVAMENTE o plan.yaml,
   nunca o BACKLOG.md — toda fonte futura (Jira via board-flow, discovery)
   entra escrevendo um plan.yaml válido, sem tocar no motor.

2. **`/maestro:run`** (a ação única). Para a onda corrente do plan.yaml:
   gc de órfãos → intake gate → sobe porteiro → fork dos slices → event loop
   → merge train → relatório. Estado da onda persistido a cada transição
   (ver 2c).

   **2a. Event loop da onda** (obrigatório — sem ele há deadlock: a sessão
   presa num wait bloqueante não drena a fila de escalação):
   ```
   loop (a cada iteração, nesta ordem):
     para cada slice ativo: herdr wait output --match --timeout 30s (rodízio)
     drenar .claude/programs/<nome>/escalations/*.yaml pendentes → apresentar ao humano
     heartbeat: mtime de resultado.txt de cada filha; sem progresso > T_heartbeat → suspeita
     timeouts: slice sem MAESTRO-EXIT após T_slice (default 45min, por-slice no plan.yaml)
               → matar filha, estado terminal TIMEOUT
   estados terminais por slice: DONE | FAIL | TIMEOUT | ESCALATED (nunca "pendurado")
   ```

   **2b. Merge train** — REUSA os guards do /common:worktree-merge (green-gate,
   single-owner, conflict-stop), nunca reimplementa:
   - merge 1 a 1, ordem determinística (ordem do plan.yaml);
   - **verify no main integrado após CADA merge** (não só o verify do slice
     contra o fork point — conflito semântico entre slices disjuntos só
     aparece aqui); vermelho pós-merge → revert do merge, slice vira FAIL;
   - **prune só ao fim da onda inteira** (worktree é barato; evidência
     perdida não volta);
   - **falha parcial:** slices verdes mergeiam; slice FAIL/TIMEOUT/UNPROVEN
     re-forka na onda seguinte a partir do main novo. A onda NÃO trava.

   **2c. Estado e recuperação** (requisito de v1, não pergunta aberta —
   morte da sessão maestro é o modo de falha mais provável de sessão longa):
   - `.claude/programs/<nome>/wave-state.yaml` escrito a cada transição:
     filhas vivas (pane id, worktree, PID), estado por slice, PID/lease do
     porteiro, escalações pendentes, merges já aterrissados;
   - **`/maestro:resume`**: reconstrói a onda do wave-state (nos moldes do
     /common:autonomous-resume — reusar o padrão, não inventar outro);
   - **gc no início de todo run**: lista e oferece limpar restos de programas
     anteriores (worktrees em ~/.herdr/worktrees, porteiro órfão por
     pidfile/lease, panes zumbis, escalações expiradas) — o análogo do que o
     cepa-doctor faz para cepa-worktrees.

3. **Porteiro** (`maestro/bin/maestro-gatekeeper`, processo próprio; paths da
   fila e da superfície **parametrizados por CLI/env**, contrato documentado
   em `common/` — o maestro é o primeiro cliente, não o dono: drain,
   autonomous-mode e o daemon v2 são consumidores previstos).
   **Fechado pelo spike (2026-07-15):** transporte = MCP streamable HTTP em
   loopback, 1 servidor por onda compartilhado pelas N filhas (stdio descartado:
   mataria o porteiro único e a fila única); resposta = JSON em `content[0].text`
   (`{"behavior":"allow|deny", ...}`); latência sub-ms, fora do caminho crítico.
   **O payload não identifica a filha** (só `tool_name`, `input`, `tool_use_id`)
   → a identidade do slice vai na URL da mcp-config gerada por fork
   (`http://127.0.0.1:P/mcp?slice=S1`); o porteiro lê o query param.
   O protocolo 3a cabe inteiro na `message` do deny — a filha obedece o
   `MAESTRO-EXIT:ESCALATED:<id>` sem nada no prompt dela (provado). Esqueleto
   funcional em `maestro/spike-gatekeeper/gatekeeper.py` (inclui `--shadow`).
   Especificação:
   - Recebe apenas a zona que as camadas 1–2 não pré-decidiram.
   - **Regra de escalação** (padrões estratégicos explícitos: editar
     contrato/OpenAPI, rename user-facing, delete fora da superfície,
     push/publish, escrita na superfície de enforcement) → fila.
   - **Zona cinza → escala SEMPRE** (D5 ajustada). Sem LLM no caminho de
     permissão no v1.
   - **Shadow-mode no primeiro programa:** aprova tudo, loga o que TERIA
     negado/escalado. Deny ativo a partir do 2º programa, com as regras
     calibradas pelo log. (Resolve também a contradição intake×porteiro da
     rev1: o intake é desenhado para zerar escalações; o shadow-mode mede se
     consegue, em vez de exigir "plantar" uma escalação.)
   - **Log com schema fixo** (5 campos: comando normalizado, camada/regra
     decisora, decisão, repo+slice, veredito humano posterior quando houver)
     — é o dataset que torna "regras da onda N+1 = aprovações recorrentes
     endossadas no debrief" um script, não um projeto.
   - **Fail-mode declarado:** porteiro fora do ar = filha recebe deny (o
     `--permission-prompt-tool` sem resposta nega) → a filha trata como
     escalação (ver 3a); o event loop detecta porteiro morto por
     pidfile/healthcheck e o ressobe.
   - Toda decisão de zona-cinza/escalada carrega **flag própria e entra no
     debrief default independente da altitude classificada** (um erro de
     classificação não pode se esconder do ritual desenhado para pegá-lo).

   **3a. Protocolo de escalação (contrato da fila)** — a filha headless NÃO
   espera em loop (queima orçamento e tende a contornar — padrão já visto no
   repo):
   - Pedido: `escalations/<id>.yaml` com `{id, slice, filha, acao, contexto,
     opcoes, criado_em, estado: pending|answered|expired, ttl}`.
   - A filha negada **termina o turno imediatamente** com marcador
     `MAESTRO-EXIT:ESCALATED:<id>` (estado terminal ESCALATED, não espera).
   - O humano decide via sessão maestro (event loop apresenta); a resposta
     vai no próprio arquivo (`estado: answered` + decisão).
   - O maestro **re-spawna a filha** com a decisão injetada no prompt
     ("decisão do dono sobre <id>: ...") — a filha continua do worktree onde
     parou.
   - **Pós-deny vigiado:** após um deny estratégico, o porteiro promove
     automaticamente qualquer write subsequente fora da superfície do slice
     a escalação (mitiga o contorno por rota oblíqua). TTL vencido → slice
     ESCALATED expira para FAIL e o relatório da onda o nomeia.

4. **Intake gate — Definition of Ready por slice** (checagem invocável em
   `common/` — `maestro` compõe; /board-flow:triage e /board-flow:drain podem
   reusar as checagens não-específicas de onda). Veredito READY/NOT-READY com
   lacunas nomeadas:
   - superfície declarada e **disjunta** dos demais slices da onda — mecânica
     definida: expandir cada glob contra a árvore de arquivos no fork point e
     intersectar os conjuntos (interseção glob×glob no abstrato não é
     computável); interseção não-vazia → NOT-READY dos dois slices;
   - superfície NÃO intersecta a zona de enforcement (camada 2 acima);
   - arquivos de alto atrito (lockfiles, migrations, settings, barrel/index)
     que nenhum slice declara → aviso nomeado no plano da onda (não veto;
     o verify pós-merge do 2b é quem pega o conflito incidental);
   - critério de aceite testável declarado; **em repo `.claude/no-build`, o
     slice DEVE declarar um critério alternativo executável** (comando de
     verificação próprio) — sem isso, NOT-READY: o merge train não pode
     aterrissar N slices com verificação zero;
   - **zero decisão estratégica em aberto** (human_gate `none` ou resolvido
     e registrado) — o preditor nº 1 de mediação;
   - contexto mínimo apontado (links de specs/cards/docs);
   - baseline verde no fork point (fonte: o mesmo last-build.json /
     capture-build-result do green-or-revert — não inventar outro sinal);
   - programa com ≥4 demandas (D7).

5. **Telemetria** — eventos de negócio E de saúde (medir só o funil feliz
   enviesa a decisão do v2; as dores operacionais são o que a justifica):
   - negócio: `program_start / slice_ready / slice_not_ready / slice_done /
     escalation / wave_done / program_done`;
   - saúde: `gatekeeper_up / gatekeeper_down / gatekeeper_error /
     slice_timeout / escalation_expired / merge_conflict / child_orphaned`.

### Schema plan.yaml v1

O formato do v0 (waves/slices/status) ganha os campos que o intake e o fork
consomem. `schema_version` obrigatório; `/maestro:run` valida e recusa versão
que não conhece.

```yaml
schema_version: 1
program: exemplo
source: BACKLOG.md
max_concurrent_slices: 3        # parâmetro, não constante; aumentar só com
                                # taxa de escalação comprovadamente baixa
waves:
  - id: 1
    mode: parallel-worktrees
    fork_after: null
    slices: [S1, S2]
    status: pending
slices:
  S1:                           # exemplo de slice READY
    demanda: "P9 do BACKLOG"
    surface: ["common/hooks/foo*.py", "docs/foo.md"]   # globs; expandidos no fork point
    human_gate: none            # ou descrição da decisão JÁ tomada
    acceptance: "pytest tests/test_foo.py verde + hook dispara no cenário X"
    context: ["BACKLOG.md#p9", "docs/foo-notes.md"]
    bash_extra: ["pytest"]      # além do conjunto base gerado nas settings
    timeout_min: 45
    status: pending
```

### Princípios herdados do v0 (mantidos)

- `max_concurrent_slices` default 3 — o limite é a atenção do humano; vira
  parâmetro porque o porteiro+intake existem para reduzir interrupções, e a
  taxa de escalação medida é o critério declarado para subir o teto.
- Onda N+1 forka somente após a onda N aterrissar no main (merge train).
- Um slice = uma sessão = um worktree; wrap-up ao fim.
- Plano é hipótese — cada filha re-valida sua fatia contra o main atual.

### Wrapper da filha (normativo)

```bash
herdr agent start <slice> --cwd <worktree> -- \
  bash -c 'set -o pipefail; claude -p "<prompt>" 2>&1 | tee resultado.txt; \
           ec=${PIPESTATUS[0]}; echo "MAESTRO-EXIT:$ec"; sleep "$MAESTRO_LINGER"'
```

- `set -o pipefail` + `PIPESTATUS[0]` (bash, não sh): o `$?` de um pipeline
  reporta o exit do `tee`, não do claude — sem isso toda filha que falha
  reporta sucesso (bug real da rev1).
- `MAESTRO_LINGER` (default 600s): o pane do herdr fecha quando o processo
  termina (pegadinha nº 1 do spike); o linger segura o pane para inspeção
  humana. A sincronização primária é por ARQUIVO (resultado.txt +
  wave-state), nunca pelo pane — o pane é cosmético/observabilidade.
- Estados especiais: `MAESTRO-EXIT:ESCALATED:<id>` (protocolo 3a).

### Dívidas nomeadas do acoplamento herdr

Mantemos o herdr como plano de controle porque panes visíveis são parte do
valor (output observável pelo humano durante a onda) e o spike já pagou a
validação. Em troca, três dívidas ficam nomeadas:

1. O contrato do wrapper (marcadores `MAESTRO-EXIT:*`) é string-match — fica
   versionado junto do plugin e testado contra cada upgrade do herdr.
2. Segundo sistema de worktrees (~/.herdr/worktrees vs ~/cepa-worktrees): o
   worktree do herdr DEVE herdar o single-owner guard e o .env seeding do
   modelo do launcher `cepa` (o maestro roda o seed no fork); o que não herdar é exceção
   nomeada no código.
3. `agent_status` unknown para filhas headless: sincronização por arquivo é
   a fonte de verdade; pane report-agent é melhoria opcional.
4. *(spike 2026-07-15)* `--permission-prompt-tool` está OCULTO no `--help` da
   CLI 2.1.210, porém funcional — mesmo tratamento da dívida 1: smoke-test do
   flag a cada upgrade do Claude Code (o run-spike.sh serve de teste).

## Ordem de construção (queimar o risco não-spikado primeiro)

1. ✅ **Spike porteiro** — FEITO 2026-07-15, VIÁVEL (commit do spike em
   `maestro/spike-gatekeeper/`; resultados e achados em SPIKE-RESULTS.md).
   Credencial/transporte/latência decididos — ver Componente 3.
2. **program-plan + intake gate** (dá para começar já: BACKLOG.md e o
   plan.yaml do v0 existem) + schema v1 + checagem DoR invocável.
3. ✅ **/maestro:run** — núcleos determinísticos FEITOS + testados 2026-07-15
   (`maestro/bin/`: maestro-fork-settings, maestro-gatekeeper [promovido do
   spike], maestro-poll, maestro-wave-state; 20 testes em
   `tests/test_maestro_run_cores.py`) + comandos `/maestro:run` e
   `/maestro:resume` autorados. FALTA a validação ponta a ponta (herdr spawn +
   onda real) — é o Passo 4. maestro 0.2.0.
4. Primeiro programa real com porteiro em shadow-mode.

## Fora do escopo do v1 (explicitamente)

- Daemon Agent SDK / launchd (v2 — disparo: telemetria mostrando programas
  multi-dia ou taxa de escalação alta demais para sessão interativa).
- Classificador LLM na zona cinza (v2 — disparo: fila de escalação afogando
  o humano, medida pelo log do porteiro).
- Filhas interativas steeradas via pane (headless-em-pane é o default do
  spike; interativo quando um caso real pedir).
- Integração Jira/board-flow no plano (BACKLOG.md é a fonte; adapter futuro
  escreve plan.yaml — a costura já está protegida pelo invariante do
  Componente 1).

## Critério de aceite do v1

Um programa real de ≥4 demandas executado ponta a ponta com **uma ação**
(`/maestro:run`):

- intake barrou ou aprovou cada slice com veredito nomeado;
- filhas rodaram via herdr com as 3 camadas de enforcement ativas e porteiro
  em shadow-mode logando;
- o pipeline de escalação foi demonstrado ponta a ponta **por uma filha real
  disparando a regra** (dar a um slice uma tarefa que naturalmente toca um
  padrão estratégico — NÃO injetar pedido sintético direto na fila, que só
  testa metade do caminho);
- uma interrupção da sessão maestro no meio da onda foi recuperada por
  `/maestro:resume` (pode ser provocada);
- merge train aterrissou a onda no main com verify pós-cada-merge verde;
- debrief agregado listou as decisões logadas, incluindo as flags de
  zona-cinza do porteiro.
