# Tarefas douradas — a suíte que mede o harness

> Estado: **existe um número de referência (2026-09-27): 2/3, US$ 4,69 por
> volta da suíte, ~5 min por tarefa**, com o harness em `24e3e2d`. Ainda não
> houve A/B: o número serve de "antes" para a próxima mudança que alguém
> queira medir. Histórico das duas corridas anteriores em "A primeira
> corrida" e "A corrida de referência", abaixo.

## Por que existe

O harness audita cards, builds e provas, e não sabe nada sobre si mesmo em
termos de resultado. `common/hooks/_telemetry.py` diz isso na primeira linha:
*"Every improvement was anecdotal."*

O que já existia responde outras perguntas:

| Mecanismo | Responde | Não responde |
|---|---|---|
| testes de contrato de prompt | "a frase continua escrita no comando?" | se o agente termina a tarefa |
| telemetria (`cepa-metrics`) | "quantas vezes um gate bloqueou?" | se bloquear ajudou |
| Gauntlet | "qual dos 3 designs é melhor?" | se o design construído funcionou |

Nenhum responde: *esta mudança no prompt / na orquestração / no roteamento de
modelo fez os agentes terminarem mais tarefas, com menos voltas e menos tokens?*

## O desenho, e a decisão que o torna honesto

Cada tarefa é um conserto **que já aconteceu neste repo**. O executor:

1. cria uma worktree limpa no commit **anterior** ao conserto (`base_commit`);
2. entrega ao agente o enunciado do problema — como ele era, **sem a solução**;
3. quando o agente termina, traz o teste do commit do conserto para a worktree
   (`git checkout <fix_commit> -- <test>`) e o roda.

O passo 3 é o que impede a tarefa de se auto-aprovar. Se a aceitação fosse um
teste que o próprio agente escreve, a suíte mediria a capacidade dele de
escrever um teste que passa — que é sempre 100%.

E há uma segunda trava, `--validate`: rodar a aceitação na worktree **sem o
agente** e exigir **vermelho**. Uma tarefa que já passa no `base_commit` não
mede nada; ficaria verde para sempre e daria a sensação de cobertura. É o mesmo
`regression-red-at-base` que o proof-gate exige dos cards de bug, aplicado à
suíte que julga o harness.

## A primeira corrida: 0/3, e o que ela ensinou

`baseline-0.28.0`, 18/08/2026, harness em `dea48e2`:

| tarefa | dificuldade | resultado | voltas | custo | bloqueios de gate |
|---|---|---|---|---|---|
| acceptance-gate-direcao | alta | falhou | 30 | US$ 3,03 | 0 |
| bounce-reason | baixa | falhou | 37 | US$ 3,07 | 1 |
| reactor-guard | média | falhou | 25 | US$ 2,73 | 1 |

A leitura preguiçosa seria "os agentes não dão conta". A leitura certa é outra:
**os três testes de aceitação exigem o caminho e o nome exatos do arquivo do
conserto original** — `common/hooks/maven-reactor-guard.py`,
`common/hooks/bounce-reason-gate.py` — e, no caso difícil, exigem até que o
agente invente a mesma chave de configuração (`transition_ids`), inclusive
citada literalmente numa mensagem de erro. Os enunciados, de propósito, não
diziam nada disso.

Ou seja: a suíte estava medindo a capacidade de **adivinhar o desenho
original**, não a de resolver o problema. Nenhum agente passaria, e um agente
que resolvesse tudo com o arquivo chamado `mvn-reactor-guard.py` falharia
igual. O 0/3 não fala sobre o harness; fala sobre esta pasta.

O desenvolvedor original não adivinhou nada disso — ele tinha as convenções da
casa na cabeça. **O campo `contrato:`** devolve essa informação ao agente:
onde a verificação vai procurar, com que nomes, e qual é o contrato de
chamada. O que continua inteiro com ele é o trabalho: a lógica, os casos de
borda, o que fazer quando não dá para decidir.

Duas mudanças saíram daí:

1. **`contrato:` virou campo obrigatório** do manifesto, anexado ao enunciado
   pelo executor sob o título "COMO O SEU TRABALHO SERÁ CONFERIDO".
   `tests/test_eval_suite.py` guarda os dois lados: o `prompt` segue proibido
   de nomear os arquivos do conserto, o `contrato` é obrigado a nomeá-los.
2. **A worktree de uma tarefa que falha não é mais apagada.** O diagnóstico
   acima só foi possível porque a causa estava nos testes, que continuam no
   repositório; se estivesse no trabalho do agente, não haveria como saber —
   a evidência já tinha ido embora. Agora o executor guarda a worktree e
   registra no resultado o que o agente mexeu.

## A corrida de referência: 1/3, depois 2/3 (2026-09-27)

