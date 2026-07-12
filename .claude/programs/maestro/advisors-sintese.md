# Painel de advisors — `.claude/programs/maestro/design.md` (área: arquitetura, 7 lentes)

Rodado em 2026-07-12 · 53 achados · workflow `wf_ed39aa0a-eb9`.

## Vereditos por lente

- **contrarian:** "O v1 é executável, mas seu mecanismo central de segurança (porteiro MCP) tende a ser teatro — cobre só o resíduo das permissões, é contornável via Bash como o histórico do próprio repo prova, e existe para um evento que o intake foi projetado para eliminar; validaria o porteiro em modo log-only e gastaria o rigor do v1 em timeout/recovery e verify pós-merge."
- **fundamentalista:** "Fiel ao v0 e ao BACKLOG na superfície, mas contorna silenciosamente três camadas de enforcement que o projeto já pagou para construir (enforcement-surface-guard, guards do worktree-merge/green-or-revert, multi-layer contra bypass) — cada quebra precisa virar reuso explícito ou exceção nomeada."
- **expansionista:** "O núcleo está certo, mas porteiro, fila de escalação e Definition of Ready são primitivas do harness inteiro nascendo acopladas ao maestro; desacoplá-las agora custa quase nada e paga em drain, autonomous-mode e no daemon v2."
- **outsider:** "Coerente para quem viveu o v0 e o spike, mas não se sustenta sozinho: herdr, plan.yaml e o vocabulário operacional só existem fora do texto, e as 7 decisões registram escolhas sem alternativas nem porquês."
- **executor:** "Direção certa, mas não é executável na segunda-feira: três blockers sem dono fecham o caminho crítico (loop de eventos vs wait bloqueante, origem do allowlist, protocolo deny-aguarde) e não há ordem de construção que queime primeiro o risco não-spikado (porteiro MCP)."
- **operador-sre:** "Desenha bem o caminho feliz, mas os dois modos de falha mais prováveis (morte da sessão maestro, queda do porteiro) estão relegados a perguntas abertas — sem estado persistido, timeouts, fail-mode e eventos de saúde, o primeiro incidente vira arqueologia manual no herdr."
- **custo-de-manutencao:** "O v1 compra três moradores permanentes caros — processo porteiro, LLM no caminho de permissão, dependência estrutural do herdr — antes de evidência de que as alternativas estáticas são insuficientes, contradizendo a própria disciplina 'espere a dor real' que aplicou ao daemon v2."

## Convergências (independentes — sinal forte)

1. **Porteiro cobre só o resíduo e é contornável via Bash** (contrarian ⨯ fundamentalista ⨯ operador-sre ⨯ custo). O `--permission-prompt-tool` só é consultado para o que as settings da filha não pré-aprovam; o histórico do repo (bash-pathlock-bypass, enforcement-surface-guard) prova que camada única falha. O design não declara o baseline de permissões da filha nem quais hooks continuam ativos no worktree do herdr.
2. **Protocolo deny-aguarde é o mecanismo central e está indefinido** (contrarian ⨯ outsider ⨯ executor ⨯ operador-sre — 4 lentes, uma como CRÍTICA). Filha `claude -p` negada não espera: contorna, aborta ou queima orçamento. Sem contrato request/response (id, estado, TTL, como a resposta volta), a Regra 2 é inimplementável e o critério de aceite depende do pedaço menos especificado.
3. **Morte da sessão maestro é o modo de falha nº 1 e está em "pergunta aberta"** (executor ⨯ operador-sre ⨯ fundamentalista ⨯ contrarian). Requisito de v1, não pergunta: estado de onda persistido (filhas vivas, pane, PID do porteiro, escalações pendentes) + `/maestro:resume` — reusando o padrão state.yaml/autonomous-resume que já existe (fundamentalista).
4. **Wrapper tem bug real + sincronização sem timeout** (contrarian ⨯ outsider ⨯ executor ⨯ operador-sre). `MAESTRO-EXIT:$?` captura o exit do `tee`, não do claude (precisa `pipefail`/`PIPESTATUS`); `sleep N` é parâmetro mágico; `wait output` sem timeout trava a onda; sem heartbeat nem estados terminais (DONE ≠ FAIL ≠ TIMEOUT).
5. **Merge train: verify indefinido, sem verify pós-merge no main integrado, sem rollback, prune prematuro** (contrarian ⨯ fundamentalista ⨯ operador-sre ⨯ executor). Slices verificados contra o fork point não garantem main verde após K merges (conflito semântico). Fundamentalista: deve REUSAR os guards do worktree-merge (green-gate, single-owner, conflict-stop), não reimplementar.
6. **Haiku no caminho de permissão é problema em 5 lentes** (ver Discordância B).
7. **Allowlist da Regra 1 sem produtor** (executor CRÍTICA ⨯ custo ⨯ expansionista). Regra central condicionada a artefato cuja origem é "pergunta aberta"; custo aponta que duplica o sistema de permissões nativo do Claude Code.
8. **plan.yaml: schema não mostrado, campos novos não versionados** (outsider ⨯ executor ⨯ custo). O DoR exige campos que o v0 nunca teve; falta seção "schema v1" + `schema_version` + exemplo de slice READY.
9. **Doc não se sustenta sozinho** (outsider, com eco no fundamentalista): herdr nunca definido, glossário programa→onda→slice/demanda ausente, decisões sem alternativas/rationale, incidentes citados sem link.
10. **Contradição interna intake × porteiro** (contrarian ⨯ outsider): o intake exige "zero decisão estratégica aberta" — que é o que geraria escalação; o critério de aceite admite "plantar" uma. Ou o intake é esperado falhar (dizer isso), ou o porteiro é especulativo no v1.

