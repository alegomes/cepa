## Painel de advisors — `docs/estrategia-lacunas-ecc.md` (área: arquitetura, 7 lentes)

Data: 2026-11-12. Total de achados: 81 (contrarian 11, fundamentalista 12, expansionista 10, outsider 15, executor 11, operador-sre 11, custo-de-manutencao 11). Cada lente leu o arquivo do disco, isolada das outras.

**Vereditos por lente**

- contrarian: "A direção do caminho P3 se sustenta e os fatos do Cepa batem no disco, mas a ordem falha em três pontos: a medição fica sem data, o lote da rodada desatendida não prova que ataca os 4 casos que cita, e o padrão `build-solo` no instalador viola a regra R5."
- fundamentalista: "Não passa como está: abre uma via para desligar o gate de escrita por modo que o Epic declara invariante, não aplica a regra de admissão do scorecard a nenhum lote, antecipa o ciclo 3 e muda o público do Cepa sem atualizar o Epic."
- expansionista: "P3 está certo, mas trata como onze peças o que são três estruturas compartilhadas: um leitor de transcrição, um registro de hooks com tipo e um conjunto de sessões gravadas."
- outsider: "Um leitor de fora não reconstrói a decisão: o status diz exploração com três decisões já tomadas, a definição dos caminhos contradiz a tabela de lotes e boa parte do vocabulário nunca é apresentada."
- executor: "Na segunda-feira só dá para começar o conserto das duas skills e os testes do validador. Todo o resto está parado em pré-condição não satisfeita ou em decisão que o documento não lista como pergunta."
- operador-sre: "Não é operável como está: liga interruptores e detectores sem dizer onde o estado deles aparece, e abre a instalação a terceiros antes de existir desinstalação."
- custo-de-manutencao: "P3 só é sustentável se encolher: o interruptor de hooks, as sessões gravadas, o desinstalador, o changelog e a fila de revisão da memória criam listas paralelas e contratos permanentes."

### Legenda

Os códigos E1 a E11, A1 a A8, R1 a R5 e Q1 a Q3 são os do documento revisado. Os usados aqui:

- **E1**: conjunto fixo de sessões gravadas para comparar as decisões de um hook antes e depois de uma mudança.
- **E2**: identificador estável e interruptor por hook.
- **E3**: validador sobre todo comando, agente e skill.
- **E4**: suíte de testes rodando em todo push.
- **E5**: checagem da lista de plugins entre os três lugares que a repetem.
- **E6**: o `cepa-until` notar que o processo filho travou.
- **E7**: teto para o texto de descrições que é sempre carregado.
- **E8**: aviso de sessão longa pelo tamanho real do contexto.
- **E9**: registro de cada compactação de contexto.
- **E11**: seção "o que não funcionou" no handoff.
- **A1**: licença, descrição e tópicos no GitHub.
- **A2**: instalar sem clonar o repositório.
- **A3**: topologia padrão no instalador.
- **A4**: desinstalador e simulação da instalação.
- **A5**: registro de versões e tags.
- **R1**: regra do documento de que nenhum lote adiciona hook que bloqueia.
- **R2**: regra de que uma lista fechada de hooks nunca é desligada.
- **R5**: regra de que a porta aberta não muda o que o instalador faz nos projetos já instalados.
- **Q1, Q2, Q3**: as respostas do dono de 2026-11-12 (abrir a outros usuários, licença MIT, memória do ciclo 3 espera revisão).

