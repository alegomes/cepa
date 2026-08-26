# Substituir o MCP da Atlassian pela CLI `twg`?

Status: proposta de estratégia. Nada implementado.
Data: 2026-08-26. CLI avaliada: `twg` 1.2.5, autenticada em `sea-solutions.atlassian.net`.

## O que é cada coisa

- **MCP da Atlassian**: hoje o harness fala com o Jira por *ferramentas MCP* — funções que o
  modelo enxerga na lista de ferramentas, com nome e schema, e chama diretamente.
  O repo usa três servidores MCP diferentes para isso.
- **`twg`**: CLI oficial que a Atlassian acabou de lançar (Teamwork Graph). Roda no shell.
  O agente chamaria via `Bash`, não via ferramenta dedicada.
- **Schema de ferramenta**: o texto que descreve nome, parâmetros e tipos de uma ferramenta MCP.
  Ele entra no contexto do agente **toda vez** que o agente é invocado, mesmo que a ferramenta
  não seja usada.

## Ponto de partida: por que existem 45 ferramentas MCP num agente só

`board-flow/agents/atlassian-expert.md` amarra **45 ferramentas MCP**. Quebrando por prefixo:

| Prefixo | Ferramentas | Contexto que atende |
|---|---|---|
| `mcp__Atlassian__*` | 16 | rotina cloud `/schedule` (não atendida) |
| `mcp__claude_ai_Atlassian__*` | 15 | sessão local interativa |
| `mcp__mcp-atlassian__*` | 14 | headless local (cron/launchd) |

São **as mesmas ~15 operações, escritas três vezes**. A triplicação não é capricho: cada
contexto de execução autentica de um jeito diferente, e o agente carrega um tradutor
camelCase↔snake_case no próprio prompt para lidar com isso.

**F1 — o custo de contexto está no schema, não na resposta.**
Medição: o schema de `mcp__mcp-atlassian__jira_search` tem 1.912 bytes.
Conta: 45 ferramentas × 1.912 bytes = 86.040 bytes ≈ **21.500 tokens** por invocação do
`atlassian-expert`.
Ressalva honesta: 1.912 é **uma** amostra usada como média; as ferramentas OAuth são mais
enxutas, então o número real deve ficar abaixo disso. A ordem de grandeza — dezenas de milhares
de tokens por invocação, para usar 2 ou 3 operações — é o que importa, não o dígito.
Com `twg`, esse custo é **zero**: o agente já tem `Bash`.

**F2 — a resposta também é mais barata, mas por pouco.**
Mesma consulta JQL (`project = WEGO AND status = "To Do"`, 3 cards), medida:

| Caminho | Bytes no contexto |
|---|---|
| MCP (`jira_search`) | 2.645 |
| `twg ... -o json` | 1.204 |

Conta: 2.645 ÷ 1.204 = 2,2× a favor do `twg`.
O motivo estrutural pesa mais que o fator: o `twg` grava o payload completo (3.893 bytes) **em
arquivo** e imprime só uma visão compacta, com o caminho do arquivo. O MCP não tem essa
válvula — tudo que ele retorna entra no contexto. Em drain de 20 cards a diferença cresce.
O que o MCP mandou a mais e ninguém usa: `avatar_url` do Gravatar, `account_id` de reporter,
`color` do status.

**F3 — a CLI tem escapatória para qualquer buraco de cobertura.**
`twg api` faz REST e GraphQL crus com as credenciais salvas
(`twg api jira:/rest/api/3/myself`). Não existe operação Jira que o MCP alcance e a CLI não —
no limite, cai no REST. O argumento "o MCP tem uma ferramenta que a CLI não tem" não se sustenta.

**F4 — a CLI resolve o problema de auth headless que criou a triplicação.**
`twg doctor` mostra um agendador `launchd` rodando a cada 12 minutos que mantém o token OAuth
fresco (`Last auth: fresh`). Existe também um modo de token estático
(`auth_api.conf`, ainda não configurado). Ou seja: numa execução headless **na máquina do
usuário**, o `twg` já acorda autenticado, sem os malabarismos de prefixo.

