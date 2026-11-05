# Especificação: três portas para o spec e o Epic (caminho O2')

**Status:** draft
**Aberta em:** 2026-11-04            **Fechada em:** -

**Fontes lidas:** `docs/estrategia-tres-portas-para-spec-e-epic.md` (seção 4, O2', e seção 6, D1 a D7) · `docs/reviews/2026-11-04-painel-tres-portas.md` · `BACKLOG.md` (fb-20261104-1) · `common/hooks/spec-readiness-gate.py` · `common/bin/cepa-plan` · `tests/test_cepa_until_dead_supervisor.py`

## Problema
**Como chegamos aqui.** Em 2026-11-04 uma sessão de exploração perguntou: "há três lugares onde alguém já pensou sobre o que construir, por que nenhum deles chega até a entrevista do `/common:spec` e do `/common:epic`?" Os três lugares: o brief que o plugin `discovery` escreve ao validar uma oportunidade; a spec que o `planning-lead` do `build-hex` escreve sozinho; e a seção "Decidido sem perguntar" que toda entrevista anterior deixa com um "vete aqui" que ninguém lê de volta. A sessão escreveu `docs/estrategia-tres-portas-para-spec-e-epic.md`, passou por um painel de sete revisores e o dono aprovou o caminho chamado O2': o arquivo no disco vira o canal, sem Jira, com um leitor só em código. Esta especificação é o passo seguinte: dizer, item por item, o que muda e como se prova.

**O que dói hoje.** Quando já existe um brief ou uma spec, o dono responde na entrevista o que já está escrito. E as decisões que o agente tomou sozinho nunca recebem veredito: ficam gravadas como se o dono tivesse concordado.

**O que O2' faz, em uma frase por item.**
- 0. Tira da suíte o teste intermitente do supervisor morto do `cepa-until`, para a fila deste ciclo não nascer vermelha.
- 1. O passo "ler antes de perguntar" dos dois comandos passa a nomear os arquivos que lê, e toda proposta tirada de um arquivo diz de onde veio: `evidência` ou `proposta de agente`.
- 2. Proposta vem antes da pergunta no mesmo turno, e nada vira `- [x]` sem resposta do dono.
- 3. Um comando, `cepa-plan decisions <arquivo>`, lista as decisões de uma spec ou Epic e diz quais já têm veredito.
- 4. Ao reabrir uma spec ou Epic, o comando mostra as decisões sem veredito, uma por turno, e grava "mantida", "vetada" ou "refinada" na própria linha.
- 5. O `/common:doctor` conta quantas decisões sem veredito existem no repo.
- 6. Ao gravar `ready`, o comando imprime essa contagem.
- 7. O card que o `discovery` cria aponta para o caminho do brief, e a regra "Brief, not Epic" diz quem o lê.

## Escopo
### Entra
- Os oito itens de O2': 0 quarentena do teste vermelho na base; 1 entradas nomeadas e rótulos; 2 ritmo e regra do `- [x]`; 3 `cepa-plan decisions`; 4 veto nos comandos; 5 check no `doctor`; 6 contagem no fechamento; 7 `epic-briefer` e regra "Brief, not Epic".
### Não entra
- Arquivo de expertise para a entrevista (D5).
- Unificar `spec/`, `specs/` e `docs/spec/` (D7, sem gatilho).
- Mudar o `/common:debrief` (D1).
- Desfazer o que já virou código a partir de decisão vetada: o veto é registro.

## Estado e migração
<a preencher>

## Critérios de sucesso

<a preencher, um por item de O2'>

## Perguntas em aberto
- [ ] Item 0: quarentenar só, sem consertar a corrida do supervisor?
- [ ] Item 0: quarentena = módulo inteiro marcado `skip` com o motivo fb-20261104-1, em vez de `xfail` ou mover de pasta?
- [ ] Item 6: a contagem de decisões sem veredito sai do hook `spec-readiness-gate` ao liberar o `ready`, e o comando só a repete no relatório?
- [ ] Item 6: hook e `cepa-plan decisions` leem a seção pelo mesmo módulo, logo o item 6 fecha depois do 3?

## Decided without asking

## Riscos e o que ficou de fora desta especificação
- O ciclo tem oito itens; a estratégia estimou um ciclo só.
