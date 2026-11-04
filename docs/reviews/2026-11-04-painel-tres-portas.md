## Painel de advisors — `docs/estrategia-tres-portas-para-spec-e-epic.md` (area: `arquitetura`, 7 lenses)

Rodado em 2026-11-04 sobre a revisão 1 do documento. 62 achados: contrarian 9, fundamentalista 9, expansionista 6, outsider 10, executor 10, operador-sre 10, custo-de-manutencao 8. Síntese pelo orquestrador da sessão; cada afirmação de lente foi conferida no disco antes de entrar aqui, e uma foi derrubada (C3 abaixo).

**Vereditos por lente**

- contrarian: "O2 é a direção certa, mas D2 está descrito sobre um gate que faz o oposto do que o texto diz, um formato de linha que dois terços dos documentos reais não seguem e um arquivo de expertise que ninguém carrega."
- fundamentalista: "O2 respeita Jira opcional e entrevista sem burocracia, mas quebra em silêncio três regras do repo: um escritor por arquivo, `- [x]` só para resposta do dono, expertise por agente."
- expansionista: "O2 está um grau estreito em três pontos baratos: leitores no `cepa-plan`, proveniência para qualquer campo proposto a partir de arquivo, e o debrief por caminho lendo também `### Decision:`."
- outsider: "Mapa competente, mas só legível por quem conhece o elenco; a recomendação depende de uma premissa nunca enunciada (por que entrevista vale mais que rascunho) e de um mecanismo nunca descrito."
- executor: "Não começa na segunda-feira: D2 depende de uma decisão aberta, de um arquivo inexistente, de um parser que não lê as sete decisões reais e de um rebaixamento que o gate não faz; a fila é de 9 a 10 itens, não 5 a 7."
- operador-sre: "O veto é um ritual que falha em silêncio no meio e cujo efeito a construção ignora: a fila derivada continua rodando depois do overrule."
- custo-de-manutencao: "O2 troca um defeito de uma linha (passo 2 não cita as fontes) por flag, matriz de três formatos no plugin base, segundo modo no debrief e três micro-formatos de anotação."

### Legenda

| código | lente | achado em uma frase |
|---|---|---|
| C1 | contrarian | O `spec-readiness-gate` bloqueia a escrita, não rebaixa o status; o debrief teria de gravar `draft` na mesma edição. |
| C2 | contrarian | O parser `- decisão — porquê` não casa com nenhuma das sete decisões reais, e o travessão é proibido pela regra editorial do dono. |
| C3 | contrarian | A mitigação do R3 cita um `handoff-seeds-gate` que não existiria no disco. **Derrubado:** `common/hooks/handoff-seeds-gate.py` existe; o que não conferi é se está ligado no `hooks.json`. |
| C4 | contrarian | No `/common:spec`, pré-preencher como `- [x]` declara que o dono respondeu o que nunca viu. |
| C5 | contrarian | As sete decisões já viraram código (fila `cepa-espiral-c1` toda `done`); vetá-las hoje não reabre nada. |
| C6 | contrarian | A fonte `spec/` do `planning-lead` é palpite de agente, e a tabela a trata igual à evidência do `handoff.md`. |
| C7 | contrarian | D3 grava um caminho relativo num card de outro board, provavelmente de outro repositório. |
| C8 | contrarian | O `build-team` escreve em `specs/`, não em `spec/`; "cabeçalhos fixos" é esperança, e "5 a 7 itens" não tem conta. |
| F1 | fundamentalista | D2 faz o debrief segundo escritor de `docs/epics` e `docs/spec`, a regra de dono único que o próprio documento usa para rejeitar O3. |
| F2 | fundamentalista | Decisão herdada de outra spec entrando como "pergunta já respondida" lava decisão de agente em resposta do dono. |
| F3 | fundamentalista | D3 aponta o brief para `/common:epic` sem reescrever a regra "Brief, not Epic", que nomeia o `epic-author`. |
| F4 | fundamentalista | O debrief por caminho não declara modo, e o `write-mode-gate` restringe `docs/epics` e `docs/spec` por modo. |
| F5 | fundamentalista | N campos pré-preenchidos de uma vez contra "uma pergunta por turno" vira o menu que o `/common:epic` proíbe. |
| E1 | expansionista | Os leitores de formato cabem no `cepa-plan`, que já tem `items_from_spec`, `items_from_epic`, `read_handoff` com testes. |
| E2 | expansionista | Proveniência deveria valer para todo campo proposto a partir de arquivo lido, com ou sem `--from`; fecha F7 sem flag. |
| E3 | expansionista | O debrief por caminho deveria ler também os blocos `### Decision:` que o `planning-lead` escreve em `spec/`. |
| E4 | expansionista | O arquivo de expertise da entrevista é o entregável de maior alcance e está escondido como detalhe. |
| E5 | expansionista | O `/common:doctor` pode listar decisões sem veredito, e aí as sete aparecem amanhã, não só no próximo fechamento. |
| O1 | outsider | O documento nunca diz por que a entrevista com o dono vale mais que um rascunho autônomo, e a recomendação inteira depende disso. |
| O2 | outsider | A terceira porta é saída da entrevista, não entrada, e o texto a trata de dois jeitos sem avisar (fonte para outra entrevista; coisa a vetar). |
| O3 | outsider | Os quatro formatos mapeados na tabela nunca são mostrados nem em esqueleto. |
| O4 | outsider | As sete decisões são contadas mas nenhuma é mostrada; o leitor não sabe se o problema é cosmético ou de escopo. |
| X1 | executor | D2 carrega duas decisões abertas (debrief ou comando novo; onde gravar expertise) e um arquivo inexistente. |
| X2 | executor | `--from` não diz o que faz quando `docs/spec/<slug>.md` já existe (mescla, ignora, recusa). |
| X3 | executor | Não há `spec/` no Cepa nem `handoff.md` no formato; os fixtures terão de ser escritos à mão a partir dos templates. |
| X4 | executor | A fila decomposta dá 10 itens, e roda num ciclo cuja suíte está vermelha na base (`test_cepa_until_dead_supervisor.py`). |
| X5 | executor | D5 é o item mais barato e observável e deveria abrir a fila, não fechá-la. |
| X6 | executor | D3 deixa o `<slug>` do Epic sem dono: chave do card ou nome escolhido na entrevista. |
| S1 | operador-sre | Overrule rebaixa a spec enquanto a fila derivada continua rodando; nenhum consumidor (`drain-plan`, `cepa-plan`, `next`) reage ao status. |
| S2 | operador-sre | `expertise-append.py` aborta em arquivo ausente (linha 111), em silêncio, depois de o veredito já ter ido ao documento. |
| S3 | operador-sre | Sem marcador uniforme por linha, uma segunda rodada do veto reapresenta decisões já refinadas ou vetadas. |
| S4 | operador-sre | Falha do parser `--from` é indistinguível de "sem fonte": o dono responde tudo de novo e culpa o comando. |
| S5 | operador-sre | A dívida de veto não é observável por ferramenta: `doctor`, `next` e `metrics` não a contam. |
| M1 | custo-de-manutencao | A alternativa mais simples não foi considerada: nomear as entradas no passo 2 dos comandos, sem flag nem parser. |
| M2 | custo-de-manutencao | D1 inverte a dependência: `common` passa a conhecer os formatos de `discovery` e `build-hex`. |
| M3 | custo-de-manutencao | D2 cria um segundo modo num comando de 241 linhas e três convenções novas de texto na linha. |
| M4 | custo-de-manutencao | A proveniência inline é um terceiro sufixo em linhas que o gate parseia; alternativa é uma linha `Fontes lidas:` no cabeçalho. |
| M5 | custo-de-manutencao | D4 "condicionado a uso" sem número é adiamento permanente de dois formatos de spec. |