**F5 — latência é pior, mas amortiza em lote.**
Medido: `twg jira workitem get` de 1 card = 1,79 / 1,80 / 1,84 s (3 execuções).
`twg jira workitem bulk-get` de 3 cards = 1,15 s no total.
O custo é de processo, não por card. Chamada avulsa em loop é o padrão ruim; `bulk-get` e
`--batch-concurrency` são o padrão bom.

**F6 — comentário em markdown é nativo.**
`twg jira workitem comment create` aceita `markdown` direto. Hoje o `atlassian-expert` carrega
regra sobre ADF vs Markdown porque os dois servidores MCP divergem nisso.

## Os dois riscos que decidem a questão

**R1 — a rotina cloud `/schedule` não tem shell.**
O prefixo `mcp__Atlassian__*` (16 das 45 ferramentas) existe para as rotinas agendadas que rodam
na infra da claude.ai, não nesta máquina. Lá não há `twg` instalado nem
`~/.config/twg/auth.conf`. `docs/loop-engineering.md` registra esse caminho como verificado em
2026-06-30. **Substituição total mataria a frota de rotinas autônomas.** O `twg` cobre o local
interativo e o headless local; não cobre o cloud.

**R2 — mover escrita de Jira para `Bash` alarga a superfície de enforcement.**
Hoje o gate é o campo `tools:` do frontmatter: **1 agente entre 50** consegue mutar o Jira.
Com `twg`, o gate vira inspeção de string de comando bash — e **18 dos 50 agentes têm `Bash`**.
Sem um hook novo, qualquer um deles transiciona card, comenta e cria issue.
Este repo já pagou exatamente essa conta: a memória `bash-pathlock-bypass` registra agentes
driblando trava de `Write` via `sed`/`cat >`/`tee`, e a correção foi um hook dedicado
(`bash-path-lock`) em cinco topologias. O mesmo padrão se repetiria aqui.

**R3 — o contrato de saída se move sozinho.**
O mesmo `launchd` de 12 minutos que mantém o token fresco também checa atualização
(`Last update check`). Uma CLI que se autoatualiza é contrato instável para agente que faz
parsing. O `-o json` reduz o risco, não elimina.

## Caminhos considerados

**O1 — Substituição total: arrancar o MCP, só `twg`.**
Ganho: mata a triplicação, zera 21k tokens de schema, elimina o tradutor camelCase↔snake_case.
Custo: quebra a rotina cloud (R1) e exige hook novo de enforcement (R2) antes de ser seguro.
Veredito: **rejeitado enquanto a rotina cloud importar.** R1 é bloqueio de fato, não de opinião.

**O2 — Status quo: ignorar a CLI.**
Ganho: zero trabalho, zero risco novo.
Custo: mantém 45 schemas, o tradutor de três vocabulários e a fragilidade de auth headless.
Veredito: defensável se a fila de trabalho tiver coisa mais valiosa. Não é errado, é caro.

**O3 — `twg` canônico em execução local, MCP mantido só para a rotina cloud.** *(recomendado)*
O `atlassian-expert` passa a chamar `twg` por `Bash` como caminho padrão e mantém apenas o
bloco `mcp__Atlassian__*` (16 ferramentas) para quando estiver rodando em rotina agendada.
Ganho: 45 → 16 ferramentas amarradas (redução de 64%); some o tradutor snake_case; comentário
em markdown nativo; auth headless local deixa de ser caso especial.
Custo: dois caminhos em vez de um, e exige o hook de R2.
Veredito: captura a maior parte do ganho sem tocar no que R1 protege.

