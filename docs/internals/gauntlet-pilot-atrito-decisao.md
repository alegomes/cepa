# Piloto Gauntlet Loop nº2 — Atrito de decisão (o harness pergunta demais e cedo demais)

Run: workflow `wf_a83d9df2-5d1`, 2026-08-15, 9 agentes, ~615k tokens, 13 min.
Método: barra pré-declarada → 3 builders isolados (ângulos distintos) → 3 juízes cegos → revisão do vencedor → checagem final.

## Barra de qualidade (escrita antes de qualquer design)

- **autonomy-bands-declared-config** — As faixas de autonomia (executa-e-reporta vs sempre-pergunta) existem como configuração versionada e enumerada — um arquivo nomeado (path exato) com a lista de ações por faixa cobrindo pelo menos as 10 mecânicas carimbadas da sessão real (rodar build, commit local, criar card, apagar branch contido na base, apagar handoff vencido, mover arquivo, atualizar plano) e as sempre-pergunta (push, merge em integração, descarte de trabalho, transição terminal no board, segredo, terceiros). A fronteira NÃO é julgamento do agente por turno, e ação ausente da lista tem um default declarado (o design diz qual e por quê).

- **audit-before-ask-mechanical** — Auditar-antes-de-perguntar é mecânico, não exortação: o design especifica um passo obrigatório (idealmente um script/gate independente do executor) que impede uma pergunta sobre card com filhos sem a enumeração completa das filhas + status de cada uma anexada à pergunta, e sobre card que cita arquivo:linha sem a linha conferida. Aplicado ao caso WEGO-1406, o design demonstra que a pergunta 'fecho o Epic?' seria bloqueada ou já viria com as 41 filhas enumeradas.

- **attestations-durable-consumed** — Atestados do dono viram fatos duráveis com esquema definido (data, autor, escopo nomeado — cluster/Epic/card —, o texto do atestado, condição de revisita) num arquivo versionado tipo .claude/attestations.yaml, com DOIS lados especificados: quem grava (em que momento do fluxo a afirmação do dono no chat vira registro) e quem consome (quais comandos leem o arquivo antes de agir), mais o comportamento em conflito — o caso real (atestado de 08-03 'concluído' vs triagem de 08-04 tratando como fila de dev) deve resultar em contradição APRESENTADA ao dono, não silenciosamente vencida por nenhum dos lados.

- **per-subtask-question-form** — O fallback de Epic indecidível é uma pergunta fechada por sub-task no formato do decide/plain-report (numerada, respondível sem abrir o card, com Recomendo sim/não, resposta em lote), com o nível de detalhe assimétrico que o dono especificou: recomendação de fechar = uma linha com o que foi verificado e onde; recomendação de manter aberto = a lista dos critérios, cada um com estado verificado + local (arquivo:linha), distinguindo critério de implementação de critério de cobertura (a distinção que derrubou o WEGO-1437).

- **enforcement-depth-honest** — O design traz uma tabela/lista explícita classificando CADA mecanismo proposto em: hook/script testado (endure), config versionada lida por código (endure), instrução em comando/skill versionado (decai menos), prosa de prompt (decai — já observado neste harness). Toda peça crítica em prosa é justificada ou tem plano de endurecimento; nenhum mecanismo é vendido como garantia quando é instrução.

- **fit-no-duplication** — O design estende as peças existentes em vez de duplicá-las: nomeia o que muda em board-flow:decide (motivos, waivers, formato) e onde a forma dele é reutilizada fora da Review; usa o formato plain-report em vez de inventar outro; classifica motivos contra needs-human-motivos.md; e o item 5 (defeito de harness vira item do BACKLOG, não interrupção) tem mecanismo próprio, não só a frase. Nenhum novo comando refaz o que decide/waivers/classify_needs_human já fazem.

- **cost-and-residual-friction** — O design fecha a conta contra a sessão real: mapeia as ~20 interrupções classificadas para o mecanismo que absorve cada classe (~10 mecânicas → faixa automática, ~4 defeitos → fila do BACKLOG, 1 prematura → gate de auditoria, 5 genuínas → ficam, mas agrupadas por rodada) com a memória de cálculo explícita, e estima o custo de construção por peça (ordem de grandeza: horas/dias, nº de hooks/arquivos) admitindo o atrito residual que NÃO some.

**Referência (inatingível de propósito):** O estado ideal: numa sessão de triagem/drain, o dono é consultado exatamente uma vez por rodada, em lote. Tudo que é reversível já aconteceu e chega como linhas de informação no relatório (com a lista das ações vindo de um arquivo versionado, não do humor do agente); tudo que é irreversível espera nessa única consulta. Cada pergunta é fechada, numerada, com Recomendo sim/não, e chega pré-auditada — nenhum card com filhas vira pergunta sem as filhas enumeradas, nenhum critério é citado sem o estado verificado em arquivo:linha, e o detalhe aparece exatamente onde a decisão depende dele (uma linha para fechar, a lista de critérios para manter aberto). O que o dono já atestou nunca é perguntado de novo: atestados vivem datados e com escopo em arquivo durável, lidos por todo comando antes de agir, e uma contradição entre atestado e código é apresentada como contradição, nunca resolvida em silêncio. Defeito do harness jamais interrompe trabalho de produto: vira item do BACKLOG automaticamente. Cada regra dessas vive na camada mais dura que comporta — hook testado ou config versionada — e o WEGO-1406 refeito nesse mundo termina com as 22 filhas despachadas numa sentada, sem nenhuma reversão.

## Designs concorrentes e julgamento

### Design A (config-first) — Faixas de autonomia versionadas + pacote-de-pergunta auditado + atestados duráveis (mecanismo/config)

## Visão de uma linha

Tudo que é reversível vira linha de informação no relatório porque uma **config versionada** diz que é; tudo que é irreversível espera **uma consulta por rodada**; nenhuma pergunta chega ao dono sem passar por um **lint de pacote-de-pergunta** que exige a auditoria anexada; o que o dono já afirmou vive em **`.claude/attestations.yaml`** e é lido antes de qualquer pergunta; defeito de harness cai numa **fila própria** sem parar o dono. Cinco peças, cada uma na camada mais dura que comporta, todas estendendo o que já existe (`decide` passos 5–7, `waivers.py`, `plain-report`, `needs-human-motivos.md`).

---

## Peça 1 — Faixas de autonomia em config versionada

**Arquivo novo: `board-flow/config/autonomy.yaml`** (default shippado no plugin) com override por repo em **`.claude/autonomy.yaml`** (mesmo padrão de precedência do `board-flow.yaml`). A fronteira sai do julgamento por turno do agente e vira lista enumerada:

```yaml
version: 1
default_para_acao_nao_listada: pergunta   # viés seguro; o miss é logado (peça 5) para a lista crescer por evidência
executa_e_reporta:
  - acao: rodar-build
    detect: {bash: '\b(mvn|mvnw|npm (test|run build)|pytest|gradle)\b'}
  - acao: commit-local
    detect: {bash: '^git commit\b'}
  - acao: criar-card            # reversível: card criado se apaga/cancela
    detect: {mcp: '(createJiraIssue|jira_create_issue)$'}
  - acao: apagar-branch-contida
    detect: {bash: '^git branch -[dD]\s+(?<branch>\S+)'}
    precondicao: 'git merge-base --is-ancestor <branch> <base>'   # falhou → cai para a faixa pergunta
  - acao: apagar-handoff-vencido
    detect: {path: '\.claude/handoffs/.*\.md$', op: delete}
    precondicao: 'idade > handoff_ttl e branch não existe mais'
  - acao: mover-arquivo-no-repo
    detect: {bash: '^git mv\b'}
  - acao: atualizar-plano
    detect: {path: '\.claude/programs/.*/plan\.yaml$'}
  - acao: commitar-docs-processo
    detect: {bash: '^git commit\b', paths_only: '(docs/|\.claude/)' }
  - acao: criar-card-divida
    detect: {mcp: '(createJiraIssue|jira_create_issue)$', label: 'debt'}
  - acao: rerodar-prove
    detect: {slash: '/board-flow:prove(-drain)?'}
sempre_pergunta:
  - {acao: push-remoto,            detect: {bash: '^git push\b'}}
  - {acao: merge-integracao,       detect: {bash: '^git merge\b', branch_atual: '(main|develop|master)'}}
  - {acao: descartar-trabalho,     detect: {bash: '(git reset --hard|git checkout \.|git clean -f|worktree remove)'}}
  - {acao: transicao-terminal,     detect: {mcp: '(transitionJiraIssue|jira_transition_issue)$', status_destino: [done, wont_do]}}  # resolvido via status_map do board-flow.yaml
  - {acao: segredo,                detect: {path: '(\.zsecrets|\.env)', op: any}}
  - {acao: saida-para-terceiros,   detect: {mcp: '(send_dm|publish_|createConfluence|add.*Comment.*external)'}}
```

Os dez itens de `executa_e_reporta` são exatamente as ~10 mecânicas carimbadas de 08-03/08-10 (build curto, card de dívida, commit de 7 docs de processo, 6 branches órfãos, 3 handoffs vencidos…). **Ação ausente da lista → `pergunta`**, declarado no próprio arquivo: o custo de perguntar uma vez a mais é minutos; o custo de executar um irreversível não listado é uma reversão — e o miss vira entrada de telemetria para promover a ação à lista por evidência, nunca por humor do agente.

**Enforcement em duas direções:**

- **Hook novo `common/hooks/autonomy-guard.py`** (PreToolUse em Bash + tools MCP do Jira, mesmo estilo do `bounce-reason-gate.py`: script Python pequeno, exit 2 com stderr didático, testado em `tests/test_autonomy_guard.py`). Ele lê o YAML, casa o tool-call contra os `detect:` e **bloqueia** qualquer ação da faixa `sempre_pergunta` que não tenha aprovação registrada em `.claude/approvals/round-<id>.yaml` (o arquivo que o `decide`/plain-report grava ao aplicar a resposta em lote — peça 3 do fluxo). Precondições (`merge-base --is-ancestor`) são comandos que o próprio hook roda: a "reversibilidade" do apagar-branch é **verificada**, não presumida. Isso resolve o lado perigoso mecanicamente: o agente não tem como *silenciosamente* fazer push/merge/transição terminal, acredite no que acreditar.
- **Lado relatório:** `common/hooks/report-style-lint.py` (já existe, avisa-não-bloqueia) ganha uma checagem: item numerado da lista final cuja pergunta casa com um `detect:` da faixa automática → desvio apontado no turno seguinte ("isso era pra ter sido feito e reportado"). As executadas viram linhas de informação no plain-report — o formato da SKILL já comporta (`### Detalhe técnico`), sem formato novo.

## Peça 2 — Auditar-antes-de-perguntar: o pacote-de-pergunta

Toda pergunta de `decide`/`triage`/`drain` passa a ser materializada **antes de aparecer no chat** como `.claude/questions/round-<ts>.yaml`, e um script novo **`board-flow/bin/audit_question.py`** (irmão de `classify_needs_human.py` e `waivers.py`, com suíte em `tests/`) valida cada item:

- `card:` com `tem_filhas: true` → obrigatório `filhas:` com **todas** (key + status + bucket), e `filhas_total` == len(lista). Lista parcial → o script recusa o pacote com a mensagem "enumere antes de perguntar".
- critério citando `arquivo:linha` → obrigatório `verificado: {arquivo, linha, estado, commit}`; o script confere que o arquivo existe e a linha existe naquele commit (`git show <commit>:<arquivo>`). Semântica ele não verifica — isso fica dito.
- `recomendacao: fechar` → exige exatamente um `verificado_em:` de uma linha. `recomendacao: manter` → exige `criterios:` cada um com `estado`, `local` e `tipo: implementacao|cobertura` (peça 4).

O comando só apresenta o que o script aprovou. **Segunda muralha, independente do comando:** o `autonomy-guard.py` (peça 1) já bloqueia `transicao-terminal`; a aprovação `round-<id>.yaml` que o libera referencia o pacote auditado — logo um "sim" colhido em prosa, fora do pacote, **não é executável**: o hook barra a transição por falta de aprovação ancorada em auditoria.

**Replay do WEGO-1406:** "fecho o Epic?" com 15 cards vistos → `audit_question.py` recusa (Epic tem filhas, lista ausente) → o comando roda a enumeração via atlassian-expert (JQL `parent = WEGO-1406`) → 41 filhas, 22 abertas → a recomendação "fechar" fica impossível de montar → o pacote sai no modo por sub-task (peça 4). E mesmo que o agente perguntasse em prosa e o dono dissesse "sim", a transição terminal do Epic morre no hook. A reversão de 08-10 não acontece.

## Peça 3 — Atestados duráveis: `.claude/attestations.yaml`

