# Intenção da sessão: as quatro perguntas que o dono quer ter sempre à mão

Status: decidido pelo dono em 2026-10-16, depois do painel `/common:advisors` (síntese no fim).
Pronto para virar itens da fila `cepa`. Data: 2026-10-16.
Base: `common/hooks/session-mode.py`, `common/bin/cepa` (função `write_modo`, linhas 245-261),
`common/hooks/session-next.py`, `common/hooks/session-label.py`, `common/skills/off-mode-capture/SKILL.md`,
`~/.claude/statusline-command.sh`, `common/commands/{recap,next,handoff,session,branch}.md`,
`docs/modos-de-trabalho.md`, `docs/context-forking.md`, `docs/precedencia-de-instrucoes.md`.

## Termos usados neste documento

- **Dono**: o usuário humano do Cepa (Alexandre), que abre as sessões e decide.
- **Agente**: o Claude Code rodando dentro de uma sessão.
- **Sessão**: um processo `claude` aberto pelo launcher `cepa`, numa pasta de trabalho, até ser encerrado.
- **Turno**: um prompt do dono e a resposta do agente a ele.
- **Harness**: o conjunto de hooks, comandos, skills e scripts em `common/` e nos outros plugins deste repo, que disciplina o agente.
- **Modo**: o estado declarado em `cepa --modo <x>` (exploração, construção, reforma...). Dura a sessão inteira; cada modo tem condição de saída fixa em `common/hooks/_modos.py`.
- **Rotina**: um comando que executa uma tarefa inteira e termina (`/board-flow:prove-drain`, `/common:drain-plan`).
- **Programa**: uma fila ordenada de itens em `.claude/programs/<nome>/plan.yaml`, escrita pelo `/common:plan`.
- **Ciclo**: uma rodada de trabalho que entrega algo demonstrável, a unidade de custo deste repo.
- **Hook**: script que o Claude Code roda num evento fixo (todo prompt, toda parada, toda abertura) e que pode injetar texto no contexto do agente ou bloquear.
- **Statusline**: a linha no rodapé do terminal, gerada por `~/.claude/statusline-command.sh`, arquivo pessoal do dono fora do repo.

## A dor, nas palavras do dono

> "Uma situação muito recorrente que acontece comigo é eu perder o raciocínio entre os turnos. Muito provavelmente por estar sempre trabalhando em vários projetos paralelos, administrando mentalmente múltiplos contextos simultâneos."

> "Ao longo da sessão o propósito original vai se perdendo em perguntas que geram novos branches de execução que vão se sobrepondo uns aos outros até chegar num ponto onde o propósito original é esquecido e não se sabe mais qual é o ponto de parada da sessão."

Numa sessão de 2026-10-16 o dono abriu com três perguntas ("o que estamos fazendo aqui?", "onde estamos?", "qual é o próximo passo?"). O resultado foi bom no sentido de que a sessão retomou o fio sem reler o histórico. Ele quer que isso aconteça sem precisar lembrar de perguntar.

As quatro informações que ele quer ter sempre à mão:

1. **O que estamos fazendo?** A intenção da sessão, não só o modo de trabalho.
2. **Qual é o plano?** O caminho traçado para cumprir essa intenção.
3. **Onde estamos em relação ao plano?** A posição no plano do item 2, não "o que a sessão faz agora".
4. **Qual é o próximo passo que devo dar?** O passo que avança o plano do item 2, não o próximo item de uma fila qualquer.

## O que já existe e o que falta

| Pergunta | O que existe | Lacuna |
|---|---|---|
| 1. O que estamos fazendo? | modo e condição de saída, injetados a cada turno por `session-mode.py` e mostrados na statusline | o modo é a categoria ("exploração"); a intenção concreta não está gravada |
| 2. Qual é o plano? | `plan.yaml` quando há programa; as perguntas de largada do `/common:session` quando há rotina | sessão de conversa (exploração, descoberta, reflexão) não tem plano gravado |
| 3. Onde estamos? | `/common:recap` responde "você pediu / eu entreguei" a partir do `session-log.md` | responde ao passado, não à posição num plano |
| 4. Próximo passo? | `/common:next` (fila de programa); seção `## Próximo passo` do handoff (entre sessões) | nenhum conhece o plano desta sessão |

Outras peças que já carregam pedaços de intenção, e que o desenho reaproveita em vez de duplicar:

- `session-next.py` extrai do handoff um `brief` e grava `<session_id>.next.json`; `session-chain.py` abre a sessão seguinte com esse brief como primeiro prompt. O brief é um propósito.
- `session-label.py` guarda uma nota de propósito na descrição do branch, exibida no SessionStart e no `/common:worktree-list`.
- `session-subject.py` roda a cada prompt, detecta mudança de assunto por vocabulário e sugere worktree. O próprio docstring diz que o sinal é ruidoso.
- `/common:branch` e `/common:return` (`docs/context-forking.md`) isolam um ramo de conversa e voltam só com a conclusão. É o mecanismo do repo para "branches que se sobrepõem".
- `cepa-until` chama `claude -p` direto, sem passar pelo `cepa`: o run desatendido não tem modo nem teria intenção. Ali a intenção já existe: é o item do `plan.yaml`.

Conclusão: as quatro perguntas são sobre um objeto só, que o harness não guarda. Este documento o chama de **intenção da sessão**: propósito em uma frase, ponto de parada, plano em passos ordenados e cursor.

## O que NÃO é o problema

- Não é falta de modo. O modo é obrigatório no `cepa` (desenho de 2026-08-18, construído em parte, conferido em 2026-09-19).
- Não é falta de handoff entre sessões. A dor é dentro da sessão, entre turnos.
- Não é falta de um comando que responda. O agente responde bem quando perguntado. O problema é que o dono precisa lembrar de perguntar, e o que ele perde é a memória de que havia algo a perguntar.

## Os caminhos considerados

### C1. Gravar a intenção num arquivo próprio e lembrá-la a cada turno

Um arquivo `.claude/session-intent`, separado do `session-mode`, com propósito, ponto de parada, plano, cursor e histórico. O hook `session-mode.py` injeta propósito e passo atual a cada turno. Um comando `whereami` imprime as quatro respostas. A statusline mostra uma linha pré-renderizada.

Por que arquivo próprio e não campos no `session-mode` (primeira versão deste doc): `write_modo` no `cepa` reescreve o `session-mode` inteiro com `>` a cada lançamento, então a intenção morreria em todo relançamento. Seis leitores (`session-mode.py`, `modo-escrita-gate.py`, `reforma-gate.py`, `cepa-feedback`, `cepa-modos`, statusline) fazem parse linha a linha e nenhum entende lista. E a doutrina do repo é escritor único por artefato (`/common:plan` é "o ÚNICO escritor da fila"; `_modos.py` existe porque três cópias da mesma tabela custaram caro).

### C2. C1 mais nomeação de desvio por passo

O agente, ao receber um prompt que não avança o passo atual, diz isso em voz alta antes de atender ("isto é um desvio do passo 2") e, se o ramo for longo, roteia para `/common:branch`; o `/common:return` devolve o cursor. Generaliza o `off-mode-capture` (desvio de modo) para desvio de passo.

Versão rejeitada: a primeira redação incluía a opção "registro e não atendo". O painel apontou que isso viola a exceção explícita do `off-mode-capture` ("o que o usuário pedir explicitamente neste turno: ele é o dono da fronteira") e a camada 1 de `precedencia-de-instrucoes.md`. O agente nunca deixa de atender um pedido do dono por estar fora do plano.

### C3. Sem arquivo: `whereami` reconstrói do histórico

Lê `session-log.md` e o handoff e pede ao modelo que reconstrua as quatro respostas. Zero mudança em hook ou launcher. Não responde sem o dono perguntar, e a reconstrução deriva junto com a conversa.

### C4. Sem arquivo: o hook injeta os primeiros prompts a cada turno

Proposto pelo painel. Os três primeiros prompts do `session-log.md` são a intenção na voz do dono, antes de qualquer branch. O hook os injeta todo turno. Mais barato que C1 e sem cursor para mentir. Falha quando o primeiro prompt não contém a intenção (`/common:doctor`, "continua", um handoff retomado), que é o caso comum.

## Comparação

