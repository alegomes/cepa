# Especificação: reforma de nomes dos comandos do cepa

**Status:** ready-to-build
**Aberta em:** 2026-11-24            **Fechada em:** 2026-11-24
**Fontes lidas:** common/bin/cepa (cabeçalho e show_help), ajuda (`--help`) de cada `common/bin/cepa-*`, frontmatter dos 71 arquivos `*/commands/*.md`, docs/commands.md (linhas 1-60), docs/cepa-cli.md (títulos), docs/spec/teclas-em-ingles.md, board-flow/bin/cepa-plan (cabeçalho), BACKLOG.md (linhas 2380-2386)

## Como chegamos aqui
"Revise todos os comandos e subcomandos do cepa e proponha melhoras que favoreçam a facilidade de entendimento, simplicidade, consistência e coerência do sistema. Avalie tanto os comandos de barra quando a CLI." (dono, 2026-11-23). Em 2026-11-24 o dono aprovou as oito propostas da revisão e acrescentou: "o nome do comando `cepa until` também me incomoda. Não faz mais sentido `cepa build` ou `cepa run`?", "atualize todos os menus de ajuda" e "transforme essa revisão em um comando para estarmos sempre refazendo-a".

## Problema
A mesma palavra nomeia coisas diferentes e a mesma coisa tem nomes diferentes conforme a porta de entrada. "plan" nomeia a CLI da fila (`cepa plan`), os passos da intenção (`cepa --plan`), um apelido antigo (`/common:plan`), o nome da fila (`/common:next --plan`) e o lote (`/common:drain-plan`). Flags e variáveis de ambiente misturam português e inglês, a CLI tem três formas de dizer uma ação, e a ajuda mostra apelidos antigos e comandos congelados ao lado dos que valem.

## Escopo
### Entra
- P1: `cepa plan` vira `cepa queue`; `/common:drain-plan` vira `/common:queue-run`; `--plan NAME` do `/common:next` vira `--queue NAME`. "plan" fica só para os passos da intenção da sessão.
- P2: saem os apelidos `/common:fila`, `/common:modos`, `/common:plan`, `cepa-intencao` e `cepa-modos`.
- P3: flags em inglês nos comandos de barra, com a flag antiga ainda aceita: `--continuar`, `--fechar`, `--lista` (`/common:spec`), `--lentes` e os valores de `--area` (`/common:advisors`), `--angulos` (`/common:gauntlet`), `--na-branch` (`/common:drain-plan`), `--fila` (`/common:until-review`), `--pendencia` e `--resolve-pendencia` (`cepa plan finish`), valores `mantida`, `vetada`, `refinada` (`cepa plan verdict`).
- P4: variáveis de ambiente todas com prefixo `CEPA_` e nome em inglês, com a antiga ainda lida (`CEPA_MODO`, `CEPA_ENCADEAR`, `CEPA_PERMISSOES`, `CEPA_PROMPT_MODO`, `CEPA_COR`, `CEPA_UNTIL_*` em português, `CLAUDE_WT_*`, `CCW_*`).
- P5: `cepa intent` e `cepa modes` passam a usar subcomandos; `cepa until-digest` vira `cepa run digest`.
- Q1: `cepa until` vira `cepa run`; `/common:until-review` vira `/common:run-review`.
- P6: a ajuda do `cepa plan` abre com os subcomandos do dono e põe os demais num bloco "usados pelos comandos"; `cepa plan queue` vira `batch`.
- P7: `/maestro:*`, `cepa dor` e `cepa hotspots` aparecem num bloco "frozen" no fim da ajuda.
- P8: o argumento se chama `<slice>` em toda a família `/common:worktree-*`; `/common:worktree-name` vira `/common:worktree-rename`.
- Q7, Q8 e Q10: os 12 plugins e suas pastas mudam de nome. `common` vira `cepa`, `board-flow` vira `cepa-board`, `build-hex` vira `cepa-hex`, `build-solo` vira `cepa-solo`, `build-team` vira `cepa-team`, `discovery` vira `cepa-discovery`, `docs` (pasta `docs-topology/`) vira `cepa-docs`, `design` vira `cepa-design`, `marketing` vira `cepa-marketing`, `review-gate` vira `cepa-review`, `maestro` vira `cepa-maestro`, `compass` vira `cepa-compass`. Comandos, skills e agentes passam a ser chamados pelo prefixo novo (`/cepa:queue`, `cepa:plain-report`, `cepa-board:atlassian-expert`).
- Q9: a instalação troca o nome antigo pelo novo nas configurações de cada repo.
- Item 10 do dono: todos os menus de ajuda atualizados com os nomes novos (ajuda da CLI, `description` e `argument-hint` dos comandos de barra, menus de modo, docs/commands.md e docs/cepa-cli.md).