**O4 — `twg` só para o que o MCP não faz.**
A CLI traz superfície que o MCP não tem: `twg` cobre Confluence, Bitbucket, Compass, JSM, goals,
e busca agêntica (Rovo) sobre conectores. Entra como capacidade **nova**, e a escrita no Jira
não se mexe.
Ganho: risco quase nulo, nenhuma regressão possível.
Custo: não colhe nada da economia de contexto — a triplicação continua de pé.
Veredito: complementar a O3, não alternativa. Pode rodar antes, como primeiro contato.

## Recomendação

**O3, precedida do hook de R2.** A ordem importa: o hook que restringe `twg` mutante ao
`atlassian-expert` precisa existir **antes** de qualquer agente com `Bash` conhecer o comando.
Inverter a ordem repete o erro que a memória `bash-pathlock-bypass` já documentou.

Sequência proposta:
1. Hook `bash-twg-lock`: bloqueia subcomando mutante do `twg` (`create`, `update`,
   `transition`, `comment create`, `delete`, `archive`) para todo agente que não seja o
   `atlassian-expert`. Leitura fica liberada.
2. `atlassian-expert` ganha o caminho `twg` como default local e perde os 29 nomes MCP dos dois
   prefixos locais.
3. Uma rotina cloud `/schedule` roda de ponta a ponta para provar que R1 continua atendido.
4. Só então O4, ampliando para Confluence/Bitbucket.

---

# Revisão pós-painel de advisors (7 lentes, 2026-08-26)

O painel derrubou parte do que está acima. As correções abaixo **substituem** a recomendação
original. O texto anterior fica como registro do raciocínio, não como proposta viva.

## Convergências (achado independente de 2+ lentes)

**C1 — O hook do passo 1 é teatro. (contrarian, operador-sre, fundamentalista,
custo-de-manutencao, outsider — 5 de 7 lentes, isoladas.)**
A denylist de verbos (`create`, `update`, `transition`…) não cobre `twg api -X POST --input
payload.json`, que cria card sem nenhum desses verbos na linha de comando — e com `--input` o
payload sequer aparece na string inspecionada. Verificado no `--help` da própria CLI. A mesma
escapatória celebrada em F3 como prova de cobertura é a que fura o gate. Polaridade errada:
o desenho defensável é allowlist (só leitura conhecida passa), não denylist.

**C2 — Nenhuma opção "podar os 45 sem trocar de tecnologia". (contrarian, custo-de-manutencao,
executor, outsider.)**
O documento compara `twg` contra "não fazer nada" e nunca contra a alternativa mais barata:
escolher UM servidor MCP por contexto e cortar os 14 nomes `snake_case` (os mais gordos, por
F1). Captura boa parte da economia de bytes, mata o tradutor camelCase↔snake_case, não exige
hook novo, não mexe em R2 e não introduz R3. Vira **O0** abaixo.

**C3 — A economia está reportada em unidade trocada. (contrarian, custo-de-manutencao,
outsider.)**
"45 → 16 = 64%" conta ferramentas; a tese (F1) é bytes. As 29 que saem incluem as 15 OAuth que
o próprio F1 admite serem as enxutas; as 16 que ficam são todas OAuth. O ganho em tokens é
desconhecido e certamente bem abaixo de 64% dos 21.500. Medir os 45 schemas reais custa uma
execução e ninguém fez.

**C4 — R3 (a CLI que se autoatualiza) é diagnosticado e sai do plano. (contrarian,
custo-de-manutencao, executor, operador-sre.)**
Nenhum dos 4 passos endereça a versão. Pior: o mesmo `launchd` de 12 minutos pode trocar a
versão **entre dois cards** do mesmo `/board-flow:drain`, sem sinal no log.

**C5 — O agente não sabe em que contexto está rodando. (contrarian, executor, operador-sre,
custo-de-manutencao.)**
O3 troca o tradutor de três prefixos por uma bifurcação entre dois mecanismos (Bash vs. MCP)
sem detector proposto. No cloud, o `Bash` retorna `command not found` — que um agente com
instrução de persistência contorna em vez de tratar como contexto errado. Falha silenciosa
justamente no caminho desatendido.

## O achado que reorienta tudo — e que nenhuma versão anterior tinha

