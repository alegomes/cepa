# Transcrição de teste: `/common:epic` (CS-5)

Duas transcrições: a rodada 4 (entrevista do zero, quatro turnos), a rodada 5 (Epic semeado até `pronta`, seis turnos) a rodada 6 (só o turno 1, regravado seis vezes) e a rodada 7 (turno 1, cinco gravações por cenário com o texto final: 10 de 10 com uma pergunta).

**Gravada em:** 2026-10-08, na branch `until/2026-10-08-2047`.
**Como:** `claude -p --plugin-dir common --model sonnet --permission-mode acceptEdits`, num repo git descartável com `.claude/session-mode` = `modo: descoberta` e só um README. Quatro turnos encadeados por `--resume`; as falas do dono são roteiro fixo (o script está ao fim). O arquivo `docs/epics/contratos-demo.md` foi copiado depois de cada turno.
**Custo:** soma do `total_cost_usd` dos quatro turnos, listado em cada um.

## O que o critério pede, e onde aparece aqui

| Pedido do CS-5 | Onde na transcrição |
|---|---|
| uma pergunta por turno, em prosa | turnos 1 a 4: um `?` por fala, sem lista (ressalva no turno 1, abaixo) |
| nunca lista de opções | nenhuma fala tem a), b), bullets ou `AskUserQuestion` |
| resposta desafiada uma vez antes de aceita | turno 2: a resposta do dono vira `- [ ]` provisória e o agente pergunta "o que quebra" |
| resposta aceita gravada no mesmo turno | turno 3: a Intenção recebe a resposta e a linha vira `- [x]`; turno 4: os invariantes entram e a segunda linha vira `- [x]` |
| só grava `pronta` quando passa no crivo | turno 4: o dono pede "pode marcar como pronta"; o Status fica `rascunho` (escada vazia) |

O crivo em si (o `spec-readiness-gate` barrando `Status: pronta` sem roteiro, tela, backend, invariante e "Decidido sem perguntar") é provado por `tests/test_epic_readiness_gate.py`, não por esta transcrição: aqui o agente nem tentou gravar `pronta`.

## Ressalvas desta rodada

- Turno 1: "Quando isso acontece com o operador, e o que ele faz com a resposta depois?" é uma frase com um `?`, mas duas perguntas ligadas por "e".
- Turno 4: o agente não marcou `pronta`, mas também não disse ao dono que recusou e por quê; seguiu para a pergunta do primeiro ciclo.

## Rodadas anteriores (o que cada uma mostrou e o que mudou)

1. Rodada 1 (antes de qualquer ajuste): o desafio do turno 2 saiu no formato de relatório (`**Pra você:**`, "Detalhe técnico", pergunta numerada com "Recomendo sim"), puxado pela regra global de `plain-report` e pelo `report-style-lint`, que trata como relatório todo turno com Edit/Write. Mudou: o comando diz que turno de entrevista é conversa, e o lint poupa o turno que só gravou `docs/epics/<nome>.md` ou `docs/spec/<slug>.md` e pergunta no último parágrafo.
2. Rodada 2: o lint ainda barrou dois turnos, que terminavam em "Corrija." depois da pergunta. Mudou: o lint aceita a pergunta em qualquer ponto do último parágrafo, e o comando põe a proposta antes da pergunta.
3. Rodada 3: zero bloqueios do lint; as perguntas dos turnos 1 e 3 enumeravam alternativas dentro da frase ("achar X, achar Y, ou entender Z?") e o turno 4 juntava duas perguntas. Mudou: o comando exige um único `?` por turno e proíbe alternativas enumeradas em linha.
4. Rodada 4: esta, abaixo. Zero bloqueios do lint no registro da sessão (`hook_blocking_error` = 0).

## Turno 1

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente** (US$ 0.202):

> Gravei o rascunho em `docs/epics/contratos-demo.md` com a sua frase de intenção. O repo não tem nada além do README, então as perguntas vão todas para você.
>
> Minha proposta é que a dor seja o operador ter uma dúvida concreta sobre um contrato, por exemplo "este plano cobre fisioterapia e com qual carência?", e hoje precisar abrir o PDF e caçar a resposta à mão. Quando isso acontece com o operador, e o que ele faz com a resposta depois?

**O que mudou em `docs/epics/contratos-demo.md` neste turno:**

```diff
@@ -0,0 +1,20 @@
+# Epic: contratos-demo
+
+**Status:** rascunho · **Aberto em:** 2026-10-08 · **Origem:** pedido do dono via /common:epic
+
+## Intenção
+
+O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.
+
+## Invariantes (nunca regridem)
+
+## Escada de valor
+
+| Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
+|---|---|---|---|---|---|
+
+## Decidido sem perguntar (vete aqui)
+
+## Perguntas em aberto
+
+## Riscos
```

## Turno 2

**Dono:**

> Quase isso. A pergunta é sempre a mesma: esse procedimento tem cobertura e com qual carência. Hoje ele liga para o setor de contratos e espera até dois dias.

**Agente** (US$ 0.236):

> Minha proposta é que a espera de dois dias seja o custo que importa, porque nesse tempo o operador não consegue dar retorno a quem perguntou a ele (beneficiário ou prestador). Se o operador passar a ter a resposta na hora e ela vier errada, o que quebra do lado dele e de quem recebe a informação?

**O que mudou em `docs/epics/contratos-demo.md` neste turno:**

```diff
@@ -17,4 +17,6 @@
 
 ## Perguntas em aberto
 
+- [ ] Qual é a dor, e o que quebra se o operador continuar sem resposta imediata? (provisória: a pergunta é sempre a mesma, "esse procedimento tem cobertura e com qual carência"; hoje o operador liga para o setor de contratos e espera até dois dias)
+
 ## Riscos
```

## Turno 3

**Dono:**

> Sim, sem a cláusula e a página ele continua ligando. A resposta tem que vir com o trecho e a página.

**Agente** (US$ 0.276):

> Minha proposta é que "toda resposta traz o trecho e a página" seja o primeiro invariante, porque foi o que você disse que decide se ele para de ligar. Quando o sistema não achar a cláusula, a tela deveria dizer "não encontrei no contrato" em vez de arriscar um palpite. O que o operador deveria ver nesse caso?