### Não entra
- Os fluxos `plan-build-validate` e `reproduce-fix-verify`: longos, mas iguais nas três topologias.
- `configure` e `capture`: o prefixo do plugin já separa.
- Apagar o Maestro, `cepa dor` ou `cepa hotspots`: só mudam de lugar na ajuda.

## Estado e migração
Nenhum arquivo gravado muda de nome nem de formato: a pasta `.claude/queues/<fila>/until/`, a branch `until/<run>`, os registros `.jsonl`, as filas e as especificações continuam como estão (Q4). Muda só o que se digita e o que a ajuda mostra. Variáveis de ambiente e flags antigas continuam lidas (P3, P4). O nome antigo de um comando renomeado é recusado com uma linha que diz o nome novo (Q3).

Duas coisas mudam em disco por causa dos prefixos (Q7 a Q10). No repo do Cepa, as 12 pastas de plugin mudam de nome com `git mv`, preservando o histórico. Em cada repo que usa o Cepa, as chaves `<nome antigo>@cepa` de `enabledPlugins` nas configurações do Claude Code são trocadas pelas novas por `bin/install.sh` e por `cepa doctor --fix`, com uma cópia do arquivo guardada antes. Os arquivos de configuração `board-flow.yaml` e `review-gate.yaml` e o conteúdo de `.claude/topology` continuam como estão.

## Critérios de sucesso

### CS-1: `cepa queue` faz o que `cepa plan` fazia, e `cepa plan` é recusado com o nome novo
**Surface:** cli
**Red test:** num repo temporário com uma fila gravada, `cepa queue status` e `cepa-queue status` imprimem a fila e saem com 0; `cepa plan status` sai com 2, imprime uma linha contendo "plan is now queue" e não imprime a fila; `cepa help` lista `queue` e não lista `plan`; `board-flow/bin/cepa-queue status` chega ao mesmo script. Hoje `cepa queue` não existe.

### CS-2: `cepa run` faz o que `cepa until` fazia, e `cepa until` é recusado com o nome novo
**Surface:** cli
**Red test:** `cepa run <fila> --for 1h --dry-run` imprime o plano da run, cita `/common:queue-run <fila> --max 1` como o comando de cada item e sai com 0; `cepa run digest <run>.jsonl` imprime o resumo que `cepa until-digest` imprime hoje; `cepa until <fila> --for 1h --dry-run` sai com 2 com uma linha contendo "until is now run"; `cepa until-digest x` sai com 2 com "until-digest is now run digest". A pasta da run continua sendo `.claude/queues/<fila>/until/` e a branch `until/<run>`.

### CS-3: os comandos de barra renomeados existem com o nome novo e os antigos não existem
**Surface:** application
**Red test:** um teste lista `common/commands/` e encontra `queue-run.md`, `run-review.md` e `worktree-rename.md`, e não encontra `drain-plan.md`, `until-review.md`, `worktree-name.md`, `fila.md`, `modos.md` nem `plan.md`. Hoje é o contrário.

### CS-4: os apelidos antigos da CLI saem e a recusa diz o nome novo
**Surface:** cli
**Red test:** `cepa intencao` sai com 2 com "intencao is now intent" e `cepa modos` sai com 2 com "modos is now modes"; os arquivos `common/bin/cepa-intencao` e `common/bin/cepa-modos` não existem; a saída de `cepa help` não contém "Old subcommand names". Hoje os dois rodam o comando novo.