| | C1 | C2 | C3 | C4 |
|---|---|---|---|---|
| Responde sem o dono perguntar | sim | sim | não | sim |
| Depende do dono lembrar de perguntar | não | não | sim | não |
| Ataca a sobreposição de branches | o dono vê o cursor | o agente nomeia o desvio | não | não |
| Depende do agente lembrar | de gravar e avançar o cursor (com gatilho no hook) | idem, mais nomear | de nada | de nada |
| Falha típica | cursor parado (visível pela idade) | cursor parado, desvio não nomeado | resposta derivada | primeiro prompt sem intenção |
| Mudança em superfícies existentes | hook, launcher, `_wtlib`, comando novo | as mesmas mais skill | nenhuma | hook |

## Decidido pelo dono em 2026-10-16

Respostas às cinco discordâncias do painel (detalhe na síntese, no fim):

- **D1. Ciclo de vida.** A intenção vive por branch/worktree e sobrevive a relançamento e `/clear`. O arquivo grava `session_id` e `aberto_em`; quando a sessão atual difere da que gravou, o hook injeta "intenção de <data>, gravada em outra sessão: continuo ou abro nova?" em vez de exibi-la como atual.
- **D2. Cursor.** O agente atualiza, rodando `cepa-intencao --passo N` ao concluir um passo. Nenhum mecanismo decide sozinho que um passo acabou. O que torna isso tolerável: o comando é evento observável (telemetria), o hook mostra há quantos turnos o cursor está parado, e o `whereami` confronta o gravado com os últimos prompts do log. O dono pode rodar o comando à mão.
- **D3. C2.** Entra reescrito, sem "não atendo", roteando ramo longo para `/common:branch`. Segundo ciclo.
- **D4. Comando.** `whereami`, nome único, sem alias. `/common:next` ganha fallback para sessão sem programa e `/common:recap` abre com "propósito / passo N de M".
- **D5. Statusline.** Entra como conveniência local, fora das garantias e testes do harness, lendo um campo `resumo:` pré-renderizado. Primeira tarefa: spike de 5 minutos para ver se o Claude Code renderiza duas linhas.

Também decidido, sem discordância no painel:

- A evidência da worktree apagada saiu deste doc. É falha do `worktree-remove-guard.py`, registrada em `.claude/desvios.md` como investigação própria.
- A mitigação no hook de Stop saiu: não há sinal mecânico de "concluiu um passo". A idade do cursor substitui.
- Propósito não é imutável. O agente pode regravar, dizendo que regravou e por quê; o anterior fica no histórico com hora.
- C4 vira o comportamento do estado vazio: sem intenção gravada, o hook injeta os três primeiros prompts do log junto com o pedido de propor.

## Desenho

### O arquivo `.claude/session-intent`

```yaml
proposito: "institucionalizar as quatro perguntas de aterrissagem"
para_quando: "doc de estratégia em docs/ passado pelo /common:advisors e decidido"
plano:
  - levantar o que o harness já cobre
  - escrever o doc com 2+ caminhos
  - rodar advisors e registrar as discordâncias
  - decidir
passo: 3                      # o passo EM ANDAMENTO (não o último concluído)
passo_desde: 2026-10-16T21:40:00Z
session_id: 209286bf
branch: main
aberto_em: 2026-10-16T18:30:00Z
resumo: "passo 3/4 · rodar advisors · institucionalizar as quatro perguntas"
historico:
  - em: 2026-10-16T18:30:00Z
    proposito: "criar um comando whereami"
    motivo_da_troca: "o dono reformulou: o objeto é a intenção, não o comando"
```

Itens do plano não contêm dois-pontos (o escritor recusa). O parser mora em `_modos.py` ou `_wtlib.py`, com teste, e o nome entra em `RESCUE` de `_wtlib.py` para o resgate de worktree não o arrastar. Plano de 1 a 6 passos; mais que isso é programa (`plan.yaml`).

### Quem escreve

Um único escritor: o comando `cepa-intencao`. Subcomandos: gravar (propósito, ponto de parada, plano), `--passo N`, `--proposito "..." --motivo "..."`, `--plano` (substitui, preservando o anterior no histórico). Ele renderiza o `resumo:`. O agente nunca edita o YAML à mão.

Quem chama o comando, por origem da sessão:

| Origem | Quem grava | Quando |
|---|---|---|
| `cepa --modo x` e conversa | o agente, no primeiro turno com conteúdo | o hook pede enquanto falta |
| `/common:session <rotina>` | a própria rotina, a partir das perguntas de largada | sem segundo ritual |
| encadeada por `next.json` | o launcher `cepa`, com o `brief` como propósito | antes do primeiro turno |
| `cepa-until` | ninguém; a intenção é o item do `plan.yaml` | `whereami` delega ao `/common:next` |
| sessão de um passo só ("corrige esse typo") | o agente, sem perguntar | propósito = o pedido, plano de um item, só mostra |

