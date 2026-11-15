# Especificação: cepa until sobre todos os itens prontos, de todas as filas

**Status:** ready-to-build
**Aberta em:** 2026-11-15            **Fechada em:** 2026-11-15
**Fontes lidas:** common/bin/cepa-until, common/bin/cepa-plan (cmd_ready, ready_of_queue), docs/spec/until-arvore-limpa.md

## Como chegamos aqui
"Eu quero um comando no shell que lance o cepa until sobre todos os itens prontos para serem construídos, independente da fila em que estão." (dono, 2026-11-15, mostrando a saída de `cepa plan ready`: 16 filas, 11 itens prontos espalhados por 5 delas)

## Problema
`cepa plan ready` já mostra os itens prontos de todas as filas, mas `cepa until` só roda uma fila por vez. Para aproveitar uma janela desatendida com itens prontos em 5 filas, o dono precisa lançar 5 runs à mão, uma depois da outra ou em paralelo, e depois aterrissar 5 branches.

## Escopo
### Entra
- Flag `--all` no `cepa until`, aceita no lugar do nome da fila e combinável com `--for`, `--until`, `--dry-run`, `--verify`, `--no-verify` e as demais opções.
- Um run sequencial, um item por subprocesso, numa única branch `until/<run>`, com o build completo após cada item `done` como hoje.
- Ordem: fila a fila, na ordem do `cepa plan ready`; dentro da fila, a ordem gravada. Os prontos são relidos antes de cada item.
- Painel de largada único com o que todas as filas guardam para o dono.
- Registro em `.claude/queues/_all/until/` e alvo `all/<run>` em `pending`, `decide`, `land` e `close-dead`.
- Fila com run próprio vivo é pulada com aviso. Fila com `--max-blocked` travados seguidos sai do run.
### Não entra
- Execução paralela entre filas (Q1: uma branch, uma aterrissagem, sem conflito entre filas).
- Escolher um subconjunto de filas ou outra ordem (Q2: o dono quer "independente da fila"; para uma fila só, `cepa until <fila>` já existe).
- Filas `parallel-waves` do Maestro (não são `single-track`, o `ready` já as ignora).
- Mudança no `cepa plan ready`, no `/common:drain-plan` ou no formato das filas.

## Estado e migração
Nenhum dado existente muda. As filas, seus `queue.yaml` e os registros `until/` de cada fila ficam como estão. O que é novo: a pasta `.claude/queues/_all/until/`, criada no primeiro run `--all`. Os subcomandos `pending`, `decide`, `land` e `close-dead` passam a reconhecer o alvo `all/<run>` além de `<fila>/<run>`. Cada item continua sendo reservado e encerrado na própria fila pelo `cepa-plan start/finish`, então o `queue.yaml` de cada fila registra o resultado do item como hoje.

## Critérios de sucesso

### CS-1: `cepa until --all --for 8h --dry-run` lista os itens prontos de todas as filas, agrupados por fila e na ordem do `cepa plan ready`, e sai com 0 sem executar nada
**Surface:** cli
**Red test:** num repo de teste com as filas `a` (1 pronto) e `b` (1 pronto), `cepa until --all --for 8h --dry-run` sai com 0 e a saída traz `a` antes de `b` com os dois ids; hoje sai com 2 porque `--all` não existe e o nome da fila é obrigatório.

### CS-2: Um run `--all` executa itens de mais de uma fila numa única branch `until/<run>`
**Surface:** cli
**Red test:** com as filas `a` e `b`, cada uma com 1 item pronto, e um `claude` falso que commita e encerra o item como `done`, `cepa until --all --for 1h` termina com os dois itens `done` nos respectivos `queue.yaml` e os dois commits na mesma branch `until/<run>`; hoje o comando é recusado.

### CS-3: A ordem é fila a fila, e um item que fica pronto durante o run entra antes de passar à fila seguinte
**Surface:** cli
**Red test:** fila `a` com `a1` e `a2` (`a2` espera `a1`) e fila `b` com `b1`; após `cepa until --all --for 1h` com o `claude` falso, os eventos `item_start` do registro aparecem na ordem `a1`, `a2`, `b1`; hoje o comando é recusado.

### CS-4: Uma fila com run próprio vivo é pulada com aviso, e as outras seguem
**Surface:** cli
**Red test:** com um `*.estado.json` em estado `rodando` e pid vivo na fila `a`, `cepa until --all --for 1h` imprime um aviso que nomeia a fila `a` e o run dela, não inicia nenhum item de `a` e termina `b1` como `done`; hoje o comando é recusado.

### CS-5: `--max-blocked` itens `blocked` seguidos tiram a fila do run e ele segue nas outras
**Surface:** cli
**Red test:** fila `a` com 3 itens que o `claude` falso devolve como `blocked` e fila `b` com 1 item `done`, `cepa until --all --for 1h --max-blocked 3` imprime uma linha dizendo que a fila `a` saiu do run e termina `b1` como `done`; hoje o comando é recusado.