### CS-5: as flags dos comandos de barra e os valores de veredito aparecem em inglês, e os antigos continuam aceitos
**Surface:** cli
**Red test:** `cepa modes menu discovery` imprime `/common:spec --continue <slug>` e não imprime `--continuar`; o `argument-hint` de `spec.md`, `advisors.md`, `gauntlet.md`, `queue-run.md` e `run-review.md` contém `--continue`, `--close`, `--list`, `--lenses`, `--angles`, `--on-branch` e `--queue` e nenhuma das formas em português; `cepa queue verdict <arquivo> 1 kept` grava o mesmo marcador que `mantida` grava hoje, e `mantida` continua aceito; `cepa queue finish ... --open-point "x"` grava o mesmo que `--pendencia "x"`, que continua aceito. Depois do CS-1.

### CS-6: toda variável de ambiente tem prefixo `CEPA_` e nome em inglês, e a antiga continua lida
**Surface:** cli
**Red test:** um teste varre `common/bin/` e `common/hooks/` e falha se achar uma variável lida que não começa com `CEPA_` ou que está na tabela de nomes antigos, fora da função que lê a antiga como reserva; `CEPA_MODE=off cepa --help` e `CEPA_MODO=off cepa --help` saem com 0, e a seção "environment" da ajuda cita `CEPA_MODE=off`, `CEPA_CHAIN=off` e `CEPA_PERMISSIONS=classifier` e nenhuma das formas antigas; com a nova e a antiga definidas com valores diferentes, vale a nova. Hoje a varredura acha `CEPA_MODO`, `CLAUDE_WT_CLAIM` e `CCW_SEED`, entre outras.

### CS-7: `cepa intent` e `cepa modes` dizem a ação por subcomando
**Surface:** cli
**Red test:** `cepa intent step 3` move o cursor para o passo 3; `cepa intent write --help` imprime a ajuda só do `write`; `cepa modes exit`, `cepa modes menu discovery` e `cepa modes purposes` imprimem o que `--exit`, `--menu discovery` e `--purposes` imprimem hoje; `cepa intent --step 3` e `cepa modes --exit` continuam aceitos. Hoje `cepa intent step 3` é erro de uso.

### CS-8: a ajuda do `cepa queue` abre com os subcomandos do dono, e `queue` vira `batch`
**Surface:** cli
**Red test:** em `cepa queue --help`, um bloco "for you" com `status`, `show`, `ready`, `waiting`, `epics`, `answer` e `add` aparece antes de um bloco "used by the commands" com os demais; `cepa queue batch <fila> --max 3` imprime o que `cepa plan queue <fila> --max 3` imprime hoje; `cepa queue queue <fila>` sai com 2 com "queue is now batch". Depois do CS-1.

### CS-9: o que está congelado aparece num bloco "frozen" no fim da ajuda
**Surface:** cli
**Red test:** em `cepa help`, `dor` e `hotspots` aparecem depois de uma linha "frozen" e depois de todos os outros subcomandos; em docs/commands.md e docs/cepa-cli.md, os comandos `/maestro:*`, `cepa dor` e `cepa hotspots` estão numa seção final "Frozen". Hoje estão em ordem alfabética junto dos demais.

### CS-10: a família worktree usa `<slice>` em todos os comandos
**Surface:** application
**Red test:** um teste lê o `argument-hint` de `worktree-start.md`, `worktree-merge.md`, `worktree-discard.md`, `worktree-rename.md` e `worktree-label.md` e falha se algum citar `<name>`, `<new-name>` ou `<old-name>` no lugar de `<slice>`, `<new-slice>` e `<old-slice>`. Hoje `worktree-discard.md` e `worktree-name.md` usam `<name>`.

### CS-12: os 12 plugins e suas pastas têm o nome novo
**Surface:** application
**Red test:** um teste lê `.claude-plugin/marketplace.json` e o `plugin.json` de cada pasta de plugin e falha se os nomes declarados não forem exatamente `cepa`, `cepa-board`, `cepa-hex`, `cepa-solo`, `cepa-team`, `cepa-discovery`, `cepa-docs`, `cepa-design`, `cepa-marketing`, `cepa-review`, `cepa-maestro` e `cepa-compass`, se alguma pasta tiver nome diferente do plugin que contém, ou se existir uma pasta `common/`, `board-flow/`, `build-hex/`, `build-solo/`, `build-team/`, `discovery/`, `docs-topology/`, `design/`, `marketing/`, `review-gate/`, `maestro/` ou `compass/` na raiz. A suíte inteira passa com os scripts em `cepa/bin/`. Depois do CS-1, CS-2, CS-3, CS-4, CS-5, CS-6, CS-7, CS-8, CS-9 e CS-10.

