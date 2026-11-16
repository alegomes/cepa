# Especificação: o registro de plugins do Cepa nunca aponta para uma pasta que vai sumir

**Status:** ready-to-build
**Aberta em:** 2026-11-16            **Fechada em:** 2026-11-16
**Fontes lidas:** bin/install.sh, common/bin/cepa-until (docstring da reinstalação, linhas 183-206; `cmd_land`), common/bin/cepa-doctor (`cepa_repo_root`, `check_plugins`, `check_ops`), common/hooks/_pluginver.py, tests/test_cepa_until_hook_reinstall.py, tests/test_install_ops.py, tests/test_doctor_install_guard.py, .claude/queues/_all/until/2026-11-15-2107.review.md, ~/.claude/plugins/known_marketplaces.json, ~/.claude/settings.json, ~/.claude/ops/last-install.json

## Como chegamos aqui
"O que fazer pra este erro não acontecer novamente?" (dono, 2026-11-16, mostrando no terminal: `SessionEnd hook [python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session-registry.py"] failed: Plugin directory does not exist: /Users/alegomes/cepa-worktrees/cepa-until-2026-11-15-1011/common (common@cepa — run /plugin to reinstall)`)

## Problema
Uma rodada do `cepa-until` que altera `hooks/` ou `bin/` de um plugin roda `sh bin/install.sh --clean` de dentro da pasta da rodada (um git worktree em `~/cepa-worktrees/cepa-until-<run>`). O instalador registra o marketplace `cepa` na pasta de onde foi chamado (`bin/install.sh:249`), e o Claude Code passa a carregar os plugins direto dessa pasta. Quando a rodada aterrissa, a pasta é removida, e toda sessão que abriu nesse intervalo falha nos hooks com "Plugin directory does not exist". O conserto hoje depende de o dono lembrar de rodar `bin/install.sh` no clone principal depois de aterrissar.

Fato conferido em 2026-11-16 (Claude Code 2.1.325): os plugins de um marketplace de diretório rodam da pasta registrada, não do cache em `~/.claude/plugins/cache/cepa`. Duas evidências: o caminho do erro acima, e o diretório-base dos skills desta sessão (`/Users/alegomes/cepa-worktrees/cepa-until-2026-11-15-2107/common/skills/...`). O texto do `cepa-until` diz que `hooks/` e `bin/` "run from the cache", o que não vale nesta versão.

## Escopo
### Entra
- `bin/install.sh` copia os plugins do repo de onde foi chamado (clone principal ou worktree) para uma pasta fixa, `~/.claude/cepa-live`, e registra o marketplace `cepa` sempre nessa pasta. Nunca mais registra o repo.
- A cópia é trocada por renomeação: monta-se a pasta nova ao lado e só então ela toma o lugar da antiga. Com `--clean`, a antiga fica em `~/.claude/cepa-live.prev`, e `--rollback` a devolve junto com o cache.
- `~/.claude/ops/last-install.json` passa a gravar `repo_dir` (de onde os plugins foram copiados), `main_clone` (o clone principal desse repo) e `live_dir` (a pasta fixa).
- `cepa until land --yes`, no repo do Cepa, roda `bin/install.sh` do clone depois do merge e do build verde, e grava o resultado no registro da rodada. Pula e avisa quando há outra rodada viva cuja reinstalação está em vigor.
- `cepa-doctor` falha quando o registro aponta para pasta que não existe, avisa quando aponta para pasta que não é a fixa, e compara versões usando `repo_dir` do `last-install.json` no lugar do caminho registrado.
- Correção do texto do `cepa-until` que diz que `hooks/` e `bin/` rodam do cache e que manda rodar `bin/install.sh` à mão depois de aterrissar.
### Não entra
- Consertar sessões já abertas com o caminho de um worktree removido: o caminho fica na memória da sessão e só some quando ela reinicia.
- Os caminhos de `alias` que o instalador imprime (`common/bin/cepa`, `common/bin/cepa-until`) a partir do repo de onde foi chamado: é texto na tela, o dono escolhe o que cola no shell.
- Outras coisas que uma rodada deixa apontando para o worktree (o `.env.local-prod` do item de BACKLOG.md linha 4815): problema diferente, já tem item.
- Instalar a partir do GitHub ou de outra máquina: aqui só o marketplace de diretório local.
- `cepa until land` em repo que não é o Cepa: segue sem instalar nada.

