## Painel de advisors — `docs/estrategia-loops-longos.md` (área: `arquitetura`, 7 lentes)

**Vereditos por lente**

- contrarian: "P1 ataca o sintoma certo, mas é espera sem canal: com Q1 e Q3 abertas e sem cruzar a hora das respostas com o prazo dos runs, não há evidência de que alguma das 261h volte."
- fundamentalista: "Fiel ao lado determinístico, mas P1 e P2 mudam em silêncio a decisão 4 de 2026-10-08, a C6 de 2026-09-26, o escritor único da fila e a regra de não devolver decisões."
- expansionista: "P1 está certo e barato, mas estreito: com uma fase de espera genérica, um aviso reaproveitável e a tabela da janela como métrica fixa, vira a primeira peça do condutor."
- outsider: "O leitor de fora entende o problema, mas não reconstrói a decisão: os números não fecham, a escolha de fila não tem critério e P1 é recomendado com as perguntas que decidem o ganho em aberto."
- executor: "P1 não começa na segunda como está: tem de ser dividido em espera, aviso e resposta remota, depois de separar os adiamentos por motivo e provar a Q2."
- operador-sre: "Troca um encerramento visível por uma espera que pode falhar em silêncio. Só deve ser construído com aviso registrado, chave de desligar, campos de diagnóstico e SIGTERM coberto por teste."
- custo-de-manutencao: "P1 e P2 deixam carga permanente no supervisor para um ganho que depende de Q3. A alternativa barata, avisar e encerrar ou perguntar tudo antes do run, nem foi avaliada."

### Legenda

| código | lente | achado em uma frase |
|---|---|---|
| CR1 | contrarian | Hora de janela parada não custa token nem cota. A métrica tem de ser entrega, não ocupação do relógio. |
| CR2 | contrarian | O ganho de P1 depende de Q1 e Q3, que estão abertas. |
| CR3 | contrarian | O histórico permite medir se o dono responde dentro do prazo do run, e essa medição não foi feita. |
| CR4 | contrarian | Os 36 runs são um teto, porque misturam adiamentos que P1 exclui. |
| CR5 | contrarian | A tabela da seção 2 não fecha com os totais. |
| CR6 | contrarian | A regra de P2 é prosa, o que V4 condena. |
| CR7 | contrarian | Uma fila nova compete com o condutor, que é a linha principal. |
| FU1 | fundamentalista | P1 reabre a decisão 4 de 2026-10-08 (`aguardando-dono` só em item com dependentes) sem declarar. |
| FU2 | fundamentalista | P1 põe o aviso no centro, contra a C6 de 2026-09-26 (estado gravado é o mecanismo e o aviso é extra). |
| FU3 | fundamentalista | Q1 a Q3 empurram decisão para o item, o que o CLAUDE.md proíbe. |
| FU4 | fundamentalista | A fila nova não tem ordem aprovada pelo dono como fonte. O nome foge do prefixo `cepa-`. |
| FU5 | fundamentalista | O alimentador do P2 cria uma quinta fonte e uma escrita sem o dono. |
| FU6 | fundamentalista | A seção 5 não declara mantida a decisão 3 (uma branch por run). |
| EX1 | expansionista | Unificar a espera do dono com a espera de cota que já existe sai quase de graça. |
| EX2 | expansionista | P1 é o que destravaria os itens `human_pending` da `cepa-espiral-c2`. |
| EX3 | expansionista | O aviso devia nascer como `cepa-notify`, uma saída única do harness. |
| EX4 | expansionista | P2 sai mais barato como modo append das fontes que o `cepa-plan` já tem. |
| EX5 | expansionista | A tabela da janela perdida devia virar métrica fixa em `/common:metrics`. |
| OU1 | outsider | O critério para escolher a fila não está escrito. |
| OU2 | outsider | Muito vocabulário interno sem definição. |
| EC1 | executor | P1 deve virar P1a (espera), P1b (aviso) e P1c (resposta remota). |
| EC2 | executor | O código adia por 4 motivos e o documento não diz quais disparam a espera. Existe o campo `esperam_dono`. |
| EC3 | executor | Q2 é pré-condição do item, não pergunta para resolver no caminho. |
| EC4 | executor | `cepa-durabilidade` tem DUR-3 `done` com `human_pending` ainda preenchido. |
| EC5 | executor | P3 e P4 não têm lembrete nem dono para reabrir. |
| SR1 | operador-sre | Aviso que falha em silêncio deixa o run esperando para sempre. Cada aviso tem de virar evento. |
| SR2 | operador-sre | Canal externo sem timeout trava o laço e o heartbeat. |
| SR3 | operador-sre | Reler a fila enquanto o dono a edita pode encerrar o run por `fila-ilegivel`. |
| SR4 | operador-sre | Responder pelo celular exige SSH até um Mac que à noite deve estar dormindo. |
| SR5 | operador-sre | Falta uma chave de desligar a espera. |
| SR6 | operador-sre | `aguardou-dono` só aparece quando o dono não respondeu, então não mede o ganho. |
| SR7 | operador-sre | Na retomada é preciso conferir de novo reserva mínima, cota e rede. |
| SR8 | operador-sre | SIGTERM durante a espera precisa de semântica e de teste. |
| CM1 | custo-de-manutencao | O estado de espera vira carga permanente em toda mudança futura do laço. |
| CM2 | custo-de-manutencao | Avisar e encerrar, ou perguntar antes do run, não foi considerado. |
| CM3 | custo-de-manutencao | Q2 acopla o clone à worktree do run. |
| CM4 | custo-de-manutencao | Classificar o adiamento é conhecimento do `cepa-plan`, não do supervisor. |
| CM5 | custo-de-manutencao | P2 traz três adaptadores e um classificador. Deve ficar sem fila. |