### O primeiro turno (texto fixo)

O hook, sem intenção gravada, injeta: "Esta sessão ainda não tem intenção gravada. Primeiros prompts: <três primeiros do log>. Se este prompt tem conteúdo, proponha em três linhas (propósito, para quando, plano numerado), grave com `cepa-intencao`, e feche com: a qualquer momento `/common:whereami` mostra onde estamos. Se o prompt é trivial ou um comando de abertura, não proponha ainda."

O agente mostra as três linhas e segue trabalhando no mesmo turno. "sim" ou silêncio mantém; qualquer outra coisa é correção e regrava. Pergunta fechada aqui é a exceção "bifurcação genuína de preferência" do `default-yes`: o propósito é do dono.

### O que o hook injeta a cada turno (teto: duas linhas)

"[intenção] <proposito>. Passo <N>/<M>: <nome> (há <k> turnos). Próximo: <N+1 nome, ou 'plano cumprido: hora de /common:wrap-up'>." Com intenção de outra sessão: a pergunta de D1 no lugar. O plano inteiro fica para o `whereami`.

### Estados do `whereami`

- Vazio: "Esta sessão não tem intenção gravada. Diga o propósito e eu proponho o plano." Em run do `cepa-until`: delega ao `/common:next`.
- Normal: as quatro respostas por extenso, o plano com o cursor marcado, a idade do cursor, e a conferência contra o log ("o arquivo diz passo 2; os últimos 3 prompts parecem do passo 3. Avanço?").
- Plano cumprido: "Os 4 passos estão feitos. Ponto de parada: <para_quando>. Próximo: `/common:wrap-up`."
- Intenção de outra sessão: mostra a data e pergunta se continua.

### Statusline (conveniência local)

Linha 2 = `sed -n 's/^resumo: //p' .claude/session-intent`, cortada a 80 colunas. O `resumo:` já vem na ordem de corte certa: passo, nome do passo, propósito. Não repete o modo, que está na linha 1. Se o spike mostrar que duas linhas não renderizam, a linha 1 perde o segmento de tokens e ganha o passo; isso é decisão do dono.

Spike (2026-10-17, C1-7, Claude Code 2.1.302): duas linhas renderizam. A prova é documental, não visual (o run desatendido não tem terminal): a página oficial da statusline (code.claude.com/docs/en/statusline) diz que "each `echo` or `print` statement displays as a separate row" e traz um exemplo de duas linhas. A linha 2 entrou em `~/.claude/statusline-command.sh` (backup em `statusline-command.sh.bak-2026-10-17`): prefixo `🧭`, texto esmaecido, some sem `resumo:`, tira as aspas e os escapes do serializador de `_modos.py`, e corta por caractere (python3; o `cut -c` do macOS corta por byte e partiria o `·`) em 80 colunas contando o prefixo, com `…` quando corta.

### Telemetria e critério de sucesso

Eventos no `_telemetry.py`: `intent.written`, `intent.cursor_advanced`, `intent.asked` (prompt do dono casa com "o que estamos fazendo / onde estamos / próximo passo"), `intent.finished_at_last_step` (wrap-up com cursor no último passo). Linha nova no `/common:metrics`.

Número do scorecard (decisão 8 de `estrategia-cepa-proximo-nivel.md`) que isto deve mover: **turnos depois da rotina**, que é a deriva que o dono descreve. Critério para C2 entrar: depois de 10 sessões com intenção gravada, se a fração de sessões que terminam com o cursor nunca avançado passar de metade, ou se "turnos depois da rotina" não cair, C2 entra.

## Ordem de implementação (dois ciclos)

Ciclo 1:
1. Formato e parser compartilhado, nome em `RESCUE`, teste.
2. `cepa-intencao` (gravar, `--passo`, `--proposito`, `--plano`, render do `resumo`), teste.
3. `session-mode.py`: estado vazio (com os três primeiros prompts), intenção de outra sessão, injeção normal de duas linhas; `tests/test_cepa_modo.py` acompanha.
4. `cepa`: grava o brief do `next.json` como propósito; `/common:session` grava a partir das perguntas de largada.
5. `whereami.md` com os quatro estados; fallback no `/common:next`; linha de abertura no `/common:recap`.
6. Eventos de telemetria e linha no `/common:metrics`.
7. Spike da statusline e, se renderizar, a linha 2.