## Estado e migração
- O primeiro `bin/install.sh` depois desta mudança move o registro do caminho atual (hoje `/Users/alegomes/cepa-worktrees/cepa-until-2026-11-15-2107`) para `~/.claude/cepa-live`. Nenhum dado é convertido.
- Sessões abertas antes desse install guardam o caminho antigo até reiniciar. A pasta da rodada 2107 só pode ser removida depois que essas sessões fecharem, senão o erro se repete uma última vez. O instalador já avisa que é preciso reiniciar as sessões.
- `last-install.json` antigo não tem `main_clone` nem `live_dir`. O `cepa-doctor` lê os dois como opcionais.
- A partir daqui, edição nos plugins do clone principal só entra no ar depois de `bin/install.sh` (resposta da Q3). Hoje, quando o registro aponta para o clone, ela vale na hora.

## Critérios de sucesso

### CS-1: instalar de dentro de um worktree registra a pasta fixa, e ela sobrevive à remoção do worktree
**Surface:** cli
**Red test:** com HOME temporário e um `claude` falso que grava os argumentos, rodar `sh bin/install.sh` de um worktree ligado; o argumento de `claude plugin marketplace add` é `$HOME/.claude/cepa-live`, `cepa-live/common/.claude-plugin/plugin.json` é igual ao do worktree, e depois de `git worktree remove` o arquivo continua lá. Hoje o argumento é o caminho do worktree.

### CS-2: instalar do clone principal também registra a pasta fixa
**Surface:** cli
**Red test:** no mesmo arranjo, rodar `sh bin/install.sh` do clone principal; o argumento de `claude plugin marketplace add` é `$HOME/.claude/cepa-live` e a pasta tem `.claude-plugin/marketplace.json` e uma pasta por plugin listado nele. Hoje o argumento é o caminho do clone.

### CS-3: `--clean` guarda a cópia anterior e `--rollback` a devolve
**Surface:** cli
**Red test:** instalar a versão A, depois `sh bin/install.sh --clean` com a versão B, depois `sh bin/install.sh --rollback`; `cepa-live/common/.claude-plugin/plugin.json` volta a dizer a versão A e `cepa-live.prev` não existe mais. Hoje `cepa-live` não existe.

### CS-4: cópia que falha no meio deixa a pasta fixa anterior inteira
**Surface:** cli
**Red test:** com a versão A instalada, rodar o instalador sobre um repo em que a cópia de um plugin falha (pasta sem permissão de leitura); o instalador sai diferente de zero, `cepa-live` ainda tem a versão A completa e `last-install.json` diz `in_progress`. Hoje não há cópia.

### CS-5: o registro operacional diz de onde veio a cópia
**Surface:** cli
**Red test:** depois de `sh bin/install.sh` de um worktree ligado, `~/.claude/ops/last-install.json` tem `repo_dir` igual ao worktree, `main_clone` igual ao clone principal e `live_dir` igual a `$HOME/.claude/cepa-live`. Hoje só existe `repo_dir`.

### CS-6: `cepa until land --yes` instala do clone depois do build verde
**Surface:** cli
**Red test:** num repo do Cepa de teste com uma rodada pronta para aterrissar e um `bin/install.sh` falso que grava de onde foi chamado, `cepa-until land <fila>/<run> --yes` chama o instalador com o clone como diretório, depois do merge, e o registro da rodada ganha `instalado_no_pouso`. Hoje o land não chama o instalador.

### CS-7: o land não instala por cima de uma rodada viva que reinstalou
**Surface:** cli
**Red test:** no mesmo arranjo, com `last-install.json` dizendo `repo_dir` igual ao worktree de outra rodada cujo processo está vivo, `cepa-until land <fila>/<run> --yes` aterrissa, não chama o instalador, grava `instalacao_adiada` no registro e imprime em "Fica com você" o pedido de rodar `bin/install.sh` no clone quando a outra rodada terminar. Hoje não há nem a instalação nem o aviso.

### CS-8: instalação que falha no pouso é desfeita e o pouso vale
**Surface:** cli
**Red test:** com um `bin/install.sh` falso que sai 1 na instalação e 0 no `--rollback`, `cepa-until land <fila>/<run> --yes` sai 0, o merge está no clone, o instalador foi chamado uma segunda vez com `--rollback`, o registro ganha `reinstalacao_desfeita` e a saída pede o install à mão em "Fica com você". Hoje o land não chama o instalador.

### CS-9: o doctor falha quando o registro aponta para pasta que não existe
**Surface:** cli
**Red test:** com `known_marketplaces.json` apontando `cepa` para um caminho inexistente e `last-install.json` com `main_clone` válido, `cepa-doctor` imprime uma falha de `plugins` que nomeia o caminho inexistente e oferece o conserto `install` com o `main_clone`. Hoje imprime "marketplace 'cepa' não encontrado em known_marketplaces.json", sem conserto.