**F7 — quatro gates de negócio morrem calados com `twg`.** *(fundamentalista; verificado.)*
Estes hooks casam pelo **nome da ferramenta MCP** e liberam por default quando o nome não bate:

| Hook | Linha | Condição |
|---|---|---|
| `common/hooks/merge-truth-gate.py` | 122-123 | `if "transitionJiraIssue" not in tool_name and "jira_transition_issue" not in tool_name: sys.exit(0)` |
| `common/hooks/acceptance-gate.py` | 146-147 | idem |
| `common/hooks/summary-nulls-gate.py` | 171-172 | idem, para `addCommentToJiraIssue` / `jira_add_comment` |
| `common/hooks/bounce-reason-gate.py` | 151-152 | idem |

`sys.exit(0)` é **liberar**. Uma chamada `twg` chega como `Bash`, não casa com nenhum nome, e
os quatro gates passam sem dizer nada. Ou seja: migrar para `twg` não "alarga a superfície de
enforcement" (R2, que era o risco nomeado) — ele **desliga em silêncio** a verificação de
critérios de aceite, de verdade-de-merge, de sumário completo e de motivo de bounce. Este é o
custo real da migração, e a versão anterior deste documento não o via.

## O risco que já é presente, não futuro

**R2 estava mal datado.** *(contrarian, executor, expansionista.)*
`twg` já está instalado (`/Users/alegomes/.local/bin/twg`), autenticado
(`~/.config/twg/auth.conf`), e a Atlassian instalou **15 skills `twg-*` em
`~/.claude/skills/`**, visíveis a qualquer sessão. Os 18 agentes com `Bash` **já podem** mutar o
Jira hoje, sem nenhuma mudança neste repo, e já contornando os quatro gates de F7.

Consequências:
- O veredito de O2 ("zero risco novo") está **errado**. O status quo não é neutro; é exposição
  aberta e não observada.
- A regra "hook ANTES de qualquer agente conhecer o comando" **já foi perdida**. O hook deixa de
  ser pré-condição de O3 e vira conserto de exposição existente — que vale mesmo escolhendo O0
  ou O2.

## DISCORDÂNCIAS NOMEADAS

**D1 — expansionista vs. custo-de-manutencao: o tamanho certo da mudança.**
O expansionista diz que O3 é *pequeno demais* — o prêmio não é 45→16 ferramentas, é board
legível por 50 agentes em vez de 1, mais Confluence/Bitbucket/Rovo entrando no harness.
O custo-de-manutencao diz que O3 já é *aumento líquido* de superfície: dois stacks Jira
permanentes, um hook novo copiado por topologia, arquivos de payload sem dono.
**O que decide:** se leitura de board por qualquer agente é capacidade desejada ou risco. Elas
não discordam de fatos, discordam de o que o harness deve ser. **Minha posição:** o
custo-de-manutencao vence *nesta rodada*, porque F7 mostra que o enforcement atual pressupõe um
único escritor identificável por nome de ferramenta; abrir leitura para 50 agentes antes de
consertar isso é construir sobre gate furado. A tese do expansionista é boa, mas é a rodada
seguinte.

**D2 — contrarian vs. fundamentalista: o que R1 é.**
O contrarian trata R1 (rotina cloud) como bloqueio de fato. O fundamentalista aponta que R1 é
afirmado a partir de um doc de dois meses atrás (`loop-engineering.md`, verificado em
2026-06-30), não de verificação em execução — o que viola a própria regra do repo de conferir
antes de afirmar. O outsider reforça: a tabela do documento marca esse contexto como
"(não atendida)" enquanto R1 o trata como frota viva a proteger — contradição interna.
**O que decide:** rodar uma rotina cloud e ver. Não fiz isso. **Enquanto não rodar, R1 é
hipótese, e a rejeição de O1 apoiada nele é provisória.**

