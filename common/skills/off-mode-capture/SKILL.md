---
name: off-mode-capture
description: Use quando a sessão tem um modo de trabalho ativo (o hook session-mode injetou "[modo] Esta sessão opera em X") e a próxima ação que você ia executar não pertence a esse modo. Registre o desvio sozinho e siga com o trabalho do modo — não pergunte, não execute o desvio. As capturas vão para o relatório final. Não dispare sem modo ativo: aí vale o comportamento normal (board-flow:suggest-capture, se instalado).
---

# Captura de desvio

## O problema

O sintoma que originou os modos: *"eu começo a especificar uma funcionalidade,
pulo pro desenvolvimento, mergulho em micro-ajustes e gasto energia na
documentação antes de terminar"*.

A causa não é falta de disciplina — é falta de **destino para o desvio**. Quando
o desvio aparece e só existem duas saídas (fazer agora, ou perder), fazer agora
sempre ganha, porque perder dói. Esta skill é a terceira saída.

## O teste, em uma pergunta

> Esta ação é necessária para a **condição de saída do modo ativo**?

- **Sim** → é trabalho do modo. Execute, por mais que pareça outra coisa.
- **Não** → é desvio. Registre e siga.

O teste é a condição de saída, não a aparência da ação. Escrever um teste durante
a Construção parece trabalho de QA e é trabalho do modo. Corrigir um bug que
impede o `proof-reviewer` de rodar parece Reforma e é trabalho do modo. Já
renomear uma variável feia no arquivo ao lado não é trabalho do modo nenhum — é
desvio, mesmo levando dez segundos. **O barato é justamente o que vaza.**

## O que é desvio, por modo

| Modo ativo | Desvio típico |
|---|---|
| exploração | começar a especificar critério de aceite, abrir código para "só conferir" |
| descoberta | implementar, refatorar, escrever documentação |
| design | implementar o design; mexer no design system além do que a feature usa |
| construção | micro-ajuste fora do critério, refatoração oportunista, documentação |
| reforma | qualquer coisa fora do orçamento declarado; mudar comportamento observável |
| reflexão | **corrigir** o que você achou (o achado vira card, não patch) |
| documentação | corrigir o código que a documentação revelou torto |

## O que NÃO é desvio

- Pergunta de esclarecimento, leitura de código, busca — nada disso muda o repo.
- O que o usuário pedir **explicitamente neste turno**: ele é o dono da fronteira
  e pode atravessá-la. Registre que atravessou, e siga.
- Bloqueio real: se sem aquilo a condição de saída do modo é inalcançável, é
  trabalho do modo. Diga em uma linha por que era bloqueio, no relatório.

## O que fazer

**Registre e siga. Não pergunte.** Perguntar devolve ao usuário a micro-interação
que o modo existe para eliminar (`default-yes`).

Destino, nesta ordem:

1. **Com `board-flow.yaml` no repo** → card via `/board-flow:capture`, com o modo
   ativo e a sessão na descrição.
2. **Sem board-flow** → uma linha em `.claude/desvios.md` (crie se não existir):

```markdown
- [ ] 2026-08-18 · modo: construcao · o resolver de contatos duplica a query N vezes; vi ao passar por ContactResolver.java:88
```

Cada linha diz **o quê**, **onde vi** e **em que modo eu estava**. Sem análise,
sem proposta de correção — analisar já é fazer o desvio.

## No relatório final

Bloco próprio, contando quantos foram:

```
**Desviei e registrei (3):** duplicação de query no ContactResolver ·
migration sem rollback · README apontando para endpoint que mudou de nome
```

Se nenhum desvio apareceu, não escreva o bloco. Ausência não precisa de linha.

## Limite

Esta skill registra; ela não prioriza nem decide. Card capturado entra na fila
como qualquer outro e passa pela triagem normal. Você não está enfileirando
trabalho aprovado — está evitando que o desvio vire trabalho **agora**.