### CS-13: toda referência a comando, skill ou agente usa o prefixo novo e aponta para algo que existe
**Surface:** cli
**Red test:** `cepa modes menu discovery` imprime `/cepa:spec --continue <slug>` e `/cepa-discovery:capture`; um teste extrai toda referência `<prefixo>:<nome>` dos arquivos vivos (`*/commands/*.md`, `*/skills/**/SKILL.md`, `*/agents/*.md`, `*/hooks/*.py`, README.md, docs/commands.md, docs/cepa-cli.md) e falha se o prefixo não for um dos 12 nomes novos ou se não existir o arquivo de comando, skill ou agente correspondente. Hoje as referências usam `common:`, `board-flow:` e os demais nomes antigos. Depois do CS-12.

### CS-14: a instalação troca o nome antigo dos plugins nas configurações do repo
**Surface:** cli
**Red test:** num repo de teste cujas configurações do Claude Code habilitam `common@cepa` e `board-flow@cepa`, `cepa doctor` aponta as duas chaves como correção mecânica e não altera o arquivo; `cepa doctor --fix` deixa `cepa@cepa` e `cepa-board@cepa` habilitados, remove as chaves antigas e guarda uma cópia do arquivo anterior; `bin/install.sh` no mesmo repo de teste chega ao mesmo resultado; rodar de novo não muda nada. Depois do CS-12.

### CS-15: `cepa doctor` avisa quando um arquivo de instruções do dono cita um prefixo antigo
**Surface:** cli
**Red test:** com um `CLAUDE.md` de teste (o global e o do repo) contendo "plugin `common`" e `common:plain-report`, `cepa doctor` lista o arquivo e a linha de cada menção no bloco do que precisa do dono, com o nome novo ao lado, e não edita o arquivo; sem menção, não lista nada. Depois do CS-12.

### CS-11: nenhum menu de ajuda nem documento vivo cita um nome antigo
**Surface:** cli
**Red test:** um teste com a tabela de nomes antigos (comandos, subcomandos, flags, valores, variáveis e prefixos de plugin desta especificação) roda `--help` em cada `cepa <subcomando>` e em cada sub-subcomando, roda `cepa modes menu <modo>` para cada modo, e lê `*/commands/*.md`, `*/skills/**/SKILL.md`, `*/agents/*.md`, `common/hooks/*.py`, README.md, docs/commands.md e docs/cepa-cli.md; falha em qualquer menção fora das linhas que declaram a compatibilidade. `tests/test_commands_catalog.py` passa com os nomes novos. Depois do CS-1, CS-2, CS-3, CS-4, CS-5, CS-6, CS-7, CS-8, CS-9, CS-10, CS-12, CS-13, CS-14 e CS-15.