### CS-6: O registro fica em `.claude/queues/_all/until/` e `pending`, `decide`, `land` e `close-dead` aceitam o alvo `all/<run>`
**Surface:** cli
**Red test:** depois de um run `--all`, existe `.claude/queues/_all/until/<run>.jsonl`, `cepa until pending` lista `all/<run>` e `cepa until land all/<run> --yes` aterrissa a branch; hoje `land` recusa o alvo com "the target is <queue>/<run>" porque não existe fila `all`.

### CS-7: Num terminal, a largada mostra um painel único com o que todas as filas guardam para o dono, agrupado por fila, e um "sim" faz o item rodar neste run
**Surface:** cli
**Red test:** com a fila `a` tendo um item com `human_pending` e a fila `b` outro, `cepa until --all --for 1h` num pseudo-terminal mostra um único painel com as seções `a` e `b`; respondendo "sim" ao item de `a`, ele aparece com `item_start` no registro do run; hoje o comando é recusado.

### CS-8: Enquanto um run `--all` está vivo, um segundo `--all` e um `cepa until <fila>` de qualquer fila são recusados com o nome do run vivo
**Surface:** cli
**Red test:** com um `.claude/queues/_all/until/*.estado.json` em estado `rodando` e pid vivo, `cepa until --all --for 1h` e `cepa until a --for 1h` saem com 2 e citam `all/<run>`; hoje o segundo comando larga normalmente.

### CS-9: Sem item pronto em nenhuma fila, o `--all` sai com 0, diz isso e não cria branch
**Surface:** cli
**Red test:** com todas as filas fechadas ou esperando o dono e o painel recusado (`--no-pre-read`), `cepa until --all --for 1h` sai com 0, imprime que nenhuma fila tem item pronto e `git branch --list 'until/*'` não ganha branch nova; hoje o comando é recusado.

## Perguntas em aberto
- [x] Q1. As filas rodam em sequência num único run e numa única branch `until/<run>`, ou em paralelo, um run por fila? — Sequencial: um run, um item por vez, uma branch `until/<run>` para aterrissar.
- [x] Q2. Em que ordem as filas são atendidas? — Fila a fila, na ordem em que `cepa plan ready` lista; dentro da fila, a ordem gravada nela.
- [x] Q3. Qual é a forma do comando: flag no `cepa until` existente ou comando novo? — Flag `--all` no comando existente: `cepa until --all --for 8h`, herdando as demais opções.
- [x] Q4. A lista de prontos é lida uma vez na largada ou relida entre itens? — Relida antes de cada item; item que fica pronto durante o run entra no mesmo run.
- [x] Q5. Onde fica o registro do run e como `decide`/`land` o endereçam? — Pasta própria `.claude/queues/_all/until/<run>.*`; `pending`, `decide` e `land` aceitam o alvo `all/<run>`.
- [x] Q6. O que acontece com uma fila que já tem um run vivo dela? — O `--all` pula os itens dessa fila enquanto o outro run estiver vivo e avisa.
- [x] Q7. O painel de largada (tarefas que esperam o dono) é um só para todas as filas? — Sim: um painel único na largada, agrupado por fila; um "sim" faz o item rodar neste run.
- [x] Q8. O limite de itens `blocked` seguidos vale por fila ou para o run inteiro? — Por fila: `--max-blocked` seguidos tiram a fila do run e ele segue nas outras. `--max-failures` continua encerrando o run inteiro.

## Decided without asking
- Ao reler os prontos entre itens, o run pega sempre o primeiro pronto na ordem do `ready`, inclusive se ele surgir numa fila anterior à atual. Consequência direta de Q2 + Q4. Vete aqui se discordar.
- Filas `parallel-waves` do `/maestro:program-plan` ficam de fora, como já ficam do `cepa plan ready`. Vete aqui se discordar.
- Enquanto um `--all` está vivo, `cepa until <fila>` de qualquer fila é recusado (CS-8): o `--all` pode chegar a qualquer fila a qualquer momento, por causa da releitura de Q4. Vete aqui se discordar.
- Sem item pronto em nenhuma fila e sem "sim" no painel, o run sai com 0 sem criar branch, como o `cepa until <fila>` já faz com fila vazia. Vete aqui se discordar.
- A análise do fim do run (`/common:until-review`) e o status no Herdr funcionam sobre o registro `all/<run>` como sobre o de uma fila. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- Uma fila chamada literalmente `all` ficaria ambígua com o alvo `all/<run>`. Hoje nenhuma fila do repo tem esse nome; a especificação não reserva o nome no `/common:queue`.
- Uma fila que trava (CS-5) sai só deste run. O próximo `--all` volta a tentá-la.
