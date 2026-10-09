# Transcrição de teste: `/common:epic` (CS-5)

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
