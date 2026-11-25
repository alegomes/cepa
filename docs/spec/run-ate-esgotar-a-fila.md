# Especificação: `cepa run` até a fila esgotar, sem prazo

**Status:** ready-to-build
**Aberta em:** 2026-11-25            **Fechada em:** 2026-11-25
**Fontes lidas:** common/bin/cepa-until, docs/estrategia-loops-longos.md, docs/spec/reforma-de-nomes-dos-comandos.md, docs/spec/until-todas-as-filas.md, docs/spec/fim-do-until-sem-espera.md, .claude/queues/cepa-loops-longos/queue.yaml, .claude/queues/cepa-durabilidade/queue.yaml

## Como chegamos aqui
"eu quero ser capaz de rodar o cepa run por um fila até o seu completo esgotamento, independente do tempo que dure. Faz sentido?" (dono, 2026-11-25)

## Problema
Hoje o `cepa run` (o supervisor `common/bin/cepa-until`) recusa largar sem `--for` ou `--until`: o grupo de argumentos da janela é obrigatório. O dono precisa chutar uma duração. Se chuta pouco, a run termina por prazo com item pronto ainda na fila. Na medição de 2026-11-10 (docs/estrategia-loops-longos.md, seção 2), 32 de 98 runs terminaram por prazo.

O prazo também é o limite de três esperas: a espera pelo reset da cota de 5h, a espera pela volta da rede e a folga (`--slack`) depois da qual um item em andamento é morto. Sem prazo, cada uma precisa de regra própria.

## Escopo
### Entra
- Flag `--to-the-end` no `cepa run`, no mesmo grupo obrigatório de `--for` e `--until`: exatamente uma das três por largada.
- Na run sem prazo, o fim é a fila sem item executável. Itens que esperam o dono ficam listados no fim, como hoje.
- Na run sem prazo, os disjuntores de 3 falhas seguidas e de 3 itens travados seguidos ficam desligados. O item que esgota as tentativas sai `blocked` e a run segue para o próximo item que não depende dele.
- Teto de 5h da conta: a run sem prazo sempre espera o reset anunciado. Três cortes seguidos sem item avançar entre eles continuam encerrando a run com `limite-de-uso`.
- Teto semanal da conta: a run termina com o motivo novo `limite-semanal`.
- Queda de rede: a run sem prazo espera a rede voltar sem limite de quedas.
- Flag `--item-ceiling DURATION` (padrão 3h), válida só com `--to-the-end`: a tentativa que passa do teto é morta e conta como falha do item.
- `cepa run --all --to-the-end`: todas as filas, sem prazo.
- Os leitores do registro da run (`cepa run digest`, `cepa run pending`, a recusa de segunda largada) passam a aceitar run sem prazo.
- `cepa run --help` e docs/cepa-until.md descrevem a flag nova.

### Não entra
- Dormir esperando resposta do dono: o painel de 2026-11-10 decidiu contra processo dormindo, e o dono confirmou em Q1.
- Esperar o reset do teto semanal: o supervisor não lê a data desse reset com segurança (Q3).
- Reabastecer a fila de dentro da run (caminho P2 de docs/estrategia-loops-longos.md): é outro assunto.
- Mudar o comportamento de runs com `--for` ou `--until`: disjuntores, folga e reserva continuam iguais nelas.
- Canal de aviso ao dono (push, Slack): fora, pelo mesmo painel.

## Estado e migração
- O evento `run_start` e o `estado.json` gravam `prazo: null` e `sem_prazo: true` na run sem prazo. Registros antigos não mudam.
- Todo leitor que hoje faz `datetime.fromisoformat(prazo)` precisa tratar `null`: a detecção de run viva na largada (common/bin/cepa-until, linhas 7243 e 7259), a detecção de supervisor morto sem pid (linha 6687) e o `cepa run digest` (common/bin/cepa-until-digest, linha 366).
- Motivo de fim novo no conjunto fechado: `limite-semanal`. Motivo de fim de tentativa novo: `teto-do-item`.
- Nenhuma migração de dado existente.

## Critérios de sucesso

### CS-1: `cepa run <fila> --to-the-end --dry-run` imprime o plano de uma run sem prazo e sai com 0, e largar sem nenhuma das três flags de janela continua recusado
**Surface:** cli
**Red test:** num repo de teste com a fila `a` (1 item pronto), `cepa run a --to-the-end --dry-run` sai com 0 e a saída contém "no deadline"; `cepa run a --dry-run` sai com 2; `cepa run --help` lista `--to-the-end`. Hoje o primeiro comando sai com 2 porque o argumento não existe.

### CS-2: a run sem prazo executa todos os itens prontos e termina com o motivo `end-of-queue`
**Surface:** cli
**Red test:** fila `a` com 2 itens prontos e um `claude` falso que commita e fecha cada item como `done`; `cepa run a --to-the-end` termina com os dois itens `done`, o `run_end` do registro traz o motivo `end-of-queue` e o `run_start` traz `prazo` nulo e `sem_prazo` verdadeiro. Hoje o comando é recusado.