**O que mudou em `docs/epics/contratos-demo.md` neste turno:**

```diff
@@ -6,6 +6,8 @@
 
 O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.
 
+A pergunta é sempre a mesma: "esse procedimento tem cobertura e com qual carência?". Hoje o operador liga para o setor de contratos e espera até dois dias. A resposta só substitui a ligação se vier com o trecho da cláusula e a página; sem isso, ele continua ligando.
+
 ## Invariantes (nunca regridem)
 
 ## Escada de valor
@@ -17,6 +19,7 @@
 
 ## Perguntas em aberto
 
-- [ ] Qual é a dor, e o que quebra se o operador continuar sem resposta imediata? (provisória: a pergunta é sempre a mesma, "esse procedimento tem cobertura e com qual carência"; hoje o operador liga para o setor de contratos e espera até dois dias)
+- [x] Qual é a dor, e o que quebra se a resposta vier sem comprovação? A pergunta é sempre "esse procedimento tem cobertura e com qual carência"; hoje o operador liga ao setor de contratos e espera até dois dias; sem o trecho da cláusula e a página, ele continua ligando.
+- [ ] Invariante candidata: toda resposta traz o trecho da cláusula e a página. O que o operador vê quando o sistema não acha a cláusula? (sem resposta ainda)
 
 ## Riscos
```

## Turno 4

**Dono:**

> Está bom assim, pode marcar o Epic como pronta agora.

**Agente** (US$ 0.316):

> Minha proposta é um ciclo inicial só: o operador sobe um PDF de contrato, digita o procedimento e vê na tela cobertura, carência, o trecho da cláusula e a página. Eu faria assim porque é o menor pedaço que já substitui a ligação para um contrato. Esse ciclo sozinho já te serve para demonstrar valor, ou o operador precisaria de mais alguma coisa antes de você considerar que ele parou de ligar?

**O que mudou em `docs/epics/contratos-demo.md` neste turno:**

```diff
@@ -10,6 +10,9 @@
 
 ## Invariantes (nunca regridem)
 
+- Toda resposta traz o trecho da cláusula e a página; sem isso o operador continua ligando ao setor de contratos.
+- Quando o sistema não acha a cláusula, a tela diz "não encontrei no contrato" e não arrisca palpite.
+
 ## Escada de valor
 
 | Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
@@ -20,6 +23,6 @@
 ## Perguntas em aberto
 
 - [x] Qual é a dor, e o que quebra se a resposta vier sem comprovação? A pergunta é sempre "esse procedimento tem cobertura e com qual carência"; hoje o operador liga ao setor de contratos e espera até dois dias; sem o trecho da cláusula e a página, ele continua ligando.
-- [ ] Invariante candidata: toda resposta traz o trecho da cláusula e a página. O que o operador vê quando o sistema não acha a cláusula? (sem resposta ainda)
+- [x] Invariante: toda resposta traz o trecho e a página. O que o operador vê quando o sistema não acha a cláusula? "Não encontrei no contrato", sem palpite (proposta do agente, aceita pelo dono: "está bom assim").
 
 ## Riscos
```

## Arquivo ao fim do turno 4

```markdown
# Epic: contratos-demo

**Status:** rascunho · **Aberto em:** 2026-10-08 · **Origem:** pedido do dono via /common:epic

## Intenção

O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

A pergunta é sempre a mesma: "esse procedimento tem cobertura e com qual carência?". Hoje o operador liga para o setor de contratos e espera até dois dias. A resposta só substitui a ligação se vier com o trecho da cláusula e a página; sem isso, ele continua ligando.

## Invariantes (nunca regridem)

- Toda resposta traz o trecho da cláusula e a página; sem isso o operador continua ligando ao setor de contratos.
- Quando o sistema não acha a cláusula, a tela diz "não encontrei no contrato" e não arrisca palpite.

## Escada de valor

| Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|

## Decidido sem perguntar (vete aqui)

## Perguntas em aberto

- [x] Qual é a dor, e o que quebra se a resposta vier sem comprovação? A pergunta é sempre "esse procedimento tem cobertura e com qual carência"; hoje o operador liga ao setor de contratos e espera até dois dias; sem o trecho da cláusula e a página, ele continua ligando.
- [x] Invariante: toda resposta traz o trecho e a página. O que o operador vê quando o sistema não acha a cláusula? "Não encontrei no contrato", sem palpite (proposta do agente, aceita pelo dono: "está bom assim").

## Riscos
```

## Script que gerou a transcrição

```bash
#!/bin/bash
set -u
PLUG=/Users/alegomes/cepa-worktrees/cepa-until-2026-10-08-2047/common
R=/tmp/cs5-epic-repo5; OUT=/tmp/cs5-transcript4; rm -rf $R $OUT; mkdir -p $R/.claude $OUT
cd $R; git init -q; printf 'modo: descoberta\n' > .claude/session-mode
printf '# demo\nRepo de demonstração: lê contratos de operadora de saúde em PDF.\n' > README.md
git add -A; git commit -qm init
TURNS=(
"/common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas."
"Quase isso. A pergunta é sempre a mesma: esse procedimento tem cobertura e com qual carência. Hoje ele liga para o setor de contratos e espera até dois dias."
"Sim, sem a cláusula e a página ele continua ligando. A resposta tem que vir com o trecho e a página."
"Está bom assim, pode marcar o Epic como pronta agora."
)
SID=""
for i in "${!TURNS[@]}"; do
  n=$((i+1))
  if [ -z "$SID" ]; then RES=(); else RES=(--resume "$SID"); fi
  timeout 540 claude -p ${RES[@]+"${RES[@]}"} --plugin-dir "$PLUG" --model sonnet --permission-mode acceptEdits --max-budget-usd 3 --output-format json "${TURNS[$i]}" > $OUT/t$n.json 2>$OUT/t$n.err
  echo "turno $n exit=$?"
  SID=$(python3 -c "import json;print(json.load(open('$OUT/t$n.json'))['session_id'])")
  printf '%s' "${TURNS[$i]}" > $OUT/t$n.dono.txt
  cp $R/docs/epics/contratos-demo.md $OUT/t$n.arquivo.md 2>/dev/null || echo "(sem arquivo)" > $OUT/t$n.arquivo.md
done
echo "session=$SID"
```