Ciclo 2 (condicional ao critério acima): C2 reescrito, roteando para `/common:branch`, substituindo o `off-mode-capture` em vez de somar um terceiro conceito de desvio.

## Painel de advisors (2026-10-16, 7 lentes: contrarian, fundamentalista, expansionista, outsider, executor, custo-de-manutencao, primeiro-uso)

**Vereditos por lente**

- contrarian: "C1 como está é um arquivo a mais que depende de dois atos de memória do agente (escrever no turno 1 e avançar o cursor) sem sinal mecânico, apoiado numa evidência que não prova a lacuna."
- fundamentalista: "C1 só é compatível com a doutrina se três quebras saírem do silêncio (segundo escritor no arquivo do launcher, hook enxuto virando gordo, cursor-instrução num projeto de travas); C2 como redigido viola o off-mode-capture e a precedência de instruções."
- expansionista: "C1 sim, mas a intenção pertence ao trabalho (branch), não ao processo; já viaja em handoff, next.json e label do branch."
- outsider: "Reconstrói o esqueleto, mas não por que a evidência prova a lacuna, como a mitigação do cursor funciona, nem como saber se C1 bastou."
- executor: "Implementável, não como está: formato primeiro (arquivo próprio), gatilho de primeiro turno no hook, comando para o cursor; Stop hook e Q3 fecham antes ou saem do escopo. Dois ciclos, não um."
- custo-de-manutencao: "Só paga a carga se a intenção morar em arquivo próprio e o cursor for derivado na hora da pergunta; do jeito escrito muda um formato com seis leitores."
- primeiro-uso: "Acerta no objeto, mas não desenha as quatro telas: turno de proposta, estado vazio, plano cumprido, cursor parado. whereami lendo o mesmo arquivo da statusline não pode ser fonte de verdade."

### Convergências (achados independentes de 2+ lentes)

- **V1. A intenção não pode morar em `session-mode`** (custo, executor, fundamentalista, expansionista, contrarian). Fatos conferidos no repo: `write_modo` reescreve o arquivo inteiro com `>` a cada `cepa`, então propósito e plano morreriam em todo relançamento; seis leitores fazem `partition(':')` por linha (session-mode.py, modo-escrita-gate.py, reforma-gate.py, cepa-feedback, cepa-modos, statusline) e nenhum entende lista YAML; a doutrina do repo é escritor único por artefato. Q2 não é gosto: arquivo próprio.
- **V2. O primeiro turno não tem gatilho mecânico** (contrarian, executor, primeiro-uso, fundamentalista). "Skill curta para o primeiro turno" é a mesma instrução-só-no-contexto que o doc usa para adiar C2. O primeiro prompt costuma ser `/common:doctor`, "continua" ou um handoff, não a intenção. Conserto apontado pelos quatro: `session-mode.py` já roda a cada turno; enquanto não houver intenção gravada, injeta "proponha e grave".
- **V3. O cursor é o estado mais frágil e a mitigação no Stop hook não tem definição** (contrarian, custo, executor, fundamentalista, outsider). "Concluiu algo" não é decidível; o único sinal do `report-style-lint.py` é Edit/Write/commit, que fica mudo justamente em sessão de exploração.
- **V4. A evidência da worktree apagada é non sequitur** (contrarian, outsider, expansionista, executor). Existe `worktree-remove-guard.py` para isso desde 2026-08-17; o incidente é um guard falhando ou contornado pelo wrap-up de outra sessão. Nenhum dos quatro campos de C1 detectaria. Sai do doc; vira investigação própria (registrado em `.claude/desvios.md`).
- **V5. A métrica mede o oposto do problema** (outsider, contrarian, executor, expansionista, fundamentalista). Se a falha é o dono esquecer de perguntar, contar perguntas premia o silêncio. Alternativas: eventos no `_telemetry.py` (`intent.written`, `intent.cursor_advanced`, `intent.asked`) lidos pelo `/common:metrics`; no wrap-up, comparar propósito gravado com o que a sessão entregou; e ligar ao scorecard da decisão 8 de `estrategia-cepa-proximo-nivel.md` ("turnos depois da rotina").
- **V6. "Propósito imutável" é armadilha** (contrarian, custo, primeiro-uso, expansionista). A própria sessão de origem mudou de propósito no meio. Regra única: o agente pode regravar, dizendo em voz alta que regravou e por quê, com o anterior preservado com hora.
- **V7. Q3 já está respondida pelo repo** (contrarian, executor, fundamentalista, expansionista). `cepa-until` chama `claude -p` direto, sem `cepa`: não tem nem modo. Ali a intenção já existe no item do `plan.yaml`. Sessão encadeada recebe o `brief` do `next.json`, que É o propósito: o launcher grava sem turno com o dono.
- **V8. Nome do comando: decidir agora, sem alias** (executor, custo, outsider, primeiro-uso). Não existe alias em `common/commands/`; são dois arquivos que divergem.
- **V9. Estados não desenhados** (primeiro-uso, outsider, executor): estado vazio do `whereami`, plano cumprido ("hora de wrap-up"), sessão de um passo só, abertura por `/common:session` (dois rituais em sequência), `passo: 2` ambíguo (fazendo ou terminou).
- **V10. Statusline** (fundamentalista, executor, custo, primeiro-uso): não é artefato do harness (arquivo pessoal em `~/.claude/`, sem install nem teste); ninguém verificou se o Claude Code renderiza duas linhas; parser shell de lista YAML é o padrão de divergência conhecido; a linha 2 proposta repete o modo e corta o passo primeiro. Se ficar: quem grava a intenção grava também um `resumo:` pré-renderizado, e a statusline continua sendo um `sed`.