| código | lente | achado em uma frase |
|---|---|---|
| CR1 | contrarian | O lote de medição não tem data: fica atrás do ciclo 2, e 3 dos seus 5 itens (E7, E8, E9) não estão no Epic nem no `BACKLOG.md`. |
| CR2 | contrarian | Os 4 casos que justificam E6 são filhos mortos no fim da folga, e nada mostra que estavam presos numa chamada de ferramenta, que é o único sinal que E6 lê. |
| CR3 | contrarian | Com `build-solo` como padrão, um `install.sh --clean` sem `--topology` num projeto `build-hex` regravaria `.claude/topology`. |
| CR4 | contrarian | Os testes do lote 1 não param ninguém: o repo tem `.claude/no-build`, R1 proíbe hook que bloqueia e a suíte travou 3 h em 05/11 e 10 h em 06/11. |
| CR5 | contrarian | A memória que espera revisão depende de quem triou 1 de 16 entradas de feedback (1 ÷ 16 = 6%). |
| CR6 | contrarian | Os lotes 0, 1, 3 e 4 não dizem qual dos quatro números do scorecard movem, e o lote 4 não tem critério de sucesso. |
| CR7 | contrarian | Descrição e tópicos convidam estranhos a um repositório cujo conteúdo não foi revisado para leitura de fora. |
| CR8 | contrarian | E2 cria o primeiro caminho oficial para desligar gate, e a lista fechada protege 3 de 53 hooks. |
| CR10 | contrarian | Não há teste de que o Claude Code não carrega as 2 skills sem cabeçalho, nem sessão em que a falta delas piorou o resultado. |
| FU1 | fundamentalista | O interruptor pode desligar o gate de escrita por modo, que `docs/epics/cepa-em-espiral.md` lista em "Invariantes (nunca regridem)". |
| FU2 | fundamentalista | `docs/estrategia-cepa-proximo-nivel.md` linha 82 diz que mudança no harness que não move um dos quatro números não entra, e o documento não aplica a regra. |
| FU3 | fundamentalista | O documento chegou ao painel com Q1, Q2 e Q3 já respondidas, e `docs/advisors.md` diz que o painel roda antes de a decisão ser tomada. |
| FU4 | fundamentalista | O lote 2 antecipa trabalho do ciclo 3, que o Epic só abre depois do ciclo 2. |
| FU5 | fundamentalista | Q3 contradiz a linha do ciclo 3 do Epic, e o comando que monta a fila lê o Epic. |
| FU6 | fundamentalista | Abrir o Cepa a estranhos muda para quem ele existe, e isso está escrito no Epic, que não foi atualizado. |
| FU7 | fundamentalista | A5 ignora `docs/versionamento.md`, que já define versão por plugin e nota de release. |
| FU9 | fundamentalista | O conserto das 2 skills fica preso atrás da aprovação de uma estratégia inteira. |
| EX1 | expansionista | E6, E8 e E9 leem a mesma transcrição da sessão e podem compartilhar o leitor que `cepa-tokens` já tem. |
| EX2 | expansionista | O registro de E2 pode declarar, por hook, se ele bloqueia, só avisa ou é protegido, e R1 e R2 viram campos conferíveis. |
| EX3 | expansionista | O conjunto de sessões gravadas, se não for estreito a um hook, serve de critério para a revisão da memória e para o experimento com e sem gate. |
| EX4 | expansionista | Tags são dependência do scorecard do ciclo 3, que precisa de pontos nomeados no histórico. |
| EX5 | expansionista | O registro de arquivos escritos pelo instalador (A4) é o que torna A3 seguro e R5 verificável. |
| EX6 | expansionista | Derivar as listas de plugins do `marketplace.json` elimina a divergência em vez de vigiá-la. |
| EX7 | expansionista | Depois de Q3, a seção do handoff (E11) é o canal de memória revisada mais barato. |
| EX10 | expansionista | A2 pode ser trabalho de minutos se `/plugin marketplace add` já funcionar com o `marketplace.json` existente. |
| EC1 | executor | O lote 2 herda três pré-condições em cadeia e o Epic está com Status rascunho. |
| EC2 | executor | O documento não diz de onde vêm as sessões gravadas, e parte das sessões reais é de repositório de cliente. |
| EC3 | executor | E2 é o maior item do plano e não tem desenho: onde mora o identificador, quem lê a variável nos 53 comandos. |
| EC4 | executor | E4 supõe que a suíte está verde, quanto demora e que roda em Linux, e nenhum dos três foi verificado. |
| EC5 | executor | O lote 0 não é minutos: alinhar as listas exige decidir qual é a verdade, e a licença exige titular e ano. |
| EC6 | executor | O lote 4 está "dentro" na linha 109 e "se acontecer" na linha 121. |
| EC8 | executor | O limite de E6 ("maior que o build mais longo medido") não tem número no documento. |
| EC9 | executor | "Espera revisão" não é implementável: falta quem revisa, onde e quando. |
| EC11 | executor | Não há orçamento de esforço nem posição entre as 12 filas que já existem em `.claude/queues`. |
| SR1 | operador-sre | Um interruptor por variável de ambiente é herdado por todo filho do `cepa-until` e não deixa rastro de que foi usado. |
| SR2 | operador-sre | O ponto único por onde passariam os 53 hooks não diz se falha aberto ou fechado. |
| SR3 | operador-sre | Os lotes 1 a 3 mexem em hooks e no supervisor antes de existir uma versão marcada para voltar. |
| SR4 | operador-sre | `/plugin marketplace add` não passa pelo `bin/install.sh`, que é quem grava o registro e o ponto de rollback. |
| SR5 | operador-sre | E6 grava um evento que ninguém lê. |
| SR8 | operador-sre | Sessão real gravada carrega código de cliente e às vezes segredo, e o lote 0 põe licença e divulgação no mesmo repositório. |
| SR10 | operador-sre | A fila de revisão da memória não tem lugar onde aparece nem limite. |
| SR11 | operador-sre | O teto de E7 alarmaria sobre a soma do repositório, não sobre o que uma instalação carrega. |
| CM1 | custo-de-manutencao | E2 cria uma segunda fonte de verdade para 53 hooks e um custo permanente em cada hook novo. |
| CM2 | custo-de-manutencao | O conjunto de sessões é um segundo conjunto de testes rotulado à mão, que exige re-rotular a cada mudança de regra. |
| CM3 | custo-de-manutencao | O lote 4 troca um caminho de instalação por dois, e R5 congela o antigo. |
| CM4 | custo-de-manutencao | `build-solo` é a topologia em que os comandos `/board-flow` não funcionam, segundo o próprio `bin/install.sh` linha 394. |
| CM5 | custo-de-manutencao | Changelog escrito à mão sobre 12 versões independentes é trabalho manual sem fim. |
| CM6 | custo-de-manutencao | Uma fonte só para a lista de plugins dispensa o verificador de E5. |
| CM8 | custo-de-manutencao | Q3 troca custo de máquina por custo humano recorrente, sem dono nem limite. |
| CM9 | custo-de-manutencao | E6 acopla o supervisor ao formato da transcrição do Claude Code, que muda sem aviso. |
| OU1 | outsider | O cabeçalho diz "em exploração" e o corpo traz três decisões tomadas. |
| OU2 | outsider | O texto diz que os lotes 0 a 3 são o caminho P1, mas P1 exclui A1 e o lote 0 a inclui. |
| OU3 | outsider | A pergunta "o que falta para a adoção do ECC" não recebe resposta direta. |
| OU5 | outsider | Termos como topologia, `build-solo` e filho carregam decisão e nunca são apresentados. |