### Convergências

1. **O gate não rebaixa status; quem rebaixa é quem escreve.** C1, X1, S3, F4, O(mecanismo nunca descrito). Trecho: regra 5 de O2, "o que derruba `Status: ready` para `draft` pelo próprio gate". Conferido: `spec-readiness-gate.py` só faz `sys.exit(2)`.
2. **O formato de linha `- decisão — porquê` não existe no corpus e o travessão é proibido.** C2, X1, S(media). Conferido: as sete linhas reais não têm o separador.
3. **O arquivo `spec-interviewer-mental-model.yaml` não existe, os comandos não carregam expertise, e o `expertise-append.py` aborta em arquivo ausente.** C(media), M(media), S2, X1, F(media), E4.
4. **Pré-preencher como `- [x]` no `/common:spec` é o atalho que R1 teme.** C4, F2, X2.
5. **D2 primeiro é a ordem errada; D5 primeiro.** C5, X5, M(baixa).
6. **D3 está mal especificado:** slug sem dono (X6), caminho em outro repo (C7), comando literal congelado em card (M baixa), regra "Brief, not Epic" não reescrita (F3).
7. **O documento não é autossuficiente:** elenco sem apresentação, formatos não mostrados, decisões não citadas, premissa da entrevista não enunciada (O1 a O4).

### DISCORDÂNCIAS NOMEADAS

- **custo-de-manutencao (M1) diz que basta nomear as entradas no passo 2 dos comandos, sem flag nem parser, porque o agente já lê prosa** vs. **expansionista (E1) diz que os leitores devem ser Python no `cepa-plan`, com testes, e a fila ganha `--from-handoff` de brinde** vs. **executor (X1, "onde vive o parser") diz que os dois entregam coisas diferentes e a estimativa só vale para a versão Python.**
  **O que decide entre elas:** se a proveniência e o desafio precisam de prova mecânica ou bastam como disciplina de prompt. A seção "Decided without asking" precisa de leitor em código, porque `doctor` (E5, S5) e o veto (S3) dependem dele. As duas fontes externas (`handoff.md`, `spec/`) não precisam: o agente lê a prosa e propõe. Recomendação: parser Python só para a seção de decisões, em `cepa-plan`; as fontes externas entram por prosa no passo 2, com proveniência genérica (E2) e sem flag obrigatório. Isso responde M1, E1 e X1 ao mesmo tempo e corta M2 (o `common` não aprende formato alheio).

