# Painel de advisors: estratégia "O Cepa no próximo nível"

**Artefato:** `docs/estrategia-cepa-proximo-nivel.md`, revisão 1 · **Data:** 2026-10-07 · **Área:** arquitetura (inferida; sessão sem dono na frente) · **Lentes:** contrarian, fundamentalista, expansionista, outsider, executor, operador-sre, custo-de-manutenção, rodadas em paralelo e isoladas (cada lente recebeu só o artefato e o próprio perfil). Síntese das discordâncias na seção 8 do artefato; decisões na seção 9.

## contrarian

**Veredito:** O2 reinventa o Maestro sem explicar por que o Maestro não virou o condutor, contradiz a decisão 3 do cepa-until que diz respeitar, e seus dois pontos de contato só mudam o momento em que o dono carimba, não a quantidade.

- (crítica) P2 é o Maestro com outro nome e o artefato não faz a autópsia do Maestro: `docs/maestro.md` já descreve fork em worktree, event loop, merge train e resume; a telemetria mostra que o condutor existente não roda. Sem saber por quê, P2 herda a causa de morte.
- (alta) P2 viola a decisão 3 do cepa-until (um commit por item, uma branch, sem merge train); o artefato atribuiu à decisão 3 o texto do R1 de 26/09. O conflito já está em O2, não só em O3.
- (alta) Dois pontos de contato mudam o momento do carimbo, não o número; e o drain-plan para no primeiro BLOCKED, então item estacionado ou trava o ciclo ou constrói sobre código não provado.
- (alta) F1, F3 e F11 misturam universos (telemetria vs. transcrições, sem corte antes/depois do default-yes); o scorecard é jogável ("turnos depois da rotina" zera com `claude -p`, "fração no cepa" sobe durante a empreitada do Cepa).
- (média) Tirar o build do modelo quebra o loop vermelho-verde; 377 path-lock e 396 reactor não somem; `expertise-append` e debrief já gravam aprendizado; `fresh-marker` não existe (é `fresh-root-install`).
- (média) "O dono não escreve critério de item nunca mais" é desmentido por R2 e pelos ciclos 3 e 4, que não têm tela; o ciclo 1 é provado numa demo que ele mesmo cria.
- (baixa) cepa-until tem 3.352 linhas, não 1.425; F5 chama de incapacidade uma regra que o dono escolheu (`CEPA_MODO` é variável de ambiente, `claude -p` já é aberto pelo harness).

## fundamentalista

**Veredito:** O2 é compatível com a doutrina no destino, mas chega lá contornando em silêncio quatro regras escritas: o custo deliberado da troca de modo, a entrada da Construção, a escrita do estado de build pelo modelo e o escopo de uma aprovação.

- (crítica) O condutor troca de modo por estágio e abre sessão irmã, apagando o custo que a Peça 2b de `docs/modos-de-trabalho.md` criou de propósito; e a entrada da Construção (teste vermelho por quem não implementa) fica sem autor nomeado.
- (crítica) "Aprovar a escada" vira consentimento em branco para quatro estágios, contra `scope-discipline` ("aprovação libera até o próximo checkpoint") e `precedencia-de-instrucoes`.
- (alta) Tirar o build das mãos do modelo contradiz `green-or-revert` (o `last-build.json` só vira SUCCESS por Bash do próprio agente); precisa de exceção declarada como a Revisão 3 fez.
- (alta) C3 e P3 reinventam o `default-yes` como instrução; a skill já diz isso e não foi obedecida; pelo README a resposta é trava, não texto.
- (média) `mode: espiral` ignora o escritor único e o versionamento do esquema do plan.yaml.
- (média) "A lista final só traz o irreversível" apaga dois dos três tipos de item do `plain-report`, inclusive a rota de validação humana.
- (média) O roteiro escolhe a altitude em vez de derivá-la (ciclo 3 é http, não tela) e substitui a saída da Descoberta (`evidence-auditor`) sem dizer.

## expansionista

**Veredito:** O2 acerta o centro de gravidade, mas desenha a empreitada um grau estreito demais (uma por repo, terceiro modo de plan.yaml, condutor só do cepa-until) e deixa na mesa a troca de modo em qualquer sessão, o Maestro como motor de ciclo e o roteiro como tutorial e manifesto de prova.

- (crítica) A empreitada precisa nascer multi-repo: o ciclo 3 do exemplo atravessa três repositórios e tudo o que P1 reusa é por repo. Um campo `repos:` custa pouco agora e muito depois.
- (alta) Modo por estágio não precisa esperar o P2: `/common:modos --delegar <modo> "<pedido>"` como filho `claude -p` com modo próprio resolve F5 hoje nas 136 sessões conduzidas.
- (alta) O condutor deveria nascer da união cepa-until + Maestro; o artefato não cita o Maestro fora de F6.
- (média) `mode: espiral` estreita onde uma camada acima generaliza: a empreitada lista ciclos, cada ciclo materializa um plan.yaml comum.
- (média) O roteiro de demonstração tem três consumidores (ui-proof, `docs:tutorial-author`, brief do `marketing`); fixar o formato agora faz tutorial e demo comercial saírem de graça.
- (média) O estacionamento do ciclo seria a quarta lista de pendências; um único estacionamento tipado lido pelo `decide` serve a P2, P3 e ao scorecard.
- (baixa) Scorecard só vira aprendizado se cada evento gravar a versão do plugin.

## outsider