### CS-3: na run sem prazo, falhas seguidas não encerram a run
**Surface:** cli
**Red test:** fila `a` com 4 itens independentes; o `claude` falso falha todas as tentativas dos 3 primeiros e fecha o quarto como `done`; `cepa run a --to-the-end` termina com os 3 primeiros `blocked`, o quarto `done` e o motivo `end-of-queue`, sem `disjuntor` nem `fila-travada` no registro. Hoje o comando é recusado, e com `--for 1h` a run termina em `disjuntor` antes do quarto item.

### CS-4: na run sem prazo, o corte pelo teto de 5h sempre espera o reset e retoma o mesmo item
**Surface:** cli
**Red test:** o `claude` falso imprime "limit reached · resets <hora daqui a 1 minuto>" na primeira tentativa e fecha o item como `done` na segunda; com `CEPA_UNTIL_MARGEM_RESET=0`, `cepa run a --to-the-end` grava o evento `limite_de_uso` com `espera` verdadeiro e termina com o item `done`. Hoje o comando é recusado.

### CS-5: o teto semanal encerra a run com o motivo `limite-semanal`
**Surface:** cli
**Red test:** o `claude` falso imprime "You've hit your weekly limit · resets Nov 30, 4pm"; `cepa run a --to-the-end` termina com o motivo `limite-semanal` no `run_end` e o item continua `pending`. Hoje o comando é recusado, e com `--for 1h` o motivo gravado é `limite-de-uso`.

### CS-6: três cortes seguidos pelo teto de 5h, sem item avançar entre eles, encerram a run sem prazo
**Surface:** cli
**Red test:** o `claude` falso imprime o corte de 5h com reset daqui a 1 minuto em toda tentativa; com `CEPA_UNTIL_MARGEM_RESET=0`, `cepa run a --to-the-end` termina com o motivo `limite-de-uso` depois do terceiro evento `limite_de_uso`. Hoje o comando é recusado.

### CS-7: na run sem prazo, a queda de rede é esperada sem limite de quedas
**Surface:** cli
**Red test:** com `CEPA_UNTIL_SONDA_REDE` apontando para uma porta local fechada e o `claude` falso saindo com erro de rede 4 vezes seguidas, abrir a porta faz `cepa run a --to-the-end` retomar o mesmo item e fechá-lo como `done`, sem o motivo `sem-rede` no registro. Hoje o comando é recusado, e com `--for 1h` a run termina em `sem-rede` na terceira queda.

### CS-8: a tentativa que passa de `--item-ceiling` é morta, conta como falha do item e a run segue
**Surface:** cli
**Red test:** fila `a` com 2 itens independentes; o `claude` falso dorme 60s no primeiro e fecha o segundo como `done`; `cepa run a --to-the-end --item-ceiling 0.05m --attempts-per-item 1` grava `item_end` do primeiro com `motivo_fim` igual a `teto-do-item`, deixa o primeiro `blocked` e o segundo `done`. Hoje o comando é recusado.

### CS-9: `cepa run --all --to-the-end` roda todas as filas sem prazo
**Surface:** cli
**Red test:** filas `a` e `b`, cada uma com 1 item pronto, e o `claude` falso que fecha como `done`; `cepa run --all --to-the-end` termina com os dois itens `done` e os dois commits na mesma branch `until/<run>`. Hoje o comando é recusado.

### CS-10: flags que só fazem sentido com prazo ou que religam disjuntor são recusadas junto de `--to-the-end`, e `--item-ceiling` é recusada sem ela
**Surface:** cli
**Red test:** `cepa run a --to-the-end` combinado com cada uma de `--for 1h`, `--slack 30m`, `--min-reserve 10m`, `--max-failures 3` e `--max-blocked 3` sai com 2 e a mensagem cita a flag recusada; `cepa run a --for 1h --item-ceiling 1h` sai com 2 citando `--item-ceiling`. Hoje todas saem com 2 por argumento desconhecido, sem citar a combinação.

### CS-11: os leitores do registro aceitam uma run sem prazo
**Surface:** cli
**Red test:** com um `*.estado.json` de run sem prazo (`prazo` nulo) em estado `rodando` e pid vivo na fila `a`: `cepa run a --for 1h` sai com 2 citando a run viva; `cepa run pending` sai com 0; `cepa run digest <run>.jsonl` imprime "prazo: sem prazo". Hoje o primeiro comando falha em `datetime.fromisoformat` ao ler o prazo nulo.