### Convergências

1. **O ganho de P1 depende de Q1 e Q3, que estão abertas** (CR2, FU3, OU, EC1, SR4, CM3, 6 de 7 lentes). Trecho: "Without it, P1 only helps when the owner comes back to the terminal before the deadline." O caso que o diagnóstico descreve é o dono dormindo. Nesse caso P1 só troca o encerramento por uma espera.
2. **A tabela não fecha** (CR5, FU, OU, 3 lentes). Conferido: faltam as linhas `sem-rede` (1 run, 7,9h pedidas, 7,5h usadas) e `cota-no-fim` (1 run, 4,0h, 2,4h), e a linha `prazo` entra com perda de −4,1h (133,8 − 137,9). Conta corrigida: 261,0 + 34,9 + 30,6 + 21,1 + 20,8 + 0,4 + 1,6 − 4,1 = 366,3h. Bate com os 366,4h do texto, com diferença de arredondamento. Os 71% se mantêm.
3. **Os 36 runs e os 346 adiamentos estão inflados** (CR4, OU, EC2, CM4, 4 lentes). A frase "N ficaram adiados" soma os quatro motivos (`reserved`, `blocked-before`, `human_pending`, `depends-on-deferred`), e P1 só atende parte deles.
4. **A métrica está errada** (CR1, OU, SR6, EX5, 4 lentes). Horas de relógio não são entrega. E `aguardou-dono` só registra a espera que falhou.
5. **P2 burla o escritor único da fila** (CR6, FU5, CM5, SR, 4 lentes).
6. **As perguntas abertas têm de virar decisão do dono antes de existir fila** (FU3, FU4, EC3, CM, 4 lentes).

### DISCORDÂNCIAS NOMEADAS

- **X1. Esperar vivo ou avisar e encerrar.** **custo-de-manutencao diz** que avisar e encerrar, deixando o dono relançar o run, ataca os mesmos 36 runs sem processo dormindo, sem motivo de fim novo e sem acoplar o clone à worktree (CM1, CM2). **expansionista diz** o contrário: a espera deve ser genérica, unificada com a espera de cota, e vira a primeira peça do condutor (EX1, EX2). O **executor** fica no meio: P1a começa já, o resto depois (EC1).
  - **O que decide entre elas:** a medição de CR3. Para cada run que parou com pergunta ao dono, o dono respondeu antes do prazo daquele run? Se quase nunca, esperar vivo não recupera nada, e avisar e encerrar basta. Recomendo fazer essa medição antes de escolher. Sem ela, a recomendação default é avisar e encerrar, que é a opção barata e reversível.
  - **Decisão do dono:** Medir antes de escolher (2026-11-10): cruzar a hora de cada resposta com o prazo do run; a escolha entre esperar vivo e avisar e encerrar sai do número.
