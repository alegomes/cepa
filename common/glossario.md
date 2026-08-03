# Glossário — vocabulário privado do Cepa

Este arquivo tem duas funções:

1. **Dar ao `report-style-lint.py` uma lista concreta** do que contar como
   jargão na abertura de um relatório. Só a primeira seção é lida pelo hook.
2. **Ser o lugar onde termo é aposentado.** Hoje o vocabulário só cresce: cada
   sessão inventa dois termos e nenhum morre. Termo que ninguém mais usa sai
   daqui; termo que virou senso comum entre o usuário e o harness desce para a
   segunda seção.

O ponto não é proibir os termos — eles são densos e úteis *no lugar certo*. O
ponto é que a **abertura** de um relatório é o lugar errado: ela existe para
quem não abriu o código, e um termo metafórico ali obriga a reler.

## Traduzir sempre

Estes são metáforas internas, não vocabulário de software. Fora do bloco de
detalhe técnico, use a tradução.

- **portão** — a verificação automática que impede uma ação (o "gate")
- **falha aberto / falha fechado** — em caso de dúvida, a verificação deixa
  passar / bloqueia
- **fresta** — buraco na verificação por onde algo errado passou
- **dublê** — objeto falso que substitui o de verdade num teste
- **perturbar / perturbação** — quebrar o código de propósito para ver se o
  teste acusa
- **ir ao vermelho / verde** — o teste falhar (como devia) / passar
- **load-bearing** — o teste realmente sustenta a garantia; se quebrar o
  código, ele acusa
- **altitude** — o nível em que a coisa é observada (dentro da classe, na API,
  na tela)
- **escada de confiança / L0..L4** — o quanto se pode confiar que um card está
  pronto
- **fio condutor** — o caminho de ponta a ponta que atravessa o harness inteiro
- **carimbo** — aprovação dada sem verificação real
- **porteiro** — o processo que autoriza cada passo de uma onda do Maestro
- **onda / slice / fork point** — lote de trabalho paralelo do Maestro e seus
  pontos de divisão
- **merge train** — a fila em que os ramos de uma onda são integrados
- **drenar / drain** — processar em lote toda uma coluna do board
- **shadow-mode** — rodando sem poder bloquear nada, só observando
- **nulo explícito** — obrigar a declarar "não se aplica" em vez de omitir
- **enum fechado** — lista fixa de valores aceitos; qualquer outro é recusado
- **altitude leiga** — explicado para quem não conhece o assunto

## Abstrações a evitar

Diferente da seção acima: aqui não são termos do projeto, são **categorias
inventadas na hora** que ocupam o lugar do fato. "O escopo virou um sinal
mecânico" não diz nada; "o hook olha se usei Edit ou Write" diz tudo, e é a
mesma frase em número de palavras.

Regra: **nomeie a coisa, não a categoria da coisa.** Se a frase sobrevive à
pergunta "que sinal? que caminho? medido como?", ela está pronta.

Isto vale no texto **inteiro**, inclusive no detalhe técnico — foi exatamente
ali que o usuário achou os três exemplos abaixo, em 03/08/2026.

- **sinal mecânico** — diga qual é o sinal: "o hook olha se o turno usou Edit"
- **caminho indireto** — diga qual é o caminho: "grava num arquivo e lê no
  turno seguinte"
- **é medido / são medidas** — diga o que a coisa faz: "conta as frases e
  procura os termos do glossário"
- **camada adicional** — diga o que a camada faz e onde ela fica
- **de forma estrutural** — diga qual estrutura
- **a nível de** — diga onde
- **em termos de** — diga o quê
- **aspecto importante / ponto central** — diga qual, direto
- **abordagem / estratégia** (sem dizer qual) — descreva o que se faz
- **superfície** (fora de "superfície de API") — diga qual código
- **peça / elemento / componente** (quando dá para nomear o arquivo)
- **contexto** (quando dá para dizer qual situação)
- **natureza de / do tipo** — corte a frase e diga a coisa

## Aceitos sem tradução

Vocabulário corrente entre o usuário e o harness. Não são sinalizados.

- worktree, branch, commit, merge, push, rebase
- handoff, baseline, hook, plugin, skill, card, board, topologia
- build, teste, cobertura, regressão