## Perguntas em aberto
- [x] Q1. O que é "esgotamento": a run termina quando não sobra item executável (os que esperam o dono ficam listados no fim), ou ela dorme esperando as respostas do dono até todo item estar fechado? — Termina quando não sobra item executável; os que esperam o dono ficam listados no fim (dono, 2026-11-25).
- [x] Q2. Forma do comando: flag explícita no lugar de `--for`/`--until`, ou a ausência das duas já significa "sem prazo"? — Flag explícita, no mesmo grupo de `--for`/`--until`; largar sem nenhuma das três continua sendo erro (dono, 2026-11-25).
- [x] Q3. Teto de uso da conta: sem prazo, a run espera todo reset de 5h. E o teto semanal, cujo reset pode estar a dias: espera ou para? — Espera todo reset de 5h; no teto semanal para, com motivo próprio (dono, 2026-11-25).
- [x] Q4. Os disjuntores que não dependem do relógio (3 falhas seguidas, 3 itens travados seguidos) continuam encerrando a run sem prazo? — Desligam: a run sem prazo só para quando a fila esgota; item que falha é pulado e a run segue (dono, 2026-11-25).
- [x] Q5. Queda de rede: sem prazo, a run espera a rede voltar sem limite, ou mantém o corte de 3 quedas seguidas sem progresso? — Espera sem limite (dono, 2026-11-25).
- [x] Q6. Teto de tempo por item: hoje um item em andamento só é morto quando passa do prazo mais a folga. Sem prazo, um item pendurado rodaria para sempre. Qual é o teto por item? — 3h por tentativa, flag `--item-ceiling`; passou disso a tentativa é morta e conta como falha do item (dono, 2026-11-25).
- [x] Q7. `cepa run --all --to-the-end` (todas as filas, sem prazo) entra nesta especificação? — Entra (dono, 2026-11-25).
- [x] Q8. O corte de 3 esperas seguidas pelo reset de 5h sem progresso entre elas continua encerrando a run? — Continua (dono, 2026-11-25).

## Decided without asking
- A pasta da run e a branch continuam `.claude/queues/<fila>/until/` e `until/<run>` — é o que docs/spec/reforma-de-nomes-dos-comandos.md (CS-2) fixou. Vete aqui se discordar. · mantida em 2026-11-25
- A flag se chama `--to-the-end` — foi o nome mostrado na opção que o dono escolheu em Q2, e as flags do `cepa run` são em inglês. Vete aqui se discordar. · mantida em 2026-11-25
- `--max-failures` e `--max-blocked` são recusadas junto de `--to-the-end`, em vez de religarem o disjuntor — o dono respondeu "desligam" em Q4, e recusar evita uma run sem prazo que para por um motivo que a flag principal nega. Vete aqui se discordar. · mantida em 2026-11-25
- `--slack` e `--min-reserve` são recusadas junto de `--to-the-end` — as duas medem distância até um prazo que não existe. Vete aqui se discordar. · mantida em 2026-11-25
- `--item-ceiling` vale só com `--to-the-end` — nas runs com prazo, a folga já é o teto do item, e esta especificação não muda essas runs. Vete aqui se discordar. · mantida em 2026-11-25
- Na run sem prazo, o item que sai `blocked` não encerra o lote: a run segue para o próximo item que não depende dele, e os dependentes ficam `pending`, listados no fim — consequência de Q4; sem isso o primeiro `blocked` encerraria a run. Vete aqui se discordar. · mantida em 2026-11-25
- O fim da run sem prazo não muda: pouso automático, análise final e o painel que espera 600s por resposta do dono rodam como hoje — as checagens "cabe na janela" passam sempre quando não há prazo. Vete aqui se discordar. · mantida em 2026-11-25
- O motivo novo `limite-semanal` vale só para a run sem prazo; runs com prazo continuam gravando `limite-de-uso` — o escopo exclui mudar runs com prazo. Vete aqui se discordar. · mantida em 2026-11-25
- A tela da run sem prazo mostra tempo decorrido no lugar da barra de janela — não há fração de janela para desenhar. Vete aqui se discordar. · mantida em 2026-11-25

## Riscos e o que ficou de fora desta especificação
- Com os disjuntores desligados, um defeito sistêmico (build quebrado, hook recusando tudo) faz a run tentar cada item da fila até esgotar as tentativas de todos. O gasto máximo é itens × tentativas por item × 3h de teto. Quem limita é a cota de 5h e o corte de 3 esperas seguidas (CS-6).
- O teto de 3h por tentativa vem de um único caso registrado no código (item de 95 min, comentário em common/bin/cepa-until perto da linha 371). 3h ÷ 95 min = 1,9 vez de folga. Se itens legítimos passarem disso, o padrão sobe.
- Reconhecer o teto semanal depende do texto que o `claude` imprime (data antes da hora no reset, ou a palavra "weekly"). Se o texto mudar, a run cai no ramo "sem hora de reset" e precisa terminar do mesmo jeito, sem dormir.
- A medição de 2026-11-10 mostra que 44 de 98 runs terminaram por fila vazia antes do prazo. Esta especificação não melhora essas runs; ela mira as 32 que terminaram por prazo.