## Perguntas em aberto
- [x] Q-P1: renomear `cepa plan` para `cepa queue` e `/common:drain-plan` para `/common:queue-run`? — sim (dono, 2026-11-24)
- [x] Q-P2: remover os 5 apelidos antigos? — sim (dono, 2026-11-24)
- [x] Q-P3: flags dos comandos de barra em inglês, aceitando as antigas? — sim (dono, 2026-11-24)
- [x] Q-P4: variáveis de ambiente em `CEPA_` em inglês, lendo as antigas? — sim (dono, 2026-11-24)
- [x] Q-P5: `intent` e `modes` com subcomandos e `until-digest` dentro do comando do lote? — sim (dono, 2026-11-24)
- [x] Q-P6: ajuda do `cepa plan` em dois blocos? — sim (dono, 2026-11-24)
- [x] Q-P7: Maestro, `dor` e `hotspots` num bloco "frozen" da ajuda? — sim (dono, 2026-11-24)
- [x] Q-P8: `<slice>` em toda a família worktree e `worktree-name` vira `worktree-rename`? — sim (dono, 2026-11-24)
- [x] Q1: `cepa until` vira `cepa run`, com `/common:until-review` virando `/common:run-review` e `cepa until-digest` virando `cepa run digest`? — sim, `cepa run` (dono, 2026-11-24)
- [x] Q2: o comando que refaz a revisão de nomes (item 11 do dono) ganha especificação própria, separada desta? — sim, separada: docs/spec/revisao-de-comandos.md (dono, 2026-11-24)
- [x] Q3: o nome antigo de um comando renomeado (`cepa plan`, `cepa until`, `/common:drain-plan`) é recusado com uma linha que diz o nome novo, em vez de continuar funcionando? — sim, recusa e diz o novo (dono, 2026-11-24)
- [x] Q4: os nomes gravados em disco (pasta `.claude/queues/<fila>/until/`, branch `until/<run>`, registros `.jsonl`) ficam como estão? — sim, ficam (dono, 2026-11-24)
- [x] Q5: para um comando de barra renomeado, mantenho um arquivo com o nome antigo só para avisar do nome novo? — não: o nome antigo some do menu e a linha com o nome novo vale só na CLI (dono, 2026-11-24)
- [x] Q6: reabro esta especificação para incluir a troca do prefixo `/common:`? — sim, e inclui a revisão dos prefixos dos outros plugins do Cepa, "para que fique claro de que são partes de algo maior (o Cepa)" (dono, 2026-11-24)
- [x] Q7: o plugin `common` passa a se chamar `cepa` (`/cepa:queue`, `/cepa:next`)? — sim, `cepa` (dono, 2026-11-24)
- [x] Q8: que forma tem o prefixo dos outros plugins (`board-flow`, `build-hex`, `build-solo`, `build-team`, `discovery`, `docs`, `design`, `marketing`, `review-gate`, `maestro`, `compass`)? — `cepa-` mais nome curto: `cepa-board`, `cepa-hex`, `cepa-solo`, `cepa-team`, `cepa-discovery`, `cepa-docs`, `cepa-design`, `cepa-marketing`, `cepa-review`, `cepa-maestro`, `cepa-compass` (dono, 2026-11-24)
- [x] Q9: a instalação troca sozinha o nome antigo dos plugins nas configurações de cada repo que usa o Cepa? — sim, `bin/install.sh` e `cepa doctor --fix` trocam, guardando uma cópia (dono, 2026-11-24)
- [x] Q10: as pastas do repo (`common/`, `board-flow/`, ...) mudam de nome junto com os plugins? — sim, pastas mudam também (dono, 2026-11-24)