Irmão dos waivers (mesma filosofia de casamento do `waivers.py`: `_chave()` normaliza escopo; waiver dispensa **prova**, atestado registra **fato do mundo**). Script novo `board-flow/bin/attestations.py` com `carregar/aplicavel/gravar`, campos obrigatórios como o `CAMPOS` do waivers.py (malformado é ignorado, não vale):

```yaml
- id: att-20260803-plugsign-operacional
  data: 2026-08-03
  autor: alegomes
  escopo: {tipo: epic, chave: WEGO-1406, texto: "pacote operacional do onboarding PlugSign"}
  afirmacao: "o pacote operacional está concluído"
  fonte: "resposta 2 do decide de 03/08 (round-20260803-1412)"
  revisita: {data: 2026-11-01}      # gatilho em prosa é MOSTRADO, nunca interpretado — mesma regra do decide.md passo 5
  status: ativo                     # ativo | contestado | vencido
```

**Quem grava:** o passo de aplicação em lote do `decide` (hoje passo 7, linhas 140–156 do decide.md) e o fechamento do `triage`: quando a resposta do dono é uma afirmação sobre o mundo ("está concluído", "o SMTP está configurado no painel"), o comando grava o atestado junto com o waiver/transição — mesmo momento em que já grava `waivers.gravar(...)`.

**Quem consome:** `decide` (novo passo 5b, logo após os waivers), `triage`, `drain`, `prove` (antes de devolver card por pendência externa) e `next`. Regra: pergunta cujo escopo casa um atestado ativo vira **informação** ("coberto pelo atestado de 03/08"); e o `audit_question.py` exige `attestation_ref` em qualquer item cujo escopo casa um atestado — aplicando-o ou nomeando o conflito. Um item sem essa referência não passa no lint: o registro que ninguém lê fica estruturalmente impossível.

**Conflito nunca é vencido em silêncio, por nenhum dos lados.** Replay do caso real: em 08-04 o `triage` carrega o atestado de 08-03 ("operacional concluído"), encontra 10 cards de desenvolvimento abertos no mesmo cluster → em vez de re-escopar por lista de chaves calado (o que fez), monta UM item de contradição no pacote: *"Seu atestado de 03/08 diz que o pacote operacional está concluído; encontrei 10 cards de desenvolvimento abertos no cluster (WEGO-…, lista). O atestado valia só para a parte operacional? Recomendo sim — os 10 são código, não operação. Se não: marco o atestado como contestado e trio os 10 normalmente."* A contradição aparece em 08-04, não em 08-10, e o atestado ganha `status: contestado` com a evidência anexada — os dois lados ficam no histórico.

## Peça 4 — Pergunta por sub-task com detalhe assimétrico

Vive no **decide.md** (novo modo `--epic KEY`, reusando o formato de lote dos passos 6–7 e as regras da lista do `plain-report` SKILL.md linhas 95–124 — numerada, fechada, `Recomendo sim/não`, resposta "1 sim, 2 não") — nenhum comando novo. O template dos dois ramos é imposto pelo schema do pacote (peça 2):

- **fechar** = uma linha: `"WEGO-1436 (POST /upload): endpoint existe em PlugSignAdapter:253, cobertura mock e vendor-drift presentes. Fecho? Recomendo sim."`
- **manter** = a lista É o motivo, critério a critério com `estado + local + tipo`: o formato exato do exemplo WEGO-1437 do BACKLOG (5 critérios, cada um com `PlugSignPort.java:201-226` etc.), com o campo `tipo: implementacao|cobertura` obrigatório — a distinção que derrubou o card em 07-30 (ramo PRESTADOR implementado em `PlugSignAdapter.java:1021`, zero ocorrências de "Contratado" em teste). Uma pergunta "está implementado?" nem compila no schema: `manter` sem `tipo` por critério é pacote recusado.

Custo aceito e declarado: o ramo `manter` é longo. No WEGO-1406 ele é minoria (12 das 22 abertas são operacionais, uma linha cada).

## Peça 5 — Fila própria para defeito de harness

Gatilho mecânico: (a) hooks que capturam exceção própria ou bloqueio reconhecidamente falso gravam via helper novo em `common/hooks/_telemetry.py` (`registrar_defeito()`) no ledger `~/.claude/cepa-telemetry/harness-debt.jsonl`; (b) o classificador já tem o slot — `nao-rodou` com causa "trava do próprio harness" está nomeado no `needs-human-motivos.md` motivo 1 — e o `decide` passo 4 passa a despachar essa causa para o mesmo ledger em vez de para o dono; (c) instrução nos comandos: bloqueio cuja causa é ferramenta → registrar + contornar/pular, nunca virar item da lista do dono. Destino: `/common:metrics` ganha a seção "defeitos de harness pendentes", e o dono varre para o BACKLOG quando quiser. No relatório: *"2 defeitos do harness registrados na fila (não são seus)"* — os 4 casos reais (tela de Labels do Jira, last-build.json em background, falso-positivo do bounce-reason-gate, summary-nulls em pt-BR) teriam ido todos por aí.

---

## Tabela de enforcement (camada por mecanismo)

| Mecanismo | Camada | Endurece? |
|---|---|---|
| `autonomy.yaml` (faixas + detect + precondições) | config versionada lida por código | endure |
| `autonomy-guard.py` bloqueando sempre-pergunta sem aprovação | hook Python testado (`test_autonomy_guard.py`) | endure |
| `audit_question.py` (filhas completas, arquivo:linha existente, schema fechar/manter) | script testado chamado pelo comando | endure quanto à forma; **não** verifica semântica nem impede fabricação (mesmo modelo de confiança dos artefatos de prova) |
| bloqueio da transição terminal sem aprovação ancorada em auditoria | hook (autonomy-guard) | endure — é a segunda muralha do audit-before-ask |
| `attestations.py` + `attestation_ref` obrigatório no pacote | script + lint | endure quanto a "ninguém ignora o arquivo"; a decisão de gravar o atestado certo é instrução de comando (decai menos) |
| templates fechar/manter no decide.md | instrução em comando versionado + schema no lint | forma mecânica, redação em prosa |
| "executadas viram linhas de informação" | prosa + `report-style-lint.py` (avisa, não bloqueia — precedente declarado na própria SKILL, linhas 218–221) | decai; plano: apertar se `/common:metrics` mostrar reincidência |
| desvio de defeito de harness | helper de telemetria (endure nos hooks) + instrução nos comandos (decai no caminho comando→ledger) | parcial, admitido |

Honestidade central: **nenhum lint impede o agente de digitar uma pergunta em prosa no chat**. O que é mecânico é que essa pergunta não produz efeito irreversível (o hook barra a aplicação) — o incentivo estrutural é montar o pacote.

## Encaixe no que existe (sem duplicação)

- `decide` **ganha**: passo 5b (atestados, espelho do passo 5 de waivers), modo `--epic`, materialização do pacote + `audit_question.py` antes do passo 6. Formato de pergunta: o mesmo dos passos 6–7, reutilizado fora da Review.
- `triage` **passa a**: consultar atestados antes de re-escopar, emitir perguntas só via pacote, despachar causa-harness ao ledger.
- `waivers.py` intocado; `attestations.py` é irmão, não fork — motivo/escopo/casamento reaproveitam `_chave()`.
- Classificação de motivos continua sendo `classify_needs_human.py` contra os sete de `needs-human-motivos.md`; nada novo classifica.
- `plain-report` intocado como formato; só a origem dos itens muda (pacote auditado) e as automáticas migram de item para informação.

## Faseamento e conta (detalhe em cost/worst_case)

Fase 1: `autonomy.yaml` + `autonomy-guard.py` (absorve ~10). Fase 2: pacote + `audit_question.py` + muralha na transição terminal (mata o caso Epic). Fase 3: `attestations.py` + consumo (mata a contradição PlugSign). Fase 4: modo `--epic` do decide. Fase 5: ledger de defeitos (absorve ~4).

**Piores casos (Epic prematuro / má-classificação / atestado contradito):** (a) Epic cedo demais (WEGO-1406): duas muralhas independentes. Primeira: `audit_question.py` recusa o pacote — item sobre card com `tem_filhas: true` sem a lista completa (key+status de cada uma, `filhas_total` batendo) não vira pergunta; o comando é forçado a enumerar via JQL antes, e com 22 abertas a recomendação "fechar" nem é montável — o pacote sai por sub-task. Segunda: se o agente contornar e perguntar em prosa, o "sim" do dono não é executável — `autonomy-guard.py` bloqueia a transição terminal do Epic porque não existe `approvals/round-<id>.yaml` ancorado em pacote auditado. O pior caso vira "o dono respondeu a uma pergunta que não produz efeito", e a sessão precisa refazer pelo caminho certo — atrito, não reversão.

(b) Irreversível classificado como reversível pelo agente: a classificação NÃO é do agente — é casamento de regex/tool-name contra o YAML, e as irreversíveis conhecidas (push, merge em integração, reset --hard/clean/worktree remove, transição terminal, segredo, terceiros) são bloqueadas pelo hook independentemente da crença do executor. Para a zona cinzenta, precondições verificadas: apagar branch só é automático se `git merge-base --is-ancestor` (rodado PELO hook) confirmar contenção — falhou, cai para pergunta. Ação nova não listada → default `pergunta`. Residual admitido: uma ação irreversível NOVA cujo comando não casa nenhum detect da faixa sempre-pergunta E que o agente acredite reversível passa — o histórico deste harness (bash-pathlock-bypass: agentes contornando via sed/tee) prova que regex de Bash tem buracos. Mitigação: default-ask para o não listado cobre o caso "não sei o que é isso"; o buraco real é o falso-negativo de detect, e cada um vira entrada no ledger + regex nova, como foi com o `(?![&=])` do bash-path-lock.

(c) Atestado que a realidade contradiz: nenhum lado vence automaticamente — nem o atestado cala a evidência (o erro de 08-04 invertido), nem a evidência apaga o atestado. O `audit_question.py` exige `attestation_ref` no item conflitante, e o template do item é a contradição explícita com a evidência enumerada e uma pergunta fechada sobre o escopo real do atestado. A resposta atualiza o registro (`status: contestado` + evidência, ou escopo estreitado), preservando os dois lados datados. Se o dono reafirmar o atestado contra a evidência, isso fica gravado com a evidência anexa — auditável quando a conta chegar. Atestado vencido (`revisita.data`) volta a ser perguntável, mesma regra de vencimento por data que o decide.md já aplica a waivers (gatilho em prosa é mostrado, nunca interpretado).

**Modos de falha (auto-declarados):** 1. Fabricação do artefato de auditoria: `audit_question.py` valida forma, não verdade — um executor pode inventar a lista de filhas. O modelo de confiança é o mesmo dos artefatos de prova deste harness (independente do esquecimento, não da mentira); inventar 41 linhas custa mais que rodar a JQL, mas o gate não é à prova de má-fé. 2. Regex de detect envelhece e tem falso-negativo: já aconteceu duas vezes neste repo (bash-pathlock-bypass via sed/tee; `>=` lido como redirect). Cada buraco exige patch + teste de regressão; o autonomy-guard herda essa manutenção perpétua. 3. Falso-positivo do guard vira novo atrito: um bloqueio errado de push no meio de um wrap-up é exatamente o tipo de defeito-de-harness que a peça 5 registra — o design se auto-alimenta, mas o dia do falso-positivo é ruim. 4. attestations.yaml apodrece: atestados vencidos/contestados acumulam; precisa entrar no `/common:consolidate` (que já re-verifica expertise contra o repo) ou vira registro morto. 5. O lado "grava o atestado certo" é instrução de comando — sessão pode gravar escopo largo demais e o atestado errado passa a calar perguntas legítimas; mitigação parcial: atestado é mostrado ao ser aplicado ("coberto pelo atestado de 03/08"), então o dono vê a aplicação e pode contestá-la. 6. A rodada única atrasa pergunta genuinamente bloqueante: uma decisão de produto que trava o card 1 do drain agora espera o fim da rodada; aceito de propósito (o dono pediu lote), mas em rodada longa isso custa horas de latência. 7. Pergunta do ramo manter continua longa — o atrito não some, muda de "abrir o card" para "ler 5 critérios"; melhor, não zero. 8. report-style-lint avisa e não bloqueia: a disciplina "automática vira informação, não item" pode reincidir até a telemetria justificar apertar.

### Design B (workflow-first) — Funil único de decisão: faixas de autonomia versionadas, dossiê antes da pergunta e atestados duráveis — tudo como extensão do board-flow:decide

PRINCÍPIO ÚNICO: toda pergunta ao dono passa pelo funil que `board-flow/commands/decide.md` já implementa para a Review (agrupar por motivo → uma pergunta fechada por grupo → resposta em lote → aplicar). O que este design faz é (a) tirar do funil o que é reversível, (b) barrar mecanicamente a pergunta não-auditada, (c) dar memória durável ao que o dono já respondeu, (d) adicionar o modo por sub-task, (e) desviar defeito de harness para fila própria. Nada novo duplica decide/waivers/classify_needs_human — cada peça estende um arquivo existente pelo nome.

