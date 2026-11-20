# Especificação: run que já está no destino sai da lista de pendências

**Status:** ready-to-build
**Aberta em:** 2026-11-20            **Fechada em:** 2026-11-20
**Fontes lidas:** common/bin/cepa-until (waiting_runs, cmd_pending, _cmd_land, install_on_landing, commit_subcommand_records, run_states), common/commands/next.md, common/hooks/_state.py (SESSIONS_KINDS), common/hooks/_wtlib.py (reap_tombstones), tests/test_state_deposits.py, docs/spec/decisoes-de-todas-as-filas.md, docs/spec/fim-do-until-sem-espera.md, docs/spec/until-arvore-limpa.md, docs/spec/registro-de-plugins-pasta-estavel.md, .gitignore, os registros de run em .claude/queues/*/until/ do clone principal

## Como chegamos aqui
Em 2026-11-20 o dono colou a lista "Pendente com você (5)", com cinco runs antigos de outras filas, e perguntou: "o que podemos fazer para que essas pendências não se acumulem?"

## Problema
A lista de runs que esperam o dono mostra pendência que não existe. Em 2026-11-20, quatro dos cinco runs listados já estavam em `main` e em `origin/main`, e a lista dizia "entrou no main com o build quebrado, não enviado". A lista lê a marca `parou: build-vermelho` do arquivo de estado do run (`common/bin/cepa-until:5880`) e nunca confere o remoto. Apagar a marca exige rodar `cepa-until land` de novo, com um build completo de cerca de 26 min por run (1.545 s, medido na revisão do run 2026-11-11-2031 da fila modos-opinativos), então ninguém apaga.

Além dos cinco listados, há outros cinco registros em `esperando-dono` que a lista esconde (10 registros nesse estado, 5 listados): dois com branch vivo já contido no `main` e três cujo branch não existe mais. O clone tem 17 branches `until/*`.

## Escopo
### Entra
- `cepa-until pending` confere, para cada registro de run em `esperando-dono`, se o trabalho do run já está no upstream do branch de destino.
- O run que já está lá é fechado pela própria lista, sem build: estado `aterrissado`, arquivos ignorados pelo git guardados em `.claude/rescued`, worktree e branch do run removidos, plugins reinstalados com a mesma regra do `land`.
- O registro em `esperando-dono` cujo branch não existe mais é fechado pelo commit gravado nele: `aterrissado` se o commit está no destino, `descartado` (estado novo) se não está.
- A lista avisa, em uma linha por run, o que fechou, separado das linhas de espera.
- `/common:next` mostra as linhas de fechamento fora de "Pendente com você".

### Não entra
- Trava de um pouso por vez no mesmo clone. Decisão do dono em 2026-11-20: medir primeiro o efeito desta especificação.
- `--auto-land` como padrão. Mesma decisão, mesma data.
- Qualquer critério sobre build vermelho falso no pouso. As duas causas conhecidas já foram corrigidas (commits b176265, bb3519e e c6f3cec). Pouso novo que sair vermelho por causa alheia ao run vira especificação própria.
- `git fetch` dentro da lista. Ela lê o upstream como o clone o conhece.
- Os itens de fila que o run deixou com o dono. Eles continuam na fila e aparecem em `cepa plan waiting`.

## Estado e migração
- O campo `estado` do registro de run (`.claude/queues/<fila>/until/<run>.estado.json`, ignorado pelo git) ganha o valor `descartado`. O catálogo de estados em `common/hooks/_state.py` passa a conhecê-lo.
- Não há passo de migração. Na primeira chamada de `cepa-until pending` no clone principal depois da mudança, os 10 registros hoje em `esperando-dono` se resolvem assim: 6 viram `aterrissado` com branch e worktree removidos (os 4 listados com build vermelho mais os 2 ocultos de perguntas-da-largada-legiveis), 3 sem branch viram `aterrissado` ou `descartado` conforme o commit gravado, e 1 continua em espera (lacunas-ecc 2026-11-13-0800, com 11 commits fora do `main`). Conta: 4 + 2 + 3 + 1 = 10.
- A saída `--json` ganha a chave `fechados`. As chaves `runs` e `mortos` não mudam.

## Critérios de sucesso

### CS-1: O run com build vermelho cujo merge já está no upstream sai da lista e vira `aterrissado`, sem build
**Surface:** cli
**Red test:** num repo de teste com remoto, o run `a/r1` está em `esperando-dono` com `aterrissagem.parou: build-vermelho` e o branch contido em `origin/main`, e o run `a/r2` está na mesma situação mas com o merge só no `main` local. O `verify` dos dois é um script que grava um arquivo marcador. Depois de `cepa-until pending`, o teste exige: nenhuma linha de espera para `a/r1`, `estado: aterrissado` no registro de `a/r1`, arquivo marcador ausente, e a linha "merged in `main` with a red build" ainda presente para `a/r2`. Hoje a linha de espera aparece para os dois e o registro de `a/r1` segue `esperando-dono`.

### CS-2: Ao fechar o run, a lista remove o branch e a worktree dele e guarda os arquivos ignorados pelo git
**Surface:** cli
**Red test:** com o run `a/r1` do CS-1 tendo uma worktree com um arquivo ignorado pelo git, depois de `cepa-until pending` o teste exige `git branch --list until/r1` vazio, a pasta da worktree ausente e o arquivo ignorado presente sob `.claude/rescued/`. Hoje branch, worktree e arquivo ficam onde estavam.

### CS-3: O run que nunca passou por `land` até o fim, mas cujo branch já está no upstream, também é fechado
**Surface:** cli
**Red test:** num repo de teste com remoto, um run em `esperando-dono` com `aterrissagem: null` e outro com `aterrissagem.parou: conflito`, ambos com o branch contido em `origin/main`. Depois de `cepa-until pending`, o teste exige `estado: aterrissado` nos dois registros e os dois branches removidos. Hoje a lista pula os dois e os registros seguem `esperando-dono`.

### CS-4: O registro em `esperando-dono` sem branch é fechado pelo commit gravado nele
**Surface:** cli
**Red test:** dois runs em `esperando-dono` cujo branch foi apagado: o commit gravado na ação `aterrissar` de `a/r3` está em `origin/main`, o de `a/r4` não está. Depois de `cepa-until pending`, o teste exige `estado: aterrissado` em `a/r3` e `estado: descartado` em `a/r4`. Hoje os dois seguem `esperando-dono`.

### CS-5: A lista diz o que fechou, em uma linha por run, separada das linhas de espera
**Surface:** cli
**Red test:** com os runs do CS-1 e do CS-4, a saída de `cepa-until pending` traz uma linha que começa com `closed:` para `a/r1`, `a/r3` e `a/r4`, cada uma com fila, run e o desfecho (`landed` ou `discarded`), e `cepa-until pending --json` traz a chave `fechados` com os três. Uma segunda chamada não imprime nenhuma linha `closed:`. Hoje não existe linha `closed:` nem a chave `fechados`.

### CS-6: No repo cepa, fechar o run reinstala os plugins com a mesma regra e as mesmas travas do `land`
**Surface:** cli
**Red test:** num repo de teste reconhecido como repo cepa, com um `bin/install.sh` falso, `cepa-until pending` fecha o run `a/r1` e o `.jsonl` do run ganha o evento `instalado_no_pouso`. Com o registro da última instalação apontando para a worktree de outro run vivo, o `.jsonl` ganha `instalacao_adiada` e o `install.sh` falso não roda. Hoje `pending` não escreve evento nenhum.

### CS-7: O que o fechamento escreve nos registros versionados entra num commit, e a árvore do clone fica limpa
**Surface:** cli
**Red test:** depois do fechamento do CS-6, o teste exige `git status --porcelain` vazio no clone e um commit no topo com a mensagem `until a/r1 pending: ...` que contém só o `.jsonl` do run. Hoje não há commit com essa mensagem.

### CS-8: O run cuja worktree tem mudança rastreada sem commit não é fechado, e a linha dele diz por quê
**Surface:** cli
**Red test:** com o run `a/r1` do CS-1 e um arquivo rastreado modificado sem commit na worktree dele, `cepa-until pending` mantém o registro em `esperando-dono`, mantém branch e worktree, e imprime para `a/r1` uma linha que nomeia a worktree e diz que há mudança sem commit. Hoje a linha impressa é "merged in `main` with a red build, not pushed".

### CS-9: `/common:next` mostra as linhas `closed:` fora de "Pendente com você"
**Surface:** cli
**Red test:** um teste lê `common/commands/next.md` e exige a instrução de que linha de `cepa-until pending` iniciada por `closed:` é relatada como fechamento, fora da seção "Pendente com você". Hoje o arquivo manda listar cada linha da saída sob "Pendente com você".

## Perguntas em aberto
- [x] Quando um run conta como já pousado: quando o commit dele está no upstream do branch de destino, ou basta estar no branch de destino local? Resposta do dono (2026-11-20): no upstream do branch de destino. Em repo sem upstream vale o branch local. O merge local com build vermelho e sem push continua listado.
- [x] Quem fecha o run já pousado: a própria leitura da lista, ou um comando que o dono roda? Resposta do dono (2026-11-20): a própria lista. `cepa-until pending` fecha sozinho (estado `aterrissado`, arquivos ignorados pelo git guardados em `.claude/rescued`, worktree e branch removidos) e avisa em uma linha o que fechou.
- [x] O que acontece com o registro em `esperando-dono` cujo branch não existe mais? Resposta do dono (2026-11-20): fecha pelo commit gravado no registro. No destino vira `aterrissado`. Fora do destino vira o estado novo `descartado`.
- [x] As duas causas conhecidas de build vermelho falso já foram corrigidas (commits b176265, bb3519e e c6f3cec, de 14 e 15/11). Sobra algum critério sobre build vermelho nesta especificação? Resposta do dono (2026-11-20): não. Pouso novo que sair vermelho por causa alheia ao run vira especificação própria.
- [x] Ao fechar sozinha um run e remover a worktree dele, a lista também reinstala os plugins? Resposta do dono (2026-11-20): sim, como o `land`, com a mesma regra e as mesmas travas.

## Decided without asking
- Com o branch do run existindo, a conferência usa a ponta do branch, não o commit gravado na ação `aterrissar`. Commit feito no branch depois do merge mantém o run na lista, porque é trabalho que ainda não está no destino. Vete aqui se discordar. · mantida em 2026-11-20
- A lista não roda `git fetch`. Um comando de leitura que depende de rede falharia sem conexão, e o push feito de outra máquina aparece no próximo fetch do dono. Vete aqui se discordar. · mantida em 2026-11-20
- Worktree com mudança rastreada sem commit impede o fechamento (CS-8). Fechar apagaria ou deixaria órfão um trabalho que não está no destino. Vete aqui se discordar. · mantida em 2026-11-20
- O fechamento só commita registros versionados que ele mesmo escreveu, com a mesma função que `decide`, `close-dead` e `land` usam, sem push. Segue a especificação docs/spec/until-arvore-limpa.md. O `.estado.json` é ignorado pelo git e não entra em commit. Vete aqui se discordar. · mantida em 2026-11-20
- As linhas novas da saída ficam em inglês (`closed:`, `landed`, `discarded`), como o resto da interface do `cepa-until`. Vete aqui se discordar. · mantida em 2026-11-20
- Os itens que o run deixou com o dono (`fica_com_voce`) não são tocados pelo fechamento. Eles vivem na fila e continuam visíveis em `cepa plan waiting`. Vete aqui se discordar. · mantida em 2026-11-20
- O estado `descartado` nunca aparece na lista e o `land` o recusa como recusa qualquer estado diferente de `esperando-dono`. Vete aqui se discordar. · mantida em 2026-11-20

## Riscos e o que ficou de fora desta especificação
- `cepa plan waiting` (especificação decisoes-de-todas-as-filas) lê a mesma fonte do `cepa until pending`. A mudança aqui muda as duas saídas juntas.
- `cepa-until pending` deixa de ser só leitura: remove worktree e branch, reinstala plugins e commita. Quem o chama (`/common:next`, `/common:doctor`, o painel do herdr ao retomar) passa a disparar esses efeitos. O tempo da reinstalação não foi medido.
- Um run pousado com build vermelho de verdade e enviado ao remoto por fora do `land` sai da lista. O vermelho passa a ser problema do `main`, visível no próximo build de qualquer run.
- Registro em `esperando-dono` sem ação `aterrissar` (run que terminou sem commit) não é tratado aqui. Não conferi se existe algum hoje.
- Não medi se as correções dos testes do herdr (bb3519e, c6f3cec) acabaram com a falha ao acaso sob carga.
