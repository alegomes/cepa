---
description: Lê um run encerrado do `cepa-until` (o registro `.jsonl` e a saída dos subprocessos `.log`) e diz o que o dono precisa fazer a partir dele, em perguntas fechadas com recomendação. Roda sozinho no fim de cada run (o `cepa-until` grava o resultado em `<run>.review.md`) e à mão para um run antigo ou para um que parou pela cota. Não lê o `.log` inteiro, que passa de 10 MB: lê o resumo mecânico do `cepa-until-digest` e confere no git o que for afirmar. Só lê: não mescla, não mexe na fila, não fala com o Jira.
argument-hint: [<run>.jsonl | latest] [--fila NOME]
interaction: routine
---

# /common:until-review

## Purpose

O resumo que o `cepa-until` imprime no fim só conta: tantos entregues, tantos
travados, tantas esperas de cota. O que o dono precisa decidir está em outro
lugar, no relatório final de cada subprocesso e na `evidence` de cada item da
fila: o card que travou pelo mesmo motivo que outros 19, o build que rodou
antes do último refactor, a migration que precisa entrar antes das outras.
Em 2026-09-24 essa leitura foi feita à mão, numa sessão aberta depois do run,
e achou tudo isso. Este comando faz essa leitura de propósito, no fim de todo
run.

## Variables

- `<run>.jsonl` — o registro do run. `latest` (default) é o `.jsonl` mais
  recente em `<raiz-principal>/.claude/programs/<fila>/until/`.
- `--fila NOME` — de qual fila, quando o repo tem mais de uma e o argumento é
  `latest`.

## Instructions

**Só leitura.** Nada de `git merge`, `cepa-plan finish`, transição de card,
build, push ou edição de arquivo. Cada providência vira uma pergunta para o
dono. Quem roda você no fim do run é um `claude -p` sem ninguém olhando, e uma
providência irreversível executada às 4h da manhã é pior do que uma pergunta
esperando às 8h.

**Leia o resumo, não o `.log`.** O `.log` do run de 2026-09-23 tinha 10,6 MB,
cerca de 2,6 milhões de tokens (10.617.662 bytes ÷ ~4 bytes por token). Uma
leitura por grep cobre o que o grep achou, e o que ficou de fora some calado. O
`cepa-until-digest` escolhe o que ler de forma mecânica e diz o que escolheu.
Abra um trecho do `.log` só para conferir algo que o resumo aponta, e diga que
abriu.

**Confira antes de afirmar.** O resumo e a `evidence` descrevem o momento do
run. Antes de dizer "a branch X não foi mesclada" ou "a worktree Y ainda
existe", rode o comando barato que confirma (`git branch --merged`, `git
worktree list`, `git rev-list --count A..B`) e diga o resultado.

## Workflow

### 1. Resolver o run e gerar o resumo

```
python3 common/bin/cepa-until-digest <run>.jsonl
```

Se o `.jsonl` não existir, pare dizendo qual caminho você procurou.

### 2. Ler procurando estas perguntas

1. **O que ficou pronto e onde está.** Itens `done`, commits na branch da
   noite (`until/<run>`) ou, em run anterior a 2026-09-24, em branches
   `session/*` soltas. Estão mesclados? (confira no git)
2. **Por que o resto não andou.** Agrupe os travados por causa. Várias rodadas
   travadas pela MESMA causa é o achado principal do run: diga quantas, quanto
   custaram (tempo e US$, com a conta) e o que destrava todas de uma vez.
3. **Build.** O build completo do supervisor ficou verde depois de cada item
   `done`? Algum relatório diz que o build rodou antes da última mudança, em
   partes, ou não rodou?
4. **Gates.** Pela contagem de agentes de cada rodada entregue: rodaram
   completion-auditor e proof-reviewer? E o validation-lead e o
   security-reviewer, quando a topologia tem?
5. **Ordem do merge.** Migrations com número de versão, arquivos alterados por
   mais de um item, enum que dois itens estendem. O que precisa entrar antes do
   quê?
6. **A fila mente?** Item `blocked` cujo código já está na main, item `done`
   cuja branch não mesclou, `blocked_by` vazio onde a `evidence` diz que há
   dependência.
7. **O próprio laço.** Esperas de cota, quedas de rede, `done_sem_commit`,
   sobras guardadas em stash, disjuntor. Algo aqui é defeito do `cepa-until` e
   não do item? Se for, diga que é do harness.

Pergunta sem achado não entra no relatório.

### 3. Relatório

No formato `plain-report`, em pt-BR: abertura de até 3 frases sem jargão,
`**Pra você:**` com a contagem de decisões, `### Detalhe técnico` e, por
último, `### Decisões e próximos passos` como lista numerada de perguntas
fechadas, cada uma com `Recomendo sim/não` e o porquê em uma linha. Todo número
vem com a conta. Todo termo aparece explicado na primeira menção.

A ordem das perguntas é a ordem em que o dono deve responder: o que destrava
mais trabalho vem primeiro.

## Constraints

- Nunca execute uma providência, mesmo reversível. Este comando responde "o
  que fazer", e quem faz é o dono ou a sessão que ele abrir.
- Nunca afirme estado do git sem ter conferido nesta execução.
- O resultado precisa caber numa leitura de 5 minutos. Detalhe que não muda
  nenhuma decisão fica de fora.