### DISCORDÂNCIAS NOMEADAS

**DA. Ciclo de vida da intenção: por sessão ou por trabalho.**
Contrarian diz que a falha mais provável é a **intenção obsoleta herdada**: o arquivo vive por checkout, nunca é apagado, e a próxima sessão na mesma raiz exibe a intenção da anterior com a mesma confiança. Mitigação dele: gravar `session_id` e o hook descartar o que não bate. Expansionista diz o oposto: a intenção **pertence ao trabalho**, deve sobreviver a `/clear`, relançamento e encadeamento, morar por branch (como o label que `session-label.py` já guarda) e aparecer no `/common:worktree-list`, que é a visão multi-projeto que o dono administra de cabeça.
O que decide: se a dor é "entre turnos" (sessão) ou "entre projetos" (trabalho). O dono disse as duas. Recomendação do sintetizador: por branch/worktree, com `session_id` e `aberto_em` gravados; quando a sessão atual difere da que gravou, o hook injeta "intenção de <data>, gravada em outra sessão: continuo ou abro nova?" em vez de descartar ou exibir como atual.

**DB. Quem mantém o cursor.**
Executor: o agente, via um comando (`cepa-intencao --passo N`), porque só assim há evento observável. Custo-de-manutenção e primeiro-uso: ninguém mantém; o cursor é **derivado na hora da pergunta** pelo `whereami`, que lê o `session-log` contra o plano gravado (o plano é régua fixa, então a crítica a C3 não vale). Fundamentalista: se for mantido, a statusline mostra "cursor parado há N turnos", nunca um número que parece certo. Contrarian: C4, sem cursor e sem arquivo, só injetando os primeiros prompts do log a cada turno.
O que decide: se a segunda linha de statusline fica no escopo. Statusline é shell e não deriva nada; com ela, o cursor tem de estar gravado. Sem ela, derivar é mais barato e não mente. Recomendação: cursor gravado por comando (DB-executor), com idade visível (DB-fundamentalista), e `whereami` confrontando o gravado com o log (DB-primeiro-uso) para poder dizer "o arquivo diz 2, os últimos prompts parecem 3". C4 fica como comportamento do estado vazio: sem intenção gravada, o hook injeta os três primeiros prompts.

**DC. C2 e quem é dono da fronteira.**
Expansionista e primeiro-uso querem que C1 já tenha o verbo "substitui o plano" e um rastro de planos trocados. Fundamentalista diz que C2, como redigido, **viola** a exceção explícita do `off-mode-capture` ("o que o usuário pedir explicitamente neste turno: ele é o dono da fronteira e pode atravessá-la") e a camada 1 de `precedencia-de-instrucoes.md`, ao criar a opção "registro e não atendo" sobre um prompt humano. E o repo já tem `/common:branch` + `/common:return` para ramo de conversa.
O que decide: o agente pode deixar de atender um pedido do dono por estar fora do plano? A doutrina diz não. Recomendação: C2 reescrito sem "não atendo": o agente nomeia o desvio, atende, e roteia ramo longo para `/common:branch`; o `/return` devolve o cursor. Rastro de planos trocados entra no formato desde C1 (lista com hora).

