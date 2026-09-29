# Revisão 3 do fim do `cepa-until`: o próprio card volta com o recado

Data: 2026-09-28. Revisa a "Revisão 2: o vermelho se resolve sem o dono" de
`docs/estrategia-fim-do-cepa-until.md` (linhas 349-439). Item da fila: `cepa/until-fim-sem-dono`.

A Revisão 2 passou pelo painel de 7 lentes em 2026-09-28 (síntese em
`.claude/programs/cepa/advisors-until-fim-revisao2-sintese.md` do clone principal, fora do git).
O painel achou dois defeitos que derrubam o "zero intervenção" no caso mais comum, e o dono
aprovou as correções abaixo no mesmo dia: devolver o próprio card com o recado e teto de duas
voltas, escrever o segundo build como exceção assumida, guardar cópia antes de apagar a lateral
e escrever esta revisão com critério de aceite e teste vermelho por passo.

**Esta revisão substitui**, da Revisão 2: o item `FIX-<teste>` criado no vermelho duplo, o
cherry-pick da lateral feito pelo supervisor antes do agente, a frase "a regra green-or-revert é
cumprida ao pé da letra" e "o dono não vê nada". Da revisão pós-painel: a tabela de ações do
Caminho 1 (sobra só `aterrissar`, porque `reincorporar` passa a ser do agente do card e
`descartar-lateral` passa a ser do supervisor, com cópia) e o passo 0 da sequência revisada (a
reexecução isolada de um teste não fixa mais nada). **Continuam valendo:** a garantia da C4, o
segundo build completo da Revisão 2 e a C8 como estava (a partir da terceira falha em cards sem
relação, só muda o texto da evidência).

## Os dois defeitos que o painel achou

1. **A fila travava.** A Revisão 2 punha o `FIX-<teste>` com `--antes-de <próximo>`, isto é,
   depois do card bloqueado por ele. O `cepa-plan queue` para no primeiro item `pending` que
   depende de outro ainda não feito (`common/bin/cepa-plan:1025-1030`, parada `bloqueado`), e o
   `cepa-until` pede um item por vez (`queue --max 1`, `cepa-until:400`). O conserto nunca
   rodava, e todo run seguinte parava na largada.
2. **O conserto rodava sem o código que quebrou o teste.** No vermelho duplo, os commits do card
   já estavam na branch lateral (a branch onde o supervisor guarda o trabalho de um item cujo
   build ficou vermelho). O agente do `FIX-<teste>` trabalhava numa base em que o teste passava,
   e não tinha o que consertar.

Os dois somem juntos quando quem conserta é o agente do próprio card.

## A regra nova, depois de um build completo vermelho

1. **Segundo build completo** no mesmo código, como na Revisão 2.
2. **Segundo verde:** o item fecha `done`, e o supervisor grava o evento `verify_repetido_verde`
   no `.jsonl` do run e um evento `build_instavel` no ledger de telemetria
   (`~/.claude/cepa-telemetry/`), com card, run, data e o nome do teste quando o relatório o der.
   Nada disso vira item de fila nesta revisão.
3. **Qualquer outro desfecho do segundo build** (vermelho no mesmo teste, em outro teste, sem
   teste identificável, ou sem tempo na janela para rodar) é uma **volta vermelha**. O
   supervisor leva os commits de todas as tentativas para a lateral (C4), devolve o **próprio
   item** para `pending` com um recado na `evidence` (qual build falhou, o motivo, a lateral com
   os commits, qual volta é esta, e que desabilitar ou apagar teste não conta como conserto) e
   grava o evento `volta_vermelha`. Não nasce item novo nem dependência entre itens, e o
   supervisor não precisa ler relatório de teste para decidir.
4. **O recado chega ao agente.** Quando o item for reservado de novo, o `cepa-plan start`
   imprime a `evidence` anterior. Hoje ele não imprime (`cmd_start`, `cepa-plan:1501`), e o
   recado ficaria no arquivo sem ninguém ler. O agente decide se aproveita a lateral
   (`git cherry-pick` ou `merge` dentro da própria tentativa) ou refaz; nos dois casos, o build
   do supervisor no fim da tentativa julga o resultado.
