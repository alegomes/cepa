# Painel de advisors: Revisão 2 do fim do `cepa-until` (2026-09-28)

Artefato: `docs/estrategia-fim-do-cepa-until.md`, seção "Revisão 2: o vermelho se resolve sem o
dono" (linhas 340-430). Área: arquitetura. 7 lentes isoladas (5 fixas + operador-sre +
custo-de-manutencao). 64 achados: 8 críticos, 27 altos, 23 médios, 6 baixos (contagem somando o
campo `severidade` dos 7 JSONs; run `wf_081e2b30-d2c`). Passo 0 do item `until-fim-sem-dono`.

## Vereditos por lente

- **contrarian:** repetir o build está certo; o caminho "vermelho duas vezes" trava a fila, cria um
  FIX que não reproduz a falha e gira sem teto. A chance de pegar uma corrida cai de p para p².
- **fundamentalista:** quebra quatro princípios em silêncio (regra 4 do green-or-revert, supervisor
  que não escreve a fila, nenhum card começa sobre código não verificado, D3) e diz cumprir dois.
- **expansionista:** o mecanismo certo no lugar errado: repetir o build deveria ser do executável de
  build (o `aterrissar` também tropeça no teste instável) e a lateral deveria usar a herança entre
  runs que já existe.
- **outsider:** a ideia se entende, a decisão não se reconstrói: respostas que não batem com as
  perguntas, sequência velha, campo e comando que não existem, ramos de falha ausentes.
- **executor:** executável na ideia, não na segunda-feira: fila trava, falta subcomando para
  reabrir item com `blocked_by`, FIX sem definição de pronto.
- **operador-sre:** só os dois desfechos felizes têm roteiro; ambiente caído vira enxurrada de FIX
  sem acionar disjuntor; "o dono não vê nada" também tira a visibilidade.
- **custo-de-manutencao:** os passos 1, 2 e 5 pagam o que custam; FIX com bloqueio cruzado,
  lateral viva entre runs e registro novo põem três conceitos permanentes para um caso que ainda
  não aconteceu. Alternativa mais simples: devolver o próprio item com a evidência.

## Convergências (independentes)

1. **A fila trava** (contrarian, fundamentalista, executor; crítico). `--antes-de <próximo>` põe o
   FIX depois do card bloqueado, e `seleciona_lote` faz `break` com `bloqueado`
   (`cepa-plan:1025-1030`, conferido); o `cepa-until` pede `--max 1` (`cepa-until:400`). Todo run
   seguinte para na largada.
2. **O FIX roda sem o código que quebrou o teste** (contrarian, operador-sre; crítico). No vermelho
   duplo os commits do card foram para a lateral; o FIX não reproduz, fecha sem commit ou
   `blocked`, e o card volta vermelho.
3. **Colisão do id `FIX-<teste>`** (contrarian, outsider, executor, operador-sre, custo). Dois
   gatilhos criam o mesmo id; `add` recusa id existente; não há teto de voltas card → FIX → card.
4. **Ramos sem desfecho** (contrarian, outsider, executor, operador-sre, custo): vermelho em outro
   teste, vermelho sem teste (compilação, tempo), segundo build sem janela.
5. **FIX sem definição de pronto** (contrarian, fundamentalista, outsider, executor): build verde
   não prova teste estável; o caminho mais barato do agente é desligar o teste.
6. **`cepa-plan` não sabe reabrir item com `blocked_by` nem guardar a lateral** (contrarian,
   outsider, executor, operador-sre).
7. **Cherry-pick da lateral sem regra de conflito** (contrarian, fundamentalista, outsider,
   executor, operador-sre, expansionista, custo). Fundamentalista acrescenta: reabre a A5, porque
   devolve código vermelho à branch da noite antes de qualquer build.
8. **Apagar a lateral sem arquivar** (contrarian, fundamentalista, executor, operador-sre):
   contradiz D3. Proposta comum: `git format-patch` ao lado do `.jsonl` antes do `branch -D`.
9. **"O restante da revisão pós-painel continua valendo" é falso**: C8 (3ª → 2ª aparição),
   tabela de ações do Caminho 1 (`reincorporar`, `descartar-lateral`) e passo 0 da sequência
   mudaram sem ser listados (fundamentalista, outsider, executor, custo).
10. **Disjuntor "como hoje" está errado**: item devolvido a `pending` não alimenta nem o contador
    de falhas nem o de fila travada (fundamentalista, outsider, operador-sre).
11. **Custo: reserva de dois builds em todo item** para um caso raro, estimada com uma medição só
    (contrarian, outsider, executor, operador-sre, expansionista, custo).

## Discordâncias nomeadas

**D-A. O que fazer no vermelho duplo.**
- *custo-de-manutencao:* não criar item novo; devolver o próprio card a `pending` com a evidência
  ("teste X vermelho duas vezes; commits em Y"), e o agente do próximo run conserta. Um gatilho só
  de FIX (o de instabilidade), sem bloqueio cruzado.