## DISCORDÂNCIAS NOMEADAS

### A. Porteiro no v1: dinâmico (D3) × estático/log-only × nem construir
- **custo-de-manutencao:** settings estáticas geradas por worktree no fork + fila de escalação em disco cobrem Regras 1 e 2 **sem processo novo**; o porteiro dinâmico só se paga com evidência — a mesma disciplina que D1 aplicou ao daemon.
- **contrarian:** construir, mas **log-only** no primeiro programa (aprova tudo, loga classificação) — ganha a telemetria sem pagar o custo do deny.
- **expansionista:** construir **e** desacoplar do maestro (paths parametrizados, contrato documentado em common/) — é o plano de controle de permissões headless do ecossistema inteiro (drain, autonomous, v2).
- **O que decide:** D3 é decisão de dono ("MCP já no v1") — a discordância não é *se* existe, é *o quanto ele decide sozinho no primeiro run*. **Recomendação do sintetizador:** honrar D3 construindo o porteiro, mas com motor mínimo: Regra 1 vira settings estáticas geradas no fork (elimina a allowlist paralela — achado 7), o porteiro fica com Regra 2 + fila + log rico, e roda o primeiro programa em modo shadow/log-only (deny ativado a partir do 2º programa). Adotar o desacoplamento do expansionista (custo marginal ~zero, confirmado pela decisão D3 de já ser processo separado).

### B. Zona cinza: Haiku classifica (D5) × escala sempre
- **custo + operador-sre:** LLM no caminho de permissão = custo recorrente, latência, não-determinismo e fail-mode indefinido num componente de segurança; "zona cinza → escala sempre" é determinístico, grátis e gera o dataset para regras futuras.
- **contrarian + fundamentalista:** se o Haiku ficar, o default fail-open é invertido (incerto deveria ESCALAR, não aprovar) e o falso-negativo some até do debrief (que filtra por altitude) — flag própria obrigatória.
- **executor:** se o Haiku ficar, faltam credencial, timeout, fail-mode e log do rationale — decisões que ele não pode tomar sozinho.
- **O que decide:** volume real da zona cinza (ninguém tem esse dado ainda). **Recomendação:** v1 sem Haiku — zona cinza escala sempre; o log da fila mede o volume e o Haiku entra no v2 se a fila afogar o humano. É um ajuste (não reversão) de D5: "regras + LLM no cinza" vira "regras + escalação no cinza; LLM quando a telemetria pedir". Precisa de ratificação do dono.

### C. herdr como plano de controle × `claude -p` background sem herdr
- **custo-de-manutencao:** o acoplamento nasce com 3 workarounds (wrapper frágil, sync por grep de string, segunda árvore de worktrees) e o v0 provou que dá sem herdr; sincronização final já é por arquivo.
- **design/spike (+ executor implícito):** o herdr dá panes visíveis (output observável pelo humano — objetivo declarado do Maestro) e as primitivas já foram spikadas.
- **O que decide:** quanto vale a visibilidade dos panes para o humano durante a onda. **Recomendação:** manter herdr (a visibilidade é parte do valor; o spike foi pago), MAS nomear a dívida no design: contrato do wrapper versionado, sync primária por arquivo (pane é cosmético), e o worktree do herdr precisa herdar o single-owner guard do modelo ccw (achado do fundamentalista) — se não der, isso é exceção nomeada.

### D. Teto de 2–3 slices: constante herdada × parâmetro
- **expansionista:** o teto era "atenção do humano" quando o humano mediava tudo; com porteiro + intake, deveria ser parâmetro do plan.yaml (default 3) com critério de aumento ligado à taxa de escalação.
- **princípio herdado do v0 (fundamentalista defenderia):** o limite é a atenção do humano e o v1 ainda não provou taxa de escalação baixa.
- **O que decide:** nada a decidir agora — as posições são compatíveis no tempo. **Recomendação:** parametrizar já (campo no YAML, default 3, sem custo), aumentar só com evidência de telemetria. Resolve as duas.

