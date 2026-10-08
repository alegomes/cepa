# Especificação: Cepa em espiral, ciclo 1 (Encadear)

**Status:** pronta-para-construir
**Aberta em:** 2026-10-08            **Fechada em:** 2026-10-08
**Epic:** `docs/epics/cepa-em-espiral.md`, ciclo 1 · **Estratégia:** `docs/estrategia-cepa-proximo-nivel.md`, decisões 2, 6, 8 e 10

## Problema
Hoje eu abro cada sessão, escolho o modo, colo o brief e decido quando a próxima começa. Ao fim de uma sessão o harness me diz "abra uma sessão nova em X" e eu digito. Também não tenho um número que diga se uma mudança no Cepa melhorou alguma coisa, e não tenho como escrever um pacote de trabalho por ciclos de demonstração: o harness só conhece card e fila.

## Escopo
### Entra
- Encadeamento de sessões pelo launcher `cepa`: a sessão que termina deixa o próximo passo gravado e o launcher abre a sessão seguinte no repo e no modo certos, com o brief, sem eu digitar.
- `/common:wrap-up` grava esse próximo passo a partir do handoff.
- Scorecard de três números no `cepa-metrics`.
- Comando `/common:epic` que entrevista o dono no estilo "grill me" e escreve `docs/epics/<nome>.md`.
- `/common:plan --from-epic` que deriva a fila de um ciclo, e `cepa-plan` aceitando `demonstra:` no cabeçalho.
### Não entra
- Condutor que roda construção, prova e aterrissagem sozinho: é o ciclo 2 do Epic.
- Poda de hooks, memória de bloqueio reincidente, versão do plugin na telemetria: ciclo 3.
- Terceiro modo no `plan-schema.yaml`: rejeitado pelo painel (decisão 2).
- Qualquer mudança no `~/.claude/CLAUDE.md` do dono: decisão 6 é feita à mão pelo dono, fora de fila.

## Estado e migração
`plan.yaml` existentes continuam válidos: `demonstra:` é opcional. Handoffs existentes sem a linha `Próximo:` continuam válidos: o launcher só encadeia quando o arquivo de próximo passo existe. Nenhum dado é migrado.

## Critérios de sucesso

### CS-1: `cepa-plan` aceita o campo `demonstra:` no cabeçalho de uma fila `single-track`
**Superfície:** cli
**Teste vermelho:** `cepa-plan validate` sobre um `plan.yaml` single-track com `demonstra: "o operador carrega o PDF e vê 3 respostas"` no cabeçalho devolve OK e `cepa-plan show` imprime o texto; hoje o campo é recusado como desconhecido pelo validador do `common/plan-schema.yaml`.

### CS-2: `cepa-metrics scorecard` imprime os três números com a conta
**Superfície:** cli
**Teste vermelho:** `cepa-metrics scorecard` sobre um diretório de telemetria e de transcrições de teste imprime três linhas, "turnos após rotina por sessão", "builds vermelhos" e "sessões no repo cepa", cada uma com numerador, denominador e resultado, para os últimos 7 dias e desde o início; hoje o subcomando não existe e o comando sai com erro.

### CS-3: o launcher `cepa` abre a sessão seguinte quando a anterior deixou o próximo passo gravado
**Superfície:** cli
**Teste vermelho:** com `.claude/sessions/<id>.next.json` contendo `{"repo": "<path>", "modo": "descoberta", "brief": "<texto>"}` escrito pela sessão que acabou de sair, o launcher `cepa` (em modo de teste, com `claude` substituído por um stub que registra argumentos) executa o stub uma segunda vez com cwd igual a `repo`, `--modo descoberta` e o brief como prompt inicial, e apaga o arquivo; hoje o launcher sai depois do primeiro `claude` e o arquivo não é lido.

### CS-4: `/common:wrap-up` grava o próximo passo a partir do handoff
**Superfície:** application
**Teste vermelho:** dado um handoff cuja zona NOTE contém a linha `**Próximo:** repo=/Users/alegomes/coding/wego/wego-product modo=descoberta comando=/common:epic contratos-e-regras`, o passo L7 do wrap-up escreve `.claude/sessions/<id>.next.json` com esses três campos e o brief igual ao parágrafo "Próximo passo" do handoff; sem a linha, não escreve nada e diz isso no relatório. Hoje o wrap-up não conhece a linha e o arquivo nunca existe.

### CS-5: `/common:epic <nome>` entrevista o dono no estilo "grill me" e escreve `docs/epics/<nome>.md`
**Superfície:** application
**Teste vermelho:** uma transcrição de teste do comando mostra: uma pergunta por turno, em prosa, nunca lista de opções; cada resposta do dono é desafiada uma vez antes de ser aceita ("quem vê isso e onde?", "o que quebra se faltar?") e a resposta aceita é gravada no arquivo no mesmo turno; o comando só grava `Status: pronta` quando cada ciclo da escada tem roteiro com efeito observável em tela e em backend, a lista de invariantes não está vazia e a seção "Decidido sem perguntar" existe; o hook `spec-readiness-gate` barra `Status: pronta` sem isso. Hoje o comando não existe.

### CS-6: `/common:plan --from-epic docs/epics/<nome>.md --ciclo N` deriva a fila do ciclo
**Superfície:** cli
**Teste vermelho:** sobre `docs/epics/cepa-em-espiral.md`, `/common:plan cepa-espiral-c2 --from-epic docs/epics/cepa-em-espiral.md --ciclo 2 --dry-run` imprime uma fila cujo cabeçalho tem `demonstra:` igual ao roteiro do ciclo 2 e um item por frase de "o que atravessa", cada item com critério de aceite e superfície, na ordem do texto; hoje `--from-epic` é flag desconhecida.

## Perguntas em aberto
- [x] Onde o launcher descobre o próximo passo? No arquivo `.claude/sessions/<id>.next.json` da raiz do clone, escrito pelo wrap-up; respondido pelo desenho do L7, que já usa `<id>.prune-on-exit` no mesmo lugar.
- [x] "Grill me" significa o quê? Uma pergunta por turno, em prosa, sem menu; a resposta é desafiada uma vez antes de ser aceita; o agente propõe a resposta e o dono corrige; gravação no mesmo turno; fecha pelo crivo, não por cansaço. Respondido pelo dono em 2026-10-08.

## Decidido sem perguntar
- `/common:epic` reusa a skill `guided-interrogation` e o hook `spec-readiness-gate` do `/common:spec`, com um crivo próprio para Epic (roteiro por ciclo + invariantes). Um comando novo em vez de flag no spec, porque o spec fecha com critérios e o epic fecha com roteiros.
- O brief do encadeamento é o parágrafo "Próximo passo" do handoff, não um arquivo novo. Vete aqui se discordar.
- O scorecard lê as mesmas fontes que o `cepa-metrics` já lê; os denominadores seguem a memória de cálculo de `docs/estrategia-cepa-proximo-nivel.md` seção 2 (F3, F8, F10).

## Riscos e o que ficou de fora desta especificação
- O launcher encadear sessões interativas exige que a sessão anterior saia de verdade; se o dono fecha o terminal em vez de dar `exit`, não há encadeamento. Aceito: é o comportamento de hoje.
- CS-5 é provado por transcrição de teste, não por teste automatizado sobre o modelo; o `proof-reviewer` deve marcar NEEDS-HUMAN se não houver transcrição.