════ PARTE 1 — Faixas de autonomia como config versionada: `common/autonomy.yaml` ════

Arquivo novo no plugin `common` (instalado junto com os hooks; override por repo em `.claude/autonomy.yaml`, mesclado com o do plugin, só podendo MOVER ação para `sempre-pergunta`, nunca o contrário — endurecer é local, afrouxar é decisão versionada no cepa). Formato:

```yaml
# common/autonomy.yaml — quem decide "pergunto ou faço" é ESTE arquivo, não o agente
versao: 1
executa_e_reporta:        # reversível: faz, e vira LINHA DE INFORMAÇÃO no plain-report
  - id: rodar-build            # rodar build/testes (qualquer duração)
  - id: commit-local           # commit em branch session/* (worktree de sessão)
  - id: criar-card             # criar card não-terminal no board (dívida, infra, follow-up)
  - id: comentar-card          # comentário em card (não-transição)
  - id: apagar-branch-contida  # apagar branch local/remota — SÓ com `git merge-base --is-ancestor <branch> <base>` verdadeiro; a verificação é pré-condição do id, gravada no relatório
  - id: apagar-handoff-vencido # handoff em .claude/handoffs/ cuja branch já morreu
  - id: mover-arquivo          # mover/renomear arquivo dentro do repo (git preserva histórico)
  - id: atualizar-plano        # escrever/atualizar .claude/programs/<nome>/plan.yaml
  - id: rerodar-prove          # re-rodar /board-flow:prove em card `nao-rodou` de causa transitória (decide.md passo 4 já propõe isso; passa a fazer)
  - id: card-infra-agregado    # criar UM card de infra agregando cards travados pela mesma causa (o padrão WEGO-2004 do decide.md passo 4)
sempre_pergunta:          # irreversível ou de fora: espera o lote do funil
  - id: push-remoto
  - id: merge-integracao       # merge em branch de integração (main etc.)
  - id: descartar-trabalho     # worktree-discard, reset --hard, apagar branch NÃO contida
  - id: transicao-terminal     # Done / Won't Do / delete de issue no board
  - id: segredo                # qualquer leitura/escrita/rotação de credencial
  - id: terceiros              # qualquer efeito que sai do par repo+board (e-mail, PR em repo alheio, comentário público, chamada a fornecedor)
default_nao_listado: sempre-pergunta
```

**Default para ação ausente da lista: `sempre-pergunta`, e por quê:** o custo de perguntar demais é atrito recuperável em segundos; o custo de agir demais é o worktree-artifact-rescue de novo (perda silenciosa que custou dias). E o default converge: cada pergunta sobre ação não listada termina com uma linha padrão "proponho adicionar `<id>` ao autonomy.yaml" — a lista cresce por diff versionado, nunca por humor do agente. A fronteira deixa de ser julgamento por turno: os comandos (drain/triage/decide/execute/wrap-up) consultam o arquivo por `id`, e o relatório muda de forma — ação da faixa automática vira linha do bloco `### Detalhe técnico` do plain-report ("Apaguei 6 branches órfãs, todas contidas em main — verificação merge-base no log"), NUNCA item numerado de `### Decisões e próximos passos`. Isso apaga sozinho as ~10 interrupções carimbadas de 08-03/08-10 (build, card de dívida, commit dos 7 docs, 6 branches órfãs, 3 handoffs vencidos).

**Enforcement em profundidade (dois lados):**
- Lado "executa": instrução nos comandos + extensão do `common/hooks/report-style-lint.py` (que já mede o relatório ao fim do turno, cf. plain-report SKILL.md linhas 219-221): passa a AVISAR quando um item numerado da lista final casa com verbo de um `id` da faixa `executa_e_reporta` ("isto era pra ter sido feito, não perguntado"). Avisa, não bloqueia — mesmo contrato do lint atual.
- Lado "sempre-pergunta": hook novo `common/hooks/autonomy-gate.py` (PreToolUse em Bash, irmão do bash-path-lock existente): bloqueia `git push`, merge em branch de integração, `git reset --hard`, `git branch -D` de branch não contida e `worktree remove` quando NÃO existe decisão registrada cobrindo a ação (arquivo `.claude/decisions/<data>-<n>.yaml` que o passo 7 do decide grava ao aplicar o lote: pergunta, resposta, escopo, data). O casamento é grosseiro de propósito (remote+branch), e o fail é fechado com mensagem nomeando o funil: "irreversível sem decisão registrada — leve para o lote do decide". A transição terminal no Jira é bloqueada pelo hook da Parte 2, que é independente.

════ PARTE 2 — Auditar-antes-de-perguntar: dossiê obrigatório + gate independente ════

Duas camadas, e a segunda NÃO depende do autoexame do agente.

**Camada A — `board-flow/bin/render_questions.py` (novo, irmão de classify_needs_human.py/waivers.py):** decide, triage (bucket NEEDS-DECISION) e execute passam a emitir TODA pergunta sobre card via este script, que lê um dossiê `.claude/decision-queue/<KEY>.yaml` e recusa com erro nomeado quando a forma não fecha:
- card com filhas (Epic, ou qualquer card cujo dossiê declare `children_total > 0`): exige `children_total` (com o campo `jql_usado`, ex. `parent = WEGO-1406 OR "Epic Link" = WEGO-1406` — o JQL fica gravado para auditoria posterior), lista `children[]` com `key + status` para TODAS, e `len(children) == children_total`. Faltou → `ERRO: pergunta sobre WEGO-1406 sem dossiê de filhas (declaradas 41, enumeradas 15)`.
- card cuja pergunta cita critério: cada critério exige `{texto, estado: presente|ausente, verificado_em: {commit, "arquivo:linha"}, tipo: implementacao|cobertura}`. Sem `verificado_em`, não renderiza.
Honestidade: isto valida FORMA, não verdade — o agente preencher os campos o obriga a olhar, mas um `arquivo:linha` inventado passa. O que segura a verdade é o proof gate a jusante e a Camada B.

**Camada B — hook independente `board-flow/hooks/terminal-transition-gate.py`:** PreToolUse nos tools `mcp__mcp-atlassian__jira_transition_issue` / `transitionJiraIssue`. Quando a transição alvo é terminal (status do `defaults.status_map` marcado como terminal no board-flow.yaml), o hook consulta o Jira DIRETO por REST (mesmas credenciais de ~/.zsecrets que o mcp-atlassian usa — verificação própria, não o relato do executor): busca filhas por `parent`/Epic Link; se existir filha aberta e não existir dossiê `.claude/decision-queue/<KEY>.yaml` com as filhas enumeradas E decisão do dono registrada (`.claude/decisions/` cobrindo a chave), BLOQUEIA e imprime a lista de filhas abertas na mensagem de erro. Pequeno, Python, testado (casos: epic com filhas abertas sem dossiê → block; com dossiê+decisão → pass; sem filhas → pass; REST fora do ar → block com "não consegui verificar", fail-fechado porque a ação é terminal).

**WEGO-1406 refeito:** o decide tenta perguntar "fecho o Epic?" → render_questions.py recusa sem as 41 filhas enumeradas → o agente enumera (22 abertas) → o Epic cai no modo por sub-task da Parte 4, e o dono despacha as 22 numa sentada. E MESMO que a pergunta prematura escapasse por prosa mal seguida e o dono dissesse "pode concluir", o terminal-transition-gate barra a escrita e devolve as 22 abertas na mensagem — a reversão de 08-10 vira impossível, não improvável.

════ PARTE 3 — Atestados: `.claude/attestations.yaml` gravado e CONSUMIDO ════

`board-flow/bin/attestations.py`, clone estrutural do waivers.py existente (mesmo `_chave()` de casamento frouxo de escopo, mesma regra "malformado é ignorado", mesmo vencimento só-por-data). Esquema por entrada:

```yaml
- id: at-2026-08-03-plugsign-ops
  data: 2026-08-03
  autor: alegomes
  escopo: {tipo: cluster, ref: "pacote operacional onboarding PlugSign", cards: [WEGO-1440, WEGO-1442, ...]}
  afirma: "o pacote operacional do onboarding PlugSign está concluído"
  fonte: "resposta à pergunta 2 do decide de 2026-08-03"
  revisita: "2026-11-01"
  status: vigente   # vigente | contestado | substituido-por: <id>
```

**Quem grava (ponto do fluxo):** o passo 7 do decide.md ("resposta em lote, aplicação em lote") ganha uma regra: resposta do dono que afirma fato sobre estado do mundo — "está concluído", "o SMTP está configurado no painel", "esse fluxo não existe mais" — não é só sim/não: vira entrada em `.claude/attestations.yaml` ANTES de aplicar, e a gravação aparece como linha de informação no relatório. Mesmo ponto no triage (respostas do bucket NEEDS-DECISION) e no plain-report (regra nova na SKILL: resposta do dono com atestado → o turno seguinte grava e reporta a linha).

**Quem consome:** triage.md (antes de classificar card: `aplicavel(atestados, escopo_do_card)`; atestado "concluído" empurra para o bucket ALREADY-IMPLEMENTED→Review — o proof gate continua valendo, o atestado nunca vira Done direto), decide.md (fato já atestado não vira pergunta de novo — vira linha "coberto pelo atestado at-...", igual ao passo 5 de waivers hoje), drain.md e execute.md (card em To Do coberto por atestado "concluído" NÃO é construído — é contradição).

**Regra de conflito — apresentar, nunca vencer em silêncio:** quando atestado e evidência de código discordam, NENHUM lado ganha. render_questions.py tem um tipo `contradicao` que obriga os dois lados na pergunta: o texto+data do atestado E a evidência arquivo:linha, com pergunta fechada e recomendação. Replay PlugSign: em 08-04 a triagem carrega o atestado de 08-03, vê que sua própria evidência classifica o cluster como fila de dev, e em vez de tirar 10 cards do escopo em silêncio emite: "**Contradição:** você atestou em 03/08 que o pacote operacional PlugSign está concluído (at-2026-08-03), mas 10 destes cards têm critérios sem código correspondente (lista). Trato os 10 como já-entregues e mando para a Review provar, ou o atestado valia só para os 12 operacionais? Recomendo a segunda — a evidência separa operação de dev." A contradição de 08-10 e o retrabalho não acontecem. Atestado contestado ganha `status: contestado` + entrada substituta; nunca é apagado (trilha de auditoria).

════ PARTE 4 — Epic indecidível: uma pergunta fechada por sub-task, detalhe assimétrico ════

Vive em decide.md (seção nova "Modo por sub-task") + nos templates do render_questions.py — não só neste design. Quando o dossiê da Parte 2 mostra Epic com filhas abertas e o agente não decide sozinho, o fallback NUNCA é pergunta única sobre o Epic nem silêncio: é o formato de lote do decide aplicado às filhas, numerado, "1 sim, 2 não", com dois templates cuja assimetria o script IMPÕE (recomendação `fechar` → só o one-liner renderiza; `manter` → recusa sem `criterios[]` não-vazio, cada um com `tipo: implementacao|cobertura`):

- **Ramo fechar (a maioria — no WEGO-1406, 12 das 22):**
  `3. WEGO-1436 (POST /upload): o endpoint existe em PlugSignAdapter:253, com cobertura mock e vendor-drift. Fecho? Recomendo sim.`
- **Ramo manter (o motivo É a lista, cada critério com estado + lugar + tipo):**
  `7. WEGO-1437 (POST /send-request) — mantenho aberto? Recomendo sim. Os 5 critérios do seu comentário 36883 (03/08), verificados no HEAD 018b1b1c — nenhum atendido:`
  `   1. [implementação] data de nascimento invariante obrigatória → ausente: PlugSignPort.java:201-226 ainda diz "opcionais"`
  `   2. [implementação] fallbacks best-effort falham explícito → ausente: SolicitarAssinaturaService.java:684,696,762,770 seguem passando nulo (o ramo MÉDICO :717-718 é o padrão a replicar)`
  `   3. [implementação] allow_birth_date incondicional → ausente: PlugSignAdapter.java:984,1010,1018`
  `   4. [cobertura] ramo PRESTADOR→"Contratado" afirmado por teste → o código existe (PlugSignAdapter.java:1021); zero ocorrências de "Contratado" em testes`
  `   5. [cobertura] E2E recusa sem data + payload verificado → ausente`

A etiqueta `[implementação]/[cobertura]` é obrigatória porque foi exatamente essa distinção que derrubou o WEGO-1437 em 07-30 (perturbar o adapter manteve os testes verdes — o contract test só instancia PACIENTE): "está implementado?" teria recebido um "sim" errado. Custo aceito e declarado: a pergunta do ramo manter é longa — por isso o detalhe só existe nesse ramo, que é minoria.