Harness em `24e3e2d`. A primeira passada deu 1/3 e, de novo, parte das falhas
era da suíte e não do agente: dois casos de teste cobravam uma convenção que o
`contrato:` não contava.

- `reactor-guard` cobrava o nome exato da saída de emergência, `# stale-ok`. O
  enunciado só dizia que "precisa existir uma saída";
- `bounce-reason` cobrava que um `Reason:` sem negrito nem cabeçalho fosse
  barrado com o texto literal `NOT in a recognized format` no stderr.

Os dois viraram frase no `contrato:` (mesma regra da primeira corrida: o
trabalho fica com o agente, a convenção de nome vai para o contrato) e só essas
duas tarefas foram re-rodadas:

| tarefa | dificuldade | 1ª passada | com o contrato corrigido | voltas | custo |
|---|---|---|---|---|---|
| acceptance-gate-direcao | alta | passou | (não re-rodada) | 27 | US$ 1,78 |
| bounce-reason | baixa | falhou (3 casos) | passou | 24 | US$ 1,46 |
| reactor-guard | média | falhou (3 casos) | falhou (2 casos) | 21 | US$ 1,45 |

Custo da suíte na referência: 1,78 + 1,46 + 1,45 = **US$ 4,69**, cerca de
16 min em série (323 s + 298 s + 301 s = 922 s). O que a medição toda gastou,
contando a primeira passada, foi 1,78 + 1,50 + 1,60 + 1,46 + 1,45 = US$ 7,79.

As duas falhas que sobraram no `reactor-guard` são legítimas, e é por isso que
a tarefa fica como está: `timeout 600 ./mvnw test -pl x` e `cd x && ./mvnw
test -pl y` passaram pela barreira do agente. O enunciado pede que o problema
"não possa mais acontecer", e um comando embrulhado ou encadeado é o jeito
comum de ele acontecer. É uma tarefa no meio da faixa: resolvida em parte, com
o buraco nomeado. É o tipo de tarefa que distingue duas versões do harness.

Resultados em `tests/eval/results/baseline-2026-09-27.json` (1ª passada) e
`ref-2026-09-27-{bounce,reactor}.json` (re-rodadas), fora do git.

## Uso

```sh
# 1. as tarefas realmente falham sem agente? (barato, não gasta modelo)
python3 tests/eval/run-eval.py --validate

# 2. rodar a suíte (GASTA MODELO — cada tarefa é uma sessão headless)
python3 tests/eval/run-eval.py --run

# 3. A/B: mesma suíte, dois estados do harness
python3 tests/eval/run-eval.py --run --label antes
#   ...instala a mudança...
python3 tests/eval/run-eval.py --run --label depois
python3 tests/eval/run-eval.py --compare antes depois
```

Resultados em `tests/eval/results/<label>.json`, ignorado pelo git.

## O que é medido, e por quê cada um

| Métrica | Pergunta |
|---|---|
| `passed` | o agente terminou a tarefa? |
| `duration_s` | quanto tempo de parede custou |
| `turns` | quantas voltas o agente deu |
| `cost_usd` | quanto custou |
| `gate_blocks` | quantas vezes um gate do harness barrou o caminho |

`gate_blocks` é o mais interessante numa comparação A/B: um harness que passa a
bloquear mais **e** a terminar mais tarefas está funcionando; bloquear mais e
terminar menos é atrito puro, e é exatamente o que o dono já sentiu na pele
(item "Atrito de decisão" no BACKLOG).

## Escrever uma tarefa nova

`tests/eval/tasks/<id>.yaml`:

```yaml
id: reactor-guard
titulo: "Barreira contra -pl sem -am no Maven"
fix_commit: b7a7c72          # o conserto que já aconteceu
base_commit: 2319856         # o pai dele — onde o agente começa
acceptance_test: tests/test_maven_reactor_guard.py
acceptance_cmd: "python3 tests/test_maven_reactor_guard.py"
dificuldade: media
prompt: |
  O enunciado do problema COMO ELE ERA, sem a solução.
```

Regras que valem a pena respeitar:

- **O enunciado não pode entregar a solução.** Descreva o sintoma e o custo,
  como o BACKLOG descreveria; não diga qual arquivo criar nem qual regex usar.
  Um enunciado que descreve o conserto mede transcrição, não engenharia.
- **A tarefa tem de passar no `--validate`** (vermelha sem agente). Sem isso
  ela entra na conta como verde grátis.
- **Nem sempre-acerta, nem sempre-erra.** Tarefa que o harness acerta 100% das
  vezes não distingue duas versões dele; a que erra 100% também não. O sinal
  vive no meio, então a suíte precisa de dificuldade variada — e a coluna
  `dificuldade` existe para que isso seja verificável em vez de torcido.
- **Barata o bastante para rodar.** Uma suíte que ninguém roda por custo é uma
  suíte que não existe.
