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

Leia também o estado do run, `<run>.estado.json`, ao lado do `.jsonl` (mesmo
nome, outro sufixo). O `cepa-until` grava esse arquivo antes de chamar você:
`estado` (`esperando-dono` ou `encerrado`), `itens` (uma linha por item),
`acoes` (a lista fechada do que um comando executa; hoje só `aterrissar`) e
`fica_com_voce` (o que nenhum comando executa). Run anterior a 2026-09-28 não
tem o arquivo: diga isso e siga só com o resumo.

**Supervisor morto ou interrompido.** Dois estados dizem que o run não chegou
ao fim:

- `interrompido`: o supervisor recebeu SIGTERM ou Ctrl+C e gravou o evento
  `run_interrompido` no `.jsonl`, com o `sinal` e o item em voo (`id`, `fase`
  e o `pid_filho`, o `claude` ou o build que roda em sessão própria e pode ter
  seguido sozinho).
- `rodando` sem `run_end` no `.jsonl`: ou o run ainda roda, ou o supervisor
  morreu calado (o run WEGO 2026-09-28-2003 parou em `item_start`, o card
  fechou `done` sozinho e o build completo nunca rodou). Não chute: rode
  `python3 common/bin/cepa-until pendentes --json` e veja a lista `mortos`,
  que confere o `pid` e o `host` gravados no estado (run sem pid conta como
  morto 3h depois do prazo; run `interrompido` também entra na lista). Se o
  run estiver lá, a primeira pergunta do relatório é fechá-lo com o comando
  do campo `fechar` (`cepa-until fecha-morto <fila>/<run> --sim`): ele roda o
  build completo que faltou na worktree da noite e, verde, grava o `run_end`
  e deixa o run `esperando-dono` com a ação `aterrissar`. O item em voo com
  status `done` está na fila sem esse build. Se não estiver na lista, o run
  ainda roda: diga isso e pare.

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
8. **Sinais de processo.** Cada rodada traz a linha `sinais de processo`:
   worktree aberta (por Bash, `EnterWorktree` ou `Agent` com
   `isolation=worktree`) e relato de gate de build contornado com o verde de
   outro módulo, cada um com QUEM. A do `proof-reviewer` com `--detach` é a
   permitida, e vem anotada; qualquer outra fere a regra da noite. Um agente
   que não é filho direto (o `qa-engineer` chamado pelo `engineering-lead`)
   não tem as chamadas no `.log`: o sinal dele vem do relatório devolvido e do
   RESULT.md, e é por isso que o resumo varre esses textos. No run
   2026-09-27-1632 o `qa-engineer` abriu worktree em 2 de 4 itens e no
   WEGO-2329 apresentou o build verde de outro módulo para passar pelo hook
   de build vermelho, e nada disso aparecia no resumo.

Pergunta sem achado não entra no relatório.

### 3. Relatório

No formato `plain-report`, em pt-BR: abertura de até 3 frases sem jargão,
`**Pra você:**` com a contagem de decisões, `### Detalhe técnico` e, por
último, `### Decisões e próximos passos` como lista numerada de perguntas
fechadas, cada uma com `Recomendo sim/não` e o porquê em uma linha. Todo número
vem com a conta. Todo termo aparece explicado na primeira menção.

A ordem das perguntas é a ordem em que o dono deve responder: o que destrava
mais trabalho vem primeiro.

**Uma lista só** (C7 de `docs/estrategia-fim-do-cepa-until.md`). Comente cada
ação de `acoes` pelo id, sem numeração própria: a pergunta sobre ela leva o id
como rótulo (`aterrissar`), diz o efeito com a `frase` do estado e traz a sua
recomendação. Os itens de `fica_com_voce` aparecem num bloco "Fica com você",
com o que o dono precisa fazer em cada um. Não invente ação fora da lista: o
que você achar e nenhum comando executa (abrir card para um teste instável,
corrigir o harness) entra em "Fica com você".

### 4. Bloco de decisões para o terminal

Depois do relatório, e só no fim do arquivo, grave um bloco cercado
```` ```json cepa-decisoes ```` que o `cepa-until` lê para perguntar ao dono,
uma por vez, no terminal (o `cepa-until decidir`). O bloco NÃO decide o que é
executado: as ações vêm de uma lista fechada do `cepa-until` (aterrissar, e o
`cepa-plan responde`, que devolve um item `blocked` para a fila ou fecha a
rota humana com a resposta do dono, ou, com `--mantem`, só grava a resposta
e deixa o item travado). Ele só dá a redação da pergunta e a sua
recomendação.

Cubra **todos os itens adiados da fila**, não só os deste run: rode
`python3 common/bin/cepa-plan queue <fila> --max 1 --json --repo <raiz>` e
pegue a lista `deferred`. Entram os de motivo `bloqueado-antes` e
`human_pending`; `reservado` e `depende-de-adiado` não são do dono e ficam de
fora. Item que já tem `question` (a pergunta que o agente gravou com
`finish --pergunta`) não precisa de linha, a menos que você recomende outra
coisa.

```json cepa-decisoes
{"aterrissar": {"recomendo": "sim", "porque": "uma linha"},
 "itens": [
   {"id": "WEGO-2336",
    "pergunta": "Fecho o card como 'medir depois do go-live'? (a alternativa é virar item do checklist do primeiro deploy)",
    "recomendo": "não",
    "porque": "o checklist preserva a medição sem deixar o card travando a fila"}
 ]}
```

Regras do bloco:

- `pergunta` é fechada, respondível sem abrir o card, na voz de quem pergunta
  ao dono, e cita as opções quando houver mais de uma.
- `recomendo` é `sim` ou `não`; `porque` cabe numa linha.
- Rota `human_pending` que é tarefa (validar à mão, rodar um login real):
  pergunte se ela já foi feita e o que se viu, e diga o que o dono precisa
  ter à mão.
- JSON válido. Se não houver nada, grave `{"itens": []}`.

## Constraints

- Nunca execute uma providência, mesmo reversível. Este comando responde "o
  que fazer", e quem faz é o dono ou a sessão que ele abrir.
- Nunca afirme estado do git sem ter conferido nesta execução.
- O resultado precisa caber numa leitura de 5 minutos. Detalhe que não muda
  nenhuma decisão fica de fora.