════ PARTE 5 — Defeito de harness vira item de fila, não interrupção ════

Gatilho: (a) mecânico — todo hook que bloqueia já grava em ~/.claude/cepa-telemetry/ (é o que /common:metrics lê); (b) julgamento — quando o agente conclui que o bloqueio é falso-positivo do harness (os 4 casos reais: bounce-reason-gate barrando a palavra "UNPROVEN" numa frase que mandava NÃO reprovar; summary-nulls-gate exigindo rótulos em inglês num comentário pt-BR; last-build.json que não grava em background com build de 26 min; tela do Jira sem o campo Labels), ele chama `common/bin/defect.py add "<título>" --hook <nome> --contexto <evidência>`. Destino: append em `~/.claude/cepa-telemetry/defects.jsonl`; o card de produto segue (parqueado como `nao-rodou` de causa harness — o motivo 1 de needs-human-motivos.md JÁ prevê "trava do próprio harness", cf. o exemplo WEGO-1785). `/common:doctor` e `/common:metrics` passam a listar defeitos pendentes, e uma sessão no cepa os drena para o BACKLOG.md. O dono nunca recebe tarefa de harness no meio de card de produto; recebe a fila quando abre o cepa. O reconhecimento do falso-positivo é julgamento (prosa em comando) — admitido na tabela abaixo; o registro e a superfície são código.

════ TABELA DE ENFORCEMENT (honesta, mecanismo a mecanismo) ════

| Mecanismo | Camada | Nota |
|---|---|---|
| common/autonomy.yaml (+ override .claude/autonomy.yaml) | config versionada lida por código | endure |
| common/hooks/autonomy-gate.py (push/merge/discard sem decisão registrada) | hook Python testado | endure; casamento ação↔decisão é grosseiro de propósito |
| board-flow/hooks/terminal-transition-gate.py (REST próprio, fail-fechado) | hook Python testado, INDEPENDENTE do executor | endure; a peça mais forte contra o caso Epic |
| board-flow/bin/render_questions.py + dossiês .claude/decision-queue/ | script lido por comando | valida FORMA, não verdade — declarado |
| board-flow/bin/attestations.py + .claude/attestations.yaml | config versionada lida por código | endure; gravação/consumo disparados por prosa de comando |
| Passos novos em decide.md / triage.md / drain.md / execute.md | instrução em comando versionado | decai menos; é onde a gravação de atestado e o uso do render vivem — plano de endurecimento: telemetria de "pergunta emitida sem render_questions" via report-style-lint |
| Extensão do report-style-lint.py (item numerado ∈ faixa executa) | hook testado que AVISA | não bloqueia — mesmo contrato atual da skill |
| Extensão da SKILL plain-report (faixa automática = linha de informação; atestado na resposta → gravar) | skill versionada | prosa que decai — por isso o lint mede o desvio |
| defect.py + defects.jsonl + doctor/metrics | script + config lida por código | gatilho de reconhecimento é prosa (julgamento irredutível), destino é código |

════ CONTA CONTRA A SESSÃO REAL (memória de cálculo) ════

| Classe (08-03 a 08-10) | Qtd | Mecanismo que absorve | Resultado |
|---|---|---|---|
| Mecânica reversível carimbada (build, card dívida, commit docs, 6 branches contidas, 3 handoffs, push/merge*) | ~10 | faixa executa_e_reporta do autonomy.yaml (*push/merge ficam na sempre-pergunta, mas entram no LOTE, não pingados) | 0 interrupções avulsas; viram linhas de informação + ≤1 item no lote |
| Defeito de harness travestido de tarefa | ~4 | defect.py → defects.jsonl → doctor/metrics | 0 interrupções em sessão de produto |
| Pergunta prematura (Epic 1406) | 1 | render gate + terminal-transition-gate + modo por sub-task | vira parte do lote, já auditada; reversão impossível |
| Genuinamente do dono (produto, atestado, priorização) | 5 | permanecem — agrupadas pelo funil do decide, 1 rodada em lote | ~5 perguntas numa consulta |
| **Total** | ~20 | | **~5 perguntas, 1 rodada** — fecha com a meta |

**Piores casos (Epic prematuro / má-classificação / atestado contradito):** (a) Epic perguntado cedo demais (o caso WEGO-1406): três anéis. O render_questions.py recusa renderizar a pergunta sem as filhas todas enumeradas com status (erro nomeado dizendo quantas faltam). Se a prosa do comando for mal seguida e a pergunta escapar mesmo assim, a RESPOSTA não é aplicável: o terminal-transition-gate.py, que consulta o Jira por REST com credencial própria (não o relato do agente), bloqueia a transição terminal de card com filha aberta e imprime a lista das abertas na mensagem de erro. O terceiro anel é o modo por sub-task: o caminho legítimo para fechar o Epic passa por despachar as 22 filhas no lote, então "fechar cedo" deixa de ter atalho. (b) Irreversível classificado errado como reversível: a classificação NÃO é do agente — é do autonomy.yaml; um erro de classificação é um erro no arquivo, corrigível por diff e visível em code review do cepa. Independente do que o arquivo diga, o autonomy-gate.py bloqueia os primitivos destrutivos nomeados (push, merge em integração, reset --hard, branch -D não contida, worktree remove) sem decisão registrada, e o override por repo só pode endurecer, nunca afrouxar. O risco residual verdadeiro — ação irreversível NOVA, fora da lista de primitivos do hook, executada por Bash criativo — cai no default `sempre-pergunta` para ação não listada, e é admitido como furo em failure_modes (o precedente bash-pathlock-bypass mostra que lista de padrões em Bash é contornável). (c) Atestado que a realidade depois contradiz: o atestado NUNCA vence o código automaticamente, e o código nunca vence o atestado em silêncio — todo consumidor que encontra a discordância é obrigado (pelo tipo `contradicao` do render_questions.py, que exige os dois lados no corpo da pergunta) a apresentá-la como pergunta fechada com recomendação. A resolução grava `status: contestado` + entrada substituta com a nova data; a entrada velha nunca é apagada, então a trilha "o dono disse X em 08-03, corrigiu para Y em 08-15" fica auditável. O campo `revisita` (só data, mesmo contrato do waivers.py: gatilho em prosa é mostrado, nunca interpretado) reapresenta o atestado vencido como pergunta.

**Modos de falha (auto-declarados):** Com franqueza: (1) Os passos novos em decide.md/triage.md são prosa versionada, e prosa neste harness já decaiu — o próprio backlog registra regra de prompt ignorada entre sessões. Mitigação parcial: o que é destrutivo tem hook atrás (transição terminal, push, merge); o que decai sem hook é a QUALIDADE da pergunta (dossiê pulado onde não há transição terminal em jogo), e a detecção disso fica na telemetria, não num bloqueio. (2) render_questions.py valida forma, não verdade: um agente pode preencher `verificado_em: arquivo:linha` sem ter olhado. O design aceita isso porque o custo de mentir ali é pego a jusante (proof gate) ou pelo dono ao conferir uma linha — mas uma rodada com dossiê inventado passa. (3) autonomy-gate.py herda a fraqueza do bash-path-lock: casar comando Bash por padrão é contornável (`python3 -c` executando git, cf. memória bash-pathlock-bypass) e já produziu falso-positivo (`>=` lido como redirect). Os testes de regressão existentes são o antídoto conhecido, não uma garantia. (4) terminal-transition-gate depende da hierarquia do Jira (parent vs Epic Link variam por site) e de credencial em ~/.zsecrets: montado errado, ou ele bloqueia tudo (fail-fechado vira atrito novo) ou não vê filha nenhuma (fail silencioso — por isso o teste com o WEGO-1406 real antes de confiar). (5) Atestados podem apodrecer: o vencimento é só por data, então um atestado errado e não-revisitado suprime perguntas legítimas até a revisita — o mesmo trade-off já aceito nos waivers. (6) O arquivo defects.jsonl pode virar cemitério se o dono não abrir o cepa; doctor listando pendências mitiga, não resolve. (7) Nada disso fica live sem reinstalar — padrão conhecido do harness, e a causa número um de "construído mas não valendo" nas memórias deste projeto.

### Design C (unconstrained) — Rodada única: faixas de autonomia versionadas + portão de auditoria de perguntas + atestados duráveis

## Visão de conjunto

O dono passa a ser consultado **uma vez por rodada, em lote**, no formato que `board-flow:decide` já usa (decide.md:111-156). Tudo reversível já aconteceu e chega como linha de informação; tudo irreversível espera na consulta única; nenhuma pergunta chega sem passar por um portão mecânico de auditoria; o que o dono já atestou nunca é perguntado de novo; defeito de harness vira item de fila, não interrupção. Cinco peças, cada uma na camada mais dura que comporta.

---

## Peça 1 — Faixas de autonomia em config versionada: `common/autonomy.yaml` (override por repo em `.claude/autonomy.yaml`)

A fronteira "pergunto ou faço?" sai do julgamento por turno e vira lista fechada num arquivo instalado pelo plugin (mesmo padrão de `board-flow.yaml`):

```yaml
version: 1
default: ask   # ação ausente da lista → SEMPRE pergunta (ver justificativa abaixo)
executa_e_reporta:        # reversível: desfazer custa um comando
  - rodar_build                      # build curto ou longo, foreground/background
  - commit_local                     # inclui os "7 documentos de processo" de 08-03
  - criar_card                       # card de dívida/infra — fechável, logo reversível
  - apagar_branch_contido_na_base    # SÓ se `git merge-base --is-ancestor` prova containment
  - apagar_handoff_vencido           # .claude/handoffs/ com data vencida
  - mover_arquivo_no_repo
  - atualizar_plano                  # .claude/programs/*/plan.yaml
  - rerodar_prove                    # re-run de /board-flow:prove em card nao-rodou
  - comentar_card_nao_terminal       # comentário/label que não transiciona
  - criar_worktree_descartavel
sempre_pergunta:          # irreversível ou sai do repo
  - push_remoto
  - merge_em_branch_de_integracao
  - descartar_trabalho               # worktree-discard, reset --hard, branch NÃO contido
  - transicao_terminal_no_board      # Done / Won't Do / fechar Epic
  - qualquer_segredo
  - visivel_a_terceiros              # PR, e-mail, comentário lido por outro time
```

**Default para ação não listada: `ask`, declarado no próprio arquivo.** Por quê: ação ausente correlaciona com ação nova, e ação nova tem reversibilidade desconhecida — o custo de perguntar uma vez é menor que o custo de um irreversível silencioso. Cada `ask` por ausência emite evento `autonomy.unlisted` na telemetria (`common/hooks/_telemetry.py`, ledger em `~/.claude/cepa-telemetry/`), e `/common:metrics` reporta os candidatos a promover para a faixa automática — a lista cresce por evidência, não por humor do agente.

**Enforcement do lado "sempre pergunta" é hook, não prosa**: novo `common/hooks/autonomy-gate.py` (PreToolUse, mesmo contrato exit 0/2-com-stderr de bounce-reason-gate.py:27-30) que casa: `git push`/merge em branch de integração via Bash; tools de transição Jira (`transitionJiraIssue`/`jira_transition_issue`) cujo destino é terminal segundo `status_map` do `board-flow.yaml`; `git branch -D`/`worktree remove` cuja branch NÃO passa em `git merge-base --is-ancestor` (o hook roda o comando barato ele mesmo — verificar antes de afirmar). O hook só libera se existe entrada aprovada correspondente em `.claude/decisions/<data>-round-<n>.yaml` — o arquivo que a Peça 2 produz e o dono responde. `.claude/decisions/` entra na lista de superfícies protegidas do `common/hooks/enforcement-guard.py` (subagente não grava aprovação para si).

**O que muda no relatório**: `plain-report/SKILL.md` ganha a regra — ação da faixa `executa_e_reporta` **nunca vira item numerado** da lista "Decisões e próximos passos" (SKILL.md:95-116); vira linha de informação no detalhe técnico, agrupada ("apagados 6 branches órfãos, todos contidos no main: <lista>"). O tipo de item "trabalho meu esperando o vai" (SKILL.md:124) fica restrito a ações `sempre_pergunta`. `report-style-lint.py` ganha um aviso: item numerado cuja pergunta casa verbo da faixa automática ("rodo o build?", "apago os handoffs?") é desvio.

## Peça 2 — Auditar-antes-de-perguntar mecânico: manifesto de perguntas + `ask-audit-gate.py`

Toda consulta ao dono em sessão board-flow passa a nascer de um **manifesto**: `.claude/pending-questions/round-<n>.yaml`, com uma entrada por pergunta: `card`, `pergunta`, `recomendo`, `evidencia`. Duas validações mecânicas, num script novo `board-flow/bin/audit_question.py` (irmão de `classify_needs_human.py`):