### Convergências

1. **A medição não tem data e o resto anda sem ela** (CR1, EC1, FU4, três lentes). Trecho: seção 7, "Lot 2 belongs to cycle 3". O ciclo 3 só abre depois do ciclo 2, que tem 0 de 2 itens feitos. E7, E8 e E9 não estão registrados em lugar nenhum.
2. **O interruptor de hooks é o item mais perigoso do plano** (FU1, SR1, SR2, CR8, CM1, EC3, cinco lentes, duas com severidade crítica). Trecho: seção 3 linha E2 e R2. Ele pode desligar um gate que o Epic declara invariante, a variável de ambiente vaza para a rodada desatendida, não há rastro de uso, e a lista fechada cobre 3 de 53.
3. **A regra de admissão do scorecard não foi aplicada** (CR6, FU2, EC11, três lentes). Trecho: seção 7 inteira. Conferi a regra em `docs/estrategia-cepa-proximo-nivel.md` linha 82.
4. **"Espera revisão" não tem desenho** (CR5, CM8, SR10, EC9, FU5, cinco lentes). Trecho: seção 9, Q3. Falta quem revisa, onde, com que limite, e o Epic ainda descreve o desenho anterior.
5. **E6 não está justificado e a primeira versão não devolve hora nenhuma** (CR2, EC8, SR5, CM9, mais o outsider, cinco lentes). Trecho: seção 3 linha E6 e R3. Conferi `docs/estrategia-durabilidade.md`: os 4 casos são "3 sem progresso + 1 com progresso", e a mesma estratégia só reabre a retomada de item acima de 5% dos fins de item. 4 ÷ 530 = 0,75%.
6. **`build-solo` como padrão colide com R5** (CR3, CM4, EC6, três lentes). Trecho: seção 7 lote 4.
7. **A suíte em todo push supõe uma suíte saudável** (CR4, EC4, mais operador-sre, custo-de-manutencao e fundamentalista, cinco lentes). Trecho: linha E4 e R4. Ninguém verificou se `tests/run-all.sh` passa, quanto demora ou se roda em Linux, e o documento não diz o que acontece com `.claude/no-build`.
8. **O teto de E7 mede o número errado** (SR11, mais custo-de-manutencao, outsider e executor, quatro lentes). O próprio documento diz que os 13.666 tokens são do repositório inteiro.
9. **Sessões reais gravadas num repositório público** (SR8, EC2, e CR7 sobre o convite a estranhos, três lentes).
10. **Derivar a lista de plugins em vez de vigiá-la** (EX6, CM6, duas lentes).
11. **O texto se contradiz** (OU1, OU2, EC6, EC5): status, definição dos caminhos, lote 4 dentro e condicional, lote 0 chamado de minutos.