### E. Falha parcial da onda: verdes mergeiam × onda trava
- **executor:** verdes mergeiam (disjuntos por construção do intake); vermelho vira slice da onda seguinte com baseline novo.
- **operador-sre:** só se o verify rodar no main integrado após CADA merge, com prune adiado para o fim da onda — senão o "verde" do fork point aterrissa vermelho.
- **O que decide:** já decidível com os inputs. **Recomendação:** adotar os dois juntos — verdes seguem + re-verify pós-cada-merge + prune só ao fim da onda + revert documentado. Fecha a pergunta aberta nº 3 do design.

## Propostas consolidadas priorizadas

1. **[CRÍTICA — mediação de verdade]** Declarar o baseline de permissões da filha (deny-by-default + settings geradas por slice no fork) e as camadas de enforcement ativas no worktree do herdr (path-lock, bash-path-lock, enforcement-guard, gate-advance). Porteiro é camada ADICIONAL, nunca única; deny incondicional da superfície de enforcement (plugins/hooks/settings) acima de qualquer glob de slice. *(contrarian, fundamentalista, operador-sre, custo)*
2. **[CRÍTICA — event loop]** Especificar o loop da onda na sessão maestro: `wait output --timeout` curto em rodízio + checagem da fila de escalações + heartbeat por mtime, com estados terminais DONE/FAIL/TIMEOUT por slice. Sem isso há deadlock por design. *(executor, operador-sre)*
3. **[CRÍTICA — protocolo de escalação]** Especificar o contrato da fila (`escalations/`): schema do pedido (id, filha, ação, contexto, opções), estados pending/answered/expired, TTL, como a resposta volta à filha (re-spawn com decisão injetada — filha negada TERMINA com `MAESTRO-EXIT:ESCALATED`, nunca espera em loop). *(4 lentes)*
4. **[CRÍTICA — recovery]** Promover recuperação de "pergunta aberta" a requisito: estado de onda em disco escrito a cada transição + `/maestro:resume` nos moldes do autonomous-resume + gc de órfãos (worktrees herdr, porteiro, panes) no início de todo run. *(operador-sre, executor, fundamentalista)*
5. **[ALTA — motor do porteiro]** Regra 1 → settings estáticas geradas no fork (mata a allowlist paralela); porteiro = Regra 2 + fila + log com schema (comando normalizado, regra decisora, repo, veredito humano posterior); primeiro programa em shadow-mode. Zona cinza escala sempre; Haiku adiado para v2 com evidência. **Condicional às discordâncias A e B (ratificação do dono).**
6. **[ALTA — merge train]** Reusar os guards do worktree-merge (green-gate, single-owner, conflict-stop); verify pós-cada-merge no main integrado; prune só ao fim da onda; política de falha parcial: verdes seguem, vermelho re-forka da onda seguinte. *(fundamentalista, operador-sre, executor, contrarian)*
7. **[ALTA — wrapper]** Corrigir `$?` (pipefail/PIPESTATUS), definir N do sleep (ou substituir por `pane report-agent`), timeout por slice com valor declarado. *(4 lentes)*
8. **[ALTA — plan.yaml]** Seção "schema v1": campos novos do DoR (globs, human_gate, aceite testável, contexto), `schema_version`, exemplo completo de slice READY, e o invariante "o run só lê plan.yaml — toda fonte entra por ele" (protege o adapter futuro de graça). *(outsider, executor, custo, expansionista)*
9. **[ALTA — ordem de construção]** Fixar sequência que queima o risco não-spikado primeiro: (a) spike porteiro-MCP com 1 filha fake (1 dia); (b) program-plan + intake gate; (c) /maestro:run integrando. *(executor)*
10. **[MÉDIA — legibilidade]** Definir herdr em 2 frases + link do spike; glossário programa→onda→slice/demanda; rationale + alternativas nas decisões D2–D7; links dos incidentes citados (Onda 2, v0); registrar a queda do critério "multi-semana" em D7 e a memória de cálculo do piso 4. *(outsider, fundamentalista, custo)*
11. **[MÉDIA — telemetria de saúde]** Somar aos eventos de negócio: `gatekeeper_up/down/error`, `slice_timeout`, `escalation_expired`, `merge_conflict`, `child_orphaned` — são as dores que justificarão (ou não) o daemon v2. *(operador-sre)*
12. **[MÉDIA — desacoplamento]** Porteiro e fila com paths parametrizados e contrato documentado em common/ (não hardcoded em `.claude/programs/<nome>/`); DoR como checagem invocável que triage/drain reusam. *(expansionista)*
13. **[MÉDIA — no-build]** Repos com `.claude/no-build` exigem critério de aceite alternativo executável no DoR — sem isso o merge train aterrissa sem verificação nenhuma. *(contrarian)*
14. **[BAIXA — teto parametrizado]** `max_concurrent_slices` no plan.yaml, default 3, aumento condicionado à taxa de escalação. *(expansionista — discordância D resolvida)*
15. **[BAIXA — flag zona-cinza no debrief]** Toda decisão vinda de zona cinza entra no debrief default independente da classificação. *(fundamentalista — vale mesmo sem Haiku)*