1. **Card com filhas**: pergunta com verbo terminal ("fecho", "concluo", "Won't Do") sobre um card exige bloco `filhas:` com a lista completa `[{key, status}]`, o `children_total`, e a JQL usada (`parent = KEY OR "Epic Link" = KEY`). O script valida: contagem interna bate, nenhum status vazio, JQL registrada. Filhas abertas > 0 → o script **recusa a forma "fecho o Epic?"** e exige o modo por sub-task (Peça 4).
2. **Card que cita `arquivo:linha`**: cada critério citado exige `{arquivo, linha, sha, trecho}` e o script confere o trecho contra o repo no disco (grep na linha) — verificação que NÃO depende do autoexame do agente.

O portão independente: novo hook `common/hooks/ask-audit-gate.py` (PreToolUse em AskUserQuestion) — quando o repo tem `board-flow.yaml` e a pergunta menciona chave de card (`[A-Z]+-\d+`), bloqueia (exit 2) se não existe manifesto validado (`audit_question.py` grava `validado_em` + hash) cobrindo aquela chave, com stderr dizendo exatamente o que falta ("WEGO-1406: pergunta terminal sem enumeração das filhas — rode a JQL e regrave o manifesto").

**Replay WEGO-1406**: agente vê 15 cards e tenta perguntar "fecho o Epic?" → ask-audit-gate bloqueia (sem manifesto) → comando roda a JQL → 41 filhas, 22 abertas → audit_question.py recusa a forma terminal → cai no modo por sub-task da Peça 4. A pergunta prematura que custou a reversão é **impossível de emitir** pelo caminho normal.

Rotulagem honesta: o hook garante que o manifesto existe e é internamente consistente e que `arquivo:linha` confere no disco; a **veracidade** da lista de filhas ainda vem da consulta Jira que o comando mandou fazer (hook não chama MCP). É tripwire forte + instrução, não prova criptográfica — dito na tabela de camadas.

## Peça 3 — Atestados duráveis: `.claude/attestations.yaml` + `board-flow/bin/attestations.py`

Módulo irmão de `waivers.py` (mesmos princípios: autor, data, gatilho de revisita obrigatórios — waivers.py `CAMPOS`; waiver responde "aceito esta prova fraca", atestado responde "o mundo está neste estado"). Esquema, com o caso real:

```yaml
- id: att-2026-08-03-plugsign-operacional
  data: 2026-08-03
  autor: alegomes
  escopo: {tipo: epic, chave: WEGO-1406, descricao: "pacote operacional do onboarding PlugSign"}
  afirmacao: "o pacote operacional está concluído; as filhas operacionais não são fila de dev"
  origem: "resposta do lote round-2, sessão triage 2026-08-03"
  revisit: {data: 2026-11-01, evento_em_prosa: "reabertura de qualquer filha"}  # prosa é mostrada, nunca interpretada — mesma regra de decide.md:103-106
  superseded_by: null
```

**Quem grava**: o passo de aplicação em lote de `decide` (decide.md:140-156) e o de confirmação de `triage` — quando a resposta do dono afirma estado do mundo fora do código ("está concluído", "o SMTP está configurado no painel"), o comando grava via `attestations.gravar(...)` no mesmo movimento em que hoje grava waiver. **Quem consome**: `triage.md`, `decide.md` (no passo 5, junto dos waivers), `drain.md` e `common/commands/next.md` carregam `attestations.carregar(repo)` antes de classificar/executar qualquer card em escopo atestado — atestado aplicável vira **informação** ("coberto pelo atestado de 03/08"), não pergunta.

**Conflito nunca é resolvido em silêncio, por nenhum dos lados**: se a evidência de código contradiz o atestado (triage encontra 10 filhas de dev não entregues dentro de escopo atestado-concluído), o comando emite um item **CONTRADIÇÃO** no lote: cita os dois lados (data+texto do atestado vs `arquivo:linha` da evidência), `Recomendo` derivado da evidência, e a resposta grava `superseded_by` num atestado novo — nunca apaga, a cadeia é auditável. Card em conflito descoberto no meio de um drain fica **Blocked com motivo**, não executado sob nenhuma das duas hipóteses. **Replay PlugSign**: a sessão de 08-04, ao triar o cluster, teria carregado o atestado de 08-03, visto a leitura "fila de dev" contradizê-lo, e feito UMA pergunta em 08-04 — em vez de descoping silencioso de 10 cards e contradição estourando em 08-10.

## Peça 4 — Modo por sub-task com detalhe assimétrico (vive em `decide.md`, seção nova "Epic indecidível", referenciada por `triage.md`)

Quando a Peça 2 recusa a pergunta terminal, o fallback é uma pergunta fechada **por filha**, no formato de lote que decide já tem, com o detalhe exatamente onde a decisão depende dele:

**Ramo fechar — uma linha**:
> 3. **WEGO-1436 (`POST /upload`) — fecho? Recomendo sim.** Endpoint existe em `PlugSignAdapter.java:253`, com cobertura mock e vendor-drift.

**Ramo manter aberto — o motivo É a lista**, cada critério com estado verificado + local, e cada um etiquetado `[implementação]` ou `[cobertura]` — a distinção que derrubou o WEGO-1437 em 07-30 (ramo PRESTADOR existia em `PlugSignAdapter.java:1021`, mas o contract test só instancia `PACIENTE`; "está implementado?" teria recebido um "sim" errado):
> 4. **WEGO-1437 (`POST /send-request`) — mantenho aberto? Recomendo sim.** Os 5 critérios do seu comentário 36883, verificados no HEAD `018b1b1c`:
>    1. `[implementação]` data de nascimento invariante → ausente: `PlugSignPort.java:201-226` ainda diz "opcional".
>    2. `[implementação]` fallbacks falham explícito → ausente: `SolicitarAssinaturaService.java:684,696,762,770` seguem passando nulo.
>    3. `[implementação]` `allow_birth_date` incondicional → ausente: `PlugSignAdapter.java:984,1010,1018`.
>    4. `[cobertura]` PRESTADOR→"Contratado" afirmado por teste → código existe (`:1021`), zero ocorrências em teste.
>    5. `[cobertura]` E2E recusa pedido sem data → ausente.

`audit_question.py` valida a forma: item "manter aberto" sem `{estado, onde}` por critério não passa; item "fechar" com mais de uma linha de evidência é aviso. Custo aceito e declarado: a pergunta do ramo minoritário é longa — no WEGO-1406, 12 das 22 filhas abertas são operacionais e cabem em uma linha.

## Peça 5 — Defeito do harness tem fila própria

Gatilho: hook/gate bloqueou (exit 2) ou uma peça do harness falhou (`last-build.json` não grava em background, `summary-nulls-gate` exigindo inglês em pt-BR) **e** o agente conclui que o bloqueio é da ferramenta, não do trabalho. Ação: aplica o desbloqueio documentado se houver, e roda `common/bin/log-harness-defect.py`, que grava um arquivo por defeito em `~/.claude/cepa-telemetry/defects/<ts>-<slug>.yaml` (dir-de-arquivos evita corrida entre sessões; o repo cepa vive em Insync, append direto no BACKLOG.md de outra sessão é corrida conhecida). Consumo: `/common:doctor` e `/common:metrics` listam a fila; uma sessão no repo cepa drena para o BACKLOG.md. Reforço mecânico do "nunca vira tarefa do dono no meio de card de produto": `report-style-lint.py` ganha a lista de nomes de componentes do harness (hooks, gates, `last-build.json`) e avisa quando um item numerado da lista final os menciona em sessão de repo de produto.

## Por que este desenho e não os alternativos considerados

- **Risco contínuo (score) em vez de faixa binária**: rejeitado — score é julgamento por turno com casas decimais; o viés observado (perguntar demais / auditar depois) voltaria pela porta da calibração. Lista fechada + default declarado é auditável e versionável.
- **Novo comando "decision-queue"**: rejeitado — decide.md já é a fila de decisão com agrupamento, waiver e lote (decide.md:94-156); duplicar seria a colisão que o critério de fit pune. O manifesto de perguntas da Peça 2 é insumo do decide/triage, não um comando paralelo.
- **Aprender da telemetria automaticamente** (promover ação para a faixa automática quando rubber-stamp rate > X): rejeitado como automático — mudança de faixa é mudança de contrato com o dono; a telemetria **propõe** via /common:metrics, o dono promove editando o YAML versionado.

## Tabela de enforcement (mecanismo → camada)

| Mecanismo | Camada | Nota honesta |
|---|---|---|
| `common/autonomy.yaml` (+ override `.claude/autonomy.yaml`) | config versionada lida por código | lida por autonomy-gate.py e pelos comandos |
| `autonomy-gate.py` | hook Python testado (endure) | Bash-regex incompleto por natureza — lição do bash-pathlock; cresce por telemetria, testes de regressão desde o dia 1 |
| `ask-audit-gate.py` + `audit_question.py` | hook testado + script com entrada/saída definidas | garante existência/consistência/`arquivo:linha`; veracidade da lista de filhas vem da consulta Jira mandada pelo comando (instrução) |
| `.claude/attestations.yaml` + `attestations.py` | config versionada + script | **consumo é instrução em comando versionado** (decai menos); plano de endurecimento: gate-advance.py checar atestado antes de transição terminal (fase posterior) |
| Templates fechar/manter (Peça 4) | instrução em decide.md/triage.md, forma validada por audit_question.py | a forma é mecânica, o conteúdo é do agente |
| Fila de defeitos | script + instrução + aviso do report-style-lint.py | o julgamento "o bloqueio é da ferramenta" é prosa — admitido |
| Faixa automática no relatório | skill (plain-report) + aviso do report-style-lint.py | lint avisa, não bloqueia — mesma política já vigente (SKILL.md:218-221) |
| Proteção de `.claude/decisions/` | extensão do enforcement-guard.py (hook existente) | cobre subagentes; o lead ainda poderia gravar — tripwire, não criptografia |

**Piores casos (Epic prematuro / má-classificação / atestado contradito):** (a) Epic perguntado cedo demais: o ask-audit-gate.py bloqueia a AskUserQuestion sobre chave de card sem manifesto validado; o manifesto exige a enumeração completa das filhas com status e a JQL usada; com filhas abertas > 0, audit_question.py recusa a própria forma "fecho o Epic?" e força o modo por sub-task — no replay do WEGO-1406, as 41 filhas aparecem ANTES de qualquer pergunta e o dono despacha as 22 abertas num lote (12 one-liners + 10 detalhadas). Evasão residual: pergunta redigida sem chave de card escapa do regex do hook — coberta em segunda linha pela regra de forma no decide/triage (instrução) e admitida como decaível. (b) Irreversível classificado como reversível: o agente NÃO classifica — a faixa é lista fechada e ação ausente cai em `default: ask`; e mesmo que o agente acredite que pode, o autonomy-gate.py bloqueia na fronteira da ferramenta (push, merge, transição terminal, branch não contido verificado por `git merge-base --is-ancestor` rodado pelo próprio hook) sem entrada aprovada em .claude/decisions/. Residual: comando Bash destrutivo fora dos padrões do hook passa — mesmo modo de falha do histórico bash-pathlock; mitigação declarada: testes de regressão e crescimento dos padrões por telemetria, nunca a promessa de cobertura total. (c) Atestado contradito pela realidade: regra fixa de conflito — nenhum lado vence em silêncio; o comando consumidor emite item CONTRADIÇÃO citando os dois lados (data+texto do atestado vs evidência em arquivo:linha), com Recomendo derivado da evidência; a resposta do dono grava um atestado novo com superseded_by (cadeia auditável, nada é apagado); card em conflito no meio de um drain vira Blocked com motivo em vez de executado sob hipótese. No caso PlugSign, isso antecipa a contradição de 08-10 para 08-04 e elimina o rework.

**Modos de falha (auto-declarados):** 1) Auto-aprovação: o lead pode, em tese, gravar ele mesmo a entrada em .claude/decisions/ que o autonomy-gate exige — enforcement-guard cobre subagentes, não o lead; é tripwire auditável (arquivo datado, diff visível), não garantia. 2) Evasão de regex: ask-audit-gate depende de a pergunta citar a chave do card; autonomy-gate depende de padrões de Bash — ambos herdam o modo de falha já observado no bash-pathlock (bypass por forma não prevista) e o inverso (falso positivo, como o `>=` e o bounce-reason-gate barrando aprovação); mitigação: cada hook nasce com suíte de regressão incluindo os falso-positivos históricos, e o próprio falso positivo cai na fila de defeitos sem interromper o dono. 3) Atestados apodrecem: um atestado de 08-03 pode ficar verdadeiro-na-data e falso-hoje; revisit por data + varredura do /common:consolidate mitigam, mas entre a mudança do mundo e a revisita há uma janela em que o harness deixa de perguntar algo que voltou a ser pergunta — por isso conflito com evidência de código SEMPRE reabre. 4) Pressão de crescimento da faixa automática: cada "sim" carimbado convida a promover a ação, e uma promoção errada (ex.: push) remove exatamente a pergunta que protegia; a promoção é edição manual do YAML versionado, nunca automática — mas o dono cansado pode promover demais, e o design não o impede. 5) O manifesto de perguntas é atrito novo para o agente (mais um arquivo antes de perguntar); se os comandos não o tornarem caminho natural, sessões fora de board-flow perguntarão livre (o hook só arma com board-flow.yaml presente) — decaimento parcial aceito e declarado. 6) A pergunta longa do ramo manter-aberto não some — é o atrito residual assumido, minoritário por construção.