5. **Teto de duas voltas.** Na segunda volta vermelha do mesmo item, contada nos `.jsonl` da
   fila (sem arquivo novo), o item vai para `blocked`, que é o comportamento de hoje, e entra no
   contador de fila travada (`--max-travados`).
6. **Disjuntor.** Cada volta vermelha conta como uma falha seguida (`--max-falhas`, padrão 3,
   `cepa-until:221`). Um ambiente quebrado (Docker fora, porta presa) deixa todo build vermelho,
   e sem essa regra cada card voltaria para `pending` sem que nenhum contador enxergasse o
   problema: hoje `pending` não alimenta nem o disjuntor nem o contador de fila travada.
7. **A lateral só some com cópia.** No começo de cada run, o supervisor apaga as laterais de
   itens em `done` ou `dropped`, mas antes grava `git format-patch` dos commits que não estão na
   branch da noite em `<run>.laterais/<branch>.patch`, ao lado do `.jsonl`. Se a cópia falhar, a
   branch fica.

## Exceções assumidas

- **À regra 4 do `green-or-revert`**, que manda consertar ou desfazer no vermelho, e não
  repetir: o segundo build é uma exceção pedida pelo dono em 26/09 ("eu não quero ter que fazer
  qualquer intervenção"), e não o cumprimento da regra. O custo dela é a chance de barrar uma
  corrida introduzida pelo card. Se a corrida falha com probabilidade p por build, antes ela era
  barrada com probabilidade p, e agora só se falhar nos dois builds, p². Com p = 1/16, a
  detecção cai de 6,25% (1/16) para 0,4% (1/16 × 1/16 = 1/256). O evento `build_instavel` na
  telemetria é a rede que sobra.
- **Ao "zero intervenção"**, três casos em que o dono ainda aparece: o item que chega à segunda
  volta vermelha (`blocked`); as checagens da C4 que param o run quando a lateral não pode ser
  montada com segurança; e o conflito da herança entre runs, que já para o run hoje
  (`abre_branch_da_noite`, `cepa-until:892`).

## Por que o supervisor não reaproveita a lateral sozinho

O painel se dividiu entre reaproveitar pela `heranca_do_run_anterior` (`cepa-until:841`), o
mecanismo que já leva trabalho inacabado de um run para o seguinte, e refazer. A herança mescla
as branches na **abertura** do run (`abre_branch_da_noite`), antes de qualquer item. Uma lateral
de vermelho mesclada ali poria código que já ficou vermelho embaixo de todos os cards do run, e
não só do dono dela. Por isso a lateral chega ao agente do card como recado, e só a tentativa
dele a carrega.

## Custo, medido (2026-09-28)

Fonte: os 46 `.jsonl` de `wego-acessos-backend/.claude/programs/WEGO/until/`.

- Build completo: 24 eventos `verify` em 6 runs, mínimo 703 s, mediana 958 s, máximo 1254 s.
  Um segundo build custa uns 16 min (958 s ÷ 60 = 16,0).
- Vermelho: 2 de 24 builds, cerca de 8% (2 ÷ 24 = 0,083): WEGO-2320 (26/09) e WEGO-2283
  (28/09). O "3 dos 42 registros" da Revisão 2 veio de `grep -l`, que conta também arquivos que
  só mencionam a palavra (o mesmo grep hoje acha 6 arquivos para 2 eventos).
- **A reserva de tempo não muda.** Pagar 16 min a mais em todo item para um caso de 8% não se
  justifica. Quando o segundo build não cabe na janela, o item entra na regra 3 (volta vermelha)
  e a tentativa seguinte faz o resto.

## Suposições de risco (a confirmar com evidência)

- **S1. O agente do card, com o recado, conserta em vez de repetir o erro.** Evidência hoje:
  nenhuma, porque nenhum item voltou com recado de vermelho. Confirma: nas primeiras voltas
  vermelhas reais, a tentativa seguinte muda o código que o teste cobre (e não o teste) e fecha
  verde. Invalida: duas voltas seguidas com o mesmo teste vermelho em mais da metade dos casos.
- **S2. O segundo build verde é o desfecho comum do vermelho instável.** Evidência hoje: o
  WEGO-2320 falhou num teste de concorrência
  (`CadastroComTagsE2ETest.doisCadastrosSimultaneosComMesmaTagNovaCriamUmaTagSo`); o WEGO-2283
  parece vermelho de código (falhas em testes de tag e de trilha de concessões). Nenhum segundo
  build foi rodado. Confirma ou invalida: a proporção `verify_repetido_verde` ÷ (esse evento +
  `volta_vermelha`) nos primeiros runs com a regra.
- **S3. O agente não "conserta" desligando o teste.** O mesmo risco que o painel viu no
  `FIX-<teste>`, agora no card. Guarda: o recado da regra 3 diz que desabilitar ou apagar teste
  não conta, e o `completion-auditor` continua valendo no fechamento.

## Sequência e critérios de aceite

A sequência do BACKLOG continua, com o passo 4 trocado pelos subpassos 4a-4f abaixo. O passo 0
foi feito em 2026-09-28 (painel e medição acima). Todos os testes são da superfície **cli**: um
`cepa-until` de verdade contra um repo falso e um comando de build falso, no molde de
`tests/test_cepa_until_branch_da_noite.py`.

| # | Critério | Teste vermelho |
|---|---|---|
| 1 | (inalterado) A lateral contém os commits de todas as tentativas do item, com as duas checagens da C4 antes do `reset`. | Item com duas tentativas e build vermelho: a lateral precisa conter os commits das duas. |
| 4a | Build vermelho seguido de segundo build verde fecha o item `done` e grava `verify_repetido_verde` no `.jsonl` e `build_instavel` na telemetria. | Build falso que falha na 1ª chamada e passa na 2ª: espera item `done` e os dois eventos. |
| 4b | Qualquer desfecho do segundo build que não seja verde devolve o item para `pending`, com `evidence` citando a lateral, o motivo e o número da volta, e grava `volta_vermelha`. | Build falso sempre vermelho, um item, `--max-falhas 5`: depois da 1ª volta o item está `pending` e a `evidence` contém o nome da lateral. |
| 4c | `cepa-plan start` imprime a `evidence` anterior de um item que a tem. | Item `pending` com `evidence` "recado X": o stdout do `start` contém "recado X". |
| 4d | Na segunda volta vermelha do mesmo item (contada nos `.jsonl` da fila), o item vai para `blocked`. | Build sempre vermelho, um item: o run termina com o item `blocked` e exatamente dois `volta_vermelha` com o id dele. |
| 4e | Cada volta vermelha conta como falha seguida no disjuntor. | Build sempre vermelho, três itens, `--max-falhas 2`: o run para com motivo `disjuntor` e nenhum item fica `done`. |
| 4f | No começo do run, a lateral de item `done` ou `dropped` só é apagada depois de o patch estar gravado em `<run>.laterais/`; sem patch, a branch fica. | Item `dropped` com lateral não mesclada: espera o `.patch` no disco e a branch apagada. Com o `format-patch` falhando: a branch continua. |
| 2, 3, 5 | Inalterados (estado do run e lista de ações; `aterrissar`; cabeçalho curto). O `aterrissar` passa a oferecer só a própria aterrissagem. | Os do BACKLOG. |

## Fica de fora desta revisão, com recomendação

- **Criar item de conserto a partir da telemetria** (um teste que aparece em `build_instavel` em
  cards sem relação). Recomendo esperar a C8 disparar pela primeira vez com dado real: hoje não
  há nenhum evento de instabilidade gravado, e o painel mostrou que um item de conserto sem
  definição de pronto tende a ser fechado desligando o teste.