### CS-10: o doctor avisa quando o registro aponta para pasta que não é a fixa
**Surface:** cli
**Red test:** com `known_marketplaces.json` apontando `cepa` para um worktree que existe, `cepa-doctor` imprime um aviso de `plugins` dizendo que o registro está fora de `~/.claude/cepa-live` e oferece o conserto `install`. Hoje não diz nada sobre o caminho.

### CS-11: o doctor compara versões com o repo de origem, não com o caminho registrado
**Surface:** cli
**Red test:** com o registro na pasta fixa em `common` 3.6.0 e `last-install.json` com `repo_dir` num repo em `common` 3.7.0, `cepa-doctor` avisa "repo está em 3.7.0 mas o cache instalado é 3.6.0". Hoje ele leria a pasta fixa como se fosse o repo e diria que está tudo instalado.

## Perguntas em aberto
- [x] Q1. Para onde o registro do marketplace `cepa` aponta quando o instalador é chamado de dentro de um worktree de rodada? O1: sempre o clone principal. O2: o worktree, e o `cepa-until` devolve no fim. O3: uma cópia em pasta fixa fora do repo, que o instalador atualiza e que nunca é apagada. — O3, cópia em pasta fixa (dono, 2026-11-16).
- [x] Q2. Depois de aterrissar a rodada, o `cepa until land` roda sozinho o `bin/install.sh` do clone principal, ou segue como passo manual? — Roda sozinho, depois do merge e do build verde (dono, 2026-11-16).
- [x] Q3. Quando o instalador roda do clone principal (não de um worktree), o registro também aponta para a pasta fixa, ou segue apontando para o clone principal como hoje? — Pasta fixa sempre (dono, 2026-11-16).
- [x] Q4. Se o `cepa until land` vai instalar do clone principal e existe outra rodada viva cuja reinstalação está em vigor, o land instala assim mesmo ou pula e avisa? — Pula e avisa (dono, 2026-11-16).

## Decided without asking
- A pasta fixa é `~/.claude/cepa-live`, ao lado de `~/.claude/cepa-telemetry` e `~/.claude/cepa-feedback`, e fora de `~/.claude/plugins/`, que o Claude Code administra. Vete aqui se discordar.
- A cópia leva `.claude-plugin/marketplace.json` e as pastas dos plugins listados nele, como estão no disco (arquivos não commitados incluídos, como hoje), sem `__pycache__`. Vete aqui se discordar.
- A reinstalação no meio da rodada do `cepa-until` não muda de código: ele segue chamando `sh bin/install.sh --clean` do worktree, e é o instalador que passa a registrar a pasta fixa. Vete aqui se discordar.
- O land instala em todo pouso feito no repo do Cepa, e não só quando a rodada tocou em `hooks/` ou `bin/`: a pasta fixa pode ter vindo do worktree da rodada e precisa voltar a ser o `main`. Em "already landed" ou sem `--yes` não instala. Vete aqui se discordar.
- O código de saída do land não muda quando a instalação falha ou é adiada: o pouso aconteceu, e o que falta vai para "Fica com você". Vete aqui se discordar.
- O doctor usa `repo_dir` do `last-install.json` como repo de origem e, se essa pasta não existe mais, `main_clone`. Sem nenhum dos dois, diz o comando a rodar e não oferece conserto automático. Vete aqui se discordar.
- Registro em pasta inexistente é falha, registro em pasta existente que não é a fixa é aviso: o primeiro quebra hooks, o segundo só vai quebrar quando a pasta for removida. Vete aqui se discordar.
- O resumo `hooks_sha` que o `cepa-until` grava segue calculado sobre o cache, que o `claude plugin install` enche a partir da pasta fixa. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- "Os plugins rodam da pasta registrada" foi observado no Claude Code 2.1.325, por dois caminhos vistos nesta sessão. Se outra versão rodar do cache, a pasta fixa não atrapalha, mas deixa de ser o que está no ar.
- `claude plugin marketplace add ~/.claude/cepa-live` ainda não foi executado. O teste de 2026-11-12 registrou o caminho de um repo. O primeiro item da construção roda isso de verdade com `CLAUDE_CONFIG_DIR` numa pasta de rascunho antes de qualquer outro.
- Passo manual que resta antes da construção: aterrissar a rodada `all/2026-11-15-2107`, rodar `sh bin/install.sh` em `/Users/alegomes/coding/cepa` e reiniciar as sessões. Sem isso o erro volta quando a pasta da 2107 for removida.
- Uma rodada que morre depois de reinstalar deixa a pasta fixa com o conteúdo dela. Nada quebra, mas o que está no ar não é o `main` até o próximo install. O CS-11 faz o doctor mostrar isso.