### Vereditos dos 3 juízes cegos

Pontos Borda: {"B": 9, "A": 4, "C": 5} — B vencedor unânime (1º lugar nos 3 rankings).

**Juiz 1** — ranking ['B', 'A', 'C']
- B (69): Melhor mecanismo no ponto mais crítico: o terminal-transition-gate.py consulta o Jira por REST com credencial própria e bloqueia fail-fechado — é o único design em que a existência de filhas abertas é verificada por algo que NÃO é o relato do executor. Citações conferidas (SKILL.md:219-221, motivo 1 + WEGO-1785 em needs-human-motivos.md, waivers.py _chave/CAMPOS) todas corretas. Tabela de conta classe→mecanismo é a mais limpa das três. Regra de override 'só endurecer, nunca afrouxar' é fit fino com a filosofia.
- A (68): Praticamente empatado com B; a arquitetura pergunta-só-vira-efeito-via-pacote-auditado é a mais elegante das três (um 'sim' colhido em prosa não é executável), e o detect: por ação torna o autonomy.yaml genuinamente lido por código. Citações (decide.md 140-156, SKILL.md 95-124/218-221, _chave) conferem. Fica atrás de B num único ponto estrutural: nada verifica as filhas independentemente do executor.
- C (64): Sólido e com fit repo-específico fino (dir-de-arquivos contra corrida do Insync, enforcement-guard protegendo .claude/decisions/, seção de alternativas rejeitadas), mas a peça central de auditoria repousa num hook em AskUserQuestion — e neste harness as perguntas do decide nascem como texto de relatório, não como tool call, então o portão mais vendido do design pode raramente disparar. Citações (decide.md:103-106/111-156/159-168, SKILL.md:95-116/124/218-221) conferem.

**Juiz 2** — ranking ['B', 'C', 'A']
- B (70): O único desenho cujo anel mais duro não depende de nada que o executor relata: o terminal-transition-gate consulta o Jira por REST com credencial própria e falha fechado, tornando o caso WEGO-1406 impossível mesmo com toda a prosa decaída. Citações todas conferidas e corretas (inclusive o WEGO-1785 no motivo 1). Conta fecha em ~5 perguntas, 1 rodada, com push/merge reconciliados dentro das ~10 mecânicas.
- C (67): Quase tão completo quanto B e o mais consciente do repo (corrida do Insync, enforcement-guard sobre .claude/decisions/, alternativas rejeitadas com motivo). O calcanhar: o portão de pergunta ancora em AskUserQuestion, mas as perguntas do decide saem como texto no chat — o hook pode não disparar no caminho real; e a veracidade da lista de filhas continua auto-relatada, sem a re-consulta independente que B faz.
- A (64): Config mais legível por máquina (detect + precondições rodadas pelo hook) e o consumo de atestados mais forte dos três (attestation_ref obrigatório no lint). Perde onde a verdade importa: a enumeração de filhas é inteiramente auto-relatada, sem muralha independente do executor além do bloqueio de transição; e a conta das ~10 mecânicas não reconcilia push/merge, que o próprio desenho põe na sempre-pergunta.

**Juiz 3** — ranking ['B', 'C', 'A']

## Design final (vencedor B revisado, com enxertos de A e C)

### Funil único de decisão, agora com binding mecânico dos dois lados: faixas de autonomia com detect por tool-call, portão de pergunta no AskUserQuestion e dossiê verificado contra o disco

PRINCÍPIO ÚNICO (mantido do design vencedor): toda pergunta ao dono passa pelo funil que `board-flow/commands/decide.md` já implementa (passo 6, linhas 111-136: agrupar por motivo → uma pergunta fechada por grupo; passo 7, linhas 138-156: resposta em lote → aplicação em lote). Este design (a) tira do funil o que é reversível, (b) barra mecanicamente a pergunta não-auditada, (c) dá memória durável ao que o dono já respondeu, (d) adiciona o modo por sub-task, (e) desvia defeito de harness para fila própria. A REVISÃO fecha os três furos apontados pelos críticos — todos sobre a mesma fraqueza: o lado "faz em vez de perguntar" e a qualidade da pergunta viviam em prosa + lint a posteriori. Agora os dois lados têm gate no momento do ato: os ids do autonomy.yaml ganham binding mecânico a tool-calls (`detect:`, enxertado do rival A), a pergunta em si ganha um hook PreToolUse em AskUserQuestion (`ask-audit-gate.py`, enxertado do rival C), e o dossiê deixa de ser validado só na forma: `arquivo:linha` é conferido contra `git show` no disco (A/C).

════ PARTE 1 — Faixas de autonomia: `common/autonomy.yaml` com `detect:` por ação ════

Arquivo novo no plugin `common` (override por repo em `.claude/autonomy.yaml`, mesclado, que só pode MOVER ação para `sempre-pergunta` — endurecer é local, afrouxar é diff versionado no cepa). REVISADO (crédito A): cada id carrega um bloco `detect:` que mapeia a ação a tool-calls concretos — regex de Bash, nome de tool MCP ou padrão de path — e, onde a reversibilidade é condicional, uma `precondicao` que O HOOK roda, não o agente:

```yaml
# common/autonomy.yaml — quem decide "pergunto ou faço" é ESTE arquivo, não o agente
versao: 2
executa_e_reporta:            # reversível: faz, e vira LINHA DE INFORMAÇÃO no plain-report
  - id: rodar-build
    detect: {bash: '\b(mvn|\./mvnw|npm (test|run build)|pytest|gradle)\b'}
  - id: commit-local
    detect: {bash: '^git commit\b'}
  - id: criar-card             # card não-terminal (dívida, infra, follow-up) — fechável, logo reversível
    detect: {mcp: '(createJiraIssue|jira_create_issue)$'}
  - id: comentar-card
    detect: {mcp: '(addCommentToJiraIssue|jira_add_comment)$'}
  - id: apagar-branch-contida
    detect: {bash: '^git branch -[dD]\s+(?P<branch>\S+)'}
    precondicao: 'git merge-base --is-ancestor <branch> <base>'   # rodada PELO autonomy-gate; falhou → vira sempre-pergunta (descartar-trabalho)
  - id: apagar-handoff-vencido
    detect: {path: '\.claude/handoffs/.*\.md$', op: delete}
    precondicao: 'branch correspondente não existe mais'
  - id: mover-arquivo
    detect: {bash: '^git mv\b'}
  - id: atualizar-plano
    detect: {path: '\.claude/programs/.*/plan\.yaml$'}
  - id: rerodar-prove          # decide.md passo 4 (linhas 79-90) já propõe; passa a fazer
    detect: {slash: '/board-flow:prove(-drain)?'}
  - id: card-infra-agregado    # o padrão WEGO-2004 do decide.md linha 90
    detect: {mcp: '(createJiraIssue|jira_create_issue)$', label: 'infra'}
sempre_pergunta:               # irreversível ou de fora: espera o lote do funil
  - {id: push-remoto,          detect: {bash: '^git push\b'}}
  - {id: merge-integracao,     detect: {bash: '^git merge\b', branch_atual: '(main|master|develop)'}}
  - {id: descartar-trabalho,   detect: {bash: '(git reset --hard|git clean -f|git checkout \.|worktree remove)'}}
  - {id: transicao-terminal,   detect: {mcp: '(transitionJiraIssue|jira_transition_issue)$', destino_terminal: true}}  # resolvido via status_map do board-flow.yaml
  - {id: segredo,              detect: {path: '(\.zsecrets|\.env)($|/)', op: any}}
  - {id: terceiros,            detect: {mcp: '(send_dm|publish_|createConfluence)'}}
default_nao_listado: sempre-pergunta
```

Os dez ids da faixa automática são as ~10 mecânicas carimbadas de 08-03/08-10 (build, card de dívida, commit dos 7 docs de processo, 6 branches órfãs contidas, 3 handoffs vencidos, mover arquivo, atualizar plano). **Default para ação ausente: `sempre-pergunta`** — perguntar demais custa segundos; agir demais é o worktree-artifact-rescue de novo. Cada miss emite evento `autonomy.unlisted` na telemetria (`common/hooks/_telemetry.py`, que já existe com `emit()` fail-silent) e a pergunta termina com "proponho adicionar `<id>` ao autonomy.yaml" — a lista cresce por diff versionado com evidência, nunca por humor do agente (regra do rival C mantida: promoção é edição manual, jamais automática).

**Enforcement dos dois lados — a revisão central:**
- Lado "sempre-pergunta" (destrutivo): `common/hooks/autonomy-gate.py` (PreToolUse em Bash + tools MCP do Jira, contrato exit 0/2-com-stderr do `bounce-reason-gate.py`). Casa o tool-call contra os `detect:` e bloqueia ação da faixa `sempre_pergunta` sem decisão registrada em `.claude/decisions/<data>-round-<n>.yaml` (o arquivo que o passo 7 do decide grava ao aplicar o lote: pergunta, resposta, escopo, data, ref ao dossiê auditado). As precondições são comandos que o PRÓPRIO hook roda (`git merge-base --is-ancestor` — verificar antes de afirmar): a reversibilidade do apagar-branch é verificada, não presumida (crédito A).
- Lado "executa-e-reporta" (o furo nº 1 e nº 3 dos críticos): `common/hooks/ask-audit-gate.py` (PreToolUse em **AskUserQuestion**, crédito C). Quando o repo tem `board-flow.yaml`: (i) pergunta cujo texto casa um `detect`/verbo de id da faixa `executa_e_reporta` ("rodo o build?", "apago os handoffs?", "crio o card de dívida?") → **exit 2** com stderr "faixa executa-e-reporta (`<id>`): faça, verifique a precondição e reporte como linha de informação"; (ii) pergunta que menciona chave de card (`[A-Z]+-\d+`) sem dossiê validado em `.claude/decision-queue/<KEY>.yaml` (com `validado_em` + hash gravados pelo render_questions) → exit 2 dizendo exatamente o que falta. "Fazer em vez de perguntar" deixa de depender de prosa: a pergunta preguiçosa é bloqueada no ato, no mesmo turno, não detectada por telemetria depois. O `report-style-lint.py` (que já mede o relatório ao fim do turno, cf. plain-report SKILL.md linha 218) continua como segunda linha para a evasão que nenhum hook pega — pergunta digitada em prosa no corpo do relatório, sem tool-call — avisando e emitindo `autonomy.asked_instead_of_did`; agora com casamento mecânico contra os mesmos `detect:` do YAML, não heurística própria.
- Anti-autoaprovação (crédito C): `.claude/decisions/`, `.claude/decision-queue/` e `.claude/attestations.yaml` entram nas superfícies protegidas do `common/hooks/enforcement-guard.py` já existente — subagente não grava aprovação nem atestado para si. O lead ainda pode; é tripwire auditável (arquivo datado, diff visível), declarado como tal.

**Relatório:** plain-report SKILL ganha a regra — ação da faixa automática NUNCA vira item numerado de `### Decisões e próximos passos` (SKILL.md linha 37/52); vira linha agrupada no `### Detalhe técnico` ("Apaguei 6 branches órfãs, todas contidas em main — merge-base no log"). Push/merge continuam existindo, mas entram no LOTE, não pingados.

════ PARTE 2 — Auditar-antes-de-perguntar: dossiê VERIFICADO + dois gates independentes ════