**Veredito:** Persuasivo para quem viveu a conversa; um leitor de fora não reconstrói o que é o Cepa, seus componentes, nem por que O2 na ordem P1 → P3 → P2 decorre dos dados.

- (crítica) O sistema sob análise nunca é apresentado; modo, rotina, card, gate, hook, worktree, proof gate aparecem como vocabulário comum.
- (crítica) O cepa-until é a peça central e não é explicado (o que faz, as lições, as decisões numeradas).
- (alta) O salto de "o dono carimba" para "a pergunta é fabricada" não está demonstrado; não há contagem de "não".
- (alta) A ordem P1 → P3 → P2 não decorre do diagnóstico: C1 é a causa direta e P2, que a ataca, vai por último.
- (alta) O exemplo Contratos e Regras surge sem contexto (Cassi, 34 perguntas, ADR 0013).
- (média) F7, F8 e F10 apoiam conclusões que não decorrem deles (bloqueio útil vs. ruidoso; 20% no cepa pode ser investimento).
- (média) Os pontos de contato e o estacionamento não têm critério de triagem definido; quem classifica é o agente que F8 chama de não confiável.

## executor

**Veredito:** Só o scorecard do P3 dá para começar na segunda (o `cepa-metrics` já calcula três dos quatro números); o resto depende de decisões não tomadas, de artefatos inexistentes nos repos-alvo ou de reescrever um supervisor 2,4 vezes maior do que o documento afirma.

- (crítica) `mode: espiral` não tem escritor nem leitor; o `cepa-plan` recusa qualquer modo que não seja `single-track`, o `/common:next` recusa `parallel-waves`. Decidir: terceiro modo com schema v3, ou `single-track` por ciclo mais documento de empreitada.
- (crítica) O estágio "descoberta" sob `claude -p` não tem comando não-interativo: `/common:spec` é conversacional e suspende o default-yes; não existe tradutor de prosa para `docs/ui-proof.yaml`.
- (alta) O cepa-until monta `claude -p` sem passar pelo `cepa`, então todo filho noturno roda sem modo; "o gate continua no filho" exige escrever o arquivo de modo na worktree do estágio.
- (alta) O `no-background-build` só dispara sob `CEPA_UNTIL_RUN`; sem ele o build em `claude -p` morre em 15 segundos. Tirá-lo troca 506 bloqueios por 506 itens sem build.
- (alta) O ciclo 1 não tem superfície para o gate provar: faltam `docs/ui-proof.yaml`, `env.yaml` e Playwright no `wego-contratos-demo`, que nasce no próprio ciclo. Precisa de passo 0 com dono no repo-alvo.
- (média) "Recomendo sim deixa de existir" colide com a regra global do `~/.claude/CLAUDE.md` do dono, fora do repo.
- (média) "needs-human por ciclo" não tem numerador até o ciclo existir; publicar o scorecard com três números já, e a medição vem antes do P1.

## operador-sre

**Veredito:** Promove a única peça que sobrevive à noite (um item, um subprocesso, uma máquina de estado) a um condutor de quatro estágios sem dizer como se observa, interrompe ou desfaz um ciclo pela metade.

- (crítica) O condutor não tem registro de estado nem "onde parou"; o run 2003 de 28/09 morreu calado por SIGHUP e levou uma investigação. Precisa de `estado.json` por empreitada, `pendentes` que o enxergue e `fecha-morto` por estágio.
- (crítica) Falha parcial de ciclo vertical não tem unidade de rollback: a lateral do vermelho é por item, o ciclo é por jornada. Regra necessária: ciclo não aceito fica em branch própria e o seguinte espera.
- (alta) A cota de 5 horas é orçada por item; descoberta e prova têm custo não medido e a prova não dá para cortar pela metade.
- (alta) Tirar os hooks de higiene remove a detecção, não o comportamento; manter o guarda e tirar a conversa.
- (alta) "Reversível executa e registra" sem definição mecânica de reversível é ação irreversível às 3h sem rollback.
- (média) Memória escrita por hook e injetada em todo filho é configuração sem dono, versão ou rollback; precisa de proveniência e TTL.
- (média) Needs-human em item com dependentes trava os seguintes; deve encerrar o ciclo em `aguardando-dono` com aviso.

## custo-de-manutenção

**Veredito:** O2 adiciona três conceitos permanentes e um terceiro orquestrador a um harness com dois meio-aterrissados e 53 hooks; a poda está descrita como intenção, não como lista de arquivos que somem; na ordem P1 → P3 → P2 o custo chega antes do ganho.

- (crítica) Terceiro orquestrador ao lado de cepa-until (3.352 linhas) e `maestro:run` (dívida "onda termina e ninguém aterrissa"); escolher um e deprecar o outro.
- (alta) `mode: espiral` quebra o contrato de dois modos que todo consumidor recusa pelo nome.
- (alta) Modo por estágio cria dois regimes de modo convivendo, com um `if` em cada hook.
- (alta) A poda é intenção sem lista de remoção; os hooks só podem sair depois do P2, então P3 na prática entrega só o scorecard.
- (média) O artefato usa 1.425 linhas para um arquivo de 3.352, sem testes de unidade e com `main` na linha 2.251.
- (média) O estacionamento é a sexta fila de pendência (plan.yaml `human_pending`, `docs/proof`, `desvios.md`, coluna Review, `.review.md`).
- (baixa) O scorecard como gate exige calcular quatro números a cada merge; melhor como relatório semanal do `cepa-metrics`.