**DD. Comando novo ou fallback nos existentes.**
Executor e custo: um comando, um nome, decidido agora. Expansionista: nenhum comando novo; `/common:next` ganha fallback (hoje falha sem `plan.yaml`) e `/common:recap` abre com "propósito / passo N de M". Criar comando é mais uma coisa para o dono lembrar, e o problema do dono é lembrar.
O que decide: o dono pediu `whereami` pelo nome. Recomendação: `/common:next` ganha o fallback (um `if`) e `whereami.md` existe como o nome que o dono vai digitar, canônico, sem segundo nome. Nome em inglês tem precedente (`recap`, `next`, `handoff`).

**DE. Statusline dentro ou fora do escopo do harness.**
Fundamentalista: fora; é arquivo pessoal, e C1 não pode depender dela para "responder sem o dono perguntar". Primeiro-uso e executor: é a única superfície que o dono vê sem pedir; sem ela, C1 vira C3 com arquivo. Decisão 6 de `estrategia-cepa-proximo-nivel.md` já fixou que arquivo em `~/.claude/` é do dono.
O que decide: se o hook injetando as quatro linhas no agente conta como "o dono vê". Não conta: o dono não lê o contexto do agente. Recomendação: a statusline entra como conveniência local declarada (não testada pelo harness), lendo um `resumo:` pré-renderizado; o spike de duas linhas é a primeira tarefa. O que o harness promete é o hook, o comando e o launcher.

### Propostas consolidadas, em ordem

1. **Arquivo próprio `.claude/session-intent`** com `proposito`, `para_quando`, `plano`, `passo`, `passo_desde`, `session_id`, `branch`, `aberto_em`, `resumo` (uma linha pré-renderizada), `historico` (propósitos e planos anteriores com hora). Parser compartilhado em `_modos.py`/`_wtlib.py`, nome em `RESCUE`, teste junto. (V1, DA, DB, V6)
2. **Gatilho no `session-mode.py`**: sem intenção gravada, injeta "proponha propósito, ponto de parada e plano, grave, e termine com: a qualquer momento /common:whereami mostra onde estamos"; com intenção de outra sessão, injeta a pergunta de DA; com intenção, injeta só propósito e passo atual com idade (teto do docstring "saída enxuta"). (V2, DA, V10)
3. **Comando `cepa-intencao`** (escrever, `--passo N`, `--proposito` com motivo) como único escritor; o agente nunca edita o YAML à mão. (DB, V1)
4. **`whereami.md`** canônico, `/common:next` com fallback, `/common:recap` com linha de abertura. Estados: vazio (ensina o caminho), plano cumprido (aponta wrap-up), um passo só (grava sem perguntar), aberto por `/common:session` (a rotina grava, sem segundo ritual), `next.json` (launcher grava o brief), `cepa-until` (sem intenção; delega ao `plan.yaml`). (V7, V8, V9, DD)
5. **Telemetria** `intent.written`, `intent.cursor_advanced`, `intent.asked`, `intent.finished_at_last_step`; linha no `/common:metrics`; ligar ao número "turnos depois da rotina" do scorecard. (V5)
6. **Retirar do doc**: a evidência da worktree apagada (vira investigação do `worktree-remove-guard.py`, já em `desvios.md`); a mitigação no Stop hook (sem sinal definido); "propósito imutável"; "statusline que mente é melhor que nenhuma"; "um ciclo" (conta honesta: dois). (V3, V4, V6)
7. **Condicional a DC**: C2 reescrito sem "não atendo", roteando para `/common:branch`.
8. **Condicional a DE**: statusline linha 2 = `passo 2/4 · <nome do passo> · <proposito>`, cortando o propósito primeiro, sem repetir o modo, após spike de renderização.
9. **Definir os termos no topo** (harness, dono, agente, turno, sessão, ciclo, rotina, programa) e os nove nomes citados sem apresentação. (outsider)