# Rodada 5: Epic semeado até `pronta` (depois da revisão de 61b71db)

**Gravada em:** 2026-10-08, sobre o commit c9d8ee1. **Por quê:** o completion-auditor marcou INCOMPLETE sobre a rodada 4: faltava o desafio sobre roteiro ou efeito, faltava o caso em que o Epic passa no crivo e vira `pronta`, e o pedido de `pronta` antes da hora foi recusado em silêncio. O comando passou a mandar recusar em voz alta.
**Como:** mesmo método da rodada 4, seis turnos, partindo de `docs/epics/contratos-demo.md` já com intenção, um invariante, "Decidido sem perguntar" e o ciclo 1 com roteiro, mas com "Efeito em tela" e "Efeito em backend" vazios (o arquivo de partida está abaixo). Custo: 0.192 + 0.229 + 0.269 + 0.284 + 0.319 + 0.371 = US$ 1.66. Bloqueios de hook no registro da sessão: 0.

| Pedido do CS-5 | Onde nesta rodada |
|---|---|
| desafio antes de aceitar | turno 2 (efeito em tela: "o que o operador vê quando o contrato não diz nada?") e turno 5 (backend: "o que quebra se o registro não guardar o trecho?"); cada um vira `- [ ]` provisória |
| resposta aceita gravada no mesmo turno | turno 3: a célula "Efeito em tela" é preenchida e a linha vira `- [x]`; turno 6: a célula "Efeito em backend" é preenchida e a linha vira `- [x]` |
| discordância que sobra vai para Riscos, sem segundo desafio | turnos 3 e 6 (contrato omisso; registro sem trecho) |
| recusa de `pronta` antes do crivo, dita em voz alta | turno 4: "A coluna Efeito em backend do ciclo 1 está vazia" |
| grava `pronta` quando o crivo passa | turno 6: Status `rascunho` vira `pronta`, com o relatório de fechamento e o próximo passo `/common:plan ... --from-epic ... --ciclo 1` |

**Ressalvas desta rodada:** o turno 1 ainda junta duas perguntas numa frase ("Onde, na tela, ..., e o que ele precisa enxergar ali...?"); o desafio do turno 2 não é literalmente "quem vê isso e onde?", e sim uma pergunta sobre o caso omisso (o comando admite "apontada para o buraco mais caro"); o dono não respondeu esse desafio e o agente aceitou a resposta e registrou a discordância em Riscos, como o comando manda.

## Arquivo de partida

```markdown
# Epic: contratos-demo

**Status:** rascunho · **Aberto em:** 2026-10-08 · **Origem:** pedido do dono via /common:epic

## Intenção

O operador da operadora quer saber se um procedimento tem cobertura e com qual carência sem ligar para o setor de contratos, que hoje leva até dois dias para responder.

## Invariantes (nunca regridem)

- Toda resposta sobre cobertura e carência vem com o trecho literal do contrato e a página do PDF.

## Escada de valor

| Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
| 1. Um contrato | O operador escolhe um contrato já carregado, digita "ressonância magnética" e vê cobertura, carência, o trecho e a página. |  |  | Extrator de cláusulas do PDF. Tela de consulta. | próxima quinzena |

## Decidido sem perguntar (vete aqui)

- Um contrato por vez no ciclo 1; vários contratos ficam para depois.

## Perguntas em aberto

- [x] O que o operador pergunta ao contrato? Aceita: sempre "tem cobertura e com qual carência".

## Riscos
```

## Rodada 5, turno 1

**Dono:**

> /common:epic contratos-demo

**Agente** (US$ 0.192):

> Retomei o rascunho. Intenção, invariante e roteiro do ciclo 1 já estão gravados. O repo só tem um README e nenhum código, então a lacuna mais próxima é o "Efeito em tela" do ciclo 1.
>
> Minha proposta é que, na própria tela de consulta, o operador veja um cartão com "Coberto" ou "Não coberto", a carência em dias, o trecho literal do contrato e "p. N" ao lado. Eu faria esse "p. N" abrir o PDF direto naquela página, porque é assim que o operador confere o trecho sem pedir ao setor de contratos. Onde, na tela, o operador deveria ver que a consulta deu certo, e o que ele precisa enxergar ali para confiar na resposta?

**O que mudou no arquivo neste turno:**

```diff
(sem mudança)
```

## Rodada 5, turno 2

**Dono:**

> Na tela de consulta aparece um cartão com 'Coberto' ou 'Não coberto', a carência em dias, o trecho e o número da página.

**Agente** (US$ 0.229):

> Gravei sua resposta como provisória em "Perguntas em aberto".
>
> O buraco que vejo é este: o cartão só tem "Coberto" e "Não coberto", e os dois trazem trecho e página. Se o contrato for omisso sobre o procedimento, não existe trecho nem página para mostrar. O cartão diria "Não coberto" sem ter base no contrato, e isso quebraria a invariante de que toda resposta vem com o trecho literal. Minha proposta é um terceiro estado, "Não encontrei no contrato", sem veredito, para o operador ligar ao setor de contratos só nesse caso. O que o operador vê na tela quando o contrato não diz nada sobre o procedimento digitado?

**O que mudou no arquivo neste turno:**

```diff
@@ -24,4 +24,6 @@
 
 - [x] O que o operador pergunta ao contrato? Aceita: sempre "tem cobertura e com qual carência".
 
+- [ ] Onde, na tela, o operador vê que a consulta deu certo? Desafiada: o que o cartão mostra quando o contrato não diz nada sobre o procedimento? (provisória: cartão na tela de consulta com "Coberto" ou "Não coberto", carência em dias, trecho e número da página)
+
 ## Riscos
```

## Rodada 5, turno 3

**Dono:**

> Quem vê é o operador da central, na tela de consulta, logo depois de clicar em Consultar. Ninguém mais.

**Agente** (US$ 0.269):