**D3 — outsider vs. todas as demais: o documento é legível?**
As outras seis lentes discutiram o mérito; o outsider diz que um leitor de fora não consegue
sequer reconstruir a decisão — falta enunciar o problema que a motiva, faltam denominadores
(21.500 tokens sobre qual janela?), e referências como `bash-pathlock-bypass` carregam
argumentos centrais sendo ilegíveis fora da equipe.
**O que decide:** o público. Se o documento é nota interna, o outsider perde; se é base de
decisão que outra pessoa vai auditar, ele vence. **Minha posição:** ele vence — F1 sem
denominador foi exatamente o número que C3 mostrou estar trocado de unidade. Opacidade
escondeu um erro real.

## Caminhos revisados

**O0 — Podar os 45 sem trocar de tecnologia.** *(novo, trazido pelo painel)*
Escolher um servidor MCP por contexto, cortar os 14 nomes `snake_case`, manter o mecanismo.
Ganho: parte grande dos bytes, morte do tradutor, zero risco novo, gates de F7 intactos.
Custo: quase nenhum. Não colhe Confluence/Bitbucket/Rovo.

**O1 — Substituição total.** Rejeitado, mas por motivo trocado: o bloqueio decisivo é **F7**
(quatro gates desligados em silêncio), não R1 — que D2 mostrou ser hipótese não verificada.

**O2 — Status quo.** Veredito corrigido: **não é "zero risco novo"**. É exposição já aberta
(R2 presente) somada aos gates de F7 já contornáveis por qualquer agente com `Bash`.

**O3 — `twg` local + MCP no cloud.** Continua atraente, mas o pré-requisito mudou: não é o hook
de denylist (furado por C1), é reescrever os quatro gates de F7 para casarem por **efeito**
(mutação de Jira, qualquer mecanismo) em vez de por nome de ferramenta.

**O4 — `twg` só para capacidade nova (Confluence/Bitbucket/Rovo).** Promovido: é o único
caminho que não toca escrita de Jira e portanto não esbarra em F7. O expansionista tem razão
que estava na ordem errada.

## Recomendação revisada

**Ordem: consertar F7 → O0 → reavaliar O3 com números reais.**

1. **Fechar F7 primeiro, independente da decisão sobre `twg`.** Os quatro gates precisam casar
   por efeito, não por nome de ferramenta, e falhar **fechado** diante de mecanismo
   desconhecido. Isso vale mesmo escolhendo O2 — a exposição já existe hoje.
2. **O0** — poda barata dos 14 nomes `snake_case`, com os bytes reais dos 45 schemas medidos
   antes e depois, para que a economia pare de ser regra de três sobre uma amostra (C3).
3. **Verificar R1 rodando uma rotina cloud**, em vez de citar doc de dois meses (D2).
4. **O4** como primeiro contato real com a CLI, onde não há gate para furar.
5. **Reavaliar O3** só com (1) fechado e (2) medido — e com detector de contexto especificado
   (C5) e versão da CLI fixada (C4).

O que **não** fazer: o hook `bash-twg-lock` como desenhado no passo 1 original. Denylist de
verbos contra uma CLI com `twg api -X POST` é enforcement que parece existir e não existe.

---

# Execução (2026-08-26) — o que saiu do papel

## Item 1 — os quatro gates passaram a reconhecer mutação por efeito

Novo módulo `common/hooks/_jiramut.py`, no mesmo padrão do `_shellscan.py` (motor
compartilhado, importado em vez de copiado). Ele recebe o payload do hook e responde se a
chamada **muta o Jira**, por qual mecanismo, devolvendo os campos já normalizados para os nomes
que os gates sempre usaram — então a lógica de negócio de cada gate ficou intacta.

Os quatro gates trocaram

```python
if "transitionJiraIssue" not in tool_name and "jira_transition_issue" not in tool_name:
    sys.exit(0)                 # liberava
```

por uma classificação por efeito que também lê linha de comando `Bash`, e **barra** quando
reconhece mutação que não consegue auditar.

