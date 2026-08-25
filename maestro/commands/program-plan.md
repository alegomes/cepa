---
description: Planeja um programa do Maestro — conversa sobre um universo de demandas (default BACKLOG.md), propõe ondas de slices com superfícies disjuntas e fork points, escreve .claude/programs/<nome>/plan.yaml (schema v2, canônico em common/plan-schema.yaml; v1 segue lida sem migração) e roda o intake gate (cepa-dor) até cada slice sair READY ou ter a lacuna nomeada. Não executa nada — /maestro:run (passo 3 da construção) é quem forka. Piso de uso: ≥4 demandas (D7); com menos, /board-flow:drain ou sessão única ganham. Com --sweep, varre a fonte INTEIRA em vez de uma lista de demandas escolhida a dedo e propõe as próximas 2-3 ondas sozinho. Com --from-plan NOME, a fonte é a fila `single-track` do repo (.claude/programs/NOME/plan.yaml) em vez de um arquivo de prosa — é a promoção fila → ondas, e a resposta a "como uso o program-plan num projeto com Jira", já que a fila aceita o Jira como fonte e o --source não.
argument-hint: [nome-do-programa] [--source ARQUIVO] [--demandas "P9,P10,..."] [--sweep] [--from-plan NOME]
interaction: conversational
---

# /maestro:program-plan

## Purpose

Transformar "quero tocar estas N demandas em paralelo" num plan.yaml que o
motor consegue executar sem mediação improvisada. O v0 (melhorias-2026-07)
provou o formato e pagou uma lição: dois slices tocaram o mesmo arquivo porque
a superfície não era declarada nem checada — 1 conflito real de merge. Este
comando existe para que TODO plano nasça com superfícies declaradas, disjuntas
e verificadas mecanicamente antes de qualquer fork.

**Invariante de costura:** `/maestro:run` lê exclusivamente o plan.yaml. Este
comando é o único lugar onde BACKLOG.md (ou outra fonte) é interpretado.

**Modo `--sweep`:** em vez de uma lista de demandas escolhida a dedo, varre a
fonte inteira e PROPÕE quais entram nas próximas ondas — ninguém hoje lê os
109 títulos do backlog inteiro e devolve "isto dá para rodar em paralelo sem
se atropelar" (docs/spec/planejador-de-lotes-paralelos.md, CS-1). Ainda é
proposta, igual ao modo normal: entra na conversa do passo 3, nunca grava o
plano sozinho. As diferenças ficam marcadas nos passos abaixo com o rótulo
`sweep` mais um identificador em negrito e colchetes — o identificador é usado
por `common/bin/cepa-promptcov` para cruzar contra a trava de regressão
(`tests/test_program_plan_sweep.py`) e apontar peça sem cobertura; ver
docs/promptcov.md.