> Gravei o "Efeito em tela" do ciclo 1, e o contrato omisso ficou em "Riscos".
>
> Agora o "Efeito em backend": o que prova que a consulta aconteceu de verdade, e não só que a tela mostrou algo. Minha proposta é que cada clique em Consultar grave um registro com contrato, texto digitado, veredito, página e trecho devolvidos, operador e horário. Assim dá para conferir depois, sem olhar a tela, que a resposta veio do contrato. Que registro, endpoint ou evento deveria existir no backend depois de um Consultar?

**O que mudou no arquivo neste turno:**

```diff
@@ -14,7 +14,7 @@
 
 | Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
 |---|---|---|---|---|---|
-| 1. Um contrato | O operador escolhe um contrato já carregado, digita "ressonância magnética" e vê cobertura, carência, o trecho e a página. |  |  | Extrator de cláusulas do PDF. Tela de consulta. | próxima quinzena |
+| 1. Um contrato | O operador escolhe um contrato já carregado, digita "ressonância magnética" e vê cobertura, carência, o trecho e a página. | Na tela de consulta, logo depois de clicar em Consultar, o operador da central vê um cartão com "Coberto" ou "Não coberto", a carência em dias, o trecho e o número da página. Ninguém mais vê. |  | Extrator de cláusulas do PDF. Tela de consulta. | próxima quinzena |
 
 ## Decidido sem perguntar (vete aqui)
 
@@ -24,6 +24,8 @@
 
 - [x] O que o operador pergunta ao contrato? Aceita: sempre "tem cobertura e com qual carência".
 
-- [ ] Onde, na tela, o operador vê que a consulta deu certo? Desafiada: o que o cartão mostra quando o contrato não diz nada sobre o procedimento? (provisória: cartão na tela de consulta com "Coberto" ou "Não coberto", carência em dias, trecho e número da página)
+- [x] Onde, na tela, o operador vê que a consulta deu certo? Aceita: na tela de consulta, logo depois de clicar em Consultar, o operador da central vê um cartão com "Coberto" ou "Não coberto", a carência em dias, o trecho e o número da página. Ninguém mais vê. (O desafio sobre o contrato omisso não foi respondido; foi para Riscos.)
 
 ## Riscos
+
+- Contrato omisso: o cartão só tem "Coberto" e "Não coberto", e os dois exigem trecho e página. Se o contrato não diz nada sobre o procedimento, o cartão afirmaria "Não coberto" sem trecho, contra a invariante. Proposta do agente, não aceita pelo dono: um terceiro estado, "Não encontrei no contrato", sem veredito.
```

## Rodada 5, turno 4

**Dono:**

> Pode marcar o Epic como pronta agora.

**Agente** (US$ 0.284):

> Ainda não dá para marcar `pronta`. A coluna **Efeito em backend** do ciclo 1 está vazia, e o crivo exige que ela esteja preenchida. Não vou encher a célula só para passar. A seção "Decidido sem perguntar" já existe, e não há `- [ ]` em aberto.
>
> Falta só o registro, endpoint ou evento que prova que a consulta aconteceu de verdade. Minha proposta continua sendo um registro por clique em Consultar, com contrato, texto digitado, veredito, página, trecho, operador e horário. O que deveria existir no backend depois de um Consultar?

**O que mudou no arquivo neste turno:**

```diff
(sem mudança)
```

## Rodada 5, turno 5

**Dono:**

> No backend, a consulta grava um registro em consultas_cobertura com o id do contrato, o procedimento, a resposta e a página citada.

**Agente** (US$ 0.319):

> Gravei a resposta como provisória em "Perguntas em aberto". Falta o desafio, e só depois dele o Epic pode virar `pronta`.
>
> O registro em `consultas_cobertura` guarda a página, mas não o trecho. A invariante diz que toda resposta vem com o trecho literal do contrato. Sem o trecho gravado, ninguém consegue conferir depois, só pelo registro, se a resposta foi fiel ao contrato. Se o PDF mudar, nem a página basta para reconstruir o que o operador viu. Minha proposta é gravar o trecho junto com a página, e também o operador e o horário. O que quebra se o registro guardar a página e não o trecho devolvido?

**O que mudou no arquivo neste turno:**

```diff
@@ -25,6 +25,7 @@
 - [x] O que o operador pergunta ao contrato? Aceita: sempre "tem cobertura e com qual carência".
 
 - [x] Onde, na tela, o operador vê que a consulta deu certo? Aceita: na tela de consulta, logo depois de clicar em Consultar, o operador da central vê um cartão com "Coberto" ou "Não coberto", a carência em dias, o trecho e o número da página. Ninguém mais vê. (O desafio sobre o contrato omisso não foi respondido; foi para Riscos.)
+- [ ] O que prova no backend que a consulta aconteceu de verdade? Desafiada: o que quebra se o registro não guardar o trecho devolvido? (provisória: a consulta grava um registro em consultas_cobertura com o id do contrato, o procedimento, a resposta e a página citada)
 
 ## Riscos
 
```

## Rodada 5, turno 6

**Dono:**

> Se faltar esse registro, a auditoria não consegue provar o que foi dito ao beneficiário. Mantém.

**Agente** (US$ 0.371):

