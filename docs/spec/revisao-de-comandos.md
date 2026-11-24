# Especificação: comando que refaz a revisão dos comandos do cepa

**Status:** ready-to-build
**Aberta em:** 2026-11-24            **Fechada em:** 2026-11-24
**Fontes lidas:** docs/spec/reforma-de-nomes-dos-comandos.md, tests/test_commands_catalog.py (cabeçalho), common/bin/cepa (show_help), frontmatter dos 71 arquivos `*/commands/*.md`

## Como chegamos aqui
"transforme essa revisão em um comando para estarmos sempre refazendo-a" (dono, 2026-11-24), depois de aprovar as oito propostas da revisão de nomes dos comandos de barra e da CLI feita na sessão de 2026-11-23.

## Problema
A revisão de 2026-11-23 foi feita à mão: o agente releu 71 comandos de barra e a ajuda de 15 subcomandos para achar palavra com dois sentidos, flag em português, apelido antigo e comando fora da documentação. Sem um comando, a próxima revisão depende de alguém lembrar de pedir, custa a leitura inteira de novo e pode repetir proposta que o dono já recusou.

## Escopo
### Entra
- Um subcomando da CLI, `cepa commands`, que lista todo comando de barra, subcomando, flag e variável de ambiente e aponta o que é contável (R1).
- Um comando de barra, `/cepa:command-review`, que lê essa lista, acrescenta o que exige julgamento e entrega propostas com pergunta fechada e recomendação (R1, R3).
- Um arquivo por revisão em docs/reviews/, com as propostas e a resposta do dono a cada uma; a revisão seguinte lê a anterior e não repete o que foi recusado (R2).

### Não entra
- Aplicar as propostas: o comando termina oferecendo `/cepa:spec` para as aprovadas, como nesta sessão.
- Revisar agentes, skills e hooks: só comandos de barra, CLI, flags e variáveis.

## Estado e migração
Nada. O comando cria arquivos novos em docs/reviews/ e não altera nenhum existente.

## Critérios de sucesso

### CS-1: `cepa commands` lista todo comando de barra, subcomando, flag e variável de ambiente
**Surface:** cli
**Red test:** no repo do cepa, `cepa commands --json` devolve um comando de barra por arquivo `*/commands/*.md`, um subcomando por script `cepa/bin/cepa-*` com seus sub-subcomandos e flags, e cada variável de ambiente lida em `cepa/bin/` e `cepa/hooks/`; a contagem de comandos de barra é igual à de arquivos. Hoje `cepa commands` não existe.

### CS-2: `cepa commands check` aponta os achados contáveis e sai com 1 quando há algum
**Surface:** cli
**Red test:** num repo de teste com um arquivo de comando marcado "Deprecated alias", um script que lê `FOO_X` (sem prefixo `CEPA_`), um `argument-hint` com `--fila` (palavra da lista em português) e um comando ausente de docs/commands.md, `cepa commands check` imprime 4 achados, cada um com o tipo e o arquivo, e sai com 1; sem esses quatro, imprime zero achados e sai com 0.

### CS-3: um achado contável no repo do cepa faz a suíte de testes falhar
**Surface:** cli
**Red test:** `tests/test_command_names.py` roda `cepa commands check` no repo real e falha se houver achado; acrescentar a flag `--fila` ao `argument-hint` de um comando faz esse teste falhar com o nome do arquivo na mensagem.

### CS-4: `/cepa:command-review` grava a revisão e não repete o que o dono recusou
**Surface:** cli
**Red test:** `cepa commands --json`, num repo de teste com `docs/reviews/command-review-2026-11-23.md` contendo uma proposta com resposta "não", devolve essa proposta em `refused`; `cepa promptcov cepa/commands/command-review.md tests/test_command_review.py` sai com 0 cobrindo os pontos `review:inventory` (roda `cepa commands --json`), `review:memory` (não propõe o que está em `refused`), `review:record` (grava `docs/reviews/command-review-<data>.md` com cada proposta, a pergunta fechada, a recomendação e a resposta) e `review:no-apply` (termina oferecendo `/cepa:spec`, não altera comando). Hoje o arquivo do comando não existe.

### CS-5: a abertura da sessão avisa quando a última revisão tem mais de 30 dias
**Surface:** cli
**Red test:** o hook de abertura de sessão, rodado no repo do cepa com a revisão mais recente de docs/reviews/ datada de 31 dias atrás, imprime uma linha de manutenção que sugere `/cepa:command-review`; com uma de 29 dias, não imprime; fora do repo do cepa, não imprime.

## Perguntas em aberto
- [x] R1: como o comando levanta os dados? — inventário da CLI mais agente (dono, 2026-11-24)
- [x] R2: o resultado de cada revisão fica gravado? — sim, em docs/reviews/, e a revisão seguinte não repete o que foi recusado (dono, 2026-11-24)
- [x] R3: que nome dou ao comando? — `/cepa:command-review`, com o inventário em `cepa commands` (dono, 2026-11-24)
- [x] R4: o que lembra o dono de refazer a revisão? — o tempo: aviso na abertura da sessão quando a última revisão tem mais de 30 dias (dono, 2026-11-24)
- [x] R5: os achados contáveis do inventário também barram a suíte de testes? — sim, falham a suíte (dono, 2026-11-24)

## Decided without asking
- Os nomes desta especificação já seguem a reforma de nomes (Q7 e Q10 de docs/spec/reforma-de-nomes-dos-comandos.md): o dono respondeu `/common:command-review` na R3 antes de trocar o prefixo `common` por `cepa`, então o comando é `/cepa:command-review` e mora em `cepa/commands/`. Vete aqui se discordar.
- O comando roda só dentro do repo do cepa, como o `--triage` do `/cepa:feedback`: o alvo é o harness. Vete aqui se discordar.
- O comando não entra no menu de nenhum modo de trabalho por enquanto. Vete aqui se discordar.
- O prazo do aviso é 30 dias, o mesmo tipo de aviso que a telemetria usa; sem nenhuma revisão gravada, o aviso aparece. Vete aqui se discordar.
- A revisão de 2026-11-23 é gravada como `docs/reviews/command-review-2026-11-23.md` a partir de docs/spec/reforma-de-nomes-dos-comandos.md, para a primeira execução já ter memória. Vete aqui se discordar.
- A lista de palavras em português fica em `cepa/naming.yaml`, junto da tabela de nomes antigos. Vete aqui se discordar.

## Riscos e o que ficou de fora desta especificação
- "Palavra em português" só é contável com uma lista de palavras: a lista começa com a tabela de nomes antigos da reforma e cresce a cada revisão.
- Ordem: o CS-3 só fica verde depois que a reforma de nomes for construída, porque hoje o repo tem apelidos antigos e flags em português. A reforma entra na fila antes.
