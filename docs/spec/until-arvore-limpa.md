# Especificação: cepa-until não deixa a árvore suja ao final da execução

**Status:** ready-to-build
**Aberta em:** 2026-11-14            **Fechada em:** 2026-11-14
**Fontes lidas:** common/bin/cepa-until, common/bin/cepa-plan, .gitignore, BACKLOG.md

## Como chegamos aqui
"Cepa until não pode deixar a árvore suja ao final da execução" (dono, 2026-11-14), na manhã em que o `git status` da main abriu com 16 entradas soltas de runs anteriores e o dono acabara de commitar à mão a fila de `perguntas-da-largada-legiveis` como "night run" (eea282e).

## Problema
Depois de cada run do `cepa-until`, a main do clone fica com arquivos sem commit que o próprio run escreveu: a `queue.yaml` com as marcas dos itens, o registro `until/<run>.jsonl`, a revisão `until/<run>.review.md` e às vezes a `queue.yaml.bak`. O `land` só avisa "commit whenever you want". O dono acaba limpando à mão, e a sujeira de um run se mistura com a dele e com a do run seguinte.

## Escopo
### Entra
- No fim do run, um commit na branch do clone com a `queue.yaml` da fila, o `until/<run>.jsonl` e o `until/<run>.review.md`, e nada além disso.
- O mesmo commit na saída por Ctrl+C, SIGTERM e limite de uso.
- Os subcomandos `decide`, `close-dead` e `land` commitam, ao sair, a fila e os registros que tocaram.
- Na largada, o `cepa-until` recolhe num commit os registros soltos de runs cujo supervisor morreu, em qualquer fila do repo.
- `.claude/queues/*/queue.yaml.bak` no `.gitignore`.
- Um commit de faxina com os registros de runs antigos que estão soltos na main.
### Não entra
- A worktree do run (`until/<run>`): o `land` já recusa a worktree suja e a remove ao aterrissar.
- Push: quem publica continua sendo o `land`, que o dono dispara.
- Forçar o commit (`--no-verify`, resolver merge ou rebase em andamento): se o git recusar, o run avisa e não insiste.
- Arquivos sujos do dono na main: o commit leva só os caminhos do run.

## Estado e migração
- `.gitignore` ganha a linha `.claude/queues/*/queue.yaml.bak`; os 3 `.bak` soltos hoje deixam de aparecer no `git status` sem ser apagados.
- Os `.jsonl` e `.review.md` soltos de runs antigos entram num commit único de faxina, feito na construção.
- Os registros já versionados (16 `.jsonl`, 16 `.review.md`) não mudam.
- O aviso "the queue ... holds the run's marks without a commit; commit whenever you want" do `land` sai, porque deixa de ser verdade.

## Critérios de sucesso

### CS-1: Ao terminar normalmente, o run deixa a main sem nenhum arquivo dele fora do git
**Surface:** cli
**Red test:** num repo de teste com uma fila de um item, `cepa-until <fila> --for 5m` termina e `git status --porcelain` do clone lista a `queue.yaml`, o `.jsonl` e o `.review.md` do run; o teste exige a saída vazia e um commit novo no topo que contém exatamente esses três caminhos.

### CS-2: O commit do run não leva arquivos que o dono deixou sujos na main
**Surface:** cli
**Red test:** com um `notas.txt` modificado e um `rascunho.md` em stage no clone antes do run, ao fim do run o commit novo não contém nenhum dos dois, e `git status --porcelain` ainda mostra os dois exatamente como estavam (um modificado, outro em stage).

### CS-3: Ctrl+C, SIGTERM e limite de uso também terminam com o commit
**Surface:** cli
**Red test:** mandar SIGINT ao supervisor no meio do segundo item (e, num segundo caso, simular a parada por limite de uso) e, depois que o processo sai, exigir `git status --porcelain` sem nenhum caminho de `.claude/queues/<fila>/` e o `.jsonl` com `run_interrompido` dentro do último commit.

### CS-4: A largada recolhe registros soltos de runs mortos de qualquer fila
**Surface:** cli
**Red test:** com um `.jsonl` e uma `queue.yaml` modificada da fila `outra` cujo supervisor morreu (pid inexistente), lançar `cepa-until <fila>`; o teste exige um commit de recolha com os caminhos de `outra` antes do primeiro item, e que a largada não recuse por árvore suja.

### CS-5: Se o git recusar o commit, o run avisa com o motivo e o comando, sem forçar
**Surface:** cli
**Red test:** com um hook `pre-commit` que sai com 1 no repo de teste, o run termina com o código de saída que teria sem o hook, a tela final e o `.review.md` trazem a linha do motivo e o comando `git commit` exato para o dono, nenhum commit novo é criado e nenhuma chamada a `git` traz `--no-verify`.