> O Epic `contratos-demo` está `pronta`. Ele define o que o operador da central vê no fim do ciclo 1: o cartão de cobertura e carência com trecho e página, e o registro que prova a consulta no backend.
>
> **Pra você:** 2 perguntas fechadas esperam por você, no fim.
>
> ### Detalhe técnico
>
> - **Arquivo:** `docs/epics/contratos-demo.md`.
> - **Crivo (as quatro condições para `pronta`):**
>   - O ciclo 1 tem Roteiro, Efeito em tela e Efeito em backend preenchidos.
>   - Há um item em Invariantes: toda resposta traz o trecho literal e a página.
>   - A seção "Decidido sem perguntar" existe.
>   - Nenhuma `- [ ]` sobrou em "Perguntas em aberto".
> - **Efeito em tela:** o operador da central vê, na tela de consulta e logo depois de clicar em Consultar, um cartão com Coberto ou Não coberto, a carência em dias, o trecho e a página.
> - **Efeito em backend:** cada consulta grava um registro em `consultas_cobertura` com o id do contrato, o procedimento, a resposta e a página citada.
> - **Dois riscos nomeados em "Riscos"**, porque a discordância sobrou depois do desafio:
>   - **Contrato omisso:** o cartão só tem Coberto e Não coberto. Se o contrato não diz nada sobre o procedimento, o cartão afirmaria "Não coberto" sem trecho, contra a invariante.
>   - **Registro sem trecho:** `consultas_cobertura` guarda a página, mas não o trecho literal, nem operador e horário. A auditoria não confere o trecho pelo registro, e se o PDF mudar a página sozinha não reconstrói o que o operador viu.
> - **O hook `spec-readiness-gate` não barrou a escrita.**
> - **Doctor:** o `/common:doctor` ainda não rodou neste repo (uns 30s). Não rodei porque você não pediu.
>
> ### Decisões e próximos passos
>
> 1. Adiciono ao ciclo 1 um terceiro estado cego, "Não encontrei no contrato", para o contrato omisso? Recomendo sim: sem ele o cartão afirma "Não coberto" sem trecho e quebra a invariante.
> 2. Acrescento trecho, operador e horário ao registro `consultas_cobertura`? Recomendo sim: sem o trecho gravado a auditoria não prova o que foi dito ao beneficiário, que foi o motivo que você deu para manter o registro.
>
> Se não tiver opinião, responda sim aos dois. O próximo passo é `/common:plan contratos-demo-c1 --from-epic docs/epics/contratos-demo.md --ciclo 1`, que deriva a fila do primeiro ciclo.

**O que mudou no arquivo neste turno:**

```diff
@@ -1,6 +1,6 @@
 # Epic: contratos-demo
 
-**Status:** rascunho · **Aberto em:** 2026-10-08 · **Origem:** pedido do dono via /common:epic
+**Status:** pronta · **Aberto em:** 2026-10-08 · **Origem:** pedido do dono via /common:epic
 
 ## Intenção
 
@@ -14,7 +14,7 @@
 
 | Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
 |---|---|---|---|---|---|
-| 1. Um contrato | O operador escolhe um contrato já carregado, digita "ressonância magnética" e vê cobertura, carência, o trecho e a página. | Na tela de consulta, logo depois de clicar em Consultar, o operador da central vê um cartão com "Coberto" ou "Não coberto", a carência em dias, o trecho e o número da página. Ninguém mais vê. |  | Extrator de cláusulas do PDF. Tela de consulta. | próxima quinzena |
+| 1. Um contrato | O operador escolhe um contrato já carregado, digita "ressonância magnética" e vê cobertura, carência, o trecho e a página. | Na tela de consulta, logo depois de clicar em Consultar, o operador da central vê um cartão com "Coberto" ou "Não coberto", a carência em dias, o trecho e o número da página. Ninguém mais vê. | Cada consulta grava um registro em consultas_cobertura com o id do contrato, o procedimento, a resposta e a página citada. Sem ele, a auditoria não prova o que foi dito ao beneficiário. | Extrator de cláusulas do PDF. Tela de consulta. | próxima quinzena |
 
 ## Decidido sem perguntar (vete aqui)
 
@@ -25,8 +25,10 @@
 - [x] O que o operador pergunta ao contrato? Aceita: sempre "tem cobertura e com qual carência".
 
 - [x] Onde, na tela, o operador vê que a consulta deu certo? Aceita: na tela de consulta, logo depois de clicar em Consultar, o operador da central vê um cartão com "Coberto" ou "Não coberto", a carência em dias, o trecho e o número da página. Ninguém mais vê. (O desafio sobre o contrato omisso não foi respondido; foi para Riscos.)
-- [ ] O que prova no backend que a consulta aconteceu de verdade? Desafiada: o que quebra se o registro não guardar o trecho devolvido? (provisória: a consulta grava um registro em consultas_cobertura com o id do contrato, o procedimento, a resposta e a página citada)
+- [x] O que prova no backend que a consulta aconteceu de verdade? Aceita: a consulta grava um registro em consultas_cobertura com o id do contrato, o procedimento, a resposta e a página citada. Se faltar, a auditoria não prova o que foi dito ao beneficiário.
 
 ## Riscos
 
+- O registro em consultas_cobertura não guarda o trecho literal devolvido, nem operador e horário. A invariante exige o trecho em toda resposta, mas a auditoria não consegue conferir o trecho pelo registro, e se o PDF mudar a página sozinha não reconstrói o que o operador viu. Proposta do agente, não aceita pelo dono: gravar também trecho, operador e horário.
+
 - Contrato omisso: o cartão só tem "Coberto" e "Não coberto", e os dois exigem trecho e página. Se o contrato não diz nada sobre o procedimento, o cartão afirmaria "Não coberto" sem trecho, contra a invariante. Proposta do agente, não aceita pelo dono: um terceiro estado, "Não encontrei no contrato", sem veredito.
```

## Script da rodada 5