- *expansionista:* o supervisor escrevendo na fila é uma categoria nova (quarto escritor) e deve ser
  assumida como tal, com `origem: supervisor` e prefixo fixo, porque destrava outros casos.
- **O que decide:** quem melhor conserta um vermelho determinístico. Se é o card que quebrou o
  teste (o caso mais provável de vermelho duplo, segundo contrarian e operador-sre), quem conserta é
  o agente do próprio card, com o código dele na base, e isso resolve as convergências 1, 2, 3 e 6
  de uma vez. **Recomendação do sintetizador: custo-de-manutencao**, com teto de voltas. A
  categoria do expansionista fica para quando houver um segundo caso real de escrita pelo
  supervisor.

**D-B. Reaproveitar a lateral ou refazer.**
- *expansionista:* reaproveitar, mas pela `heranca_do_run_anterior` (`cepa-until:841-889`), não
  por um segundo mecanismo.
- *custo-de-manutencao:* não reaproveitar; refazer do zero, com o recado apontando a lateral.
- *fundamentalista:* se reaproveitar, desfazer pelo caminho do `desfaz_item` quando não fechar verde.
- **O que decide:** se a herança existente já cobre "item volta a `pending` com commits numa
  branch". Se cobre com mudança pequena, a herança vence (um mecanismo só). Falta ler
  `heranca_do_run_anterior` para saber; é o primeiro passo técnico.

**D-C. Onde fica o registro de instabilidade.**
- *expansionista:* no ledger de telemetria (`~/.claude/cepa-telemetry/`), lido pelo `cepa-metrics`.
- *custo-de-manutencao:* nenhum arquivo novo; derivar dos `.jsonl` dos runs.
- **O que decide:** se algum consumidor fora do `cepa-until` precisa da contagem. O `aterrissar`
  precisa (expansionista). **Recomendação: telemetria**, que já é compartilhada; não é arquivo novo.

**D-D. O segundo build é "green-or-revert ao pé da letra"?**
- *documento:* sim. *fundamentalista e contrarian:* não; a regra 4 manda consertar ou desfazer, e
  repetir reduz a detecção de uma corrida de p para p² (p = 1/16: 6,25% → 1/256 ≈ 0,4%).
- **O que decide:** nada técnico; é o dono aceitar a troca. **Recomendação:** reescrever como
  exceção explícita à regra 4, autorizada em 26/09, com o p² escrito.

## Propostas consolidadas, priorizadas

1. Vermelho duplo (qualquer motivo) devolve o próprio card a `pending` com a evidência; sem
   `FIX-<teste>` nesse caminho. Teto: na 2ª volta vermelha o card vai para `blocked` e alimenta o
   contador de fila travada (exceção nomeada ao "zero intervenção"). [D-A; contrarian, executor,
   operador-sre, custo]
2. Qualquer desfecho fora de "segundo build verde" entra no ramo do item 1; cada ramo grava um
   evento com nome próprio no `.jsonl`. [convergência 4]
3. Reescrever o passo 2 como exceção à regra 4 do green-or-revert, com a conta p → p². [D-D]
4. Arquivar `git format-patch` ao lado do `.jsonl` antes de apagar qualquer lateral. [conv. 8]
5. `FIX-<teste>` só pelo gatilho de instabilidade, com pronto definido (N execuções isoladas
   verdes e diff que não desliga nem apaga o teste) e reuso do item se ele já existir. [conv. 3, 5]
6. Listar no texto tudo que a Revisão 2 substitui: C1, D4, C8, a tabela do Caminho 1 e o passo 0.
   [conv. 9]
7. Reserva de tempo: manter a atual; quando o segundo build não couber, cair no item 1. [conv. 11]
8. (Condicional a D-B) retomada pela `heranca_do_run_anterior`.
9. (Condicional a D-C) registro de instabilidade como evento de telemetria.

## Medição do passo 0 (sem rodar build)

Fonte: 46 `.jsonl` em `wego-acessos-backend/.claude/programs/WEGO/until/`.
- 24 eventos `verify` em 6 runs: mínimo 703 s, mediana 958 s, máximo 1254 s. Um segundo build
  custa uns 16 min (958 s ÷ 60).
- 2 vermelhos em 24 builds, cerca de 8% (2 ÷ 24 = 0,083): WEGO-2320 (26/09) e WEGO-2283 (28/09).
  O "3 de 42" do documento veio de `grep -l`, que também conta arquivos que só mencionam a palavra
  (hoje dá 6 arquivos para 2 eventos).
- O vermelho do WEGO-2283 mostra falhas em testes de tag e trilha: parece código, não instabilidade.
- A reexecução isolada do `CadastroComTagsE2ETest` não foi medida: a worktree de 26/09 foi removida,
  e a Revisão 2 trocou a reexecução isolada pelo build completo.