### DISCORDÂNCIAS NOMEADAS

- **D1. O interruptor de hooks (E2).** **O expansionista diz para enriquecer** (EX2): o mesmo registro declara por hook se ele bloqueia e se é protegido, e R1 e R2 viram campos conferíveis. **O custo-de-manutencao diz para não construir** (CM1): é uma segunda fonte de verdade para 53 hooks, e a medição cabe no executor das sessões gravadas, sem interruptor em sessão real. **O fundamentalista e o operador-sre dizem que, como está, viola uma invariante e não deixa rastro** (FU1, SR1).
  - **O que decide entre elas:** se alguma medição planejada precisa desligar um hook dentro de uma sessão real. A comparação antes e depois (E1) não precisa, porque o executor chama o hook direto. Só o experimento com e sem gate precisa, e ele está "sem fila". Recomendação do sintetizador: não construir o interruptor agora. E1 vem primeiro e sozinho. O interruptor volta quando o experimento entrar em fila, e só obedecido quando o executor do experimento o liga, com evento gravado e com as invariantes do Epic na lista fechada.
  - **Decisão do dono:** 2026-11-12, sim à recomendação: o interruptor de hooks sai do plano imediato e só volta quando o experimento com e sem gate entrar em fila, obedecido apenas pelo executor do experimento, com evento gravado e as invariantes do Epic na lista fechada.

- **D2. O conjunto de sessões gravadas (E1).** **O expansionista diz para generalizar** (EX3): formato que sirva também à revisão da memória e ao experimento. **O custo-de-manutencao diz que ele apodrece** (CM2): cada mudança intencional de regra exige re-rotular. **O operador-sre e o executor dizem que sessão real não pode morar em repositório público** (SR8, EC2).
  - **O que decide entre elas:** se os cenários são gravações de sessões reais ou entradas de hook escritas à mão e pequenas. Recomendação do sintetizador: entradas sintéticas, sem dado de cliente, só para os três hooks que mais bloqueiam, no formato estreito que o `BACKLOG.md` já descreve. Generalizar só quando um segundo uso existir.
  - **Decisão do dono:** 2026-11-12, sim à recomendação: entradas de hook escritas à mão, sem dado de cliente, só para os três hooks que mais bloqueiam, no formato estreito do `BACKLOG.md`.

- **D3. Quando a medição acontece.** **O contrarian e o executor dizem para adiantar** (CR1, EC1): sem isso quatro lotes somam harness sem medida, que é a dor P1-4. **O fundamentalista diz que adiantar fura a ordem do Epic** (FU4): ciclo 3 vem depois do ciclo 2, e a quebra precisa ser explícita.
  - **O que decide entre elas:** se E1 é trabalho do ciclo 3 ou ferramenta de teste independente dele. Recomendação do sintetizador: adiantar só E1, fora do ciclo 3, porque é um teste e não toca nos hooks. E7, E8 e E9 ficam no ciclo 3 e passam a constar no Epic. A antecipação fica escrita no Epic com data.
  - **Decisão do dono:** 2026-11-12, sim à recomendação: só E1 é adiantado para fora do ciclo 3, com a antecipação escrita no Epic. E7, E8 e E9 ficam no ciclo 3 e passam a constar no Epic.

- **D4. Tags e registro de versões (A5).** **O expansionista e o operador-sre dizem para adiantar** (EX4, SR3): o scorecard do ciclo 3 e o rollback precisam de pontos nomeados no histórico. **O custo-de-manutencao e o fundamentalista dizem que A5 como escrito é trabalho manual sem fim e contradiz `docs/versionamento.md`** (CM5, FU7).
  - **O que decide entre elas:** se o que se quer é um ponto para voltar ou um texto para leitores. Recomendação do sintetizador: separar. Uma tag do repositório a cada fila aterrissada entra já, antes de qualquer lote que mexa em hook. O `CHANGELOG.md` escrito à mão sai do plano. A versão por plugin continua como `docs/versionamento.md` define.
  - **Decisão do dono:** 2026-11-12, sim à recomendação: uma tag do repositório a cada fila aterrissada, antes de qualquer lote que mexa em hook. O `CHANGELOG.md` manual sai do plano e a versão por plugin segue `docs/versionamento.md`.