```bash
#!/bin/bash
set -u
PLUG=/Users/alegomes/cepa-worktrees/cepa-until-2026-10-08-2047/common
R=/tmp/cs5-epic-seed; OUT=/tmp/cs5-transcript-seed; rm -rf $R $OUT; mkdir -p $R/.claude $R/docs/epics $OUT
cd $R; git init -q; printf 'modo: descoberta\n' > .claude/session-mode
printf '# demo\nRepo de demonstração: lê contratos de operadora de saúde em PDF.\n' > README.md
cat > docs/epics/contratos-demo.md <<'MD'
# Epic: contratos-demo

**Status:** rascunho · **Aberto em:** 2026-10-08 · **Origem:** pedido do dono via /common:epic

## Intenção

O operador da operadora quer saber se um procedimento tem cobertura e com qual carência sem ligar para o setor de contratos, que hoje leva até dois dias para responder.

## Invariantes (nunca regridem)

- Toda resposta sobre cobertura e carência vem com o trecho literal do contrato e a página do PDF.

## Escada de valor

| Ciclo | Roteiro de demonstração (o que o dono vê) | Efeito em tela | Efeito em backend | O que atravessa | Quando |
|---|---|---|---|---|---|
| 1. Um contrato | O operador escolhe um contrato já carregado, digita "ressonância magnética" e vê cobertura, carência, o trecho e a página. |  |  | Extrator de cláusulas do PDF. Tela de consulta. | próxima quinzena |

## Decidido sem perguntar (vete aqui)

- Um contrato por vez no ciclo 1; vários contratos ficam para depois.

## Perguntas em aberto

- [x] O que o operador pergunta ao contrato? Aceita: sempre "tem cobertura e com qual carência".

## Riscos
MD
git add -A; git commit -qm init
TURNS=(
"/common:epic contratos-demo"
"Na tela de consulta aparece um cartão com 'Coberto' ou 'Não coberto', a carência em dias, o trecho e o número da página."
"Quem vê é o operador da central, na tela de consulta, logo depois de clicar em Consultar. Ninguém mais."
"Pode marcar o Epic como pronta agora."
"No backend, a consulta grava um registro em consultas_cobertura com o id do contrato, o procedimento, a resposta e a página citada."
"Se faltar esse registro, a auditoria não consegue provar o que foi dito ao beneficiário. Mantém."
)
SID=""
for i in "${!TURNS[@]}"; do
  n=$((i+1))
  if [ -z "$SID" ]; then RES=(); else RES=(--resume "$SID"); fi
  timeout 540 claude -p ${RES[@]+"${RES[@]}"} --plugin-dir "$PLUG" --model sonnet --permission-mode acceptEdits --max-budget-usd 3 --output-format json "${TURNS[$i]}" > $OUT/t$n.json 2>$OUT/t$n.err
  echo "turno $n exit=$?"
  SID=$(python3 -c "import json;print(json.load(open('$OUT/t$n.json'))['session_id'])")
  printf '%s' "${TURNS[$i]}" > $OUT/t$n.dono.txt
  cp $R/docs/epics/contratos-demo.md $OUT/t$n.arquivo.md
done
cp $OUT/../cs5-transcript-seed/t1.arquivo.md /dev/null 2>&1
git -C $R show HEAD:docs/epics/contratos-demo.md > $OUT/t0.arquivo.md
echo "session=$SID"
```


# Rodada 6: só o turno 1, regravado (depois da reauditoria de d21e45b)

**Por quê:** a reauditoria fechou desafio, gravação no mesmo turno e `pronta`, e deixou uma lacuna: nas rodadas 4 e 5 o turno 1 juntava duas perguntas com "e" numa frase com um só `?`.

**O que mudou no comando, em duas etapas:**
- Etapa A: "Antes de encerrar o turno, releia a pergunta" e corte o segundo pedido ligado por "e".
- Etapa B: a lacuna 1 ("o que o dono quer e o que hoje dói") virou dois turnos. Era o próprio comando pedindo a pergunta dupla.

**Resultado, contado pergunta a pergunta** (uma pergunta = um pedido; "X, e Y?" conta como dupla):

| Gravação | Texto do comando | Cenário | Perguntas no turno 1 |
|---|---|---|---|
| semeado-1 | etapa A | Epic retomado | 1 |
| semeado-2 | etapa A | Epic retomado | 1 |
| zero-1 (A) | etapa A | Epic do zero | 2 ("qual a situação real..., e o que acontece hoje...?") |
| zero-2 (A) | etapa A | Epic do zero | 2 ("o que estava tentando descobrir, e o que aconteceu...?") |
| zero-1 (B) | etapa B | Epic do zero | 2 ("como essa pessoa descobre e o que faz esse caminho doer?") |
| zero-2 (B) | etapa B | Epic do zero | 1 |

Conta: com o texto final (etapa B), o Epic do zero saiu com uma pergunta em 1 de 2 gravações (50%). O Epic retomado saiu com uma pergunta em 2 de 2 com a etapa A, e a etapa B não muda nada nele (só mexe na lacuna da intenção, que no semeado já está preenchida). Nos turnos 2 em diante das rodadas 4 e 5 (8 turnos), 0 perguntas duplas. Isto é comportamento do modelo, não do hook: nenhum gate mecânico conta perguntas, e o texto do comando é a única alavanca.

### semeado-1 (US$ 0.184) · etapa A

**Dono:**

> /common:epic contratos-demo

**Agente:**

> Retomei o rascunho. Falta o **Efeito em tela** do ciclo 1, e Efeito em backend também, mas esse vem depois.
>
> Minha proposta é que, depois de digitar "ressonância magnética", o operador veja na própria tela de consulta um cartão com "Coberto" ou "Não coberto", a carência em dias, o trecho literal da cláusula e "página N do PDF". Faço assim porque o invariante exige trecho e página junto da resposta, e a tela de consulta já é onde ele digita. Onde na tela o operador deveria ver isso?

### semeado-2 (US$ 0.197) · etapa A

**Dono:**

> /common:epic contratos-demo

**Agente:**

> Retomei o rascunho. Intenção, invariante e roteiro do ciclo 1 já estão gravados, e faltam as colunas **Efeito em tela** e **Efeito em backend** desse ciclo. Ainda não gravei nada neste turno, porque não houve resposta nova.
>
> Minha proposta: depois de digitar "ressonância magnética", o operador vê abaixo do campo de busca um cartão. No topo ficam "Cobertura: sim" e "Carência: N dias". Embaixo vem o trecho literal entre aspas e "contrato X, página N", e clicar na página abre o PDF nela. Eu proponho isso porque o invariante promete trecho e página, e o operador só confia na resposta se conseguir conferir ali mesmo.
>
> Na tela de consulta, o que o operador precisa ver para saber que a resposta veio do contrato e não de um chute do sistema?

### zero-1 (US$ 0.202) · etapa A

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente:**

> Gravei a intenção inicial em `docs/epics/contratos-demo.md` (status rascunho). O repo só tem um README, então não há código nem docs que respondam o que vem a seguir.
>
> Minha proposta é que a dor hoje seja o operador abrir o PDF de 80 páginas e rolar até achar o trecho de que precisa, gastando minutos num caso que um atendente deveria resolver em segundos. Qual é a situação real em que esse operador precisa saber o que o contrato diz, e o que acontece hoje quando ele não consegue?

### zero-2 (US$ 0.203) · etapa A

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente:**