**Camada A — `board-flow/bin/render_questions.py`** (novo, irmão de `classify_needs_human.py`/`waivers.py`): decide, triage (bucket NEEDS-DECISION) e execute emitem TODA pergunta sobre card via este script, que lê o dossiê `.claude/decision-queue/<KEY>.yaml` e recusa com erro nomeado quando não fecha. REVISADO (furo nº 2): ele agora verifica CONTEÚDO onde dá, não só forma:
- Card com filhas: exige `children_total`, `jql_usado` (ex. `parent = WEGO-1406 OR "Epic Link" = WEGO-1406`), lista `children[]` com key+status para TODAS, `len == children_total`, E o artefato bruto `.claude/decision-queue/<KEY>.children.json` — o retorno cru que o atlassian-expert grava no momento da consulta. O script confere a lista do dossiê contra o JSON bruto (chaves e statuses batem). Fabricar exige fabricar dois artefatos consistentes, e o gate da Camada B re-consulta por REST de qualquer jeito. Faltou → `ERRO: pergunta sobre WEGO-1406 sem dossiê de filhas (declaradas 41, enumeradas 15)`.
- Critério com `arquivo:linha`: cada um exige `{texto, estado: presente|ausente, tipo: implementacao|cobertura, verificado_em: {commit, arquivo, linha, trecho}}` e o script RODA `git show <commit>:<arquivo>` conferindo que o `trecho` aparece na `linha` ±2 (crédito A/C). `arquivo:linha` inventado não passa mais — falha mecânica, não confiança. Semântica ("o trecho prova o critério") continua sendo do agente; dito na tabela.
- Ao aprovar, grava `validado_em` + hash do dossiê — é isso que o ask-audit-gate.py exige antes de deixar a AskUserQuestion sair.
- Assimetria dos templates (Parte 4) e o tipo `contradicao` (Parte 3) são impostos aqui.

**Camada B — `board-flow/hooks/terminal-transition-gate.py`** (mantido do vencedor, a peça mais forte): PreToolUse em `transitionJiraIssue`/`jira_transition_issue`. Transição para status terminal (marcado no `status_map` do board-flow.yaml) → o hook consulta o Jira DIRETO por REST com as credenciais de ~/.zsecrets (verificação própria, não o relato do executor): filha aberta + sem dossiê validado + sem decisão em `.claude/decisions/` cobrindo a chave → BLOQUEIA e imprime a lista das filhas abertas. Fail-fechado (REST fora do ar → block "não consegui verificar"), porque a ação é terminal.

**WEGO-1406 refeito, agora com três anéis mecânicos:** o agente tenta perguntar "fecho o Epic?" com 15 vistas → o ask-audit-gate bloqueia a AskUserQuestion (sem dossiê validado) → render_questions recusa o dossiê parcial (41 declaradas, 15 enumeradas) → enumeração via JQL → 22 abertas → a forma "fecho o Epic?" fica inconstruível e cai no modo por sub-task. E se tudo isso fosse contornado por prosa e o dono dissesse "pode concluir", o "sim" não é executável: o terminal-transition-gate barra a escrita e devolve as 22 abertas. A reversão de 08-10 vira impossível no efeito, não improvável na conduta.

════ PARTE 3 — Atestados: `.claude/attestations.yaml` gravado e CONSUMIDO ════ (mantido, com um reforço)

`board-flow/bin/attestations.py`, clone estrutural do `waivers.py` (mesma `_chave()` de casamento frouxo, linhas 42-47; mesma regra "malformado é ignorado", linhas 50-68; vencimento só por data, linhas 71-79 — gatilho em prosa é mostrado, nunca interpretado, mesma regra do decide.md linhas 103-106). Esquema:

```yaml
- id: at-2026-08-03-plugsign-ops
  data: 2026-08-03
  autor: alegomes
  escopo: {tipo: cluster, ref: "pacote operacional onboarding PlugSign", cards: [WEGO-1440, WEGO-1442, ...]}
  afirma: "o pacote operacional do onboarding PlugSign está concluído"
  fonte: "resposta 2 do decide de 2026-08-03 (round ref em .claude/decisions/)"
  revisita: "2026-11-01"
  status: vigente        # vigente | contestado | substituido-por: <id>
```

**Quem grava:** o passo 7 do decide.md — resposta do dono que afirma fato sobre o mundo ("está concluído", "o SMTP está configurado no painel") vira entrada ANTES de aplicar, no mesmo movimento em que hoje grava `waivers.gravar(...)`; idem no fechamento do triage; a gravação aparece como linha de informação no relatório. **Quem consome:** triage.md (atestado "concluído" empurra para ALREADY-IMPLEMENTED→Review — o proof gate continua valendo, atestado NUNCA vira Done direto), decide.md (novo passo 5b, espelho do passo 5 de waivers: fato atestado vira linha "coberto pelo atestado at-...", não pergunta), drain.md e execute.md (card To Do coberto por atestado "concluído" não é construído — é contradição). **Reforço da revisão (crédito A):** o render_questions exige `attestation_ref` em qualquer item cujo escopo casa um atestado vigente — aplicando-o ou nomeando o conflito. Item em escopo atestado sem a referência não renderiza: o arquivo que ninguém lê fica estruturalmente impossível, em vez de depender da prosa "consulte os atestados".

**Conflito — apresentar, nunca vencer em silêncio:** tipo `contradicao` do render_questions obriga os dois lados no corpo (texto+data do atestado E evidência arquivo:linha verificada), pergunta fechada, recomendação. Replay PlugSign: em 08-04 a triagem carrega o atestado de 08-03, sua evidência lê o cluster como fila de dev, e em vez de tirar 10 cards do escopo em silêncio emite: "**Contradição:** você atestou em 03/08 que o pacote operacional PlugSign está concluído (at-2026-08-03), mas 10 destes cards têm critérios sem código correspondente (lista com arquivo:linha). O atestado valia só para os 12 operacionais? Recomendo sim — a evidência separa operação de dev." A contradição aparece em 08-04, não em 08-10; o retrabalho não acontece. Resolução grava `status: contestado` + entrada substituta datada; nada é apagado (trilha auditável). Card em conflito no meio de um drain fica Blocked com motivo, nunca executado sob hipótese (crédito C).

════ PARTE 4 — Epic indecidível: pergunta fechada por sub-task, detalhe assimétrico ════ (mantido)

Vive em decide.md (seção nova "Modo por sub-task") + nos templates do render_questions.py, que IMPÕE a assimetria: recomendação `fechar` → só o one-liner renderiza (mais de uma linha de evidência = recusa); `manter` → recusa sem `criterios[]` não-vazio, cada um com `tipo: implementacao|cobertura` e `verificado_em` conferido no disco. Formato do lote do decide (numerado, "1 sim, 2 não"):

- **Ramo fechar (maioria — 12 das 22 no WEGO-1406):** `3. WEGO-1436 (POST /upload): o endpoint existe em PlugSignAdapter:253, com cobertura mock e vendor-drift. Fecho? Recomendo sim.`
- **Ramo manter (o motivo É a lista):** `7. WEGO-1437 (POST /send-request) — mantenho aberto? Recomendo sim. Os 5 critérios do seu comentário 36883 (03/08), verificados no HEAD 018b1b1c — nenhum atendido:` seguido dos 5, cada um `[implementação]`/`[cobertura]` + estado + local — ex.: `2. [implementação] fallbacks best-effort falham explícito → ausente: SolicitarAssinaturaService.java:684,696,762,770 seguem passando nulo (o ramo MÉDICO :717-718 é o padrão a replicar)`; `4. [cobertura] PRESTADOR→"Contratado" afirmado por teste → o código existe (PlugSignAdapter.java:1021); zero ocorrências de "Contratado" em testes`.

A etiqueta é obrigatória porque foi essa distinção que derrubou o WEGO-1437 em 07-30 (o contract test só instancia PACIENTE; perturbar o adapter manteve verde): "está implementado?" teria recebido um "sim" errado — e agora nem compila no schema. Custo aceito: o ramo manter é longo; por isso o detalhe só existe nele, que é minoria.

════ PARTE 5 — Defeito de harness vira fila, não interrupção ════ (mantido, com um conserto do rival C)

Gatilho: (a) mecânico — hooks que bloqueiam já emitem telemetria; (b) julgamento — agente reconhece falso-positivo do harness (os 4 reais: bounce-reason-gate barrando "UNPROVEN" numa frase que mandava NÃO reprovar; summary-nulls-gate exigindo inglês em pt-BR; last-build.json que não grava com build de 26 min em background; tela do Jira sem Labels) e chama `common/bin/defect.py add "<título>" --hook <nome> --contexto <evidência>`. Destino REVISADO (crédito C): um arquivo por defeito em `~/.claude/cepa-telemetry/defects/<ts>-<slug>.yaml` — dir-de-arquivos, não JSONL compartilhado, porque o append concorrente entre sessões é corrida conhecida (o repo vive em Insync). O card de produto segue parqueado como `nao-rodou` de causa harness — o motivo já previsto em docs/needs-human-motivos.md (linha 32: "trava do próprio harness"). `/common:doctor` e `/common:metrics` listam a fila; uma sessão no cepa drena para o BACKLOG.md. O reconhecimento do falso-positivo é julgamento (prosa) — admitido; registro e superfície são código. Falso-positivo dos hooks NOVOS deste design cai nessa mesma fila, não no colo do dono.

════ TABELA DE ENFORCEMENT (revisada, honesta) ════

| Mecanismo | Camada | Nota |
|---|---|---|
| common/autonomy.yaml com detect:/precondicao (+ override) | config versionada lida por código | endure; detect é o binding que faltava (crédito A) |
| common/hooks/autonomy-gate.py (destrutivos sem decisão registrada; precondições rodadas pelo hook) | hook Python testado | endure; regex de Bash é contornável — lição bash-pathlock, testes de regressão desde o dia 1 |
| common/hooks/ask-audit-gate.py (AskUserQuestion: bloqueia pergunta de faixa executa E pergunta sobre card sem dossiê validado) | hook Python testado | endure; NOVO — fecha os furos 1 e 3 dos críticos; não pega pergunta em prosa no relatório (sem tool-call) |
| board-flow/hooks/terminal-transition-gate.py (REST próprio, fail-fechado) | hook independente do executor | endure; a peça mais forte contra o caso Epic |
| board-flow/bin/render_questions.py (dossiês; git show confere trecho na linha; children.json cruzado; attestation_ref obrigatório) | script testado chamado por comando | verifica EXISTÊNCIA e CONSISTÊNCIA mecanicamente; semântica ("o trecho prova o critério") segue do agente — declarado |
| board-flow/bin/attestations.py + .claude/attestations.yaml | config versionada lida por código | endure; o consumo é forçado pelo attestation_ref do render, não só por prosa |
| enforcement-guard.py cobrindo .claude/decisions/, decision-queue/, attestations.yaml | extensão de hook existente | cobre subagentes; lead ainda grava — tripwire auditável (crédito C) |
| Passos novos em decide/triage/drain/execute.md | instrução em comando versionado | decai menos; mas agora TODO desvio destrutivo ou de pergunta esbarra num dos três hooks — a prosa virou conveniência, não muralha |
| Extensão do report-style-lint.py (item numerado casando detect de faixa executa; pergunta em prosa) | hook que AVISA + telemetria | segunda linha para a única evasão sem tool-call; mesmo contrato da SKILL (linha 218) |
| SKILL plain-report (faixa automática = informação; atestado na resposta → gravar) | skill versionada | prosa que decai — medida pelo lint |
| defect.py + defects/<ts>-<slug>.yaml + doctor/metrics | script + arquivos lidos por código | gatilho de reconhecimento é prosa (julgamento irredutível); destino é código |

════ CONTA CONTRA A SESSÃO REAL ════

| Classe (08-03 a 08-10) | Qtd | Mecanismo | Resultado |
|---|---|---|---|
| Mecânica reversível carimbada (build, card dívida, commit 7 docs, 6 branches contidas, 3 handoffs; push/merge*) | ~10 | faixa executa_e_reporta + ask-audit-gate bloqueando a pergunta preguiçosa no ato (*push/merge ficam na sempre-pergunta, mas entram no LOTE) | 0 interrupções avulsas; linhas de informação + ≤1 item no lote |
| Defeito de harness travestido de tarefa | ~4 | defect.py → defects/ → doctor/metrics | 0 interrupções em sessão de produto |
| Pergunta prematura (Epic 1406) | 1 | ask-audit-gate + render + terminal-transition-gate + modo por sub-task | parte do lote, pré-auditada; reversão impossível no efeito |
| Genuinamente do dono (produto, atestado, priorização) | 5 | permanecem — funil do decide, 1 rodada em lote | ~5 perguntas numa consulta |
| **Total** | ~20 | | **~5 perguntas, 1 rodada** — fecha com a meta; eliminá-las seria defeito |

