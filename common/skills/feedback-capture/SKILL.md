---
name: feedback-capture
description: Use quando o usuário reclamar do harness — do comando que perguntou demais, do gate que barrou o que não devia, do relatório ilegível, do agente que fez o que não foi pedido — ou quando pedir explicitamente para registrar um feedback sobre a Cepa. Grave a queixa verbatim pelo `cepa-feedback add` e siga com o trabalho do turno; não pergunte se deve registrar, não discuta se a queixa procede, não conserte o harness agora. Não dispare para reclamação sobre o CÓDIGO do projeto (isso é card, não feedback do harness).
---

# Captura de feedback do harness

## O problema

O incômodo com a Cepa nunca aparece sozinho. Ele aparece no meio de outra
tarefa, no repo do cliente, com o contexto inteiro carregado — e nesse instante
existem duas saídas: largar a tarefa para abrir o `BACKLOG.md` da Cepa (que quase
nunca é o repo aberto), ou seguir e esquecer. Seguir e esquecer sempre ganha,
porque parar dói. Esta skill é a terceira saída, e é a mesma forma do
[off-mode-capture](../off-mode-capture/SKILL.md): registrar custa uma linha,
então o desvio não precisa virar trabalho agora.

O que se perde sem ela tem nome: a queixa existe como texto do dono, escrita no
calor do episódio, com o comando que a causou ainda na tela. Um mês depois sobra
"o harness pergunta demais" — verdadeiro, e não acionável.

## Quando disparar

Dispare quando o alvo da reclamação é **a Cepa**: um comando, um hook, um gate,
um agente, um relatório, um prompt, o fluxo de uma rotina.

Não dispare quando o alvo é o **projeto**: bug no código, API de terceiro,
build quebrado, decisão de produto. Isso é card — `/board-flow:capture`, ou uma
linha em `.claude/desvios.md` se não houver quadro.

O teste, em uma pergunta:

> Reinstalar a Cepa em outra máquina levaria o incômodo junto?

Sim → feedback do harness. Não → card do projeto.

## O que fazer

Uma chamada, e siga com o trabalho do turno:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/bin/cepa-feedback" add \
  "<o texto do dono, verbatim>" --alvo <comando|hook|agente> --origem skill
```

(Fora de uma sessão com plugin carregado, o caminho é `common/bin/cepa-feedback`
no repo da Cepa.)

Três regras sobre o texto:

1. **Verbatim.** Grave o que o dono escreveu, não o seu resumo dele. O resumo
   troca a queixa pela sua leitura da queixa, e é a leitura que costuma estar
   errada — se você tivesse entendido, o incômodo não teria acontecido.
2. **`--alvo` sempre que der.** `modo-escrita-gate`, `board-flow:drain`,
   `proof-reviewer`. É o que transforma "o harness atrapalha" em algo que alguém
   consegue abrir. Sem alvo identificável, grave assim mesmo — feedback sem alvo
   ainda é sinal; feedback não gravado não é nada.
3. **Sem análise, sem proposta de correção.** Analisar já é fazer o desvio. O
   registro guarda o episódio; a triagem decide o que fazer, depois.

Repo, branch e modo da sessão entram sozinhos no registro — você não os digita.

## O que NÃO fazer

- **Não pergunte se deve registrar.** A pergunta devolve ao dono a micro-interação
  que a `default-yes` existe para matar. Registre e diga em uma linha que registrou.
- **Não conserte o harness agora.** Mesmo parecendo trivial: o conserto é trabalho
  de outra sessão, num repo que provavelmente não é este, e o turno em curso tem
  dono. Se o dono pedir o conserto explicitamente, aí é ordem — atenda e registre
  que atravessou.
- **Não discuta a queixa.** "Na verdade o gate estava certo" pode ser verdade e
  não é a hora. O registro guarda o que ele sentiu; a triagem confere os fatos.
- **Não grave duas vezes o mesmo episódio.** Uma queixa repetida no mesmo turno é
  um registro só.

## Como aparece na resposta

Uma linha, no fim do que você já ia responder:

```
**Feedback registrado (fb-20260826-2):** o gate de escrita barrou um commit legítimo · alvo: modo-escrita-gate
```

Nada além disso. O turno pertence à tarefa que o dono pediu.

## Depois

`/common:feedback` lista o que está aberto e — no repo da Cepa — vira item de
`BACKLOG.md` com o episódio e o contexto junto. Registrar não é aprovar
trabalho: o item entra na fila e passa pela triagem como qualquer outro.