> Gravei o esqueleto em `docs/epics/contratos-demo.md` (status rascunho). Só o README existe no repo, então a pergunta é sua.
>
> Minha proposta é que a dor seja o operador ter uma dúvida concreta sobre um contrato (por exemplo, "esse plano cobre fisioterapia?") e hoje precisar rolar 80 páginas até achar a cláusula, porque o que ele quer é a resposta e não o documento. Me conta numa situação real recente: o que o operador estava tentando descobrir, e o que aconteceu quando ele foi atrás no PDF?

### zero-1 (B) (US$ 0.197) · etapa B

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente:**

> Gravei o esqueleto em `docs/epics/contratos-demo.md` (rascunho) com a sua frase como intenção. O repo só tem o README, então nada nele responde perguntas de produto.
>
> Minha proposta: o operador cola ou sobe um contrato e digita uma pergunta do dia a dia, como "esse plano cobre fisioterapia e com qual carência?", e recebe a resposta em poucas linhas, com a página do PDF de onde ela saiu. Isso daria a ele a resposta sem abrir o arquivo, e ainda poderia conferir na fonte. Hoje, quando alguém da operadora precisa saber o que um contrato diz, como essa pessoa descobre e o que faz esse caminho doer?

### zero-2 (B) (US$ 0.189) · etapa B

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente:**

> Gravei o esqueleto em `docs/epics/contratos-demo.md` (status `rascunho`). O repo só tem o README, então não havia nada para eu ler que respondesse perguntas.
>
> Minha proposta é registrar sua intenção como você a contou: o operador quer saber o que um contrato diz sem abrir o PDF de 80 páginas. O que ele faz hoje, na prática, quando precisa descobrir o que um contrato diz?

## Script da rodada 6

```bash
#!/bin/bash
# Grava só o turno 1, em dois cenários: Epic do zero e Epic retomado (semeado).
set -u
PLUG=/Users/alegomes/cepa-worktrees/cepa-until-2026-10-08-2047/common
OUT=/tmp/cs5-t1rounds-b; rm -rf $OUT; mkdir -p $OUT
for cen in zero; do for k in 1 2; do
  R=/tmp/cs5-t1-$cen-$k; rm -rf $R; mkdir -p $R/.claude $R/docs/epics; cd $R; git init -q
  printf 'modo: descoberta\n' > .claude/session-mode
  printf '# demo\nRepo de demonstração: lê contratos de operadora de saúde em PDF.\n' > README.md
  if [ $cen = semeado ]; then cp /tmp/cs5-transcript-seed/t0.arquivo.md docs/epics/contratos-demo.md; P="/common:epic contratos-demo";
  else P="/common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas."; fi
  git add -A; git commit -qm init
  timeout 400 claude -p --plugin-dir "$PLUG" --model sonnet --permission-mode acceptEdits --max-budget-usd 2 --output-format json "$P" > $OUT/$cen-$k.json 2>$OUT/$cen-$k.err
  echo "$cen-$k exit=$?"
  printf '%s' "$P" > $OUT/$cen-$k.dono.txt
  cd /; rm -rf $R
done; done
```


# Rodada 7: turno 1, cinco gravações por cenário, com o `epic.md` de e0c7d05

**Por quê:** a reauditoria de 65908ee pediu 5 de 5 gravações com uma pergunta só, por cenário, com o texto final do comando. Antes de medir, o comando ganhou uma linha: com a intenção no argumento, o turno 1 pergunta só o que se faz hoje (commit e0c7d05).
**Como:** o script ao fim, as dez gravações sobre o mesmo `epic.md`. Custo total: US$ 1.94.

| Cenário | Gravações com uma pergunta só |
|---|---|
| Epic do zero | 5 de 5 |
| Epic retomado (semeado) | 5 de 5 |

**Ressalva:** no Epic retomado, as gravações 2 e 4 perguntaram pelo ciclo 2 em vez da lacuna "Efeito em tela" do ciclo 1, fora da ordem que o passo 3 do comando manda. A pergunta é única e em prosa; a ordem é que escapou.

Abaixo, a última pergunta de cada gravação (o parágrafo com `?`); a fala inteira está no `result` de cada gravação, reproduzida em seguida.

### zero-1 (US$ 0.183)

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente:**

> Gravei a intenção que veio no argumento em `docs/epics/contratos-demo.md` (rascunho). O repo só tem um README, então nada do que li responde as perguntas de produto.
>
> Minha proposta é que hoje o operador receba a pergunta de um beneficiário ou de um prestador, procure o contrato da operadora no PDF e leia à mão até achar o trecho que responde. Quando isso acontece, o que ele faz hoje, passo a passo, para descobrir o que o contrato diz?

### zero-2 (US$ 0.203)

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente:**

> Gravei a intenção que veio no argumento em `docs/epics/contratos-demo.md` (status `rascunho`). O repo só tem um README de uma linha, então não há código nem doc que responda isto por mim.
>
> Minha proposta é que hoje o operador receba uma pergunta de um cliente ou de outro setor, procure o PDF numa pasta ou sistema e vá rolando até achar a cláusula, porque é o que costuma acontecer com contrato de 80 páginas. O que o operador faz hoje, passo a passo, quando precisa saber o que um contrato diz?

### zero-3 (US$ 0.205)

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente:**

> Gravei a intenção no rascunho `docs/epics/contratos-demo.md`. O repo só tem um README de uma linha ("lê contratos de operadora de saúde em PDF"), então não há código nem doc que responda por você.
>
> Minha proposta é que hoje o operador abra o PDF, use a busca por texto (Ctrl+F) com palavras que ele imagina que o contrato usa, e vá lendo trechos até achar a cláusula, porque é o que qualquer pessoa faz com um PDF de 80 páginas. O que o operador faz hoje, passo a passo, quando chega uma pergunta sobre um contrato?

### zero-4 (US$ 0.193)

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente:**