**Superfícies:** common/autonomy.yaml (novo: faixas + detect + precondicao; override .claude/autonomy.yaml só-endurece); common/hooks/autonomy-gate.py (novo hook PreToolUse Bash+MCP) + tests/test_autonomy_gate.py; common/hooks/ask-audit-gate.py (novo hook PreToolUse em AskUserQuestion) + tests/test_ask_audit_gate.py; board-flow/hooks/terminal-transition-gate.py (novo hook, REST próprio) + tests/test_terminal_transition_gate.py; board-flow/bin/render_questions.py (novo) + .claude/decision-queue/<KEY>.yaml e <KEY>.children.json + tests/test_render_questions.py; board-flow/bin/attestations.py (novo, clone estrutural de board-flow/bin/waivers.py) + .claude/attestations.yaml + tests/test_attestations.py; .claude/decisions/<data>-round-<n>.yaml (gravado pelo passo 7 do decide, lido pelos hooks); common/hooks/enforcement-guard.py (estendido: .claude/decisions/, decision-queue/, attestations.yaml protegidos de subagentes); common/hooks/report-style-lint.py (estendido: casamento mecânico contra detect: do autonomy.yaml; evento autonomy.asked_instead_of_did); common/skills/plain-report/SKILL.md (faixa automática vira linha de informação; atestado na resposta → gravação); common/bin/defect.py (novo) + ~/.claude/cepa-telemetry/defects/<ts>-<slug>.yaml (um arquivo por defeito); common/commands/doctor.md e /common:metrics (listam fila de defeitos + autonomy.unlisted como candidatos a promoção); board-flow/commands/decide.md (passo 5b atestados, passo 6 via render_questions, passo 7 grava decisions+atestados, seção nova modo por sub-task); board-flow/commands/triage.md, drain.md, execute.md (consomem atestados e autonomy.yaml; perguntas só via render_questions); docs/needs-human-motivos.md (causa-harness → defect.py, referenciando o motivo já existente na linha 32)

**Piores casos:** (a) Epic perguntado cedo demais (WEGO-1406): quatro anéis, três mecânicos. 1º: ask-audit-gate.py bloqueia a própria AskUserQuestion que menciona chave de card sem dossiê validado — a pergunta prematura nem chega ao chat pelo caminho de tool. 2º: render_questions.py recusa o dossiê parcial nomeando o déficit (41 declaradas, 15 enumeradas) e cruza a lista contra o children.json bruto da consulta. 3º: se a pergunta escapar em prosa e o dono responder "pode concluir", a resposta não é executável — terminal-transition-gate.py consulta o Jira por REST com credencial própria e bloqueia a transição terminal com filha aberta, imprimindo as 22 na mensagem. 4º: o caminho legítimo é o modo por sub-task — fechar o Epic passa por despachar as 22 no lote, então "fechar cedo" perde o atalho. Evasão residual nomeada: pergunta em prosa sem chave de card escapa dos regex; ela continua não produzindo efeito (anel 3) e é medida pelo report-style-lint. (b) Irreversível classificado errado como reversível: a classificação não é do agente — é casamento de detect: contra o YAML versionado; erro de classificação é erro de arquivo, corrigível por diff. Independente da crença do executor, autonomy-gate.py bloqueia os primitivos destrutivos sem decisão registrada, e roda ELE MESMO a precondição (merge-base) do apagar-branch — reversibilidade verificada, não presumida. Ação nova não listada cai no default sempre-pergunta. O furo verdadeiro — Bash criativo que não casa nenhum detect (precedente bash-pathlock-bypass: sed/tee/python3 -c) — é admitido: cada falso-negativo vira patch + teste de regressão, como foi o `(?![&=])`, nunca vendido como cobertura total. Subagente gravando a própria aprovação em .claude/decisions/ é barrado pelo enforcement-guard; o lead gravando é tripwire auditável, não impossibilidade. (c) Atestado que a realidade contradiz: nenhum lado vence em silêncio — o attestation_ref obrigatório no render torna estruturalmente impossível ignorar o atestado, e o tipo `contradicao` obriga os dois lados (texto+data vs evidência arquivo:linha VERIFICADA por git show) numa pergunta fechada com recomendação. Card em conflito no meio de um drain vira Blocked com motivo, não executado sob nenhuma das hipóteses. Resolução grava `status: contestado` + entrada substituta datada; a velha nunca é apagada — a trilha "disse X em 08-03, corrigiu para Y em 08-15" fica auditável. `revisita` só por data (contrato do waivers.py linhas 71-79) reapresenta o atestado vencido como pergunta.

**Modos de falha:** Com franqueza: (1) O ask-audit-gate fecha o furo do tool-call, mas pergunta digitada em prosa no corpo do relatório final não passa por PreToolUse nenhum — essa evasão fica com o report-style-lint (avisa) + telemetria, e o dono ainda pode receber uma pergunta preguiçosa por esse caminho; o que é garantido é que ela não produz efeito irreversível. (2) render_questions agora verifica trecho-na-linha e cruza children.json, mas não verifica SEMÂNTICA: um trecho real citado como prova de um critério que ele não prova passa — o modelo de confiança é o mesmo dos artefatos de prova (independente do esquecimento, não da má-fé), e o proof gate a jusante segue sendo quem pega a mentira semântica. E o children.json vem de uma consulta que o agente mandou fazer: fabricar os dois arquivos consistentes é possível; o backstop de verdade é só o REST do terminal gate. (3) Três hooks novos = três fontes novas de falso-positivo (o precedente `>=` do bash-path-lock e o bounce-reason-gate barrando aprovação são reais); o dia do falso-positivo é ruim — a mitigação é que ele cai na fila de defeitos (Parte 5) em vez de no colo do dono, e cada um vira teste de regressão. O ask-audit-gate em particular pode bloquear uma pergunta legítima que apenas MENCIONA um verbo de build — os testes nascem com os falso-positivos históricos, mas o primeiro mês vai achar novos. (4) terminal-transition-gate depende da hierarquia do Jira (parent vs Epic Link variam por site) e de ~/.zsecrets: montado errado, bloqueia tudo (fail-fechado vira atrito) ou não vê filha (silencioso) — daí o teste contra o WEGO-1406 real antes de confiar. (5) Atestados apodrecem: vencimento só por data significa que um atestado errado suprime perguntas legítimas até a revisita — trade-off já aceito nos waivers; conflito com evidência de código sempre reabre, o que estreita a janela mas não a zera. (6) A jardinagem é perpétua: regexes de detect envelhecem, autonomy.yaml e attestations.yaml são dois arquivos vivos, e o dono cansado pode promover ação demais para a faixa automática — a promoção manual e versionada torna isso visível, não impossível. (7) defects/ pode virar cemitério se o dono não abrir o cepa; doctor listando pendências mitiga, não resolve. (8) Nada vale sem reinstalar — causa número um de "construído mas não valendo" nas memórias deste projeto.

**Plano de teste:** Unit (pytest, padrão da suíte em tests/): test_autonomy_gate.py — push/merge/reset --hard/worktree remove sem .claude/decisions/ → block; com decisão cobrindo remote+branch → pass; branch -D contida (fixture git com merge-base real, rodado pelo hook) → pass; não contida → block; comando inocente contendo "push" em string → pass (regressão anti-falso-positivo, lição do `>=` herdada de test_bash_path_lock_redir.py); YAML ausente/malformado → fail-fechado só para a lista mínima de irreversíveis hard-coded. test_ask_audit_gate.py — pergunta "rodo o build?" → block citando o id; pergunta com WEGO-#### sem dossiê validado → block dizendo o que falta; com dossiê validado (hash confere) → pass; pergunta sem chave nem verbo de faixa → pass (evasão documentada como known-gap no próprio teste); repo sem board-flow.yaml → pass (hook desarmado). test_terminal_transition_gate.py — epic com filha aberta sem dossiê → block com lista na mensagem; com dossiê+decisão → pass; sem filhas → pass; REST indisponível → block "não consegui verificar". test_render_questions.py — 41 declaradas/15 enumeradas → recusa nomeando o déficit; children[] divergente do children.json → recusa; critério sem verificado_em → recusa; trecho ausente na linha ±2 do `git show` (fixture com commit real) → recusa; template fechar com >1 linha → recusa; manter sem tipo implementacao|cobertura → recusa; item em escopo atestado sem attestation_ref → recusa; contradicao sem os dois lados → recusa. test_attestations.py — clone dos casos de test_waivers.py (_chave, malformado ignorado, vencimento por data) + contestado nunca casa como vigente + cadeia substituido-por preserva a entrada velha. test_report_style_lint.py ganha os casos: item numerado casando detect de faixa executa → aviso + evento. Integração de mesa: (i) replay WEGO-1406 com dossiê real das 41 filhas → lote por sub-task com 12 one-liners + 10 blocos de critérios; (ii) replay PlugSign: atestado 08-03 + fixture da triagem 08-04 → exatamente um item de contradição, zero descope silencioso; (iii) sessão sintética com as 20 interrupções classificadas → ~10 linhas de informação, ~4 arquivos em defects/, ~5 itens numerados. Aceitação em produção (após reinstalar): próxima triage/drain no WEGO — meta ≤6 consultas em ≤2 lotes, zero item numerado casando detect de faixa executa (medido pelo lint), zero tarefa de harness ao dono, e validação do terminal gate contra o WEGO-1406 real (parent vs Epic Link) antes de confiar no fail-fechado.

**Custo:** Construção ~2,5-3 dias, faseada pelo ganho: FASE 1 (meio dia) — autonomy.yaml com detect + edições em plain-report/decide/drain/triage + extensão do report-style-lint: absorve as ~10 mecânicas já por disciplina+lint. FASE 2 (1 dia) — ask-audit-gate.py + render_questions.py com verificação git-show e children.json + testes: o lado executa ganha bloqueio no ato (fecha os furos dos críticos) e a pergunta não-auditada morre; mata também a contradição PlugSign junto com attestations.py (~150 linhas, clone do waivers.py). FASE 3 (1 dia, a parte arriscada) — autonomy-gate.py e terminal-transition-gate.py com testes e validação contra o WEGO real (hierarquia parent/Epic Link + credenciais); defect.py é ~30 min; extensão do enforcement-guard ~1h. Total: 5 hooks/scripts novos ou estendidos, 2 configs novas, 5 comandos editados, + reinstalação obrigatória. Atrito residual que NÃO some, com todas as letras: as ~5 decisões genuínas continuam (eliminá-las seria defeito) — só chegam agrupadas, e a latência delas passa a ser o tamanho da rodada, não o instante do bloqueio; a pergunta do ramo manter-aberto é longa por construção; o dono mantém dois arquivos vivos (autonomy override e attestations) e responde às revisitas datadas; os três hooks novos vão gerar falso-positivos no primeiro mês, que caem na fila de defeitos deles em vez de no colo do dono, mas custam o dia em que acontecem; e a fila de defeitos espera o dono a cada visita ao cepa.

## Checagem final contra a barra

**Barra atingida:** SIM

Aprovado: todos os 7 critérios ≥ 7 (notas 9,9,9,9,9,8,9). Os anchors citados conferem no repo (decide.md passos 4-7, waivers.py linhas 42-79, plain-report SKILL, needs-human-motivos linha ~32, _telemetry.emit, enforcement-guard, classify_needs_human, BACKLOG 788-927 com os exemplos WEGO-1436/1437). A revisão fechou de fato os furos anteriores: os dois lados da faixa têm gate no ato (detect: no YAML + ask-audit-gate em AskUserQuestion), o dossiê é verificado contra o disco (git show, children.json cruzado), e o consumo de atestados é estrutural (attestation_ref). A conta fecha em ~5 perguntas numa rodada sem eliminar as genuínas. Gaps remanescentes são de implementação/verificação (spike do hook em AskUserQuestion, resgate dos artefatos de decisão em worktree, mapa completo de tools MCP), não de mecanismo.

**Gaps remanescentes (de implementação, não de mecanismo):**

- A viabilidade de PreToolUse em AskUserQuestion não foi provada: o design assume que o Claude Code dispara hook para essa tool no runtime atual. Se não disparar, o ask-audit-gate (a peça que fecha os furos 1 e 3) degrada para o report-style-lint. Merece um spike de 30 min antes da Fase 2 e um plano B declarado (ex.: mover a exigência de dossiê para dentro do render como único caminho de pergunta).
- Persistência dos artefatos de decisão em worktrees: .claude/decisions/ e .claude/decision-queue/ são arquivos ignorados sob .claude/ — exatamente a classe que some calada ao remover worktree (memória worktree-artifact-rescue, common 0.27.0). O design não diz se esses paths entram na lista de resgate do rescue; sem isso, a decisão registrada que o autonomy-gate exige pode evaporar entre sessões.
- Cobertura de detect para os dois conectores Jira está nos exemplos (createJiraIssue|jira_create_issue), mas o mapa completo tool-MCP → id precisa de auditoria na implementação (ex.: editJiraIssue/jira_update_issue não aparecem em faixa nenhuma — caem no default sempre-pergunta, o que pode reintroduzir atrito em edições triviais de descrição até a lista crescer via autonomy.unlisted).
- Evasões admitidas que permanecem por construção (não são defeito do design, mas do território): pergunta em prosa no relatório só é avisada; semântica do trecho-prova-o-critério segue confiança no agente com backstop no proof gate; Bash criativo fora dos regex (precedente sed/tee/python3 -c) segue jogo de gato e rato com testes de regressão.
- A regra parent vs Epic Link do terminal-transition-gate varia por site Jira; o design manda validar contra o WEGO-1406 real antes de confiar, mas o JQL canônico deveria vir do board-flow.yaml (config) em vez de hard-coded no hook — não especificado.