- **X2. O papel do aviso.** **fundamentalista diz** que, pela C6, o estado gravado é o mecanismo e o aviso é só um extra, e que P1 inverte isso (FU2). **operador-sre diz** que, no desenho como está, tudo depende do aviso, e que aviso que falha tem de virar evento e motivo de fim (SR1, SR2).
  - **O que decide entre elas:** se o dono responde de longe do Mac. Se não responde, o aviso é extra e vale a C6. Se responde, o aviso é o caminho crítico e vale o SR1. Recomendo seguir a C6: estado gravado como fonte e aviso registrado como evento `aviso_enviado`/`aviso_falhou`, com timeout curto e sem encerrar o run quando falhar.
  - **Decisão do dono:** Sim (2026-11-10): estado gravado é a fonte (C6); cada aviso vira evento `aviso_enviado`/`aviso_falhou`, com timeout curto, e falha de aviso não encerra o run.
- **X3. O que fazer com P2.** **custo-de-manutencao diz** que P2 fica sem fila, como P3 e P4 (CM5). **expansionista diz** que P2 sai barato como modo append das fontes que o `cepa-plan` já tem (EX4). **fundamentalista diz** que qualquer versão cria uma quinta fonte e precisa de decisão explícita sua (FU5).
  - **O que decide entre elas:** os 8 runs de fila vazia sem item adiado justificam um segundo modo de escrita na fila? Recomendo que não por enquanto. P2 fica fora de fila e, se voltar, volta no formato EX4, declarado como quinta fonte.
  - **Decisão do dono:** Sim (2026-11-10): P2 fica fora de fila; se voltar, volta como modo append das fontes do `cepa-plan`, declarado como quinta fonte.
- **X4. Onde P1 mora em relação ao condutor.** **contrarian diz** que uma fila paralela compete com a linha principal, que é o condutor (CR7). **expansionista diz** que P1 é a primeira peça do condutor e deve cobrir os itens `human_pending` da `cepa-espiral-c2` (EX2). **fundamentalista diz** que P1 reabre a decisão 4, que só para em `aguardando-dono` quando o item tem dependentes (FU1).
  - **O que decide entre elas:** se a regra de espera do run de fila comum é a mesma do ciclo do condutor. Recomendo declarar no documento que a decisão 4 continua valendo para o condutor e que P1, se for construído, vale só para run de fila comum, numa fila `cepa-loops-longos` cuja fonte é a ordem aprovada aqui (FU4).
  - **Decisão do dono:** Sim (2026-11-10): decisão 4 continua valendo para o condutor; P1, se construído, vale só para run de fila comum, na fila `cepa-loops-longos` com fonte nesta ordem aprovada.

### Propostas consolidadas priorizadas

1. Corrigir a tabela da seção 2: incluir as linhas `sem-rede` e `cota-no-fim` e explicar a linha `prazo` com −4,1h (CR5, FU, OU).
2. Passo 0 antes de qualquer código. Separar os adiamentos por motivo pelo campo `esperam_dono` e cruzar a hora de cada resposta (commit do `queue.yaml` feito por `decide`/`answer`) com o prazo do run (CR3, EC2, OU, CM4). Decide X1.
3. Trocar a métrica por entrega: itens fechados depois de uma resposta dada no meio do run, medidos com eventos `espera_inicio`/`espera_fim` (CR1, SR6, EX5).
4. Transformar Q1, Q2 e Q3 numa seção "Decisões do dono" com perguntas fechadas e recomendação (FU3, EC3, CM3).
5. Acrescentar o bloco "decisões que este documento mantém ou reabre", com a decisão 4, a C6, a decisão 3 e o escritor único (FU1, FU2, FU6, FU5).
6. Acrescentar o caminho P0, avisar e encerrar ou perguntar antes do run (CM2). *Condicional a X1.*
7. Se a espera for construída: dividir em P1a, P1b e P1c (EC1), com chave de desligar (SR5), heartbeat a cada 60s durante a espera (CR), leitura tolerante da fila (SR3), conferência de cota e reserva na retomada (SR7), SIGTERM coberto por teste (SR8) e `cepa-plan` devolvendo pronto o campo de "há pergunta do dono" (CM4). *Condicional a X1 e X2.*
8. P2 fora de fila (CM5, CR6, FU5). *Condicional a X3.*
9. Fila `cepa-loops-longos` com fonte nesta ordem aprovada (FU4, OU1). Resolver a pendência de DUR-3 em `cepa-durabilidade` antes de chamá-la de fechada (EC4). *Condicional a X4.*
10. Lembrete datado para reabrir P3 e P4 (EC5), uma linha em `docs/estrategia-durabilidade.md` apontando este documento, e um glossário curto para leitor de fora (OU2).