- **D5. A memória que espera revisão (Q3).** **O dono decidiu esperar revisão.** **O contrarian diz que a fila de revisão não será lida** (CR5, 1 de 16 entradas de feedback triadas) e que o ciclo 3 perde a metade "aprender". **O expansionista diz que o handoff resolve** (EX7): a seção "o que não funcionou" é lida pelo dono e recebida pela sessão seguinte. **O custo-de-manutencao e o operador-sre exigem dono, lugar e limite** (CM8, SR10).
  - **O que decide entre elas:** onde a revisão acontece. Uma fila nova não será lida. Recomendação do sintetizador: manter Q3, com a linha candidata aparecendo dentro do relatório que o dono já lê ao fim de cada rodada desatendida (`/common:until-review`), como pergunta fechada, e expirando se não for respondida em N rodadas. A linha do ciclo 3 no Epic é corrigida antes de qualquer fila.
  - **Decisão do dono:** 2026-11-12, sim à recomendação: Q3 mantida, com a linha candidata como pergunta fechada no relatório de fim de rodada desatendida (`/common:until-review`), expirando se não for respondida. A linha do ciclo 3 no Epic foi corrigida.

- **D6. O tamanho da porta aberta (lote 4, Q1).** **O dono disse sim à forma mínima.** **O fundamentalista diz que mudar o público exige Epic próprio** (FU6). **O custo-de-manutencao e o contrarian dizem que são dois caminhos de instalação e nenhum critério de sucesso** (CM3, CR6), e que `build-solo` como padrão viola R5 (CR3, CM4). **O expansionista diz que a porta pode custar minutos** (EX10).
  - **O que decide entre elas:** se `/plugin marketplace add` já funciona hoje. Conferi no disco que o arquivo está em `.claude-plugin/marketplace.json`, que é o lugar padrão (a lente EX10 disse que estava na raiz e errou o lugar). Falta o teste numa máquina limpa. Recomendação do sintetizador: testar primeiro. Se funcionar, a porta aberta é licença, descrição e uma linha no README, e A3 e A4 saem do plano, porque esse caminho não usa o `bin/install.sh`. Se não funcionar, o lote 4 vira Epic próprio.
  - **Decisão do dono:** 2026-11-12, sim à recomendação: testado no mesmo dia. Com uma pasta de configuração vazia, `claude plugin marketplace add <pasta do repo>` e `claude plugin install common@cepa` e `build-solo@cepa` funcionaram. A porta aberta fica em licença, descrição e uma linha no README. A3 e A4 saem do plano. Não testado: adicionar a partir do GitHub, e abrir uma sessão num projeto sem `.claude/topology`.

### Propostas consolidadas priorizadas

1. **Tirar E2 do plano imediato e reescrever R2** (convergência 2, D1). Condicional a D1.
2. **Dar data à medição: E1 adiantado como teste, com entradas sintéticas** (convergências 1 e 9, D2, D3). Condicional a D2 e D3.
3. **Acrescentar à tabela da seção 7 a coluna "qual dos quatro números move"** e retirar ou declarar como exceção o que não mover nenhum (convergência 3).
4. **Corrigir a linha do ciclo 3 em `docs/epics/cepa-em-espiral.md`** para refletir Q3, e registrar E7, E8 e E9 no Epic (convergências 1 e 4, FU5). Condicional a D5 quanto ao desenho da revisão.
5. **Rebaixar E6 a condição**, como `docs/estrategia-durabilidade.md` já fez com a retomada de item: só entra se a causa dos 4 casos for verificada e for chamada de ferramenta presa (convergência 5).
6. **Tirar `build-solo` como padrão** até existir mecanismo que garanta R5 (convergência 6). Condicional a D6.
7. **Antes de E4, medir a suíte**: passa hoje, quanto demora, roda em Linux. Decidir o destino de `.claude/no-build` (convergência 7).
8. **Trocar E5 por derivação**: o resumo do instalador e a lista do `docs/getting-started.md` saem do `marketplace.json` (convergência 10).
9. **Adiar E7** até existir o número de uma instalação real (convergência 8).
10. **Mandar o conserto das 2 skills pela rota de item avulso**, sem esperar a estratégia (FU9), depois de um teste que mostre que o Claude Code não as carrega (CR10).
11. **Revisar o conteúdo do repositório para leitura de fora antes de pôr descrição e tópicos** (CR7). A licença pode entrar antes.
12. **Uma tag do repositório por fila aterrissada, sem changelog manual** (D4). Condicional a D4.
13. **Consertar o texto**: status, definição de P1 contra o lote 0, lote 4 dentro e condicional, termos sem apresentação, resposta direta à pergunta sobre adoção (convergência 11, OU3, OU5).
14. **Registrar que Q1, Q2 e Q3 foram respondidas antes do painel** e que ficam sujeitas a esta síntese (FU3).
15. **Compartilhar o leitor de transcrição entre E8 e E9** quando o ciclo 3 abrir (EX1).
