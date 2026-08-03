---
name: plain-report
description: O formato obrigatório do relatório de trabalho feito — abertura leiga de até 3 frases, o que é do usuário, e só então o detalhe técnico. Use ao fechar uma tarefa, entregar um veredito ou reportar um diagnóstico. Não se aplica a conversa, pergunta curta ou ida-e-volta de design.
---

# Skill: plain-report

O usuário disse, em 03/08/2026: *"o seu estilo de redação é confuso, o uso
excessivo de jargões internos cria muito atrito na leitura, geralmente eu tenho
que ler mais de uma vez pra conseguir entender algo"*.

A regra já existia no CLAUDE.md global dele — "2 frases leigas, recomendação
default, detalhe técnico por último" — e vinha sendo aplicada só a *findings*
técnicos isolados, nunca ao relatório inteiro. Esta skill fecha essa brecha de
leitura e vale para **todo relatório de trabalho feito**.

## Quando se aplica

Quando você fecha uma tarefa, entrega um veredito, reporta um diagnóstico —
qualquer resposta que conte o que foi feito. Reconhecível por um sinal
mecânico: **o turno alterou alguma coisa** (escrita, edição, commit).

Não se aplica a conversa, resposta de uma linha, pergunta de esclarecimento ou
discussão de design em andamento. Formatar um "sim, existe" em três blocos
seria pior que o problema.

## O formato

```
<Abertura: até 3 frases, zero jargão. O resultado, não o mecanismo.>

**Pra você:** <a decisão pendente ou a ação manual — ou "nada">

### Detalhe técnico
<livre: arquivos, nomes, evidência, mecanismo>
```

Regras duras:

- **Abertura: no máximo 3 frases, e nenhum termo da seção "Traduzir sempre" do
  `common/glossario.md`.** Se você não consegue escrever a abertura sem um
  desses termos, você não entendeu o que fez — o termo está fazendo o trabalho
  que o entendimento deveria fazer.
- **`Pra você:` sempre presente**, mesmo quando a resposta é "nada pra
  decidir". O usuário precisa saber que pode parar de ler ali.
- **Teto de 200 palavras** somando abertura e `Pra você:`. O detalhe técnico é
  livre — quem não quer, para no cabeçalho.
- **Ordem: resultado antes de mecanismo.** Nunca abra por como funciona.

## A regra que vale no texto inteiro

O bloco de detalhe técnico tem liberdade de **tamanho**, não de clareza. A
primeira versão desta skill o tratava como zona franca, e o usuário achou lá
dentro, no mesmo dia: *"virou um sinal mecânico"*, *"nunca são medidas"*,
*"chega por um caminho indireto"*. Nenhuma delas é jargão do projeto — são
categorias inventadas na hora que ocupam o lugar do fato.

**Nomeie a coisa, não a categoria da coisa.** Toda frase precisa sobreviver à
pergunta *"que sinal? que caminho? medido como?"*:

| Categoria | A coisa |
|---|---|
| "virou um sinal mecânico" | "o hook olha se o turno usou Edit ou Write" |
| "nunca são medidas" | "o hook não conta as frases nem procura os termos" |
| "chega por um caminho indireto" | "grava num arquivo e lê no turno seguinte" |

Dois corolários:

- **Quem age vem antes do que aconteceu.** "são medidas" esconde quem mede.
  Diga o sujeito: *o hook conta*, *o guard bloqueia*, *o teste falha*.
- **Se dá para nomear o arquivo, a classe ou o comando, nomeie.** "a peça
  responsável" custa as mesmas palavras que `report-style-lint.py`.

A lista de abstrações vive na seção "Abstrações a evitar" do
`common/glossario.md` e cresce com evidência: toda vez que o usuário apontar
uma frase obscura, ela entra lá.

## O erro característico

Abertura real, de um relatório de 03/08/2026:

> "O portão agora falha fechado. Cada `status:` é conferido contra o enum
> fechado do seu nível, não contra uma lista de proibidos."

Quatro termos internos em duas frases, e o leitor ainda não sabe o que ganhou.
A mesma coisa dentro do formato:

> "O verificador de provas aceitava qualquer palavra que não estivesse numa
> lista de proibidas — um erro de digitação virava aprovação. Agora ele só
> aceita as palavras previstas.
>
> **Pra você:** nada pra decidir; precisa reinstalar pra valer."

## Relação com as outras skills

`conversational-response` continua valendo para a resposta que sobe a cadeia de
delegação (worker → lead). Esta aqui é mais estrita e vale na ponta, onde o
leitor é o usuário. Onde as duas se aplicam, esta ganha.

O `report-style-lint.py` mede o resultado ao fim do turno e devolve o desvio no
turno seguinte. Ele **avisa, não bloqueia** — a decisão de apertar depende do
que a telemetria mostrar (`/common:metrics`).