**Reconhecimento de leitura é lista branca, não lista negra.** Foi a correção central: a
denylist de verbos que eu tinha proposto é furada por `twg api jira:/rest/api/3/issue -X POST
--input p.json`, que cria card sem conter nenhum verbo da lista e com o corpo escondido num
arquivo. Agora, o que não está declarado como leitura conhecida é tratado como escrita, e
escrita ilegível é barrada.

**Prova adversarial — 25 casos, 25 passaram** (`tests/test_jiramut_deteccao_por_efeito.py`),
incluindo os bypasses que o painel descreveu:

| Caso | Esperado | Resultado |
|---|---|---|
| `twg api ... -X POST --input p.json` | barra | barra |
| `twg api graphql -X POST` | barra | barra |
| `twg api jira:/rest/api/3/myself` (GET) | ignora | ignora |
| `echo oi; twg jira workitem create ...` | barra | barra |
| `/Users/…/bin/twg jira workitem delete …` | barra | barra |
| `TWG_AGENT_DEFAULTS=1 twg jira workitem update …` | barra | barra |
| `twg jira workitem bulk-transition …` (verbo novo) | barra | barra |
| `twg jira workitem transition --id X` (sem `--transition-id`) | ignora (é descoberta) | ignora |
| `twg jira workitem query 'sp >= 3'` | ignora | ignora |
| ferramenta MCP (regressão) | passa ao gate | passa ao gate |

O último caso do `>=` está ali de propósito: é o falso-positivo que já custou dois meses a este
repo (`bash-pathlock-ge-falsematch`), e o motor compartilhado já o trata.

Suíte completa do repo: **55/55**.

## Item 2 — os schemas, medidos em vez de estimados

O painel tinha razão em C3. Interroguei o `tools/list` do próprio servidor `mcp-atlassian`
(63 ferramentas expostas) e medi as 14 que este repo amarra, uma a uma:

| Ferramenta | Bytes | | Ferramenta | Bytes |
|---|---:|---|---|---:|
| `jira_update_issue` | 2.189 | | `jira_create_issue_link` | 1.225 |
| `jira_get_issue` | 2.115 | | `jira_transition_issue` | 1.195 |
| `jira_search` | 2.037 | | `jira_add_comment` | 1.132 |
| `jira_create_issue` | 1.828 | | `jira_search_fields` | 511 |
| `jira_get_field_options` | 1.506 | | `jira_link_to_epic` | 460 |
| | | | `jira_get_user_profile` | 366 |
| | | | `jira_get_transitions` | 306 |
| | | | `jira_get_all_projects` | 268 |
| | | | `jira_get_link_types` | 255 |
| **Soma** | | | | **15.393** |

Conta: 15.393 bytes ÷ 4 ≈ **3.848 tokens** economizados por invocação do `atlassian-expert`.

**Minha estimativa original estava inflada em 74%.** Usei 1.912 bytes como média; a média real
é 1.099. Eu tinha escolhido como amostra justamente a terceira maior ferramenta do conjunto.
O número de F1 (21.500 tokens para as 45) deve ser lido como teto folgado, não como medição.
As 31 ferramentas OAuth restantes **não foram medidas** — vivem no servidor da claude.ai, fora
do alcance de um `tools/list` local — e nenhuma extrapolação delas entra aqui.

**O corte foi aplicado**: `atlassian-expert` foi de 45 para 31 ferramentas MCP (mais 3 nativas).
Sumiram junto a tabela de tradução camelCase↔snake_case e a regra de bolso de três prefixos —
o documento do agente agora descreve dois prefixos com vocabulário único.

**Pré-condição que verifiquei antes de cortar:** não existe job `launchd` nem `crontab` rodando
`claude` contra o Jira nesta máquina. O caminho headless local foi validado uma vez e nunca
promovido, então o corte não derrubou nada em uso. Isso está registrado no próprio documento do
agente, junto com as duas formas de reativá-lo — porque afirmar que ele existe sem conferir é
exatamente o hábito que este repo já decidiu não repetir.