## Decided without asking
- Os arquivos de histórico que citam os nomes antigos (docs/acceptance, docs/proof, `.claude/queues`, docs/archive e especificações já fechadas) não são reescritos: registram o que valia na data. Vete aqui se discordar.
- A flag `--until HH:MM` do lote com prazo não muda de nome: diz a hora de parar, não o comando. Vete aqui se discordar.
- `cepa prove` (o lote com prazo da coluna Review do Jira) não muda de nome: o dono não o citou e ele não se chama "until". Vete aqui se discordar.
- Os scripts com hífen seguem o nome novo (`cepa-queue`, `cepa-run`); `cepa-plan`, `cepa-until` e `cepa-until-digest` deixam de existir, e a linha "is now" é dada pelo lançador `cepa`. Segue Q3 e Q5. Vete aqui se discordar.
- Os 5 apelidos de P2 seguem a regra de Q3 e Q5: na CLI, recusa com o nome novo; no comando de barra, o arquivo some. Vete aqui se discordar.
- Nomes em inglês das flags: `--continue`, `--close`, `--list` (`/common:spec`); `--lenses` e `--area security|api-contract|data|ux|architecture` (`/common:advisors`); `--angles` (`/common:gauntlet`); `--on-branch` (`/common:queue-run`); `--queue` (`/common:run-review` e `/common:next`); `--open-point` e `--resolve-open-point` (`cepa queue finish`); `kept`, `vetoed`, `refined` (`cepa queue verdict`). Vete aqui se discordar.
- O marcador que o veredito grava no documento (`· mantida em`, `· vetada em`, `· refinada em`) não muda: é texto de um documento em português, não o que se digita. Vete aqui se discordar.
- Nomes novos das variáveis: `CEPA_MODO` vira `CEPA_MODE`, `CEPA_ENCADEAR` vira `CEPA_CHAIN`, `CEPA_PERMISSOES=classificador` vira `CEPA_PERMISSIONS=classifier`, `CEPA_PROMPT_MODO=substitui` vira `CEPA_PROMPT_MODE=replace`, `CEPA_COR` vira `CEPA_COLOR`, `CEPA_UNTIL_<X>` vira `CEPA_RUN_<X em inglês>`, `CLAUDE_WT_<X>` vira `CEPA_WT_<X>`, `CCW_<X>` vira `CEPA_<X>`. Vete aqui se discordar.
- Em `cepa intent`, a edição sem ação vira `cepa intent step N` e `cepa intent edit --purpose/--plan --reason`; em `cepa modes`, `cepa modes [MODE]` sem subcomando continua imprimindo a tabela. Vete aqui se discordar.
- `--demandas` do `/maestro:program-plan` não é traduzida: o comando está congelado. Vete aqui se discordar.
- O prefixo antigo de comando de barra segue a regra de Q5: some do menu, sem arquivo de aviso. Vete aqui se discordar.
- Os scripts da CLI mantêm o nome (`cepa-queue`, `cepa-run`, ...) e passam a morar em `cepa/bin/`; os scripts `maestro-*` não mudam de nome, o Maestro está congelado. Vete aqui se discordar.
- `board-flow.yaml`, `review-gate.yaml` e o valor gravado em `.claude/topology` (por exemplo `build-solo`) não mudam: são arquivos dos repos que usam o Cepa, e os leitores aceitam o valor antigo. Segue a resposta da Q4. Vete aqui se discordar.
- O `CLAUDE.md` do dono não é editado pela instalação: o `cepa doctor` só aponta a linha (CS-15). Vete aqui se discordar.
- Na fila, a troca de pastas e plugins (CS-12) vem depois de CS-1 a CS-10, e a varredura final (CS-11) vem por último. Vete aqui se discordar.
- Critério sobre arquivo de comando de barra usa a Surface `application`: o teste lê o arquivo, não existe camada mais externa que um teste alcance. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- `common/bin/cepa-until` chama `/common:drain-plan` e `/common:until-review` por nome em 24 linhas (contagem: `grep -n 'drain-plan\|until-review' common/bin/cepa-until | wc -l`, 2026-11-24). Uma run aberta durante a troca chamaria o nome antigo: a troca entra com nenhuma run aberta.
- Em 2026-10 a troca de nome de dois hooks sem compatibilidade derrubou Bash, Edit e Write das sessões abertas até `/reload-plugins` (BACKLOG.md, linhas 2380-2386). Uma sessão aberta antes da troca continua oferecendo os comandos de barra antigos até recarregar os plugins.
- 372 arquivos vivos citam `common:` (contagem: `grep -rlE '(/|")common:'` em `.md`, `.py`, `.json` e `.yaml`, fora de docs/acceptance, docs/proof e docs/archive, 2026-11-24). A troca do prefixo e das pastas é o item de maior alcance da reforma.
- Os caminhos escritos nos critérios CS-1 a CS-10 usam as pastas de hoje (`common/commands/`, `board-flow/bin/`). Depois do CS-12 os testes desses critérios passam a apontar para `cepa/` e `cepa-board/`.
- A instalação viva em `~/.claude/cepa-live/common/` muda de caminho: uma sessão aberta durante a instalação perde os hooks até reabrir.
- Hábito: quem digita `/common:drain-plan` recebe "Unknown command" sem a dica do nome novo (Q5).
- Fica de fora: um passo do plano da intenção não pode conter `:`, então não cita um comando de barra. Não foi aprovado como mudança.
- Fica de fora: o comando que refaz esta revisão, especificado em docs/spec/revisao-de-comandos.md (Q2).