> Gravei a intenção e criei o rascunho em `docs/epics/contratos-demo.md`. O repo só tem o README, então não havia mais nada para ler antes de perguntar.
>
> Minha proposta é que hoje o operador receba uma dúvida (de um beneficiário ou de um colega), procure o PDF do contrato certo numa pasta ou sistema, abra as 80 páginas e use Ctrl+F até achar a cláusula. Esse é o caminho que o Epic precisa encurtar. O que o operador faz hoje, passo a passo, desde que surge a dúvida até ele ter a resposta?

### zero-5 (US$ 0.206)

**Dono:**

> /common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas.

**Agente:**

> Gravei a intenção em `docs/epics/contratos-demo.md` (rascunho). O repo só tem um README, então não havia nada para ler que respondesse isto.
>
> Minha proposta é que hoje o operador receba uma pergunta de um cliente ou de um colega, procure o PDF do contrato em alguma pasta ou sistema, abra o arquivo e role ou busque por palavra até achar a cláusula que responde. Quando o operador precisa saber o que um contrato diz, o que ele faz hoje, passo a passo, até chegar à resposta?

### semeado-1 (US$ 0.195)

**Dono:**

> /common:epic contratos-demo

**Agente:**

> Retomei o rascunho que já existia: a intenção, a primeira pergunta e um invariante estão gravados. As células "Efeito em tela" e "Efeito em backend" do ciclo 1 estão vazias, então começo pela de tela.
>
> Minha proposta é que o resultado apareça na própria tela de consulta, logo abaixo do campo onde o operador digitou "ressonância magnética". Ali ficam "Cobertura: sim ou não" e "Carência: N dias", e depois o trecho do contrato entre aspas com "página X do PDF". Assim ele não troca de tela para conferir a fonte. Onde, na tela, o operador deveria ver a resposta com o trecho e a página?

### semeado-2 (US$ 0.198)

**Dono:**

> /common:epic contratos-demo

**Agente:**

> Retomei o rascunho. A intenção, o que dói (até dois dias de espera pelo setor de contratos), o invariante e o roteiro do ciclo 1 já estão gravados. Faltam a escada além do ciclo 1 e as colunas de efeito em tela e em backend.
>
> Minha proposta é que o ciclo 2 seja "vários contratos": o operador digita "ressonância magnética" sem escolher contrato e vê a resposta de cada contrato carregado, cada uma com trecho e página. Escolhi essa porque o ciclo 1 já deixou "vários contratos" para depois e porque o operador no dia a dia raramente sabe de antemão em qual contrato olhar. Depois do ciclo 1, o que você quer ver funcionando no fim do ciclo seguinte?

### semeado-3 (US$ 0.192)

**Dono:**

> /common:epic contratos-demo

**Agente:**

> O arquivo `docs/epics/contratos-demo.md` já existe como rascunho. Retomo dele, sem refazer o que já está marcado. Ficaram vazias as colunas "Efeito em tela" e "Efeito em backend" do ciclo 1.
>
> Minha proposta: o operador vê o resultado na própria tela de consulta, logo abaixo do campo onde digitou "ressonância magnética". Ali aparecem o selo "Coberto, carência de N dias" e o trecho literal do contrato com "página X". Como o invariante exige o trecho, ele fica visível sem clique extra. Onde, na tela, o operador deveria ver que a resposta apareceu?

### semeado-4 (US$ 0.183)

**Dono:**

> /common:epic contratos-demo

**Agente:**

> Retomei `docs/epics/contratos-demo.md`. A intenção, um invariante e o roteiro do ciclo 1 já estão gravados, então não repito essas perguntas. Falta a escada inteira: só existe o ciclo 1, e as colunas de efeito em tela e em backend estão vazias.
>
> Minha proposta é uma escada de três ciclos, porque o ciclo 1 já deixa explícito que "vários contratos ficam para depois". O ciclo 1 seria um contrato, o ciclo 2 buscaria em todos os contratos da operadora e o ciclo 3 cuidaria do que fazer quando o contrato não responde com clareza. Depois do ciclo 1 funcionando, o que você quer que o operador consiga fazer a mais?

### semeado-5 (US$ 0.185)

**Dono:**

> /common:epic contratos-demo

**Agente:**

> Retomei o `docs/epics/contratos-demo.md`, que já existia: a intenção, um invariante e o roteiro do ciclo 1 estão gravados. A primeira lacuna é o "Efeito em tela" do ciclo 1.
>
> Minha proposta é que, depois de digitar "ressonância magnética", o operador veja na própria tela de consulta um cartão com "Cobertura: sim" e "Carência: N dias", o trecho literal da cláusula logo abaixo e a página do PDF ao lado. Eu ligaria a página a um link que abre o PDF naquela página, porque é assim que ele confere sem ligar para o contrato. Onde, na tela, o operador precisa ver que a resposta veio do contrato e não de um palpite?

## Script da rodada 7

```bash
#!/bin/bash
# Turno 1 do /common:epic, 5 gravações por cenário, com o epic.md do HEAD.
set -u
PLUG=/Users/alegomes/cepa-worktrees/cepa-until-2026-10-08-2047/common
OUT=/tmp/cs5-t1x5; rm -rf $OUT; mkdir -p $OUT
grava() { cen=$1; k=$2
  R=/tmp/cs5-t1x5-$cen-$k; rm -rf $R; mkdir -p $R/.claude $R/docs/epics; cd $R; git init -q
  printf 'modo: descoberta\n' > .claude/session-mode
  printf '# demo\nRepo de demonstração: lê contratos de operadora de saúde em PDF.\n' > README.md
  if [ $cen = semeado ]; then cp /tmp/cs5-transcript-seed/t0.arquivo.md docs/epics/contratos-demo.md; P="/common:epic contratos-demo";
  else P="/common:epic contratos-demo O operador da operadora quer saber o que um contrato diz sem abrir o PDF de 80 páginas."; fi
  git add -A; git commit -qm init
  timeout 400 claude -p --plugin-dir "$PLUG" --model sonnet --permission-mode acceptEdits --max-budget-usd 2 --output-format json "$P" > $OUT/$cen-$k.json 2>$OUT/$cen-$k.err
  echo "$cen-$k exit=$?"; printf '%s' "$P" > $OUT/$cen-$k.dono.txt; cd /; rm -rf $R; }
for k in 1 2 3 4 5; do grava zero $k & grava semeado $k & wait; done
```