**Modo `--from-plan NOME`:** a fonte é a fila `single-track` que já existe no
repo (`<raiz-principal>/.claude/programs/NOME/plan.yaml`), escrita pelo
`/common:plan` a partir de uma spec, de uma triagem de Jira ou ditada à mão.
É a etapa 4 do desenho "um escritor, três fontes" (BACKLOG.md, "Cinco portas
de planejamento") e a única promoção que faltava: fila → ondas era declarada
manual em `docs/execution-plan.md` por não haver caminho. Também é a resposta a
*"como uso o program-plan num projeto com Jira"* — o `--source` só aceita
arquivo, e a fila aceita o board como fonte.

Quem lê a fila é `common/bin/cepa-plan promote`, não esta prosa. A regra de
quem pode virar slice mora no código pelo mesmo motivo das etapas 1 e 2: um
parágrafo que manda "promova só os `pending`" só pode ser provado por um grep
nele mesmo, que mostra a PROMESSA e nunca a execução. Os blocos anotados com a
família `from-plan` abaixo dizem o que fazer com o que o script devolve — a
mesma convenção do `--sweep`, medida pelo `cepa-promptcov`.

## Steps

1. **Fonte e universo.** Leia a fonte (`--source`, default `BACKLOG.md`) e
   identifique as demandas candidatas (as passadas em `--demandas`, ou as que
   o usuário descrever). Menos de 4 demandas → pare e diga que o piso (D7) não
   foi atingido; recomende /board-flow:drain ou sessão única.

   **[sweep:full-source]** Leia a fonte INTEIRA, do início ao fim — não só o trecho que o
   usuário apontou. Descarte o que já tem `Status: FEITO/CONSTRUÍDO/✅` ou já
   pertence a um plano existente (um `plan.yaml` em
   `<raiz-principal>/.claude/programs/*/`); entre o resto, pare nas próximas
   **2-3 ondas** (não tente particionar o backlog inteiro de uma vez — é
   hipótese, revalidada por sessão). Prefira demandas
   cuja superfície fica FORA da zona de enforcement do cepa-dor (`.claude/
   settings*`, `.claude-plugin/*`, `*/hooks/*`, `*/plugins/*`) — o intake veta
   essa zona incondicionalmente, então uma demanda cujo trabalho real é editar
   um hook não é candidata a fork autônomo; nomeie isso ao usuário e sugira
   sessão supervisionada em vez de forçar a onda.

   **[from-plan:source]** Com `--from-plan NOME`, não leia `BACKLOG.md`: rode

   ```
   python3 common/bin/cepa-plan promote <NOME> --repo . --json
   ```

   e trate `demands[]` como o universo — na ORDEM em que vêm, que é a ordem da
   fila. O que ficou de fora vem em `excluded[]` com o motivo por item
   (`done`/`dropped` já saíram da fila, `in_progress` está reservado por outra
   sessão, `blocked` travou num run anterior); **mostre essa lista ao usuário**
   em vez de calar — um item que ele espera ver na onda e não aparece é a
   pergunta que ele vai fazer, e a resposta já está no JSON. O piso D7 é
   mecânico aqui: **exit 4 = pare** e recomende `/common:drain-plan <NOME>`,
   que executa a mesma fila em série, sem worktree nenhuma. Exit 3 = o nome
   aponta para um plano de ondas, não para uma fila.

2. **Análise por demanda** (leitura do repo, sem escrever nada):
   - **superfície**: quais arquivos/globs a demanda realisticamente toca —
     derive do texto da demanda + grep/glob no código; na dúvida, declare o
     glob mais largo e honesto;
   - **dependências** entre demandas (uma cria o que a outra consome → ondas
     diferentes, `fork_after`);
   - **gate humano**: existe decisão estratégica em aberto (escopo, contrato,
     naming user-facing, breaking change)? Ela precisa ser tomada AGORA, na
     conversa, e registrada no `human_gate` — ou a demanda fica fora da onda;
   - **critério de aceite executável** (`acceptance` + `acceptance_cmd` — o
     repo é `.claude/no-build`, então `acceptance_cmd` é obrigatório);
   - **forma do aceite** (`acceptance_form`): se a demanda só nomeia passos
     privados de implementação — nenhum Given/When/Then observável em alguma
     superfície — ela não é US. Ou o `acceptance` ganha a tripla observável
     (`acceptance_form: bdd`), ou o slice **assume** que é substrato
     (`acceptance_form: substrate`). Sem uma das duas, o intake reprova.

   **[from-plan:carry-why]** O `why` de cada demanda vem pronto da fila e é
   COPIADO, nunca reescrito: ele é o critério que colocou aquele item naquela
   posição, e reescrevê-lo aqui apaga a priorização que a fila existe para
   guardar. Ele vai para o `context:` do slice (ou para o `demanda:`, junto do
   `id`); o que esta conversa acrescenta é o que a fila não tem — superfície,
   aceite e gate humano.

   **[from-plan:human-gate]** Demanda que chega com `human_gate` diferente de
   `none` traz uma rota que só o humano fecha (`human_pending` da fila). Ou a
   decisão é tomada AGORA, na conversa, e o `human_gate` do slice registra o
   que foi decidido — ou o slice fica fora da onda. Não copie o `open:` para o
   plano esperando resolver depois: o `cepa-dor` reprova, e com razão, porque
   forkar uma filha em cima de uma coisa que ninguém validou é construir no
   escuro.

   **[sweep:solo-wave]** Demanda cuja superfície não dá para derivar com confiança
   (prosa vaga demais, ou toca área grande demais para um glob honesto) NÃO
   entra dividindo onda com outras — vai **sozinha para sua própria onda**,
   tratada como se tocasse o repo inteiro. É um custo aceito conscientemente:
   cada demanda assim consome uma onda inteira; se o varrimento produzir muitas
   ondas de uma slice só, esse é o sintoma a reportar ao usuário, não a
   esconder forçando um glob dúbio.

3. **Proposta de ondas.** Agrupe slices de superfícies disjuntas na mesma onda
   (teto `max_concurrent_slices`, default 3); dependências e decisões pesadas
   empurram para ondas posteriores. Apresente a proposta ao usuário em tabela
   (onda · slice · demanda · superfície · gate humano · aceite) e discuta.

   **[from-plan:deps-to-waves]** Com `--from-plan`, o `onda_minima` de cada
   demanda é PISO, não sugestão: ele sai do `blocked_by` da fila, e dois itens
   em que um depende do outro não podem forkar na mesma onda mesmo que as
   superfícies sejam disjuntas — a filha de baixo forkaria antes de existir o
   que ela consome. Agrupe por superfície DENTRO do piso, nunca por cima dele,
   e use `fork_after: "wave-<N-1>"` na onda N. Um item pode subir de onda
   (superfície colidiu, teto cheio); descer, nunca.

   **[sweep:wave-cap]** O teto de slices por onda não é fixo em 3 — **sugira** o teto
   observando os arquivos-cartório medidos (passo 4): quanto mais concentrados
   os conflitos em poucos arquivos, menor o teto seguro; repo sem cartório
   claro sustenta onda maior. Proponha o número ao usuário com o porquê, não
   grave sem revisão.

4. **Escrever o plano.** Antes de gravar qualquer byte, confira que o nome
   está livre:
   ```
   python3 maestro/bin/maestro-programs . --check-name <nome>
   ```
   **Exit 3 = pare.** Aquele caminho já guarda a fila `single-track` de um board
   (é o `/board-flow:triage` que a escreve, um plano por board) e gravar ondas
   por cima apaga a ordem dos itens e o `why` de cada um — o dado que o plano
   existe para guardar, e que o Jira não tem. Mostre a mensagem ao usuário e
   peça outro nome; não invente um sufixo por conta própria. Exit 0 com aviso de
   "nome ocupado por um plano parallel-waves" é o caso normal de replanejar as
   ondas do mesmo programa: siga.

   **[from-plan:other-name]** Com `--from-plan NOME`, o `--check-name <NOME>`
   dá exit 3 SEMPRE — `NOME` é a fila, e é dela que as demandas vieram. Isso é
   o mecanismo funcionando, não um erro a contornar: gravar as ondas ali
   apagaria a fila que acabou de ser promovida. O plano de ondas precisa de um
   nome PRÓPRIO, e quem escolhe é o usuário — não invente um sufixo por conta
   própria (`NOME-ondas` parece inofensivo e vira um segundo documento que
   ninguém sabe de onde veio). Peça, e rode o `--check-name` de novo com o nome
   escolhido.

   **[from-plan:traceable-source]** Grave em `source:` a linha que o
   `cepa-plan promote` devolve em `source` — ela diz de qual fila, de qual
   caminho e quantos itens dos quantos vieram, e é a outra ponta do fio que o
   `demanda:` de cada slice (o `id` do item) começa. Sem ela o plano de ondas
   nasce órfão: meses depois ninguém sabe de que fila aquele slice saiu, nem em
   que estado ela estava quando foi promovida.

   Com o desenho acordado e o nome liberado, escreva
   `<raiz-principal>/.claude/programs/<nome>/plan.yaml` seguindo
   `common/plan-schema.yaml` (`schema_version: 2`, `mode: parallel-waves`). Um
   slice por demanda, salvo demanda grande que o usuário concorde em fatiar. O `mode` é explícito porque
   o mesmo schema também serve o `single-track` do board-flow — é o campo que
   diz a quem lê qual dos dois este plano é. Planos v1 no disco (sem `mode`)
   continuam válidos e **não precisam ser migrados**.

   **`<raiz-principal>`** é o pai de `git rev-parse --git-common-dir` sem o
   `/.git` final — em worktree ligada isso aponta para o CLONE PRINCIPAL, não
   para a árvore atual; fora dela é o mesmo que `git rev-parse --show-toplevel`.
   O plano é estado do repo, não da sessão: escrito dentro de worktree de
   sessão, morre com ela, e num repo cujo `.gitignore` cobre `.claude/` inteiro
   nenhuma guarda do caminho de remoção enxerga o arquivo. Vale para ler e para
   escrever. Ver `docs/execution-plan.md`, "Where the file lives".

   **[sweep:cartorios]** Antes de escrever, rode `python3 common/bin/cepa-hotspots
   <raiz-principal> --json` e grave a lista `hotspots[].path` no campo novo e
   opcional `cartorios:` no TOPO do plano (irmão de `schema_version`/`mode`,
   documentado em `common/plan-schema.yaml`) — é o dado que o `cepa-dor` usa
   para vetar só a interseção que cai num arquivo-cartório de verdade, em vez
   de qualquer cruzamento. Histórico insuficiente → o script diz isso
   explicitamente; deixe `cartorios:` ausente, não invente a lista.

5. **Intake gate.** Rode:

   ```
   python3 common/bin/cepa-dor <raiz-principal>/.claude/programs/<nome>/plan.yaml --wave 1 --repo .
   ```

   Para cada NOT-READY, corrija COM o usuário (ajustar globs, registrar a
   decisão do human_gate, escrever acceptance_cmd) e rode de novo, até a onda 1
   sair READY (avisos ⚠ são aceitáveis e ficam anotados no plano). Repita para
   as demais ondas se o usuário quiser antecipar.

6. **Encerramento.** Mostre o veredito final do cepa-dor e o caminho do plano.
   Diga explicitamente: a execução é `/maestro:run` (ainda não construído —
   passo 3 da ordem de construção; até lá, o plano serve para as ondas manuais
   com worktrees, como no v0).

## Notes

- Este comando NÃO executa demandas, não cria worktrees, não sobe porteiro.
- **[from-plan:queue-untouched]** Promover não mexe na fila: `cepa-plan promote`
  só lê, e os itens continuam `pending` lá. A fila segue sendo o documento da
  ORDEM; o plano de ondas é uma hipótese sobre um recorte dela. O risco que
  sobra é humano e vale dizer em voz alta ao usuário no encerramento: o mesmo
  item agora tem dois executores possíveis (`/common:drain-plan` e a onda), e
  rodar os dois constrói duas vezes.
- Superfície é promessa de escrita, não de leitura — a filha pode ler o repo
  inteiro; só escreve dentro dos globs (camada 1 das settings geradas).
- A zona de enforcement (plugins/, hooks/, .claude/settings*, plugin-cache) é
  veto incondicional do cepa-dor: nenhum glob de slice pode incluí-la.
- Arquivos de alto atrito não declarados (lockfiles, migrations, index/barrel)
  viram aviso, não veto — o verify pós-merge do merge train é quem pega
  conflito incidental.
- `acceptance_form: substrate` não é escape hatch: é uma **declaração**. Um
  slice de substrato aceita ser verificado por critério técnico porque ninguém
  finge que ele tem superfície observável. Marcar `substrate` numa demanda que
  o usuário enxerga é mentir para o gate — e o gate acredita.