### CS-6: Com a main no meio de um merge ou rebase, o run não commita e avisa
**Surface:** cli
**Red test:** com `.git/MERGE_HEAD` presente no clone ao fim do run, nenhum commit é criado, o merge em andamento continua intacto (`git status` ainda diz "All conflicts fixed but you are still merging" ou o estado original) e a tela final diz por que não commitou.

### CS-7: `decide`, `close-dead` e `land` commitam o que escreveram na fila e nos registros
**Surface:** cli
**Red test:** depois de um run terminado e commitado, `cepa-until decide` respondendo uma pergunta deixa `git status --porcelain` vazio e um commit novo com a `queue.yaml`; o mesmo para `close-dead` sobre um run morto (commit com o `.jsonl` e a fila) e para `land --yes` (nenhum caminho de `.claude/queues/` sujo depois).

### CS-8: O run não faz push
**Surface:** cli
**Red test:** num repo de teste com um remoto bare, ao fim do run o `HEAD` do remoto é o mesmo de antes da largada, enquanto o clone tem o commit novo.

### CS-9: A `queue.yaml.bak` não aparece no `git status`
**Surface:** cli
**Red test:** `cepa-plan --from-spec` regravando uma fila existente cria `queue.yaml.bak`, e `git status --porcelain --untracked-files=all` não lista esse arquivo.

## Perguntas em aberto
- [x] P1. Quando e onde a sujeira do run vira commit? — No fim do run: o próprio `cepa-until` faz um commit na branch do clone só com os caminhos que o run escreveu.
- [x] P2. O `.jsonl` e o `.review.md` de cada run são versionados ou ignorados pelo git? — Versionados.
- [x] P3. A `queue.yaml.bak` (escrita pelo `cepa-plan --from-spec`, não pelo run) entra no escopo? — Sim, vai para o `.gitignore`.
- [x] P4. O que fazer com as 16 entradas soltas que já estão na main hoje? — Um commit de faxina na construção junta os `.jsonl` e `.review.md` existentes; os `.bak` somem pelo `.gitignore`.
- [x] P5. Se o run para antes do fim normal, o commit acontece? — Sim: Ctrl+C, SIGTERM e limite de uso commitam na saída; a morte sem aviso é recolhida pelo próximo `cepa-until`.
- [x] P6. Se o commit falhar (hook recusa, merge ou rebase em andamento)? — Não força e avisa: motivo e comando exato na tela final e no `.review.md`, nunca `--no-verify`, o resultado do run continua valendo.
- [x] P7. O run faz push depois do commit? — Não, só commit local.
- [x] P8. A worktree do run também precisa terminar limpa? — Não, esta especificação trata só da main do clone.
- [x] P9. `decide`, `close-dead` e `land` também commitam o que escreveram? — Sim, os três.
- [x] P10. A largada recolhe registros de runs mortos só da mesma fila ou de todas? — De todas as filas do repo.

## Decided without asking
- Os `.log` e `.estado.json` do run seguem ignorados como hoje (`.gitignore`, linhas 47-50): já não sujam a árvore. Vete aqui se discordar.
- O commit do run é o último passo do run, depois das perguntas do fim (que gravam respostas na `queue.yaml` pelo `cepa-plan answer`) e depois do `.review.md`: commitar antes deixaria a fila suja de novo. Vete aqui se discordar.
- O commit usa pathspec (`git commit -- <caminhos>`), que leva só os caminhos do run e deixa o stage do dono intacto. Vete aqui se discordar.
- A `queue.yaml` entra inteira no commit, mesmo que o dono a tenha editado durante o run (por exemplo, respondendo pelo `cepa-plan` em outro terminal): é o mesmo arquivo e não há como separar as linhas. Vete aqui se discordar.
- Mensagem do commit: `until <fila>/<run>: queue marks and run records` (em inglês, como os commits do repo); a recolha usa `until: collect records of dead runs (<filas>)` e os subcomandos `until <fila>/<run> <subcomando>: ...`. Vete aqui se discordar.
- Com a branch do clone em HEAD destacado, o run não commita e avisa, pela mesma regra do CS-6. Vete aqui se discordar.
- Sem nada a commitar (nenhum caminho do run sujo), não cria commit vazio. Vete aqui se discordar.
- Vale também para o `.claude/programs/<fila>/plan.yaml` que o `land` já trata como fila (`common/bin/cepa-until`, por volta da linha 2245). Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- O commit automático na main é o primeiro que o run faz fora da sua branch `until/<run>`; até hoje só o `land`, disparado pelo dono, mexia na main. O risco é limitado porque o commit só leva arquivos de `.claude/queues/` e `.claude/programs/`, e é reversível com `git revert`.
- Se o dono commitar à mão a fila enquanto o run roda, o commit do fim fica menor ou vazio, sem conflito.
- A morte do processo durante o próprio commit (entre o `git add` e o `git commit`) deixa caminhos em stage; a próxima largada os recolhe pelo CS-4.