- **fundamentalista (F1) diz que o debrief virar escritor de `docs/epics` e `docs/spec` quebra a regra de dono único, e que `/common:veto` evitaria três quebras** vs. **expansionista (E3) diz que o debrief por caminho é o lugar certo e deveria ler ainda mais (os `### Decision:` do `planning-lead`)** vs. **custo-de-manutencao (M3) diz que um segundo modo no debrief é carga permanente.**
  **O que decide entre elas:** quem é o escritor dos documentos de entrevista. Os dois comandos declaram "the only file this command writes". Recomendação: o veto é um passo dos próprios comandos de entrevista, no `--continuar` e no `--fechar`, que abrem listando as decisões sem veredito, uma por turno, no mesmo ritmo da entrevista (resolve F5 também). O debrief não muda. E3 fica para o `planning-lead` dentro de run, que já é coberto.

- **contrarian (C5) diz que vetar as sete decisões já construídas é teatro retroativo** vs. **expansionista (E5) e operador-sre (S5) dizem que a dívida de veto precisa ser visível amanhã de manhã, pelo `doctor`** vs. **operador-sre (S1) diz que um veto que rebaixa a spec enquanto a fila roda é pior que não vetar.**
  **O que decide entre elas:** se o veto tem efeito sobre a construção já feita. Não tem, e não deve ter: a fila e o código já existem. Recomendação: veto registra na linha (`mantida`, `vetada`, `refinada`, com data) e nunca mexe no `Status`; `Status` só muda pela entrevista. O `doctor` lista documentos com linhas sem veredito. Uma decisão vetada vira item novo na fila do próximo ciclo, pela mão do dono, não por propagação automática. Isso esvazia S1 e C1 ao mesmo tempo.

- **contrarian (C6) e fundamentalista (F2) dizem que `spec/` do `planning-lead` e decisões herdadas são palpite de agente, e não podem entrar com o mesmo rótulo que evidência de usuário** vs. **expansionista (E2) diz que uma proveniência única e genérica fecha F7 inteira.**
  **O que decide entre elas:** se o dono distingue a origem ao ver a proposta. A memória do projeto registra que ele aprovava recomendações sem entendê-las. Recomendação: proveniência genérica (E2), mas com dois rótulos, `evidência` (handoff do discovery, com audit) e `proposta de agente` (spec do `planning-lead`, decisões de outra entrevista). Decisão herdada de outra spec entra na seção "Decided without asking" do documento novo, com origem, nunca como pergunta respondida (F2).

### Propostas consolidadas priorizadas

1. **Reescrever D2 como passo dos comandos de entrevista, sem tocar no debrief e sem mexer no `Status`.** (C1, F1, F4, M3, S1, S3, X1.) Marcador uniforme por linha com data; só linhas sem marcador entram na caminhada.
2. **Fixar o formato de linha da seção: a linha inteira é a decisão, sem separador obrigatório; o porquê vem após ponto final.** (C2, X1, S.) O leitor em `cepa-plan`, com teste sobre os três documentos reais, aceita os cabeçalhos pt-BR antigos como o gate já faz.
3. **D5 primeiro, e um check no `doctor` para a dívida de veto.** (X5, E5, S5, C5.)
4. **Trocar o flag `--from` obrigatório por entradas nomeadas no passo 2 dos dois comandos, com proveniência genérica de dois rótulos; `--from` fica como atalho opcional que só aponta o arquivo.** (M1, E2, C6, F2, M2, M4.) Proveniência vai numa linha `Fontes lidas:` no cabeçalho mais o rótulo na proposta do turno, não como sufixo na linha do critério.
5. **Nada vira `- [x]` sem resposta do dono.** (C4, F2, X2.) Campo pré-preenchido fica no corpo com o rótulo até ser desafiado; a pergunta correspondente fica `- [ ]` até o turno dela.
6. **Retirar o arquivo de expertise da entrevista desta rodada.** (S2, E4, F, M.) O que o dono quer tornar regra vai para o `CLAUDE.md` do repo, que os comandos já leem; expertise para comando é decisão separada, com contrato próprio.
7. **Reescrever D3:** o card recebe só o caminho do brief e o repositório onde ele vive; o `<slug>` é escolhido na entrevista; a regra "Brief, not Epic" passa a nomear os dois consumidores. (X6, C7, F3, M.) Condicional à aprovação da proposta 4.
8. **Tornar o documento autossuficiente:** quadro de atores, esqueleto dos formatos, as sete decisões citadas, e o parágrafo que diz por que a entrevista vale mais que o rascunho autônomo. (O1 a O4.)
9. **Refazer a estimativa com memória de cálculo e um item 0 para a suíte vermelha.** (X4, C8.)
10. **D4 com gatilho numérico ou retirado.** (M5.) Condicional: se a proposta 4 passa, o parser de `spec/` não existe e D4 perde o motivo.
